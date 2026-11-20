"""Penarik Basketball-Reference: statistik tim NBA (jenjang 2).

TEMUAN SUMBER (terverifikasi dari cache probe 2a + panggilan live
2026-11-20): halaman "advanced" liga (leagues/NBA_YYYY_advanced.html)
hanya memuat statistik PEMAIN (PER, TS%, BPM) — tidak ada ORtg/DRtg/Pace
tim di sana. Statistik tim (ORtg/DRtg/NetRtg/Pace/dll) ada di tabel
"advanced-team" pada halaman utama liga (leagues/NBA_YYYY.html), yang
dipakai fetcher ini. Halaman leagues/NBA_YYYY_misc.html TIDAK ADA (404).

Konvensi tahun BBRef: season = tahun musim berakhir (2027 = musim
2026-27; 2026 = musim 2025-26). Default season=2026 mengikuti probe 2a;
untuk musim berjalan, panggil dengan season=2027.

Tabel diparsing dengan html.parser (stdlib) lewat atribut data-stat per
sel. Baris "League Average" (di <tfoot>) dilewati — hanya 30 tim yang
dikembalikan. Tes kesehatan: tabel id="advanced-team" dan kolom wajib
(off_rtg, def_rtg, pace) harus ada, bila tidak ok=False dengan error
"bbref_format_changed".
"""

from __future__ import annotations

from html.parser import HTMLParser

from ingest.common import (
    DiskCache,
    FetchResult,
    HttpClient,
    RateLimiter,
    default_cache_dir,
    now_iso,
)

SOURCE = "Basketball-Reference"
TIER = 2
CACHE_TTL_SECONDS = 21600  # 6 jam (cache agresif, sesuai risiko probe)
RATE_GAP_SECONDS = 4.0  # jeda probe 2a; BBRef membatasi request agresif

LEAGUE_URL = "https://www.basketball-reference.com/leagues/NBA_{season}.html"
TABLE_ID = "advanced-team"

# Kolom wajib (tes kesehatan): bila salah satunya hilang, format berubah.
REQUIRED_STATS = ("off_rtg", "def_rtg", "pace")

# Kolom yang dikembalikan per tim (data-stat -> nama field). DUMMY,
# arena_name, attendance, dan attendance_per_g tidak dipakai analisis
# sehingga tidak dikembalikan.
_TEAM_FIELDS = {
    "team": "team",
    "age": "age",
    "wins": "wins",
    "losses": "losses",
    "wins_pyth": "wins_pyth",
    "losses_pyth": "losses_pyth",
    "mov": "mov",
    "sos": "sos",
    "srs": "srs",
    "off_rtg": "off_rtg",
    "def_rtg": "def_rtg",
    "net_rtg": "net_rtg",
    "pace": "pace",
    "fta_per_fga_pct": "fta_per_fga_pct",
    "fg3a_per_fga_pct": "fg3a_per_fga_pct",
    "ts_pct": "ts_pct",
    "efg_pct": "efg_pct",
    "tov_pct": "tov_pct",
    "orb_pct": "orb_pct",
    "ft_rate": "ft_rate",
    "opp_efg_pct": "opp_efg_pct",
    "opp_tov_pct": "opp_tov_pct",
    "drb_pct": "drb_pct",
    "opp_ft_rate": "opp_ft_rate",
}


# Satu limiter untuk SEMUA request modul ini (dibagi semua pemanggilan):
# membuat RateLimiter baru per panggilan berarti tidak ada jeda antar
# panggilan — slate memanggil fetcher berkali-kali (Kalshi: 3 series;
# Polymarket: 1x per pasar) dan API membalas 429 (teramati: Kalshi total
# EPL 429 saat demo 2b). RateLimiter.wait() melacak per host, jadi satu
# limiter aman untuk beberapa host modul ini.
_LIMITER = RateLimiter(RATE_GAP_SECONDS)


def _default_client() -> HttpClient:
    """Buat HttpClient default (jeda 4 dtk, cache 6 jam)."""
    return HttpClient(
        _LIMITER,
        cache=DiskCache(default_cache_dir(), CACHE_TTL_SECONDS),
    )


def _to_number(text: str) -> int | float | None:
    """Ubah teks sel jadi angka (toleran koma ribuan dan tanda '+').

    Mengembalikan None bila teks kosong/bukan angka.
    """
    cleaned = text.replace(",", "").strip().lstrip("+")
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        pass
    try:
        return float(cleaned)
    except ValueError:
        return None


class _AdvancedTableParser(HTMLParser):
    """Parser tabel advanced-team BBRef (hanya <tbody>, per data-stat)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.in_tbody = False
        self.in_row = False
        self.in_cell = False
        self.table_found = False
        self.current_stat: str | None = None
        self.current_text: list[str] = []
        self.current_row: dict[str, str] = {}
        self.rows: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "table" and attrs_dict.get("id") == TABLE_ID:
            self.in_table = True
            self.table_found = True
        if not self.in_table:
            return
        if tag == "tbody":
            self.in_tbody = True
        elif tag == "tr" and self.in_tbody:
            self.in_row = True
            self.current_row = {}
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.current_stat = attrs_dict.get("data-stat")
            self.current_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self.in_table:
            self.in_table = False
            self.in_tbody = False
        if not self.in_table and tag != "table":
            return
        if tag == "tbody":
            self.in_tbody = False
        elif tag == "tr" and self.in_row:
            self.in_row = False
            if self.current_row:
                self.rows.append(self.current_row)
            self.current_row = {}
        elif tag in ("td", "th") and self.in_cell:
            self.in_cell = False
            if self.current_stat:
                self.current_row[self.current_stat] = "".join(self.current_text)
            self.current_stat = None
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_text.append(data)


def parse_advanced_table(html: str) -> list[dict]:
    """Ubah HTML halaman liga BBRef jadi list statistik tim.

    Setiap tim: team (nama lengkap, "*" playoff dibuang), age, wins,
    losses, wins_pyth, losses_pyth, mov, sos, srs, off_rtg, def_rtg,
    net_rtg, pace, fta_per_fga_pct, fg3a_per_fga_pct, ts_pct, efg_pct,
    tov_pct, orb_pct, ft_rate, opp_efg_pct, opp_tov_pct, drb_pct,
    opp_ft_rate. Angka diparsing jadi int/float, kosong jadi None.
    ValueError("bbref_format_changed") bila tabel id="advanced-team"
    tidak ada atau kolom wajib (off_rtg/def_rtg/pace) hilang.
    """
    parser = _AdvancedTableParser()
    parser.feed(html)
    parser.close()
    if not parser.table_found:
        raise ValueError("bbref_format_changed")
    seen_stats = {stat for row in parser.rows for stat in row}
    if any(stat not in seen_stats for stat in REQUIRED_STATS):
        raise ValueError("bbref_format_changed")
    teams = []
    for row in parser.rows:
        team_name = row.get("team", "").strip().rstrip("*").strip()
        if not team_name or team_name == "League Average":
            continue
        team: dict = {"team": team_name}
        for data_stat, field in _TEAM_FIELDS.items():
            if field == "team":
                continue
            team[field] = _to_number(row.get(data_stat, ""))
        teams.append(team)
    return teams


def fetch_team_advanced(
    season: int = 2026, client: HttpClient | None = None
) -> FetchResult:
    """Ambil statistik tim NBA (ORtg/DRtg/Pace/dll) satu musim BBRef.

    season: tahun musim berakhir di konvensi BBRef (2027 = musim
    2026-27; default 2026 = musim 2025-26, mengikuti probe 2a).
    data: list statistik tim (lihat parse_advanced_table). Fetch/format
    gagal -> ok=False dengan error (tidak melempar).
    """
    fetched_at = now_iso()
    url = LEAGUE_URL.format(season=season)
    resp = (client or _default_client()).get(url)
    if resp.get("status") != 200:
        return FetchResult(
            SOURCE,
            TIER,
            fetched_at,
            False,
            error=f"http_{resp.get('status')}: {resp.get('error') or 'bbref gagal'}",
        )
    body = resp.get("body")
    if not isinstance(body, str):
        return FetchResult(
            SOURCE, TIER, fetched_at, False, error="bbref_format_changed"
        )
    try:
        teams = parse_advanced_table(body)
    except ValueError as exc:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=str(exc))
    return FetchResult(
        SOURCE,
        TIER,
        fetched_at,
        True,
        data=teams,
        extra={"season": season, "n_teams": len(teams)},
    )
