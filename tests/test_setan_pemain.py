"""Tes setan per pemain — TANPA network, TANPA membaca out/.

Semua fixture dibangun di dalam file ini (JSON stats.nba.com sintetis,
HTML BBRef sintetis, daftar pemain sintetis, CDF sintetis), jadi tes
lulus di checkout bersih — KECUALI TestDenChiEndToEnd (kasus uji wajib
DEN@CHI dari artefak nyata; dilewati bila artefak tidak ada, seperti
TestDenChiSetan di tests/test_stress.py). Angka ekspektasi dihitung
tangan dari definisi di docstring engine/setan_pemain.py.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine import setan_pemain as sp
from engine import stress
from ingest import pemain_3p as p3p

CFG_SETAN = {
    "setan_pemain": {
        "enabled": True,
        "pct_terbaik_min_total_3pa": 50,
        "ambang_menit_rotasi": 10.0,
    },
}

CFG_STRESS = {
    "stress": {
        "banjir_3p_points": 10.0,
        "banjir_ft_points": 15.0,
        "setan_points": 25.0,
    },
    "tickets": {
        "insurance": {"min_leg_prob": 0.74},
        "main": {"min_leg_prob": 0.65},
    },
    "setan_pemain": dict(CFG_SETAN["setan_pemain"]),
}

# CDF sintetis (sama seperti tests/test_stress.py).
MARKETS = {
    "moneyline_home": 0.6,
    "moneyline_away": 0.4,
    "total_under_200.5": 0.10,
    "total_under_210.5": 0.30,
    "total_under_220.5": 0.50,
    "total_under_230.5": 0.70,
    "total_under_240.5": 0.85,
    "total_under_250.5": 0.95,
}

TANGGA = [
    {"line": 250.5, "side": "under", "price_cents": 90.0, "thin": True},
    {"line": 230.5, "side": "under", "price_cents": 70.0, "thin": False},
    {"line": 240.5, "side": "under", "price_cents": 80.0, "thin": False},
]


def _pemain(nama, tim, gp, menit, fg3a, pct, source="stats.nba.com"):
    """Satu baris pemain skema ingest/pemain_3p.py."""
    return {
        "player": nama,
        "team": tim,
        "games_played": gp,
        "mp_per_game": menit,
        "fg3a_per_game": fg3a,
        "fg3_per_game": round(fg3a * pct, 2) if pct is not None else None,
        "fg3_pct": pct,
        "fg3a_total": fg3a * gp if gp is not None else None,
        "bbref_slug": None,
        "source": source,
    }


def _analysis(median=220.5, garis_market=224.5, legs=None):
    return {
        "match_id": "XXX@YYY_2026-11-22",
        "simulation": {
            "markets": dict(MARKETS),
            "score_distribution": {"total": {"median": median}},
        },
        "market": {
            "main_total_line": garis_market,
            "totals": list(TANGGA),
        },
        "legs": (
            legs
            if legs is not None
            else [{"line": 240.5, "ticket": "insurance", "price_cents": 80.0}]
        ),
    }


# --- Fixture DEN@CHI: nilai ASLI (dibulatkan) dari stats.nba.com 23 Nov
# 2026 — 10 pemain rotasi DEN + 12 rotasi CHI yang main, pemain OUT,
# pemain di luar rotasi, dan % terbaik liga (Cam Spencer, MEM, 54,1%).
# Ekspektasi dihitung tangan di TestDenChiEndToEnd (lihat komentar di
# sana); angka-angka ini JUGA dipakai verifikasi live di
# scripts/verifikasi_setan_pemain.py (total 274,14).
DEN_CHI_PEMAIN = [
    # DEN rotasi yang main (10).
    _pemain("Nikola Jokić", "DEN", 15, 37.1, 4.2, 0.302),
    _pemain("Jamal Murray", "DEN", 15, 37.0, 7.1, 0.472),
    _pemain("Christian Braun", "DEN", 15, 34.0, 4.9, 0.351),
    _pemain("Aaron Gordon", "DEN", 15, 29.5, 3.9, 0.276),
    _pemain("Cameron Johnson", "DEN", 12, 28.8, 5.3, 0.359),
    _pemain("DeMar DeRozan", "DEN", 14, 22.5, 1.3, 0.167),
    _pemain("Trevon Brazile", "DEN", 15, 18.1, 2.0, 0.367),
    _pemain("Spencer Jones", "DEN", 8, 18.0, 1.8, 0.429),
    _pemain("Marvin Bagley III", "DEN", 15, 11.8, 0.5, 0.250),
    _pemain("Tyus Jones", "DEN", 15, 10.4, 1.1, 0.235),
    # DEN OUT (3 di data; Strawther tidak ada di data — GP 0).
    _pemain("Bryce Hopkins", "DEN", 8, 12.9, 0.6, 0.400),
    _pemain("Cam Whitmore", "DEN", 2, 7.4, 1.0, 0.0),
    _pemain("DaRon Holmes II", "DEN", 4, 2.4, 0.8, 0.333),
    # DEN di luar rotasi (3).
    _pemain("Alpha Diallo", "DEN", 4, 8.0, 0.8, 0.0),
    _pemain("Zeke Nnaji", "DEN", 2, 3.7, 0.5, 1.000),
    _pemain("Ryan Nembhard", "DEN", 3, 3.2, 0.3, 1.000),
    # CHI rotasi yang main (12).
    _pemain("Josh Giddey", "CHI", 16, 28.6, 3.8, 0.317),
    _pemain("Matas Buzelis", "CHI", 16, 27.9, 5.9, 0.362),
    _pemain("Jalen Smith", "CHI", 14, 25.3, 5.2, 0.411),
    _pemain("Isaac Okoro", "CHI", 16, 24.4, 3.3, 0.283),
    _pemain("Patrick Williams", "CHI", 9, 20.9, 2.7, 0.292),
    _pemain("Tre Jones", "CHI", 16, 19.0, 1.1, 0.278),
    _pemain("Buddy Hield", "CHI", 14, 18.0, 4.9, 0.435),
    _pemain("Leonard Miller", "CHI", 12, 14.0, 2.4, 0.172),
    _pemain("Noa Essengue", "CHI", 15, 12.9, 2.0, 0.267),
    _pemain("Zach Collins", "CHI", 11, 11.5, 1.4, 0.133),
    _pemain("Tobe Awaka", "CHI", 4, 10.2, 0.0, 0.0),
    _pemain("Jordan Hawkins", "CHI", 8, 10.1, 2.5, 0.200),
    # CHI OUT (4).
    _pemain("Caleb Wilson", "CHI", 10, 30.8, 7.1, 0.324),
    _pemain("Norman Powell", "CHI", 13, 29.5, 6.8, 0.341),
    _pemain("Nic Claxton", "CHI", 6, 20.4, 0.0, 0.0),
    _pemain("Jaylin Sellers", "CHI", 6, 8.0, 2.8, 0.412),
    # CHI di luar rotasi (1).
    _pemain("Dailyn Swain", "CHI", 4, 6.7, 1.3, 0.0),
    # % terbaik liga (min 50 total percobaan): Cam Spencer, MEM.
    _pemain("Cam Spencer", "MEM", 17, 20.0, 3.6, 0.541),
]

DEN_CHI_ABSEN = {
    "DaRon Holmes II",
    "Bryce Hopkins",
    "Julian Strawther",  # Tidak ada di data pemain (GP 0) -> catatan.
    "Cam Whitmore",
    "Nic Claxton",
    "Norman Powell",
    "Jaylin Sellers",
    "Caleb Wilson",
}


class TestParseStatsNba(unittest.TestCase):
    """Parser JSON leaguedashplayerstats."""

    def _json(self, rows, headers=None):
        headers = headers or [
            "PLAYER_ID",
            "PLAYER_NAME",
            "TEAM_ABBREVIATION",
            "GP",
            "MIN",
            "FG3M",
            "FG3A",
            "FG3_PCT",
        ]
        return {
            "resultSets": [
                {"name": "LeagueDashPlayerStats", "headers": headers, "rowSet": rows}
            ]
        }

    def test_parse_ok_dan_skema(self):
        data = self._json(
            [
                [1, "Jamal Murray", "DEN", 15, 37.0, 3.3, 7.1, 0.472],
                [2, "Nic Claxton", "CHI", 6, 20.4, 0.0, 0.0, 0.0],
            ]
        )
        hasil = p3p.parse_stats_nba_pemain(data)
        self.assertEqual(len(hasil), 2)
        murray = hasil[0]
        self.assertEqual(murray["player"], "Jamal Murray")
        self.assertEqual(murray["team"], "DEN")
        self.assertEqual(murray["games_played"], 15)
        self.assertEqual(murray["mp_per_game"], 37.0)
        self.assertEqual(murray["fg3a_per_game"], 7.1)
        self.assertEqual(murray["fg3_pct"], 0.472)
        self.assertAlmostEqual(murray["fg3a_total"], 106.5)
        self.assertEqual(murray["source"], "stats.nba.com")
        self.assertIsNone(murray["bbref_slug"])

    def test_baris_tanpa_nama_atau_tim_dilewati(self):
        data = self._json(
            [
                [1, "", "DEN", 15, 37.0, 3.3, 7.1, 0.472],
                [2, "Jamal Murray", "", 15, 37.0, 3.3, 7.1, 0.472],
                [3, "Jamal Murray", "DEN", 15, 37.0, 3.3, 7.1, 0.472],
            ]
        )
        self.assertEqual(len(p3p.parse_stats_nba_pemain(data)), 1)

    def test_kolom_wajib_hilang_raises(self):
        data = self._json(
            [[1, "Jamal Murray", "DEN", 15, 37.0, 3.3, 7.1]],
            headers=[
                "PLAYER_ID",
                "PLAYER_NAME",
                "TEAM_ABBREVIATION",
                "GP",
                "MIN",
                "FG3M",
                "FG3A",
            ],
        )
        with self.assertRaises(ValueError):
            p3p.parse_stats_nba_pemain(data)

    def test_tidak_ada_resultset_raises(self):
        with self.assertRaises(ValueError):
            p3p.parse_stats_nba_pemain({"resultSets": []})
        with self.assertRaises(ValueError):
            p3p.parse_stats_nba_pemain({})


class TestParseBbref(unittest.TestCase):
    """Parser tabel per-game BBRef (id=per_game_stats, kolom _per_g)."""

    HTML = """<html><body><table id="per_game_stats"><tbody>
<tr><th data-stat="name_display"><a href="/players/m/murraja01.html">Jamal Murray</a></th>
<td data-stat="team_name_abbr">DEN</td><td data-stat="games">15</td>
<td data-stat="mp_per_g">37.0</td><td data-stat="fg3_per_g">3.3</td>
<td data-stat="fg3a_per_g">7.1</td><td data-stat="fg3_pct">.472</td></tr>
<tr><th data-stat="name_display">Pemain Brooklyn</th>
<td data-stat="team_name_abbr">BRK</td><td data-stat="games">10</td>
<td data-stat="mp_per_g">20.0</td><td data-stat="fg3_per_g">1.0</td>
<td data-stat="fg3a_per_g">3.0</td><td data-stat="fg3_pct">.333</td></tr>
<tr><th data-stat="name_display">Pemain Pindah</th>
<td data-stat="team_name_abbr">TOT</td><td data-stat="games">20</td>
<td data-stat="mp_per_g">25.0</td><td data-stat="fg3_per_g">2.0</td>
<td data-stat="fg3a_per_g">5.0</td><td data-stat="fg3_pct">.400</td></tr>
<tr><th data-stat="name_display">League Average</th>
<td data-stat="team_name_abbr"></td><td data-stat="games"></td>
<td data-stat="mp_per_g"></td><td data-stat="fg3_per_g"></td>
<td data-stat="fg3a_per_g"></td><td data-stat="fg3_pct"></td></tr>
</tbody></table></body></html>"""

    def test_parse_ok_slug_dan_tricode(self):
        hasil = p3p.parse_bbref_per_game(self.HTML)
        self.assertEqual(len(hasil), 2)
        murray = hasil[0]
        self.assertEqual(murray["player"], "Jamal Murray")
        self.assertEqual(murray["team"], "DEN")
        self.assertEqual(murray["games_played"], 15)
        self.assertEqual(murray["mp_per_game"], 37.0)
        self.assertEqual(murray["fg3a_per_game"], 7.1)
        self.assertEqual(murray["fg3_pct"], 0.472)
        self.assertAlmostEqual(murray["fg3a_total"], 106.5)
        self.assertEqual(murray["bbref_slug"], "m/murraja01")
        self.assertEqual(murray["source"], "Basketball-Reference")
        # BRK dipetakan ke BKN; TOT + League Average dilewati.
        self.assertEqual(hasil[1]["team"], "BKN")

    def test_tabel_hilang_raises(self):
        with self.assertRaises(ValueError):
            p3p.parse_bbref_per_game("<html><body>tidak ada tabel</body></html>")

    def test_tabel_dalam_komentar_tetap_terbaca(self):
        html_komentar = self.HTML.replace(
            '<table id="per_game_stats">', '<!--<table id="per_game_stats">'
        ).replace("</table>", "</table>-->")
        hasil = p3p.parse_bbref_per_game(html_komentar)
        self.assertEqual(len(hasil), 2)

    def test_kolom_wajib_hilang_raises(self):
        html = self.HTML.replace('data-stat="fg3a_per_g"', 'data-stat="fg3a"')
        with self.assertRaises(ValueError):
            p3p.parse_bbref_per_game(html)


class TestPctTerbaikLiga(unittest.TestCase):
    """Seleksi % 3P terbaik liga (ambang percobaan minimum)."""

    def test_ambang_menyaring_sampel_kecil(self):
        pemain = [
            _pemain("Fluke", "AAA", 2, 30.0, 1.0, 1.000),  # total 2.0
            _pemain("Terbaik", "BBB", 17, 30.0, 3.6, 0.541),  # total 61.2
            _pemain("Biasa", "CCC", 15, 30.0, 7.0, 0.400),  # total 105.0
        ]
        hasil = sp.pct_terbaik_liga(pemain, 50)
        self.assertEqual(hasil["player"], "Terbaik")
        self.assertEqual(hasil["pct"], 0.541)
        self.assertEqual(hasil["team"], "BBB")
        self.assertAlmostEqual(hasil["total_3pa"], 61.2)

    def test_seri_pct_pilih_total_percobaan_lebih_besar(self):
        pemain = [
            _pemain("A", "AAA", 10, 30.0, 5.0, 0.500),  # total 50.0
            _pemain("B", "BBB", 15, 30.0, 5.0, 0.500),  # total 75.0
        ]
        self.assertEqual(sp.pct_terbaik_liga(pemain, 50)["player"], "B")

    def test_tidak_ada_kandidat_none(self):
        pemain = [_pemain("Kecil", "AAA", 2, 30.0, 1.0, 0.900)]
        self.assertIsNone(sp.pct_terbaik_liga(pemain, 50))
        self.assertIsNone(sp.pct_terbaik_liga([], 50))

    def test_ambang_negatif_raises(self):
        with self.assertRaises(ValueError):
            sp.pct_terbaik_liga([], -1)


class TestPemainAbsen(unittest.TestCase):
    """Ekstraksi pemain OUT dari artefak analisis."""

    def test_bentuk_entries_nba_analysis(self):
        analysis = {
            "injuries": {
                "entries": [
                    {"player": "Caleb Wilson", "status": "OUT"},
                    {"player": "Jalen Smith", "status": "PROBABLE"},
                    {"player": "Norman Powell", "status": "OUT"},
                ]
            }
        }
        self.assertEqual(
            sp.pemain_absen_dari_artefak(analysis),
            {"Caleb Wilson", "Norman Powell"},
        )

    def test_bentuk_daftar_slate_dan_status_kecil(self):
        analysis = {
            "injuries": [
                {"player": "A", "status": "Out"},
                {"player": "B", "status": "Available"},
                {"player": "C", "status": "out"},
                {"player": "D", "status": "Day-To-Day"},
            ]
        }
        self.assertEqual(sp.pemain_absen_dari_artefak(analysis), {"A", "C"})

    def test_tanpa_blok_cedera_kosong(self):
        self.assertEqual(sp.pemain_absen_dari_artefak({}), set())
        self.assertEqual(sp.pemain_absen_dari_artefak({"injuries": None}), set())


class TestHitungSetanPemain(unittest.TestCase):
    """Rumus setan per pemain (hitung tangan)."""

    def _pemain_rumus(self):
        # % terbaik liga: ZZZ 60,0% (5,0 x 20 = 100 total >= 50).
        return [
            _pemain("P1", "AAA", 15, 30.0, 6.0, 0.400),
            _pemain("P2", "AAA", 15, 20.0, 4.0, 0.200),
            _pemain("P3_OUT", "AAA", 15, 30.0, 10.0, 0.500),
            _pemain("P4_BENCH", "AAA", 15, 5.0, 2.0, 0.400),
            _pemain("Q1", "BBB", 15, 30.0, 5.0, 0.350),
            _pemain("Q2", "BBB", 15, 15.0, 3.0, 0.250),
            _pemain("ZZZ", "CCC", 20, 30.0, 5.0, 0.600),
        ]

    def test_rumus_hitung_tangan(self):
        # AAA: P1 normal 6,0x0,4x3=7,2 setan 6,0x0,6x3=10,8;
        #      P2 normal 4,0x0,2x3=2,4 setan 4,0x0,6x3=7,2.
        #      -> att 10,0 normal 9,6 setan 18,0.
        # BBB: Q1 normal 5,0x0,35x3=5,25 setan 9,0;
        #      Q2 normal 3,0x0,25x3=2,25 setan 5,4.
        #      -> att 8,0 normal 7,5 setan 14,4.
        # Gabung: att 18,0 normal 17,1 setan 32,4.
        # Total = 230,0 - 17,1 + 32,4 = 245,3; geser 15,3;
        # deviasi vs 232,5 = +12,8.
        hasil = sp.hitung_setan_pemain(
            self._pemain_rumus(),
            "AAA",
            "BBB",
            230.0,
            garis_bandar=232.5,
            pemain_absen={"P3_OUT"},
            cfg=CFG_SETAN,
        )
        self.assertEqual(hasil["total_setan_pemain"], 245.3)
        self.assertEqual(hasil["geser_setan_pemain"], 15.3)
        self.assertEqual(hasil["deviasi_setan_pemain_dari_garis_bandar"], 12.8)
        self.assertEqual(hasil["percobaan_3p_diharapkan_gabungan"], 18.0)
        self.assertEqual(hasil["poin_3p_normal_gabungan"], 17.1)
        self.assertEqual(hasil["poin_3p_setan_gabungan"], 32.4)
        self.assertEqual(hasil["pct_terbaik_liga"]["player"], "ZZZ")
        self.assertEqual(hasil["pct_terbaik_liga"]["pct"], 0.6)
        aaa = hasil["tim"]["kandang"]
        self.assertEqual(aaa["n_pemain_rotasi_main"], 2)
        self.assertEqual(aaa["n_pemain_absen_dikeluarkan"], 1)
        self.assertEqual(aaa["pemain_absen_dikeluarkan"], ["P3_OUT"])
        self.assertEqual(aaa["n_pemain_di_luar_rotasi"], 1)
        self.assertEqual(aaa["percobaan_3p_diharapkan"], 10.0)
        # Top kontributor AAA: P2 (selisih 4,8) di atas P1 (3,6).
        self.assertEqual(aaa["top_kontributor"][0]["player"], "P2")
        self.assertEqual(aaa["top_kontributor"][0]["selisih_vs_normal"], 4.8)
        self.assertEqual(aaa["top_kontributor"][1]["player"], "P1")

    def test_pemain_absen_tidak_dihitung(self):
        # Tanpa filter absen, P3_OUT (10,0 percobaan) ikut: total naik.
        dengan_filter = sp.hitung_setan_pemain(
            self._pemain_rumus(),
            "AAA",
            "BBB",
            230.0,
            pemain_absen={"P3_OUT"},
            cfg=CFG_SETAN,
        )
        tanpa_filter = sp.hitung_setan_pemain(
            self._pemain_rumus(), "AAA", "BBB", 230.0, pemain_absen=set(), cfg=CFG_SETAN
        )
        # P3_OUT: normal 10,0x0,5x3=15,0; setan 10,0x0,6x3=18,0;
        # selisih +3,0 -> total tanpa filter 248,3.
        self.assertEqual(dengan_filter["total_setan_pemain"], 245.3)
        self.assertEqual(tanpa_filter["total_setan_pemain"], 248.3)
        self.assertEqual(
            tanpa_filter["percobaan_3p_diharapkan_gabungan"],
            dengan_filter["percobaan_3p_diharapkan_gabungan"] + 10.0,
        )

    def test_tanpa_info_cedera_dicatat(self):
        hasil = sp.hitung_setan_pemain(
            self._pemain_rumus(), "AAA", "BBB", 230.0, pemain_absen=None, cfg=CFG_SETAN
        )
        self.assertTrue(any("tidak ada info cedera" in c for c in hasil["catatan"]))

    def test_garis_bandar_none_deviasi_none(self):
        hasil = sp.hitung_setan_pemain(
            self._pemain_rumus(),
            "AAA",
            "BBB",
            230.0,
            garis_bandar=None,
            pemain_absen=set(),
            cfg=CFG_SETAN,
        )
        self.assertIsNone(hasil["deviasi_setan_pemain_dari_garis_bandar"])
        self.assertIsNone(hasil["garis_bandar"])

    def test_pemain_tanpa_data_dilewati_dan_dicatat(self):
        pemain = self._pemain_rumus()
        rusak = _pemain("RUSAK", "AAA", 15, None, 5.0, 0.400)  # tanpa menit
        pemain.append(rusak)
        hasil = sp.hitung_setan_pemain(
            pemain, "AAA", "BBB", 230.0, pemain_absen={"P3_OUT"}, cfg=CFG_SETAN
        )
        # Total tidak berubah (RUSAK dilewati, bukan ditebak 0).
        self.assertEqual(hasil["total_setan_pemain"], 245.3)
        self.assertEqual(hasil["tim"]["kandang"]["n_pemain_dilewati_tanpa_data"], 1)
        self.assertTrue(any("RUSAK" in c for c in hasil["catatan"]))

    def test_daftar_kosong_raises(self):
        with self.assertRaises(ValueError):
            sp.hitung_setan_pemain([], "AAA", "BBB", 230.0, cfg=CFG_SETAN)

    def test_tidak_ada_kandidat_pct_terbaik_raises(self):
        pemain = [_pemain("Kecil", "AAA", 2, 30.0, 1.0, 0.900)]
        with self.assertRaises(ValueError):
            sp.hitung_setan_pemain(pemain, "AAA", "BBB", 230.0, cfg=CFG_SETAN)

    def test_config_hilang_raises(self):
        with self.assertRaises(config_mod.ConfigError):
            sp.hitung_setan_pemain(self._pemain_rumus(), "AAA", "BBB", 230.0, cfg={})


class TestWiringStress(unittest.TestCase):
    """Wiring skenario_panas: setan pemain dipakai / fallback."""

    def test_setan_pemain_dipakai(self):
        # Total setan 242,5; median 220,5 -> geser 22,0.
        # Kaki U240,5: P(setan) = CDF(218,5) = 0,30+0,20x(8/10) = 0,46.
        # P(normal) = CDF(240,5) = 0,85 >= 0,74 -> flag_setan True.
        # Deviasi vs garis bandar 224,5 = +18,0.
        # Garis tahan-setan: TIDAK ADA — garis tangga tertinggi 250,5
        # memberi CDF(228,5)=0,66 < 0,74 (interpolasi 220,5: 0,50 ->
        # 230,5: 0,70).
        data = {"total_setan_pemain": 242.5}
        hasil = stress.skenario_panas(_analysis(), cfg=CFG_STRESS, setan_pemain=data)
        self.assertTrue(hasil["setan_pemain_dipakai"])
        self.assertEqual(hasil["skenario"]["setan"]["geser_points"], 22.0)
        self.assertEqual(hasil["skenario"]["setan"]["sumber_setan"], "pemain")
        self.assertEqual(hasil["skenario"]["setan"]["total_setan_pemain"], 242.5)
        kaki = hasil["kaki"][0]
        self.assertEqual(kaki["p_under"]["setan"], 0.46)
        self.assertEqual(kaki["p_setan_pemain"], 0.46)
        self.assertTrue(kaki["flag_setan"])
        self.assertTrue(kaki["flag_setan_pemain"])
        self.assertEqual(kaki["total_setan_pemain"], 242.5)
        self.assertEqual(kaki["deviasi_setan_pemain_dari_garis_bandar"], 18.0)
        self.assertIsNone(kaki["garis_tahan_setan"])
        self.assertIsNotNone(kaki["alasan_tidak_tahan_setan"])
        # Banjir TIDAK berubah: geser banjir_3p tetap 10,0.
        self.assertEqual(hasil["skenario"]["banjir_3p"]["geser_points"], 10.0)
        self.assertEqual(kaki["p_under"]["banjir_3p"], 0.70)

    def test_fallback_tanpa_data(self):
        hasil = stress.skenario_panas(_analysis(), cfg=CFG_STRESS)
        self.assertFalse(hasil["setan_pemain_dipakai"])
        self.assertEqual(hasil["skenario"]["setan"]["geser_points"], 25.0)
        self.assertEqual(hasil["skenario"]["setan"]["sumber_setan"], "umum")
        self.assertIn("Fallback", hasil["skenario"]["setan"]["penjelasan"])
        kaki = hasil["kaki"][0]
        self.assertIsNone(kaki["total_setan_pemain"])
        self.assertIsNone(kaki["deviasi_setan_pemain_dari_garis_bandar"])
        self.assertIsNone(kaki["p_setan_pemain"])
        self.assertIsNone(kaki["flag_setan_pemain"])
        # P setan umum tetap jalan: CDF(240,5-25)=CDF(215,5)=0,40.
        self.assertEqual(kaki["p_under"]["setan"], 0.40)

    def test_fallback_data_rusak_dicatat(self):
        hasil = stress.skenario_panas(
            _analysis(), cfg=CFG_STRESS, setan_pemain={"total_setan_pemain": "xx"}
        )
        self.assertFalse(hasil["setan_pemain_dipakai"])
        self.assertEqual(hasil["skenario"]["setan"]["geser_points"], 25.0)
        self.assertTrue(
            any("tanpa total_setan_pemain numerik" in c for c in hasil["catatan"])
        )

    def test_data_dari_analysis_dict(self):
        analysis = _analysis()
        analysis["setan_pemain"] = {"total_setan_pemain": 242.5}
        hasil = stress.skenario_panas(analysis, cfg=CFG_STRESS)
        self.assertTrue(hasil["setan_pemain_dipakai"])
        self.assertEqual(hasil["skenario"]["setan"]["geser_points"], 22.0)

    def test_argumen_menang_atas_analysis(self):
        analysis = _analysis()
        analysis["setan_pemain"] = {"total_setan_pemain": 242.5}
        hasil = stress.skenario_panas(
            analysis, cfg=CFG_STRESS, setan_pemain={"total_setan_pemain": 230.5}
        )
        self.assertEqual(hasil["skenario"]["setan"]["geser_points"], 10.0)

    def test_dinonaktifkan_di_config_fallback(self):
        cfg = {
            "stress": CFG_STRESS["stress"],
            "tickets": CFG_STRESS["tickets"],
            "setan_pemain": {
                "enabled": False,
                "pct_terbaik_min_total_3pa": 50,
                "ambang_menit_rotasi": 10.0,
            },
        }
        hasil = stress.skenario_panas(
            _analysis(), cfg=cfg, setan_pemain={"total_setan_pemain": 242.5}
        )
        self.assertFalse(hasil["setan_pemain_dipakai"])
        self.assertEqual(hasil["skenario"]["setan"]["geser_points"], 25.0)
        self.assertTrue(any("dinonaktifkan" in c for c in hasil["catatan"]))

    def test_section_hilang_kompatibel(self):
        cfg = {"stress": CFG_STRESS["stress"], "tickets": CFG_STRESS["tickets"]}
        hasil = stress.skenario_panas(
            _analysis(), cfg=cfg, setan_pemain={"total_setan_pemain": 242.5}
        )
        self.assertTrue(hasil["setan_pemain_dipakai"])

    def test_enabled_hilang_raises(self):
        cfg = {
            "stress": CFG_STRESS["stress"],
            "tickets": CFG_STRESS["tickets"],
            "setan_pemain": {"pct_terbaik_min_total_3pa": 50},
        }
        with self.assertRaises(config_mod.ConfigError):
            stress.skenario_panas(_analysis(), cfg=cfg)

    def test_garis_bandar_tidak_ada_deviasi_none(self):
        analysis = _analysis(garis_market=None)
        hasil = stress.skenario_panas(
            analysis, cfg=CFG_STRESS, setan_pemain={"total_setan_pemain": 242.5}
        )
        self.assertTrue(hasil["setan_pemain_dipakai"])
        self.assertIsNone(hasil["kaki"][0]["deviasi_setan_pemain_dari_garis_bandar"])


class TestDenChiEndToEnd(unittest.TestCase):
    """DEN@CHI ujung-ke-ujung dengan fixture nilai asli.

    Ekspektasi dihitung tangan dari nilai fixture (stats.nba.com
    23 Nov 2026, dibulatkan — lihat DEN_CHI_PEMAIN):
    - DEN rotasi main (10): att 32,10; normal 34,28; setan 52,10.
    - CHI rotasi main (12): att 35,20; normal 33,81; setan 57,13.
    - Gabung: att 67,30; normal 68,09; setan 109,23.
    - Total = 233,0 - 68,09 + 109,23 = 274,14; geser 41,14;
      deviasi vs garis bandar 236,5 = +37,64.
    - % terbaik liga: Cam Spencer (MEM) 54,1% (61,2 percobaan).
    """

    ARTEFAK = (
        Path(__file__).resolve().parent.parent
        / "out"
        / "analysis_verif_tahap4_2026-11-22.json"
    )

    def test_total_setan_dan_rincian(self):
        hasil = sp.hitung_setan_pemain(
            DEN_CHI_PEMAIN,
            "CHI",
            "DEN",
            233.0,
            garis_bandar=236.5,
            pemain_absen=DEN_CHI_ABSEN,
            cfg=CFG_SETAN,
        )
        self.assertEqual(hasil["total_setan_pemain"], 274.14)
        self.assertEqual(hasil["geser_setan_pemain"], 41.14)
        self.assertEqual(hasil["deviasi_setan_pemain_dari_garis_bandar"], 37.64)
        self.assertEqual(hasil["percobaan_3p_diharapkan_gabungan"], 67.3)
        self.assertEqual(hasil["poin_3p_normal_gabungan"], 68.09)
        self.assertEqual(hasil["poin_3p_setan_gabungan"], 109.23)
        self.assertEqual(hasil["pct_terbaik_liga"]["player"], "Cam Spencer")
        self.assertEqual(hasil["pct_terbaik_liga"]["pct"], 0.541)
        self.assertEqual(hasil["pct_terbaik_liga"]["team"], "MEM")
        den = hasil["tim"]["tandang"]
        chi = hasil["tim"]["kandang"]
        self.assertEqual(den["n_pemain_rotasi_main"], 10)
        self.assertEqual(den["n_pemain_absen_dikeluarkan"], 3)
        self.assertEqual(den["n_pemain_di_luar_rotasi"], 3)
        self.assertEqual(chi["n_pemain_rotasi_main"], 12)
        self.assertEqual(chi["n_pemain_absen_dikeluarkan"], 4)
        self.assertEqual(chi["n_pemain_di_luar_rotasi"], 1)
        # Top kontributor: DEN Aaron Gordon (selisih 3,10), CHI Matas
        # Buzelis (selisih 3,17).
        self.assertEqual(den["top_kontributor"][0]["player"], "Aaron Gordon")
        self.assertEqual(den["top_kontributor"][0]["selisih_vs_normal"], 3.10)
        self.assertEqual(chi["top_kontributor"][0]["player"], "Matas Buzelis")
        self.assertEqual(chi["top_kontributor"][0]["selisih_vs_normal"], 3.17)
        # Strawther (OUT, tidak ada di data) dicatat, bukan error.
        self.assertTrue(any("Strawther" in c for c in hasil["catatan"]))

    def _den_chi(self):
        import json

        data = json.loads(self.ARTEFAK.read_text(encoding="utf-8"))
        for match in data["matches"]:
            if "den-chi" in match["match_id"]:
                return match["nba_analysis"]
        self.fail("DEN@CHI tidak ada di artefak verif tahap 4")

    @unittest.skipUnless(
        ARTEFAK.exists(), "artefak verif tahap 4 tidak ada di checkout ini"
    )
    def test_kedua_kaki_nyata_di_flag_rapuh(self):
        # Total setan 274,14 > kedua garis nyata (252,5 / 250,5).
        # P(setan pemain) dari CDF artefak, geser 41,14:
        # U252,5: CDF(211,36) = 0,12025+0,02211x0,43 = 0,1298.
        # U250,5: CDF(209,36) = 0,00001+0,12024x(73,86/75) = 0,1184
        # (CDF tersimpan jarang di ujung bawah: 135,5 -> 210,5).
        cfg = config_mod.load_playstyle()
        hasil_setan = sp.hitung_setan_pemain(
            DEN_CHI_PEMAIN,
            "CHI",
            "DEN",
            233.0,
            garis_bandar=236.5,
            pemain_absen=DEN_CHI_ABSEN,
            cfg=cfg,
        )
        kaki = [
            {"line": 252.5, "ticket": "insurance", "price_cents": 82.0},
            {"line": 250.5, "ticket": "main", "price_cents": 79.0},
        ]
        hasil = stress.skenario_panas(
            self._den_chi(), kaki=kaki, cfg=cfg, setan_pemain=hasil_setan
        )
        self.assertTrue(hasil["setan_pemain_dipakai"])
        self.assertEqual(hasil["skenario"]["setan"]["geser_points"], 41.14)
        by_ticket = {k["ticket"]: k for k in hasil["kaki"]}
        asuransi = by_ticket["insurance"]
        self.assertTrue(asuransi["flag_setan_pemain"])
        self.assertEqual(asuransi["total_setan_pemain"], 274.14)
        self.assertEqual(asuransi["deviasi_setan_pemain_dari_garis_bandar"], 37.64)
        self.assertAlmostEqual(asuransi["p_setan_pemain"], 0.1298, places=4)
        self.assertTrue(asuransi["flag_setan"])
        utama = by_ticket["main"]
        self.assertTrue(utama["flag_setan_pemain"])
        self.assertAlmostEqual(utama["p_setan_pemain"], 0.1184, places=4)
        self.assertTrue(utama["flag_setan"])


if __name__ == "__main__":
    unittest.main()
