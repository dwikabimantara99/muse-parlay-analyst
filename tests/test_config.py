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
        # Fondasi harga & pengali (keputusan user 2026-11-23 08:19
        # WIB): Asuransi x2 atau lebih dikit; x2,0 tetap menutup
        # total modal dengan split 50/50. Menggantikan rentang
        # 2,5–3,0 (filosofi lama yang menuntut di atas x2,5).
        self.assertEqual(ins["multiplier_min"], 2.0)
        self.assertEqual(ins["multiplier_max"], 2.5)
        self.assertEqual(ins["min_leg_prob"], 0.74)
        # Gate edge minimum Asuransi (insiden DEN 2026-11-23):
        # NILAI PROPOSAL (pola D12) — menunggu persetujuan user.
        self.assertEqual(ins["min_edge_pct"], 3.5)
        self.assertTrue(ins["must_cover_total_stake"])

    def test_tiket_utama(self):
        main = self.cfg["tickets"]["main"]
        # Profil user 2026-11-22 (Langkah 3): Utama x3–x4, maks x5.
        # Target lunak 3,5 per fondasi harga & pengali (keputusan
        # user 2026-11-23): Utama x3 atau lebih dikit; x4–x5 adalah
        # keberuntungan, bukan target (menggantikan lunak 4,0).
        self.assertEqual(main["multiplier_min"], 3.0)
        self.assertEqual(main["multiplier_max"], 5.0)
        self.assertEqual(main["target_multiplier_max"], 3.5)
        # Kriteria "yakin" Tahap 4 (USULAN): ambang p_final per kaki.
        self.assertEqual(main["yakin_min_leg_prob"], 0.75)
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

    # Label harga (keputusan user 2026-11-21, berlaku Tahap 3)
    def test_price_labels(self):
        pl = self.cfg["price_labels"]
        self.assertEqual(pl["diskon_min_ev_pct"], 2.0)
        self.assertEqual(pl["mahal_max_ev_pct"], -2.0)
        self.assertGreater(pl["diskon_min_ev_pct"], pl["mahal_max_ev_pct"])

    def test_optimizer_mahal(self):
        # Keputusan user 2026-11-21: kaki MAHAL tidak masuk Asuransi
        # kecuali user meminta eksplisit; boleh masuk Utama dgn label.
        opt = self.cfg["optimizer"]
        self.assertTrue(opt["exclude_mahal_from_insurance"])
        self.assertTrue(opt["allow_mahal_in_main"])
        self.assertTrue(opt["mahal_label_required_in_main"])

    # §7a — filter keras
    def test_filter_semua_pasar(self):
        f = self.cfg["filters"]["all_markets"]
        self.assertTrue(f["exclude_data_incomplete"])
        # Keputusan user 2026-11-21: EV < -2% BUKAN lagi filter keras
        # (mengganti §7a) — kaki MAHAL tetap tampil dengan label.
        self.assertNotIn("min_ev_pct", f)

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
        # Bantalan kaku D10 (8/12 berbasis spread) + lantai market+8
        # DIHAPUS di versi 13 — digantikan bantalan adaptif (analis)
        # + syarat "di atas Utama" + harga minimum + volume.
        for kunci_mati in (
            "min_cushion_points",
            "min_cushion_points_close_spread",
            "close_spread_threshold",
            "market_cushion_floor_points",
        ):
            self.assertNotIn(kunci_mati, f)
        # Target peluang Asuransi TETAP 0,74.
        self.assertEqual(f["insurance_target_probability"], 0.74)

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
        # Keputusan user 2026-11-21: kalibrasi membandingkan Brier
        # model vs pasar; kenaikan w hanya atas persetujuan user.
        self.assertTrue(self.cfg["calibration"]["compare_brier_model_vs_market"])

    def test_simulasi_nba_sudah_difit_bola_masih_tbd(self):
        # D12: parameter NBA diisi dari HASIL FIT 2026-11-22 (2701 laga,
        # lihat LAPORAN-FIT-NBA.md) — bukan tebakan. Parameter bola
        # tetap null sampai difit (Tahap 3 langkah 5).
        sim = self.cfg["simulation"]
        nba = sim["nba"]
        for kunci in (
            "sigma_points",
            "sigma_margin_points",
            "sigma_total_points",
            "t_nu",
            "home_advantage_points",
            "back_to_back_penalty_points",
            "altitude_adjustment_points",
        ):
            self.assertIsInstance(nba[kunci], (int, float), kunci)
        self.assertGreater(nba["sigma_margin_points"], 0)
        self.assertGreater(nba["sigma_total_points"], 0)
        self.assertGreater(nba["t_nu"], 2)
        # B2B bertanda negatif (tim B2B mencetak lebih sedikit).
        self.assertLess(nba["back_to_back_penalty_points"], 0)
        # Asumsi awal yang didokumentasikan (BELUM difit — lihat yaml).
        self.assertEqual(nba["bpm_scale"], 1.0)
        self.assertEqual(nba["tournament_adjustment_points"], 0.0)
        self.assertEqual(nba["recency"], {"season": 0.6, "last10": 0.4})
        self.assertEqual(nba["ot_max_periods"], 5)
        self.assertIsNone(sim["football"]["dixon_coles_rho"])
        fitting = sim["fitting"]
        self.assertEqual(fitting["history_seasons"], "2-3")
        self.assertEqual(fitting["football_rho_method"], "MLE per liga")
        self.assertTrue(fitting["requires_user_approval"])
        self.assertEqual(fitting["min_games_total"], 100)
        self.assertEqual(fitting["min_group_n"], 30)

    def test_meta_versi_15(self):
        # Versi 15: skenario setan (deviasi maksimal 3PM, deteksi
        # kerapuhan — BUKAN gate; koreksi user 2026-11-23 09:52 WIB)
        # — di atas versi 14 (fondasi harga & pengali + gate edge
        # Asuransi 3,5% PROPOSAL, insiden DEN).
        meta = self.cfg["meta"]
        self.assertEqual(meta["version"], 15)
        self.assertEqual(meta["last_reviewed"], "2026-11-23")

    def test_analis_section(self):
        # Section analis (v13): harga minimum kaki + parameter rumus
        # bantalan adaptif + parameter nilai wajar. Bobot bantalan
        # NILAI AWAL — BELUM DIKALIBRASI, lihat komentar di yaml.
        analis = self.cfg["analis"]
        self.assertEqual(analis["harga_min_utama_cents"], 75)
        self.assertEqual(analis["harga_min_asuransi_cents"], 75)
        bantalan = analis["cushion"]
        self.assertEqual(bantalan["acuan_points"], 8.0)
        self.assertEqual(bantalan["std_factor"], 0.42)
        self.assertEqual(bantalan["ortg_weight"], 0.5)
        self.assertEqual(bantalan["form_weight"], 0.25)
        self.assertEqual(bantalan["min_points"], 4.0)
        self.assertEqual(bantalan["max_points"], 20.0)
        self.assertGreater(bantalan["max_points"], bantalan["min_points"])
        self.assertEqual(analis["wajar"]["selisih_minimum_poin"], 0.0)

    def test_soccer_section(self):
        # Wiring otak bola (Langkah 5): section soccer + jendela hasil.
        # Parameter fit TETAP null (D12 — belum difit/disetujui).
        soccer = self.cfg["soccer"]
        self.assertEqual(soccer["leagues_supported"], ["EPL"])
        self.assertEqual(soccer["fit_params_path"], "out/fit_soccer_params.json")
        self.assertTrue(soccer["fit_requires_approval"])
        fb = self.cfg["simulation"]["football"]
        self.assertEqual(fb["results_window_days"], 150)
        self.assertIsNone(fb["dixon_coles_rho"])
        self.assertIsNone(fb["home_advantage_by_league"])
        self.assertIsNone(fb["absence_penalty"])

    def test_live_section(self):
        # Ambang pantauan live (Langkah 4) — NILAI AWAL, BELUM
        # DIKALIBRASI, lihat komentar di yaml.
        live = self.cfg["live"]
        self.assertEqual(live["status_margin_aman_points"], 6.0)
        self.assertEqual(live["status_margin_waspada_points"], 2.0)
        self.assertEqual(live["ot_risk_margin_points"], 3)
        self.assertEqual(live["ot_risk_minutes_remaining"], 2.0)
        self.assertEqual(live["anomaly_min_minutes_elapsed"], 12)
        self.assertEqual(live["anomaly_fg3_rate_multiplier"], 1.5)
        self.assertEqual(live["anomaly_ft_rate_multiplier"], 1.5)
        self.assertEqual(live["anomaly_scoring_rate_multiplier"], 1.15)

    def test_shrinkage_k_games(self):
        # Shrinkage menit+BPM ke musim lalu (temuan auditor 2):
        # w = n/(n+K); K=10 pilihan desain mengikuti D-R2, bukan fit.
        self.assertEqual(self.cfg["simulation"]["nba"]["shrinkage_k_games"], 10)

    def test_recheck_section(self):
        # Ambang recheck Langkah 2: garis market bergerak > 2 poin ->
        # hitung ulang simulasi + garis. Ambang harga 3¢ dipakai ulang
        # dari anomaly.sharp_move_cents (aturan Thunder).
        recheck = self.cfg["recheck"]
        self.assertEqual(recheck["market_line_move_points"], 2.0)
        self.assertEqual(self.cfg["anomaly"]["sharp_move_cents"], 3)

    def test_fees_kalshi(self):
        # Koefisien fee taker Kalshi (Fee Schedule resmi, 7 Jul 2026).
        self.assertEqual(self.cfg["fees"]["kalshi_taker_fee_coeff"], 0.07)

    def test_fees_jup_markup(self):
        # Markup tipikal jup.ag: median terukur 0,5¢ (probe tambahan 3).
        self.assertEqual(self.cfg["fees"]["jup_typical_markup_cents"], 0.5)

    def test_market_line_check_nilai_awal(self):
        # NILAI AWAL, BELUM DIKALIBRASI — lihat komentar di yaml.
        mlc = self.cfg["market_line_check"]
        self.assertEqual(mlc["total_gap_points"], 5.0)
        self.assertEqual(mlc["min_model_under_prob"], 0.70)

    def test_polymarket_ladder_min_volume(self):
        # HEURISTIK AWAL — lihat komentar di yaml.
        self.assertEqual(self.cfg["polymarket_ladder"]["min_volume_usd"], 100.0)


class TestGetValue(unittest.TestCase):
    def test_ambil_nilai_bersarang(self):
        cfg = config.load_playstyle()
        # Nilai contoh: multiplier_min Asuransi (2,0 sejak fondasi
        # harga & pengali 2026-11-23, dulu 2,5).
        self.assertEqual(
            config.get_value(cfg, "tickets", "insurance", "multiplier_min"),
            2.0,
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
        # batas 500 kredit/bulan, peringatan di 80%.
        src = config.load_sources()
        limits = src["sources"]["comparison_prices"]["odds_api_limits"]
        self.assertEqual(limits["monthly_credit_limit"], 500)
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
