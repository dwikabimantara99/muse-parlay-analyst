"""Tes cli.py analyze — build_slate di-mock (tanpa network)."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cli
from ingest import slate as slate_mod

REPO_ROOT = Path(__file__).resolve().parent.parent


def _slate(confirmed=True, matches=None):
    return {
        "slate_id": "slate-test-001",
        "created_at_wib": "2026-11-20T18:30:00+07:00",
        "source": "manual",
        "mode": "standard",
        "confirmed_by_user": confirmed,
        "stake_split": {"insurance": 0.5, "main": 0.5},
        "matches": (
            matches
            if matches is not None
            else [
                {
                    "match_id": "nba-2026-11-20-lal-bos",
                    "sport": "nba",
                    "league": "NBA",
                    "home": "Lakers",
                    "away": "Celtics",
                    "start_time": "2026-11-20T20:00:00+07:00",
                },
                {
                    "match_id": "epl-2026-11-21-ars-che",
                    "sport": "football",
                    "league": "Premier League",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "start_time": "2026-11-21T02:00:00+07:00",
                },
            ]
        ),
    }


def _fake_slate(sport, date):
    return {
        "slate_id": f"slate-{sport}-{date}",
        "sport": sport,
        "slate_date": date,
        "generated_at": "2026-11-20T16:00:00+00:00",
        "matches": [
            {
                "match_id": f"{sport}-m1",
                "sport": sport,
                "status": "OK",
                "labels": [],
            }
        ],
        "summary": {
            "matches": 1,
            "ok": 1,
            "data_incomplete": 0,
            "hold": 0,
            "model_only": 0,
            "tanpa_xg": 1 if sport == "football" else 0,
        },
        "odds_api": {"calls": 1, "credits_used": 1},
    }


class TestCliAnalyze(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_slate(self, slate):
        path = self.tmp_path / "slate.json"
        path.write_text(json.dumps(slate), encoding="utf-8")
        return path

    def test_input_tidak_valid_exit_1(self):
        bad = self.tmp_path / "bad.json"
        bad.write_text('{"slate_id": "x"}', encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            code = cli.main(["analyze", "--input", str(bad)])
        self.assertEqual(code, 1)

    def test_json_rusak_exit_1(self):
        bad = self.tmp_path / "bad.json"
        bad.write_text("{bukan json", encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            code = cli.main(["analyze", "--input", str(bad)])
        self.assertEqual(code, 1)

    def test_file_hilang_exit_1(self):
        with redirect_stdout(io.StringIO()):
            code = cli.main(["analyze", "--input", str(self.tmp_path / "hilang.json")])
        self.assertEqual(code, 1)

    def test_confirmed_false_exit_1(self):
        path = self._write_slate(_slate(confirmed=False))
        with redirect_stdout(io.StringIO()):
            code = cli.main(["analyze", "--input", str(path)])
        self.assertEqual(code, 1)

    def test_confirmed_hilang_exit_1(self):
        slate = _slate()
        del slate["confirmed_by_user"]
        path = self._write_slate(slate)
        with redirect_stdout(io.StringIO()):
            code = cli.main(["analyze", "--input", str(path)])
        self.assertEqual(code, 1)

    def test_sukses_gabung_per_sport(self):
        path = self._write_slate(_slate())
        out = self.tmp_path / "analysis.json"
        calls = []

        def fake_build(sport, date, matches=None, **kwargs):
            calls.append((sport, date, kwargs.get("league")))
            return _fake_slate(sport, date)

        with mock.patch.object(slate_mod, "build_slate", side_effect=fake_build):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = cli.main(["analyze", "--input", str(path), "--out", str(out)])
        self.assertEqual(code, 0)
        # Dikelompokkan per sport; tanggal dari start_time laga pertama.
        self.assertEqual(
            sorted(calls),
            [
                ("football", "2026-11-21", "EPL"),
                ("nba", "2026-11-20", None),
            ],
        )
        output = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(output["slate_id"], "slate-test-001")
        self.assertEqual(len(output["matches"]), 2)
        self.assertEqual(output["summary"]["matches"], 2)
        self.assertEqual(output["summary"]["ok"], 2)
        self.assertEqual(output["summary"]["tanpa_xg"], 1)
        self.assertEqual(output["odds_api"], {"calls": 2, "credits_used": 2})
        text = stdout.getvalue()
        self.assertIn("2 laga", text)
        self.assertIn("TANPA_XG: 1 laga", text)
        self.assertIn("Odds API: 2 panggilan, 2 kredit", text)

    def test_tanggal_nba_dikonversi_ke_eastern(self):
        # 2026-11-21T08:00 WIB = 2026-11-20T20:00 EST: tanggal NBA harus
        # 2026-11-20 (stats.nba.com memakai tanggal Eastern), sedangkan
        # bola tetap memakai tanggal start_time apa adanya (2026-11-21).
        matches = [
            {
                "match_id": "nba-x",
                "sport": "nba",
                "league": "NBA",
                "home": "Lakers",
                "away": "Celtics",
                "start_time": "2026-11-21T08:00:00+07:00",
            },
            {
                "match_id": "epl-x",
                "sport": "football",
                "league": "Premier League",
                "home": "Arsenal",
                "away": "Chelsea",
                "start_time": "2026-11-21T08:00:00+07:00",
            },
        ]
        path = self._write_slate(_slate(matches=matches))
        out = self.tmp_path / "analysis.json"
        calls = []

        def fake_build(sport, date, matches=None, **kwargs):
            calls.append((sport, date))
            return _fake_slate(sport, date)

        with (
            mock.patch.object(slate_mod, "build_slate", side_effect=fake_build),
            redirect_stdout(io.StringIO()),
        ):
            code = cli.main(["analyze", "--input", str(path), "--out", str(out)])
        self.assertEqual(code, 0)
        self.assertEqual(
            sorted(calls),
            [("football", "2026-11-21"), ("nba", "2026-11-20")],
        )

    def test_out_default(self):
        path = self._write_slate(_slate())
        with (
            mock.patch.object(
                slate_mod,
                "build_slate",
                side_effect=lambda sport, date, **k: _fake_slate(sport, date),
            ),
            redirect_stdout(io.StringIO()),
        ):
            code = cli.main(["analyze", "--input", str(path)])
        self.assertEqual(code, 0)
        default_out = REPO_ROOT / "out" / "analysis_slate-test-001.json"
        self.assertTrue(default_out.exists())
        default_out.unlink()

    def test_build_gagal_exit_1(self):
        path = self._write_slate(_slate())
        with (
            mock.patch.object(
                slate_mod,
                "build_slate",
                side_effect=ValueError("config rusak"),
            ),
            redirect_stdout(io.StringIO()),
        ):
            code = cli.main(["analyze", "--input", str(path)])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
