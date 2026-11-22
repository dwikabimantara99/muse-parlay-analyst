"""Tes ingest/player_gamelog.py — TANPA network (mock client + fixture).

Fixture player_gamelog_duren_2027.html adalah cuplikan NYATA tabel
player_game_log_reg dari halaman game log Jalen Duren musim 2026-27
(diambil live 2026-11-22): 15 laga (2 bermain + 13 Inactive) + 1 baris
header di tengah <tbody> yang harus dilewati.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import bbref, player_gamelog

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "nba_brain"
DUREN_HTML = (FIXTURES / "player_gamelog_duren_2027.html").read_text(encoding="utf-8")
DUREN_URL = "https://www.basketball-reference.com/players/d/durenja01/gamelog/2027/"


class FakeClient:
    """Client palsu: get() mengembalikan respons yang sudah disiapkan."""

    def __init__(self, responses: dict[str, dict]) -> None:
        self.responses = responses
        self.urls_requested: list[str] = []

    def get(self, url: str, use_cache: bool = True) -> dict:
        """Kembalikan respons untuk URL (default: 404)."""
        self.urls_requested.append(url)
        return self.responses.get(url, {"status": 404, "body": "", "error": None})


def _resp(status: int, body: str) -> dict:
    return {"status": status, "body": body, "error": None}


def _laga(tanggal: str, nomor: int, tim: str = "DET", main: bool = True) -> dict:
    """Satu dict laga sintetis (bentuk hasil parse_player_gamelog)."""
    return {
        "date": tanggal,
        "team_game_num": nomor,
        "team": tim,
        "opponent": "BOS",
        "result": "W, 100-90",
        "played": main,
        "mp": "25:00" if main else None,
        "status": None if main else "Inactive",
    }


class TestParsePlayerGamelog(unittest.TestCase):
    def test_parse_fixture_duren_nyata(self):
        games = player_gamelog.parse_player_gamelog(DUREN_HTML)
        # 15 laga nyata (baris header tengah tabel dilewati).
        self.assertEqual(len(games), 15)
        pertama = games[0]
        self.assertEqual(pertama["date"], "2026-10-20")
        self.assertEqual(pertama["team_game_num"], 1)
        self.assertEqual(pertama["team"], "DET")
        self.assertEqual(pertama["opponent"], "BOS")
        self.assertTrue(pertama["played"])
        self.assertEqual(pertama["mp"], "28:02")
        self.assertIsNone(pertama["status"])
        # 2 bermain, 13 tidak bermain.
        self.assertEqual(sum(1 for g in games if g["played"]), 2)
        tidak_main = [g for g in games if not g["played"]]
        self.assertEqual(len(tidak_main), 13)
        self.assertTrue(all(g["status"] == "Inactive" for g in tidak_main))
        self.assertTrue(all(g["mp"] is None for g in tidak_main))
        # Laga terakhir: 2026-11-20, laga tim ke-15.
        self.assertEqual(games[-1]["date"], "2026-11-20")
        self.assertEqual(games[-1]["team_game_num"], 15)

    def test_baris_header_tengah_dilewati(self):
        # Fixture memuat baris header di tengah <tbody> (date="Date",
        # nomor="Gtm") — tidak boleh muncul sebagai laga.
        games = player_gamelog.parse_player_gamelog(DUREN_HTML)
        self.assertTrue(all(g["date"] != "Date" for g in games))
        self.assertEqual([g["team_game_num"] for g in games], list(range(1, 16)))

    def test_tabel_hilang_melempar(self):
        with self.assertRaises(ValueError) as ctx:
            player_gamelog.parse_player_gamelog("<html><body>kosong</body></html>")
        self.assertIn("bbref_format_changed", str(ctx.exception))

    def test_tabel_dalam_komentar_tetap_terparse(self):
        # BBRef kadang membungkus tabel di komentar — fallback harus
        # bekerja (konvensi ingest.bbref).
        html_berkomentar = f"<html><body><!--{DUREN_HTML}--></body></html>"
        games = player_gamelog.parse_player_gamelog(html_berkomentar)
        self.assertEqual(len(games), 15)


class TestCountMissedLast10(unittest.TestCase):
    def test_duren_missed_10_dari_10_terakhir(self):
        games = player_gamelog.parse_player_gamelog(DUREN_HTML)
        hitungan = player_gamelog.count_missed_last10(games, team="DET")
        # 10 laga terakhir DET (laga tim 6-15): Duren Inactive semua.
        self.assertEqual(hitungan["missed_last10"], 10)
        self.assertEqual(hitungan["played_last10"], 0)
        self.assertEqual(hitungan["games_considered"], 10)
        self.assertEqual(hitungan["window"], 10)

    def test_filter_tim_lain_nol_laga(self):
        games = player_gamelog.parse_player_gamelog(DUREN_HTML)
        hitungan = player_gamelog.count_missed_last10(games, team="BOS")
        self.assertEqual(hitungan["missed_last10"], 0)
        self.assertEqual(hitungan["games_considered"], 0)

    def test_hitungan_pada_log_sintetis(self):
        # 12 laga: 5 pertama bermain, 7 terakhir tidak bermain.
        games = [
            _laga(f"2026-11-{d:02d}", i + 1, main=(i < 5))
            for i, d in enumerate(range(1, 13))
        ]
        hitungan = player_gamelog.count_missed_last10(games)
        # 10 terakhir = laga 3-12: 3 bermain (laga 3-5) + 7 tidak.
        self.assertEqual(hitungan["missed_last10"], 7)
        self.assertEqual(hitungan["played_last10"], 3)
        self.assertEqual(hitungan["games_considered"], 10)

    def test_awal_musim_laga_kurang_dari_window(self):
        games = [
            _laga(f"2026-10-{d:02d}", i + 1, main=False)
            for i, d in enumerate(range(20, 24))
        ]
        hitungan = player_gamelog.count_missed_last10(games)
        self.assertEqual(hitungan["missed_last10"], 4)
        self.assertEqual(hitungan["games_considered"], 4)

    def test_tricode_bbref_dipetakan(self):
        # Baris BBRef "BRK" harus cocok dengan argumen team "BKN".
        games = [_laga("2026-11-01", 1, tim="BRK", main=False)]
        hitungan = player_gamelog.count_missed_last10(games, team="BKN")
        self.assertEqual(hitungan["games_considered"], 1)
        self.assertEqual(hitungan["missed_last10"], 1)

    def test_pemain_pindah_tim_hanya_tim_saat_ini(self):
        games = [
            _laga("2026-10-20", 1, tim="DET", main=False),
            _laga("2026-10-23", 2, tim="DET", main=False),
            _laga("2026-10-25", 3, tim="ATL", main=True),
        ]
        hitungan = player_gamelog.count_missed_last10(games, team="ATL")
        self.assertEqual(hitungan["games_considered"], 1)
        self.assertEqual(hitungan["missed_last10"], 0)

    def test_window_tidak_valid_melempar(self):
        with self.assertRaises(ValueError):
            player_gamelog.count_missed_last10([], window=0)


class TestFetchMissedLast10(unittest.TestCase):
    def test_fetch_duren_dari_fixture(self):
        client = FakeClient({DUREN_URL: _resp(200, DUREN_HTML)})
        result = player_gamelog.fetch_missed_last10(
            "d/durenja01", team="DET", client=client
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.data["missed_last10"], 10)
        self.assertEqual(result.data["games_considered"], 10)
        self.assertEqual(result.data["slug"], "d/durenja01")
        self.assertEqual(client.urls_requested, [DUREN_URL])

    def test_fetch_404_tidak_melempar(self):
        client = FakeClient({})
        result = player_gamelog.fetch_missed_last10(
            "x/tidakada01", team="DET", client=client
        )
        self.assertFalse(result.ok)
        self.assertIn("http_404", result.error)

    def test_slug_tidak_valid_tidak_melempar(self):
        result = player_gamelog.fetch_missed_last10("", team="DET")
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "bbref_slug_tidak_valid")

    def test_fetch_many_campur_sukses_dan_gagal(self):
        client = FakeClient({DUREN_URL: _resp(200, DUREN_HTML)})
        hasil = player_gamelog.fetch_missed_last10_many(
            [
                {
                    "player": "Jalen Duren",
                    "bbref_slug": "d/durenja01",
                    "team_tricode": "DET",
                },
                {
                    "player": "Tanpa Slug",
                    "bbref_slug": None,
                    "team_tricode": "DET",
                },
                {
                    "player": "Halaman Hilang",
                    "bbref_slug": "x/hilang01",
                    "team_tricode": "ATL",
                },
            ],
            client=client,
        )
        self.assertEqual(hasil["Jalen Duren"]["missed_last10"], 10)
        self.assertIsNone(hasil["Jalen Duren"]["error"])
        self.assertIsNone(hasil["Tanpa Slug"]["missed_last10"])
        self.assertEqual(hasil["Tanpa Slug"]["error"], "bbref_slug_tidak_ada")
        self.assertIsNone(hasil["Halaman Hilang"]["missed_last10"])
        self.assertIn("http_404", hasil["Halaman Hilang"]["error"])


class TestBbrefSlug(unittest.TestCase):
    """Kontrak slug: bbref.parse_player_advanced harus mengembalikan
    bbref_slug untuk dipakai player_gamelog. (Tes ini tinggal di sini
    karena tests/test_ingest_bbref.py di luar kepemilikan patch ini.)"""

    def test_slug_ditangkap_dari_tautan_nama(self):
        html = """<html><body>
<table class="stats_table" id="advanced">
<thead><tr>
<th data-stat="ranker">Rk</th><th data-stat="name_display">Player</th>
<th data-stat="team_name_abbr">Tm</th><th data-stat="games">G</th>
<th data-stat="mp">MP</th><th data-stat="bpm">BPM</th>
</tr></thead>
<tbody>
<tr><th data-stat="ranker">1</th>
<td data-stat="name_display"><a href="/players/d/durenja01.html">Jalen Duren</a></td>
<td data-stat="team_name_abbr">DET</td><td data-stat="games">2</td>
<td data-stat="mp">38</td><td data-stat="bpm">8.8</td></tr>
<tr><th data-stat="ranker">2</th>
<td data-stat="name_display">Pemain Tanpa Tautan</td>
<td data-stat="team_name_abbr">ATL</td><td data-stat="games">5</td>
<td data-stat="mp">100</td><td data-stat="bpm">1.0</td></tr>
</tbody></table>
</body></html>"""
        players = bbref.parse_player_advanced(html)
        self.assertEqual(len(players), 2)
        self.assertEqual(players[0]["bbref_slug"], "d/durenja01")
        self.assertEqual(players[0]["player"], "Jalen Duren")
        self.assertIsNone(players[1]["bbref_slug"])


if __name__ == "__main__":
    unittest.main()
