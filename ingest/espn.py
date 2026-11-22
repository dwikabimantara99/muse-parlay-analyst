"""Penarik ESPN JSON publik: scoreboard, cedera NBA, odds bola (jenjang 2).

Cadangan jadwal/statistik NBA bila stats.nba.com gagal, dan sumber garis
sportsbook bola (devig, DECISIONS.md urutan pembanding).

Cedera NBA (fetch_injuries_nba) adalah pasangan cek silang tier 2 untuk
PDF resmi tier 1 di nba_brain (aturan B2). Sejak 2026-11-22 ESPN
MENGGANTIKAN Rotowire di peran itu — Rotowire gratis hanya mengembalikan
5 entri + "Subscribers Only" (paywall, terverifikasi live 22 Nov 2026),
sedang ESPN mengembalikan 110 cedera 30 tim dalam satu panggilan.

PEMETAAN STATUS ESPN -> status ternormalisasi (dipakai is_injury,
konflik status-vs-komentar, dan merge nba_brain):
  Out -> OUT (eksak); Doubtful -> DOUBTFUL (eksak);
  Questionable -> QUESTIONABLE (eksak); Probable -> PROBABLE (eksak);
  Available -> AVAILABLE (eksak); Day-To-Day -> QUESTIONABLE
  (perkiraan terdekat, status asli disimpan di "status_asli");
  GTD / Game-Time Decision -> QUESTIONABLE (perkiraan terdekat).
  Status lain -> None (tidak dikenal; merge mencatatnya di "missing").
  Pemetaan ini SAMA dengan nba_brain._normalize_status — keduanya harus
  tetap selaras; nba_brain memakai "status_normalized" dari entri ESPN
  bila ada, dan _normalize_status hanya untuk baris tanpa field itu
  (misal PDF resmi).

KONFLIK STATUS vs KOMENTAR (terverifikasi di data live 22 Nov 2026):
field "status" ESPN kadang bertentangan dengan shortComment-nya —
contoh nyata: Ronald Holland II status Out tapi komentar "listed as
questionable". Aturan: status adalah datum terstruktur (yang dipakai),
komentar disimpan sebagai konteks ("detail" + "long_comment"), dan
"status_comment_conflict" = True bila pasangan berikut terjadi
(pencocokan substring case-insensitive, HANYA pada shortComment —
longComment adalah narasi dan terbukti memberi false positive, misal
"if he remains sidelined" yang kondisional):
  - status OUT + komentar mengandung "questionable", "probable",
    "game-time decision", "expected to play", "likely to play", atau
    "will play" (contoh: Holland, Flemings — 2 dari 110 entri live);
  - status PROBABLE/AVAILABLE + komentar mengandung "ruled out",
    "will not play", "won't play", "will miss", "listed as out",
    "is out for", "out for the", atau "sidelined";
  - status QUESTIONABLE/DOUBTFUL + komentar mengandung salah satu
    frasa "definitif tidak main" di atas (contoh: Day-To-Day tapi
    "has been ruled out" — 8 dari 110 entri live).
  Day-To-Day + "probable" BUKAN konflik (probable masih dalam keluarga
  game-time decision). "Won't return" (laga yang sedang berjalan) BUKAN
  sinyal konflik — itu soal laga berjalan, bukan laga berikutnya.

ENTRI NON-CEDERA: daftar cedera ESPN juga memuat entri administratif
yang BUKAN cedera — contoh nyata: Ugonna Onyenso Day-To-Day karena
"agreed to a two-way contract". "is_injury" = True HANYA bila
(a) status ternormalisasi OUT/DOUBTFUL/QUESTIONABLE, DAN (b) ada detail
cedera (details.type/detail/side terisi, atau shortComment terisi),
DAN (c) TIDAK ada alasan administratif sebagai isi utama shortComment
(pola: "two-way contract/deal", "personal reasons", "G League
assignment" / "assigned to ... G League", "suspend(ed/ion)"), DAN
(d) details.type BUKAN "Rest"/"Personal" (klasifikasi ESPN sendiri;
contoh: Tatum "(rest)", Small "personal reasons"). Catatan penting:
pencocokan HANYA pada shortComment, bukan longComment — substring
"two-way"/"g league" di longComment terbukti false positive pada
pemain yang benar-benar cedera (misal Holmgren, Sheppard, Watkins —
semuanya cedera sungguhan dengan kata itu di narasi). "Illness"
(details.type) DIHITUNG sebagai detail kesehatan (pemain tidak
tersedia karena alasan kesehatan). Entri is_injury=False TIDAK
dihitung sebagai konfirmasi cedera oleh merge nba_brain.

FAKTA: ESPN TIDAK PUNYA ODDS NBA. Terbukti di probe odds 2a-lanjutan
(probes/espn_odds.py): scoreboard NBA hari ini 0/4 event punya odds,
scoreboard NBA besok 0/6, dan summary laga NBA memuat field odds kosong
([]). Karena itu modul ini TIDAK menyediakan fetch_odds_nba — sengaja,
bukan kelalaian. Odds NBA untuk devig berasal dari The Odds API
(ingest/odds_api.py, worker lain).

Odds bola (fetch_odds_football) memakai entri odds scoreboard EPL:
provider DraftKings (ML + spread + total lengkap, 7/7 laga terverifikasi
di probe). Bila suatu laga tidak punya odds, laga dicatat di
extra["games_without_odds"], bukan error.
"""

from __future__ import annotations

import re
from datetime import datetime

from ingest.common import (
    DiskCache,
    FetchResult,
    HttpClient,
    RateLimiter,
    default_cache_dir,
    now_iso,
    parse_json_body,
)

SOURCE = "ESPN"
TIER = 2
CACHE_TTL_SECONDS = 600
RATE_GAP_SECONDS = 1.0

NBA_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
)
NBA_INJURIES_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
)
SOCCER_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard"
)

# Total ESPN memakai prefiks "o"/"u" pada garis, misal "o3.5"/"u3.5".
_TOTAL_LINE_RE = re.compile(r"^[ou]([0-9]+(?:\.[0-9]+)?)$", re.I)

# Pemetaan status cedera ESPN -> status ternormalisasi (lihat docstring
# modul). Kunci: huruf kecil, tanda hubung/garis bawah -> spasi.
_STATUS_EXACT = {
    "out": "OUT",
    "doubtful": "DOUBTFUL",
    "questionable": "QUESTIONABLE",
    "probable": "PROBABLE",
    "available": "AVAILABLE",
}
_STATUS_APPROX = {
    "day to day": "QUESTIONABLE",
    "gtd": "QUESTIONABLE",
    "game time decision": "QUESTIONABLE",
}

# Sinyal di shortComment bahwa pemain DEFINITIF tidak main.
_OUT_SIGNALS = (
    "ruled out",
    "will not play",
    "won't play",
    "will miss",
    "listed as out",
    "is out for",
    "out for the",
    "sidelined",
)
# Sinyal di shortComment bahwa pemain MUNGKIN/BISA main.
_AVAILABLE_SIGNALS = (
    "questionable",
    "probable",
    "game-time decision",
    "game time decision",
    "expected to play",
    "likely to play",
    "will play",
)

# Pola alasan administratif sebagai isi utama shortComment (bukan
# cedera). Dicocokkan HANYA pada shortComment — lihat docstring modul
# soal false positive di longComment.
_NON_INJURY_RE = re.compile(
    r"two-way (contract|deal)"
    r"|personal reasons?"
    r"|g league assignment"
    r"|assigned to (the |his |her )?g league"
    r"|suspend(ed|ion)",
    re.I,
)
# details.type ESPN yang BUKAN cedera (klasifikasi ESPN sendiri).
_NON_INJURY_DETAIL_TYPES = frozenset({"rest", "personal"})


def normalize_injury_status(raw: object) -> tuple[str | None, str | None]:
    """Normalisasi status cedera ESPN.

    Mengembalikan (status_ternormalisasi, status_asli). status_asli
    diisi hanya bila pemetaannya perkiraan (Day-To-Day/GTD) atau tidak
    dikenal, agar jejaknya tidak hilang. Pemetaan sama dengan
    nba_brain._normalize_status — keduanya harus tetap selaras.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None, None
    key = re.sub(r"\s+", " ", raw.strip().lower().replace("-", " ").replace("_", " "))
    if key in _STATUS_EXACT:
        return _STATUS_EXACT[key], None
    if key in _STATUS_APPROX:
        return _STATUS_APPROX[key], raw.strip()
    return None, raw.strip()


def _status_comment_conflict(status_normalized: str | None, short_comment: str) -> bool:
    """True bila status terstruktur bertentangan dengan shortComment.

    Pasangan yang dianggap bertentangan (lihat docstring modul):
    OUT + sinyal bisa-main; PROBABLE/AVAILABLE + sinyal definitif
    tidak main; QUESTIONABLE/DOUBTFUL + sinyal definitif tidak main.
    """
    comment = (short_comment or "").lower()
    says_out = any(signal in comment for signal in _OUT_SIGNALS)
    says_available = any(signal in comment for signal in _AVAILABLE_SIGNALS)
    if status_normalized == "OUT":
        return says_available
    if status_normalized in ("PROBABLE", "AVAILABLE"):
        return says_out
    if status_normalized in ("QUESTIONABLE", "DOUBTFUL"):
        return says_out
    return False


def _is_injury_entry(
    status_normalized: str | None, short_comment: str, details: dict
) -> bool:
    """True bila entri ESPN ini adalah konfirmasi cedera.

    Syarat (lihat docstring modul): status OUT/DOUBTFUL/QUESTIONABLE,
    ada detail cedera, dan tidak ada alasan administratif. "Illness"
    dihitung sebagai detail kesehatan.
    """
    if status_normalized not in ("OUT", "DOUBTFUL", "QUESTIONABLE"):
        return False
    detail_type = str(details.get("type") or "").strip().lower()
    if detail_type in _NON_INJURY_DETAIL_TYPES:
        return False
    if _NON_INJURY_RE.search(short_comment or ""):
        return False
    has_detail = bool(
        details.get("type") or details.get("detail") or details.get("side")
    ) or bool((short_comment or "").strip())
    return has_detail


def parse_injuries_nba(data: dict) -> list[dict]:
    """Ubah respons JSON injuries ESPN jadi list cedera NBA.

    Setiap entri: {player, team, status, detail, status_normalized,
    status_comment_conflict, is_injury, long_comment, date, source,
    tier} + "status_asli" bila pemetaan statusnya perkiraan
    (Day-To-Day/GTD). "status" memakai istilah ESPN apa adanya ("Out",
    "Day-To-Day", ...); "status_normalized" hasil normalize_injury_status;
    "detail" = shortComment (fallback: gabungan type/detail/side dari
    field details). "time" (jam pengambilan) TIDAK diisi di sini —
    ditambahkan fetch_injuries_nba dari fetched_at FetchResult.
    ValueError("espn_format_changed") bila field injuries tidak ada.
    """
    teams = data.get("injuries")
    if not isinstance(teams, list):
        raise ValueError("espn_format_changed")
    injuries = []
    for team in teams:
        if not isinstance(team, dict):
            continue
        team_name = team.get("displayName")
        for injury in team.get("injuries") or []:
            if not isinstance(injury, dict):
                continue
            athlete = injury.get("athlete") or {}
            player = athlete.get("displayName")
            status = injury.get("status")
            if not player or not team_name or not status:
                continue
            detail = injury.get("shortComment")
            details = injury.get("details") or {}
            if not detail:
                parts = [
                    str(details.get(key))
                    for key in ("type", "detail", "side")
                    if details.get(key)
                ]
                detail = " - ".join(parts) if parts else None
            status_normalized, status_asli = normalize_injury_status(status)
            short_comment = injury.get("shortComment") or ""
            entry = {
                "player": player,
                "team": team_name,
                "status": status,
                "detail": detail,
                "status_normalized": status_normalized,
                "status_comment_conflict": _status_comment_conflict(
                    status_normalized, short_comment
                ),
                "is_injury": _is_injury_entry(
                    status_normalized, short_comment, details
                ),
                "long_comment": injury.get("longComment"),
                "date": injury.get("date"),
                "source": SOURCE,
                "tier": TIER,
            }
            if status_asli is not None:
                entry["status_asli"] = status_asli
            injuries.append(entry)
    return injuries


# Satu limiter untuk SEMUA request modul ini (dibagi semua pemanggilan):
# membuat RateLimiter baru per panggilan berarti tidak ada jeda antar
# panggilan — slate memanggil fetcher berkali-kali (Kalshi: 3 series;
# Polymarket: 1x per pasar) dan API membalas 429 (teramati: Kalshi total
# EPL 429 saat demo 2b). RateLimiter.wait() melacak per host, jadi satu
# limiter aman untuk beberapa host modul ini.
_LIMITER = RateLimiter(RATE_GAP_SECONDS)


def _default_client() -> HttpClient:
    """Buat HttpClient default (jeda 1 dtk, cache 600 dtk)."""
    return HttpClient(
        _LIMITER,
        cache=DiskCache(default_cache_dir(), CACHE_TTL_SECONDS),
    )


def _competitors(event: dict) -> tuple[dict | None, dict | None]:
    """Ambil kompetitor kandang/tandang dari satu event scoreboard."""
    competitions = event.get("competitions") or []
    if not competitions or not isinstance(competitions[0], dict):
        return None, None
    home = away = None
    for competitor in competitions[0].get("competitors") or []:
        if not isinstance(competitor, dict):
            continue
        if competitor.get("homeAway") == "home":
            home = competitor
        elif competitor.get("homeAway") == "away":
            away = competitor
    return home, away


def _team_name(competitor: dict | None) -> str | None:
    """Nama tim dari satu kompetitor (displayName, fallback nama pendek)."""
    if not competitor:
        return None
    team = competitor.get("team") or {}
    return team.get("displayName") or team.get("name") or team.get("shortDisplayName")


def _event_status(event: dict) -> str:
    """Status event (description, fallback shortDetail/state)."""
    status = event.get("status") or {}
    status_type = status.get("type") or {}
    return (
        status_type.get("description")
        or status_type.get("shortDetail")
        or status_type.get("state")
        or "UNKNOWN"
    )


def parse_scoreboard(data: dict, sport: str) -> list[dict]:
    """Ubah respons JSON scoreboard ESPN jadi list game.

    Setiap game: game_id, home_team, away_team, start_time (ISO dari
    field date event), status (description ESPN apa adanya), league
    (slug liga dari respons, fallback argumen sport).
    ValueError("espn_format_changed") bila field events tidak ada.
    """
    events = data.get("events")
    if not isinstance(events, list):
        raise ValueError("espn_format_changed")
    leagues = data.get("leagues") or []
    league_slug = None
    if leagues and isinstance(leagues[0], dict):
        league_slug = leagues[0].get("slug")
    games = []
    for event in events:
        if not isinstance(event, dict):
            continue
        home, away = _competitors(event)
        games.append(
            {
                "game_id": str(event.get("id")),
                "home_team": _team_name(home),
                "away_team": _team_name(away),
                "start_time": event.get("date"),
                "status": _event_status(event),
                "league": league_slug or sport,
            }
        )
    return games


def _close_odds(section: dict, side: str) -> dict | None:
    """Ambil node odds 'close' satu sisi (moneyline/spread/total)."""
    node = section.get(side) or {}
    close = node.get("close")
    return close if isinstance(close, dict) else None


def _total_line(entry_total: dict) -> float | None:
    """Ambil garis total numerik dari "o3.5"/"u3.5" (over diutamakan)."""
    for side in ("over", "under"):
        node = _close_odds(entry_total, side)
        if node:
            match = _TOTAL_LINE_RE.match(str(node.get("line") or ""))
            if match:
                return float(match.group(1))
    return None


def parse_odds_entry(entry: dict) -> dict:
    """Ubah satu entri odds ESPN jadi struktur ringkas (odds 'close').

    Diadaptasi dari probes/espn_odds.py parse_odds_entry. Odds Amerika
    disimpan apa adanya (string); garis total dinormalisasi jadi float
    (tanpa prefiks o/u). Field yang tidak ada dicatat None (bukan ditebak).
    """
    provider = entry.get("provider") or {}
    moneyline = entry.get("moneyline") or {}
    spread = entry.get("pointSpread") or {}
    total = entry.get("total") or {}
    ml_home = _close_odds(moneyline, "home")
    ml_away = _close_odds(moneyline, "away")
    ml_draw = _close_odds(moneyline, "draw")
    sp_home = _close_odds(spread, "home")
    sp_away = _close_odds(spread, "away")
    tot_over = _close_odds(total, "over")
    tot_under = _close_odds(total, "under")
    return {
        "provider": provider.get("name"),
        "moneyline": {
            "home": ml_home.get("odds") if ml_home else None,
            "draw": ml_draw.get("odds") if ml_draw else None,
            "away": ml_away.get("odds") if ml_away else None,
        },
        "spread": {
            "home_line": sp_home.get("line") if sp_home else None,
            "home_odds": sp_home.get("odds") if sp_home else None,
            "away_line": sp_away.get("line") if sp_away else None,
            "away_odds": sp_away.get("odds") if sp_away else None,
        },
        "total": {
            "line": _total_line(total),
            "over_odds": tot_over.get("odds") if tot_over else None,
            "under_odds": tot_under.get("odds") if tot_under else None,
        },
    }


def _pick_odds_entry(odds_list: list) -> dict | None:
    """Pilih entri odds: DraftKings diutamakan, bila tidak ada entri pertama."""
    if not odds_list:
        return None
    for entry in odds_list:
        if isinstance(entry, dict):
            provider = entry.get("provider") or {}
            if provider.get("name") == "DraftKings":
                return entry
    first = odds_list[0]
    return first if isinstance(first, dict) else None


def parse_football_odds(data: dict) -> tuple[list[dict], list[str]]:
    """Ubah respons scoreboard bola ESPN jadi (list odds, laga tanpa odds).

    Setiap entri odds: home_team, away_team, commence_time (ISO dari
    field date event), provider, moneyline {home, draw, away} (odds
    Amerika), spread {home_line, home_odds, away_line, away_odds},
    total {line (float), over_odds, under_odds}. Laga tanpa odds
    dikembalikan sebagai daftar nama (bukan error).
    ValueError("espn_format_changed") bila field events tidak ada.
    """
    events = data.get("events")
    if not isinstance(events, list):
        raise ValueError("espn_format_changed")
    odds_rows: list[dict] = []
    without_odds: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        home, away = _competitors(event)
        name = event.get("name") or (
            f"{_team_name(away) or '?'} at {_team_name(home) or '?'}"
        )
        competitions = event.get("competitions") or []
        odds_list = []
        if competitions and isinstance(competitions[0], dict):
            odds_list = competitions[0].get("odds") or []
        entry = _pick_odds_entry(odds_list) if isinstance(odds_list, list) else None
        if entry is None:
            without_odds.append(name)
            continue
        parsed = parse_odds_entry(entry)
        odds_rows.append(
            {
                "home_team": _team_name(home),
                "away_team": _team_name(away),
                "commence_time": event.get("date"),
                "provider": parsed["provider"],
                "moneyline": parsed["moneyline"],
                "spread": parsed["spread"],
                "total": parsed["total"],
            }
        )
    return odds_rows, without_odds


def _fetch_json(url: str, client: HttpClient | None) -> tuple[dict | None, str | None]:
    """GET satu URL JSON ESPN; kembalikan (data, error). error None bila OK."""
    resp = (client or _default_client()).get(url)
    if resp.get("status") != 200:
        return None, f"http_{resp.get('status')}: {resp.get('error') or 'espn gagal'}"
    data = parse_json_body(resp)
    if not isinstance(data, dict):
        return None, "espn_format_changed"
    return data, None


def fetch_scoreboard(
    sport: str, date_str: str, client: HttpClient | None = None
) -> FetchResult:
    """Ambil scoreboard ESPN untuk satu tanggal.

    sport: "nba" atau "epl". date_str: "YYYY-MM-DD". data: list game
    (lihat parse_scoreboard). Fetch gagal -> ok=False (tidak melempar).
    """
    fetched_at = now_iso()
    if sport not in ("nba", "epl"):
        return FetchResult(
            SOURCE, TIER, fetched_at, False, error=f"sport_tidak_dikenal: {sport!r}"
        )
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return FetchResult(
            SOURCE, TIER, fetched_at, False, error=f"tanggal_tidak_valid: {date_str!r}"
        )
    if sport == "nba":
        base_url = NBA_SCOREBOARD_URL
    else:
        base_url = SOCCER_SCOREBOARD_URL.format(league="eng.1")
    url = f"{base_url}?dates={day.strftime('%Y%m%d')}"
    data, error = _fetch_json(url, client)
    if error is not None:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=error)
    assert data is not None
    try:
        games = parse_scoreboard(data, sport)
    except ValueError as exc:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=str(exc))
    return FetchResult(
        SOURCE,
        TIER,
        fetched_at,
        True,
        data=games,
        extra={"sport": sport, "date": date_str, "n_games": len(games)},
    )


def fetch_injuries_nba(client: HttpClient | None = None) -> FetchResult:
    """Ambil daftar cedera NBA dari ESPN (jenjang 2, cek silang).

    data: list cedera (lihat parse_injuries_nba) + "time" (jam
    pengambilan, = FetchResult.fetched_at) di tiap entri. extra
    mencatat n_injuries (semua entri), n_injury (yang dihitung sebagai
    konfirmasi cedera, is_injury True), dan n_non_injury (entri
    administratif yang dikecualikan — two-way, rest, personal, dst).
    Fetch gagal -> ok=False dengan error (tidak melempar).
    """
    fetched_at = now_iso()
    data, error = _fetch_json(NBA_INJURIES_URL, client)
    if error is not None:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=error)
    assert data is not None
    try:
        injuries = parse_injuries_nba(data)
    except ValueError as exc:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=str(exc))
    for injury in injuries:
        injury["time"] = fetched_at
    n_non_injury = sum(1 for injury in injuries if not injury["is_injury"])
    return FetchResult(
        SOURCE,
        TIER,
        fetched_at,
        True,
        data=injuries,
        extra={
            "n_injuries": len(injuries),
            "n_injury": len(injuries) - n_non_injury,
            "n_non_injury": n_non_injury,
        },
    )


def fetch_odds_football(
    league: str = "eng.1", client: HttpClient | None = None
) -> FetchResult:
    """Ambil garis sportsbook bola dari scoreboard ESPN (DraftKings).

    league: slug liga ESPN ("eng.1" = Premier League, terverifikasi di
    probe). data: list odds per laga (lihat parse_football_odds). Laga
    tanpa odds dicatat di extra["games_without_odds"], bukan error.
    Fetch gagal -> ok=False dengan error (tidak melempar).
    """
    fetched_at = now_iso()
    url = SOCCER_SCOREBOARD_URL.format(league=league)
    data, error = _fetch_json(url, client)
    if error is not None:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=error)
    assert data is not None
    try:
        odds_rows, without_odds = parse_football_odds(data)
    except ValueError as exc:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=str(exc))
    return FetchResult(
        SOURCE,
        TIER,
        fetched_at,
        True,
        data=odds_rows,
        extra={
            "league": league,
            "n_games_with_odds": len(odds_rows),
            "games_without_odds": without_odds,
        },
    )
