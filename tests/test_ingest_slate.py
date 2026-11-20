"""Tes ingest.slate — SEMUA fetcher kontrak di-mock (tanpa network).

Modul worker paralel (jupiter/odds_api/kalshi/polymarket/espn/stats_nba/
nba_injury_pdf/rotowire/bbref/matching/devig) diganti modul palsu di
sys.modules, jadi tes ini berdiri sendiri apa pun status modul aslinya.
premier_league/understat (modul sendiri) di-patch fungsinya.
"""

import re
import sys
import types
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import premier_league, understat
from ingest.common import FetchResult, now_iso
from ingest.slate import (
    _closest_by_time,
    build_football_slate,
    build_nba_slate,
    build_slate,
)

_MISSING = object()

PLAYSTYLE = {
    "data": {"stale_hours_injury_lineup": 3},
    "comparison": {"order": ["odds_api_devig", "espn_odds_devig", "kalshi"]},
}

NBA_DATE = "2026-11-20"
FB_DATE = "2026-11-21"


def _ok(source, tier, data, credits=0, fetched_at=None):
    return FetchResult(
        source=source,
        tier=tier,
        fetched_at=fetched_at or now_iso(),
        ok=True,
        data=data,
        credits_used=credits,
    )


def _fail(source, tier, error):
    return FetchResult(
        source=source, tier=tier, fetched_at=now_iso(), ok=False, error=error
    )


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def _fake_teams_match(a, b, sport):
    """Matcher palsu: sama ternormalisasi, atau substring."""
    left, right = _norm(a), _norm(b)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _fake_devig(odds, odds_format="decimal"):
    if odds_format == "american":
        odds = [_fake_american(o) for o in odds]
    implied = [1.0 / o for o in odds]
    total = sum(implied)
    return [p / total for p in implied]


def _fake_american(american):
    american = float(american)
    if american > 0:
        return 1.0 + american / 100.0
    return 1.0 + 100.0 / abs(american)


def _jup_market(
    market_type,
    outcome,
    home,
    away,
    line=None,
    provider="polymarket",
    yes=74,
    sport="nba",
):
    return {
        "event_id": "e1",
        "event_title": f"{away} vs. {home}",
        "market_id": f"m-{market_type}-{outcome}",
        "market_type": market_type,
        "line": line,
        "provider": provider,
        "outcome": outcome,
        "yes_price_cents": yes,
        "no_price_cents": None,
        "home_team": home,
        "away_team": away,
        "sport": sport,
        "league": "NBA 2026" if sport == "nba" else "Premier League",
    }


def _odds_event(home, away, bookmakers):
    return {
        "event_id": "ev1",
        "sport_key": "basketball_nba",
        "home_team": home,
        "away_team": away,
        "commence_time": "2026-11-21T01:00:00Z",
        "bookmakers": bookmakers,
    }


def _kalshi_market(kind, home, away, side, line, bid, ask):
    return {
        "market_ticker": f"K-{kind}-{side}-{line}",
        "event_ticker": "EVT",
        "title": f"{home} vs {away}",
        "league": "nba",
        "market_type": kind,
        "home_team": home,
        "away_team": away,
        "line": line,
        "side": side,
        "yes_bid_dollars": bid,
        "yes_ask_dollars": ask,
    }


class SlateTestBase(unittest.TestCase):
    """Pasang modul palsu + data default NBA; tearDown mengembalikan semua."""

    def setUp(self):
        self.data = {}
        self.calls = {"espn_odds": 0}
        self._saved = {}
        self._install_fakes()
        self._patchers = [
            mock.patch.object(
                premier_league,
                "fetch_fixtures",
                side_effect=lambda *a, **k: self.data["fixtures"],
            ),
            mock.patch.object(
                premier_league,
                "fetch_injuries_fpl",
                side_effect=lambda *a, **k: self.data["football_injuries"],
            ),
            mock.patch.object(
                understat,
                "fetch_xg",
                side_effect=lambda *a, **k: self.data["xg"],
            ),
        ]
        for patcher in self._patchers:
            patcher.start()
        self.data.update(self._default_data())

    def tearDown(self):
        mock.patch.stopall()
        for name, saved in self._saved.items():
            if saved is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved

    def _install_fake(self, name, **funcs):
        module = types.ModuleType(name)
        for key, func in funcs.items():
            setattr(module, key, func)
        self._saved[name] = sys.modules.get(name, _MISSING)
        sys.modules[name] = module

    def _install_fakes(self):
        data = self.data
        self._install_fake(
            "ingest.jupiter",
            fetch_sports_markets=lambda *a, **k: data["jupiter"],
        )
        self._install_fake(
            "ingest.odds_api",
            fetch_odds=lambda *a, **k: data["odds_api"],
        )
        self._install_fake(
            "ingest.kalshi",
            fetch_moneyline_markets=lambda *a, **k: data["kalshi_moneyline"],
            fetch_spread_markets=lambda *a, **k: data["kalshi_spread"],
            fetch_total_markets=lambda *a, **k: data["kalshi_total"],
            kalshi_probability=lambda m: (
                float(m["yes_bid_dollars"]) + float(m["yes_ask_dollars"])
            )
            / 2.0,
        )
        self._install_fake(
            "ingest.polymarket",
            find_token_for_jup_market=lambda m: data["poly_token"],
            fetch_orderbook=lambda t: data["poly_orderbook"],
            compute_jup_markup=lambda jup, mid: jup - mid,
        )
        self._install_fake(
            "ingest.espn",
            fetch_scoreboard=lambda *a, **k: data["espn_scoreboard"],
            fetch_injuries_nba=lambda *a, **k: data["injuries_espn"],
            fetch_odds_football=lambda *a, **k: self._espn_odds(),
        )
        self._install_fake(
            "ingest.stats_nba",
            fetch_scoreboard=lambda *a, **k: data["scoreboard"],
            fetch_standings=lambda *a, **k: data["standings"],
        )
        self._install_fake(
            "ingest.bbref",
            fetch_team_advanced=lambda *a, **k: data["advanced"],
        )
        self._install_fake(
            "ingest.nba_injury_pdf",
            fetch_report=lambda *a, **k: data["injuries_pdf"],
        )
        self._install_fake(
            "ingest.rotowire",
            fetch_injuries=lambda *a, **k: data["injuries_rotowire"],
        )
        self._install_fake(
            "ingest.matching",
            teams_match=_fake_teams_match,
            normalize_team=lambda name, sport: _norm(name),
        )
        self._install_fake(
            "engine.devig",
            devig=_fake_devig,
            american_to_decimal=_fake_american,
        )

    def _espn_odds(self):
        self.calls["espn_odds"] += 1
        return self.data["espn_odds"]

    def _default_data(self):
        """Data default: 1 laga NBA lengkap + fixtures bola Chelsea-Leeds."""
        pinnacle = {
            "key": "pinnacle",
            "title": "Pinnacle",
            "markets": [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Lakers", "price": 1.35, "point": None},
                        {"name": "Celtics", "price": 3.20, "point": None},
                    ],
                }
            ],
        }
        return {
            "jupiter": _ok(
                "Jupiter Prediction API",
                1,
                [
                    _jup_market("moneyline", "Lakers", "Lakers", "Celtics"),
                    _jup_market("moneyline", "Celtics", "Lakers", "Celtics", yes=32),
                    _jup_market(
                        "first_half_spreads",
                        "Lakers",
                        "Lakers",
                        "Celtics",
                        line=-0.5,
                    ),
                ],
            ),
            "odds_api": _ok(
                "The Odds API",
                2,
                [_odds_event("Lakers", "Celtics", [pinnacle])],
                credits=1,
            ),
            "kalshi_moneyline": _ok(
                "Kalshi API",
                2,
                [
                    _kalshi_market(
                        "moneyline", "Lakers", "Celtics", "home", None, 0.70, 0.72
                    ),
                    _kalshi_market(
                        "moneyline", "Lakers", "Celtics", "away", None, 0.28, 0.30
                    ),
                ],
            ),
            "kalshi_spread": _fail("Kalshi API", 2, "tidak ada pasar"),
            "kalshi_total": _fail("Kalshi API", 2, "tidak ada pasar"),
            "poly_token": "tok1",
            "poly_orderbook": _ok(
                "Polymarket CLOB",
                2,
                {
                    "bid_cents": 69.0,
                    "ask_cents": 71.0,
                    "mid_cents": 70.0,
                    "spread_cents": 2.0,
                },
            ),
            "espn_scoreboard": _ok(
                "ESPN",
                2,
                [
                    {
                        "game_id": "g1",
                        "home_team": "Lakers",
                        "away_team": "Celtics",
                        "start_time": "2026-11-21T01:00:00Z",
                        "status": "Scheduled",
                        "league": "nba",
                    }
                ],
            ),
            "espn_odds": _fail("ESPN odds", 2, "tidak ada odds"),
            "scoreboard": _ok(
                "stats.nba.com",
                1,
                [
                    {
                        "game_id": "g1",
                        "home_team": "Lakers",
                        "away_team": "Celtics",
                        "home_tricode": "LAL",
                        "away_tricode": "BOS",
                        "start_time": "2026-11-21T01:00:00Z",
                        "status": "7:00 pm ET",
                    }
                ],
            ),
            "standings": _ok(
                "stats.nba.com",
                1,
                [
                    {"team": "Lakers", "wins": 10, "losses": 5},
                    {"team": "Celtics", "wins": 9, "losses": 6},
                ],
            ),
            "advanced": _ok(
                "Basketball-Reference",
                2,
                [
                    {"team": "Lakers", "off_rtg": 115.0, "def_rtg": 110.0},
                    {"team": "Celtics", "off_rtg": 113.0, "def_rtg": 109.0},
                ],
            ),
            "injuries_pdf": _ok(
                "Official NBA Injury Report",
                1,
                [
                    {
                        "player": "LeBron James",
                        "team": "Lakers",
                        "status": "OUT",
                        "detail": "ankle",
                    }
                ],
            ),
            "injuries_rotowire": _ok(
                "Rotowire",
                2,
                [
                    {
                        "player": "LeBron James",
                        "team": "Lakers",
                        "status": "OUT",
                        "detail": "ankle",
                    }
                ],
            ),
            "injuries_espn": _ok("ESPN injuries", 2, []),
            "fixtures": _ok(
                "Premier League (JSON resmi)",
                1,
                [
                    {
                        "home_team": "Chelsea",
                        "away_team": "Leeds United",
                        "kickoff": "2026-11-21T17:30:00+00:00",
                        "status": "U",
                        "matchweek": 12,
                    }
                ],
            ),
            "xg": _fail(
                "Understat", 2, "understat_not_available: status 'maintenance'"
            ),
            # Default: FPL gagal — tes bola yang tidak menyetelnya tetap
            # melihat 0 sumber cedera (perilaku lama, jujur).
            "football_injuries": _fail("Fantasy Premier League API", 1, "http_500"),
        }

    def _nba_match(self):
        return build_nba_slate(
            NBA_DATE,
            matches=[{"home": "Lakers", "away": "Celtics"}],
            playstyle=PLAYSTYLE,
        )["matches"][0]


class TestNbaSlate(SlateTestBase):
    def test_ok_lengkap(self):
        match = self._nba_match()
        self.assertEqual(match["status"], "OK")
        self.assertEqual(match["labels"], [])
        kinds = {s["data_kind"] for s in match["sources"]}
        self.assertIn("nba_schedule_stats", kinds)
        self.assertEqual(
            sum(1 for s in match["sources"] if s["data_kind"] == "nba_injuries"),
            3,
        )
        self.assertIn("jup_prices", kinds)
        self.assertIn("comparison_prices", kinds)
        self.assertEqual(match["missing"], [])
        self.assertEqual(match["conflicts"], [])
        self.assertEqual(len(match["injuries"]), 1)
        self.assertEqual(match["injuries"][0]["player"], "LeBron James")

    def test_p_market_dari_odds_api_tanpa_label(self):
        # Aturan 2a: Odds API ada -> dipakai, tanpa label PEMBANDING_KALSHI.
        match = self._nba_match()
        entry = match["market_prices"]["moneyline_home"]
        self.assertEqual(entry["comparison_source"], "odds_api_devig")
        self.assertAlmostEqual(entry["p_market"], 0.7033, places=3)
        self.assertEqual(entry["labels"], [])
        self.assertEqual(entry["side"], "home")
        self.assertEqual(entry["jup_price_cents"], 74)
        self.assertEqual(entry["jup_provider"], "polymarket")
        self.assertEqual(entry["jup_markup_cents"], 4.0)
        self.assertIsNone(entry["jup_markup_reason"])
        # Jenis pasar di luar kontrak (first_half_spreads) dibuang.
        self.assertNotIn("first_half_spread_home_-0.5", match["market_prices"])

    def test_konflik_cedera_ditampilkan_keduanya(self):
        self.data["injuries_espn"] = _ok(
            "ESPN injuries",
            2,
            [
                {
                    "player": "LeBron James",
                    "team": "Lakers",
                    "status": "QUESTIONABLE",
                    "detail": "ankle",
                }
            ],
        )
        match = self._nba_match()
        self.assertEqual(len(match["conflicts"]), 1)
        conflict = match["conflicts"][0]
        self.assertEqual(conflict["field"], "injuries:LeBron James")
        values = {v["source"]: v["value"] for v in conflict["values"]}
        self.assertEqual(values["Official NBA Injury Report"], "OUT")
        self.assertEqual(values["ESPN injuries"], "QUESTIONABLE")
        statuses = {i["status"] for i in match["injuries"]}
        self.assertEqual(statuses, {"OUT", "QUESTIONABLE"})

    def test_p2_kalshi_dilewati_bila_asal_kalshi(self):
        self.data["jupiter"] = _ok(
            "Jupiter Prediction API",
            1,
            [
                _jup_market(
                    "moneyline",
                    "Lakers",
                    "Lakers",
                    "Celtics",
                    provider="kalshi",
                )
            ],
        )
        self.data["odds_api"] = _fail("The Odds API", 2, "http_401")
        match = self._nba_match()
        entry = match["market_prices"]["moneyline_home"]
        self.assertIsNone(entry["p_market"])
        self.assertIsNone(entry["comparison_source"])
        self.assertIn("kalshi_dilewati_p2", entry["p_market_missing_reason"])
        self.assertIn("MODEL_ONLY", match["labels"])

    def test_espn_odds_dilewati_nba_kalshi_dipakai(self):
        # Aturan 2c (NBA): Odds API kosong -> ESPN dilewati -> Kalshi + label.
        self.data["odds_api"] = _fail("The Odds API", 2, "http_401")
        match = self._nba_match()
        self.assertEqual(self.calls["espn_odds"], 0)
        entry = match["market_prices"]["moneyline_home"]
        self.assertEqual(entry["comparison_source"], "kalshi")
        self.assertAlmostEqual(entry["p_market"], 0.71)
        self.assertEqual(entry["labels"], ["PEMBANDING_KALSHI"])
        self.assertFalse(entry["p_market_complement"])
        self.assertNotIn("MODEL_ONLY", match["labels"])

    def test_semua_pembanding_kosong_model_only(self):
        # Aturan 2d: semua kosong -> p_market None + MODEL_ONLY.
        self.data["odds_api"] = _fail("The Odds API", 2, "http_401")
        self.data["kalshi_moneyline"] = _fail("Kalshi API", 2, "http_500")
        match = self._nba_match()
        entry = match["market_prices"]["moneyline_home"]
        self.assertIsNone(entry["p_market"])
        self.assertIn("MODEL_ONLY", match["labels"])
        self.assertEqual(match["status"], "OK")

    def test_jup_markup_source_dicatat(self):
        # Sumber mid (book vs midpoint-fallback) dicatat di entri — mid
        # dari pasar ilikuid (fallback) bisa menyesatkan.
        self.data["poly_orderbook"] = FetchResult(
            source="Polymarket CLOB",
            tier=2,
            fetched_at=now_iso(),
            ok=True,
            data={
                "bid_cents": None,
                "ask_cents": None,
                "mid_cents": 42.5,
                "spread_cents": None,
            },
            extra={"source": "midpoint"},
        )
        match = self._nba_match()
        entry = match["market_prices"]["moneyline_home"]
        self.assertEqual(entry["jup_markup_source"], "midpoint")
        self.assertAlmostEqual(entry["jup_markup_cents"], 74.0 - 42.5)

    def test_jup_markup_token_tidak_ditemukan(self):
        self.data["poly_token"] = None
        match = self._nba_match()
        entry = match["market_prices"]["moneyline_home"]
        self.assertIsNone(entry["jup_markup_cents"])
        self.assertEqual(entry["jup_markup_reason"], "polymarket_token_tidak_ditemukan")

    def test_summary_dan_odds_api(self):
        slate = build_nba_slate(
            NBA_DATE,
            matches=[
                {"home": "Lakers", "away": "Celtics"},
                {"home": "Nuggets", "away": "Suns"},
            ],
            playstyle=PLAYSTYLE,
        )
        self.assertEqual(slate["slate_id"], f"slate-nba-{NBA_DATE}")
        self.assertEqual(slate["summary"]["matches"], 2)
        self.assertEqual(slate["summary"]["ok"], 1)
        self.assertEqual(slate["summary"]["data_incomplete"], 1)
        self.assertEqual(slate["summary"]["hold"], 0)
        self.assertEqual(slate["odds_api"], {"calls": 1, "credits_used": 1})
        nuggets = slate["matches"][1]
        self.assertEqual(nuggets["status"], "DATA_INCOMPLETE")

    def test_discovery_dari_scoreboard(self):
        slate = build_nba_slate(NBA_DATE, matches=None, playstyle=PLAYSTYLE)
        self.assertEqual(len(slate["matches"]), 1)
        self.assertEqual(
            slate["matches"][0]["match_id"], f"nba-{NBA_DATE}-lakers-celtics"
        )

    def test_duplikat_pasangan_jup_pilih_yang_terdekat(self):
        # BUG DEMO 2b: Suns-Jazz main dua kali (malam ini + rematch 29
        # Nov); tanpa pembedaan jam, slate memakai harga rematch (76/55)
        # bukan malam ini (63/38). Per kunci pasar, yang terdekat dengan
        # start_time laga ini yang dipakai.
        tonight = "2026-11-21T02:30:00+00:00"
        future = "2026-11-29T22:00:00+00:00"
        suns_now = _jup_market("moneyline", "Suns", "Jazz", "Suns", yes=63)
        suns_now["start_time"] = tonight
        jazz_now = _jup_market("moneyline", "Jazz", "Jazz", "Suns", yes=38)
        jazz_now["start_time"] = tonight
        suns_later = _jup_market("moneyline", "Suns", "Jazz", "Suns", yes=76)
        suns_later["start_time"] = future
        jazz_later = _jup_market("moneyline", "Jazz", "Jazz", "Suns", yes=55)
        jazz_later["start_time"] = future
        self.data["jupiter"] = _ok(
            "Jupiter Prediction API",
            1,
            [suns_now, jazz_now, suns_later, jazz_later],
        )
        match = build_nba_slate(
            NBA_DATE,
            matches=[
                {
                    "home": "Jazz",
                    "away": "Suns",
                    "start_time": "2026-11-21T09:30:00+07:00",
                }
            ],
            playstyle=PLAYSTYLE,
        )["matches"][0]
        self.assertEqual(
            match["market_prices"]["moneyline_away"]["jup_price_cents"], 63.0
        )
        self.assertEqual(
            match["market_prices"]["moneyline_home"]["jup_price_cents"], 38.0
        )

    def test_duplikat_event_odds_api_pilih_yang_terdekat(self):
        # Odds API mengembalikan ~1 minggu laga: dua event Lakers-Celtics
        # (malam ini + 29 Nov) — p_market harus dari event malam ini.
        tonight = _odds_event(
            "Lakers",
            "Celtics",
            [
                {
                    "key": "pinnacle",
                    "title": "Pinnacle",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Lakers", "price": 1.35, "point": None},
                                {"name": "Celtics", "price": 3.20, "point": None},
                            ],
                        }
                    ],
                }
            ],
        )
        tonight["commence_time"] = "2026-11-21T01:00:00Z"
        future = _odds_event(
            "Lakers",
            "Celtics",
            [
                {
                    "key": "pinnacle",
                    "title": "Pinnacle",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Lakers", "price": 2.00, "point": None},
                                {"name": "Celtics", "price": 1.80, "point": None},
                            ],
                        }
                    ],
                }
            ],
        )
        future["commence_time"] = "2026-11-29T01:00:00Z"
        self.data["odds_api"] = _ok("The Odds API", 2, [future, tonight], credits=1)
        markets = [
            {**m, "start_time": "2026-11-21T01:00:00+00:00"}
            for m in self.data["jupiter"].data
        ]
        self.data["jupiter"] = _ok("Jupiter Prediction API", 1, markets)
        match = self._nba_match()
        # Devig malam ini: Lakers 0.703; bila event 29 Nov terpilih: 0.474.
        self.assertAlmostEqual(
            match["market_prices"]["moneyline_home"]["p_market"], 0.703, places=3
        )
        self.assertEqual(
            match["market_prices"]["moneyline_home"]["comparison_source"],
            "odds_api_devig",
        )

    def test_duplikat_pasar_kalshi_pilih_yang_terdekat(self):
        # Dua kandidat Kalshi Lakers (malam ini + rematch) — pilih yang
        # expiration-nya terdekat dengan jam mulai pasar jup.
        self.data["odds_api"] = _fail("The Odds API", 2, "http_401")
        tonight = _kalshi_market(
            "moneyline", "Lakers", "Celtics", "home", None, 0.70, 0.72
        )
        tonight["expiration_time"] = "2026-11-21T06:00:00Z"
        future = _kalshi_market(
            "moneyline", "Lakers", "Celtics", "home", None, 0.40, 0.42
        )
        future["expiration_time"] = "2026-11-29T06:00:00Z"
        away = _kalshi_market(
            "moneyline", "Lakers", "Celtics", "away", None, 0.28, 0.30
        )
        self.data["kalshi_moneyline"] = _ok("Kalshi API", 2, [future, tonight, away])
        markets = [
            {**m, "start_time": "2026-11-21T01:00:00+00:00"}
            for m in self.data["jupiter"].data
        ]
        self.data["jupiter"] = _ok("Jupiter Prediction API", 1, markets)
        match = self._nba_match()
        entry = match["market_prices"]["moneyline_home"]
        self.assertAlmostEqual(entry["p_market"], 0.71)
        self.assertEqual(entry["comparison_source"], "kalshi")
        self.assertEqual(entry["labels"], ["PEMBANDING_KALSHI"])

    def test_stale_hours_dari_playstyle(self):
        hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        for key in ("injuries_pdf", "injuries_rotowire", "injuries_espn"):
            old = self.data[key]
            self.data[key] = _ok(old.source, old.tier, old.data, fetched_at=hour_ago)
        strict = {
            "data": {"stale_hours_injury_lineup": 0.5},
            "comparison": PLAYSTYLE["comparison"],
        }
        slate = build_nba_slate(
            NBA_DATE,
            matches=[{"home": "Lakers", "away": "Celtics"}],
            playstyle=strict,
        )
        self.assertEqual(slate["matches"][0]["status"], "HOLD")
        self.assertIn("basi", slate["matches"][0]["status_reason"])


class TestFootballSlate(SlateTestBase):
    def setUp(self):
        super().setUp()
        self._football_data()

    def _football_data(self):
        """Timpa data default dengan slate bola Chelsea-Leeds."""
        self.data["jupiter"] = _ok(
            "Jupiter Prediction API",
            1,
            [
                _jup_market(
                    "moneyline",
                    "Chelsea",
                    "Chelsea",
                    "Leeds United",
                    yes=65,
                    sport="football",
                ),
                _jup_market(
                    "spreads",
                    "Chelsea",
                    "Chelsea",
                    "Leeds United",
                    line=-1.5,
                    yes=32,
                    sport="football",
                ),
                _jup_market(
                    "spreads",
                    "Leeds United",
                    "Chelsea",
                    "Leeds United",
                    line=1.5,
                    yes=70,
                    sport="football",
                ),
                _jup_market(
                    "totals",
                    "Over",
                    "Chelsea",
                    "Leeds United",
                    line=2.5,
                    yes=54,
                    sport="football",
                ),
                _jup_market(
                    "totals",
                    "Under",
                    "Chelsea",
                    "Leeds United",
                    line=2.5,
                    yes=46,
                    sport="football",
                ),
                _jup_market(
                    "both_teams_to_score",
                    "Both Teams to Score",
                    "Chelsea",
                    "Leeds United",
                    yes=55,
                    sport="football",
                ),
            ],
        )
        self.data["odds_api"] = _fail("The Odds API", 2, "http_401")
        self.data["espn_odds"] = _ok(
            "ESPN odds",
            2,
            [
                {
                    "home_team": "Chelsea",
                    "away_team": "Leeds United",
                    "commence_time": "2026-11-21T17:30:00Z",
                    "provider": "DraftKings",
                    "moneyline": {
                        "home": "-150",
                        "draw": "+280",
                        "away": "+400",
                    },
                    "spread": {
                        "home_line": "-1.5",
                        "home_odds": "-110",
                        "away_line": "1.5",
                        "away_odds": "-110",
                    },
                    "total": {
                        "line": 2.5,
                        "over_odds": "-110",
                        "under_odds": "-110",
                    },
                }
            ],
        )
        self.data["kalshi_moneyline"] = _ok(
            "Kalshi API",
            2,
            [
                _kalshi_market(
                    "moneyline",
                    "Chelsea",
                    "Leeds United",
                    "home",
                    None,
                    0.60,
                    0.62,
                )
            ],
        )
        self.data["kalshi_spread"] = _ok(
            "Kalshi API",
            2,
            [
                _kalshi_market(
                    "spread",
                    "Chelsea",
                    "Leeds United",
                    "home",
                    1.5,
                    0.30,
                    0.34,
                ),
                _kalshi_market(
                    "spread",
                    "Chelsea",
                    "Leeds United",
                    "away",
                    1.5,
                    0.08,
                    0.10,
                ),
            ],
        )
        self.data["kalshi_total"] = _ok(
            "Kalshi API",
            2,
            [
                _kalshi_market(
                    "total",
                    "Chelsea",
                    "Leeds United",
                    "over",
                    2.5,
                    0.53,
                    0.55,
                )
            ],
        )

    def _fb_match(self):
        return build_football_slate(
            FB_DATE,
            matches=[{"home": "Chelsea", "away": "Leeds United"}],
            playstyle=PLAYSTYLE,
        )["matches"][0]

    def test_tanpa_xg_label_dan_fixture(self):
        match = self._fb_match()
        self.assertIn("TANPA_XG", match["labels"])
        self.assertEqual(match["stats"]["fixture"]["matchweek"], 12)
        self.assertEqual(match["stats"]["fixture"]["status"], "U")
        # Default: FPL gagal + ESPN tanpa cedera -> 0 sumber cedera bola
        # -> DATA_INCOMPLETE (jujur) + football_lineup_injuries di missing.
        self.assertEqual(match["status"], "DATA_INCOMPLETE")
        self.assertIn("0 sumber", match["status_reason"])
        self.assertIn("football_lineup_injuries", match["missing"])

    def test_fpl_cedera_satu_sumber_hold(self):
        # FPL berhasil = 1 sumber cedera bola -> HOLD (B2 butuh 2 sumber),
        # bukan DATA_INCOMPLETE; cedera Chelsea masuk, sumber tercatat.
        self.data["football_injuries"] = _ok(
            "Fantasy Premier League API",
            1,
            [
                {
                    "player": "Cole Palmer",
                    "team": "Chelsea",
                    "status": "Doubtful",
                    "detail": "Groin injury - 75% chance of playing",
                },
                {
                    "player": "Bukayo Saka",
                    "team": "Arsenal",
                    "status": "Out",
                    "detail": "Thigh injury",
                },
            ],
        )
        match = self._fb_match()
        self.assertEqual(match["status"], "HOLD")
        self.assertIn("hanya 1 sumber", match["status_reason"])
        self.assertEqual(len(match["injuries"]), 1)
        self.assertEqual(match["injuries"][0]["player"], "Cole Palmer")
        self.assertEqual(match["injuries"][0]["status"], "Doubtful")
        injury_sources = [
            entry
            for entry in match["sources"]
            if entry["data_kind"] == "football_lineup_injuries"
        ]
        self.assertEqual(len(injury_sources), 1)
        self.assertEqual(injury_sources[0]["source"], "Fantasy Premier League API")
        self.assertEqual(injury_sources[0]["tier"], 1)
        self.assertNotIn("football_lineup_injuries", match["missing"])

    def test_espn_odds_dipakai_bila_odds_api_kosong(self):
        # Aturan 2b: Odds API kosong, ESPN odds ada (bola) -> ESPN, tanpa label.
        match = self._fb_match()
        entry = match["market_prices"]["moneyline_home"]
        self.assertEqual(entry["comparison_source"], "espn_odds_devig")
        self.assertAlmostEqual(entry["p_market"], 0.5644, places=3)
        self.assertEqual(entry["labels"], [])
        self.assertNotIn("MODEL_ONLY", match["labels"])

    def test_espn_spread_garis_cocok(self):
        match = self._fb_match()
        entry = match["market_prices"]["spread_home_-1.5"]
        self.assertEqual(entry["comparison_source"], "espn_odds_devig")
        self.assertEqual(entry["comparison_line"], -1.5)
        self.assertTrue(entry["line_matched"])
        self.assertAlmostEqual(entry["p_market"], 0.5, places=3)

    def test_kalshi_spread_favorit_langsung(self):
        self.data["espn_odds"] = _fail("ESPN odds", 2, "tidak ada odds")
        match = self._fb_match()
        entry = match["market_prices"]["spread_home_-1.5"]
        self.assertEqual(entry["comparison_source"], "kalshi")
        self.assertAlmostEqual(entry["p_market"], 0.32)
        self.assertEqual(entry["labels"], ["PEMBANDING_KALSHI"])
        self.assertEqual(entry["comparison_line"], 1.5)
        self.assertTrue(entry["line_matched"])
        self.assertFalse(entry["p_market_complement"])

    def test_kalshi_spread_underdog_komplemen(self):
        # Leeds +1.5 = 1 - P(Chelsea menang > 1.5), BUKAN pasar Leeds 1.5.
        self.data["espn_odds"] = _fail("ESPN odds", 2, "tidak ada odds")
        match = self._fb_match()
        entry = match["market_prices"]["spread_away_1.5"]
        self.assertEqual(entry["comparison_source"], "kalshi")
        self.assertAlmostEqual(entry["p_market"], 0.68)
        self.assertTrue(entry["p_market_complement"])
        self.assertEqual(entry["comparison_line"], 1.5)
        self.assertTrue(entry["line_matched"])

    def test_kalshi_spread_garis_tidak_cocok(self):
        self.data["espn_odds"] = _fail("ESPN odds", 2, "tidak ada odds")
        self.data["kalshi_spread"] = _ok(
            "Kalshi API",
            2,
            [
                _kalshi_market(
                    "spread",
                    "Chelsea",
                    "Leeds United",
                    "home",
                    2.5,
                    0.15,
                    0.17,
                )
            ],
        )
        self.data["jupiter"] = _ok(
            "Jupiter Prediction API",
            1,
            [
                _jup_market(
                    "spreads",
                    "Chelsea",
                    "Chelsea",
                    "Leeds United",
                    line=-1.5,
                    yes=32,
                    sport="football",
                )
            ],
        )
        match = self._fb_match()
        entry = match["market_prices"]["spread_home_-1.5"]
        self.assertIsNone(entry["p_market"])
        self.assertIsNone(entry["comparison_line"])
        self.assertFalse(entry["line_matched"])
        self.assertIn("MODEL_ONLY", match["labels"])

    def test_kalshi_total_over_langsung_dan_under_komplemen(self):
        self.data["espn_odds"] = _fail("ESPN odds", 2, "tidak ada odds")
        match = self._fb_match()
        over = match["market_prices"]["total_over_2.5"]
        self.assertAlmostEqual(over["p_market"], 0.54)
        self.assertFalse(over["p_market_complement"])
        self.assertEqual(over["comparison_line"], 2.5)
        self.assertTrue(over["line_matched"])
        under = match["market_prices"]["total_under_2.5"]
        self.assertAlmostEqual(under["p_market"], 0.46)
        self.assertTrue(under["p_market_complement"])

    def test_btts_tanpa_pembanding_bukan_model_only(self):
        match = self._fb_match()
        btts = match["market_prices"]["both_teams_to_score_yes"]
        self.assertEqual(btts["side"], "yes")
        self.assertIsNone(btts["p_market"])
        # Moneyline punya p_market -> laga BUKAN MODEL_ONLY.
        self.assertNotIn("MODEL_ONLY", match["labels"])

    def test_xg_tersedia_tanpa_label_tanpa_xg(self):
        self.data["xg"] = _ok(
            "Understat",
            2,
            {
                "1": {"id": 1, "title": "Chelsea", "history": []},
                "2": {"id": 2, "title": "Leeds", "history": []},
            },
        )
        match = self._fb_match()
        self.assertNotIn("TANPA_XG", match["labels"])
        self.assertIn("xg", match["stats"])


class TestClosestByTime(unittest.TestCase):
    def test_terdekat_menang(self):
        items = [
            {"id": "jauh", "start_time": "2026-11-29T22:00:00+00:00"},
            {"id": "dekat", "start_time": "2026-11-21T02:30:00+00:00"},
        ]
        chosen = _closest_by_time(items, "2026-11-21T02:30:00+00:00", "start_time")
        self.assertEqual(chosen["id"], "dekat")

    def test_target_none_paling_awal(self):
        items = [
            {"id": "nanti", "start_time": "2026-11-29T22:00:00+00:00"},
            {"id": "awal", "start_time": "2026-11-21T02:30:00+00:00"},
        ]
        chosen = _closest_by_time(items, None, "start_time")
        self.assertEqual(chosen["id"], "awal")

    def test_tanpa_waktu_item_pertama(self):
        items = [{"id": "a"}, {"id": "b", "start_time": "bukan jam"}]
        chosen = _closest_by_time(items, "2026-11-21T02:30:00+00:00", "start_time")
        self.assertEqual(chosen["id"], "a")

    def test_kosong_none(self):
        self.assertIsNone(
            _closest_by_time([], "2026-11-21T02:30:00+00:00", "start_time")
        )


class TestBuildSlate(unittest.TestCase):
    def test_sport_tidak_dikenal(self):
        with self.assertRaises(ValueError):
            build_slate("tenis", "2026-11-20", playstyle=PLAYSTYLE)


if __name__ == "__main__":
    unittest.main()
