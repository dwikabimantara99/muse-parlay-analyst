"""Tes titik equilibrium per kaki (engine/equilibrium.py).

Definisi yang diuji — MODE PER TIKET (keputusan user 12:20 +
12:33 WIB 2026-11-23; config equilibrium.mode_insurance /
mode_main, worker B):
- Asuransi (safety_first): di antara garis tangga yang lolos SEMUA
  gate tiket itu, equilibrium = garis dengan p_final TERTINGGI
  (paling aman). Seri p_final (< 1e-9) -> ER lebih besar -> garis
  lebih kecil.
- Utama (max_er): equilibrium = garis dengan expected return
  tertinggi ER = p_final x (100 / harga venue). Seri ER (< 1e-9)
  -> p_final lebih besar -> garis lebih kecil.
Tidak ada lantai ER > 1: equilibrium adalah yang terbaik yang
tersedia; viabilitas tiket dinilai di level tiket oleh komposer.
Kendala pengali Asuransi (x2) ditegakkan komposer (_pilih_subset),
bukan di sini.

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


def _analisis_edge_mengikat(match_id="DET@ATL_2026-11-22"):
    """Fixture edge-mengikat: garis tahan banjir tidak thin ada, tapi
    edge < 3,5% di semua garis (harga 90–98¢ vs p_final 0,93–1,00).

    KALIBRASI ULANG (koreksi banjir 2026-11-23, worker B): dengan
    geser bersih, garis tahan banjir pertama turun ke 240,5 —
    tangga lama (240,5 @82¢) kini lolos edge (+10,5%), jadi harga
    dinaikkan agar fixture tetap menguji gate edge (bukan banjir
    atau volume).
    """
    tangga = _tangga(
        [
            (240.5, 90.0, 500.0, False),
            (242.5, 94.0, 500.0, False),
            (244.5, 96.0, 500.0, False),
            (246.5, 97.0, 500.0, False),
            (248.5, 98.0, 500.0, False),
        ]
    )
    return _analisis_224(match_id, tangga=tangga)


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
        # Utama tetap max-ER (keputusan user 12:33 WIB): di
        # fixture-224, 6 garis lolos gate Utama; ER tertinggi di
        # 238,5 @80,5¢ (1,2008) — lihat juga
        # test_bukan_garis_termurah_yang_lolos. Tes Asuransi
        # safety-first ada di TestSafetyFirst.
        hasil = equilibrium.cari_equilibrium(_analisis_224(), "main", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 238.5)
        self.assertEqual(hasil["harga_venue_cents"], 80.5)
        self.assertEqual(hasil["p_final"], 0.966624)
        self.assertAlmostEqual(hasil["expected_return"], 1.2008, places=3)
        self.assertEqual(hasil["mode"], "max_er")
        # ER equilibrium > ER garis lolos lain (240,5).
        ktx = equilibrium.siapkan_konteks(_analisis_224(), "main", CFG)
        _, _, p_final_240 = equilibrium.peluang_pada_garis(ktx, 240.5)
        self.assertGreater(hasil["expected_return"], p_final_240 * (100.0 / 82.5))

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


class TestSafetyFirst(unittest.TestCase):
    """Mode safety-first Asuransi (keputusan user 12:20 + 12:33 WIB).

    Asuransi memilih garis dengan p_final TERTINGGI di antara garis
    yang lolos semua gate — bukan ER tertinggi. Utama tetap max-ER.
    """

    def test_asuransi_pilih_p_final_tertinggi_bukan_er(self):
        # Fixture-224 Asuransi: 6 garis lolos (240,5–250,5).
        # Safety-first memilih 250,5 @92,5¢ (p_final 0,999612, ER
        # 1,0807) — garis paling aman, BUKAN max-ER (242,5 @84,5¢,
        # p_final 0,967212, ER 1,1446).
        hasil = equilibrium.cari_equilibrium(_analisis_224(), "insurance", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["mode"], "safety_first")
        self.assertEqual(hasil["garis"], 250.5)
        self.assertEqual(hasil["harga_venue_cents"], 92.5)
        self.assertEqual(hasil["p_final"], 0.999612)
        self.assertAlmostEqual(hasil["expected_return"], 1.0807, places=3)
        self.assertEqual(hasil["n_kandidat_lolos"], 6)
        # p_final equilibrium > p_final garis lolos lain (248,5).
        ktx = equilibrium.siapkan_konteks(_analisis_224(), "insurance", CFG)
        _, _, p_final_248 = equilibrium.peluang_pada_garis(ktx, 248.5)
        self.assertGreater(hasil["p_final"], p_final_248)
        # ... meski ER-nya lebih rendah dari max-ER (242,5).
        _, _, p_final_242 = equilibrium.peluang_pada_garis(ktx, 242.5)
        self.assertLess(hasil["expected_return"], p_final_242 * (100.0 / 84.5))

    def test_mode_max_er_di_config_memilih_er(self):
        # Override config mode_insurance=max_er -> perilaku lama:
        # 242,5 @84,5¢ (p_final 0,967212, ER 1,1446). Bukti mode
        # dikendalikan config, bukan hardcode per tiket.
        cfg = copy.deepcopy(CFG)
        cfg["equilibrium"]["mode_insurance"] = "max_er"
        hasil = equilibrium.cari_equilibrium(_analisis_224(), "insurance", cfg)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["mode"], "max_er")
        self.assertEqual(hasil["garis"], 242.5)
        self.assertEqual(hasil["harga_venue_cents"], 84.5)
        self.assertEqual(hasil["p_final"], 0.967212)
        self.assertAlmostEqual(hasil["expected_return"], 1.1446, places=3)

    def test_mode_utama_safety_first_memilih_p_final(self):
        # Mode juga bisa dibalik (Utama safety-first) — bukti mode
        # murni fungsi config per tiket: Utama memilih garis p_final
        # tertinggi yang lolos (250,5), bukan max-ER (238,5).
        cfg = copy.deepcopy(CFG)
        cfg["equilibrium"]["mode_main"] = "safety_first"
        hasil = equilibrium.cari_equilibrium(_analisis_224(), "main", cfg)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["mode"], "safety_first")
        self.assertEqual(hasil["garis"], 250.5)

    def test_seri_p_final_pilih_er_tertinggi(self):
        # CDF datar di atas 240 (p 0,99): dua garis p_final seri
        # persis 0,99 -> yang ER lebih besar (248,5 @90,5¢, ER
        # 1,0939) menang atas 250,5 @92,5¢ (ER 1,0703).
        hasil = equilibrium.cari_equilibrium(
            self._analisis_seri(92.0), "insurance", CFG
        )
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 248.5)
        self.assertEqual(hasil["p_final"], 0.99)
        self.assertAlmostEqual(hasil["expected_return"], 1.0939, places=3)

    def test_seri_penuh_pilih_garis_terkecil(self):
        # p_final seri + harga sama -> ER seri -> garis terkecil
        # (248,5) menang.
        hasil = equilibrium.cari_equilibrium(
            self._analisis_seri(90.0), "insurance", CFG
        )
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 248.5)
        self.assertEqual(hasil["p_final"], 0.99)

    def test_mode_tidak_dikenal_config_error(self):
        cfg = copy.deepcopy(CFG)
        cfg["equilibrium"]["mode_insurance"] = "paling_murah"
        with self.assertRaises(config.ConfigError):
            equilibrium.cari_equilibrium(_analisis_224(), "insurance", cfg)

    def test_mode_hilang_config_error(self):
        # Fail-closed: kunci mode hilang -> ConfigError, bukan
        # default diam-diam (mode yang salah diam-diam lebih buruk
        # daripada error keras).
        cfg = copy.deepcopy(CFG)
        del cfg["equilibrium"]["mode_insurance"]
        with self.assertRaises(config.ConfigError):
            equilibrium.cari_equilibrium(_analisis_224(), "insurance", cfg)

    @staticmethod
    def _analisis_seri(harga_atas):
        # CDF datar 0,99 di atas 240: p_final seri di 248,5/250,5
        # (keduanya lolos banjir: P banjir 79,3%/89,1% >= 74%).
        return {
            "format": "nba_analysis",
            "format_version": 1,
            "match_id": "SER@I_2026-11-22",
            "status": "OK",
            "legs": [
                _kaki("SER@I_2026-11-22", "insurance", 240.5, 0.9, 0.9, 80.0),
                _kaki("SER@I_2026-11-22", "main", 240.5, 0.9, 0.9, 80.0),
            ],
            "simulation": {
                "score_distribution": {"total": {"median": 230.0}},
                "markets": {
                    "total_under_230": 0.50,
                    "total_under_240": 0.99,
                    "total_under_250": 0.99,
                    "total_under_260": 0.99,
                },
            },
            "market": {
                "main_total_line": 231.5,
                "totals": _tangga(
                    [
                        (248.5, 90.0, 500.0, False),
                        (250.5, harga_atas, 500.0, False),
                    ]
                ),
            },
        }


class TestGate(unittest.TestCase):
    """Gate per tiket + diagnosis gate yang mengikat."""

    def test_asuransi_volume_mengikat_fixture_den(self):
        # PERUBAHAN REALITA (koreksi banjir 2026-11-23, worker B):
        # dengan geser bersih, fixture DEN sintetis kini PUNYA
        # equilibrium Asuransi — garis tahan banjir pertama turun
        # dari 264,5 ke 258,5, dan 258,5 @85,5¢ tidak thin (edge
        # +4,5%) sehingga menjadi satu-satunya garis yang lolos
        # semua gate. Cakupan "volume mengikat" sintetis pindah ke
        # artefak nyata DEN live/verif (TestArtefakNyata) — di sana
        # semua garis tahan banjir tetap thin. Utama tetap 254,5.
        analisis = _analisis_den()
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["mode"], "safety_first")
        self.assertEqual(hasil["garis"], 258.5)
        self.assertEqual(hasil["harga_venue_cents"], 85.5)
        self.assertEqual(hasil["p_final"], 0.900437)
        self.assertAlmostEqual(hasil["expected_return"], 1.0531, places=3)
        self.assertEqual(hasil["n_kandidat_lolos"], 1)
        self.assertFalse(hasil["thin"])
        hasil_main = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil_main["ada"])
        self.assertEqual(hasil_main["garis"], 254.5)

    def test_asuransi_edge_mengikat(self):
        # Garis tahan banjir tidak thin ada, tapi edge di bawah
        # minimum 3,5% di semua garis -> tidak ada equilibrium,
        # gate mengikat edge, token edge_kecil dipakai. Fixture
        # dikalibrasi ulang untuk geser bersih (lihat
        # _analisis_edge_mengikat).
        analisis = _analisis_edge_mengikat()
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertFalse(hasil["ada"])
        self.assertIn("edge", hasil["alasan_tidak_ada"])
        self.assertIn("edge_kecil", hasil["alasan_tidak_ada"])

    def test_asuransi_banjir_mengikat_tanpa_garis_tahan(self):
        # Tangga berhenti di bawah garis tahan banjir -> token
        # tidak_ada_garis_tahan_banjir dipakai ulang (jejak audit
        # tetap nyambung dengan aturan lama). Dengan geser bersih,
        # garis tahan banjir pertama fixture-224 adalah 240,5, jadi
        # tangga dipendekkan sampai 238,5 (sebelumnya 244,5 —
        # koreksi banjir 2026-11-23, worker B).
        tangga = _tangga(
            [
                (232.5, 74.0, 500.0, False),
                (234.5, 76.0, 500.0, False),
                (236.5, 78.0, 500.0, False),
                (238.5, 80.0, 500.0, False),
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
        # Garis Utama BOLEH gagal target banjir Asuransi (74%):
        # P banjir 238,5 adalah 65,4% — di bawah 74% (dengan geser
        # bersih; sebelum koreksi nilainya 27,6%, di bawah 65%).
        # Intinya tetap: Utama tidak di-gate banjir.
        self.assertLess(hasil["p_banjir_terburuk"], 0.74)

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
        # dilewati; safety-first memilih p_final tertinggi di
        # antara yang lolos (250,5 @92,5¢, p_final 0,999612, tidak
        # thin). Keputusan lama "gate tidak melompat" digantikan.
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
        self.assertEqual(hasil["garis"], 250.5)
        self.assertFalse(hasil["thin"])
        self.assertEqual(hasil["p_final"], 0.999612)


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
        self.assertEqual(kaki_baru["line"], 250.5)
        self.assertEqual(kaki_baru["price_cents"], 92.0)
        self.assertEqual(kaki_baru["jup_estimated_cents"], 92.5)
        self.assertEqual(kaki_baru["p_final"], 0.999612)
        self.assertEqual(kaki_baru["p_model"], 1.0)
        self.assertEqual(kaki_baru["p_market"], 0.999445)
        self.assertEqual(kaki_baru["thin"], False)
        self.assertEqual(kaki_baru["volume_usd"], 500.0)
        self.assertTrue(kaki_baru["meets"])
        # Cushion dihitung ulang di garis baru; cushion artefak
        # (per-laga) dipertahankan.
        self.assertEqual(kaki_baru["cushion_vs_median_points"], 26.5)
        self.assertEqual(kaki_baru["cushion_vs_market_points"], 25.0)
        self.assertEqual(kaki_baru["cushion_points"], 8.0)
        self.assertEqual(kaki_baru["cushion_reason"], "bantalan_adaptif")
        self.assertEqual(
            kaki_baru["climb"],
            {
                "from_line": 240.5,
                "to_line": 250.5,
                "rungs": 5,
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
        # Fixture edge-mengikat (tidak ada equilibrium Asuransi)
        # -> rakit_kaki mengembalikan None. Sebelum koreksi banjir,
        # tes ini memakai fixture DEN — kini DEN sintetis PUNYA
        # equilibrium Asuransi (lihat
        # test_asuransi_volume_mengikat_fixture_den).
        analisis = _analisis_edge_mengikat()
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
                "to_line": 250.5,
                "rungs": 6,
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
        # equilibrium Asuransi; gate mengikat volume (garis tahan
        # banjir 260,5–266,5, keempatnya thin — geser bersih
        # 12,52; sebelum koreksi hanya U266,5 @94¢).
        analisis = self.live["DEN@CHI_2026-11-22"]
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertFalse(hasil["ada"])
        self.assertIn("volume", hasil["alasan_tidak_ada"])
        self.assertIn("260.5", hasil["alasan_tidak_ada"])
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
        # Garis tahan banjir pertama verif: 258,5 (geser bersih;
        # sebelum koreksi 264,5).
        self.assertIn("258.5", hasil_ins["alasan_tidak_ada"])
        hasil_main = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil_main["ada"])
        self.assertEqual(hasil_main["garis"], 250.5)
        self.assertEqual(hasil_main["harga_venue_cents"], 78.5)

    def test_okc_verif_asuransi_vs_utama_berbeda_tujuan(self):
        # KASUS WAJIB (worker B): equilibrium Asuransi vs Utama
        # BERBEDA sesuai tujuannya. OKC@MIA verif:
        # - Utama (max-er): ADA di U240,5 @75,5¢, p_final 0,788828,
        #   ER 1,0448 — titik paling manis (nilai terbaik).
        # - Asuransi (safety-first): TIDAK ADA — garis terbaik yang
        #   lolos banjir + volume (U250,5 @89,5¢, p_final 0,908)
        #   gagal edge (+1,3% < 3,5%). Safety-first TIDAK
        #   melonggarkan gate: garis paling aman pun harus lolos
        #   semua gate; bila tidak ada yang lolos, tidak ada
        #   equilibrium (bukan dipaksa ke garis termurah).
        # Catatan jujur: perbedaan MODE (safety-first vs max-er)
        # dibuktikan di fixture sintetis (TestSafetyFirst) — di
        # OKC verif, Asuransi tidak punya garis yang lolos di mode
        # mana pun, jadi tes ini membuktikan perbedaan HASIL
        # (Utama ada, Asuransi tidak ada) + alasan gate-nya.
        analisis = self.verif["OKC@MIA_2026-11-22"]
        hasil_ins = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        hasil_main = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertEqual(hasil_ins["mode"], "safety_first")
        self.assertEqual(hasil_main["mode"], "max_er")
        self.assertFalse(hasil_ins["ada"])
        self.assertIn("edge", hasil_ins["alasan_tidak_ada"])
        self.assertIn("250.5", hasil_ins["alasan_tidak_ada"])
        self.assertIn("+1.3%", hasil_ins["alasan_tidak_ada"])
        self.assertTrue(hasil_main["ada"])
        self.assertEqual(hasil_main["garis"], 240.5)
        self.assertEqual(hasil_main["harga_venue_cents"], 75.5)
        self.assertAlmostEqual(hasil_main["p_final"], 0.788828, places=5)
        self.assertAlmostEqual(hasil_main["expected_return"], 1.0448, places=3)

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
