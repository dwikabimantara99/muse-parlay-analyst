"""Penarik game log pemain NBA dari Basketball-Reference (jenjang 2).

Dipakai patch langkah 1b perbaikan 2 (temuan auditor 2): menghitung
`missed_last10` — jumlah dari 10 laga terakhir TIM yang tidak dimainkan
seorang pemain — untuk koreksi tumpang-tindih dampak pemain absen di
engine.nba_sim (rating tim sudah mengandung 40% last10, jadi pemain
yang sudah absen di last10 terhitung ganda bila dampaknya dikurangi
penuh).

SUMBER: https://www.basketball-reference.com/players/<slug>/gamelog/<musim>/
(slug = "huruf/slug", misal "d/durenja01", dari field bbref_slug
ingest.bbref.fetch_player_advanced; musim = tahun berakhir, 2027 =
musim 2026-27). Satu halaman per pemain per musim.

STRUKTUR HALAMAN (terverifikasi live 2026-11-22, contoh Duren):
- Tabel id="player_game_log_reg" — BUKAN "pgl_basic" (id lama yang
  tidak ditemukan; itulah penyebab percobaan main agent gagal). Tabel
  ADA di HTML mentah (bukan di dalam komentar) pada 2026-11-22; parser
  tetap mencoba membuka komentar sebagai fallback, mengikuti konvensi
  ingest.bbref, karena BBRef kadang membungkus tabel di komentar.
- Satu baris per laga TIM (termasuk laga yang tidak dimainkan pemain),
  urut kronologis menaik, dengan kolom data-stat: date, team_game_num_
  season (nomor laga tim musim ini), team_name_abbr, opp_name_abbr,
  game_result, is_starter, mp (dst. statistik bila bermain).
- Baris TIDAK BERMAIN: sel is_starter colspan=25 berisi "Inactive" /
  "Did Not Play" (dst.) dan TIDAK ADA sel mp. Aturan main: played =
  sel mp ada dan tidak kosong. Teks is_starter disimpan sebagai
  `status` (alasan tidak bermain, misal "Inactive").
- BBRef menyisipkan baris HEADER di tengah <tbody> (date="Date",
  team_game_num_season="Gtm", mp="MP") — baris tanpa tanggal valid /
  nomor laga numerik dilewati.

JENDELA: 10 laga terakhir tim (bukan 10 laga terakhir pemain). Bila
tim baru memainkan < 10 laga, yang dipakai hanya laga yang ada
(games_considered < 10 dicatat di hasil; penyebut rumus overlap di
nba_sim tetap 10 — lihat keterbatasan di bawah).

KETERBATASAN (didokumentasikan, bukan disembunyikan):
- Awal musim (tim < 10 laga): missed_last10 dihitung dari laga yang
  ada; faktor overlap (1 - 0,4 x missed/10) sedikit KURANG mengoreksi
  karena penyebutnya tetap 10. Dampaknya kecil dan hanya di awal musim.
- Pemain pindah tim di tengah musim: baris difilter ke tim SAAT INI
  (argumen team); laga bersama tim lama tidak dihitung.
- Tricode BBRef (BRK/CHO/PHO) dipetakan ke konvensi stats.nba.com
  (BKN/CHA/PHX) lewat BBREF_TRICODE_MAP di kedua arah.
- stats.nba.com playergamelog TIDAK dipakai: endpoint itu butuh
  PlayerID NBA yang tidak tersedia dari BBRef, dan BBRef sudah
  terbukti bisa diparse — rantai fallback tidak diperlukan.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from ingest import bbref as bbref_mod
from ingest.common import FetchResult, HttpClient, now_iso

SOURCE = "Basketball-Reference"
TIER = 2

GAMELOG_URL = "https://www.basketball-reference.com/players/{slug}/gamelog/{season}/"
TABLE_ID = "player_game_log_reg"

# Jendela default: 10 laga terakhir tim (sesuai bobot last10 di nba_sim).
WINDOW_DEFAULT = 10

# Kolom wajib tabel game log (tes kesehatan): bila salah satunya
# hilang, format berubah.
REQUIRED_STATS = ("date", "team_game_num_season", "mp", "is_starter")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class _GamelogTableParser(HTMLParser):
    """Parser tabel game log pemain BBRef (hanya <tbody>, per data-stat)."""

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


def _parse_gamelog_once(html: str) -> list[dict]:
    """Satu kali parse tabel game log; ValueError bila tabel/kolom hilang."""
    parser = _GamelogTableParser()
    parser.feed(html)
    parser.close()
    if not parser.table_found:
        raise ValueError("bbref_format_changed")
    seen_stats = {stat for row in parser.rows for stat in row}
    if any(stat not in seen_stats for stat in REQUIRED_STATS):
        raise ValueError("bbref_format_changed")
    games = []
    for row in parser.rows:
        tanggal = (row.get("date") or "").strip()
        nomor = (row.get("team_game_num_season") or "").strip()
        # Baris header di tengah <tbody> (date="Date", nomor="Gtm")
        # bukan laga — dilewati.
        if not _DATE_RE.match(tanggal) or not nomor.isdigit():
            continue
        mp = (row.get("mp") or "").strip()
        is_starter = (row.get("is_starter") or "").strip()
        played = bool(mp)
        games.append(
            {
                "date": tanggal,
                "team_game_num": int(nomor),
                "team": (row.get("team_name_abbr") or "").strip(),
                "opponent": (row.get("opp_name_abbr") or "").strip(),
                "result": (row.get("game_result") or "").strip(),
                "played": played,
                "mp": mp or None,
                # Alasan tidak bermain ("Inactive", "Did Not Play", ...)
                # bila tidak bermain; None bila bermain.
                "status": is_starter if not played else None,
            }
        )
    return games


def parse_player_gamelog(html: str) -> list[dict]:
    """Ubah HTML halaman game log BBRef jadi list laga (urut kronologis).

    Setiap laga: date (YYYY-MM-DD), team_game_num (nomor laga tim
    musim ini), team (tricode BBRef — BRK/CHO/PHO apa adanya),
    opponent, result, played (bool — True bila sel mp ada dan tidak
    kosong), mp ("MM:SS" atau None), status (teks is_starter bila
    tidak bermain, misal "Inactive"; None bila bermain). Baris header
    di tengah <tbody> dilewati. ValueError ("bbref_format_changed")
    bila tabel id="player_game_log_reg" tidak ada atau kolom wajib
    hilang — termasuk setelah mencoba membuka komentar HTML.
    """
    try:
        return _parse_gamelog_once(html)
    except ValueError:
        if "<!--" not in html:
            raise
        # Coba lagi dengan komentar dibuka (tabel di dalam komentar).
        return _parse_gamelog_once(html.replace("<!--", "").replace("-->", ""))


def _tricode_nba(tricode: str) -> str:
    """Normalisasi tricode ke konvensi stats.nba.com (BRK->BKN, ...)."""
    return bbref_mod.BBREF_TRICODE_MAP.get(tricode, tricode)


def count_missed_last10(
    games: list[dict], team: str | None = None, window: int = WINDOW_DEFAULT
) -> dict:
    """Hitung missed_last10 dari list laga hasil parse_player_gamelog.

    games: list laga urut kronologis (boleh dari parse atau sintetis).
    team: bila diisi, hanya laga tim itu yang dihitung (tricode
    dinormalisasi ke konvensi stats.nba.com di kedua sisi, jadi
    team="BKN" cocok dengan baris BBRef "BRK"). window: jumlah laga
    terakhir tim yang dipakai (default 10).
    Mengembalikan {"missed_last10", "played_last10",
    "games_considered", "window", "team"} — games_considered < window
    bila tim baru memainkan laga lebih sedikit dari window.
    """
    if window < 1:
        raise ValueError(f"window harus >= 1, didapat {window!r}")
    if team is not None:
        team_nba = _tricode_nba(team)
        games = [g for g in games if _tricode_nba(g.get("team") or "") == team_nba]
    jendela = games[-window:]
    missed = sum(1 for g in jendela if not g.get("played"))
    return {
        "missed_last10": missed,
        "played_last10": len(jendela) - missed,
        "games_considered": len(jendela),
        "window": window,
        "team": team,
    }


def fetch_player_gamelog(
    slug: str, season: int = 2027, client: HttpClient | None = None
) -> FetchResult:
    """Ambil game log satu pemain BBRef (satu musim).

    slug: jalur gamelog "huruf/slug" (field bbref_slug dari
    ingest.bbref.fetch_player_advanced). season: tahun musim berakhir
    di konvensi BBRef (2027 = musim 2026-27, default = musim
    berjalan). data: list laga (lihat parse_player_gamelog).
    Fetch/format gagal -> ok=False dengan error (tidak melempar).
    """
    fetched_at = now_iso()
    if not slug or "/" not in slug:
        return FetchResult(
            SOURCE, TIER, fetched_at, False, error="bbref_slug_tidak_valid"
        )
    url = GAMELOG_URL.format(slug=slug, season=season)
    resp = (client or bbref_mod.shared_client()).get(url)
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
        games = parse_player_gamelog(body)
    except ValueError as exc:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=str(exc))
    return FetchResult(
        SOURCE,
        TIER,
        fetched_at,
        True,
        data=games,
        extra={"slug": slug, "season": season, "n_games": len(games)},
    )


def fetch_missed_last10(
    slug: str,
    team: str | None = None,
    season: int = 2027,
    client: HttpClient | None = None,
) -> FetchResult:
    """Ambil game log satu pemain dan hitung missed_last10-nya.

    data: {"missed_last10", "played_last10", "games_considered",
    "window", "team", "slug"} (lihat count_missed_last10).
    Fetch/format gagal -> ok=False dengan error (tidak melempar) —
    pemanggil memakai fallback faktor overlap 1,0 + catatan.
    """
    result = fetch_player_gamelog(slug, season=season, client=client)
    if not result.ok:
        return result
    hitungan = count_missed_last10(result.data or [], team=team)
    hitungan["slug"] = slug
    return FetchResult(
        SOURCE,
        TIER,
        result.fetched_at,
        True,
        data=hitungan,
        extra={"slug": slug, "season": season, "team": team},
    )


def fetch_missed_last10_many(
    players: list[dict], season: int = 2027, client: HttpClient | None = None
) -> dict[str, dict]:
    """Hitung missed_last10 untuk daftar pemain (satu request per pemain).

    players: list dict {"player", "bbref_slug", "team_tricode"} —
    biasanya pemain OUT yang punya data BPM (hanya mereka yang
    memengaruhi proyeksi lewat jalur absen). Mengembalikan dict
    nama pemain -> {"missed_last10": int | None, "games_considered":
    int, "error": str | None, "slug": str | None}. Pemain tanpa slug
    atau yang fetch-nya gagal -> missed_last10 None + error (pemanggil
    memakai fallback faktor overlap 1,0 + catatan, JANGAN mengarang
    partisipasi). Memakai client bersama BBRef (limiter 4 dtk) bila
    client tidak diberikan.
    """
    hasil: dict[str, dict] = {}
    client_efektif = client or bbref_mod.shared_client()
    for pemain in players:
        nama = pemain.get("player") or "pemain_tidak_dikenal"
        slug = pemain.get("bbref_slug")
        if not slug:
            hasil[nama] = {
                "missed_last10": None,
                "games_considered": 0,
                "error": "bbref_slug_tidak_ada",
                "slug": None,
            }
            continue
        result = fetch_missed_last10(
            slug,
            team=pemain.get("team_tricode"),
            season=season,
            client=client_efektif,
        )
        if not result.ok:
            hasil[nama] = {
                "missed_last10": None,
                "games_considered": 0,
                "error": result.error or "gagal",
                "slug": slug,
            }
            continue
        data = result.data or {}
        hasil[nama] = {
            "missed_last10": data.get("missed_last10"),
            "games_considered": data.get("games_considered", 0),
            "error": None,
            "slug": slug,
        }
    return hasil
