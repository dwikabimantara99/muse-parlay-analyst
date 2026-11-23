"""Tes OT empiris v18 (engine/ot_empiris.py).

Rumus: p_ot(spread) = base_rate_ot x exp(-spread^2 / (2 x sigma_margin^2)),
sigma_margin = 14,4307 (FIT dari 2.701 laga, config
simulation.sigma_margin), base_rate_ot = 0,0575 (PRIOR terdokumentasi,
bukan fit — leaguegamefinder tidak membawa flag OT; lihat docstring
engine/ot_empiris.py). Hard-skip bila p_ot >= 0,085 INITIAL.

KEJUJURAN (didokumentasikan di modul + laporan): di bawah rumus ini
hard-skip 0,085 TIDAK TERCAPAI — p_ot maksimum (spread 0) = 0,0575
< 0,085. Gerbang dormant sampai kalibrasi ledger memberi laju OT
per kelompok spread atau ambang diturunkan atas persetujuan user.
Tes test_hard_skip_dormant mengunci fakta ini supaya tidak ada yang
mengira gerbang ini aktif.

Kasus wajib: DET@ATL (spread 2,0) TIDAK hard-skip.
"""

from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path

import config
from engine import ot_empiris

CFG = config.load_playstyle()
ROOT = Path(__file__).resolve().parent.parent
ARTEFAK_LIVE = ROOT / "out" / "analysis_live_2026-11-22.json"

# Nilai hasil hitung tangan (python3 -c, 2026-11-23):
#   p(0)   = 0,0575
#   p(2,0) = 0,0575 x exp(-4 / (2 x 14,4307^2)) = 0,056950409501032494
#   p(2,5) = 0,05664357653841656
#   p(15)  = 0,033500359045927054
P_SPREAD_0 = 0.0575
P_SPREAD_2 = 0.056950409501032494
P_SPREAD_2_5 = 0.05664357653841656
P_SPREAD_15 = 0.033500359045927054


def _analisis_spread(spread, ot_sim=None):
    """Artefak minimal dengan margin median = spread."""
    distribusi = {"margin": {"median": spread}}
    if ot_sim is not None:
        distribusi["ot_probability"] = ot_sim
    return {
        "format": "nba_analysis",
        "match_id": "TES@TES_2026-11-22",
        "simulation": {"score_distribution": distribusi},
    }


class TestRumus(unittest.TestCase):
    """Rumus p_ot vs hitung tangan + sifat-sifatnya."""

    def test_nilai_beku_hitung_tangan(self):
        self.assertEqual(ot_empiris.probabilitas_ot_empiris(0.0), P_SPREAD_0)
        self.assertEqual(ot_empiris.probabilitas_ot_empiris(2.0), P_SPREAD_2)
        self.assertEqual(ot_empiris.probabilitas_ot_empiris(2.5), P_SPREAD_2_5)
        self.assertEqual(ot_empiris.probabilitas_ot_empiris(15.0), P_SPREAD_15)

    def test_rumus_independen(self):
        # Hitung ulang dari konstanta mentah (bukan lewat fungsi).
        sigma = CFG["simulation"]["nba"]["sigma_margin_points"]
        dasar = CFG["ot_seleksi"]["base_rate_ot"]
        for spread in (0.0, 1.0, 3.5, 8.0, 20.0):
            harapan = dasar * math.exp(-(spread**2) / (2.0 * sigma**2))
            self.assertAlmostEqual(
                ot_empiris.probabilitas_ot_empiris(spread), harapan, places=12
            )

    def test_monoton_turun_dan_terbatas(self):
        sebelumnya = ot_empiris.probabilitas_ot_empiris(0.0)
        self.assertLessEqual(sebelumnya, 1.0)
        for spread in (1.0, 2.0, 5.0, 10.0, 20.0, 50.0):
            nilai = ot_empiris.probabilitas_ot_empiris(spread)
            self.assertLess(nilai, sebelumnya)
            self.assertGreater(nilai, 0.0)
            sebelumnya = nilai

    def test_spread_negatif_sama_dengan_positif(self):
        # Rumus memakai spread^2 — tanda tidak berpengaruh.
        self.assertEqual(
            ot_empiris.probabilitas_ot_empiris(-2.0),
            ot_empiris.probabilitas_ot_empiris(2.0),
        )

    def test_spread_tidak_valid_value_error(self):
        for buruk in (None, float("nan"), float("inf"), float("-inf"), "2,0"):
            with self.subTest(buruk=buruk), self.assertRaises(ValueError):
                ot_empiris.probabilitas_ot_empiris(buruk)

    def test_pace_diterima_tapi_tidak_dipakai_v18(self):
        # pace_tercepat adalah parameter masa depan (belum ada
        # hubungan pace->OT yang terukur) — nilainya tidak boleh
        # mengubah hasil di v18.
        tanpa = ot_empiris.probabilitas_ot_empiris(2.0)
        dengan = ot_empiris.probabilitas_ot_empiris(2.0, pace_tercepat=103.5)
        self.assertEqual(tanpa, dengan)


class TestConfig(unittest.TestCase):
    """Validasi config: mode, laju dasar, ambang hard-skip."""

    def test_mode_bukan_empiris_config_error(self):
        cfg = copy.deepcopy(CFG)
        cfg["ot_seleksi"]["mode"] = "sim"
        with self.assertRaises(config.ConfigError):
            ot_empiris.probabilitas_ot_empiris(2.0, cfg=cfg)
        cfg = copy.deepcopy(CFG)
        del cfg["ot_seleksi"]["mode"]
        with self.assertRaises(config.ConfigError):
            ot_empiris.probabilitas_ot_empiris(2.0, cfg=cfg)

    def test_base_rate_tidak_valid_config_error(self):
        for buruk in (None, 0.0, 1.5, "0,0575"):
            cfg = copy.deepcopy(CFG)
            cfg["ot_seleksi"]["base_rate_ot"] = buruk
            with (
                self.subTest(buruk=buruk),
                self.assertRaises(config.ConfigError),
            ):
                ot_empiris.probabilitas_ot_empiris(2.0, cfg=cfg)

    def test_ambang_hard_skip(self):
        self.assertEqual(ot_empiris.baca_ambang_hard_skip(CFG), 0.085)
        cfg = copy.deepcopy(CFG)
        cfg["ot_seleksi"]["hard_skip_ot_prob"] = 1.5
        with self.assertRaises(config.ConfigError):
            ot_empiris.baca_ambang_hard_skip(cfg)
        cfg = copy.deepcopy(CFG)
        del cfg["ot_seleksi"]["hard_skip_ot_prob"]
        with self.assertRaises(config.ConfigError):
            ot_empiris.baca_ambang_hard_skip(cfg)

    def test_kunci_v17_hilang(self):
        # skip_ot_prob dihapus di v18 — tidak boleh ada lagi.
        self.assertNotIn("skip_ot_prob", CFG["ot_seleksi"])


class TestHardSkipDormant(unittest.TestCase):
    """Hard-skip 0,085 tidak tercapai di bawah rumus v18."""

    def test_p_ot_maks_di_bawah_ambang(self):
        # p_ot maksimum ada di spread 0 (= laju dasar 0,0575).
        self.assertEqual(
            ot_empiris.probabilitas_ot_empiris(0.0),
            CFG["ot_seleksi"]["base_rate_ot"],
        )
        self.assertLess(
            ot_empiris.probabilitas_ot_empiris(0.0),
            CFG["ot_seleksi"]["hard_skip_ot_prob"],
        )

    def test_pickem_tidak_hard_skip(self):
        hasil = ot_empiris.evaluasi_ot(_analisis_spread(0.0), CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertFalse(hasil["hard_skip"])
        self.assertEqual(hasil["p_ot_empiris"], P_SPREAD_0)

    def test_ambang_diturunkan_bisa_hard_skip(self):
        # Jalur hard-skip tetap teruji: dengan ambang 0,05 (cfg tes),
        # spread 0 (0,0575) kena hard-skip, spread 15 (0,0335) tidak.
        cfg = copy.deepcopy(CFG)
        cfg["ot_seleksi"]["hard_skip_ot_prob"] = 0.05
        hasil = ot_empiris.evaluasi_ot(_analisis_spread(0.0), cfg)
        self.assertTrue(hasil["hard_skip"])
        hasil = ot_empiris.evaluasi_ot(_analisis_spread(15.0), cfg)
        self.assertFalse(hasil["hard_skip"])


class TestEvaluasiOt(unittest.TestCase):
    """evaluasi_ot: baca spread, fallback, tidak-dievaluasi."""

    def test_baca_spread_median_lebih_dulu(self):
        self.assertEqual(ot_empiris.baca_spread(_analisis_spread(2.0)), 2.0)
        analisis = _analisis_spread(-3.0)
        self.assertEqual(ot_empiris.baca_spread(analisis), 3.0)

    def test_baca_spread_fallback_mean(self):
        analisis = {"simulation": {"score_distribution": {"margin": {"mean": 4.0}}}}
        self.assertEqual(ot_empiris.baca_spread(analisis), 4.0)

    def test_baca_spread_tidak_ada(self):
        self.assertIsNone(ot_empiris.baca_spread({}))
        self.assertIsNone(
            ot_empiris.baca_spread(
                {"simulation": {"score_distribution": {"total": {"median": 230.0}}}}
            )
        )

    def test_tanpa_spread_tidak_dievaluasi(self):
        hasil = ot_empiris.evaluasi_ot({"simulation": {}}, CFG)
        self.assertFalse(hasil["dievaluasi"])
        self.assertIsNone(hasil["p_ot_empiris"])
        self.assertIsNone(hasil["spread_points"])
        self.assertFalse(hasil["hard_skip"])

    def test_ot_sim_dicatat_sebagai_info(self):
        hasil = ot_empiris.evaluasi_ot(_analisis_spread(2.0, ot_sim=0.0289), CFG)
        self.assertEqual(hasil["p_ot_sim"], 0.0289)
        self.assertEqual(hasil["p_ot_empiris"], P_SPREAD_2)
        # Keputusan memakai empiris, bukan sim: sim 0,0289 di bawah
        # ambang lama 0,028 pun tidak relevan lagi.
        self.assertFalse(hasil["hard_skip"])


@unittest.skipUnless(
    ARTEFAK_LIVE.exists(),
    "artefak out/analysis_live_2026-11-22.json tidak ada (runtime)",
)
class TestArtefakNyata(unittest.TestCase):
    """Kasus wajib di artefak nyata 22 Nov."""

    @classmethod
    def setUpClass(cls):
        data = json.loads(ARTEFAK_LIVE.read_text(encoding="utf-8"))
        cls.live = {
            (m.get("nba_analysis") or {}).get("match_id"): m.get("nba_analysis") or {}
            for m in data.get("matches") or []
        }

    def test_det_tidak_hard_skip(self):
        # KASUS WAJIB v18: DET@ATL (spread 2,0) TIDAK hard-skip.
        # Di v17, ot_prob sim DET 2,89% >= 2,8% memicu hard-skip;
        # di v18, p_ot empiris(2,0) = 0,0570 < 0,085.
        analisis = self.live["DET@ATL_2026-11-22"]
        self.assertEqual(ot_empiris.baca_spread(analisis), 2.0)
        hasil = ot_empiris.evaluasi_ot(analisis, CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertFalse(hasil["hard_skip"])
        self.assertEqual(hasil["p_ot_empiris"], P_SPREAD_2)

    def test_semua_laga_live_tidak_hard_skip(self):
        # Dengan rumus v18, tidak ada laga live yang hard-skip
        # (gerbang dormant — lihat TestHardSkipDormant).
        for match_id, analisis in self.live.items():
            with self.subTest(match_id=match_id):
                hasil = ot_empiris.evaluasi_ot(analisis, CFG)
                if hasil["dievaluasi"]:
                    self.assertFalse(hasil["hard_skip"])


if __name__ == "__main__":
    unittest.main()
