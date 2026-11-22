"""Tes cli.py laporan / tanya / racik (Tahap 3 Langkah 3, offline).

Matematika peracik diuji di tests/test_ticket_composer.py; di sini
hanya plumbing CLI (baca file, exit code, tulis output) + render/tanya
pada fixture nyata. compose_tickets di-mock untuk jalur racik.
"""

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import cli

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "recheck"
ANALYSIS = FIXTURES / "det_atl_analysis.json"
MATCH_ID = "DET@ATL_2026-11-22"


def _recheck_minimal():
    return {
        "format": "nba_recheck",
        "format_version": 1,
        "match_id": MATCH_ID,
        "analysis_generated_at": "2026-11-22T10:00:00+00:00",
        "recheck_at": "2026-11-22T12:00:00+00:00",
        "verdict": "GO",
        "resimulated": False,
        "resim_reasons": [],
        "changes": [],
        "legs": [],
        "anomalies": [],
        "missing": [],
        "attention": [],
        "action_required": None,
    }


class TestKumpulkanNbaAnalysis(unittest.TestCase):
    def test_artefak_langsung(self):
        data = json.loads(ANALYSIS.read_text(encoding="utf-8"))
        got, error = cli._kumpulkan_nba_analysis(data)
        self.assertIsNone(error)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["match_id"], MATCH_ID)

    def test_output_analyze(self):
        data = json.loads(ANALYSIS.read_text(encoding="utf-8"))
        out = {"matches": [{"match_id": MATCH_ID, "nba_analysis": data}]}
        got, error = cli._kumpulkan_nba_analysis(out)
        self.assertIsNone(error)
        self.assertEqual(len(got), 1)

    def test_bukan_analisis(self):
        got, error = cli._kumpulkan_nba_analysis({"format": "lain"})
        self.assertIsNone(got)
        self.assertIn("bukan artefak", error)


class TestAmbilNbaAnalysis(unittest.TestCase):
    def test_match_id_artefak_diterima(self):
        # --match menerima match_id artefak ("DET@ATL_..."), bukan
        # hanya match_id slate ("nba-2026-11-22-det-atl").
        data = json.loads(ANALYSIS.read_text(encoding="utf-8"))
        out = {
            "matches": [{"match_id": "nba-2026-11-22-det-atl", "nba_analysis": data}]
        }
        art, error = cli._ambil_nba_analysis(out, MATCH_ID)
        self.assertIsNone(error)
        self.assertEqual(art["match_id"], MATCH_ID)

    def test_match_id_slate_tetap_diterima(self):
        data = json.loads(ANALYSIS.read_text(encoding="utf-8"))
        out = {
            "matches": [{"match_id": "nba-2026-11-22-det-atl", "nba_analysis": data}]
        }
        art, error = cli._ambil_nba_analysis(out, "nba-2026-11-22-det-atl")
        self.assertIsNone(error)
        self.assertEqual(art["match_id"], MATCH_ID)


class TestCmdLaporan(unittest.TestCase):
    def _args(self, **kw):
        ns = argparse.Namespace(
            analysis=str(ANALYSIS),
            match=None,
            recheck=None,
            out=None,
            json=False,
        )
        ns.__dict__.update(kw)
        return ns

    def test_teks_stdout(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.cmd_laporan(self._args())
        self.assertEqual(code, 0)
        self.assertIn("Laporan Laga NBA", buf.getvalue())

    def test_json(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.cmd_laporan(self._args(json=True))
        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["format"], "nba_report")
        self.assertEqual(data["match_id"], MATCH_ID)

    def test_out_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "laporan.txt")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.cmd_laporan(self._args(out=out))
            self.assertEqual(code, 0)
            self.assertIn("Laporan Laga NBA", Path(out).read_text(encoding="utf-8"))

    def test_dengan_recheck(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec = Path(tmp) / "recheck.json"
            rec.write_text(json.dumps(_recheck_minimal()), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.cmd_laporan(self._args(recheck=str(rec)))
            self.assertEqual(code, 0)
            self.assertIn("Laporan Laga NBA", buf.getvalue())

    def test_file_tidak_ada(self):
        buf_err = io.StringIO()
        with redirect_stderr(buf_err):
            code = cli.cmd_laporan(self._args(analysis="/tmp/tidak-ada.json"))
        self.assertEqual(code, 2)


class TestCmdTanya(unittest.TestCase):
    def _args(self, pertanyaan, **kw):
        ns = argparse.Namespace(
            analysis=str(ANALYSIS), match=None, pertanyaan=pertanyaan
        )
        ns.__dict__.update(kw)
        return ns

    def test_kenapa_total(self):
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(io.StringIO()):
            code = cli.cmd_tanya(self._args("Kenapa totalnya 219?"))
        self.assertEqual(code, 0)
        self.assertTrue(len(buf.getvalue().strip()) > 0)

    def test_tidak_mengerti(self):
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(io.StringIO()):
            code = cli.cmd_tanya(self._args("xyz tak jelas"))
        self.assertEqual(code, 0)
        self.assertIn("tidak mengerti", buf.getvalue())

    def test_file_tidak_ada(self):
        buf_err = io.StringIO()
        with redirect_stderr(buf_err):
            code = cli.cmd_tanya(
                self._args("Kenapa totalnya 219?", analysis="/tmp/tidak-ada.json")
            )
        self.assertEqual(code, 2)


class TestCmdRacik(unittest.TestCase):
    def _args(self, **kw):
        ns = argparse.Namespace(
            analysis=[str(ANALYSIS)],
            recheck=None,
            stake_total=20.0,
            out=None,
        )
        ns.__dict__.update(kw)
        return ns

    def _hasil(self, insurance=True, main=True):
        tiket = {
            "ticket_id": "tkt-tes",
            "type": "Asuransi",
            "stake": 10.0,
            "multiplier": 2.3,
            "legs": [],
        }
        return {
            "insurance": dict(tiket) if insurance else None,
            "insurance_reason": None if insurance else "tidak ada kaki",
            "main": (
                dict(tiket, ticket_id="tkt-tes-2", type="Utama") if main else None
            ),
            "main_reason": None if main else "tidak ada kaki",
            "warnings": ["recheck sudah basi"],
            "summary": "Ringkasan tes.",
        }

    def test_sukses_menulis_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "tickets.json")
            with mock.patch(
                "engine.ticket_composer.compose_tickets",
                return_value=self._hasil(),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = cli.cmd_racik(self._args(out=out))
            self.assertEqual(code, 0)
            data = json.loads(Path(out).read_text(encoding="utf-8"))
            self.assertEqual(data["format"], "tickets")
            self.assertIsNotNone(data["insurance"])
            self.assertIsNotNone(data["main"])
            self.assertIn("Ringkasan tes.", buf.getvalue())
            self.assertIn("PERINGATAN: recheck sudah basi", buf.getvalue())

    def test_keduanya_none_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "tickets.json")
            with mock.patch(
                "engine.ticket_composer.compose_tickets",
                return_value=self._hasil(insurance=False, main=False),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = cli.cmd_racik(self._args(out=out))
            self.assertEqual(code, 1)

    def test_file_tidak_ada(self):
        buf_err = io.StringIO()
        with redirect_stderr(buf_err):
            code = cli.cmd_racik(self._args(analysis=["/tmp/tidak-ada.json"]))
        self.assertEqual(code, 2)

    def test_recheck_bukan_laporan(self):
        with tempfile.TemporaryDirectory() as tmp:
            bukan = Path(tmp) / "bukan.json"
            bukan.write_text(json.dumps({"format": "lain"}), encoding="utf-8")
            buf_err = io.StringIO()
            with redirect_stderr(buf_err):
                code = cli.cmd_racik(self._args(recheck=[str(bukan)]))
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
