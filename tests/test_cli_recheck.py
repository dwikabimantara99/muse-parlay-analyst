"""Tes cli.py recheck — fetch_fresh/decide di-mock (tanpa network)."""

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import cli
from engine import nba_analysis as nba_analysis_mod


def _artefak(match_id="DET@ATL_2026-11-22"):
    """Artefak minimal yang valid vs skema nba_analysis."""
    away, home = match_id.split("@")[0], match_id.split("@")[1].split("_")[0]
    return nba_analysis_mod.minimal_nba_analysis(
        match_id=match_id,
        home_tricode=home,
        away_tricode=away,
        game_date=match_id.rsplit("_", 1)[1],
        missing=["tes"],
    )


def _laporan(verdict="GO", legs=None, action=None):
    return {
        "format": "nba_recheck",
        "format_version": 1,
        "match_id": "DET@ATL_2026-11-22",
        "analysis_generated_at": "2026-11-22T10:00:00+00:00",
        "recheck_at": "2026-11-22T12:00:00+00:00",
        "verdict": verdict,
        "resimulated": False,
        "resim_reasons": [],
        "changes": [],
        "legs": (
            legs
            if legs is not None
            else [
                {
                    "leg_id": "DET@ATL_2026-11-22:total_under_233.5:insurance",
                    "ticket": "insurance",
                    "verdict": "TETAP_OK",
                    "reasons": [],
                    "old_line": 233.5,
                    "new_line": 233.5,
                    "old_price_cents": 66.5,
                    "new_price_cents": 66.5,
                    "price_move_cents": 0.0,
                    "resimulated": False,
                    "probability_used": "model",
                    "probability_value": 0.77,
                    "kenapa_beda": {
                        "gap_points": None,
                        "triggered": False,
                        "reason_found": False,
                        "reason": None,
                    },
                }
            ]
        ),
        "anomalies": [],
        "missing": [],
        "attention": [],
        "action_required": action,
    }


def _args(analysis, match=None, out=None):
    return argparse.Namespace(analysis=str(analysis), match=match, out=out)


class TestCmdRecheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _tulis(self, nama, data):
        path = self.dir / nama
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def _jalankan(self, args):
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            kode = cli.cmd_recheck(args)
        return kode, out.getvalue(), err.getvalue()

    @mock.patch("engine.recheck.decide")
    @mock.patch("engine.recheck.fetch_fresh")
    def test_go_keluar_0_dan_laporan_ditulis(self, mock_fetch, mock_decide):
        mock_fetch.return_value = {"inputs": None}
        mock_decide.return_value = _laporan("GO")
        analisis = self._tulis("analisis.json", _artefak())
        out_path = self.dir / "recheck.json"
        kode, stdout, _ = self._jalankan(_args(analisis, out=str(out_path)))
        self.assertEqual(kode, 0)
        self.assertIn("recheck DET@ATL_2026-11-22: GO", stdout)
        self.assertIn("insurance U233.5: TETAP_OK", stdout)
        self.assertTrue(out_path.exists())
        self.assertEqual(json.loads(out_path.read_text())["verdict"], "GO")
        mock_fetch.assert_called_once()
        mock_decide.assert_called_once()

    @mock.patch("engine.recheck.decide")
    @mock.patch("engine.recheck.fetch_fresh")
    def test_kaki_tanpa_ticket_dibaca_dari_leg_id(self, mock_fetch, mock_decide):
        leg_tanpa_ticket = {
            "leg_id": "DET@ATL_2026-11-22:total_under_233.5:insurance",
            "verdict": "TETAP_OK",
            "reasons": [],
            "old_line": 233.5,
            "new_line": 233.5,
            "old_price_cents": 66.5,
            "new_price_cents": 66.5,
            "price_move_cents": 0.0,
            "resimulated": False,
            "probability_used": "model",
            "probability_value": 0.77,
            "kenapa_beda": {
                "gap_points": None,
                "triggered": False,
                "reason_found": False,
                "reason": None,
            },
        }
        mock_decide.return_value = _laporan("GO", legs=[leg_tanpa_ticket])
        analisis = self._tulis("analisis.json", _artefak())
        kode, stdout, _ = self._jalankan(
            _args(analisis, out=str(self.dir / "recheck.json"))
        )
        self.assertEqual(kode, 0)
        self.assertIn("insurance U233.5: TETAP_OK", stdout)

    @mock.patch("engine.recheck.decide")
    @mock.patch("engine.recheck.fetch_fresh")
    def test_no_go_keluar_1_laporan_tetap_ditulis(self, mock_fetch, mock_decide):
        mock_decide.return_value = _laporan(
            "NO-GO",
            legs=[
                {
                    "leg_id": "x:total_under_233.5:insurance",
                    "ticket": "insurance",
                    "verdict": "JANGAN_PASANG",
                    "reasons": ["harga bergerak 4 sen"],
                    "old_line": 233.5,
                    "new_line": 233.5,
                    "old_price_cents": 75.0,
                    "new_price_cents": 71.0,
                    "price_move_cents": -4.0,
                    "resimulated": False,
                    "probability_used": "model",
                    "probability_value": 0.77,
                    "kenapa_beda": {
                        "gap_points": None,
                        "triggered": False,
                        "reason_found": False,
                        "reason": None,
                    },
                }
            ],
            action="tunggu kabar pemain X",
        )
        analisis = self._tulis("analisis.json", _artefak())
        out_path = self.dir / "recheck.json"
        kode, stdout, _ = self._jalankan(_args(analisis, out=str(out_path)))
        self.assertEqual(kode, 1)
        self.assertIn("NO-GO", stdout)
        self.assertIn("harga bergerak 4 sen", stdout)
        self.assertIn("yang harus diubah: tunggu kabar pemain X", stdout)
        self.assertTrue(out_path.exists())

    def test_file_hilang_keluar_2(self):
        kode, _, stderr = self._jalankan(_args(self.dir / "tidak-ada.json"))
        self.assertEqual(kode, 2)
        self.assertIn("tidak bisa membaca", stderr)

    def test_json_rusak_keluar_2(self):
        path = self.dir / "rusak.json"
        path.write_text("{bukan json", encoding="utf-8")
        kode, _, stderr = self._jalankan(_args(path))
        self.assertEqual(kode, 2)
        self.assertIn("tidak bisa membaca", stderr)

    def test_bukan_analisis_maupun_slate_keluar_2(self):
        path = self._tulis("lain.json", {"foo": 1})
        kode, _, stderr = self._jalankan(_args(path))
        self.assertEqual(kode, 2)
        self.assertIn("bukan artefak nba_analysis", stderr)

    @mock.patch("engine.recheck.decide")
    @mock.patch("engine.recheck.fetch_fresh")
    def test_slate_satu_laga_tanpa_match(self, mock_fetch, mock_decide):
        mock_decide.return_value = _laporan("GO")
        slate = {
            "slate_id": "s1",
            "matches": [{"match_id": "DET@ATL_2026-11-22", "nba_analysis": _artefak()}],
        }
        path = self._tulis("slate.json", slate)
        kode, _, _ = self._jalankan(_args(path, out=str(self.dir / "recheck.json")))
        self.assertEqual(kode, 0)
        self.assertEqual(mock_fetch.call_args[0][0]["match_id"], "DET@ATL_2026-11-22")

    def test_slate_dua_laga_tanpa_match_error(self):
        slate = {
            "slate_id": "s1",
            "matches": [
                {"match_id": "DET@ATL_2026-11-22", "nba_analysis": _artefak()},
                {
                    "match_id": "BOS@NYK_2026-11-22",
                    "nba_analysis": _artefak("BOS@NYK_2026-11-22"),
                },
            ],
        }
        path = self._tulis("slate.json", slate)
        kode, _, stderr = self._jalankan(_args(path))
        self.assertEqual(kode, 2)
        self.assertIn("DET@ATL_2026-11-22", stderr)
        self.assertIn("BOS@NYK_2026-11-22", stderr)

    @mock.patch("engine.recheck.decide")
    @mock.patch("engine.recheck.fetch_fresh")
    def test_slate_match_memilih_laga_kedua(self, mock_fetch, mock_decide):
        mock_decide.return_value = _laporan("GO")
        slate = {
            "slate_id": "s1",
            "matches": [
                {"match_id": "DET@ATL_2026-11-22", "nba_analysis": _artefak()},
                {
                    "match_id": "BOS@NYK_2026-11-22",
                    "nba_analysis": _artefak("BOS@NYK_2026-11-22"),
                },
            ],
        }
        path = self._tulis("slate.json", slate)
        kode, _, _ = self._jalankan(
            _args(
                path,
                match="BOS@NYK_2026-11-22",
                out=str(self.dir / "recheck.json"),
            )
        )
        self.assertEqual(kode, 0)
        self.assertEqual(mock_fetch.call_args[0][0]["match_id"], "BOS@NYK_2026-11-22")

    def test_match_salah_pada_artefak_langsung(self):
        path = self._tulis("analisis.json", _artefak())
        kode, _, stderr = self._jalankan(_args(path, match="BOS@NYK_2026-11-22"))
        self.assertEqual(kode, 2)
        self.assertIn("bukan BOS@NYK_2026-11-22", stderr)

    @mock.patch("engine.recheck.fetch_fresh")
    def test_artefak_tidak_valid_keluar_2_tanpa_fetch(self, mock_fetch):
        buruk = _artefak()
        del buruk["legs"]
        path = self._tulis("analisis.json", buruk)
        kode, _, stderr = self._jalankan(_args(path))
        self.assertEqual(kode, 2)
        self.assertIn("tidak valid", stderr)
        mock_fetch.assert_not_called()

    @mock.patch("engine.recheck.decide")
    @mock.patch("engine.recheck.fetch_fresh")
    def test_decide_gagal_keluar_2_tanpa_laporan(self, mock_fetch, mock_decide):
        mock_decide.side_effect = ValueError("skema gagal")
        path = self._tulis("analisis.json", _artefak())
        out_path = self.dir / "recheck.json"
        kode, _, stderr = self._jalankan(_args(path, out=str(out_path)))
        self.assertEqual(kode, 2)
        self.assertIn("recheck gagal", stderr)
        self.assertFalse(out_path.exists())


if __name__ == "__main__":
    unittest.main()
