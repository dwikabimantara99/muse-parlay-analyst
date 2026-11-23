"""Penarik usage rate (USG%) per pemain NBA (timing gate + rem alami v18).

Dipakai engine/vonis.py: (1) timing gate TUNGGU_LINEUP — bintang
Questionable dengan USG >= 24% atau BPM >= +2,0 menahan laga;
(2) rem alami (2) — pencetak utama (USG >= 25%) OUT di kedua tim.
Satu tarikan mencakup SELURUH liga (bukan satu tim).

SUMBER (gratis, 0 kredit Odds API; terverifikasi live 2026-11-23):
1. stats.nba.com (jenjang 1, UTAMA):
   leaguedashplayerstats, MeasureType=Usage, PerMode=PerGame — JSON,
   474 baris pemain musim 2026-27 (tarikan 23 Nov 2026). Kolom:
   PLAYER_NAME, TEAM_ABBREVIATION, GP, USG_PCT (pecahan 0-1; misal
   0,237 = 23,7%). CATATAN: kolom MIN di measure ini adalah TOTAL
   menit (bukan per laga) — tidak dipakai di sini.
2. Basketball-Reference (jenjang 2, FALLBACK):
   leagues/NBA_YYYY_advanced.html, tabel id="advanced". Kolom
   data-stat: name_display, team_name_abbr, games, mp, usg_pct
   (PERSEN, misal 28,5 — dinormalisasi ke pecahan 0,285 di parser).
   Parser sendiri di modul ini (pola yang sama dengan
   ingest/pemain_3p.py) karena ingest/bbref.parse_player_advanced
   tidak mengembalikan usg_pct.

Kedua sumber mengembalikan SKEMA YANG SAMA (lihat
_pemain_dari_stats_nba / _parse_bbref_sekali): player, team
(tricode stats.nba.com), games_played, usg_pct (pecahan 0-1; None
bila tidak ada), source. Nilai yang tidak ada di sumber dicatat
None (JANGAN diisi tebakan) — engine/vonis.py yang memutuskan
pemain seperti apa yang dilewati + dicatat.

Cache + rate limit mengikuti modul ingest lain: stats.nba.com TTL
10 menit + jeda 1 dtk (sama seperti ingest/stats_nba.py); BBRef
TTL 6 jam + jeda 4 dtk lewat client bersama ingest.bbref (limiter
yang SAMA — request semua modul BBRef tetap terjeda satu sama lain).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from ingest import bbref as bbref_mod
from ingest import stats_nba as stats_nba_mod
from ingest.common import (
    DiskCache,
    FetchResult,
    HttpClient,
    RateLimiter,
    default_cache_dir,
    now_iso,
    parse_json_body,
)

SOURCE_STATS_NBA = "stats.nba.com"
SOURCE_BBREF = "Basketball-Reference"
TIER_STATS_NBA = 1
TIER_BBREF = 2

# stats.nba.com: TTL + jeda sama seperti ingest/stats_nba.py.
STATS_NBA_CACHE_TTL_SECONDS = 600
STATS_NBA_RATE_GAP_SECONDS = 1.0

STATS_NBA_URL = (
    "https://stats.nba.com/stats/leaguedashplayerstats"
    "?LeagueID=00&Season={season}&SeasonType=Regular+Season"
    "&MeasureType=Usage&PerMode=PerGame&PlusMinus=N&PaceAdjust=N&Rank=N"
    "&Outcome=&Location=&Month=0&SeasonSegment=&DateFrom=&DateTo="
    "&OpponentTeamID=0&VsConference=&VsDivision=&TeamID=0&Conference="
    "&Division=&GameSegment=&Period=0&ShotClockRange=&LastNGames=0"
)

BBREF_ADVANCED_URL = (
    "https://www.basketball-reference.com/leagues/NBA_{season}_advanced.html"
)
BBREF_TABLE_ID = "advanced"

# Kolom wajib resultSet stats.nba.com (tes kesehatan): bila salah
# satunya hilang, format berubah.
STATS_NBA_REQUIRED_HEADERS = (
    "PLAYER_NAME",
    "TEAM_ABBREVIATION",
    "GP",
    "USG_PCT",
)

# Kolom wajib tabel advanced BBRef (tes kesehatan): bila salah
# satunya hilang, format berubah.
BBREF_REQUIRED_STATS = (
    "name_display",
    "team_name_abbr",
    "games",
    "usg_pct",
)

_LIMITER_STATS_NBA = RateLimiter(STATS_NBA_RATE_GAP_SECONDS)


def _client_stats_nba() -> HttpClient:
    """HttpClient stats.nba.com (header NBA + cache 10 menit)."""
    return HttpClient(
        _LIMITER_STATS_NBA,
        cache=DiskCache(default_cache_dir(), STATS_NBA_CACHE_TTL_SECONDS),
        extra_headers=stats_nba_mod.STATS_HEADERS,
    )


def _angka(nilai: object) -> float | None:
    """Ubah nilai jadi float; None bila bukan angka hingga (bool bukan angka)."""
    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        return None
    try:
        hasil = float(nilai)
    except (TypeError, ValueError, OverflowError):
        return None
    if hasil != hasil or hasil in (float("inf"), float("-inf")):
        return None
    return hasil


def _musim_bbref(season: str) -> int:
    """Ubah musim format NBA ("2026-27") jadi tahun BBRef (2027)."""
    cocok = re.fullmatch(r"(\d{4})-(\d{2})", season.strip())
    if not cocok:
        raise ValueError(f"format musim tidak valid: {season!r} (contoh: '2026-27')")
    return int(cocok.group(1)) + 1


def _pemain_dari_stats_nba(baris: dict) -> dict:
    """Normalisasi satu baris leaguedashplayerstats (Usage) ke skema USG."""
    games = _angka(baris.get("GP"))
    return {
        "player": (baris.get("PLAYER_NAME") or "").strip() or None,
        "team": (baris.get("TEAM_ABBREVIATION") or "").strip() or None,
        "games_played": int(games) if games is not None else None,
        "usg_pct": _angka(baris.get("USG_PCT")),
        "source": SOURCE_STATS_NBA,
    }


def parse_stats_nba_usg(data: dict) -> list[dict]:
    """Ubah respons JSON leaguedashplayerstats (Usage) jadi list pemain USG.

    Setiap pemain: player, team (tricode), games_played, usg_pct
    (pecahan 0-1), source ("stats.nba.com"). Baris tanpa nama pemain
    atau tanpa tim dilewati (bukan pemain). ValueError bila resultSet
    hilang, kolom wajib hilang, atau tidak ada baris pemain sama
    sekali.
    """
    if not isinstance(data, dict):
        raise ValueError("respons stats.nba.com bukan dict")
    result_sets = data.get("resultSets")
    if not isinstance(result_sets, list) or not result_sets:
        raise ValueError("stats_nba_format_changed")
    result_set = result_sets[0]
    headers = result_set.get("headers") or []
    rows = result_set.get("rowSet") or []
    if any(h not in headers for h in STATS_NBA_REQUIRED_HEADERS):
        raise ValueError("stats_nba_format_changed")
    pemain = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(headers):
            continue
        entri = _pemain_dari_stats_nba(dict(zip(headers, row, strict=True)))
        if not entri["player"] or not entri["team"]:
            continue
        pemain.append(entri)
    if not pemain:
        raise ValueError("stats_nba_format_changed")
    return pemain


class _AdvancedTableParser(HTMLParser):
    """Parser tabel advanced BBRef (hanya <tbody>, per data-stat).

    Cerminan _PerGameTableParser ingest/pemain_3p.py untuk tabel
    id="advanced" di halaman leagues/NBA_YYYY_advanced.html (hanya
    kolom USG yang dipakai di sini).
    """

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
        if tag == "table" and attrs_dict.get("id") == BBREF_TABLE_ID:
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


def _parse_bbref_sekali(html: str) -> list[dict]:
    """Satu kali parse tabel advanced BBRef; ValueError bila gagal.

    usg_pct BBRef dalam PERSEN (28,5) — dibagi 100 ke pecahan
    (0,285) supaya skemanya sama dengan stats.nba.com.
    """
    parser = _AdvancedTableParser()
    parser.feed(html)
    parser.close()
    if not parser.table_found:
        raise ValueError("bbref_format_changed")
    seen_stats = {stat for row in parser.rows for stat in row}
    if any(stat not in seen_stats for stat in BBREF_REQUIRED_STATS):
        raise ValueError("bbref_format_changed")
    pemain = []
    for row in parser.rows:
        nama = (row.get("name_display") or "").strip()
        team_raw = (row.get("team_name_abbr") or "").strip()
        if not nama or nama == "League Average" or not team_raw:
            continue
        if team_raw == "TOT":
            continue
        usg_persen = bbref_mod._to_number(row.get("usg_pct", ""))
        usg = None
        if isinstance(usg_persen, (int, float)):
            usg = float(usg_persen) / 100.0
        pemain.append(
            {
                "player": nama,
                "team": bbref_mod.BBREF_TRICODE_MAP.get(team_raw, team_raw),
                "games_played": bbref_mod._to_number(row.get("games", "")),
                "usg_pct": usg,
                "source": SOURCE_BBREF,
            }
        )
    if not pemain:
        raise ValueError("bbref_format_changed")
    return pemain


def parse_bbref_usg(html: str) -> list[dict]:
    """Ubah HTML halaman advanced BBRef jadi list pemain USG (skema sama).

    Skema keluaran sama persis dengan parse_stats_nba_usg, kecuali
    source="Basketball-Reference". ValueError ("bbref_format_changed")
    bila tabel id="advanced" tidak ada atau kolom wajib hilang —
    termasuk setelah mencoba membuka komentar HTML (BBRef kadang
    membungkus tabel di komentar).
    """
    try:
        return _parse_bbref_sekali(html)
    except ValueError:
        if "<!--" not in html:
            raise
        return _parse_bbref_sekali(html.replace("<!--", "").replace("-->", ""))


def fetch_pemain_usg_stats_nba(
    season: str = "2026-27", client: HttpClient | None = None
) -> FetchResult:
    """Ambil USG% pemain dari stats.nba.com (jenjang 1).

    season: musim format NBA ("2026-27"). data: list pemain (lihat
    parse_stats_nba_usg). Fetch/format gagal -> ok=False dengan
    error (tidak melempar).
    """
    fetched_at = now_iso()
    url = STATS_NBA_URL.format(season=season)
    resp = (client or _client_stats_nba()).get(url)
    if resp.get("status") != 200:
        return FetchResult(
            SOURCE_STATS_NBA,
            TIER_STATS_NBA,
            fetched_at,
            False,
            error=(
                f"http_{resp.get('status')}: "
                f"{resp.get('error') or 'stats.nba.com gagal'}"
            ),
        )
    data = parse_json_body(resp)
    if data is None or not isinstance(data, dict):
        return FetchResult(
            SOURCE_STATS_NBA,
            TIER_STATS_NBA,
            fetched_at,
            False,
            error="stats_nba_format_changed",
        )
    try:
        pemain = parse_stats_nba_usg(data)
    except ValueError as exc:
        return FetchResult(
            SOURCE_STATS_NBA, TIER_STATS_NBA, fetched_at, False, error=str(exc)
        )
    return FetchResult(
        SOURCE_STATS_NBA,
        TIER_STATS_NBA,
        fetched_at,
        True,
        data=pemain,
        extra={"season": season, "n_players": len(pemain)},
    )


def fetch_pemain_usg_bbref(
    season: str = "2026-27", client: HttpClient | None = None
) -> FetchResult:
    """Ambil USG% pemain dari BBRef (jenjang 2, fallback).

    season: musim format NBA ("2026-27", diubah ke tahun BBRef).
    data: list pemain (lihat parse_bbref_usg). Fetch/format
    gagal -> ok=False dengan error (tidak melempar).
    """
    fetched_at = now_iso()
    try:
        tahun = _musim_bbref(season)
    except ValueError as exc:
        return FetchResult(SOURCE_BBREF, TIER_BBREF, fetched_at, False, error=str(exc))
    url = BBREF_ADVANCED_URL.format(season=tahun)
    resp = (client or bbref_mod.shared_client()).get(url)
    if resp.get("status") != 200:
        return FetchResult(
            SOURCE_BBREF,
            TIER_BBREF,
            fetched_at,
            False,
            error=f"http_{resp.get('status')}: {resp.get('error') or 'bbref gagal'}",
        )
    body = resp.get("body")
    if not isinstance(body, str):
        return FetchResult(
            SOURCE_BBREF, TIER_BBREF, fetched_at, False, error="bbref_format_changed"
        )
    try:
        pemain = parse_bbref_usg(body)
    except ValueError as exc:
        return FetchResult(SOURCE_BBREF, TIER_BBREF, fetched_at, False, error=str(exc))
    return FetchResult(
        SOURCE_BBREF,
        TIER_BBREF,
        fetched_at,
        True,
        data=pemain,
        extra={"season": season, "n_players": len(pemain)},
    )


def fetch_pemain_usg(
    season: str = "2026-27",
    client_stats_nba: HttpClient | None = None,
    client_bbref: HttpClient | None = None,
) -> FetchResult:
    """Ambil USG% pemain seluruh liga (stats.nba.com, fallback BBRef).

    Satu tarikan mencakup semua pemain semua tim. Bila stats.nba.com
    gagal (timeout/HTTP/format), dicoba BBRef; sumber yang dipakai
    tercatat di extra["source_used"] + FetchResult.source. Kedua
    sumber gagal -> ok=False dengan kedua error (tidak melempar).
    """
    hasil = fetch_pemain_usg_stats_nba(season=season, client=client_stats_nba)
    if hasil.ok:
        hasil.extra["source_used"] = SOURCE_STATS_NBA
        hasil.extra["fallback"] = False
        return hasil
    error_utama = hasil.error or "gagal"
    hasil_bbref = fetch_pemain_usg_bbref(season=season, client=client_bbref)
    if hasil_bbref.ok:
        hasil_bbref.extra["source_used"] = SOURCE_BBREF
        hasil_bbref.extra["fallback"] = True
        hasil_bbref.extra["error_stats_nba"] = error_utama
        return hasil_bbref
    return FetchResult(
        SOURCE_STATS_NBA,
        TIER_STATS_NBA,
        hasil.fetched_at,
        False,
        error=(
            f"stats.nba.com gagal ({error_utama}); "
            f"BBRef gagal ({hasil_bbref.error or 'gagal'})"
        ),
        extra={"source_used": None, "fallback": True},
    )


def peta_usg(pemain: list[dict]) -> dict[str, float]:
    """List pemain USG -> {nama_pemain: usg_pct} (tanpa None).

    Nama dipakai apa adanya (pemanggil yang menormalisasi bila perlu
    mencocokkan antar-sumber — lihat engine/vonis._normalisasi_nama).
    Bila satu nama muncul dua kali (pindah tim), entri terakhir menang.
    """
    hasil: dict[str, float] = {}
    for entri in pemain or []:
        if not isinstance(entri, dict):
            continue
        nama = entri.get("player")
        usg = _angka(entri.get("usg_pct"))
        if isinstance(nama, str) and nama and usg is not None:
            hasil[nama] = usg
    return hasil


# Cache satu-proses hasil fetch liga. Satu tarikan mencakup SEMUA tim,
# tapi analyze/vonis memanggil per laga — tanpa cache, slate 10 laga
# berarti 10 tarikan stats.nba.com (lambat + boros). Hanya hasil OK
# yang di-cache; hasil gagal selalu dicoba ulang di panggilan berikut.
_CACHE_PEMAIN_USG: dict[str, FetchResult] = {}


def fetch_pemain_usg_cached(season: str = "2026-27") -> FetchResult:
    """Ambil data USG pemain se-liga, sekali per musim per proses.

    Dipakai engine/vonis.py (timing gate + rem alami): dalam satu
    jalan ``cli.py analyze`` (satu proses untuk seluruh slate),
    tarikan pertama di-cache dan laga berikutnya memakai cache.
    """
    hasil = _CACHE_PEMAIN_USG.get(season)
    if hasil is not None and hasil.ok:
        return hasil
    hasil = fetch_pemain_usg(season=season)
    if hasil.ok:
        _CACHE_PEMAIN_USG[season] = hasil
    return hasil


def bersihkan_cache_pemain_usg() -> None:
    """Kosongkan cache USG pemain (untuk tes)."""
    _CACHE_PEMAIN_USG.clear()
