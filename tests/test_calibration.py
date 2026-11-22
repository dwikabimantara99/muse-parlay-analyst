"""Tes engine/calibration.py (Tahap 3 Langkah 6).

Fixture sintetis yang didokumentasikan: w optimal diketahui dari
konstruksi (p_model sempurna -> w=1,0; p_market sempurna -> w=0,0;
konstruksi simetris -> w=0,5). TANPA network. Satu tes memakai
cfg=None untuk membuktikan kunci baru di playstyle.yaml terbaca.
"""

import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine import calibration

REPO_ROOT = Path(__file__).resolve().parent.parent
PLAYSTYLE = REPO_ROOT / "config" / "playstyle.yaml"

CFG = {"blend": {"w_model": 0.3}, "calibration": {"min_legs_w": 50}}


def _kaki(i, p_model, p_market, result, settled=True, **overrides):
    """Satu record hasil bentuk engine/learning.py (pekerja A)."""
    if p_model is not None and p_market is not None:
        p_final = 0.3 * p_model + 0.7 * p_market
    else:
        p_final = p_model
    kaki = {
        "leg_id": f"LEG-{i:03d}",
        "ticket_id": "TIKET-1",
        "sport": "nba",
        "market": "total_under",
        "selection": "Under 225.5",
        "p_model": p_model,
        "p_market": p_market,
        "p_final": p_final,
        "price_buy_cents": 70,
        "price_close_cents": 72,
        "ev_pct": 0.0,
        "result": result,
        "settled": settled,
        "sumber": "fixture",
    }
    kaki.update(overrides)
    return kaki


def _hash_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class TestRekomendasiW(unittest.TestCase):
    def test_model_sempurna_w_rekomendasi_1(self):
        # p_model = 1 bila menang, 0 bila kalah (Brier 0); p_market = 0,5
        # terus (Brier 0,25). Blend terbaik: w=1,0 murni model.
        # Brier blend w=0,3: (1-0,65)^2 = (0-0,35)^2 = 0,1225.
        outcomes = [
            _kaki(i, 1.0 if i % 2 == 0 else 0.0, 0.5, i % 2 == 0) for i in range(50)
        ]
        hasil = calibration.rekomendasi_w(outcomes, cfg=copy.deepcopy(CFG))
        self.assertEqual(hasil["n"], 50)
        self.assertTrue(hasil["cukup_data"])
        self.assertEqual(hasil["w_saat_ini"], 0.3)
        self.assertEqual(hasil["w_rekomendasi"], 1.0)
        self.assertAlmostEqual(hasil["brier_model"], 0.0)
        self.assertAlmostEqual(hasil["brier_market"], 0.25)
        self.assertAlmostEqual(hasil["brier_blend_w_saat_ini"], 0.1225)
        self.assertAlmostEqual(hasil["brier_blend_w_rekomendasi"], 0.0)
        self.assertFalse(hasil["diterapkan"])
        self.assertTrue(hasil["butuh_persetujuan_user"])

    def test_market_sempurna_w_rekomendasi_0(self):
        # Kebalikan: p_market sempurna, p_model = 0,5 terus.
        outcomes = [
            _kaki(i, 0.5, 1.0 if i % 2 == 0 else 0.0, i % 2 == 0) for i in range(50)
        ]
        hasil = calibration.rekomendasi_w(outcomes, cfg=copy.deepcopy(CFG))
        self.assertEqual(hasil["w_rekomendasi"], 0.0)
        self.assertAlmostEqual(hasil["brier_model"], 0.25)
        self.assertAlmostEqual(hasil["brier_market"], 0.0)
        self.assertAlmostEqual(hasil["brier_blend_w_rekomendasi"], 0.0)
        self.assertTrue(hasil["cukup_data"])

    def test_sampel_kecil_tidak_cukup(self):
        # 10 kaki model sempurna: Brier tetap dihitung, tapi TIDAK ada
        # rekomendasi — sampel di bawah ambang 50.
        outcomes = [
            _kaki(i, 1.0 if i % 2 == 0 else 0.0, 0.5, i % 2 == 0) for i in range(10)
        ]
        hasil = calibration.rekomendasi_w(outcomes, cfg=copy.deepcopy(CFG))
        self.assertEqual(hasil["n"], 10)
        self.assertFalse(hasil["cukup_data"])
        self.assertIsNone(hasil["w_rekomendasi"])
        self.assertIsNone(hasil["brier_blend_w_rekomendasi"])
        self.assertAlmostEqual(hasil["brier_model"], 0.0)
        self.assertEqual(hasil["alasan"], "sampel belum cukup (n=10, butuh >=50)")
        self.assertFalse(hasil["diterapkan"])
        self.assertTrue(hasil["butuh_persetujuan_user"])

    def test_ambang_49_vs_50(self):
        # n=49 belum cukup; n=50 cukup (ambang inklusif).
        dasar = [
            _kaki(i, 1.0 if i % 2 == 0 else 0.0, 0.5, i % 2 == 0) for i in range(50)
        ]
        self.assertFalse(
            calibration.rekomendasi_w(dasar[:49], cfg=copy.deepcopy(CFG))["cukup_data"]
        )
        self.assertTrue(
            calibration.rekomendasi_w(dasar, cfg=copy.deepcopy(CFG))["cukup_data"]
        )

    def test_kaki_tanpa_p_market_diabaikan(self):
        # 50 kaki terpakai + 10 MODEL_ONLY (p_market None) + 5 belum
        # settled + 3 settled tapi result None -> n tetap 50.
        outcomes = [
            _kaki(i, 1.0 if i % 2 == 0 else 0.0, 0.5, i % 2 == 0) for i in range(50)
        ]
        outcomes += [_kaki(100 + i, 0.9, None, True) for i in range(10)]
        outcomes += [_kaki(200 + i, 0.9, 0.9, None, settled=False) for i in range(5)]
        outcomes += [_kaki(300 + i, 0.9, 0.9, None) for i in range(3)]
        hasil = calibration.rekomendasi_w(outcomes, cfg=copy.deepcopy(CFG))
        self.assertEqual(hasil["n"], 50)
        self.assertEqual(hasil["w_rekomendasi"], 1.0)

    def test_w_optimal_sama_dengan_w_saat_ini(self):
        # Konstruksi simetris: separuh kaki model sempurna/pasar 0,5,
        # separuh pasar sempurna/model 0,5, semua menang. Brier blend
        # f(w) = ((0,5-0,5w)^2 + (0,5w)^2)/2, minimum di w=0,5
        # (f=0,0625; di 0,45 dan 0,55 f=0,063125). Dengan w saat ini
        # 0,5 -> tidak ada perubahan yang diusulkan.
        outcomes = [_kaki(i, 1.0, 0.5, True) for i in range(25)]
        outcomes += [_kaki(25 + i, 0.5, 1.0, True) for i in range(25)]
        cfg = {"blend": {"w_model": 0.5}, "calibration": {"min_legs_w": 50}}
        hasil = calibration.rekomendasi_w(outcomes, cfg=cfg)
        self.assertEqual(hasil["w_rekomendasi"], 0.5)
        self.assertAlmostEqual(hasil["brier_blend_w_rekomendasi"], 0.0625)
        self.assertIn("tidak ada perubahan yang diusulkan", hasil["alasan"])

    def test_tanpa_data(self):
        hasil = calibration.rekomendasi_w([], cfg=copy.deepcopy(CFG))
        self.assertEqual(hasil["n"], 0)
        self.assertFalse(hasil["cukup_data"])
        self.assertIsNone(hasil["w_rekomendasi"])
        self.assertIsNone(hasil["brier_model"])
        self.assertIsNone(hasil["brier_market"])
        self.assertIsNone(hasil["brier_blend_w_saat_ini"])
        self.assertIsNone(hasil["brier_blend_w_rekomendasi"])
        self.assertEqual(hasil["alasan"], "sampel belum cukup (n=0, butuh >=50)")

    def test_peluang_tidak_valid_ditolak(self):
        outcomes = [_kaki(i, 0.9, 0.9, True) for i in range(49)]
        outcomes.append(_kaki(49, 1.5, 0.9, True))
        with self.assertRaises(ValueError):
            calibration.rekomendasi_w(outcomes, cfg=copy.deepcopy(CFG))

    def test_tidak_mengubah_file_atau_cfg(self):
        # Rekomendasi TIDAK diterapkan: playstyle.yaml + modul engine
        # tidak berubah, dan dict cfg yang dilewatkan tidak dimutasi.
        sebelum = {
            p: _hash_file(p)
            for p in (
                PLAYSTYLE,
                REPO_ROOT / "engine" / "calibration.py",
                REPO_ROOT / "engine" / "proposals.py",
            )
        }
        cfg = copy.deepcopy(CFG)
        cfg_sebelum = copy.deepcopy(cfg)
        outcomes = [
            _kaki(i, 1.0 if i % 2 == 0 else 0.0, 0.5, i % 2 == 0) for i in range(50)
        ]
        calibration.rekomendasi_w(outcomes, cfg=cfg)
        calibration.rekomendasi_w(outcomes, cfg=None)
        for path, hash_sebelum in sebelum.items():
            self.assertEqual(_hash_file(path), hash_sebelum, path)
        self.assertEqual(cfg, cfg_sebelum)
        # w di file tetap 0,3 — tidak berubah jadi 1,0.
        self.assertEqual(
            config_mod.get_value(config_mod.load_playstyle(), "blend", "w_model"),
            0.3,
        )

    def test_cfg_none_memakai_playstyle_asli(self):
        # Kunci baru calibration.min_legs_w (50) terbaca dari file asli.
        outcomes = [
            _kaki(i, 1.0 if i % 2 == 0 else 0.0, 0.5, i % 2 == 0) for i in range(50)
        ]
        hasil = calibration.rekomendasi_w(outcomes, cfg=None)
        self.assertEqual(hasil["w_saat_ini"], 0.3)
        self.assertEqual(hasil["w_rekomendasi"], 1.0)
        self.assertTrue(hasil["cukup_data"])


if __name__ == "__main__":
    unittest.main()
