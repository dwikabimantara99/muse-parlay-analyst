"""Penarik stats.nba.com: scoreboard harian + klasemen NBA (jenjang 1).

Sumber UTAMA jadwal/statistik NBA (config/sources.yaml nba_schedule_stats).
Endpoint dipakai persis dari probe 2a (probes/nba_com.py): scoreboardv2 dan
leaguestandingsv3, dengan header STATS_HEADERS yang sama. CDN scoreboard
(cdn.nba.com/.../todaysScoreboard_00.json) 403 dari VM ini — TIDAK dipakai.

Catatan bentuk respons (terverifikasi dari cache probe 2a + panggilan live
2026-11-20 s.d. 2026-11-22):

- scoreboardv2 mengembalikan resultSets GameHeader + LineScore (+ lainnya).
  GameHeader hanya memuat ID tim (HOME_TEAM_ID/VISITOR_TEAM_ID); nama tim
  dan tricode diambil dari LineScore (TEAM_ABBREVIATION, TEAM_CITY_NAME,
  TEAM_NAME) dengan join per TEAM_ID.
- GAME_STATUS_TEXT berisi jam tip-off ("7:00 pm ET") untuk laga yang belum
  mulai, "Final"/"Halftime"/"Q3 5:32" untuk laga berjalan/selesai. start_time
  hanya bisa diparsing dari teks jam tip-off; untuk laga tanpa teks jam,
  start_time None (jam tip-off tidak ada di respons).
- leaguestandingsv3 TIDAK memuat tricode; tricode diambil dari peta statis
  TEAM_TRICODES (30 tim, ketiganya terverifikasi dari LineScore live).
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from ingest.common import (
    DiskCache,
    FetchResult,
    HttpClient,
    RateLimiter,
    default_cache_dir,
    now_iso,
    parse_json_body,
)

SOURCE = "stats.nba.com"
TIER = 1
CACHE_TTL_SECONDS = 600
RATE_GAP_SECONDS = 1.0

# Header persis dari probes/nba_com.py (STATS_HEADERS) — jangan diubah
# tanpa bukti, karena stats.nba.com menolak request tanpa header ini.
STATS_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
}

SCOREBOARD_URL = "https://stats.nba.com/stats/scoreboardv2"
STANDINGS_URL = "https://stats.nba.com/stats/leaguestandingsv3"

# Zona waktu tanggal scoreboard NBA (GAME_DATE_EST).
EASTERN = ZoneInfo("America/New_York")

# Jam tip-off di GAME_STATUS_TEXT, misal "7:00 pm ET" / "10:30 am ET".
_TIPOFF_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(am|pm)\s*ET", re.I)

# TeamID stats.nba.com -> tricode. Seluruh 30 tim terverifikasi dari
# LineScore live (scoreboardv2 2026-11-20, 2026-11-21, 2026-11-22).
TEAM_TRICODES = {
    1610612737: "ATL",
    1610612738: "BOS",
    1610612739: "CLE",
    1610612740: "NOP",
    1610612741: "CHI",
    1610612742: "DAL",
    1610612743: "DEN",
    1610612744: "GSW",
    1610612745: "HOU",
    1610612746: "LAC",
    1610612747: "LAL",
    1610612748: "MIA",
    1610612749: "MIL",
    1610612750: "MIN",
    1610612751: "BKN",
    1610612752: "NYK",
    1610612753: "ORL",
    1610612754: "IND",
    1610612755: "PHI",
    1610612756: "PHX",
    1610612757: "POR",
    1610612758: "SAC",
    1610612759: "SAS",
    1610612760: "OKC",
    1610612761: "TOR",
    1610612762: "UTA",
    1610612763: "MEM",
    1610612764: "WAS",
    1610612765: "DET",
    1610612766: "CHA",
}


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
        extra_headers=STATS_HEADERS,
    )


def _result_sets(data: dict) -> dict[str, dict]:
    """Ubah resultSets stats.nba.com jadi dict nama -> {headers, rowSet}."""
    sets: dict[str, dict] = {}
    for result_set in data.get("resultSets") or []:
        if isinstance(result_set, dict) and result_set.get("name"):
            sets[result_set["name"]] = result_set
    return sets


def _rows(result_set: dict | None) -> list[dict]:
    """Ubah satu resultSet jadi list dict (header -> nilai per baris)."""
    if not result_set:
        return []
    headers = result_set.get("headers") or []
    rows = []
    for row in result_set.get("rowSet") or []:
        if isinstance(row, list) and len(row) == len(headers):
            rows.append(dict(zip(headers, row, strict=True)))
    return rows


def _parse_tipoff(game_date_est: str, status_text: str) -> str | None:
    """Parse jam tip-off dari GAME_STATUS_TEXT jadi ISO 8601.

    game_date_est: tanggal laga "YYYY-MM-DDTHH:MM:SS" (tengah malam ET).
    status_text: misal "7:00 pm ET". Mengembalikan None bila teks status
    bukan jam tip-off (laga berjalan/selesai).
    """
    match = _TIPOFF_RE.search(status_text or "")
    if not match:
        return None
    try:
        day = datetime.strptime(game_date_est[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    hour = int(match.group(1)) % 12
    if match.group(3).lower() == "pm":
        hour += 12
    tipoff = datetime(day.year, day.month, day.day, hour, int(match.group(2)))
    return tipoff.replace(tzinfo=EASTERN).isoformat()


def parse_scoreboard(data: dict) -> list[dict]:
    """Ubah respons JSON scoreboardv2 jadi list game.

    Setiap game: game_id, home_team, away_team, home_tricode,
    away_tricode, start_time (ISO atau None bila tidak ada jam tip-off
    di respons), status (GAME_STATUS_TEXT apa adanya), status_id,
    game_date_est. ValueError("stats_nba_format_changed") bila struktur
    resultSets yang diharapkan tidak ada.
    """
    sets = _result_sets(data)
    if "GameHeader" not in sets or "LineScore" not in sets:
        raise ValueError("stats_nba_format_changed")
    teams: dict[int, dict] = {}
    for row in _rows(sets["LineScore"]):
        team_id = row.get("TEAM_ID")
        if isinstance(team_id, int):
            city = row.get("TEAM_CITY_NAME") or ""
            name = row.get("TEAM_NAME") or ""
            teams[team_id] = {
                "name": f"{city} {name}".strip() or None,
                "tricode": row.get("TEAM_ABBREVIATION"),
            }
    games = []
    for row in _rows(sets["GameHeader"]):
        home_id = row.get("HOME_TEAM_ID")
        away_id = row.get("VISITOR_TEAM_ID")
        home = teams.get(home_id, {}) if isinstance(home_id, int) else {}
        away = teams.get(away_id, {}) if isinstance(away_id, int) else {}
        status_text = row.get("GAME_STATUS_TEXT") or ""
        games.append(
            {
                "game_id": str(row.get("GAME_ID")),
                "home_team": home.get("name"),
                "away_team": away.get("name"),
                "home_tricode": home.get("tricode"),
                "away_tricode": away.get("tricode"),
                "start_time": _parse_tipoff(
                    str(row.get("GAME_DATE_EST") or ""), status_text
                ),
                "status": status_text,
                "status_id": row.get("GAME_STATUS_ID"),
                "game_date_est": str(row.get("GAME_DATE_EST") or "")[:10] or None,
            }
        )
    return games


def parse_standings(data: dict) -> list[dict]:
    """Ubah respons JSON leaguestandingsv3 jadi list klasemen tim.

    Setiap tim: team ("Kota Nama"), tricode (dari TEAM_TRICODES),
    wins, losses, win_pct, conference, division, division_rank,
    playoff_rank, league_rank, record, home, road, l10, current_streak,
    points_pg, opp_points_pg, diff_points_pg. ValueError
    ("stats_nba_format_changed") bila resultSet Standings tidak ada.
    """
    sets = _result_sets(data)
    if "Standings" not in sets:
        raise ValueError("stats_nba_format_changed")
    standings = []
    for row in _rows(sets["Standings"]):
        city = row.get("TeamCity") or ""
        name = row.get("TeamName") or ""
        standings.append(
            {
                "team": f"{city} {name}".strip(),
                "tricode": TEAM_TRICODES.get(row.get("TeamID")),
                "wins": row.get("WINS"),
                "losses": row.get("LOSSES"),
                "win_pct": row.get("WinPCT"),
                "conference": row.get("Conference"),
                "division": row.get("Division"),
                "division_rank": row.get("DivisionRank"),
                "playoff_rank": row.get("PlayoffRank"),
                "league_rank": row.get("LeagueRank"),
                "record": row.get("Record"),
                "home": row.get("HOME"),
                "road": row.get("ROAD"),
                "l10": row.get("L10"),
                "current_streak": row.get("strCurrentStreak"),
                "points_pg": row.get("PointsPG"),
                "opp_points_pg": row.get("OppPointsPG"),
                "diff_points_pg": row.get("DiffPointsPG"),
            }
        )
    return standings


def fetch_scoreboard(date_str: str, client: HttpClient | None = None) -> FetchResult:
    """Ambil scoreboard NBA untuk satu tanggal (waktu US Eastern).

    date_str: "YYYY-MM-DD" (tanggal Eastern, sesuai GAME_DATE_EST).
    data: list game (lihat parse_scoreboard). Fetch gagal -> ok=False
    dengan error (tidak melempar).
    """
    fetched_at = now_iso()
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return FetchResult(
            SOURCE, TIER, fetched_at, False, error=f"tanggal_tidak_valid: {date_str!r}"
        )
    game_date = f"{day.month}/{day.day}/{day.year}"
    url = f"{SCOREBOARD_URL}?GameDate={game_date}&LeagueID=00&DayOffset=0"
    resp = (client or _default_client()).get(url)
    if resp.get("status") != 200:
        return FetchResult(
            SOURCE,
            TIER,
            fetched_at,
            False,
            error=f"http_{resp.get('status')}: {resp.get('error') or 'scoreboardv2 gagal'}",
        )
    data = parse_json_body(resp)
    if not isinstance(data, dict):
        return FetchResult(
            SOURCE, TIER, fetched_at, False, error="stats_nba_format_changed"
        )
    try:
        games = parse_scoreboard(data)
    except ValueError as exc:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=str(exc))
    extra: dict = {"date": date_str, "n_games": len(games)}
    missing = sorted(
        {
            game["game_id"]
            for game in games
            if game["home_team"] is None or game["away_team"] is None
        }
    )
    if missing:
        extra["games_tanpa_nama_tim"] = missing
    return FetchResult(SOURCE, TIER, fetched_at, True, data=games, extra=extra)


def fetch_standings(
    client: HttpClient | None = None, season: str = "2026-27"
) -> FetchResult:
    """Ambil klasemen NBA musim reguler (leaguestandingsv3).

    season: "YYYY-YY" (musim berjalan 2026-27; probe 2a memakai
    2025-26). data: list klasemen tim (lihat parse_standings).
    Fetch gagal -> ok=False dengan error (tidak melempar).
    """
    fetched_at = now_iso()
    url = f"{STANDINGS_URL}?LeagueID=00&Season={season}" "&SeasonType=Regular%20Season"
    resp = (client or _default_client()).get(url)
    if resp.get("status") != 200:
        return FetchResult(
            SOURCE,
            TIER,
            fetched_at,
            False,
            error=(
                f"http_{resp.get('status')}: "
                f"{resp.get('error') or 'leaguestandingsv3 gagal'}"
            ),
        )
    data = parse_json_body(resp)
    if not isinstance(data, dict):
        return FetchResult(
            SOURCE, TIER, fetched_at, False, error="stats_nba_format_changed"
        )
    try:
        standings = parse_standings(data)
    except ValueError as exc:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=str(exc))
    extra: dict = {"season": season, "n_teams": len(standings)}
    unknown = [row["team"] for row in standings if row["tricode"] is None]
    if unknown:
        extra["teams_tanpa_tricode"] = unknown
    return FetchResult(SOURCE, TIER, fetched_at, True, data=standings, extra=extra)
