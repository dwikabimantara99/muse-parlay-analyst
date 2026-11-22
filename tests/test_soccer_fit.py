"""Tes fit + validasi model Dixon-Coles sepak bola — TANPA network.

Data sintetis dibangkitkan dari parameter "benar" yang diketahui
(rho, attack/defence, avg goals) lewat grid Dixon-Coles yang sama
dengan mesin sim; fit harus memulihkannya dalam toleransi statistik
yang longgar. Semua tes deterministik (seed tetap).
"""

import importlib.util
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import football_sim
from ingest import football_data

REPO_ROOT = Path(__file__).resolve().parent.parent

_SPEK_FIT = importlib.util.spec_from_file_location(
    "fit_soccer_params", REPO_ROOT / "scripts" / "fit_soccer_params.py"
)
fit_mod = importlib.util.module_from_spec(_SPEK_FIT)
_SPEK_FIT.loader.exec_module(fit_mod)

_SPEK_VAL = importlib.util.spec_from_file_location(
    "validate_soccer_model", REPO_ROOT / "scripts" / "validate_soccer_model.py"
)
val_mod = importlib.util.module_from_spec(_SPEK_VAL)
_SPEK_VAL.loader.exec_module(val_mod)

# Parameter "benar" data sintetis.
RHO_BENAR = -0.12
AVG_HOME_BENAR = 1.5
AVG_AWAY_BENAR = 1.2
TIM_SINTETIS = [f"Tim{i:02d}" for i in range(12)]
ATTACK_BENAR = {
    "Tim00": 1.40,
    "Tim01": 1.30,
    "Tim02": 1.20,
    "Tim03": 1.10,
    "Tim04": 1.05,
    "Tim05": 1.00,
    "Tim06": 0.95,
    "Tim07": 0.90,
    "Tim08": 0.85,
    "Tim09": 0.80,
    "Tim10": 0.75,
    "Tim11": 0.70,
}
DEFENCE_BENAR = {
    "Tim00": 0.70,
    "Tim01": 0.75,
    "Tim02": 0.80,
    "Tim03": 0.85,
    "Tim04": 0.90,
    "Tim05": 0.95,
    "Tim06": 1.00,
    "Tim07": 1.05,
    "Tim08": 1.10,
    "Tim09": 1.20,
    "Tim10": 1.30,
    "Tim11": 1.40,
}


def _sampling_skor(rng, lam_h, lam_a, rho):
    """Sampling satu skor dari grid Dixon-Coles 0..10 (kode independen).

    Dibangun langsung dari rumus (Poisson x tau), bukan memakai
    probabilitas_laga — agar tes tidak menguji dirinya sendiri.
    """
    grid = []
    total = 0.0
    for h in range(11):
        for a in range(11):
            p = (
                math.exp(-lam_h)
                * lam_h**h
                / math.factorial(h)
                * math.exp(-lam_a)
                * lam_a**a
                / math.factorial(a)
                * fit_mod.tau_dc(h, a, lam_h, lam_a, rho)
            )
            grid.append(p)
            total += p
    u = rng.random() * total
    berjalan = 0.0
    for idx, p in enumerate(grid):
        berjalan += p
        if u <= berjalan:
            return divmod(idx, 11)
    return (10, 10)


def buat_laga_sintetis(seed=7, n_ronde=3, musim="2223", tanggal_awal="2022-08-01"):
    """Bangkitkan laga sintetis round-robin ganda dari parameter benar.

    12 tim, tiap ronde = semua pasangan kandang+tandang (132 laga).
    Tanggal naik 7 hari per ronde (cukup untuk pengujian rolling).
    """
    rng = random.Random(seed)
    laga = []
    hari = 0
    from datetime import date, timedelta

    awal = date.fromisoformat(tanggal_awal)
    for _ in range(n_ronde):
        for kandang in TIM_SINTETIS:
            for tandang in TIM_SINTETIS:
                if kandang == tandang:
                    continue
                lam_h = ATTACK_BENAR[kandang] * DEFENCE_BENAR[tandang] * AVG_HOME_BENAR
                lam_a = ATTACK_BENAR[tandang] * DEFENCE_BENAR[kandang] * AVG_AWAY_BENAR
                h, a = _sampling_skor(rng, lam_h, lam_a, RHO_BENAR)
                laga.append(
                    {
                        "date": (awal + timedelta(days=hari)).isoformat(),
                        "season": musim,
                        "season_label": musim,
                        "league": "EPL",
                        "home_team": kandang,
                        "away_team": tandang,
                        "home_goals": h,
                        "away_goals": a,
                    }
                )
        hari += 7
    return laga


class TestLoaderFootballData(unittest.TestCase):
    def test_parse_tanggal_format(self):
        self.assertEqual(
            football_data.parse_tanggal_fd("16/08/2024").isoformat(), "2024-08-16"
        )
        self.assertEqual(
            football_data.parse_tanggal_fd("05/08/22").isoformat(), "2022-08-05"
        )
        self.assertIsNone(football_data.parse_tanggal_fd("bukan-tanggal"))
        self.assertIsNone(football_data.parse_tanggal_fd(""))
        self.assertIsNone(football_data.parse_tanggal_fd("31/02/2024"))

    def test_muat_csv_hasil_fixture(self):
        isi = (
            "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,PSH,PSD,PSA\n"
            "E0,16/08/2024,Arsenal,Leeds,2,1,1.5,4.0,6.0\n"
            "E0,17/08/2024,Chelsea,Arsenal,0,0,2.5,3.2,2.9\n"
            "E0,18/08/2024,Leeds,Chelsea,,,2.1,3.4,3.5\n"
        )
        with tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8-sig"
        ) as fh:
            fh.write(isi)
            path = fh.name
        try:
            laga, info = football_data.muat_csv_hasil(path, "EPL", "2425")
        finally:
            Path(path).unlink()
        # Baris tanpa skor dilewati + dihitung (bukan dikarang).
        self.assertEqual(len(laga), 2)
        self.assertEqual(info["n_baris"], 3)
        self.assertEqual(info["n_tanpa_skor"], 1)
        self.assertEqual(laga[0]["home_team"], "Arsenal")
        self.assertEqual(laga[0]["home_goals"], 2)
        self.assertEqual(laga[0]["date"], "2024-08-16")
        self.assertEqual(laga[0]["season_label"], "2024/25")
        # Kolom odds TIDAK dibaca ke record laga.
        self.assertNotIn("PSH", laga[0])

    def test_muat_csv_hasil_file_hilang_dan_kolom_hilang(self):
        with self.assertRaises(FileNotFoundError):
            football_data.muat_csv_hasil("data/tidak_ada.csv", "EPL", "2425")
        with tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("Div,Date,HomeTeam\nE0,16/08/2024,Arsenal\n")
            path = fh.name
        try:
            with self.assertRaises(ValueError):
                football_data.muat_csv_hasil(path, "EPL", "2425")
        finally:
            Path(path).unlink()

    def test_muat_musim_liga_tidak_dikenal(self):
        with self.assertRaises(ValueError):
            football_data.muat_musim("data", "Bundesliga", ["2425"])


class TestTauDanPeluang(unittest.TestCase):
    def test_tau_nilai_hitung_tangan(self):
        lam_h, lam_a, rho = 1.5, 1.2, -0.1
        self.assertAlmostEqual(
            fit_mod.tau_dc(0, 0, lam_h, lam_a, rho), 1 - 1.5 * 1.2 * -0.1
        )
        self.assertAlmostEqual(fit_mod.tau_dc(1, 0, lam_h, lam_a, rho), 1 + 1.2 * -0.1)
        self.assertAlmostEqual(fit_mod.tau_dc(0, 1, lam_h, lam_a, rho), 1 + 1.5 * -0.1)
        self.assertAlmostEqual(fit_mod.tau_dc(1, 1, lam_h, lam_a, rho), 1 - -0.1)
        self.assertEqual(fit_mod.tau_dc(2, 0, lam_h, lam_a, rho), 1.0)
        self.assertEqual(fit_mod.tau_dc(3, 2, lam_h, lam_a, rho), 1.0)
        self.assertEqual(fit_mod.tau_dc(0, 0, lam_h, lam_a, 0.0), 1.0)

    def test_probabilitas_berjumlah_satu(self):
        for lam_h, lam_a, rho in (
            (1.5, 1.2, -0.12),
            (2.5, 0.8, 0.05),
            (0.9, 0.9, 0.0),
            (3.0, 2.0, -0.2),
        ):
            p = fit_mod.probabilitas_laga(lam_h, lam_a, rho)
            self.assertAlmostEqual(p["home_win"] + p["draw"] + p["away_win"], 1.0)
            self.assertAlmostEqual(p["over_2.5"] + p["under_2.5"], 1.0)
            self.assertAlmostEqual(p["btts_yes"] + p["btts_no"], 1.0)
            # Massa grid ~1: koreksi tau saling meniadakan; yang hilang
            # hanya ekor Poisson di atas 10 gol (untuk lam <= 3, < 1e-3).
            self.assertAlmostEqual(p["massa_grid"], 1.0, places=3)
        # Untuk lambda kecil, ekornya jauh lebih kecil lagi.
        p_kecil = fit_mod.probabilitas_laga(0.9, 0.9, -0.12)
        self.assertAlmostEqual(p_kecil["massa_grid"], 1.0, places=5)

    def test_probabilitas_simetris(self):
        p = fit_mod.probabilitas_laga(1.5, 1.5, 0.0)
        self.assertAlmostEqual(p["home_win"], p["away_win"])
        self.assertGreater(p["draw"], 0.2)

    def test_probabilitas_tau_tidak_valid_ditolak(self):
        # tau(0,0) = 1 - 3*3*0.5 < 0 -> parameter tidak valid.
        with self.assertRaises(ValueError):
            fit_mod.probabilitas_laga(3.0, 3.0, 0.5)
        with self.assertRaises(ValueError):
            fit_mod.probabilitas_laga(0.0, 1.0, 0.0)

    def test_konsisten_dengan_engine_football_sim(self):
        """Peluang analitik cocok dengan simulasi Monte Carlo engine B.

        Toleransi longgar (±0,02 ~ 5x simpangan Monte Carlo pada
        20.000 iterasi) — penjaga agar rumus fit tidak drift dari sim.
        """
        hasil = football_sim.simulate(
            inputs={
                "home": {"name": "Arsenal", "attack": 1.4, "defence": 0.7},
                "away": {"name": "Chelsea", "attack": 1.0, "defence": 1.0},
                "match": {
                    "match_id": "tes",
                    "home_team": "Arsenal",
                    "away_team": "Chelsea",
                    "date": "2026-11-22",
                },
            },
            params={
                "rho": -0.12,
                "avg_home_goals": 1.5,
                "avg_away_goals": 1.2,
                "league": "EPL",
                "fit_version": "tes",
            },
            seed=42,
            iterations=20000,
        )
        p = fit_mod.probabilitas_laga(1.4 * 1.0 * 1.5, 1.0 * 0.7 * 1.2, -0.12)
        markets = hasil["markets"]
        for kunci, nilai in (
            ("home_win", p["home_win"]),
            ("draw", p["draw"]),
            ("away_win", p["away_win"]),
            ("total_over_2_5", p["over_2.5"]),
            ("btts_yes", p["btts_yes"]),
        ):
            self.assertAlmostEqual(markets[kunci], nilai, delta=0.02)


class TestFitDixonColes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.laga = buat_laga_sintetis(seed=7, n_ronde=3)
        cls.hasil = fit_mod.fit_dixon_coles(cls.laga)

    def test_pemulihan_parameter_benar(self):
        self.assertTrue(self.hasil["converged"])
        self.assertAlmostEqual(self.hasil["rho"], RHO_BENAR, delta=0.10)
        self.assertAlmostEqual(self.hasil["avg_home_goals"], AVG_HOME_BENAR, delta=0.15)
        self.assertAlmostEqual(self.hasil["avg_away_goals"], AVG_AWAY_BENAR, delta=0.15)
        for tim in TIM_SINTETIS:
            self.assertAlmostEqual(
                self.hasil["attack"][tim], ATTACK_BENAR[tim], delta=0.25
            )
            self.assertAlmostEqual(
                self.hasil["defence"][tim], DEFENCE_BENAR[tim], delta=0.25
            )

    def test_normalisasi_rata_rata_satu(self):
        attack = self.hasil["attack"]
        defence = self.hasil["defence"]
        mean_atk = sum(attack.values()) / len(attack)
        mean_def = sum(defence.values()) / len(defence)
        self.assertAlmostEqual(mean_atk, 1.0, places=9)
        self.assertAlmostEqual(mean_def, 1.0, places=9)

    def test_rho_dalam_batas_dan_tau_positif(self):
        self.assertGreaterEqual(self.hasil["rho"], -0.5)
        self.assertLessEqual(self.hasil["rho"], 0.5)
        for m in self.laga:
            pred = fit_mod.prediksi_laga(self.hasil, m["home_team"], m["away_team"])
            for x, y in ((0, 0), (1, 0), (0, 1), (1, 1)):
                self.assertGreater(
                    fit_mod.tau_dc(
                        x,
                        y,
                        pred["lambda_home"],
                        pred["lambda_away"],
                        self.hasil["rho"],
                    ),
                    0,
                )

    def test_loglik_meningkat_dari_awal(self):
        self.assertGreater(self.hasil["loglik"], self.hasil["loglik_awal"])
        # Rata-rata lambda hasil fit ~ rata-rata gol sampel (sifat MLE).
        lam_h = [
            fit_mod.prediksi_laga(self.hasil, m["home_team"], m["away_team"])[
                "lambda_home"
            ]
            for m in self.laga
        ]
        mean_sampel = sum(m["home_goals"] for m in self.laga) / len(self.laga)
        self.assertAlmostEqual(sum(lam_h) / len(lam_h), mean_sampel, delta=0.05)

    def test_deterministik(self):
        hasil2 = fit_mod.fit_dixon_coles(self.laga)
        self.assertEqual(hasil2, self.hasil)

    def test_warm_start_hasil_sama(self):
        setengah = self.laga[: len(self.laga) // 2]
        awal = fit_mod.fit_dixon_coles(setengah)
        hangat = fit_mod.fit_dixon_coles(self.laga, warm_start=awal)
        dingin = fit_mod.fit_dixon_coles(self.laga)
        self.assertAlmostEqual(hangat["rho"], dingin["rho"], delta=0.005)
        self.assertAlmostEqual(hangat["loglik"], dingin["loglik"], delta=0.5)
        for tim in TIM_SINTETIS:
            self.assertAlmostEqual(
                hangat["attack"][tim], dingin["attack"][tim], delta=0.01
            )
        self.assertLessEqual(hangat["n_sweeps"], dingin["n_sweeps"])

    def test_data_tidak_cukup_ditolak(self):
        with self.assertRaises(ValueError):
            fit_mod.fit_dixon_coles(self.laga[:50], min_matches=100)
        with self.assertRaises(ValueError):
            fit_mod.fit_dixon_coles([], min_matches=100)

    def test_prediksi_tim_tidak_dikenal(self):
        pred = fit_mod.prediksi_laga(self.hasil, "Tim00", "TimBaru")
        self.assertEqual(pred["attack_away"], 1.0)
        self.assertEqual(pred["defence_away"], 1.0)
        self.assertIn("TimBaru", pred["tim_tidak_dikenal"])
        self.assertNotIn("Tim00", pred["tim_tidak_dikenal"])
        self.assertAlmostEqual(pred["home_win"] + pred["draw"] + pred["away_win"], 1.0)


class TestValidasiSoccer(unittest.TestCase):
    def test_brier_1x2_hitung_tangan(self):
        pairs = [((0.5, 0.3, 0.2), 0), ((0.2, 0.3, 0.5), 2)]
        # Laga 1: .25+.09+.04 = .38; laga 2: .04+.09+.25 = .38.
        self.assertAlmostEqual(val_mod.brier_1x2(pairs), 0.38)
        # Tebakan 1/3: Brier = 2/3 persis.
        sepertiga = [((1 / 3, 1 / 3, 1 / 3), o) for o in (0, 1, 2, 0, 2)]
        self.assertAlmostEqual(val_mod.brier_1x2(sepertiga), 2 / 3, places=9)
        with self.assertRaises(ValueError):
            val_mod.brier_1x2([])
        with self.assertRaises(ValueError):
            val_mod.brier_1x2([((0.5, 0.5, 0.5), 0)])
        with self.assertRaises(ValueError):
            val_mod.brier_1x2([((0.5, 0.3, 0.2), 3)])

    def test_frekuensi_dasar_hitung_tangan(self):
        laga = [
            {"home_goals": 2, "away_goals": 1},  # H, over, btts
            {"home_goals": 0, "away_goals": 0},  # D
            {"home_goals": 1, "away_goals": 1},  # D, btts
            {"home_goals": 0, "away_goals": 3},  # A, over
        ]
        klim = val_mod.frekuensi_dasar(laga)
        self.assertAlmostEqual(klim["p_home_win"], 0.25)
        self.assertAlmostEqual(klim["p_draw"], 0.5)
        self.assertAlmostEqual(klim["p_away_win"], 0.25)
        self.assertAlmostEqual(klim["p_over_2.5"], 0.5)
        self.assertAlmostEqual(klim["p_btts"], 0.5)
        with self.assertRaises(ValueError):
            val_mod.frekuensi_dasar([])

    def test_bagi_ronde(self):
        laga = [
            {"date": f"2025-08-{d:02d}", "home_team": "A", "away_team": "B"}
            for d in range(1, 26)
        ]
        # Acak urutan input — bagi_ronde harus mengurutkan tanggal dulu.
        rng = random.Random(1)
        rng.shuffle(laga)
        ronde = val_mod.bagi_ronde(laga, ukuran=10)
        self.assertEqual([len(r) for r in ronde], [10, 10, 5])
        tanggal = [m["date"] for r in ronde for m in r]
        self.assertEqual(tanggal, sorted(tanggal))

    def test_hitung_metrik_fixture(self):
        records = [
            {
                "p_home_win": 0.6,
                "p_draw": 0.25,
                "p_away_win": 0.15,
                "outcome_1x2": 0,
                "p_over_2.5": 0.7,
                "actual_over_2.5": True,
                "p_btts": 0.6,
                "actual_btts": True,
                "klim_p_home_win": 0.45,
                "klim_p_draw": 0.25,
                "klim_p_away_win": 0.30,
                "klim_p_over_2.5": 0.55,
                "klim_p_btts": 0.55,
                "tim_tidak_dikenal": [],
            },
            {
                "p_home_win": 0.2,
                "p_draw": 0.3,
                "p_away_win": 0.5,
                "outcome_1x2": 2,
                "p_over_2.5": 0.4,
                "actual_over_2.5": False,
                "p_btts": 0.4,
                "actual_btts": False,
                "klim_p_home_win": 0.45,
                "klim_p_draw": 0.25,
                "klim_p_away_win": 0.30,
                "klim_p_over_2.5": 0.55,
                "klim_p_btts": 0.55,
                "tim_tidak_dikenal": ["TimBaru"],
            },
        ]
        metrik = val_mod.hitung_metrik(records)
        self.assertEqual(metrik["n"], 2)
        # Brier 1X2 model: laga1 .16+.0625+.0225=.245; laga2 .04+.09+.25=.38.
        self.assertAlmostEqual(metrik["brier_1x2"]["model"], (0.245 + 0.38) / 2)
        # Tebakan 1/3 = 2/3 (disimpan dibulatkan 6 desimal di metrik).
        self.assertAlmostEqual(
            metrik["brier_1x2"]["tebakan_sepertiga"], 2 / 3, places=6
        )
        self.assertAlmostEqual(metrik["akurasi_over_2.5"], 1.0)
        self.assertAlmostEqual(metrik["akurasi_1x2_argmax"], 1.0)
        self.assertEqual(metrik["n_laga_tim_tidak_dikenal"], 1)
        self.assertIn("selisih_model_vs_klim", metrik["brier_1x2"])

    def test_holdout_sintetis_ujung_ke_ujung(self):
        latih = buat_laga_sintetis(seed=11, n_ronde=2, musim="2425")
        uji = buat_laga_sintetis(
            seed=99, n_ronde=1, musim="2526", tanggal_awal="2025-08-01"
        )
        hasil = val_mod.jalankan_holdout(fit_mod, "EPL", latih, uji)
        self.assertEqual(hasil["n_uji"], len(uji))
        metrik = hasil["metrik"]
        # Model yang benar harus mengalahkan tebakan 1/3 pada 1X2.
        self.assertLess(metrik["brier_1x2"]["model"], 2 / 3)
        self.assertLess(
            metrik["brier_1x2"]["model"], metrik["brier_1x2"]["klimatologi"]
        )
        self.assertTrue(hasil["fit"]["converged"])

    def test_rolling_point_in_time(self):
        """Fit ronde 1 rolling = fit langsung atas data latih saja.

        Laga musim uji TIDAK boleh memengaruhi fit ronde 1 — bila
        kode memakai laga setelah tanggal uji, nilai rho ronde 1 akan
        berbeda dari fit langsung atas data latih.
        """
        latih = buat_laga_sintetis(seed=11, n_ronde=2, musim="2425")
        uji = buat_laga_sintetis(
            seed=99, n_ronde=1, musim="2526", tanggal_awal="2025-08-01"
        )
        langsung = fit_mod.fit_dixon_coles(latih)
        hasil = val_mod.jalankan_rolling(fit_mod, "EPL", latih, uji)
        ronde1 = hasil["per_ronde"][0]
        self.assertEqual(ronde1["n_latih"], len(latih))
        self.assertAlmostEqual(ronde1["rho"], langsung["rho"], places=3)
        # Semua laga uji terprediksi, tanpa kebocoran tanggal.
        self.assertEqual(hasil["n_uji"], len(uji))
        for record, laga in zip(hasil["hasil_per_laga"], uji, strict=True):
            self.assertEqual(record["date"], laga["date"])


if __name__ == "__main__":
    unittest.main()
