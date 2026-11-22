"""Tes tangga Polymarket (ingest/polymarket.py) — HARGA VENUE, bukan pembanding.

TANPA network. Fixture: cuplikan event Gamma DET-ATL 2026-11-22
(tests/fixtures/polymarket_ladder/det_atl_sample.json) — 6 pasar verbatim
dari out/poly_event_det_atl.json (moneyline, 2 spread, 3 total).
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from ingest import polymarket

FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "polymarket_ladder"
    / "det_atl_sample.json"
)

# cfg eksplisit (koordinator menambahkan kunci ini ke playstyle.yaml).
CFG = {
    "polymarket_ladder": {"min_volume_usd": 100.0},
    "fees": {"jup_typical_markup_cents": 0.5},
}


def load_fixture() -> dict:
    """Baca fixture event DET-ATL (salinan baru tiap panggilan)."""
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


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


def _total(entries, line, side):
    """Cari satu entri total berdasarkan garis + sisi."""
    for entry in entries:
        if entry["line"] == line and entry["side"] == side:
            return entry
    raise AssertionError(f"entri total tidak ditemukan: {line} {side}")


class TestNbaSlug(unittest.TestCase):
    def test_det_atl_terverifikasi(self):
        self.assertEqual(
            polymarket.nba_slug("DET", "ATL", "2026-11-22"),
            "nba-det-atl-2026-11-22",
        )

    def test_huruf_kecil_dan_spasi(self):
        self.assertEqual(
            polymarket.nba_slug(" det ", " atl ", "2026-11-22"),
            "nba-det-atl-2026-11-22",
        )

    def test_urutan_away_home(self):
        # Dibalik -> slug berbeda (ATL di DET, bukan DET di ATL).
        self.assertEqual(
            polymarket.nba_slug("ATL", "DET", "2026-11-22"),
            "nba-atl-det-2026-11-22",
        )

    def test_input_tidak_valid(self):
        with self.assertRaises(ValueError):
            polymarket.nba_slug("", "ATL", "2026-11-22")
        with self.assertRaises(ValueError):
            polymarket.nba_slug("DET", "ATL", "22-11-2026")
        with self.assertRaises(ValueError):
            polymarket.nba_slug("DET", "ATL", "2026/11/22")


class TestResolveSlugFromJupEvent(unittest.TestCase):
    def test_slug_dari_metadata(self):
        jup_event = {
            "eventId": "POLY-1338695",
            "metadata": {
                "slug": "nba-det-atl-2026-11-22",
                "title": "Pistons vs. Hawks",
                "series": "polymarket",
            },
        }
        self.assertEqual(
            polymarket.resolve_slug_from_jup_event(jup_event),
            "nba-det-atl-2026-11-22",
        )

    def test_tanpa_metadata_atau_slug(self):
        self.assertIsNone(polymarket.resolve_slug_from_jup_event({}))
        self.assertIsNone(
            polymarket.resolve_slug_from_jup_event({"metadata": {"title": "X"}})
        )
        self.assertIsNone(polymarket.resolve_slug_from_jup_event({"metadata": {}}))
        self.assertIsNone(polymarket.resolve_slug_from_jup_event(None))

    def test_series_bukan_polymarket(self):
        jup_event = {"metadata": {"slug": "nba-det-atl-2026-11-22", "series": "kalshi"}}
        self.assertIsNone(polymarket.resolve_slug_from_jup_event(jup_event))


class TestFetchEventBySlug(unittest.TestCase):
    def test_sukses(self):
        event = load_fixture()
        client = FakeHttpClient({"/events/slug/": (200, json.dumps(event))})
        result = polymarket.fetch_event_by_slug("nba-det-atl-2026-11-22", client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["slug"], "nba-det-atl-2026-11-22")
        self.assertEqual(result.extra["n_markets"], 6)
        self.assertIn("/events/slug/nba-det-atl-2026-11-22", client.urls[0])

    def test_404(self):
        client = FakeHttpClient({"/events/slug/": (404, "not found")})
        result = polymarket.fetch_event_by_slug("nba-xxx-yyy-2026-11-22", client=client)
        self.assertFalse(result.ok)
        self.assertIn("404", result.error)

    def test_body_bukan_event(self):
        client = FakeHttpClient({"/events/slug/": (200, json.dumps({"foo": 1}))})
        result = polymarket.fetch_event_by_slug("nba-det-atl-2026-11-22", client=client)
        self.assertFalse(result.ok)

    def test_slug_kosong(self):
        client = FakeHttpClient({})
        result = polymarket.fetch_event_by_slug("", client=client)
        self.assertFalse(result.ok)
        self.assertEqual(client.urls, [])


class TestVenuePriceCents(unittest.TestCase):
    def test_markup_ditambah(self):
        self.assertAlmostEqual(polymarket.venue_price_cents(71.0, cfg=CFG), 71.5)
        self.assertAlmostEqual(polymarket.venue_price_cents(29.0, cfg=CFG), 29.5)

    def test_kunci_config_hilang(self):
        with self.assertRaises(config.ConfigError):
            polymarket.venue_price_cents(71.0, cfg={})


class TestParseEventLadders(unittest.TestCase):
    def test_struktur_dan_jumlah_entri(self):
        ladders = polymarket.parse_event_ladders(load_fixture(), cfg=CFG)
        self.assertEqual(ladders["slug"], "nba-det-atl-2026-11-22")
        self.assertEqual(ladders["title"], "Pistons vs. Hawks")
        # Moneyline: 2 entri (satu per tim). Spread: 2 pasar. Total:
        # 3 garis x 2 sisi = 6 entri.
        self.assertEqual(len(ladders["moneyline"]), 2)
        self.assertEqual(len(ladders["spreads"]), 2)
        self.assertEqual(len(ladders["totals"]), 6)
        self.assertEqual(ladders["warnings"], [])

    def test_total_likuid_225(self):
        ladders = polymarket.parse_event_ladders(load_fixture(), cfg=CFG)
        over = _total(ladders["totals"], 225.5, "over")
        under = _total(ladders["totals"], 225.5, "under")
        # Book Over 0.47/0.48 -> mid 47.5; Under = 100 - 47.5.
        self.assertEqual(over["price_cents"], 47.5)
        self.assertEqual(over["bid_cents"], 47.0)
        self.assertEqual(over["ask_cents"], 48.0)
        self.assertEqual(under["price_cents"], 52.5)
        self.assertEqual(under["bid_cents"], 52.0)
        self.assertEqual(under["ask_cents"], 53.0)
        self.assertEqual(over["price_source"], "book")
        self.assertEqual(under["price_source"], "book")
        self.assertAlmostEqual(over["volume_usd"], 41963.73, places=2)
        self.assertFalse(over["thin"])
        self.assertFalse(under["thin"])
        self.assertEqual(over["last_cents"], 49.0)
        self.assertEqual(under["last_cents"], 51.0)
        self.assertEqual(over["market_id"], "7240973")

    def test_under_komplemen_235(self):
        # U 235.5 = 71¢ dari bid/ask Over 0.28/0.30 (mid 29 -> 100-29).
        ladders = polymarket.parse_event_ladders(load_fixture(), cfg=CFG)
        under = _total(ladders["totals"], 235.5, "under")
        self.assertEqual(under["price_cents"], 71.0)
        self.assertEqual(under["bid_cents"], 70.0)
        self.assertEqual(under["ask_cents"], 72.0)
        self.assertEqual(under["price_source"], "book")

    def test_thin_flag(self):
        ladders = polymarket.parse_event_ladders(load_fixture(), cfg=CFG)
        # Volume $9,48 < $100 -> thin.
        self.assertTrue(_total(ladders["totals"], 235.5, "under")["thin"])
        # Volume $41.964 -> tidak thin.
        self.assertFalse(_total(ladders["totals"], 225.5, "under")["thin"])
        # Volume None -> thin.
        thin_none = _total(ladders["totals"], 241.5, "under")
        self.assertIsNone(thin_none["volume_usd"])
        self.assertTrue(thin_none["thin"])
        # ...tapi harganya tetap dari book (bid 0.17/ask 0.20 -> Under 81.5).
        self.assertEqual(thin_none["price_cents"], 81.5)
        self.assertEqual(thin_none["price_source"], "book")

    def test_last_price_none_tidak_dipakai(self):
        ladders = polymarket.parse_event_ladders(load_fixture(), cfg=CFG)
        under = _total(ladders["totals"], 235.5, "under")
        self.assertIsNone(under["last_cents"])
        # Harga utama tetap 71¢ (dari book), bukan None.
        self.assertEqual(under["price_cents"], 71.0)

    def test_jup_estimated_mid_plus_markup(self):
        ladders = polymarket.parse_event_ladders(load_fixture(), cfg=CFG)
        under = _total(ladders["totals"], 235.5, "under")
        self.assertEqual(under["jup_estimated_cents"], 71.5)
        over = _total(ladders["totals"], 225.5, "over")
        self.assertEqual(over["jup_estimated_cents"], 48.0)

    def test_spread_home_away(self):
        ladders = polymarket.parse_event_ladders(load_fixture(), cfg=CFG)
        by_team = {e["team"]: e for e in ladders["spreads"]}
        pistons = by_team["Pistons"]
        self.assertEqual(pistons["line"], -1.5)
        self.assertEqual(pistons["side"], "away")
        self.assertEqual(pistons["price_cents"], 51.0)  # mid 0.50/0.52
        self.assertFalse(pistons["thin"])  # volume $403,60 > $100
        hawks = by_team["Hawks"]
        self.assertEqual(hawks["line"], -1.5)
        self.assertEqual(hawks["side"], "home")
        self.assertEqual(hawks["price_cents"], 43.5)  # mid 0.43/0.44
        self.assertTrue(hawks["thin"])  # volume $65,48 < $100

    def test_moneyline_dua_tim(self):
        ladders = polymarket.parse_event_ladders(load_fixture(), cfg=CFG)
        by_team = {e["team"]: e for e in ladders["moneyline"]}
        self.assertEqual(by_team["Pistons"]["side"], "away")
        self.assertEqual(by_team["Pistons"]["price_cents"], 54.5)
        self.assertIsNone(by_team["Pistons"]["line"])
        # Hawks = komplemen (100 - 54.5), cocok outcomePrices[1] 0.455.
        self.assertEqual(by_team["Hawks"]["side"], "home")
        self.assertEqual(by_team["Hawks"]["price_cents"], 45.5)

    def test_min_volume_dari_cfg(self):
        cfg_500 = {
            "polymarket_ladder": {"min_volume_usd": 500.0},
            "fees": {"jup_typical_markup_cents": 0.5},
        }
        ladders = polymarket.parse_event_ladders(load_fixture(), cfg=cfg_500)
        by_team = {e["team"]: e for e in ladders["spreads"]}
        # Spread Pistons $403,60 kini di bawah ambang $500 -> thin.
        self.assertTrue(by_team["Pistons"]["thin"])
        self.assertFalse(_total(ladders["totals"], 225.5, "under")["thin"])

    def test_kunci_config_hilang(self):
        with self.assertRaises(config.ConfigError):
            polymarket.parse_event_ladders(load_fixture(), cfg={})

    def test_p2_tidak_ada_field_p_market(self):
        # Guardrail P2: hasil tangga TIDAK BOLEH memuat kunci p_market
        # di level mana pun (tangga = harga venue, bukan pembanding).
        ladders = polymarket.parse_event_ladders(load_fixture(), cfg=CFG)

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    self.assertNotEqual(key, "p_market")
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(ladders)

    def test_fallback_outcome_prices_tanpa_book(self):
        event = {
            "slug": "nba-was-chi-2026-11-22",
            "title": "Wizards vs. Bulls",
            "teams": [
                {"name": "Wizards", "ordering": "away"},
                {"name": "Bulls", "ordering": "home"},
            ],
            "markets": [
                {
                    "id": "1",
                    "question": "Wizards vs. Bulls: O/U 243.5",
                    "sportsMarketType": "totals",
                    "outcomes": '["Over", "Under"]',
                    "outcomePrices": '["0.42", "0.58"]',
                    "bestBid": None,
                    "bestAsk": None,
                    "lastTradePrice": 0.40,
                    "volume": "5000",
                    "liquidity": "1000",
                    "active": True,
                    "closed": False,
                }
            ],
        }
        ladders = polymarket.parse_event_ladders(event, cfg=CFG)
        over = _total(ladders["totals"], 243.5, "over")
        under = _total(ladders["totals"], 243.5, "under")
        self.assertEqual(over["price_source"], "outcome_prices")
        self.assertEqual(over["price_cents"], 42.0)
        self.assertEqual(under["price_cents"], 58.0)
        self.assertIsNone(over["mid_cents"])
        # Tanpa bid/ask -> thin walau volume besar.
        self.assertTrue(over["thin"])
        self.assertTrue(under["thin"])
        # lastTradePrice tetap info (Over 40¢, Under komplemen 60¢).
        self.assertEqual(over["last_cents"], 40.0)
        self.assertEqual(under["last_cents"], 60.0)

    def test_outcome_prices_tidak_berjumlah_satu_dicatat(self):
        event = {
            "slug": "nba-was-chi-2026-11-22",
            "title": "Wizards vs. Bulls",
            "teams": [
                {"name": "Wizards", "ordering": "away"},
                {"name": "Bulls", "ordering": "home"},
            ],
            "markets": [
                {
                    "id": "1",
                    "question": "Wizards vs. Bulls: O/U 243.5",
                    "sportsMarketType": "totals",
                    "outcomes": '["Over", "Under"]',
                    "outcomePrices": '["0.40", "0.40"]',
                    "bestBid": 0.40,
                    "bestAsk": 0.42,
                    "lastTradePrice": None,
                    "volume": "5000",
                    "liquidity": "1000",
                    "active": True,
                    "closed": False,
                }
            ],
        }
        ladders = polymarket.parse_event_ladders(event, cfg=CFG)
        self.assertEqual(len(ladders["totals"]), 2)
        self.assertEqual(len(ladders["warnings"]), 1)
        self.assertIn("80.0", ladders["warnings"][0])

    def test_pasar_tutup_dan_prop_dilewati(self):
        event = load_fixture()
        closed_total = dict(event["markets"][2])
        closed_total["question"] = "Pistons vs. Hawks: O/U 999.5"
        closed_total["closed"] = True
        prop = {
            "id": "9",
            "question": "Cade Cunningham: Points O/U 26.5",
            "sportsMarketType": "points",
            "outcomes": '["Over", "Under"]',
            "outcomePrices": '["0.50", "0.50"]',
            "bestBid": 0.49,
            "bestAsk": 0.51,
            "lastTradePrice": 0.50,
            "volume": "10000",
            "liquidity": "1000",
            "active": True,
            "closed": False,
        }
        event["markets"] = event["markets"] + [closed_total, prop]
        ladders = polymarket.parse_event_ladders(event, cfg=CFG)
        lines = sorted({e["line"] for e in ladders["totals"]})
        self.assertEqual(lines, [225.5, 235.5, 241.5])

    def test_fallback_judul_bila_teams_tidak_ada(self):
        event = load_fixture()
        del event["teams"]
        ladders = polymarket.parse_event_ladders(event, cfg=CFG)
        by_team = {e["team"]: e for e in ladders["moneyline"]}
        self.assertEqual(by_team["Pistons"]["side"], "away")
        self.assertEqual(by_team["Hawks"]["side"], "home")

    def test_event_tanpa_markets(self):
        ladders = polymarket.parse_event_ladders({"slug": "x"}, cfg=CFG)
        self.assertEqual(ladders["moneyline"], [])
        self.assertEqual(len(ladders["warnings"]), 1)


class TestCountEventMarkets(unittest.TestCase):
    def test_hitung_fixture(self):
        counts = polymarket.count_event_markets(load_fixture())
        self.assertEqual(counts["spread_markets"], 2)
        self.assertEqual(counts["total_markets"], 3)
        self.assertEqual(counts["spread_lines"], [-1.5])
        self.assertEqual(counts["total_lines"], [225.5, 235.5, 241.5])

    def test_event_kosong(self):
        counts = polymarket.count_event_markets({})
        self.assertEqual(counts["spread_markets"], 0)
        self.assertEqual(counts["total_markets"], 0)


if __name__ == "__main__":
    unittest.main()
