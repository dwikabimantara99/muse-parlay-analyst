"""Tes engine/markets.py — peluang dari draws sintetis yang bisa dihitung
tangan. TANPA network, TANPA RNG.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import markets

# 4 draws yang bisa dihitung tangan:
#   (110,100): margin +10, total 210 — kandang menang
#   (105,100): margin +5,  total 205 — kandang menang
#   (100,110): margin -10, total 210 — tandang menang
#   (100,100): margin 0,  total 200 — seri
DRAWS_4 = [(110, 100), (105, 100), (100, 110), (100, 100)]


class TestMoneyline(unittest.TestCase):
    def test_moneyline_dari_draws(self):
        hasil = markets.evaluate_markets(DRAWS_4)
        self.assertAlmostEqual(hasil["moneyline_home"], 0.5)  # 2/4
        self.assertAlmostEqual(hasil["moneyline_away"], 0.25)  # 1/4
        # Seri tidak dihitung di keduanya: jumlah < 1.
        self.assertAlmostEqual(hasil["moneyline_home"] + hasil["moneyline_away"], 0.75)

    def test_tanpa_lines_hanya_moneyline(self):
        hasil = markets.evaluate_markets(DRAWS_4, None)
        self.assertEqual(set(hasil), {"moneyline_home", "moneyline_away"})

    def test_semua_kandang_menang(self):
        hasil = markets.evaluate_markets([(120, 100), (130, 90)])
        self.assertEqual(hasil["moneyline_home"], 1.0)
        self.assertEqual(hasil["moneyline_away"], 0.0)


class TestSpread(unittest.TestCase):
    def test_spread_negatif(self):
        # spread_home_-5.5 = P(margin > 5.5): hanya margin +10 -> 1/4.
        hasil = markets.evaluate_markets(DRAWS_4, {"spreads": [-5.5]})
        self.assertAlmostEqual(hasil["spread_home_-5.5"], 0.25)

    def test_spread_positif(self):
        # spread_home_+5.5 = P(margin > -5.5): +10, +5, 0 -> 3/4.
        hasil = markets.evaluate_markets(DRAWS_4, {"spreads": [5.5]})
        self.assertAlmostEqual(hasil["spread_home_+5.5"], 0.75)

    def test_spread_push_bukan_menang(self):
        # spread_home_-5 = P(margin > 5): margin +5 = push, bukan menang.
        hasil = markets.evaluate_markets(DRAWS_4, {"spreads": [-5]})
        self.assertAlmostEqual(hasil["spread_home_-5"], 0.25)

    def test_format_kunci_spread(self):
        hasil = markets.evaluate_markets(DRAWS_4, {"spreads": [-5.5, 5.5, -2, 0]})
        self.assertIn("spread_home_-5.5", hasil)
        self.assertIn("spread_home_+5.5", hasil)
        self.assertIn("spread_home_-2", hasil)
        self.assertIn("spread_home_+0", hasil)


class TestTotal(unittest.TestCase):
    def test_total_under_over(self):
        # Total: 210, 205, 210, 200. Garis 205.5: under 205+200 -> 2/4,
        # over 210+210 -> 2/4.
        hasil = markets.evaluate_markets(DRAWS_4, {"totals": [205.5]})
        self.assertAlmostEqual(hasil["total_under_205.5"], 0.5)
        self.assertAlmostEqual(hasil["total_over_205.5"], 0.5)

    def test_total_push_bukan_menang(self):
        # Garis 210: total 210 = push di kedua sisi.
        hasil = markets.evaluate_markets(DRAWS_4, {"totals": [210]})
        self.assertAlmostEqual(hasil["total_under_210"], 0.5)  # 205, 200
        self.assertAlmostEqual(hasil["total_over_210"], 0.0)

    def test_format_kunci_total(self):
        hasil = markets.evaluate_markets(DRAWS_4, {"totals": [224.5, 200]})
        self.assertIn("total_under_224.5", hasil)
        self.assertIn("total_over_224.5", hasil)
        self.assertIn("total_under_200", hasil)
        self.assertIn("total_over_200", hasil)


class TestValidasi(unittest.TestCase):
    def test_draws_kosong_ditolak(self):
        with self.assertRaises(ValueError):
            markets.evaluate_markets([])
        with self.assertRaises(ValueError):
            markets.evaluate_markets(None)

    def test_draw_buruk_ditolak(self):
        for buruk in (
            [(110,)],
            [(110, 100, 90)],
            [("110", 100)],
            [(110, float("nan"))],
            [(110, float("inf"))],
            [(True, 100)],
        ):
            with self.subTest(buruk=buruk), self.assertRaises(ValueError):
                markets.evaluate_markets(buruk)

    def test_lines_buruk_ditolak(self):
        with self.assertRaises(ValueError):
            markets.evaluate_markets(DRAWS_4, {"spreads": ["-5.5"]})
        with self.assertRaises(ValueError):
            markets.evaluate_markets(DRAWS_4, {"totals": [float("nan")]})
        with self.assertRaises(ValueError):
            markets.evaluate_markets(DRAWS_4, {"spreads": -5.5})
        with self.assertRaises(ValueError):
            markets.evaluate_markets(DRAWS_4, "spread")

    def test_semua_peluang_0_sampai_1(self):
        hasil = markets.evaluate_markets(
            DRAWS_4, {"spreads": [-5.5, 5.5], "totals": [200, 205.5, 210]}
        )
        for kunci, nilai in hasil.items():
            with self.subTest(kunci=kunci):
                self.assertGreaterEqual(nilai, 0.0)
                self.assertLessEqual(nilai, 1.0)


if __name__ == "__main__":
    unittest.main()
