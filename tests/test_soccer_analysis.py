"""Tes engine/soccer_analysis + wiring cli.py analyze — SEMUA offline.

fetch_match_inputs dan football_sim.simulate di-stub (unittest.mock);
devig.blend, price_labels, dan validasi skema dipakai ASLI. Config
dibaca dari playstyle.yaml asli (nilai parameter TIDAK di-hardcode —
khususnya w blend 0,3 dan penalti TANPA_XG 5 poin).
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cli
import config as config_mod
from engine import soccer_analysis as sa_mod
from ingest import soccer_brain as sb_mod
from ingest.common import FetchResult, now_iso

REPO_ROOT = Path(__file__).resolve().parent.parent
CFG = config_mod.load_playstyle()

HOME = "Liverpool"
AWAY = "Manchester United"
TANGGAL = "2026-11-22"
MATCH_ID = "manchester-united@liverpool_2026-11-22"
START_TIME = "2026-11-22T16:30:00+00:00"

FIT_CONTOH = {
    "rho": -0.13,
    "avg_home_goals": 1.55,
    "avg_away_goals": 1.20,
    "league": "EPL",
    "fit_version": "CONTOH — fit menunggu persetujuan",
    "approved": False,
}
FIT_DISETUJUI = dict(FIT_CONTOH, fit_version="fit-v1", approved=True)


def _ok(source, tier, data):
    return FetchResult(
        source=source, tier=tier, fetched_at=now_iso(), ok=True, data=data
    )


def _fail(source, tier, error):
    return FetchResult(
        source=source, tier=tier, fetched_at=now_iso(), ok=False, error=error
    )


def _blok_tim(nama, attack, defence, cedera=None):
    return {
        "team": nama,
        "stats_season": {
            "played": 11,
            "w": 7,
            "d": 2,
            "l": 2,
            "goals_for_per_match": 1.9,
            "goals_against_per_match": 0.9,
        },
        "stats_last6": {
            "played": 6,
            "w": 4,
            "d": 1,
            "l": 1,
            "goals_for_per_match": 2.0,
            "goals_against_per_match": 0.8,
        },
        "form5": [],
        "home_record": {
            "played": 5,
            "w": 4,
            "d": 1,
            "l": 0,
            "gf_per_match": 2.2,
            "ga_per_match": 0.6,
        },
        "away_record": {
            "played": 6,
            "w": 3,
            "d": 1,
            "l": 2,
            "gf_per_match": 1.7,
            "ga_per_match": 1.2,
        },
        "attack": attack,
        "defence": defence,
        "injuries": cedera or [],
    }


def _inputs(n_sumber_cedera=0):
    """Dict mentah fetch_match_inputs untuk LIV-MUN."""
    return {
        "match": {
            "home_team": HOME,
            "away_team": AWAY,
            "match_date": TANGGAL,
            "season": "2026-27",
            "league": "EPL",
            "matchweek": 11,
            "kickoff": START_TIME,
        },
        "home": _blok_tim(HOME, 1.25, 1.15),
        "away": _blok_tim(AWAY, 0.95, 0.90),
        "h2h_last5": [],
        "league": {
            "avg_goals_per_team_match": 1.35,
            "n_matches": 110,
            "n_teams": 20,
        },
        "weights": {
            "season": 0.6,
            "recent": 0.4,
            "recent_matches": 6,
            "source": "config",
        },
        "injuries_status": {
            "n_sources": n_sumber_cedera,
            "confirmed": n_sumber_cedera >= 2,
            "note": "cedera tidak terkonfirmasi" if n_sumber_cedera < 2 else "ok",
        },
        "injury_sources_checked": [],
        "missing": ["injuries_tidak_terkonfirmasi"] if n_sumber_cedera < 2 else [],
        "sources": [
            {
                "data_kind": "football_results",
                "source": "Premier League (JSON resmi)",
                "tier": 1,
                "fetched_at": now_iso(),
            }
        ],
        "fetched_at": now_iso(),
    }


def _entri_slate(jup_cents, p_market=None, comparison_source=None, line=None):
    entri = {
        "market_type": "moneyline",
        "line": line,
        "outcome": "X",
        "side": "home",
        "jup_price_cents": jup_cents,
        "jup_provider": "polymarket",
        "p_market": p_market,
        "comparison_source": comparison_source,
    }
    return entri


def _slate_match():
    """Entri MatchData 2b LIV-MUN (harga jup.ag + p_market per P1-P4)."""
    return {
        "match_id": "football-2026-11-22-liverpool-manchester-united",
        "sport": "football",
        "fetched_at": now_iso(),
        "status": "HOLD",
        "start_time": START_TIME,
        "market_prices": {
            "moneyline_home": _entri_slate(55.0, 0.54, "espn_odds_devig"),
            "moneyline_draw": _entri_slate(23.0, 0.23, "espn_odds_devig"),
            "moneyline_away": _entri_slate(23.0, 0.23, "espn_odds_devig"),
            "total_over_2.5": dict(
                _entri_slate(64.0, 0.645, "kalshi", line=2.5),
                market_type="totals",
                side="over",
            ),
            "total_under_2.5": dict(
                _entri_slate(37.0, 0.355, "kalshi", line=2.5),
                market_type="totals",
                side="under",
            ),
            "both_teams_to_score_yes": dict(
                _entri_slate(64.0, None, None),
                market_type="both_teams_to_score",
                side="yes",
            ),
            # Spread tidak dibuat kakinya (di luar lingkup langkah 5).
            "spread_home_-1.5": dict(
                _entri_slate(40.0, 0.40, "kalshi", line=-1.5),
                market_type="spreads",
                side="home",
            ),
        },
    }


def _sim_palsu(markets=None):
    """Dict hasil football_sim.simulate (kontrak markets nyata pekerja B).

    Kunci 1X2: home_win/draw/away_win; total: total_over/under_0_5
    s.d. _8_5 (garis pakai garis bawah); score_distribution:
    home_points/away_points (mean/median) + total.
    """
    return {
        "match_id": MATCH_ID,
        "sport": "football",
        "iterations": 1000,
        "generated_at": now_iso(),
        "engine": {"name": "dixon-coles-fixture", "seed": 7, "version": "fixture-1"},
        "markets": (
            markets
            if markets is not None
            else {
                "home_win": 0.60,
                "draw": 0.22,
                "away_win": 0.18,
                "total_over_2_5": 0.62,
                "total_under_2_5": 0.38,
                "btts_yes": 0.58,
                "btts_no": 0.42,
            }
        ),
        "score_distribution": {
            "total": {"median": 2.7, "mean": 2.75, "std": 1.6},
            "home_points": {"mean": 1.6, "median": 2.0},
            "away_points": {"mean": 1.15, "median": 1.0},
        },
        "inputs_summary": {},
    }


def _file_fit_bersarang(status="MENUNGGU persetujuan user", liga="EPL"):
    """Isi out/fit_soccer_params.json pekerja A (format bersarang)."""
    return {
        "generated_at": "2026-11-22T15:03:27.019320+00:00",
        "method": "MLE Dixon-Coles",
        "status_persetujuan": status,
        "leagues": {
            liga: {
                "kode_file": "E0",
                "musim_fit": ["2022/23", "2023/24", "2024/25"],
                "pooled": {
                    "rho": -0.003,
                    "avg_home_goals": 1.6892,
                    "avg_away_goals": 1.4062,
                    "home_advantage_ratio": 1.2013,
                },
                "live_parsial": {
                    "rho": 0.091,
                    "avg_home_goals": 1.5639,
                    "avg_away_goals": 1.2266,
                },
                "per_musim": {},
            }
        },
    }


def _tulis_temp_json(data):
    """Tulis dict ke file temp; kembalikan path (pemanggil menghapus)."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        json.dump(data, tmp)
        return tmp.name


class TestMuatFit(unittest.TestCase):
    def test_argumen_contoh(self):
        params, status, alasan = sa_mod._muat_fit(FIT_CONTOH)
        self.assertIsNone(alasan)
        self.assertEqual(params["rho"], -0.13)
        self.assertEqual(status["source"], "argumen")
        self.assertEqual(status["status"], "menunggu_persetujuan")
        self.assertFalse(status["approved"])

    def test_argumen_disetujui(self):
        _, status, _ = sa_mod._muat_fit(FIT_DISETUJUI)
        self.assertEqual(status["status"], "disetujui")
        self.assertTrue(status["approved"])

    def test_argumen_tidak_valid(self):
        _, _, alasan = sa_mod._muat_fit({"rho": "bukan-angka"})
        self.assertIsNotNone(alasan)
        self.assertIn("tidak_valid", alasan)

    def test_file_tidak_ada(self):
        _, status, alasan = sa_mod._muat_fit(
            None, fit_path="/tmp/tidak-ada-fit-soccer-test.json"
        )
        self.assertIsNone(alasan)
        self.assertEqual(status["status"], "tidak_ada")

    def test_file_dibaca(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(FIT_DISETUJUI, tmp)
            path = tmp.name
        params, status, alasan = sa_mod._muat_fit(None, fit_path=path)
        self.assertIsNone(alasan)
        self.assertEqual(status["source"], "out/fit_soccer_params.json")
        self.assertTrue(status["approved"])
        Path(path).unlink()

    def test_file_json_rusak(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            tmp.write("{bukan json")
            path = tmp.name
        _, _, alasan = sa_mod._muat_fit(None, fit_path=path)
        self.assertIn("json_rusak", alasan)
        Path(path).unlink()

    def test_file_bersarang_pakai_pooled_menunggu(self):
        path = _tulis_temp_json(_file_fit_bersarang())
        params, status, alasan = sa_mod._muat_fit(None, fit_path=path)
        Path(path).unlink()
        self.assertIsNone(alasan)
        # POOLED yang dipakai (bukan live_parsial yang noisy).
        self.assertEqual(params["rho"], -0.003)
        self.assertEqual(params["avg_home_goals"], 1.6892)
        self.assertEqual(params["avg_away_goals"], 1.4062)
        self.assertEqual(params["league"], "EPL")
        self.assertIn("pooled EPL 2022/23", status["fit_version"])
        self.assertEqual(status["source"], "out/fit_soccer_params.json")
        self.assertEqual(status["status"], "menunggu_persetujuan")
        self.assertFalse(status["approved"])

    def test_file_bersarang_disetujui(self):
        path = _tulis_temp_json(_file_fit_bersarang(status="DISETUJUI user 2026-11-22"))
        _, status, alasan = sa_mod._muat_fit(None, fit_path=path)
        Path(path).unlink()
        self.assertIsNone(alasan)
        self.assertEqual(status["status"], "disetujui")
        self.assertTrue(status["approved"])

    def test_file_bersarang_belum_disetujui_bukan_disetujui(self):
        # "BELUM DISETUJUI" mengandung kata DISETUJUI tapi TIDAK
        # diawali itu -> belum disetujui (aturan startswith).
        path = _tulis_temp_json(_file_fit_bersarang(status="BELUM DISETUJUI user"))
        _, status, _ = sa_mod._muat_fit(None, fit_path=path)
        Path(path).unlink()
        self.assertFalse(status["approved"])

    def test_file_bersarang_liga_tidak_ada(self):
        path = _tulis_temp_json(_file_fit_bersarang(liga="LaLiga"))
        _, _, alasan = sa_mod._muat_fit(None, fit_path=path, liga="EPL")
        Path(path).unlink()
        self.assertIn("liga_EPL_tidak_ada", alasan)

    def test_file_bersarang_tanpa_pooled(self):
        data = _file_fit_bersarang()
        del data["leagues"]["EPL"]["pooled"]
        path = _tulis_temp_json(data)
        _, _, alasan = sa_mod._muat_fit(None, fit_path=path)
        Path(path).unlink()
        self.assertIn("pooled_EPL_tidak_ada", alasan)


class TestValidasiArgumen(unittest.TestCase):
    def test_argumen_tidak_valid(self):
        with self.assertRaises(ValueError):
            sa_mod.build_soccer_analysis("", AWAY, TANGGAL)
        with self.assertRaises(ValueError):
            sa_mod.build_soccer_analysis(HOME, AWAY, "22-11-2026")
        with self.assertRaises(ValueError):
            sa_mod.build_soccer_analysis(HOME, AWAY, TANGGAL, seed=1.5)
        with self.assertRaises(ValueError):
            sa_mod.build_soccer_analysis(HOME, AWAY, TANGGAL, iterations=0)


class TestBuildSoccerAnalysis(unittest.TestCase):
    def _build(self, fit_params=FIT_CONTOH, **kwargs):
        kwargs.setdefault("cfg", CFG)
        kwargs.setdefault("fit_path", "/tmp/tidak-ada-fit-soccer-test.json")
        with (
            mock.patch.object(
                sb_mod,
                "fetch_match_inputs",
                return_value=_ok("soccer_brain", 1, _inputs()),
            ),
            mock.patch.object(
                sa_mod.football_sim_mod, "simulate", return_value=_sim_palsu()
            ),
        ):
            return sa_mod.build_soccer_analysis(
                HOME,
                AWAY,
                TANGGAL,
                slate_match=_slate_match(),
                fit_params=fit_params,
                **kwargs,
            )

    def test_jalur_bahagia_hold_karena_fit_dan_b2(self):
        art = self._build()
        self.assertEqual(art["status"], "HOLD")
        self.assertEqual(art["format"], "soccer_analysis")
        self.assertEqual(art["match_id"], MATCH_ID)
        self.assertIn("TANPA_XG", art["labels"])
        self.assertNotIn("MODEL_ONLY", art["labels"])
        self.assertIn("fit_belum_disetujui", art["missing"])
        self.assertIn("cedera_kurang_dari_2_sumber", art["missing"])
        self.assertEqual(
            art["fit_status"]["fit_version"], "CONTOH — fit menunggu persetujuan"
        )
        # 3 moneyline + 2 total + 1 BTTS = 6 kaki (spread tidak dibuat).
        self.assertEqual(len(art["legs"]), 6)
        self.assertEqual(
            [leg["market_type"] for leg in art["legs"]],
            [
                "moneyline_home",
                "moneyline_draw",
                "moneyline_away",
                "total_over",
                "total_under",
                "btts_yes",
            ],
        )
        for leg in art["legs"]:
            self.assertTrue(leg["no_xg"])
            self.assertTrue(leg["banned_from_insurance"])
            self.assertEqual(leg["threshold_penalty_points"], 5)
            self.assertEqual(leg["ticket"], "main")
            self.assertTrue(leg["meets"])
        self.assertIsNone(sa_mod.validate_soccer_analysis(art))

    def test_hitungan_kaki_moneyline_home(self):
        art = self._build()
        leg = next(
            kaki for kaki in art["legs"] if kaki["market_type"] == "moneyline_home"
        )
        # p_model 0,60; p_market 0,54; w=0,3 -> 0,3*0,6+0,7*0,54 = 0,558.
        self.assertAlmostEqual(leg["p_model"], 0.60)
        self.assertAlmostEqual(leg["p_market"], 0.54)
        self.assertAlmostEqual(leg["p_final"], 0.3 * 0.60 + 0.7 * 0.54, places=9)
        self.assertEqual(leg["comparison_source"], "espn_odds_devig")
        self.assertEqual(leg["price_cents"], 55.0)
        self.assertEqual(leg["jup_estimated_cents"], 55.0)
        # EV = 0,558*(100/55)-1 = +1,45% -> WAJAR.
        ev = (0.558 * (100.0 / 55.0) - 1.0) * 100.0
        self.assertAlmostEqual(leg["ev_pct"], ev, places=6)
        self.assertEqual(leg["price_label"], "WAJAR")
        self.assertFalse(leg["model_only"])

    def test_kaki_btts_model_only(self):
        art = self._build()
        leg = next(kaki for kaki in art["legs"] if kaki["market_type"] == "btts_yes")
        self.assertIsNone(leg["p_market"])
        self.assertIsNone(leg["comparison_source"])
        self.assertTrue(leg["model_only"])
        # MODEL_ONLY: p_final = p_model.
        self.assertEqual(leg["p_final"], leg["p_model"])

    def test_kaki_tanpa_p_model(self):
        sim = _sim_palsu(markets={"home_win": 0.6})
        with (
            mock.patch.object(
                sb_mod,
                "fetch_match_inputs",
                return_value=_ok("soccer_brain", 1, _inputs()),
            ),
            mock.patch.object(sa_mod.football_sim_mod, "simulate", return_value=sim),
        ):
            art = sa_mod.build_soccer_analysis(
                HOME,
                AWAY,
                TANGGAL,
                slate_match=_slate_match(),
                cfg=CFG,
                fit_params=FIT_CONTOH,
            )
        by_type = {leg["market_type"]: leg for leg in art["legs"]}
        self.assertTrue(by_type["moneyline_home"]["meets"])
        self.assertFalse(by_type["moneyline_draw"]["meets"])
        self.assertEqual(by_type["moneyline_draw"]["reason"], "p_model_tidak_ada")
        self.assertIsNone(by_type["moneyline_draw"]["p_final"])

    def test_sim_dipanggil_dengan_match_id_dan_date(self):
        # football_sim.simulate WAJIB punya match.match_id + match.date
        # (ValueError bila hilang) — builder harus mengisinya.
        with (
            mock.patch.object(
                sb_mod,
                "fetch_match_inputs",
                return_value=_ok("soccer_brain", 1, _inputs()),
            ),
            mock.patch.object(
                sa_mod.football_sim_mod, "simulate", return_value=_sim_palsu()
            ) as mock_sim,
        ):
            sa_mod.build_soccer_analysis(
                HOME,
                AWAY,
                TANGGAL,
                slate_match=_slate_match(),
                cfg=CFG,
                fit_params=FIT_CONTOH,
            )
        mock_sim.assert_called_once()
        inputs_sim = mock_sim.call_args.args[0]
        self.assertEqual(inputs_sim["match"]["match_id"], MATCH_ID)
        self.assertEqual(inputs_sim["match"]["date"], TANGGAL)
        self.assertEqual(inputs_sim["home"]["name"], HOME)
        self.assertEqual(inputs_sim["home"]["attack"], 1.25)
        params_sim = mock_sim.call_args.args[1]
        self.assertEqual(params_sim["rho"], -0.13)
        self.assertEqual(params_sim["league"], "EPL")

    def test_garis_total_di_luar_sim_tidak_memenuhi(self):
        # Sim hanya punya garis 1.5/2.5/3.5 — garis 4.5 dari slate
        # tetap dibuat kakinya tapi meets=false (jujur, bukan ditebak).
        slate = _slate_match()
        slate["market_prices"]["total_over_4.5"] = dict(
            _entri_slate(20.0, 0.20, "kalshi", line=4.5),
            market_type="totals",
            side="over",
        )
        slate["market_prices"]["total_under_4.5"] = dict(
            _entri_slate(81.0, 0.80, "kalshi", line=4.5),
            market_type="totals",
            side="under",
        )
        with (
            mock.patch.object(
                sb_mod,
                "fetch_match_inputs",
                return_value=_ok("soccer_brain", 1, _inputs()),
            ),
            mock.patch.object(
                sa_mod.football_sim_mod, "simulate", return_value=_sim_palsu()
            ),
        ):
            art = sa_mod.build_soccer_analysis(
                HOME,
                AWAY,
                TANGGAL,
                slate_match=slate,
                cfg=CFG,
                fit_params=FIT_CONTOH,
            )
        kaki_45 = [k for k in art["legs"] if k.get("line") == 4.5]
        self.assertEqual(len(kaki_45), 2)
        for kaki in kaki_45:
            self.assertFalse(kaki["meets"])
            self.assertEqual(kaki["reason"], "p_model_tidak_ada")
            self.assertIsNone(kaki["p_model"])
        # Garis 2.5 tetap memenuhi.
        kaki_25 = [k for k in art["legs"] if k.get("line") == 2.5]
        self.assertTrue(all(k["meets"] for k in kaki_25))

    def test_builder_membaca_file_fit_bersarang(self):
        path = _tulis_temp_json(_file_fit_bersarang())
        with (
            mock.patch.object(
                sb_mod,
                "fetch_match_inputs",
                return_value=_ok("soccer_brain", 1, _inputs()),
            ),
            mock.patch.object(
                sa_mod.football_sim_mod, "simulate", return_value=_sim_palsu()
            ) as mock_sim,
        ):
            art = sa_mod.build_soccer_analysis(
                HOME,
                AWAY,
                TANGGAL,
                slate_match=_slate_match(),
                cfg=CFG,
                fit_params=None,
                fit_path=path,
            )
        Path(path).unlink()
        self.assertEqual(art["status"], "HOLD")
        self.assertIn("pooled EPL 2022/23", art["fit_status"]["fit_version"])
        self.assertFalse(art["fit_status"]["approved"])
        # Parameter pooled diteruskan ke sim (bukan live_parsial).
        params_sim = mock_sim.call_args.args[1]
        self.assertEqual(params_sim["rho"], -0.003)
        self.assertEqual(params_sim["avg_home_goals"], 1.6892)

    def test_ok_bila_fit_disetujui_dan_b2_terpenuhi(self):
        inputs = _inputs(n_sumber_cedera=2)
        inputs["missing"] = []
        with (
            mock.patch.object(
                sb_mod,
                "fetch_match_inputs",
                return_value=_ok("soccer_brain", 1, inputs),
            ),
            mock.patch.object(
                sa_mod.football_sim_mod, "simulate", return_value=_sim_palsu()
            ),
        ):
            art = sa_mod.build_soccer_analysis(
                HOME,
                AWAY,
                TANGGAL,
                slate_match=_slate_match(),
                cfg=CFG,
                fit_params=FIT_DISETUJUI,
            )
        self.assertEqual(art["status"], "OK")
        self.assertIsNone(sa_mod.validate_soccer_analysis(art))

    def test_fit_tidak_ada(self):
        with (
            mock.patch.object(
                sb_mod,
                "fetch_match_inputs",
                return_value=_ok("soccer_brain", 1, _inputs()),
            ),
            mock.patch.object(
                sa_mod.football_sim_mod, "simulate", return_value=_sim_palsu()
            ),
        ):
            art = sa_mod.build_soccer_analysis(
                HOME,
                AWAY,
                TANGGAL,
                slate_match=_slate_match(),
                cfg=CFG,
                fit_params=None,
                fit_path="/tmp/tidak-ada-fit-soccer-test.json",
            )
        self.assertEqual(art["status"], "DATA_INCOMPLETE")
        self.assertIn("fit_menunggu_persetujuan", art["missing"])
        # Inputs tetap terlampir (tahap yang berhasil tidak hilang).
        self.assertIsNotNone(art["inputs"])
        self.assertIsNone(sa_mod.validate_soccer_analysis(art))

    def test_fit_tidak_valid(self):
        art = self._build(fit_params={"rho": 1})
        self.assertEqual(art["status"], "DATA_INCOMPLETE")
        self.assertTrue(any("fit_argumen_tidak_valid" in m for m in art["missing"]))

    def test_sim_belum_tersedia(self):
        with (
            mock.patch.object(
                sb_mod,
                "fetch_match_inputs",
                return_value=_ok("soccer_brain", 1, _inputs()),
            ),
            mock.patch.object(
                sa_mod.football_sim_mod,
                "simulate",
                side_effect=NotImplementedError("belum tersedia"),
            ),
        ):
            art = sa_mod.build_soccer_analysis(
                HOME,
                AWAY,
                TANGGAL,
                slate_match=_slate_match(),
                cfg=CFG,
                fit_params=FIT_CONTOH,
            )
        self.assertEqual(art["status"], "DATA_INCOMPLETE")
        self.assertIn("simulasi_belum_tersedia", art["missing"])

    def test_start_time_fallback_ke_kickoff_inputs(self):
        # MatchData 2b tidak punya field start_time — bila pemanggil
        # tidak memberi start_time, builder memakai kickoff fixture
        # PL dari inputs.
        slate = _slate_match()
        del slate["start_time"]
        with (
            mock.patch.object(
                sb_mod,
                "fetch_match_inputs",
                return_value=_ok("soccer_brain", 1, _inputs()),
            ),
            mock.patch.object(
                sa_mod.football_sim_mod, "simulate", return_value=_sim_palsu()
            ),
        ):
            art = sa_mod.build_soccer_analysis(
                HOME,
                AWAY,
                TANGGAL,
                slate_match=slate,
                cfg=CFG,
                fit_params=FIT_CONTOH,
            )
        self.assertEqual(art["start_time"], START_TIME)

    def test_tanpa_slate(self):
        with mock.patch.object(
            sb_mod, "fetch_match_inputs", return_value=_ok("soccer_brain", 1, _inputs())
        ):
            art = sa_mod.build_soccer_analysis(
                HOME, AWAY, TANGGAL, slate_match=None, cfg=CFG, fit_params=FIT_CONTOH
            )
        self.assertEqual(art["status"], "DATA_INCOMPLETE")
        self.assertIn("slate_match_tidak_ada", art["missing"])

    def test_inputs_gagal(self):
        with mock.patch.object(
            sb_mod,
            "fetch_match_inputs",
            return_value=_fail("soccer_brain", 1, "semua_sumber_gagal"),
        ):
            art = sa_mod.build_soccer_analysis(
                HOME,
                AWAY,
                TANGGAL,
                slate_match=_slate_match(),
                cfg=CFG,
                fit_params=FIT_CONTOH,
            )
        self.assertEqual(art["status"], "DATA_INCOMPLETE")
        self.assertTrue(any("inputs_gagal" in m for m in art["missing"]))

    def test_attack_tidak_lengkap(self):
        inputs = _inputs()
        inputs["home"]["attack"] = None
        with (
            mock.patch.object(
                sb_mod,
                "fetch_match_inputs",
                return_value=_ok("soccer_brain", 1, inputs),
            ),
            mock.patch.object(
                sa_mod.football_sim_mod, "simulate", return_value=_sim_palsu()
            ),
        ):
            art = sa_mod.build_soccer_analysis(
                HOME,
                AWAY,
                TANGGAL,
                slate_match=_slate_match(),
                cfg=CFG,
                fit_params=FIT_CONTOH,
            )
        self.assertEqual(art["status"], "DATA_INCOMPLETE")
        self.assertIn("attack_defence_tidak_lengkap", art["missing"])

    def test_blok_market(self):
        art = self._build()
        market = art["market"]
        self.assertEqual(market["source"], "jup_ag_via_slate")
        self.assertEqual(market["n_markets"], 7)
        self.assertEqual(market["moneyline"]["home_cents"], 55.0)
        self.assertEqual(market["btts_cents"], 64.0)
        self.assertEqual(len(market["totals"]), 1)
        self.assertEqual(market["totals"][0]["line"], 2.5)
        self.assertEqual(market["totals"][0]["over_cents"], 64.0)
        self.assertEqual(market["totals"][0]["under_cents"], 37.0)

    def test_price_snapshots(self):
        art = self._build()
        self.assertEqual(art["price_snapshots"]["moneyline_home_home"]["cents"], 55.0)
        self.assertEqual(art["price_snapshots"]["total_under_2.5"]["cents"], 37.0)
        self.assertEqual(art["price_snapshots"]["btts_yes_yes"]["cents"], 64.0)

    def test_label_model_only_bila_semua_tanpa_pasar(self):
        slate = _slate_match()
        for entri in slate["market_prices"].values():
            entri["p_market"] = None
            entri["comparison_source"] = None
        with (
            mock.patch.object(
                sb_mod,
                "fetch_match_inputs",
                return_value=_ok("soccer_brain", 1, _inputs()),
            ),
            mock.patch.object(
                sa_mod.football_sim_mod, "simulate", return_value=_sim_palsu()
            ),
        ):
            art = sa_mod.build_soccer_analysis(
                HOME,
                AWAY,
                TANGGAL,
                slate_match=slate,
                cfg=CFG,
                fit_params=FIT_CONTOH,
            )
        self.assertIn("MODEL_ONLY", art["labels"])

    def test_minimal_valid(self):
        art = sa_mod.minimal_soccer_analysis(MATCH_ID, HOME, AWAY, TANGGAL, ["alasan"])
        self.assertEqual(art["status"], "DATA_INCOMPLETE")
        self.assertIsNone(sa_mod.validate_soccer_analysis(art))

    def test_config_no_xg_hilang(self):
        cfg = {"no_xg": {}}
        with mock.patch.object(
            sb_mod, "fetch_match_inputs", return_value=_ok("soccer_brain", 1, _inputs())
        ):
            art = sa_mod.build_soccer_analysis(
                HOME,
                AWAY,
                TANGGAL,
                slate_match=_slate_match(),
                cfg=cfg,
                fit_params=FIT_CONTOH,
            )
        self.assertEqual(art["status"], "DATA_INCOMPLETE")
        self.assertTrue(any("config_no_xg_hilang" in m for m in art["missing"]))


class TestLampirkanSoccerAnalysisCli(unittest.TestCase):
    def test_lampirkan_ke_laga_bola(self):
        artefak = sa_mod.minimal_soccer_analysis(MATCH_ID, HOME, AWAY, TANGGAL, ["tes"])
        matches_2b = [{"match_id": "m1", "sport": "football"}]
        entries = [
            {
                "match_id": "m1",
                "home": HOME,
                "away": AWAY,
                "start_time": START_TIME,
                "league": "Premier League",
            }
        ]
        with mock.patch.object(
            sa_mod, "build_soccer_analysis", return_value=artefak
        ) as mock_build:
            cli._lampirkan_soccer_analysis(matches_2b, entries, TANGGAL)
        mock_build.assert_called_once()
        _, kwargs = mock_build.call_args
        self.assertEqual(kwargs["slate_match"], matches_2b[0])
        self.assertEqual(matches_2b[0]["soccer_analysis"], artefak)

    def test_builder_gagal_tetap_minimal(self):
        matches_2b = [{"match_id": "m1", "sport": "football"}]
        entries = [
            {
                "match_id": "m1",
                "home": HOME,
                "away": AWAY,
                "start_time": START_TIME,
                "league": "Premier League",
            }
        ]
        with mock.patch.object(
            sa_mod, "build_soccer_analysis", side_effect=RuntimeError("meledak")
        ):
            cli._lampirkan_soccer_analysis(matches_2b, entries, TANGGAL)
        art = matches_2b[0]["soccer_analysis"]
        self.assertEqual(art["status"], "DATA_INCOMPLETE")
        self.assertTrue(any("builder_gagal" in m for m in art["missing"]))

    def test_tanpa_entri_slate_dilewati(self):
        matches_2b = [{"match_id": "m-tanpa-entri", "sport": "football"}]
        cli._lampirkan_soccer_analysis(matches_2b, [], TANGGAL)
        self.assertNotIn("soccer_analysis", matches_2b[0])


if __name__ == "__main__":
    unittest.main()
