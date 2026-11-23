"""Tes engine/recheck.py — SEMUA offline, tanpa network, 0 kredit Odds API.

Fixture JSON di tests/fixtures/recheck/:
- thunder_*: rekonstruksi sintetis pelajaran Thunder (DECISIONS.md):
  Under 227.5 @ 75c -> 71c sebelum tip-off, tiket kalah. Gerak 4c >
  ambang sharp 3c = ANOMALI. Lawan (DEN) + tanggal adalah sintetis.
- det_atl_*: contoh final DET@ATL 2026-11-22 (LAPORAN 1b §3-4):
  median model 219, garis market 225,5 (selisih 6,5 > 5,0),
  garis Asuransi/Utama 233,5 @ 66,5c (jup 67,0c), P_model ~77%,
  Jalen Duren OUT di kedua sisi.
"""

import contextlib
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from engine import recheck

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "recheck"

SEKARANG = "2026-11-22T12:30:00+00:00"


def muat_fixture(nama: str) -> dict:
    """Muat satu fixture JSON (deep copy baru tiap panggil)."""
    return json.loads((FIXTURES / nama).read_text(encoding="utf-8"))


def entri_tangga(garis, sisi, harga, volume=1000.0, jup=None, mid=None):
    """Satu entri tangga totals bentuk parse_event_ladders."""
    return {
        "line": garis,
        "side": sisi,
        "price_cents": harga,
        "bid_cents": (harga - 1.0) if harga is not None else None,
        "ask_cents": (harga + 1.0) if harga is not None else None,
        "mid_cents": mid if mid is not None else harga,
        "volume_usd": volume,
        "thin": volume is not None and volume < 100.0,
        "market_id": f"m-{garis}",
        "jup_estimated_cents": jup if jup is not None else harga,
    }


def tangga_minimal(harga_under, garis_utama=225.5, volume_utama=45000.0):
    """Tangga totals minimal: garis utama + garis-garis di harga_under.

    harga_under: {garis: harga_cents} untuk sisi Under.
    """
    totals = [
        entri_tangga(garis_utama, "under", 50.0, volume_utama),
        entri_tangga(garis_utama, "over", 50.0, volume_utama),
    ]
    for garis, harga in sorted(harga_under.items()):
        if garis == garis_utama:
            continue
        totals.append(entri_tangga(garis, "under", harga, 8000.0))
    return {"slug": "nba-det-atl-2026-11-22", "totals": totals}


def kaki(garis=233.5, tiket="insurance", harga=66.5, jup=67.0, p_model=0.77):
    """Satu kaki total_under bentuk kontrak artefak."""
    return {
        "leg_id": f"DET@ATL_2026-11-22:total_under_{garis:g}:{tiket}",
        "market_type": "total_under",
        "line": garis,
        "ticket": tiket,
        "p_model": p_model,
        "p_market": 0.66,
        "comparison_source": "kalshi",
        "p_final": 0.693,
        "price_cents": harga,
        "jup_estimated_cents": jup,
        "ev_pct": 3.43,
        "price_label": "DISKON",
        "cushion_vs_median_points": 14.5,
        "cushion_vs_market_points": 8.0,
        "meets": True,
        "reason": None,
        "fetched_at": "2026-11-22T10:00:00+00:00",
    }


def analisis_minimal(median=224.0, garis_market=225.5, legs=None, **overrides):
    """Artefak analisis minimal (median dekat garis -> pemicu nonaktif)."""
    analisis = {
        "format": "nba_analysis",
        "format_version": 1,
        "match_id": "DET@ATL_2026-11-22",
        "home_tricode": "ATL",
        "away_tricode": "DET",
        "game_date": "2026-11-22",
        "start_time": "2026-11-23T00:30:00+00:00",
        "generated_at": "2026-11-22T10:00:00+00:00",
        "status": "OK",
        "missing": [],
        "sources": [],
        "inputs": {
            "home": {"tricode": "ATL", "injuries": []},
            "away": {"tricode": "DET", "injuries": []},
        },
        "simulation": {
            "match_id": "DET@ATL_2026-11-22",
            "score_distribution": {
                "total": {"median": median, "p74": 231.0, "p75": 232.0}
            },
        },
        "market": {
            "slug": "nba-det-atl-2026-11-22",
            "main_total_line": garis_market,
            "main_total_volume_usd": 44032.0,
            "ladder_fetched_at": "2026-11-22T10:00:00+00:00",
            "ladder_warnings": [],
            "moneyline_jup": None,
            "totals": [],
            "spreads": [],
        },
        "legs": legs if legs is not None else [kaki()],
        "injuries": {
            "sources": ["NBA Injury Report", "ESPN"],
            "n_sources": 2,
            "confirmed_both": [],
            "entries": [],
            "conflicts": [],
            "fetched_at": "2026-11-22T10:00:00+00:00",
        },
        "anomalies": [],
        "price_snapshots": {
            "total_under_233.5": {"cents": 67.0, "at": "2026-11-22T10:00:00+00:00"}
        },
    }
    analisis.update(overrides)
    return analisis


def fresh_minimal(harga_under=None, cedera_baru=None, **overrides):
    """Dict fresh minimal: harga stabil + cedera tidak berubah."""
    if harga_under is None:
        harga_under = {233.5: 66.5}
    cedera = cedera_baru if cedera_baru is not None else []
    fresh = {
        "inputs": {
            "home": {"tricode": "ATL", "injuries": []},
            "away": {"tricode": "DET", "injuries": cedera},
        },
        "ladders": tangga_minimal(harga_under),
        "moneyline_jup": None,
        "fetched_at": "2026-11-22T12:00:00+00:00",
        "errors": {},
    }
    fresh.update(overrides)
    return fresh


def resim_stub(garis_baru=233.5, meets=True, median_baru=224.0, p_model=0.77):
    """Stub resim_fn: sim baru + satu kaki (tiket insurance)."""

    def _resim(fresh):
        return {
            "simulation": {
                "match_id": "DET@ATL_2026-11-22",
                "score_distribution": {
                    "total": {"median": median_baru, "p74": 231.0, "p75": 232.0}
                },
            },
            "legs": [
                dict(
                    kaki(garis=garis_baru, p_model=p_model),
                    meets=meets,
                    reason=None if meets else "tidak_ada_garis_memenuhi",
                    fetched_at="2026-11-22T12:00:00+00:00",
                )
            ],
        }

    return _resim


def validasi_skema(laporan):
    """Laporan recheck harus lolos schemas/recheck.schema.json."""
    schema = json.loads(
        (REPO_ROOT / "schemas" / "recheck.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(instance=laporan, schema=schema)


class CushionStub:
    """Pengganti engine.cushion dengan signature BARU (kontrak pekerja A).

    Mencatat tiap pemanggilan (kwargs) + mengembalikan garis yang
    diminta dari tangga. garis_ins/garis_main None = meets False
    dengan alasan stub. Dipakai karena cushion asli sedang dibangun
    paralel oleh pekerja A — tes recheck menguji wiring-nya, bukan
    logika pemilihan garis cushion.
    """

    def __init__(
        self, garis_ins=233.5, garis_main=233.5, alasan="tidak_ada_garis_memenuhi"
    ):
        self.calls = []
        self.garis_ins = garis_ins
        self.garis_main = garis_main
        self.alasan = alasan

    def _hasil(self, garis, ladder, persen, garis_market):
        entri = None
        for baris in ladder:
            if isinstance(baris, dict) and baris.get("line") == garis:
                entri = baris
                break
        if garis is None or entri is None:
            return {
                "line": None,
                "meets": False,
                "reason": self.alasan,
                "price_cents": None,
                "jup_estimated_cents": None,
                "cushion_vs_median_points": None,
                "cushion_vs_market_points": None,
            }
        median = persen.get("median")
        return {
            "line": garis,
            "meets": True,
            "reason": None,
            "price_cents": entri.get("price_cents"),
            "jup_estimated_cents": entri.get("jup_estimated_cents"),
            "cushion_vs_median_points": (
                round(garis - median, 9) if median is not None else None
            ),
            "cushion_vs_market_points": round(garis - garis_market, 9),
        }

    def insurance_line(
        self,
        percentiles,
        market_line,
        ladder,
        cfg=None,
        garis_di_atas=None,
        peluang_under=None,
        harga_min_cents=None,
    ):
        self.calls.append(
            (
                "insurance",
                {
                    "garis_di_atas": garis_di_atas,
                    "peluang_under": peluang_under,
                    "harga_min_cents": harga_min_cents,
                },
            )
        )
        return self._hasil(self.garis_ins, ladder, percentiles, market_line)

    def utama_line(
        self,
        percentiles,
        market_line,
        ladder,
        cfg=None,
        cushion_points=None,
        peluang_under=None,
        harga_min_cents=None,
    ):
        self.calls.append(
            (
                "main",
                {
                    "cushion_points": cushion_points,
                    "peluang_under": peluang_under,
                    "harga_min_cents": harga_min_cents,
                },
            )
        )
        return self._hasil(self.garis_main, ladder, percentiles, market_line)


@contextlib.contextmanager
def stub_cushion(stub):
    """Pasang CushionStub sebagai engine.recheck.cushion sementara."""
    with mock.patch.object(recheck, "cushion", stub):
        yield stub


@contextlib.contextmanager
def stub_analis(hasil=None, exception=None):
    """Suntikkan modul engine.analis palsu ke sys.modules sementara.

    hasil: dict yang dikembalikan bantalan_adaptif (None = analis
    mengembalikan None). exception: bila diberikan, bantalan_adaptif
    melemparkannya. Modul palsu mencatat pemanggilan di .calls.
    """
    calls = []

    class _Modul:
        pass

    modul = _Modul()

    def _bantalan(stats_laga, distribusi_sim, cfg=None):
        calls.append(
            {
                "stats_laga": stats_laga,
                "distribusi_sim": distribusi_sim,
                "cfg": cfg,
            }
        )
        if exception is not None:
            raise exception
        return hasil

    modul.bantalan_adaptif = _bantalan
    modul.calls = calls
    lama = sys.modules.get("engine.analis")
    sys.modules["engine.analis"] = modul
    try:
        yield modul
    finally:
        if lama is None:
            sys.modules.pop("engine.analis", None)
        else:
            sys.modules["engine.analis"] = lama


def inputs_minimal_bantalan():
    """Inputs minimal untuk stats_laga_untuk_analis (off_rtg musim)."""
    return {
        "home": {"stats_season": {"off_rtg": 115.0}},
        "away": {"stats_season": {"off_rtg": 110.0}},
        "league": {"avg_off_rtg": 112.0},
    }


class TestCompareInjuries(unittest.TestCase):
    def test_pemain_baru_out(self):
        diff = recheck.compare_injuries(
            [], [{"player": "Cade Cunningham", "status": "OUT"}]
        )
        self.assertEqual(diff["new_out"], ["Cade Cunningham"])
        self.assertEqual(diff["resolved"], [])

    def test_status_memburuk_ke_doubtful(self):
        diff = recheck.compare_injuries(
            [{"player": "Trae Young", "status": "QUESTIONABLE"}],
            [{"player": "Trae Young", "status": "doubtful"}],
        )
        self.assertEqual(diff["new_out"], ["Trae Young"])
        self.assertEqual(
            diff["status_changed"],
            [{"player": "Trae Young", "old": "QUESTIONABLE", "new": "DOUBTFUL"}],
        )

    def test_out_ke_doubtful_bukan_new_out(self):
        # Membaik (OUT -> DOUBTFUL): bukan new_out, tapi status berubah.
        diff = recheck.compare_injuries(
            [{"player": "Jalen Duren", "status": "OUT"}],
            [{"player": "Jalen Duren", "status": "DOUBTFUL"}],
        )
        self.assertEqual(diff["new_out"], [])
        self.assertEqual(len(diff["status_changed"]), 1)

    def test_pemain_kembali_resolved(self):
        diff = recheck.compare_injuries(
            [{"player": "Jalen Duren", "status": "OUT"}], []
        )
        self.assertEqual(diff["resolved"], ["Jalen Duren"])
        self.assertEqual(diff["new_out"], [])

    def test_normalisasi_nama_dan_status(self):
        # Spasi berlebih + huruf kecil tetap cocok dengan nama yang sama.
        diff = recheck.compare_injuries(
            [{"player": "Jalen   Duren", "status": "out"}],
            [{"player": "jalen duren", "status": "OUT"}],
        )
        self.assertEqual(diff, {"new_out": [], "status_changed": [], "resolved": []})

    def test_status_tidak_dikenal_tidak_material(self):
        diff = recheck.compare_injuries(
            [],
            [{"player": "Pemain X", "status": "DAY-TO-DAY"}],
        )
        self.assertEqual(diff["new_out"], [])
        # Tapi perubahannya tetap tercatat.
        self.assertEqual(len(diff["status_changed"]), 1)

    def test_tidak_ada_perubahan(self):
        entri = [{"player": "Jalen Duren", "status": "OUT"}]
        self.assertEqual(
            recheck.compare_injuries(entri, copy.deepcopy(entri)),
            {"new_out": [], "status_changed": [], "resolved": []},
        )


class TestComparePrices(unittest.TestCase):
    def test_gerak_4c_anomali(self):
        analisis = analisis_minimal()
        fresh = fresh_minimal({233.5: 62.5})  # 67.0 -> 62.5 = -4.5
        diff = recheck.compare_prices(analisis, fresh)
        self.assertEqual(len(diff["moves"]), 1)
        gerak = diff["moves"][0]
        self.assertEqual(gerak["old_cents"], 67.0)
        self.assertEqual(gerak["new_cents"], 62.5)
        self.assertEqual(gerak["move_cents"], -4.5)
        self.assertTrue(gerak["anomaly"])

    def test_gerak_tepat_3c_anomali(self):
        analisis = analisis_minimal()
        fresh = fresh_minimal({233.5: 64.0})  # 67.0 -> 64.0 = -3 tepat
        gerak = recheck.compare_prices(analisis, fresh)["moves"][0]
        self.assertEqual(gerak["move_cents"], -3.0)
        self.assertTrue(gerak["anomaly"])

    def test_gerak_2c_bukan_anomali(self):
        analisis = analisis_minimal()
        fresh = fresh_minimal({233.5: 65.0})  # 67.0 -> 65.0 = -2
        gerak = recheck.compare_prices(analisis, fresh)["moves"][0]
        self.assertEqual(gerak["move_cents"], -2.0)
        self.assertFalse(gerak["anomaly"])

    def test_snapshot_dipakai_sebagai_baseline(self):
        # Harga kaki 70.0 tapi snapshot pertama 67.0 -> gerak dari 67.0.
        analisis = analisis_minimal(legs=[kaki(harga=70.0, jup=70.0)])
        fresh = fresh_minimal({233.5: 67.0})
        gerak = recheck.compare_prices(analisis, fresh)["moves"][0]
        self.assertEqual(gerak["old_cents"], 67.0)
        self.assertEqual(gerak["move_cents"], 0.0)

    def test_tanpa_snapshot_pakai_harga_kaki(self):
        analisis = analisis_minimal(price_snapshots={})
        fresh = fresh_minimal({233.5: 66.5})
        gerak = recheck.compare_prices(analisis, fresh)["moves"][0]
        self.assertEqual(gerak["old_cents"], 67.0)  # jup_estimated kaki

    def test_garis_hilang_dari_tangga(self):
        analisis = analisis_minimal()
        fresh = fresh_minimal({})  # tangga hanya garis utama
        gerak = recheck.compare_prices(analisis, fresh)["moves"][0]
        self.assertTrue(gerak["missing_line"])
        self.assertIsNone(gerak["new_cents"])
        self.assertIsNone(gerak["move_cents"])
        self.assertFalse(gerak["anomaly"])

    def test_gerak_garis_market(self):
        analisis = analisis_minimal(garis_market=225.5)
        fresh = fresh_minimal({233.5: 66.5})
        fresh["ladders"] = tangga_minimal({233.5: 66.5}, garis_utama=228.0)
        gerak = recheck.compare_prices(analisis, fresh)["market_line_move"]
        self.assertEqual(gerak, {"old": 225.5, "new": 228.0, "move_points": 2.5})

    def test_garis_utama_volume_terbesar(self):
        totals = [
            entri_tangga(225.5, "under", 50.0, 100.0),
            entri_tangga(227.5, "under", 60.0, 99999.0),
            entri_tangga(223.5, "under", 40.0, 500.0),
        ]
        self.assertEqual(recheck.garis_utama_dari_tangga(totals), 227.5)
        self.assertIsNone(recheck.garis_utama_dari_tangga([]))
        self.assertIsNone(
            recheck.garis_utama_dari_tangga([entri_tangga(225.5, "under", 50.0, None)])
        )

    def test_kunci_ambang_hilang_config_error(self):
        cfg = {"anomaly": {}}
        with self.assertRaises(config.ConfigError):
            recheck.compare_prices(analisis_minimal(), fresh_minimal(), cfg=cfg)


class TestNeedsResim(unittest.TestCase):
    def test_cedera_baru_out_memuat(self):
        perlu, alasan = recheck.needs_resim(
            {"new_out": ["Cade Cunningham"], "status_changed": [], "resolved": []},
            {"moves": [], "market_line_move": {"move_points": 0.0}},
        )
        self.assertTrue(perlu)
        self.assertIn("Cade Cunningham", alasan[0])

    def test_resolved_saja_tidak_memuat(self):
        perlu, _ = recheck.needs_resim(
            {"new_out": [], "status_changed": [], "resolved": ["Jalen Duren"]},
            {"moves": [], "market_line_move": {"move_points": 0.0}},
        )
        self.assertFalse(perlu)

    def test_garis_tepat_2_tidak_memuat(self):
        perlu, _ = recheck.needs_resim(
            {"new_out": [], "status_changed": [], "resolved": []},
            {"moves": [], "market_line_move": {"move_points": 2.0}},
        )
        self.assertFalse(perlu)

    def test_garis_2_5_memuat(self):
        perlu, alasan = recheck.needs_resim(
            {"new_out": [], "status_changed": [], "resolved": []},
            {"moves": [], "market_line_move": {"move_points": -2.5}},
        )
        self.assertTrue(perlu)
        self.assertTrue(any("garis_market" in a for a in alasan))

    def test_harga_anomali_memuat(self):
        perlu, _ = recheck.needs_resim(
            None,
            {
                "moves": [{"leg_key": "total_under_233.5", "anomaly": True}],
                "market_line_move": {"move_points": None},
            },
        )
        self.assertTrue(perlu)

    def test_tidak_ada_pemicu(self):
        perlu, alasan = recheck.needs_resim(
            {"new_out": [], "status_changed": [], "resolved": []},
            {"moves": [], "market_line_move": {"move_points": 0.5}},
        )
        self.assertFalse(perlu)
        self.assertEqual(alasan, [])

    def test_kunci_ambang_hilang_config_error(self):
        with self.assertRaises(config.ConfigError):
            recheck.needs_resim(
                {"new_out": [], "status_changed": [], "resolved": []},
                {"moves": [], "market_line_move": {"move_points": 0.0}},
                cfg={"recheck": {}},
            )


class TestFetchFresh(unittest.TestCase):
    def test_sukses_dengan_stub(self):
        def _inputs(analysis, client=None):
            from ingest.common import FetchResult

            return FetchResult("test", 1, "2026-11-22T12:00:00+00:00", True, data={})

        def _ladder(analysis, client=None):
            return {"slug": "x", "totals": []}

        def _ml(analysis, client=None):
            return {
                "home_cents": 60.0,
                "away_cents": 40.0,
                "fetched_at": "2026-11-22T12:00:00+00:00",
            }

        hasil = recheck.fetch_fresh(
            analisis_minimal(),
            fetch_inputs=_inputs,
            fetch_ladder=_ladder,
            fetch_jup_ml=_ml,
        )
        self.assertEqual(hasil["inputs"], {})
        self.assertEqual(hasil["ladders"], {"slug": "x", "totals": []})
        self.assertEqual(hasil["moneyline_jup"]["home_cents"], 60.0)
        self.assertEqual(hasil["errors"], {})

    def test_fetch_gagal_jadi_errors_bukan_exception(self):
        def _gagal(analysis, client=None):
            raise RuntimeError("jaringan putus")

        hasil = recheck.fetch_fresh(
            analisis_minimal(), fetch_inputs=_gagal, fetch_ladder=_gagal
        )
        self.assertIsNone(hasil["inputs"])
        self.assertIsNone(hasil["ladders"])
        self.assertIn("jaringan putus", hasil["errors"]["inputs"])
        self.assertIn("jaringan putus", hasil["errors"]["ladders"])

    def test_fetchresult_gagal_jadi_errors(self):
        def _inputs(analysis, client=None):
            from ingest.common import FetchResult

            return FetchResult(
                "test", 1, "2026-11-22T12:00:00+00:00", False, error="http 500"
            )

        hasil = recheck.fetch_fresh(
            analisis_minimal(),
            fetch_inputs=_inputs,
            fetch_ladder=lambda a, c=None: {"slug": "x", "totals": []},
        )
        self.assertIsNone(hasil["inputs"])
        self.assertEqual(hasil["errors"]["inputs"], "http 500")

    def test_moneyline_default_none_dengan_catatan(self):
        hasil = recheck.fetch_fresh(
            analisis_minimal(),
            fetch_inputs=lambda a, c=None: {},
            fetch_ladder=lambda a, c=None: {"slug": "x", "totals": []},
        )
        self.assertIsNone(hasil["moneyline_jup"])
        self.assertIn("moneyline_jup", hasil["errors"])


class TestDecideDasar(unittest.TestCase):
    def test_tidak_ada_perubahan_go(self):
        laporan = recheck.decide(analisis_minimal(), fresh_minimal(), sekarang=SEKARANG)
        self.assertEqual(laporan["verdict"], "GO")
        self.assertEqual(laporan["legs"][0]["verdict"], "TETAP_OK")
        self.assertFalse(laporan["resimulated"])
        self.assertEqual(laporan["attention"], [])
        self.assertIsNone(laporan["action_required"])
        validasi_skema(laporan)

    def test_gerak_2c_perhatian_tetap_go(self):
        laporan = recheck.decide(
            analisis_minimal(),
            fresh_minimal({233.5: 65.0}),
            sekarang=SEKARANG,
        )
        self.assertEqual(laporan["verdict"], "GO")
        self.assertEqual(laporan["legs"][0]["verdict"], "PERHATIAN")
        self.assertTrue(laporan["attention"])
        self.assertEqual(
            laporan["action_required"],
            "baca daftar perhatian di laporan sebelum submit",
        )
        validasi_skema(laporan)

    def test_garis_market_bergerak_1_5_perhatian(self):
        fresh = fresh_minimal({233.5: 66.5})
        fresh["ladders"] = tangga_minimal({233.5: 66.5}, garis_utama=227.0)
        laporan = recheck.decide(analisis_minimal(), fresh, sekarang=SEKARANG)
        self.assertEqual(laporan["verdict"], "GO")
        self.assertEqual(laporan["legs"][0]["verdict"], "PERHATIAN")

    def test_garis_hilang_jangan_pasang(self):
        laporan = recheck.decide(
            analisis_minimal(), fresh_minimal({}), sekarang=SEKARANG
        )
        self.assertEqual(laporan["verdict"], "NO_GO")
        self.assertEqual(laporan["legs"][0]["verdict"], "JANGAN_PASANG")
        self.assertIn("hilang", laporan["legs"][0]["reasons"][0])

    def test_tangga_gagal_data_incomplete(self):
        fresh = fresh_minimal(ladders=None, errors={"ladders": "Gamma http 500"})
        laporan = recheck.decide(analisis_minimal(), fresh, sekarang=SEKARANG)
        self.assertEqual(laporan["verdict"], "NO_GO")
        self.assertEqual(laporan["legs"][0]["verdict"], "DATA_INCOMPLETE")
        self.assertIn("ladders", laporan["missing"])

    def test_cedera_gagal_dan_basi_data_incomplete(self):
        # generated_at 10:00, recheck 12:30 -> umur 2,5 jam (belum basi),
        # jadi pakai sekarang yang lebih lambat agar basi.
        fresh = fresh_minimal(inputs=None, errors={"inputs": "stats.nba.com timeout"})
        laporan = recheck.decide(
            analisis_minimal(),
            fresh,
            sekarang="2026-11-22T14:00:00+00:00",  # umur 4 jam > 3 jam
        )
        self.assertEqual(laporan["verdict"], "NO_GO")
        self.assertEqual(laporan["legs"][0]["verdict"], "DATA_INCOMPLETE")
        self.assertTrue(any(c["kind"] == "stale" for c in laporan["changes"]))

    def test_cedera_gagal_tapi_masih_segar_tetap_go(self):
        # Umur data 2,5 jam <= 3 jam: data lama masih valid.
        fresh = fresh_minimal(inputs=None, errors={"inputs": "stats.nba.com timeout"})
        laporan = recheck.decide(analisis_minimal(), fresh, sekarang=SEKARANG)
        self.assertEqual(laporan["verdict"], "GO")
        self.assertEqual(laporan["legs"][0]["verdict"], "TETAP_OK")
        self.assertTrue(any(c["kind"] == "fetch_error" for c in laporan["changes"]))

    def test_status_hold_jangan_pasang(self):
        laporan = recheck.decide(
            analisis_minimal(status="HOLD"), fresh_minimal(), sekarang=SEKARANG
        )
        self.assertEqual(laporan["verdict"], "NO_GO")
        self.assertEqual(laporan["legs"][0]["verdict"], "JANGAN_PASANG")

    def test_status_data_incomplete(self):
        laporan = recheck.decide(
            analisis_minimal(status="DATA_INCOMPLETE"),
            fresh_minimal(),
            sekarang=SEKARANG,
        )
        self.assertEqual(laporan["legs"][0]["verdict"], "DATA_INCOMPLETE")

    def test_kaki_awal_tidak_meets(self):
        analisis = analisis_minimal(legs=[dict(kaki(), meets=False)])
        laporan = recheck.decide(analisis, fresh_minimal(), sekarang=SEKARANG)
        self.assertEqual(laporan["legs"][0]["verdict"], "JANGAN_PASANG")

    def test_tanpa_kaki_no_go(self):
        laporan = recheck.decide(
            analisis_minimal(legs=[]), fresh_minimal(), sekarang=SEKARANG
        )
        self.assertEqual(laporan["verdict"], "NO_GO")
        self.assertIn("legs", laporan["missing"])

    def test_error_moneyline_diabaikan(self):
        fresh = fresh_minimal(errors={"moneyline_jup": "tidak ada fetcher"})
        laporan = recheck.decide(analisis_minimal(), fresh, sekarang=SEKARANG)
        self.assertEqual(laporan["verdict"], "GO")
        self.assertNotIn("moneyline_jup", laporan["missing"])

    def test_resim_gagal_data_incomplete(self):
        # Garis market bergerak 2.5 -> resim dibutuhkan -> stub melempar.
        fresh = fresh_minimal({233.5: 66.5})
        fresh["ladders"] = tangga_minimal({233.5: 66.5}, garis_utama=228.0)

        def _resim_gagal(fresh):
            raise ValueError("sim rusak")

        laporan = recheck.decide(
            analisis_minimal(),
            fresh,
            resim_fn=_resim_gagal,
            sekarang=SEKARANG,
        )
        self.assertEqual(laporan["verdict"], "NO_GO")
        self.assertEqual(laporan["legs"][0]["verdict"], "DATA_INCOMPLETE")
        self.assertFalse(laporan["resimulated"])
        self.assertIn("resim", laporan["missing"])


class TestFixtureThunder(unittest.TestCase):
    def test_thunder_no_go_dengan_resim_stub(self):
        analisis = muat_fixture("thunder_analysis.json")
        fresh = muat_fixture("thunder_fresh.json")

        def _resim(fresh):
            leg = dict(
                analisis["legs"][0],
                fetched_at="2026-11-15T12:00:00+00:00",
            )
            return {
                "simulation": {
                    "match_id": "OKC@DEN_2026-11-15",
                    "score_distribution": {
                        "total": {"median": 219.0, "p74": 231.0, "p75": 232.0}
                    },
                },
                "legs": [leg],
            }

        laporan = recheck.decide(
            analisis,
            fresh,
            resim_fn=_resim,
            sekarang="2026-11-15T12:30:00+00:00",
        )
        self.assertEqual(laporan["verdict"], "NO_GO")
        self.assertTrue(laporan["resimulated"])
        leg = laporan["legs"][0]
        self.assertEqual(leg["verdict"], "JANGAN_PASANG")
        self.assertEqual(leg["price_move_cents"], -4.0)
        self.assertEqual(len(laporan["anomalies"]), 1)
        self.assertEqual(laporan["anomalies"][0]["type"], "sharp_move")
        self.assertEqual(laporan["anomalies"][0]["delta_cents"], -4.0)
        # Kaki Utama: aturan condong-ke-market tidak berlaku meski
        # pemicu aktif (gap 6,5) — probabilitas model tetap dipakai.
        self.assertTrue(leg["kenapa_beda"]["triggered"])
        self.assertEqual(leg["probability_used"], "model")
        validasi_skema(laporan)

    def test_thunder_sharp_move_bukan_diskon(self):
        """Pola Thunder (75¢ -> 71¢): TIDAK BOLEH berlabel DISKON polos.

        Kaki harus JANGAN_PASANG (lebih keras dari PERHATIAN) +
        label DISKON_DITEKAN + "Kenapa beda?" dipicu
        (kenapa_beda_required) + alasan framing peringatan.
        """
        analisis = muat_fixture("thunder_analysis.json")
        fresh = muat_fixture("thunder_fresh.json")

        def _resim(fresh):
            leg = dict(
                analisis["legs"][0],
                fetched_at="2026-11-15T12:00:00+00:00",
            )
            return {
                "simulation": {
                    "match_id": "OKC@DEN_2026-11-15",
                    "score_distribution": {
                        "total": {"median": 219.0, "p74": 231.0, "p75": 232.0}
                    },
                },
                "legs": [leg],
            }

        laporan = recheck.decide(
            analisis,
            fresh,
            resim_fn=_resim,
            sekarang="2026-11-15T12:30:00+00:00",
        )
        leg = laporan["legs"][0]
        self.assertEqual(leg["verdict"], "JANGAN_PASANG")
        self.assertEqual(leg["price_move_cents"], -4.0)
        # Label: DISKON_DITEKAN, bukan DISKON polos.
        self.assertEqual(len(laporan["anomalies"]), 1)
        anomali = laporan["anomalies"][0]
        self.assertEqual(anomali["type"], "sharp_move")
        self.assertEqual(anomali["price_label"], "DISKON_DITEKAN")
        self.assertNotEqual(anomali["price_label"], "DISKON")
        # "Kenapa beda?" dipicu sampai pergerakannya dijelaskan.
        self.assertTrue(anomali["kenapa_beda_required"])
        self.assertIn("harga baru bergerak tajam, selidiki dulu", anomali["catatan"])
        # Alasan kaki membawa framing peringatan, bukan diskon.
        self.assertTrue(
            any("DISKON_DITEKAN" in r for r in leg["reasons"]),
            leg["reasons"],
        )
        self.assertTrue(
            any(
                "harga baru bergerak tajam, selidiki dulu" in r for r in leg["reasons"]
            ),
            leg["reasons"],
        )
        validasi_skema(laporan)

    def test_tanpa_sharp_move_tanpa_penkanan(self):
        # Harga stabil: tidak ada anomali, tidak ada penekanan label.
        laporan = recheck.decide(analisis_minimal(), fresh_minimal(), sekarang=SEKARANG)
        self.assertEqual(laporan["anomalies"], [])
        for leg in laporan["legs"]:
            self.assertFalse(
                any("DISKON_DITEKAN" in r for r in leg["reasons"]),
                leg["reasons"],
            )

    def test_thunder_tanpa_resim_fn_resim_default_gagal_aman(self):
        # Inputs fixture minimal (tanpa stats) -> _resim_default gagal
        # (sim butuh stats_season); kaki tetap JANGAN_PASANG karena
        # sharp move, bukan karena resim gagal.
        analisis = muat_fixture("thunder_analysis.json")
        fresh = muat_fixture("thunder_fresh.json")
        laporan = recheck.decide(analisis, fresh, sekarang="2026-11-15T12:30:00+00:00")
        self.assertEqual(laporan["verdict"], "NO_GO")
        self.assertEqual(laporan["legs"][0]["verdict"], "JANGAN_PASANG")
        self.assertFalse(laporan["resimulated"])
        self.assertIn("resim", laporan["missing"])


class TestCederaBintangBaruOut(unittest.TestCase):
    def _analisis_dan_fresh(self):
        analisis = analisis_minimal()
        cedera = [
            {
                "player": "Cade Cunningham",
                "status": "OUT",
                "team_tricode": "DET",
                "sources": ["NBA Injury Report", "ESPN"],
            }
        ]
        fresh = fresh_minimal(cedera_baru=cedera)
        return analisis, fresh

    def test_garis_berubah_jangan_pasang(self):
        analisis, fresh = self._analisis_dan_fresh()
        laporan = recheck.decide(
            analisis,
            fresh,
            resim_fn=resim_stub(garis_baru=235.5, median_baru=221.0),
            sekarang=SEKARANG,
        )
        self.assertEqual(laporan["verdict"], "NO_GO")
        self.assertTrue(laporan["resimulated"])
        self.assertTrue(any("cedera_baru" in a for a in laporan["resim_reasons"]))
        leg = laporan["legs"][0]
        self.assertEqual(leg["verdict"], "JANGAN_PASANG")
        self.assertEqual(leg["old_line"], 233.5)
        self.assertEqual(leg["new_line"], 235.5)
        self.assertTrue(leg["resimulated"])
        self.assertEqual(laporan["action_required"], "ganti garis ke 235.5")
        self.assertTrue(any(c["kind"] == "injury" for c in laporan["changes"]))
        validasi_skema(laporan)

    def test_garis_tetap_perhatian_tetap_go(self):
        analisis, fresh = self._analisis_dan_fresh()
        laporan = recheck.decide(
            analisis,
            fresh,
            resim_fn=resim_stub(garis_baru=233.5, median_baru=221.0),
            sekarang=SEKARANG,
        )
        self.assertEqual(laporan["verdict"], "GO")
        self.assertEqual(laporan["legs"][0]["verdict"], "PERHATIAN")
        self.assertTrue(laporan["attention"])
        validasi_skema(laporan)

    def test_garis_baru_tidak_meets_jangan_pasang(self):
        analisis, fresh = self._analisis_dan_fresh()
        laporan = recheck.decide(
            analisis,
            fresh,
            resim_fn=resim_stub(meets=False),
            sekarang=SEKARANG,
        )
        self.assertEqual(laporan["legs"][0]["verdict"], "JANGAN_PASANG")
        self.assertIn("tidak memenuhi syarat", laporan["legs"][0]["reasons"][0])

    def test_konflik_baru_perhatian(self):
        analisis = analisis_minimal()
        cedera = [
            {
                "player": "Trae Young",
                "status": "QUESTIONABLE",
                "team_tricode": "ATL",
                "sources": ["NBA Injury Report", "ESPN"],
                "conflict": {"NBA Injury Report": "QUESTIONABLE", "ESPN": "OUT"},
            }
        ]
        fresh = fresh_minimal(cedera_baru=cedera)
        fresh["inputs"]["home"]["injuries"] = cedera
        fresh["inputs"]["away"]["injuries"] = []
        laporan = recheck.decide(analisis, fresh, sekarang=SEKARANG)
        # QUESTIONABLE baru (bukan OUT/DOUBTFUL) -> tidak resim, tapi
        # konflik baru -> PERHATIAN.
        self.assertEqual(laporan["verdict"], "GO")
        self.assertEqual(laporan["legs"][0]["verdict"], "PERHATIAN")


class TestCondongKeMarket(unittest.TestCase):
    def test_det_atl_fixture_asuransi_jangan_pasang(self):
        analisis = muat_fixture("det_atl_analysis.json")
        fresh = muat_fixture("det_atl_fresh.json")
        laporan = recheck.decide(analisis, fresh, sekarang=SEKARANG)
        self.assertEqual(laporan["verdict"], "NO_GO")
        by_ticket = {leg["leg_id"]: leg for leg in laporan["legs"]}
        asuransi = by_ticket["DET@ATL_2026-11-22:total_under_233.5:insurance"]
        utama = by_ticket["DET@ATL_2026-11-22:total_under_233.5:main"]
        self.assertEqual(asuransi["verdict"], "JANGAN_PASANG")
        self.assertEqual(asuransi["probability_used"], "market")
        self.assertEqual(asuransi["probability_value"], 0.665)
        self.assertEqual(asuransi["kenapa_beda"]["gap_points"], 6.5)
        self.assertTrue(asuransi["kenapa_beda"]["triggered"])
        self.assertFalse(asuransi["kenapa_beda"]["reason_found"])
        self.assertIn("condong_ke_market", asuransi["reasons"][0])
        # Kaki Utama tidak kena aturan ini.
        self.assertEqual(utama["verdict"], "TETAP_OK")
        self.assertEqual(utama["probability_used"], "model")
        self.assertEqual(utama["probability_value"], 0.77)
        validasi_skema(laporan)

    def test_pesan_action_required_baru(self):
        # Aturan condong menolak kaki Asuransi: pesan lama ("cari garis
        # Asuransi lain") menyesatkan karena seleksi sudah naik tangga —
        # pesan baru menjelaskan kaki ditolak setelah naik tangga.
        # Logika condong TIDAK berubah: market dipakai, nilai sama.
        analisis = muat_fixture("det_atl_analysis.json")
        fresh = muat_fixture("det_atl_fresh.json")
        laporan = recheck.decide(analisis, fresh, sekarang=SEKARANG)
        self.assertEqual(laporan["verdict"], "NO_GO")
        self.assertIn(
            "sudah menaikkan garis ke anak tangga", laporan["action_required"]
        )
        self.assertIn("di bawah ambang Asuransi", laporan["action_required"])
        self.assertNotIn("cari garis Asuransi lain", laporan["action_required"])
        asuransi = next(
            leg for leg in laporan["legs"] if leg["leg_id"].endswith(":insurance")
        )
        self.assertEqual(asuransi["probability_used"], "market")
        self.assertEqual(asuransi["probability_value"], 0.665)
        self.assertEqual(asuransi["verdict"], "JANGAN_PASANG")

    def test_alasan_konkret_ada_model_dipakai(self):
        # Cedera bintang baru OUT + garis market tidak bergerak:
        # market belum menghargai cedera -> model boleh dipakai.
        analisis = analisis_minimal(median=219.0)
        cedera = [
            {
                "player": "Cade Cunningham",
                "status": "OUT",
                "team_tricode": "DET",
                "sources": ["NBA Injury Report", "ESPN"],
            }
        ]
        fresh = fresh_minimal(cedera_baru=cedera)
        laporan = recheck.decide(
            analisis,
            fresh,
            resim_fn=resim_stub(garis_baru=233.5, median_baru=216.0),
            sekarang=SEKARANG,
        )
        leg = laporan["legs"][0]
        self.assertTrue(leg["kenapa_beda"]["triggered"])
        self.assertTrue(leg["kenapa_beda"]["reason_found"])
        self.assertIn("Cade Cunningham", leg["kenapa_beda"]["reason"])
        self.assertIn("OUT", leg["kenapa_beda"]["reason"])
        self.assertEqual(leg["probability_used"], "model")
        self.assertEqual(leg["verdict"], "PERHATIAN")  # resim, garis tetap
        self.assertEqual(laporan["verdict"], "GO")
        validasi_skema(laporan)

    def test_market_sudah_bergerak_searah_alasan_tidak_ada(self):
        # Median model turun 3 poin DAN garis market turun 3 poin:
        # market sudah menghargai cedera -> alasan (a) tidak berlaku.
        analisis = analisis_minimal(median=219.0)
        cedera = [
            {
                "player": "Cade Cunningham",
                "status": "OUT",
                "team_tricode": "DET",
                "sources": ["NBA Injury Report", "ESPN"],
            }
        ]
        fresh = fresh_minimal(cedera_baru=cedera)
        fresh["ladders"] = tangga_minimal({233.5: 66.5}, garis_utama=222.5)
        laporan = recheck.decide(
            analisis,
            fresh,
            resim_fn=resim_stub(garis_baru=233.5, median_baru=216.0),
            sekarang=SEKARANG,
        )
        leg = laporan["legs"][0]
        self.assertTrue(leg["kenapa_beda"]["triggered"])
        self.assertFalse(leg["kenapa_beda"]["reason_found"])
        self.assertEqual(leg["probability_used"], "market")
        self.assertEqual(leg["probability_value"], 0.665)
        self.assertEqual(leg["verdict"], "JANGAN_PASANG")

    def test_probabilitas_market_lolos_ambang(self):
        # Pemicu aktif, tanpa alasan, tapi harga market 75c >= 74%:
        # lolos syarat peluang -> PERHATIAN (basis probabilitas berubah).
        analisis = analisis_minimal(
            median=219.0, legs=[kaki(harga=75.0, jup=75.5, p_model=0.77)]
        )
        analisis["price_snapshots"] = {
            "total_under_233.5": {"cents": 75.5, "at": "2026-11-22T10:00:00+00:00"}
        }
        fresh = fresh_minimal({233.5: 75.0})
        fresh["ladders"]["totals"] = [
            entri_tangga(225.5, "under", 50.0, 45000.0),
            entri_tangga(225.5, "over", 50.0, 45000.0),
            entri_tangga(233.5, "under", 75.0, 8000.0, jup=75.5),
        ]
        laporan = recheck.decide(analisis, fresh, sekarang=SEKARANG)
        leg = laporan["legs"][0]
        self.assertTrue(leg["kenapa_beda"]["triggered"])
        self.assertEqual(leg["probability_used"], "market")
        self.assertEqual(leg["probability_value"], 0.75)
        self.assertEqual(leg["verdict"], "PERHATIAN")
        self.assertEqual(laporan["verdict"], "GO")

    def test_mid_cents_fallback(self):
        analisis = muat_fixture("det_atl_analysis.json")
        analisis["legs"] = [analisis["legs"][0]]  # hanya Asuransi
        fresh = muat_fixture("det_atl_fresh.json")
        for entri in fresh["ladders"]["totals"]:
            if entri["line"] == 233.5 and entri["side"] == "under":
                entri["price_cents"] = None
                entri["mid_cents"] = 70.0
        laporan = recheck.decide(analisis, fresh, sekarang=SEKARANG)
        leg = laporan["legs"][0]
        self.assertEqual(leg["probability_value"], 0.70)
        self.assertEqual(leg["verdict"], "JANGAN_PASANG")

    def test_harga_market_tidak_ada_data_incomplete(self):
        analisis = muat_fixture("det_atl_analysis.json")
        analisis["legs"] = [analisis["legs"][0]]  # hanya Asuransi
        fresh = muat_fixture("det_atl_fresh.json")
        for entri in fresh["ladders"]["totals"]:
            if entri["line"] == 233.5 and entri["side"] == "under":
                entri["price_cents"] = None
                entri["mid_cents"] = None
        laporan = recheck.decide(analisis, fresh, sekarang=SEKARANG)
        leg = laporan["legs"][0]
        self.assertEqual(leg["probability_used"], "market")
        self.assertIsNone(leg["probability_value"])
        self.assertEqual(leg["verdict"], "DATA_INCOMPLETE")

    def test_pemicu_tidak_aktif_model_dipakai(self):
        laporan = recheck.decide(
            analisis_minimal(median=224.0), fresh_minimal(), sekarang=SEKARANG
        )
        leg = laporan["legs"][0]
        self.assertEqual(leg["kenapa_beda"]["gap_points"], 1.5)
        self.assertFalse(leg["kenapa_beda"]["triggered"])
        self.assertFalse(leg["kenapa_beda"]["reason_found"])
        self.assertEqual(leg["probability_used"], "model")


class TestResimDefault(unittest.TestCase):
    def _cfg_kecil(self):
        cfg = copy.deepcopy(config.load_playstyle())
        cfg["simulation"]["iterations"] = 200
        return cfg

    def _inputs_minimal(self):
        blok = {
            "tricode": "ATL",
            "stats_season": {"off_rtg": 115.0, "def_rtg": 110.0, "pace": 100.0},
            "players": [],
            "injuries": [],
        }
        return {
            "home": dict(blok),
            "away": dict(blok, tricode="DET"),
            "match": {"game_date": "2026-11-22", "season": "2026-27"},
            "league": {},
        }

    def _tangga_lebar(self):
        totals = []
        for i, garis in enumerate([199.5 + 2.0 * k for k in range(31)]):
            harga = round(5.0 + (90.0 * i / 30.0), 1)
            totals.append(entri_tangga(garis, "under", harga, 1000.0))
        totals.append(entri_tangga(225.5, "over", 50.0, 45000.0))
        return {
            "slug": "nba-det-atl-2026-11-22",
            "totals": totals,
            # Spreads ikut dalam ladder tapi DIABAIKAN hitung ulang
            # sejak bantalan adaptif menggantikan aturan spread.
            "spreads": [
                {
                    "line": -5.5,
                    "side": "home",
                    "team": "Atlanta Hawks",
                    "price_cents": 55.0,
                    "volume_usd": 30000.0,
                },
                {
                    "line": 5.5,
                    "side": "away",
                    "team": "Detroit Pistons",
                    "price_cents": 45.0,
                    "volume_usd": 29000.0,
                },
            ],
        }

    def test_tanpa_inputs_value_error(self):
        with self.assertRaises(ValueError):
            recheck._resim_default({"inputs": None, "ladders": {"totals": []}})

    def test_tangga_kosong_value_error(self):
        with self.assertRaises(ValueError):
            recheck._resim_default(
                {"inputs": self._inputs_minimal(), "ladders": {"totals": []}}
            )

    def test_end_to_end_sim_nyata(self):
        cfg = self._cfg_kecil()
        fresh = {
            "inputs": self._inputs_minimal(),
            "ladders": self._tangga_lebar(),
            "fetched_at": "2026-11-22T12:00:00+00:00",
            "errors": {},
        }
        analisis = analisis_minimal(legs=[kaki(tiket="insurance"), kaki(tiket="main")])
        # Sim NYATA; cushion + analis di-stub (signature baru).
        with (
            stub_cushion(CushionStub()),
            stub_analis({"cushion_points": 8.0, "alasan": "stub"}),
        ):
            hasil = recheck._resim_default(fresh, cfg=cfg, analysis=analisis)
        self.assertIn("simulation", hasil)
        self.assertEqual(len(hasil["legs"]), 2)
        for leg in hasil["legs"]:
            self.assertTrue(leg["meets"])
            self.assertIsNotNone(leg["line"])
            self.assertIsNotNone(leg["p_model"])
            self.assertIsNotNone(leg["p_final"])
            self.assertIsNotNone(leg["price_label"])
            self.assertEqual(leg["cushion_points"], 8.0)

    def test_sharp_move_menekan_label_kaki_resim(self):
        # Pola Thunder lewat _resim_default: snapshot 75¢, tangga segar
        # 71¢ -> sharp move 4¢ untuk kedua tiket (garis sama 233.5).
        # Tes ini property-style (tidak bergantung hasil sim): kaki
        # resim TIDAK BOLEH berlabel DISKON polos, dan bila EV-nya
        # memenuhi ambang DISKON, labelnya harus DISKON_DITEKAN.
        cfg = self._cfg_kecil()
        ladders = self._tangga_lebar()
        for entri in ladders["totals"]:
            if entri["line"] == 233.5 and entri["side"] == "under":
                entri["price_cents"] = 71.0
                entri["jup_estimated_cents"] = 71.0
        fresh = {
            "inputs": self._inputs_minimal(),
            "ladders": ladders,
            "fetched_at": "2026-11-22T12:00:00+00:00",
            "errors": {},
        }
        analisis = analisis_minimal(
            legs=[
                kaki(tiket="insurance", harga=75.0, jup=75.0),
                kaki(tiket="main", harga=75.0, jup=75.0),
            ]
        )
        analisis["price_snapshots"] = {
            "total_under_233.5": {
                "cents": 75.0,
                "at": "2026-11-22T10:00:00+00:00",
            }
        }
        with (
            stub_cushion(CushionStub()),
            stub_analis({"cushion_points": 8.0, "alasan": "stub"}),
        ):
            hasil = recheck._resim_default(fresh, cfg=cfg, analysis=analisis)
        self.assertEqual(len(hasil["legs"]), 2)
        for leg in hasil["legs"]:
            self.assertNotEqual(leg["price_label"], "DISKON")
            if leg["ev_pct"] is not None and leg["ev_pct"] >= 2.0:
                self.assertEqual(leg["price_label"], "DISKON_DITEKAN")

    def test_fallback_inputs_lama(self):
        cfg = self._cfg_kecil()
        fresh = {
            "inputs": None,
            "ladders": self._tangga_lebar(),
            "fetched_at": "2026-11-22T12:00:00+00:00",
            "errors": {},
        }
        analisis = analisis_minimal()
        analisis["inputs"] = self._inputs_minimal()
        with (
            stub_cushion(CushionStub()),
            stub_analis({"cushion_points": 8.0, "alasan": "stub"}),
        ):
            hasil = recheck._resim_default(fresh, cfg=cfg, analysis=analisis)
        self.assertEqual(len(hasil["legs"]), 1)

    def test_bangun_kaki_tidak_meets(self):
        simulation = {
            "match_id": "DET@ATL_2026-11-22",
            "score_distribution": {
                "total": {"median": 219.0, "p74": 231.0, "p75": 232.0}
            },
            "markets": {"total_under_233.5": 0.77},
        }
        # Stub cushion mengembalikan meets=False (tidak ada garis lolos).
        entri = [entri_tangga(229.5, "under", 60.0, 1000.0)]
        with (
            stub_cushion(CushionStub(garis_ins=None)),
            stub_analis({"cushion_points": 8.0, "alasan": "stub"}),
        ):
            legs = recheck._bangun_kaki_resim(
                simulation,
                entri,
                225.5,
                [kaki()],
                "DET@ATL_2026-11-22",
                "2026-11-22T12:00:00+00:00",
                config.load_playstyle(),
                inputs=inputs_minimal_bantalan(),
            )
        self.assertEqual(len(legs), 1)
        self.assertFalse(legs[0]["meets"])
        self.assertEqual(legs[0]["line"], 233.5)  # garis lama dipertahankan
        self.assertIsNotNone(legs[0]["reason"])
        self.assertEqual(legs[0]["cushion_points"], 8.0)

    def test_resim_fn_bentuk_rusak_data_incomplete(self):
        fresh = fresh_minimal({233.5: 66.5})
        fresh["ladders"] = tangga_minimal({233.5: 66.5}, garis_utama=228.0)
        laporan = recheck.decide(
            analisis_minimal(),
            fresh,
            resim_fn=lambda f: {"simulation": {}},
            sekarang=SEKARANG,
        )
        self.assertEqual(laporan["legs"][0]["verdict"], "DATA_INCOMPLETE")


class TestFetchFreshParseEvent(unittest.TestCase):
    def test_fetch_ladder_event_gamma_di_parse(self):
        def _ladder(analysis, client=None):
            from ingest.common import FetchResult

            return FetchResult(
                "Polymarket Gamma",
                1,
                "2026-11-22T12:00:00+00:00",
                True,
                data={
                    "slug": "nba-det-atl-2026-11-22",
                    "title": "Detroit Pistons vs. Atlanta Hawks",
                    "markets": [],
                },
            )

        hasil = recheck.fetch_fresh(
            analisis_minimal(),
            fetch_inputs=lambda a, c=None: {},
            fetch_ladder=_ladder,
        )
        self.assertEqual(hasil["ladders"]["slug"], "nba-det-atl-2026-11-22")
        self.assertEqual(hasil["ladders"]["totals"], [])
        self.assertNotIn("ladders", hasil["errors"])


class TestValidateRecheck(unittest.TestCase):
    def test_laporan_valid(self):
        laporan = recheck.decide(analisis_minimal(), fresh_minimal(), sekarang=SEKARANG)
        self.assertIsNone(recheck.validate_recheck(laporan))

    def test_laporan_tanpa_verdict_ditolak(self):
        laporan = recheck.decide(analisis_minimal(), fresh_minimal(), sekarang=SEKARANG)
        del laporan["verdict"]
        self.assertIsNotNone(recheck.validate_recheck(laporan))


class TestSpreadDariTangga(unittest.TestCase):
    def test_spread_volume_terbesar_absolut(self):
        spreads = [
            {"line": -1.5, "volume_usd": 100.0},
            {"line": -5.5, "volume_usd": 30000.0},
            {"line": 5.5, "volume_usd": 29000.0},
        ]
        self.assertEqual(recheck.spread_abs_dari_tangga(spreads), 5.5)

    def test_spread_tidak_ada_none(self):
        self.assertIsNone(recheck.spread_abs_dari_tangga([]))
        self.assertIsNone(recheck.spread_abs_dari_tangga(None))
        self.assertIsNone(
            recheck.spread_abs_dari_tangga([{"line": -5.5}])
        )  # tanpa volume

    def test_spread_seri_entri_pertama(self):
        spreads = [
            {"line": -3.5, "volume_usd": 1000.0},
            {"line": 7.5, "volume_usd": 1000.0},
        ]
        self.assertEqual(recheck.spread_abs_dari_tangga(spreads), 3.5)


class TestBangunKakiSignatureBaru(unittest.TestCase):
    """Pemanggilan cushion signature baru + bantalan adaptif di resim.

    Cushion + analis di-stub (keduanya dibangun paralel pekerja A);
    tes ini menguji wiring recheck: argumen yang diteruskan, urutan
    Utama-dulu, dan fail-closed bila bantalan tidak tersedia.
    """

    def _sim_dan_tangga(self):
        simulation = {
            "match_id": "DET@ATL_2026-11-22",
            "score_distribution": {
                "total": {
                    "median": 219.0,
                    "std": 19.0,
                    "p74": 231.0,
                    "p75": 232.0,
                }
            },
            "markets": {
                f"total_under_{garis:g}": 0.70
                for garis in (229.5, 231.5, 233.5, 235.5, 237.5, 239.5, 241.5)
            },
        }
        entri = [
            entri_tangga(garis, "under", 60.0 + i, 1000.0)
            for i, garis in enumerate((229.5, 231.5, 233.5, 235.5, 237.5, 239.5, 241.5))
        ]
        return simulation, entri

    def _bangun(self, simulation, entri, legs, cushion_stub, cfg=None, inputs=None):
        return recheck._bangun_kaki_resim(
            simulation,
            entri,
            225.5,
            legs,
            "DET@ATL_2026-11-22",
            "2026-11-22T12:00:00+00:00",
            cfg or config.load_playstyle(),
            inputs=inputs if inputs is not None else inputs_minimal_bantalan(),
        )

    def test_utama_dipanggil_dengan_bantalan_adaptif(self):
        simulation, entri = self._sim_dan_tangga()
        stub = CushionStub(garis_main=237.5)
        with (
            stub_cushion(stub),
            stub_analis({"cushion_points": 12.0, "alasan": "laga ketat"}),
        ):
            legs = self._bangun(simulation, entri, [kaki(tiket="main")], stub)
        self.assertEqual(len(stub.calls), 1)
        tiket, kwargs = stub.calls[0]
        self.assertEqual(tiket, "main")
        self.assertEqual(kwargs["cushion_points"], 12.0)
        self.assertIs(kwargs["peluang_under"], simulation["markets"])
        self.assertEqual(kwargs["harga_min_cents"], 75)
        self.assertTrue(legs[0]["meets"])
        self.assertEqual(legs[0]["line"], 237.5)
        self.assertEqual(legs[0]["cushion_points"], 12.0)
        self.assertEqual(legs[0]["cushion_reason"], "laga ketat")

    def test_insurance_dipanggil_dengan_garis_di_atas(self):
        simulation, entri = self._sim_dan_tangga()
        stub = CushionStub(garis_ins=239.5, garis_main=237.5)
        with (
            stub_cushion(stub),
            stub_analis({"cushion_points": 12.0, "alasan": "stub"}),
        ):
            legs = self._bangun(
                simulation,
                entri,
                [kaki(tiket="insurance"), kaki(tiket="main")],
                stub,
            )
        # Utama dipanggil DULU, lalu Asuransi dengan garis_di_atas.
        self.assertEqual([c[0] for c in stub.calls], ["main", "insurance"])
        panggilan_ins = next(c for c in stub.calls if c[0] == "insurance")
        self.assertEqual(panggilan_ins[1]["garis_di_atas"], 237.5)
        self.assertEqual(panggilan_ins[1]["harga_min_cents"], 75)
        garis = {leg["ticket"]: leg["line"] for leg in legs}
        self.assertEqual(garis, {"insurance": 239.5, "main": 237.5})

    def test_insurance_tanpa_garis_utama_bila_utama_gagal(self):
        simulation, entri = self._sim_dan_tangga()
        stub = CushionStub(garis_ins=239.5, garis_main=None)
        with (
            stub_cushion(stub),
            stub_analis({"cushion_points": 12.0, "alasan": "stub"}),
        ):
            legs = self._bangun(
                simulation,
                entri,
                [kaki(tiket="insurance"), kaki(tiket="main")],
                stub,
            )
        panggilan_ins = next(c for c in stub.calls if c[0] == "insurance")
        self.assertIsNone(panggilan_ins[1]["garis_di_atas"])
        leg_main = next(leg for leg in legs if leg["ticket"] == "main")
        self.assertFalse(leg_main["meets"])
        self.assertEqual(leg_main["line"], 233.5)  # garis lama dipertahankan

    def test_harga_min_dari_config(self):
        simulation, entri = self._sim_dan_tangga()
        cfg = copy.deepcopy(config.load_playstyle())
        cfg["analis"]["harga_min_utama_cents"] = 80
        cfg["analis"]["harga_min_asuransi_cents"] = 81
        stub = CushionStub()
        with (
            stub_cushion(stub),
            stub_analis({"cushion_points": 8.0, "alasan": "stub"}),
        ):
            self._bangun(
                simulation,
                entri,
                [kaki(tiket="insurance"), kaki(tiket="main")],
                stub,
                cfg=cfg,
            )
        harga = {tiket: kwargs["harga_min_cents"] for tiket, kwargs in stub.calls}
        self.assertEqual(harga, {"main": 80, "insurance": 81})

    def test_harga_min_default_75_bila_kunci_hilang(self):
        simulation, entri = self._sim_dan_tangga()
        cfg = copy.deepcopy(config.load_playstyle())
        del cfg["analis"]
        stub = CushionStub()
        with (
            stub_cushion(stub),
            stub_analis({"cushion_points": 8.0, "alasan": "stub"}),
        ):
            self._bangun(
                simulation,
                entri,
                [kaki(tiket="insurance"), kaki(tiket="main")],
                stub,
                cfg=cfg,
            )
        for _tiket, kwargs in stub.calls:
            self.assertEqual(kwargs["harga_min_cents"], 75)

    def test_harga_min_tidak_valid_value_error(self):
        simulation, entri = self._sim_dan_tangga()
        cfg = copy.deepcopy(config.load_playstyle())
        cfg["analis"]["harga_min_utama_cents"] = 150
        stub = CushionStub()
        with (
            stub_cushion(stub),
            stub_analis({"cushion_points": 8.0, "alasan": "stub"}),
            self.assertRaises(ValueError),
        ):
            self._bangun(simulation, entri, [kaki(tiket="main")], stub, cfg=cfg)

    def test_bantalan_tidak_tersedia_tanpa_inputs(self):
        # inputs None -> kedua kaki fail-closed, cushion TIDAK dipanggil.
        simulation, entri = self._sim_dan_tangga()
        stub = CushionStub()
        with stub_cushion(stub):
            legs = recheck._bangun_kaki_resim(
                simulation,
                entri,
                225.5,
                [kaki(tiket="insurance"), kaki(tiket="main")],
                "DET@ATL_2026-11-22",
                "2026-11-22T12:00:00+00:00",
                config.load_playstyle(),
                inputs=None,
            )
        self.assertEqual(stub.calls, [])
        self.assertEqual(len(legs), 2)
        for leg in legs:
            self.assertFalse(leg["meets"])
            self.assertEqual(leg["reason"], "inputs_tidak_tersedia")
            self.assertIsNone(leg["cushion_points"])
            self.assertEqual(leg["cushion_reason"], "inputs_tidak_tersedia")

    def test_analis_hilang_kedua_kaki_fail_closed(self):
        simulation, entri = self._sim_dan_tangga()
        stub = CushionStub()
        asli = recheck._muat_modul

        def _palsu(nama):
            if nama == "engine.analis":
                return None
            return asli(nama)

        with (
            stub_cushion(stub),
            mock.patch.object(recheck, "_muat_modul", side_effect=_palsu),
        ):
            legs = self._bangun(
                simulation,
                entri,
                [kaki(tiket="insurance"), kaki(tiket="main")],
                stub,
            )
        self.assertEqual(stub.calls, [])
        for leg in legs:
            self.assertFalse(leg["meets"])
            self.assertEqual(leg["reason"], "analis_belum_tersedia")

    def test_analis_mengembalikan_none(self):
        simulation, entri = self._sim_dan_tangga()
        stub = CushionStub()
        with stub_cushion(stub), stub_analis(None):
            legs = self._bangun(
                simulation,
                entri,
                [kaki(tiket="insurance"), kaki(tiket="main")],
                stub,
            )
        self.assertEqual(stub.calls, [])
        for leg in legs:
            self.assertFalse(leg["meets"])
            self.assertEqual(leg["reason"], "bantalan_adaptif_tidak_tersedia")

    def test_analis_gagal_exception(self):
        simulation, entri = self._sim_dan_tangga()
        stub = CushionStub()
        with stub_cushion(stub), stub_analis(exception=RuntimeError("boom")):
            legs = self._bangun(
                simulation,
                entri,
                [kaki(tiket="insurance"), kaki(tiket="main")],
                stub,
            )
        self.assertEqual(stub.calls, [])
        for leg in legs:
            self.assertFalse(leg["meets"])
            self.assertEqual(leg["reason"], "bantalan_adaptif_gagal: RuntimeError")

    def test_analis_menerima_input_yang_sama_dengan_nba_analysis(self):
        # bantalan_adaptif dipanggil dengan (stats_laga dari inputs,
        # distribusi sim segar) — input yang sama seperti nba_analysis.
        simulation, entri = self._sim_dan_tangga()
        stub = CushionStub()
        with (
            stub_cushion(stub),
            stub_analis({"cushion_points": 8.0, "alasan": "stub"}) as analis,
        ):
            self._bangun(simulation, entri, [kaki(tiket="main")], stub)
        self.assertEqual(len(analis.calls), 1)
        panggilan = analis.calls[0]
        self.assertEqual(panggilan["stats_laga"]["ortg_home"], 115.0)
        self.assertEqual(panggilan["stats_laga"]["ortg_away"], 110.0)
        self.assertEqual(panggilan["stats_laga"]["ortg_liga_rata"], 112.0)
        self.assertEqual(panggilan["distribusi_sim"]["median"], 219.0)
        self.assertEqual(panggilan["distribusi_sim"]["std"], 19.0)


class TestResimSharpMoveBukanDiskon(unittest.TestCase):
    """Kaki resim: sharp move menekan label DISKON (kasus Thunder).

    EV deterministik: p_model 0,70 + p_market 0,66 (kaki lama) ->
    p_final 0,672; di harga 64¢ EV = +5,0% -> DISKON tanpa penekanan.
    """

    def _sim_dan_tangga(self):
        simulation = {
            "match_id": "DET@ATL_2026-11-22",
            "score_distribution": {
                "total": {
                    "median": 219.0,
                    "std": 19.0,
                    "p74": 231.0,
                    "p75": 232.0,
                }
            },
            "markets": {
                f"total_under_{garis:g}": 0.70
                for garis in (229.5, 231.5, 233.5, 235.5, 237.5, 239.5, 241.5)
            },
        }
        entri = [
            entri_tangga(garis, "under", 60.0 + i, 1000.0)
            for i, garis in enumerate((229.5, 231.5, 233.5, 235.5, 237.5, 239.5, 241.5))
        ]
        return simulation, entri

    def _bangun(self, simulation, entri, legs, sharp=None):
        with (
            stub_cushion(CushionStub(garis_main=237.5)),
            stub_analis({"cushion_points": 12.0, "alasan": "stub"}),
        ):
            return recheck._bangun_kaki_resim(
                simulation,
                entri,
                225.5,
                legs,
                "DET@ATL_2026-11-22",
                "2026-11-22T12:00:00+00:00",
                config.load_playstyle(),
                inputs=inputs_minimal_bantalan(),
                sharp_move_per_tiket=sharp,
            )

    def test_label_ditekan_bila_sharp_move(self):
        simulation, entri = self._sim_dan_tangga()
        legs = self._bangun(
            simulation, entri, [kaki(tiket="main")], sharp={"main": True}
        )
        self.assertEqual(legs[0]["ev_pct"], 5.0)
        self.assertEqual(legs[0]["price_label"], "DISKON_DITEKAN")

    def test_label_diskon_bila_tanpa_sharp_move(self):
        simulation, entri = self._sim_dan_tangga()
        legs = self._bangun(simulation, entri, [kaki(tiket="main")])
        self.assertEqual(legs[0]["price_label"], "DISKON")

    def test_sharp_move_tiket_lain_tidak_menekan(self):
        # Sharp move di tiket insurance tidak menekan label kaki main.
        simulation, entri = self._sim_dan_tangga()
        legs = self._bangun(
            simulation, entri, [kaki(tiket="main")], sharp={"insurance": True}
        )
        self.assertEqual(legs[0]["price_label"], "DISKON")


class TestIstirahatMendadak(unittest.TestCase):
    """Bukti item 6 Langkah 2: recheck menangkap kabar istirahat mendadak.

    Skenario (offline, sim NYATA 20.000 iterasi — bukan stub resim):
    analisis awal 21:30 UTC, bintang Cade Cunningham tersedia, median
    224, garis market 225,5; recheck 23:45 UTC — 45 menit sebelum
    tip-off 00:30 UTC — menemukan Cade OUT karena Rest. Entri OUT/rest
    di fresh inputs persis bentuk yang dihasilkan lapisan ketersediaan
    dari entri ESPN "(rest)" (lihat TestLapisanKetersediaan di
    tests/test_ingest_nba_brain.py). Harga + garis market diam — SATU-
    SATUNYA perubahan adalah kabar istirahat itu, jadi perubahan
    putusan bisa diatribusikan ke kabar tersebut.
    """

    RECHECK = "2026-11-22T23:45:00+00:00"

    def _cfg(self):
        cfg = copy.deepcopy(config.load_playstyle())
        cfg["simulation"]["iterations"] = 20000
        return cfg

    def _inputs(self, bintang_out=False):
        cedera_det = []
        if bintang_out:
            cedera_det = [
                {
                    "player": "Cade Cunningham",
                    "status": "OUT",
                    "team_tricode": "DET",
                    "sources": ["ESPN"],
                    "is_injury": False,
                    "reason": "rest",
                    "availability_n_sources": 1,
                }
            ]
        blok = {
            "tricode": "ATL",
            "stats_season": {"off_rtg": 115.0, "def_rtg": 110.0, "pace": 100.0},
            "players": [],
            "injuries": [],
        }
        return {
            "home": dict(blok),
            "away": dict(
                blok,
                tricode="DET",
                players=[
                    {
                        "player": "Cade Cunningham",
                        "bpm": 6.0,
                        "mp_per_game": 34.0,
                        "games_played": 17,
                    }
                ],
                injuries=cedera_det,
            ),
            "match": {"game_date": "2026-11-22", "season": "2026-27"},
            "league": {},
        }

    def _tangga_lebar(self):
        totals = []
        for i, garis in enumerate([199.5 + 2.0 * k for k in range(31)]):
            # Harga Under 233.5 DIAM di 66,5c (jup 67,0c) seperti
            # analisis awal — tidak ada gerak harga di fixture ini.
            if garis == 233.5:
                totals.append(entri_tangga(garis, "under", 66.5, 8000.0, jup=67.0))
                continue
            harga = round(5.0 + (90.0 * i / 30.0), 1)
            totals.append(entri_tangga(garis, "under", harga, 1000.0))
        totals.append(entri_tangga(225.5, "over", 50.0, 45000.0))
        return {
            "slug": "nba-det-atl-2026-11-22",
            "totals": totals,
            # Spreads ikut dalam ladder tapi DIABAIKAN hitung ulang
            # sejak bantalan adaptif menggantikan aturan spread.
            "spreads": [
                {
                    "line": -5.5,
                    "side": "home",
                    "team": "Atlanta Hawks",
                    "price_cents": 55.0,
                    "volume_usd": 30000.0,
                },
                {
                    "line": 5.5,
                    "side": "away",
                    "team": "Detroit Pistons",
                    "price_cents": 45.0,
                    "volume_usd": 29000.0,
                },
            ],
        }

    def _analisis_dan_fresh(self):
        # Kedua kaki di 233.5 (garis stub cushion di tes ini).
        analisis = analisis_minimal(
            legs=[kaki(tiket="insurance"), kaki(tiket="main")],
        )
        analisis["generated_at"] = "2026-11-22T21:30:00+00:00"
        analisis["injuries"]["fetched_at"] = "2026-11-22T21:30:00+00:00"
        analisis["inputs"] = self._inputs(bintang_out=False)
        fresh = {
            "inputs": self._inputs(bintang_out=True),
            "ladders": self._tangga_lebar(),
            "moneyline_jup": None,
            "fetched_at": self.RECHECK,
            "errors": {},
        }
        return analisis, fresh

    def test_rest_mendadak_resim_dan_putusan_berubah(self):
        analisis, fresh = self._analisis_dan_fresh()
        # Sim NYATA; cushion + analis di-stub (garis tetap 233.5).
        with (
            stub_cushion(CushionStub()),
            stub_analis({"cushion_points": 8.0, "alasan": "stub"}),
        ):
            laporan = recheck.decide(
                analisis, fresh, cfg=self._cfg(), sekarang=self.RECHECK
            )
        # Resim dipicu kabar cedera baru (OUT apa pun alasannya).
        self.assertTrue(laporan["resimulated"])
        self.assertTrue(any("cedera_baru" in a for a in laporan["resim_reasons"]))
        perubahan_cedera = [c for c in laporan["changes"] if c["kind"] == "injury"]
        self.assertEqual(len(perubahan_cedera), 1)
        self.assertIn("Cade Cunningham", perubahan_cedera[0]["detail"])
        # Dampak absen Cade: (6,0-(-2,0)) x 34/48 = 5,67 poin —
        # median turun ~224 -> ~218, selisih vs garis market 225,5
        # melewati ambang 5,0, TAPI kabar Rest itu sendiri adalah
        # alasan konkret aturan condong-ke-market (market diam) ->
        # probabilitas model tetap dipakai, kaki tidak gagal Asuransi
        # karena aturan itu.
        for leg in laporan["legs"]:
            self.assertTrue(leg["resimulated"])
            self.assertEqual(leg["kenapa_beda"]["triggered"], True)
            self.assertEqual(leg["kenapa_beda"]["reason_found"], True)
            self.assertEqual(leg["probability_used"], "model")
            # Garis tidak berubah (stub cushion mengembalikan 233.5) ->
            # PERHATIAN, bukan TETAP_OK: putusan berubah karena resim.
            self.assertEqual(leg["verdict"], "PERHATIAN")
            self.assertEqual(leg["new_line"], 233.5)
        self.assertEqual(laporan["verdict"], "GO")
        self.assertTrue(laporan["attention"])
        validasi_skema(laporan)

    def test_alasan_rest_tercatat_di_sim_hasil_resim(self):
        analisis, fresh = self._analisis_dan_fresh()
        with (
            stub_cushion(CushionStub()),
            stub_analis({"cushion_points": 8.0, "alasan": "stub"}),
        ):
            hasil = recheck._resim_default(fresh, cfg=self._cfg(), analysis=analisis)
        notes = hasil["simulation"]["inputs_summary"]["notes"]
        self.assertIn("pemain OUT: Cade Cunningham (alasan: rest)", notes)
        # Median sim segar turun dibanding analisis awal (dampak absen
        # Cade ~5,67 poin; toleransi longgar untuk noise sim).
        median_baru = hasil["simulation"]["score_distribution"]["total"]["median"]
        self.assertLess(median_baru, 224.0 - 3.0)


if __name__ == "__main__":
    unittest.main()
