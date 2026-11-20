"""Tes ingest/espn.py — TANPA network (mock client + fixture).

Fixture dibentuk dari respons asli yang tersimpan di cache probe 2a/2a-lanjutan
(scoreboard NBA + EPL, injuries NBA, odds EPL DraftKings).
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import espn


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


def _event(event_id, name, date, status_desc, home, away, odds=None):
    return {
        "id": event_id,
        "name": name,
        "date": date,
        "status": {
            "type": {
                "id": "3",
                "name": "STATUS_FINAL",
                "state": "post",
                "description": status_desc,
                "detail": status_desc,
                "shortDetail": status_desc,
            }
        },
        "competitions": [
            {
                "id": event_id,
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {
                            "displayName": home[0],
                            "abbreviation": home[1],
                            "shortDisplayName": home[0].split()[-1],
                        },
                    },
                    {
                        "homeAway": "away",
                        "team": {
                            "displayName": away[0],
                            "abbreviation": away[1],
                            "shortDisplayName": away[0].split()[-1],
                        },
                    },
                ],
                "odds": odds if odds is not None else [],
            }
        ],
    }


NBA_SCOREBOARD_FIXTURE = {
    "leagues": [{"id": "46", "slug": "nba", "abbreviation": "NBA"}],
    "events": [
        _event(
            "401910019",
            "Golden State Warriors at Memphis Grizzlies",
            "2026-11-20T01:00Z",
            "Final",
            ("Memphis Grizzlies", "MEM"),
            ("Golden State Warriors", "GS"),
        )
    ],
}

# Entri odds DraftKings dari probes/out/espn_odds.json (Fulham @ Man City).
DRAFTKINGS_ODDS = {
    "provider": {"name": "DraftKings"},
    "details": "MNC -260",
    "overUnder": 3.5,
    "moneyline": {
        "home": {"close": {"odds": "-260"}},
        "away": {"close": {"odds": "+650"}},
        "draw": {"close": {"odds": "+425"}},
    },
    "pointSpread": {
        "home": {"close": {"line": "-1.5", "odds": "-105"}},
        "away": {"close": {"line": "+1.5", "odds": "-130"}},
    },
    "total": {
        "over": {"close": {"line": "o3.5", "odds": "+120"}},
        "under": {"close": {"line": "u3.5", "odds": "-145"}},
    },
}

EPL_SCOREBOARD_FIXTURE = {
    "leagues": [{"id": "700", "slug": "eng.1", "abbreviation": "Premier League"}],
    "events": [
        _event(
            "401879233",
            "Fulham at Manchester City",
            "2026-11-21T12:30Z",
            "Scheduled",
            ("Manchester City", "MNC"),
            ("Fulham", "FUL"),
            odds=[DRAFTKINGS_ODDS],
        ),
        _event(
            "401879234",
            "Arsenal at Chelsea",
            "2026-11-21T15:00Z",
            "Scheduled",
            ("Chelsea", "CHE"),
            ("Arsenal", "ARS"),
            odds=[],
        ),
    ],
}

INJURIES_FIXTURE = {
    "timestamp": "2026-11-20T15:28:54Z",
    "status": "success",
    "injuries": [
        {
            "id": "1",
            "displayName": "Atlanta Hawks",
            "injuries": [
                {
                    "id": "540056",
                    "status": "Out",
                    "shortComment": "Landale (hip) won't play in Friday's game.",
                    "athlete": {"displayName": "Jock Landale"},
                    "details": {
                        "type": "Hip",
                        "detail": "Inflammation",
                        "side": "Right",
                    },
                },
                {
                    "id": "540057",
                    "status": "Day-To-Day",
                    "shortComment": None,
                    "athlete": {"displayName": "Kingston Flemings"},
                    "details": {"type": "Back", "detail": "Strain"},
                },
            ],
        },
        {
            "id": "2",
            "displayName": "Brooklyn Nets",
            "injuries": [],
        },
    ],
}


class TestParseScoreboard(unittest.TestCase):
    def test_parse_nba(self):
        games = espn.parse_scoreboard(NBA_SCOREBOARD_FIXTURE, "nba")
        self.assertEqual(len(games), 1)
        game = games[0]
        self.assertEqual(game["game_id"], "401910019")
        self.assertEqual(game["home_team"], "Memphis Grizzlies")
        self.assertEqual(game["away_team"], "Golden State Warriors")
        self.assertEqual(game["start_time"], "2026-11-20T01:00Z")
        self.assertEqual(game["status"], "Final")
        self.assertEqual(game["league"], "nba")

    def test_parse_tanpa_events(self):
        with self.assertRaises(ValueError) as ctx:
            espn.parse_scoreboard({}, "nba")
        self.assertEqual(str(ctx.exception), "espn_format_changed")


class TestFetchScoreboard(unittest.TestCase):
    def test_fetch_nba_memakai_param_dates(self):
        url = (
            "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
            "?dates=20261120"
        )
        client = FakeClient({url: _resp(200, NBA_SCOREBOARD_FIXTURE)})
        result = espn.fetch_scoreboard("nba", "2026-11-20", client=client)
        self.assertTrue(result.ok)
        self.assertEqual(result.source, "ESPN")
        self.assertEqual(result.tier, 2)
        self.assertEqual(len(result.data), 1)
        self.assertEqual(client.urls_requested, [url])

    def test_fetch_epl(self):
        url = (
            "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"
            "?dates=20261121"
        )
        client = FakeClient({url: _resp(200, EPL_SCOREBOARD_FIXTURE)})
        result = espn.fetch_scoreboard("epl", "2026-11-21", client=client)
        self.assertTrue(result.ok)
        self.assertEqual(len(result.data), 2)
        self.assertEqual(result.data[0]["home_team"], "Manchester City")
        self.assertEqual(result.data[0]["league"], "eng.1")

    def test_fetch_sport_tidak_dikenal(self):
        result = espn.fetch_scoreboard("nhl", "2026-11-20", client=FakeClient({}))
        self.assertFalse(result.ok)
        self.assertIn("sport_tidak_dikenal", result.error or "")

    def test_fetch_tanggal_tidak_valid(self):
        result = espn.fetch_scoreboard("nba", "20-11-2026", client=FakeClient({}))
        self.assertFalse(result.ok)
        self.assertIn("tanggal_tidak_valid", result.error or "")

    def test_fetch_http_gagal(self):
        result = espn.fetch_scoreboard("nba", "2026-11-20", client=FakeClient({}))
        self.assertFalse(result.ok)
        self.assertIn("http_404", result.error or "")


class TestFetchInjuriesNba(unittest.TestCase):
    def test_parse_injuries(self):
        injuries = espn.parse_injuries_nba(INJURIES_FIXTURE)
        self.assertEqual(len(injuries), 2)
        self.assertEqual(injuries[0]["player"], "Jock Landale")
        self.assertEqual(injuries[0]["team"], "Atlanta Hawks")
        self.assertEqual(injuries[0]["status"], "Out")
        self.assertEqual(
            injuries[0]["detail"], "Landale (hip) won't play in Friday's game."
        )
        # Tanpa shortComment: detail digabung dari details.
        self.assertEqual(injuries[1]["player"], "Kingston Flemings")
        self.assertEqual(injuries[1]["status"], "Day-To-Day")
        self.assertEqual(injuries[1]["detail"], "Back - Strain")

    def test_parse_tanpa_injuries(self):
        with self.assertRaises(ValueError) as ctx:
            espn.parse_injuries_nba({})
        self.assertEqual(str(ctx.exception), "espn_format_changed")

    def test_fetch_injuries(self):
        client = FakeClient({espn.NBA_INJURIES_URL: _resp(200, INJURIES_FIXTURE)})
        result = espn.fetch_injuries_nba(client=client)
        self.assertTrue(result.ok)
        self.assertEqual(result.extra["n_injuries"], 2)


class TestFetchOddsFootball(unittest.TestCase):
    def test_parse_odds_draftkings(self):
        parsed = espn.parse_odds_entry(DRAFTKINGS_ODDS)
        self.assertEqual(parsed["provider"], "DraftKings")
        self.assertEqual(
            parsed["moneyline"], {"home": "-260", "draw": "+425", "away": "+650"}
        )
        self.assertEqual(
            parsed["spread"],
            {
                "home_line": "-1.5",
                "home_odds": "-105",
                "away_line": "+1.5",
                "away_odds": "-130",
            },
        )
        # Garis total dinormalisasi dari "o3.5" jadi float 3.5.
        self.assertEqual(
            parsed["total"], {"line": 3.5, "over_odds": "+120", "under_odds": "-145"}
        )

    def test_parse_odds_kosong_jadi_none(self):
        parsed = espn.parse_odds_entry({"provider": {"name": "DraftKings"}})
        self.assertEqual(
            parsed["moneyline"], {"home": None, "draw": None, "away": None}
        )
        self.assertIsNone(parsed["total"]["line"])

    def test_fetch_odds_laga_tanpa_odds_dicatat(self):
        url = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"
        client = FakeClient({url: _resp(200, EPL_SCOREBOARD_FIXTURE)})
        result = espn.fetch_odds_football(client=client)
        self.assertTrue(result.ok)
        self.assertEqual(len(result.data), 1)
        row = result.data[0]
        self.assertEqual(row["home_team"], "Manchester City")
        self.assertEqual(row["away_team"], "Fulham")
        self.assertEqual(row["commence_time"], "2026-11-21T12:30Z")
        self.assertEqual(row["provider"], "DraftKings")
        self.assertEqual(row["moneyline"]["home"], "-260")
        # Laga tanpa odds dicatat di extra, bukan error.
        self.assertEqual(result.extra["games_without_odds"], ["Arsenal at Chelsea"])
        self.assertEqual(result.extra["n_games_with_odds"], 1)

    def test_fetch_odds_http_gagal(self):
        result = espn.fetch_odds_football(client=FakeClient({}))
        self.assertFalse(result.ok)
        self.assertIn("http_404", result.error or "")

    def test_tidak_ada_fetch_odds_nba(self):
        # ESPN tidak punya odds NBA (terbukti di probe) — fungsi itu
        # memang tidak boleh ada.
        self.assertFalse(hasattr(espn, "fetch_odds_nba"))


if __name__ == "__main__":
    unittest.main()
