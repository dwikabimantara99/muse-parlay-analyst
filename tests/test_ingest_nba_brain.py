"""Tes ingest/nba_brain.py — TANPA network (fetcher di-patch).

Skenario utama: laga DAL @ UTA, 2026-11-22 (UTA kandang — menguji
bendera altitude). Fixture inline berbentuk data TERPARSE dari tiap
fetcher (bentuk persis yang dikembalikan fetcher aslinya); parsing
respons mentah dites di test_ingest_stats_nba.py / test_ingest_bbref.py.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import nba_brain
from ingest.common import FetchResult

GAME_DATE = "2026-11-22"
SEASON = "2026-27"
FETCHED_AT = "2026-11-22T00:00:00+00:00"

TEAM_NAMES = {
    "UTA": "Utah Jazz",
    "DAL": "Dallas Mavericks",
    "MEM": "Memphis Grizzlies",
    "DEN": "Denver Nuggets",
    "PHX": "Phoenix Suns",
    "SAC": "Sacramento Kings",
    "GSW": "Golden State Warriors",
    "OKC": "Oklahoma City Thunder",
    "HOU": "Houston Rockets",
    "MIN": "Minnesota Timberwolves",
    "SAS": "San Antonio Spurs",
    "LAC": "LA Clippers",
    "POR": "Portland Trail Blazers",
    "BOS": "Boston Celtics",
    "NYK": "New York Knicks",
}


def _game(game_id, game_date, home_tri, away_tri, home_pts, away_pts):
    """Satu laga bentuk parse_league_games."""
    return {
        "game_id": game_id,
        "game_date": game_date,
        "home_tricode": home_tri,
        "away_tricode": away_tri,
        "home_team": TEAM_NAMES[home_tri],
        "away_team": TEAM_NAMES[away_tri],
        "home_pts": home_pts,
        "away_pts": away_pts,
        "status": "Final",
    }


# Laga musim (sebelum 2026-11-22) + 2 laga yang harus DIABAIKAN
# (tanggal >= game_date) + 1 laga tim lain (noise).
GAMES = [
    _game("g01", "2026-11-21", "UTA", "MEM", 118, 110),  # UTA kemarin -> B2B
    _game("g02", "2026-11-19", "UTA", "DEN", 105, 112),
    _game("g03", "2026-11-17", "PHX", "UTA", 120, 115),
    _game("g04", "2026-11-15", "UTA", "SAC", 121, 119),
    _game("g05", "2026-11-13", "GSW", "UTA", 100, 108),
    _game("g06", "2026-11-11", "UTA", "OKC", 99, 110),  # ke-6, di luar form5
    _game("d01", "2026-11-20", "DAL", "HOU", 112, 108),
    _game("d02", "2026-11-18", "MIN", "DAL", 104, 98),
    _game("d03", "2026-11-16", "DAL", "SAS", 115, 110),
    _game("d04", "2026-11-14", "LAC", "DAL", 117, 121),
    _game("d05", "2026-11-12", "DAL", "POR", 109, 111),
    _game("h01", "2026-10-25", "UTA", "DAL", 110, 105),  # H2H musim ini
    _game("x01", "2026-11-22", "BOS", "UTA", 100, 99),  # hari-H: abaikan
    _game("x02", "2026-11-24", "UTA", "NYK", 100, 99),  # masa depan: abaikan
    _game("n01", "2026-11-21", "BOS", "NYK", 120, 115),  # tim lain
]

ADV_SEASON = [
    {
        "team": "Utah Jazz",
        "tricode": "UTA",
        "off_rtg": 112.0,
        "def_rtg": 113.5,
        "net_rtg": -1.5,
        "pace": 100.0,
    },
    {
        "team": "Dallas Mavericks",
        "tricode": "DAL",
        "off_rtg": 114.5,
        "def_rtg": 111.0,
        "net_rtg": 3.5,
        "pace": 99.0,
    },
    {
        "team": "Oklahoma City Thunder",
        "tricode": "OKC",
        "off_rtg": 113.7,
        "def_rtg": 109.4,
        "net_rtg": 4.3,
        "pace": 99.28,
    },
]

ADV_LAST10 = [
    {
        "team": "Utah Jazz",
        "tricode": "UTA",
        "off_rtg": 110.0,
        "def_rtg": 112.0,
        "net_rtg": -2.0,
        "pace": 99.5,
    },
    {
        "team": "Dallas Mavericks",
        "tricode": "DAL",
        "off_rtg": 115.0,
        "def_rtg": 110.0,
        "net_rtg": 5.0,
        "pace": 98.5,
    },
]

# Fallback BBRef (nama tim lengkap, tanpa tricode).
BBREF_TEAMS = [
    {
        "team": "Utah Jazz",
        "off_rtg": 112.2,
        "def_rtg": 113.6,
        "net_rtg": -1.4,
        "pace": 100.1,
    },
    {
        "team": "Dallas Mavericks",
        "off_rtg": 114.4,
        "def_rtg": 111.1,
        "net_rtg": 3.3,
        "pace": 99.2,
    },
]

# 9 pemain UTA (uji potong top-8 + urutan mp_per_game + mpg None di akhir),
# 3 pemain DAL, 1 pemain tim lain.
PLAYERS = [
    {
        "player": "Lauri Markkanen",
        "team": "UTA",
        "mp": 520,
        "mp_per_game": 32.5,
        "bpm": 2.1,
    },
    {
        "player": "Keyonte George",
        "team": "UTA",
        "mp": 480,
        "mp_per_game": 30.1,
        "bpm": 0.5,
    },
    {
        "player": "Walker Kessler",
        "team": "UTA",
        "mp": 450,
        "mp_per_game": 28.0,
        "bpm": 1.8,
        "bbref_slug": "k/kesslwa01",
    },
    {
        "player": "Brice Sensabaugh",
        "team": "UTA",
        "mp": 400,
        "mp_per_game": 25.0,
        "bpm": -0.5,
    },
    {
        "player": "Kyle Filipowski",
        "team": "UTA",
        "mp": 380,
        "mp_per_game": 24.0,
        "bpm": 0.2,
    },
    {
        "player": "Isaiah Collier",
        "team": "UTA",
        "mp": 350,
        "mp_per_game": 22.0,
        "bpm": -1.0,
    },
    {
        "player": "Svi Mykhailiuk",
        "team": "UTA",
        "mp": 300,
        "mp_per_game": 18.5,
        "bpm": -0.8,
    },
    {
        "player": "Taylor Hendricks",
        "team": "UTA",
        "mp": 280,
        "mp_per_game": 17.5,
        "bpm": 0.9,
    },
    {
        "player": "Pemain Cadangan",
        "team": "UTA",
        "mp": 50,
        "mp_per_game": 5.0,
        "bpm": -2.0,
    },
    {
        "player": "Pemain Tanpa Menit",
        "team": "UTA",
        "mp": 0,
        "mp_per_game": None,
        "bpm": None,
    },
    {
        "player": "Luka Doncic",
        "team": "DAL",
        "mp": 560,
        "mp_per_game": 35.0,
        "bpm": 8.5,
    },
    {
        "player": "Kyrie Irving",
        "team": "DAL",
        "mp": 500,
        "mp_per_game": 31.0,
        "bpm": 3.2,
    },
    {
        "player": "Anthony Davis",
        "team": "DAL",
        "mp": 480,
        "mp_per_game": 30.0,
        "bpm": 4.1,
    },
    {
        "player": "Shai Gilgeous-Alexander",
        "team": "OKC",
        "mp": 600,
        "mp_per_game": 34.0,
        "bpm": 9.0,
    },
]

PDF_INJURIES = [
    {
        "player": "Walker Kessler",
        "team": "Utah Jazz",
        "status": "Out",
        "detail": "Left knee",
    },
    {
        "player": "Kyrie Irving",
        "team": "Dallas Mavericks",
        "status": "Questionable",
        "detail": "Ankle",
    },
    {
        "player": "Jayson Tatum",
        "team": "Boston Celtics",
        "status": "Out",
        "detail": "Achilles",
    },
]

# Bentuk TERPARSE fetcher ESPN (ingest/espn.py): status mentah +
# status_normalized + flag konflik/is_injury + source/tier/time.
ESPN_INJURIES = [
    {
        "player": "Walker Kessler",
        "team": "Utah Jazz",
        "status": "Out",
        "detail": "Kessler (knee) won't play.",
        "status_normalized": "OUT",
        "status_comment_conflict": False,
        "is_injury": True,
        "source": "ESPN",
        "tier": 2,
        "time": FETCHED_AT,
    },
    {
        "player": "Kyrie Irving",
        "team": "Dallas Mavericks",
        "status": "Probable",
        "detail": "Irving (ankle) is probable.",
        "status_normalized": "PROBABLE",
        "status_comment_conflict": False,
        "is_injury": True,
        "source": "ESPN",
        "tier": 2,
        "time": FETCHED_AT,
    },
    {
        "player": "Anthony Davis",
        "team": "Dallas Mavericks",
        "status": "Day-To-Day",
        "detail": "Davis (back) is day-to-day.",
        "status_normalized": "QUESTIONABLE",
        "status_asli": "Day-To-Day",
        "status_comment_conflict": False,
        "is_injury": True,
        "source": "ESPN",
        "tier": 2,
        "time": FETCHED_AT,
    },
    {
        "player": "LeBron James",
        "team": "Los Angeles Lakers",
        "status": "Out",
        "detail": "James (back) is out.",
        "status_normalized": "OUT",
        "status_comment_conflict": False,
        "is_injury": True,
        "source": "ESPN",
        "tier": 2,
        "time": FETCHED_AT,
    },
]


def _ok(source, tier, data):
    return FetchResult(source, tier, FETCHED_AT, True, data=data)


def _fail(source, tier, error):
    return FetchResult(source, tier, FETCHED_AT, False, error=error)


def _adv_side_effect(season, last_n_games=None, client=None):
    """fetch_team_advanced_stats: musim penuh vs 10 laga terakhir."""
    if last_n_games is None:
        return _ok("stats.nba.com", 1, ADV_SEASON)
    return _ok("stats.nba.com", 1, ADV_LAST10)


def _partisipasi_side_effect(targets, season=None, client=None):
    """Game log palsu untuk _PatchSemua: Kessler absen 7/10, lain 0/10."""
    hasil = {}
    for t in targets or []:
        nama = t.get("player")
        hasil[nama] = {
            "missed_last10": 7 if nama == "Walker Kessler" else 0,
            "games_considered": 10,
        }
    return hasil


class _PatchSemua:
    """Context manager: patch semua fetcher yang dipakai nba_brain."""

    def __init__(self, **overrides):
        self.overrides = overrides
        self.patchers = []
        self.mocks = {}

    def __enter__(self):
        defaults = {
            "fetch_league_games": _ok("stats.nba.com", 1, GAMES),
            "fetch_player_advanced": _ok("Basketball-Reference", 2, PLAYERS),
            "fetch_report": _ok("Official NBA Injury Report", 1, PDF_INJURIES),
            "fetch_injuries_nba": _ok("ESPN", 2, ESPN_INJURIES),
            "fetch_missed_last10_many": _partisipasi_side_effect,
            "fetch_team_advanced": _fail(
                "Basketball-Reference", 2, "tidak boleh dipanggil di jalur normal"
            ),
        }
        for name, value in defaults.items():
            value = self.overrides.get(name, value)
            if callable(value) and not isinstance(value, FetchResult):
                patcher = patch(f"ingest.nba_brain.{name}", side_effect=value)
            else:
                patcher = patch(f"ingest.nba_brain.{name}", return_value=value)
            self.mocks[name] = patcher.start()
            self.patchers.append(patcher)
        # fetch_team_advanced_stats: dispatch musim vs last10.
        adv = self.overrides.get("fetch_team_advanced_stats", _adv_side_effect)
        if callable(adv) and not isinstance(adv, FetchResult):
            patcher = patch(
                "ingest.nba_brain.fetch_team_advanced_stats", side_effect=adv
            )
        else:
            patcher = patch(
                "ingest.nba_brain.fetch_team_advanced_stats", return_value=adv
            )
        self.mocks["fetch_team_advanced_stats"] = patcher.start()
        self.patchers.append(patcher)
        return self

    def __exit__(self, *exc):
        for patcher in reversed(self.patchers):
            patcher.stop()
        return False


class TestFetchMatchInputsLengkap(unittest.TestCase):
    def test_kontrak_lengkap(self):
        with _PatchSemua():
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        self.assertTrue(result.ok)
        self.assertIsNone(result.error)
        self.assertEqual(result.extra, {})
        data = result.data
        self.assertEqual(
            data["match"],
            {
                "home_tricode": "UTA",
                "away_tricode": "DAL",
                "game_date": GAME_DATE,
                "season": SEASON,
            },
        )
        # Hanya konflik Irving + bendera turnamen yang missing.
        self.assertEqual(
            set(data["missing"]),
            {
                "injuries_konflik:Kyrie Irving",
                "tournament_flag_tidak_dapat_ditentukan",
            },
        )
        self.assertIsNone(data["tournament"])
        self.assertEqual(data["fetched_at"], result.fetched_at)
        # 6 sumber tercatat (urutan fetch).
        self.assertEqual(
            [(s["data_kind"], s["source"], s["tier"]) for s in data["sources"]],
            [
                ("nba_games_season", "stats.nba.com", 1),
                ("nba_team_advanced_season", "stats.nba.com", 1),
                ("nba_team_advanced_last10", "stats.nba.com", 1),
                ("nba_player_impact", "Basketball-Reference", 2),
                ("nba_injuries", "Official NBA Injury Report", 1),
                ("nba_injuries", "ESPN", 2),
            ],
        )
        # Rata-rata liga dari 3 tim fixture.
        self.assertAlmostEqual(data["league"]["avg_pace"], (100.0 + 99.0 + 99.28) / 3)
        self.assertAlmostEqual(
            data["league"]["avg_off_rtg"], (112.0 + 114.5 + 113.7) / 3
        )
        # H2H: 1 pertemuan musim ini.
        self.assertEqual(len(data["h2h_last5"]), 1)
        self.assertEqual(data["h2h_last5"][0]["game_id"], "h01")
        self.assertEqual(data["h2h_last5"][0]["home_pts"], 110)
        self.assertEqual(data["h2h_last5"][0]["away_pts"], 105)

    def test_blok_tim_kandang_uta(self):
        with _PatchSemua():
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        home = result.data["home"]
        self.assertEqual(home["tricode"], "UTA")
        self.assertEqual(home["team"], "Utah Jazz")
        self.assertTrue(home["altitude_home"])
        self.assertEqual(
            home["stats_season"],
            {"off_rtg": 112.0, "def_rtg": 113.5, "net_rtg": -1.5, "pace": 100.0},
        )
        self.assertEqual(
            home["stats_last10"],
            {"off_rtg": 110.0, "def_rtg": 112.0, "net_rtg": -2.0, "pace": 99.5},
        )
        # form5 terbaru dulu; g06 (ke-6) dan laga tanggal >= game_date di luar.
        self.assertEqual(
            [f["game_date"] for f in home["form5"]],
            ["2026-11-21", "2026-11-19", "2026-11-17", "2026-11-15", "2026-11-13"],
        )
        first = home["form5"][0]
        self.assertEqual(first["opponent_tricode"], "MEM")
        self.assertTrue(first["home"])
        self.assertEqual(first["wl"], "W")
        self.assertEqual(first["pts"], 118)
        self.assertEqual(first["opp_pts"], 110)
        third = home["form5"][2]
        self.assertEqual(third["opponent_tricode"], "PHX")
        self.assertFalse(third["home"])
        self.assertEqual(third["wl"], "L")
        # Rekor kandang: 5 laga (g01 W, g02 L, g04 W, g06 L, h01 W).
        self.assertEqual(home["home_record"]["w"], 3)
        self.assertEqual(home["home_record"]["l"], 2)
        self.assertAlmostEqual(home["home_record"]["ppg"], 553 / 5)
        self.assertAlmostEqual(home["home_record"]["opp_ppg"], 556 / 5)
        # Rekor tandang: 2 laga (g03 L, g05 W).
        self.assertEqual(home["road_record"]["w"], 1)
        self.assertEqual(home["road_record"]["l"], 1)
        self.assertAlmostEqual(home["road_record"]["ppg"], 111.5)
        self.assertAlmostEqual(home["road_record"]["opp_ppg"], 110.0)
        # Main kemarin -> rest 0, back-to-back.
        self.assertEqual(home["rest_days"], 0)
        self.assertTrue(home["back_to_back"])
        # Pemain: top 8 urut mp_per_game desc; pemain ke-9 + tanpa menit terpotong.
        self.assertEqual(len(home["players"]), 8)
        self.assertEqual(home["players"][0]["player"], "Lauri Markkanen")
        self.assertEqual(home["players"][0]["bpm"], 2.1)
        self.assertEqual(home["players"][0]["mp_per_game"], 32.5)
        self.assertEqual(home["players"][0]["team_tricode"], "UTA")
        self.assertEqual(home["players"][-1]["player"], "Taylor Hendricks")
        self.assertEqual(
            [p["mp_per_game"] for p in home["players"]],
            sorted([p["mp_per_game"] for p in home["players"]], reverse=True),
        )
        # Cedera UTA: hanya Kessler (Tatum tim lain tersaring).
        self.assertEqual(len(home["injuries"]), 1)
        kessler = home["injuries"][0]
        self.assertEqual(kessler["player"], "Walker Kessler")
        self.assertEqual(kessler["status"], "OUT")
        self.assertEqual(kessler["team_tricode"], "UTA")
        self.assertEqual(kessler["sources"], ["Official NBA Injury Report", "ESPN"])
        self.assertNotIn("conflict", kessler)
        # Partisipasi game log tersambung (patch 1b): Kessler OUT
        # mendapat missed_last10 dari side effect _PatchSemua.
        kessler_pemain = next(
            p for p in home["players"] if p["player"] == "Walker Kessler"
        )
        self.assertEqual(kessler_pemain["missed_last10"], 7)

    def test_blok_tim_tandang_dal(self):
        with _PatchSemua():
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        away = result.data["away"]
        self.assertEqual(away["tricode"], "DAL")
        self.assertEqual(away["team"], "Dallas Mavericks")
        self.assertFalse(away["altitude_home"])
        self.assertEqual(
            away["stats_season"],
            {"off_rtg": 114.5, "def_rtg": 111.0, "net_rtg": 3.5, "pace": 99.0},
        )
        self.assertEqual(
            away["stats_last10"],
            {"off_rtg": 115.0, "def_rtg": 110.0, "net_rtg": 5.0, "pace": 98.5},
        )
        self.assertEqual(len(away["form5"]), 5)
        self.assertEqual(away["form5"][0]["game_date"], "2026-11-20")
        # Rekor kandang DAL: d01 W, d03 W, d05 L.
        self.assertEqual(away["home_record"]["w"], 2)
        self.assertEqual(away["home_record"]["l"], 1)
        self.assertAlmostEqual(away["home_record"]["ppg"], 336 / 3)
        # Rekor tandang DAL: d02 L, d04 W, h01 L.
        self.assertEqual(away["road_record"]["w"], 1)
        self.assertEqual(away["road_record"]["l"], 2)
        self.assertAlmostEqual(away["road_record"]["ppg"], 108.0)
        # Laga terakhir 2026-11-20 -> 1 hari istirahat, bukan B2B.
        self.assertEqual(away["rest_days"], 1)
        self.assertFalse(away["back_to_back"])
        # Pemain DAL: 3 pemain, urut mp_per_game desc.
        self.assertEqual(len(away["players"]), 3)
        self.assertEqual(away["players"][0]["player"], "Luka Doncic")
        # Cedera DAL: Irving (konflik) + Davis (Day-To-Day).
        self.assertEqual(len(away["injuries"]), 2)
        irving = [i for i in away["injuries"] if i["player"] == "Kyrie Irving"][0]
        # Konflik: tier 1 (Questionable) menang, konflik dicatat.
        self.assertEqual(irving["status"], "QUESTIONABLE")
        self.assertEqual(
            irving["conflict"],
            {"Official NBA Injury Report": "QUESTIONABLE", "ESPN": "PROBABLE"},
        )
        self.assertEqual(irving["sources"], ["Official NBA Injury Report", "ESPN"])
        davis = [i for i in away["injuries"] if i["player"] == "Anthony Davis"][0]
        self.assertEqual(davis["status"], "QUESTIONABLE")
        self.assertEqual(davis["status_asli"], "Day-To-Day")
        self.assertEqual(davis["sources"], ["ESPN"])

    def test_fallback_bbref_tidak_dipanggil_bila_stats_ok(self):
        with _PatchSemua() as patched:
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        self.assertTrue(result.ok)
        # fetch_team_advanced (fallback) tidak boleh dipanggil sama sekali.
        patched.mocks["fetch_team_advanced"].assert_not_called()
        # fetch_team_advanced_stats dipanggil 2x: musim + last10.
        self.assertEqual(patched.mocks["fetch_team_advanced_stats"].call_count, 2)

    def test_pemain_cedera_di_luar_top8_tetap_masuk(self):
        """Pemain cedera di luar 8 besar tetap ada di daftar pemain agar
        model bisa menghitung dampak absennya (perbaikan koordinator:
        pada contoh DET@ATL 2026-11-22, 7 dari 10 pemain OUT semula
        dihitung 0 karena di luar 8 besar)."""
        pdf = PDF_INJURIES + [
            {
                "player": "Pemain Cadangan",
                "team": "Utah Jazz",
                "status": "Out",
                "detail": "Knee",
            }
        ]
        with _PatchSemua(fetch_report=_ok("Official NBA Injury Report", 1, pdf)):
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        self.assertTrue(result.ok)
        names = [p["player"] for p in result.data["home"]["players"]]
        self.assertIn("Pemain Cadangan", names)
        # 8 besar tetap ada + 1 cedera di luar top-8 = 9 pemain.
        self.assertEqual(len(names), 9)
        cadangan = next(
            p
            for p in result.data["home"]["players"]
            if p["player"] == "Pemain Cadangan"
        )
        self.assertEqual(cadangan["bpm"], -2.0)
        self.assertEqual(cadangan["mp_per_game"], 5.0)
        # Pemain tanpa menit & tanpa cedera tetap tidak masuk.
        self.assertNotIn("Pemain Tanpa Menit", names)


class TestFetchMatchInputsGagalSebagian(unittest.TestCase):
    def test_fallback_bbref_bila_stats_musim_gagal(self):
        def adv_gagal_musim(season, last_n_games=None, client=None):
            if last_n_games is None:
                return _fail("stats.nba.com", 1, "http_500: leaguedashteamstats gagal")
            return _ok("stats.nba.com", 1, ADV_LAST10)

        with _PatchSemua(
            fetch_team_advanced_stats=adv_gagal_musim,
            fetch_team_advanced=_ok("Basketball-Reference", 2, BBREF_TEAMS),
        ):
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        self.assertTrue(result.ok)
        # Statistik musim dari BBRef (tier 2).
        self.assertEqual(
            result.data["home"]["stats_season"],
            {"off_rtg": 112.2, "def_rtg": 113.6, "net_rtg": -1.4, "pace": 100.1},
        )
        self.assertEqual(result.data["home"]["team"], "Utah Jazz")
        # Last10 tetap dari stats.nba.com.
        self.assertEqual(result.data["home"]["stats_last10"]["off_rtg"], 110.0)
        kinds = [
            (s["data_kind"], s["source"], s["tier"]) for s in result.data["sources"]
        ]
        self.assertIn(("nba_team_advanced_season", "Basketball-Reference", 2), kinds)
        self.assertEqual(
            result.extra["fetch_errors"]["team_advanced_season"],
            "http_500: leaguedashteamstats gagal",
        )
        # Rata-rata liga dari BBRef (2 tim).
        self.assertAlmostEqual(result.data["league"]["avg_pace"], (100.1 + 99.2) / 2)

    def test_statistik_gagal_total_nama_dari_laga(self):
        def adv_selalu_gagal(season, last_n_games=None, client=None):
            return _fail("stats.nba.com", 1, "http_500: gagal")

        with _PatchSemua(
            fetch_team_advanced_stats=adv_selalu_gagal,
            fetch_team_advanced=_fail("Basketball-Reference", 2, "http_403: gagal"),
        ):
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        self.assertTrue(result.ok)
        home = result.data["home"]
        self.assertEqual(
            home["stats_season"],
            {"off_rtg": None, "def_rtg": None, "net_rtg": None, "pace": None},
        )
        self.assertEqual(
            home["stats_last10"],
            {"off_rtg": None, "def_rtg": None, "net_rtg": None, "pace": None},
        )
        # Nama tim masih didapat dari daftar laga.
        self.assertEqual(home["team"], "Utah Jazz")
        self.assertEqual(result.data["away"]["team"], "Dallas Mavericks")
        self.assertIsNone(result.data["league"]["avg_pace"])
        self.assertIsNone(result.data["league"]["avg_off_rtg"])
        for field in (
            "home.stats_season",
            "away.stats_season",
            "home.stats_last10",
            "away.stats_last10",
            "league.avg_pace",
            "league.avg_off_rtg",
        ):
            self.assertIn(field, result.data["missing"])
        self.assertNotIn("home.team", result.data["missing"])

    def test_laga_musim_gagal(self):
        with _PatchSemua(
            fetch_league_games=_fail("stats.nba.com", 1, "http_500: gagal"),
        ):
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        self.assertTrue(result.ok)
        home = result.data["home"]
        self.assertEqual(home["form5"], [])
        self.assertEqual(
            home["home_record"], {"w": 0, "l": 0, "ppg": None, "opp_ppg": None}
        )
        self.assertIsNone(home["rest_days"])
        self.assertIsNone(home["back_to_back"])
        self.assertEqual(result.data["h2h_last5"], [])
        for field in (
            "games_season",
            "h2h_last5",
            "home.form5",
            "away.form5",
            "home.home_record",
            "home.road_record",
            "home.rest_days",
            "home.back_to_back",
        ):
            self.assertIn(field, result.data["missing"])
        # Nama tim tetap dari statistik musim.
        self.assertEqual(home["team"], "Utah Jazz")
        # Statistik + pemain + cedera tetap ada.
        self.assertEqual(home["stats_season"]["off_rtg"], 112.0)
        self.assertEqual(len(home["players"]), 8)
        self.assertEqual(len(home["injuries"]), 1)

    def test_pemain_gagal(self):
        with _PatchSemua(
            fetch_player_advanced=_fail("Basketball-Reference", 2, "http_403: gagal"),
        ):
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["home"]["players"], [])
        self.assertEqual(result.data["away"]["players"], [])
        self.assertIn("home.players", result.data["missing"])
        self.assertIn("away.players", result.data["missing"])

    def test_cedera_hanya_satu_sumber(self):
        with _PatchSemua(
            fetch_report=_fail(
                "Official NBA Injury Report", 1, "pdf_http_404: tidak ada"
            ),
        ):
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        self.assertTrue(result.ok)
        # Cedera hanya dari ESPN; Irving PROBABLE tanpa konflik.
        irving = [
            i for i in result.data["away"]["injuries"] if i["player"] == "Kyrie Irving"
        ][0]
        self.assertEqual(irving["status"], "PROBABLE")
        self.assertEqual(irving["sources"], ["ESPN"])
        self.assertNotIn("conflict", irving)
        self.assertIn("injuries_official_pdf", result.data["missing"])
        self.assertNotIn("away.injuries", result.data["missing"])
        self.assertNotIn("injuries_konflik:Kyrie Irving", result.data["missing"])

    def test_cedera_kedua_sumber_gagal(self):
        with _PatchSemua(
            fetch_report=_fail("Official NBA Injury Report", 1, "pdf gagal"),
            fetch_injuries_nba=_fail("ESPN", 2, "http_500: gagal"),
        ):
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["home"]["injuries"], [])
        self.assertEqual(result.data["away"]["injuries"], [])
        for field in (
            "injuries_official_pdf",
            "injuries_espn",
            "home.injuries",
            "away.injuries",
        ):
            self.assertIn(field, result.data["missing"])

    def test_status_tidak_dikenal_tier2_menang(self):
        pdf = [
            {
                "player": "John Collins",
                "team": "Utah Jazz",
                "status": "UNKNOWN",
                "detail": None,
            }
        ]
        # Baris bentuk LAMA (tanpa status_normalized): menguji jalur
        # fallback _normalize_status di merge.
        espn_rows = [
            {"player": "John Collins", "team": "UTA", "status": "Out", "detail": "Knee"}
        ]
        with _PatchSemua(
            fetch_report=_ok("Official NBA Injury Report", 1, pdf),
            fetch_injuries_nba=_ok("ESPN", 2, espn_rows),
        ):
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        collins = result.data["home"]["injuries"][0]
        # Status tier 1 tidak terbaca -> status tier 2 (OUT) dipakai.
        self.assertEqual(collins["status"], "OUT")
        self.assertIn(
            "injuries_status_tidak_dikenal:John Collins", result.data["missing"]
        )
        self.assertNotIn("conflict", collins)

    def test_status_tidak_dikenal_di_semua_sumber(self):
        pdf = [
            {
                "player": "John Collins",
                "team": "Utah Jazz",
                "status": "UNKNOWN",
                "detail": None,
            }
        ]
        with _PatchSemua(
            fetch_report=_ok("Official NBA Injury Report", 1, pdf),
            fetch_injuries_nba=_ok("ESPN", 2, []),
        ):
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        collins = result.data["home"]["injuries"][0]
        self.assertIsNone(collins["status"])
        self.assertEqual(collins["status_asli"], "UNKNOWN")
        self.assertIn(
            "injuries_status_tidak_dikenal:John Collins", result.data["missing"]
        )

    def test_fetcher_exception_ditangkap(self):
        def meledak(*args, **kwargs):
            raise RuntimeError("boom")

        with _PatchSemua(fetch_league_games=meledak):
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        self.assertTrue(result.ok)
        self.assertIn("games_season", result.data["missing"])
        self.assertIn(
            "exception_RuntimeError", result.extra["fetch_errors"]["league_games"]
        )


class TestFetchMatchInputsGagalTotalDanInput(unittest.TestCase):
    def test_semua_sumber_gagal(self):
        def adv_gagal(season, last_n_games=None, client=None):
            return _fail("stats.nba.com", 1, "http_500")

        with _PatchSemua(
            fetch_league_games=_fail("stats.nba.com", 1, "http_500"),
            fetch_team_advanced_stats=adv_gagal,
            fetch_team_advanced=_fail("Basketball-Reference", 2, "http_403"),
            fetch_player_advanced=_fail("Basketball-Reference", 2, "http_403"),
            fetch_report=_fail("Official NBA Injury Report", 1, "pdf gagal"),
            fetch_injuries_nba=_fail("ESPN", 2, "http_500"),
        ):
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        self.assertFalse(result.ok)
        self.assertIn("semua_sumber_gagal", result.error or "")
        # Kerangka data tetap berbentuk kontrak.
        self.assertEqual(result.data["match"]["home_tricode"], "UTA")
        self.assertEqual(result.data["sources"], [])
        self.assertEqual(result.data["h2h_last5"], [])
        self.assertIsNone(result.data["home"]["team"])
        self.assertIn("home.team", result.data["missing"])
        self.assertIn("tournament_flag_tidak_dapat_ditentukan", result.data["missing"])
        # 7 percobaan fetch (termasuk fallback BBRef statistik musim).
        self.assertEqual(
            set(result.extra["fetch_errors"]),
            {
                "league_games",
                "team_advanced_season",
                "team_advanced_bbref",
                "team_advanced_last10",
                "player_advanced",
                "injuries_official_pdf",
                "injuries_espn",
            },
        )

    def test_input_tidak_valid(self):
        with _PatchSemua():
            for home, away, game_date, season in (
                ("XXX", "DAL", GAME_DATE, SEASON),  # tricode tak dikenal
                ("UTA", "UTA", GAME_DATE, SEASON),  # tim sama
                ("UTA", "DAL", "22-11-2026", SEASON),  # tanggal salah format
                ("UTA", "DAL", GAME_DATE, "2026/27"),  # musim salah format
            ):
                result = nba_brain.fetch_match_inputs(home, away, game_date, season)
                self.assertFalse(result.ok, f"{home}/{away}/{game_date}/{season}")
                self.assertIsNone(result.data)

    def test_tricode_huruf_kecil_diterima(self):
        with _PatchSemua():
            result = nba_brain.fetch_match_inputs("uta", "dal", GAME_DATE, SEASON)
        self.assertTrue(result.ok)
        self.assertEqual(result.data["match"]["home_tricode"], "UTA")

    def test_tanpa_laga_sebelumnya(self):
        # Tanggal sebelum laga pertama musim (2026-10-20): tidak ada
        # form/rekor/rest/H2H, tapi itu fakta — bukan kegagalan fetch.
        with _PatchSemua():
            result = nba_brain.fetch_match_inputs("UTA", "DAL", "2026-10-19", SEASON)
        self.assertTrue(result.ok)
        home = result.data["home"]
        self.assertEqual(home["form5"], [])
        self.assertEqual(
            home["home_record"], {"w": 0, "l": 0, "ppg": None, "opp_ppg": None}
        )
        self.assertIsNone(home["rest_days"])
        self.assertIsNone(home["back_to_back"])
        self.assertEqual(result.data["h2h_last5"], [])
        self.assertNotIn("games_season", result.data["missing"])
        self.assertNotIn("home.form5", result.data["missing"])


class TestMergeESPN(unittest.TestCase):
    """Merge PDF resmi + ESPN: pengecualian non-cedera, flag konflik
    komentar, dan kegagalan satu sumber (Perbaikan 4, patch 1b)."""

    def _baris_espn(self, player, team, status, detail, **extra):
        """Satu baris bentuk TERPARSE fetcher ESPN."""
        baris = {
            "player": player,
            "team": team,
            "status": status,
            "detail": detail,
            "status_normalized": extra.pop("status_normalized", None),
            "status_comment_conflict": extra.pop("status_comment_conflict", False),
            "is_injury": extra.pop("is_injury", True),
            "source": "ESPN",
            "tier": 2,
            "time": FETCHED_AT,
        }
        baris.update(extra)
        return baris

    def test_entri_bukan_cedera_dikecualikan(self):
        espn_rows = ESPN_INJURIES + [
            self._baris_espn(
                "Alex Two-Way",
                "Utah Jazz",
                "Day-To-Day",
                "Two-Way agreed to a two-way contract.",
                status_normalized="QUESTIONABLE",
                status_asli="Day-To-Day",
                is_injury=False,
            ),
            self._baris_espn(
                "Ben Rest",
                "Dallas Mavericks",
                "Out",
                "Rest (rest) is out.",
                status_normalized="OUT",
                is_injury=False,
            ),
        ]
        with _PatchSemua(fetch_injuries_nba=_ok("ESPN", 2, espn_rows)):
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        home_names = [i["player"] for i in result.data["home"]["injuries"]]
        away_names = [i["player"] for i in result.data["away"]["injuries"]]
        self.assertNotIn("Alex Two-Way", home_names)
        self.assertNotIn("Ben Rest", away_names)
        # Pengecualian dicatat di missing (jejak audit, bukan diam-diam).
        self.assertIn("injuries_bukan_cedera:Alex Two-Way", result.data["missing"])
        self.assertIn("injuries_bukan_cedera:Ben Rest", result.data["missing"])
        # Cedera sungguhan tetap ada.
        self.assertIn("Walker Kessler", home_names)
        self.assertIn("Anthony Davis", away_names)

    def test_konflik_komentar_diteruskan(self):
        espn_rows = ESPN_INJURIES + [
            self._baris_espn(
                "Chris Konflik",
                "Utah Jazz",
                "Out",
                "Konflik (knee) is listed as questionable.",
                status_normalized="OUT",
                status_comment_conflict=True,
            ),
        ]
        with _PatchSemua(fetch_injuries_nba=_ok("ESPN", 2, espn_rows)):
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        konflik = [
            i for i in result.data["home"]["injuries"] if i["player"] == "Chris Konflik"
        ][0]
        self.assertEqual(konflik["status"], "OUT")
        self.assertTrue(konflik["status_comment_conflict"])
        self.assertIn("injuries_komentar_konflik:Chris Konflik", result.data["missing"])
        # Entri tanpa konflik tidak membawa kunci itu.
        kessler = [
            i
            for i in result.data["home"]["injuries"]
            if i["player"] == "Walker Kessler"
        ][0]
        self.assertNotIn("status_comment_conflict", kessler)

    def test_espn_gagal_pdf_saja(self):
        with _PatchSemua(
            fetch_injuries_nba=_fail("ESPN", 2, "http_500: gagal"),
        ):
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        self.assertTrue(result.ok)
        # Irving hanya dari PDF: QUESTIONABLE, tanpa konflik.
        irving = [
            i for i in result.data["away"]["injuries"] if i["player"] == "Kyrie Irving"
        ][0]
        self.assertEqual(irving["status"], "QUESTIONABLE")
        self.assertEqual(irving["sources"], ["Official NBA Injury Report"])
        self.assertNotIn("conflict", irving)
        # Davis (hanya ada di ESPN) tidak ada.
        away_names = [i["player"] for i in result.data["away"]["injuries"]]
        self.assertNotIn("Anthony Davis", away_names)
        self.assertIn("injuries_espn", result.data["missing"])
        self.assertNotIn("away.injuries", result.data["missing"])
        self.assertNotIn("injuries_konflik:Kyrie Irving", result.data["missing"])

    def test_baris_tanpa_status_normalized_dinormalisasi_merge(self):
        # Baris bentuk lama (tanpa status_normalized, misal sumber lain)
        # tetap dinormalisasi lewat _normalize_status di merge.
        espn_rows = [
            {
                "player": "Dan Lama",
                "team": "Utah Jazz",
                "status": "Day-To-Day",
                "detail": "Back",
            }
        ]
        with _PatchSemua(
            fetch_report=_ok("Official NBA Injury Report", 1, []),
            fetch_injuries_nba=_ok("ESPN", 2, espn_rows),
        ):
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        dan = result.data["home"]["injuries"][0]
        self.assertEqual(dan["player"], "Dan Lama")
        self.assertEqual(dan["status"], "QUESTIONABLE")
        self.assertEqual(dan["status_asli"], "Day-To-Day")

    def test_b2_dua_sumber_terpenuhi(self):
        # Cedera yang ada di kedua sumber membawa kedua nama sumber —
        # bukti cek silang B2 bekerja.
        with _PatchSemua():
            result = nba_brain.fetch_match_inputs("UTA", "DAL", GAME_DATE, SEASON)
        kessler = result.data["home"]["injuries"][0]
        self.assertEqual(kessler["sources"], ["Official NBA Injury Report", "ESPN"])
        kinds = [(s["data_kind"], s["source"]) for s in result.data["sources"]]
        self.assertIn(("nba_injuries", "Official NBA Injury Report"), kinds)
        self.assertIn(("nba_injuries", "ESPN"), kinds)


class TestNormalizeStatus(unittest.TestCase):
    def test_status_eksak(self):
        for raw, expected in (
            ("Out", "OUT"),
            ("DOUBTFUL", "DOUBTFUL"),
            ("Questionable", "QUESTIONABLE"),
            ("probable", "PROBABLE"),
            ("Available", "AVAILABLE"),
        ):
            status, asli = nba_brain._normalize_status(raw)
            self.assertEqual(status, expected)
            self.assertIsNone(asli)

    def test_status_perkiraan(self):
        for raw in ("Day-To-Day", "day to day", "GTD", "Game-Time Decision"):
            status, asli = nba_brain._normalize_status(raw)
            self.assertEqual(status, "QUESTIONABLE")
            self.assertEqual(asli, raw)

    def test_status_tidak_dikenal(self):
        status, asli = nba_brain._normalize_status("UNKNOWN")
        self.assertIsNone(status)
        self.assertEqual(asli, "UNKNOWN")
        status, asli = nba_brain._normalize_status(None)
        self.assertIsNone(status)
        self.assertIsNone(asli)


class TestTambahPartisipasi(unittest.TestCase):
    """Wiring partisipasi game log (patch 1b, koreksi tumpang-tindih)."""

    def _blok(self):
        return {
            "tricode": "DET",
            "players": [
                {"player": "Jalen Duren", "bpm": 8.8, "mp_per_game": 19.0},
                {"player": "Cade Cunningham", "bpm": 5.0, "mp_per_game": 35.0},
                {"player": "Pemain Tanpa Slug", "bpm": 1.0, "mp_per_game": 10.0},
            ],
            "injuries": [
                {"player": "Jalen Duren", "status": "OUT"},
                {"player": "Pemain Tanpa Slug", "status": "OUT"},
            ],
        }

    def _rows(self):
        return [
            {"player": "Jalen Duren", "bbref_slug": "d/durenja01"},
            {"player": "Cade Cunningham", "bbref_slug": "c/cunnica01"},
            {"player": "Pemain Tanpa Slug", "bbref_slug": None},
        ]

    def test_out_mendapat_missed_last10(self):
        blok = self._blok()
        missing: list = []
        errors: dict = {}
        panggilan: list = []

        def palsu(targets, season=None, client=None):
            panggilan.append((targets, season))
            return {
                "Jalen Duren": {"missed_last10": 10, "games_considered": 10},
                "Pemain Tanpa Slug": {
                    "missed_last10": None,
                    "error": "tanpa slug",
                },
            }

        with patch.object(nba_brain, "fetch_missed_last10_many", palsu):
            nba_brain._tambah_partisipasi(
                blok, self._rows(), 2027, None, missing, errors
            )
        # Hanya pemain OUT yang diambil game log-nya (Cade sehat).
        self.assertEqual(len(panggilan), 1)
        self.assertEqual(
            {t["player"] for t in panggilan[0][0]},
            {"Jalen Duren", "Pemain Tanpa Slug"},
        )
        self.assertEqual(panggilan[0][1], 2027)
        pemain = {p["player"]: p for p in blok["players"]}
        self.assertEqual(pemain["Jalen Duren"]["missed_last10"], 10)
        self.assertNotIn("missed_last10", pemain["Cade Cunningham"])
        self.assertNotIn("missed_last10", pemain["Pemain Tanpa Slug"])
        self.assertIn("DET.participation:Pemain Tanpa Slug", missing)
        self.assertEqual(errors, {})

    def test_gagal_total_tidak_menggagalkan(self):
        blok = self._blok()
        missing: list = []
        errors: dict = {}

        def palsu_gagal(*args, **kwargs):
            raise RuntimeError("jaringan putus")

        with patch.object(nba_brain, "fetch_missed_last10_many", palsu_gagal):
            nba_brain._tambah_partisipasi(
                blok, self._rows(), 2027, None, missing, errors
            )
        self.assertIn("participation_DET", errors)
        self.assertIn("DET.participation", missing)
        for p in blok["players"]:
            self.assertNotIn("missed_last10", p)

    def test_tanpa_pemain_out_tidak_memanggil(self):
        blok = {"tricode": "DET", "players": [{"player": "Cade Cunningham"}]}
        missing: list = []
        errors: dict = {}
        with patch.object(
            nba_brain, "fetch_missed_last10_many", side_effect=AssertionError
        ):
            nba_brain._tambah_partisipasi(blok, [], 2027, None, missing, errors)
        self.assertEqual(missing, [])
        self.assertEqual(errors, {})


if __name__ == "__main__":
    unittest.main()
