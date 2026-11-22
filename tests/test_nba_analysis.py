"""Tes engine/nba_analysis + penyambungan cli.py analyze — SEMUA offline.

fetch_match_inputs, fetch_event_by_slug, dan fetch_total_markets
di-stub (unittest.mock); parse_event_ladders, nba_sim.simulate
(kecuali tes yang men-stub-nya secara eksplisit), cushion, devig,
price_labels, dan anomaly dipakai ASLI. Config dibaca dari
playstyle.yaml asli (nilai parameter TIDAK di-hardcode di sini —
khususnya parameter simulasi hasil adopsi rolling v7).
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

import jsonschema

import cli
import config as config_mod
from engine import nba_analysis as nba_analysis_mod
from ingest import nba_brain as nba_brain_mod
from ingest import slate as slate_mod
from ingest.common import FetchResult, now_iso

REPO_ROOT = Path(__file__).resolve().parent.parent
CFG = config_mod.load_playstyle()

HOME = "ATL"
AWAY = "DET"
TANGGAL = "2026-11-22"
MATCH_ID = "DET@ATL_2026-11-22"
START_TIME = "2026-11-23T07:00:00+07:00"

SUMBER_PDF = "Official NBA Injury Report"
SUMBER_ESPN = "ESPN injuries"


def _ok(source, tier, data):
    return FetchResult(
        source=source, tier=tier, fetched_at=now_iso(), ok=True, data=data
    )


def _fail(source, tier, error):
    return FetchResult(
        source=source, tier=tier, fetched_at=now_iso(), ok=False, error=error
    )


def _blok_tim(tricode, nama, off, deff, pace, cedera=None):
    """Satu blok tim kontrak nba_brain (cukup untuk simulasi nyata)."""
    return {
        "tricode": tricode,
        "team": nama,
        "stats_season": {
            "off_rtg": off,
            "def_rtg": deff,
            "net_rtg": off - deff,
            "pace": pace,
        },
        "stats_last10": {
            "off_rtg": off + 1.0,
            "def_rtg": deff - 1.0,
            "net_rtg": off - deff + 2.0,
            "pace": pace + 1.0,
        },
        "form5": [],
        "home_record": {"w": 5, "l": 3, "ppg": 110.0, "opp_ppg": 108.0},
        "road_record": {"w": 4, "l": 4, "ppg": 109.0, "opp_ppg": 109.0},
        "rest_days": 1,
        "back_to_back": False,
        "altitude_home": False,
        "players": [
            {
                "player": "Bintang Satu",
                "bpm": 4.0,
                "mp_per_game": 32.0,
                "team_tricode": tricode,
            },
            {
                "player": "Bintang Dua",
                "bpm": 2.0,
                "mp_per_game": 28.0,
                "team_tricode": tricode,
            },
        ],
        "injuries": cedera or [],
    }


def _inputs(n_sumber_cedera=2, stats_rusak=False):
    """Dict mentah fetch_match_inputs untuk DET@ATL."""
    cedera_home = [
        {
            "player": "Bintang Dua",
            "status": "OUT",
            "team_tricode": HOME,
            "sources": [SUMBER_PDF, SUMBER_ESPN][:n_sumber_cedera],
        }
    ]
    home = _blok_tim(HOME, "Atlanta Hawks", 114.0, 112.0, 100.0, cedera_home)
    away = _blok_tim(AWAY, "Detroit Pistons", 113.0, 113.0, 99.0)
    if stats_rusak:
        home["stats_season"]["off_rtg"] = None
    sources = [
        {
            "data_kind": "nba_team_advanced_season",
            "source": "stats.nba.com",
            "tier": 1,
            "fetched_at": now_iso(),
        },
        {
            "data_kind": "nba_injuries",
            "source": SUMBER_PDF,
            "tier": 1,
            "fetched_at": now_iso(),
        },
    ]
    if n_sumber_cedera >= 2:
        sources.append(
            {
                "data_kind": "nba_injuries",
                "source": SUMBER_ESPN,
                "tier": 2,
                "fetched_at": now_iso(),
            }
        )
    return {
        "match": {
            "home_tricode": HOME,
            "away_tricode": AWAY,
            "game_date": TANGGAL,
            "season": "2026-27",
        },
        "home": home,
        "away": away,
        "h2h_last5": [],
        "tournament": None,
        "league": {"avg_pace": 99.5, "avg_off_rtg": 113.0},
        "missing": ["tournament_flag_tidak_dapat_ditentukan"],
        "sources": sources,
        "fetched_at": now_iso(),
    }


def _pasar_total(garis, harga_over, volume, pakai_book=True):
    """Satu pasar total Gamma (Over/Under)."""
    pasar = {
        "id": f"tot-{garis}",
        "question": f"Detroit Pistons vs. Atlanta Hawks: O/U {garis}",
        "sportsMarketType": "totals",
        "outcomes": ["Over", "Under"],
        "outcomePrices": [str(harga_over), str(round(1.0 - harga_over, 3))],
        "bestBid": None,
        "bestAsk": None,
        "volume": volume,
        "liquidity": 1000.0,
        "active": True,
        "closed": False,
    }
    if pakai_book:
        pasar["bestBid"] = str(round(harga_over - 0.005, 3))
        pasar["bestAsk"] = str(round(harga_over + 0.005, 3))
    return pasar


def _pasar_spread(tim, lawan, garis, harga, volume):
    """Satu pasar spread Gamma."""
    return {
        "id": f"spr-{tim}-{garis}",
        "question": f"Spread: {tim} ({garis:+g})",
        "sportsMarketType": "spreads",
        "outcomes": [tim, lawan],
        "outcomePrices": [str(harga), str(round(1.0 - harga, 3))],
        "bestBid": str(round(harga - 0.005, 3)),
        "bestAsk": str(round(harga + 0.005, 3)),
        "volume": volume,
        "liquidity": 1000.0,
        "active": True,
        "closed": False,
    }


def _event_gamma(garis_total=None, dengan_spread=True):
    """Satu event Gamma DET@ATL (moneyline + spread + total)."""
    if garis_total is None:
        garis_total = [225.5, 229.5, 233.5, 237.5, 241.5, 245.5, 249.5, 253.5]
    # Harga Over turun seiring garis naik; garis utama 225.5 paling cair.
    harga_over = {
        225.5: 0.52,
        229.5: 0.44,
        233.5: 0.335,
        237.5: 0.245,
        241.5: 0.17,
        245.5: 0.115,
        249.5: 0.075,
        253.5: 0.045,
    }
    volume = {
        225.5: 41964.0,
        229.5: 1200.0,
        233.5: 11.0,
        237.5: 9.0,
        241.5: 8.0,
        245.5: 7.0,
        249.5: 6.0,
        253.5: 5.0,
    }
    markets = [
        {
            "id": "ml-1",
            "question": "Detroit Pistons vs. Atlanta Hawks",
            "sportsMarketType": "moneyline",
            "outcomes": ["Detroit Pistons", "Atlanta Hawks"],
            "outcomePrices": ["0.41", "0.59"],
            "bestBid": "0.40",
            "bestAsk": "0.42",
            "volume": 50000.0,
            "liquidity": 5000.0,
            "active": True,
            "closed": False,
        }
    ]
    if dengan_spread:
        markets.append(
            _pasar_spread("Atlanta Hawks", "Detroit Pistons", -5.5, 0.52, 10000.0)
        )
        markets.append(
            _pasar_spread("Detroit Pistons", "Atlanta Hawks", 5.5, 0.48, 9000.0)
        )
    for garis in garis_total:
        # Garis jauh tipis: tanpa book (harga dari outcomePrices saja).
        markets.append(
            _pasar_total(
                garis, harga_over[garis], volume[garis], pakai_book=garis <= 229.5
            )
        )
    return {
        "slug": "nba-det-atl-2026-11-22",
        "title": "Detroit Pistons vs. Atlanta Hawks",
        "teams": [
            {"name": "Detroit Pistons", "ordering": "away"},
            {"name": "Atlanta Hawks", "ordering": "home"},
        ],
        "markets": markets,
    }


def _pasar_kalshi_total(garis, bid, ask):
    """Satu pasar total Kalshi (Over saja; Under = komplemen)."""
    return {
        "market_ticker": f"KXNBATOTAL-DETATL-{garis:g}",
        "event_ticker": "KXNBATOTAL-DETATL",
        "title": f"Full Game: Over {garis:g} points scored",
        "league": "nba",
        "market_type": "total",
        "home_team": "Atlanta Hawks",
        "away_team": "Detroit Pistons",
        "line": garis,
        "side": "over",
        "yes_bid_dollars": str(bid),
        "yes_ask_dollars": str(ask),
        "expiration_time": "2026-11-23T02:00:00Z",
    }


def _sim_stub(pasar=None, median=219.0, p74=232.0, p75=233.0):
    """Dict simulasi stub (valid vs simulation.schema.json).

    Nilai default = contoh final DET@ATL pasca-regenerasi (median 219,
    p74 232, ML kandang 59,1%) — lihat LAPORAN-TAHAP-3-LANGKAH-1B.md.
    """
    markets = {"moneyline_home": 0.591, "moneyline_away": 0.409}
    markets.update(pasar or {})
    return {
        "match_id": MATCH_ID,
        "sport": "nba",
        "iterations": 100000,
        "generated_at": "2026-11-22T13:28:18+00:00",
        "engine": {"name": "nba_sim", "version": "1.1.0", "seed": 7},
        "markets": markets,
        "inputs_summary": {
            "home_tricode": HOME,
            "away_tricode": AWAY,
            "game_date": TANGGAL,
        },
        "score_distribution": {
            "margin": {
                "mean": 3.0,
                "std": 14.0,
                "median": 3.0,
                "p5": -20.0,
                "p25": -6.0,
                "p75": 12.0,
                "p95": 26.0,
            },
            "total": {
                "mean": 219.5,
                "std": 19.0,
                "median": median,
                "p5": 189.0,
                "p25": 207.0,
                "p74": p74,
                "p75": p75,
                "p95": 251.0,
            },
            "home_points": {"mean": 111.0, "median": 111.0},
            "away_points": {"mean": 108.0, "median": 108.0},
            "ot_probability": 0.03,
        },
        "squad_scenarios": [],
    }


_SLATE_MATCH = {
    "match_id": "nba-2026-11-22-det-atl",
    "sport": "nba",
    "fetched_at": "2026-11-22T12:00:00+00:00",
    "status": "OK",
    "market_prices": {
        "moneyline_home": {"jup_price_cents": 59.0},
        "moneyline_away": {"jup_price_cents": 41.0},
    },
}


def _skema_nba_analysis():
    return json.loads(
        (REPO_ROOT / "schemas" / "nba_analysis.schema.json").read_text(encoding="utf-8")
    )


class _BasisTes(unittest.TestCase):
    """Helper patch fetch untuk builder."""

    def _patch_fetch(self, inputs=None, event=None, kalshi=None, sim=None):
        """Patch ketiga fetcher (+ sim bila diberikan); kembalikan patcher list.

        Default: inputs 2 sumber cedera, event tangga penuh, Kalshi
        tanpa garis cocok (MODEL_ONLY), sim ASLI (iterations kecil).
        """
        patchers = []
        hasil_inputs = (
            inputs
            if isinstance(inputs, FetchResult)
            else _ok(nba_brain_mod.SOURCE, nba_brain_mod.TIER, inputs or _inputs())
        )
        patchers.append(
            mock.patch.object(
                nba_brain_mod, "fetch_match_inputs", return_value=hasil_inputs
            )
        )
        hasil_event = (
            event
            if isinstance(event, FetchResult)
            else _ok("Polymarket CLOB", 2, event or _event_gamma())
        )
        patchers.append(
            mock.patch(
                "ingest.polymarket.fetch_event_by_slug", return_value=hasil_event
            )
        )
        hasil_kalshi = (
            kalshi
            if isinstance(kalshi, FetchResult)
            else _ok("Kalshi API", 2, kalshi if kalshi is not None else [])
        )
        patchers.append(
            mock.patch("ingest.kalshi.fetch_total_markets", return_value=hasil_kalshi)
        )
        if sim is not None:
            patchers.append(mock.patch("engine.nba_sim.simulate", return_value=sim))
        for patcher in patchers:
            patcher.start()
        self.addCleanup(lambda: [p.stop() for p in patchers])

    def _bangun(self, **kwargs):
        """Panggil builder dengan default tes (sim nyata, iterasi kecil)."""
        kwargs.setdefault("cfg", CFG)
        kwargs.setdefault("seed", 7)
        kwargs.setdefault("iterations", 200)
        kwargs.setdefault("slate_match", _SLATE_MATCH)
        kwargs.setdefault("start_time", START_TIME)
        return nba_analysis_mod.build_nba_analysis(HOME, AWAY, TANGGAL, **kwargs)


class TestArtefakLengkap(_BasisTes):
    def test_pipeline_sim_nyata_status_ok_dan_valid_vs_skema(self):
        self._patch_fetch()
        artefak = self._bangun()
        jsonschema.validate(instance=artefak, schema=_skema_nba_analysis())
        self.assertEqual(artefak["format"], "nba_analysis")
        self.assertEqual(artefak["format_version"], 1)
        self.assertEqual(artefak["match_id"], MATCH_ID)
        self.assertEqual(artefak["status"], "OK")
        self.assertEqual(artefak["simulation"]["match_id"], MATCH_ID)
        self.assertEqual(artefak["market"]["main_total_line"], 225.5)
        self.assertEqual(artefak["market"]["main_total_volume_usd"], 41964.0)
        self.assertEqual(artefak["market"]["moneyline_jup"]["home_cents"], 59.0)
        self.assertEqual(artefak["market"]["moneyline_jup"]["away_cents"], 41.0)
        self.assertEqual(artefak["injuries"]["n_sources"], 2)
        self.assertEqual(artefak["injuries"]["confirmed_both"], ["Bintang Dua"])
        kinds = {s["kind"] for s in artefak["sources"]}
        self.assertIn("nba_team_advanced_season", kinds)
        self.assertIn("polymarket_ladder", kinds)
        self.assertIn("kalshi_total_markets", kinds)
        # Dua kaki: Asuransi + Utama.
        self.assertEqual(len(artefak["legs"]), 2)
        self.assertEqual(
            [leg["ticket"] for leg in artefak["legs"]], ["insurance", "main"]
        )
        for leg in artefak["legs"]:
            self.assertTrue(leg["meets"])
            self.assertIsNotNone(leg["p_model"])
            self.assertIsNone(leg["p_market"])  # Kalshi kosong -> MODEL_ONLY
            self.assertIsNone(leg["comparison_source"])
            self.assertEqual(leg["p_final"], leg["p_model"])
            self.assertIsNotNone(leg["price_label"])
            kunci = f"total_under_{leg['line']:g}"
            self.assertIn(kunci, artefak["price_snapshots"])

    def test_garis_kaki_memenuhi_aturan_cushion(self):
        # Properti (bukan hardcode garis): garis Asuransi = garis tangga
        # terkecil >= max(p74, garis market + 8); Utama = terkecil >=
        # max(median, garis market) + 8 (spread 5,5 > 2,5).
        self._patch_fetch()
        artefak = self._bangun()
        dist = artefak["simulation"]["score_distribution"]["total"]
        garis_under = sorted(
            {e["line"] for e in artefak["market"]["totals"] if e["side"] == "under"}
        )
        required_asuransi = max(dist["p74"], 225.5 + 8.0)
        harap_asuransi = min(g for g in garis_under if g >= required_asuransi)
        required_utama = max(dist["median"], 225.5) + 8.0
        harap_utama = min(g for g in garis_under if g >= required_utama)
        self.assertEqual(artefak["legs"][0]["line"], harap_asuransi)
        self.assertEqual(artefak["legs"][1]["line"], harap_utama)

    def test_sim_dipanggil_dua_pass_dengan_garis_tangga_plus_median(self):
        sim = _sim_stub({"total_under_233.5": 0.77, "total_under_219": 0.5})
        self._patch_fetch(sim=sim)
        with mock.patch("engine.nba_sim.simulate", return_value=sim) as mock_sim:
            self._bangun(iterations=None, seed=7)
        self.assertEqual(mock_sim.call_count, 2)
        # Pass 1: lines=None (default median); pass 2: semua garis Under
        # tangga + garis median 219.
        self.assertIsNone(mock_sim.call_args_list[0].kwargs.get("lines"))
        garis_pass2 = mock_sim.call_args_list[1].kwargs["lines"]["totals"]
        self.assertIn(219.0, garis_pass2)
        for garis in (225.5, 229.5, 233.5, 237.5, 241.5, 245.5, 249.5, 253.5):
            self.assertIn(garis, garis_pass2)

    def test_tanpa_cfg_memakai_playstyle_yaml(self):
        self._patch_fetch()
        artefak = nba_analysis_mod.build_nba_analysis(
            HOME,
            AWAY,
            TANGGAL,
            slate_match=_SLATE_MATCH,
            start_time=START_TIME,
            seed=7,
            iterations=200,
        )
        self.assertEqual(artefak["status"], "OK")


class TestContoh1b(_BasisTes):
    def test_asuransi_233_5_di_66_5_sen(self):
        # Contoh final 1b (regenerasi): median 219, p74 232, garis
        # market 225,5 -> lantai market 233,5 yang mengikat.
        sim = _sim_stub(
            {
                "total_under_233.5": 0.77,
                "total_under_237.5": 0.83,
                "total_under_219": 0.5,
            }
        )
        self._patch_fetch(sim=sim)
        artefak = self._bangun(iterations=None)
        jsonschema.validate(instance=artefak, schema=_skema_nba_analysis())
        self.assertEqual(artefak["status"], "OK")
        asuransi, utama = artefak["legs"]
        self.assertEqual(asuransi["line"], 233.5)
        self.assertEqual(asuransi["price_cents"], 66.5)
        self.assertEqual(asuransi["jup_estimated_cents"], 67.0)
        self.assertEqual(asuransi["p_model"], 0.77)
        self.assertTrue(asuransi["meets"])
        self.assertIsNone(asuransi["reason"])
        self.assertEqual(asuransi["leg_id"], f"{MATCH_ID}:total_under_233.5:insurance")
        # Utama: max(219, 225.5) + 8 = 233.5 (spread 5,5 -> bantalan 8).
        self.assertEqual(utama["line"], 233.5)
        self.assertEqual(utama["leg_id"], f"{MATCH_ID}:total_under_233.5:main")
        # EV = 0,77 * (100/67) - 1 = +14,9% -> DISKON.
        self.assertAlmostEqual(asuransi["ev_pct"], 14.925373, places=4)
        self.assertEqual(asuransi["price_label"], "DISKON")
        self.assertEqual(artefak["price_snapshots"]["total_under_233.5"]["cents"], 67.0)

    def test_anomali_total_line_vs_model_median_219_vs_market_225_5(self):
        # Temuan main agent 1b: selisih 6,5 > ambang 5,0.
        sim = _sim_stub({"total_under_233.5": 0.77, "total_under_219": 0.5})
        self._patch_fetch(sim=sim)
        artefak = self._bangun(iterations=None)
        tipe = [a["type"] for a in artefak["anomalies"]]
        self.assertIn("total_line_vs_model", tipe)
        anomali = next(
            a for a in artefak["anomalies"] if a["type"] == "total_line_vs_model"
        )
        self.assertEqual(anomali["gap_points"], 6.5)
        self.assertTrue(anomali["kenapa_beda_required"])
        # Cushion dikonfirmasi market (8,0 >= 8) -> tidak ada anomali itu.
        self.assertNotIn("cushion_tidak_dikonfirmasi_market", tipe)


class TestFailClosed(_BasisTes):
    def test_fetch_inputs_gagal_data_incomplete_bukan_exception(self):
        self._patch_fetch(inputs=_fail(nba_brain_mod.SOURCE, 1, "semua_sumber_gagal"))
        artefak = self._bangun()
        jsonschema.validate(instance=artefak, schema=_skema_nba_analysis())
        self.assertEqual(artefak["status"], "DATA_INCOMPLETE")
        self.assertEqual(artefak["legs"], [])
        self.assertIsNone(artefak["inputs"])
        self.assertIsNone(artefak["simulation"])
        self.assertTrue(any("inputs_gagal" in m for m in artefak["missing"]))

    def test_tangga_gagal_data_incomplete_inputs_tetap_terlampir(self):
        self._patch_fetch(
            event=_fail("Polymarket CLOB", 2, "Gamma /events/slug HTTP 404")
        )
        artefak = self._bangun()
        self.assertEqual(artefak["status"], "DATA_INCOMPLETE")
        self.assertIsNotNone(artefak["inputs"])
        self.assertIsNone(artefak["market"])
        self.assertTrue(any("tangga_gagal" in m for m in artefak["missing"]))

    def test_tangga_under_kosong_data_incomplete(self):
        event = _event_gamma(garis_total=[])
        self._patch_fetch(event=event)
        artefak = self._bangun()
        self.assertEqual(artefak["status"], "DATA_INCOMPLETE")
        self.assertIn("tangga_under_kosong", artefak["missing"])

    def test_sim_gagal_data_incomplete_bukan_exception(self):
        self._patch_fetch(inputs=_inputs(stats_rusak=True))
        artefak = self._bangun()
        self.assertEqual(artefak["status"], "DATA_INCOMPLETE")
        self.assertIsNone(artefak["simulation"])
        self.assertIsNotNone(artefak["inputs"])
        self.assertIsNotNone(artefak["market"])
        self.assertTrue(any("simulasi_gagal" in m for m in artefak["missing"]))

    def test_tricode_tidak_dikenal_data_incomplete(self):
        self._patch_fetch(
            inputs=_fail(nba_brain_mod.SOURCE, 1, "tricode_tidak_dikenal: 'XXX'")
        )
        artefak = nba_analysis_mod.build_nba_analysis(
            "XXX", "DET", TANGGAL, cfg=CFG, seed=7, iterations=200
        )
        self.assertEqual(artefak["status"], "DATA_INCOMPLETE")

    def test_argumen_tidak_valid_value_error(self):
        with self.assertRaises(ValueError):
            nba_analysis_mod.build_nba_analysis("", AWAY, TANGGAL)
        with self.assertRaises(ValueError):
            nba_analysis_mod.build_nba_analysis(HOME, AWAY, "22-11-2026")
        with self.assertRaises(ValueError):
            nba_analysis_mod.build_nba_analysis(HOME, AWAY, "2026-13-40")
        with self.assertRaises(ValueError):
            nba_analysis_mod.build_nba_analysis(HOME, AWAY, TANGGAL, seed="tujuh")
        with self.assertRaises(ValueError):
            nba_analysis_mod.build_nba_analysis(HOME, AWAY, TANGGAL, iterations=0)

    def test_minimal_artefak_valid_vs_skema(self):
        minimal = nba_analysis_mod.minimal_nba_analysis(
            MATCH_ID, HOME, AWAY, TANGGAL, ["contoh_gagal"]
        )
        jsonschema.validate(instance=minimal, schema=_skema_nba_analysis())
        self.assertEqual(minimal["status"], "DATA_INCOMPLETE")
        self.assertEqual(minimal["legs"], [])


class TestStatusHold(_BasisTes):
    def test_cedera_satu_sumber_hold(self):
        self._patch_fetch(inputs=_inputs(n_sumber_cedera=1))
        artefak = self._bangun()
        self.assertEqual(artefak["status"], "HOLD")
        self.assertEqual(artefak["injuries"]["n_sources"], 1)
        self.assertIn("cedera_kurang_dari_2_sumber", artefak["missing"])
        # Kaki tetap dirakit (bukan DATA_INCOMPLETE).
        self.assertEqual(len(artefak["legs"]), 2)

    def test_asuransi_tidak_memenuhi_dicatat_sebagai_leg_dan_hold(self):
        sim = _sim_stub({"total_under_229.5": 0.65, "total_under_219": 0.5})
        self._patch_fetch(event=_event_gamma(garis_total=[225.5, 229.5]), sim=sim)
        artefak = self._bangun(iterations=None)
        jsonschema.validate(instance=artefak, schema=_skema_nba_analysis())
        self.assertEqual(artefak["status"], "HOLD")
        asuransi, utama = artefak["legs"]
        self.assertFalse(asuransi["meets"])
        self.assertIsNone(asuransi["line"])
        self.assertEqual(asuransi["reason"], "tidak_ada_garis_memenuhi")
        self.assertEqual(asuransi["leg_id"], f"{MATCH_ID}:total_under_none:insurance")
        self.assertIsNone(asuransi["p_model"])
        self.assertIsNone(asuransi["p_final"])
        self.assertIsNone(asuransi["ev_pct"])
        self.assertIsNone(asuransi["price_label"])
        self.assertFalse(utama["meets"])
        self.assertEqual(artefak["price_snapshots"], {})


class TestKakiDanHarga(_BasisTes):
    def test_p_model_dari_kunci_sim_yang_benar(self):
        sim = _sim_stub(
            {
                "total_under_233.5": 0.77,
                "total_under_237.5": 0.83,
                "total_under_219": 0.5,
            }
        )
        self._patch_fetch(sim=sim)
        artefak = self._bangun(iterations=None)
        for leg in artefak["legs"]:
            kunci = f"total_under_{leg['line']:g}"
            self.assertEqual(leg["p_model"], sim["markets"][kunci])

    def test_blend_model_only_saat_p_market_null(self):
        # Kalshi hanya punya garis bulat (226/228) — tidak ada yang cocok
        # dengan garis tangga .5 -> MODEL_ONLY.
        kalshi = [
            _pasar_kalshi_total(226.0, 0.45, 0.47),
            _pasar_kalshi_total(228.0, 0.40, 0.42),
        ]
        sim = _sim_stub({"total_under_233.5": 0.77, "total_under_219": 0.5})
        self._patch_fetch(kalshi=kalshi, sim=sim)
        artefak = self._bangun(iterations=None)
        for leg in artefak["legs"]:
            self.assertIsNone(leg["p_market"])
            self.assertIsNone(leg["comparison_source"])
            self.assertEqual(leg["p_final"], leg["p_model"])

    def test_p_market_kalshi_komplemen_dan_blend(self):
        # Kalshi Over 233.5 bid/ask 0,30/0,32 -> p_over 0,31 ->
        # p_under 0,69; blend w_model dari config (0,3):
        # p_final = 0,3*0,77 + 0,7*0,69 = 0,714.
        kalshi = [_pasar_kalshi_total(233.5, 0.30, 0.32)]
        sim = _sim_stub({"total_under_233.5": 0.77, "total_under_219": 0.5})
        self._patch_fetch(kalshi=kalshi, sim=sim)
        artefak = self._bangun(iterations=None)
        w = config_mod.get_value(CFG, "blend", "w_model")
        for leg in artefak["legs"]:
            self.assertEqual(leg["p_market"], 0.69)
            self.assertEqual(leg["comparison_source"], "kalshi")
            self.assertAlmostEqual(
                leg["p_final"], w * 0.77 + (1.0 - w) * 0.69, places=9
            )

    def test_kalshi_gagal_model_only_status_tetap_ok(self):
        sim = _sim_stub({"total_under_233.5": 0.77, "total_under_219": 0.5})
        self._patch_fetch(
            kalshi=_fail("Kalshi API", 2, "Kalshi markets HTTP 500"), sim=sim
        )
        artefak = self._bangun(iterations=None)
        self.assertEqual(artefak["status"], "OK")
        for leg in artefak["legs"]:
            self.assertIsNone(leg["p_market"])
            self.assertEqual(leg["p_final"], leg["p_model"])
        self.assertTrue(
            any("kalshi_total_markets_gagal" in m for m in artefak["missing"])
        )

    def test_label_mahal_saat_ev_negatif(self):
        sim = _sim_stub({"total_under_233.5": 0.55, "total_under_219": 0.5})
        self._patch_fetch(sim=sim)
        artefak = self._bangun(iterations=None)
        asuransi = artefak["legs"][0]
        # EV = 0,55 * (100/67) - 1 = -17,9% -> MAHAL.
        self.assertAlmostEqual(asuransi["ev_pct"], -17.910448, places=4)
        self.assertEqual(asuransi["price_label"], "MAHAL")

    def test_tanpa_spread_bantalan_utama_12_dan_dicatat(self):
        # Fail-closed konservatif (keputusan user 2026-11-22, Langkah 2):
        # tanpa spread, Utama memakai bantalan rapat 12 (bukan 8):
        # max(219, 225.5) + 12 = 237.5.
        sim = _sim_stub({"total_under_233.5": 0.77, "total_under_219": 0.5})
        self._patch_fetch(event=_event_gamma(dengan_spread=False), sim=sim)
        artefak = self._bangun(iterations=None)
        self.assertEqual(artefak["legs"][1]["line"], 237.5)
        self.assertIn("spread_tidak_diketahui", artefak["missing"])

    def test_tanpa_slate_match_moneyline_null_dan_dicatat(self):
        sim = _sim_stub({"total_under_233.5": 0.77, "total_under_219": 0.5})
        self._patch_fetch(sim=sim)
        artefak = self._bangun(iterations=None, slate_match=None, start_time=None)
        self.assertIsNone(artefak["market"]["moneyline_jup"])
        self.assertIn("slate_match_tidak_ada", artefak["missing"])
        self.assertIsNone(artefak["start_time"])


class TestTanpaOddsApi(_BasisTes):
    def test_builder_tidak_memanggil_odds_api(self):
        # Bila builder (atau dependensinya) memanggil Odds API, tes ini
        # meledak — builder hanya boleh memakai Kalshi sebagai pembanding.
        from ingest import odds_api as odds_api_mod

        sim = _sim_stub({"total_under_233.5": 0.77, "total_under_219": 0.5})
        self._patch_fetch(sim=sim)
        with mock.patch.object(
            odds_api_mod,
            "fetch_odds",
            side_effect=AssertionError("Odds API terpanggil"),
        ):
            artefak = self._bangun(iterations=None)
        self.assertEqual(artefak["status"], "OK")
        self.assertNotIn("odds_api", {s["kind"] for s in artefak["sources"]})


class TestHelperTricode(unittest.TestCase):
    def test_team_tricode(self):
        self.assertEqual(nba_brain_mod.team_tricode("Los Angeles Lakers"), "LAL")
        self.assertEqual(nba_brain_mod.team_tricode("Lakers"), "LAL")
        self.assertEqual(nba_brain_mod.team_tricode("Atlanta Hawks"), "ATL")
        self.assertEqual(nba_brain_mod.team_tricode("ATL"), "ATL")
        self.assertIsNone(nba_brain_mod.team_tricode("Tim Khayalan"))
        self.assertIsNone(nba_brain_mod.team_tricode(""))


class TestFlagTanpaOddsApi(unittest.TestCase):
    """Flag --tanpa-odds-api: build_slate tidak memanggil Odds API."""

    _PLAYSTYLE = {
        "data": {"stale_hours_injury_lineup": 3},
        "comparison": {"order": ["odds_api_devig", "kalshi"]},
    }

    def _rakit(self, skip):
        panggilan = []

        def _fetch_palsu(module_name, func_name, source, tier, *args, **kwargs):
            panggilan.append((module_name, func_name))
            return _fail(source, tier, "palsu_gagal")

        with mock.patch.object(slate_mod, "_fetch", side_effect=_fetch_palsu):
            hasil = slate_mod.build_nba_slate(
                "2026-11-20",
                matches=[{"home": "Lakers", "away": "Celtics"}],
                playstyle=self._PLAYSTYLE,
                skip_odds_api=skip,
            )
        return hasil, panggilan

    def test_skip_true_odds_api_tidak_dipanggil_dan_nol_kredit(self):
        hasil, panggilan = self._rakit(skip=True)
        modul = {m for m, _ in panggilan}
        self.assertNotIn("ingest.odds_api", modul)
        self.assertEqual(hasil["odds_api"], {"calls": 0, "credits_used": 0})

    def test_skip_false_perilaku_lama_odds_api_dipanggil(self):
        hasil, panggilan = self._rakit(skip=False)
        modul = {m for m, _ in panggilan}
        self.assertIn("ingest.odds_api", modul)
        self.assertEqual(hasil["odds_api"]["calls"], 1)

    def test_default_skip_false(self):
        # Tanpa argumen, perilaku lama (Odds API dipanggil).
        panggilan = []

        def _fetch_palsu(module_name, func_name, source, tier, *args, **kwargs):
            panggilan.append(module_name)
            return _fail(source, tier, "palsu_gagal")

        with mock.patch.object(slate_mod, "_fetch", side_effect=_fetch_palsu):
            slate_mod.build_nba_slate(
                "2026-11-20",
                matches=[{"home": "Lakers", "away": "Celtics"}],
                playstyle=self._PLAYSTYLE,
            )
        self.assertIn("ingest.odds_api", panggilan)


class TestCliAnalyzeNba(unittest.TestCase):
    """Penyambungan analyze -> nba_analysis (build_slate + builder di-mock)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _slate(self, matches=None):
        return {
            "slate_id": "slate-test-nba-001",
            "created_at_wib": "2026-11-20T18:30:00+07:00",
            "source": "manual",
            "mode": "standard",
            "confirmed_by_user": True,
            "stake_split": {"insurance": 0.5, "main": 0.5},
            "matches": (
                matches
                if matches is not None
                else [
                    {
                        "match_id": "nba-2026-11-20-lal-bos",
                        "sport": "nba",
                        "league": "NBA",
                        "home": "Los Angeles Lakers",
                        "away": "Boston Celtics",
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

    def _tulis_slate(self, slate):
        path = self.tmp_path / "slate.json"
        path.write_text(json.dumps(slate), encoding="utf-8")
        return path

    def _fake_slate_2b(self, sport, match_id):
        return {
            "slate_id": f"slate-{sport}-x",
            "sport": sport,
            "slate_date": "2026-11-20",
            "generated_at": "2026-11-20T16:00:00+00:00",
            "matches": [
                {
                    "match_id": match_id,
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
                "tanpa_xg": 0,
            },
            "odds_api": {"calls": 1, "credits_used": 1},
        }

    def _fake_build(self, sport, date, matches=None, **kwargs):
        match_id = matches[0]["match_id"] if matches else f"{sport}-m1"
        return self._fake_slate_2b(sport, match_id)

    def test_nba_analysis_dilampirkan_dengan_tricode_benar(self):
        path = self._tulis_slate(self._slate())
        out = self.tmp_path / "analysis.json"
        artefak_palsu = {"status": "OK", "match_id": "BOS@LAL_2026-11-20"}
        panggilan_builder = []

        def _builder_palsu(home, away, tanggal, **kwargs):
            panggilan_builder.append((home, away, tanggal, kwargs.get("start_time")))
            return artefak_palsu

        with (
            mock.patch.object(slate_mod, "build_slate", side_effect=self._fake_build),
            mock.patch.object(
                nba_analysis_mod,
                "build_nba_analysis",
                side_effect=_builder_palsu,
            ),
            redirect_stdout(io.StringIO()),
        ):
            code = cli.main(["analyze", "--input", str(path), "--out", str(out)])
        self.assertEqual(code, 0)
        # 20:00 WIB = 08:00 EST hari yang sama -> tanggal NBA 2026-11-20.
        self.assertEqual(
            panggilan_builder,
            [("LAL", "BOS", "2026-11-20", "2026-11-20T20:00:00+07:00")],
        )
        output = json.loads(out.read_text(encoding="utf-8"))
        nba = next(
            m for m in output["matches"] if m["match_id"] == "nba-2026-11-20-lal-bos"
        )
        self.assertEqual(nba["nba_analysis"], artefak_palsu)
        bola = next(
            m for m in output["matches"] if m["match_id"] == "epl-2026-11-21-ars-che"
        )
        self.assertNotIn("nba_analysis", bola)

    def test_builder_gagal_total_minimal_data_incomplete_analyze_tetap_0(self):
        path = self._tulis_slate(self._slate())
        out = self.tmp_path / "analysis.json"
        with (
            mock.patch.object(slate_mod, "build_slate", side_effect=self._fake_build),
            mock.patch.object(
                nba_analysis_mod,
                "build_nba_analysis",
                side_effect=RuntimeError("meledak"),
            ),
            redirect_stdout(io.StringIO()),
        ):
            code = cli.main(["analyze", "--input", str(path), "--out", str(out)])
        self.assertEqual(code, 0)
        output = json.loads(out.read_text(encoding="utf-8"))
        nba = next(
            m for m in output["matches"] if m["match_id"] == "nba-2026-11-20-lal-bos"
        )
        self.assertEqual(nba["nba_analysis"]["status"], "DATA_INCOMPLETE")
        self.assertEqual(nba["nba_analysis"]["match_id"], "BOS@LAL_2026-11-20")

    def test_tricode_tidak_dikenal_minimal_data_incomplete(self):
        slate = self._slate(
            matches=[
                {
                    "match_id": "nba-x",
                    "sport": "nba",
                    "league": "NBA",
                    "home": "Tim Khayalan",
                    "away": "Boston Celtics",
                    "start_time": "2026-11-20T20:00:00+07:00",
                }
            ]
        )
        path = self._tulis_slate(slate)
        out = self.tmp_path / "analysis.json"
        with (
            mock.patch.object(slate_mod, "build_slate", side_effect=self._fake_build),
            mock.patch.object(
                nba_analysis_mod,
                "build_nba_analysis",
                side_effect=AssertionError("builder tidak boleh dipanggil"),
            ),
            redirect_stdout(io.StringIO()),
        ):
            code = cli.main(["analyze", "--input", str(path), "--out", str(out)])
        self.assertEqual(code, 0)
        output = json.loads(out.read_text(encoding="utf-8"))
        nba = output["matches"][0]
        self.assertEqual(nba["nba_analysis"]["status"], "DATA_INCOMPLETE")
        self.assertTrue(
            any("tricode_tidak_dikenal" in m for m in nba["nba_analysis"]["missing"])
        )

    def test_flag_tanpa_odds_api_diteruskan_ke_build_slate(self):
        path = self._tulis_slate(self._slate())
        out = self.tmp_path / "analysis.json"
        panggilan = []

        def _fake_build_catatan(sport, date, matches=None, **kwargs):
            panggilan.append(kwargs.get("skip_odds_api"))
            return self._fake_build(sport, date, matches=matches, **kwargs)

        with (
            mock.patch.object(
                slate_mod, "build_slate", side_effect=_fake_build_catatan
            ),
            mock.patch.object(
                nba_analysis_mod,
                "build_nba_analysis",
                return_value={"status": "OK"},
            ),
            redirect_stdout(io.StringIO()),
        ):
            code = cli.main(
                [
                    "analyze",
                    "--input",
                    str(path),
                    "--out",
                    str(out),
                    "--tanpa-odds-api",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(panggilan, [True, True])

        panggilan.clear()
        with (
            mock.patch.object(
                slate_mod, "build_slate", side_effect=_fake_build_catatan
            ),
            mock.patch.object(
                nba_analysis_mod,
                "build_nba_analysis",
                return_value={"status": "OK"},
            ),
            redirect_stdout(io.StringIO()),
        ):
            code = cli.main(["analyze", "--input", str(path), "--out", str(out)])
        self.assertEqual(code, 0)
        self.assertEqual(panggilan, [False, False])


if __name__ == "__main__":
    unittest.main()
