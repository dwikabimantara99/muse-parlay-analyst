"""Tes validate.checks — semua status + precedence + kebasian."""

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validate.checks import validate_match_data

NOW = datetime(2026, 11, 20, 16, 0, tzinfo=UTC)
FRESH = (NOW - timedelta(hours=1)).isoformat()
STALE = (NOW - timedelta(hours=4)).isoformat()


def _match(sources=(), stats=None, market_prices=None):
    return {
        "match_id": "nba-2026-11-20-lal-bos",
        "sport": "nba",
        "fetched_at": NOW.isoformat(),
        "status": "OK",
        "sources": list(sources),
        "stats": stats if stats is not None else {"standings": {}},
        "injuries": [],
        "lineup": None,
        "market_prices": (
            market_prices
            if market_prices is not None
            else {"moneyline_home": {"p_market": 0.7}}
        ),
        "missing": [],
        "conflicts": [],
        "status_reason": None,
    }


def _injury_source(source, fetched_at=FRESH, kind="nba_injuries"):
    return {
        "data_kind": kind,
        "source": source,
        "tier": 1,
        "fetched_at": fetched_at,
    }


class TestValidate(unittest.TestCase):
    def test_ok_lengkap_dan_segar(self):
        match = _match(
            sources=[
                _injury_source("Official NBA Injury Report"),
                _injury_source("ESPN injuries"),
            ]
        )
        verdict = validate_match_data(match, 3, now=NOW)
        self.assertEqual(verdict["status"], "OK")
        self.assertEqual(verdict["reasons"], [])

    def test_cedera_0_sumber_data_incomplete(self):
        verdict = validate_match_data(_match(), 3, now=NOW)
        self.assertEqual(verdict["status"], "DATA_INCOMPLETE")
        self.assertTrue(any("0 sumber" in r for r in verdict["reasons"]))

    def test_cedera_1_sumber_hold(self):
        match = _match(sources=[_injury_source("ESPN injuries")])
        verdict = validate_match_data(match, 3, now=NOW)
        self.assertEqual(verdict["status"], "HOLD")
        self.assertTrue(any("B2 butuh 2 sumber" in r for r in verdict["reasons"]))

    def test_duplikat_sumber_yang_sama_tetap_1(self):
        match = _match(
            sources=[
                _injury_source("ESPN injuries"),
                _injury_source("ESPN injuries"),
            ]
        )
        verdict = validate_match_data(match, 3, now=NOW)
        self.assertEqual(verdict["status"], "HOLD")

    def test_stats_kosong_data_incomplete(self):
        match = _match(
            sources=[
                _injury_source("Official NBA Injury Report"),
                _injury_source("ESPN injuries"),
            ],
            stats={},
        )
        verdict = validate_match_data(match, 3, now=NOW)
        self.assertEqual(verdict["status"], "DATA_INCOMPLETE")
        self.assertTrue(any("stats kosong" in r for r in verdict["reasons"]))

    def test_market_prices_kosong_data_incomplete(self):
        match = _match(
            sources=[
                _injury_source("Official NBA Injury Report"),
                _injury_source("ESPN injuries"),
            ],
            market_prices={},
        )
        verdict = validate_match_data(match, 3, now=NOW)
        self.assertEqual(verdict["status"], "DATA_INCOMPLETE")
        self.assertTrue(any("market_prices" in r for r in verdict["reasons"]))

    def test_cedera_basi_hold(self):
        match = _match(
            sources=[
                _injury_source("Official NBA Injury Report", STALE),
                _injury_source("ESPN injuries", STALE),
            ]
        )
        verdict = validate_match_data(match, 3, now=NOW)
        self.assertEqual(verdict["status"], "HOLD")
        self.assertTrue(any("basi" in r for r in verdict["reasons"]))

    def test_satu_sumber_segar_cukup(self):
        match = _match(
            sources=[
                _injury_source("Official NBA Injury Report", STALE),
                _injury_source("ESPN injuries", FRESH),
            ]
        )
        verdict = validate_match_data(match, 3, now=NOW)
        self.assertEqual(verdict["status"], "OK")

    def test_batas_stale_pas_tidak_basi(self):
        exactly = (NOW - timedelta(hours=3)).isoformat()
        match = _match(
            sources=[
                _injury_source("Official NBA Injury Report", exactly),
                _injury_source("ESPN injuries", exactly),
            ]
        )
        verdict = validate_match_data(match, 3, now=NOW)
        self.assertEqual(verdict["status"], "OK")

    def test_jam_tidak_bisa_dibaca_hold(self):
        match = _match(
            sources=[
                _injury_source("Official NBA Injury Report", "kemarin"),
                _injury_source("ESPN injuries", "kemarin"),
            ]
        )
        verdict = validate_match_data(match, 3, now=NOW)
        self.assertEqual(verdict["status"], "HOLD")
        self.assertTrue(any("tidak bisa dibaca" in r for r in verdict["reasons"]))

    def test_data_incomplete_mengalahkan_hold(self):
        match = _match(sources=[_injury_source("ESPN injuries")], stats={})
        verdict = validate_match_data(match, 3, now=NOW)
        self.assertEqual(verdict["status"], "DATA_INCOMPLETE")
        self.assertEqual(len(verdict["reasons"]), 2)

    def test_p_market_kosong_bukan_incompleteness(self):
        # MODEL_ONLY ditangani label slate, bukan validate (aturan 6).
        match = _match(
            sources=[
                _injury_source("Official NBA Injury Report"),
                _injury_source("ESPN injuries"),
            ],
            market_prices={"moneyline_home": {"p_market": None}},
        )
        verdict = validate_match_data(match, 3, now=NOW)
        self.assertEqual(verdict["status"], "OK")

    def test_kind_cedera_bola_dihitung(self):
        match = _match(
            sources=[
                _injury_source("ESPN soccer", kind="football_lineup_injuries"),
                _injury_source("ESPN soccer", kind="football_lineup_injuries"),
            ]
        )
        match["sport"] = "football"
        verdict = validate_match_data(match, 3, now=NOW)
        self.assertEqual(verdict["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
