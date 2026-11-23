"""Tes ekor 3 poin per laga — fit (scripts/fit_ekor_3p.py), sim
(engine/nba_sim.py ekor_3p), dan parser fg3 BBRef (ingest/bbref.py).

TANPA network. Semua data sintetis/fixture inline.
"""

import importlib.util
import json
import math
import random
import statistics
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import nba_sim  # noqa: E402
from ingest import bbref  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

_SPEK = importlib.util.spec_from_file_location(
    "fit_ekor_3p", REPO_ROOT / "scripts" / "fit_ekor_3p.py"
)
fit_ekor_3p = importlib.util.module_from_spec(_SPEK)
_SPEK.loader.exec_module(fit_ekor_3p)


# ---------------------------------------------------------------------------
# OLS
# ---------------------------------------------------------------------------


class TestOls(unittest.TestCase):
    def test_memulihkan_slope_dan_intersep(self):
        rng = random.Random(7)
        xs = [60.0 + i * 0.5 for i in range(100)]
        ys = [100.0 + 2.0 * x + rng.gauss(0, 5) for x in xs]
        hasil = fit_ekor_3p.ols(xs, ys)
        self.assertAlmostEqual(hasil["b"], 2.0, delta=0.2)
        self.assertAlmostEqual(hasil["a"], 100.0, delta=15.0)
        self.assertGreater(hasil["t_b"], 5.0)
        self.assertGreater(hasil["r2"], 0.9)
        self.assertEqual(hasil["n"], 100)

    def test_slope_nol_terdeteksi(self):
        rng = random.Random(3)
        xs = [60.0 + i * 0.5 for i in range(100)]
        ys = [225.0 + rng.gauss(0, 5) for _ in xs]
        hasil = fit_ekor_3p.ols(xs, ys)
        self.assertAlmostEqual(hasil["b"], 0.0, delta=0.2)
        self.assertLess(abs(hasil["t_b"]), 2.0)

    def test_n_kurang_dari_3_gagal(self):
        with self.assertRaises(ValueError):
            fit_ekor_3p.ols([1.0, 2.0], [1.0, 2.0])

    def test_varians_x_nol_gagal(self):
        with self.assertRaises(ValueError):
            fit_ekor_3p.ols([5.0, 5.0, 5.0], [1.0, 2.0, 3.0])


# ---------------------------------------------------------------------------
# Parse FG3A dari leaguegamefinder mentah
# ---------------------------------------------------------------------------

_HEADERS_FG3A = [
    "SEASON_ID",
    "TEAM_ID",
    "TEAM_ABBREVIATION",
    "TEAM_NAME",
    "GAME_ID",
    "GAME_DATE",
    "MATCHUP",
    "WL",
    "MIN",
    "FGA",
    "FG3M",
    "FG3A",
    "PTS",
]


def _baris_fg3a(tri, game_id, tanggal, matchup, wl, fga, fg3m, fg3a):
    return [
        "22024",
        1,
        tri,
        tri,
        game_id,
        tanggal,
        matchup,
        wl,
        240,
        fga,
        fg3m,
        fg3a,
        110,
    ]


def _payload_fg3a(baris):
    return {
        "resultSets": [
            {
                "name": "LeagueGameFinderResults",
                "headers": _HEADERS_FG3A,
                "rowSet": baris,
            }
        ]
    }


class TestParseFg3a(unittest.TestCase):
    def test_parse_dua_laga_selesai(self):
        payload = _payload_fg3a(
            [
                _baris_fg3a("ATL", "g1", "2024-10-22", "ATL vs. BOS", "W", 90, 12, 35),
                _baris_fg3a("BOS", "g1", "2024-10-22", "BOS @ ATL", "L", 88, 10, 30),
                _baris_fg3a("CHI", "g2", "2024-10-23", "CHI vs. DAL", "W", 92, 15, 40),
                _baris_fg3a("DAL", "g2", "2024-10-23", "DAL @ CHI", "L", 85, 9, 28),
            ]
        )
        records, info = fit_ekor_3p.parse_fg3a_team_game(payload, "2024-25")
        self.assertEqual(len(records), 4)
        self.assertEqual(info["n_laga_berjalan_dilewati"], 0)
        atl = [r for r in records if r["tricode"] == "ATL"][0]
        self.assertEqual(atl["game_id"], "g1")
        self.assertEqual(atl["game_date"], "2024-10-22")
        self.assertEqual(atl["fg3a"], 35.0)
        self.assertEqual(atl["fg3m"], 12.0)
        self.assertEqual(atl["fga"], 90.0)
        self.assertEqual(info["tanggal_awal"], "2024-10-22")
        self.assertEqual(info["tanggal_akhir"], "2024-10-23")

    def test_laga_berjalan_dilewati(self):
        # WL kosong = laga belum selesai saat snapshot (kasus 22 Nov).
        payload = _payload_fg3a(
            [
                _baris_fg3a("ATL", "g1", "2024-10-22", "ATL vs. BOS", "W", 90, 12, 35),
                _baris_fg3a("BOS", "g1", "2024-10-22", "BOS @ ATL", "L", 88, 10, 30),
                _baris_fg3a("DEN", "g9", "2026-11-22", "DEN @ CHI", "", 50, 10, 20),
                _baris_fg3a("CHI", "g9", "2026-11-22", "CHI vs. DEN", None, 55, 14, 28),
            ]
        )
        records, info = fit_ekor_3p.parse_fg3a_team_game(payload, "2026-27")
        self.assertEqual(len(records), 2)
        self.assertEqual(info["n_laga_berjalan_dilewati"], 2)
        self.assertEqual({r["tricode"] for r in records}, {"ATL", "BOS"})

    def test_baris_tanpa_angka_dilewati(self):
        baris = _baris_fg3a("ATL", "g1", "2024-10-22", "ATL vs. BOS", "W", 90, 12, 35)
        baris_tanpa = _baris_fg3a(
            "BOS", "g1", "2024-10-22", "BOS @ ATL", "L", 88, 10, None
        )
        payload = _payload_fg3a([baris, baris_tanpa])
        records, info = fit_ekor_3p.parse_fg3a_team_game(payload, "2024-25")
        self.assertEqual(len(records), 1)
        self.assertEqual(info["n_baris_tanpa_angka_dilewati"], 1)

    def test_resultset_hilang_gagal(self):
        with self.assertRaises(ValueError):
            fit_ekor_3p.parse_fg3a_team_game({"resultSets": []}, "2024-25")


# ---------------------------------------------------------------------------
# Laju 3PA point-in-time
# ---------------------------------------------------------------------------


def _riwayat_tim(tri, tanggal_awal, n_hari, fg3a_list, fg3m_list, fga=85):
    """Riwayat team-game sintetis: satu record per hari."""
    riwayat = []
    for i in range(n_hari):
        tanggal = tanggal_awal + timedelta(days=i)
        riwayat.append(
            {
                "season": "2024-25",
                "game_id": f"g{tri}{i}",
                "game_date": tanggal.isoformat(),
                "tricode": tri,
                "fg3a": float(fg3a_list[i]),
                "fg3m": float(fg3m_list[i]),
                "fga": float(fga),
            }
        )
    return riwayat


class TestLaju3paSebelum(unittest.TestCase):
    def test_nilai_hitung_tangan(self):
        # 10 laga: 3PA selang-seling 30/40 (rata-rata 35), 3PM 12/16.
        riwayat = _riwayat_tim(
            "ATL",
            date(2024, 10, 22),
            10,
            [30, 40] * 5,
            [12, 16] * 5,
        )
        laju = fit_ekor_3p.laju_3pa_sebelum(riwayat, "2024-11-01")
        self.assertIsNotNone(laju)
        self.assertEqual(laju["n_laga"], 10)
        self.assertAlmostEqual(laju["fg3a_per_game"], 35.0)
        self.assertAlmostEqual(laju["fg3_pct"], 140 / 350)
        self.assertAlmostEqual(laju["sd_3pm"], statistics.stdev([12, 16] * 5))
        self.assertAlmostEqual(laju["share_3pa"], 350 / 850)
        # Varians binomial: 35 x 0,4 x 0,6 x 9 = 75,6.
        self.assertAlmostEqual(laju["var3p_binom"], 75.6)

    def test_laga_tanggal_yang_sama_tidak_masuk(self):
        # Point-in-time: laga PADA tanggal uji tidak boleh memengaruhi
        # laju (laga itu belum dimainkan saat proyeksi dibuat).
        riwayat = _riwayat_tim(
            "ATL", date(2024, 10, 22), 10, [30, 40] * 5, [12, 16] * 5
        )
        riwayat.append(
            {
                "season": "2024-25",
                "game_id": "gATL10",
                "game_date": "2024-11-01",
                "tricode": "ATL",
                "fg3a": 100.0,
                "fg3m": 50.0,
                "fga": 120.0,
            }
        )
        laju = fit_ekor_3p.laju_3pa_sebelum(riwayat, "2024-11-01")
        self.assertEqual(laju["n_laga"], 10)
        self.assertAlmostEqual(laju["fg3a_per_game"], 35.0)

    def test_di_bawah_min_laga_none(self):
        riwayat = _riwayat_tim("ATL", date(2024, 10, 22), 4, [35] * 4, [12] * 4)
        self.assertIsNone(fit_ekor_3p.laju_3pa_sebelum(riwayat, "2024-11-01"))
        # Tepat di ambang (5) dipakai.
        riwayat = _riwayat_tim("ATL", date(2024, 10, 22), 5, [35] * 5, [12] * 5)
        self.assertIsNotNone(fit_ekor_3p.laju_3pa_sebelum(riwayat, "2024-11-01"))


# ---------------------------------------------------------------------------
# Fit ujung-ke-ujung pada data sintetis
# ---------------------------------------------------------------------------

_LAJU_TIM_SINTETIS = {"ATL": 30.0, "BOS": 35.0, "CHI": 40.0, "DAL": 45.0, "HOU": 50.0}
_PCT_TIM_SINTETIS = {"ATL": 0.34, "BOS": 0.35, "CHI": 0.36, "DAL": 0.37, "HOU": 0.38}
_RATING_SINTETIS = {"off_rtg": 110.0, "def_rtg": 110.0, "pace": 100.0}


def _bangun_data_sintetis(n_laga, slope_benar, seed=11):
    """Game log + rolling + FG3A sintetis dengan slope varians diketahui.

    Rating semua tim sama (mu 110-110 tiap laga); residual total
    dibangkitkan agar resid_total^2 ~ 100 + slope_benar x 3PA_gabung
    (dengan noise kecil), tanda selang-seling agar mean residual ~0.
    Mengembalikan (games, rolling, fg3a_records).
    """
    rng = random.Random(seed)
    tricodes = sorted(_LAJU_TIM_SINTETIS)
    fg3a_records: list[dict] = []
    for tri, laju in _LAJU_TIM_SINTETIS.items():
        # 3P% berbeda per tim + 3PM selang-seling +/-1 agar prediktor
        # alternatif (3P%, sd_3pm) ikut bervariasi.
        pct = _PCT_TIM_SINTETIS[tri]
        fg3m_list = [laju * pct + (1.0 if i % 2 == 0 else -1.0) for i in range(30)]
        fg3a_records.extend(
            _riwayat_tim(
                tri,
                date(2024, 10, 22),
                30,
                [laju] * 30,
                fg3m_list,
            )
        )
    games: list[dict] = []
    rolling: dict = {}
    tanggal_awal = date(2024, 11, 22)
    for i in range(n_laga):
        home = tricodes[i % 5]
        away = tricodes[(i + 1) % 5]
        tanggal = tanggal_awal + timedelta(days=i // 2)
        game_id = f"sint{i:04d}"
        pa3_gabung = _LAJU_TIM_SINTETIS[home] + _LAJU_TIM_SINTETIS[away]
        var_target = 100.0 + slope_benar * pa3_gabung
        resid = math.sqrt(var_target) * (1.0 + rng.gauss(0, 0.05))
        if rng.random() < 0.5:
            resid = -resid
        games.append(
            {
                "season": "2024-25",
                "game_date": tanggal.isoformat(),
                "game_id": game_id,
                "home_tricode": home,
                "away_tricode": away,
                "home_pts": 110.0 + resid / 2.0,
                "away_pts": 110.0 + resid / 2.0,
            }
        )
        rolling[game_id] = {
            "home_efektif": dict(_RATING_SINTETIS),
            "away_efektif": dict(_RATING_SINTETIS),
            "lg_avg_off_rtg": 110.0,
        }
    return games, rolling, fg3a_records


class TestFitEkor3p(unittest.TestCase):
    def test_memulihkan_slope_varians_benar(self):
        games, rolling, fg3a = _bangun_data_sintetis(200, slope_benar=2.0)
        hasil = fit_ekor_3p.fit_ekor_3p(games, rolling, fg3a, min_games_total=100)
        self.assertEqual(hasil["n_games_used"], 200)
        utama = hasil["regresi"]["varians_total_vs_3pa"]
        self.assertAlmostEqual(utama["slope"], 2.0, delta=0.5)
        self.assertAlmostEqual(utama["intersep"], 100.0, delta=40.0)
        self.assertGreater(utama["t_slope"], 2.0)
        self.assertEqual(hasil["verdict"], "SIGNIFIKAN")
        self.assertAlmostEqual(hasil["slope_aktif_direkomendasikan"], utama["slope"])
        # Tabel kuartil: 4 baris, n berjumlah 200, laju naik per kuartil.
        kuartil = hasil["kuartil_3pa"]
        self.assertEqual(len(kuartil), 4)
        self.assertEqual(sum(q["n"] for q in kuartil), 200)
        pa3_mean = [q["pa3_gabung_mean"] for q in kuartil]
        self.assertEqual(pa3_mean, sorted(pa3_mean))

    def test_slope_nol_verdict_tidak_signifikan(self):
        games, rolling, fg3a = _bangun_data_sintetis(200, slope_benar=0.0)
        hasil = fit_ekor_3p.fit_ekor_3p(games, rolling, fg3a, min_games_total=100)
        utama = hasil["regresi"]["varians_total_vs_3pa"]
        self.assertAlmostEqual(utama["slope"], 0.0, delta=0.5)
        self.assertEqual(hasil["verdict"], "TIDAK_SIGNIFIKAN")
        self.assertEqual(hasil["slope_aktif_direkomendasikan"], 0.0)

    def test_data_tidak_cukup_null(self):
        games, rolling, fg3a = _bangun_data_sintetis(5, slope_benar=2.0)
        hasil = fit_ekor_3p.fit_ekor_3p(games, rolling, fg3a, min_games_total=100)
        self.assertEqual(hasil["verdict"], "DATA_TIDAK_CUKUP")
        self.assertIsNone(hasil["regresi"]["varians_total_vs_3pa"].get("value"))
        self.assertIsNone(hasil["slope_aktif_direkomendasikan"])

    def test_laga_tanpa_laju_dilewati_dicatat(self):
        # Game di awal musim (belum 5 laga sebelumnya) dilewati.
        games, rolling, fg3a = _bangun_data_sintetis(10, slope_benar=2.0)
        games_dini = [
            dict(
                games[0],
                game_id="dini001",
                game_date="2024-10-23",
            )
        ]
        rolling["dini001"] = rolling[games[0]["game_id"]]
        hasil = fit_ekor_3p.fit_ekor_3p(
            games + games_dini, rolling, fg3a, min_games_total=1
        )
        self.assertEqual(hasil["n_games_skipped_no_laju_3pa"], 1)
        self.assertEqual(hasil["n_games_used"], 10)


# ---------------------------------------------------------------------------
# Config ekor_3p + rumus sigma per laga (engine/nba_sim.py)
# ---------------------------------------------------------------------------


class TestBacaEkor3p(unittest.TestCase):
    def test_section_tidak_ada_default_global(self):
        slope, pusat, min_f, max_f, dikonfigurasi = nba_sim._baca_ekor_3p({})
        self.assertEqual(
            (slope, pusat, min_f, max_f, dikonfigurasi), (0.0, None, 0.5, 2.0, False)
        )

    def test_section_lengkap_dibaca(self):
        cfg = {
            "ekor_3p": {
                "slope_aktif": 2.0,
                "tiga_pa_gabungan_rata_liga": 74.54,
                "sigma_min_faktor": 0.5,
                "sigma_max_faktor": 2.0,
            }
        }
        slope, pusat, min_f, max_f, dikonfigurasi = nba_sim._baca_ekor_3p(cfg)
        self.assertEqual(
            (slope, pusat, min_f, max_f, dikonfigurasi), (2.0, 74.54, 0.5, 2.0, True)
        )

    def test_slope_nol_tanpa_pusat_boleh(self):
        slope, pusat, _min_f, _max_f, dikonfigurasi = nba_sim._baca_ekor_3p(
            {"ekor_3p": {"slope_aktif": 0.0}}
        )
        self.assertEqual(slope, 0.0)
        self.assertIsNone(pusat)
        self.assertTrue(dikonfigurasi)

    def test_nilai_tidak_valid_gagal_keras(self):
        kasus_tidak_valid = [
            {"ekor_3p": {"slope_aktif": "besar"}},
            {"ekor_3p": {"slope_aktif": True}},
            {"ekor_3p": {"slope_aktif": 2.0}},  # slope != 0 tanpa pusat
            {"ekor_3p": {"slope_aktif": 0.0, "tiga_pa_gabungan_rata_liga": -5.0}},
            {"ekor_3p": {"sigma_min_faktor": 0.0}},
            {"ekor_3p": {"sigma_max_faktor": -1.0}},
            {"ekor_3p": {"sigma_min_faktor": 2.0, "sigma_max_faktor": 0.5}},
            {"ekor_3p": {"slope_aktif": float("inf")}},
        ]
        for cfg in kasus_tidak_valid:
            with self.assertRaises(ValueError, msg=str(cfg)):
                nba_sim._baca_ekor_3p(cfg)


class TestSigmaTotalPerLaga(unittest.TestCase):
    def test_rumus_hitung_tangan(self):
        # var = 17,5^2 + 2,0 x (90 - 74,54) = 306,25 + 30,92 = 337,17.
        sigma = nba_sim._sigma_total_per_laga(17.5, 2.0, 74.54, 0.5, 2.0, 90.0)
        self.assertAlmostEqual(sigma, math.sqrt(337.17), places=4)
        # Di bawah pusat: sigma mengecil.
        sigma_rendah = nba_sim._sigma_total_per_laga(17.5, 2.0, 74.54, 0.5, 2.0, 60.0)
        self.assertAlmostEqual(sigma_rendah, math.sqrt(306.25 - 29.08), places=4)
        self.assertLess(sigma_rendah, 17.5)
        # Slope 0 -> persis global.
        self.assertEqual(
            nba_sim._sigma_total_per_laga(17.5, 0.0, 74.54, 0.5, 2.0, 90.0), 17.5
        )

    def test_jepit_atas_dan_bawah(self):
        # Slope raksasa -> dijepit ke 2,0 x global.
        self.assertEqual(
            nba_sim._sigma_total_per_laga(17.5, 1000.0, 74.54, 0.5, 2.0, 90.0),
            35.0,
        )
        # Slope negatif raksasa -> dijepit ke 0,5 x global (bukan
        # akar varians negatif).
        self.assertEqual(
            nba_sim._sigma_total_per_laga(17.5, -1000.0, 74.54, 0.5, 2.0, 90.0),
            8.75,
        )


class TestLaju3pa(unittest.TestCase):
    def test_nilai_valid_dibaca(self):
        self.assertEqual(
            nba_sim._laju_3pa({"tembakan_3p": {"fg3a_per_game": 37.5}}), 37.5
        )

    def test_nilai_tidak_valid_none(self):
        for blok in (
            {},
            {"tembakan_3p": None},
            {"tembakan_3p": {}},
            {"tembakan_3p": {"fg3a_per_game": None}},
            {"tembakan_3p": {"fg3a_per_game": "37,5"}},
            {"tembakan_3p": {"fg3a_per_game": True}},
            {"tembakan_3p": {"fg3a_per_game": 0}},
            {"tembakan_3p": {"fg3a_per_game": -3.0}},
            {"tembakan_3p": {"fg3a_per_game": float("nan")}},
            {"tembakan_3p": {"fg3a_per_game": float("inf")}},
        ):
            self.assertIsNone(nba_sim._laju_3pa(blok), msg=str(blok))


# ---------------------------------------------------------------------------
# Integrasi simulate()
# ---------------------------------------------------------------------------


def _buat_cfg(ekor: dict | None = None) -> dict:
    """Config tes (mirror tests/test_nba_sim.py buat_cfg)."""
    cfg = {
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
    if ekor is not None:
        cfg["ekor_3p"] = ekor
    return cfg


def _blok_tim(tri, off, deff, pace, pa3=None):
    blok = {
        "tricode": tri,
        "team": tri,
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
        "rest_days": 2,
        "back_to_back": False,
        "altitude_home": False,
        "players": [],
        "injuries": [],
    }
    if pa3 is not None:
        blok["tembakan_3p"] = {
            "fg3a_per_game": pa3,
            "fg3_per_game": pa3 * 0.36,
            "fg3_pct": 0.36,
            "games": 15,
            "source": "Basketball-Reference",
            "tier": 2,
            "fetched_at": "2026-11-22T00:00:00+00:00",
        }
    return blok


def _buat_inputs(pa3_home=None, pa3_away=None):
    return {
        "match": {
            "home_tricode": "ATL",
            "away_tricode": "DET",
            "game_date": "2026-11-22",
            "season": "2026-27",
        },
        "home": _blok_tim("ATL", 115.0, 113.0, 100.0, pa3_home),
        "away": _blok_tim("DET", 114.0, 112.0, 99.0, pa3_away),
        "h2h_last5": [],
        "tournament": None,
        "league": {"avg_pace": 99.5, "avg_off_rtg": 114.0},
        "missing": [],
        "sources": [],
        "fetched_at": "2026-11-22T10:00:00+00:00",
    }


_EKOR_SLOPE_2 = {
    "slope_aktif": 2.0,
    "tiga_pa_gabungan_rata_liga": 74.54,
    "sigma_min_faktor": 0.5,
    "sigma_max_faktor": 2.0,
}


class TestSimEkor3p(unittest.TestCase):
    def test_slope_positif_laju_tinggi_sigma_membesar(self):
        hasil = nba_sim.simulate(
            _buat_inputs(pa3_home=45.0, pa3_away=45.0),
            cfg=_buat_cfg(_EKOR_SLOPE_2),
            seed=9,
            iterations=2000,
        )
        ringkasan = hasil["inputs_summary"]
        # var = 17,5^2 + 2,0 x (90 - 74,54) = 337,17.
        self.assertAlmostEqual(
            ringkasan["sigma_total_points"], math.sqrt(337.17), places=4
        )
        self.assertEqual(ringkasan["sigma_total_global_points"], 17.5)
        ekor = ringkasan["ekor_3p"]
        self.assertEqual(ekor["sumber_sigma"], "per_laga")
        self.assertEqual(ekor["tiga_pa_gabung"], 90.0)
        self.assertEqual(ekor["tiga_pa_kandang"], 45.0)
        self.assertEqual(ekor["tiga_pa_tandang"], 45.0)
        self.assertTrue(ekor["dikonfigurasi"])
        self.assertTrue(any("sigma_total per laga" in c for c in ringkasan["notes"]))

    def test_sigma_lebih_besar_peluang_under_lebih_kecil(self):
        # Garis di atas median: sebaran lebih lebar -> P(Under) turun.
        lines = {"spreads": [], "totals": [245.5]}
        global_ = nba_sim.simulate(
            _buat_inputs(pa3_home=45.0, pa3_away=45.0),
            cfg=_buat_cfg(),
            lines=lines,
            seed=9,
            iterations=20000,
        )
        cfg_lebar = _buat_cfg(dict(_EKOR_SLOPE_2, slope_aktif=10.0))
        lebar = nba_sim.simulate(
            _buat_inputs(pa3_home=45.0, pa3_away=45.0),
            cfg=cfg_lebar,
            lines=lines,
            seed=9,
            iterations=20000,
        )
        # sigma 17,5 -> akar(306,25 + 10 x 15,46) = 21,47.
        self.assertAlmostEqual(
            lebar["inputs_summary"]["sigma_total_points"],
            math.sqrt(306.25 + 10.0 * 15.46),
            places=4,
        )
        self.assertLess(
            lebar["markets"]["total_under_245.5"],
            global_["markets"]["total_under_245.5"],
        )

    def test_slope_nol_identik_dengan_model_lama(self):
        # Slope produksi (0) + data 3PA -> angka SAMA PERSIS dengan
        # model lama (tanpa section, tanpa data 3PA): seed sama.
        cfg_nol = _buat_cfg(
            {
                "slope_aktif": 0.0,
                "tiga_pa_gabungan_rata_liga": 74.54,
                "sigma_min_faktor": 0.5,
                "sigma_max_faktor": 2.0,
            }
        )
        baru = nba_sim.simulate(
            _buat_inputs(pa3_home=45.0, pa3_away=45.0),
            cfg=cfg_nol,
            seed=9,
            iterations=2000,
        )
        lama = nba_sim.simulate(
            _buat_inputs(), cfg=_buat_cfg(), seed=9, iterations=2000
        )
        self.assertEqual(baru["markets"], lama["markets"])
        self.assertEqual(baru["score_distribution"], lama["score_distribution"])
        self.assertEqual(
            baru["inputs_summary"]["sigma_total_points"],
            lama["inputs_summary"]["sigma_total_points"],
        )
        self.assertEqual(
            baru["inputs_summary"]["ekor_3p"]["sumber_sigma"], "global_slope_nol"
        )
        # ...tapi datanya TERCATAT (bukan hilang).
        self.assertEqual(baru["inputs_summary"]["ekor_3p"]["tiga_pa_gabung"], 90.0)

    def test_data_3pa_hilang_fallback_global_dicatat(self):
        hasil = nba_sim.simulate(
            _buat_inputs(pa3_home=45.0, pa3_away=None),
            cfg=_buat_cfg(_EKOR_SLOPE_2),
            seed=9,
            iterations=2000,
        )
        ringkasan = hasil["inputs_summary"]
        self.assertEqual(ringkasan["sigma_total_points"], 17.5)
        self.assertEqual(ringkasan["ekor_3p"]["sumber_sigma"], "global_tanpa_data_3pa")
        self.assertIsNone(ringkasan["ekor_3p"]["tiga_pa_gabung"])
        self.assertTrue(
            any("tidak tersedia" in c and "DET" in c for c in ringkasan["notes"])
        )

    def test_section_tidak_ada_global_dicatat(self):
        hasil = nba_sim.simulate(
            _buat_inputs(pa3_home=45.0, pa3_away=45.0),
            cfg=_buat_cfg(),
            seed=9,
            iterations=2000,
        )
        ringkasan = hasil["inputs_summary"]
        self.assertEqual(ringkasan["sigma_total_points"], 17.5)
        self.assertEqual(ringkasan["ekor_3p"]["sumber_sigma"], "global_tanpa_config")
        self.assertFalse(ringkasan["ekor_3p"]["dikonfigurasi"])
        self.assertTrue(any("tidak dikonfigurasi" in c for c in ringkasan["notes"]))

    def test_config_ekor_tidak_valid_gagal(self):
        with self.assertRaises(ValueError):
            nba_sim.simulate(
                _buat_inputs(pa3_home=45.0, pa3_away=45.0),
                cfg=_buat_cfg({"slope_aktif": 2.0}),
                iterations=100,
            )

    def test_hasil_valid_terhadap_skema(self):
        schema = json.loads(
            (REPO_ROOT / "schemas" / "simulation.schema.json").read_text(
                encoding="utf-8"
            )
        )
        hasil = nba_sim.simulate(
            _buat_inputs(pa3_home=45.0, pa3_away=45.0),
            cfg=_buat_cfg(_EKOR_SLOPE_2),
            seed=9,
            iterations=2000,
        )
        jsonschema.validate(instance=hasil, schema=schema)

    def test_deterministik_seed_sama(self):
        kwargs = {"cfg": _buat_cfg(_EKOR_SLOPE_2), "seed": 9, "iterations": 2000}
        pertama = nba_sim.simulate(_buat_inputs(45.0, 45.0), **kwargs)
        kedua = nba_sim.simulate(_buat_inputs(45.0, 45.0), **kwargs)
        self.assertEqual(pertama["markets"], kedua["markets"])


# ---------------------------------------------------------------------------
# Parser fg3 BBRef
# ---------------------------------------------------------------------------

_HTML_FG3 = """<html><body><table id="totals-team"><tbody>
<tr><td data-stat="team"><a href="/teams/DET/2027.html">Detroit Pistons</a></td>
<td data-stat="g">15</td><td data-stat="fg3">180</td>
<td data-stat="fg3a">532</td><td data-stat="fta">369</td></tr>
<tr><td data-stat="team"><a href="/teams/ATL/2027.html">Atlanta Hawks</a></td>
<td data-stat="g">16</td><td data-stat="fg3">220</td>
<td data-stat="fg3a">686</td><td data-stat="fta">326</td></tr>
</tbody></table></body></html>"""

_HTML_TANPA_FG3 = """<html><body><table id="totals-team"><tbody>
<tr><td data-stat="team"><a href="/teams/DET/2027.html">Detroit Pistons</a></td>
<td data-stat="g">15</td><td data-stat="fg3a">532</td>
<td data-stat="fta">369</td></tr>
</tbody></table></body></html>"""


class TestBbrefFg3(unittest.TestCase):
    def test_fg3_pct_dan_fg3_per_game(self):
        teams = bbref.parse_team_shooting_totals(_HTML_FG3)
        det = [t for t in teams if t["tricode"] == "DET"][0]
        self.assertAlmostEqual(det["fg3_per_game"], 180 / 15)
        self.assertAlmostEqual(det["fg3a_per_game"], 532 / 15)
        self.assertAlmostEqual(det["fg3_pct"], 180 / 532)
        atl = [t for t in teams if t["tricode"] == "ATL"][0]
        self.assertAlmostEqual(atl["fg3_pct"], 220 / 686)

    def test_tanpa_kolom_fg3_tidak_gagal(self):
        # Kolom fg3 tidak wajib: fg3_pct None, fg3a tetap mengalir.
        teams = bbref.parse_team_shooting_totals(_HTML_TANPA_FG3)
        self.assertEqual(len(teams), 1)
        self.assertIsNone(teams[0]["fg3_pct"])
        self.assertIsNone(teams[0]["fg3_per_game"])
        self.assertAlmostEqual(teams[0]["fg3a_per_game"], 532 / 15)

    def test_fg3a_nol_fg3_pct_none(self):
        html = _HTML_TANPA_FG3.replace(
            '<td data-stat="fg3a">532</td>', '<td data-stat="fg3a">0</td>'
        ).replace(
            '<td data-stat="g">15</td>',
            '<td data-stat="g">15</td><td data-stat="fg3">0</td>',
        )
        teams = bbref.parse_team_shooting_totals(html)
        self.assertIsNone(teams[0]["fg3_pct"])

    def test_fixture_lama_tanpa_fg3_tetap_terbaca(self):
        html = (
            REPO_ROOT / "tests" / "fixtures" / "live_anomaly_totals.html"
        ).read_text(encoding="utf-8")
        teams = bbref.parse_team_shooting_totals(html)
        self.assertEqual(len(teams), 2)
        for tim in teams:
            self.assertIsNone(tim["fg3_pct"])
            self.assertIsNotNone(tim["fg3a_per_game"])


if __name__ == "__main__":
    unittest.main()
