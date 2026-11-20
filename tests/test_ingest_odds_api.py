"""Tes ingest/odds_api.py — fetch odds sportsbook (mock).

TANPA network (LARANGAN KERAS: tes tidak pernah memanggil The Odds API
sungguhan — kuota 500 kredit/bulan milik koordinator). Fixture meniru
bentuk respons v4 yang diketahui (list event + bookmakers; Pinnacle
key "pinnacle").
"""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import odds_api

# Fixture: 2 event NBA, bookmakers Pinnacle + DraftKings.
FIXTURE_EVENTS = [
    {
        "id": "evt-1",
        "sport_key": "basketball_nba",
        "sport_title": "NBA",
        "commence_time": "2026-11-21T01:00:00Z",
        "home_team": "Chicago Bulls",
        "away_team": "Washington Wizards",
        "bookmakers": [
            {
                "key": "pinnacle",
                "title": "Pinnacle",
                "last_update": "2026-11-20T15:00:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": "2026-11-20T15:00:00Z",
                        "outcomes": [
                            {"name": "Chicago Bulls", "price": 1.72},
                            {"name": "Washington Wizards", "price": 2.15},
                        ],
                    },
                    {
                        "key": "spreads",
                        "last_update": "2026-11-20T15:00:00Z",
                        "outcomes": [
                            {"name": "Chicago Bulls", "price": 1.91, "point": -2.5},
                            {"name": "Washington Wizards", "price": 1.91, "point": 2.5},
                        ],
                    },
                    {
                        "key": "totals",
                        "last_update": "2026-11-20T15:00:00Z",
                        "outcomes": [
                            {"name": "Over", "price": 1.95, "point": "243.5"},
                            {"name": "Under", "price": 1.87, "point": 243.5},
                            {"name": "Tanpa Harga"},
                        ],
                    },
                ],
            },
            {
                "key": "draftkings",
                "title": "DraftKings",
                "last_update": "2026-11-20T15:00:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": "2026-11-20T15:00:00Z",
                        "outcomes": [
                            {"name": "Chicago Bulls", "price": 1.70},
                            {"name": "Washington Wizards", "price": 2.20},
                        ],
                    }
                ],
            },
        ],
    },
    {
        "id": "evt-2",
        "sport_key": "basketball_nba",
        "sport_title": "NBA",
        "commence_time": "2026-11-21T02:00:00Z",
        "home_team": "Atlanta Hawks",
        "away_team": "Charlotte Hornets",
        "bookmakers": [],
    },
]


class FakeHttpClient:
    """Client HTTP palsu: mengembalikan respons canned + mencatat URL."""

    def __init__(self, status=200, body=None, headers=None):
        self.status = status
        self.body = body if body is not None else json.dumps(FIXTURE_EVENTS)
        self.headers = headers or {}
        self.urls = []

    def get(self, url, use_cache=True):
        self.urls.append(url)
        return {
            "url": url,
            "status": self.status,
            "headers": self.headers,
            "rate_limit_headers": {},
            "body": self.body,
            "error": None,
            "from_cache": False,
        }


class TestFetchOdds(unittest.TestCase):
    def test_sukses_dan_normalisasi(self):
        client = FakeHttpClient(
            headers={"x-requests-last": "1", "x-requests-remaining": "499"}
        )
        result = odds_api.fetch_odds(
            "basketball_nba", client=client, api_key="key-palsu"
        )
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.source, "The Odds API")
        self.assertEqual(result.tier, 2)
        self.assertEqual(len(result.data), 2)
        event = result.data[0]
        self.assertEqual(event["event_id"], "evt-1")
        self.assertEqual(event["sport_key"], "basketball_nba")
        self.assertEqual(event["home_team"], "Chicago Bulls")
        self.assertEqual(event["away_team"], "Washington Wizards")
        self.assertEqual(event["commence_time"], "2026-11-21T01:00:00Z")
        pinnacle = event["bookmakers"][0]
        self.assertEqual(pinnacle["key"], "pinnacle")
        self.assertEqual(pinnacle["title"], "Pinnacle")
        h2h = pinnacle["markets"][0]
        self.assertEqual(h2h["key"], "h2h")
        self.assertEqual(h2h["outcomes"][0]["price"], 1.72)
        self.assertIsNone(h2h["outcomes"][0]["point"])
        spreads = pinnacle["markets"][1]
        self.assertEqual(spreads["outcomes"][0]["point"], -2.5)
        totals = pinnacle["markets"][2]
        # point string "243.5" diparse jadi float; outcome tanpa harga dibuang.
        self.assertEqual(len(totals["outcomes"]), 2)
        self.assertEqual(totals["outcomes"][0]["point"], 243.5)

    def test_credits_dari_header(self):
        client = FakeHttpClient(
            headers={"x-requests-last": "1", "x-requests-remaining": "499"}
        )
        result = odds_api.fetch_odds(
            "basketball_nba", client=client, api_key="key-palsu"
        )
        self.assertEqual(result.credits_used, 1)
        self.assertEqual(result.extra["requests_remaining"], "499")
        self.assertEqual(result.extra["events_returned"], 2)

    def test_header_tanpa_peduli_kapitalisasi(self):
        client = FakeHttpClient(
            headers={"X-Requests-Last": "2", "X-Requests-Remaining": "498"}
        )
        result = odds_api.fetch_odds(
            "basketball_nba", client=client, api_key="key-palsu"
        )
        self.assertEqual(result.credits_used, 2)
        self.assertEqual(result.extra["requests_remaining"], "498")

    def test_url_memuat_parameter_benar(self):
        client = FakeHttpClient()
        odds_api.fetch_odds(
            "soccer_epl",
            markets="h2h",
            regions="eu",
            client=client,
            api_key="key-palsu",
        )
        url = client.urls[0]
        self.assertIn("/sports/soccer_epl/odds", url)
        self.assertIn("apiKey=key-palsu", url)
        self.assertIn("regions=eu", url)
        self.assertIn("markets=h2h", url)
        self.assertIn("oddsFormat=decimal", url)

    def test_url_cache_tanpa_apikey(self):
        # Properti keamanan: kunci cache tidak boleh memuat apiKey.
        cache_url = odds_api._cache_url("basketball_nba", "h2h", "eu")
        self.assertNotIn("apiKey", cache_url)
        self.assertNotIn("key-palsu", cache_url)
        request_url = odds_api._request_url("basketball_nba", "h2h", "eu", "key-palsu")
        self.assertIn("apiKey=key-palsu", request_url)

    def test_http_error(self):
        client = FakeHttpClient(status=401, body="unauthorized")
        result = odds_api.fetch_odds(
            "basketball_nba", client=client, api_key="key-salah"
        )
        self.assertFalse(result.ok)
        self.assertIn("401", result.error)

    def test_body_bukan_list(self):
        client = FakeHttpClient(body=json.dumps({"error": "bukan list"}))
        result = odds_api.fetch_odds(
            "basketball_nba", client=client, api_key="key-palsu"
        )
        self.assertFalse(result.ok)

    def test_sport_key_tidak_didukung(self):
        client = FakeHttpClient()
        result = odds_api.fetch_odds(
            "basketball_ncaab", client=client, api_key="key-palsu"
        )
        self.assertFalse(result.ok)
        self.assertEqual(client.urls, [])

    def test_key_tidak_ada(self):
        client = FakeHttpClient()
        with mock.patch("ingest.odds_api.load_dotenv", return_value={}):
            result = odds_api.fetch_odds("basketball_nba", client=client)
        self.assertFalse(result.ok)
        self.assertIn("ODDS_API_KEY", result.error)
        self.assertEqual(client.urls, [])


if __name__ == "__main__":
    unittest.main()
