"""Tes Vegas sanity check (engine/vegas.py, v18).

Fungsi sesuaikan_median dipakai worker C di nba_analysis.py
(wiring) — signature + perilaku di sini DIKUNCI: median disusutkan
setengah jarak ke pasar bila |median - pasar| > 5,0 poin tanpa
sebab cedera baru terverifikasi. Angka-angka dihitung tangan
(median 220, pasar 228,5 -> median baru 224,25, geser +4,25).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import config as config_mod
from engine import vegas as vegas_mod

ROOT = Path(__file__).resolve().parents[1]
ARTEFAK_LIVE = ROOT / "out" / "analysis_live_2026-11-22.json"
ARTEFAK_VERIF = ROOT / "out" / "analysis_verif_tahap4_2026-11-22.json"

CFG_V18 = {
    "calibration": {
        "lean_to_market_gap": 5.0,
        "shrinkage": {"mode": "setengah_jarak", "fraction": 0.5},
    }
}


class TestSesuaikanMedian(unittest.TestCase):
    """Hitung tangan + batas ambang + pengecualian cedera."""

    def test_hitung_tangan_setengah_jarak(self):
        # Median 220, pasar 228,5: gap 8,5 > 5,0 -> susut setengah
        # jarak: 220 + 0,5 x 8,5 = 224,25; geser +4,25.
        hasil = vegas_mod.sesuaikan_median(220, 228.5, False, cfg=CFG_V18)
        self.assertTrue(hasil["diterapkan"])
        self.assertAlmostEqual(hasil["median_baru"], 224.25)
        self.assertAlmostEqual(hasil["geser"], 4.25)
        self.assertIn("setengah jarak", hasil["alasan"])

    def test_hitung_tangan_turun(self):
        # Median di ATAS pasar: 230 vs 220 -> 230 + 0,5 x (-10) = 225.
        hasil = vegas_mod.sesuaikan_median(230, 220, False, cfg=CFG_V18)
        self.assertTrue(hasil["diterapkan"])
        self.assertAlmostEqual(hasil["median_baru"], 225.0)
        self.assertAlmostEqual(hasil["geser"], -5.0)

    def test_gap_tepat_ambang_tidak_disusutkan(self):
        # Aturan: susut hanya bila gap > ambang (bukan >=).
        hasil = vegas_mod.sesuaikan_median(220, 225, False, cfg=CFG_V18)
        self.assertFalse(hasil["diterapkan"])
        self.assertAlmostEqual(hasil["median_baru"], 220.0)
        self.assertAlmostEqual(hasil["geser"], 0.0)

    def test_gap_sedikit_di_atas_ambang_disusutkan(self):
        hasil = vegas_mod.sesuaikan_median(220, 225.1, False, cfg=CFG_V18)
        self.assertTrue(hasil["diterapkan"])
        self.assertAlmostEqual(hasil["median_baru"], 222.55)
        self.assertAlmostEqual(hasil["geser"], 2.55)

    def test_sebab_cedera_baru_membatalkan(self):
        # Gap besar + sebab cedera terverifikasi -> median dipertahankan.
        hasil = vegas_mod.sesuaikan_median(220, 228.5, True, cfg=CFG_V18)
        self.assertFalse(hasil["diterapkan"])
        self.assertAlmostEqual(hasil["median_baru"], 220.0)
        self.assertIn("cedera", hasil["alasan"])

    def test_gap_kecil_tidak_disusutkan(self):
        hasil = vegas_mod.sesuaikan_median(220, 223, False, cfg=CFG_V18)
        self.assertFalse(hasil["diterapkan"])
        self.assertAlmostEqual(hasil["median_baru"], 220.0)


class TestSesuaikanMedianConfig(unittest.TestCase):
    """Fraction / ambang dari config + default + config rusak."""

    def test_fraction_dari_config(self):
        cfg = {
            "calibration": {
                "lean_to_market_gap": 5.0,
                "shrinkage": {"mode": "setengah_jarak", "fraction": 0.25},
            }
        }
        hasil = vegas_mod.sesuaikan_median(220, 228.5, False, cfg=cfg)
        self.assertAlmostEqual(hasil["median_baru"], 222.125)
        self.assertAlmostEqual(hasil["geser"], 2.125)

    def test_ambang_gap_dari_config(self):
        cfg = {
            "calibration": {
                "lean_to_market_gap": 10.0,
                "shrinkage": {"mode": "setengah_jarak", "fraction": 0.5},
            }
        }
        hasil = vegas_mod.sesuaikan_median(220, 228.5, False, cfg=cfg)
        self.assertFalse(hasil["diterapkan"])

    def test_kunci_hilang_pakai_default_v18(self):
        # Config kosong -> default gap 5,0 + fraction 0,5 (pola
        # integrasi paralel v18; nilai default = nilai config v18).
        hasil = vegas_mod.sesuaikan_median(220, 228.5, False, cfg={})
        self.assertTrue(hasil["diterapkan"])
        self.assertAlmostEqual(hasil["median_baru"], 224.25)

    def test_fraction_di_luar_0_1_config_error(self):
        cfg = {
            "calibration": {
                "lean_to_market_gap": 5.0,
                "shrinkage": {"mode": "setengah_jarak", "fraction": 1.5},
            }
        }
        with self.assertRaises(config_mod.ConfigError):
            vegas_mod.sesuaikan_median(220, 228.5, False, cfg=cfg)

    def test_fraction_bukan_angka_config_error(self):
        cfg = {
            "calibration": {
                "lean_to_market_gap": 5.0,
                "shrinkage": {"mode": "setengah_jarak", "fraction": "setengah"},
            }
        }
        with self.assertRaises(config_mod.ConfigError):
            vegas_mod.sesuaikan_median(220, 228.5, False, cfg=cfg)

    def test_mode_tidak_dikenal_config_error(self):
        cfg = {
            "calibration": {
                "lean_to_market_gap": 5.0,
                "shrinkage": {"mode": "penuh_ke_pasar", "fraction": 0.5},
            }
        }
        with self.assertRaises(config_mod.ConfigError):
            vegas_mod.sesuaikan_median(220, 228.5, False, cfg=cfg)

    def test_ambang_gap_negatif_config_error(self):
        cfg = {
            "calibration": {
                "lean_to_market_gap": -1.0,
                "shrinkage": {"mode": "setengah_jarak", "fraction": 0.5},
            }
        }
        with self.assertRaises(config_mod.ConfigError):
            vegas_mod.sesuaikan_median(220, 228.5, False, cfg=cfg)


class TestSesuaikanMedianInputTidakValid(unittest.TestCase):
    """Median/pasar bukan angka -> ValueError (bukan diam-diam 0)."""

    def test_median_bukan_angka(self):
        with self.assertRaises(ValueError):
            vegas_mod.sesuaikan_median("dua ratus", 228.5, False, cfg=CFG_V18)

    def test_pasar_none(self):
        with self.assertRaises(ValueError):
            vegas_mod.sesuaikan_median(220, None, False, cfg=CFG_V18)

    def test_median_bool(self):
        with self.assertRaises(ValueError):
            vegas_mod.sesuaikan_median(True, 228.5, False, cfg=CFG_V18)


class TestVegasKonterfaktualArtefak(unittest.TestCase):
    """Konterfaktual di slate uji tersimpan (10 baris, 2 file).

    Diukur 2026-11-23 (lihat LAPORAN-GATE-V18.md): 6 dari 10 median
    bergeser (semua ke ATAS — median model selalu di bawah pasar di
    slate ini). Tes ini mengunci hitungan itu; bila artefak berubah,
    angka ini harus diukur ulang, bukan disesuaikan diam-diam.
    """

    @classmethod
    def setUpClass(cls):
        if not ARTEFAK_LIVE.exists() or not ARTEFAK_VERIF.exists():
            raise unittest.SkipTest("artefak slate uji tidak ada di out/")
        cls.baris = []
        for jalur in (ARTEFAK_LIVE, ARTEFAK_VERIF):
            dokumen = json.loads(jalur.read_text(encoding="utf-8"))
            for entri in dokumen["matches"]:
                analisis = entri["nba_analysis"]
                median = analisis["simulation"]["score_distribution"]["total"]["median"]
                pasar = analisis["market"]["main_total_line"]
                cls.baris.append((analisis["match_id"], median, pasar))

    def test_enam_dari_sepuluh_median_bergeser(self):
        bergeser = [
            (mid, hasil["geser"])
            for mid, median, pasar in self.baris
            if (hasil := vegas_mod.sesuaikan_median(median, pasar, False, cfg=CFG_V18))[
                "diterapkan"
            ]
        ]
        self.assertEqual(len(self.baris), 10)
        self.assertEqual(len(bergeser), 6)
        # Semua geser ke atas (median < pasar di semua baris yang
        # bergeser) — total geser +28,0 poin.
        self.assertTrue(all(geser > 0 for _, geser in bergeser))
        self.assertAlmostEqual(sum(g for _, g in bergeser), 28.0)

    def test_bos_live_geser_terbesar(self):
        # BOS live: median 198,0 vs pasar 211,5 -> gap 13,5 ->
        # median baru 204,75, geser +6,75 (terbesar di slate).
        hasil = vegas_mod.sesuaikan_median(198.0, 211.5, False, cfg=CFG_V18)
        self.assertTrue(hasil["diterapkan"])
        self.assertAlmostEqual(hasil["median_baru"], 204.75)
        self.assertAlmostEqual(hasil["geser"], 6.75)


if __name__ == "__main__":
    unittest.main()
