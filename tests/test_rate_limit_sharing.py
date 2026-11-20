"""Tes jeda sopan: satu RateLimiter dibagi semua pemanggilan per modul.

Regresi: _default_client() tiap modul membuat RateLimiter BARU per
panggilan, sehingga tidak ada jeda ANTAR pemanggilan — slate memanggil
fetcher berkali-kali (Kalshi: 3 series; Polymarket: 1x per pasar) dan
API membalas 429 (teramati: Kalshi total EPL 429 saat demo 2b).

Tes ini tanpa network: membuktikan client default memakai SATU objek
limiter yang sama (identitas), bukan dua limiter berbeda.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import (
    bbref,
    espn,
    kalshi,
    odds_api,
    polymarket,
    premier_league,
    rotowire,
    stats_nba,
)
from ingest.common import RateLimiter


class TestDefaultClientBerbagiLimiter(unittest.TestCase):
    def test_limiter_sama_dua_panggilan(self):
        for module in (
            espn,
            stats_nba,
            bbref,
            rotowire,
            premier_league,
        ):
            with self.subTest(module=module.__name__):
                first = module._default_client()
                second = module._default_client()
                self.assertIs(first.rate_limiter, second.rate_limiter)
                self.assertIs(first.rate_limiter, module._LIMITER)
                self.assertIsInstance(module._LIMITER, RateLimiter)


class TestKalshiBerbagiLimiter(unittest.TestCase):
    def test_fetch_markets_memakai_limiter_modul(self):
        seen = {}

        class CapturingClient:
            def __init__(self, rate_limiter, cache=None):
                seen["limiter"] = rate_limiter

            def get(self, url, use_cache=True):
                if "/events?" in url:
                    body = json.dumps({"events": []})
                else:
                    body = json.dumps({"markets": []})
                return {"status": 200, "body": body, "error": None}

        with mock.patch.object(kalshi, "HttpClient", CapturingClient):
            result = kalshi.fetch_moneyline_markets("nba")
        self.assertTrue(result.ok, result.error)
        self.assertIs(seen["limiter"], kalshi._LIMITER)


class TestPolymarketBerbagiLimiter(unittest.TestCase):
    def test_fetch_orderbook_memakai_limiter_modul(self):
        seen = {}

        class CapturingClient:
            def __init__(self, rate_limiter, cache=None):
                seen["limiter"] = rate_limiter

            def get(self, url, use_cache=True):
                return {
                    "status": 200,
                    "body": json.dumps(
                        {"bids": [{"price": "0.60"}], "asks": [{"price": "0.62"}]}
                    ),
                    "error": None,
                }

        with mock.patch.object(polymarket, "HttpClient", CapturingClient):
            result = polymarket.fetch_orderbook("token-1")
        self.assertTrue(result.ok, result.error)
        self.assertIs(seen["limiter"], polymarket._LIMITER)


class TestOddsApiBerbagiLimiter(unittest.TestCase):
    def test_fetch_odds_memakai_limiter_modul(self):
        seen = {}

        class CapturingClient:
            def __init__(self, rate_limiter, cache=None):
                seen["limiter"] = rate_limiter

            def get(self, url, use_cache=True):
                return {"status": 200, "headers": {}, "body": "[]", "error": None}

        # Cache dimatikan (mock): bila cache live masih hangat, client
        # tidak pernah dibuat dan limiter tidak tertangkap.
        empty_cache = mock.Mock()
        empty_cache.get.return_value = None
        with (
            mock.patch.object(odds_api, "HttpClient", CapturingClient),
            mock.patch.object(odds_api, "DiskCache", return_value=empty_cache),
        ):
            result = odds_api.fetch_odds("basketball_nba", api_key="kunci-tes")
        self.assertTrue(result.ok, result.error)
        self.assertIs(seen["limiter"], odds_api._LIMITER)


if __name__ == "__main__":
    unittest.main()
