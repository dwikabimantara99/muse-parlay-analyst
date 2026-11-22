"""Perakit input Otak Bola untuk satu laga EPL (Tahap 3 Langkah 5).

Mengikuti kontrak ingest/nba_brain.py: satu paket input siap model
untuk SATU laga, dengan blok home/away + missing + sources. Bedanya:
bola berjalan TANPA_XG (DECISIONS.md B4 — rantai xG putus, Understat
maintenance), jadi model berbasis GOL: statistik tim diturunkan dari
hasil laga (gol/kebobolan per laga, form 5, H2H, kandang-tandang) dan
kekuatan serang/bertahan dihitung dari laju gol.

RUMUS KEKUATAN (BERSAMA — sama dengan fit pekerja A + sim pekerja B,
konvensi Dixon-Coles standar):
  laju_gol = 0,6 * gol_per_laga_musim + 0,4 * gol_per_laga_6_laga_terakhir
  laju_kebobolan = campuran yang sama untuk kebobolan
  attack  = laju_gol / rata-rata_gol_liga
  defence = laju_kebobolan / rata-rata_kebobolan_liga
  (rata-rata gol liga = rata-rata kebobolan liga = total gol /
  (2 * jumlah laga); setiap gol yang dicetak satu tim adalah gol
  yang kebobolan tim lain.)
  attack/defence lalu DINORMALISASI: dibagi rata-rata seluruh tim
  liga sehingga rata-rata liga = 1 persis.
KONVENSI defence (PENTING): defence adalah KEBOCORAN, bukan kekuatan
— defence > 1 berarti tim kebobolan LEBIH BANYAK dari rata-rata liga
(pertahanan bocor), defence < 1 berarti lebih sedikit (pertahanan
rapat). Ini konvensi Dixon-Coles standar: lambda lawan dikalikan
defence tim ini (football_sim.simulate; fit pekerja A: Arsenal
2024/25 defence 0,62, Southampton 1,51).
KOREKSI 2026-11-22 (pekerja C): rumus defence di TUGAS tertulis
terbalik (rata-rata_liga / laju_kebobolan = kekuatan) — bila dipakai
apa adanya, sim membalik arti pertahanan: tim rapat justru membuat
lawan mencetak LEBIH BANYAK gol (contoh live LIV-MUN: model memberi
Man Utd 50% menang di Anfield vs market 23%). Rumus di atas adalah
yang BENAR per fit + sim pekerja A/B; koreksi ini dilaporkan ke
koordinator untuk diratifikasi, bukan didiamkan.
Bobot 60/40 + 6 laga terakhir dibaca dari config
(simulation.football.xg_weight_season / xg_weight_recent /
recent_matches) — kunci yang sama dengan §5b, dipakai ulang untuk
laju GOL selama TANPA_XG (lihat komentar di playstyle.yaml).

KONTRAK OUTPUT (data FetchResult):
  {"match": {"home_team", "away_team", "match_date", "season",
             "league", "matchweek", "kickoff"},
   "home": {blok tim}, "away": {blok tim},
   "h2h_last5": [laga...],
   "league": {"avg_goals_per_team_match", "n_matches", "n_teams"},
   "weights": {"season", "recent", "recent_matches", "source"},
   "injuries_status": {"n_sources", "confirmed", "note"},
   "injury_sources_checked": [{source, result}...],
   "missing": [nama field yang gagal diambil],
   "sources": [{data_kind, source, tier, fetched_at}...],
   "fetched_at": iso}
Blok tim:
  {"team", "stats_season": {played, w, d, l, goals_for_per_match,
              goals_against_per_match},
   "stats_last6": {kunci sama},
   "form5": [{"match_date", "opponent", "home", "result",
              "goals_for", "goals_against"}... urutan terbaru dulu],
   "home_record": {played, w, d, l, gf_per_match, ga_per_match},
   "away_record": {sama},
   "attack": float | None, "defence": float | None,
   "injuries": []}

SUMBER (B1 — jenjang tertinggi dulu):
- JSON resmi Premier League (tier 1, PRIMER EPL): endpoint fixtures
  yang sama dengan ingest/premier_league.py
  (footballapi.pulselive.com/football/fixtures). Modul ini mengambil
  halaman mentahnya sendiri karena parse_fixtures di modul itu
  membuang SKOR — dan skor adalah bahan statistik gol. Hanya hasil
  musim berjalan yang dipakai (jendela ke belakang dari config
  simulation.football.results_window_days).
- ESPN scoreboard (tier 2, CADANGAN): hanya bila fetch PL gagal —
  dipakai untuk mengonfirmasi fixture laga ini (kickoff/status) pada
  tanggal laga. TIDAK dipakai untuk hasil musim: endpoint scoreboard
  ESPN tidak menerima rentang tanggal (HTTP 400, diverifikasi
  2026-11-22), jadi mengambil satu musim butuh puluhan request
  per tanggal — tidak dilakukan.
- CEDERA: TIDAK ADA sumber cedera bola yang bisa dipakai
  (diselidiki langsung 2026-11-22):
  * Endpoint cedera bola ESPN (site.api.espn.com/.../soccer/eng.1/
    injuries) mengembalikan list KOSONG — diverifikasi ulang live
    2026-11-22, sama seperti temuan 2b.
  * Situs resmi Premier League tidak punya endpoint/halaman cedera
    (premierleague.com/injuries -> HTTP 404; halaman news adalah HTML
    narasi, bukan data cedera terstruktur).
  * Fantasy Premier League API HIDUP (terverifikasi 2026-11-22) tapi
    BELUM diratifikasi user — modul ini TIDAK memakainya (aturan
    keras langkah 5). Karena itu n_sources selalu 0 dan status cedera
    TIDAK terkonfirmasi: setiap laga bola HOLD (B2 butuh 2 sumber).
  Modul ini tetap MENGECEK endpoint cedera ESPN setiap kali jalan
  (1 request, cache 10 menit): bila suatu hari ESPN mengisi daftar
  itu, mesin akan melihatnya sebagai sumber ke-1 (tetap < 2 sumber,
  tetap HOLD — tapi tercatat jujur, bukan 0 diam-diam).

LALIGA (dan liga lain): BELUM DIDUKUNG. Tidak ada fetcher JSON resmi
LaLiga di repo ini, dan ingest/espn.py fetch_scoreboard hanya
mendukung "nba"/"epl" — jadi fetch_match_inputs mengembalikan
ok=False (liga_tidak_didukung) untuk liga selain EPL. Kalshi hanya
punya moneyline LaLiga (KXLALIGAGAME, tanpa spread/total), dan
endpoint cedera ESPN esp.1 juga kosong (diverifikasi 2026-11-22).

ATURAN GAGAL (seperti nba_brain): setiap kegagalan fetch -> field
None (atau list kosong) + nama field di "missing" + error di
FetchResult.extra["fetch_errors"]. ok=False HANYA bila SEMUA sumber
gagal total; bila sebagian berhasil, ok=True dengan "missing" terisi.
Tim yang belum pernah main musim ini -> attack/defence None +
"missing". Tim dengan laju kebobolan 0 -> defence None (pembagian
nol tidak didefinisikan) + "missing"; attack 0,0 sah (tim yang belum
pernah mencetak gol).
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta

import config as config_mod
from ingest import matching
from ingest import premier_league as pl_mod
from ingest.common import (
    DiskCache,
    FetchResult,
    HttpClient,
    RateLimiter,
    default_cache_dir,
    now_iso,
    parse_json_body,
)

SOURCE = "soccer_brain"
TIER = 1  # Perakit ini tier 1; tiap datum membawa sumber + tier
# aslinya sendiri di data["sources"].

# Endpoint cedera bola ESPN (diselidiki langsung 2026-11-22: selalu
# mengembalikan list kosong — dicek ulang tiap jalan, lihat docstring).
ESPN_SOCCER_INJURIES_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/injuries"
)
_ESPN_INJURY_LEAGUES = {"EPL": "eng.1"}

# Cache 1800 detik + jeda 1 detik antar request (kontrak yang sama
# dengan ingest/premier_league.py).
CACHE_TTL_SECONDS = 1800
MIN_GAP_SECONDS = 1.0

# Batas halaman yang diambil setelah halaman target ditemukan (pengaman
# agar satu panggilan tidak pernah mengunduh seluruh arsip PL).
MAX_PAGES_AFTER_TARGET = 8
_PAGE_SIZE = 100

# Default bila kunci config belum ada (PILIHAN DESAIN mengikuti §5b —
# 60% musim + 40% 6 laga terakhir; dicatat di data["weights"]).
DEFAULT_WEIGHT_SEASON = 0.6
DEFAULT_WEIGHT_RECENT = 0.4
DEFAULT_RECENT_MATCHES = 6
DEFAULT_RESULTS_WINDOW_DAYS = 150

_MUSIM_LABEL_RE = re.compile(r"(\d{4})/(\d{4})")
_TANGGAL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Satu limiter untuk SEMUA request modul ini (pola yang sama dengan
# modul ingest lain: satu limiter per modul, dibagi semua pemanggilan).
_LIMITER = RateLimiter(MIN_GAP_SECONDS)


def _default_client() -> HttpClient:
    """Client default: jeda 1 detik, cache 1800 detik."""
    cache = DiskCache(default_cache_dir(), ttl_seconds=CACHE_TTL_SECONDS)
    return HttpClient(_LIMITER, cache=cache)


def _source_entry(data_kind: str, result: FetchResult) -> dict:
    """Satu entri sources[] dari FetchResult yang berhasil."""
    return {
        "data_kind": data_kind,
        "source": result.source,
        "tier": result.tier,
        "fetched_at": result.fetched_at,
    }


def _safe_fetch(func, *args, **kwargs) -> FetchResult:
    """Panggil fetcher; exception diubah jadi FetchResult gagal."""
    try:
        return func(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - semua exception fetch dicatat
        return FetchResult(
            SOURCE,
            TIER,
            now_iso(),
            False,
            error=f"exception_{type(exc).__name__}: {exc}",
        )


def _to_float(value: object) -> float | None:
    """Ubah nilai jadi float; None bila bukan angka."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _mean(values: list) -> float | None:
    """Rata-rata nilai angka; None bila tidak ada satu pun."""
    numbers = [
        value for value in (_to_float(item) for item in values) if value is not None
    ]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


# ---------------------------------------------------------------------------
# Pembacaan config (bobot laju gol + jendela hasil)
# ---------------------------------------------------------------------------


def _baca_bobot(cfg: dict | None) -> tuple[dict, str]:
    """Baca bobot laju gol + jendela hasil dari simulation.football.

    Mengembalikan (parameter, sumber): sumber "config" bila SEMUA kunci
    ada di config, "default" bila ada yang hilang (nilai default §5b
    dipakai untuk kunci yang hilang saja). cfg None -> baca
    playstyle.yaml; gagal baca -> semua default. Nilai yang ada harus
    angka hingga yang sah (bobot 0-1 dan berjumlah > 0, recent_matches
    int >= 1, window int >= 1), bila tidak -> ValueError (pola
    nba_brain._baca_k_shrinkage: config rusak tidak didiamkan).
    """
    params = {
        "season": DEFAULT_WEIGHT_SEASON,
        "recent": DEFAULT_WEIGHT_RECENT,
        "recent_matches": DEFAULT_RECENT_MATCHES,
        "results_window_days": DEFAULT_RESULTS_WINDOW_DAYS,
    }
    if cfg is None:
        try:
            cfg = config_mod.load_playstyle()
        except Exception:  # noqa: BLE001 - config gagal = default
            return params, "default"
    sumber = "config"
    kunci_map = (
        ("season", "xg_weight_season"),
        ("recent", "xg_weight_recent"),
        ("recent_matches", "recent_matches"),
        ("results_window_days", "results_window_days"),
    )
    for nama, kunci in kunci_map:
        try:
            nilai = config_mod.get_value(cfg, "simulation", "football", kunci)
        except config_mod.ConfigError:
            sumber = "default"
            continue
        if nama in ("season", "recent"):
            angka = _to_float(nilai)
            if angka is None or not math.isfinite(angka) or not 0.0 <= angka <= 1.0:
                raise ValueError(
                    f"simulation.football.{kunci} tidak valid: {nilai!r} "
                    "(harus angka 0-1)"
                )
            params[nama] = angka
        else:
            if isinstance(nilai, bool) or not isinstance(nilai, int) or nilai < 1:
                raise ValueError(
                    f"simulation.football.{kunci} tidak valid: {nilai!r} "
                    "(harus integer >= 1)"
                )
            params[nama] = nilai
    if params["season"] + params["recent"] <= 0:
        raise ValueError(
            "bobot laju gol berjumlah 0 — xg_weight_season + "
            "xg_weight_recent harus > 0"
        )
    return params, sumber


# ---------------------------------------------------------------------------
# Fetch mentah fixtures PL (dengan skor)
# ---------------------------------------------------------------------------


def _pl_url(page: int, page_size: int) -> str:
    """URL satu halaman fixtures (parameter sama seperti URL probe)."""
    return f"{pl_mod.BASE_URL}?comps=1&page={page}&pageSize={page_size}&sort=asc"


def _fetch_pl_page(
    client: HttpClient, page: int, page_size: int
) -> tuple[dict | None, str | None]:
    """Ambil satu halaman; kembalikan (payload, error)."""
    result = client.get(_pl_url(page, page_size))
    if result.get("status") != 200:
        return None, (
            f"http_{result.get('status')}: {result.get('error') or 'tanpa body'}"
        )
    payload = parse_json_body(result)
    if not isinstance(payload, dict):
        return None, "body_bukan_json"
    return payload, None


def parse_pl_results(payload: dict) -> list[dict]:
    """Ubah payload JSON fixtures PL menjadi list hasil/fixture.

    Setiap entri: home_team, away_team, kickoff (ISO UTC), status
    (kode apa adanya: "C" selesai, "U" dijadwalkan, "L" berjalan),
    matchweek (int | None), home_goals/away_goals (float | None —
    None untuk laga yang belum selesai), season_label (label musim
    mentah, mis. "English Premier League Season 2026/2027").
    Fixture tanpa dua tim atau tanpa kickoff dilewati.
    """
    fixtures: list[dict] = []
    if not isinstance(payload, dict):
        return fixtures
    for item in payload.get("content") or []:
        if not isinstance(item, dict):
            continue
        teams = item.get("teams") or []
        if len(teams) < 2:
            continue
        home = (teams[0].get("team") or {}).get("name") or (
            teams[0].get("team") or {}
        ).get("shortName")
        away = (teams[1].get("team") or {}).get("name") or (
            teams[1].get("team") or {}
        ).get("shortName")
        if not home or not away:
            continue
        kickoff = item.get("kickoff") or {}
        millis = kickoff.get("millis")
        if millis is None:
            continue
        try:
            kickoff_iso = datetime.fromtimestamp(
                float(millis) / 1000, tz=UTC
            ).isoformat()
        except (TypeError, ValueError, OverflowError):
            continue
        gameweek = item.get("gameweek") or {}
        matchweek = gameweek.get("gameweek")
        comp_season = gameweek.get("compSeason") or {}
        fixtures.append(
            {
                "home_team": home,
                "away_team": away,
                "kickoff": kickoff_iso,
                "status": item.get("status"),
                "matchweek": int(matchweek) if matchweek is not None else None,
                "home_goals": _to_float(teams[0].get("score")),
                "away_goals": _to_float(teams[1].get("score")),
                "season_label": (
                    comp_season.get("label")
                    if isinstance(comp_season.get("label"), str)
                    else None
                ),
            }
        )
    return fixtures


def _kickoff_range_millis(payload: dict) -> tuple[float | None, float | None]:
    """Kickoff (milidetik) paling awal & akhir di satu halaman, atau None."""
    lowest: float | None = None
    highest: float | None = None
    if not isinstance(payload, dict):
        return lowest, highest
    for item in payload.get("content") or []:
        if not isinstance(item, dict):
            continue
        millis = (item.get("kickoff") or {}).get("millis")
        if millis is None:
            continue
        try:
            value = float(millis)
        except (TypeError, ValueError):
            continue
        lowest = value if lowest is None else min(lowest, value)
        highest = value if highest is None else max(highest, value)
    return lowest, highest


def fetch_pl_results(
    client: HttpClient | None = None,
    now: datetime | None = None,
    past_days: int = DEFAULT_RESULTS_WINDOW_DAYS,
    future_days: int = 7,
    page_size: int = _PAGE_SIZE,
) -> FetchResult:
    """Ambil fixtures EPL (dengan skor) dalam jendela waktu.

    Jendela: [now - past_days, now + future_days]. Pencarian biner
    berdasarkan kickoff (halaman terurut menaik — arsip dimulai dari
    1992), lalu kumpulkan halaman sampai akhir jendela terlampaui
    (maks MAX_PAGES_AFTER_TARGET halaman). data: list hasil/fixture
    (lihat parse_pl_results). ``now`` bisa di-inject (untuk tes).
    """
    fetched_at = now_iso()
    moment = now or datetime.now(UTC)
    window_start = (moment - timedelta(days=past_days)).timestamp() * 1000
    window_end = (moment + timedelta(days=future_days)).timestamp() * 1000
    http = client or _default_client()

    first_page, error = _fetch_pl_page(http, 0, page_size)
    if error is not None:
        return FetchResult(
            source=pl_mod.SOURCE,
            tier=pl_mod.TIER,
            fetched_at=fetched_at,
            ok=False,
            error=error,
        )
    page_info = first_page.get("pageInfo") or {}
    try:
        num_pages = int(page_info.get("numPages") or 1)
    except (TypeError, ValueError):
        num_pages = 1
    pages_fetched = 1

    low, high = 0, max(num_pages - 1, 0)
    target_page = high
    while low <= high:
        mid = (low + high) // 2
        if mid == 0:
            payload = first_page
        else:
            payload, error = _fetch_pl_page(http, mid, page_size)
            pages_fetched += 1
            if error is not None:
                return FetchResult(
                    source=pl_mod.SOURCE,
                    tier=pl_mod.TIER,
                    fetched_at=fetched_at,
                    ok=False,
                    error=error,
                )
        _, highest = _kickoff_range_millis(payload)
        if highest is None or highest < window_start:
            low = mid + 1
        else:
            target_page = mid
            high = mid - 1

    fixtures: list[dict] = []
    page = target_page
    collected = 0
    while page < num_pages and collected < MAX_PAGES_AFTER_TARGET:
        if page == 0:
            payload = first_page
        else:
            payload, error = _fetch_pl_page(http, page, page_size)
            pages_fetched += 1
            if error is not None:
                return FetchResult(
                    source=pl_mod.SOURCE,
                    tier=pl_mod.TIER,
                    fetched_at=fetched_at,
                    ok=False,
                    error=error,
                )
        lowest, _ = _kickoff_range_millis(payload)
        if lowest is not None and lowest > window_end:
            break
        fixtures.extend(parse_pl_results(payload))
        collected += 1
        page += 1

    in_window = [
        fixture
        for fixture in fixtures
        if window_start
        <= datetime.fromisoformat(fixture["kickoff"]).timestamp() * 1000
        <= window_end
    ]
    return FetchResult(
        source=pl_mod.SOURCE,
        tier=pl_mod.TIER,
        fetched_at=fetched_at,
        ok=True,
        data=in_window,
        extra={"pages_fetched": pages_fetched, "past_days": past_days},
    )


# ---------------------------------------------------------------------------
# Cek cedera ESPN (selalu kosong — dicek ulang tiap jalan)
# ---------------------------------------------------------------------------


def check_espn_soccer_injuries(
    league: str = "EPL",
    client: HttpClient | None = None,
) -> FetchResult:
    """Cek endpoint cedera bola ESPN (1 request, cache 10 menit).

    data: list entri cedera (kosong sejak 2b — diverifikasi ulang
    2026-11-22). ok=True + data kosong berarti endpoint hidup tapi
    tidak memberi cedera apa pun (BUKAN error). ok=False berarti
    endpointnya sendiri tidak bisa dicek.
    """
    fetched_at = now_iso()
    slug = _ESPN_INJURY_LEAGUES.get(league)
    if slug is None:
        return FetchResult(
            "ESPN",
            2,
            fetched_at,
            False,
            error=f"liga_tidak_didukung_espn_injuries: {league!r}",
        )
    http = client or _default_client()
    try:
        resp = http.get(ESPN_SOCCER_INJURIES_URL.format(league=slug))
    except Exception as exc:  # noqa: BLE001 - cek gagal != crash
        return FetchResult(
            "ESPN", 2, fetched_at, False, error=f"network: {type(exc).__name__}"
        )
    if resp.get("status") != 200:
        return FetchResult(
            "ESPN", 2, fetched_at, False, error=f"http_{resp.get('status')}"
        )
    payload = parse_json_body(resp)
    if not isinstance(payload, dict) or not isinstance(payload.get("injuries"), list):
        return FetchResult("ESPN", 2, fetched_at, False, error="espn_format_changed")
    return FetchResult(
        "ESPN",
        2,
        fetched_at,
        True,
        data=payload["injuries"],
        extra={"n_injuries": len(payload["injuries"])},
    )


# ---------------------------------------------------------------------------
# Statistik dari hasil laga
# ---------------------------------------------------------------------------


def _gol_tim(fixture: dict, tim: str) -> tuple[float | None, float | None]:
    """(gol tim, gol lawan) untuk satu tim di satu hasil laga."""
    if matching.teams_match(fixture.get("home_team"), tim, "football"):
        return fixture.get("home_goals"), fixture.get("away_goals")
    return fixture.get("away_goals"), fixture.get("home_goals")


def _hasil_tim(hasil: list, tim: str) -> list[dict]:
    """Hasil-hasil satu tim (sudah selesai + berskor)."""
    return [
        fixture
        for fixture in hasil
        if matching.teams_match(fixture.get("home_team"), tim, "football")
        or matching.teams_match(fixture.get("away_team"), tim, "football")
    ]


def _ringkasan_hasil(hasil_tim: list, tim: str) -> dict:
    """Ringkasan {played, w, d, l, goals_for_per_match,
    goals_against_per_match} dari daftar hasil satu tim."""
    played = wins = draws = losses = 0
    gol: list[float] = []
    kebobolan: list[float] = []
    for fixture in hasil_tim:
        gf, ga = _gol_tim(fixture, tim)
        if gf is None or ga is None:
            continue
        played += 1
        if gf > ga:
            wins += 1
        elif gf < ga:
            losses += 1
        else:
            draws += 1
        gol.append(gf)
        kebobolan.append(ga)
    return {
        "played": played,
        "w": wins,
        "d": draws,
        "l": losses,
        "goals_for_per_match": _mean(gol),
        "goals_against_per_match": _mean(kebobolan),
    }


def _form5(hasil_tim: list, tim: str) -> list[dict]:
    """5 laga terakhir tim (terbaru dulu)."""
    recent = sorted(
        hasil_tim,
        key=lambda fixture: str(fixture.get("kickoff") or ""),
        reverse=True,
    )[:5]
    form = []
    for fixture in recent:
        gf, ga = _gol_tim(fixture, tim)
        if gf is None or ga is None:
            result = None
        elif gf > ga:
            result = "W"
        elif gf < ga:
            result = "L"
        else:
            result = "D"
        kandang = matching.teams_match(fixture.get("home_team"), tim, "football")
        form.append(
            {
                "match_date": str(fixture.get("kickoff") or "")[:10],
                "opponent": (
                    fixture.get("away_team") if kandang else fixture.get("home_team")
                ),
                "home": kandang,
                "result": result,
                "goals_for": gf,
                "goals_against": ga,
            }
        )
    return form


def _rekor(hasil_tim: list, tim: str, kandang: bool) -> dict:
    """Rekor kandang/tandang: {played, w, d, l, gf_per_match,
    ga_per_match}."""
    subset = [
        fixture
        for fixture in hasil_tim
        if matching.teams_match(fixture.get("home_team"), tim, "football") == kandang
    ]
    ringkasan = _ringkasan_hasil(subset, tim)
    return {
        "played": ringkasan["played"],
        "w": ringkasan["w"],
        "d": ringkasan["d"],
        "l": ringkasan["l"],
        "gf_per_match": ringkasan["goals_for_per_match"],
        "ga_per_match": ringkasan["goals_against_per_match"],
    }


def _laju(ringkasan_musim: dict, ringkasan_terakhir: dict, bobot: dict) -> tuple:
    """(laju_gol, laju_kebobolan): campuran 60% musim + 40% terakhir.

    Bobot dinormalisasi (dibagi jumlahnya) agar campuran tetap sah
    bila config memakai bobot yang jumlahnya bukan 1. Bila salah satu
    sisi None (tim belum main di jendela itu), sisi yang ada dipakai
    penuh — tim baru promosi di awal musim tetap punya laju dari
    laga yang sudah dimainkan. Bila keduanya None -> (None, None).
    """
    w_musim = bobot["season"] / (bobot["season"] + bobot["recent"])
    w_terakhir = bobot["recent"] / (bobot["season"] + bobot["recent"])

    def _campur(musim, terakhir):
        if musim is None and terakhir is None:
            return None
        if musim is None:
            return terakhir
        if terakhir is None:
            return musim
        return w_musim * musim + w_terakhir * terakhir

    return (
        _campur(
            ringkasan_musim.get("goals_for_per_match"),
            ringkasan_terakhir.get("goals_for_per_match"),
        ),
        _campur(
            ringkasan_musim.get("goals_against_per_match"),
            ringkasan_terakhir.get("goals_against_per_match"),
        ),
    )


def hitung_attack_defence(
    hasil: list,
    tim_target: list[str],
    bobot: dict,
) -> dict[str, dict]:
    """Hitung attack/defence ternormalisasi untuk tim-tim target.

    Murni (tanpa network): dari daftar hasil musim (lihat
    parse_pl_results). Mengembalikan {nama_tim: {"attack": float |
    None, "defence": float | None, "alasan": str | None}} — "alasan"
    terisi bila salah satu nilainya None ("belum_main" /
    "rata_liga_nol" / "laju_tidak_terhitung"). Normalisasi:
    attack/defence mentah tiap tim dibagi rata-rata seluruh tim liga
    yang nilainya terhitung, sehingga rata-rata liga = 1 persis.

    KONVENSI (Dixon-Coles standar, sama dengan fit pekerja A +
    football_sim): attack = laju_gol / rata-rata_gol_liga (lebih
    besar = lebih tajam); defence = laju_kebobolan /
    rata-rata_kebobolan_liga — KEBOCORAN (lebih besar = lebih bocor).
    Tim yang belum pernah kebobolan mendapat defence 0,0 (nilai sah,
    bukan None — simetris dengan attack 0,0 untuk tim yang belum
    pernah mencetak gol).
    """
    # Kumpulkan semua tim yang muncul di hasil.
    semua_tim: list[str] = []
    for fixture in hasil:
        for kunci in ("home_team", "away_team"):
            nama = fixture.get(kunci)
            if isinstance(nama, str) and nama and nama not in semua_tim:
                semua_tim.append(nama)
    n_laga = 0
    total_gol = 0.0
    for fixture in hasil:
        hg = fixture.get("home_goals")
        ag = fixture.get("away_goals")
        if hg is None or ag is None:
            continue
        n_laga += 1
        total_gol += hg + ag
    rata_liga = total_gol / (2 * n_laga) if n_laga > 0 else None

    mentah: dict[str, dict] = {}
    for tim in semua_tim:
        hasil_tim = _hasil_tim(hasil, tim)
        ringkasan_musim = _ringkasan_hasil(hasil_tim, tim)
        terakhir = sorted(
            hasil_tim, key=lambda f: str(f.get("kickoff") or ""), reverse=True
        )[: bobot["recent_matches"]]
        ringkasan_terakhir = _ringkasan_hasil(terakhir, tim)
        laju_gol, laju_kebobolan = _laju(ringkasan_musim, ringkasan_terakhir, bobot)
        mentah[tim] = {
            "laju_gol": laju_gol,
            "laju_kebobolan": laju_kebobolan,
            "played": ringkasan_musim["played"],
        }
    attack_mentah: dict[str, float] = {}
    defence_mentah: dict[str, float] = {}
    for tim, nilai in mentah.items():
        if rata_liga is None or rata_liga <= 0:
            continue
        if nilai["laju_gol"] is not None:
            attack_mentah[tim] = nilai["laju_gol"] / rata_liga
        # defence = KEBOCORAN (Dixon-Coles standar): laju kebobolan
        # dibagi rata-rata liga; 0,0 bila belum pernah kebobolan.
        if nilai["laju_kebobolan"] is not None:
            defence_mentah[tim] = nilai["laju_kebobolan"] / rata_liga
    rata_attack = _mean(list(attack_mentah.values()))
    rata_defence = _mean(list(defence_mentah.values()))

    hasil_akhir: dict[str, dict] = {}
    for tim in tim_target:
        nilai = mentah.get(tim)
        attack = defence = None
        alasan = None
        if nilai is None or nilai["played"] == 0:
            alasan = "belum_main"
        elif rata_liga is None or rata_liga <= 0:
            alasan = "rata_liga_nol"
        else:
            if tim in attack_mentah and rata_attack:
                attack = attack_mentah[tim] / rata_attack
            if tim in defence_mentah and rata_defence:
                defence = defence_mentah[tim] / rata_defence
            if attack is None or defence is None:
                alasan = "laju_tidak_terhitung"
        hasil_akhir[tim] = {
            "attack": attack,
            "defence": defence,
            "alasan": alasan,
        }
    return hasil_akhir


def _musim_dari_label(label: str | None, tanggal) -> str:
    """Musim "YYYY-YY" dari label compSeason PL, atau dari tanggal.

    Label mentah: "English Premier League Season 2026/2027" ->
    "2026-27". Fallback dari tanggal laga: Agu–Des -> musim yang
    dimulai tahun itu; Jan–Jul -> musim yang dimulai tahun sebelumnya.
    """
    if isinstance(label, str):
        cocok = _MUSIM_LABEL_RE.search(label)
        if cocok:
            return f"{cocok.group(1)}-{cocok.group(2)[2:]}"
    tahun = tanggal.year
    bulan = tanggal.month
    awal = tahun if bulan >= 8 else tahun - 1
    return f"{awal}-{str(awal + 1)[2:]}"


def _build_team_block(
    tim: str,
    prefix: str,
    hasil: list | None,
    bobot: dict,
    attack_defence: dict | None,
    missing: list,
) -> dict:
    """Rakit satu blok tim (lihat docstring modul untuk kontraknya).

    hasil None berarti fetch hasil gagal -> statistik None/kosong +
    dicatat di `missing`. attack_defence: hasil hitung_attack_defence
    (None bila hasil gagal).
    """
    block: dict = {
        "team": tim,
        "stats_season": {
            "played": 0,
            "w": 0,
            "d": 0,
            "l": 0,
            "goals_for_per_match": None,
            "goals_against_per_match": None,
        },
        "stats_last6": {
            "played": 0,
            "w": 0,
            "d": 0,
            "l": 0,
            "goals_for_per_match": None,
            "goals_against_per_match": None,
        },
        "form5": [],
        "home_record": {
            "played": 0,
            "w": 0,
            "d": 0,
            "l": 0,
            "gf_per_match": None,
            "ga_per_match": None,
        },
        "away_record": {
            "played": 0,
            "w": 0,
            "d": 0,
            "l": 0,
            "gf_per_match": None,
            "ga_per_match": None,
        },
        "attack": None,
        "defence": None,
        "injuries": [],
    }
    if hasil is None:
        missing.append(f"{prefix}.stats_season")
        missing.append(f"{prefix}.stats_last6")
        missing.append(f"{prefix}.form5")
        missing.append(f"{prefix}.home_record")
        missing.append(f"{prefix}.away_record")
        missing.append(f"{prefix}.attack")
        missing.append(f"{prefix}.defence")
        return block
    hasil_tim = _hasil_tim(hasil, tim)
    block["stats_season"] = _ringkasan_hasil(hasil_tim, tim)
    terakhir = sorted(
        hasil_tim, key=lambda f: str(f.get("kickoff") or ""), reverse=True
    )[: bobot["recent_matches"]]
    block["stats_last6"] = _ringkasan_hasil(terakhir, tim)
    block["form5"] = _form5(hasil_tim, tim)
    block["home_record"] = _rekor(hasil_tim, tim, kandang=True)
    block["away_record"] = _rekor(hasil_tim, tim, kandang=False)
    if attack_defence is not None:
        nilai = attack_defence.get(tim) or {}
        block["attack"] = nilai.get("attack")
        block["defence"] = nilai.get("defence")
        if block["attack"] is None:
            missing.append(f"{prefix}.attack")
        if block["defence"] is None:
            missing.append(f"{prefix}.defence")
    else:
        missing.append(f"{prefix}.attack")
        missing.append(f"{prefix}.defence")
    return block


def fetch_match_inputs(
    home_team: str,
    away_team: str,
    match_date: str,
    league: str = "EPL",
    client: HttpClient | None = None,
    cfg: dict | None = None,
) -> FetchResult:
    """Rakit input Otak Bola untuk satu laga EPL.

    home_team/away_team: nama tim (bentuk apa pun yang dikenali
    ingest.matching — "Liverpool", "Manchester United", "Man City").
    match_date: "YYYY-MM-DD" (tanggal kickoff). league: "EPL" saja
    (liga lain -> ok=False, liga_tidak_didukung). client: HttpClient
    bersama (opsional). cfg: dict playstyle untuk bobot laju gol +
    jendela hasil (opsional; None = baca playstyle.yaml).

    data: paket kontrak (lihat docstring modul). ok=False hanya bila
    SEMUA sumber gagal total atau input tidak valid. Kegagalan
    sebagian -> ok=True dengan field None/kosong + "missing" terisi +
    error tiap fetch di extra["fetch_errors"]. ValueError bila bobot
    di config ada tapi tidak valid. TIDAK PERNAH memanggil Odds API.
    TIDAK PERNAH memakai FPL sebagai sumber cedera (belum diratifikasi).
    """
    fetched_at = now_iso()
    home = (home_team or "").strip()
    away = (away_team or "").strip()
    if not home or not away:
        return FetchResult(
            SOURCE,
            TIER,
            fetched_at,
            False,
            error="nama_tim_kosong",
        )
    if matching.teams_match(home, away, "football"):
        return FetchResult(
            SOURCE,
            TIER,
            fetched_at,
            False,
            error=f"tim_kandang_sama_dengan_tandang: {home}",
        )
    if not isinstance(match_date, str) or not _TANGGAL_RE.match(match_date):
        return FetchResult(
            SOURCE,
            TIER,
            fetched_at,
            False,
            error=f"tanggal_tidak_valid: {match_date!r}",
        )
    try:
        target = datetime.strptime(match_date, "%Y-%m-%d").date()
    except ValueError:
        return FetchResult(
            SOURCE,
            TIER,
            fetched_at,
            False,
            error=f"tanggal_tidak_valid: {match_date!r}",
        )
    liga = (league or "").strip()
    if liga not in ("EPL", "Premier League"):
        return FetchResult(
            SOURCE,
            TIER,
            fetched_at,
            False,
            error=(
                f"liga_tidak_didukung: {league!r} — hanya EPL yang punya "
                "fetcher JSON resmi + ESPN di repo ini (LaLiga: tidak ada "
                "sumber tier 1, Kalshi hanya moneyline, cedera ESPN kosong)"
            ),
        )

    # Bobot laju gol + jendela hasil (config rusak -> ValueError).
    bobot, bobot_sumber = _baca_bobot(cfg)

    missing: list[str] = []
    sources: list[dict] = []
    fetch_errors: dict[str, str] = {}
    n_ok = 0

    # 1. Hasil + fixture PL resmi (tier 1) — bahan semua statistik.
    now_dt = datetime.combine(target, datetime.min.time(), tzinfo=UTC)
    pl_result = _safe_fetch(
        fetch_pl_results,
        client=client,
        now=now_dt,
        past_days=bobot["results_window_days"],
        future_days=7,
    )
    hasil_musim: list | None = None
    fixture_target: dict | None = None
    season_label: str | None = None
    if pl_result.ok:
        sources.append(_source_entry("football_results", pl_result))
        n_ok += 1
        semua = pl_result.data or []
        hasil_musim = [
            fixture
            for fixture in semua
            if fixture.get("status") == "C"
            and fixture.get("home_goals") is not None
            and fixture.get("away_goals") is not None
            and str(fixture.get("kickoff") or "")[:10] < match_date
        ]
        for fixture in semua:
            if not (
                matching.teams_match(fixture.get("home_team"), home, "football")
                and matching.teams_match(fixture.get("away_team"), away, "football")
            ):
                continue
            try:
                kickoff_date = datetime.fromisoformat(fixture["kickoff"]).date()
            except (KeyError, TypeError, ValueError):
                continue
            if abs((kickoff_date - target).days) <= 1:
                fixture_target = fixture
                season_label = fixture.get("season_label")
                break
        if fixture_target is None:
            missing.append("fixture_target_tidak_ditemukan")
    else:
        fetch_errors["pl_results"] = pl_result.error or "gagal"
        missing.append("football_results")

    # 2. ESPN scoreboard (tier 2, CADANGAN fixture) — hanya bila PL gagal.
    if pl_result.ok is False:
        from ingest import espn as espn_mod

        espn_result = _safe_fetch(
            espn_mod.fetch_scoreboard, "epl", match_date, client=client
        )
        if espn_result.ok:
            sources.append(_source_entry("football_fixture_espn", espn_result))
            n_ok += 1
            for game in espn_result.data or []:
                if not isinstance(game, dict):
                    continue
                if matching.teams_match(
                    game.get("home_team"), home, "football"
                ) and matching.teams_match(game.get("away_team"), away, "football"):
                    fixture_target = {
                        "home_team": game.get("home_team"),
                        "away_team": game.get("away_team"),
                        "kickoff": game.get("start_time"),
                        "status": game.get("status"),
                        "matchweek": None,
                        "home_goals": None,
                        "away_goals": None,
                        "season_label": None,
                    }
                    break
            if fixture_target is None:
                missing.append("fixture_target_tidak_ditemukan")
        else:
            fetch_errors["espn_scoreboard"] = espn_result.error or "gagal"
            missing.append("football_fixture_espn")

    # 3. Cek cedera ESPN (selalu kosong sejak 2b — diverifikasi ulang
    # tiap jalan; FPL TIDAK dipakai — belum diratifikasi user).
    cedera_espn = _safe_fetch(check_espn_soccer_injuries, league="EPL", client=client)
    injury_checked: list[dict] = []
    entri_cedera_espn: list = []
    if cedera_espn.ok:
        sources.append(_source_entry("football_injuries_espn", cedera_espn))
        entri_cedera_espn = cedera_espn.data or []
        injury_checked.append(
            {
                "source": "ESPN injuries (eng.1)",
                "result": (
                    f"hidup, {len(entri_cedera_espn)} entri"
                    if entri_cedera_espn
                    else "hidup, kosong (0 entri)"
                ),
            }
        )
    else:
        fetch_errors["espn_injuries"] = cedera_espn.error or "gagal"
        injury_checked.append(
            {
                "source": "ESPN injuries (eng.1)",
                "result": f"gagal dicek: {cedera_espn.error or 'gagal'}",
            }
        )
    injury_checked.append(
        {
            "source": "Premier League official",
            "result": "tidak ada endpoint/halaman cedera (404)",
        }
    )
    injury_checked.append(
        {
            "source": "Fantasy Premier League API",
            "result": "tidak dipakai — belum diratifikasi user",
        }
    )
    # Cedera ESPN (bila suatu hari terisi) dihitung sebagai sumber ke-1.
    # Entri yang relevan dengan kedua tim laga ini dicatat apa adanya.
    n_sumber_cedera = 1 if entri_cedera_espn else 0
    cedera_relevan: list[dict] = []
    for entri in entri_cedera_espn:
        if not isinstance(entri, dict):
            continue
        tim_entri = entri.get("team") or ""
        if matching.teams_match(tim_entri, home, "football") or matching.teams_match(
            tim_entri, away, "football"
        ):
            cedera_relevan.append(entri)
    missing.append("injuries_tidak_terkonfirmasi")

    # Rata-rata liga + attack/defence.
    league_info: dict = {
        "avg_goals_per_team_match": None,
        "n_matches": 0,
        "n_teams": 0,
    }
    attack_defence = None
    if hasil_musim is not None:
        n_laga = 0
        total_gol = 0.0
        tim_set: set[str] = set()
        for fixture in hasil_musim:
            hg = fixture.get("home_goals")
            ag = fixture.get("away_goals")
            if hg is None or ag is None:
                continue
            n_laga += 1
            total_gol += hg + ag
            for kunci in ("home_team", "away_team"):
                if isinstance(fixture.get(kunci), str):
                    tim_set.add(fixture[kunci])
        league_info["n_matches"] = n_laga
        league_info["n_teams"] = len(tim_set)
        if n_laga > 0:
            league_info["avg_goals_per_team_match"] = total_gol / (2 * n_laga)
        else:
            missing.append("league.avg_goals_per_team_match")
        attack_defence = hitung_attack_defence(hasil_musim, [home, away], bobot)
    else:
        missing.append("league.avg_goals_per_team_match")

    home_block = _build_team_block(
        home, "home", hasil_musim, bobot, attack_defence, missing
    )
    away_block = _build_team_block(
        away, "away", hasil_musim, bobot, attack_defence, missing
    )
    # Cedera ESPN yang relevan (bila ada) masuk blok timnya; bila tidak
    # ada, blok injuries tetap kosong (jujur: tidak ada data).
    for entri in cedera_relevan:
        tim_entri = entri.get("team") or ""
        blok = (
            home_block
            if matching.teams_match(tim_entri, home, "football")
            else away_block
        )
        blok["injuries"].append(
            {
                "player": entri.get("player"),
                "status": entri.get("status"),
                "team": tim_entri,
                "sources": ["ESPN"],
            }
        )

    # H2H 5 pertemuan terakhir (dari hasil yang tersedia).
    h2h: list[dict] = []
    if hasil_musim is not None:
        meetings = [
            fixture
            for fixture in hasil_musim
            if (
                matching.teams_match(fixture.get("home_team"), home, "football")
                and matching.teams_match(fixture.get("away_team"), away, "football")
            )
            or (
                matching.teams_match(fixture.get("home_team"), away, "football")
                and matching.teams_match(fixture.get("away_team"), home, "football")
            )
        ]
        meetings.sort(key=lambda f: str(f.get("kickoff") or ""), reverse=True)
        h2h = [
            {
                "match_date": str(f.get("kickoff") or "")[:10],
                "home_team": f.get("home_team"),
                "away_team": f.get("away_team"),
                "home_goals": f.get("home_goals"),
                "away_goals": f.get("away_goals"),
            }
            for f in meetings[:5]
        ]
    else:
        missing.append("h2h_last5")

    data = {
        "match": {
            "home_team": home,
            "away_team": away,
            "match_date": match_date,
            "season": _musim_dari_label(season_label, target),
            "league": "EPL",
            "matchweek": (fixture_target.get("matchweek") if fixture_target else None),
            "kickoff": (fixture_target.get("kickoff") if fixture_target else None),
        },
        "home": home_block,
        "away": away_block,
        "h2h_last5": h2h,
        "league": league_info,
        "weights": {
            "season": bobot["season"],
            "recent": bobot["recent"],
            "recent_matches": bobot["recent_matches"],
            "source": bobot_sumber,
        },
        "injuries_status": {
            "n_sources": n_sumber_cedera,
            "confirmed": n_sumber_cedera >= 2,
            "note": (
                "cedera tidak terkonfirmasi: tidak ada sumber cedera bola "
                "yang bisa dipakai (ESPN kosong; FPL belum diratifikasi) — "
                "B2 butuh 2 sumber"
            ),
        },
        "injury_sources_checked": injury_checked,
        "missing": missing,
        "sources": sources,
        "fetched_at": fetched_at,
    }
    ok = n_ok > 0
    error = None
    if not ok:
        error = "semua_sumber_gagal: " + "; ".join(
            f"{kind}={msg}" for kind, msg in fetch_errors.items()
        )
    extra: dict = {}
    if fetch_errors:
        extra["fetch_errors"] = fetch_errors
    return FetchResult(
        SOURCE, TIER, fetched_at, ok, data=data, error=error, extra=extra
    )
