"""Tes ingest/check_nba_lines.py — pindai spread/total NBA (mock).

TANPA network: main() dites dengan fetch_sports_events yang di-mock;
scan_nba_lines + recheck_schedule dites murni dari fixture event.
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import check_nba_lines
from ingest.common import FetchResult


def _market(market_id, title, mtype, line):
    return {
        "marketId": market_id,
        "title": title,
        "sportsMarketType": mtype,
        "sportsLine": line,
        "provider": "polymarket",
        "pricing": {"buyYesPriceUsd": 500000, "buyNoPriceUsd": 0},
    }


def _event(event_id, subcategory, title, markets, begin_at="1795222800"):
    return {
        "eventId": event_id,
        "category": "sports",
        "subcategory": subcategory,
        "beginAt": begin_at,
        "metadata": {"title": title, "league": "NBA 2026"},
        "markets": markets,
    }


# beginAt 1795222800 = 2026-11-21T01:00:00Z; 1795309200 = 2026-11-22T01:00:00Z.
NBA_GAME_WITH_LINES = _event(
    "POLY-1",
    "nba",
    "Wizards vs. Bulls",
    [
        _market("M1", "Wizards", "moneyline", None),
        _market("M2", "Bulls", "moneyline", None),
        _market("M3", "Bulls", "spreads", "-2.5"),
        _market("M4", "Wizards", "spreads", "-2.5"),
        _market("M5", "Over", "totals", "243.5"),
        _market("M6", "Under", "totals", "243.5"),
        _market("M7", "Over", "first_half_totals", "120.5"),
    ],
    begin_at="1795222800",
)

NBA_GAME_MONEYLINE_ONLY = _event(
    "POLY-2",
    "nba",
    "Hornets vs. Hawks",
    [
        _market("M8", "Hornets", "moneyline", None),
        _market("M9", "Hawks", "moneyline", None),
    ],
    begin_at="1795309200",
)

NBA_FUTURES = _event("POLY-3", "nba", "NBA: 2027 Champion", [], begin_at=None)

EPL_EVENT = _event(
    "POLY-4",
    "epl",
    "Chelsea FC vs. Leeds United FC",
    [_market("M10", "Over", "totals", "2.5")],
    begin_at="1795222800",
)

EVENTS = [
    NBA_GAME_WITH_LINES,
    NBA_GAME_MONEYLINE_ONLY,
    NBA_FUTURES,
    EPL_EVENT,
]


class TestScanNbaLines(unittest.TestCase):
    def test_ringkasan(self):
        scan = check_nba_lines.scan_nba_lines(EVENTS)
        self.assertEqual(scan["nba_events"], 3)
        self.assertEqual(scan["nba_games"], 2)
        self.assertEqual(scan["games_with_spread"], 1)
        self.assertEqual(scan["games_with_total"], 1)
        self.assertEqual(scan["games_without_spread_total"], 1)
        self.assertEqual(scan["total_spread_markets"], 2)
        # first_half_totals TIDAK dihitung sebagai total full game.
        self.assertEqual(scan["total_total_markets"], 2)
        self.assertEqual(scan["spread_lines_all"], [-2.5])
        self.assertEqual(scan["total_lines_all"], [243.5])

    def test_per_laga(self):
        scan = check_nba_lines.scan_nba_lines(EVENTS)
        game = scan["games"][0]
        self.assertEqual(game["event_id"], "POLY-1")
        self.assertEqual(game["event_title"], "Wizards vs. Bulls")
        self.assertEqual(game["tip_off"], "2026-11-21T01:00:00+00:00")
        # NBA: tandang dulu — Bulls kandang.
        self.assertEqual(game["home_team"], "Bulls")
        self.assertEqual(game["away_team"], "Wizards")
        self.assertEqual(game["n_markets"], 7)
        self.assertEqual(game["spread_markets"], 2)
        self.assertEqual(game["total_markets"], 2)
        self.assertEqual(game["spread_lines"], [-2.5])
        self.assertEqual(game["total_lines"], [243.5])
        self.assertTrue(game["has_spread"])
        self.assertTrue(game["has_total"])
        game2 = scan["games"][1]
        self.assertFalse(game2["has_spread"])
        self.assertFalse(game2["has_total"])
        self.assertEqual(game2["tip_off"], "2026-11-22T01:00:00+00:00")

    def test_kosong(self):
        scan = check_nba_lines.scan_nba_lines([])
        self.assertEqual(scan["nba_games"], 0)
        self.assertEqual(scan["games"], [])


class TestRecheckSchedule(unittest.TestCase):
    def test_tiga_dan_satu_jam_sebelum_tipoff(self):
        games = [
            {
                "event_id": "POLY-1",
                "event_title": "Wizards vs. Bulls",
                "tip_off": "2026-11-21T01:00:00+00:00",
            },
            {
                "event_id": "POLY-2",
                "event_title": "X vs. Y",
                "tip_off": None,
            },
        ]
        schedule = check_nba_lines.recheck_schedule(games)
        self.assertEqual(schedule[0]["recheck_3h_before"], "2026-11-20T22:00:00+00:00")
        self.assertEqual(schedule[0]["recheck_1h_before"], "2026-11-21T00:00:00+00:00")
        self.assertIsNone(schedule[1]["recheck_3h_before"])
        self.assertIsNone(schedule[1]["recheck_1h_before"])


class TestMain(unittest.TestCase):
    def _ok_result(self):
        return FetchResult(
            source="Jupiter Prediction API",
            tier=1,
            fetched_at="2026-11-20T16:00:00+00:00",
            ok=True,
            data=EVENTS,
            extra={
                "pages_fetched": 1,
                "events_scanned": 4,
                "scan_complete": True,
                "stopped_reason": "semua_halaman",
            },
        )

    def test_main_menulis_laporan(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "laporan.json"
            with mock.patch(
                "ingest.check_nba_lines.fetch_sports_events",
                return_value=self._ok_result(),
            ):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    code = check_nba_lines.main(["--out", str(out_path)])
            self.assertEqual(code, 0)
            report = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertTrue(report["ok"])
            self.assertEqual(report["scan"]["nba_games"], 2)
            self.assertEqual(len(report["recheck_schedule"]), 2)
            self.assertEqual(
                report["recheck_schedule"][0]["recheck_3h_before"],
                "2026-11-20T22:00:00+00:00",
            )
            self.assertIn("Wizards vs. Bulls", stdout.getvalue())
            self.assertIn("Laporan:", stdout.getvalue())

    def test_main_filter_tanggal(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "laporan.json"
            with mock.patch(
                "ingest.check_nba_lines.fetch_sports_events",
                return_value=self._ok_result(),
            ):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    code = check_nba_lines.main(
                        ["--date", "2026-11-22", "--out", str(out_path)]
                    )
            self.assertEqual(code, 0)
            report = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(report["date_filter"], "2026-11-22")
            self.assertEqual(report["scan"]["nba_games"], 1)
            self.assertEqual(
                report["scan"]["games"][0]["event_title"], "Hornets vs. Hawks"
            )

    def test_main_fetch_gagal(self):
        failed = FetchResult(
            source="Jupiter Prediction API",
            tier=1,
            fetched_at="2026-11-20T16:00:00+00:00",
            ok=False,
            error="Jupiter /events HTTP 500",
            extra={"pages_fetched": 1},
        )
        with mock.patch(
            "ingest.check_nba_lines.fetch_sports_events",
            return_value=failed,
        ):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = check_nba_lines.main([])
        self.assertEqual(code, 1)
        self.assertIn("PINDAI GAGAL", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
