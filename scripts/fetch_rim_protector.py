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

ATURAN DERIVASI (ambang dari section vonis.rim_protector di
config/playstyle.yaml — bukan dari kode):
- Rotasi: GP >= min_games DAN MP >= min_mp_per_game.
- Blok bermakna: BLK >= min_blk_per_game.
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
Wilson 0,9) juga OUT. KETERBATASAN JUJUR: aturan BPG murni bisa
menamai guard di tim yang bloknya lemah (mis. DET: Cade Cunningham
0,9) — veto hanya menyala bila pemain itu OUT + garis/pace tinggi,
dan alasannya selalu menyebut nama + angka bloknya supaya bisa
diaudit.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
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
    blk_per_game, source. Baris tanpa nama/tim dilewati; baris TOT
    (agregat pemain pindah tim) dilewati. ValueError bila resultSet
    hilang, kolom wajib hilang, atau tidak ada baris pemain sama
    sekali (format berubah).
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
) -> dict[str, list[dict]]:
    """Pilih rim protector per tim (maks max_per_team, urut BPG).

    Hanya pemain rotasi (GP >= min_games, MP >= min_mp) dengan blok
    bermakna (BLK >= min_blk). Seri BPG (< 1e-9) -> menit lebih besar
    -> nama abjad (deterministik). Tim tanpa pemain yang memenuhi
    syarat tidak muncul di pemetaan (veto tidak bisa menilai tim itu).
    """
    per_tim: dict[str, list[dict]] = {}
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
        per_tim.setdefault(tim, []).append(
            {
                "player": nama,
                "blk_per_game": round(blk, 4),
                "mp_per_game": round(mp, 4),
                "games_played": int(gp),
            }
        )
    hasil: dict[str, list[dict]] = {}
    for tim, daftar in per_tim.items():
        daftar.sort(key=lambda e: (-e["blk_per_game"], -e["mp_per_game"], e["player"]))
        hasil[tim] = daftar[:max_per_team]
    return hasil


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
    rp = cfg["vonis"]["rim_protector"]
    min_games = float(rp["min_games"])
    min_mp = float(rp["min_mp_per_game"])
    min_blk = float(rp["min_blk_per_game"])
    max_per_team = int(rp["max_per_team"])
    try:
        pemain, sumber = fetch_pemain_blok(args.season)
    except RuntimeError as exc:
        print(f"gagal: {exc}", file=sys.stderr)
        return 2
    pemetaan = turunkan_pemetaan(pemain, min_games, min_mp, min_blk, max_per_team)
    dokumen = {
        "format": "rim_protector",
        "format_version": 1,
        "season": args.season,
        "fetched_at": now_iso(),
        "source": sumber,
        "n_players_fetched": len(pemain),
        "rule": {
            "min_games": min_games,
            "min_mp_per_game": min_mp,
            "min_blk_per_game": min_blk,
            "max_per_team": max_per_team,
            "penjelasan": (
                "Per tim maksimal max_per_team pemain rotasi "
                "(GP >= min_games, MP >= min_mp_per_game) dengan blok "
                "bermakna (BLK >= min_blk_per_game), urut BPG "
                "tertinggi (seri -> menit -> nama). Aturan + ambang "
                "di config/playstyle.yaml section vonis.rim_protector."
            ),
        },
        "teams": pemetaan,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(dokumen, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Sumber: {sumber} ({len(pemain)} pemain, musim {args.season})")
    print(f"Tim terpetakan: {len(pemetaan)} dari 30")
    for tim in sorted(pemetaan):
        daftar = ", ".join(
            f"{p['player']} ({p['blk_per_game']} blok/laga, "
            f"{p['mp_per_game']} mnt, {p['games_played']} laga)"
            for p in pemetaan[tim]
        )
        print(f"  {tim}: {daftar}")
    print(f"\nDitulis: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
