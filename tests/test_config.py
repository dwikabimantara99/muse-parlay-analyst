"""Tes loader config + isi playstyle.yaml & sources.yaml.

Setiap angka di sini dicocokkan dengan Blueprint — kalau ada yang berubah di
yaml tanpa alasan, tes ini yang pertama berteriak.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config


class TestPlaystyle(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load_playstyle()

    def test_semua_bagian_wajib_ada(self):
        for section in config.REQUIRED_PLAYSTYLE_SECTIONS:
            self.assertIn(section, self.cfg)

    # §6a — dua tiket
    def test_tiket_asuransi(self):
        ins = self.cfg["tickets"]["insurance"]
        self.assertEqual(ins["multiplier_min"], 2.20)
        self.assertEqual(ins["multiplier_max"], 2.50)
        self.assertEqual(ins["min_leg_prob"], 0.74)
        self.assertTrue(ins["must_cover_total_stake"])

    def test_tiket_utama(self):
        main = self.cfg["tickets"]["main"]
        self.assertEqual(main["multiplier_min"], 3.5)
        self.assertEqual(main["multiplier_max"], 6.0)
        self.assertEqual(main["min_leg_prob"], 0.65)

    def test_mode_default_standard(self):
        self.assertEqual(self.cfg["tickets"]["mode"], "standard")

    # §6c — optimizer
    def test_optimizer(self):
        opt = self.cfg["optimizer"]
        self.assertEqual(opt["sort_by"], ["p_total_loss_asc", "combined_ev_desc"])
        self.assertEqual(opt["top_options"], 3)
        self.assertEqual(
            opt["top_option_labels"], ["Paling aman", "Seimbang", "Agresif"]
        )

    # §6d — combo
    def test_combo_spread(self):
        self.assertEqual(self.cfg["combo"]["spread_cut_pct"], 5.5)

    # §5c — blend
    def test_blend_w(self):
        self.assertEqual(self.cfg["blend"]["w_model"], 0.3)

    # §5d — anomali
    def test_anomali(self):
        anom = self.cfg["anomaly"]
        self.assertEqual(anom["jup_vs_market_points"], 4.0)
        self.assertEqual(anom["model_vs_market_points"], 8.0)
        # Ambang "harga bergerak tajam" tidak ada di blueprint -> null (TBD),
        # bukan angka karangan.
        self.assertIsNone(anom["sharp_move_points"])

    # §7a — filter keras
    def test_filter_semua_pasar(self):
        f = self.cfg["filters"]["all_markets"]
        self.assertTrue(f["exclude_data_incomplete"])
        self.assertEqual(f["min_ev_pct"], -2.0)

    def test_filter_moneyline(self):
        f = self.cfg["filters"]["moneyline"]
        self.assertEqual(f["min_p_final"], 0.65)
        self.assertTrue(f["allow_below_min_in_aggressive"])
        self.assertTrue(f["aggressive_label_required"])

    def test_filter_nba_alt_under(self):
        f = self.cfg["filters"]["nba_alt_under"]
        self.assertEqual(f["drtg_bad_rank_from"], 23)
        self.assertEqual(f["drtg_bad_rank_to"], 30)
        self.assertEqual(f["both_top_pace_n"], 10)
        self.assertEqual(f["spread_no_cushion_max"], 2.5)
        # "Bantalan ekstra" tidak didefinisikan di blueprint -> null (TBD).
        self.assertIsNone(f["extra_cushion_points"])

    def test_filter_btts(self):
        self.assertEqual(
            self.cfg["filters"]["football_btts_yes"]["min_combined_xg"], 2.45
        )

    def test_filter_lineup_bola(self):
        f = self.cfg["filters"]["football_lineup"]
        self.assertEqual(f["lineup_missing_minutes_before_kickoff"], 60)
        self.assertIsNone(f["key_player_definition"])

    # §5 — simulasi
    def test_simulasi(self):
        sim = self.cfg["simulation"]
        self.assertEqual(sim["iterations"], 100000)
        self.assertEqual(sim["nba"]["distribution"], "student-t")
        self.assertEqual(sim["nba"]["overtime_minutes"], 5)
        self.assertEqual(
            sim["nba"]["squad_scenarios"],
            ["full", "missing_1", "missing_2", "missing_4"],
        )
        self.assertEqual(sim["football"]["model"], "dixon-coles")
        self.assertEqual(sim["football"]["xg_weight_season"], 0.60)
        self.assertEqual(sim["football"]["xg_weight_recent"], 0.40)

    # §4 — data, §9 — kalibrasi
    def test_data_dan_kalibrasi(self):
        self.assertEqual(self.cfg["data"]["stale_hours_injury_lineup"], 3)
        self.assertEqual(self.cfg["data"]["recheck_window_minutes"], [30, 60])
        self.assertEqual(self.cfg["calibration"]["report_every_legs"], 50)


class TestGetValue(unittest.TestCase):
    def test_ambil_nilai_bersarang(self):
        cfg = config.load_playstyle()
        self.assertEqual(
            config.get_value(cfg, "tickets", "insurance", "multiplier_min"),
            2.20,
        )

    def test_kunci_hilang_melempar(self):
        cfg = config.load_playstyle()
        with self.assertRaises(config.ConfigError):
            config.get_value(cfg, "tickets", "tidak_ada")

    def test_file_hilang_melempar(self):
        with self.assertRaises(config.ConfigError):
            config.load_playstyle("/tmp/tidak-ada-playstyle.yaml")


class TestSources(unittest.TestCase):
    def test_semua_jenis_data_ada(self):
        src = config.load_sources()
        kinds = src["sources"]
        for kind in (
            "jup_prices",
            "comparison_prices",
            "nba_schedule_stats",
            "nba_injuries",
            "nba_player_impact",
            "football_stats_xg",
            "football_lineup_injuries",
        ):
            self.assertIn(kind, kinds)
            self.assertIn("primary", kinds[kind])
            self.assertIn("fallback", kinds[kind])

    def test_tidak_ada_api_key_di_sources(self):
        # API key hanya di .env — pastikan tidak ada nilai key di sources.yaml.
        text = config.DEFAULT_SOURCES_PATH.read_text(encoding="utf-8")
        self.assertNotIn("sk-", text)
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("env_key:"):
                value = stripped.split(":", 1)[1].strip()
                # Hanya nama variabel env (atau null), bukan nilai key.
                self.assertTrue(value in ("null", "") or value.isupper())


if __name__ == "__main__":
    unittest.main()
