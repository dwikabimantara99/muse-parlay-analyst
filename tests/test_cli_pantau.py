"""Tes cli.py pantau (Tahap 3 Langkah 4) — TANPA network.

Fungsi fetch/evaluasi modul pekerja A (ingest/live_nba) + pekerja B
(engine/live_status) di-stub dengan menambal atribut modul aslinya
(save/restore manual di setUp/tearDown) — mengikuti signature asli
yang terverifikasi dari modul tersebut. Fetcher baseline BBRef +
config juga di-stub dengan cara yang sama.
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
import config as config_mod
from engine import live_status as live_status_mod
from ingest import bbref
from ingest import live_nba as live_nba_mod
from ingest.common import FetchResult

LIVE_CFG = {
    "live": {
        "status_margin_aman_points": 6.0,
        "status_margin_waspada_points": 2.0,
        "anomaly_min_minutes_elapsed": 12,
        "anomaly_fg3_rate_multiplier": 1.5,
        "anomaly_ft_rate_multiplier": 1.5,
        "anomaly_scoring_rate_multiplier": 1.15,
        "ot_risk_margin_points": 3,
        "ot_risk_minutes_remaining": 2.0,
    }
}

BASELINE_DATA = [
    {
        "tricode": "DET",
        "team": "Detroit Pistons",
        "games": 15,
        "fg3a_per_game": 35.47,
        "fta_per_game": 24.60,
    },
    {
        "tricode": "ATL",
        "team": "Atlanta Hawks",
        "games": 16,
        "fg3a_per_game": 42.88,
        "fta_per_game": 20.38,
    },
]


def _game(
    home_score=50,
    away_score=50,
    home_fg3a=10,
    away_fg3a=10,
    home_fta=5,
    away_fta=5,
    status="berjalan",
    seconds_remaining=1440,
    period=2,
    match_id="DET@ATL_2026-11-22",
):
    return {
        "match_id": match_id,
        "espn_game_id": "401810001",
        "home_abbr": "ATL",
        "away_abbr": "DET",
        "home_team": "Atlanta Hawks",
        "away_team": "Detroit Pistons",
        "status": status,
        "period": period,
        "clock_display": "12:00",
        "seconds_remaining": seconds_remaining,
        "home_score": home_score,
        "away_score": away_score,
        "line_scores": None,
        "stats": {
            "ATL": {
                "fg3_made": 5,
                "fg3_attempted": home_fg3a,
                "ft_made": 4,
                "ft_attempted": home_fta,
            },
            "DET": {
                "fg3_made": 4,
                "fg3_attempted": away_fg3a,
                "ft_made": 4,
                "ft_attempted": away_fta,
            },
        },
        "fetched_at": "2026-11-22T00:00:00+00:00",
        "source": "ESPN",
    }


def _ticket(legs):
    return {
        "ticket_id": "tkt-test-utm",
        "type": "Utama",
        "stake": 10.0,
        "multiplier": 3.0,
        "legs": legs,
    }


def _leg(match_id="DET@ATL_2026-11-22", line=237.5):
    return {
        "leg_id": f"{match_id}:total_under_{line}:main",
        "match_id": match_id,
        "sport": "nba",
        "market": "total_under",
        "selection": f"Under {line} ({match_id.split('_')[0]})",
        "p_final": 0.77,
        "status": "OK",
    }


def _ok(data):
    return FetchResult("ESPN", 1, "2026-11-22T00:00:00+00:00", True, data=data)


def _gagal(error):
    return FetchResult("ESPN", 1, "2026-11-22T00:00:00+00:00", False, error=error)


def _project_stub(live_game, pregame_median_total=None, cfg=None):
    menit = (2880 - live_game["seconds_remaining"]) / 60.0
    total = live_game["home_score"] + live_game["away_score"]
    live_ppm = total / menit if menit > 0 else 0.0
    return {
        "projected_total": live_ppm * 48.0,
        "method": "laju_live_x_48 (stub tes)",
        "live_rate_ppm": live_ppm,
        "pregame_rate_ppm": (
            pregame_median_total / 48.0 if pregame_median_total is not None else None
        ),
        "minutes_elapsed": menit,
        "minutes_remaining": 48.0 - menit,
        "ot_risk": False,
        "notes": [],
    }


def _evaluate_leg_stub(leg, live_game, pregame_median_total=None, cfg=None):
    import re

    if live_game is None:
        return {
            "leg_id": leg.get("leg_id"),
            "match_id": leg.get("match_id"),
            "selection": leg.get("selection"),
            "status": "DATA_INCOMPLETE",
            "projected_total": None,
            "margin_points": None,
        }
    cocok = re.search(r"Under ([\d.]+)", leg.get("selection", ""))
    garis = float(cocok.group(1)) if cocok else 0.0
    proj = _project_stub(live_game, pregame_median_total, cfg)
    proyeksi = proj["projected_total"]
    margin = garis - proyeksi if proyeksi is not None else None
    status = "AMAN"
    if margin is not None and margin < 2.0:
        status = "TERANCAM"
    return {
        "leg_id": leg.get("leg_id"),
        "match_id": leg.get("match_id"),
        "selection": leg.get("selection"),
        "status": status,
        "projected_total": proyeksi,
        "margin_points": margin,
    }


def _evaluate_ticket_stub(ticket, live_games, pregame_medians=None, cfg=None):
    games = live_games or {}
    medians = pregame_medians or {}
    legs = [
        _evaluate_leg_stub(
            kaki,
            games.get(kaki.get("match_id")),
            medians.get(kaki.get("match_id")),
            cfg,
        )
        for kaki in ticket.get("legs", [])
    ]
    status = (
        "TERANCAM"
        if any(leg["status"] in ("TERANCAM", "KALAH") for leg in legs)
        else "AMAN"
    )
    return {
        "ticket_id": ticket.get("ticket_id"),
        "type": ticket.get("type"),
        "status": status,
        "legs": legs,
        "notes": [],
    }


def _render_stub(ticket_result, anomalies_by_match=None):
    baris = [
        f"Tiket {ticket_result.get('type')} "
        f"({ticket_result.get('ticket_id')}): {ticket_result.get('status')}"
    ]
    for leg in ticket_result.get("legs", []):
        baris.append(f"  {leg.get('selection')}: {leg.get('status')}")
        for anom in (anomalies_by_match or {}).get(leg.get("match_id"), []):
            teks = anom.get("description") if isinstance(anom, dict) else str(anom)
            baris.append(f"  Anomali: {teks}")
    return "\n".join(baris)


class TestCmdPantau(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self._saved = []
        self._games_by_date = {"2026-11-22": [_game()]}
        self._fail_dates: set[str] = set()
        self._tambal(config_mod, "load_playstyle", lambda *a, **k: dict(LIVE_CFG))
        self._tambal(
            bbref,
            "fetch_team_shooting_baselines",
            lambda **k: FetchResult(
                "Basketball-Reference",
                2,
                "2026-11-22T00:00:00+00:00",
                True,
                data=[dict(b) for b in BASELINE_DATA],
                extra={"season": 2027, "n_teams": 2},
            ),
        )
        self._tambal(live_nba_mod, "fetch_live_games", self._fetch_games)
        self._tambal(live_nba_mod, "fetch_game_stats", self._fetch_stats)
        self._tambal(live_status_mod, "project_final_total", _project_stub)
        self._tambal(live_status_mod, "evaluate_leg", _evaluate_leg_stub)
        self._tambal(live_status_mod, "evaluate_ticket", _evaluate_ticket_stub)
        self._tambal(live_status_mod, "render_live_status", _render_stub)

    def tearDown(self):
        for modul, nama, asli in reversed(self._saved):
            setattr(modul, nama, asli)
        self.tmp.cleanup()

    def _tambal(self, modul, nama, pengganti):
        self._saved.append((modul, nama, getattr(modul, nama)))
        setattr(modul, nama, pengganti)

    def _fetch_games(self, tanggal=None, client=None):
        if tanggal in self._fail_dates:
            return _gagal("http_500: espn gagal")
        return _ok([dict(g) for g in self._games_by_date.get(tanggal, [])])

    def _fetch_stats(self, espn_game_id, client=None):
        for games in self._games_by_date.values():
            for game in games:
                if str(game.get("espn_game_id")) == str(espn_game_id):
                    return _ok(dict(game.get("stats") or {}))
        return _gagal("game tidak ditemukan")

    def _tulis(self, nama, data):
        path = self.tmp_path / nama
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def _jalankan(self, **kwargs):
        args = argparse.Namespace(
            ticket=kwargs.get("ticket"),
            analysis=kwargs.get("analysis"),
            match=kwargs.get("match"),
            date=kwargs.get("date"),
            output=kwargs.get("output"),
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            kode = cli.cmd_pantau(args)
        return kode, buf.getvalue()

    def test_tiket_aman_exit_0(self):
        path = self._tulis("t.json", _ticket([_leg()]))
        kode, out = self._jalankan(ticket=path)
        self.assertEqual(kode, 0)
        self.assertIn("AMAN", out)
        self.assertNotIn("PERINGATAN", out)

    def test_kaki_terancam_exit_1(self):
        # Skor 122 dalam 24 menit -> proyeksi 244 > garis 237.5.
        self._games_by_date = {"2026-11-22": [_game(home_score=62, away_score=60)]}
        path = self._tulis("t.json", _ticket([_leg()]))
        kode, out = self._jalankan(ticket=path)
        self.assertEqual(kode, 1)
        self.assertIn("TERANCAM", out)

    def test_anomali_saja_exit_1(self):
        # Skor aman (proyeksi 200) tapi hujan 3PT: 60x 3PA/24 mnt.
        self._games_by_date = {"2026-11-22": [_game(home_fg3a=30, away_fg3a=30)]}
        path = self._tulis("t.json", _ticket([_leg()]))
        kode, out = self._jalankan(ticket=path)
        self.assertEqual(kode, 1)
        self.assertIn("Hujan 3 angka", out)

    def test_file_tiket_tidak_ada_exit_2(self):
        kode, _ = self._jalankan(ticket=str(self.tmp_path / "hilang.json"))
        self.assertEqual(kode, 2)

    def test_file_tiket_tidak_valid_exit_2(self):
        path = self._tulis("t.json", {"bukan": "tiket"})
        kode, _ = self._jalankan(ticket=path)
        self.assertEqual(kode, 2)

    def test_semua_feed_gagal_exit_2(self):
        self._fail_dates = {"2026-11-22"}
        path = self._tulis("t.json", _ticket([_leg()]))
        kode, _ = self._jalankan(ticket=path)
        self.assertEqual(kode, 2)

    def test_bentuk_pasangan_racik(self):
        data = {
            "format": "tickets",
            "game_date": "2026-11-22",
            "insurance": None,
            "main": _ticket([_leg()]),
        }
        path = self._tulis("t.json", data)
        kode, out = self._jalankan(ticket=path)
        self.assertEqual(kode, 0)
        self.assertIn("Utama", out)

    def test_bentuk_daftar_tickets(self):
        data = {"tickets": [_ticket([_leg()])]}
        path = self._tulis("t.json", data)
        kode, _ = self._jalankan(ticket=path)
        self.assertEqual(kode, 0)

    def test_match_filter_artefak(self):
        # Dua kaki, dua laga; --match memilih satu. Laga kedua tidak
        # ada di scoreboard -> tanpa filter akan DATA_INCOMPLETE.
        tiket = _ticket(
            [
                _leg("DET@ATL_2026-11-22", 237.5),
                _leg("BOS@GSW_2026-11-22", 219.5),
            ]
        )
        path = self._tulis("t.json", tiket)
        kode, out = self._jalankan(ticket=path, match="DET@ATL_2026-11-22")
        self.assertEqual(kode, 0)
        self.assertIn("237.5", out)
        self.assertNotIn("219.5", out)

    def test_match_filter_slate(self):
        tiket = _ticket([_leg("DET@ATL_2026-11-22", 237.5)])
        path = self._tulis("t.json", tiket)
        kode, _ = self._jalankan(ticket=path, match="nba-2026-11-22-det-atl")
        self.assertEqual(kode, 0)

    def test_match_tidak_ada_di_tiket_exit_2(self):
        path = self._tulis("t.json", _ticket([_leg()]))
        kode, _ = self._jalankan(ticket=path, match="OKC@MIA_2026-11-22")
        self.assertEqual(kode, 2)

    def test_laga_hilang_data_incomplete_exit_1(self):
        # Laga tidak ada di scoreboard: kaki DATA_INCOMPLETE, pantauan
        # tetap berjalan tapi exit 1 — tidak diketahui ≠ aman
        # (fail-closed, keputusan koordinator langkah 4).
        self._games_by_date = {"2026-11-22": []}
        path = self._tulis("t.json", _ticket([_leg()]))
        kode, out = self._jalankan(ticket=path)
        self.assertEqual(kode, 1)
        self.assertIn("DATA_INCOMPLETE", out)
        self.assertIn("PERINGATAN", out)

    def test_output_json_ditulis(self):
        out_path = str(self.tmp_path / "pantau.json")
        path = self._tulis("t.json", _ticket([_leg()]))
        kode, _ = self._jalankan(ticket=path, output=out_path)
        self.assertEqual(kode, 0)
        laporan = json.loads(Path(out_path).read_text(encoding="utf-8"))
        self.assertEqual(laporan["format"], "live_monitor")
        self.assertEqual(len(laporan["tickets"]), 1)
        self.assertIn("DET@ATL_2026-11-22", laporan["matches"])
        self.assertFalse(laporan["has_threatened_leg"])
        self.assertFalse(laporan["has_anomaly"])


if __name__ == "__main__":
    unittest.main()
