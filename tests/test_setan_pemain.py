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
        "boost_pp": 12.0,
        "cap_pct": 0.50,
    },
    "vonis": {
        "tiga_pa_rate_top10_cutoff": 0.45,
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
# sana); total setan v18 (rumus cap) adalah 253,71 (v17: 274,14).
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


class TestRumusCap(unittest.TestCase):
    """Rumus cap v18: pct_setan = min(cap, pct musim + boost)."""

    def test_pemain_36_2_persen_tambah_12pp_tanpa_cap(self):
        # Kasus wajib tugas: 36,2% + 12pp = 48,2% < 50% cap.
        self.assertAlmostEqual(sp.pct_setan_pemain(0.362, 12.0, 0.50), 0.482)

    def test_pemain_45_persen_kena_cap_50_persen(self):
        # Kasus wajib tugas: 45% + 12pp = 57% -> cap 50%.
        self.assertAlmostEqual(sp.pct_setan_pemain(0.45, 12.0, 0.50), 0.50)

    def test_pemain_30_persen_tambah_12pp(self):
        self.assertAlmostEqual(sp.pct_setan_pemain(0.30, 12.0, 0.50), 0.42)

    def test_pemain_50_persen_tetap_cap(self):
        # Penembak 50% tidak naik lagi: min(0,50, 0,62) = 0,50.
        self.assertAlmostEqual(sp.pct_setan_pemain(0.50, 12.0, 0.50), 0.50)


class TestFlag3Par(unittest.TestCase):
    """Flag 3P Volume Risk: kedua tim Top-10 3PAr."""

    def test_kedua_tim_di_atas_cutoff_true(self):
        self.assertIs(sp.evaluasi_flag_3par(0.46, 0.47, 0.45), True)

    def test_satu_tim_di_bawah_cutoff_false(self):
        self.assertIs(sp.evaluasi_flag_3par(0.46, 0.40, 0.45), False)

    def test_nilai_3par_hilang_tidak_dievaluasi(self):
        self.assertEqual(sp.evaluasi_flag_3par(None, 0.47, 0.45), "tidak_dievaluasi")
        self.assertEqual(sp.evaluasi_flag_3par(0.46, None, 0.45), "tidak_dievaluasi")

    def test_cutoff_hilang_tidak_dievaluasi(self):
        self.assertEqual(sp.evaluasi_flag_3par(0.46, 0.47, None), "tidak_dievaluasi")


class TestHitungSetanPemain(unittest.TestCase):
    """Rumus setan per pemain (hitung tangan)."""

    def _pemain_rumus(self):
        # % terbaik liga (INFO saja di v18, bukan input rumus):
        # ZZZ 60,0% (5,0 x 20 = 100 total >= 50).
        return [
            _pemain("P1", "AAA", 15, 30.0, 6.0, 0.400),
            _pemain("P2", "AAA", 15, 20.0, 4.0, 0.200),
            _pemain("P3_OUT", "AAA", 15, 30.0, 10.0, 0.300),
            _pemain("P4_BENCH", "AAA", 15, 5.0, 2.0, 0.400),
            _pemain("Q1", "BBB", 15, 30.0, 5.0, 0.350),
            _pemain("Q2", "BBB", 15, 15.0, 3.0, 0.250),
            _pemain("ZZZ", "CCC", 20, 30.0, 5.0, 0.600),
        ]

    def test_rumus_hitung_tangan(self):
        # Rumus cap v18 (boost 12pp, cap 50%):
        # AAA: P1 pct setan min(0,50, 0,52)=0,50 -> normal 6,0x0,4x3=7,2
        #      setan 6,0x0,5x3=9,0; P2 pct setan 0,32 -> normal
        #      4,0x0,2x3=2,4 setan 4,0x0,32x3=3,84.
        #      -> att 10,0 normal 9,6 setan 12,84.
        # BBB: Q1 pct setan 0,47 -> normal 5,0x0,35x3=5,25 setan
        #      5,0x0,47x3=7,05; Q2 pct setan 0,37 -> normal
        #      3,0x0,25x3=2,25 setan 3,0x0,37x3=3,33.
        #      -> att 8,0 normal 7,5 setan 10,38.
        # Gabung: att 18,0 normal 17,1 setan 23,22.
        # Total = 230,0 - 17,1 + 23,22 = 236,12; geser 6,12;
        # deviasi vs 232,5 = +3,62.
        hasil = sp.hitung_setan_pemain(
            self._pemain_rumus(),
            "AAA",
            "BBB",
            230.0,
            garis_bandar=232.5,
            pemain_absen={"P3_OUT"},
            cfg=CFG_SETAN,
        )
        self.assertEqual(hasil["total_setan_pemain"], 236.12)
        self.assertEqual(hasil["geser_setan_pemain"], 6.12)
        self.assertEqual(hasil["deviasi_setan_pemain_dari_garis_bandar"], 3.62)
        self.assertEqual(hasil["percobaan_3p_diharapkan_gabungan"], 18.0)
        self.assertEqual(hasil["poin_3p_normal_gabungan"], 17.1)
        self.assertEqual(hasil["poin_3p_setan_gabungan"], 23.22)
        self.assertEqual(hasil["boost_pp"], 12.0)
        self.assertEqual(hasil["cap_pct"], 0.50)
        self.assertEqual(hasil["sumber_boost_cap"], "config")
        # % terbaik liga tetap dilaporkan sebagai INFO (bukan input).
        self.assertEqual(hasil["pct_terbaik_liga"]["player"], "ZZZ")
        self.assertEqual(hasil["pct_terbaik_liga"]["pct"], 0.6)
        # Tanpa 3PAr -> flag tidak dievaluasi (bukan False).
        self.assertEqual(hasil["flag_3par_volume_risk"], "tidak_dievaluasi")
        aaa = hasil["tim"]["kandang"]
        self.assertEqual(aaa["n_pemain_rotasi_main"], 2)
        self.assertEqual(aaa["n_pemain_absen_dikeluarkan"], 1)
        self.assertEqual(aaa["pemain_absen_dikeluarkan"], ["P3_OUT"])
        self.assertEqual(aaa["n_pemain_di_luar_rotasi"], 1)
        self.assertEqual(aaa["percobaan_3p_diharapkan"], 10.0)
        # Top kontributor AAA: P1 (selisih 1,8) di atas P2 (1,44).
        self.assertEqual(aaa["top_kontributor"][0]["player"], "P1")
        self.assertEqual(aaa["top_kontributor"][0]["selisih_vs_normal"], 1.8)
        self.assertEqual(aaa["top_kontributor"][0]["pct_setan_3p"], 0.5)
        self.assertEqual(aaa["top_kontributor"][1]["player"], "P2")
        self.assertEqual(aaa["top_kontributor"][1]["pct_setan_3p"], 0.32)

    def test_flag_3par_dari_argumen_tiga_pa_rate(self):
        hasil = sp.hitung_setan_pemain(
            self._pemain_rumus(),
            "AAA",
            "BBB",
            230.0,
            pemain_absen={"P3_OUT"},
            cfg=CFG_SETAN,
            tiga_pa_rate={"AAA": 0.46, "BBB": 0.47},
        )
        self.assertIs(hasil["flag_3par_volume_risk"], True)
        self.assertEqual(hasil["tiga_pa_rate"], {"kandang": 0.46, "tandang": 0.47})
        self.assertEqual(hasil["tiga_pa_rate_top10_cutoff"], 0.45)
        hasil_rendah = sp.hitung_setan_pemain(
            self._pemain_rumus(),
            "AAA",
            "BBB",
            230.0,
            pemain_absen={"P3_OUT"},
            cfg=CFG_SETAN,
            tiga_pa_rate={"AAA": 0.46, "BBB": 0.40},
        )
        self.assertIs(hasil_rendah["flag_3par_volume_risk"], False)

    def test_cutoff_3par_hilang_flag_tidak_dievaluasi(self):
        cfg_tanpa_cutoff = {"setan_pemain": dict(CFG_SETAN["setan_pemain"])}
        hasil = sp.hitung_setan_pemain(
            self._pemain_rumus(),
            "AAA",
            "BBB",
            230.0,
            pemain_absen={"P3_OUT"},
            cfg=cfg_tanpa_cutoff,
            tiga_pa_rate={"AAA": 0.46, "BBB": 0.47},
        )
        self.assertEqual(hasil["flag_3par_volume_risk"], "tidak_dievaluasi")
        self.assertIsNone(hasil["tiga_pa_rate_top10_cutoff"])

    def test_flag_dimatikan_di_config_tidak_dievaluasi(self):
        cfg_flag_mati = {
            "setan_pemain": {
                **CFG_SETAN["setan_pemain"],
                "add_3par_volume_flag": False,
            },
            "vonis": dict(CFG_SETAN["vonis"]),
        }
        hasil = sp.hitung_setan_pemain(
            self._pemain_rumus(),
            "AAA",
            "BBB",
            230.0,
            pemain_absen={"P3_OUT"},
            cfg=cfg_flag_mati,
            tiga_pa_rate={"AAA": 0.46, "BBB": 0.47},
        )
        self.assertEqual(hasil["flag_3par_volume_risk"], "tidak_dievaluasi")
        self.assertTrue(any("dinonaktifkan" in c for c in hasil["catatan"]))

    def test_boost_cap_hilang_pakai_nilai_kontrak_default(self):
        # Kunci boost_pp/cap_pct ditulis worker A; bila belum ada,
        # dipakai nilai kontrak 12,0/0,50 + sumber "default" (pola
        # DEFAULT_HARGA_MIN_CENTS) — total sama dengan CFG_SETAN.
        cfg_tanpa_kunci = {
            "setan_pemain": {
                "enabled": True,
                "pct_terbaik_min_total_3pa": 50,
                "ambang_menit_rotasi": 10.0,
            },
            "vonis": dict(CFG_SETAN["vonis"]),
        }
        hasil = sp.hitung_setan_pemain(
            self._pemain_rumus(),
            "AAA",
            "BBB",
            230.0,
            garis_bandar=232.5,
            pemain_absen={"P3_OUT"},
            cfg=cfg_tanpa_kunci,
        )
        self.assertEqual(hasil["boost_pp"], 12.0)
        self.assertEqual(hasil["cap_pct"], 0.50)
        self.assertEqual(hasil["sumber_boost_cap"], "default")
        self.assertEqual(hasil["total_setan_pemain"], 236.12)

    def test_boost_cap_tidak_valid_config_error(self):
        cfg_boost_negatif = {
            "setan_pemain": {**CFG_SETAN["setan_pemain"], "boost_pp": -1.0}
        }
        with self.assertRaises(config_mod.ConfigError):
            sp.hitung_setan_pemain(
                self._pemain_rumus(), "AAA", "BBB", 230.0, cfg=cfg_boost_negatif
            )
        cfg_cap_lebih_satu = {
            "setan_pemain": {**CFG_SETAN["setan_pemain"], "cap_pct": 1.5}
        }
        with self.assertRaises(config_mod.ConfigError):
            sp.hitung_setan_pemain(
                self._pemain_rumus(), "AAA", "BBB", 230.0, cfg=cfg_cap_lebih_satu
            )

    def test_pemain_absen_tidak_dihitung(self):
        # Tanpa filter absen, P3_OUT (10,0 percobaan @30%) ikut:
        # normal 10,0x0,3x3=9,0; setan 10,0x0,42x3=12,6;
        # selisih +3,6 -> total tanpa filter 239,72.
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
        self.assertEqual(dengan_filter["total_setan_pemain"], 236.12)
        self.assertEqual(tanpa_filter["total_setan_pemain"], 239.72)
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
        self.assertEqual(hasil["total_setan_pemain"], 236.12)
        self.assertEqual(hasil["tim"]["kandang"]["n_pemain_dilewati_tanpa_data"], 1)
        self.assertTrue(any("RUSAK" in c for c in hasil["catatan"]))

    def test_daftar_kosong_raises(self):
        with self.assertRaises(ValueError):
            sp.hitung_setan_pemain([], "AAA", "BBB", 230.0, cfg=CFG_SETAN)

    def test_tidak_ada_kandidat_pct_terbaik_info_none_tanpa_raise(self):
        # v18: % terbaik liga hanya INFO — tidak ada kandidat bukan
        # lagi error. Satu pemain AAA 1,0 percobaan @90%:
        # pct setan min(0,50, 1,02)=0,50; normal 2,7; setan 1,5;
        # total = 230,0 - 2,7 + 1,5 = 228,8. BBB tanpa pemain -> 0.
        pemain = [_pemain("Kecil", "AAA", 2, 30.0, 1.0, 0.900)]
        hasil = sp.hitung_setan_pemain(pemain, "AAA", "BBB", 230.0, cfg=CFG_SETAN)
        self.assertIsNone(hasil["pct_terbaik_liga"])
        self.assertEqual(hasil["total_setan_pemain"], 228.8)
        self.assertTrue(
            any("tidak ada pemain memenuhi ambang" in c for c in hasil["catatan"])
        )

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
    23 Nov 2026, dibulatkan — lihat DEN_CHI_PEMAIN), rumus cap v18
    (boost 12pp, cap 50%):
    - DEN rotasi main (10): att 32,10; normal 34,28; setan 43,61
      (Murray 7,1 @47,2% -> cap 50%: 10,65; Spencer Jones 1,8 @42,9%
      -> cap 50%: 2,70; sisanya +12pp di bawah cap).
    - CHI rotasi main (12): att 35,20; normal 33,81; setan 45,19
      (Jalen Smith 5,2 @41,1% -> cap 50%: 7,80; Hield 4,9 @43,5% ->
      cap 50%: 7,35; sisanya +12pp di bawah cap).
    - Gabung: att 67,30; normal 68,09; setan 88,80.
    - Total = 233,0 - 68,09 + 88,80 = 253,71; geser 20,71;
      deviasi vs garis bandar 236,5 = +17,21.
      (v17 dengan % terbaik liga 54,1% seragam: 274,14 — cap
      menurunkan total 20,43 poin, TAPI kedua kaki nyata tetap
      rapuh karena 253,71 masih di atas U252,5/U250,5.)
    - % terbaik liga (INFO saja di v18): Cam Spencer (MEM) 54,1%
      (61,2 percobaan).
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
        self.assertEqual(hasil["total_setan_pemain"], 253.71)
        self.assertEqual(hasil["geser_setan_pemain"], 20.71)
        self.assertEqual(hasil["deviasi_setan_pemain_dari_garis_bandar"], 17.21)
        self.assertEqual(hasil["percobaan_3p_diharapkan_gabungan"], 67.3)
        self.assertEqual(hasil["poin_3p_normal_gabungan"], 68.09)
        self.assertEqual(hasil["poin_3p_setan_gabungan"], 88.8)
        self.assertEqual(hasil["pct_terbaik_liga"]["player"], "Cam Spencer")
        self.assertEqual(hasil["pct_terbaik_liga"]["pct"], 0.541)
        self.assertEqual(hasil["pct_terbaik_liga"]["team"], "MEM")
        den = hasil["tim"]["tandang"]
        chi = hasil["tim"]["kandang"]
        self.assertEqual(den["n_pemain_rotasi_main"], 10)
        self.assertEqual(den["n_pemain_absen_dikeluarkan"], 3)
        self.assertEqual(den["n_pemain_di_luar_rotasi"], 3)
        self.assertEqual(den["poin_3p_setan"], 43.61)
        self.assertEqual(chi["n_pemain_rotasi_main"], 12)
        self.assertEqual(chi["n_pemain_absen_dikeluarkan"], 4)
        self.assertEqual(chi["n_pemain_di_luar_rotasi"], 1)
        self.assertEqual(chi["poin_3p_setan"], 45.19)
        # Top kontributor v18: DEN Cameron Johnson (selisih 1,91),
        # CHI Matas Buzelis (selisih 2,12).
        self.assertEqual(den["top_kontributor"][0]["player"], "Cameron Johnson")
        self.assertEqual(den["top_kontributor"][0]["selisih_vs_normal"], 1.91)
        self.assertEqual(den["top_kontributor"][0]["pct_setan_3p"], 0.479)
        self.assertEqual(chi["top_kontributor"][0]["player"], "Matas Buzelis")
        self.assertEqual(chi["top_kontributor"][0]["selisih_vs_normal"], 2.12)
        self.assertEqual(chi["top_kontributor"][0]["pct_setan_3p"], 0.482)
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
        # Total setan v18 253,71 > kedua garis nyata (252,5 / 250,5)
        # — MASIH rapuh, tapi tipis (hanya +1,21 / +3,21 di atas
        # garis, vs +21,64 / +23,64 di v17).
        # P(setan pemain) dari CDF artefak, geser 20,71:
        # U252,5: CDF(231,79) = 0,45132+0,645x(0,49293-0,45132) = 0,4782
        #   (interpolasi 230,5 -> 232,5).
        # U250,5: CDF(229,79) = 0,40996+0,645x(0,45132-0,40996) = 0,4366
        #   (interpolasi 228,5 -> 230,5).
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
        self.assertEqual(hasil["skenario"]["setan"]["geser_points"], 20.71)
        by_ticket = {k["ticket"]: k for k in hasil["kaki"]}
        asuransi = by_ticket["insurance"]
        self.assertTrue(asuransi["flag_setan_pemain"])
        self.assertEqual(asuransi["total_setan_pemain"], 253.71)
        self.assertEqual(asuransi["deviasi_setan_pemain_dari_garis_bandar"], 17.21)
        self.assertAlmostEqual(asuransi["p_setan_pemain"], 0.4782, places=4)
        self.assertTrue(asuransi["flag_setan"])
        utama = by_ticket["main"]
        self.assertTrue(utama["flag_setan_pemain"])
        self.assertAlmostEqual(utama["p_setan_pemain"], 0.4366, places=4)
        self.assertTrue(utama["flag_setan"])


if __name__ == "__main__":
    unittest.main()
