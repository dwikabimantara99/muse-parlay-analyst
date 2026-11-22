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
from engine import validation

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


if __name__ == "__main__":
    unittest.main()
