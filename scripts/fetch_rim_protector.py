"""Tarik data blok per pemain + turunkan pemetaan rim protector per tim.

    python3 scripts/fetch_rim_protector.py [--season 2026-27]
        [--out config/rim_protector_2026-27.json]

Satu tarikan mencakup SELURUH liga, lalu per tim dipilih maksimal 2
rim protector (aturan di bawah) dan ditulis ke file JSON yang dipakai
engine/vonis.py (veto rim protector). File ini CHECK-IN ke repo di
config/ (BUKAN data/ — /data/ di-.gitignore karena isinya output
lokal; file ini input statis versi mesin, seperti playstyle.yaml)
supaya veto jalan di produksi tanpa fetch; segarkan dengan
menjalankan ulang script ini (seminggu sekali, atau setelah trade
besar / perubahan rotasi).

SUMBER (gratis, 0 kredit Odds API; pola yang sama dengan
ingest/pemain_3p.py):
1. stats.nba.com (jenjang 1, UTAMA): leaguedashplayerstats,
   MeasureType=Base, PerMode=PerGame — JSON. Kolom yang dipakai:
   PLAYER_NAME, TEAM_ABBREVIATION, GP, MIN, BLK.
2. Basketball-Reference (jenjang 2, FALLBACK bila stats.nba.com
   gagal): leagues/NBA_YYYY_per_game.html, tabel id="per_game_stats".
   Kolom data-stat: name_display, team_name_abbr, games, mp_per_g,
   blk_per_g. Tricode BBRef dipetakan ke konvensi stats.nba.com
   (BRK->BKN, CHO->CHA, PHO->PHX) lewat BBREF_TRICODE_MAP ingest.bbref.
3. POSISI (SELALU dari BBRef): stats.nba.com
   leaguedashplayerstats TIDAK punya kolom POSITION (diverifikasi
   live 2026-11-23 — header respons tidak mengandung posisi) —
   jadi posisi diambil dari kolom data-stat="pos" tabel per-game
   BBRef yang sama. Bila sumber blok adalah stats.nba.com, script
   menarik halaman per-game BBRef SEKALI lagi khusus untuk posisi
   dan menggabungkan per (nama ternormalisasi, tim); bila sumber
   blok adalah BBRef, posisi sudah ada dari parse yang sama.
   Bila tarikan posisi BBRef gagal -> script GAGAL (exit 2) dan
   file JSON lama dipertahankan: pemetaan tanpa filter posisi
   adalah cacat v17 (guard ikut masuk) — lebih baik tidak
   regenerate daripada regenerate cacat.

ATURAN DERIVASI (ambang dari section vonis.veto.rim_protector di
config/playstyle.yaml — bukan dari kode; v18: pindah dari
vonis.rim_protector ke vonis.veto.rim_protector):
- Rotasi: GP >= min_games DAN MP >= min_mp_per_game.
- Blok bermakna: BLK >= min_blk_per_game.
- Posisi big: pos BBRef harus ada di position_filter
  (["C", "PF", "F-C", "C-F"]) — v18: memperbaiki cacat v17 yang
  menamai guard di tim yang bloknya lemah (DET: Cade Cunningham
  0,9; IND: Tyrese Haliburton 0,8). Pemain yang lolos ambang
  blok/menit tapi posisinya tidak diketahui (nama tidak cocok
  antara kedua sumber) DIKELUARKAN dari pemetaan dan dicatat di
  daftar "tanpa_posisi" pada JSON output (jejak audit).
- Per tim diambil maksimal max_per_team pemain, urut BPG tertinggi;
  seri (selisih < 1e-9) -> menit lebih besar -> nama abjad
  (deterministik). Baris TOT (agregat pemain pindah tim) dilewati —
  baris per timnya ada terpisah.
- Pemain dengan GP di bawah ambang TIDAK BISA diidentifikasi dari
  data musim berjalan (perannya belum terbentuk di statistik) —
  keterbatasan yang didokumentasikan (mis. Jalen Duren DET, 2 laga):
  veto tidak menangkap mereka. Perbaikan ke depan: identifikasi peran
  dari statistik musim lalu.

KENAPA TOP-2 (bukan top-1): perlindungan ring adalah pekerjaan
rotasi (center starter + big cadangan); selisih BPG #1 vs #2 sering
di dalam noise statistik (CHI: Jalen Smith 1,1 vs Nic Claxton 1,0 —
satu blok per 10 laga). Hanya memakai #1 akan menyatakan CHI "aman"
padahal Claxton (1,0 blok/laga) OUT dan cadangan ketiganya (Caleb
Wilson 0,9) juga OUT. v18: filter posisi menutup celah v17 (guard
di tim yang bloknya lemah); bila suatu tim tidak punya big yang
lolos ambang, tim itu tidak muncul di pemetaan dan veto tidak bisa
menilai tim itu (dicatat "tidak_dinilai", BUKAN veto).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from ingest import bbref as bbref_mod
from ingest import stats_nba as stats_nba_mod
from ingest.common import (
    DiskCache,
    HttpClient,
    RateLimiter,
    default_cache_dir,
    now_iso,
    parse_json_body,
)

# Endpoint yang sama dengan ingest/pemain_3p.py (leaguedashplayerstats
# Base PerGame — satu tarikan seluruh liga; kolom BLK ikut di sana).
STATS_NBA_URL = (
    "https://stats.nba.com/stats/leaguedashplayerstats"
    "?LeagueID=00&Season={season}&SeasonType=Regular+Season"
    "&MeasureType=Base&PerMode=PerGame&PlusMinus=N&PaceAdjust=N&Rank=N"
    "&Outcome=&Location=&Month=0&SeasonSegment=&DateFrom=&DateTo="
    "&OpponentTeamID=0&VsConference=&VsDivision=&TeamID=0&Conference="
    "&Division=&GameSegment=&Period=0&ShotClockRange=&LastNGames=0"
)
BBREF_PER_GAME_URL = (
    "https://www.basketball-reference.com/leagues/NBA_{season}_per_game.html"
)
BBREF_TABLE_ID = "per_game_stats"

STATS_NBA_REQUIRED_HEADERS = (
    "PLAYER_NAME",
    "TEAM_ABBREVIATION",
    "GP",
    "MIN",
    "BLK",
)
BBREF_REQUIRED_STATS = (
    "name_display",
    "team_name_abbr",
    "games",
    "mp_per_g",
    "blk_per_g",
    "pos",
)

STATS_NBA_CACHE_TTL_SECONDS = 600
STATS_NBA_RATE_GAP_SECONDS = 1.0

SOURCE_STATS_NBA = "stats.nba.com"
SOURCE_BBREF = "Basketball-Reference"

_LIMITER_STATS_NBA = RateLimiter(STATS_NBA_RATE_GAP_SECONDS)


def _angka(nilai: object) -> float | None:
    """Ubah nilai jadi float berhingga; None bila bukan angka."""
    if isinstance(nilai, bool) or nilai is None:
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


def _client_stats_nba() -> HttpClient:
    """HttpClient stats.nba.com (header NBA + cache 10 menit)."""
    return HttpClient(
        _LIMITER_STATS_NBA,
        cache=DiskCache(default_cache_dir(), STATS_NBA_CACHE_TTL_SECONDS),
        extra_headers=stats_nba_mod.STATS_HEADERS,
    )


def parse_stats_nba_blok(data: dict) -> list[dict]:
    """Ubah respons JSON leaguedashplayerstats jadi list pemain blok.

    Setiap pemain: player, team (tricode), games_played, mp_per_game,
    blk_per_game, pos (None — stats.nba.com tidak menyediakan posisi;
    diisi dari BBRef oleh gabung_posisi), source. Baris tanpa
    nama/tim dilewati; baris TOT (agregat pemain pindah tim)
    dilewati. ValueError bila resultSet hilang, kolom wajib hilang,
    atau tidak ada baris pemain sama sekali (format berubah).
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
        baris = dict(zip(headers, row, strict=True))
        nama = (baris.get("PLAYER_NAME") or "").strip()
        tim = (baris.get("TEAM_ABBREVIATION") or "").strip()
        if not nama or not tim or tim == "TOT":
            continue
        pemain.append(
            {
                "player": nama,
                "team": tim,
                "games_played": _angka(baris.get("GP")),
                "mp_per_game": _angka(baris.get("MIN")),
                "blk_per_game": _angka(baris.get("BLK")),
                "pos": None,
                "source": SOURCE_STATS_NBA,
            }
        )
    if not pemain:
        raise ValueError("stats_nba_format_changed")
    return pemain


class _PerGameTableParser(HTMLParser):
    """Parser tabel per-game BBRef (hanya <tbody>, per data-stat).

    Cerminan _PerGameTableParser ingest/pemain_3p.py untuk tabel
    id="per_game_stats" (hanya kolom blok yang dipakai di sini).
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
    """Satu kali parse tabel per-game BBRef; ValueError bila gagal."""
    parser = _PerGameTableParser()
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
        pemain.append(
            {
                "player": nama,
                "team": bbref_mod.BBREF_TRICODE_MAP.get(team_raw, team_raw),
                "games_played": _angka(row.get("games", "")),
                "mp_per_game": _angka(row.get("mp_per_g", "")),
                "blk_per_game": _angka(row.get("blk_per_g", "")),
                "pos": (row.get("pos") or "").strip() or None,
                "source": SOURCE_BBREF,
            }
        )
    if not pemain:
        raise ValueError("bbref_format_changed")
    return pemain


def parse_bbref_blok(html: str) -> list[dict]:
    """Ubah HTML halaman per-game BBRef jadi list pemain blok.

    Skema keluaran sama dengan parse_stats_nba_blok (source
    "Basketball-Reference"). Mencoba juga dengan komentar HTML dibuka
    (BBRef kadang membungkus tabel di komentar).
    """
    try:
        return _parse_bbref_sekali(html)
    except ValueError:
        if "<!--" not in html:
            raise
        return _parse_bbref_sekali(html.replace("<!--", "").replace("-->", ""))


def normalisasi_nama(nama: str) -> str:
    """Nama pemain ternormalisasi untuk pencocokan antar-sumber.

    Aksen dilucuti (Jokić -> Jokic), huruf kecil, spasi diringkas.
    stats.nba.com dan BBRef memakai ejaan yang sama untuk sebagian
    besar pemain; yang tidak cocok tercatat di "tanpa_posisi".
    """
    tanpa_aksen = unicodedata.normalize("NFKD", nama)
    tanpa_aksen = tanpa_aksen.encode("ascii", "ignore").decode("ascii")
    return " ".join(tanpa_aksen.lower().split())


def fetch_posisi_bbref(season: str) -> dict[tuple[str, str], str]:
    """Peta posisi BBRef: (nama ternormalisasi, tim) -> pos.

    Satu tarikan halaman per-game BBRef. Raise RuntimeError bila
    fetch/parse gagal — pemanggil memutuskan (main: gagal total).
    """
    try:
        url = BBREF_PER_GAME_URL.format(season=_musim_bbref(season))
        resp = bbref_mod.shared_client().get(url)
        if resp.get("status") != 200 or not isinstance(resp.get("body"), str):
            raise RuntimeError(
                f"BBRef posisi: http_{resp.get('status')} "
                f"{resp.get('error') or 'gagal'}"
            )
        pemain = parse_bbref_blok(resp["body"])
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"BBRef posisi: {exc}") from exc
    posisi: dict[tuple[str, str], str] = {}
    for entri in pemain:
        pos = entri.get("pos")
        if pos:
            posisi[(normalisasi_nama(entri["player"]), entri["team"])] = pos
    if not posisi:
        raise RuntimeError("BBRef posisi: tidak ada posisi terbaca")
    return posisi


def gabung_posisi(pemain: list[dict], posisi: dict[tuple[str, str], str]) -> list[dict]:
    """Isi field "pos" tiap pemain dari peta posisi BBRef.

    Pemain yang sudah punya pos (sumber BBRef) tidak ditimpa.
    Pemain yang tidak cocok dibiarkan pos=None (ditangani
    turunkan_pemetaan -> daftar "tanpa_posisi").
    """
    for entri in pemain:
        if entri.get("pos"):
            continue
        entri["pos"] = posisi.get(
            (normalisasi_nama(entri.get("player") or ""), entri.get("team"))
        )
    return pemain


def fetch_pemain_blok(season: str) -> tuple[list[dict], str]:
    """Tarik pemain blok seluruh liga (stats.nba.com, fallback BBRef).

    Mengembalikan (pemain, sumber). Raise RuntimeError bila kedua
    sumber gagal (pesan kedua kegagalan dirangkai).
    """
    galat: list[str] = []
    try:
        resp = _client_stats_nba().get(STATS_NBA_URL.format(season=season))
        if resp.get("status") == 200:
            data = parse_json_body(resp)
            if isinstance(data, dict):
                return parse_stats_nba_blok(data), SOURCE_STATS_NBA
        galat.append(
            f"stats.nba.com: http_{resp.get('status')} "
            f"{resp.get('error') or 'gagal'}"
        )
    except (ValueError, TypeError) as exc:
        galat.append(f"stats.nba.com: {exc}")
    try:
        url = BBREF_PER_GAME_URL.format(season=_musim_bbref(season))
        resp = bbref_mod.shared_client().get(url)
        if resp.get("status") == 200 and isinstance(resp.get("body"), str):
            return parse_bbref_blok(resp["body"]), SOURCE_BBREF
        galat.append(f"BBRef: http_{resp.get('status')} {resp.get('error') or 'gagal'}")
    except (ValueError, TypeError) as exc:
        galat.append(f"BBRef: {exc}")
    raise RuntimeError("tarik data blok gagal di kedua sumber: " + "; ".join(galat))


def turunkan_pemetaan(
    pemain: list[dict],
    min_games: float,
    min_mp: float,
    min_blk: float,
    max_per_team: int,
    position_filter: list[str] | tuple[str, ...] | None = None,
) -> tuple[dict[str, list[dict]], list[dict]]:
    """Pilih rim protector per tim (maks max_per_team, urut BPG).

    Hanya pemain rotasi (GP >= min_games, MP >= min_mp) dengan blok
    bermakna (BLK >= min_blk) DAN posisi big (pos ada di
    position_filter; position_filter None/[] = tanpa filter posisi
    — hanya untuk keperluan tes/kompatibilitas, JANGAN dipakai di
    produksi v18). Seri BPG (< 1e-9) -> menit lebih besar -> nama
    abjad (deterministik). Tim tanpa pemain yang memenuhi syarat
    tidak muncul di pemetaan (veto tidak bisa menilai tim itu).

    Mengembalikan (pemetaan, tanpa_posisi): "tanpa_posisi" adalah
    pemain yang lolos ambang blok/menit tapi posisinya tidak
    diketahui (pos None) sehingga dikeluarkan — jejak audit.
    Pemain yang posisinya diketahui tapi di luar filter (guard/
    wing) dikeluarkan tanpa dicatat (itu fungsi filter).
    """
    saringan = set(position_filter or [])
    per_tim: dict[str, list[dict]] = {}
    tanpa_posisi: list[dict] = []
    for entri in pemain:
        gp = _angka(entri.get("games_played"))
        mp = _angka(entri.get("mp_per_game"))
        blk = _angka(entri.get("blk_per_game"))
        tim = entri.get("team")
        nama = entri.get("player")
        if not tim or not nama or gp is None or mp is None or blk is None:
            continue
        if gp < min_games or mp < min_mp or blk < min_blk:
            continue
        pos = (entri.get("pos") or "").strip() or None
        if saringan:
            if pos is None:
                tanpa_posisi.append(
                    {
                        "player": nama,
                        "team": tim,
                        "blk_per_game": round(blk, 4),
                        "mp_per_game": round(mp, 4),
                        "games_played": int(gp),
                    }
                )
                continue
            if pos not in saringan:
                continue
        per_tim.setdefault(tim, []).append(
            {
                "player": nama,
                "pos": pos,
                "blk_per_game": round(blk, 4),
                "mp_per_game": round(mp, 4),
                "games_played": int(gp),
            }
        )
    hasil: dict[str, list[dict]] = {}
    for tim, daftar in per_tim.items():
        daftar.sort(key=lambda e: (-e["blk_per_game"], -e["mp_per_game"], e["player"]))
        hasil[tim] = daftar[:max_per_team]
    return hasil, tanpa_posisi


def main(argv: list[str] | None = None) -> int:
    """Tarik + turunkan + tulis pemetaan. 0 sukses, 2 fetch gagal."""
    parser = argparse.ArgumentParser(
        description="Tarik data blok pemain + turunkan pemetaan rim protector."
    )
    parser.add_argument("--season", default="2026-27", help="musim NBA (2026-27)")
    parser.add_argument(
        "--out",
        default="config/rim_protector_2026-27.json",
        help="file output JSON (default: config/rim_protector_2026-27.json)",
    )
    args = parser.parse_args(argv)
    cfg = config_mod.load_playstyle()
    rp = cfg["vonis"]["veto"]["rim_protector"]
    min_games = float(rp["min_games"])
    min_mp = float(rp["min_mp_per_game"])
    min_blk = float(rp["min_blk_per_game"])
    max_per_team = int(rp["max_per_team"])
    position_filter = list(rp["position_filter"])
    try:
        pemain, sumber = fetch_pemain_blok(args.season)
    except RuntimeError as exc:
        print(f"gagal: {exc}", file=sys.stderr)
        return 2
    # Posisi selalu dari BBRef (stats.nba.com tidak menyediakan
    # kolom posisi). Bila sumber blok sudah BBRef, pos sudah ada.
    sumber_posisi = SOURCE_BBREF
    if sumber == SOURCE_STATS_NBA:
        try:
            posisi = fetch_posisi_bbref(args.season)
        except RuntimeError as exc:
            print(
                f"gagal: {exc} — pemetaan tanpa filter posisi "
                "adalah cacat v17; file JSON lama dipertahankan",
                file=sys.stderr,
            )
            return 2
        gabung_posisi(pemain, posisi)
    pemetaan, tanpa_posisi = turunkan_pemetaan(
        pemain, min_games, min_mp, min_blk, max_per_team, position_filter
    )
    dokumen = {
        "format": "rim_protector",
        "format_version": 1,
        "season": args.season,
        "fetched_at": now_iso(),
        "source": sumber,
        "position_source": sumber_posisi,
        "n_players_fetched": len(pemain),
        "rule": {
            "min_games": min_games,
            "min_mp_per_game": min_mp,
            "min_blk_per_game": min_blk,
            "max_per_team": max_per_team,
            "position_filter": position_filter,
            "penjelasan": (
                "Per tim maksimal max_per_team pemain rotasi "
                "(GP >= min_games, MP >= min_mp_per_game) dengan blok "
                "bermakna (BLK >= min_blk_per_game) DAN posisi big "
                "(pos BBRef ada di position_filter), urut BPG "
                "tertinggi (seri -> menit -> nama). Aturan + ambang "
                "di config/playstyle.yaml section "
                "vonis.veto.rim_protector."
            ),
        },
        "tanpa_posisi": tanpa_posisi,
        "teams": pemetaan,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(dokumen, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Sumber: {sumber} ({len(pemain)} pemain, musim {args.season})")
    print(f"Posisi: {sumber_posisi} (filter {position_filter})")
    print(f"Tim terpetakan: {len(pemetaan)} dari 30")
    for tim in sorted(pemetaan):
        daftar = ", ".join(
            f"{p['player']} ({p.get('pos')}, {p['blk_per_game']} blok/laga, "
            f"{p['mp_per_game']} mnt, {p['games_played']} laga)"
            for p in pemetaan[tim]
        )
        print(f"  {tim}: {daftar}")
    if tanpa_posisi:
        print(
            f"\nTanpa posisi (lolos ambang tapi dikeluarkan, "
            f"{len(tanpa_posisi)} pemain):"
        )
        for entri in tanpa_posisi:
            print(
                f"  {entri['player']} ({entri['team']}, "
                f"{entri['blk_per_game']} blok/laga)"
            )
    print(f"\nDitulis: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
