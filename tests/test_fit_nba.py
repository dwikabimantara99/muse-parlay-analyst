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


# --- Rating rolling point-in-time (patch 1b) ---

# Box score mentah dua laga ATL (nilai dihitung tangan di tes):
#   Laga 1 (2025-10-28, ATL kandang vs BOS):
#     ATL: PTS 110, FGA 90, FTA 20, OREB 10, TOV 12, MIN 240
#     BOS: PTS 100, FGA 85, FTA 18, OREB 9, TOV 14, MIN 240
#   Laga 2 (2025-10-30, ATL tandang @ CHI, OT):
#     ATL: PTS 105, FGA 88, FTA 22, OREB 8, TOV 15, MIN 265
#     CHI: PTS 108, FGA 92, FTA 15, OREB 11, TOV 11, MIN 265


def _record_boxscore(
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
    season="2025-26",
):
    """Satu record team-game (bentuk keluaran parse_boxscores_*)."""
    return {
        "season": season,
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


def _boxscore_atl_dua_laga():
    """Record box score 2 laga ATL di atas (poss dihitung dari rumus)."""
    poss_atl_1 = 90 + 0.44 * 20 - 10 + 12  # 100.8
    poss_bos_1 = 85 + 0.44 * 18 - 9 + 14  # 97.92
    poss_atl_2 = 88 + 0.44 * 22 - 8 + 15  # 104.68
    poss_chi_2 = 92 + 0.44 * 15 - 11 + 11  # 98.6
    return [
        _record_boxscore(
            "g-okt28",
            "2025-10-28",
            "ATL",
            "BOS",
            True,
            110,
            poss_atl_1,
            100,
            poss_bos_1,
        ),
        _record_boxscore(
            "g-okt28",
            "2025-10-28",
            "BOS",
            "ATL",
            False,
            100,
            poss_bos_1,
            110,
            poss_atl_1,
        ),
        _record_boxscore(
            "g-okt30",
            "2025-10-30",
            "ATL",
            "CHI",
            False,
            105,
            poss_atl_2,
            108,
            poss_chi_2,
            menit=265.0,
        ),
        _record_boxscore(
            "g-okt30",
            "2025-10-30",
            "CHI",
            "ATL",
            True,
            108,
            poss_chi_2,
            105,
            poss_atl_2,
            menit=265.0,
        ),
    ]


def _prior_sintetis_rolling():
    """Prior 4 tim (rating 'musim sebelumnya')."""
    return {
        "2025-26": {
            "ATL": {"off_rtg": 114.0, "def_rtg": 114.0, "net_rtg": 0.0, "pace": 100.0},
            "DET": {"off_rtg": 112.0, "def_rtg": 113.0, "net_rtg": -1.0, "pace": 99.0},
            "BOS": {"off_rtg": 115.0, "def_rtg": 110.0, "net_rtg": 5.0, "pace": 101.0},
            "CHI": {"off_rtg": 111.0, "def_rtg": 112.0, "net_rtg": -1.0, "pace": 98.0},
        }
    }


def _laga_uji_rolling():
    """Laga uji 2025-11-01 (ATL vs DET) + laga 2025-11-03 (ATL vs BOS)."""
    return [
        {
            "season": "2025-26",
            "game_date": "2025-11-01",
            "game_id": "uji-1101",
            "home_tricode": "ATL",
            "away_tricode": "DET",
            "home_pts": 112,
            "away_pts": 108,
        },
        {
            "season": "2025-26",
            "game_date": "2025-11-03",
            "game_id": "uji-1103",
            "home_tricode": "ATL",
            "away_tricode": "BOS",
            "home_pts": 105,
            "away_pts": 110,
        },
    ]


class TestPossessions(unittest.TestCase):
    def test_rumus_dean_oliver(self):
        # 90 + 0,44*20 - 10 + 12 = 100,8.
        self.assertAlmostEqual(fit_nba_params.hitung_possessions(90, 20, 10, 12), 100.8)

    def test_input_bukan_angka_none(self):
        self.assertIsNone(fit_nba_params.hitung_possessions(90, None, 10, 12))
        self.assertIsNone(fit_nba_params.hitung_possessions(90, 20, 10, True))
        self.assertIsNone(fit_nba_params.hitung_possessions("90", 20, 10, 12))


class TestMusimSebelumnya(unittest.TestCase):
    def test_2024_25_ke_2023_24(self):
        self.assertEqual(fit_nba_params._musim_sebelumnya("2024-25"), "2023-24")
        self.assertEqual(fit_nba_params._musim_sebelumnya("2026-27"), "2025-26")

    def test_format_salah(self):
        with self.assertRaises(ValueError):
            fit_nba_params._musim_sebelumnya("2024")


class TestParseBoxscores(unittest.TestCase):
    def test_satu_laga_normal(self):
        headers = [
            "GAME_ID",
            "GAME_DATE",
            "MATCHUP",
            "TEAM_ABBREVIATION",
            "PTS",
            "FGA",
            "FTA",
            "OREB",
            "TOV",
            "MIN",
        ]
        data = {
            "resultSets": [
                {
                    "name": "LeagueGameFinderResults",
                    "headers": headers,
                    "rowSet": [
                        [
                            "g1",
                            "2025-10-28",
                            "ATL vs. BOS",
                            "ATL",
                            110,
                            90,
                            20,
                            10,
                            12,
                            240,
                        ],
                        [
                            "g1",
                            "2025-10-28",
                            "ATL vs. BOS",
                            "BOS",
                            100,
                            85,
                            18,
                            9,
                            14,
                            240,
                        ],
                    ],
                }
            ]
        }
        records, info = fit_nba_params.parse_boxscores_leaguegamefinder(data, "2025-26")
        self.assertEqual(len(records), 2)
        self.assertEqual(info["n_laga_mentah"], 1)
        self.assertEqual(info["n_laga_tidak_berpasangan"], 0)
        atl = next(r for r in records if r["tricode"] == "ATL")
        self.assertTrue(atl["is_home"])
        self.assertEqual(atl["pts"], 110)
        self.assertAlmostEqual(atl["poss"], 100.8)
        self.assertEqual(atl["pts_lawan"], 100)
        self.assertAlmostEqual(atl["poss_lawan"], 97.92)
        self.assertEqual(atl["minutes"], 240.0)

    def test_anomali_matchup_kedua_baris_sama(self):
        # Laga 0022600189: kedua baris menulis "DEN @ IND" — IND tetap
        # kandang (logika cermin _pair_game_rows).
        headers = [
            "GAME_ID",
            "GAME_DATE",
            "MATCHUP",
            "TEAM_ABBREVIATION",
            "PTS",
            "FGA",
            "FTA",
            "OREB",
            "TOV",
            "MIN",
        ]
        data = {
            "resultSets": [
                {
                    "name": "LeagueGameFinderResults",
                    "headers": headers,
                    "rowSet": [
                        [
                            "g2",
                            "2025-10-28",
                            "DEN @ IND",
                            "DEN",
                            100,
                            85,
                            18,
                            9,
                            14,
                            240,
                        ],
                        [
                            "g2",
                            "2025-10-28",
                            "DEN @ IND",
                            "IND",
                            110,
                            90,
                            20,
                            10,
                            12,
                            240,
                        ],
                    ],
                }
            ]
        }
        records, _info = fit_nba_params.parse_boxscores_leaguegamefinder(
            data, "2025-26"
        )
        self.assertEqual(len(records), 2)
        ind = next(r for r in records if r["tricode"] == "IND")
        self.assertTrue(ind["is_home"])

    def test_resultset_hilang(self):
        with self.assertRaises(ValueError):
            fit_nba_params.parse_boxscores_leaguegamefinder(
                {"resultSets": []}, "2025-26"
            )


class TestRatingRolling(unittest.TestCase):
    def test_nilai_hitung_tangan_atl_dua_laga(self):
        """Rating ATL setelah 2 laga = hitungan tangan dari box score."""
        per_laga, info = fit_nba_params.bangun_rating_rolling(
            _laga_uji_rolling(),
            _boxscore_atl_dua_laga(),
            _prior_sintetis_rolling(),
        )
        self.assertEqual(info["n_laga_dengan_rating"], 2)
        atl = per_laga["uji-1101"]["home"]
        self.assertEqual(atl["n_musim"], 2)
        self.assertEqual(atl["n_last10"], 2)
        # Nilai harapan — dihitung langsung dari angka box score mentah
        # (bukan lewat fungsi modul).
        poss_atl_1 = 90 + 0.44 * 20 - 10 + 12
        poss_bos_1 = 85 + 0.44 * 18 - 9 + 14
        poss_atl_2 = 88 + 0.44 * 22 - 8 + 15
        poss_chi_2 = 92 + 0.44 * 15 - 11 + 11
        off_obs = 100 * (110 + 105) / (poss_atl_1 + poss_atl_2)
        def_obs = 100 * (100 + 108) / (poss_bos_1 + poss_chi_2)
        pace_obs = 240 * (poss_atl_1 + poss_atl_2) / (240 + 265)
        k, n = 10, 2
        off_musim = (n * off_obs + k * 114.0) / (n + k)
        def_musim = (n * def_obs + k * 114.0) / (n + k)
        pace_musim = (n * pace_obs + k * 100.0) / (n + k)
        off_last10 = (n * off_obs + k * off_musim) / (n + k)
        def_last10 = (n * def_obs + k * def_musim) / (n + k)
        pace_last10 = (n * pace_obs + k * pace_musim) / (n + k)
        for field, harapan in (
            ("off_rtg", off_musim),
            ("def_rtg", def_musim),
            ("pace", pace_musim),
        ):
            with self.subTest(field=field, jendela="musim"):
                self.assertAlmostEqual(atl["stats_season"][field], harapan, places=9)
        for field, harapan in (
            ("off_rtg", off_last10),
            ("def_rtg", def_last10),
            ("pace", pace_last10),
        ):
            with self.subTest(field=field, jendela="last10"):
                self.assertAlmostEqual(atl["stats_last10"][field], harapan, places=9)
        efektif = per_laga["uji-1101"]["home_efektif"]
        self.assertAlmostEqual(
            efektif["off_rtg"], 0.6 * off_musim + 0.4 * off_last10, places=9
        )
        self.assertAlmostEqual(
            efektif["def_rtg"], 0.6 * def_musim + 0.4 * def_last10, places=9
        )
        self.assertAlmostEqual(
            efektif["pace"], 0.6 * pace_musim + 0.4 * pace_last10, places=9
        )
        self.assertAlmostEqual(
            efektif["net_rtg"],
            efektif["off_rtg"] - efektif["def_rtg"],
            places=9,
        )

    def test_tanpa_laga_sebelumnya_rating_sama_dengan_prior(self):
        """n=0 -> rating = prior persis (DET belum main sebelum 1 Nov)."""
        per_laga, _info = fit_nba_params.bangun_rating_rolling(
            _laga_uji_rolling(),
            _boxscore_atl_dua_laga(),
            _prior_sintetis_rolling(),
        )
        det = per_laga["uji-1101"]["away"]
        self.assertEqual(det["n_musim"], 0)
        self.assertEqual(det["n_last10"], 0)
        self.assertEqual(det["stats_season"]["off_rtg"], 112.0)
        self.assertEqual(det["stats_season"]["def_rtg"], 113.0)
        self.assertEqual(det["stats_season"]["pace"], 99.0)
        self.assertEqual(det["stats_last10"]["off_rtg"], 112.0)
        efektif = per_laga["uji-1101"]["away_efektif"]
        self.assertEqual(efektif["off_rtg"], 112.0)
        self.assertEqual(efektif["net_rtg"], -1.0)

    def test_point_in_time_laga_setelah_tanggal_tidak_memengaruhi(self):
        """Box score 2 Nov (setelah laga uji 1 Nov) tidak boleh mengubah
        rating laga 1 Nov — tapi BOLEH mengubah rating laga 3 Nov."""
        dasar = _boxscore_atl_dua_laga()
        per_laga_sebelum, _ = fit_nba_params.bangun_rating_rolling(
            _laga_uji_rolling(), dasar, _prior_sintetis_rolling()
        )
        # ATL main lagi 2 Nov (kandang vs DET): 130 poin, poss besar.
        tambahan = [
            _record_boxscore(
                "g-nov02", "2025-11-02", "ATL", "DET", True, 130, 110.0, 90, 95.0
            ),
            _record_boxscore(
                "g-nov02", "2025-11-02", "DET", "ATL", False, 90, 95.0, 130, 110.0
            ),
        ]
        per_laga_sesudah, _ = fit_nba_params.bangun_rating_rolling(
            _laga_uji_rolling(), dasar + tambahan, _prior_sintetis_rolling()
        )
        self.assertEqual(per_laga_sesudah["uji-1101"], per_laga_sebelum["uji-1101"])
        # Laga 3 Nov HARUS berubah (laga 2 Nov masuk jendelanya).
        self.assertNotEqual(
            per_laga_sesudah["uji-1103"]["home_efektif"]["off_rtg"],
            per_laga_sebelum["uji-1103"]["home_efektif"]["off_rtg"],
        )
        self.assertEqual(per_laga_sesudah["uji-1103"]["home"]["n_musim"], 3)

    def test_boxscore_tanggal_yang_sama_tidak_memengaruhi(self):
        """Box score tanggal 1 Nov sendiri tidak masuk rating laga 1 Nov."""
        dasar = _boxscore_atl_dua_laga()
        per_laga_sebelum, _ = fit_nba_params.bangun_rating_rolling(
            _laga_uji_rolling(), dasar, _prior_sintetis_rolling()
        )
        tambahan = [
            _record_boxscore(
                "uji-1101", "2025-11-01", "ATL", "DET", True, 112, 100.0, 108, 99.0
            ),
            _record_boxscore(
                "uji-1101", "2025-11-01", "DET", "ATL", False, 108, 99.0, 112, 100.0
            ),
        ]
        per_laga_sesudah, _ = fit_nba_params.bangun_rating_rolling(
            _laga_uji_rolling(), dasar + tambahan, _prior_sintetis_rolling()
        )
        self.assertEqual(per_laga_sesudah["uji-1101"], per_laga_sebelum["uji-1101"])

    def test_deterministik(self):
        args = (
            _laga_uji_rolling(),
            _boxscore_atl_dua_laga(),
            _prior_sintetis_rolling(),
        )
        hasil1, info1 = fit_nba_params.bangun_rating_rolling(*args)
        hasil2, info2 = fit_nba_params.bangun_rating_rolling(*args)
        self.assertEqual(hasil1, hasil2)
        self.assertEqual(info1, info2)

    def test_lg_avg_point_in_time(self):
        """lg_avg = rata-rata off_rtg efektif ke-4 tim pada tanggal itu."""
        per_laga, _ = fit_nba_params.bangun_rating_rolling(
            _laga_uji_rolling(),
            _boxscore_atl_dua_laga(),
            _prior_sintetis_rolling(),
        )
        # BOS (1 laga vs ATL 28 Okt) dan CHI (1 laga vs ATL 30 Okt)
        # dihitung tangan dari box score mentah; DET = prior (n=0).
        poss_bos_1 = 85 + 0.44 * 18 - 9 + 14
        off_bos_obs = 100 * 100 / poss_bos_1
        off_bos_musim = (1 * off_bos_obs + 10 * 115.0) / 11
        off_bos_last10 = (1 * off_bos_obs + 10 * off_bos_musim) / 11
        off_bos_ef = 0.6 * off_bos_musim + 0.4 * off_bos_last10
        poss_chi_2 = 92 + 0.44 * 15 - 11 + 11
        off_chi_obs = 100 * 108 / poss_chi_2
        off_chi_musim = (1 * off_chi_obs + 10 * 111.0) / 11
        off_chi_last10 = (1 * off_chi_obs + 10 * off_chi_musim) / 11
        off_chi_ef = 0.6 * off_chi_musim + 0.4 * off_chi_last10
        off_atl_ef = per_laga["uji-1101"]["home_efektif"]["off_rtg"]
        harapan = (off_atl_ef + 112.0 + off_bos_ef + off_chi_ef) / 4.0
        self.assertAlmostEqual(
            per_laga["uji-1101"]["lg_avg_off_rtg"], harapan, places=9
        )

    def test_tim_tanpa_prior_laga_dilewati(self):
        games = [
            {
                "season": "2025-26",
                "game_date": "2025-11-01",
                "game_id": "tanpa-prior",
                "home_tricode": "XXX",
                "away_tricode": "ATL",
                "home_pts": 100,
                "away_pts": 99,
            }
        ]
        per_laga, info = fit_nba_params.bangun_rating_rolling(
            games, _boxscore_atl_dua_laga(), _prior_sintetis_rolling()
        )
        self.assertEqual(per_laga, {})
        self.assertEqual(info["n_laga_tanpa_prior"], 1)


class TestFitDenganRolling(unittest.TestCase):
    def test_fit_rolling_jalan_dan_memakai_rating_rolling(self):
        """fit_parameters(rolling=...) memakai rating rolling: mengubah
        box score harus mengubah hasil fit (bukan memakai rating penuh)."""
        games, ratings = buat_data_sintetis(seed=77, n_laga_per_musim=60)
        priors = {
            musim: {tri: dict(rating) for tri, rating in per_tim.items()}
            for musim, per_tim in ratings.items()
        }

        def _boxscore_dari_laga(laga):
            # Box score sintetis yang konsisten dengan skor laga: poss
            # ~99,8 dari FGA 88 / FTA 20 / OREB 10 / TOV 13.
            poss = 88 + 0.44 * 20 - 10 + 13
            return [
                _record_boxscore(
                    laga["game_id"],
                    laga["game_date"],
                    laga["home_tricode"],
                    laga["away_tricode"],
                    True,
                    laga["home_pts"],
                    poss,
                    laga["away_pts"],
                    poss,
                    season=laga["season"],
                ),
                _record_boxscore(
                    laga["game_id"],
                    laga["game_date"],
                    laga["away_tricode"],
                    laga["home_tricode"],
                    False,
                    laga["away_pts"],
                    poss,
                    laga["home_pts"],
                    poss,
                    season=laga["season"],
                ),
            ]

        boxscores = []
        for laga in games:
            boxscores.extend(_boxscore_dari_laga(laga))
        rolling, _info = fit_nba_params.bangun_rating_rolling(games, boxscores, priors)
        hasil = fit_nba_params.fit_parameters(
            games, {}, min_games_total=5, min_group_n=1, rolling=rolling
        )
        self.assertEqual(hasil["ratings_mode"], "rolling")
        self.assertEqual(hasil["n_games_used"], 120)
        self.assertEqual(hasil["n_games_skipped_no_rolling"], 0)
        self.assertIsNotNone(hasil["parameters"]["sigma_margin_points"]["value"])
        self.assertIsNotNone(hasil["parameters"]["sigma_total_points"]["value"])
        self.assertIsNotNone(hasil["parameters"]["home_advantage_points"]["value"])
        # Mengubah box score (ATL mencetak 40 poin lebih banyak di semua
        # laganya) harus menggeser sigma — bukti rating rolling dipakai.
        boxscores_ubah = []
        for rec in boxscores:
            rec_baru = dict(rec)
            if rec_baru["tricode"] == "ATL":
                rec_baru["pts"] = rec_baru["pts"] + 40
            if rec_baru["opp_tricode"] == "ATL":
                rec_baru["pts_lawan"] = rec_baru["pts_lawan"] + 40
            boxscores_ubah.append(rec_baru)
        rolling_ubah, _ = fit_nba_params.bangun_rating_rolling(
            games, boxscores_ubah, priors
        )
        hasil_ubah = fit_nba_params.fit_parameters(
            games, {}, min_games_total=5, min_group_n=1, rolling=rolling_ubah
        )
        self.assertNotEqual(
            hasil_ubah["parameters"]["sigma_total_points"]["value"],
            hasil["parameters"]["sigma_total_points"]["value"],
        )


if __name__ == "__main__":
    unittest.main()
