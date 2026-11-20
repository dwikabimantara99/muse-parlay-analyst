"""Tes ingest/polymarket.py — orderbook CLOB + pencari token (mock).

TANPA network. Mencakup PERANGKAP TOKEN: pasar 2-outcome berbagi satu
pasangan token — token dipilih dari indeks judul di outcomes.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import polymarket

BOOK = {
    "bids": [
        {"price": "0.42", "size": "100"},
        {"price": "0.41", "size": "50"},
    ],
    "asks": [
        {"price": "0.43", "size": "80"},
        {"price": "0.44", "size": "10"},
    ],
}

# Respons public-search Gamma untuk event "Wizards vs. Bulls"
# (bentuk asli: outcomes/clobTokenIds berupa string JSON).
GAMMA_SEARCH = {
    "events": [
        {
            "id": "1323813",
            "title": "Wizards vs. Bulls",
            "markets": [
                {
                    "question": "Wizards vs. Bulls",
                    "outcomes": '["Wizards", "Bulls"]',
                    "clobTokenIds": '["token-wizards", "token-bulls"]',
                },
                {
                    "question": "Spread: Bulls (-2.5)",
                    "outcomes": '["Bulls", "Wizards"]',
                    "clobTokenIds": '["token-bulls-spread", "token-wiz-spread"]',
                },
                {
                    "question": "Wizards vs. Bulls: O/U 243.5",
                    "outcomes": '["Over", "Under"]',
                    "clobTokenIds": '["token-over", "token-under"]',
                },
            ],
        }
    ],
    "pagination": {"hasMore": False, "totalResults": 1},
}


class FakeHttpClient:
    """Client palsu: merutekan URL ke respons canned."""

    def __init__(self, routes):
        self.routes = routes
        self.urls = []

    def get(self, url, use_cache=True):
        self.urls.append(url)
        for substring, payload in self.routes.items():
            if substring in url:
                status, body = payload
                return {
                    "url": url,
                    "status": status,
                    "headers": {},
                    "rate_limit_headers": {},
                    "body": body,
                    "error": None,
                    "from_cache": False,
                }
        raise AssertionError(f"URL tak terduga: {url}")


class NoNetworkClient:
    """Client yang melempar bila dipanggil — membuktikan jalur tanpa network."""

    def get(self, url, use_cache=True):
        raise AssertionError(f"network tidak boleh dipanggil: {url}")


class TestFetchOrderbook(unittest.TestCase):
    def test_book_mid_dan_spread(self):
        client = FakeHttpClient({"/book?": (200, json.dumps(BOOK))})
        result = polymarket.fetch_orderbook("token-1", client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.source, "Polymarket CLOB")
        self.assertEqual(result.data["bid_cents"], 42.0)
        self.assertEqual(result.data["ask_cents"], 43.0)
        self.assertEqual(result.data["mid_cents"], 42.5)
        self.assertEqual(result.data["spread_cents"], 1.0)
        self.assertEqual(result.extra["source"], "book")

    def test_book_kosong_fallback_midpoint(self):
        client = FakeHttpClient(
            {
                "/book?": (200, json.dumps({"bids": [], "asks": []})),
                "/midpoint?": (200, json.dumps({"mid": "0.425"})),
            }
        )
        result = polymarket.fetch_orderbook("token-1", client=client)
        self.assertTrue(result.ok, result.error)
        self.assertIsNone(result.data["bid_cents"])
        self.assertIsNone(result.data["ask_cents"])
        self.assertEqual(result.data["mid_cents"], 42.5)
        self.assertIsNone(result.data["spread_cents"])
        self.assertEqual(result.extra["source"], "midpoint")

    def test_keduanya_gagal(self):
        client = FakeHttpClient(
            {
                "/book?": (200, json.dumps({"bids": [], "asks": []})),
                "/midpoint?": (500, "error"),
            }
        )
        result = polymarket.fetch_orderbook("token-1", client=client)
        self.assertFalse(result.ok)

    def test_token_id_kosong(self):
        result = polymarket.fetch_orderbook("", client=NoNetworkClient())
        self.assertFalse(result.ok)


class TestYesTokenId(unittest.TestCase):
    def test_pasar_dua_outcome_berbagi_token(self):
        # PERANGKAP: Bulls (tim kedua) memakai token [1], bukan [0].
        market = {
            "title": "Bulls",
            "team": {"name": "Bulls"},
            "outcomes": ["Wizards", "Bulls"],
            "clobTokenIds": ["token-wizards", "token-bulls"],
        }
        token, index, how = polymarket.yes_token_id(market)
        self.assertEqual(token, "token-bulls")
        self.assertEqual(index, 1)
        self.assertIn("indeks", how)
        market["title"] = "Wizards"
        market["team"] = {"name": "Wizards"}
        token, index, _ = polymarket.yes_token_id(market)
        self.assertEqual(token, "token-wizards")
        self.assertEqual(index, 0)

    def test_pasar_biner_mandiri_fallback_nol(self):
        market = {
            "title": "Chelsea FC",
            "team": {"name": "Chelsea FC"},
            "outcomes": ["Yes", "No"],
            "clobTokenIds": ["token-yes", "token-no"],
        }
        token, index, how = polymarket.yes_token_id(market)
        self.assertEqual(token, "token-yes")
        self.assertEqual(index, 0)
        self.assertIn("fallback", how)

    def test_tanpa_token(self):
        token, index, _ = polymarket.yes_token_id(
            {"title": "X", "outcomes": ["X", "Y"], "clobTokenIds": []}
        )
        self.assertIsNone(token)
        self.assertIsNone(index)

    def test_outcomes_string_json_gamma(self):
        market = {
            "title": "Bulls",
            "outcomes": '["Wizards", "Bulls"]',
            "clobTokenIds": '["token-wizards", "token-bulls"]',
        }
        token, index, _ = polymarket.yes_token_id(market)
        self.assertEqual(token, "token-bulls")
        self.assertEqual(index, 1)


class TestFindToken(unittest.TestCase):
    def test_jalur_mentah_tanpa_network(self):
        market = {
            "title": "Bulls",
            "team": {"name": "Bulls"},
            "outcomes": ["Wizards", "Bulls"],
            "clobTokenIds": ["token-wizards", "token-bulls"],
        }
        self.assertEqual(
            polymarket.find_token_for_jup_market(market, client=NoNetworkClient()),
            "token-bulls",
        )

    def test_jalur_mentah_pasar_ternormalisasi(self):
        # Pasar bentuk slate (hasil _normalize_market: punya "outcome" +
        # passthrough clobTokenIds/outcomes, tanpa "title"/"team") harus
        # tetap memakai jalur tanpa-network — token dipilih dari indeks
        # outcome di outcomes.
        market = {
            "event_title": "Wizards vs. Bulls",
            "outcome": "Bulls",
            "market_type": "moneyline",
            "line": None,
            "outcomes": ["Wizards", "Bulls"],
            "clobTokenIds": ["token-wizards", "token-bulls"],
        }
        self.assertEqual(
            polymarket.find_token_for_jup_market(market, client=NoNetworkClient()),
            "token-bulls",
        )
        market["outcome"] = "Wizards"
        self.assertEqual(
            polymarket.find_token_for_jup_market(market, client=NoNetworkClient()),
            "token-wizards",
        )

    def test_jalur_gamma_moneyline(self):
        client = FakeHttpClient({"/public-search": (200, json.dumps(GAMMA_SEARCH))})
        market = {
            "event_title": "Wizards vs. Bulls",
            "outcome": "Bulls",
            "market_type": "moneyline",
            "line": None,
        }
        self.assertEqual(
            polymarket.find_token_for_jup_market(market, client=client),
            "token-bulls",
        )
        market["outcome"] = "Wizards"
        self.assertEqual(
            polymarket.find_token_for_jup_market(market, client=client),
            "token-wizards",
        )

    def test_jalur_gamma_spread_dan_total(self):
        client = FakeHttpClient({"/public-search": (200, json.dumps(GAMMA_SEARCH))})
        spread = {
            "event_title": "Wizards vs. Bulls",
            "outcome": "Bulls",
            "market_type": "spreads",
            "line": -2.5,
        }
        self.assertEqual(
            polymarket.find_token_for_jup_market(spread, client=client),
            "token-bulls-spread",
        )
        total = {
            "event_title": "Wizards vs. Bulls",
            "outcome": "Over",
            "market_type": "totals",
            "line": 243.5,
        }
        self.assertEqual(
            polymarket.find_token_for_jup_market(total, client=client),
            "token-over",
        )
        total["outcome"] = "Under"
        self.assertEqual(
            polymarket.find_token_for_jup_market(total, client=client),
            "token-under",
        )
        # Garis tidak ada -> None (bukan tebak garis terdekat).
        total["line"] = 999.5
        self.assertIsNone(polymarket.find_token_for_jup_market(total, client=client))

    def test_gamma_ambigu_fail_closed(self):
        ambiguous = {
            "events": [
                {"title": "Wizards vs. Bulls", "markets": []},
                {"title": "Wizards vs. Bulls", "markets": []},
            ]
        }
        client = FakeHttpClient({"/public-search": (200, json.dumps(ambiguous))})
        market = {
            "event_title": "Wizards vs. Bulls",
            "outcome": "Bulls",
            "market_type": "moneyline",
            "line": None,
        }
        self.assertIsNone(polymarket.find_token_for_jup_market(market, client=client))

    def test_gamma_gagal_network(self):
        client = FakeHttpClient({"/public-search": (500, "error")})
        market = {
            "event_title": "Wizards vs. Bulls",
            "outcome": "Bulls",
            "market_type": "moneyline",
            "line": None,
        }
        self.assertIsNone(polymarket.find_token_for_jup_market(market, client=client))

    def test_tanpa_event_title(self):
        self.assertIsNone(
            polymarket.find_token_for_jup_market(
                {"outcome": "Bulls"}, client=NoNetworkClient()
            )
        )


class TestComputeJupMarkup(unittest.TestCase):
    def test_markup(self):
        self.assertAlmostEqual(polymarket.compute_jup_markup(43.0, 42.5), 0.5)
        self.assertAlmostEqual(polymarket.compute_jup_markup(25.0, 25.5), -0.5)
        self.assertAlmostEqual(polymarket.compute_jup_markup(50.0, 50.0), 0.0)


if __name__ == "__main__":
    unittest.main()
