"""Tes engine/cushion.py — TANPA network, TANPA membaca out/.

Fixture DISALIN (bukan dibaca) dari bukti nyata agar tes tidak
bergantung pada file out/:
- Persentil total sim DET@ATL 2026-11-22 dari
  examples/simulation_nba_ATL_DET_2026-11-22.json (score_distribution
  total: median 223,0, p75 235,0; p74 BELUM ada di output sim saat ini
  -> jalur interpolasi).
- Tangga Under Polymarket nba-det-atl-2026-11-22 dari
  out/poly_ladder_nba-det-atl-2026-11-22.json (31 garis Under,
  line + price_cents + jup_estimated_cents; bid/ask/volume dibuang).
- Garis market 225,5 = garis total bervolume terbesar ($44.032).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import cushion

# Persentil total sim DET@ATL (contoh; tanpa p74 -> interpolasi).
PERCENTILES_DET_ATL = {"median": 223.0, "p75": 235.0}
MARKET_LINE_DET_ATL = 225.5

# Tangga Under DET@ATL (line, price_cents, jup_estimated_cents).
UNDER_LADDER_DET_ATL = [
    (199.5, 7.5, 8.0),
    (201.5, 8.5, 9.0),
    (203.5, 10.5, 11.0),
    (205.5, 13.0, 13.5),
    (207.5, 16.5, 17.0),
    (209.5, 20.0, 20.5),
    (211.5, 23.0, 23.5),
    (213.5, 27.0, 27.5),
    (215.5, 31.5, 32.0),
    (217.5, 35.5, 36.0),
    (219.5, 40.0, 40.5),
    (221.5, 44.0, 44.5),
    (223.5, 48.5, 49.0),
    (224.5, 50.0, 50.5),
    (225.5, 52.5, 53.0),
    (226.5, 55.5, 56.0),
    (227.5, 57.5, 58.0),
    (229.5, 61.5, 62.0),
    (231.5, 65.5, 66.0),
    (233.5, 66.5, 67.0),
    (235.5, 71.0, 71.5),
    (237.5, 75.5, 76.0),
    (239.5, 80.5, 81.0),
    (241.5, 81.5, 82.0),
    (243.5, 85.5, 86.0),
    (245.5, 87.5, 88.0),
    (247.5, 89.5, 90.0),
    (249.5, 92.5, 93.0),
    (251.5, 93.5, 94.0),
    (253.5, 95.5, 96.0),
    (255.5, 95.45, 95.95),
]

LADDER_DET_ATL = [
    {"line": line, "price_cents": harga, "jup_estimated_cents": jup}
    for line, harga, jup in UNDER_LADDER_DET_ATL
]

# Config minimal: kunci bantalan yang SUDAH ada di playstyle.yaml.
# Parameter baru Asuransi (insurance_target_probability,
# market_cushion_floor_points) SENGAJA tidak ada di sini -> jalur
# default (koordinator belum menambahkannya).
CFG_MINIMAL = {
    "filters": {
        "nba_alt_under": {
            "min_cushion_points": 8,
            "min_cushion_points_close_spread": 12,
            "close_spread_threshold": 2.5,
        }
    }
}

CFG_DENGAN_PARAM_BARU = {
    "filters": {
        "nba_alt_under": {
            "min_cushion_points": 8,
            "min_cushion_points_close_spread": 12,
            "close_spread_threshold": 2.5,
            "insurance_target_probability": 0.70,
            "market_cushion_floor_points": 10,
        }
    }
}


class TestInsuranceLineDetAtl(unittest.TestCase):
    def test_interpolasi_p74(self):
        hasil = cushion.insurance_line(
            PERCENTILES_DET_ATL, MARKET_LINE_DET_ATL, LADDER_DET_ATL, CFG_MINIMAL
        )
        self.assertTrue(hasil["meets"])
        self.assertIsNone(hasil["reason"])
        # p74 interpolasi: 223 + (0,74-0,50)/(0,75-0,50) x (235-223) = 234,52.
        self.assertAlmostEqual(hasil["p_target"], 234.52, places=6)
        self.assertEqual(hasil["p_target_source"], "interpolasi_median_p75")
        # Lantai market: 225,5 + 8 = 233,5 < 234,52 -> p74 yang mengikat.
        self.assertEqual(hasil["market_floor"], 233.5)
        self.assertAlmostEqual(hasil["required_line"], 234.52, places=6)
        # Garis terkecil >= 234,52 adalah 235,5.
        self.assertEqual(hasil["line"], 235.5)
        self.assertEqual(hasil["price_cents"], 71.0)
        self.assertEqual(hasil["jup_estimated_cents"], 71.5)
        self.assertEqual(hasil["cushion_vs_market_points"], 10.0)
        self.assertEqual(hasil["cushion_vs_median_points"], 12.5)
        # Parameter baru belum di config -> sumber "default".
        self.assertEqual(hasil["target_probability"], 0.74)
        self.assertEqual(hasil["target_probability_source"], "default")
        self.assertEqual(hasil["market_cushion_floor_points"], 8)
        self.assertEqual(hasil["market_cushion_floor_source"], "default")

    def test_dengan_p74_langsung(self):
        percentiles = {"median": 223.0, "p74": 234.0, "p75": 235.0}
        hasil = cushion.insurance_line(
            percentiles, MARKET_LINE_DET_ATL, LADDER_DET_ATL, CFG_MINIMAL
        )
        self.assertTrue(hasil["meets"])
        self.assertEqual(hasil["p_target"], 234.0)
        self.assertEqual(hasil["p_target_source"], "p74")
        self.assertEqual(hasil["line"], 235.5)

    def test_lantai_market_mengikat(self):
        # p74 rendah (230) -> lantai market 233,5 yang mengikat.
        percentiles = {"median": 223.0, "p74": 230.0, "p75": 235.0}
        hasil = cushion.insurance_line(
            percentiles, MARKET_LINE_DET_ATL, LADDER_DET_ATL, CFG_MINIMAL
        )
        self.assertTrue(hasil["meets"])
        self.assertEqual(hasil["required_line"], 233.5)
        self.assertEqual(hasil["line"], 233.5)
        self.assertEqual(hasil["price_cents"], 66.5)

    def test_sigma_melebar_garis_naik(self):
        # Sebaran melebar (p75 235 -> 245): p74 interpolasi naik ke
        # 223 + 0,96 x 22 = 244,12 -> garis Asuransi ikut naik ke 245,5.
        percentiles = {"median": 223.0, "p75": 245.0}
        hasil = cushion.insurance_line(
            percentiles, MARKET_LINE_DET_ATL, LADDER_DET_ATL, CFG_MINIMAL
        )
        self.assertTrue(hasil["meets"])
        self.assertAlmostEqual(hasil["p_target"], 244.12, places=6)
        self.assertEqual(hasil["line"], 245.5)
        self.assertEqual(hasil["price_cents"], 87.5)

    def test_tidak_ada_garis_memenuhi(self):
        # Tangga terpotong di 235,5, tapi required 244,12 (sigma lebar).
        percentiles = {"median": 223.0, "p75": 245.0}
        tangga_pendek = [b for b in LADDER_DET_ATL if b["line"] <= 235.5]
        hasil = cushion.insurance_line(
            percentiles, MARKET_LINE_DET_ATL, tangga_pendek, CFG_MINIMAL
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "tidak_ada_garis_memenuhi")
        self.assertIsNone(hasil["line"])
        self.assertIsNone(hasil["price_cents"])
        self.assertAlmostEqual(hasil["required_line"], 244.12, places=6)

    def test_data_hilang(self):
        # Tanpa persentil -> tidak bisa hitung p_target.
        hasil = cushion.insurance_line(
            {}, MARKET_LINE_DET_ATL, LADDER_DET_ATL, CFG_MINIMAL
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "persentil_tidak_lengkap")
        # Tanpa garis market -> tidak bisa hitung lantai.
        hasil = cushion.insurance_line(
            PERCENTILES_DET_ATL, None, LADDER_DET_ATL, CFG_MINIMAL
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "garis_market_tidak_ada")
        # Tangga kosong.
        hasil = cushion.insurance_line(
            PERCENTILES_DET_ATL, MARKET_LINE_DET_ATL, [], CFG_MINIMAL
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "tangga_kosong")

    def test_target_di_luar_jangkauan(self):
        cfg = {"filters": {"nba_alt_under": {"insurance_target_probability": 0.90}}}
        hasil = cushion.insurance_line(
            PERCENTILES_DET_ATL, MARKET_LINE_DET_ATL, LADDER_DET_ATL, cfg
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "target_di_luar_jangkauan_persentil")

    def test_parameter_dari_config(self):
        # Target 0,70 + lantai 10 dari config (bukan default).
        hasil = cushion.insurance_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            CFG_DENGAN_PARAM_BARU,
        )
        self.assertTrue(hasil["meets"])
        self.assertEqual(hasil["target_probability"], 0.70)
        self.assertEqual(hasil["target_probability_source"], "config")
        self.assertEqual(hasil["market_cushion_floor_points"], 10)
        self.assertEqual(hasil["market_cushion_floor_source"], "config")
        # p70 interpolasi: 223 + 0,8 x 12 = 232,6; lantai 235,5 mengikat.
        self.assertAlmostEqual(hasil["p_target"], 232.6, places=6)
        self.assertEqual(hasil["required_line"], 235.5)
        self.assertEqual(hasil["line"], 235.5)


class TestUtamaLine(unittest.TestCase):
    def test_det_atl_spread_lebar(self):
        # Spread 5,0 -> bantalan 8; base max(223, 225,5) = 225,5;
        # required 233,5 -> garis 233,5.
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            spread=5.0,
            cfg=CFG_MINIMAL,
        )
        self.assertTrue(hasil["meets"])
        self.assertEqual(hasil["cushion_points"], 8)
        self.assertEqual(hasil["base_line"], 225.5)
        self.assertEqual(hasil["required_line"], 233.5)
        self.assertEqual(hasil["line"], 233.5)
        self.assertEqual(hasil["price_cents"], 66.5)

    def test_spread_rapat_bantalan_12(self):
        # Spread 2,0 <= 2,5 -> bantalan 12; required 237,5.
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            spread=2.0,
            cfg=CFG_MINIMAL,
        )
        self.assertTrue(hasil["meets"])
        self.assertEqual(hasil["cushion_points"], 12)
        self.assertEqual(hasil["required_line"], 237.5)
        self.assertEqual(hasil["line"], 237.5)
        self.assertEqual(hasil["price_cents"], 75.5)

    def test_spread_tepat_di_ambang(self):
        # Spread tepat 2,5 -> 12 (aturan: <= 2,5).
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            spread=2.5,
            cfg=CFG_MINIMAL,
        )
        self.assertEqual(hasil["cushion_points"], 12)
        self.assertEqual(hasil["line"], 237.5)

    def test_spread_negatif_diperlakukan_absolut(self):
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            spread=-2.0,
            cfg=CFG_MINIMAL,
        )
        self.assertEqual(hasil["spread"], 2.0)
        self.assertEqual(hasil["cushion_points"], 12)

    def test_spread_tidak_diketahui_bantalan_8(self):
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            spread=None,
            cfg=CFG_MINIMAL,
        )
        self.assertEqual(hasil["cushion_points"], 8)
        self.assertEqual(hasil["line"], 233.5)

    def test_median_lebih_tinggi_dari_market(self):
        # Median model 230 > market 225,5 -> base 230, required 238.
        percentiles = {"median": 230.0, "p75": 242.0}
        hasil = cushion.utama_line(
            percentiles,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            spread=5.0,
            cfg=CFG_MINIMAL,
        )
        self.assertEqual(hasil["base_line"], 230.0)
        self.assertEqual(hasil["required_line"], 238.0)
        self.assertEqual(hasil["line"], 239.5)

    def test_tidak_ada_garis_memenuhi(self):
        tangga_pendek = [b for b in LADDER_DET_ATL if b["line"] <= 229.5]
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            tangga_pendek,
            spread=5.0,
            cfg=CFG_MINIMAL,
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "tidak_ada_garis_memenuhi")
        self.assertIsNone(hasil["line"])

    def test_data_hilang(self):
        hasil = cushion.utama_line(
            {}, MARKET_LINE_DET_ATL, LADDER_DET_ATL, spread=5.0, cfg=CFG_MINIMAL
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "median_tidak_ada")
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL, None, LADDER_DET_ATL, spread=5.0, cfg=CFG_MINIMAL
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "garis_market_tidak_ada")


class TestTanggaDanValidasi(unittest.TestCase):
    def test_tangga_angka_saja(self):
        hasil = cushion.insurance_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            [233.5, 235.5, 237.5],
            CFG_MINIMAL,
        )
        self.assertTrue(hasil["meets"])
        self.assertEqual(hasil["line"], 235.5)
        self.assertIsNone(hasil["price_cents"])

    def test_tangga_tidak_urut_tetap_dipilih_terkecil(self):
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            [239.5, 233.5, 237.5],
            spread=5.0,
            cfg=CFG_MINIMAL,
        )
        self.assertEqual(hasil["line"], 233.5)

    def test_validasi(self):
        with self.assertRaises(ValueError):
            cushion.insurance_line(
                ["bukan", "dict"], MARKET_LINE_DET_ATL, LADDER_DET_ATL, CFG_MINIMAL
            )
        with self.assertRaises(ValueError):
            cushion.insurance_line(
                PERCENTILES_DET_ATL, "225,5", LADDER_DET_ATL, CFG_MINIMAL
            )
        with self.assertRaises(ValueError):
            cushion.insurance_line(
                PERCENTILES_DET_ATL,
                MARKET_LINE_DET_ATL,
                [{"tanpa_garis": 1}],
                CFG_MINIMAL,
            )
        with self.assertRaises(ValueError):
            cushion.insurance_line(
                {"median": "223", "p75": 235.0},
                MARKET_LINE_DET_ATL,
                LADDER_DET_ATL,
                CFG_MINIMAL,
            )
        with self.assertRaises(ValueError):
            cushion.utama_line(
                PERCENTILES_DET_ATL,
                MARKET_LINE_DET_ATL,
                LADDER_DET_ATL,
                spread="rapat",
                cfg=CFG_MINIMAL,
            )

    def test_target_probability_tidak_valid(self):
        cfg = {"filters": {"nba_alt_under": {"insurance_target_probability": 1.5}}}
        with self.assertRaises(ValueError):
            cushion.insurance_line(
                PERCENTILES_DET_ATL, MARKET_LINE_DET_ATL, LADDER_DET_ATL, cfg
            )


if __name__ == "__main__":
    unittest.main()
