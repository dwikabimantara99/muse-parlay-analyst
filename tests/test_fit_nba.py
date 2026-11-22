"""Tes scripts/fit_nba_params.py — fit pada data sintetis dengan parameter
diketahui: estimasi harus mendekati nilai benar. TANPA network.

Data sintetis dibangkitkan dengan parameter "benar" yang diketahui
(HA +2,5; sigma margin 12; sigma total 17; penalti B2B -2,0;
altitude +1,5; nu 6), lalu fit_parameters harus memulihkannya dalam
toleransi statistik yang longgar.
"""

import importlib.util
import random
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import nba_sim
from ingest.stats_nba import TEAM_TRICODES

REPO_ROOT = Path(__file__).resolve().parent.parent

_SPEK = importlib.util.spec_from_file_location(
    "fit_nba_params", REPO_ROOT / "scripts" / "fit_nba_params.py"
)
fit_nba_params = importlib.util.module_from_spec(_SPEK)
_SPEK.loader.exec_module(fit_nba_params)

# Parameter "benar" data sintetis.
HA_BENAR = 2.5
SIGMA_MARGIN_BENAR = 12.0
SIGMA_TOTAL_BENAR = 17.0
B2B_BENAR = -2.0
ALT_BENAR = 1.5
NU_BENAR = 6.0

TRICODES = sorted(set(TEAM_TRICODES.values()))


def buat_data_sintetis(seed: int = 123, n_laga_per_musim: int = 1000):
    """Bangkitkan (games, ratings) sintetis dengan parameter diketahui.

    Skor dibuat dari proyeksi project_points + penyesuaian benar +
    noise Student-t. B2B dideteksi dari jadwal dulu (logika yang sama
    dengan fit), lalu penaltinya diterapkan ke skor.
    """
    rng = random.Random(seed)
    musim_list = ["2024-25", "2025-26"]
    ratings: dict[str, dict[str, dict[str, float]]] = {}
    for musim in musim_list:
        per_tim = {}
        for tricode in TRICODES:
            off = rng.gauss(114.0, 2.5)
            deff = rng.gauss(114.0, 2.5)
            per_tim[tricode] = {
                "off_rtg": round(off, 2),
                "def_rtg": round(deff, 2),
                "net_rtg": round(off - deff, 2),
                "pace": round(rng.gauss(99.0, 1.5), 2),
            }
        ratings[musim] = per_tim

    # Jadwal dulu (tim + tanggal), agar B2B bisa dideteksi sebelum skor dibuat.
    jadwal: list[dict] = []
    for musim in musim_list:
        awal = date(2025, 10, 21) if musim == "2024-25" else date(2026, 10, 20)
        for i in range(n_laga_per_musim):
            home, away = rng.sample(TRICODES, 2)
            tanggal = awal + timedelta(days=rng.randrange(170))
            jadwal.append(
                {
                    "season": musim,
                    "game_date": tanggal.isoformat(),
                    "game_id": f"{musim}-{i:05d}",
                    "home_tricode": home,
                    "away_tricode": away,
                }
            )
    b2b = fit_nba_params.detect_back_to_back(jadwal)
    games: list[dict] = []
    for game in jadwal:
        musim = game["season"]
        rating_musim = ratings[musim]
        lg_avg = sum(r["off_rtg"] for r in rating_musim.values()) / 30.0
        mu_home, mu_away, _pace = nba_sim.project_points(
            rating_musim[game["home_tricode"]],
            rating_musim[game["away_tricode"]],
            lg_avg,
        )
        noise_margin = nba_sim._student_t_draw(rng, NU_BENAR) * SIGMA_MARGIN_BENAR
        noise_total = nba_sim._student_t_draw(rng, NU_BENAR) * SIGMA_TOTAL_BENAR
        home_pts = mu_home + HA_BENAR / 2.0 + noise_margin / 2.0 + noise_total / 2.0
        away_pts = mu_away - HA_BENAR / 2.0 - noise_margin / 2.0 + noise_total / 2.0
        if game["home_tricode"] in ("DEN", "UTA"):
            home_pts += ALT_BENAR / 2.0
            away_pts -= ALT_BENAR / 2.0
        game_id = game["game_id"]
        if b2b.get(f"{game_id}:{game['home_tricode']}", False):
            home_pts += B2B_BENAR
        if b2b.get(f"{game_id}:{game['away_tricode']}", False):
            away_pts += B2B_BENAR
        games.append({**game, "home_pts": round(home_pts), "away_pts": round(away_pts)})
    return games, ratings


class TestFitSintetis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.games, cls.ratings = buat_data_sintetis()
        cls.hasil = fit_nba_params.fit_parameters(cls.games, cls.ratings)

    def test_jumlah_laga(self):
        self.assertEqual(self.hasil["n_games_used"], 2000)
        self.assertEqual(self.hasil["n_games_skipped_no_rating"], 0)

    def test_sigma_margin_mendekati_benar(self):
        nilai = self.hasil["parameters"]["sigma_margin_points"]["value"]
        self.assertAlmostEqual(nilai, SIGMA_MARGIN_BENAR, delta=0.8)

    def test_sigma_total_mendekati_benar(self):
        nilai = self.hasil["parameters"]["sigma_total_points"]["value"]
        self.assertAlmostEqual(nilai, SIGMA_TOTAL_BENAR, delta=0.8)

    def test_home_advantage_mendekati_benar(self):
        nilai = self.hasil["parameters"]["home_advantage_points"]["value"]
        self.assertAlmostEqual(nilai, HA_BENAR, delta=0.8)

    def test_b2b_mendekati_benar(self):
        param = self.hasil["parameters"]["back_to_back_penalty_points"]
        self.assertAlmostEqual(param["value"], B2B_BENAR, delta=1.0)
        self.assertGreater(param["n_b2b"], 100)

    def test_altitude_mendekati_benar(self):
        param = self.hasil["parameters"]["altitude_adjustment_points"]
        self.assertAlmostEqual(param["value"], ALT_BENAR, delta=3.0)
        self.assertGreater(param["n_alt_home"], 30)

    def test_nu_mendekati_benar(self):
        nilai = self.hasil["parameters"]["t_nu"]["value"]
        self.assertGreaterEqual(nilai, 4.0)
        self.assertLessEqual(nilai, 10.0)


class TestFitDataTidakCukup(unittest.TestCase):
    def test_laga_sedikit_semua_null(self):
        games, ratings = buat_data_sintetis(seed=999, n_laga_per_musim=5)
        hasil = fit_nba_params.fit_parameters(games, ratings)
        for nama, param in hasil["parameters"].items():
            with self.subTest(nama=nama):
                self.assertIsNone(param["value"])
                self.assertIn("reason", param)

    def test_laga_tanpa_rating_dilewati(self):
        games, ratings = buat_data_sintetis(seed=999, n_laga_per_musim=5)
        games.append(
            {
                "season": "2024-25",
                "game_date": "2025-11-01",
                "game_id": "tanpa-rating",
                "home_tricode": "XXX",
                "away_tricode": "YYY",
                "home_pts": 100,
                "away_pts": 99,
            }
        )
        hasil = fit_nba_params.fit_parameters(games, ratings)
        self.assertEqual(hasil["n_games_skipped_no_rating"], 1)


class TestDetectBackToBack(unittest.TestCase):
    def test_b2b_dari_tanggal_berurutan(self):
        games = [
            {
                "game_id": "g1",
                "game_date": "2025-11-01",
                "home_tricode": "ATL",
                "away_tricode": "BOS",
            },
            {
                "game_id": "g2",
                "game_date": "2025-11-02",
                "home_tricode": "ATL",
                "away_tricode": "CHI",
            },
            {
                "game_id": "g3",
                "game_date": "2025-11-05",
                "home_tricode": "BOS",
                "away_tricode": "CHI",
            },
        ]
        b2b = fit_nba_params.detect_back_to_back(games)
        self.assertTrue(b2b["g2:ATL"])  # ATL main lagi sehari setelah g1
        self.assertFalse(b2b["g1:ATL"])
        self.assertFalse(b2b["g2:CHI"])
        self.assertFalse(b2b["g3:BOS"])
        self.assertFalse(b2b["g3:CHI"])


if __name__ == "__main__":
    unittest.main()
