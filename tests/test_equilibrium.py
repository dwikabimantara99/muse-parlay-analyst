"""Tes titik equilibrium per kaki (engine/equilibrium.py).

Definisi yang diuji: di antara garis tangga yang lolos SEMUA gate
tiket itu, equilibrium = garis dengan expected return tertinggi
ER = p_final x (100 / harga venue). Seri ER (< 1e-9) -> p_final
lebih besar -> garis lebih kecil. Tidak ada lantai ER > 1: max-ER
adalah yang terbaik yang tersedia; viabilitas tiket dinilai di
level tiket oleh komposer.

Tes artefak nyata memakai out/analysis_live_2026-11-22.json +
out/analysis_verif_tahap4_2026-11-22.json (file runtime, gitignored)
dan di-skip bila file tidak ada — pola yang sama seperti
tests/test_cli_belajar.py untuk out/validation_nba_rolling.json.
"""

from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path

import config
from engine import equilibrium

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
    harga_venue = harga
    p_final = None
    ev_pct = None
    if p_model is not None:
        p_final = (
            round(0.3 * p_model + 0.7 * p_market, 3)
            if p_market is not None
            else p_model
        )
        ev_pct = round((p_final * (100.0 / harga_venue) - 1.0) * 100.0, 2)
    kaki = {
        "leg_id": f"{match_id}:total_under_{line:g}:{ticket}",
        "market_type": "total_under",
        "line": line,
        "p_model": p_model,
        "p_market": p_market,
        "comparison_source": "kalshi" if p_market is not None else None,
        "p_final": p_final,
        "price_cents": harga,
        "jup_estimated_cents": harga_venue,
        "ev_pct": ev_pct,
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


def _analisis(match_id, median, sigma, kaki_ins, kaki_main, tangga, ot=None):
    """Artefak nba_analysis minimal dengan CDF normal penuh + tangga."""
    markets = _cdf_normal(median, sigma, median - 30, median + 45)
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


def _tangga_224():
    """Tangga fixture median 224 sigma 5 (garis 232,5–250,5)."""
    return _tangga(
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
    )


def _analisis_224(match_id="DET@ATL_2026-11-22", tangga=None):
    """Fixture median 224 sigma 5 (jangkar ins U240,5 p_market 0,90)."""
    return _analisis(
        match_id,
        224.0,
        5.0,
        _kaki(match_id, "insurance", 240.5, 0.99, 0.90, 82.0),
        _kaki(match_id, "main", 236.5, 0.99, 0.90, 78.0),
        tangga if tangga is not None else _tangga_224(),
    )


def _tangga_den():
    """Tangga DEN@CHI sintetis (238,5–274,5; >= 264,5 thin).

    Harga naik dengan garis; 252,5 @82¢, 264,5 @94¢ (mirip artefak
    nyata). Sama bentuknya dengan fixture gate banjir komposer.
    """
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
    return _tangga(baris)


def _analisis_den(match_id="DET@ATL_2026-11-22"):
    """Fixture DEN sintetis: median 233, sigma 19,2, tangga DEN."""
    return _analisis(
        match_id,
        233.0,
        19.2,
        _kaki(match_id, "insurance", 252.5, 0.845, 0.83, 82.0),
        _kaki(match_id, "main", 250.5, 0.819, 0.80, 79.0),
        _tangga_den(),
    )


def _muat_artefak(path):
    """Analisis per laga dari satu file artefak (dict match_id -> dict).

    Kunci = match_id nba_analysis (mis. OKC@MIA_2026-11-22), BUKAN
    slug match ("nba-2026-11-22-okc-mia").
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    hasil = {}
    for match in data.get("matches") or []:
        analysis = match.get("nba_analysis") or {}
        if analysis.get("match_id"):
            hasil[analysis["match_id"]] = analysis
    return hasil


class TestMaxER(unittest.TestCase):
    """Definisi equilibrium: expected return tertinggi, bukan termurah."""

    def test_memilih_expected_return_tertinggi(self):
        # Asuransi: 3 garis lolos semua gate (246,5/248,5/250,5);
        # ER tertinggi di 246,5 (1,1246) — garis termurah di antara
        # yang lolos SEKALIGUS max-ER di fixture ini.
        hasil = equilibrium.cari_equilibrium(_analisis_224(), "insurance", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 246.5)
        self.assertEqual(hasil["harga_venue_cents"], 88.5)
        self.assertEqual(hasil["p_final"], 0.995248)
        self.assertAlmostEqual(hasil["expected_return"], 1.1246, places=3)
        self.assertEqual(hasil["n_kandidat_lolos"], 3)
        # ER equilibrium > ER garis lolos lain (248,5).
        ktx = equilibrium.siapkan_konteks(_analisis_224(), "insurance", CFG)
        _, _, p_final_248 = equilibrium.peluang_pada_garis(ktx, 248.5)
        self.assertGreater(hasil["expected_return"], p_final_248 * (100.0 / 90.5))

    def test_bukan_garis_termurah_yang_lolos(self):
        # Utama: garis termurah yang lolos lantai + peluang adalah
        # 234,5 @76,5¢ (ER 0,88) — equilibrium memilih 238,5 @80,5¢
        # (ER 1,20): sedikit lebih mahal, jauh lebih mungkin menang.
        hasil = equilibrium.cari_equilibrium(_analisis_224(), "main", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 238.5)
        self.assertEqual(hasil["harga_venue_cents"], 80.5)
        self.assertAlmostEqual(hasil["expected_return"], 1.2008, places=3)
        ktx = equilibrium.siapkan_konteks(_analisis_224(), "main", CFG)
        _, _, p_final_234 = equilibrium.peluang_pada_garis(ktx, 234.5)
        self.assertGreaterEqual(p_final_234, 0.65)
        self.assertGreater(hasil["expected_return"], p_final_234 * (100.0 / 76.5))

    def test_seri_er_pilih_p_final_tertinggi(self):
        # Dua garis ER sama persis 1,0 (p 0,8 @80¢ vs p 0,9 @90¢)
        # -> yang p_final lebih besar (242,5) menang.
        analisis = {
            "format": "nba_analysis",
            "format_version": 1,
            "match_id": "SER@I_2026-11-22",
            "status": "OK",
            "legs": [
                _kaki("SER@I_2026-11-22", "insurance", 240.5, 0.8, 0.8, 80.0),
                _kaki("SER@I_2026-11-22", "main", 242.5, 0.9, 0.9, 90.0),
            ],
            "simulation": {
                "score_distribution": {"total": {"median": 230.0}},
                "markets": {
                    "total_under_240.5": 0.8,
                    "total_under_242.5": 0.9,
                },
            },
            "market": {
                "main_total_line": 231.5,
                "totals": [
                    {
                        "line": 240.5,
                        "side": "under",
                        "price_cents": 80.0,
                        "jup_estimated_cents": 80.0,
                        "volume_usd": 500.0,
                        "thin": False,
                    },
                    {
                        "line": 242.5,
                        "side": "under",
                        "price_cents": 90.0,
                        "jup_estimated_cents": 90.0,
                        "volume_usd": 500.0,
                        "thin": False,
                    },
                ],
            },
        }
        hasil = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 242.5)
        self.assertAlmostEqual(hasil["expected_return"], 1.0, places=9)

    def test_seri_penuh_pilih_garis_terkecil(self):
        # CDF datar (p sama) + harga sama -> ER dan p_final seri
        # persis -> garis terkecil (240,5) menang.
        analisis = {
            "format": "nba_analysis",
            "format_version": 1,
            "match_id": "DAT@AR_2026-11-22",
            "status": "OK",
            "legs": [
                _kaki("DAT@AR_2026-11-22", "insurance", 240.5, 0.85, 0.85, 85.0),
                _kaki("DAT@AR_2026-11-22", "main", 240.5, 0.85, 0.85, 85.0),
            ],
            "simulation": {
                "score_distribution": {"total": {"median": 230.0}},
                "markets": {
                    "total_under_240.5": 0.85,
                    "total_under_242.5": 0.85,
                },
            },
            "market": {
                "main_total_line": 231.5,
                "totals": [
                    {
                        "line": 240.5,
                        "side": "under",
                        "price_cents": 85.0,
                        "jup_estimated_cents": 85.0,
                        "volume_usd": 500.0,
                        "thin": False,
                    },
                    {
                        "line": 242.5,
                        "side": "under",
                        "price_cents": 85.0,
                        "jup_estimated_cents": 85.0,
                        "volume_usd": 500.0,
                        "thin": False,
                    },
                ],
            },
        }
        hasil = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 240.5)

    def test_tidak_ada_lantai_expected_return(self):
        # Semua garis ER < 1 (CDF datar 0,7; harga 75–85¢) ->
        # equilibrium TETAP ada di ER tertinggi (0,9333, garis
        # termurah). Keputusan desain: tidak ada lantai ER > 1;
        # max-ER adalah yang terbaik yang tersedia dan dilaporkan
        # transparan; viabilitas dinilai di level tiket.
        analisis = {
            "format": "nba_analysis",
            "format_version": 1,
            "match_id": "MIN@US_2026-11-22",
            "status": "OK",
            "legs": [
                _kaki("MIN@US_2026-11-22", "insurance", 240.5, 0.7, 0.7, 80.0),
                _kaki("MIN@US_2026-11-22", "main", 240.5, 0.7, 0.7, 80.0),
            ],
            "simulation": {
                "score_distribution": {"total": {"median": 230.0}},
                "markets": {
                    "total_under_238.5": 0.7,
                    "total_under_240.5": 0.7,
                    "total_under_242.5": 0.7,
                },
            },
            "market": {
                "main_total_line": 231.5,
                "totals": [
                    {
                        "line": 238.5,
                        "side": "under",
                        "price_cents": 75.0,
                        "jup_estimated_cents": 75.0,
                        "volume_usd": 500.0,
                        "thin": False,
                    },
                    {
                        "line": 240.5,
                        "side": "under",
                        "price_cents": 80.0,
                        "jup_estimated_cents": 80.0,
                        "volume_usd": 500.0,
                        "thin": False,
                    },
                    {
                        "line": 242.5,
                        "side": "under",
                        "price_cents": 85.0,
                        "jup_estimated_cents": 85.0,
                        "volume_usd": 500.0,
                        "thin": False,
                    },
                ],
            },
        }
        hasil = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 238.5)
        self.assertLess(hasil["expected_return"], 1.0)
        self.assertAlmostEqual(hasil["expected_return"], 0.9333, places=3)


class TestGate(unittest.TestCase):
    """Gate per tiket + diagnosis gate yang mengikat."""

    def test_asuransi_volume_mengikat_fixture_den(self):
        # Fixture DEN: satu-satunya garis tahan banjir (264,5)
        # thin -> tidak ada equilibrium Asuransi, gate mengikat
        # volume; Utama tetap punya equilibrium (254,5).
        analisis = _analisis_den()
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertFalse(hasil["ada"])
        self.assertIn("volume", hasil["alasan_tidak_ada"])
        self.assertIn("264.5", hasil["alasan_tidak_ada"])
        self.assertIn("volume tipis", hasil["alasan_tidak_ada"])
        hasil_main = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil_main["ada"])
        self.assertEqual(hasil_main["garis"], 254.5)

    def test_asuransi_edge_mengikat(self):
        # Garis tahan banjir tidak thin ada, tapi edge di bawah
        # minimum 3,5% di semua garis -> tidak ada equilibrium,
        # gate mengikat edge, token edge_kecil dipakai.
        tangga = _tangga(
            [
                (240.5, 82.0, 500.0, False),
                (242.5, 84.0, 500.0, False),
                (244.5, 86.0, 500.0, False),
                (246.5, 96.0, 500.0, False),
                (248.5, 98.0, 500.0, False),
            ]
        )
        analisis = _analisis_224(tangga=tangga)
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertFalse(hasil["ada"])
        self.assertIn("edge", hasil["alasan_tidak_ada"])
        self.assertIn("edge_kecil", hasil["alasan_tidak_ada"])

    def test_asuransi_banjir_mengikat_tanpa_garis_tahan(self):
        # Tangga berhenti di bawah garis tahan banjir -> token
        # tidak_ada_garis_tahan_banjir dipakai ulang (jejak audit
        # tetap nyambung dengan aturan lama).
        tangga = _tangga(
            [
                (232.5, 74.0, 500.0, False),
                (234.5, 76.0, 500.0, False),
                (236.5, 78.0, 500.0, False),
                (238.5, 80.0, 500.0, False),
                (240.5, 82.0, 500.0, False),
                (242.5, 84.0, 500.0, False),
                (244.5, 86.0, 500.0, False),
            ]
        )
        analisis = _analisis_224(tangga=tangga)
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertFalse(hasil["ada"])
        self.assertIn("banjir", hasil["alasan_tidak_ada"])
        self.assertIn("tidak_ada_garis_tahan_banjir", hasil["alasan_tidak_ada"])

    def test_diagnosis_urutan_peluang_dulu(self):
        # Satu-satunya garis gagal peluang (p_final 55,4% < 74%)
        # sekaligus gagal banjir -> yang dinamai adalah peluang
        # (pertama dalam urutan diagnosis).
        tangga = _tangga([(232.5, 76.0, 500.0, False)])
        analisis = _analisis_224(tangga=tangga)
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertFalse(hasil["ada"])
        self.assertIn("peluang", hasil["alasan_tidak_ada"])
        self.assertIn("55.4%", hasil["alasan_tidak_ada"])

    def test_utama_tanpa_gate_banjir_edge_volume(self):
        # Utama: garis equilibrium boleh thin dan boleh gagal banjir
        # (aturan lama dipertahankan — gate banjir/edge/volume hanya
        # untuk Asuransi). Di sini 238,5 ditandai thin dan tetap
        # dipilih sebagai equilibrium Utama.
        tangga = _tangga_224()
        for entri in tangga:
            if entri["line"] == 238.5:
                entri["thin"] = True
                entri["volume_usd"] = 5.0
        analisis = _analisis_224(tangga=tangga)
        hasil = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 238.5)
        self.assertTrue(hasil["thin"])
        self.assertLess(hasil["p_banjir_terburuk"], 0.65)

    def test_label_mahal_tersubsumsi_gate_edge(self):
        # Untuk Asuransi, gate label MAHAL saat ini tidak pernah
        # mengikat: edge >= 3,5% selalu berimplikasi EV > 0 (p_final
        # > harga -> EV = p_final*100/harga - 1 > 0), jadi garis yang
        # lolos edge tidak mungkin MAHAL. Gate label dipertahankan
        # sebagai pertahanan berlapis bila min_edge_pct suatu saat
        # diturunkan. Tes ini mendokumentasikan subsumsi itu.
        for p_final, harga in ((0.80, 76.0), (0.95, 90.0), (0.995, 88.5)):
            edge = p_final - harga / 100.0
            ev_pct = (p_final * (100.0 / harga) - 1.0) * 100.0
            if edge >= 0.035:
                self.assertGreater(ev_pct, 0.0)
        hasil = equilibrium.cari_equilibrium(_analisis_224(), "insurance", CFG)
        self.assertEqual(hasil["price_label"], "DISKON")

    def test_asuransi_boleh_melompati_garis_tahan_thin(self):
        # Equilibrium menilai SEMUA garis: garis tahan 246,5 thin
        # dilewati, 248,5 tebal dipilih (248,5 @90,5¢, edge +9,4%).
        # Keputusan lama "gate tidak melompat" digantikan.
        tangga = _tangga(
            [
                (232.5, 74.0, 500.0, False),
                (234.5, 76.0, 500.0, False),
                (236.5, 78.0, 500.0, False),
                (238.5, 80.0, 500.0, False),
                (240.5, 82.0, 500.0, False),
                (242.5, 84.0, 500.0, False),
                (244.5, 86.0, 500.0, False),
                (246.5, 88.0, 12.0, True),
                (248.5, 90.0, 500.0, False),
                (250.5, 92.0, 500.0, False),
            ]
        )
        analisis = _analisis_224(tangga=tangga)
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 248.5)
        self.assertFalse(hasil["thin"])
        self.assertEqual(hasil["p_final"], 0.998538)


class TestJangkarPasar(unittest.TestCase):
    """Geser pasar tersirat (implied shift) dari kaki jangkar."""

    def test_geser_mereproduksi_p_market_jangkar(self):
        # Di garis jangkar, p_market hasil geser = p_market kaki
        # artefak persis (konstruksi delta menjamin itu); p_final
        # = blend w=0,3 dari p_model CDF dan p_market itu.
        analisis = _analisis_224()
        ktx = equilibrium.siapkan_konteks(analisis, "insurance", CFG)
        self.assertTrue(ktx["ok"])
        self.assertEqual(ktx["anchor"]["line"], 240.5)
        self.assertAlmostEqual(ktx["delta"], 10.0, places=3)
        p_model, p_market, p_final = equilibrium.peluang_pada_garis(ktx, 240.5)
        self.assertAlmostEqual(p_market, 0.90, places=9)
        self.assertAlmostEqual(p_final, 0.3 * p_model + 0.7 * 0.90, places=9)
        # p_model di garis jangkar berasal dari CDF (0,999445),
        # bukan dari p_model kaki artefak (0,99 fixture).
        self.assertAlmostEqual(p_model, 0.999445, places=6)

    def test_jangkar_tiket_lain_bila_tiket_sama_tanpa_p_market(self):
        # Kaki Asuransi tanpa p_market -> jangkar diambil dari kaki
        # Utama (geser pasar adalah sifat laga); equilibrium tetap
        # dihitung.
        analisis = _analisis_224()
        analisis["legs"][0]["p_market"] = None
        analisis["legs"][0]["comparison_source"] = None
        ktx = equilibrium.siapkan_konteks(analisis, "insurance", CFG)
        self.assertTrue(ktx["ok"])
        self.assertEqual(ktx["anchor"]["ticket"], "main")
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil["dihitung"])

    def test_tanpa_jangkar_tidak_dihitung(self):
        # Kedua kaki tanpa p_market -> tidak ada jangkar ->
        # dihitung False dengan alasan (bukan crash, bukan tebak).
        analisis = _analisis_224()
        for leg in analisis["legs"]:
            leg["p_market"] = None
            leg["comparison_source"] = None
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertFalse(hasil["dihitung"])
        self.assertIn("jangkar", hasil["alasan_tidak_dihitung"])


class TestTidakDihitung(unittest.TestCase):
    """Data tidak lengkap -> dihitung False (fallback komposer)."""

    def test_tanpa_markets_tidak_dihitung(self):
        analisis = _analisis_224()
        analisis["simulation"]["markets"] = {}
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertFalse(hasil["dihitung"])
        self.assertIn("CDF", hasil["alasan_tidak_dihitung"])

    def test_tanpa_tangga_tidak_dihitung(self):
        analisis = _analisis_224()
        analisis["market"]["totals"] = []
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertFalse(hasil["dihitung"])
        self.assertIn("tangga", hasil["alasan_tidak_dihitung"])

    def test_tanpa_simulation_tidak_dihitung(self):
        analisis = _analisis_224()
        del analisis["simulation"]
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertFalse(hasil["dihitung"])

    def test_tiket_tidak_dikenal_value_error(self):
        with self.assertRaises(ValueError):
            equilibrium.cari_equilibrium(_analisis_224(), "bukan_tiket", CFG)

    def test_config_banjir_hilang_config_error(self):
        cfg = copy.deepcopy(CFG)
        del cfg["stress"]["banjir_3p_points"]
        with self.assertRaises(config.ConfigError):
            equilibrium.cari_equilibrium(_analisis_224(), "insurance", cfg)


class TestRakitKaki(unittest.TestCase):
    """rakit_kaki_equilibrium: kaki artefak dibangun ulang di garis baru."""

    def test_dibangun_ulang_di_garis_baru(self):
        analisis = _analisis_224()
        kaki_lama = analisis["legs"][0]
        kaki_lama["cushion_points"] = 8.0
        kaki_lama["cushion_reason"] = "bantalan_adaptif"
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        kaki_baru = equilibrium.rakit_kaki_equilibrium(kaki_lama, hasil, analisis, CFG)
        self.assertIsNotNone(kaki_baru)
        # Identitas sama (recheck tetap cocok), isi garis baru.
        self.assertEqual(kaki_baru["leg_id"], kaki_lama["leg_id"])
        self.assertEqual(kaki_baru["line"], 246.5)
        self.assertEqual(kaki_baru["price_cents"], 88.0)
        self.assertEqual(kaki_baru["jup_estimated_cents"], 88.5)
        self.assertEqual(kaki_baru["p_final"], 0.995248)
        self.assertEqual(kaki_baru["p_model"], 0.999996)
        self.assertEqual(kaki_baru["p_market"], 0.993213)
        self.assertEqual(kaki_baru["thin"], False)
        self.assertEqual(kaki_baru["volume_usd"], 500.0)
        self.assertTrue(kaki_baru["meets"])
        # Cushion dihitung ulang di garis baru; cushion artefak
        # (per-laga) dipertahankan.
        self.assertEqual(kaki_baru["cushion_vs_median_points"], 22.5)
        self.assertEqual(kaki_baru["cushion_vs_market_points"], 21.0)
        self.assertEqual(kaki_baru["cushion_points"], 8.0)
        self.assertEqual(kaki_baru["cushion_reason"], "bantalan_adaptif")
        self.assertEqual(
            kaki_baru["climb"],
            {
                "from_line": 240.5,
                "to_line": 246.5,
                "rungs": 3,
                "reason": "equilibrium",
            },
        )
        # Kaki lama tidak berubah (tidak ada mutasi artefak).
        self.assertEqual(kaki_lama["line"], 240.5)
        self.assertEqual(kaki_lama["p_final"], 0.927)
        self.assertIsNone(kaki_lama["climb"])

    def test_garis_sama_tidak_dibangun_ulang(self):
        # Equilibrium == garis artefak -> None (kaki artefak dipakai
        # apa adanya, tanpa selisih pembulatan).
        analisis = _analisis_224()
        kaki_lama = analisis["legs"][0]
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        hasil = dict(hasil)
        hasil["garis"] = kaki_lama["line"]
        self.assertIsNone(
            equilibrium.rakit_kaki_equilibrium(kaki_lama, hasil, analisis, CFG)
        )

    def test_tidak_ada_equilibrium_tidak_dibangun_ulang(self):
        analisis = _analisis_den()
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertFalse(hasil["ada"])
        self.assertIsNone(
            equilibrium.rakit_kaki_equilibrium(
                analisis["legs"][0], hasil, analisis, CFG
            )
        )

    def test_climb_lama_dirangkai(self):
        # Kaki artefak sudah punya climb (mis. dari analisis) ->
        # climb baru merangkai: from_line dipertahankan, rungs
        # dijumlah, reason digabung dengan "+".
        analisis = _analisis_224()
        kaki_lama = analisis["legs"][0]
        kaki_lama["climb"] = {
            "from_line": 238.5,
            "to_line": 240.5,
            "rungs": 1,
            "reason": "volume_tipis",
        }
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        kaki_baru = equilibrium.rakit_kaki_equilibrium(kaki_lama, hasil, analisis, CFG)
        self.assertEqual(
            kaki_baru["climb"],
            {
                "from_line": 238.5,
                "to_line": 246.5,
                "rungs": 4,
                "reason": "volume_tipis+equilibrium",
            },
        )


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

    def test_den_live_tidak_ada_equilibrium_asuransi(self):
        # KASUS WAJIB 1 (bagian Asuransi): DEN@CHI live — tidak ada
        # equilibrium Asuransi; gate mengikat volume (satu-satunya
        # garis tahan banjir U266,5 @94¢ thin).
        analisis = self.live["DEN@CHI_2026-11-22"]
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertFalse(hasil["ada"])
        self.assertIn("volume", hasil["alasan_tidak_ada"])
        self.assertIn("266.5", hasil["alasan_tidak_ada"])
        self.assertIn("volume tipis", hasil["alasan_tidak_ada"])

    def test_den_live_ada_equilibrium_utama(self):
        # Presisi penting: DEN@CHI TIDAK punya equilibrium Asuransi,
        # tapi PUNYA equilibrium Utama (U250,5 @76,5¢, ER 1,0033).
        # Skip DEN datang dari pola-Denver (b), bukan dari (a).
        analisis = self.live["DEN@CHI_2026-11-22"]
        hasil = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 250.5)
        self.assertEqual(hasil["harga_venue_cents"], 76.5)
        self.assertAlmostEqual(hasil["p_final"], 0.767526, places=5)
        self.assertAlmostEqual(hasil["expected_return"], 1.0033, places=3)

    def test_den_verif_sama(self):
        analisis = self.verif["DEN@CHI_2026-11-22"]
        hasil_ins = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertFalse(hasil_ins["ada"])
        self.assertIn("264.5", hasil_ins["alasan_tidak_ada"])
        hasil_main = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil_main["ada"])
        self.assertEqual(hasil_main["garis"], 250.5)
        self.assertEqual(hasil_main["harga_venue_cents"], 78.5)

    def test_okc_verif_equilibrium_utama(self):
        # KASUS WAJIB 2: OKC@MIA verif — equilibrium Utama ada di
        # U240,5 @75,5¢ (p_final 0,789, ER 1,0448), LEBIH MURAH dan
        # bernilai lebih baik daripada kaki artefak U244,5 @82,5¢
        # (p_final 0,842, ER 1,0207). Equilibrium memilih nilai,
        # bukan garis termahal maupun termurah.
        analisis = self.verif["OKC@MIA_2026-11-22"]
        hasil = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 240.5)
        self.assertEqual(hasil["harga_venue_cents"], 75.5)
        self.assertAlmostEqual(hasil["p_final"], 0.788828, places=5)
        self.assertAlmostEqual(hasil["expected_return"], 1.0448, places=3)
        self.assertFalse(hasil["thin"])
        ktx = equilibrium.siapkan_konteks(analisis, "main", CFG)
        _, _, p_final_244 = equilibrium.peluang_pada_garis(ktx, 244.5)
        er_244 = p_final_244 * (100.0 / 82.5)
        self.assertAlmostEqual(er_244, 1.0207, places=3)
        self.assertGreater(hasil["expected_return"], er_244)

    def test_okc_verif_tidak_ada_equilibrium_asuransi_karena_edge(self):
        # OKC verif Asuransi: garis tahan banjir tidak thin ADA
        # (U250,5 @89,5¢) tapi edge +1,3% < minimum 3,5% -> tidak
        # ada equilibrium; gate mengikat edge.
        analisis = self.verif["OKC@MIA_2026-11-22"]
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertFalse(hasil["ada"])
        self.assertIn("edge", hasil["alasan_tidak_ada"])
        self.assertIn("edge_kecil", hasil["alasan_tidak_ada"])
        self.assertIn("250.5", hasil["alasan_tidak_ada"])
        self.assertIn("+1.3%", hasil["alasan_tidak_ada"])

    def test_jankar_mereproduksi_p_final_artefak_okc_verif(self):
        # Di garis jangkar artefak nyata, p_final hasil geser
        # mereproduksi p_final kaki artefak (0,908341) — bukti
        # asumsi geser-lokasi konsisten dengan data nyata.
        analisis = self.verif["OKC@MIA_2026-11-22"]
        ktx = equilibrium.siapkan_konteks(analisis, "insurance", CFG)
        _, _, p_final = equilibrium.peluang_pada_garis(ktx, 250.5)
        self.assertAlmostEqual(p_final, 0.908341, places=5)

    def test_sepuluh_baris_utama_selalu_ada_asuransi_tidak_pernah(self):
        # 10 baris slate nyata: equilibrium Utama ada di semua baris,
        # Asuransi tidak ada di baris mana pun (temuan banjir+edge
        # LAPORAN-ATURAN-KERAS §5 bertahan di bawah equilibrium).
        semua = list(self.live.values()) + list(self.verif.values())
        self.assertEqual(len(semua), 10)
        for analisis in semua:
            with self.subTest(match_id=analisis.get("match_id")):
                hasil_main = equilibrium.cari_equilibrium(analisis, "main", CFG)
                self.assertTrue(hasil_main["ada"], hasil_main)
                hasil_ins = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
                self.assertFalse(hasil_ins["ada"], hasil_ins)

    def test_orl_live_equilibrium_utama_ev_negatif(self):
        # ORL@WAS live: equilibrium Utama ADA tapi ER 0,9889 < 1 —
        # titik paling manis pun kalah sendiri (bukti tidak ada
        # lantai ER > 1; angka dilaporkan apa adanya).
        analisis = self.live["ORL@WAS_2026-11-22"]
        hasil = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 241.5)
        self.assertLess(hasil["expected_return"], 1.0)
        self.assertAlmostEqual(hasil["expected_return"], 0.9889, places=3)


if __name__ == "__main__":
    unittest.main()
