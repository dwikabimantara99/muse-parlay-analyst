"""Tes skip dari awal (engine/skip_awal.py).

Tiga pemicu (satu cukup untuk skip dari KEDUA tiket):
(a) tidak_ada_equilibrium — equilibrium tidak ada di kedua tiket;
(b) pola_denver — konjungsi 4 syarat (flag setan + tidak ada garis
    tidak-tipis yang tahan banjir + garis acuan thin + edge kecil);
(c) ot_tinggi — ot_probability sim >= ambang ot_seleksi.skip_ot_prob.

Tanpa data -> "tidak dievaluasi", BUKAN skip.

Tes artefak nyata memakai out/analysis_live_2026-11-22.json +
out/analysis_verif_tahap4_2026-11-22.json (file runtime, gitignored)
dan di-skip bila file tidak ada.
"""

from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path

import config
from engine import skip_awal

CFG = config.load_playstyle()
ROOT = Path(__file__).resolve().parent.parent
ARTEFAK_LIVE = ROOT / "out" / "analysis_live_2026-11-22.json"
ARTEFAK_VERIF = ROOT / "out" / "analysis_verif_tahap4_2026-11-22.json"


def _cdf_normal(median, sigma, garis_min, garis_max, langkah=2.0):
    """CDF total normal (median, sigma) sebagai sim markets."""
    markets = {}
    n = int(round((garis_max - garis_min) / langkah)) + 1
    for i in range(n):
        garis = garis_min + i * langkah
        z = (garis - median) / sigma
        p = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        markets[f"total_under_{garis:g}"] = round(p, 6)
    return markets


def _tangga(baris):
    """Tangga totals dari daftar (garis, harga, volume, thin).

    Harga jup.ag = harga Polymarket + 0,5¢ (markup tipikal).
    """
    return [
        {
            "line": garis,
            "side": "under",
            "price_cents": harga,
            "jup_estimated_cents": harga + 0.5,
            "volume_usd": volume,
            "thin": thin,
        }
        for garis, harga, volume, thin in baris
    ]


def _kaki(match_id, ticket, line, p_model, p_market, harga, **ubah):
    """Satu kaki artefak nba_analysis (bentuk _rakit_kaki)."""
    p_final = None
    if p_model is not None:
        p_final = (
            round(0.3 * p_model + 0.7 * p_market, 3)
            if p_market is not None
            else p_model
        )
    kaki = {
        "leg_id": f"{match_id}:total_under_{line:g}:{ticket}",
        "market_type": "total_under",
        "line": line,
        "p_model": p_model,
        "p_market": p_market,
        "comparison_source": "kalshi" if p_market is not None else None,
        "p_final": p_final,
        "price_cents": harga,
        "jup_estimated_cents": harga,
        "ev_pct": None,
        "price_label": None,
        "cushion_vs_median_points": 14.5,
        "cushion_vs_market_points": 8.0,
        "cushion_points": None,
        "cushion_reason": None,
        "volume_usd": None,
        "thin": None,
        "climb": None,
        "meets": True,
        "reason": None,
        "fetched_at": "2026-11-22T10:00:00+00:00",
        "ticket": ticket,
    }
    kaki.update(ubah)
    return kaki


def _analisis(
    match_id, median, sigma, kaki_ins, kaki_main, tangga, ot=None, langkah=2.0
):
    """Artefak nba_analysis minimal dengan CDF normal penuh + tangga."""
    markets = _cdf_normal(median, sigma, median - 30, median + 45, langkah)
    distribusi = {"total": {"median": median}}
    if ot is not None:
        distribusi["ot_probability"] = ot
    return {
        "format": "nba_analysis",
        "format_version": 1,
        "match_id": match_id,
        "status": "OK",
        "legs": [kaki_ins, kaki_main],
        "simulation": {
            "score_distribution": distribusi,
            "markets": markets,
        },
        "market": {"main_total_line": median + 1.5, "totals": tangga},
    }


def _analisis_pola_denver(match_id="DEN@CHI_2026-11-22", ot=0.02):
    """Fixture pola Denver: keempat syarat benar (median 233, sigma 19,2).

    Garis acuan 246,5 @72,5¢ thin (P normal 75,9%, P setan 40,6%,
    edge -1,5%); garis tahan banjir 264,5–270,5 semuanya thin.
    Equilibrium Utama ADA (U252,5) — skip hanya via pola (b),
    bukan via (a). OT 2,0% (di bawah ambang) — bukan via (c).
    """
    tangga = _tangga(
        [
            (238.5, 60.0, 500.0, False),
            (240.5, 62.0, 500.0, False),
            (242.5, 64.0, 500.0, False),
            (244.5, 66.0, 500.0, False),
            (246.5, 72.0, 20.0, True),
            (248.5, 72.0, 500.0, False),
            (250.5, 74.0, 500.0, False),
            (252.5, 76.0, 500.0, False),
            (254.5, 78.0, 500.0, False),
            (256.5, 80.0, 500.0, False),
            (258.5, 82.0, 500.0, False),
            (260.5, 84.0, 500.0, False),
            (262.5, 86.0, 500.0, False),
            (264.5, 94.0, 10.0, True),
            (266.5, 95.0, 10.0, True),
            (268.5, 96.0, 10.0, True),
            (270.5, 97.0, 10.0, True),
        ]
    )
    return _analisis(
        match_id,
        233.0,
        19.2,
        _kaki(match_id, "insurance", 248.5, 0.78, 0.725, 72.0),
        _kaki(match_id, "main", 246.5, 0.76, 0.71, 72.0),
        tangga,
        ot=ot,
    )


def _muat_artefak(path):
    """Analisis per laga dari satu file artefak (dict match_id -> dict)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    hasil = {}
    for match in data.get("matches") or []:
        analysis = match.get("nba_analysis") or {}
        if analysis.get("match_id"):
            hasil[analysis["match_id"]] = analysis
    return hasil


class TestPolaDenverKonjungsi(unittest.TestCase):
    """Pola Denver = konjungsi 4 syarat; tiap syarat perlu."""

    def test_keempat_syarat_benar_skip(self):
        hasil = skip_awal.evaluasi_skip_awal(_analisis_pola_denver(), CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertTrue(hasil["skip"])
        self.assertEqual(hasil["pemicu"], ["pola_denver"])
        self.assertIn("pola Denver", hasil["alasan"])
        pola = hasil["pola_denver"]
        self.assertTrue(pola["dievaluasi"])
        self.assertTrue(pola["cocok"])
        self.assertEqual(
            pola["syarat"],
            {
                "flag_setan": True,
                "tidak_ada_tahan_banjir_nonthin": True,
                "garis_acuan_thin": True,
                "edge_kecil": True,
            },
        )
        acuan = pola["garis_acuan"]
        self.assertEqual(acuan["garis"], 246.5)
        self.assertTrue(acuan["thin"])
        self.assertAlmostEqual(acuan["p_normal"], 0.75879, places=4)
        self.assertAlmostEqual(acuan["p_setan"], 0.406, places=2)
        self.assertLess(acuan["edge"], 0.035)
        self.assertEqual(acuan["n_tahan_banjir"], 4)
        self.assertEqual(acuan["n_tahan_banjir_nonthin"], 0)

    def test_syarat2_mati_ada_garis_tahan_tebal(self):
        # Satu garis tahan banjir dibuat tidak thin -> syarat (2)
        # mati -> pola tidak cocok -> tidak di-skip.
        analisis = _analisis_pola_denver()
        for entri in analisis["market"]["totals"]:
            if entri["line"] == 266.5:
                entri["thin"] = False
                entri["volume_usd"] = 500.0
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertFalse(
            hasil["pola_denver"]["syarat"]["tidak_ada_tahan_banjir_nonthin"]
        )
        self.assertFalse(hasil["pola_denver"]["cocok"])
        self.assertFalse(hasil["skip"])

    def test_syarat3_mati_garis_acuan_tebal(self):
        # Garis acuan dibuat tidak thin -> syarat (3) mati -> pola
        # tidak cocok -> tidak di-skip.
        analisis = _analisis_pola_denver()
        for entri in analisis["market"]["totals"]:
            if entri["line"] == 246.5:
                entri["thin"] = False
                entri["volume_usd"] = 500.0
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertFalse(hasil["pola_denver"]["syarat"]["garis_acuan_thin"])
        self.assertFalse(hasil["pola_denver"]["cocok"])
        self.assertFalse(hasil["skip"])

    def test_syarat4_mati_edge_besar(self):
        # Harga garis acuan diturunkan ke 60¢ -> edge +10,5% (>=
        # 3,5%) -> syarat (4) mati -> pola tidak cocok.
        analisis = _analisis_pola_denver()
        for entri in analisis["market"]["totals"]:
            if entri["line"] == 246.5:
                entri["price_cents"] = 60.0
                entri["jup_estimated_cents"] = 60.5
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertFalse(hasil["pola_denver"]["syarat"]["edge_kecil"])
        self.assertFalse(hasil["pola_denver"]["cocok"])
        self.assertFalse(hasil["skip"])

    def test_syarat1_flag_setan_bisa_mati_tangga_jarang(self):
        # Syarat (1) hampir selalu benar pada tangga rapat (garis
        # acuan − 18,07 poin pasti jauh di bawah target), karena
        # garis acuan adalah garis PERTAMA yang lolos target. Tes
        # ini membuktikan syarat (1) tetap beban di kode: dengan
        # tangga JARANG (hanya 230,5 dan 250,5) + CDF sangat curam
        # (sigma 0,5), P setan di acuan 250,5 mencapai 96,9% ->
        # flag mati -> pola tidak cocok, padahal syarat (2)–(4)
        # benar semua. Grid CDF 1 poin (bukan 2) dipakai di sini
        # karena interpolasi linear pada grid 2 poin mengaburkan CDF
        # securam ini (P setan jadi 73,3% < 74% — flag tetap hidup).
        match_id = "JAR@ANG_2026-11-22"
        tangga = _tangga(
            [
                (230.5, 70.0, 500.0, False),
                (250.5, 97.0, 10.0, True),
            ]
        )
        analisis = _analisis(
            match_id,
            231.5,
            0.5,
            _kaki(match_id, "insurance", 250.5, 0.99, 0.97, 97.0),
            _kaki(match_id, "main", 250.5, 0.99, 0.97, 97.0),
            tangga,
            ot=0.02,
            langkah=1.0,
        )
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        syarat = hasil["pola_denver"]["syarat"]
        self.assertFalse(syarat["flag_setan"])
        self.assertTrue(syarat["tidak_ada_tahan_banjir_nonthin"])
        self.assertTrue(syarat["garis_acuan_thin"])
        self.assertTrue(syarat["edge_kecil"])
        self.assertFalse(hasil["pola_denver"]["cocok"])
        self.assertFalse(hasil["skip"])

    def test_syarat1_kontrol_cdf_normal_flag_hidup(self):
        # Kontrol tes di atas: tangga jarang yang sama dengan CDF
        # normal (sigma 19,2) -> flag hidup -> pola cocok -> skip.
        match_id = "JAR@ANG_2026-11-22"
        tangga = _tangga(
            [
                (230.5, 70.0, 500.0, False),
                (250.5, 97.0, 10.0, True),
            ]
        )
        analisis = _analisis(
            match_id,
            233.0,
            19.2,
            _kaki(match_id, "insurance", 250.5, 0.82, 0.82, 97.0),
            _kaki(match_id, "main", 250.5, 0.82, 0.82, 97.0),
            tangga,
            ot=0.02,
        )
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertTrue(hasil["pola_denver"]["syarat"]["flag_setan"])
        self.assertTrue(hasil["pola_denver"]["cocok"])
        self.assertTrue(hasil["skip"])
        self.assertEqual(hasil["pemicu"], ["pola_denver"])


class TestOT(unittest.TestCase):
    """Pemicu (c): potensi OT tinggi -> skip (bukan bantalan)."""

    def test_ambang_batas(self):
        # Ambang 0,028 (>=, inklusif): 0,0280 kena, 0,0279 tidak.
        analisis = _analisis_pola_denver(ot=0.028)
        tinggi, ot, ambang = skip_awal.potensi_ot_tinggi(analisis, CFG)
        self.assertTrue(tinggi)
        self.assertEqual(ot, 0.028)
        self.assertEqual(ambang, 0.028)
        analisis = _analisis_pola_denver(ot=0.0279)
        tinggi, _, _ = skip_awal.potensi_ot_tinggi(analisis, CFG)
        self.assertFalse(tinggi)

    def test_ot_tinggi_skip_dengan_alasan(self):
        # Laga normal (bukan pola Denver) + OT 2,89% (DET live) ->
        # skip HANYA via ot_tinggi.
        analisis = _analisis(
            "DET@ATL_2026-11-22",
            224.0,
            5.0,
            _kaki("DET@ATL_2026-11-22", "insurance", 240.5, 0.99, 0.90, 82.0),
            _kaki("DET@ATL_2026-11-22", "main", 236.5, 0.99, 0.90, 78.0),
            _tangga(
                [
                    (232.5, 74.0, 500.0, False),
                    (234.5, 76.0, 500.0, False),
                    (236.5, 78.0, 500.0, False),
                    (238.5, 80.0, 500.0, False),
                    (240.5, 82.0, 500.0, False),
                    (242.5, 84.0, 500.0, False),
                    (244.5, 86.0, 500.0, False),
                    (246.5, 88.0, 500.0, False),
                    (248.5, 90.0, 500.0, False),
                    (250.5, 92.0, 500.0, False),
                ]
            ),
            ot=0.0289,
        )
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertTrue(hasil["skip"])
        self.assertEqual(hasil["pemicu"], ["ot_tinggi"])
        self.assertIn("overtime", hasil["alasan"])
        self.assertIn("2.89%", hasil["alasan"])

    def test_tanpa_ot_tidak_bisa_dinilai(self):
        analisis = _analisis_pola_denver(ot=None)
        tinggi, ot, ambang = skip_awal.potensi_ot_tinggi(analisis, CFG)
        self.assertIsNone(tinggi)
        self.assertIsNone(ot)
        self.assertEqual(ambang, 0.028)

    def test_baca_ot_fallback_dan_kanonik_menang(self):
        # Fallback simulation.ot_probability dibaca bila kanonik
        # tidak ada; bila keduanya ada, yang kanonik menang.
        analisis = {"simulation": {"ot_probability": 0.03}}
        self.assertEqual(skip_awal.baca_ot_probability(analisis), 0.03)
        analisis = {
            "simulation": {
                "score_distribution": {"ot_probability": 0.02},
                "ot_probability": 0.03,
            }
        }
        self.assertEqual(skip_awal.baca_ot_probability(analisis), 0.02)
        self.assertIsNone(skip_awal.baca_ot_probability({}))
        self.assertIsNone(
            skip_awal.baca_ot_probability(
                {"simulation": {"score_distribution": {"ot_probability": 1.5}}}
            )
        )

    def test_ambang_tidak_valid_config_error(self):
        cfg = copy.deepcopy(CFG)
        cfg["ot_seleksi"]["skip_ot_prob"] = 1.5
        with self.assertRaises(config.ConfigError):
            skip_awal.potensi_ot_tinggi(_analisis_pola_denver(), cfg)
        cfg = copy.deepcopy(CFG)
        del cfg["ot_seleksi"]["skip_ot_prob"]
        with self.assertRaises(config.ConfigError):
            skip_awal.potensi_ot_tinggi(_analisis_pola_denver(), cfg)

    def test_pemicu_ganda_pola_dan_ot(self):
        # Fixture pola Denver + OT tinggi -> kedua pemicu tercatat.
        hasil = skip_awal.evaluasi_skip_awal(_analisis_pola_denver(ot=0.03), CFG)
        self.assertTrue(hasil["skip"])
        self.assertEqual(hasil["pemicu"], ["pola_denver", "ot_tinggi"])


class TestTidakAdaEquilibrium(unittest.TestCase):
    """Pemicu (a): tidak ada equilibrium di KEDUA tiket."""

    def test_tanpa_equilibrium_kedua_tiket_skip(self):
        # Semua garis di bawah lantai 75¢ -> equilibrium tidak ada
        # di kedua tiket (Utama: lantai; Asuransi: lantai) -> skip
        # via (a). Garis acuan tidak thin -> pola tidak ikut.
        match_id = "REN@DAH_2026-11-22"
        analisis = _analisis(
            match_id,
            224.0,
            5.0,
            _kaki(match_id, "insurance", 240.5, 0.99, 0.90, 82.0),
            _kaki(match_id, "main", 236.5, 0.99, 0.90, 78.0),
            _tangga(
                [
                    (232.5, 70.0, 500.0, False),
                    (234.5, 72.0, 500.0, False),
                    (236.5, 74.0, 500.0, False),
                ]
            ),
            ot=0.02,
        )
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertTrue(hasil["skip"])
        self.assertEqual(hasil["pemicu"], ["tidak_ada_equilibrium"])
        self.assertIn("tidak ada equilibrium di kedua tiket", hasil["alasan"])
        self.assertFalse(hasil["equilibrium"]["insurance"]["ada"])
        self.assertFalse(hasil["equilibrium"]["main"]["ada"])

    def test_satu_tiket_punya_equilibrium_tidak_skip_via_a(self):
        # Fixture pola Denver punya equilibrium Utama -> (a) tidak
        # memicu (skip-nya murni via pola); fixture 224/5 punya
        # equilibrium di kedua tiket -> tidak ada pemicu sama sekali.
        hasil = skip_awal.evaluasi_skip_awal(_analisis_pola_denver(), CFG)
        self.assertNotIn("tidak_ada_equilibrium", hasil["pemicu"])
        self.assertTrue(hasil["equilibrium"]["main"]["ada"])
        match_id = "NOR@MAL_2026-11-22"
        analisis = _analisis(
            match_id,
            224.0,
            5.0,
            _kaki(match_id, "insurance", 240.5, 0.99, 0.90, 82.0),
            _kaki(match_id, "main", 236.5, 0.99, 0.90, 78.0),
            _tangga(
                [
                    (232.5, 74.0, 500.0, False),
                    (234.5, 76.0, 500.0, False),
                    (236.5, 78.0, 500.0, False),
                    (238.5, 80.0, 500.0, False),
                    (240.5, 82.0, 500.0, False),
                    (242.5, 84.0, 500.0, False),
                    (244.5, 86.0, 500.0, False),
                    (246.5, 88.0, 500.0, False),
                    (248.5, 90.0, 500.0, False),
                    (250.5, 92.0, 500.0, False),
                ]
            ),
            ot=0.02,
        )
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertFalse(hasil["skip"])
        self.assertEqual(hasil["pemicu"], [])

    def test_fixture_den_sintetis_tidak_di_skip(self):
        # KONTROL: fixture DEN sintetis komposer (CDF persis
        # normal(233, 19,2), tangga harga rendah) TIDAK memicu pola
        # — edge di garis acuan +7% (bukan kecil) dan garis acuan
        # tidak thin. Hanya artefak NYATA yang memicu pola; tes
        # kasus wajib harus memakai artefak nyata, bukan fixture
        # ini. (Juga membuktikan pola tidak memukul semua laga.)
        match_id = "DET@ATL_2026-11-22"
        baris = []
        garis = 238.5
        while garis <= 274.5 + 1e-9:
            harga = round(55.0 + (garis - 238.5) * 1.5, 1)
            baris.append((garis, harga, 500.0, garis >= 264.5))
            garis = round(garis + 2.0, 9)
        for i, (garis, _, volume, thin) in enumerate(baris):
            if abs(garis - 252.5) < 1e-9:
                baris[i] = (garis, 82.0, volume, thin)
            if abs(garis - 264.5) < 1e-9:
                baris[i] = (garis, 94.0, None, True)
        analisis = _analisis(
            match_id,
            233.0,
            19.2,
            _kaki(match_id, "insurance", 252.5, 0.845, 0.83, 82.0),
            _kaki(match_id, "main", 250.5, 0.819, 0.80, 79.0),
            _tangga(baris),
            ot=0.02,
        )
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertFalse(hasil["skip"])
        syarat = hasil["pola_denver"]["syarat"]
        self.assertFalse(syarat["garis_acuan_thin"])
        self.assertFalse(syarat["edge_kecil"])


class TestTidakDievaluasi(unittest.TestCase):
    """Tanpa data -> tidak dievaluasi, BUKAN skip."""

    def test_tanpa_data_tidak_dievaluasi(self):
        analisis = {
            "format": "nba_analysis",
            "format_version": 1,
            "match_id": "KOS@ONG_2026-11-22",
            "status": "OK",
            "legs": [],
            "simulation": {"score_distribution": {"total": {"median": 230.0}}},
            "market": {"main_total_line": 231.5, "totals": []},
        }
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertFalse(hasil["dievaluasi"])
        self.assertFalse(hasil["skip"])
        self.assertEqual(hasil["pemicu"], [])
        self.assertIsNotNone(hasil["alasan_tidak_dievaluasi"])

    def test_soccer_tidak_dievaluasi(self):
        analisis = {
            "format": "soccer_analysis",
            "format_version": 1,
            "match_id": "ARS@CHE_2026-11-22",
            "status": "OK",
        }
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertFalse(hasil["dievaluasi"])
        self.assertFalse(hasil["skip"])

    def test_ot_saja_cukup_untuk_dinilai(self):
        # Tanpa CDF/tangga tapi OT tinggi ada -> dievaluasi (via OT
        # saja) dan skip via (c). Tanpa CDF/tangga dan OT rendah ->
        # dievaluasi tapi tidak skip.
        dasar = {
            "format": "nba_analysis",
            "format_version": 1,
            "match_id": "OT@SAJA_2026-11-22",
            "status": "OK",
            "legs": [],
            "simulation": {
                "score_distribution": {
                    "total": {"median": 230.0},
                    "ot_probability": 0.03,
                },
                "markets": {},
            },
            "market": {"main_total_line": 231.5, "totals": []},
        }
        hasil = skip_awal.evaluasi_skip_awal(dasar, CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertTrue(hasil["skip"])
        self.assertEqual(hasil["pemicu"], ["ot_tinggi"])
        dasar["simulation"]["score_distribution"]["ot_probability"] = 0.02
        hasil = skip_awal.evaluasi_skip_awal(dasar, CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertFalse(hasil["skip"])


@unittest.skipUnless(
    ARTEFAK_LIVE.exists() and ARTEFAK_VERIF.exists(),
    "artefak out/analysis_live_2026-11-22.json / "
    "out/analysis_verif_tahap4_2026-11-22.json tidak ada (runtime)",
)
class TestArtefakNyata(unittest.TestCase):
    """Kasus uji wajib di artefak nyata 22 Nov (10 baris)."""

    @classmethod
    def setUpClass(cls):
        cls.live = _muat_artefak(ARTEFAK_LIVE)
        cls.verif = _muat_artefak(ARTEFAK_VERIF)

    def test_den_live_di_skip_pola_denver(self):
        # KASUS WAJIB: DEN@CHI live di-skip dengan alasan pola
        # Denver — keempat syarat benar: flag setan (P normal
        # 75,9% vs P setan 40,5%), tidak ada garis tidak-tipis yang
        # tahan banjir (satu-satunya U266,5 thin), garis acuan
        # U248,5 @72¢ thin, edge +1,5% < 3,5%.
        hasil = skip_awal.evaluasi_skip_awal(self.live["DEN@CHI_2026-11-22"], CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertTrue(hasil["skip"])
        self.assertEqual(hasil["pemicu"], ["pola_denver"])
        self.assertIn("pola Denver", hasil["alasan"])
        pola = hasil["pola_denver"]
        self.assertTrue(pola["cocok"])
        self.assertTrue(all(pola["syarat"].values()))
        acuan = pola["garis_acuan"]
        self.assertEqual(acuan["garis"], 248.5)
        self.assertTrue(acuan["thin"])
        self.assertAlmostEqual(acuan["p_normal"], 0.75889, places=4)
        self.assertAlmostEqual(acuan["p_setan"], 0.405449, places=4)
        self.assertAlmostEqual(acuan["edge"], 0.015167, places=4)
        self.assertEqual(acuan["n_tahan_banjir_nonthin"], 0)

    def test_den_verif_di_skip_pola_denver(self):
        hasil = skip_awal.evaluasi_skip_awal(self.verif["DEN@CHI_2026-11-22"], CFG)
        self.assertTrue(hasil["skip"])
        self.assertEqual(hasil["pemicu"], ["pola_denver"])
        acuan = hasil["pola_denver"]["garis_acuan"]
        self.assertEqual(acuan["garis"], 246.5)
        self.assertTrue(acuan["thin"])

    def test_den_ot_tidak_tinggi_kejujuran(self):
        # KEJUJURAN: DEN@CHI yang benar-benar masuk OT punya
        # ot_prob sim hanya 2,36% (live) / 2,13% (verif) — di bawah
        # ambang 2,8%. Aturan OT TIDAK menangkap Denver; Denver
        # ditangkap pola_denver. Aturan OT menangkap laga praktis
        # imbang lainnya (mis. DET).
        for analisis in (
            self.live["DEN@CHI_2026-11-22"],
            self.verif["DEN@CHI_2026-11-22"],
        ):
            tinggi, ot, _ = skip_awal.potensi_ot_tinggi(analisis, CFG)
            self.assertFalse(tinggi)
            self.assertLess(ot, 0.028)

    def test_okc_verif_tidak_di_skip(self):
        # KONTROL NORMAL (kasus wajib 2): OKC@MIA verif TIDAK
        # di-skip — garis tahan banjir tidak thin ADA (U250,5
        # @89,5¢) dan edge di garis acuan tidak kecil.
        hasil = skip_awal.evaluasi_skip_awal(self.verif["OKC@MIA_2026-11-22"], CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertFalse(hasil["skip"])
        self.assertEqual(hasil["pemicu"], [])
        syarat = hasil["pola_denver"]["syarat"]
        self.assertFalse(syarat["tidak_ada_tahan_banjir_nonthin"])
        self.assertFalse(syarat["edge_kecil"])

    def test_det_live_di_skip_ot_tinggi(self):
        # DET@ATL live: OT sim 2,89% >= ambang 2,8% -> skip via
        # ot_tinggi (satu-satunya pemicu OT di 10 baris).
        hasil = skip_awal.evaluasi_skip_awal(self.live["DET@ATL_2026-11-22"], CFG)
        self.assertTrue(hasil["skip"])
        self.assertEqual(hasil["pemicu"], ["ot_tinggi"])
        self.assertAlmostEqual(hasil["ot"]["ot_probability"], 0.0289, places=4)

    def test_dal_dan_bos_live_tidak_di_skip(self):
        # DAL@UTA live selamat dari pola HANYA karena edge di garis
        # acuan +4,66% >= 3,5% (margin tipis — syarat lain benar
        # semua). BOS@GSW live selamat karena edge +6,87% DAN garis
        # acuan tidak thin.
        for match_id in ("DAL@UTA_2026-11-22", "BOS@GSW_2026-11-22"):
            with self.subTest(match_id=match_id):
                hasil = skip_awal.evaluasi_skip_awal(self.live[match_id], CFG)
                self.assertFalse(hasil["skip"])
                self.assertFalse(hasil["pola_denver"]["syarat"]["edge_kecil"])

    def test_enam_dari_sepuluh_baris_di_skip(self):
        # Rekap 10 baris: 6 di-skip (5 pola Denver — DEN 2x, OKC
        # live, ORL, IND — + 1 OT — DET), 4 tidak (DAL, BOS live,
        # OKC verif, BOS verif). Tidak ada yang skip via (a) —
        # semua baris punya equilibrium Utama.
        semua = list(self.live.values()) + list(self.verif.values())
        self.assertEqual(len(semua), 10)
        di_skip = []
        for analisis in semua:
            hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
            if hasil["skip"]:
                di_skip.append(analisis["match_id"])
            self.assertNotIn("tidak_ada_equilibrium", hasil["pemicu"])
        self.assertEqual(len(di_skip), 6)
        self.assertEqual(di_skip.count("DEN@CHI_2026-11-22"), 2)
        self.assertIn("DET@ATL_2026-11-22", di_skip)
        self.assertIn("OKC@MIA_2026-11-22", di_skip)
        self.assertIn("ORL@WAS_2026-11-22", di_skip)
        self.assertIn("IND@NYK_2026-11-22", di_skip)


if __name__ == "__main__":
    unittest.main()
