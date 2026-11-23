"""Tes short-circuit veto + wiring TUNGGU_LINEUP + Vegas (v18) — TANPA network.

fetch_match_inputs, fetch_event_by_slug, fetch_total_markets,
fetch_news_nba, simulate, dan fetch_pemain_3p_cached di-stub
(unittest.mock). Fixture inputs/event/sim dipakai ulang dari
tests/test_nba_analysis.py (helper _inputs/_blok_tim/_event_gamma/
_sim_stub/_ok) supaya bentuk kontraknya sama dengan builder.

CFG TES: deepcopy playstyle.yaml + kunci veto v17 yang ditulis ulang
(vonis.veto_total_tinggi_points / veto_pace_tinggi +
market_line_check.total_gap_points) — dipertahankan sebagai jaring
pengaman bila rewrite vonis/anomaly worker A berubah lagi; rewrite
v18 SUDAH mendarat (vonis.veto subsection + logika AND) dan fixture
veto di bawah memenuhi logika OR v17 MAUPUN AND v18: garis 237,5
>= 232,0 dan pace 103,22 >= 100,5.
"""

import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_nba_analysis as tna

import config as config_mod
from engine import nba_analysis as na
from engine import vonis as vonis_mod
from ingest import kalshi as kalshi_mod
from ingest import nba_brain as nba_brain_mod
from ingest import news_nba as news_nba_mod
from ingest import pemain_3p as p3p_mod
from ingest import polymarket as polymarket_mod
from ingest.common import FetchResult, now_iso

TANGGAL = "2026-11-22"
START_TIME = "2026-11-23T07:00:00+07:00"
SUMBER_PDF = "Official NBA Injury Report"
SUMBER_ESPN = "ESPN injuries"


def _cfg_tes():
    """Config tes: playstyle nyata + kunci v17 yang dihapus worker A."""
    cfg = copy.deepcopy(config_mod.load_playstyle())
    cfg.setdefault("vonis", {}).update(
        {"veto_total_tinggi_points": 235.0, "veto_pace_tinggi": 102.0}
    )
    cfg.setdefault("market_line_check", {}).update({"total_gap_points": 5.0})
    return cfg


def _inputs_den_chi():
    """Inputs DEN@CHI: Claxton (pelindung ring CHI) OUT terkonfirmasi.

    Pace CHI 103,22 (tercepat) + garis pasar 237,5 (lihat
    _event_den_chi) -> veto menyala di logika OR v17 maupun AND v18.
    """
    cedera_chi = [
        {
            "player": "Nic Claxton",
            "status": "OUT",
            "team_tricode": "CHI",
            "sources": [SUMBER_PDF, SUMBER_ESPN],
            "availability_n_sources": 2,
        },
        {
            "player": "Caleb Wilson",
            "status": "OUT",
            "team_tricode": "CHI",
            "sources": [SUMBER_PDF, SUMBER_ESPN],
            "availability_n_sources": 2,
        },
    ]
    home = tna._blok_tim("CHI", "Chicago Bulls", 114.0, 113.0, 103.22, cedera_chi)
    away = tna._blok_tim("DEN", "Denver Nuggets", 116.0, 112.0, 98.3)
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
        {
            "data_kind": "nba_injuries",
            "source": SUMBER_ESPN,
            "tier": 2,
            "fetched_at": now_iso(),
        },
    ]
    return {
        "match": {
            "home_tricode": "CHI",
            "away_tricode": "DEN",
            "game_date": TANGGAL,
            "season": "2026-27",
        },
        "home": home,
        "away": away,
        "h2h_last5": [],
        "tournament": None,
        "league": {"avg_pace": 99.5, "avg_off_rtg": 113.0},
        "missing": [],
        "sources": sources,
        "fetched_at": now_iso(),
    }


def _event_den_chi():
    """Event Gamma dengan garis utama 237,5 (volume terbesar)."""
    event = copy.deepcopy(tna._event_gamma())
    for pasar in event["markets"]:
        if pasar.get("sportsMarketType") == "totals" and "237.5" in str(
            pasar.get("question")
        ):
            pasar["volume"] = 50000.0
    return event


class _BasisShortCircuit(unittest.TestCase):
    """Helper patch semua fetcher + sim untuk builder."""

    def _patch_semua(self, inputs, event, sim):
        patchers = [
            mock.patch.object(
                nba_brain_mod,
                "fetch_match_inputs",
                return_value=tna._ok(nba_brain_mod.SOURCE, nba_brain_mod.TIER, inputs),
            ),
            mock.patch.object(
                polymarket_mod,
                "fetch_event_by_slug",
                return_value=tna._ok("Polymarket CLOB", 2, event),
            ),
            mock.patch.object(
                kalshi_mod,
                "fetch_total_markets",
                return_value=tna._ok("Kalshi API", 2, []),
            ),
            mock.patch.object(
                news_nba_mod,
                "fetch_news_nba",
                return_value=tna._ok("ESPN", 2, []),
            ),
        ]
        self.mock_sim = mock.patch("engine.nba_sim.simulate", return_value=sim).start()
        self.addCleanup(mock.patch.stopall)
        mocks = {}
        for patcher in patchers:
            mocks[patcher.attribute] = patcher.start()
        self.mock_fetch_inputs = mocks["fetch_match_inputs"]
        self.mock_fetch_tangga = mocks["fetch_event_by_slug"]
        self.mock_kalshi = mocks["fetch_total_markets"]
        self.mock_news = mocks["fetch_news_nba"]
        self.mock_pemain = mock.patch.object(
            p3p_mod,
            "fetch_pemain_3p_cached",
            # Fetch gagal yang SAH (bukan MagicMock mentah — blok
            # setan_pemain "gagal" tetap valid vs skema; tes veto
            # menegaskan mock ini TIDAK dipanggil sama sekali).
            return_value=FetchResult(
                "stats.nba.com",
                2,
                now_iso(),
                False,
                error="stub pemain 3P gagal (tes short-circuit)",
            ),
        ).start()


class TestShortCircuitVeto(_BasisShortCircuit):
    """Laga kena veto: Tahap 3/5/5b/5c dilewati, artefak tetap valid."""

    def test_veto_menyala_lewati_sim_kalshi_news_setan(self):
        sim = tna._sim_stub({"total_under_237.5": 0.83})
        self._patch_semua(_inputs_den_chi(), _event_den_chi(), sim)
        artefak = na.build_nba_analysis(
            "CHI",
            "DEN",
            TANGGAL,
            cfg=_cfg_tes(),
            seed=7,
            iterations=None,
            slate_match=tna._SLATE_MATCH,
            start_time=START_TIME,
        )
        # Tahap 1+2 jalan; Tahap 3/5/5b/5c TIDAK jalan.
        self.mock_fetch_inputs.assert_called_once()
        self.mock_fetch_tangga.assert_called_once()
        self.mock_sim.assert_not_called()
        self.mock_kalshi.assert_not_called()
        self.mock_news.assert_not_called()
        self.mock_pemain.assert_not_called()
        # Artefak tetap ditulis + valid vs skema.
        self.assertEqual(artefak["status"], "DATA_INCOMPLETE")
        self.assertIsNone(na.validate_nba_analysis(artefak))
        self.assertIsNotNone(artefak["inputs"])
        self.assertIsNotNone(artefak["market"])
        self.assertIsNone(artefak["simulation"])
        self.assertEqual(artefak["legs"], [])
        # Blok veto ada + menyala + alasan menyebut Claxton.
        veto = artefak["veto"]
        self.assertTrue(veto["dievaluasi"])
        self.assertTrue(veto["menyala"])
        self.assertTrue(any("Claxton" in a for a in veto["alasan"]))
        self.assertTrue(any("veto_short_circuit" in m for m in artefak["missing"]))
        self.assertTrue(any("vonis_kuning" in m for m in artefak["missing"]))
        # nilai_vonis atas artefak short-circuit tetap KUNING
        # (data_tidak_cukup karena tanpa sim — tapi alasan veto
        # ikut tercatat, bukan hilang).
        hasil_vonis = vonis_mod.nilai_vonis(artefak, None, _cfg_tes())
        self.assertEqual(hasil_vonis["vonis"], "kuning")
        self.assertTrue(
            any("Claxton" in a for a in hasil_vonis["alasan"])
            or hasil_vonis["indikator"]["veto"]["menyala"]
        )

    def test_veto_tidak_menyala_lanjut_normal(self):
        # DEN@CHI dengan garis pasar RENDAH (225,5 < ambang veto 232,0):
        # Claxton OUT + pace 103,22 menyala, tapi kondisi garis TIDAK —
        # logika AND v18 -> veto dievaluasi tapi tidak menyala (hanya
        # peringatan_parsial) -> semua tahap jalan normal.
        # CATATAN FIXTURE: memakai DEN@CHI (bukan DET@ATL) karena
        # pemetaan rim protector v18 yang diregenerasi worker A
        # (position filter + MP >= 18 + BLK >= 1,0) TIDAK memetakan
        # DET/ATL — evaluasi_veto v18 mengembalikan dievaluasi=False
        # untuk laga tanpa tim terpetakan (perilaku vonis A, bukan
        # wiring ini). DEN/CHI terpetakan, jadi tes ini menguji
        # wiring short-circuit, bukan pemetaan.
        sim = tna._sim_stub({"total_under_237.5": 0.83})
        self._patch_semua(_inputs_den_chi(), tna._event_gamma(), sim)
        artefak = na.build_nba_analysis(
            "CHI",
            "DEN",
            TANGGAL,
            cfg=_cfg_tes(),
            seed=7,
            iterations=None,
            slate_match=tna._SLATE_MATCH,
            start_time=START_TIME,
        )
        self.mock_sim.assert_called()
        self.assertEqual(self.mock_sim.call_count, 2)
        self.mock_kalshi.assert_called_once()
        self.mock_news.assert_called_once()
        self.assertIn(artefak["status"], ("OK", "HOLD"))
        self.assertIsNone(na.validate_nba_analysis(artefak))
        veto = artefak["veto"]
        self.assertTrue(veto["dievaluasi"])
        self.assertFalse(veto["menyala"])
        # Bukti logika AND: hanya kondisi pace yang menyala.
        self.assertTrue(veto["peringatan_parsial"])
        self.assertEqual(veto["kondisi_menyala"], ["pace"])
        self.assertFalse(any("veto_short_circuit" in m for m in artefak["missing"]))
        self.assertEqual(len(artefak["legs"]), 2)


class TestTungguLineup(_BasisShortCircuit):
    """Timing gate: tunggu=True -> draf + HOLD (sim tetap jalan)."""

    def test_tunggu_lineup_draf_dan_hold(self):
        sim = tna._sim_stub({"total_under_237.5": 0.83})
        self._patch_semua(tna._inputs(), tna._event_gamma(), sim)
        cek_palsu = mock.Mock(
            return_value={
                "tunggu": True,
                "bintang": ["Karl-Anthony Towns"],
                "alasan": ["bintang Questionable (USG 0,28)"],
            }
        )
        with mock.patch.object(vonis_mod, "cek_tunggu_lineup", cek_palsu, create=True):
            artefak = na.build_nba_analysis(
                tna.HOME,
                tna.AWAY,
                TANGGAL,
                cfg=_cfg_tes(),
                seed=7,
                iterations=None,
                slate_match=tna._SLATE_MATCH,
                start_time=START_TIME,
            )
        cek_palsu.assert_called_once()
        # DRAF: sim + kaki tetap dihitung (bukan berhenti di Tahap 1).
        self.assertEqual(self.mock_sim.call_count, 2)
        self.assertEqual(len(artefak["legs"]), 2)
        self.assertIsNotNone(artefak["simulation"])
        # Tapi status HOLD + blok + missing supaya komposer menahan.
        self.assertEqual(artefak["status"], "HOLD")
        blok = artefak["tunggu_lineup"]
        self.assertTrue(blok["tunggu"])
        self.assertEqual(blok["bintang"], ["Karl-Anthony Towns"])
        self.assertTrue(any("tunggu_lineup" in m for m in artefak["missing"]))
        self.assertIsNone(na.validate_nba_analysis(artefak))

    def test_tidak_tunggu_status_normal(self):
        sim = tna._sim_stub(
            {
                "total_under_219": 0.5,
                "total_under_222.25": 0.56,
                "total_under_225.5": 0.62,
                "total_under_237.5": 0.83,
                "total_under_241.5": 0.86,
            }
        )
        self._patch_semua(tna._inputs(), tna._event_gamma(), sim)
        cek_palsu = mock.Mock(
            return_value={"tunggu": False, "bintang": [], "alasan": []}
        )
        with mock.patch.object(vonis_mod, "cek_tunggu_lineup", cek_palsu, create=True):
            artefak = na.build_nba_analysis(
                tna.HOME,
                tna.AWAY,
                TANGGAL,
                cfg=_cfg_tes(),
                seed=7,
                iterations=None,
                slate_match=tna._SLATE_MATCH,
                start_time=START_TIME,
            )
        self.assertFalse(artefak["tunggu_lineup"]["tunggu"])
        self.assertEqual(artefak["status"], "OK")
        self.assertFalse(any("tunggu_lineup:" in m for m in artefak["missing"]))

    def test_cek_gagal_fail_closed_hold(self):
        sim = tna._sim_stub({"total_under_237.5": 0.83})
        self._patch_semua(tna._inputs(), tna._event_gamma(), sim)
        cek_palsu = mock.Mock(side_effect=RuntimeError("USG fetch meledak"))
        with mock.patch.object(vonis_mod, "cek_tunggu_lineup", cek_palsu, create=True):
            artefak = na.build_nba_analysis(
                tna.HOME,
                tna.AWAY,
                TANGGAL,
                cfg=_cfg_tes(),
                seed=7,
                iterations=None,
                slate_match=tna._SLATE_MATCH,
                start_time=START_TIME,
            )
        # Gate gagal -> tahan laga (HOLD), bukan lolos diam-diam.
        self.assertEqual(artefak["status"], "HOLD")
        self.assertTrue(artefak["tunggu_lineup"]["tunggu"])
        self.assertFalse(artefak["tunggu_lineup"]["dievaluasi"])


class TestVegasWiring(_BasisShortCircuit):
    """Vegas shrinkage: median baru dipakai kaki, mentah tersimpan."""

    def _inputs_tanpa_bintang_out(self):
        """Inputs DET@ATL tanpa cedera (tanpa sebab cedera baru)."""
        inputs = copy.deepcopy(tna._inputs())
        inputs["home"]["injuries"] = []
        return inputs

    def test_geser_diterapkan_kaki_pakai_median_baru(self):
        # Median sim 219,0 vs garis pasar 225,5: gap 6,5 > 5,0,
        # tanpa sebab cedera -> median baru 219 + 0,5x6,5 = 222,25.
        sim = tna._sim_stub(
            {
                "total_under_219": 0.5,
                "total_under_222.25": 0.56,
                "total_under_225.5": 0.62,
                "total_under_237.5": 0.83,
                "total_under_241.5": 0.86,
            }
        )
        self._patch_semua(self._inputs_tanpa_bintang_out(), tna._event_gamma(), sim)
        artefak = na.build_nba_analysis(
            tna.HOME,
            tna.AWAY,
            TANGGAL,
            cfg=_cfg_tes(),
            seed=7,
            iterations=None,
            slate_match=tna._SLATE_MATCH,
            start_time=START_TIME,
        )
        wajar = artefak["analisis_wajar"]
        self.assertTrue(wajar["vegas_diterapkan"])
        self.assertAlmostEqual(wajar["median_disesuaikan"], 222.25)
        self.assertAlmostEqual(wajar["median_mentah"], 219.0)
        self.assertAlmostEqual(wajar["geser_vegas"], 3.25)
        self.assertIn("disusutkan", wajar["vegas_alasan"])
        # Kontrak kanonik v18 (integrasi koordinator): distribusi
        # EFEKTIF menjadi simulation.markets + total; mentah pindah
        # ke markets_mentah + total_mentah (bukti); blok root vegas
        # mencatat keputusan.
        sim = artefak["simulation"]
        dist = sim["score_distribution"]["total"]
        self.assertAlmostEqual(dist["median"], 222.25)
        self.assertAlmostEqual(dist["p74"], 235.25)
        self.assertAlmostEqual(dist["mean"], 222.75)
        self.assertEqual(dist["std"], 19.0)
        mentah = sim["score_distribution"]["total_mentah"]
        self.assertEqual(mentah["median"], 219.0)
        self.assertEqual(mentah["p74"], 232.0)
        # P efektif di 237,5 = CDF mentah di 234,25 (interpolasi
        # linear 225,5->0,62 s.d. 237,5->0,83): 0,62 + (8,75/12)x0,21
        # = 0,773125. Di 241,5: CDF mentah di 238,25 = 0,835625.
        self.assertAlmostEqual(sim["markets"]["total_under_237.5"], 0.773125)
        self.assertAlmostEqual(sim["markets"]["total_under_241.5"], 0.835625)
        self.assertEqual(sim["markets_mentah"]["total_under_237.5"], 0.83)
        self.assertEqual(sim["markets_mentah"]["total_under_241.5"], 0.86)
        vegas = artefak["vegas"]
        self.assertTrue(vegas["diterapkan"])
        self.assertEqual(vegas["median_mentah"], 219.0)
        self.assertAlmostEqual(vegas["median_baru"], 222.25)
        self.assertAlmostEqual(vegas["geser"], 3.25)
        # Pembaca hilir melihat CDF yang disesuaikan: pemuat CDF
        # bersama (dipakai equilibrium/vonis/skip) membaca titik
        # (237,5 -> 0,773125) dari markets artefak, bukan 0,83 mentah.
        from engine import stress as stress_mod

        cdf = dict(stress_mod.cdf_total_dari_markets(artefak["simulation"]["markets"]))
        self.assertAlmostEqual(cdf[237.5], 0.773125)
        self.assertAlmostEqual(cdf[241.5], 0.835625)
        # Acuan analisis wajar memakai median EFEKTIF.
        self.assertAlmostEqual(wajar["acuan_sim"], 222.25)
        self.assertIsNone(na.validate_nba_analysis(artefak))

    def test_sebab_cedera_bintang_memblokir_penyusutan(self):
        # Fixture standar: "Bintang Dua" OUT terkonfirmasi (2 sumber)
        # + BPM 2,0 >= ambang bintang 2,0 -> sebab cedera ada ->
        # median dipertahankan walau gap 6,5 > 5,0.
        sim = tna._sim_stub({"total_under_237.5": 0.83})
        self._patch_semua(tna._inputs(), tna._event_gamma(), sim)
        artefak = na.build_nba_analysis(
            tna.HOME,
            tna.AWAY,
            TANGGAL,
            cfg=_cfg_tes(),
            seed=7,
            iterations=None,
            slate_match=tna._SLATE_MATCH,
            start_time=START_TIME,
        )
        wajar = artefak["analisis_wajar"]
        self.assertFalse(wajar["vegas_diterapkan"])
        self.assertEqual(wajar["median_disesuaikan"], 219.0)
        self.assertEqual(wajar["geser_vegas"], 0.0)
        self.assertTrue(wajar["vegas_sebab_cedera_baru"]["ada"])
        self.assertIn("Bintang Dua", wajar["vegas_sebab_cedera_baru"]["pemain"])
        self.assertEqual(wajar["acuan_sim"], 219.0)
        # Tidak diterapkan -> markets tetap mentah, tanpa kunci _mentah;
        # blok root vegas mencatat keputusan tidak-menyusut.
        sim = artefak["simulation"]
        self.assertNotIn("markets_mentah", sim)
        self.assertNotIn("total_mentah", sim["score_distribution"])
        self.assertEqual(sim["markets"]["total_under_237.5"], 0.83)
        self.assertFalse(artefak["vegas"]["diterapkan"])
        self.assertEqual(artefak["vegas"]["median_mentah"], 219.0)

    def test_gap_kecil_tidak_disusutkan(self):
        # Median 224,0 vs pasar 225,5: gap 1,5 <= 5,0 -> dipertahankan.
        sim = tna._sim_stub(
            {"total_under_237.5": 0.83}, median=224.0, p74=236.0, p75=237.0
        )
        self._patch_semua(self._inputs_tanpa_bintang_out(), tna._event_gamma(), sim)
        artefak = na.build_nba_analysis(
            tna.HOME,
            tna.AWAY,
            TANGGAL,
            cfg=_cfg_tes(),
            seed=7,
            iterations=None,
            slate_match=tna._SLATE_MATCH,
            start_time=START_TIME,
        )
        wajar = artefak["analisis_wajar"]
        self.assertFalse(wajar["vegas_diterapkan"])
        self.assertEqual(wajar["median_disesuaikan"], 224.0)
        # Tidak diterapkan -> markets tetap mentah, tanpa kunci _mentah.
        sim = artefak["simulation"]
        self.assertNotIn("markets_mentah", sim)
        self.assertNotIn("total_mentah", sim["score_distribution"])
        self.assertFalse(artefak["vegas"]["diterapkan"])


class TestSebabCederaBaru(unittest.TestCase):
    """Definisi wiring _sebab_cedera_baru (unit)."""

    # v18.1 (Patch #4): CFG minimal kini memuat ambang GP; pemain
    # fixture membawa games_played >= 3 agar lolos filter kesegaran
    # (tanpa GP, pemain TIDAK segar -> bukan sebab).
    CFG = {
        "vonis": {"tunggu_lineup": {"bpm_bintang": 2.0}},
        "calibration": {"fresh_injury_min_gp_season": 3},
    }

    def _artefak(self, cedera, pemain):
        return {
            "inputs": {
                "home": {"players": pemain},
                "away": {"players": []},
            },
            "injuries": {"entries": cedera},
        }

    def _out(self, nama, n_sumber=2):
        return {
            "player": nama,
            "status": "OUT",
            "sources": ["A", "B"][:n_sumber],
            "availability_n_sources": n_sumber,
        }

    def test_bintang_out_terkonfirmasi_true(self):
        artefak = self._artefak(
            [self._out("Bintang", 2)],
            [{"player": "Bintang", "bpm": 4.5, "games_played": 12}],
        )
        ada, nama, dievaluasi, _ = na._sebab_cedera_baru(artefak, self.CFG)
        self.assertTrue(ada)
        self.assertEqual(nama, ["Bintang"])
        self.assertTrue(dievaluasi)

    def test_out_satu_sumber_bukan_sebab(self):
        artefak = self._artefak(
            [self._out("Bintang", 1)],
            [{"player": "Bintang", "bpm": 4.5, "games_played": 12}],
        )
        ada, _, _, _ = na._sebab_cedera_baru(artefak, self.CFG)
        self.assertFalse(ada)

    def test_out_bukan_bintang_bukan_sebab(self):
        artefak = self._artefak(
            [self._out("Bangku", 2)],
            [{"player": "Bangku", "bpm": 0.5, "games_played": 12}],
        )
        ada, _, _, _ = na._sebab_cedera_baru(artefak, self.CFG)
        self.assertFalse(ada)

    def test_questionable_bukan_sebab(self):
        artefak = self._artefak(
            [
                {
                    "player": "Bintang",
                    "status": "QUESTIONABLE",
                    "sources": ["A", "B"],
                    "availability_n_sources": 2,
                }
            ],
            [{"player": "Bintang", "bpm": 4.5, "games_played": 12}],
        )
        ada, _, _, _ = na._sebab_cedera_baru(artefak, self.CFG)
        self.assertFalse(ada)

    def test_tanpa_data_pemain_tidak_dievaluasi(self):
        ada, nama, dievaluasi, dikecualikan = na._sebab_cedera_baru(
            {"inputs": {}, "injuries": {"entries": []}}, self.CFG
        )
        self.assertFalse(ada)
        self.assertEqual(nama, [])
        self.assertFalse(dievaluasi)
        self.assertEqual(dikecualikan, [])


class TestGeserDistribusi(unittest.TestCase):
    """Geser kaku CDF (unit, hitung tangan)."""

    def test_geser_naik_menurunkan_p_under(self):
        # CDF: 220 -> 0,50; 230 -> 0,70. Geser +4: P(U230) =
        # CDF(226) = 0,50 + 0,20x(6/10) = 0,62. Kuantil +4; std tetap.
        markets = {
            "moneyline_home": 0.6,
            "total_under_220": 0.50,
            "total_under_230": 0.70,
        }
        dist = {"mean": 220.0, "std": 10.0, "median": 220.0, "p75": 230.0}
        markets_baru, dist_baru = na._geser_distribusi(markets, dist, 4.0)
        self.assertAlmostEqual(markets_baru["total_under_230"], 0.62)
        self.assertAlmostEqual(markets_baru["total_under_220"], 0.50)
        self.assertEqual(markets_baru["moneyline_home"], 0.6)
        self.assertEqual(dist_baru["median"], 224.0)
        self.assertEqual(dist_baru["mean"], 224.0)
        self.assertEqual(dist_baru["p75"], 234.0)
        self.assertEqual(dist_baru["std"], 10.0)
        # Dict mentah tidak diubah.
        self.assertEqual(markets["total_under_230"], 0.70)
        self.assertEqual(dist["median"], 220.0)

    def test_geser_nol_tidak_berubah(self):
        markets = {"total_under_220": 0.50}
        dist = {"median": 220.0, "std": 10.0}
        markets_baru, dist_baru = na._geser_distribusi(markets, dist, 0.0)
        self.assertEqual(markets_baru, markets)
        self.assertEqual(dist_baru, dist)


if __name__ == "__main__":
    unittest.main()
