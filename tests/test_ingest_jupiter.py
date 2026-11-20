"""Tes ingest/jupiter.py — fetch slate sports + paginasi (mock).

TANPA network dan TANPA API key: semua tes memakai client palsu.
Fixture meniru payload asli (probes/out/cache, 100 event / 5.720 pasar).
"""

import http.client
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import jupiter
from ingest.common import JupiterClient


def _market(market_id, title, mtype, line, buy_yes, buy_no=0, provider="polymarket"):
    """Satu pasar mentah jup.ag (bentuk payload asli)."""
    return {
        "marketId": market_id,
        "title": title,
        "sportsMarketType": mtype,
        "sportsLine": line,
        "provider": provider,
        "pricing": {
            "buyYesPriceUsd": buy_yes,
            "sellYesPriceUsd": (
                buy_yes - 10000 if isinstance(buy_yes, (int, float)) and buy_yes else 0
            ),
            "buyNoPriceUsd": buy_no,
            "sellNoPriceUsd": 0,
        },
    }


def _event(event_id, subcategory, title, league, markets, begin_at="1795222800"):
    """Satu event mentah jup.ag (bentuk payload asli)."""
    return {
        "eventId": event_id,
        "category": "sports",
        "subcategory": subcategory,
        "beginAt": begin_at,
        "metadata": {"title": title, "league": league},
        "markets": markets,
    }


NBA_EVENT = _event(
    "POLY-1323813",
    "nba",
    "Wizards vs. Bulls",
    "NBA 2026",
    [
        _market("POLY-6742003-0", "Wizards", "moneyline", None, 430000),
        _market("POLY-6742003-1", "Bulls", "moneyline", None, 580000),
    ],
)

EPL_EVENT = _event(
    "POLY-1323814",
    "epl",
    "Chelsea FC vs. Leeds United FC",
    "Premier League 2025",
    [
        _market("M1", "Chelsea FC", "moneyline", None, 580000, buy_no=440000),
        _market("M2", "Draw", "moneyline", None, 250000),
        _market("M3", "Over", "totals", "2.5", 940000),
        _market("M4", "Chelsea FC", "spreads", "-1.5", 620000),
    ],
)

FUTURES_EVENT = _event("POLY-1196500", "nba", "NBA: 2027 Champion", "NBA 2026", [])

NFL_EVENT = _event(
    "POLY-999",
    "nfl",
    "Chiefs vs. Bills",
    "NFL 2026",
    [_market("M9", "Chiefs", "moneyline", None, 510000)],
)


def _page_response(events, has_next, mode="keyed", from_cache=False, status=200):
    """Dict respons JupiterClient untuk satu halaman /events."""
    start = 0
    return {
        "status": status,
        "mode": mode,
        "from_cache": from_cache,
        "error": None,
        "body": json.dumps(
            {
                "data": events,
                "pagination": {
                    "start": start,
                    "end": len(events),
                    "hasNext": has_next,
                },
            }
        ),
    }


class FakeJupiterClient:
    """Client palsu: mengembalikan halaman-halaman canned berurutan."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        if not self.pages:
            raise AssertionError("client palsu kehabisan halaman")
        return self.pages.pop(0)


class TestFetchSportsMarkets(unittest.TestCase):
    def test_normalisasi_nba_dan_epl(self):
        client = FakeJupiterClient(
            [_page_response([NBA_EVENT, EPL_EVENT], has_next=False)]
        )
        result = jupiter.fetch_sports_markets(client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.source, "Jupiter Prediction API")
        self.assertEqual(result.tier, 1)
        self.assertEqual(len(result.data), 6)
        wizards = result.data[0]
        self.assertEqual(wizards["event_id"], "POLY-1323813")
        self.assertEqual(wizards["event_title"], "Wizards vs. Bulls")
        self.assertEqual(wizards["market_id"], "POLY-6742003-0")
        self.assertEqual(wizards["market_type"], "moneyline")
        self.assertIsNone(wizards["line"])
        self.assertEqual(wizards["provider"], "polymarket")
        self.assertEqual(wizards["outcome"], "Wizards")
        # 430000 micro-USD = 43.0 ¢; sisi No 0 = tidak ada kuotasi.
        self.assertEqual(wizards["yes_price_cents"], 43.0)
        self.assertIsNone(wizards["no_price_cents"])
        # NBA: "Wizards vs. Bulls" -> Wizards tandang, Bulls kandang.
        self.assertEqual(wizards["home_team"], "Bulls")
        self.assertEqual(wizards["away_team"], "Wizards")
        self.assertEqual(wizards["sport"], "nba")
        self.assertEqual(wizards["league"], "NBA 2026")

    def test_kandang_tandang_bola_terbalik_dari_nba(self):
        client = FakeJupiterClient([_page_response([EPL_EVENT], has_next=False)])
        result = jupiter.fetch_sports_markets(client=client)
        chelsea = result.data[0]
        # Bola: "Chelsea vs. Leeds" -> Chelsea kandang, Leeds tandang.
        self.assertEqual(chelsea["home_team"], "Chelsea FC")
        self.assertEqual(chelsea["away_team"], "Leeds United FC")
        self.assertEqual(chelsea["sport"], "football")
        self.assertEqual(chelsea["no_price_cents"], 44.0)
        totals = result.data[2]
        self.assertEqual(totals["line"], 2.5)
        self.assertEqual(totals["yes_price_cents"], 94.0)
        spreads = result.data[3]
        self.assertEqual(spreads["line"], -1.5)

    def test_olahraga_lain_tanpa_kandang_tandang(self):
        client = FakeJupiterClient([_page_response([NFL_EVENT], has_next=False)])
        result = jupiter.fetch_sports_markets(client=client)
        self.assertEqual(result.data[0]["sport"], "other")
        self.assertIsNone(result.data[0]["home_team"])
        self.assertIsNone(result.data[0]["away_team"])

    def test_token_polymarket_diteruskan(self):
        # Passthrough clobTokenIds/outcomes agar find_token_for_jup_market
        # memakai jalur tanpa-network (koordinator: tanpa ini, setiap
        # pasar memicu 1 pencarian Gamma saat menghitung jup_markup).
        market = _market("M-tok", "Bulls", "moneyline", None, 580000)
        market["outcomes"] = ["Wizards", "Bulls"]
        market["clobTokenIds"] = ["token-wizards", "token-bulls"]
        client = FakeJupiterClient(
            [
                _page_response(
                    [_event("E-tok", "nba", "Wizards vs. Bulls", "NBA 2026", [market])],
                    has_next=False,
                )
            ]
        )
        result = jupiter.fetch_sports_markets(client=client)
        self.assertEqual(
            result.data[0]["clobTokenIds"], ["token-wizards", "token-bulls"]
        )
        self.assertEqual(result.data[0]["outcomes"], ["Wizards", "Bulls"])

    def test_start_time_dari_begin_at(self):
        # beginAt 1795222800 = 2026-11-21T01:00:00Z (default fixture _event).
        client = FakeJupiterClient([_page_response([NBA_EVENT], has_next=False)])
        result = jupiter.fetch_sports_markets(client=client)
        self.assertEqual(result.data[0]["start_time"], "2026-11-21T01:00:00+00:00")

    def test_start_time_tidak_valid_jadi_none(self):
        event = _event("E-x", "nba", "Wizards vs. Bulls", "NBA 2026", [])
        event["beginAt"] = "bukan angka"
        market = _market("M-x", "Wizards", "moneyline", None, 430000)
        event["markets"] = [market]
        client = FakeJupiterClient([_page_response([event], has_next=False)])
        result = jupiter.fetch_sports_markets(client=client)
        self.assertIsNone(result.data[0]["start_time"])

    def test_spread_garis_dibalik_untuk_sisi_cover(self):
        # Tiap garis punya DUA pasar (satu per tim sebagai favorit);
        # sportsLine adalah garis untuk tim outcomes[0] — pasar tim
        # outcomes[1] adalah sisi cover dan garisnya dibalik (bug demo
        # 2b: "Arsenal +2.5" 99¢ tercatat sebagai -2.5 dan dibandingkan
        # dengan pembanding -2.5).
        markets = [
            {
                **_market("S1", "Arsenal FC", "spreads", "-2.5", 190000),
                "outcomes": ["Arsenal FC", "Newcastle United FC"],
            },
            {
                **_market("S2", "Newcastle United FC", "spreads", "-2.5", 830000),
                "outcomes": ["Arsenal FC", "Newcastle United FC"],
            },
            {
                **_market("S3", "Newcastle United FC", "spreads", "-2.5", 14000),
                "outcomes": ["Newcastle United FC", "Arsenal FC"],
            },
            {
                **_market("S4", "Arsenal FC", "spreads", "-2.5", 990000),
                "outcomes": ["Newcastle United FC", "Arsenal FC"],
            },
        ]
        event = _event(
            "E-sp",
            "epl",
            "Newcastle United FC vs. Arsenal FC",
            "Premier League 2025",
            markets,
        )
        client = FakeJupiterClient([_page_response([event], has_next=False)])
        result = jupiter.fetch_sports_markets(client=client)
        lines = {m["market_id"]: m["line"] for m in result.data}
        self.assertEqual(lines, {"S1": -2.5, "S2": 2.5, "S3": -2.5, "S4": 2.5})

    def test_spread_judul_tidak_di_outcomes_garis_apa_adanya(self):
        market = {
            **_market("S9", "Chelsea FC", "spreads", "-1.5", 620000),
            "outcomes": ["Yes", "No"],
        }
        event = _event(
            "E-sp9",
            "epl",
            "Chelsea FC vs. Leeds United FC",
            "Premier League 2025",
            [market],
        )
        client = FakeJupiterClient([_page_response([event], has_next=False)])
        result = jupiter.fetch_sports_markets(client=client)
        self.assertEqual(result.data[0]["line"], -1.5)

    def test_event_tanpa_vs_tanpa_tim(self):
        client = FakeJupiterClient([_page_response([FUTURES_EVENT], has_next=False)])
        result = jupiter.fetch_sports_markets(client=client)
        self.assertTrue(result.ok)
        self.assertEqual(result.data, [])

    def test_harga_tidak_valid_jadi_none(self):
        bad = _event(
            "POLY-BAD",
            "nba",
            "A vs. B",
            "NBA 2026",
            [
                _market("X1", "A", "moneyline", None, 0),
                _market("X2", "B", "moneyline", None, 1000001),
                _market("X3", "C", "moneyline", None, "430000"),
            ],
        )
        client = FakeJupiterClient([_page_response([bad], has_next=False)])
        result = jupiter.fetch_sports_markets(client=client)
        self.assertTrue(all(m["yes_price_cents"] is None for m in result.data))

    def test_http_error(self):
        client = FakeJupiterClient([_page_response([], has_next=False, status=500)])
        client.pages[0]["body"] = "error"
        client.pages[0]["error"] = "Internal Server Error"
        result = jupiter.fetch_sports_markets(client=client)
        self.assertFalse(result.ok)
        self.assertIn("500", result.error)

    def test_json_tidak_valid(self):
        client = FakeJupiterClient([_page_response([], has_next=False)])
        client.pages[0]["body"] = "bukan json {"
        result = jupiter.fetch_sports_markets(client=client)
        self.assertFalse(result.ok)

    def test_limit_tidak_valid(self):
        result = jupiter.fetch_sports_markets(limit=0, client=FakeJupiterClient([]))
        self.assertFalse(result.ok)

    def test_mode_keyless_dicatat(self):
        client = FakeJupiterClient(
            [_page_response([NBA_EVENT], has_next=False, mode="keyless")]
        )
        result = jupiter.fetch_sports_markets(client=client)
        self.assertTrue(result.ok)
        self.assertEqual(result.extra["mode"], "keyless")


class TestPagination(unittest.TestCase):
    def test_multi_halaman_digabung(self):
        client = FakeJupiterClient(
            [
                _page_response([NBA_EVENT], has_next=True),
                _page_response([EPL_EVENT], has_next=False),
            ]
        )
        result = jupiter.fetch_sports_events(client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(result.data), 2)
        self.assertEqual(result.extra["pages_fetched"], 2)
        self.assertEqual(result.extra["events_scanned"], 2)
        self.assertTrue(result.extra["scan_complete"])
        self.assertEqual(result.extra["stopped_reason"], "semua_halaman")
        # Parameter window start/end/limit benar per halaman.
        self.assertEqual(client.calls[0][0], "/events")
        self.assertEqual(
            client.calls[0][1],
            {"category": "sports", "limit": "100", "start": "0", "end": "100"},
        )
        self.assertEqual(
            client.calls[1][1],
            {"category": "sports", "limit": "100", "start": "100", "end": "200"},
        )

    def test_cap_menghentikan_pindaian(self):
        page1 = [{**NBA_EVENT, "eventId": f"POLY-NBA-{i}"} for i in range(100)]
        page2 = [{**EPL_EVENT, "eventId": f"POLY-EPL-{i}"} for i in range(50)]
        client = FakeJupiterClient(
            [
                _page_response(page1, has_next=True),
                _page_response(page2, has_next=True),
            ]
        )
        result = jupiter.fetch_sports_events(limit=150, client=client)
        self.assertTrue(result.ok)
        self.assertEqual(result.extra["pages_fetched"], 2)
        self.assertFalse(result.extra["scan_complete"])
        self.assertEqual(result.extra["stopped_reason"], "cap_tercapai")
        # Halaman kedua hanya meminta 50 event (150 - 100).
        self.assertEqual(
            client.calls[1][1],
            {"category": "sports", "limit": "50", "start": "100", "end": "150"},
        )

    def test_deduplikasi_event_id(self):
        client = FakeJupiterClient(
            [
                _page_response([NBA_EVENT], has_next=True),
                _page_response([NBA_EVENT, EPL_EVENT], has_next=False),
            ]
        )
        result = jupiter.fetch_sports_events(client=client)
        self.assertEqual(len(result.data), 2)
        self.assertEqual(result.extra["events_scanned"], 2)

    def test_halaman_kedua_gagal_http(self):
        client = FakeJupiterClient(
            [
                _page_response([NBA_EVENT], has_next=True),
                _page_response([], has_next=False, status=500),
            ]
        )
        with mock.patch("ingest.jupiter.time.sleep"):
            result = jupiter.fetch_sports_events(client=client)
        self.assertFalse(result.ok)
        self.assertIn("halaman 2", result.error)
        self.assertEqual(result.extra["events_scanned"], 1)
        self.assertFalse(result.extra["scan_complete"])


class TestRetryTransport(unittest.TestCase):
    def test_incomplete_read_lalu_berhasil(self):
        calls = []

        class FlakyClient:
            def get(self, path, params=None):
                calls.append(params)
                if len(calls) == 1:
                    raise http.client.IncompleteRead(b"parsial", 100)
                return _page_response([NBA_EVENT], has_next=False)

        with mock.patch("ingest.jupiter.time.sleep") as sleep_mock:
            result = jupiter.fetch_sports_events(client=FlakyClient())
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(calls), 2)
        sleep_mock.assert_called_once_with(1.0)

    def test_status_none_lalu_berhasil(self):
        responses = [
            {"status": None, "error": "RemoteDisconnected", "from_cache": False},
            _page_response([NBA_EVENT], has_next=False),
        ]

        class FlakyClient:
            def get(self, path, params=None):
                return responses.pop(0)

        with mock.patch("ingest.jupiter.time.sleep"):
            result = jupiter.fetch_sports_events(client=FlakyClient())
        self.assertTrue(result.ok, result.error)

    def test_gagal_total_setelah_8_percobaan(self):
        attempts = []

        class DeadClient:
            def get(self, path, params=None):
                attempts.append(1)
                raise http.client.RemoteDisconnected("putus")

        with mock.patch("ingest.jupiter.time.sleep"):
            result = jupiter.fetch_sports_events(client=DeadClient())
        self.assertFalse(result.ok)
        self.assertEqual(len(attempts), jupiter.MAX_ATTEMPTS_PER_PAGE)
        self.assertIn("8x", result.error)


class TestAttemptCounting(unittest.TestCase):
    def test_tanpa_retry_attempts_sama_dengan_halaman(self):
        client = FakeJupiterClient(
            [
                _page_response([NBA_EVENT], has_next=True),
                _page_response([EPL_EVENT], has_next=False),
            ]
        )
        result = jupiter.fetch_sports_events(client=client)
        self.assertTrue(result.ok)
        self.assertEqual(result.extra["total_attempts"], 2)
        self.assertEqual(result.extra["retried_pages"], 0)

    def test_satu_retry_dicatat(self):
        calls = []

        class FlakyClient:
            def get(self, path, params=None):
                calls.append(params)
                if len(calls) == 1:
                    raise http.client.IncompleteRead(b"parsial", 100)
                return _page_response([NBA_EVENT], has_next=False)

        with mock.patch("ingest.jupiter.time.sleep"):
            result = jupiter.fetch_sports_events(client=FlakyClient())
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.extra["total_attempts"], 2)
        self.assertEqual(result.extra["retried_pages"], 1)


class TestKeylessFallback(unittest.TestCase):
    def test_key_ditolak_lalu_keyless_berhasil(self):
        page = _page_response([NBA_EVENT], has_next=False)

        def fake_request(url, keyed, params):
            if keyed:
                return {
                    "status": 401,
                    "body": "unauthorized",
                    "error": None,
                    "from_cache": False,
                    "headers": {},
                    "rate_limit_headers": {},
                }
            return {**page, "headers": {}, "rate_limit_headers": {}}

        client = JupiterClient(api_key="key-palsu", cache=None)
        with mock.patch.object(JupiterClient, "_request", side_effect=fake_request):
            result = jupiter.fetch_sports_markets(client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.extra["mode"], "keyless")
        self.assertTrue(client.fallback_used)


if __name__ == "__main__":
    unittest.main()
