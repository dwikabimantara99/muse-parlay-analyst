"""Tes engine/validation.py + scripts/validate_nba_model.py.

Tes unit memakai data sintetis yang bisa dihitung tangan (termasuk
bucket kosong, n=0). Tes ujung-ke-ujung kecil menjalankan fungsi
backtest pada 3 laga sintetis dengan iterasi kecil. TANPA network —
backtest penuh (150 laga, 100.000x) BUKAN bagian suite, itu run script.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine import nba_sim, validation

REPO_ROOT = Path(__file__).resolve().parent.parent

_SPEK = importlib.util.spec_from_file_location(
    "validate_nba_model", REPO_ROOT / "scripts" / "validate_nba_model.py"
)
validate_nba_model = importlib.util.module_from_spec(_SPEK)
_SPEK.loader.exec_module(validate_nba_model)


class TestBrierScore(unittest.TestCase):
    def test_tebakan_50_persen(self):
        # (0,5-1)^2 = 0,25 dan (0,5-0)^2 = 0,25 -> rata-rata 0,25.
        self.assertAlmostEqual(
            validation.brier_score([(0.5, True), (0.5, False)]), 0.25
        )

    def test_sempurna(self):
        self.assertAlmostEqual(validation.brier_score([(1.0, True), (0.0, False)]), 0.0)

    def test_salah_total(self):
        self.assertAlmostEqual(validation.brier_score([(1.0, False), (0.0, True)]), 1.0)

    def test_hitung_tangan(self):
        # (0,8-0)^2 = 0,64; (0,2-1)^2 = 0,64 -> rata-rata 0,64.
        self.assertAlmostEqual(
            validation.brier_score([(0.8, False), (0.2, True)]), 0.64
        )

    def test_terjadi_int_0_1_diterima(self):
        self.assertAlmostEqual(validation.brier_score([(0.5, 1), (0.5, 0)]), 0.25)

    def test_validasi_input(self):
        with self.assertRaises(ValueError):
            validation.brier_score([])
        with self.assertRaises(ValueError):
            validation.brier_score([(1.5, True)])
        with self.assertRaises(ValueError):
            validation.brier_score([(-0.1, False)])
        with self.assertRaises(ValueError):
            validation.brier_score([(0.5, "ya")])
        with self.assertRaises(ValueError):
            validation.brier_score([(0.5,)])


class TestReliabilityBuckets(unittest.TestCase):
    def test_hitung_tangan_dan_bucket_kosong(self):
        pairs = [
            (0.05, True),
            (0.15, False),
            (0.15, True),
            (0.85, True),
            (0.95, False),
        ]
        buckets = validation.reliability_buckets(pairs, n_buckets=10)
        self.assertEqual(len(buckets), 10)
        # Bucket 0 [0, 0.1): satu anggota, prediksi 0,05, terjadi.
        self.assertEqual(buckets[0]["n"], 1)
        self.assertAlmostEqual(buckets[0]["mean_prediksi"], 0.05)
        self.assertAlmostEqual(buckets[0]["frekuensi_aktual"], 1.0)
        # Bucket 1 [0.1, 0.2): dua anggota, mean 0,15, satu terjadi.
        self.assertEqual(buckets[1]["n"], 2)
        self.assertAlmostEqual(buckets[1]["mean_prediksi"], 0.15)
        self.assertAlmostEqual(buckets[1]["frekuensi_aktual"], 0.5)
        # Bucket 8 dan 9: masing-masing satu anggota.
        self.assertEqual(buckets[8]["n"], 1)
        self.assertAlmostEqual(buckets[8]["frekuensi_aktual"], 1.0)
        self.assertEqual(buckets[9]["n"], 1)
        self.assertAlmostEqual(buckets[9]["frekuensi_aktual"], 0.0)
        # Bucket 2-7 KOSONG: tetap dicatat dengan n=0, bukan dihilangkan.
        for i in range(2, 8):
            self.assertEqual(buckets[i]["n"], 0)
            self.assertIsNone(buckets[i]["mean_prediksi"])
            self.assertIsNone(buckets[i]["frekuensi_aktual"])
            self.assertEqual(
                buckets[i]["bucket"], (round(i / 10, 6), round((i + 1) / 10, 6))
            )

    def test_batas_p_0_dan_p_1(self):
        # p=0.0 masuk bucket pertama, p=1.0 masuk bucket terakhir.
        buckets = validation.reliability_buckets(
            [(0.0, False), (1.0, True)], n_buckets=10
        )
        self.assertEqual(buckets[0]["n"], 1)
        self.assertEqual(buckets[9]["n"], 1)

    def test_jumlah_bucket_sesuai(self):
        buckets = validation.reliability_buckets([(0.5, True)], n_buckets=4)
        self.assertEqual(len(buckets), 4)
        self.assertEqual(buckets[2]["n"], 1)  # 0,5 masuk [0.5, 0.75)
        with self.assertRaises(ValueError):
            validation.reliability_buckets([(0.5, True)], n_buckets=0)


class TestCalibrationSummary(unittest.TestCase):
    def test_hitung_tangan(self):
        pairs = [(0.2, True), (0.4, False), (0.6, True), (0.8, False)]
        ringkasan = validation.calibration_summary(pairs)
        self.assertEqual(ringkasan["n"], 4)
        self.assertAlmostEqual(ringkasan["mean_prediksi"], 0.5)
        self.assertAlmostEqual(ringkasan["frekuensi_aktual"], 0.5)
        # Brier: (0,64+0,16+0,16+0,64)/4 = 0,4.
        self.assertAlmostEqual(ringkasan["brier"], 0.4)
        self.assertEqual(len(ringkasan["buckets"]), 10)

    def test_overconfident_terlihat(self):
        # Model yakin 90% tapi hanya 1 dari 4 yang terjadi.
        pairs = [(0.9, True), (0.9, False), (0.9, False), (0.9, False)]
        ringkasan = validation.calibration_summary(pairs)
        self.assertAlmostEqual(ringkasan["mean_prediksi"], 0.9)
        self.assertAlmostEqual(ringkasan["frekuensi_aktual"], 0.25)
        bucket = ringkasan["buckets"][9]
        self.assertEqual(bucket["n"], 4)
        self.assertAlmostEqual(bucket["frekuensi_aktual"], 0.25)


def _rating_sintetis() -> dict:
    """Rating sintetis 4 tim, satu musim."""
    return {
        "2025-26": {
            "ATL": {"off_rtg": 114.0, "def_rtg": 112.0, "net_rtg": 2.0, "pace": 100.0},
            "DET": {"off_rtg": 115.0, "def_rtg": 110.0, "net_rtg": 5.0, "pace": 99.0},
            "BOS": {"off_rtg": 116.0, "def_rtg": 109.0, "net_rtg": 7.0, "pace": 98.0},
            "NYK": {"off_rtg": 113.0, "def_rtg": 111.0, "net_rtg": 2.0, "pace": 97.0},
        }
    }


def _laga_sintetis() -> list[dict]:
    """3 laga sintetis (tanggal berjauhan — tidak ada B2B)."""
    return [
        {
            "season": "2025-26",
            "game_date": "2025-11-01",
            "game_id": "0022500001",
            "home_tricode": "ATL",
            "away_tricode": "DET",
            "home_pts": 110,
            "away_pts": 105,
        },
        {
            "season": "2025-26",
            "game_date": "2025-11-05",
            "game_id": "0022500002",
            "home_tricode": "BOS",
            "away_tricode": "NYK",
            "home_pts": 98,
            "away_pts": 102,
        },
        {
            "season": "2025-26",
            "game_date": "2025-11-09",
            "game_id": "0022500003",
            "home_tricode": "DET",
            "away_tricode": "BOS",
            "home_pts": 120,
            "away_pts": 120 - 15,
        },
    ]


class TestBacktestKecil(unittest.TestCase):
    def test_ujung_ke_ujung_3_laga(self):
        cfg = config_mod.load_playstyle()
        games = _laga_sintetis()
        hasil = validate_nba_model.jalankan_backtest(
            games, games, _rating_sintetis(), cfg, iterations=200
        )
        self.assertEqual(hasil["n_laga"], 3)
        self.assertEqual(hasil["n_dilewati"], 0)
        self.assertGreaterEqual(hasil["waktu_detik"], 0.0)
        per_laga = hasil["hasil_per_laga"]
        self.assertEqual(len(per_laga), 3)
        for record, game in zip(per_laga, games, strict=True):
            self.assertEqual(record["game_id"], game["game_id"])
            self.assertTrue(0.0 <= record["p_home_win"] <= 1.0)
            self.assertTrue(0.0 <= record["p_under"] <= 1.0)
            # Aktual harus cocok dengan skor sintetis.
            self.assertEqual(
                record["actual_home_win"],
                game["home_pts"] > game["away_pts"],
            )
            self.assertEqual(
                record["actual_under"],
                game["home_pts"] + game["away_pts"] < record["garis_under"],
            )
            # Garis = median+8 dibulatkan ke 0,5 (selisih maks 0,25).
            self.assertLessEqual(
                abs(record["garis_under"] - (record["median_total"] + 8.0)),
                0.25 + 1e-9,
            )

    def test_deterministik_seed_game_id(self):
        cfg = config_mod.load_playstyle()
        games = _laga_sintetis()
        ratings = _rating_sintetis()
        hasil1 = validate_nba_model.jalankan_backtest(
            games, games, ratings, cfg, iterations=200
        )
        hasil2 = validate_nba_model.jalankan_backtest(
            games, games, ratings, cfg, iterations=200
        )
        for r1, r2 in zip(
            hasil1["hasil_per_laga"], hasil2["hasil_per_laga"], strict=True
        ):
            self.assertEqual(r1["p_home_win"], r2["p_home_win"])
            self.assertEqual(r1["p_under"], r2["p_under"])

    def test_laga_tanpa_rating_dilewati(self):
        cfg = config_mod.load_playstyle()
        games = _laga_sintetis()
        games_tanpa_rating = games + [
            {
                "season": "2025-26",
                "game_date": "2025-11-12",
                "game_id": "0022500004",
                "home_tricode": "XXX",
                "away_tricode": "ATL",
                "home_pts": 100,
                "away_pts": 99,
            }
        ]
        hasil = validate_nba_model.jalankan_backtest(
            games_tanpa_rating,
            games_tanpa_rating,
            _rating_sintetis(),
            cfg,
            iterations=200,
        )
        self.assertEqual(hasil["n_laga"], 3)
        self.assertEqual(hasil["n_dilewati"], 1)
        self.assertEqual(hasil["dilewati"][0]["game_id"], "0022500004")


class TestPilihSubset(unittest.TestCase):
    def test_terbaru_per_musim(self):
        games = []
        for musim, tahun in (("2024-25", "2025"), ("2025-26", "2026")):
            for hari in range(1, 8):
                games.append(
                    {
                        "season": musim,
                        "game_date": f"{tahun}-01-0{hari}",
                        "game_id": f"{musim}-{hari}",
                    }
                )
        subset = validate_nba_model.pilih_subset(games, per_musim=3)
        self.assertEqual(len(subset), 6)
        tanggal = [g["game_date"] for g in subset]
        self.assertEqual(
            tanggal,
            [
                "2025-01-05",
                "2025-01-06",
                "2025-01-07",
                "2026-01-05",
                "2026-01-06",
                "2026-01-07",
            ],
        )


# --- Backtest rolling point-in-time (patch 1b) ---

_SPEK_FIT = importlib.util.spec_from_file_location(
    "fit_nba_params_rolling", REPO_ROOT / "scripts" / "fit_nba_params.py"
)
fit_nba_params = importlib.util.module_from_spec(_SPEK_FIT)
_SPEK_FIT.loader.exec_module(fit_nba_params)


def _record_boxscore_validasi(
    game_id,
    tanggal,
    tricode,
    lawan,
    kandang,
    pts,
    poss,
    pts_lawan,
    poss_lawan,
    menit=240.0,
):
    """Satu record team-game untuk fixture rolling validasi."""
    return {
        "season": "2025-26",
        "game_id": game_id,
        "game_date": tanggal,
        "tricode": tricode,
        "opp_tricode": lawan,
        "is_home": kandang,
        "pts": pts,
        "poss": poss,
        "pts_lawan": pts_lawan,
        "poss_lawan": poss_lawan,
        "minutes": menit,
    }


def _boxscore_validasi():
    """Box score akhir Okt 2025 untuk ke-4 tim laga sintetis.

    Tiap tim 2 laga sebelum 1 Nov 2025 (poss ~100, angka sintetis
    yang konsisten: off_rtg sekitar pts yang dicetak).
    """
    records = []
    # 28 Okt: ATL 110 - 100 BOS; DET 105 - 108 NYK.
    records.append(
        _record_boxscore_validasi(
            "v-okt28a", "2025-10-28", "ATL", "BOS", True, 110, 100.8, 100, 97.9
        )
    )
    records.append(
        _record_boxscore_validasi(
            "v-okt28a", "2025-10-28", "BOS", "ATL", False, 100, 97.9, 110, 100.8
        )
    )
    records.append(
        _record_boxscore_validasi(
            "v-okt28b", "2025-10-28", "DET", "NYK", True, 105, 99.5, 108, 101.2
        )
    )
    records.append(
        _record_boxscore_validasi(
            "v-okt28b", "2025-10-28", "NYK", "DET", False, 108, 101.2, 105, 99.5
        )
    )
    # 30 Okt: BOS 112 - 104 NYK; DET 98 - 110 ATL.
    records.append(
        _record_boxscore_validasi(
            "v-okt30a", "2025-10-30", "BOS", "NYK", True, 112, 101.0, 104, 99.0
        )
    )
    records.append(
        _record_boxscore_validasi(
            "v-okt30a", "2025-10-30", "NYK", "BOS", False, 104, 99.0, 112, 101.0
        )
    )
    records.append(
        _record_boxscore_validasi(
            "v-okt30b", "2025-10-30", "DET", "ATL", True, 98, 98.0, 110, 100.0
        )
    )
    records.append(
        _record_boxscore_validasi(
            "v-okt30b", "2025-10-30", "ATL", "DET", False, 110, 100.0, 98, 98.0
        )
    )
    return records


def _prior_validasi():
    """Prior 4 tim laga sintetis (rating 'musim sebelumnya')."""
    return {
        "2025-26": {
            "ATL": {"off_rtg": 114.0, "def_rtg": 112.0, "net_rtg": 2.0, "pace": 100.0},
            "DET": {"off_rtg": 115.0, "def_rtg": 110.0, "net_rtg": 5.0, "pace": 99.0},
            "BOS": {"off_rtg": 116.0, "def_rtg": 109.0, "net_rtg": 7.0, "pace": 98.0},
            "NYK": {"off_rtg": 113.0, "def_rtg": 111.0, "net_rtg": 2.0, "pace": 97.0},
        }
    }


def _rolling_validasi(boxscores=None):
    """Bangun rating rolling untuk 3 laga sintetis."""
    games = _laga_sintetis()
    rolling, _info = fit_nba_params.bangun_rating_rolling(
        games,
        boxscores if boxscores is not None else _boxscore_validasi(),
        _prior_validasi(),
    )
    return rolling


class TestBacktestRolling(unittest.TestCase):
    def test_ujung_ke_ujung_3_laga_rolling(self):
        cfg = config_mod.load_playstyle()
        games = _laga_sintetis()
        hasil = validate_nba_model.jalankan_backtest(
            games,
            games,
            {},
            cfg,
            iterations=200,
            rolling=_rolling_validasi(),
        )
        self.assertEqual(hasil["n_laga"], 3)
        self.assertEqual(hasil["n_dilewati"], 0)
        for record, game in zip(hasil["hasil_per_laga"], games, strict=True):
            self.assertEqual(record["game_id"], game["game_id"])
            self.assertTrue(0.0 <= record["p_home_win"] <= 1.0)
            self.assertTrue(0.0 <= record["p_under"] <= 1.0)
            self.assertEqual(
                record["actual_home_win"],
                game["home_pts"] > game["away_pts"],
            )

    def test_deterministik_rolling(self):
        cfg = config_mod.load_playstyle()
        games = _laga_sintetis()
        rolling = _rolling_validasi()
        hasil1 = validate_nba_model.jalankan_backtest(
            games, games, {}, cfg, iterations=200, rolling=rolling
        )
        hasil2 = validate_nba_model.jalankan_backtest(
            games, games, {}, cfg, iterations=200, rolling=rolling
        )
        for r1, r2 in zip(
            hasil1["hasil_per_laga"], hasil2["hasil_per_laga"], strict=True
        ):
            self.assertEqual(r1["p_home_win"], r2["p_home_win"])
            self.assertEqual(r1["p_under"], r2["p_under"])

    def test_inputs_rolling_memakai_last10(self):
        """bangun_inputs dengan rolling menyertakan stats_last10 dari
        rating rolling (bobot resensi beroperasi, bukan fallback musim)."""
        games = _laga_sintetis()
        rolling = _rolling_validasi()
        modul_fit = validate_nba_model._muat_modul_fit()
        b2b = modul_fit.detect_back_to_back(games)
        game = games[0]  # ATL vs DET, 2025-11-01
        inputs = validate_nba_model.bangun_inputs(
            game, {}, 0.0, b2b, rolling_laga=rolling[game["game_id"]]
        )
        data = rolling[game["game_id"]]
        self.assertEqual(inputs["home"]["stats_season"], data["home"]["stats_season"])
        self.assertEqual(inputs["home"]["stats_last10"], data["home"]["stats_last10"])
        self.assertEqual(inputs["away"]["stats_last10"], data["away"]["stats_last10"])
        self.assertEqual(inputs["league"]["avg_off_rtg"], data["lg_avg_off_rtg"])

    def test_inputs_rolling_point_in_time(self):
        """Box score DET 7 Nov tidak boleh mengubah inputs laga 1 Nov
        (ATL vs DET), tapi HARUS mengubah inputs laga 9 Nov
        (DET vs BOS)."""
        games = _laga_sintetis()
        modul_fit = validate_nba_model._muat_modul_fit()
        b2b = modul_fit.detect_back_to_back(games)
        rolling_dasar = _rolling_validasi()
        tambahan = [
            _record_boxscore_validasi(
                "v-nov07", "2025-11-07", "DET", "CHI", True, 130, 110.0, 90, 95.0
            ),
            _record_boxscore_validasi(
                "v-nov07", "2025-11-07", "CHI", "DET", False, 90, 95.0, 130, 110.0
            ),
        ]
        rolling_baru = _rolling_validasi(_boxscore_validasi() + tambahan)
        inputs_1101_dasar = validate_nba_model.bangun_inputs(
            games[0],
            {},
            0.0,
            b2b,
            rolling_laga=rolling_dasar[games[0]["game_id"]],
        )
        inputs_1101_baru = validate_nba_model.bangun_inputs(
            games[0],
            {},
            0.0,
            b2b,
            rolling_laga=rolling_baru[games[0]["game_id"]],
        )
        self.assertEqual(inputs_1101_dasar, inputs_1101_baru)
        inputs_1109_dasar = validate_nba_model.bangun_inputs(
            games[2],
            {},
            0.0,
            b2b,
            rolling_laga=rolling_dasar[games[2]["game_id"]],
        )
        inputs_1109_baru = validate_nba_model.bangun_inputs(
            games[2],
            {},
            0.0,
            b2b,
            rolling_laga=rolling_baru[games[2]["game_id"]],
        )
        self.assertNotEqual(
            inputs_1109_dasar["home"]["stats_season"]["off_rtg"],
            inputs_1109_baru["home"]["stats_season"]["off_rtg"],
        )

    def test_laga_tanpa_rolling_dilewati(self):
        cfg = config_mod.load_playstyle()
        games = _laga_sintetis()
        rolling = _rolling_validasi()
        del rolling[games[1]["game_id"]]  # hapus laga ke-2
        hasil = validate_nba_model.jalankan_backtest(
            games, games, {}, cfg, iterations=200, rolling=rolling
        )
        self.assertEqual(hasil["n_laga"], 2)
        self.assertEqual(hasil["n_dilewati"], 1)
        self.assertEqual(hasil["dilewati"][0]["game_id"], games[1]["game_id"])


# --- Sinkronisasi rumus dampak pemain (patch 1b, perbaikan 2) ---

# Parameter rumus dampak (sama dengan config: bpm_scale 1,0,
# bpm_replacement -2,0, w_last10 ternormalisasi 0,4).
_BPM_SCALE = 1.0
_BPM_REPLACEMENT = -2.0
_W_LAST10 = 0.4


class TestDampakPemainSinkronEngine(unittest.TestCase):
    def test_wrapper_sama_dengan_fungsi_engine(self):
        """_dampak_pemain skrip ini mendelegasikan ke engine — hasilnya
        harus IDENTIK dengan nba_sim._dampak_pemain untuk semua kasus
        (termasuk missed_last10 None/invalid dan BPM/menit hilang)."""
        kasus = [
            {"player": "A", "bpm": 5.0, "mp_per_game": 36.0},
            {"player": "B", "bpm": 2.0, "mp_per_game": 40.0, "missed_last10": 5},
            {"player": "C", "bpm": -3.0, "mp_per_game": 24.0, "missed_last10": 10},
            {"player": "D", "bpm": None, "mp_per_game": 30.0},
            {"player": "E", "bpm": 4.0, "mp_per_game": None},
            {"player": "F", "bpm": 1.0, "mp_per_game": 20.0, "missed_last10": None},
            {"player": "G", "bpm": 1.0, "mp_per_game": 20.0, "missed_last10": 99},
        ]
        for pemain in kasus:
            with self.subTest(pemain=pemain["player"]):
                harapan, _catatan = nba_sim._dampak_pemain(
                    pemain, _BPM_SCALE, _BPM_REPLACEMENT, _W_LAST10
                )
                self.assertEqual(
                    validate_nba_model._dampak_pemain(
                        pemain, _BPM_SCALE, _BPM_REPLACEMENT, _W_LAST10
                    ),
                    harapan,
                )

    def test_nilai_hitung_tangan_rumus_baru(self):
        """Rumus baru, dihitung tangan:
        dampak = (BPM - (-2,0)) x (mp/48) x 1,0 x (1 - 0,4 x missed/10)."""
        # A: (5+2) x (36/48) x 1,0 = 5,25.
        self.assertAlmostEqual(
            validate_nba_model._dampak_pemain(
                {"player": "A", "bpm": 5.0, "mp_per_game": 36.0},
                _BPM_SCALE,
                _BPM_REPLACEMENT,
                _W_LAST10,
            ),
            5.25,
        )
        # B: (2+2) x (40/48) x (1 - 0,4 x 5/10) = 4 x 0,8333 x 0,8.
        self.assertAlmostEqual(
            validate_nba_model._dampak_pemain(
                {"player": "B", "bpm": 2.0, "mp_per_game": 40.0, "missed_last10": 5},
                _BPM_SCALE,
                _BPM_REPLACEMENT,
                _W_LAST10,
            ),
            4.0 * (40.0 / 48.0) * 0.8,
        )
        # C di bawah replacement (BPM -3,0): (-3+2) x (24/48) = -0,5
        # (negatif: absennya menaikkan proyeksi karena penggantinya
        # level -2,0 lebih baik darinya).
        self.assertAlmostEqual(
            validate_nba_model._dampak_pemain(
                {"player": "C", "bpm": -3.0, "mp_per_game": 24.0},
                _BPM_SCALE,
                _BPM_REPLACEMENT,
                _W_LAST10,
            ),
            -0.5,
        )
        # missed_last10 None -> faktor 1,0 (sama dengan missed 0).
        tanpa_missed = validate_nba_model._dampak_pemain(
            {"player": "D", "bpm": 1.0, "mp_per_game": 24.0},
            _BPM_SCALE,
            _BPM_REPLACEMENT,
            _W_LAST10,
        )
        missed_nol = validate_nba_model._dampak_pemain(
            {"player": "D", "bpm": 1.0, "mp_per_game": 24.0, "missed_last10": 0},
            _BPM_SCALE,
            _BPM_REPLACEMENT,
            _W_LAST10,
        )
        self.assertEqual(tanpa_missed, missed_nol)
        self.assertAlmostEqual(tanpa_missed, 3.0 * 0.5)


class TestBintangTeratasRumusBaru(unittest.TestCase):
    def test_peringkat_berubah_dibanding_rumus_lama(self):
        """Kasus pembeda: rumus LAMA memilih Y, rumus BARU memilih X.
        X: BPM 0,5, 48 menit -> lama 0,5; baru (0,5+2) x 1 = 2,5.
        Y: BPM 4,0, 12 menit, absen 10/10 last10 -> lama 1,0;
        baru (4+2) x 0,25 x (1-0,4) = 0,9. Jadi bintang baru = X."""
        inputs = {
            "home": {
                "players": [
                    {"player": "X", "bpm": 0.5, "mp_per_game": 48.0},
                    {
                        "player": "Y",
                        "bpm": 4.0,
                        "mp_per_game": 12.0,
                        "missed_last10": 10,
                    },
                    {"player": "Z-OUT", "bpm": 9.0, "mp_per_game": 40.0},
                ],
                "injuries": [{"player": "Z-OUT", "status": "OUT"}],
            },
            "away": {
                "players": [
                    {"player": "C", "bpm": -3.0, "mp_per_game": 24.0},
                    {"player": "E", "bpm": 0.0, "mp_per_game": 30.0},
                ],
                "injuries": [],
            },
        }
        bintang = validate_nba_model._bintang_teratas(
            inputs, _BPM_SCALE, _BPM_REPLACEMENT, _W_LAST10
        )
        # Kandang: X (2,5) > Y (0,9); Z-OUT dikecualikan walau BPM 9,0.
        self.assertEqual(bintang["home"], "X")
        # Tandang: E ((0+2) x 30/48 = 1,25) > C (-0,5).
        self.assertEqual(bintang["away"], "E")

    def test_tanpa_pemain_valid_keduanya_none(self):
        inputs = {
            "home": {"players": [], "injuries": []},
            "away": {
                "players": [{"player": "A", "bpm": 5.0, "mp_per_game": 30.0}],
                "injuries": [{"player": "A", "status": "OUT"}],
            },
        }
        bintang = validate_nba_model._bintang_teratas(
            inputs, _BPM_SCALE, _BPM_REPLACEMENT, _W_LAST10
        )
        self.assertIsNone(bintang["home"])
        self.assertIsNone(bintang["away"])


if __name__ == "__main__":
    unittest.main()
