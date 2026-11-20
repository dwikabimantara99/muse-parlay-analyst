"""Tes engine/devig.py — konversi odds Amerika + devig (murni).

Rumus Blueprint §5c: p_no-vig(A) = (1/odds_A) / Σ(1/odds_i).
TANPA network.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import devig


class TestAmericanToDecimal(unittest.TestCase):
    def test_positif(self):
        self.assertAlmostEqual(devig.american_to_decimal(150), 2.5)
        self.assertAlmostEqual(devig.american_to_decimal(100), 2.0)
        self.assertAlmostEqual(devig.american_to_decimal(200), 3.0)

    def test_negatif(self):
        self.assertAlmostEqual(devig.american_to_decimal(-110), 1.0 + 100 / 110)
        self.assertAlmostEqual(devig.american_to_decimal(-200), 1.5)
        self.assertAlmostEqual(devig.american_to_decimal(-100), 2.0)

    def test_tidak_valid(self):
        for bad in (0, 50, -50, 99, -99, "abc", None, True, float("inf"), float("nan")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                devig.american_to_decimal(bad)


class TestDevig(unittest.TestCase):
    def test_dua_outcome_seimbang(self):
        result = devig.devig([2.0, 2.0])
        self.assertAlmostEqual(result[0], 0.5)
        self.assertAlmostEqual(result[1], 0.5)

    def test_dua_outcome_contoh_5c(self):
        # odds 1.5 dan 2.75: implisit 2/3 dan 4/11, total 34/33.
        result = devig.devig([1.5, 2.75])
        self.assertAlmostEqual(result[0], 11 / 17)
        self.assertAlmostEqual(result[1], 6 / 17)
        self.assertAlmostEqual(sum(result), 1.0)

    def test_tiga_outcome(self):
        result = devig.devig([2.0, 3.0, 6.0])
        self.assertAlmostEqual(result[0], 0.5)
        self.assertAlmostEqual(result[1], 1 / 3)
        self.assertAlmostEqual(result[2], 1 / 6)

    def test_odds_amerika(self):
        result = devig.devig([-110, -110], odds_format="american")
        self.assertAlmostEqual(result[0], 0.5)
        self.assertAlmostEqual(result[1], 0.5)

    def test_odds_amerika_campuran(self):
        # -150 -> 5/3 (implisit 0.6); +130 -> 2.3 (implisit 10/23).
        result = devig.devig([-150, 130], odds_format="american")
        self.assertAlmostEqual(result[0], 69 / 119)
        self.assertAlmostEqual(result[1], 50 / 119)
        self.assertAlmostEqual(sum(result), 1.0)

    def test_urutan_dipertahankan(self):
        result = devig.devig([1.25, 4.0, 9.0])
        self.assertGreater(result[0], result[1])
        self.assertGreater(result[1], result[2])
        self.assertAlmostEqual(sum(result), 1.0)

    def test_validasi(self):
        with self.assertRaises(ValueError):
            devig.devig([])
        with self.assertRaises(ValueError):
            devig.devig(None)
        with self.assertRaises(ValueError):
            devig.devig("2.0")
        for bad in ([1.0], [0.5], [0], [-2.0], [2.0, 0], [True], [float("nan")]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                devig.devig(bad)
        with self.assertRaises(ValueError):
            devig.devig([2.0, 2.0], odds_format="pecahan")
        with self.assertRaises(ValueError):
            devig.devig([-110, 50], odds_format="american")


class TestBlendMasihStub(unittest.TestCase):
    def test_blend_melempar_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            devig.blend()


if __name__ == "__main__":
    unittest.main()
