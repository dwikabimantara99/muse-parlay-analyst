"""Tes engine/nba_sim.py — determinisme, skema, OT, skenario, validasi.

TANPA network. Tes unit memakai iterations kecil via parameter; SATU tes
kecepatan memakai 100.000 iterasi penuh (batas waktu longgar).
"""

import copy
import json
import random
import sys
import unittest
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine import nba_sim

REPO_ROOT = Path(__file__).resolve().parent.parent


def buat_cfg() -> dict:
    """Config tes lengkap (nilai parameter fiktif tapi realistis)."""
    return {
        "simulation": {
            "iterations": 100000,
            "nba": {
                "sigma_margin_points": 13.5,
                "sigma_total_points": 17.5,
                "t_nu": 6.0,
                "bpm_scale": 1.0,
                "bpm_replacement": -2.0,
                "home_advantage_points": 2.5,
                "back_to_back_penalty_points": -1.5,
                "altitude_adjustment_points": 1.0,
                "tournament_adjustment_points": 0.0,
                "overtime_minutes": 5,
                "ot_max_periods": 5,
                "recency": {"season": 0.6, "last10": 0.4},
                "squad_scenarios": ["full", "missing_1", "missing_2", "missing_4"],
            },
        },
    }


def _blok_tim(
    tricode: str,
    team: str,
    off: float,
    deff: float,
    pace: float,
    players: list[dict],
    injuries: list[dict] | None = None,
    b2b: bool | None = False,
    rest: int | None = 2,
    altitude: bool = False,
) -> dict:
    """Satu blok tim sesuai kontrak ingest.nba_brain."""
    return {
        "tricode": tricode,
        "team": team,
        "stats_season": {
            "off_rtg": off,
            "def_rtg": deff,
            "net_rtg": off - deff,
            "pace": pace,
        },
        "stats_last10": {
            "off_rtg": off + 0.5,
            "def_rtg": deff - 0.5,
            "net_rtg": off - deff + 1.0,
            "pace": pace + 0.3,
        },
        "form5": [],
        "home_record": {"w": 10, "l": 5, "ppg": 110.0, "opp_ppg": 105.0},
        "road_record": {"w": 8, "l": 7, "ppg": 108.0, "opp_ppg": 107.0},
        "rest_days": rest,
        "back_to_back": b2b,
        "altitude_home": altitude,
        "players": players,
        "injuries": injuries or [],
    }


def buat_inputs() -> dict:
    """Fixture laga DET @ ATL (angka fiktif, realistis)."""
    pemain_kandang = [
        {
            "player": "Bintang Home",
            "bpm": 8.0,
            "mp_per_game": 36.0,
            "team_tricode": "ATL",
        },
        {
            "player": "Starter Home 2",
            "bpm": 3.0,
            "mp_per_game": 30.0,
            "team_tricode": "ATL",
        },
        {
            "player": "Starter Home 3",
            "bpm": 1.5,
            "mp_per_game": 28.0,
            "team_tricode": "ATL",
        },
        {
            "player": "Rotasi Home",
            "bpm": 0.5,
            "mp_per_game": 18.0,
            "team_tricode": "ATL",
        },
    ]
    pemain_tandang = [
        {
            "player": "Bintang Away",
            "bpm": 7.0,
            "mp_per_game": 35.0,
            "team_tricode": "DET",
        },
        {
            "player": "Starter Away 2",
            "bpm": 2.5,
            "mp_per_game": 29.0,
            "team_tricode": "DET",
        },
        {
            "player": "Starter Away 3",
            "bpm": 1.0,
            "mp_per_game": 25.0,
            "team_tricode": "DET",
        },
        {
            "player": "Rotasi Away",
            "bpm": 0.0,
            "mp_per_game": 15.0,
            "team_tricode": "DET",
        },
    ]
    return {
        "match": {
            "home_tricode": "ATL",
            "away_tricode": "DET",
            "game_date": "2026-11-22",
            "season": "2026-27",
        },
        "home": _blok_tim("ATL", "Atlanta Hawks", 115.0, 113.0, 100.0, pemain_kandang),
        "away": _blok_tim("DET", "Detroit Pistons", 114.0, 112.0, 99.0, pemain_tandang),
        "h2h_last5": [],
        "tournament": None,
        "league": {"avg_pace": 99.5, "avg_off_rtg": 114.0},
        "missing": [],
        "sources": [],
        "fetched_at": "2026-11-22T10:00:00+00:00",
    }


def _tanpa_variabel_waktu(hasil: dict) -> dict:
    """Salinan hasil tanpa generated_at/elapsed (berubah tiap run)."""
    salinan = copy.deepcopy(hasil)
    salinan.pop("generated_at", None)
    salinan.get("inputs_summary", {}).pop("elapsed_seconds", None)
    return salinan


class TestProjectPoints(unittest.TestCase):
    def test_rumus_hitung_tangan(self):
        # pace = (100+98)/2 = 99. off kandang = 115+(111-113) = 113
        # (lawan bertahan di bawah rata-rata -> kandang cetak lebih
        # sedikit dari ratingnya). off tandang = 112+(110-113) = 109.
        # mu = 113*0.99, 109*0.99.
        mu_h, mu_a, pace = nba_sim.project_points(
            {"off_rtg": 115.0, "def_rtg": 110.0, "pace": 100.0},
            {"off_rtg": 112.0, "def_rtg": 111.0, "pace": 98.0},
            113.0,
        )
        self.assertAlmostEqual(pace, 99.0)
        self.assertAlmostEqual(mu_h, 111.87, places=2)
        self.assertAlmostEqual(mu_a, 107.91, places=2)

    def test_margin_proyeksi_sama_dengan_selisih_net_rating(self):
        # Sifat rumus yang benar: margin proyeksi = selisih net rating
        # x pace/100. (Dengan tanda penyesuaian yang terbalik, sifat ini
        # gagal — itulah bug yang tertangkap fit data nyata 2026-11-22.)
        mu_h, mu_a, pace = nba_sim.project_points(
            {"off_rtg": 118.0, "def_rtg": 112.0, "pace": 101.0},
            {"off_rtg": 110.0, "def_rtg": 113.0, "pace": 99.0},
            114.0,
        )
        net_diff = (118.0 - 112.0) - (110.0 - 113.0)
        self.assertAlmostEqual(mu_h - mu_a, net_diff * pace / 100.0, places=9)


class TestStudentT(unittest.TestCase):
    def test_momen_sampler(self):
        # 50000 draw t(5) diskalakan: mean ~0, std ~1, ekor tebal.
        rng = random.Random(42)
        draws = [nba_sim._student_t_draw(rng, 5.0) for _ in range(50000)]
        mean = sum(draws) / len(draws)
        var = sum((x - mean) ** 2 for x in draws) / len(draws)
        ekor = sum(1 for x in draws if abs(x) > 3.0) / len(draws)
        self.assertLess(abs(mean), 0.05)
        self.assertLess(abs(var**0.5 - 1.0), 0.05)
        # Ekor t(5) jauh lebih tebal dari normal (P(|Z|>3) = 0,0027).
        self.assertGreater(ekor, 0.005)


class TestSimulate(unittest.TestCase):
    def test_determinisme_seed(self):
        hasil1 = nba_sim.simulate(
            buat_inputs(), cfg=buat_cfg(), seed=7, iterations=2000
        )
        hasil2 = nba_sim.simulate(
            buat_inputs(), cfg=buat_cfg(), seed=7, iterations=2000
        )
        self.assertEqual(
            json.dumps(_tanpa_variabel_waktu(hasil1), sort_keys=True),
            json.dumps(_tanpa_variabel_waktu(hasil2), sort_keys=True),
        )

    def test_validasi_skema(self):
        schema = json.loads(
            (REPO_ROOT / "schemas" / "simulation.schema.json").read_text(
                encoding="utf-8"
            )
        )
        hasil = nba_sim.simulate(
            buat_inputs(),
            cfg=buat_cfg(),
            lines={"spreads": [-5.5, 5.5], "totals": [224.5]},
            seed=11,
            iterations=1000,
        )
        jsonschema.validate(instance=hasil, schema=schema)
        self.assertEqual(hasil["sport"], "nba")
        self.assertEqual(hasil["match_id"], "DET@ATL_2026-11-22")
        self.assertEqual(hasil["engine"]["name"], "nba_sim")
        self.assertEqual(hasil["engine"]["seed"], 11)
        self.assertEqual(hasil["iterations"], 1000)

    def test_semua_peluang_0_sampai_1(self):
        hasil = nba_sim.simulate(
            buat_inputs(),
            cfg=buat_cfg(),
            lines={"spreads": [-5.5], "totals": [224.5]},
            seed=3,
            iterations=2000,
        )
        for kunci, nilai in hasil["markets"].items():
            with self.subTest(kunci=kunci):
                self.assertGreaterEqual(nilai, 0.0)
                self.assertLessEqual(nilai, 1.0)
        for skenario in hasil["squad_scenarios"]:
            for kunci, nilai in skenario["markets"].items():
                with self.subTest(skenario=skenario["scenario"], kunci=kunci):
                    self.assertGreaterEqual(nilai, 0.0)
                    self.assertLessEqual(nilai, 1.0)

    def test_ot_terhitung(self):
        hasil = nba_sim.simulate(
            buat_inputs(), cfg=buat_cfg(), seed=5, iterations=20000
        )
        ot = hasil["score_distribution"]["ot_probability"]
        # Model: P(seri) ~ 3% (margin std 13,5). Rentang longgar.
        self.assertGreater(ot, 0.01)
        self.assertLess(ot, 0.06)

    def test_skenario_mengubah_peluang_ke_arah_benar(self):
        hasil = nba_sim.simulate(
            buat_inputs(), cfg=buat_cfg(), seed=9, iterations=20000
        )
        per_skenario = {s["scenario"]: s["markets"] for s in hasil["squad_scenarios"]}
        ml_full = per_skenario["full"]["moneyline_home"]
        ml_m1 = per_skenario["missing_1"]["moneyline_home"]
        ml_m2 = per_skenario["missing_2"]["moneyline_home"]
        ml_m4 = per_skenario["missing_4"]["moneyline_home"]
        # Bintang kandang (BPM 8, 36 menit, replacement -2 -> 7,5 poin)
        # absen -> peluang kandang menang turun. missing_2 juga
        # mengeluarkan bintang tandang (6,56 poin) -> peluang kandang
        # naik kembali dibanding missing_1, tapi tetap di bawah full
        # (net -0,94 poin). missing_4 menambah 2 pemain lapis kedua
        # (net -1,34 vs full).
        self.assertLess(ml_m1, ml_full)
        self.assertLess(ml_m1, ml_m2)
        self.assertLess(ml_m2, ml_full)
        self.assertLess(ml_m4, ml_m2)
        # Pemain yang absen tercatat.
        absen_m1 = next(
            s["absent_players"]
            for s in hasil["squad_scenarios"]
            if s["scenario"] == "missing_1"
        )
        self.assertEqual(absen_m1, ["Bintang Home"])

    def test_out_absen_di_base_case(self):
        inputs = buat_inputs()
        inputs["home"]["injuries"] = [
            {
                "player": "Bintang Home",
                "status": "OUT",
                "team_tricode": "ATL",
                "sources": ["nba.com"],
            }
        ]
        hasil = nba_sim.simulate(inputs, cfg=buat_cfg(), seed=9, iterations=20000)
        per_skenario = {s["scenario"]: s["markets"] for s in hasil["squad_scenarios"]}
        # Base case (OUT absen) peluang kandangnya di bawah skenario full.
        self.assertLess(
            hasil["markets"]["moneyline_home"],
            per_skenario["full"]["moneyline_home"],
        )
        self.assertIn("Bintang Home", hasil["inputs_summary"]["base_absent_players"])
        # missing_1 memakai pemain tersedia berikutnya (bintang sudah OUT).
        absen_m1 = next(
            s["absent_players"]
            for s in hasil["squad_scenarios"]
            if s["scenario"] == "missing_1"
        )
        self.assertIn("Bintang Home", absen_m1)
        self.assertIn("Starter Home 2", absen_m1)

    def test_doubtful_out_dibuatkan_skenario(self):
        inputs = buat_inputs()
        inputs["away"]["injuries"] = [
            {
                "player": "Bintang Away",
                "status": "QUESTIONABLE",
                "team_tricode": "DET",
                "sources": ["nba.com"],
            }
        ]
        hasil = nba_sim.simulate(inputs, cfg=buat_cfg(), seed=9, iterations=5000)
        nama_skenario = [s["scenario"] for s in hasil["squad_scenarios"]]
        self.assertIn("doubtful_out", nama_skenario)
        skenario = next(
            s for s in hasil["squad_scenarios"] if s["scenario"] == "doubtful_out"
        )
        self.assertIn("Bintang Away", skenario["absent_players"])
        # Base case: pemain QUESTIONABLE tetap bermain (tidak di base_absent).
        self.assertNotIn("Bintang Away", hasil["inputs_summary"]["base_absent_players"])

    def test_skenario_kustom_arbitrer(self):
        # Contoh user: 3 bintang vs 2 bintang (per tim arbitrer).
        hasil = nba_sim.simulate(
            buat_inputs(),
            cfg=buat_cfg(),
            scenarios=[
                {
                    "name": "tiga_vs_dua",
                    "home_out": ["Starter Home 3"],
                    "away_out": ["Bintang Away", "Starter Away 2"],
                }
            ],
            seed=9,
            iterations=5000,
        )
        self.assertEqual(len(hasil["squad_scenarios"]), 1)
        skenario = hasil["squad_scenarios"][0]
        self.assertEqual(skenario["scenario"], "tiga_vs_dua")
        self.assertEqual(
            skenario["absent_players"],
            ["Bintang Away", "Starter Away 2", "Starter Home 3"],
        )

    def test_garis_default_total_median(self):
        hasil = nba_sim.simulate(
            buat_inputs(), cfg=buat_cfg(), lines=None, seed=9, iterations=2000
        )
        total_proyeksi = hasil["inputs_summary"]["projected_total"]
        garis = round(total_proyeksi * 2) / 2  # ke 0,5 terdekat
        # Kunci garis default harus ada (median dibulatkan ke .5).
        kunci_under = [k for k in hasil["markets"] if k.startswith("total_under_")]
        self.assertEqual(len(kunci_under), 1)
        garis_dari_kunci = float(kunci_under[0].removeprefix("total_under_"))
        self.assertAlmostEqual(garis_dari_kunci, garis, delta=0.5)
        self.assertIn("moneyline_home", hasil["markets"])

    def test_data_tidak_lengkap_melempar(self):
        # Statistik musim kandang hilang.
        inputs = buat_inputs()
        inputs["home"]["stats_season"] = None
        with self.assertRaises(ValueError) as ctx:
            nba_sim.simulate(inputs, cfg=buat_cfg(), iterations=100)
        self.assertIn("data_tidak_lengkap", str(ctx.exception))
        # Satu field musim hilang.
        inputs = buat_inputs()
        inputs["away"]["stats_season"]["pace"] = None
        with self.assertRaises(ValueError) as ctx:
            nba_sim.simulate(inputs, cfg=buat_cfg(), iterations=100)
        self.assertIn("data_tidak_lengkap", str(ctx.exception))
        # Blok away hilang.
        inputs = buat_inputs()
        del inputs["away"]
        with self.assertRaises(ValueError):
            nba_sim.simulate(inputs, cfg=buat_cfg(), iterations=100)

    def test_last10_hilang_pakai_musim_saja(self):
        inputs = buat_inputs()
        inputs["home"]["stats_last10"] = None
        hasil = nba_sim.simulate(inputs, cfg=buat_cfg(), seed=1, iterations=500)
        catatan = hasil["inputs_summary"]["notes"]
        self.assertTrue(any("stats_last10" in c for c in catatan))
        self.assertIn("moneyline_home", hasil["markets"])

    def test_parameter_null_melempar_config_error(self):
        cfg = buat_cfg()
        cfg["simulation"]["nba"]["sigma_margin_points"] = None
        with self.assertRaises(config_mod.ConfigError) as ctx:
            nba_sim.simulate(buat_inputs(), cfg=cfg, iterations=100)
        self.assertIn("parameter_belum_difit", str(ctx.exception))

    def test_seed_bukan_integer_ditolak(self):
        with self.assertRaises(ValueError):
            nba_sim.simulate(buat_inputs(), cfg=buat_cfg(), seed="abc")

    def test_simulate_dengan_config_asli(self):
        # Integrasi: config repo (nilai fit) + input fixture.
        cfg = config_mod.load_playstyle()
        hasil = nba_sim.simulate(buat_inputs(), cfg=cfg, seed=2, iterations=1000)
        self.assertEqual(hasil["iterations"], 1000)
        self.assertIn("moneyline_home", hasil["markets"])

    def test_kecepatan_100k(self):
        # SATU tes 100.000 iterasi penuh (batas longgar 120 detik).
        hasil = nba_sim.simulate(buat_inputs(), cfg=buat_cfg(), seed=13)
        self.assertEqual(hasil["iterations"], 100000)
        elapsed = hasil["inputs_summary"]["elapsed_seconds"]
        self.assertLess(elapsed, 120.0)


class TestReplacementLevelDanOverlap(unittest.TestCase):
    """Patch langkah 1b perbaikan 2 (temuan auditor 2): replacement
    level + koreksi tumpang-tindih last10."""

    def test_dampak_pemain_rumus_replacement(self):
        # (BPM - (-2,0)) x mp/48 x skala x faktor (missed 0 -> 1,0).
        dampak, note = nba_sim._dampak_pemain(
            {"player": "A", "bpm": 8.8, "mp_per_game": 30.0, "missed_last10": 0},
            1.0,
            -2.0,
            0.4,
        )
        self.assertAlmostEqual(dampak, (8.8 + 2.0) * 30 / 48, places=9)
        self.assertIsNone(note)
        # BPM negatif di atas replacement: dampak tetap POSITIF.
        dampak, _ = nba_sim._dampak_pemain(
            {"player": "B", "bpm": -1.0, "mp_per_game": 24.0, "missed_last10": 0},
            1.0,
            -2.0,
            0.4,
        )
        self.assertAlmostEqual(dampak, 0.5, places=9)
        # BPM di bawah replacement: dampak NEGATIF — penggantinya
        # (level -2,0) lebih baik darinya. Jawaban jujur model.
        dampak, _ = nba_sim._dampak_pemain(
            {"player": "C", "bpm": -3.0, "mp_per_game": 24.0, "missed_last10": 0},
            1.0,
            -2.0,
            0.4,
        )
        self.assertAlmostEqual(dampak, -0.5, places=9)
        # Tanpa BPM/menit: dampak 0.
        dampak, _ = nba_sim._dampak_pemain({"player": "D"}, 1.0, -2.0, 0.4)
        self.assertEqual(dampak, 0.0)

    def test_faktor_overlap_duren_7_dari_10(self):
        # Gaya Duren: BPM 8,8, 30 menit, absen 7 dari 10 laga terakhir
        # tim -> faktor (1 - 0,4 x 7/10) = 0,72; dampak 10,8 x 30/48
        # x 0,72 = 4,86 (tanpa koreksi: 6,75).
        dampak, note = nba_sim._dampak_pemain(
            {
                "player": "Duren",
                "bpm": 8.8,
                "mp_per_game": 30.0,
                "missed_last10": 7,
            },
            1.0,
            -2.0,
            0.4,
        )
        self.assertAlmostEqual(dampak, 10.8 * 30 / 48 * 0.72, places=9)
        self.assertAlmostEqual(dampak, 4.86, places=9)
        self.assertIsNone(note)
        # missed 0 -> faktor 1,0; missed 10 -> faktor 0,6.
        dampak_0, _ = nba_sim._dampak_pemain(
            {"player": "X", "bpm": 5.0, "mp_per_game": 24.0, "missed_last10": 0},
            1.0,
            -2.0,
            0.4,
        )
        dampak_10, _ = nba_sim._dampak_pemain(
            {"player": "X", "bpm": 5.0, "mp_per_game": 24.0, "missed_last10": 10},
            1.0,
            -2.0,
            0.4,
        )
        self.assertAlmostEqual(dampak_0, 7.0 * 0.5, places=9)
        self.assertAlmostEqual(dampak_10, 7.0 * 0.5 * 0.6, places=9)

    def test_pemain_bpm_negatif_absen_tidak_menaikkan_proyeksi(self):
        # Temuan auditor: 4 pemain cadangan BPM negatif MENAIKKAN total
        # DET-ATL +3,67 dengan rumus lama. Dengan replacement level,
        # pemain BPM -1 yang absen MENURUNKAN proyeksi timnya sebesar
        # (-1 + 2) x 20/48 = 0,4167 poin.
        inputs = buat_inputs()
        inputs["home"]["players"].append(
            {
                "player": "Cadangan Negatif",
                "bpm": -1.0,
                "mp_per_game": 20.0,
                "team_tricode": "ATL",
            }
        )
        hasil_sehat = nba_sim.simulate(inputs, cfg=buat_cfg(), seed=9, iterations=500)
        inputs["home"]["injuries"] = [
            {
                "player": "Cadangan Negatif",
                "status": "OUT",
                "team_tricode": "ATL",
                "sources": ["tes"],
            }
        ]
        hasil_cedera = nba_sim.simulate(inputs, cfg=buat_cfg(), seed=9, iterations=500)
        self.assertAlmostEqual(
            hasil_sehat["inputs_summary"]["projected_home_points"]
            - hasil_cedera["inputs_summary"]["projected_home_points"],
            0.4167,
            delta=0.02,
        )
        self.assertLess(
            hasil_cedera["inputs_summary"]["projected_total"],
            hasil_sehat["inputs_summary"]["projected_total"],
        )

    def test_missed_last10_hilang_faktor_1_dan_catatan(self):
        inputs = buat_inputs()
        inputs["home"]["injuries"] = [
            {
                "player": "Bintang Home",
                "status": "OUT",
                "team_tricode": "ATL",
                "sources": ["tes"],
            }
        ]
        hasil = nba_sim.simulate(inputs, cfg=buat_cfg(), seed=9, iterations=500)
        catatan = hasil["inputs_summary"]["notes"]
        self.assertTrue(
            any("missed_last10 Bintang Home tidak ada" in c for c in catatan)
        )
        # Faktor 1,0: proyeksi kandang turun penuh 7,5 poin vs sehat.
        hasil_sehat = nba_sim.simulate(
            buat_inputs(), cfg=buat_cfg(), seed=9, iterations=500
        )
        self.assertAlmostEqual(
            hasil_sehat["inputs_summary"]["projected_home_points"]
            - hasil["inputs_summary"]["projected_home_points"],
            7.5,
            delta=0.02,
        )

    def test_missed_last10_mengurangi_dampak_di_simulasi(self):
        # Bintang Home OUT dengan missed 7/10 -> dampak 7,5 x 0,72 = 5,4
        # (bukan 7,5); tidak ada catatan missed_last10 untuknya.
        inputs = buat_inputs()
        inputs["home"]["players"][0]["missed_last10"] = 7
        inputs["home"]["injuries"] = [
            {
                "player": "Bintang Home",
                "status": "OUT",
                "team_tricode": "ATL",
                "sources": ["tes"],
            }
        ]
        hasil = nba_sim.simulate(inputs, cfg=buat_cfg(), seed=9, iterations=500)
        self.assertFalse(
            any("Bintang Home" in c for c in hasil["inputs_summary"]["notes"])
        )
        hasil_sehat = nba_sim.simulate(
            buat_inputs(), cfg=buat_cfg(), seed=9, iterations=500
        )
        self.assertAlmostEqual(
            hasil_sehat["inputs_summary"]["projected_home_points"]
            - hasil["inputs_summary"]["projected_home_points"],
            5.4,
            delta=0.02,
        )

    def test_missed_last10_tidak_valid_faktor_1_dan_catatan(self):
        for buruk in (11, -1, "tujuh", True, 2.5):
            with self.subTest(missed_last10=buruk):
                dampak, note = nba_sim._dampak_pemain(
                    {
                        "player": "X",
                        "bpm": 5.0,
                        "mp_per_game": 24.0,
                        "missed_last10": buruk,
                    },
                    1.0,
                    -2.0,
                    0.4,
                )
                self.assertAlmostEqual(dampak, 7.0 * 0.5, places=9)
                self.assertIsNotNone(note)
                self.assertIn("tidak valid", note)

    def test_tiga_bintang_vs_dua_bintang(self):
        # Skenario arbitrer: 3 pemain inti kandang absen vs 2 inti
        # tandang. Dampak eksplisit (replacement -2,0, faktor 1,0):
        # kandang 7,5 + 3,125 + 2,0417 = 12,6667; tandang 6,5625 +
        # 2,71875 = 9,28125; net margin -3,3854 vs full.
        inputs = buat_inputs()
        dampak_kandang = sum(
            nba_sim._dampak_pemain(p, 1.0, -2.0, 0.4)[0]
            for p in inputs["home"]["players"][:3]
        )
        dampak_tandang = sum(
            nba_sim._dampak_pemain(p, 1.0, -2.0, 0.4)[0]
            for p in inputs["away"]["players"][:2]
        )
        self.assertAlmostEqual(dampak_kandang, 12.6667, places=4)
        self.assertAlmostEqual(dampak_tandang, 9.28125, places=4)
        self.assertAlmostEqual(dampak_kandang - dampak_tandang, 3.3854, places=4)
        # Arah + besaran di peluang: kandang jauh lebih kecil dari full.
        hasil = nba_sim.simulate(
            buat_inputs(),
            cfg=buat_cfg(),
            scenarios=[
                {"name": "full", "home_out": [], "away_out": []},
                {
                    "name": "tiga_vs_dua",
                    "home_out": ["Bintang Home", "Starter Home 2", "Starter Home 3"],
                    "away_out": ["Bintang Away", "Starter Away 2"],
                },
            ],
            seed=9,
            iterations=20000,
        )
        per_skenario = {s["scenario"]: s["markets"] for s in hasil["squad_scenarios"]}
        ml_full = per_skenario["full"]["moneyline_home"]
        ml_sken = per_skenario["tiga_vs_dua"]["moneyline_home"]
        self.assertLess(ml_sken, ml_full)
        # Selisih margin -3,39 pada sigma margin 13,5 -> peluang kandang
        # turun > 5 poin persentase (seed tetap, deterministik).
        self.assertLess(ml_sken, ml_full - 0.05)

    def test_p74_hadir_di_output(self):
        hasil = nba_sim.simulate(buat_inputs(), cfg=buat_cfg(), seed=9, iterations=5000)
        total = hasil["score_distribution"]["total"]
        self.assertIn("p74", total)
        self.assertLessEqual(total["median"], total["p74"])
        self.assertLessEqual(total["p74"], total["p75"])

    def test_bpm_replacement_null_melempar_config_error(self):
        cfg = buat_cfg()
        cfg["simulation"]["nba"]["bpm_replacement"] = None
        with self.assertRaises(config_mod.ConfigError) as ctx:
            nba_sim.simulate(buat_inputs(), cfg=cfg, iterations=100)
        self.assertIn("parameter_belum_difit", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
