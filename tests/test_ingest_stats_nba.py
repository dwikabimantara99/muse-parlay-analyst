"""Tes ingest/stats_nba.py — TANPA network (mock client + fixture).

Fixture dibentuk dari respons asli yang tersimpan di cache probe 2a
(scoreboardv2 2026-11-20, leaguestandingsv3 2025-26).
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import stats_nba


class FakeClient:
    """Client palsu: get() mengembalikan respons yang sudah disiapkan."""

    def __init__(self, responses: dict[str, dict]) -> None:
        self.responses = responses
        self.urls_requested: list[str] = []

    def get(self, url: str, use_cache: bool = True) -> dict:
        """Kembalikan respons untuk URL (default: 404)."""
        self.urls_requested.append(url)
        return self.responses.get(url, {"status": 404, "body": "", "error": None})


def _resp(status: int, body: object) -> dict:
    return {
        "status": status,
        "body": body if isinstance(body, str) else json.dumps(body),
        "error": None,
    }


# Satu laga dari scoreboardv2 2026-11-20 (cache probe 2a): CHA@ATL,
# game 0022600043, status "7:00 pm ET".
SCOREBOARD_FIXTURE = {
    "resource": "scoreboardV2",
    "parameters": {"LeagueID": "00", "GameDate": "11/20/2026", "DayOffset": 0},
    "resultSets": [
        {
            "name": "GameHeader",
            "headers": [
                "GAME_DATE_EST",
                "GAME_SEQUENCE",
                "GAME_ID",
                "GAME_STATUS_ID",
                "GAME_STATUS_TEXT",
                "GAMECODE",
                "HOME_TEAM_ID",
                "VISITOR_TEAM_ID",
                "SEASON",
            ],
            "rowSet": [
                [
                    "2026-11-20T00:00:00",
                    1,
                    "0022600043",
                    1,
                    "7:00 pm ET",
                    "20261120/CHAATL",
                    1610612737,
                    1610612766,
                    "2026",
                ],
                [
                    "2026-11-20T00:00:00",
                    2,
                    "0022600044",
                    3,
                    "Final",
                    "20261120/GSWMEM",
                    1610612763,
                    1610612744,
                    "2026",
                ],
            ],
        },
        {
            "name": "LineScore",
            "headers": [
                "GAME_DATE_EST",
                "GAME_SEQUENCE",
                "GAME_ID",
                "TEAM_ID",
                "TEAM_ABBREVIATION",
                "TEAM_CITY_NAME",
                "TEAM_NAME",
                "TEAM_WINS_LOSSES",
            ],
            "rowSet": [
                [
                    "2026-11-20T00:00:00",
                    1,
                    "0022600043",
                    1610612737,
                    "ATL",
                    "Atlanta",
                    "Hawks",
                    "9-6",
                ],
                [
                    "2026-11-20T00:00:00",
                    1,
                    "0022600043",
                    1610612766,
                    "CHA",
                    "Charlotte",
                    "Hornets",
                    "5-10",
                ],
                [
                    "2026-11-20T00:00:00",
                    2,
                    "0022600044",
                    1610612763,
                    "MEM",
                    "Memphis",
                    "Grizzlies",
                    "8-7",
                ],
                [
                    "2026-11-20T00:00:00",
                    2,
                    "0022600044",
                    1610612744,
                    "GSW",
                    "Golden State",
                    "Warriors",
                    "10-5",
                ],
            ],
        },
    ],
}

STANDINGS_HEADERS = [
    "LeagueID",
    "SeasonID",
    "TeamID",
    "TeamCity",
    "TeamName",
    "TeamSlug",
    "Conference",
    "ConferenceRecord",
    "PlayoffRank",
    "ClinchIndicator",
    "Division",
    "DivisionRecord",
    "DivisionRank",
    "WINS",
    "LOSSES",
    "WinPCT",
    "LeagueRank",
    "Record",
    "HOME",
    "ROAD",
    "L10",
    "Last10Home",
    "Last10Road",
    "OT",
    "ThreePTSOrLess",
    "TenPTSOrMore",
    "LongHomeStreak",
    "strLongHomeStreak",
    "LongRoadStreak",
    "strLongRoadStreak",
    "LongWinStreak",
    "LongLossStreak",
    "CurrentHomeStreak",
    "strCurrentHomeStreak",
    "CurrentRoadStreak",
    "strCurrentRoadStreak",
    "CurrentStreak",
    "strCurrentStreak",
    "ConferenceGamesBack",
    "DivisionGamesBack",
    "ClinchedConferenceTitle",
    "ClinchedDivisionTitle",
    "ClinchedPlayoffBirth",
    "ClinchedPlayIn",
    "EliminatedConference",
    "EliminatedDivision",
    "AheadAtHalf",
    "BehindAtHalf",
    "TiedAtHalf",
    "AheadAtThird",
    "BehindAtThird",
    "TiedAtThird",
    "Score100PTS",
    "OppScore100PTS",
    "OppOver500",
    "LeadInFGPCT",
    "LeadInReb",
    "FewerTurnovers",
    "PointsPG",
    "OppPointsPG",
    "DiffPointsPG",
]


def _standings_row(team_id, city, name, wins, losses, win_pct, points_pg):
    row = [None] * len(STANDINGS_HEADERS)
    values = {
        "TeamID": team_id,
        "TeamCity": city,
        "TeamName": name,
        "Conference": "West",
        "Division": "Northwest",
        "PlayoffRank": 1,
        "DivisionRank": 1,
        "WINS": wins,
        "LOSSES": losses,
        "WinPCT": win_pct,
        "LeagueRank": 1,
        "Record": f"{wins}-{losses}",
        "HOME": "34-7",
        "ROAD": "30-10",
        "L10": "7-3",
        "strCurrentStreak": "L 2",
        "PointsPG": points_pg,
        "OppPointsPG": 107.9,
        "DiffPointsPG": 11.1,
    }
    for key, value in values.items():
        row[STANDINGS_HEADERS.index(key)] = value
    return row


STANDINGS_FIXTURE = {
    "resource": "leaguestandings",
    "resultSets": [
        {
            "name": "Standings",
            "headers": STANDINGS_HEADERS,
            "rowSet": [
                _standings_row(
                    1610612760, "Oklahoma City", "Thunder", 64, 18, 0.78, 119.0
                ),
                _standings_row(
                    1610612755, "Philadelphia", "76ers", 13, 3, 0.813, 118.2
                ),
            ],
        }
    ],
}


class TestFetchScoreboard(unittest.TestCase):
    def test_parse_satu_laga_pre_game(self):
        games = stats_nba.parse_scoreboard(SCOREBOARD_FIXTURE)
        self.assertEqual(len(games), 2)
        game = games[0]
        self.assertEqual(game["game_id"], "0022600043")
        self.assertEqual(game["home_team"], "Atlanta Hawks")
        self.assertEqual(game["away_team"], "Charlotte Hornets")
        self.assertEqual(game["home_tricode"], "ATL")
        self.assertEqual(game["away_tricode"], "CHA")
        self.assertEqual(game["status"], "7:00 pm ET")
        self.assertEqual(game["status_id"], 1)
        # Jam tip-off 7:00 pm ET tanggal 2026-11-20 (EST, UTC-5).
        self.assertEqual(game["start_time"], "2026-11-20T19:00:00-05:00")
        self.assertEqual(game["game_date_est"], "2026-11-20")

    def test_parse_laga_final_start_time_none(self):
        games = stats_nba.parse_scoreboard(SCOREBOARD_FIXTURE)
        final = games[1]
        self.assertEqual(final["status"], "Final")
        self.assertIsNone(final["start_time"])
        self.assertEqual(final["home_team"], "Memphis Grizzlies")

    def test_parse_tanpa_resultset_wajib(self):
        with self.assertRaises(ValueError) as ctx:
            stats_nba.parse_scoreboard({"resultSets": []})
        self.assertEqual(str(ctx.exception), "stats_nba_format_changed")

    def test_fetch_memakai_url_dan_param_probe(self):
        url = (
            "https://stats.nba.com/stats/scoreboardv2"
            "?GameDate=11/20/2026&LeagueID=00&DayOffset=0"
        )
        client = FakeClient({url: _resp(200, SCOREBOARD_FIXTURE)})
        result = stats_nba.fetch_scoreboard("2026-11-20", client=client)
        self.assertTrue(result.ok)
        self.assertEqual(result.source, "stats.nba.com")
        self.assertEqual(result.tier, 1)
        self.assertEqual(client.urls_requested, [url])
        self.assertEqual(len(result.data), 2)
        self.assertEqual(result.extra["n_games"], 2)
        self.assertNotIn("games_tanpa_nama_tim", result.extra)

    def test_fetch_tanggal_tidak_valid(self):
        result = stats_nba.fetch_scoreboard("20-11-2026", client=FakeClient({}))
        self.assertFalse(result.ok)
        self.assertIn("tanggal_tidak_valid", result.error or "")

    def test_fetch_http_gagal(self):
        client = FakeClient({})
        result = stats_nba.fetch_scoreboard("2026-11-20", client=client)
        self.assertFalse(result.ok)
        self.assertIn("http_404", result.error or "")

    def test_fetch_tim_tidak_dikenal_dicatat_di_extra(self):
        fixture = json.loads(json.dumps(SCOREBOARD_FIXTURE))
        # Hapus baris LineScore tim tamu laga pertama.
        fixture["resultSets"][1]["rowSet"] = fixture["resultSets"][1]["rowSet"][:1]
        url = (
            "https://stats.nba.com/stats/scoreboardv2"
            "?GameDate=11/20/2026&LeagueID=00&DayOffset=0"
        )
        client = FakeClient({url: _resp(200, fixture)})
        result = stats_nba.fetch_scoreboard("2026-11-20", client=client)
        self.assertTrue(result.ok)
        self.assertIsNone(result.data[0]["away_team"])
        self.assertIn("0022600043", result.extra["games_tanpa_nama_tim"])


class TestFetchStandings(unittest.TestCase):
    def test_parse_klasemen(self):
        rows = stats_nba.parse_standings(STANDINGS_FIXTURE)
        self.assertEqual(len(rows), 2)
        okc = rows[0]
        self.assertEqual(okc["team"], "Oklahoma City Thunder")
        self.assertEqual(okc["tricode"], "OKC")
        self.assertEqual(okc["wins"], 64)
        self.assertEqual(okc["losses"], 18)
        self.assertEqual(okc["win_pct"], 0.78)
        self.assertEqual(okc["record"], "64-18")
        self.assertEqual(okc["points_pg"], 119.0)
        self.assertEqual(okc["current_streak"], "L 2")
        self.assertEqual(rows[1]["tricode"], "PHI")

    def test_peta_tricode_lengkap_30_tim(self):
        self.assertEqual(len(stats_nba.TEAM_TRICODES), 30)
        self.assertEqual(stats_nba.TEAM_TRICODES[1610612744], "GSW")
        self.assertEqual(stats_nba.TEAM_TRICODES[1610612748], "MIA")

    def test_parse_tanpa_standings(self):
        with self.assertRaises(ValueError) as ctx:
            stats_nba.parse_standings({"resultSets": []})
        self.assertEqual(str(ctx.exception), "stats_nba_format_changed")

    def test_fetch_standings(self):
        url = (
            "https://stats.nba.com/stats/leaguestandingsv3"
            "?LeagueID=00&Season=2026-27&SeasonType=Regular%20Season"
        )
        client = FakeClient({url: _resp(200, STANDINGS_FIXTURE)})
        result = stats_nba.fetch_standings(client=client)
        self.assertTrue(result.ok)
        self.assertEqual(result.extra["season"], "2026-27")
        self.assertEqual(result.extra["n_teams"], 2)
        self.assertEqual(client.urls_requested, [url])

    def test_fetch_standings_musim_lain(self):
        url = (
            "https://stats.nba.com/stats/leaguestandingsv3"
            "?LeagueID=00&Season=2025-26&SeasonType=Regular%20Season"
        )
        client = FakeClient({url: _resp(200, STANDINGS_FIXTURE)})
        result = stats_nba.fetch_standings(client=client, season="2025-26")
        self.assertTrue(result.ok)
        self.assertEqual(result.extra["season"], "2025-26")

    def test_fetch_standings_http_gagal(self):
        result = stats_nba.fetch_standings(client=FakeClient({}))
        self.assertFalse(result.ok)
        self.assertIn("http_404", result.error or "")


if __name__ == "__main__":
    unittest.main()
