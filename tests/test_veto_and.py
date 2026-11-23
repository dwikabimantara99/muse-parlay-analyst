"""Tes veto AND v18 (engine/vonis.py::evaluasi_veto).

v18: veto menyala HANYA bila rim protector OUT terkonfirmasi (>= 2
sumber) DAN garis pasar >= 232,0 DAN pace tercepat >= 100,5
(logika AND, config vonis.veto.logic). Ambang INITIAL (keputusan
user 2026-11-23 13:59 WIB — "pake AND yang diusulkan gemini, aku
setuju"); kembali ke OR adalah perubahan satu baris config.

Bila HANYA satu kondisi lingkungan menyala: veto TIDAK menyala,
tapi "peringatan_parsial": true + "kondisi_menyala" tercatat
(worker B memakai ini untuk +3 bantalan).

Kasus wajib (artefak verif 22 Nov):
- DEN@CHI verif MENYALA: Claxton OUT (2 sumber) + garis 236,5 +
  pace 103,22.
- OKC@MIA verif TIDAK menyala: garis 231,5 < 232,0 (pace 102,19
  menyala sendiri -> peringatan parsial).
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import config
from engine import vonis

CFG = config.load_playstyle()
ROOT = Path(__file__).resolve().parent.parent
ARTEFAK_VERIF = ROOT / "out" / "analysis_verif_tahap4_2026-11-22.json"
PEMETAAN = ROOT / "config" / "rim_protector_2026-27.json"

# Pemetaan sintetis (disuntikkan via argumen pemetaan — tidak
# tergantung file JSON): CHI punya Claxton (C), OKC punya Holmgren.
PEMETAAN_SINTETIS = {
    "CHI": [
        {"player": "Nic Claxton", "blk_per_game": 1.0, "pos": "C"},
        {"player": "Jalen Smith", "blk_per_game": 1.1, "pos": "C"},
    ],
    "OKC": [{"player": "Chet Holmgren", "blk_per_game": 3.0, "pos": "PF"}],
    "DEN": [{"player": "Nikola Jokić", "blk_per_game": 1.0, "pos": "C"}],
}


def _analisis(
    match_id="DEN@CHI_2026-11-22",
    garis=236.5,
    pace_tandang=99.0,
    pace_kandang=103.22,
    cedera=None,
):
    """Artefak minimal untuk evaluasi_veto."""
    return {
        "format": "nba_analysis",
        "match_id": match_id,
        "market": {"main_total_line": garis},
        "inputs": {
            "away": {"stats_season": {"pace": pace_tandang}},
            "home": {"stats_season": {"pace": pace_kandang}},
        },
        "injuries": {"entries": cedera or []},
    }


def _out(nama, n_sumber=2):
    return {
        "player": nama,
        "status": "OUT",
        "availability_n_sources": n_sumber,
        "sources": ["Official NBA Injury Report", "ESPN"][:n_sumber],
    }


class TestVetoAndSintetis(unittest.TestCase):
    """Logika AND pada fixture sintetis (pemetaan disuntikkan)."""

    def test_ketiga_kondisi_menyala(self):
        analisis = _analisis(cedera=[_out("Nic Claxton")])
        hasil = vonis.evaluasi_veto(analisis, CFG, PEMETAAN_SINTETIS)
        self.assertTrue(hasil["dievaluasi"])
        self.assertTrue(hasil["menyala"])
        self.assertFalse(hasil["peringatan_parsial"])
        self.assertEqual(hasil["kondisi_menyala"], ["garis", "pace"])
        self.assertEqual([p["player"] for p in hasil["pelindung_out"]], ["Nic Claxton"])
        self.assertEqual(hasil["logic"], "AND")
        self.assertIn("Claxton", hasil["alasan"][0])

    def test_hanya_garis_tidak_menyala_parsial(self):
        analisis = _analisis(
            pace_tandang=99.0, pace_kandang=100.0, cedera=[_out("Nic Claxton")]
        )
        hasil = vonis.evaluasi_veto(analisis, CFG, PEMETAAN_SINTETIS)
        self.assertTrue(hasil["dievaluasi"])
        self.assertFalse(hasil["menyala"])
        self.assertTrue(hasil["peringatan_parsial"])
        self.assertEqual(hasil["kondisi_menyala"], ["garis"])

    def test_hanya_pace_tidak_menyala_parsial(self):
        analisis = _analisis(garis=231.5, cedera=[_out("Nic Claxton")])
        hasil = vonis.evaluasi_veto(analisis, CFG, PEMETAAN_SINTETIS)
        self.assertFalse(hasil["menyala"])
        self.assertTrue(hasil["peringatan_parsial"])
        self.assertEqual(hasil["kondisi_menyala"], ["pace"])

    def test_tanpa_kondisi_tidak_menyala_tanpa_parsial(self):
        analisis = _analisis(
            garis=228.0,
            pace_tandang=99.0,
            pace_kandang=100.0,
            cedera=[_out("Nic Claxton")],
        )
        hasil = vonis.evaluasi_veto(analisis, CFG, PEMETAAN_SINTETIS)
        self.assertFalse(hasil["menyala"])
        self.assertFalse(hasil["peringatan_parsial"])
        self.assertEqual(hasil["kondisi_menyala"], [])

    def test_tanpa_pelindung_out_tidak_menyala(self):
        # Kedua kondisi lingkungan menyala, tapi tidak ada pelindung
        # OUT -> veto tidak menyala (dan bukan parsial: parsial
        # hanya bermakna bila ada pelindung OUT).
        analisis = _analisis(cedera=[])
        hasil = vonis.evaluasi_veto(analisis, CFG, PEMETAAN_SINTETIS)
        self.assertFalse(hasil["menyala"])
        self.assertFalse(hasil["peringatan_parsial"])

    def test_out_satu_sumber_tidak_terkonfirmasi(self):
        analisis = _analisis(cedera=[_out("Nic Claxton", n_sumber=1)])
        hasil = vonis.evaluasi_veto(analisis, CFG, PEMETAAN_SINTETIS)
        self.assertFalse(hasil["menyala"])
        self.assertEqual(hasil["pelindung_out"], [])
        diperiksa = {p["player"]: p["status"] for p in hasil["pelindung_diperiksa"]}
        self.assertEqual(diperiksa["Nic Claxton"], "OUT_belum_terkonfirmasi")

    def test_ambang_batas_inklusif(self):
        # >= : garis tepat 232,0 dan pace tepat 100,5 menyala.
        analisis = _analisis(
            garis=232.0,
            pace_tandang=100.5,
            pace_kandang=99.0,
            cedera=[_out("Nic Claxton")],
        )
        hasil = vonis.evaluasi_veto(analisis, CFG, PEMETAAN_SINTETIS)
        self.assertTrue(hasil["menyala"])
        # Di bawah ambang sedikit: tidak menyala.
        analisis = _analisis(
            garis=231.9,
            pace_tandang=100.5,
            pace_kandang=99.0,
            cedera=[_out("Nic Claxton")],
        )
        hasil = vonis.evaluasi_veto(analisis, CFG, PEMETAAN_SINTETIS)
        self.assertFalse(hasil["menyala"])
        self.assertTrue(hasil["peringatan_parsial"])

    def test_or_reversibel_satu_baris_config(self):
        # Dengan logic "OR" (satu baris config), OKC-sintetis
        # (hanya pace) MENYALA — membuktikan revert ke OR adalah
        # perubahan config, bukan kode.
        cfg_or = copy.deepcopy(CFG)
        cfg_or["vonis"]["veto"]["logic"] = "OR"
        analisis = _analisis(garis=231.5, cedera=[_out("Nic Claxton")])
        hasil = vonis.evaluasi_veto(analisis, cfg_or, PEMETAAN_SINTETIS)
        self.assertTrue(hasil["menyala"])
        self.assertEqual(hasil["logic"], "OR")

    def test_logic_tidak_valid_config_error(self):
        cfg = copy.deepcopy(CFG)
        cfg["vonis"]["veto"]["logic"] = "XOR"
        with self.assertRaises(config.ConfigError):
            vonis.evaluasi_veto(_analisis(), cfg, PEMETAAN_SINTETIS)

    def test_ambang_hilang_config_error(self):
        cfg = copy.deepcopy(CFG)
        del cfg["vonis"]["veto"]["total_tinggi_points"]
        with self.assertRaises(config.ConfigError):
            vonis.evaluasi_veto(_analisis(), cfg, PEMETAAN_SINTETIS)

    def test_tanpa_garis_dan_pace_tidak_dievaluasi(self):
        analisis = _analisis(cedera=[_out("Nic Claxton")])
        analisis["market"] = {}
        analisis["inputs"] = {"away": {}, "home": {}}
        hasil = vonis.evaluasi_veto(analisis, CFG, PEMETAAN_SINTETIS)
        self.assertFalse(hasil["dievaluasi"])
        self.assertFalse(hasil["menyala"])
        self.assertIsNotNone(hasil["alasan_tidak_dievaluasi"])

    def test_tim_tidak_terpetakan_dicatat(self):
        # DET tidak ada di pemetaan sintetis -> dicatat, tapi CHI
        # terpetakan sehingga veto tetap dievaluasi.
        analisis = _analisis(
            match_id="DET@CHI_2026-11-22", cedera=[_out("Nic Claxton")]
        )
        hasil = vonis.evaluasi_veto(analisis, CFG, PEMETAAN_SINTETIS)
        self.assertIn("DET", hasil["tim_tidak_terpetakan"])
        self.assertTrue(hasil["dievaluasi"])
        self.assertTrue(hasil["menyala"])


class TestPemetaanRegenerasi(unittest.TestCase):
    """Pemetaan JSON hasil regenerate v18.1 (filter posisi + fallback)."""

    @classmethod
    def setUpClass(cls):
        cls.dokumen = json.loads(PEMETAAN.read_text(encoding="utf-8"))

    def test_format_dan_aturan(self):
        self.assertEqual(self.dokumen["format"], "rim_protector")
        self.assertEqual(self.dokumen["position_source"], "Basketball-Reference")
        rule = self.dokumen["rule"]
        self.assertEqual(rule["min_mp_per_game"], 18.0)
        self.assertEqual(rule["min_blk_per_game"], 1.0)
        self.assertEqual(rule["min_games"], 3.0)
        self.assertEqual(rule["max_per_team"], 2)
        self.assertEqual(rule["position_filter"], ["C", "PF", "F-C", "C-F"])

    def test_claxton_di_chi_holmgren_di_okc(self):
        chi = [p["player"] for p in self.dokumen["teams"]["CHI"]]
        self.assertIn("Nic Claxton", chi)
        okc = [p["player"] for p in self.dokumen["teams"]["OKC"]]
        self.assertIn("Chet Holmgren", okc)

    def test_guard_tidak_ada(self):
        semua = [
            p["player"] for daftar in self.dokumen["teams"].values() for p in daftar
        ]
        # v18.1: OG Anunoby DIHAPUS dari daftar ini — ia BUKAN guard
        # (BBRef pos PF) dan sah menjadi entri fallback NYK (0,9
        # blok/laga, 34,0 mnt — big terbaik NYK menurut aturan).
        # Keputusan ini menunggu keberatan reviewer (lihat
        # LAPORAN-V18-1-C.md §Keputusan desain): bila fallback
        # dibatasi posisi C saja, NYK akan memakai KAT (0,7).
        for guard in (
            "Cade Cunningham",
            "Tyrese Haliburton",
            "Jamal Murray",
            "Kevin Huerter",
        ):
            self.assertNotIn(guard, semua)

    def test_semua_entri_posisi_big(self):
        for tim, daftar in self.dokumen["teams"].items():
            self.assertLessEqual(len(daftar), 2, tim)
            for entri in daftar:
                self.assertIn(entri["pos"], ["C", "PF", "F-C", "C-F"], entri)
                self.assertIn(entri.get("tier"), ("primary", "fallback"), entri)
                lantai_blk = 1.0 if entri["tier"] == "primary" else 0.7
                self.assertGreaterEqual(entri["blk_per_game"], lantai_blk)
                self.assertGreaterEqual(entri["mp_per_game"], 18.0)
                self.assertGreaterEqual(entri["games_played"], 3)


@unittest.skipUnless(
    ARTEFAK_VERIF.exists(),
    "artefak out/analysis_verif_tahap4_2026-11-22.json tidak ada (runtime)",
)
class TestArtefakNyata(unittest.TestCase):
    """Kasus wajib veto AND di artefak verif 22 Nov (pemetaan JSON)."""

    @classmethod
    def setUpClass(cls):
        data = json.loads(ARTEFAK_VERIF.read_text(encoding="utf-8"))
        cls.verif = {
            (m.get("nba_analysis") or {}).get("match_id"): m.get("nba_analysis") or {}
            for m in data.get("matches") or []
        }

    def test_den_verif_menyala(self):
        # KASUS WAJIB: Claxton OUT (2 sumber) + garis 236,5 +
        # pace 103,22 -> veto AND menyala.
        hasil = vonis.evaluasi_veto(self.verif["DEN@CHI_2026-11-22"], CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertTrue(hasil["menyala"])
        self.assertEqual(hasil["garis_pasar"], 236.5)
        self.assertEqual(hasil["pace_tercepat"], 103.22)
        self.assertEqual([p["player"] for p in hasil["pelindung_out"]], ["Nic Claxton"])
        self.assertEqual(hasil["kondisi_menyala"], ["garis", "pace"])

    def test_okc_verif_tidak_menyala_parsial_pace(self):
        # KASUS WAJIB: Holmgren OUT (2 sumber) tapi garis 231,5
        # < 232,0 -> veto TIDAK menyala; pace 102,19 menyala
        # sendiri -> peringatan parsial (worker B: +3 bantalan).
        hasil = vonis.evaluasi_veto(self.verif["OKC@MIA_2026-11-22"], CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertFalse(hasil["menyala"])
        self.assertTrue(hasil["peringatan_parsial"])
        self.assertEqual(hasil["kondisi_menyala"], ["pace"])
        self.assertEqual(hasil["garis_pasar"], 231.5)
        self.assertEqual(hasil["pace_tercepat"], 102.19)
        self.assertEqual(
            [p["player"] for p in hasil["pelindung_out"]], ["Chet Holmgren"]
        )

    def test_okc_verif_menyala_dengan_or(self):
        # Bukti reversibilitas di artefak nyata: dengan logic OR,
        # OKC verif menyala (pace saja cukup).
        cfg_or = copy.deepcopy(CFG)
        cfg_or["vonis"]["veto"]["logic"] = "OR"
        hasil = vonis.evaluasi_veto(self.verif["OKC@MIA_2026-11-22"], cfg_or)
        self.assertTrue(hasil["menyala"])


if __name__ == "__main__":
    unittest.main()
