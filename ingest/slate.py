"""Perakit slate: gabungkan semua fetcher menjadi MatchData per laga — Tahap 2b.

SOP langkah 2–3: untuk setiap laga, tarik jadwal/stats, cedera, dan harga
(jup.ag + pembanding), lalu nilai dengan ``validate.checks`` menjadi
OK / HOLD / DATA_INCOMPLETE.

KONTRAK ANTAR WORKER: modul ini memakai fetcher pasar/NBA dari worker
paralel (``ingest.jupiter``, ``ingest.odds_api``, ``ingest.kalshi``,
``ingest.polymarket``, ``ingest.espn``, ``ingest.stats_nba``,
``ingest.nba_injury_pdf``, ``ingest.rotowire``, ``ingest.bbref``,
``ingest.matching``, ``engine.devig``) lewat import MALAS: bila modul atau
fungsinya belum ada, fetch itu dicatat gagal (``ok=False``) dan slate
tetap dirakit — satu fetcher yang belum tersedia tidak boleh mematikan
analisis. Fetcher bola (``premier_league``, ``understat``) adalah modul
sendiri di paket ini.

ATURAN PEMBANDING p_market (DECISIONS.md P1–P4 + keputusan user 2b):
sportsbook dulu (Odds API devig → ESPN odds devig, bola saja), Kalshi
HANYA bila tidak ada pembanding sportsbook untuk pasar itu. Bila p_market
akhirnya dari Kalshi, entri pasar itu berlabel ``PEMBANDING_KALSHI``
(harga Kalshi kurang tajam dibanding sportsbook; Tahap 3 meneruskan label
ini ke kaki). Polymarket TIDAK dipakai sebagai pembanding (P2) — hanya
untuk ``jup_markup``. Urutan relatif langkah sportsbook dibaca dari
playstyle.yaml (``comparison.order``); Kalshi selalu terakhir apa pun
urutannya di config.

OUTCOME: ``outcome`` di pasar jup.ag ternormalisasi adalah JUDUL pasar
(nama tim untuk moneyline/spread, "Over"/"Under" untuk total, "Both Teams
to Score" untuk BTTS) — bukan kata sisi. Sisi kanonik (home/away/draw/
over/under/yes) dipecahkan dari judul + tim laga (``_resolve_outcome_side``)
dan dicatat sebagai kunci ``side`` di tiap entri pasar.

GARIS (spread/total): pembanding hanya sah bila garisnya SAMA PERSIS
dengan garis jup.ag — peluang untuk garis lain adalah peluang yang lain.
Entri pasar spread/total mencatat ``comparison_line`` (garis pembanding
yang dipakai, atau None) dan ``line_matched`` (true bila ada pembanding
dengan garis yang sama). Garis spread Kalshi adalah MAGNITUDO (selalu
positif: "X wins by more than 1.5"), jadi dicocokkan dengan |garis jup|.

KOMPLEMEN KALSHI (identitas pasar biner, bukan tebakan): Kalshi hanya
punya pasar Over untuk total dan pasar "menang dengan selisih > X" untuk
spread. Under = sisi No pasar Over yang sama (p = 1 − p_over); spread
pihak underdog (garis +) = 1 − p pasar lawan ("lawan menang > |garis|").
Bila p_market dihitung dengan komplemen, entri pasar mencatat
``p_market_complement: true``. Pasar spread underdog TIDAK PERNAH
dicocokkan ke pasar Kalshi tim yang sama (itu peluang kejadian lain).

LABEL LAGA (ekstensi 2b, kunci ``labels`` pada tiap MatchData — ditambahkan
ke schemas/match_data.schema.json sebagai kunci opsional oleh koordinator
2b, lihat ingest/README.md): ``TANPA_XG`` bila bola tanpa xG (B4),
``MODEL_ONLY`` bila TIDAK SATU PUN pasar di laga itu punya p_market (D2).
Label pasar (kunci ``labels`` pada tiap entri market_prices):
``PEMBANDING_KALSHI`` bila p_market pasar itu dari Kalshi.

Ambang dibaca dari config, bukan hardcode: ``stale_hours`` dari
playstyle.yaml ``data.stale_hours_injury_lineup`` (diteruskan ke
validate), urutan pembanding dari ``comparison.order``.
"""

from __future__ import annotations

import importlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from validate.checks import validate_match_data

from . import premier_league, understat
from .common import FetchResult, now_iso

# Jenis pasar jup.ag yang dipakai (DECISIONS.md C: sportsMarketType).
JUP_MARKET_TYPES = frozenset({"moneyline", "spreads", "totals", "both_teams_to_score"})

# Langkah pembanding yang berasal dari sportsbook (didahulukan atas Kalshi).
SPORTSBOOK_STEPS = ("odds_api_devig", "espn_odds_devig")
KALSHI_STEP = "kalshi"

# Pemetaan liga bola ke kode yang dipakai tiap fetcher.
_KALSHI_LEAGUES = {"EPL": "epl", "LaLiga": "laliga"}
_ESPN_ODDS_LEAGUES = {"EPL": "eng.1"}

# Kunci nama tim yang mungkin dipakai baris stats (bentuk data mentah
# tiap fetcher tidak semuanya terikat kontrak — coba semuanya).
_TEAM_NAME_KEYS = ("team", "team_name", "name", "TEAM_NAME", "Team")

# Kunci ringkasan event ESPN yang aman dicatat (hindari dump event mentah
# yang besar ke dalam stats).
_ESPN_EVENT_KEYS = (
    "id",
    "name",
    "date",
    "start_time",
    "commence_time",
    "status",
    "home_team",
    "away_team",
    "home_record",
    "away_record",
    "venue",
)


def _normalize_simple(name: object) -> str:
    """Normalisasi nama untuk pencocokan fallback (huruf kecil, alfanumerik)."""
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def _slug(name: str) -> str:
    """Slug pendek untuk match_id hasil generate."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "tim"


def _parse_line(value: object) -> float | None:
    """Parse garis (spread/total) menjadi float; None bila tidak ada/tidak sah."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _to_number(value: object) -> float | None:
    """Parse angka (int/float/string angka) menjadi float; None bila tidak sah.

    Odds Amerika ESPN disimpan sebagai string ("-150"); ``american_to_decimal``
    hanya menerima angka, jadi konversi ini wajib sebelum devig.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _load_module(dotted: str):
    """Import malas satu modul; None bila modul belum ada."""
    try:
        return importlib.import_module(dotted)
    except ImportError:
        return None


def _failed_fetch(source: str, tier: int, error: str, attempted: bool) -> FetchResult:
    """FetchResult gagal standar (fetch tidak pernah melempar ke slate)."""
    return FetchResult(
        source=source,
        tier=tier,
        fetched_at=now_iso(),
        ok=False,
        error=error,
        extra={"attempted": attempted},
    )


def _fetch(
    module_name: str,
    func_name: str,
    source: str,
    tier: int,
    *args: Any,
    **kwargs: Any,
) -> FetchResult:
    """Panggil satu fetcher kontrak; kegagalan apa pun menjadi FetchResult ok=False.

    Modul belum ada, fungsi belum ada, exception di dalam fetcher, atau
    hasil bukan FetchResult — semuanya dicatat sebagai fetch gagal, bukan
    exception, agar slate tetap bisa dirakit (fail-closed per fetch).
    """
    module = _load_module(module_name)
    if module is None:
        return _failed_fetch(
            source, tier, f"modul_belum_tersedia: {module_name}", attempted=False
        )
    func = getattr(module, func_name, None)
    if func is None:
        return _failed_fetch(
            source,
            tier,
            f"fungsi_belum_tersedia: {module_name}.{func_name}",
            attempted=False,
        )
    try:
        result = func(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - satu fetcher rusak != slate mati
        return _failed_fetch(
            source, tier, f"{type(exc).__name__}: {exc}", attempted=True
        )
    if not isinstance(result, FetchResult):
        return _failed_fetch(
            source,
            tier,
            f"hasil_bukan_fetchresult: {type(result).__name__}",
            attempted=True,
        )
    return result


def _resolve_matcher():
    """Kembalikan fungsi teams_match(a, b, sport); fallback bila modul belum ada.

    Fallback (best-effort): nama ternormalisasi sama persis, atau salah
    satunya substring dari yang lain ("lakers" cocok dengan
    "los angeles lakers"). Modul ``ingest.matching`` yang asli menangani
    alias/singkatan dengan benar bila sudah ada.
    """
    module = _load_module("ingest.matching")
    func = getattr(module, "teams_match", None) if module is not None else None
    if func is not None:

        def _match(a: object, b: object, sport: str) -> bool:
            try:
                return bool(func(a, b, sport))
            except Exception:  # noqa: BLE001 - jatuh ke fallback
                return _fallback_match(a, b)

        return _match
    return _fallback_match


def _fallback_match(a: object, b: object, sport: str = "") -> bool:
    """Pencocokan nama tim fallback (tanpa modul matching)."""
    left, right = _normalize_simple(a), _normalize_simple(b)
    if not left or not right:
        return False
    if left == right:
        return True
    return left in right or right in left


def _resolve_devig():
    """Kembalikan (devig, american_to_decimal) dari engine.devig (bisa None)."""
    module = _load_module("engine.devig")
    if module is None:
        return None, None
    return (
        getattr(module, "devig", None),
        getattr(module, "american_to_decimal", None),
    )


def _load_playstyle(playstyle: dict | None) -> dict:
    """Pakai playstyle yang diberikan, atau muat dari config/playstyle.yaml."""
    if playstyle is not None:
        return playstyle
    try:
        import config as config_mod
    except ImportError as exc:
        raise RuntimeError(
            "tidak bisa memuat config/playstyle.yaml (modul config tidak "
            "ditemukan) — teruskan playstyle secara eksplisit"
        ) from exc
    return config_mod.load_playstyle()


class _Builder:
    """Perakit satu slate (satu sport, satu tanggal)."""

    def __init__(
        self,
        sport: str,
        date: str,
        league: str,
        playstyle: dict | None,
    ) -> None:
        """Siapkan builder; ``playstyle`` None = muat dari config."""
        cfg = _load_playstyle(playstyle)
        try:
            self.stale_hours = cfg["data"]["stale_hours_injury_lineup"]
        except (KeyError, TypeError) as exc:
            raise ValueError(
                "playstyle.yaml kehilangan data.stale_hours_injury_lineup"
            ) from exc
        try:
            configured_order = list(cfg["comparison"]["order"])
        except (KeyError, TypeError) as exc:
            raise ValueError("playstyle.yaml kehilangan comparison.order") from exc
        # Sportsbook dulu (urutan relatif sesuai config), Kalshi selalu
        # terakhir — keputusan user 2b, apa pun urutan di config.
        sportsbook = [s for s in configured_order if s in SPORTSBOOK_STEPS]
        other = [
            s
            for s in configured_order
            if s not in SPORTSBOOK_STEPS and s != KALSHI_STEP
        ]
        self.comparison_order = sportsbook + other
        if KALSHI_STEP in configured_order:
            self.comparison_order.append(KALSHI_STEP)
        self.sport = sport
        self.date = date
        self.league = league
        self.teams_match = _resolve_matcher()
        self.devig_fn, self.american_fn = _resolve_devig()
        poly = _load_module("ingest.polymarket")
        self._poly_find_token = (
            getattr(poly, "find_token_for_jup_market", None)
            if poly is not None
            else None
        )
        self._poly_orderbook = (
            getattr(poly, "fetch_orderbook", None) if poly is not None else None
        )
        self._poly_markup = (
            getattr(poly, "compute_jup_markup", None) if poly is not None else None
        )
        kalshi_mod = _load_module("ingest.kalshi")
        self._kalshi_probability = (
            getattr(kalshi_mod, "kalshi_probability", None)
            if kalshi_mod is not None
            else None
        )
        # Bundle hasil fetch (diisi fetch_all).
        self.jupiter: FetchResult | None = None
        self.odds_api: FetchResult | None = None
        self.kalshi: dict[str, FetchResult] = {}
        self.espn_odds: FetchResult | None = None
        self.scoreboard: FetchResult | None = None
        self.standings: FetchResult | None = None
        self.advanced: FetchResult | None = None
        self.injuries: list[FetchResult] = []
        self.espn_scoreboard: FetchResult | None = None
        self.fixtures: FetchResult | None = None
        self.xg: FetchResult | None = None
        self.football_injuries: FetchResult | None = None
        self.odds_api_calls = 0
        self.odds_api_credits = 0

    # -- fetch sekali per slate -------------------------------------------

    def fetch_all(self) -> None:
        """Tarik semua data sekali (dipakai ulang untuk semua laga)."""
        # Tanpa limit: fetch_sports_markets memindai SEMUA event sports
        # (paginasi, safety cap 2000 di modul jupiter). JANGAN dibatasi
        # 100 — keputusan user 2b (probe 100 event melewatkan pasar).
        self.jupiter = _fetch(
            "ingest.jupiter",
            "fetch_sports_markets",
            "Jupiter Prediction API",
            1,
        )
        sport_key = "basketball_nba" if self.sport == "nba" else "soccer_epl"
        self.odds_api = _fetch(
            "ingest.odds_api",
            "fetch_odds",
            "The Odds API",
            2,
            sport_key,
            markets="h2h,spreads,totals",
            regions="eu",
        )
        if self.odds_api.extra.get("attempted", True):
            self.odds_api_calls = 1
            self.odds_api_credits = self.odds_api.credits_used
        kalshi_league = (
            "nba" if self.sport == "nba" else _KALSHI_LEAGUES.get(self.league)
        )
        if kalshi_league is not None:
            for kind, func_name in (
                ("moneyline", "fetch_moneyline_markets"),
                ("spread", "fetch_spread_markets"),
                ("total", "fetch_total_markets"),
            ):
                self.kalshi[kind] = _fetch(
                    "ingest.kalshi",
                    func_name,
                    "Kalshi API",
                    2,
                    kalshi_league,
                )
        if self.sport == "football" and self.league in _ESPN_ODDS_LEAGUES:
            self.espn_odds = _fetch(
                "ingest.espn",
                "fetch_odds_football",
                "ESPN odds",
                2,
                league=_ESPN_ODDS_LEAGUES[self.league],
            )
        if self.sport == "nba":
            self.scoreboard = _fetch(
                "ingest.stats_nba",
                "fetch_scoreboard",
                "stats.nba.com",
                1,
                self.date,
            )
            self.standings = _fetch(
                "ingest.stats_nba", "fetch_standings", "stats.nba.com", 1
            )
            # BBRef: season=2027 = musim berjalan 2026-27 (konvensi:
            # tahun musim berakhir; 2026 = musim 2025-26 yang sudah lewat).
            self.advanced = _fetch(
                "ingest.bbref",
                "fetch_team_advanced",
                "Basketball-Reference",
                2,
                season=2027,
            )
            self.injuries = [
                _fetch(
                    "ingest.nba_injury_pdf",
                    "fetch_report",
                    "Official NBA Injury Report",
                    1,
                ),
                _fetch("ingest.rotowire", "fetch_injuries", "Rotowire", 2),
                _fetch(
                    "ingest.espn",
                    "fetch_injuries_nba",
                    "ESPN injuries",
                    2,
                ),
            ]
            self.espn_scoreboard = _fetch(
                "ingest.espn",
                "fetch_scoreboard",
                "ESPN",
                2,
                "nba",
                self.date,
            )
        else:
            if self.league == "EPL":
                try:
                    self.fixtures = premier_league.fetch_fixtures()
                except Exception as exc:  # noqa: BLE001 - fetch gagal != slate mati
                    self.fixtures = _failed_fetch(
                        premier_league.SOURCE,
                        premier_league.TIER,
                        f"{type(exc).__name__}: {exc}",
                        attempted=True,
                    )
            try:
                self.xg = understat.fetch_xg(league=self.league, season=2025)
            except Exception as exc:  # noqa: BLE001 - fetch gagal != slate mati
                self.xg = _failed_fetch(
                    understat.SOURCE,
                    understat.TIER,
                    f"{type(exc).__name__}: {exc}",
                    attempted=True,
                )
            # Scoreboard ESPN bola hanya EPL (eng.1); liga lain tidak
            # punya sumber jadwal ESPN di kontrak 2b.
            if self.league == "EPL":
                self.espn_scoreboard = _fetch(
                    "ingest.espn",
                    "fetch_scoreboard",
                    "ESPN",
                    2,
                    "epl",
                    self.date,
                )
                # FPL API hanya EPL; liga lain tidak punya sumber cedera
                # bola di kontrak 2b (laga itu tetap DATA_INCOMPLETE jujur).
                try:
                    self.football_injuries = premier_league.fetch_injuries_fpl()
                except Exception as exc:  # noqa: BLE001 - fetch gagal != slate mati
                    self.football_injuries = _failed_fetch(
                        premier_league.FPL_SOURCE,
                        premier_league.TIER,
                        f"{type(exc).__name__}: {exc}",
                        attempted=True,
                    )

    # -- daftar laga ------------------------------------------------------

    def match_list(self, matches: list[dict] | None) -> list[dict]:
        """Normalisasi daftar laga input; None = semua laga hari itu."""
        if matches is not None:
            normalized = []
            for entry in matches:
                home = entry.get("home")
                away = entry.get("away")
                if not home or not away:
                    raise ValueError(f"entri matches tanpa home/away: {entry!r}")
                match_id = entry.get("match_id") or (
                    f"{self.sport}-{self.date}-{_slug(str(home))}"
                    f"-{_slug(str(away))}"
                )
                normalized.append(
                    {
                        "home": home,
                        "away": away,
                        "match_id": match_id,
                        "start_time": entry.get("start_time"),
                        "league": entry.get("league"),
                    }
                )
            return normalized
        return self._discover_matches()

    def _discover_matches(self) -> list[dict]:
        """Semua laga hari itu dari sumber jadwal (bila matches=None)."""
        found: list[dict] = []
        if self.sport == "nba":
            games = (
                self.scoreboard.data
                if self.scoreboard is not None
                and self.scoreboard.ok
                and isinstance(self.scoreboard.data, list)
                else []
            )
            for game in games:
                if not isinstance(game, dict):
                    continue
                home = game.get("home_team")
                away = game.get("away_team")
                if home and away:
                    found.append(
                        {
                            "home": home,
                            "away": away,
                            "match_id": (
                                f"nba-{self.date}-{_slug(str(home))}"
                                f"-{_slug(str(away))}"
                            ),
                            "start_time": game.get("start_time"),
                            "league": "NBA",
                        }
                    )
            return found
        # Bola: fixtures PL (EPL) dalam ±1 hari dari tanggal slate.
        fixtures = (
            self.fixtures.data
            if self.fixtures is not None
            and self.fixtures.ok
            and isinstance(self.fixtures.data, list)
            else []
        )
        try:
            target = datetime.fromisoformat(self.date).date()
        except ValueError:
            target = None
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
            home = fixture.get("home_team")
            away = fixture.get("away_team")
            if not home or not away:
                continue
            if target is not None:
                kickoff = _parse_time(fixture.get("kickoff"))
                if kickoff is None or abs((kickoff.date() - target).days) > 1:
                    continue
            found.append(
                {
                    "home": home,
                    "away": away,
                    "match_id": (
                        f"football-{self.date}-{_slug(str(home))}"
                        f"-{_slug(str(away))}"
                    ),
                    "start_time": fixture.get("kickoff"),
                    "league": self.league,
                }
            )
        return found

    # -- perakitan per laga -----------------------------------------------

    def build(self, matches: list[dict] | None, slate_id: str | None) -> dict:
        """Rakit slate lengkap untuk satu sport + tanggal."""
        self.fetch_all()
        entries = self.match_list(matches)
        assembled = [self.assemble(entry) for entry in entries]
        summary = {
            "matches": len(assembled),
            "ok": sum(1 for m in assembled if m["status"] == "OK"),
            "data_incomplete": sum(
                1 for m in assembled if m["status"] == "DATA_INCOMPLETE"
            ),
            "hold": sum(1 for m in assembled if m["status"] == "HOLD"),
            "model_only": sum(1 for m in assembled if "MODEL_ONLY" in m["labels"]),
            "tanpa_xg": sum(1 for m in assembled if "TANPA_XG" in m["labels"]),
        }
        return {
            "slate_id": slate_id or f"slate-{self.sport}-{self.date}",
            "sport": self.sport,
            "slate_date": self.date,
            "generated_at": now_iso(),
            "matches": assembled,
            "summary": summary,
            "odds_api": {
                "calls": self.odds_api_calls,
                "credits_used": self.odds_api_credits,
            },
        }

    def assemble(self, entry: dict) -> dict:
        """Rakit satu MatchData (+ ekstensi labels 2b) untuk satu laga."""
        home, away = entry["home"], entry["away"]
        sources: list[dict] = []
        missing: list[str] = []
        conflicts: list[dict] = []
        labels: list[str] = []
        stats: dict[str, Any] = {}
        injuries: list[dict] = []
        market_prices = self._market_prices(
            home, away, sources, missing, entry.get("start_time")
        )

        if self.sport == "nba":
            self._nba_stats(home, away, stats, sources, missing)
            injuries, nba_conflicts = self._nba_injuries(home, away, sources)
            conflicts.extend(nba_conflicts)
            if all(result is None or not result.ok for result in self.injuries):
                missing.append("nba_injuries")
        else:
            self._football_stats(home, away, stats, sources, missing, labels)
            injuries, fb_conflicts = self._football_injuries(home, away, sources)
            conflicts.extend(fb_conflicts)
            if not any(
                isinstance(entry, dict)
                and entry.get("data_kind") == "football_lineup_injuries"
                for entry in sources
            ):
                missing.append("football_lineup_injuries")

        if market_prices and all(
            item.get("p_market") is None for item in market_prices.values()
        ):
            labels.append("MODEL_ONLY")

        match: dict[str, Any] = {
            "match_id": entry["match_id"],
            "sport": self.sport,
            "fetched_at": now_iso(),
            "status": "OK",
            "sources": sources,
            "stats": stats,
            "injuries": injuries,
            "lineup": None,
            "market_prices": market_prices,
            "missing": sorted(set(missing)),
            "conflicts": conflicts,
            "status_reason": None,
            "labels": labels,
        }
        verdict = validate_match_data(match, self.stale_hours)
        match["status"] = verdict["status"]
        match["status_reason"] = (
            "; ".join(verdict["reasons"]) if verdict["reasons"] else None
        )
        return match

    # -- stats NBA --------------------------------------------------------

    def _nba_stats(
        self,
        home: str,
        away: str,
        stats: dict[str, Any],
        sources: list[dict],
        missing: list[str],
    ) -> None:
        """Isi stats NBA dari scoreboard + standings + BBRef (apa adanya)."""
        schedule_ok = False
        if self.scoreboard is not None and self.scoreboard.ok:
            game = _find_in_list(
                self.scoreboard.data, home, away, self.teams_match, self.sport
            )
            if game is not None:
                stats["scoreboard"] = {
                    "game_id": game.get("game_id"),
                    "start_time": game.get("start_time"),
                    "status": game.get("status"),
                }
                schedule_ok = True
                _record_source(sources, "nba_schedule_stats", self.scoreboard)
        if self.standings is not None and self.standings.ok:
            rows = _find_team_rows(
                self.standings.data, home, away, self.teams_match, self.sport
            )
            if rows:
                stats["standings"] = rows
                schedule_ok = True
                _record_source(sources, "nba_schedule_stats", self.standings)
        if self.advanced is not None and self.advanced.ok:
            rows = _find_team_rows(
                self.advanced.data, home, away, self.teams_match, self.sport
            )
            if rows:
                stats["advanced"] = rows
                schedule_ok = True
                _record_source(sources, "nba_schedule_stats", self.advanced)
        # Jadwal cadangan: scoreboard ESPN (jenjang 2) bila stats.nba.com
        # tidak memberi apa-apa untuk laga ini.
        if (
            not schedule_ok
            and self.espn_scoreboard is not None
            and self.espn_scoreboard.ok
        ):
            event = _find_in_list(
                self.espn_scoreboard.data,
                home,
                away,
                self.teams_match,
                self.sport,
            )
            summary = _espn_event_summary(event)
            if summary:
                stats["espn_scoreboard"] = summary
                _record_source(sources, "nba_schedule_stats", self.espn_scoreboard)
        if all(
            result is None or not result.ok
            for result in (
                self.scoreboard,
                self.standings,
                self.advanced,
                self.espn_scoreboard,
            )
        ):
            missing.append("nba_schedule_stats")

    def _nba_injuries(
        self, home: str, away: str, sources: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """Gabung 3 sumber cedera NBA; konflik dicatat, bukan dipilih diam-diam."""
        usable = [r for r in self.injuries if r is not None and r.ok]
        for result in usable:
            _record_source(sources, "nba_injuries", result)
        return _merge_injuries(usable, home, away, self.teams_match, self.sport)

    # -- stats bola -------------------------------------------------------

    def _football_stats(
        self,
        home: str,
        away: str,
        stats: dict[str, Any],
        sources: list[dict],
        missing: list[str],
        labels: list[str],
    ) -> None:
        """Isi stats bola: fixtures PL + xG (bila ada) + scoreboard ESPN."""
        if self.fixtures is not None and self.fixtures.ok:
            fixture = _find_fixture(
                self.fixtures.data, home, away, self.date, self.teams_match
            )
            if fixture is not None:
                stats["fixture"] = {
                    "kickoff": fixture.get("kickoff"),
                    "status": fixture.get("status"),
                    "matchweek": fixture.get("matchweek"),
                }
                _record_source(sources, "football_stats_xg", self.fixtures)
        if self.xg is not None and self.xg.ok:
            xg_rows = _find_xg_rows(self.xg.data, home, away, self.teams_match)
            if xg_rows:
                stats["xg"] = xg_rows
                _record_source(sources, "football_stats_xg", self.xg)
        else:
            # B4: tanpa xG, bola jalan TANPA_XG (bukan ditebak).
            labels.append("TANPA_XG")
        if self.espn_scoreboard is not None and self.espn_scoreboard.ok:
            event = _find_in_list(
                self.espn_scoreboard.data,
                home,
                away,
                self.teams_match,
                self.sport,
            )
            summary = _espn_event_summary(event)
            if summary:
                stats["espn_scoreboard"] = summary
                _record_source(sources, "football_stats_xg", self.espn_scoreboard)
        if all(
            result is None or not result.ok
            for result in (self.fixtures, self.xg, self.espn_scoreboard)
        ):
            missing.append("football_stats_xg")

    def _football_injuries(
        self, home: str, away: str, sources: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """Cedera bola: FPL API (jenjang 1) + scoreboard ESPN bila ada.

        FPL adalah satu-satunya sumber cedera bola khusus di 2b (sumber
        baru dari integrasi — butuh ratifikasi user, lihat
        premier_league.py); dengan 1 sumber, validate memberi HOLD (B2
        butuh 2 sumber). Bila event ESPN juga memuat daftar cedera, kedua
        sumber digabung dan konflik dicatat. Bila tidak ada sumber yang
        berhasil, laga ini punya 0 sumber cedera (DATA_INCOMPLETE jujur).
        """
        usable: list[FetchResult] = []
        if self.football_injuries is not None and self.football_injuries.ok:
            usable.append(self.football_injuries)
            _record_source(sources, "football_lineup_injuries", self.football_injuries)
        if self.espn_scoreboard is not None and self.espn_scoreboard.ok:
            event = _find_in_list(
                self.espn_scoreboard.data,
                home,
                away,
                self.teams_match,
                self.sport,
            )
            if isinstance(event, dict):
                raw = event.get("injuries")
                if isinstance(raw, list) and raw:
                    pseudo = FetchResult(
                        source=self.espn_scoreboard.source,
                        tier=self.espn_scoreboard.tier,
                        fetched_at=self.espn_scoreboard.fetched_at,
                        ok=True,
                        data=raw,
                    )
                    _record_source(sources, "football_lineup_injuries", pseudo)
                    usable.append(pseudo)
        if not usable:
            return [], []
        return _merge_injuries(usable, home, away, self.teams_match, self.sport)

    # -- harga pasar ------------------------------------------------------

    def _market_prices(
        self,
        home: str,
        away: str,
        sources: list[dict],
        missing: list[str],
        start_time: str | None = None,
    ) -> dict[str, dict]:
        """Rakit market_prices untuk satu laga dari pasar jup.ag + pembanding.

        ``start_time`` (jam mulai laga ini) dipakai untuk membedakan dua
        laga pasangan tim yang sama: pasangan yang sama bisa main dua kali
        (malam ini + rematch minggu depan), dan tanpa pembedaan jam, pasar
        laga yang salah bisa terpilih (bug demo 2b: Suns-Jazz memakai
        harga rematch 29 Nov, bukan malam ini). Per kunci pasar, hanya
        pasar yang start_time-nya terdekat dengan laga ini yang dipakai.
        """
        prices: dict[str, dict] = {}
        if self.jupiter is None or not self.jupiter.ok:
            missing.append("jup_prices")
            if self._comparison_fetch_failed():
                missing.append("comparison_prices")
            return prices
        markets = self.jupiter.data if isinstance(self.jupiter.data, list) else []
        matched = [
            m
            for m in markets
            if isinstance(m, dict)
            and str(m.get("market_type", "")).lower() in JUP_MARKET_TYPES
            and self._jup_market_is_match(m, home, away)
        ]
        if matched:
            _record_source(sources, "jup_prices", self.jupiter)
        by_key: dict[str, list[dict]] = {}
        for market in matched:
            side = _resolve_outcome_side(market, self.teams_match, self.sport)
            by_key.setdefault(_market_key(market, side), []).append(market)
        for key, group in by_key.items():
            market = _closest_by_time(group, start_time, "start_time") or group[0]
            entry = self._market_entry(market)
            prices[key] = entry
        if any(e.get("p_market") is not None for e in prices.values()):
            _record_source_comparison(sources, self, prices)
        elif self._comparison_fetch_failed():
            missing.append("comparison_prices")
        return prices

    def _comparison_fetch_failed(self) -> bool:
        """True bila SEMUA fetch pembanding yang dicoba gagal."""
        attempted = []
        for result in [self.odds_api, self.espn_odds, *self.kalshi.values()]:
            if result is None:
                continue
            if not result.extra.get("attempted", True):
                continue
            attempted.append(result)
        return bool(attempted) and all(not r.ok for r in attempted)

    def _jup_market_is_match(self, market: dict, home: str, away: str) -> bool:
        """Apakah pasar jup.ag ini milik laga (home, away) + sport ini?"""
        market_sport = _normalize_simple(market.get("sport"))
        if self.sport == "nba" and market_sport in ("football", "soccer"):
            return False
        if self.sport == "football" and market_sport in ("nba", "basketball"):
            return False
        return self.teams_match(
            market.get("home_team"), home, self.sport
        ) and self.teams_match(market.get("away_team"), away, self.sport)

    def _market_entry(self, market: dict) -> dict:
        """Rakit satu entri market_prices (harga jup + markup + p_market)."""
        jup_price = market.get("yes_price_cents")
        jup_provider = market.get("provider")
        market_type = str(market.get("market_type", "")).lower()
        side = _resolve_outcome_side(market, self.teams_match, self.sport)
        markup, markup_reason, markup_source = self._jup_markup(market, jup_price)
        p_market, comparison_source, missing_reason, comp_line, complement = (
            self._resolve_p_market(market, side, jup_provider)
        )
        labels: list[str] = []
        if comparison_source == KALSHI_STEP:
            labels.append("PEMBANDING_KALSHI")
        entry: dict[str, Any] = {
            "market_type": market_type,
            "line": market.get("line"),
            "outcome": market.get("outcome"),
            "side": side,
            "jup_price_cents": jup_price,
            "jup_provider": jup_provider,
            "jup_markup_cents": markup,
            "jup_markup_reason": markup_reason,
            "jup_markup_source": markup_source,
            "p_market": p_market,
            "comparison_source": comparison_source,
            "p_market_missing_reason": missing_reason,
            "p_market_complement": complement,
            "labels": labels,
        }
        if market_type in ("spreads", "totals"):
            jup_line = _parse_line(market.get("line"))
            entry["comparison_line"] = comp_line
            # Spread: garis Kalshi adalah magnitudo, garis sportsbook
            # bertanda — keduanya "cocok" bila |garis| sama.
            if market_type == "spreads":
                entry["line_matched"] = (
                    comp_line is not None
                    and jup_line is not None
                    and abs(comp_line) == abs(jup_line)
                )
            else:
                entry["line_matched"] = (
                    comp_line is not None
                    and jup_line is not None
                    and comp_line == jup_line
                )
        return entry

    def _jup_markup(
        self, market: dict, jup_price_cents: object
    ) -> tuple[float | None, str | None, str | None]:
        """Selisih harga jup.ag vs midpoint orderbook Polymarket (BUKAN edge).

        Mengembalikan (markup, alasan_gagal, sumber_mid). ``sumber_mid``:
        "book" (midpoint dari bid/ask orderbook) atau "midpoint"
        (fallback endpoint /midpoint saat orderbook kosong — mid dari
        pasar ilikuid bisa basi/menyesatkan, mis. 42,5¢ untuk pasar
        spread -4.5 yang praktis tidak diperdagangkan; pembaca wajib
        memeriksa sumber ini sebelum memakai markup).
        """
        if (
            self._poly_find_token is None
            or self._poly_orderbook is None
            or self._poly_markup is None
        ):
            return None, "modul_polymarket_belum_tersedia", None
        if jup_price_cents is None:
            return None, "harga_jup_tidak_ada", None
        try:
            token = self._poly_find_token(market)
        except Exception as exc:  # noqa: BLE001 - markup gagal != pasar gagal
            return None, f"find_token_gagal: {exc}", None
        if not token:
            return None, "polymarket_token_tidak_ditemukan", None
        try:
            orderbook = self._poly_orderbook(token)
        except Exception as exc:  # noqa: BLE001 - markup gagal != pasar gagal
            return None, f"orderbook_gagal: {exc}", None
        if not isinstance(orderbook, FetchResult) or not orderbook.ok:
            error = (
                orderbook.error
                if isinstance(orderbook, FetchResult)
                else "bukan_fetchresult"
            )
            return None, f"orderbook_gagal: {error}", None
        mid = (orderbook.data or {}).get("mid_cents")
        if mid is None:
            return None, "orderbook_tanpa_mid", None
        try:
            markup = self._poly_markup(jup_price_cents, mid)
        except Exception as exc:  # noqa: BLE001 - markup gagal != pasar gagal
            return None, f"compute_markup_gagal: {exc}", None
        return markup, None, orderbook.extra.get("source")

    def _resolve_p_market(
        self, market: dict, side: str | None, jup_provider: object
    ) -> tuple[float | None, str | None, str | None, float | None, bool]:
        """Pilih p_market per urutan pembanding (sportsbook dulu, Kalshi terakhir).

        Mengembalikan (p_market, comparison_source, missing_reason,
        comparison_line, complement). Garis spread/total harus sama persis
        dengan garis jup.ag di semua sumber (spread Kalshi dicocokkan
        dengan magnitudo |garis|). Bila sisi outcome tidak bisa dipecahkan,
        tidak ada pembanding yang bisa dipakai (fail-closed).
        """
        if side is None:
            return None, None, "outcome_tidak_dikenali", None, False
        reasons: list[str] = []
        for step in self.comparison_order:
            if step == "odds_api_devig":
                prob, reason, line, complement = self._p_from_odds_api(market, side)
            elif step == "espn_odds_devig":
                if self.sport != "football":
                    continue
                prob, reason, line, complement = self._p_from_espn_odds(market, side)
            elif step == KALSHI_STEP:
                if str(jup_provider or "").lower() == "kalshi":
                    reasons.append("kalshi_dilewati_p2_asal_kalshi")
                    continue
                prob, reason, line, complement = self._p_from_kalshi(market, side)
            else:
                reasons.append(f"langkah_pembanding_tidak_dikenal: {step}")
                continue
            if prob is not None:
                return prob, step, None, line, complement
            reasons.append(reason or f"{step}_gagal")
        return None, None, "; ".join(reasons) if reasons else None, None, False

    def _devig_probs(self, odds: list[float]) -> list[float] | None:
        """Devig satu daftar odds desimal; None bila modul/hasil tidak sah."""
        if self.devig_fn is None or not odds:
            return None
        try:
            probs = self.devig_fn(odds)
        except Exception:  # noqa: BLE001 - devig gagal = pembanding gagal
            return None
        if (
            not isinstance(probs, list)
            or len(probs) != len(odds)
            or any(not isinstance(p, (int, float)) or not 0 <= p <= 1 for p in probs)
        ):
            return None
        return [float(p) for p in probs]

    def _p_from_odds_api(
        self, market: dict, side: str
    ) -> tuple[float | None, str | None, float | None, bool]:
        """p_market dari devig sportsbook The Odds API (Pinnacle dulu)."""
        result = self.odds_api
        if result is None or not result.ok:
            error = result.error if result is not None else "tidak_dipanggil"
            return None, f"odds_api_gagal: {error}", None, False
        if self.devig_fn is None:
            return None, "modul_devig_belum_tersedia", None, False
        events = result.data if isinstance(result.data, list) else []
        # Odds API mengembalikan ~1 minggu laga: pasangan yang sama bisa
        # muncul dua kali — pilih event yang commence_time-nya terdekat
        # dengan jam mulai pasar jup.ag (bukan yang pertama di list).
        candidates = [
            item
            for item in events
            if isinstance(item, dict)
            and self.teams_match(
                item.get("home_team"), market.get("home_team"), self.sport
            )
            and self.teams_match(
                item.get("away_team"), market.get("away_team"), self.sport
            )
        ]
        event = _closest_by_time(candidates, market.get("start_time"), "commence_time")
        if event is None:
            return None, "odds_api_event_tidak_ditemukan", None, False
        bookmakers = event.get("bookmakers") or []
        if not bookmakers:
            return None, "odds_api_tanpa_bookmaker", None, False
        book = next(
            (b for b in bookmakers if str(b.get("key", "")).lower() == "pinnacle"),
            bookmakers[0],
        )
        market_type = str(market.get("market_type", "")).lower()
        key_map = {"moneyline": "h2h", "spreads": "spreads", "totals": "totals"}
        wanted = key_map.get(market_type)
        if wanted is None:
            return None, f"odds_api_tidak_mendukung_{market_type}", None, False
        target = next(
            (m for m in (book.get("markets") or []) if m.get("key") == wanted),
            None,
        )
        if target is None:
            return None, f"odds_api_pasar_{wanted}_tidak_ada", None, False
        outcomes = target.get("outcomes") or []
        if not outcomes:
            return None, f"odds_api_pasar_{wanted}_kosong", None, False
        jup_line = _parse_line(market.get("line"))
        # Pasangan outcomes yang relevan untuk devig: moneyline = semua;
        # totals = yang point-nya == garis; spreads = garis dan lawannya
        # (home -1.5 berpasangan dengan away +1.5).
        if market_type == "moneyline":
            relevant = list(outcomes)
        elif market_type == "totals":
            if jup_line is None:
                return None, "odds_api_garis_jup_tidak_ada", None, False
            relevant = [
                item for item in outcomes if _parse_line(item.get("point")) == jup_line
            ]
        else:  # spreads
            if jup_line is None:
                return None, "odds_api_garis_jup_tidak_ada", None, False
            relevant = [
                item
                for item in outcomes
                if _parse_line(item.get("point")) in (jup_line, -jup_line)
            ]
        if not relevant:
            return None, "odds_api_garis_tidak_cocok", None, False
        prices: list[float] = []
        our_index: int | None = None
        for index, item in enumerate(relevant):
            try:
                prices.append(float(item["price"]))
            except (KeyError, TypeError, ValueError):
                return None, "odds_api_harga_tidak_sah", None, False
            if not _odds_outcome_is_ours(
                item, side, market, self.teams_match, self.sport
            ):
                continue
            if market_type in ("spreads", "totals") and (
                _parse_line(item.get("point")) != jup_line
            ):
                continue
            our_index = index
        if our_index is None:
            return None, "odds_api_outcome_tidak_cocok", None, False
        probs = self._devig_probs(prices)
        if probs is None:
            return None, "odds_api_devig_gagal", None, False
        line_used = jup_line if market_type in ("spreads", "totals") else None
        return probs[our_index], None, line_used, False

    def _p_from_espn_odds(
        self, market: dict, side: str
    ) -> tuple[float | None, str | None, float | None, bool]:
        """p_market dari devig odds ESPN (BOLA SAJA — NBA tidak punya odds ESPN).

        Odds Amerika ESPN disimpan sebagai string ("-150") — dikonversi
        ke angka dulu karena ``american_to_decimal`` hanya menerima angka.
        """
        result = self.espn_odds
        if result is None or not result.ok:
            error = result.error if result is not None else "tidak_dipanggil"
            return None, f"espn_odds_gagal: {error}", None, False
        if self.devig_fn is None or self.american_fn is None:
            return None, "modul_devig_belum_tersedia", None, False
        events = result.data if isinstance(result.data, list) else []
        # Sama seperti Odds API: pasangan yang sama bisa muncul dua kali
        # — pilih event yang commence_time-nya terdekat dengan pasar jup.
        candidates = [
            item
            for item in events
            if isinstance(item, dict)
            and self.teams_match(
                item.get("home_team"), market.get("home_team"), self.sport
            )
            and self.teams_match(
                item.get("away_team"), market.get("away_team"), self.sport
            )
        ]
        event = _closest_by_time(candidates, market.get("start_time"), "commence_time")
        if event is None:
            return None, "espn_odds_event_tidak_ditemukan", None, False
        market_type = str(market.get("market_type", "")).lower()
        jup_line = _parse_line(market.get("line"))
        try:
            if market_type == "moneyline":
                moneyline = event.get("moneyline") or {}
                american = [
                    _to_number(moneyline.get("home")),
                    _to_number(moneyline.get("draw")),
                    _to_number(moneyline.get("away")),
                ]
                if any(o is None for o in american):
                    return None, "espn_moneyline_tidak_lengkap", None, False
                index = {"home": 0, "draw": 1, "away": 2}.get(side)
                if index is None:
                    return None, "espn_outcome_tidak_cocok", None, False
                probs = self._devig_probs(
                    [float(self.american_fn(o)) for o in american]
                )
                if probs is None:
                    return None, "espn_devig_gagal", None, False
                return probs[index], None, None, False
            if market_type == "spreads":
                spread = event.get("spread") or {}
                if side == "home":
                    line = _parse_line(spread.get("home_line"))
                    index = 0
                elif side == "away":
                    line = _parse_line(spread.get("away_line"))
                    index = 1
                else:
                    return None, "espn_outcome_tidak_cocok", None, False
                odds_pair = [
                    _to_number(spread.get("home_odds")),
                    _to_number(spread.get("away_odds")),
                ]
                if (
                    line is None
                    or jup_line is None
                    or line != jup_line
                    or any(o is None for o in odds_pair)
                ):
                    return None, "espn_garis_tidak_cocok", None, False
                probs = self._devig_probs(
                    [float(self.american_fn(o)) for o in odds_pair]
                )
                if probs is None:
                    return None, "espn_devig_gagal", None, False
                return probs[index], None, line, False
            if market_type == "totals":
                total = event.get("total") or {}
                line = _parse_line(total.get("line"))
                if line is None or jup_line is None or line != jup_line:
                    return None, "espn_garis_tidak_cocok", None, False
                odds_pair = [
                    _to_number(total.get("over_odds")),
                    _to_number(total.get("under_odds")),
                ]
                if side == "over":
                    index = 0
                elif side == "under":
                    index = 1
                else:
                    return None, "espn_outcome_tidak_cocok", None, False
                if any(o is None for o in odds_pair):
                    return None, "espn_odds_total_tidak_lengkap", None, False
                probs = self._devig_probs(
                    [float(self.american_fn(o)) for o in odds_pair]
                )
                if probs is None:
                    return None, "espn_devig_gagal", None, False
                return probs[index], None, line, False
            return None, f"espn_tidak_mendukung_{market_type}", None, False
        except (TypeError, ValueError) as exc:
            return None, f"espn_odds_tidak_sah: {exc}", None, False

    def _p_from_kalshi(
        self, market: dict, side: str
    ) -> tuple[float | None, str | None, float | None, bool]:
        """p_market dari midpoint bid/ask Kalshi (garis harus sama persis).

        Semantik Kalshi (terverifikasi probe kalshi_sports + cache):
        garis spread adalah MAGNITUDO ("X wins by more than 1.5" ->
        line 1.5); hanya ada pasar Over untuk total. Favorit spread
        (garis jup negatif) cocok langsung ke pasar tim yang sama;
        underdog spread (garis +) dan Under memakai KOMPLEMEN (1 - p)
        dari pasar lawan/Over — identitas pasar biner, dicatat lewat
        ``p_market_complement``. Pasar spread underdog TIDAK PERNAH
        dicocokkan ke pasar Kalshi tim yang sama (itu peluang lain).
        """
        market_type = str(market.get("market_type", "")).lower()
        kind_map = {
            "moneyline": "moneyline",
            "spreads": "spread",
            "totals": "total",
        }
        kind = kind_map.get(market_type)
        if kind is None:
            return None, f"kalshi_tidak_mendukung_{market_type}", None, False
        result = self.kalshi.get(kind)
        if result is None or not result.ok:
            error = result.error if result is not None else "tidak_dipanggil"
            return None, f"kalshi_{kind}_gagal: {error}", None, False
        if self._kalshi_probability is None:
            return None, "fungsi_kalshi_probability_belum_tersedia", None, False
        markets = result.data if isinstance(result.data, list) else []
        jup_line = _parse_line(market.get("line"))
        # Sisi Kalshi yang dicari + apakah peluangnya dikomplemenkan.
        if kind == "moneyline":
            want_side, complement = side, False
            want_line: float | None = None
        elif kind == "spread":
            if jup_line is None or jup_line == 0:
                return None, "kalshi_garis_tidak_cocok", None, False
            want_line = abs(jup_line)
            if jup_line < 0:
                want_side, complement = side, False
            else:
                if side not in ("home", "away"):
                    return None, "kalshi_outcome_tidak_cocok", None, False
                want_side = "away" if side == "home" else "home"
                complement = True
        else:  # total
            if jup_line is None:
                return None, "kalshi_garis_tidak_cocok", None, False
            if side not in ("over", "under"):
                return None, "kalshi_outcome_tidak_cocok", None, False
            want_side, want_line = "over", jup_line
            complement = side == "under"
        matches: list[dict] = []
        for candidate in markets:
            if not isinstance(candidate, dict):
                continue
            if not (
                self.teams_match(
                    candidate.get("home_team"),
                    market.get("home_team"),
                    self.sport,
                )
                and self.teams_match(
                    candidate.get("away_team"),
                    market.get("away_team"),
                    self.sport,
                )
            ):
                continue
            candidate_side = str(candidate.get("side") or "").lower()
            if candidate_side != want_side:
                continue
            if kind in ("spread", "total"):
                line = _parse_line(candidate.get("line"))
                if line is None or line != want_line:
                    continue
            matches.append(candidate)
        if not matches:
            if kind in ("spread", "total"):
                return None, "kalshi_garis_tidak_cocok", None, False
            return None, "kalshi_pasar_tidak_ditemukan", None, False
        # Pasangan yang sama bisa muncul dua kali (malam ini + rematch) —
        # pilih yang expiration_time-nya terdekat dengan jam mulai pasar
        # jup (expiration ≈ mulai + durasi laga), bukan yang pertama.
        chosen = _closest_by_time(matches, market.get("start_time"), "expiration_time")
        if chosen is None:  # tidak mungkin (matches tidak kosong)
            return None, "kalshi_pasar_tidak_ditemukan", None, False
        line = want_line if kind in ("spread", "total") else None
        try:
            prob = float(self._kalshi_probability(chosen))
        except (TypeError, ValueError):
            return None, "kalshi_probability_tidak_sah", None, False
        except Exception as exc:  # noqa: BLE001 - pembanding gagal
            return None, f"kalshi_probability_gagal: {exc}", None, False
        if not 0 <= prob <= 1:
            return None, "kalshi_probability_di_luar_0_1", None, False
        if complement:
            prob = 1.0 - prob
        return prob, None, line, complement


# -- helper pencocokan & pencatatan ---------------------------------------


def _parse_time(value: object) -> datetime | None:
    """Parse ISO 8601 (dengan zona waktu) menjadi datetime; None bila gagal."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _closest_by_time(items: list[dict], target: object, time_key: str) -> dict | None:
    """Pilih item yang waktunya (kunci ``time_key``, ISO) terdekat target.

    Dipakai untuk membedakan dua laga pasangan tim yang sama (malam ini
    vs rematch minggu depan — laga pasangan sama berjarak hari, jadi yang
    terdekat menang tanpa ambang). Bila target tidak terbaca: item
    berwaktu paling awal; bila tak ada item berwaktu: item pertama.
    Seri selisih: item pertama di list. List kosong -> None.
    """
    if not items:
        return None
    target_dt = _parse_time(target)
    timed = [
        (item, parsed)
        for item in items
        if (parsed := _parse_time(item.get(time_key))) is not None
    ]
    if target_dt is None:
        if timed:
            return min(timed, key=lambda pair: pair[1])[0]
        return items[0]
    if not timed:
        return items[0]
    return min(timed, key=lambda pair: abs(pair[1] - target_dt))[0]


def _find_in_list(
    data: object,
    home: object,
    away: object,
    teams_match,
    sport: str,
) -> dict | None:
    """Cari event/pertandingan di list berdasarkan pasangan tim."""
    if not isinstance(data, list):
        return None
    for item in data:
        if not isinstance(item, dict):
            continue
        if teams_match(item.get("home_team"), home, sport) and teams_match(
            item.get("away_team"), away, sport
        ):
            return item
    return None


def _find_team_rows(
    data: object,
    home: object,
    away: object,
    teams_match,
    sport: str,
) -> dict[str, dict]:
    """Cari baris stats per tim; kembalikan {"home": row, "away": row}."""
    rows: dict[str, dict] = {}
    if not isinstance(data, list):
        return rows
    for item in data:
        if not isinstance(item, dict):
            continue
        name = next(
            (item.get(key) for key in _TEAM_NAME_KEYS if item.get(key)),
            None,
        )
        if name is None:
            continue
        if "home" not in rows and teams_match(name, home, sport):
            rows["home"] = item
        elif "away" not in rows and teams_match(name, away, sport):
            rows["away"] = item
    return rows


def _find_fixture(
    data: object,
    home: object,
    away: object,
    date: str,
    teams_match,
) -> dict | None:
    """Cari fixture PL berdasarkan tim + kickoff dalam ±1 hari dari tanggal slate."""
    if not isinstance(data, list):
        return None
    try:
        target = datetime.fromisoformat(date).date()
    except ValueError:
        target = None
    best: dict | None = None
    best_gap: timedelta | None = None
    for item in data:
        if not isinstance(item, dict):
            continue
        if not (
            teams_match(item.get("home_team"), home, "football")
            and teams_match(item.get("away_team"), away, "football")
        ):
            continue
        kickoff = _parse_time(item.get("kickoff"))
        if target is not None:
            if kickoff is None or abs((kickoff.date() - target).days) > 1:
                continue
            gap = abs(kickoff.date() - target)
            if best_gap is not None and gap >= best_gap:
                continue
            best_gap = gap
        best = item
    return best


def _find_xg_rows(
    data: object, home: object, away: object, teams_match
) -> dict[str, dict]:
    """Cari baris xG Understat per tim (teamsData: id -> {title, ...})."""
    rows: dict[str, dict] = {}
    if not isinstance(data, dict):
        return rows
    for team in data.values():
        if not isinstance(team, dict):
            continue
        title = team.get("title")
        if title is None:
            continue
        if "home" not in rows and teams_match(title, home, "football"):
            rows["home"] = team
        elif "away" not in rows and teams_match(title, away, "football"):
            rows["away"] = team
    return rows


def _espn_event_summary(event: dict | None) -> dict | None:
    """Ringkasan kecil event ESPN (hanya kunci yang dikenal, tanpa dump mentah)."""
    if not isinstance(event, dict):
        return None
    summary = {key: event[key] for key in _ESPN_EVENT_KEYS if key in event}
    return summary or None


def _record_source(sources: list[dict], data_kind: str, result: FetchResult) -> None:
    """Catat satu sumber (data_kind + sumber + jenjang + jam ASLI fetch)."""
    sources.append(
        {
            "data_kind": data_kind,
            "source": result.source,
            "tier": result.tier,
            "fetched_at": result.fetched_at,
        }
    )


def _record_source_comparison(
    sources: list[dict], builder: _Builder, prices: dict[str, dict]
) -> None:
    """Catat sumber comparison_prices yang benar-benar dipakai laga ini.

    Hanya langkah pembanding yang menghasilkan p_market untuk setidaknya
    satu pasar di laga ini yang dicatat (sekali per nama sumber).
    """
    kalshi_kinds = {"moneyline": "moneyline", "spreads": "spread", "totals": "total"}
    seen: set[str] = set()
    for entry in prices.values():
        step = entry.get("comparison_source")
        if step == "odds_api_devig":
            result = builder.odds_api
        elif step == "espn_odds_devig":
            result = builder.espn_odds
        elif step == KALSHI_STEP:
            result = builder.kalshi.get(
                kalshi_kinds.get(str(entry.get("market_type", "")), "")
            )
        else:
            result = None
        if result is None or not result.ok or result.source in seen:
            continue
        seen.add(result.source)
        _record_source(sources, "comparison_prices", result)


def _merge_injuries(
    results: list[FetchResult],
    home: object,
    away: object,
    teams_match,
    sport: str,
) -> tuple[list[dict], list[dict]]:
    """Gabung daftar cedera dari beberapa sumber; konflik dicatat di conflicts[].

    Satu pemain yang statusnya berbeda antar sumber muncul sekali per status
    di ``injuries`` + satu entri di ``conflicts`` (B2: tampilkan keduanya,
    jangan pilih diam-diam). Hanya cedera untuk kedua tim laga ini.
    """
    by_player: dict[str, dict] = {}
    order: list[str] = []
    for result in results:
        entries = result.data if isinstance(result.data, list) else []
        for item in entries:
            if not isinstance(item, dict):
                continue
            player = item.get("player")
            status = item.get("status")
            team = item.get("team")
            if not player or not status:
                continue
            if not (teams_match(team, home, sport) or teams_match(team, away, sport)):
                continue
            key = _normalize_simple(player)
            if key not in by_player:
                by_player[key] = {
                    "player": player,
                    "team": team,
                    "by_source": {},
                }
                order.append(key)
            by_player[key]["by_source"][result.source] = (
                status,
                item.get("detail"),
            )
    injuries: list[dict] = []
    conflicts: list[dict] = []
    for key in order:
        record = by_player[key]
        by_source = record["by_source"]
        distinct = sorted({str(s).lower() for s, _ in by_source.values()})
        if len(distinct) == 1:
            status, detail = next(iter(by_source.values()))
            injuries.append(
                {
                    "player": record["player"],
                    "team": record["team"],
                    "status": status,
                    "detail": detail,
                }
            )
        else:
            seen_status: dict[str, tuple[str, object]] = {}
            for status, detail in by_source.values():
                seen_status.setdefault(str(status).lower(), (status, detail))
            for status, detail in sorted(seen_status.values()):
                injuries.append(
                    {
                        "player": record["player"],
                        "team": record["team"],
                        "status": status,
                        "detail": detail,
                    }
                )
            conflicts.append(
                {
                    "field": f"injuries:{record['player']}",
                    "values": [
                        {"source": source, "value": status}
                        for source, (status, _) in sorted(by_source.items())
                    ],
                }
            )
    return injuries, conflicts


def _resolve_outcome_side(market: dict, teams_match, sport: str) -> str | None:
    """Pecahkan outcome pasar jup.ag menjadi sisi kanonik.

    ``outcome`` adalah JUDUL pasar (terverifikasi dari cache probe):
    nama tim untuk moneyline/spread, "Over"/"Under" untuk total, "Both
    Teams to Score" untuk BTTS. Mengembalikan "home"/"away"/"draw"/
    "over"/"under"/"yes", atau None bila judul tidak bisa dipecahkan
    (fail-closed: pasar tanpa sisi tidak mendapat p_market).
    """
    market_type = str(market.get("market_type", "")).lower()
    raw = str(market.get("outcome") or "").strip()
    if not raw:
        return None
    lowered = raw.lower()
    if market_type in ("moneyline", "spreads"):
        if market_type == "moneyline" and lowered in (
            "draw",
            "tie",
            "tie is the result",
        ):
            return "draw"
        if teams_match(raw, market.get("home_team"), sport):
            return "home"
        if teams_match(raw, market.get("away_team"), sport):
            return "away"
        return None
    if market_type == "totals":
        if lowered == "over":
            return "over"
        if lowered == "under":
            return "under"
        return None
    if market_type == "both_teams_to_score":
        if "both teams to score" in lowered:
            return "yes"
        return None
    return None


def _market_key(market: dict, side: str | None) -> str:
    """Kunci market_prices, mis. moneyline_home / spread_home_-1.5 / total_over_2.5."""
    market_type = str(market.get("market_type", "")).lower()
    label = side or _normalize_simple(market.get("outcome")) or "unknown"
    if market_type in ("spreads", "totals"):
        line = market.get("line")
        line_text = str(line) if line is not None else "na"
        return f"{market_type[:-1]}_{label}_{line_text}"
    return f"{market_type}_{label}"


def _odds_outcome_is_ours(
    item: dict, side: str, market: dict, teams_match, sport: str
) -> bool:
    """Apakah satu outcome Odds API adalah sisi pasar jup.ag kita?"""
    name = str(item.get("name", ""))
    market_type = str(market.get("market_type", "")).lower()
    if market_type == "moneyline":
        if side == "home":
            return teams_match(name, market.get("home_team"), sport)
        if side == "away":
            return teams_match(name, market.get("away_team"), sport)
        if side == "draw":
            return name.strip().lower() == "draw"
        return False
    if market_type == "spreads":
        if side == "home":
            return teams_match(name, market.get("home_team"), sport)
        if side == "away":
            return teams_match(name, market.get("away_team"), sport)
        return False
    if market_type == "totals":
        return name.strip().lower() == side
    return False


# -- API publik -----------------------------------------------------------


def build_slate(
    sport: str,
    date: str,
    matches: list[dict] | None = None,
    slate_id: str | None = None,
    playstyle: dict | None = None,
    league: str = "EPL",
) -> dict:
    """Rakit slate untuk satu sport + tanggal (dispatch ke NBA/bola).

    ``matches``: list ``{home, away}`` (+ opsional ``match_id``,
    ``start_time``, ``league``) untuk memfilter; None = semua laga hari
    itu dari sumber jadwal. ``league`` hanya dipakai untuk bola (EPL
    default; LaLiga didukung sebagian — tanpa fixtures PL & odds ESPN).
    """
    if sport == "nba":
        return build_nba_slate(date, matches, slate_id, playstyle)
    if sport == "football":
        return build_football_slate(date, league, matches, slate_id, playstyle)
    raise ValueError(f"sport tidak dikenal: {sport!r} (pakai 'nba'/'football')")


def build_nba_slate(
    date: str,
    matches: list[dict] | None = None,
    slate_id: str | None = None,
    playstyle: dict | None = None,
) -> dict:
    """Rakit slate NBA untuk satu tanggal US Eastern (YYYY-MM-DD).

    ``date`` adalah tanggal Eastern — stats.nba.com memakai tanggal
    Eastern; cli.py mengonversi start_time slate ke Eastern sebelum
    memanggil fungsi ini.
    """
    builder = _Builder("nba", date, "NBA", playstyle)
    return builder.build(matches, slate_id)


def build_football_slate(
    date: str,
    league: str = "EPL",
    matches: list[dict] | None = None,
    slate_id: str | None = None,
    playstyle: dict | None = None,
) -> dict:
    """Rakit slate sepak bola untuk satu tanggal (YYYY-MM-DD) + liga."""
    builder = _Builder("football", date, league, playstyle)
    return builder.build(matches, slate_id)
