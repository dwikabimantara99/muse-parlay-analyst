"""Tes engine/football_sim.py — Dixon-Coles: determinisme, skema,
komplementaritas pasar, validasi argumen, kasus Poisson independen.

TANPA network. Tes unit memakai iterations kecil via parameter; SATU
tes kecepatan memakai 100.000 iterasi penuh (batas 5 detik).
"""

import copy
import json
import math
import sys
import time
import unittest
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine import football_sim

REPO_ROOT = Path(__file__).resolve().parent.parent

PASAR_WAJIB = {
    "home_win",
    "draw",
    "away_win",
    "total_over_0_5",
    "total_under_0_5",
    "total_over_1_5",
    "total_under_1_5",
    "total_over_2_5",
    "total_under_2_5",
    "total_over_3_5",
    "total_under_3_5",
    "total_over_4_5",
    "total_under_4_5",
    "total_over_5_5",
    "total_under_5_5",
    "total_over_6_5",
    "total_under_6_5",
    "total_over_7_5",
    "total_under_7_5",
    "total_over_8_5",
    "total_under_8_5",
    "btts_yes",
    "btts_no",
}


def buat_cfg(iterations: int = 100000) -> dict:
    """Config tes minimal — hanya simulation.iterations yang dibaca sim."""
    return {"simulation": {"iterations": iterations}}


def buat_inputs() -> dict:
    """Fixture laga Arsenal vs Chelsea (angka contoh, realistis)."""
    return {
        "home": {"name": "Arsenal", "attack": 1.15, "defence": 0.85},
        "away": {"name": "Chelsea", "attack": 1.05, "defence": 0.95},
        "match": {
            "match_id": "ARS_CHE_2026-11-22",
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "date": "2026-11-22",
        },
    }


def buat_params() -> dict:
    """Parameter fit CONTOH (bukan hasil fit — menunggu persetujuan user)."""
    return {
        "rho": -0.13,
        "avg_home_goals": 1.55,
        "avg_away_goals": 1.20,
        "league": "EPL",
        "fit_version": "contoh-tes-0.1",
    }


def _tanpa_stempel_waktu(hasil: dict) -> dict:
    """Salinan hasil tanpa field yang berubah tiap jalan (determinisme)."""
    salinan = copy.deepcopy(hasil)
    salinan.pop("generated_at", None)
    salinan.get("inputs_summary", {}).pop("elapsed_seconds", None)
    return salinan


def _poisson(lam: float, k: int) -> float:
    """P(X = k) untuk X ~ Poisson(lam), dihitung tangan."""
    return math.exp(-lam) * lam**k / math.factorial(k)


class TestFootballSim(unittest.TestCase):
    def test_determinisme_seed_sama_output_identik(self):
        hasil_a = football_sim.simulate(
            buat_inputs(), buat_params(), buat_cfg(), seed=42, iterations=5000
        )
        hasil_b = football_sim.simulate(
            buat_inputs(), buat_params(), buat_cfg(), seed=42, iterations=5000
        )
        self.assertEqual(_tanpa_stempel_waktu(hasil_a), _tanpa_stempel_waktu(hasil_b))

    def test_seed_berbeda_output_berbeda(self):
        hasil_a = football_sim.simulate(
            buat_inputs(), buat_params(), buat_cfg(), seed=1, iterations=2000
        )
        hasil_b = football_sim.simulate(
            buat_inputs(), buat_params(), buat_cfg(), seed=2, iterations=2000
        )
        self.assertNotEqual(hasil_a["markets"], hasil_b["markets"])

    def test_markets_kunci_lengkap(self):
        hasil = football_sim.simulate(
            buat_inputs(), buat_params(), buat_cfg(), seed=7, iterations=1000
        )
        self.assertEqual(set(hasil["markets"]), PASAR_WAJIB)
        self.assertEqual(hasil["sport"], "football")
        self.assertEqual(hasil["engine"]["name"], "football_sim")
        self.assertEqual(hasil["engine"]["version"], "1.0.0")
        self.assertEqual(hasil["engine"]["seed"], 7)

    def test_1x2_berjumlah_satu(self):
        hasil = football_sim.simulate(
            buat_inputs(), buat_params(), buat_cfg(), seed=7, iterations=10000
        )
        jumlah = (
            hasil["markets"]["home_win"]
            + hasil["markets"]["draw"]
            + hasil["markets"]["away_win"]
        )
        self.assertAlmostEqual(jumlah, 1.0, delta=2e-6)

    def test_over_under_komplementer(self):
        hasil = football_sim.simulate(
            buat_inputs(), buat_params(), buat_cfg(), seed=7, iterations=10000
        )
        for garis in (
            "0_5",
            "1_5",
            "2_5",
            "3_5",
            "4_5",
            "5_5",
            "6_5",
            "7_5",
            "8_5",
        ):
            with self.subTest(garis=garis):
                jumlah = (
                    hasil["markets"][f"total_over_{garis}"]
                    + hasil["markets"][f"total_under_{garis}"]
                )
                self.assertAlmostEqual(jumlah, 1.0, delta=2e-6)

    def test_btts_komplementer(self):
        hasil = football_sim.simulate(
            buat_inputs(), buat_params(), buat_cfg(), seed=7, iterations=10000
        )
        jumlah = hasil["markets"]["btts_yes"] + hasil["markets"]["btts_no"]
        self.assertAlmostEqual(jumlah, 1.0, delta=2e-6)

    def test_default_iterations_dari_config(self):
        hasil = football_sim.simulate(
            buat_inputs(), buat_params(), buat_cfg(100000), seed=7
        )
        self.assertEqual(hasil["iterations"], 100000)
        hasil_kecil = football_sim.simulate(
            buat_inputs(), buat_params(), buat_cfg(500), seed=7
        )
        self.assertEqual(hasil_kecil["iterations"], 500)

    def test_config_tanpa_bagian_football_tetap_jalan(self):
        # Sim hanya membaca simulation.iterations dari config — tidak
        # menyentuh simulation.football (rho masih null/TBD di sana).
        hasil = football_sim.simulate(
            buat_inputs(),
            buat_params(),
            {"simulation": {"iterations": 1000}},
            seed=7,
        )
        self.assertEqual(hasil["iterations"], 1000)

    def test_argumen_tidak_valid_melempar_error(self):
        kasus = []

        def tambah(label, ubah_inputs=None, ubah_params=None, **kwargs):
            kasus.append((label, ubah_inputs, ubah_params, kwargs))

        tambah("attack nol", ubah_inputs=lambda i: i["home"].update(attack=0))
        tambah("attack negatif", ubah_inputs=lambda i: i["away"].update(attack=-1.2))
        tambah("defence nol", ubah_inputs=lambda i: i["home"].update(defence=0))
        tambah(
            "defence nan", ubah_inputs=lambda i: i["home"].update(defence=float("nan"))
        )
        tambah("defence string", ubah_inputs=lambda i: i["home"].update(defence="kuat"))
        tambah("nama tim kosong", ubah_inputs=lambda i: i["home"].update(name=""))
        tambah("blok away hilang", ubah_inputs=lambda i: i.pop("away"))
        tambah("match_id hilang", ubah_inputs=lambda i: i["match"].pop("match_id"))
        tambah("tanggal kosong", ubah_inputs=lambda i: i["match"].update(date=""))
        tambah("rho terlalu besar", ubah_params=lambda p: p.update(rho=0.9))
        tambah("rho terlalu kecil", ubah_params=lambda p: p.update(rho=-0.6))
        tambah("rho string", ubah_params=lambda p: p.update(rho="kecil"))
        tambah("avg home nol", ubah_params=lambda p: p.update(avg_home_goals=0))
        tambah("avg away negatif", ubah_params=lambda p: p.update(avg_away_goals=-1.0))
        tambah("league kosong", ubah_params=lambda p: p.update(league=""))
        tambah("fit_version hilang", ubah_params=lambda p: p.pop("fit_version"))
        tambah("iterations nol", iterations=0)
        tambah("iterations negatif", iterations=-5)
        tambah("iterations float", iterations=100.5)
        tambah("iterations bool", iterations=True)
        tambah("seed float", seed=1.5)
        tambah("seed bool", seed=True)

        for label, ubah_inputs, ubah_params, kwargs in kasus:
            with self.subTest(kasus=label):
                inputs = buat_inputs()
                params = buat_params()
                if ubah_inputs is not None:
                    ubah_inputs(inputs)
                if ubah_params is not None:
                    ubah_params(params)
                panggilan = {"seed": 7, "iterations": 100}
                panggilan.update(kwargs)
                with self.assertRaises(ValueError):
                    football_sim.simulate(inputs, params, buat_cfg(), **panggilan)

    def test_inputs_params_bukan_dict_melempar_error(self):
        with self.assertRaises(ValueError):
            football_sim.simulate("bukan dict", buat_params(), buat_cfg())
        with self.assertRaises(ValueError):
            football_sim.simulate(buat_inputs(), None, buat_cfg())

    def test_tau_negatif_ditolak(self):
        # lambda 4 x 4 dengan rho 0,1 -> tau(0,0) = 1 - 16 x 0,1 < 0.
        params = buat_params()
        params.update(rho=0.1, avg_home_goals=4.0, avg_away_goals=4.0)
        inputs = buat_inputs()
        inputs["home"].update(attack=1.0, defence=1.0)
        inputs["away"].update(attack=1.0, defence=1.0)
        with self.assertRaises(ValueError) as ctx:
            football_sim.simulate(inputs, params, buat_cfg(), seed=7, iterations=100)
        self.assertIn("tau(0,0)", str(ctx.exception))

    def test_config_iterations_null_melempar_config_error(self):
        cfg = {"simulation": {"iterations": None}}
        with self.assertRaises(config_mod.ConfigError):
            football_sim.simulate(buat_inputs(), buat_params(), cfg, seed=7)

    def test_output_valid_vs_skema(self):
        hasil = football_sim.simulate(
            buat_inputs(), buat_params(), buat_cfg(), seed=7, iterations=1000
        )
        skema = json.loads(
            (REPO_ROOT / "schemas" / "simulation.schema.json").read_text(
                encoding="utf-8"
            )
        )
        # Validasi langsung dengan jsonschema (tanpa lewat modul).
        jsonschema.validate(hasil, skema)
        # + validator publik modul.
        self.assertIsNone(football_sim.validate_football_sim(hasil))
        self.assertIsNotNone(football_sim.validate_football_sim({}))
        self.assertIsNotNone(football_sim.validate_football_sim("bukan dict"))

    def test_kasus_dikenal_poisson_independen(self):
        """rho=0 + kekuatan simetris -> cocok dengan Poisson independen.

        lambda kandang = lambda tandang = 1,5. Peluang eksak dihitung
        tangan di sini (bukan dari modul) atas Poisson independen.
        """
        lam = 1.5
        inputs = buat_inputs()
        inputs["home"].update(attack=1.0, defence=1.0)
        inputs["away"].update(attack=1.0, defence=1.0)
        params = buat_params()
        params.update(rho=0.0, avg_home_goals=lam, avg_away_goals=lam)
        hasil = football_sim.simulate(
            inputs, params, buat_cfg(), seed=123, iterations=100000
        )
        markets = hasil["markets"]

        # Hitung tangan: Poisson independen 0..30 (ekor < 1e-15).
        peluang = [_poisson(lam, k) for k in range(31)]
        menang_kandang = sum(
            peluang[h] * peluang[a] for h in range(31) for a in range(h)
        )
        seri = sum(p * p for p in peluang)
        menang_tandang = sum(
            peluang[h] * peluang[a] for h in range(31) for a in range(h + 1, 31)
        )
        # Total ~ Poisson(3): P(total >= 3) = 1 - P(0) - P(1) - P(2).
        over_2_5 = 1.0 - sum(_poisson(3.0, t) for t in range(3))
        btts_yes = (1.0 - peluang[0]) ** 2

        # Toleransi 0,01: noise Monte Carlo 100.000x (std ~0,0016)
        # + pemotongan PMF 0..10 (P(X>10|lam=1,5) ~ 1e-6, diabaikan).
        self.assertAlmostEqual(markets["home_win"], menang_kandang, delta=0.01)
        self.assertAlmostEqual(markets["draw"], seri, delta=0.01)
        self.assertAlmostEqual(markets["away_win"], menang_tandang, delta=0.01)
        self.assertAlmostEqual(markets["total_over_2_5"], over_2_5, delta=0.01)
        self.assertAlmostEqual(markets["total_under_2_5"], 1.0 - over_2_5, delta=0.01)
        self.assertAlmostEqual(markets["btts_yes"], btts_yes, delta=0.01)
        # Simetri: home_win == away_win dalam noise.
        self.assertAlmostEqual(markets["home_win"], markets["away_win"], delta=0.01)

    def test_koreksi_tau_mengubah_peluang_0_0(self):
        """rho negatif menaikkan P(0-0) sebesar faktor tau(0,0)."""
        lam = 1.5
        rho = -0.13
        inputs = buat_inputs()
        inputs["home"].update(attack=1.0, defence=1.0)
        inputs["away"].update(attack=1.0, defence=1.0)
        params = buat_params()
        params.update(rho=rho, avg_home_goals=lam, avg_away_goals=lam)
        hasil = football_sim.simulate(
            inputs, params, buat_cfg(), seed=123, iterations=100000
        )
        scorelines = {
            (s["home_goals"], s["away_goals"]): s["probability"]
            for s in hasil["score_distribution"]["scorelines"]
        }
        self.assertIn((0, 0), scorelines)
        # P(0-0) = exp(-3) x (1 - lam^2 x rho); massa total PMF
        # Dixon-Coles tetap 1, jadi tanpa koreksi normalisasi.
        ekspektasi = math.exp(-2 * lam) * (1.0 - lam * lam * rho)
        self.assertAlmostEqual(scorelines[(0, 0)], ekspektasi, delta=0.01)
        # Dan lebih besar dari nilai Poisson independen (rho = 0).
        self.assertGreater(scorelines[(0, 0)], math.exp(-2 * lam))

    def test_scorelines_10_teratas_urut_probabilitas(self):
        hasil = football_sim.simulate(
            buat_inputs(), buat_params(), buat_cfg(), seed=7, iterations=10000
        )
        scorelines = hasil["score_distribution"]["scorelines"]
        self.assertEqual(len(scorelines), 10)
        peluang = [s["probability"] for s in scorelines]
        self.assertEqual(peluang, sorted(peluang, reverse=True))
        self.assertLessEqual(sum(peluang), 1.0)
        for s in scorelines:
            self.assertIsInstance(s["home_goals"], int)
            self.assertIsInstance(s["away_goals"], int)
            self.assertGreater(s["probability"], 0.0)

    def test_squad_scenarios_kosong(self):
        # Pemodelan absensi pemain bola BELUM ada — jangan dikarang.
        hasil = football_sim.simulate(
            buat_inputs(), buat_params(), buat_cfg(), seed=7, iterations=1000
        )
        self.assertEqual(hasil["squad_scenarios"], [])

    def test_lambda_di_inputs_summary(self):
        hasil = football_sim.simulate(
            buat_inputs(), buat_params(), buat_cfg(), seed=7, iterations=1000
        )
        ringkasan = hasil["inputs_summary"]
        # lam kandang = 1,15 x 0,95 x 1,55 = 1,693375.
        self.assertAlmostEqual(ringkasan["lambda_home"], 1.6934, places=4)
        # lam tandang = 1,05 x 0,85 x 1,20 = 1,071.
        self.assertAlmostEqual(ringkasan["lambda_away"], 1.071, places=4)
        self.assertEqual(ringkasan["league"], "EPL")
        self.assertEqual(ringkasan["fit_version"], "contoh-tes-0.1")

    def test_fixture_ars_che(self):
        fixture = json.loads(
            (
                REPO_ROOT / "tests" / "fixtures" / "soccer_sim_ars_che_inputs.json"
            ).read_text(encoding="utf-8")
        )
        hasil = football_sim.simulate(
            fixture["inputs"],
            fixture["params"],
            buat_cfg(),
            seed=fixture["seed"],
            iterations=10000,
        )
        self.assertIsNone(football_sim.validate_football_sim(hasil))
        self.assertEqual(hasil["match_id"], "ARS_CHE_2026-11-22")

    def test_runtime_100000_di_bawah_5_detik(self):
        mulai = time.perf_counter()
        hasil = football_sim.simulate(
            buat_inputs(), buat_params(), buat_cfg(), seed=7, iterations=100000
        )
        durasi = time.perf_counter() - mulai
        self.assertLess(durasi, 5.0)
        self.assertLess(hasil["inputs_summary"]["elapsed_seconds"], 5.0)


if __name__ == "__main__":
    unittest.main()
