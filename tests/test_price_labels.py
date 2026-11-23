"""Tes label harga DISKON/WAJAR/MAHAL (keputusan user 2026-11-21).

Ambang dari playstyle.yaml: DISKON EV >= +2%, MAHAL EV < -2%, WAJAR
di antaranya. Tes ini memakai config asli — test_config yang mengunci
angkanya.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from engine import price_labels


class TestLabelForEv(unittest.TestCase):
    def test_batas_diskon(self):
        self.assertEqual(price_labels.label_for_ev(2.0), "DISKON")
        self.assertEqual(price_labels.label_for_ev(2.5), "DISKON")
        self.assertEqual(price_labels.label_for_ev(100.0), "DISKON")

    def test_batas_wajar(self):
        self.assertEqual(price_labels.label_for_ev(1.99), "WAJAR")
        self.assertEqual(price_labels.label_for_ev(0.0), "WAJAR")
        self.assertEqual(price_labels.label_for_ev(-1.99), "WAJAR")
        # Tepat -2% masih WAJAR (MAHAL hanya EV < -2%).
        self.assertEqual(price_labels.label_for_ev(-2.0), "WAJAR")

    def test_batas_mahal(self):
        self.assertEqual(price_labels.label_for_ev(-2.01), "MAHAL")
        self.assertEqual(price_labels.label_for_ev(-5.0), "MAHAL")

    def test_ev_tidak_valid_melempar(self):
        for bad in (None, "2", True, float("nan"), float("inf")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                price_labels.label_for_ev(bad)

    def test_ambang_terbalik_melempar(self):
        cfg = {
            "price_labels": {
                "diskon_min_ev_pct": -2.0,
                "mahal_max_ev_pct": 2.0,
            }
        }
        with self.assertRaises(config.ConfigError):
            price_labels.label_for_ev(0.0, cfg)


class TestLabelSharpMoveBukanDiskon(unittest.TestCase):
    """Sharp move BUKAN diskon (keputusan user 2026-11-23, kasus Thunder).

    Bila harga baru bergerak tajam, DISKON polos dilarang: EV yang
    akan berlabel DISKON dikembalikan sebagai DISKON_DITEKAN.
    Definisi EV dan ambang label tidak berubah.
    """

    def test_sharp_move_menekan_diskon(self):
        # EV +5,63% (pola Thunder: p_final 0,75 di harga 71¢).
        self.assertEqual(
            price_labels.label_for_ev(5.63, sharp_move=True), "DISKON_DITEKAN"
        )
        # Tepat di ambang DISKON (+2%) juga ditekan.
        self.assertEqual(
            price_labels.label_for_ev(2.0, sharp_move=True), "DISKON_DITEKAN"
        )

    def test_sharp_move_tidak_mengubah_wajar_mahal(self):
        self.assertEqual(price_labels.label_for_ev(0.0, sharp_move=True), "WAJAR")
        self.assertEqual(price_labels.label_for_ev(1.99, sharp_move=True), "WAJAR")
        self.assertEqual(price_labels.label_for_ev(-2.0, sharp_move=True), "WAJAR")
        self.assertEqual(price_labels.label_for_ev(-5.0, sharp_move=True), "MAHAL")

    def test_tanpa_sharp_move_tetap_diskon(self):
        # Kompatibel mundur: pemanggil lama tanpa parameter tidak
        # berubah perilakunya.
        self.assertEqual(price_labels.label_for_ev(5.63), "DISKON")
        self.assertEqual(price_labels.label_for_ev(5.63, sharp_move=False), "DISKON")
        self.assertEqual(price_labels.label_for_ev(2.0), "DISKON")

    def test_konstanta_diskon_ditekan(self):
        self.assertEqual(price_labels.DISKON_DITEKAN, "DISKON_DITEKAN")


if __name__ == "__main__":
    unittest.main()
