"""Tes engine/anomaly.py — fee Kalshi, snapshot harga, anomali, evaluate_leg.

Tes memakai cfg dict eksplisit (tidak bergantung pada playstyle.yaml yang
sedang diubah worker lain), kecuali tes config nyata yang skip bila bagian
"fees" belum ada. TANPA network.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from engine import anomaly

# cfg lengkap untuk semua fungsi anomaly (angka sama dengan playstyle.yaml).
CFG = {
    "blend": {"w_model": 0.3},
    "price_labels": {"diskon_min_ev_pct": 2.0, "mahal_max_ev_pct": -2.0},
    "anomaly": {
        "jup_vs_market_points": 4.0,
        "model_vs_market_points": 8.0,
        "sharp_move_cents": 3,
    },
    "fees": {"kalshi_taker_fee_coeff": 0.07},
}

# Fixture pelajaran Thunder (Nov 2026, DECISIONS.md): Thunder Under 227.5
# dibeli di 75¢, bergerak ke 71¢ sebelum tip-off karena news yang tidak
# diketahui user; tiket kalah. Hanya harga 75¢ -> 71¢ yang berasal dari
# kasus nyata; kunci dan jam di bawah adalah data fixture.
THUNDER_KEY = "nba_thunder:total_under_227.5"
THUNDER_FIRST_AT = "2026-11-22T10:00:00+07:00"


class TestKalshiFee(unittest.TestCase):
    def test_contoh_acuan(self):
        # 80¢ -> 81,12¢; 50¢ -> 51,75¢ (fee 0,07 x P x (1-P)).
        self.assertAlmostEqual(anomaly.kalshi_effective_price_cents(80.0, CFG), 81.12)
        self.assertAlmostEqual(anomaly.kalshi_effective_price_cents(50.0, CFG), 51.75)

    def test_fee_maksimal_di_tengah(self):
        # Fee P x (1-P) maksimal di 50¢; di tepi (90¢) lebih kecil.
        fee_50 = anomaly.kalshi_effective_price_cents(50.0, CFG) - 50.0
        fee_90 = anomaly.kalshi_effective_price_cents(90.0, CFG) - 90.0
        self.assertAlmostEqual(fee_50, 1.75)
        self.assertAlmostEqual(fee_90, 0.63)
        self.assertGreater(fee_50, fee_90)

    def test_koefisien_dari_cfg(self):
        cfg = {"fees": {"kalshi_taker_fee_coeff": 0.10}}
        # 50¢ + 100 x 0,10 x 0,25 = 52,5¢.
        self.assertAlmostEqual(anomaly.kalshi_effective_price_cents(50.0, cfg), 52.5)

    def test_validasi_harga(self):
        for bad in (0, 100, -5, 101, "80", None, True, float("nan")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                anomaly.kalshi_effective_price_cents(bad, CFG)

    def test_koefisien_tidak_valid(self):
        for bad in (-0.1, 1.0, "0.07", None):
            cfg = {"fees": {"kalshi_taker_fee_coeff": bad}}
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                anomaly.kalshi_effective_price_cents(80.0, cfg)

    def test_fee_dari_config_nyata(self):
        """Bila playstyle.yaml sudah punya bagian fees (worker model)."""
        cfg = config.load_playstyle()
        if "fees" not in cfg:
            self.skipTest("playstyle.yaml belum punya bagian 'fees' (worker model)")
        self.assertAlmostEqual(anomaly.kalshi_effective_price_cents(80.0, cfg), 81.12)


class TestPriceSnapshots(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "snapshots.json"
        self.snaps = anomaly.PriceSnapshots(self.path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_record_dan_get(self):
        self.assertTrue(self.snaps.record("k1", 75.0, "2026-11-22T10:00:00+07:00"))
        got = self.snaps.get("k1")
        self.assertEqual(got["price_cents"], 75.0)
        self.assertEqual(got["first_at"], "2026-11-22T10:00:00+07:00")
        self.assertIsNone(self.snaps.get("tidak_ada"))

    def test_hanya_snapshot_pertama_disimpan(self):
        self.snaps.record("k1", 75.0, "2026-11-22T10:00:00+07:00")
        self.assertFalse(self.snaps.record("k1", 71.0, "2026-11-22T11:00:00+07:00"))
        self.assertEqual(self.snaps.get("k1")["price_cents"], 75.0)

    def test_persisten_antar_instance(self):
        self.snaps.record("k1", 75.0, "2026-11-22T10:00:00+07:00")
        ulang = anomaly.PriceSnapshots(self.path)
        self.assertEqual(ulang.get("k1")["price_cents"], 75.0)
        # File tersimpan sebagai JSON yang bisa dibaca.
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["k1"]["price_cents"], 75.0)

    def test_file_rusak_melempar(self):
        self.path.write_text("{bukan json", encoding="utf-8")
        with self.assertRaises(ValueError):
            anomaly.PriceSnapshots(self.path)

    def test_validasi_record(self):
        with self.assertRaises(ValueError):
            self.snaps.record("", 75.0, "2026-11-22T10:00:00+07:00")
        with self.assertRaises(ValueError):
            self.snaps.record("k1", 0, "2026-11-22T10:00:00+07:00")
        with self.assertRaises(ValueError):
            self.snaps.record("k1", 75.0, "")

    def test_sharp_move_batas(self):
        self.snaps.record("k1", 75.0, "2026-11-22T10:00:00+07:00")
        # Tepat 3¢ -> anomali (>= 3¢, D9).
        gerak = self.snaps.sharp_move("k1", 72.0, CFG)
        self.assertIsNotNone(gerak)
        self.assertEqual(gerak["type"], "sharp_move")
        self.assertEqual(gerak["first_cents"], 75.0)
        self.assertEqual(gerak["now_cents"], 72.0)
        self.assertAlmostEqual(gerak["delta_cents"], -3.0)
        # 2,9¢ -> bukan anomali.
        self.assertIsNone(self.snaps.sharp_move("k1", 72.1, CFG))
        # Gerak naik juga dihitung.
        gerak_naik = self.snaps.sharp_move("k1", 78.0, CFG)
        self.assertIsNotNone(gerak_naik)
        self.assertAlmostEqual(gerak_naik["delta_cents"], 3.0)

    def test_sharp_move_tanpa_snapshot(self):
        self.assertIsNone(self.snaps.sharp_move("belum_ada", 71.0, CFG))

    def test_fixture_pelajaran_thunder(self):
        """Thunder Under 227.5: 75¢ -> 71¢ (gerak 4¢) HARUS anomali."""
        self.snaps.record(THUNDER_KEY, 75.0, THUNDER_FIRST_AT)
        gerak = self.snaps.sharp_move(THUNDER_KEY, 71.0, CFG)
        self.assertIsNotNone(gerak)
        self.assertEqual(gerak["type"], "sharp_move")
        self.assertAlmostEqual(gerak["delta_cents"], -4.0)
        self.assertEqual(gerak["first_at"], THUNDER_FIRST_AT)


class TestCheckJupVsMarket(unittest.TestCase):
    def test_tepat_di_ambang_bukan_anomali(self):
        # |75¢ - 0,71| = tepat 4 poin -> bukan anomali (aturan "lebih dari").
        self.assertIsNone(anomaly.check_jup_vs_market(75.0, 0.71, CFG))

    def test_di_atas_ambang_anomali(self):
        hasil = anomaly.check_jup_vs_market(75.0, 0.70, CFG)
        self.assertIsNotNone(hasil)
        self.assertEqual(hasil["type"], "jup_vs_market")
        self.assertAlmostEqual(hasil["diff_points"], 5.0)

    def test_di_bawah_ambang_bukan_anomali(self):
        self.assertIsNone(anomaly.check_jup_vs_market(75.0, 0.73, CFG))

    def test_p_market_none_bukan_anomali(self):
        self.assertIsNone(anomaly.check_jup_vs_market(75.0, None, CFG))

    def test_validasi(self):
        with self.assertRaises(ValueError):
            anomaly.check_jup_vs_market(0, 0.70, CFG)
        with self.assertRaises(ValueError):
            anomaly.check_jup_vs_market(75.0, 1.5, CFG)


class TestCheckModelVsMarket(unittest.TestCase):
    def test_tepat_di_ambang_bukan_anomali(self):
        # |0,80 - 0,72| = tepat 8 poin -> bukan anomali (aturan "lebih dari").
        self.assertIsNone(anomaly.check_model_vs_market(0.80, 0.72, CFG))

    def test_di_atas_ambang_anomali(self):
        hasil = anomaly.check_model_vs_market(0.80, 0.71, CFG)
        self.assertIsNotNone(hasil)
        self.assertEqual(hasil["type"], "model_vs_market")
        self.assertAlmostEqual(hasil["diff_points"], 9.0)
        self.assertTrue(hasil["kenapa_beda_required"])

    def test_di_bawah_ambang_bukan_anomali(self):
        self.assertIsNone(anomaly.check_model_vs_market(0.80, 0.73, CFG))

    def test_p_market_none_bukan_anomali(self):
        self.assertIsNone(anomaly.check_model_vs_market(0.80, None, CFG))

    def test_validasi(self):
        with self.assertRaises(ValueError):
            anomaly.check_model_vs_market(1.5, 0.70, CFG)
        with self.assertRaises(ValueError):
            anomaly.check_model_vs_market(0.80, -0.1, CFG)


class TestEvaluateLeg(unittest.TestCase):
    def test_jup_ujung_ke_ujung_tanpa_anomali(self):
        hasil = anomaly.evaluate_leg(
            0.80, 0.75, 76.0, "odds_api_devig", CFG, venue="jup"
        )
        # p_final = 0,3 x 0,80 + 0,7 x 0,75 = 0,765.
        self.assertAlmostEqual(hasil["p_final"], 0.765)
        self.assertEqual(hasil["w_model"], 0.3)
        self.assertFalse(hasil["model_only"])
        self.assertEqual(hasil["comparison_source"], "odds_api_devig")
        self.assertEqual(hasil["price_cents"], 76.0)
        self.assertEqual(hasil["effective_price_cents"], 76.0)
        self.assertEqual(hasil["venue"], "jup")
        # EV = (0,765 x 100/76 - 1) x 100 ≈ +0,66% -> WAJAR.
        self.assertAlmostEqual(hasil["ev_pct"], 0.6578947368421053)
        self.assertEqual(hasil["price_label"], "WAJAR")
        self.assertEqual(hasil["anomalies"], [])

    def test_kalshi_model_only_diskon(self):
        # Venue Kalshi + p_market None: harga efektif 81,12¢, MODEL_ONLY.
        hasil = anomaly.evaluate_leg(0.85, None, 80.0, None, CFG, venue="kalshi")
        self.assertTrue(hasil["model_only"])
        self.assertAlmostEqual(hasil["p_final"], 0.85)
        self.assertAlmostEqual(hasil["effective_price_cents"], 81.12)
        # EV = (0,85 x 100/81,12 - 1) x 100 ≈ +4,78% -> DISKON.
        self.assertAlmostEqual(hasil["ev_pct"], 4.783037475345142)
        self.assertEqual(hasil["price_label"], "DISKON")
        self.assertEqual(hasil["anomalies"], [])

    def test_mahal_tetap_dilaporkan_bukan_ditolak(self):
        # EV ≈ -4,38% -> MAHAL, kaki tetap dikembalikan apa adanya.
        hasil = anomaly.evaluate_leg(
            0.80, 0.75, 80.0, "odds_api_devig", CFG, venue="jup"
        )
        self.assertEqual(hasil["price_label"], "MAHAL")
        self.assertAlmostEqual(hasil["ev_pct"], -4.375)
        # |80¢ - 0,75| = 5 poin > 4 -> anomali jup_vs_market ikut tercatat.
        self.assertEqual(len(hasil["anomalies"]), 1)
        self.assertEqual(hasil["anomalies"][0]["type"], "jup_vs_market")

    def test_model_vs_market_tercatat(self):
        # |0,85 - 0,70| = 15 poin > 8 -> anomali model_vs_market.
        hasil = anomaly.evaluate_leg(
            0.85, 0.70, 72.0, "odds_api_devig", CFG, venue="jup"
        )
        jenis = [a["type"] for a in hasil["anomalies"]]
        self.assertIn("model_vs_market", jenis)
        anomali = next(a for a in hasil["anomalies"] if a["type"] == "model_vs_market")
        self.assertTrue(anomali["kenapa_beda_required"])

    def test_thunder_sharp_move_lewat_evaluate_leg(self):
        """Fixture Thunder ujung-ke-ujung: snapshot 75¢, harga kini 71¢."""
        with tempfile.TemporaryDirectory() as tmpdir:
            snaps = anomaly.PriceSnapshots(Path(tmpdir) / "snapshots.json")
            snaps.record(THUNDER_KEY, 75.0, THUNDER_FIRST_AT)
            hasil = anomaly.evaluate_leg(
                0.75,
                0.72,
                71.0,
                "odds_api_devig",
                CFG,
                venue="jup",
                snapshots=snaps,
                snapshot_key=THUNDER_KEY,
            )
        self.assertEqual(len(hasil["anomalies"]), 1)
        gerak = hasil["anomalies"][0]
        self.assertEqual(gerak["type"], "sharp_move")
        self.assertAlmostEqual(gerak["delta_cents"], -4.0)

    def test_tanpa_snapshot_tidak_ada_sharp_move(self):
        # snapshots tidak diberikan -> tidak ada cek sharp move.
        hasil = anomaly.evaluate_leg(
            0.75, 0.72, 71.0, "odds_api_devig", CFG, venue="jup"
        )
        self.assertEqual(hasil["anomalies"], [])

    def test_dengan_config_nyata_jup(self):
        # Venue jup tidak butuh bagian fees, jadi config nyata bisa dipakai.
        hasil = anomaly.evaluate_leg(0.80, 0.75, 76.0, "odds_api_devig")
        self.assertAlmostEqual(hasil["p_final"], 0.765)
        self.assertEqual(hasil["price_label"], "WAJAR")

    def test_validasi(self):
        with self.assertRaises(ValueError):
            anomaly.evaluate_leg(
                0.80, 0.75, 76.0, "odds_api_devig", CFG, venue="polymarket"
            )
        with self.assertRaises(ValueError):
            anomaly.evaluate_leg(None, 0.75, 76.0, "odds_api_devig", CFG)
        with self.assertRaises(ValueError):
            anomaly.evaluate_leg(0.80, 0.75, 0, "odds_api_devig", CFG)


# cfg untuk cek garis market: CFG + ambang baru. Nilai market_line_check
# adalah NILAI AWAL yang diusulkan (BELUM DIKALIBRASI) — playstyle.yaml
# belum punya bagian ini (koordinator menambahkannya saat integrasi).
# Cek bantalan TIDAK lagi membaca config (bantalan adaptif tercatat
# diteruskan sebagai argumen — kunci D10 dihapus di playstyle v13).
CFG_GARIS = {
    **CFG,
    "market_line_check": {"total_gap_points": 5.0, "min_model_under_prob": 0.70},
}


class TestMarketLineSnapshots(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "market_lines.json"
        self.snaps = anomaly.MarketLineSnapshots(self.path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_record_dan_get(self):
        self.assertTrue(
            self.snaps.record("k1", 227.5, 75.0, "2026-11-22T10:00:00+07:00")
        )
        got = self.snaps.get("k1")
        self.assertEqual(got["line"], 227.5)
        self.assertEqual(got["price_cents"], 75.0)
        self.assertEqual(got["first_at"], "2026-11-22T10:00:00+07:00")
        self.assertIsNone(self.snaps.get("tidak_ada"))

    def test_hanya_snapshot_pertama_disimpan(self):
        self.snaps.record("k1", 227.5, 75.0, "2026-11-22T10:00:00+07:00")
        self.assertFalse(
            self.snaps.record("k1", 229.5, 71.0, "2026-11-22T11:00:00+07:00")
        )
        got = self.snaps.get("k1")
        self.assertEqual(got["line"], 227.5)
        self.assertEqual(got["price_cents"], 75.0)

    def test_persisten_antar_instance(self):
        self.snaps.record("k1", 227.5, 75.0, "2026-11-22T10:00:00+07:00")
        ulang = anomaly.MarketLineSnapshots(self.path)
        self.assertEqual(ulang.get("k1")["line"], 227.5)
        # File tersimpan sebagai JSON yang bisa dibaca.
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["k1"]["line"], 227.5)
        self.assertEqual(data["k1"]["price_cents"], 75.0)

    def test_file_rusak_melempar(self):
        self.path.write_text("{bukan json", encoding="utf-8")
        with self.assertRaises(ValueError):
            anomaly.MarketLineSnapshots(self.path)
        # Entri tidak lengkap (tanpa line) juga rusak, bukan dihapus diam-diam.
        self.path.write_text(
            json.dumps({"k1": {"price_cents": 75.0, "first_at": "jam"}}),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            anomaly.MarketLineSnapshots(self.path)

    def test_validasi_record(self):
        with self.assertRaises(ValueError):
            self.snaps.record("", 227.5, 75.0, "2026-11-22T10:00:00+07:00")
        for bad_line in (0, -1, "227.5", None, float("nan")):
            with self.subTest(bad_line=bad_line), self.assertRaises(ValueError):
                self.snaps.record("k1", bad_line, 75.0, "2026-11-22T10:00:00+07:00")
        with self.assertRaises(ValueError):
            self.snaps.record("k1", 227.5, 0, "2026-11-22T10:00:00+07:00")
        with self.assertRaises(ValueError):
            self.snaps.record("k1", 227.5, 75.0, "")


class TestCheckTotalLineVsModel(unittest.TestCase):
    def test_market_lebih_tinggi_melewati_ambang(self):
        # gap = 227,5 - 218 = +9,5 > 5 -> anomali, arah berbahaya buat Under.
        hasil = anomaly.check_total_line_vs_model(218, 227.5, CFG_GARIS)
        self.assertIsNotNone(hasil)
        self.assertEqual(hasil["type"], "total_line_vs_model")
        self.assertEqual(hasil["direction"], "market_lebih_tinggi")
        self.assertAlmostEqual(hasil["gap_points"], 9.5)
        self.assertEqual(hasil["model_median_total"], 218.0)
        self.assertEqual(hasil["market_total_line"], 227.5)
        self.assertTrue(hasil["kenapa_beda_required"])

    def test_model_lebih_tinggi_melewati_ambang(self):
        # gap = 218 - 227,5 = -9,5 -> anomali arah sebaliknya.
        hasil = anomaly.check_total_line_vs_model(227.5, 218, CFG_GARIS)
        self.assertIsNotNone(hasil)
        self.assertEqual(hasil["type"], "total_line_vs_model")
        self.assertEqual(hasil["direction"], "model_lebih_tinggi")
        self.assertAlmostEqual(hasil["gap_points"], -9.5)
        self.assertTrue(hasil["kenapa_beda_required"])

    def test_tepat_di_ambang_bukan_anomali(self):
        # gap tepat 5,0 (kedua arah) -> bukan anomali (aturan "lebih dari").
        self.assertIsNone(anomaly.check_total_line_vs_model(220, 225, CFG_GARIS))
        self.assertIsNone(anomaly.check_total_line_vs_model(225, 220, CFG_GARIS))

    def test_di_bawah_ambang_bukan_anomali(self):
        self.assertIsNone(anomaly.check_total_line_vs_model(218, 219, CFG_GARIS))

    def test_input_none_bukan_anomali(self):
        self.assertIsNone(anomaly.check_total_line_vs_model(None, 227.5, CFG_GARIS))
        self.assertIsNone(anomaly.check_total_line_vs_model(218, None, CFG_GARIS))
        self.assertIsNone(anomaly.check_total_line_vs_model(None, None, CFG_GARIS))

    def test_validasi(self):
        for bad in (0, -5, "218", float("nan")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                anomaly.check_total_line_vs_model(bad, 227.5, CFG_GARIS)
        with self.assertRaises(ValueError):
            anomaly.check_total_line_vs_model(218, 0, CFG_GARIS)


class TestCheckCushionVsMarket(unittest.TestCase):
    def test_kasus_kunci_model_lolos_market_tidak(self):
        # KUNCI: model median 218, garis market 227,5, alt line 227,5,
        # bantalan adaptif tercatat 8 -> bantalan model 9,5 (lolos)
        # tapi bantalan market 0 -> ANOMALI.
        hasil = anomaly.check_cushion_vs_market(227.5, 218, 227.5, 8.0)
        self.assertIsNotNone(hasil)
        self.assertEqual(hasil["type"], "cushion_tidak_dikonfirmasi_market")
        self.assertAlmostEqual(hasil["model_cushion_points"], 9.5)
        self.assertAlmostEqual(hasil["market_cushion_points"], 0.0)
        self.assertEqual(hasil["required_cushion_points"], 8)
        self.assertEqual(hasil["alt_line"], 227.5)
        self.assertTrue(hasil["kenapa_beda_required"])

    def test_lolos_keduanya_bukan_anomali(self):
        # Model median 215, garis market 218, alt line 227,5 ->
        # bantalan market 9,5 >= 8 -> None.
        self.assertIsNone(anomaly.check_cushion_vs_market(227.5, 215, 218, 8.0))

    def test_bantalan_adaptif_12(self):
        # Bantalan adaptif tercatat 12 (laga menuntut lebih tebal):
        # bantalan model 12,5 lolos tapi bantalan market 10 -> ANOMALI.
        hasil = anomaly.check_cushion_vs_market(227.5, 215, 217.5, 12.0)
        self.assertIsNotNone(hasil)
        self.assertEqual(hasil["type"], "cushion_tidak_dikonfirmasi_market")
        self.assertAlmostEqual(hasil["model_cushion_points"], 12.5)
        self.assertAlmostEqual(hasil["market_cushion_points"], 10.0)
        self.assertEqual(hasil["required_cushion_points"], 12)

    def test_bantalan_adaptif_12_lolos_keduanya_bukan_anomali(self):
        # Bantalan adaptif 12 + bantalan market 12,5 >= 12 -> None.
        self.assertIsNone(anomaly.check_cushion_vs_market(227.5, 213, 215, 12.0))

    def test_model_cushion_kurang_bukan_urusan_fungsi_ini(self):
        # Bantalan model 6,5 < 8 -> urusan pemilihan garis, fungsi ini None
        # (walau bantalan market 2,5 juga kurang).
        self.assertIsNone(anomaly.check_cushion_vs_market(227.5, 221, 225, 8.0))

    def test_garis_none_bukan_anomali(self):
        self.assertIsNone(anomaly.check_cushion_vs_market(None, 218, 227.5, 8.0))
        self.assertIsNone(anomaly.check_cushion_vs_market(227.5, None, 227.5, 8.0))
        self.assertIsNone(anomaly.check_cushion_vs_market(227.5, 218, None, 8.0))

    def test_bantalan_none_tidak_bisa_dicek(self):
        # Bantalan adaptif tidak tercatat -> tidak bisa dicek -> None
        # (bukan anomali, bukan juga lolos — ketiadaan data).
        self.assertIsNone(anomaly.check_cushion_vs_market(227.5, 218, 227.5, None))

    def test_validasi(self):
        with self.assertRaises(ValueError):
            anomaly.check_cushion_vs_market(0, 218, 227.5, 8.0)
        with self.assertRaises(ValueError):
            anomaly.check_cushion_vs_market(227.5, 218, 227.5, "8")
        with self.assertRaises(ValueError):
            anomaly.check_cushion_vs_market(227.5, 218, 227.5, -1.0)


class TestCheckUnderSafety(unittest.TestCase):
    def test_model_optimis_harga_melawan(self):
        # Model optimis (p=0,80) + harga Under turun 4¢ -> anomali
        # model_optimis_harga_melawan + safe_confirmed False. Garis
        # sengaja rapat (gap 1, bantalan market 8,5) supaya hanya cek
        # harga yang memicu.
        hasil = anomaly.check_under_safety(0.80, 218, 219, 227.5, 8.0, -4.0, CFG_GARIS)
        self.assertFalse(hasil["safe_confirmed"])
        self.assertEqual(len(hasil["anomalies"]), 1)
        anomali = hasil["anomalies"][0]
        self.assertEqual(anomali["type"], "model_optimis_harga_melawan")
        self.assertEqual(anomali["p_model_under"], 0.80)
        self.assertEqual(anomali["price_delta_cents"], -4.0)
        self.assertTrue(anomali["kenapa_beda_required"])

    def test_semua_cek_lolos(self):
        # Garis rapat + bantalan terkonfirmasi + gerak harga kecil
        # -> safe_confirmed True, tanpa anomali.
        hasil = anomaly.check_under_safety(0.80, 218, 219, 227.5, 8.0, -1.0, CFG_GARIS)
        self.assertTrue(hasil["safe_confirmed"])
        self.assertEqual(hasil["anomalies"], [])

    def test_harga_turun_2_cent_bukan_anomali(self):
        # Turun 2¢ < ambang sharp 3¢ -> bukan anomali harga-melawan.
        hasil = anomaly.check_under_safety(0.80, 218, 219, 227.5, 8.0, -2.0, CFG_GARIS)
        self.assertTrue(hasil["safe_confirmed"])
        self.assertEqual(hasil["anomalies"], [])

    def test_anomali_garis_ikut_terkumpul(self):
        # Gap 9,5 + bantalan tak terkonfirmasi -> kedua anomali garis
        # terkumpul, safe_confirmed False (tanpa cek harga).
        hasil = anomaly.check_under_safety(
            0.60, 218, 227.5, 227.5, 8.0, None, CFG_GARIS
        )
        self.assertFalse(hasil["safe_confirmed"])
        jenis = [a["type"] for a in hasil["anomalies"]]
        self.assertIn("total_line_vs_model", jenis)
        self.assertIn("cushion_tidak_dikonfirmasi_market", jenis)

    def test_p_model_none_lewati_cek_harga(self):
        # p None -> cek harga-melawan dilewati walau harga turun 4¢;
        # cek garis tetap jalan (di sini lolos) -> aman.
        hasil = anomaly.check_under_safety(None, 218, 219, 227.5, 8.0, -4.0, CFG_GARIS)
        self.assertTrue(hasil["safe_confirmed"])
        self.assertEqual(hasil["anomalies"], [])

    def test_p_di_bawah_ambang_optimis_bukan_anomali(self):
        # p=0,65 < 0,70 -> model tidak cukup optimis, harga turun 4¢
        # bukan anomali harga-melawan.
        hasil = anomaly.check_under_safety(0.65, 218, 219, 227.5, 8.0, -4.0, CFG_GARIS)
        self.assertTrue(hasil["safe_confirmed"])
        self.assertEqual(hasil["anomalies"], [])

    def test_validasi(self):
        with self.assertRaises(ValueError):
            anomaly.check_under_safety(1.5, 218, 219, 227.5, 8.0, -4.0, CFG_GARIS)
        with self.assertRaises(ValueError):
            anomaly.check_under_safety(0.80, 218, 219, 227.5, 8.0, "turun", CFG_GARIS)


class TestIlustrasiGarisThunder(unittest.TestCase):
    """ILUSTRASI — garis market Thunder tidak diketahui, angka hipotetis.

    Garis total market pada laga Thunder yang sebenarnya TIDAK diketahui
    (user hanya memberi harga 75¢ -> 71¢). Tes di kelas ini memakai
    angka garis HIPOTETIS untuk mengilustrasikan cek garis — JANGAN
    pernah menyajikan angka ini sebagai data nyata laga Thunder.
    """

    def test_ilustrasi_garis_thunder_hipotetis(self):
        """ILUSTRASI (garis hipotetis, bukan data nyata laga Thunder):
        model median 218, garis market 227,5, alt line 227,5, bantalan
        adaptif tercatat 8 -> bantalan model 9,5 lolos tapi bantalan
        market 0 -> ANOMALI."""
        hasil = anomaly.check_cushion_vs_market(227.5, 218, 227.5, 8.0)
        self.assertIsNotNone(hasil)
        self.assertEqual(hasil["type"], "cushion_tidak_dikonfirmasi_market")


if __name__ == "__main__":
    unittest.main()
