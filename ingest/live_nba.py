"""Umpan skor live NBA dari scoreboard + summary ESPN (Tahap 3 langkah 4).

Modul ini dibuat terpisah dari ingest/espn.py karena parser scoreboard
lama di sana hanya mengembalikan tim/waktu/status tanpa skor. Parser di
sini membaca skor, kuarter, jam, dan skor per kuarter untuk pantauan
live on-demand (pekerja B/C langkah 4).

FAKTA FORMAT ESPN (terverifikasi live 2026-11-22 dari respons asli):
- Skor kompetitor adalah STRING ("132"), bukan angka — parser mengubah
  ke int, None bila tidak bisa diubah.
- Skor per kuarter ada di kunci "linescores" (huruf kecil semua) dengan
  entri {"displayValue": "29"} — BUKAN "lineScores"/"value" seperti
  dugaan awal. Parser membaca "linescores"/"displayValue" dulu, dengan
  fallback "lineScores"/"value" bila ESPN mengubah casing.
- Pada laga yang belum mulai, kunci "linescores" TIDAK ADA dan skor
  adalah "0" — parser mengembalikan line_scores [] dan skor None
  (laga belum mulai tidak punya skor).
- Tanggal parameter "dates" ESPN adalah tanggal Amerika Timur: laga
  2026-11-21 (dates=20261121) punya field date UTC 2026-11-21T18:00Z
  s.d. 2026-11-22T03:00Z. Karena itu tanggal match_id diambil dari
  date_str yang diminta (tanggal AS), atau — bila parser dipanggil
  tanpa date_str — dari field date event yang dikonversi ke
  America/New_York. Field date UTC mentah TIDAK dipakai langsung
  (laga malam AS akan jatuh ke tanggal UTC keesokan hari).
- Summary boxscore: statistik tim hanya punya "displayValue" bentuk
  "16-44" (made-attempted) untuk 3PT dan FT — tidak ada field numerik
  terpisah. Parser memecah string itu; gagal pecah -> None.
- Singkatan tim ESPN BERBEDA dari tricode repo untuk 6 tim: GS->GSW,
  NY->NYK, NO->NOP, SA->SAS, UTAH->UTA, WSH->WAS (tricode repo
  mengikuti stats.nba.com, lihat ingest/stats_nba.py TEAM_TRICODES;
  terverifikasi dari ke-30 singkatan ESPN di scoreboard 21–23 Nov
  2026 — UTAH ditemukan lewat pantau live DAL@UTA, WSH mentah
  dikonfirmasi dari JSON asli). Parser memetakan singkatan ESPN ke
  tricode repo (_ESPN_KE_TRICODE) agar match_id live tersambung ke
  kaki tiket dan baseline BBRef (keputusan koordinator langkah 4;
  tanpa ini laga 6 tim itu tidak pernah join).

KONTRAK LiveGame (kunci dict, JANGAN diubah — dipakai pekerja B/C):
  match_id, espn_game_id, home_abbr, away_abbr, home_team, away_team,
  status, period, clock_display, seconds_remaining, home_score,
  away_score, line_scores, stats, fetched_at, source.

Aturan nilai yang tidak ada (DATA_INCOMPLETE, jangan ditebak):
- Laga belum mulai: period/clock_display/seconds_remaining/skor None.
- Laga selesai: seconds_remaining 0, clock_display None.
- Laga OT (period > 4): seconds_remaining 0 (regulasi habis); period
  sendiri mencatat nomor periode OT.
- Event yang rusak (tanpa id/tim/status yang dikenal/tanggal yang
  bisa dipakai) DILEWATI — satu event rusak tidak boleh mematikan
  seluruh tanggal. Hanya struktur tingkat atas yang salah (data bukan
  dict, "events" bukan list) yang melempar
  ValueError("espn_format_changed").
- stats selalu None di sini — diisi pekerja stats langkah 4.

Tanpa cache disk: pantauan live bersifat on-demand dan data berubah
tiap detik; cache akan menyajikan skor basi. Rate limit tetap dijaga
satu _LIMITER bersama per modul (1 dtk), seperti modul ingest lain.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

from ingest.common import (
    FetchResult,
    HttpClient,
    RateLimiter,
    now_iso,
    parse_json_body,
)

SOURCE = "espn_scoreboard"
TIER = 2
RATE_GAP_SECONDS = 1.0

SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
)
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"

# Zona waktu tanggal scoreboard NBA (parameter dates ESPN).
EASTERN = ZoneInfo("America/New_York")

# Durasi satu kuarter regulasi NBA (detik); total regulasi 4 x 720 = 2880.
_QUARTER_SECONDS = 720

# Pemetaan status.type.state ESPN -> status ternormalisasi LiveGame.
_STATUS_MAP = {
    "pre": "belum_mulai",
    "in": "berjalan",
    "post": "selesai",
}

# Singkatan ESPN -> tricode repo (stats.nba.com). 24 tim lain sama
# di kedua sumber; 6 tim ini berbeda (lihat docstring modul).
_ESPN_KE_TRICODE = {
    "GS": "GSW",
    "NY": "NYK",
    "NO": "NOP",
    "SA": "SAS",
    "UTAH": "UTA",
    "WSH": "WAS",
}


def _tricode(abbr: str) -> str:
    """Singkatan ESPN -> tricode repo (tidak dikenal -> apa adanya)."""
    return _ESPN_KE_TRICODE.get(abbr, abbr)


# Nama statistik boxscore summary ESPN (displayValue "made-attempted").
_STAT_3PT = "threePointFieldGoalsMade-threePointFieldGoalsAttempted"
_STAT_FT = "freeThrowsMade-freeThrowsAttempted"

# Satu limiter untuk SEMUA request modul ini (dibagi semua pemanggilan),
# seperti modul ingest lain — lihat tests/test_rate_limit_sharing.py.
_LIMITER = RateLimiter(RATE_GAP_SECONDS)


def _default_client() -> HttpClient:
    """Buat HttpClient default (jeda 1 dtk, tanpa cache — skor live)."""
    return HttpClient(_LIMITER, cache=None)


def _to_int(value: object) -> int | None:
    """Ubah nilai ESPN (string angka / angka) jadi int, None bila gagal."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            try:
                number = float(text)
            except ValueError:
                return None
            return int(number) if number.is_integer() else None
    return None


def _parse_clock_seconds(display_clock: object) -> int | None:
    """Ubah displayClock ESPN jadi detik tersisa dalam kuarter itu.

    Format yang dikenal: "M:SS" (misal "5:32" -> 332) dan detik polos
    ("45.2" -> 45, "0.0" -> 0). None bila tidak bisa diurai.
    """
    if not isinstance(display_clock, str):
        return None
    text = display_clock.strip()
    if not text:
        return None
    try:
        if ":" in text:
            minutes_part, seconds_part = text.split(":", 1)
            minutes = int(minutes_part.strip())
            seconds = float(seconds_part.strip())
            total = minutes * 60 + seconds
        else:
            total = float(text)
    except ValueError:
        return None
    if total < 0:
        return None
    return int(total)


def compute_seconds_remaining(
    period: int | None, display_clock: str | None, state: str
) -> int | None:
    """Hitung TOTAL detik tersisa sampai akhir regulasi 48 menit.

    period: nomor kuarter (1-4 regulasi, >4 berarti OT). display_clock:
    displayClock ESPN ("5:32" / "45.2"). state: status.type.state ESPN
    ("pre"/"in"/"post").
    - selesai -> 0; belum mulai -> None.
    - OT (period > 4) -> 0 (regulasi sudah habis; period mencatat OT).
    - berjalan -> (4 - period) * 720 + detik jam kuarter itu.
    - period/jam tidak diketahui saat berjalan -> None (jangan ditebak).
    """
    if state == "post":
        return 0
    if state != "in":
        return None
    if period is None or period < 1:
        return None
    if period > 4:
        return 0
    clock_seconds = _parse_clock_seconds(display_clock)
    if clock_seconds is None:
        return None
    return (4 - period) * _QUARTER_SECONDS + clock_seconds


def _team_name(competitor: dict | None) -> str | None:
    """Nama tim dari satu kompetitor (displayName, fallback nama pendek)."""
    if not competitor:
        return None
    team = competitor.get("team") or {}
    if not isinstance(team, dict):
        return None
    return team.get("displayName") or team.get("name") or team.get("shortDisplayName")


def _team_abbr(competitor: dict | None) -> str | None:
    """Tricode repo satu kompetitor (singkatan ESPN dipetakan).

    Misal ESPN "NY" -> "NYK" agar match_id cocok format artefak.
    """
    if not competitor:
        return None
    team = competitor.get("team") or {}
    if not isinstance(team, dict):
        return None
    abbr = team.get("abbreviation")
    return _tricode(abbr) if isinstance(abbr, str) and abbr else None


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


def _line_scores(competitor: dict | None) -> list[int]:
    """Skor per kuarter satu kompetitor (dari "linescores").

    Kunci asli ESPN "linescores" (huruf kecil), entri {"displayValue":
    "29"}; fallback "lineScores"/"value". Entri yang tidak bisa diubah
    ke int dilewati. [] bila kuncinya tidak ada (misal laga belum mulai).
    """
    if not competitor:
        return []
    entries = competitor.get("linescores")
    if not isinstance(entries, list):
        entries = competitor.get("lineScores")
    if not isinstance(entries, list):
        return []
    scores: list[int] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        value = _to_int(entry.get("displayValue"))
        if value is None:
            value = _to_int(entry.get("value"))
        if value is not None:
            scores.append(value)
    return scores


def _valid_date_str(date_str: object) -> str | None:
    """Kembalikan date_str bila formatnya "YYYY-MM-DD", None bila bukan."""
    if not isinstance(date_str, str):
        return None
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None
    return date_str


def _event_date_eastern(event: dict) -> str | None:
    """Tanggal laga (YYYY-MM-DD) dari field date event, zona Timur AS.

    Field date ESPN adalah ISO UTC; dikonversi ke America/New_York
    agar cocok dengan parameter dates ESPN (tanggal AS). None bila
    field date tidak ada / tidak bisa diurai.
    """
    raw = event.get("date")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.date().isoformat()
    return parsed.astimezone(EASTERN).date().isoformat()


def _parse_live_event(
    event: dict, date_str: str | None, fetched_at: str
) -> dict | None:
    """Ubah satu event scoreboard jadi dict LiveGame, None bila rusak.

    Event dilewati (None) bila id/tim/status/tanggal tidak lengkap —
    lihat docstring modul soal aturan event rusak.
    """
    espn_game_id = event.get("id")
    if espn_game_id is None or str(espn_game_id) == "":
        return None
    home, away = _competitors(event)
    home_abbr = _team_abbr(home)
    away_abbr = _team_abbr(away)
    if home_abbr is None or away_abbr is None:
        return None
    status = event.get("status") or {}
    status_type = status.get("type") or {} if isinstance(status, dict) else {}
    state = status_type.get("state") if isinstance(status_type, dict) else None
    if state not in _STATUS_MAP:
        return None
    game_date = _valid_date_str(date_str) or _event_date_eastern(event)
    if game_date is None:
        return None
    period = None
    if state in ("in", "post"):
        period = _to_int(status.get("period")) if isinstance(status, dict) else None
    display_clock = status.get("displayClock") if isinstance(status, dict) else None
    clock_display = (
        display_clock if state == "in" and isinstance(display_clock, str) else None
    )
    if state == "pre":
        home_score = away_score = None
    else:
        home_score = _to_int(home.get("score")) if home else None
        away_score = _to_int(away.get("score")) if away else None
    return {
        "match_id": f"{away_abbr}@{home_abbr}_{game_date}",
        "espn_game_id": str(espn_game_id),
        "home_abbr": home_abbr,
        "away_abbr": away_abbr,
        "home_team": _team_name(home),
        "away_team": _team_name(away),
        "status": _STATUS_MAP[state],
        "period": period,
        "clock_display": clock_display,
        "seconds_remaining": compute_seconds_remaining(period, display_clock, state),
        "home_score": home_score,
        "away_score": away_score,
        "line_scores": {
            home_abbr: _line_scores(home),
            away_abbr: _line_scores(away),
        },
        "stats": None,
        "fetched_at": fetched_at,
        "source": SOURCE,
    }


def parse_live_scoreboard(
    data: dict, date_str: str | None = None, fetched_at: str | None = None
) -> list[dict]:
    """Ubah respons JSON scoreboard ESPN jadi list dict LiveGame.

    date_str: tanggal yang diminta ("YYYY-MM-DD", tanggal AS) — dipakai
    untuk match_id; bila tidak diberikan, tanggal diambil per event
    dari field date yang dikonversi ke zona Timur AS. fetched_at: jam
    pengambilan (default: sekarang, ISO UTC).
    ValueError("espn_format_changed") bila data bukan dict atau field
    events tidak ada/bukan list. Event yang rusak dilewati (bukan error).
    """
    if not isinstance(data, dict):
        raise ValueError("espn_format_changed")
    events = data.get("events")
    if not isinstance(events, list):
        raise ValueError("espn_format_changed")
    taken_at = fetched_at or now_iso()
    games: list[dict] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        game = _parse_live_event(event, date_str, taken_at)
        if game is not None:
            games.append(game)
    return games


def _fetch_json(url: str, client: HttpClient | None) -> tuple[dict | None, str | None]:
    """GET satu URL JSON ESPN; kembalikan (data, error). error None bila OK."""
    resp = (client or _default_client()).get(url)
    if resp.get("status") != 200:
        return None, f"http_{resp.get('status')}: {resp.get('error') or 'espn gagal'}"
    data = parse_json_body(resp)
    if not isinstance(data, dict):
        return None, "espn_format_changed"
    return data, None


def fetch_live_games(
    date_str: str | None = None, client: HttpClient | None = None
) -> FetchResult:
    """Ambil skor live NBA satu tanggal dari scoreboard ESPN.

    date_str: "YYYY-MM-DD" (tanggal AS); default hari ini zona Timur AS.
    Satu panggilan mengembalikan semua laga tanggal itu. data: list
    dict LiveGame (lihat parse_live_scoreboard). Fetch gagal ->
    ok=False (tidak melempar).
    """
    fetched_at = now_iso()
    if date_str is None:
        date_str = datetime.now(EASTERN).date().isoformat()
    if _valid_date_str(date_str) is None:
        return FetchResult(
            SOURCE, TIER, fetched_at, False, error=f"tanggal_tidak_valid: {date_str!r}"
        )
    day = datetime.strptime(date_str, "%Y-%m-%d")
    url = f"{SCOREBOARD_URL}?dates={day.strftime('%Y%m%d')}"
    data, error = _fetch_json(url, client)
    if error is not None:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=error)
    assert data is not None
    try:
        games = parse_live_scoreboard(data, date_str=date_str, fetched_at=fetched_at)
    except ValueError as exc:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=str(exc))
    return FetchResult(
        SOURCE,
        TIER,
        fetched_at,
        True,
        data=games,
        extra={"date": date_str, "n_games": len(games)},
    )


def _split_made_attempted(display_value: object) -> tuple[int | None, int | None]:
    """Pecah displayValue "made-attempted" (misal "16-44") jadi (16, 44).

    (None, None) bila formatnya tidak dikenal.
    """
    if not isinstance(display_value, str):
        return None, None
    parts = display_value.strip().split("-")
    if len(parts) != 2:
        return None, None
    return _to_int(parts[0]), _to_int(parts[1])


def parse_game_summary(data: dict) -> dict:
    """Ubah respons JSON summary ESPN jadi statistik tim per laga.

    Mengembalikan dict {tricode: {fg3_made, fg3_attempted, ft_made,
    ft_attempted}} dari boxscore team stats (singkatan ESPN dipetakan
    ke tricode repo, sama seperti scoreboard). Nilai None bila statistik
    itu tidak ada / tidak bisa diurai. Tim tanpa singkatan dilewati.
    ValueError("espn_format_changed") bila boxscore/teams tidak ada
    atau bukan list.
    """
    if not isinstance(data, dict):
        raise ValueError("espn_format_changed")
    boxscore = data.get("boxscore")
    if not isinstance(boxscore, dict):
        raise ValueError("espn_format_changed")
    teams = boxscore.get("teams")
    if not isinstance(teams, list):
        raise ValueError("espn_format_changed")
    stats: dict[str, dict[str, int | None]] = {}
    for team_entry in teams:
        if not isinstance(team_entry, dict):
            continue
        team = team_entry.get("team") or {}
        abbr = team.get("abbreviation") if isinstance(team, dict) else None
        if not isinstance(abbr, str) or not abbr:
            continue
        abbr = _tricode(abbr)
        by_name: dict[str, object] = {}
        for stat in team_entry.get("statistics") or []:
            if isinstance(stat, dict) and isinstance(stat.get("name"), str):
                by_name[stat["name"]] = stat.get("displayValue")
        fg3_made, fg3_attempted = _split_made_attempted(by_name.get(_STAT_3PT))
        ft_made, ft_attempted = _split_made_attempted(by_name.get(_STAT_FT))
        stats[abbr] = {
            "fg3_made": fg3_made,
            "fg3_attempted": fg3_attempted,
            "ft_made": ft_made,
            "ft_attempted": ft_attempted,
        }
    return stats


def fetch_game_stats(
    espn_game_id: str | int, client: HttpClient | None = None
) -> FetchResult:
    """Ambil statistik tim satu laga dari summary ESPN.

    espn_game_id: id event ESPN (misal "401910023"). data: dict
    {abbr: {fg3_made, fg3_attempted, ft_made, ft_attempted}} (lihat
    parse_game_summary). Fetch gagal -> ok=False (tidak melempar).
    """
    fetched_at = now_iso()
    game_id = str(espn_game_id).strip()
    if not game_id:
        return FetchResult(SOURCE, TIER, fetched_at, False, error="espn_game_id_kosong")
    url = f"{SUMMARY_URL}?event={urllib.parse.quote(game_id)}"
    data, error = _fetch_json(url, client)
    if error is not None:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=error)
    assert data is not None
    try:
        stats = parse_game_summary(data)
    except ValueError as exc:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=str(exc))
    return FetchResult(
        SOURCE,
        TIER,
        fetched_at,
        True,
        data=stats,
        extra={"espn_game_id": game_id, "n_teams": len(stats)},
    )
