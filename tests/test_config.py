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

    def test_stake_split_default_50_50(self):
        # D13: modal default 50/50.
        self.assertEqual(
            self.cfg["tickets"]["stake_split_default"],
            {"insurance": 0.5, "main": 0.5},
        )

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
        # D9: harga bergerak tajam = berubah >= 3¢ sejak pengambilan pertama.
        self.assertEqual(anom["sharp_move_cents"], 3)

    # Aturan pembanding independen (DECISIONS.md P1-P3)
    def test_comparison(self):
        comp = self.cfg["comparison"]
        self.assertTrue(comp["record_origin_provider"])
        self.assertTrue(comp["forbid_same_provider"])
        self.assertEqual(
            comp["allowed_comparison_sources"],
            ["other_prediction_provider", "sportsbook_devig"],
        )
        # Urutan pembanding p_market (keputusan user 2026-11-20, pasca 2a).
        self.assertEqual(
            comp["order"],
            ["odds_api_devig", "espn_odds_devig", "kalshi"],
        )

    # D2 — MODEL_ONLY
    def test_model_only(self):
        mo = self.cfg["model_only"]
        self.assertTrue(mo["p_final_equals_p_model"])
        self.assertEqual(mo["threshold_penalty_points"], 5)
        self.assertEqual(mo["max_legs_per_ticket"], 1)
        self.assertTrue(mo["banned_from_insurance"])

    # B4 — TANPA_XG
    def test_no_xg(self):
        nx = self.cfg["no_xg"]
        self.assertEqual(nx["label"], "TANPA_XG")
        self.assertEqual(nx["fallback_model"], "Dixon-Coles berbasis gol")
        self.assertEqual(nx["threshold_penalty_points"], 5)
        self.assertTrue(nx["banned_from_insurance"])

    # D7/D8 — rumus
    def test_formulas(self):
        formulas = self.cfg["formulas"]
        self.assertIn("p_akhir", formulas["leg_ev"])
        self.assertIn("spread_pct", formulas["combo_multiplier"])
        self.assertIn("pengali", formulas["ticket_ev"])

    # D14 — mata uang
    def test_currency(self):
        self.assertEqual(self.cfg["currency"]["base"], "USD")
        self.assertEqual(self.cfg["currency"]["usdc_to_usd"], 1.0)

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
        # D10: bantalan = garis Alt Under - median proyeksi total.
        self.assertEqual(f["min_cushion_points"], 8)
        self.assertEqual(f["min_cushion_points_close_spread"], 12)
        self.assertEqual(f["close_spread_threshold"], 2.5)

    def test_filter_btts(self):
        self.assertEqual(
            self.cfg["filters"]["football_btts_yes"]["min_combined_xg"], 2.45
        )

    def test_filter_lineup_bola(self):
        f = self.cfg["filters"]["football_lineup"]
        self.assertEqual(f["lineup_missing_minutes_before_kickoff"], 60)
        # D11: definisi pemain kunci bola.
        key_def = f["key_player_definition"]
        self.assertEqual(key_def["goalkeeper"], "kiper utama")
        self.assertEqual(key_def["centre_backs"], "2 bek tengah dengan menit terbanyak")
        self.assertEqual(key_def["top_attacker"], "pemain xG+xA terbanyak")
        self.assertEqual(key_def["minutes_threshold_pct"], 70)

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
        # B2: cedera & lineup dicek silang min 2 sumber.
        self.assertEqual(self.cfg["data"]["cross_check_min_sources_injury_lineup"], 2)
        self.assertEqual(self.cfg["calibration"]["report_every_legs"], 50)

    def test_simulasi_tetap_tbd_sampai_fit(self):
        # D12: parameter simulasi tetap null sampai di-fit dari data historis
        # dan disetujui user — tidak boleh ditebak.
        sim = self.cfg["simulation"]
        self.assertIsNone(sim["nba"]["sigma_points"])
        self.assertIsNone(sim["nba"]["home_advantage_points"])
        self.assertIsNone(sim["football"]["dixon_coles_rho"])
        fitting = sim["fitting"]
        self.assertEqual(fitting["history_seasons"], "2-3")
        self.assertEqual(fitting["football_rho_method"], "MLE per liga")
        self.assertTrue(fitting["requires_user_approval"])


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
            # Tiap jenis data punya daftar kandidat berjenjang (DECISIONS.md B).
            candidates = kinds[kind]["candidates"]
            self.assertGreaterEqual(len(candidates), 1)
            for cand in candidates:
                self.assertIn(cand["tier"], (1, 2, 3))
                self.assertIn("name", cand)

    def test_jenjang_tertinggi_didahulukan(self):
        # NBA: stats.nba.com jenjang 1 (UTAMA, probe 2a: bekerja dari VM).
        # Bola: situs resmi liga jenjang 1.
        src = config.load_sources()
        nba = src["sources"]["nba_schedule_stats"]["candidates"]
        self.assertEqual(nba[0]["name"], "stats.nba.com")
        self.assertEqual(nba[0]["tier"], 1)
        bola = src["sources"]["football_stats_xg"]["candidates"]
        self.assertEqual(bola[0]["tier"], 1)

    def test_batas_odds_api(self):
        # D3: cache 30 menit, maks 2 panggilan/analisis, region eu (Pinnacle),
        # batas 450 kredit/bulan, peringatan di 80%.
        src = config.load_sources()
        limits = src["sources"]["comparison_prices"]["odds_api_limits"]
        self.assertEqual(limits["monthly_credit_limit"], 450)
        self.assertEqual(limits["warn_at_pct"], 80)
        self.assertEqual(limits["cache_minutes"], 30)
        self.assertEqual(limits["max_calls_per_analysis"], 2)
        self.assertEqual(limits["region"], "eu")
        self.assertEqual(limits["bookmaker"], "Pinnacle")

    def test_aturan_sumber(self):
        src = config.load_sources()
        rules = src["rules"]
        self.assertTrue(rules["use_highest_tier_available"])
        self.assertTrue(rules["record_tier_source_time"])
        self.assertEqual(rules["cross_check_min_sources_injury_lineup"], 2)
        self.assertTrue(rules["show_conflicting_sources"])
        self.assertEqual(rules["all_sources_dead"], "DATA_INCOMPLETE")
        # B4 pasca probe 2a: FotMob + Sofascore ditolak, rantai tinggal
        # resmi -> Understat; tanpa xG berlaku TANPA_XG.
        self.assertEqual(rules["xg_chain"], ["resmi", "Understat"])

    def test_urutan_pembanding(self):
        # Urutan p_market: Odds API -> ESPN odds -> Kalshi -> Polymarket
        # (Polymarket terakhir + hanya untuk pasar bukan asal Polymarket).
        src = config.load_sources()
        names = [c["name"] for c in src["sources"]["comparison_prices"]["candidates"]]
        self.assertEqual(
            names,
            ["The Odds API", "ESPN odds", "Kalshi API", "Polymarket API"],
        )

    def test_sumber_ditolak(self):
        # FotMob (ToS) + Sofascore (403) ada di daftar rejected dengan
        # alasan, dan TIDAK muncul di kandidat sumber mana pun.
        src = config.load_sources()
        rejected = {r["name"]: r for r in src["rejected"]}
        self.assertIn("FotMob", rejected)
        self.assertIn("Sofascore", rejected)
        for entry in rejected.values():
            self.assertIn("reason", entry)
            self.assertTrue(entry["reason"])
            self.assertIn("rejected_on", entry)
        for kind in src["sources"].values():
            names = [c["name"] for c in kind["candidates"]]
            self.assertNotIn("FotMob", names)
            self.assertNotIn("Sofascore", names)

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
