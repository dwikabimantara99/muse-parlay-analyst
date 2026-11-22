"""Tes engine/cushion.py — TANPA network, TANPA membaca out/.

Fixture DISALIN (bukan dibaca) dari bukti nyata agar tes tidak
bergantung pada file out/:
- Persentil total sim DET@ATL 2026-11-22 dari
  examples/simulation_nba_ATL_DET_2026-11-22.json (score_distribution
  total: median 219,0, std 19,45, p5 188, p25 206, p74 232, p75 232,
  p95 252 — fixture lama median 223/p75 235 sudah basi).
- Tangga Under Polymarket nba-det-atl-2026-11-22 dari
  out/poly_ladder_nba-det-atl-2026-11-22.json (31 garis Under
  199,5–255,5; line + price_cents + jup_estimated_cents + volume_usd
  + thin). Harga 235,5 dikoreksi 71,0 -> 72,0 sesuai artefak (juga
  205,5/207,5/209,5/213,5/221,5/224,5/229,5).

KOREKSI PENTING (temuan pekerja A, 2026-11-23): garis 249,5 punya
volume $141 (thin False) — jadi dengan lantai harga 75¢ + penghalang
volume, Asuransi TIDAK gagal total: ia naik tangga sampai 249,5 dan
meets. Premis "237,5+ gagal volume" salah di 249,5. Tes
test_naik_tangga_harga_dan_volume_det_atl menegaskan perilaku BENAR
ini; tes test_tidak_ada_garis_lolos_tangga_terpotong memakai tangga
yang dipotong di 247,5 (tanpa 249,5) untuk kasus meets=False.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import cushion

# Persentil total sim DET@ATL (artefak terkini, dengan p74 langsung).
PERCENTILES_DET_ATL = {
    "median": 219.0,
    "std": 19.45,
    "p5": 188.0,
    "p25": 206.0,
    "p74": 232.0,
    "p75": 232.0,
    "p95": 252.0,
}
MARKET_LINE_DET_ATL = 225.5

# Tangga Under DET@ATL (line, price_cents, jup_estimated_cents,
# volume_usd, thin) — nilai nyata dari artefak ladder.
UNDER_LADDER_DET_ATL = [
    (199.5, 7.5, 8.0, 15.957433, True),
    (201.5, 8.5, 9.0, None, True),
    (203.5, 10.5, 11.0, 38.46, True),
    (205.5, 13.5, 14.0, None, True),
    (207.5, 15.5, 16.0, 2.325578, True),
    (209.5, 20.5, 21.0, 18.0, True),
    (211.5, 23.0, 23.5, None, True),
    (213.5, 26.5, 27.0, 48.09, True),
    (215.5, 31.5, 32.0, 31.0, True),
    (217.5, 35.5, 36.0, 19.629126, True),
    (219.5, 40.0, 40.5, 1142.490439, False),
    (221.5, 43.5, 44.0, 637.380953, False),
    (223.5, 48.5, 49.0, 9730.457231, False),
    (224.5, 49.5, 50.0, 50.0, True),
    (225.5, 52.5, 53.0, 44048.564621, False),
    (226.5, 55.5, 56.0, 25435.626323, False),
    (227.5, 57.5, 58.0, 9582.653142, False),
    (229.5, 62.0, 62.5, 430.597603, False),
    (231.5, 65.5, 66.0, 169.0, False),
    (233.5, 66.5, 67.0, 269.985075, False),
    (235.5, 72.0, 72.5, 434.091258, False),
    (237.5, 75.5, 76.0, 6.2987, True),
    (239.5, 80.5, 81.0, 5.0, True),
    (241.5, 83.0, 83.5, None, True),
    (243.5, 85.0, 85.5, 10.580247, True),
    (245.5, 87.5, 88.0, 93.0, True),
    (247.5, 89.5, 90.0, None, True),
    (249.5, 92.5, 93.0, 141.0, False),
    (251.5, 93.5, 94.0, None, True),
    (253.5, 95.5, 96.0, None, True),
    (255.5, 95.45, 95.95, None, True),
]

LADDER_DET_ATL = [
    {
        "line": line,
        "price_cents": harga,
        "jup_estimated_cents": jup,
        "volume_usd": volume,
        "thin": thin,
    }
    for line, harga, jup, volume, thin in UNDER_LADDER_DET_ATL
]

# Config minimal: hanya lantai volume. Target peluang Asuransi (0,74)
# SENGAJA tidak ada -> jalur default.
CFG_MINIMAL = {"polymarket_ladder": {"min_volume_usd": 100.0}}

CFG_TARGET_70 = {
    "polymarket_ladder": {"min_volume_usd": 100.0},
    "filters": {"nba_alt_under": {"insurance_target_probability": 0.70}},
}


class TestInsuranceLineDetAtl(unittest.TestCase):
    def test_dengan_p74_langsung(self):
        # p74 = 232 langsung; kandidat pertama 233,5 (tidak tipis,
        # P_model interpolasi 0,765 >= 0,74) -> meets tanpa naik tangga.
        hasil = cushion.insurance_line(
            PERCENTILES_DET_ATL, MARKET_LINE_DET_ATL, LADDER_DET_ATL, CFG_MINIMAL
        )
        self.assertTrue(hasil["meets"])
        self.assertIsNone(hasil["reason"])
        self.assertEqual(hasil["p_target"], 232.0)
        self.assertEqual(hasil["p_target_source"], "p74")
        self.assertEqual(hasil["required_line"], 232.0)
        self.assertEqual(hasil["line"], 233.5)
        self.assertEqual(hasil["price_cents"], 66.5)
        self.assertEqual(hasil["jup_estimated_cents"], 67.0)
        self.assertEqual(hasil["cushion_vs_market_points"], 8.0)
        self.assertEqual(hasil["cushion_vs_median_points"], 14.5)
        self.assertAlmostEqual(hasil["p_model_pada_garis"], 0.765, places=6)
        self.assertEqual(hasil["p_model_source"], "interpolasi_persentil")
        self.assertEqual(hasil["volume_usd"], 269.985075)
        self.assertFalse(hasil["thin"])
        self.assertIsNone(hasil["climb"])
        # Target belum di config -> sumber "default".
        self.assertEqual(hasil["target_probability"], 0.74)
        self.assertEqual(hasil["target_probability_source"], "default")
        # Lantai market DIHAPUS (v13) — tidak ada lagi di hasil.
        self.assertNotIn("market_cushion_floor_points", hasil)
        self.assertNotIn("market_floor", hasil)

    def test_interpolasi_p74(self):
        # Tanpa p74: p74 interpolasi median->p75 = 219 + 0,96 x 13 = 231,48.
        percentiles = {"median": 219.0, "p75": 232.0}
        hasil = cushion.insurance_line(
            percentiles, MARKET_LINE_DET_ATL, LADDER_DET_ATL, CFG_MINIMAL
        )
        self.assertTrue(hasil["meets"])
        self.assertAlmostEqual(hasil["p_target"], 231.48, places=6)
        self.assertEqual(hasil["p_target_source"], "interpolasi_median_p75")
        # Garis terkecil >= 231,48 adalah 231,5; P_model interpolasi
        # 0,7404 >= 0,74 (konsisten dengan target p74).
        self.assertEqual(hasil["line"], 231.5)
        self.assertAlmostEqual(hasil["p_model_pada_garis"], 0.740385, places=6)

    def test_interpolasi_batas_bawah_di_atas_p75(self):
        # Persentil hanya median + p75: garis 233,5 di atas jangkar
        # tertinggi (p75) -> p None, tapi batas bawah 0,75 >= 0,74
        # cukup untuk lolos syarat peluang.
        percentiles = {"median": 219.0, "p75": 232.0}
        tangga = [b for b in LADDER_DET_ATL if b["line"] >= 233.5]
        hasil = cushion.insurance_line(
            percentiles, MARKET_LINE_DET_ATL, tangga, CFG_MINIMAL
        )
        self.assertTrue(hasil["meets"])
        self.assertEqual(hasil["line"], 233.5)
        self.assertIsNone(hasil["p_model_pada_garis"])
        self.assertEqual(hasil["p_model_source"], "di_luar_jangkauan_persentil")
        self.assertEqual(hasil["p_model_batas_bawah"], 0.75)

    def test_naik_tangga_harga_dan_volume_det_atl(self):
        # Lantai harga 75¢ + penghalang volume: 233,5 gagal harga
        # (jup 67), 235,5 gagal harga (jup 72,5), 237,5–247,5 gagal
        # volume (tipis) — tapi 249,5 LOLOS (jup 93, volume $141,
        # tidak tipis, P_model 0,925). Meets di 249,5, BUKAN gagal.
        # (Koreksi premis "237,5+ gagal volume": 249,5 volumenya $141.)
        hasil = cushion.insurance_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            CFG_MINIMAL,
            harga_min_cents=75,
        )
        self.assertTrue(hasil["meets"])
        self.assertEqual(hasil["line"], 249.5)
        self.assertEqual(hasil["price_cents"], 92.5)
        self.assertEqual(hasil["jup_estimated_cents"], 93.0)
        self.assertEqual(hasil["volume_usd"], 141.0)
        self.assertFalse(hasil["thin"])
        self.assertAlmostEqual(hasil["p_model_pada_garis"], 0.925, places=6)
        self.assertEqual(hasil["rungs_dicoba"], 9)
        climb = hasil["climb"]
        self.assertEqual(climb["from_line"], 233.5)
        self.assertEqual(climb["to_line"], 249.5)
        self.assertEqual(climb["rungs"], 8)
        self.assertEqual(climb["reason"], "harga_minimum+volume_tipis")

    def test_tidak_ada_garis_lolos_tangga_terpotong(self):
        # Tangga dipotong di 247,5 (tanpa 249,5): semua kandidat gagal
        # — 233,5/235,5 gagal harga, 237,5+ gagal volume -> meets=False
        # + alasan menyebut kedua syarat yang gagal.
        tangga_pendek = [b for b in LADDER_DET_ATL if b["line"] <= 247.5]
        hasil = cushion.insurance_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            tangga_pendek,
            CFG_MINIMAL,
            harga_min_cents=75,
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(
            hasil["reason"], "tidak_ada_garis_lolos: harga_minimum, volume_tipis"
        )
        self.assertEqual(hasil["syarat_gagal"], ["harga_minimum", "volume_tipis"])
        self.assertEqual(hasil["rungs_dicoba"], 8)
        self.assertIsNone(hasil["line"])
        self.assertIsNone(hasil["price_cents"])

    def test_asuransi_di_atas_utama(self):
        # Utama di 237,5 -> Asuransi harus > 237,5. Kandidat mulai
        # 239,5 (tipis) -> naik sampai 249,5 yang lolos.
        hasil = cushion.insurance_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            CFG_MINIMAL,
            garis_di_atas=237.5,
            harga_min_cents=75,
        )
        self.assertTrue(hasil["meets"])
        self.assertEqual(hasil["line"], 249.5)
        self.assertGreater(hasil["line"], 237.5)
        self.assertEqual(hasil["garis_di_atas"], 237.5)
        climb = hasil["climb"]
        self.assertEqual(climb["from_line"], 239.5)
        self.assertEqual(climb["to_line"], 249.5)
        self.assertEqual(climb["rungs"], 5)
        self.assertEqual(climb["reason"], "volume_tipis")

    def test_asuransi_di_atas_utama_tanpa_lantai_harga(self):
        # Tanpa lantai harga, penghalang volume saja sudah mendorong
        # Asuransi dari 239,5 (tipis) ke 249,5.
        hasil = cushion.insurance_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            CFG_MINIMAL,
            garis_di_atas=237.5,
        )
        self.assertTrue(hasil["meets"])
        self.assertEqual(hasil["line"], 249.5)
        self.assertEqual(hasil["climb"]["reason"], "volume_tipis")

    def test_peluang_under_dari_simulasi(self):
        # peluang_under eksplisit: 233,5 P=0,70 < 0,74 -> naik ke 235,5
        # (P=0,76) yang lolos.
        peluang = {233.5: 0.70, 235.5: 0.76}
        hasil = cushion.insurance_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            CFG_MINIMAL,
            peluang_under=peluang,
        )
        self.assertTrue(hasil["meets"])
        self.assertEqual(hasil["line"], 235.5)
        self.assertEqual(hasil["p_model_pada_garis"], 0.76)
        self.assertEqual(hasil["p_model_source"], "peluang_under")
        self.assertEqual(hasil["climb"]["from_line"], 233.5)
        self.assertEqual(hasil["climb"]["to_line"], 235.5)
        self.assertEqual(hasil["climb"]["rungs"], 1)
        self.assertEqual(hasil["climb"]["reason"], "peluang_model")

    def test_volume_penghalang_keras_sintetis(self):
        # Tangga sintetis: anak tangga pertama tipis -> dilewati walau
        # harga + peluang lolos; anak tangga kedua (tidak tipis) dipilih.
        percentiles = {"median": 200.0, "p74": 210.0, "p75": 212.0}
        tangga = [
            {
                "line": 210.5,
                "price_cents": 70.0,
                "jup_estimated_cents": 70.0,
                "volume_usd": 5.0,
                "thin": True,
            },
            {
                "line": 212.5,
                "price_cents": 74.0,
                "jup_estimated_cents": 74.0,
                "volume_usd": 500.0,
                "thin": False,
            },
        ]
        hasil = cushion.insurance_line(
            percentiles, 205.5, tangga, CFG_MINIMAL, harga_min_cents=70
        )
        self.assertTrue(hasil["meets"])
        self.assertEqual(hasil["line"], 212.5)
        self.assertFalse(hasil["thin"])
        self.assertEqual(hasil["climb"]["reason"], "volume_tipis")
        # 212,5 di atas p75 -> p None, batas bawah 0,75.
        self.assertIsNone(hasil["p_model_pada_garis"])
        self.assertEqual(hasil["p_model_batas_bawah"], 0.75)

    def test_sigma_melebar_garis_naik(self):
        # Sebaran melebar (p75 232 -> 245, tanpa p74): p74 interpolasi
        # 219 + 0,96 x 26 = 243,96 -> kandidat pertama 245,5, tapi
        # tipis -> naik ke 249,5 (tidak tipis, P di atas p75).
        percentiles = {"median": 219.0, "p75": 245.0}
        hasil = cushion.insurance_line(
            percentiles, MARKET_LINE_DET_ATL, LADDER_DET_ATL, CFG_MINIMAL
        )
        self.assertTrue(hasil["meets"])
        self.assertAlmostEqual(hasil["p_target"], 243.96, places=6)
        self.assertEqual(hasil["line"], 249.5)

    def test_tidak_ada_garis_memenuhi(self):
        # Tangga terpotong di bawah p74-target 232 -> tidak ada kandidat.
        tangga_pendek = [b for b in LADDER_DET_ATL if b["line"] <= 229.5]
        hasil = cushion.insurance_line(
            PERCENTILES_DET_ATL, MARKET_LINE_DET_ATL, tangga_pendek, CFG_MINIMAL
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "tidak_ada_garis_memenuhi")
        self.assertIsNone(hasil["line"])

    def test_data_hilang(self):
        # Tanpa persentil -> tidak bisa hitung p_target.
        hasil = cushion.insurance_line(
            {}, MARKET_LINE_DET_ATL, LADDER_DET_ATL, CFG_MINIMAL
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "persentil_tidak_lengkap")
        # Tanpa garis market.
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
        cfg = {
            "polymarket_ladder": {"min_volume_usd": 100.0},
            "filters": {"nba_alt_under": {"insurance_target_probability": 0.90}},
        }
        hasil = cushion.insurance_line(
            PERCENTILES_DET_ATL, MARKET_LINE_DET_ATL, LADDER_DET_ATL, cfg
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "target_di_luar_jangkauan_persentil")

    def test_target_probability_dari_config(self):
        # Target 0,70 dari config (bukan default): p70 interpolasi
        # 219 + 0,8 x 13 = 229,4 -> garis 229,5 (P_model 0,7019).
        hasil = cushion.insurance_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            CFG_TARGET_70,
        )
        self.assertTrue(hasil["meets"])
        self.assertEqual(hasil["target_probability"], 0.70)
        self.assertEqual(hasil["target_probability_source"], "config")
        self.assertAlmostEqual(hasil["p_target"], 229.4, places=6)
        self.assertEqual(hasil["p_target_source"], "interpolasi_median_p75")
        self.assertEqual(hasil["line"], 229.5)


class TestUtamaLine(unittest.TestCase):
    def test_det_atl_bantalan_8_tanpa_harga_min(self):
        # Bantalan adaptif 8; base max(219, 225,5) = 225,5;
        # required 233,5 -> garis 233,5 (tidak tipis).
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            cfg=CFG_MINIMAL,
            cushion_points=8.0,
        )
        self.assertTrue(hasil["meets"])
        self.assertEqual(hasil["cushion_points"], 8.0)
        self.assertEqual(hasil["base_line"], 225.5)
        self.assertEqual(hasil["required_line"], 233.5)
        self.assertEqual(hasil["line"], 233.5)
        self.assertEqual(hasil["price_cents"], 66.5)
        self.assertEqual(hasil["jup_estimated_cents"], 67.0)
        self.assertEqual(hasil["volume_usd"], 269.985075)
        self.assertFalse(hasil["thin"])
        self.assertIsNone(hasil["climb"])
        self.assertAlmostEqual(hasil["p_model_pada_garis"], 0.765, places=6)

    def test_naik_tangga_harga_75_garis_tipis_boleh(self):
        # Lantai harga 75¢: 233,5 (jup 67) + 235,5 (jup 72,5) gagal
        # harga -> naik ke 237,5 (jup 76). Garis tipis BOLEH untuk
        # Utama — dicatat thin=True, bukan penghalang.
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            cfg=CFG_MINIMAL,
            cushion_points=8.0,
            harga_min_cents=75,
        )
        self.assertTrue(hasil["meets"])
        self.assertEqual(hasil["line"], 237.5)
        self.assertEqual(hasil["price_cents"], 75.5)
        self.assertEqual(hasil["jup_estimated_cents"], 76.0)
        self.assertEqual(hasil["volume_usd"], 6.2987)
        self.assertTrue(hasil["thin"])
        self.assertAlmostEqual(hasil["p_model_pada_garis"], 0.805, places=6)
        climb = hasil["climb"]
        self.assertEqual(climb["from_line"], 233.5)
        self.assertEqual(climb["to_line"], 237.5)
        self.assertEqual(climb["rungs"], 2)
        self.assertEqual(climb["reason"], "harga_minimum")

    def test_bantalan_adaptif_tidak_tersedia(self):
        # cushion_points None -> meets=False, TIDAK ada fallback ke
        # aturan lama (aturan 8/12 berbasis spread dihapus).
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            cfg=CFG_MINIMAL,
            cushion_points=None,
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "bantalan_adaptif_tidak_tersedia")
        self.assertIsNone(hasil["line"])
        self.assertIsNone(hasil["required_line"])

    def test_parameter_spread_dihapus(self):
        # Signature baru tidak lagi menerima spread (aturan berbasis
        # spread dihapus) — pemanggil lama harus diperbarui.
        with self.assertRaises(TypeError):
            cushion.utama_line(
                PERCENTILES_DET_ATL,
                MARKET_LINE_DET_ATL,
                LADDER_DET_ATL,
                spread=5.0,
                cfg=CFG_MINIMAL,
            )

    def test_harga_minimum_tidak_tercapai(self):
        # Lantai 99¢: harga jup tertinggi di tangga 95,95 -> tidak ada
        # garis yang mencapai lantai.
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            cfg=CFG_MINIMAL,
            cushion_points=8.0,
            harga_min_cents=99,
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "harga_minimum_tidak_tercapai")
        self.assertEqual(hasil["garis_bantalan"], 233.5)
        self.assertIsNone(hasil["line"])

    def test_median_lebih_tinggi_dari_market(self):
        # Median model 230 > market 225,5 -> base 230, required 238.
        percentiles = {"median": 230.0, "p75": 242.0}
        hasil = cushion.utama_line(
            percentiles,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            cfg=CFG_MINIMAL,
            cushion_points=8.0,
        )
        self.assertEqual(hasil["base_line"], 230.0)
        self.assertEqual(hasil["required_line"], 238.0)
        self.assertEqual(hasil["line"], 239.5)

    def test_bantalan_adaptif_12_92(self):
        # Bantalan adaptif 12,92 (laga dua penyerang panas, analis):
        # required 225,5 + 12,92 = 238,42 -> garis 239,5.
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            cfg=CFG_MINIMAL,
            cushion_points=12.92,
        )
        self.assertTrue(hasil["meets"])
        self.assertAlmostEqual(hasil["required_line"], 238.42, places=6)
        self.assertEqual(hasil["line"], 239.5)

    def test_tidak_ada_garis_memenuhi(self):
        tangga_pendek = [b for b in LADDER_DET_ATL if b["line"] <= 229.5]
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            tangga_pendek,
            cfg=CFG_MINIMAL,
            cushion_points=8.0,
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "tidak_ada_garis_memenuhi")
        self.assertIsNone(hasil["line"])

    def test_data_hilang(self):
        hasil = cushion.utama_line(
            {},
            MARKET_LINE_DET_ATL,
            LADDER_DET_ATL,
            cfg=CFG_MINIMAL,
            cushion_points=8.0,
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "median_tidak_ada")
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL,
            None,
            LADDER_DET_ATL,
            cfg=CFG_MINIMAL,
            cushion_points=8.0,
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "garis_market_tidak_ada")


class TestTanggaDanValidasi(unittest.TestCase):
    def test_parse_tangga_pertahankan_volume_dan_thin(self):
        parsed = cushion._parse_tangga(LADDER_DET_ATL, 100.0)
        baris = {b["line"]: b for b in parsed}
        self.assertEqual(baris[235.5]["volume_usd"], 434.091258)
        self.assertFalse(baris[235.5]["thin"])
        self.assertEqual(baris[237.5]["volume_usd"], 6.2987)
        self.assertTrue(baris[237.5]["thin"])
        # Volume None -> thin True walau flag bilang False.
        parsed = cushion._parse_tangga(
            [{"line": 240.5, "volume_usd": None, "thin": False}], 100.0
        )
        self.assertTrue(parsed[0]["thin"])
        self.assertIsNone(parsed[0]["volume_usd"])
        # Tanpa flag thin: dihitung dari volume vs lantai.
        parsed = cushion._parse_tangga(
            [
                {"line": 240.5, "volume_usd": 50.0},
                {"line": 242.5, "volume_usd": 500.0},
            ],
            100.0,
        )
        self.assertTrue(parsed[0]["thin"])
        self.assertFalse(parsed[1]["thin"])
        # Baris angka saja: tanpa volume -> thin True.
        parsed = cushion._parse_tangga([233.5, 235.5])
        self.assertIsNone(parsed[0]["volume_usd"])
        self.assertTrue(parsed[0]["thin"])

    def test_tangga_angka_saja_asuransi_gagal_volume_utama_lolos(self):
        # Tangga angka saja = semua garis tipis: Asuransi gagal
        # (penghalang keras), Utama lolos (tipis hanya peringatan).
        hasil = cushion.insurance_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            [233.5, 235.5, 237.5],
            CFG_MINIMAL,
        )
        self.assertFalse(hasil["meets"])
        self.assertEqual(hasil["reason"], "tidak_ada_garis_lolos: volume_tipis")
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            [233.5, 235.5, 237.5],
            cfg=CFG_MINIMAL,
            cushion_points=8.0,
        )
        self.assertTrue(hasil["meets"])
        self.assertEqual(hasil["line"], 233.5)
        self.assertTrue(hasil["thin"])

    def test_tangga_tidak_urut_tetap_dipilih_terkecil(self):
        hasil = cushion.utama_line(
            PERCENTILES_DET_ATL,
            MARKET_LINE_DET_ATL,
            [239.5, 233.5, 237.5],
            cfg=CFG_MINIMAL,
            cushion_points=8.0,
        )
        self.assertEqual(hasil["line"], 233.5)

    def test_default_lantai_market_dihapus(self):
        self.assertFalse(hasattr(cushion, "DEFAULT_MARKET_CUSHION_FLOOR_POINTS"))
        self.assertTrue(hasattr(cushion, "DEFAULT_INSURANCE_TARGET_PROBABILITY"))

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
                {"median": "219", "p75": 232.0},
                MARKET_LINE_DET_ATL,
                LADDER_DET_ATL,
                CFG_MINIMAL,
            )
        with self.assertRaises(ValueError):
            cushion.utama_line(
                PERCENTILES_DET_ATL,
                MARKET_LINE_DET_ATL,
                LADDER_DET_ATL,
                cfg=CFG_MINIMAL,
                cushion_points="8",
            )
        with self.assertRaises(ValueError):
            cushion.utama_line(
                PERCENTILES_DET_ATL,
                MARKET_LINE_DET_ATL,
                LADDER_DET_ATL,
                cfg=CFG_MINIMAL,
                cushion_points=-1.0,
            )
        with self.assertRaises(ValueError):
            cushion.utama_line(
                PERCENTILES_DET_ATL,
                MARKET_LINE_DET_ATL,
                LADDER_DET_ATL,
                cfg=CFG_MINIMAL,
                cushion_points=8.0,
                harga_min_cents=150,
            )
        with self.assertRaises(ValueError):
            cushion.insurance_line(
                PERCENTILES_DET_ATL,
                MARKET_LINE_DET_ATL,
                LADDER_DET_ATL,
                CFG_MINIMAL,
                peluang_under={233.5: 1.5},
            )
        with self.assertRaises(ValueError):
            cushion.insurance_line(
                PERCENTILES_DET_ATL,
                MARKET_LINE_DET_ATL,
                [{"line": 233.5, "thin": "ya"}],
                CFG_MINIMAL,
            )

    def test_target_probability_tidak_valid(self):
        cfg = {"filters": {"nba_alt_under": {"insurance_target_probability": 1.5}}}
        with self.assertRaises(ValueError):
            cushion.insurance_line(
                PERCENTILES_DET_ATL, MARKET_LINE_DET_ATL, LADDER_DET_ATL, cfg
            )


if __name__ == "__main__":
    unittest.main()
