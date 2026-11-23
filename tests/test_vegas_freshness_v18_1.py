"""Tes Patch #4 v18.1 — filter kesegaran _sebab_cedera_baru.

Pemain OUT hanya dihitung penyebab gap cedera baru bila
games_played musim berjalan >= calibration.fresh_injury_min_gp_season
(3). Pemain GP < 3 (termasuk GP == 0 — absen sejak awal musim,
mis. Haliburton) sudah terserap harga pasar sehingga TIDAK boleh
membatalkan Vegas shrinkage. GP tidak tersedia -> TIDAK segar
(fail-closed ke arah shrinkage berjalan) + dicatat di elemen
keempat kembalian ("dikecualikan").

Kembalian _sebab_cedera_baru v18.1 adalah 4-tuple:
(ada, [nama sebab], dievaluasi, [dikecualikan]) — dikecualikan
adalah list {"player", "games_played", "alasan"}.
"""

from __future__ import annotations

import copy
import unittest

import config as config_mod
from engine import nba_analysis as na

CFG = config_mod.load_playstyle()


def _cfg_minimal():
    return {
        "vonis": {"tunggu_lineup": {"bpm_bintang": 2.0}},
        "calibration": {"fresh_injury_min_gp_season": 3},
    }


def _out(nama, n_sumber=2):
    return {
        "player": nama,
        "status": "OUT",
        "sources": ["A", "B"][:n_sumber],
        "availability_n_sources": n_sumber,
    }


def _pemain(nama, bpm, gp=12):
    return {"player": nama, "bpm": bpm, "games_played": gp}


def _artefak(cedera, pemain):
    return {
        "inputs": {
            "home": {"players": pemain},
            "away": {"players": []},
        },
        "injuries": {"entries": cedera},
    }


class TestFilterKesegaran(unittest.TestCase):
    """GP musim berjalan menentukan segar/tidaknya sebab cedera."""

    def test_haliburton_gp_nol_bukan_sebab(self):
        # Kasus wajib Patch #4: Haliburton (BPM +7,8, OUT 2 sumber)
        # tapi GP 0 -> TIDAK membatalkan shrinkage; tercatat di
        # dikecualikan dengan alasan gp_di_bawah_minimum.
        artefak = _artefak(
            [_out("Tyrese Haliburton", 2)],
            [_pemain("Tyrese Haliburton", 7.8, gp=0)],
        )
        ada, nama, dievaluasi, dikecualikan = na._sebab_cedera_baru(
            artefak, _cfg_minimal()
        )
        self.assertFalse(ada)
        self.assertEqual(nama, [])
        self.assertTrue(dievaluasi)
        self.assertEqual(len(dikecualikan), 1)
        self.assertEqual(dikecualikan[0]["player"], "Tyrese Haliburton")
        self.assertEqual(dikecualikan[0]["games_played"], 0)
        self.assertEqual(dikecualikan[0]["alasan"], "gp_di_bawah_minimum")

    def test_gp_dua_bukan_sebab(self):
        artefak = _artefak(
            [_out("Bintang", 2)],
            [_pemain("Bintang", 4.5, gp=2)],
        )
        ada, nama, dievaluasi, dikecualikan = na._sebab_cedera_baru(
            artefak, _cfg_minimal()
        )
        self.assertFalse(ada)
        self.assertEqual(nama, [])
        self.assertTrue(dievaluasi)
        self.assertEqual(dikecualikan[0]["alasan"], "gp_di_bawah_minimum")

    def test_gp_tiga_sebab_batas_inklusif(self):
        # Ambang inklusif (>=): GP tepat 3 tetap sebab.
        artefak = _artefak(
            [_out("Bintang", 2)],
            [_pemain("Bintang", 4.5, gp=3)],
        )
        ada, nama, dievaluasi, dikecualikan = na._sebab_cedera_baru(
            artefak, _cfg_minimal()
        )
        self.assertTrue(ada)
        self.assertEqual(nama, ["Bintang"])
        self.assertTrue(dievaluasi)
        self.assertEqual(dikecualikan, [])

    def test_gp_besar_baru_out_tetap_sebab(self):
        # Pemain GP >= 3 yang baru OUT tetap memicu (kasus wajib).
        artefak = _artefak(
            [_out("Bintang", 2)],
            [_pemain("Bintang", 4.5, gp=14)],
        )
        ada, nama, _, dikecualikan = na._sebab_cedera_baru(artefak, _cfg_minimal())
        self.assertTrue(ada)
        self.assertEqual(nama, ["Bintang"])
        self.assertEqual(dikecualikan, [])

    def test_gp_tidak_tersedia_bukan_sebab_fail_closed(self):
        # GP tidak ada di inputs -> TIDAK segar (shrinkage berjalan)
        # + dicatat dengan alasan gp_tidak_tersedia.
        artefak = _artefak(
            [_out("Bintang", 2)],
            [{"player": "Bintang", "bpm": 4.5}],
        )
        ada, nama, dievaluasi, dikecualikan = na._sebab_cedera_baru(
            artefak, _cfg_minimal()
        )
        self.assertFalse(ada)
        self.assertEqual(nama, [])
        self.assertTrue(dievaluasi)
        self.assertEqual(len(dikecualikan), 1)
        self.assertIsNone(dikecualikan[0]["games_played"])
        self.assertEqual(dikecualikan[0]["alasan"], "gp_tidak_tersedia")

    def test_gp_bukan_angka_bukan_sebab(self):
        artefak = _artefak(
            [_out("Bintang", 2)],
            [_pemain("Bintang", 4.5, gp="rusak")],
        )
        ada, _, _, dikecualikan = na._sebab_cedera_baru(artefak, _cfg_minimal())
        self.assertFalse(ada)
        self.assertEqual(dikecualikan[0]["alasan"], "gp_tidak_tersedia")

    def test_bukan_bintang_gp_besar_tetap_bukan_sebab(self):
        # Filter GP tidak mengubah gerbang BPM: pemain bangku
        # (BPM < 2,0) dengan GP besar tetap bukan sebab — dan TIDAK
        # masuk dikecualikan (bukan kandidat sebab sejak awal).
        artefak = _artefak(
            [_out("Bangku", 2)],
            [_pemain("Bangku", 0.5, gp=15)],
        )
        ada, nama, dievaluasi, dikecualikan = na._sebab_cedera_baru(
            artefak, _cfg_minimal()
        )
        self.assertFalse(ada)
        self.assertEqual(nama, [])
        self.assertTrue(dievaluasi)
        self.assertEqual(dikecualikan, [])

    def test_satu_segar_satu_tidak(self):
        # Dua bintang OUT: satu GP 10 (sebab), satu GP 0
        # (dikecualikan) -> ada=True hanya dengan yang segar.
        artefak = _artefak(
            [_out("Segar", 2), _out("Lama", 2)],
            [_pemain("Segar", 3.0, gp=10), _pemain("Lama", 6.0, gp=0)],
        )
        ada, nama, _, dikecualikan = na._sebab_cedera_baru(artefak, _cfg_minimal())
        self.assertTrue(ada)
        self.assertEqual(nama, ["Segar"])
        self.assertEqual([d["player"] for d in dikecualikan], ["Lama"])

    def test_ambang_gp_dari_config(self):
        # Ambang dibaca dari config, bukan hardcode: dengan ambang
        # 5, pemain GP 4 bukan sebab.
        cfg = _cfg_minimal()
        cfg["calibration"]["fresh_injury_min_gp_season"] = 5
        artefak = _artefak(
            [_out("Bintang", 2)],
            [_pemain("Bintang", 4.5, gp=4)],
        )
        ada, _, _, _ = na._sebab_cedera_baru(artefak, cfg)
        self.assertFalse(ada)

    def test_kunci_gp_hilang_tidak_dievaluasi(self):
        # Config tanpa kunci ambang -> tidak dievaluasi (konsisten
        # dengan penanganan ambang BPM hilang): shrinkage berjalan
        # tanpa pengecualian cedera.
        cfg = {"vonis": {"tunggu_lineup": {"bpm_bintang": 2.0}}}
        artefak = _artefak(
            [_out("Bintang", 2)],
            [_pemain("Bintang", 4.5, gp=12)],
        )
        ada, nama, dievaluasi, dikecualikan = na._sebab_cedera_baru(artefak, cfg)
        self.assertFalse(ada)
        self.assertEqual(nama, [])
        self.assertFalse(dievaluasi)
        self.assertEqual(dikecualikan, [])

    def test_config_lengkap_kunci_hadir(self):
        self.assertEqual(CFG["calibration"]["fresh_injury_min_gp_season"], 3)


class TestTerapanVegasMencatatDikecualikan(unittest.TestCase):
    """_terapkan_vegas meneruskan daftar dikecualikan ke vegas_info."""

    def test_info_memuat_dikecualikan_gp(self):
        cfg = copy.deepcopy(CFG)
        artefak = _artefak(
            [_out("Tyrese Haliburton", 2)],
            [_pemain("Tyrese Haliburton", 7.8, gp=0)],
        )
        info, _catatan = na._terapkan_vegas(220.0, 228.5, cfg, artefak)
        self.assertIsNotNone(info)
        sebab = info["sebab_cedera_baru"]
        self.assertFalse(sebab["ada"])
        self.assertEqual(sebab["pemain"], [])
        self.assertTrue(sebab["dievaluasi"])
        dikecualikan = sebab["dikecualikan_gp"]
        self.assertEqual(len(dikecualikan), 1)
        self.assertEqual(dikecualikan[0]["player"], "Tyrese Haliburton")
        # Haliburton tidak membatalkan -> shrinkage TETAP berjalan
        # (gap 8,5 > 5,0): median 220 -> 224,25.
        self.assertTrue(info["diterapkan"])
        self.assertAlmostEqual(info["median_baru"], 224.25)


if __name__ == "__main__":
    unittest.main()
