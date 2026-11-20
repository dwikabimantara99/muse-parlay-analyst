"""Tes ingest/kalshi.py — fetch pasar Kalshi (mock).

TANPA network. Fixture meniru respons API asli (cache probe
kalshi_sports): field harga `*_dollars`, judul "<Tim> wins" /
"wins by more than/over X" / total.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import kalshi

NBA_GAME_EVENTS = [
    {
        "event_ticker": "KXNBAGAME-26NOV20CHAATL",
        "series_ticker": "KXNBAGAME",
        "title": "Charlotte vs Atlanta",
        "sub_title": "CHA vs ATL (Nov 20)",
    }
]

NBA_GAME_MARKETS = [
    {
        "ticker": "KXNBAGAME-26NOV20CHAATL-CHA",
        "event_ticker": "KXNBAGAME-26NOV20CHAATL",
        "title": "Charlotte wins",
        "yes_bid_dollars": "0.1200",
        "yes_ask_dollars": "0.1300",
        "last_price_dollars": "0.1300",
    },
    {
        "ticker": "KXNBAGAME-26NOV20CHAATL-ATL",
        "event_ticker": "KXNBAGAME-26NOV20CHAATL",
        "title": "Atlanta wins",
        "yes_bid_dollars": "0.8600",
        "yes_ask_dollars": "0.8700",
        "last_price_dollars": "0.8700",
    },
    {
        # Tanpa ask -> ditolak (bukan diisi last_price).
        "ticker": "KXNBAGAME-26NOV20CHAATL-XXX",
        "event_ticker": "KXNBAGAME-26NOV20CHAATL",
        "title": "Charlotte wins",
        "yes_bid_dollars": "0.1200",
        "yes_ask_dollars": None,
        "last_price_dollars": "0.1200",
    },
]

EPL_GAME_EVENTS = [
    {
        "event_ticker": "KXEPLGAME-26NOV21CHEBHA",
        "series_ticker": "KXEPLGAME",
        "title": "Chelsea vs Leeds United",
    }
]

EPL_GAME_MARKETS = [
    {
        "ticker": "KXEPLGAME-26NOV21CHEBHA-CHE",
        "event_ticker": "KXEPLGAME-26NOV21CHEBHA",
        "title": "Chelsea wins",
        "yes_bid_dollars": "0.5800",
        "yes_ask_dollars": "0.5900",
        "last_price_dollars": "0.5800",
    },
    {
        "ticker": "KXEPLGAME-26NOV21CHEBHA-TIE",
        "event_ticker": "KXEPLGAME-26NOV21CHEBHA",
        "title": "Tie is the result",
        "yes_bid_dollars": "0.2400",
        "yes_ask_dollars": "0.2500",
        "last_price_dollars": "0.2400",
    },
    {
        "ticker": "KXEPLGAME-26NOV21CHEBHA-LEE",
        "event_ticker": "KXEPLGAME-26NOV21CHEBHA",
        "title": "Leeds United wins",
        "yes_bid_dollars": "0.1600",
        "yes_ask_dollars": "0.1700",
        "last_price_dollars": "0.1600",
    },
]

NBA_SPREAD_EVENTS = [
    {
        "event_ticker": "KXNBASPREAD-26NOV20PHXUTA",
        "series_ticker": "KXNBASPREAD",
        "title": "Phoenix vs Utah: Spread",
    }
]

NBA_SPREAD_MARKETS = [
    {
        "ticker": "KXNBASPREAD-26NOV20PHXUTA-UTA8",
        "event_ticker": "KXNBASPREAD-26NOV20PHXUTA",
        "title": "Utah wins by over 7.5 points",
        "yes_bid_dollars": "0.1800",
        "yes_ask_dollars": "0.2100",
        "last_price_dollars": "0.0000",
    },
    {
        "ticker": "KXNBASPREAD-26NOV20PHXUTA-PHX8",
        "event_ticker": "KXNBASPREAD-26NOV20PHXUTA",
        "title": "Phoenix wins by over 7.5 points",
        "yes_bid_dollars": "0.0100",
        "yes_ask_dollars": "0.0200",
        "last_price_dollars": "0.0200",
    },
]

NBA_TOTAL_EVENTS = [
    {
        "event_ticker": "KXNBATOTAL-26NOV20CHAATL",
        "series_ticker": "KXNBATOTAL",
        "title": "Charlotte vs Atlanta: Total Points",
    }
]

NBA_TOTAL_MARKETS = [
    {
        "ticker": "KXNBATOTAL-26NOV20CHAATL-1",
        "event_ticker": "KXNBATOTAL-26NOV20CHAATL",
        "title": "Full Game: Over 254.5 points scored",
        "yes_bid_dollars": "0.0400",
        "yes_ask_dollars": "0.0700",
        "last_price_dollars": "0.0000",
    },
]

EPL_SPREAD_MARKETS = [
    {
        "ticker": "KXEPLSPREAD-26NOV23BREEVE-EVE2",
        "event_ticker": "KXEPLSPREAD-26NOV23BREEVE",
        "title": "Everton wins by more than 1.5 goals?",
        "yes_bid_dollars": "0.3000",
        "yes_ask_dollars": "0.3200",
        "last_price_dollars": "0.3100",
    },
]

EPL_TOTAL_MARKETS = [
    {
        "ticker": "KXEPLTOTAL-26NOV23BREEVE-3",
        "event_ticker": "KXEPLTOTAL-26NOV23BREEVE",
        "title": "Will over 2.5 goals be scored?",
        "yes_bid_dollars": "0.5200",
        "yes_ask_dollars": "0.5400",
        "last_price_dollars": "0.5300",
    },
]


class FakeKalshiClient:
    """Client palsu: merutekan /events dan /markets ke fixture."""

    def __init__(self, events, markets, status=200):
        self.events = events
        self.markets = markets
        self.status = status
        self.urls = []

    def get(self, url, use_cache=True):
        self.urls.append(url)
        if "/events?" in url:
            body = json.dumps({"events": self.events})
        elif "/markets?" in url:
            body = json.dumps({"markets": self.markets})
        else:
            body = json.dumps({})
        return {
            "url": url,
            "status": self.status,
            "headers": {},
            "rate_limit_headers": {},
            "body": body,
            "error": None,
            "from_cache": False,
        }


class TestMoneyline(unittest.TestCase):
    def test_nba_moneyline(self):
        client = FakeKalshiClient(NBA_GAME_EVENTS, NBA_GAME_MARKETS)
        result = kalshi.fetch_moneyline_markets("nba", client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.source, "Kalshi API")
        self.assertEqual(result.tier, 2)
        # Pasar tanpa ask ditolak -> 2 pasar.
        self.assertEqual(len(result.data), 2)
        self.assertEqual(result.extra["skipped_no_bid_ask"], 1)
        charlotte = result.data[0]
        self.assertEqual(charlotte["market_ticker"], "KXNBAGAME-26NOV20CHAATL-CHA")
        self.assertEqual(charlotte["event_ticker"], "KXNBAGAME-26NOV20CHAATL")
        self.assertEqual(charlotte["title"], "Charlotte wins")
        self.assertEqual(charlotte["league"], "nba")
        self.assertEqual(charlotte["market_type"], "moneyline")
        self.assertIsNone(charlotte["line"])
        # NBA: "Charlotte vs Atlanta" -> Charlotte tandang, Atlanta kandang.
        self.assertEqual(charlotte["home_team"], "Atlanta")
        self.assertEqual(charlotte["away_team"], "Charlotte")
        self.assertEqual(charlotte["side"], "away")
        self.assertEqual(result.data[1]["side"], "home")
        self.assertEqual(charlotte["yes_bid_dollars"], "0.1200")
        self.assertEqual(charlotte["yes_ask_dollars"], "0.1300")

    def test_expiration_time_diteruskan(self):
        # Passthrough mentah untuk disambiguasi rematch di slate.
        markets = [
            {**NBA_GAME_MARKETS[0], "expiration_time": "2026-11-21T06:00:00Z"},
            {**NBA_GAME_MARKETS[1]},
        ]
        client = FakeKalshiClient(NBA_GAME_EVENTS, markets)
        result = kalshi.fetch_moneyline_markets("nba", client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data[0]["expiration_time"], "2026-11-21T06:00:00Z")
        self.assertIsNone(result.data[1]["expiration_time"])

    def test_epl_moneyline_dan_seri(self):
        client = FakeKalshiClient(EPL_GAME_EVENTS, EPL_GAME_MARKETS)
        result = kalshi.fetch_moneyline_markets("epl", client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(result.data), 3)
        chelsea = result.data[0]
        # Bola: "Chelsea vs Leeds" -> Chelsea kandang.
        self.assertEqual(chelsea["home_team"], "Chelsea")
        self.assertEqual(chelsea["side"], "home")
        tie = result.data[1]
        self.assertEqual(tie["side"], "draw")
        self.assertEqual(tie["title"], "Tie is the result")

    def test_series_benar_di_url(self):
        client = FakeKalshiClient(NBA_GAME_EVENTS, NBA_GAME_MARKETS)
        kalshi.fetch_moneyline_markets("nba", client=client)
        self.assertTrue(
            any("series_ticker=KXNBAGAME" in u for u in client.urls),
            client.urls,
        )

    def test_liga_tidak_dikenal(self):
        client = FakeKalshiClient([], [])
        result = kalshi.fetch_moneyline_markets("bundesliga", client=client)
        self.assertFalse(result.ok)
        self.assertEqual(client.urls, [])

    def test_http_error(self):
        client = FakeKalshiClient([], [], status=500)
        result = kalshi.fetch_moneyline_markets("nba", client=client)
        self.assertFalse(result.ok)


class TestSpreadTotal(unittest.TestCase):
    def test_nba_spread(self):
        client = FakeKalshiClient(NBA_SPREAD_EVENTS, NBA_SPREAD_MARKETS)
        result = kalshi.fetch_spread_markets("nba", client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(result.data), 2)
        utah = result.data[0]
        self.assertEqual(utah["market_type"], "spread")
        self.assertEqual(utah["line"], 7.5)
        # Utah tim kedua di judul NBA -> kandang.
        self.assertEqual(utah["side"], "home")
        self.assertEqual(utah["home_team"], "Utah")
        self.assertEqual(utah["away_team"], "Phoenix")
        # last_price 0.0000 diabaikan — bid/ask yang dipakai.
        self.assertEqual(utah["yes_bid_dollars"], "0.1800")

    def test_nba_total(self):
        client = FakeKalshiClient(NBA_TOTAL_EVENTS, NBA_TOTAL_MARKETS)
        result = kalshi.fetch_total_markets("nba", client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(result.data), 1)
        total = result.data[0]
        self.assertEqual(total["market_type"], "total")
        self.assertEqual(total["line"], 254.5)
        self.assertEqual(total["side"], "over")
        self.assertEqual(total["home_team"], "Atlanta")
        self.assertEqual(total["away_team"], "Charlotte")

    def test_epl_spread_dan_total(self):
        spread_events = [
            {
                "event_ticker": "KXEPLSPREAD-26NOV23BREEVE",
                "series_ticker": "KXEPLSPREAD",
                "title": "Brentford vs Everton: Spread",
            }
        ]
        client = FakeKalshiClient(spread_events, EPL_SPREAD_MARKETS)
        result = kalshi.fetch_spread_markets("epl", client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data[0]["line"], 1.5)
        # Bola: Everton tim kedua -> tandang.
        self.assertEqual(result.data[0]["side"], "away")
        total_events = [
            {
                "event_ticker": "KXEPLTOTAL-26NOV23BREEVE",
                "series_ticker": "KXEPLTOTAL",
                "title": "Brentford vs Everton: Total Goals",
            }
        ]
        client = FakeKalshiClient(total_events, EPL_TOTAL_MARKETS)
        result = kalshi.fetch_total_markets("epl", client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data[0]["line"], 2.5)
        self.assertEqual(result.data[0]["side"], "over")

    def test_laliga_spread_total_tidak_tersedia(self):
        client = FakeKalshiClient([], [])
        self.assertFalse(kalshi.fetch_spread_markets("laliga", client=client).ok)
        self.assertFalse(kalshi.fetch_total_markets("laliga", client=client).ok)
        self.assertEqual(client.urls, [])

    def test_bentuk_data_sama_moneyline(self):
        keys = {
            "market_ticker",
            "event_ticker",
            "title",
            "league",
            "market_type",
            "home_team",
            "away_team",
            "line",
            "side",
            "yes_bid_dollars",
            "yes_ask_dollars",
            "expiration_time",
        }
        ml = kalshi.fetch_moneyline_markets(
            "nba", client=FakeKalshiClient(NBA_GAME_EVENTS, NBA_GAME_MARKETS)
        )
        sp = kalshi.fetch_spread_markets(
            "nba", client=FakeKalshiClient(NBA_SPREAD_EVENTS, NBA_SPREAD_MARKETS)
        )
        to = kalshi.fetch_total_markets(
            "nba", client=FakeKalshiClient(NBA_TOTAL_EVENTS, NBA_TOTAL_MARKETS)
        )
        for result in (ml, sp, to):
            for row in result.data:
                self.assertEqual(set(row.keys()), keys)


class TestPaginationCursor(unittest.TestCase):
    def test_markets_multi_halaman_digabung(self):
        market_a = dict(NBA_SPREAD_MARKETS[0])
        market_b = dict(NBA_SPREAD_MARKETS[1])

        class PagedClient:
            def __init__(self):
                self.urls = []

            def get(self, url, use_cache=True):
                self.urls.append(url)
                if "/events?" in url:
                    body = json.dumps({"events": NBA_SPREAD_EVENTS, "cursor": ""})
                elif "cursor=" in url:
                    body = json.dumps({"markets": [market_b], "cursor": ""})
                else:
                    body = json.dumps({"markets": [market_a], "cursor": "halaman-2"})
                return {
                    "url": url,
                    "status": 200,
                    "headers": {},
                    "rate_limit_headers": {},
                    "body": body,
                    "error": None,
                    "from_cache": False,
                }

        client = PagedClient()
        result = kalshi.fetch_spread_markets("nba", client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(result.data), 2)
        self.assertEqual(result.extra["market_pages"], 2)
        self.assertEqual(result.extra["markets_open"], 2)
        self.assertTrue(any("cursor=halaman-2" in u for u in client.urls))


class TestKalshiProbability(unittest.TestCase):
    def test_midpoint_bid_ask(self):
        market = {"yes_bid_dollars": "0.1200", "yes_ask_dollars": "0.1300"}
        self.assertAlmostEqual(kalshi.kalshi_probability(market), 0.125)

    def test_bukan_last_price(self):
        # last_price 0.0000 tidak boleh dipakai walau bid/ask ada.
        market = {
            "yes_bid_dollars": "0.0400",
            "yes_ask_dollars": "0.0700",
            "last_price_dollars": "0.0000",
        }
        self.assertAlmostEqual(kalshi.kalshi_probability(market), 0.055)

    def test_tidak_valid(self):
        for bad in (
            {},
            {"yes_bid_dollars": "0.12"},
            {"yes_bid_dollars": "x", "yes_ask_dollars": "0.13"},
            {"yes_bid_dollars": "1.20", "yes_ask_dollars": "0.13"},
            {"yes_bid_dollars": "-0.1", "yes_ask_dollars": "0.13"},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                kalshi.kalshi_probability(bad)


if __name__ == "__main__":
    unittest.main()
