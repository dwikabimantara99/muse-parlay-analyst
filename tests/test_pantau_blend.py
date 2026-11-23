"""Tes Item 5: proyeksi live memakai median pra-laga (metode "blend").

SEMUANYA offline dari fixture yang dibangun di dalam file ini
(tidak bergantung pada out/ — out/ gitignored, tes harus lulus di
checkout bersih). 0 kredit Odds API.

Latar: tiket nyata 23 Nov 2026 dipantau tanpa artefak analisis
terlampir, sehingga proyeksi jatuh ke "live_rate_only" dan goyang
(Thunder 241 -> 240 -> 228 -> 236 -> 237 -> 242 -> 227). Perbaikan:
``cli.py pantau --analysis`` menerima BANYAK file (artefak terbaru
per laga menang), median pra-laga ditempelkan ke evaluasi, dan laga
tanpa median dicatat eksplisit (tetap live-rate-only, fail-closed).

Angka acuan tes proyeksi (laga tengah, halftime DEN@CHI 23 Nov):
total berjalan 142 dalam 24 menit (laju live 5,9167 poin/menit),
median pra-laga 233 (laju 4,8542). Blend (w_live 0,5):
142 + (0,5*5,9167 + 0,5*4,8542)*24 = 271,25. Live-rate-only:
142 + 5,9167*24 = 284,0. Keduanya dihitung dari angka di atas,
bukan ditebak.
"""

import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cli
import config
from engine import live_status

CFG = config.load_playstyle()

# Laga tengah sintetis: halftime, total 142 (70 + 72), 24 menit tersisa.
_GAME_TENGAH = {
    "match_id": "DEN@CHI_2026-11-22",
    "espn_game_id": "401000000",
    "home_abbr": "CHI",
    "away_abbr": "DEN",
    "home_team": "Chicago Bulls",
    "away_team": "Denver Nuggets",
    "status": "berjalan",
    "period": 2,
    "clock_display": "0:00",
    "seconds_remaining": 1440,
    "home_score": 72,
    "away_score": 70,
    "line_scores": [],
    "stats": {},
    "fetched_at": "2026-11-23T01:00:00+00:00",
    "source": "fixture-tes",
}


def _tiket_satu_kaki(harga=79.0):
    return {
        "ticket_id": "tkt-tes-blend",
        "type": "main",
        "stake": 15.0,
        "multiplier": 3.72,
        "legs": [
            {
                "leg_id": "DEN@CHI_2026-11-22:total_under_250.5:main",
                "match_id": "DEN@CHI_2026-11-22",
                "sport": "nba",
                "market": "total_under",
                "selection": "Under 250.5 (DEN@CHI)",
                "jup_price_cents": harga,
                "status": "OK",
            }
        ],
    }


def _slate(match_id, median, generated_at):
    """Dokumen output analyze minimal (satu laga, satu median)."""
    return {
        "slate_id": "slate-tes",
        "matches": [
            {
                "match_id": "nba-2026-11-22-den-chi",
                "nba_analysis": {
                    "format": "nba_analysis",
                    "match_id": match_id,
                    "generated_at": generated_at,
                    "simulation": {"score_distribution": {"total": {"median": median}}},
                },
            }
        ],
    }


class TestProjectFinalTotalBlend(unittest.TestCase):
    def test_blend_dengan_median(self):
        hasil = live_status.project_final_total(dict(_GAME_TENGAH), 233.0, CFG)
        self.assertEqual(hasil["method"], "blend")
        self.assertAlmostEqual(hasil["projected_total"], 271.25, places=2)
        self.assertAlmostEqual(hasil["live_rate_ppm"], 142 / 24, places=4)
        self.assertAlmostEqual(hasil["pregame_rate_ppm"], 233 / 48, places=4)

    def test_live_rate_only_tanpa_median(self):
        hasil = live_status.project_final_total(dict(_GAME_TENGAH), None, CFG)
        self.assertEqual(hasil["method"], "live_rate_only")
        self.assertAlmostEqual(hasil["projected_total"], 284.0, places=2)

    def test_blend_lebih_rendah_dari_live_rate_only_saat_banjir(self):
        # Saat laga berjalan jauh di atas median pra-laga, blend menarik
        # proyeksi ke bawah (ke arah median) dibanding live-rate-only.
        dengan = live_status.project_final_total(dict(_GAME_TENGAH), 233.0, CFG)
        tanpa = live_status.project_final_total(dict(_GAME_TENGAH), None, CFG)
        self.assertLess(dengan["projected_total"], tanpa["projected_total"])

    def test_median_tidak_valid_diabaikan(self):
        hasil = live_status.project_final_total(dict(_GAME_TENGAH), -5.0, CFG)
        self.assertEqual(hasil["method"], "live_rate_only")


class TestEvaluateTicketMedian(unittest.TestCase):
    def test_median_diteruskan_ke_proyeksi(self):
        games = {"DEN@CHI_2026-11-22": dict(_GAME_TENGAH)}
        dengan = live_status.evaluate_ticket(
            _tiket_satu_kaki(),
            games,
            {"DEN@CHI_2026-11-22": 233.0},
            CFG,
        )
        tanpa = live_status.evaluate_ticket(_tiket_satu_kaki(), games, {}, CFG)
        self.assertAlmostEqual(dengan["legs"][0]["projected_total"], 271.25, places=2)
        self.assertAlmostEqual(tanpa["legs"][0]["projected_total"], 284.0, places=2)

    def test_laga_tanpa_median_tetap_live_rate_only(self):
        # Median hanya untuk laga lain -> laga ini tanpa median.
        games = {"DEN@CHI_2026-11-22": dict(_GAME_TENGAH)}
        hasil = live_status.evaluate_ticket(
            _tiket_satu_kaki(),
            games,
            {"OKC@MIA_2026-11-22": 220.0},
            CFG,
        )
        self.assertAlmostEqual(hasil["legs"][0]["projected_total"], 284.0, places=2)


class TestMuatMedianPraLaga(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _tulis(self, nama, data):
        path = self.dir / nama
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def test_banyak_file_terbaru_menang(self):
        lama = self._tulis(
            "lama.json",
            _slate("DEN@CHI_2026-11-22", 235.0, "2026-11-22T14:25:00+00:00"),
        )
        baru = self._tulis(
            "baru.json",
            _slate("DEN@CHI_2026-11-22", 233.0, "2026-11-22T21:57:00+00:00"),
        )
        median, _ = cli._muat_median_pra_laga([lama, baru])
        self.assertEqual(median, {"DEN@CHI_2026-11-22": 233.0})

    def test_file_rusak_dilewati_file_lain_tetap_dipakai(self):
        bagus = self._tulis(
            "bagus.json",
            _slate("DEN@CHI_2026-11-22", 233.0, "2026-11-22T21:57:00+00:00"),
        )
        hilang = str(self.dir / "tidak-ada.json")
        median, catatan = cli._muat_median_pra_laga([hilang, bagus])
        self.assertEqual(median, {"DEN@CHI_2026-11-22": 233.0})
        self.assertTrue(any("tidak bisa dibaca" in c for c in catatan))

    def test_median_hilang_dicatat(self):
        dokumen = _slate("DEN@CHI_2026-11-22", 233.0, "2026-11-22T21:57:00+00:00")
        dokumen["matches"][0]["nba_analysis"]["simulation"]["score_distribution"][
            "total"
        ] = {}
        path = self._tulis("tanpa-median.json", dokumen)
        median, catatan = cli._muat_median_pra_laga([path])
        self.assertEqual(median, {})
        self.assertTrue(any("DEN@CHI_2026-11-22" in c for c in catatan))


class TestParserPantauAudit(unittest.TestCase):
    def test_pantau_analysis_banyak_file(self):
        args = cli.build_parser().parse_args(
            [
                "pantau",
                "--ticket",
                "t.json",
                "--analysis",
                "a.json",
                "b.json",
            ]
        )
        self.assertEqual(args.analysis, ["a.json", "b.json"])

    def test_pantau_analysis_satu_file_tetap_list(self):
        args = cli.build_parser().parse_args(
            ["pantau", "--ticket", "t.json", "--analysis", "a.json"]
        )
        self.assertEqual(args.analysis, ["a.json"])

    def test_pantau_tanpa_analysis_none(self):
        args = cli.build_parser().parse_args(["pantau", "--ticket", "t.json"])
        self.assertIsNone(args.analysis)

    def test_audit_subcommand_ada(self):
        args = cli.build_parser().parse_args(
            ["audit", "--ticket", "t.json", "--analysis", "a.json", "b.json"]
        )
        self.assertEqual(args.func, cli.cmd_audit)
        self.assertEqual(args.ticket, "t.json")
        self.assertEqual(args.analysis, ["a.json", "b.json"])

    def test_audit_tanpa_analysis_ditolak(self):
        with (
            self.assertRaises(SystemExit),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            cli.build_parser().parse_args(["audit", "--ticket", "t.json"])


class TestCmdAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _tulis(self, nama, data):
        path = self.dir / nama
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def _analisis(self, p_model=0.86):
        return {
            "format": "nba_analysis",
            "match_id": "AAA@BBB_2026-11-22",
            "generated_at": "2026-11-22T14:24:00+00:00",
            "simulation": {
                "markets": {"total_under_240.5": p_model},
                "score_distribution": {"total": {"median": 220.0}},
            },
            "market": {
                "main_total_line": 221.5,
                "totals": [
                    {
                        "line": 240.5,
                        "side": "under",
                        "price_cents": 80.0,
                        "volume_usd": 500.0,
                        "thin": False,
                    }
                ],
            },
        }

    def _jalankan(self, tiket_path, analisis_paths, output=None):
        args = argparse.Namespace(
            ticket=tiket_path,
            analysis=analisis_paths,
            output=output,
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            kode = cli.cmd_audit(args)
        return kode, buf.getvalue()

    def test_audit_go_exit_0_dan_json_ditulis(self):
        tiket = {
            "ticket_id": "tkt-tes",
            "type": "main",
            "stake": 15.0,
            "multiplier": 2.0,
            "legs": [
                {
                    "leg_id": "AAA@BBB_2026-11-22:total_under_240.5:main",
                    "match_id": "AAA@BBB_2026-11-22",
                    "sport": "nba",
                    "market": "total_under",
                    "selection": "Under 240.5 (AAA@BBB)",
                    "jup_price_cents": 80.0,
                    "status": "OK",
                }
            ],
        }
        t_path = self._tulis("tiket.json", tiket)
        a_path = self._tulis("analisis.json", self._analisis())
        out_path = str(self.dir / "audit.json")
        kode, teks = self._jalankan(t_path, [a_path], out_path)
        self.assertEqual(kode, 0)
        self.assertIn("Verdict: GO", teks)
        hasil = json.loads(Path(out_path).read_text(encoding="utf-8"))
        self.assertEqual(hasil["format"], "ticket_audit")
        self.assertEqual(hasil["tickets"][0]["verdict"], "GO")
        # File tiket asli tidak diubah.
        self.assertEqual(json.loads(Path(t_path).read_text(encoding="utf-8")), tiket)

    def test_audit_no_go_exit_1(self):
        # P_model 0,60 < 0,65 (Utama) -> NO-GO, laporan tetap ditulis.
        tiket = {
            "ticket_id": "tkt-tes",
            "type": "main",
            "stake": 15.0,
            "multiplier": 2.0,
            "legs": [
                {
                    "leg_id": "AAA@BBB_2026-11-22:total_under_240.5:main",
                    "match_id": "AAA@BBB_2026-11-22",
                    "sport": "nba",
                    "market": "total_under",
                    "selection": "Under 240.5 (AAA@BBB)",
                    "jup_price_cents": 80.0,
                    "status": "OK",
                }
            ],
        }
        t_path = self._tulis("tiket.json", tiket)
        a_path = self._tulis("analisis.json", self._analisis(p_model=0.60))
        out_path = str(self.dir / "audit.json")
        kode, teks = self._jalankan(t_path, [a_path], out_path)
        self.assertEqual(kode, 1)
        self.assertIn("Verdict: NO-GO", teks)
        self.assertTrue(Path(out_path).exists())

    def test_audit_file_tiket_hilang_exit_2(self):
        a_path = self._tulis("analisis.json", self._analisis())
        with contextlib.redirect_stderr(io.StringIO()):
            kode, _ = self._jalankan(str(self.dir / "hilang.json"), [a_path])
        self.assertEqual(kode, 2)

    def test_audit_file_analisis_rusak_exit_2(self):
        # Fail-closed: file analisis rusak -> audit batal (exit 2).
        tiket = {
            "ticket_id": "tkt-tes",
            "type": "main",
            "stake": 15.0,
            "multiplier": 2.0,
            "legs": [],
        }
        t_path = self._tulis("tiket.json", tiket)
        with contextlib.redirect_stderr(io.StringIO()):
            kode, _ = self._jalankan(t_path, [str(self.dir / "hilang.json")])
        self.assertEqual(kode, 2)


if __name__ == "__main__":
    unittest.main()
