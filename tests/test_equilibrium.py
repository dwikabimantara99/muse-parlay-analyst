"""Tes titik equilibrium per kaki (engine/equilibrium.py).

Definisi yang diuji — MODE PER TIKET (keputusan user 12:20 +
12:33 WIB 2026-11-23; config equilibrium.mode_insurance /
mode_main, worker B) + GATE v18 (keputusan user 13:57 WIB
2026-11-23; banjir 70/65 + EV, p_market, gate eksekusi
likuiditas + spread — revisi koordinator, bukan volume):
- Asuransi (safety_first): di antara garis tangga yang lolos SEMUA
  gate tiket itu DALAM band harga 80–89¢, equilibrium = garis
  dengan p_final TERTINGGI (paling aman). Seri p_final (< 1e-9)
  -> ER lebih besar -> garis lebih kecil. Bila tidak ada garis
  lolos dalam band, fallback ke semua garis lolos (fallback_band
  True dicatat — band adalah preferensi seleksi, bukan gate).
- Utama (max_er): di antara garis lolos dalam band 76–84¢,
  equilibrium = garis dengan expected return tertinggi
  ER = p_final x (100 / harga venue). Tie-break: selisih ER
  < 0,015 (tiebreak_er_tolerance) -> garis yang LEBIH AMAN
  (p_final lebih tinggi) menang. Seri penuh -> garis lebih kecil.
Gate v18: Asuransi = peluang (p_final >= 0,82) + p_market
(>= 0,80; MODEL_ONLY tidak dievaluasi, dicatat) + banjir 3P
(>= 0,70) + banjir FT (>= 0,65, DUA ambang terpisah) + EV
(>= -1%) + lantai harga + eksekusi (likuiditas Gamma >= $30 =
max(2 x stake, $25) + spread <= 5¢ + ask nyata); Utama =
peluang (>= 0,74) + lantai harga + EV (>= -2%) + eksekusi
(banjir warning-only). Edge datar 3,5% DIHAPUS v18 (diganti
EV); thin BUKAN lagi gate (diganti gate eksekusi). Volume
kumulatif BUKAN lagi gate (revisi koordinator — ukuran sejarah,
bukan kemampuan beli sekarang). Tidak ada lantai ER > 1:
equilibrium adalah yang terbaik yang tersedia; viabilitas tiket
dinilai di level tiket oleh komposer. Kendala pengali Asuransi
(x2) ditegakkan komposer (_pilih_subset), bukan di sini.

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
    Kuotasi default hidup (bid harga-1 / ask harga+0,5, spread
    1,5¢) + likuiditas Gamma $30.000 — garis fixture lolos gate
    eksekusi v18 kecuali tes mengubahnya eksplisit (lihat
    TestGateEksekusiLikuiditasSpread). Ask = harga+0,5 (bukan +1)
    supaya garis 98¢ tidak menyentuh sentinel ask 99¢.
    """
    return [
        {
            "line": garis,
            "side": "under",
            "price_cents": harga,
            "jup_estimated_cents": harga + 0.5,
            "volume_usd": volume,
            "thin": thin,
            "bid_cents": harga - 1.0,
            "ask_cents": harga + 0.5,
            "liquidity": 30000.0,
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


def _analisis_ev_mengikat(match_id="DET@ATL_2026-11-22"):
    """Fixture EV-mengikat (v18, MENGGANTIKAN edge-mengikat v17):
    garis lolos SEMUA gate lain (peluang, p_market, banjir 3P/FT,
    lantai, eksekusi) tapi EV < -1% di semua garis — harga 90–97¢
    terlalu mahal untuk p_final 0,86–0,92 (CDF DEN sigma 19,2).

    Fixture edge-mengikat v17 (harga 90–98¢, p_final 0,93–1,00)
    DIHAPUS: di v18 semua garisnya lolos EV (+1,4% s.d. +2,7%),
    jadi tidak lagi mengikat apa pun — itu sendiri temuan v18:
    garis yang dulu gagal edge datar kini lolos bila EV-nya
    positif.
    """
    tangga = _tangga(
        [
            (254.5, 90.0, 500.0, False),
            (256.5, 93.0, 500.0, False),
            (258.5, 95.0, 500.0, False),
            (260.5, 97.0, 500.0, False),
        ]
    )
    return _analisis(
        match_id,
        233.0,
        19.2,
        _kaki(match_id, "insurance", 252.5, 0.845, 0.83, 82.0),
        _kaki(match_id, "main", 250.5, 0.819, 0.80, 79.0),
        tangga,
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
        # Utama tetap max-ER (keputusan user 12:33 WIB) + tie-break
        # v18: di fixture-224, 9 garis lolos gate Utama; ER
        # tertinggi di 238,5 @80,5¢ (1,2008) tapi 240,5 @82,5¢
        # (ER 1,1957) hanya selisih 0,0051 < toleransi 0,015 —
        # tie-break memilih yang LEBIH AMAN (p_final 0,9865 >
        # 0,9666). Equilibrium TIDAK selalu ER maksimum mentah:
        # dalam toleransi, keamanan menang. Tes Asuransi
        # safety-first ada di TestSafetyFirst.
        hasil = equilibrium.cari_equilibrium(_analisis_224(), "main", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 240.5)
        self.assertEqual(hasil["harga_venue_cents"], 82.5)
        self.assertEqual(hasil["p_final"], 0.986455)
        self.assertAlmostEqual(hasil["expected_return"], 1.1957, places=3)
        self.assertEqual(hasil["mode"], "max_er")
        self.assertEqual(hasil["n_kandidat_lolos"], 9)
        self.assertTrue(hasil["dalam_band"])
        self.assertFalse(hasil["fallback_band"])
        # ER equilibrium < ER maksimum (238,5) tapi selisihnya
        # dalam toleransi — dan p_final-nya lebih tinggi.
        ktx = equilibrium.siapkan_konteks(_analisis_224(), "main", CFG)
        _, _, p_final_238 = equilibrium.peluang_pada_garis(ktx, 238.5)
        er_238 = p_final_238 * (100.0 / 80.5)
        self.assertAlmostEqual(er_238, 1.2008, places=3)
        self.assertLess(hasil["expected_return"], er_238)
        self.assertLess(er_238 - hasil["expected_return"], 0.015)
        self.assertGreater(hasil["p_final"], p_final_238)

    def test_bukan_garis_termurah_yang_lolos(self):
        # Utama: garis termurah yang lolos semua gate adalah 234,5
        # @76,5¢ (ER 1,1280) — equilibrium memilih 240,5 @82,5¢
        # (ER 1,1957): sedikit lebih mahal, jauh lebih mungkin
        # menang.
        hasil = equilibrium.cari_equilibrium(_analisis_224(), "main", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 240.5)
        self.assertEqual(hasil["harga_venue_cents"], 82.5)
        self.assertAlmostEqual(hasil["expected_return"], 1.1957, places=3)
        ktx = equilibrium.siapkan_konteks(_analisis_224(), "main", CFG)
        _, _, p_final_234 = equilibrium.peluang_pada_garis(ktx, 234.5)
        self.assertGreaterEqual(p_final_234, 0.74)
        self.assertGreater(hasil["expected_return"], p_final_234 * (100.0 / 76.5))

    def test_seri_er_pilih_p_final_tertinggi(self):
        # Dua garis ER sama persis 1,0 (p 0,8 @80¢ vs p 0,84 @84¢)
        # -> yang p_final lebih besar (242,5) menang (tie-break
        # toleransi 0,015). KEDUA garis harus dalam band Utama
        # 76–84¢: fixture v17 (242,5 @90¢) kini kalah di seleksi
        # band SEBELUM tie-break — band didahulukan atas ER.
        analisis = {
            "format": "nba_analysis",
            "format_version": 1,
            "match_id": "SER@I_2026-11-22",
            "status": "OK",
            "legs": [
                _kaki("SER@I_2026-11-22", "insurance", 240.5, 0.8, 0.8, 80.0),
                _kaki("SER@I_2026-11-22", "main", 242.5, 0.84, 0.84, 84.0),
            ],
            "simulation": {
                "score_distribution": {"total": {"median": 230.0}},
                "markets": {
                    "total_under_240.5": 0.8,
                    "total_under_242.5": 0.84,
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
                        "bid_cents": 79.0,
                        "ask_cents": 80.5,
                        "liquidity": 30000.0,
                    },
                    {
                        "line": 242.5,
                        "side": "under",
                        "price_cents": 84.0,
                        "jup_estimated_cents": 84.0,
                        "volume_usd": 500.0,
                        "thin": False,
                        "bid_cents": 83.0,
                        "ask_cents": 84.5,
                        "liquidity": 30000.0,
                    },
                ],
            },
        }
        hasil = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 242.5)
        self.assertAlmostEqual(hasil["expected_return"], 1.0, places=9)
        self.assertTrue(hasil["dalam_band"])

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
                        "bid_cents": 84.0,
                        "ask_cents": 85.5,
                        "liquidity": 30000.0,
                    },
                    {
                        "line": 242.5,
                        "side": "under",
                        "price_cents": 85.0,
                        "jup_estimated_cents": 85.0,
                        "volume_usd": 500.0,
                        "thin": False,
                        "bid_cents": 84.0,
                        "ask_cents": 85.5,
                        "liquidity": 30000.0,
                    },
                ],
            },
        }
        hasil = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 240.5)

    def test_tidak_ada_lantai_expected_return(self):
        # Semua garis ER < 1 (CDF datar 0,74; harga 75–85¢) ->
        # equilibrium TETAP ada di ER tertinggi (0,9867, garis
        # termurah 238,5 @75¢, EV -1,33% lolos gate EV Utama -2%).
        # Keputusan desain: tidak ada lantai ER > 1; max-ER adalah
        # yang terbaik yang tersedia dan dilaporkan transparan;
        # viabilitas dinilai di level tiket. Fixture v17 (p 0,7)
        # kini GAGAL gate EV Utama (EV -6,7% < -2%) — p dinaikkan
        # ke 0,74 (ambang peluang Utama) agar tes tetap menguji
        # tidak-adanya lantai ER, bukan gate EV.
        analisis = {
            "format": "nba_analysis",
            "format_version": 1,
            "match_id": "MIN@US_2026-11-22",
            "status": "OK",
            "legs": [
                _kaki("MIN@US_2026-11-22", "insurance", 240.5, 0.74, 0.74, 80.0),
                _kaki("MIN@US_2026-11-22", "main", 240.5, 0.74, 0.74, 80.0),
            ],
            "simulation": {
                "score_distribution": {"total": {"median": 230.0}},
                "markets": {
                    "total_under_238.5": 0.74,
                    "total_under_240.5": 0.74,
                    "total_under_242.5": 0.74,
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
                        "bid_cents": 74.0,
                        "ask_cents": 75.5,
                        "liquidity": 30000.0,
                    },
                    {
                        "line": 240.5,
                        "side": "under",
                        "price_cents": 80.0,
                        "jup_estimated_cents": 80.0,
                        "volume_usd": 500.0,
                        "thin": False,
                        "bid_cents": 79.0,
                        "ask_cents": 80.5,
                        "liquidity": 30000.0,
                    },
                    {
                        "line": 242.5,
                        "side": "under",
                        "price_cents": 85.0,
                        "jup_estimated_cents": 85.0,
                        "volume_usd": 500.0,
                        "thin": False,
                        "bid_cents": 84.0,
                        "ask_cents": 85.5,
                        "liquidity": 30000.0,
                    },
                ],
            },
        }
        hasil = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 238.5)
        self.assertLess(hasil["expected_return"], 1.0)
        self.assertAlmostEqual(hasil["expected_return"], 0.9867, places=3)
        self.assertAlmostEqual(hasil["ev_pct"], -1.33, places=1)
        # 75¢ di bawah band Utama (76–84) -> fallback band dicatat.
        self.assertTrue(hasil["fallback_band"])


class TestSafetyFirst(unittest.TestCase):
    """Mode safety-first Asuransi (keputusan user 12:20 + 12:33 WIB).

    Asuransi memilih garis dengan p_final TERTINGGI di antara garis
    yang lolos semua gate — bukan ER tertinggi. Utama tetap max-ER.
    """

    def test_asuransi_pilih_p_final_tertinggi_bukan_er(self):
        # Fixture-224 Asuransi: 7 garis lolos (238,5–250,5); dalam
        # band 80–89¢ ada 5 garis (238,5–246,5). Safety-first
        # memilih p_final TERTINGGI DALAM BAND: 246,5 @88,5¢
        # (p_final 0,995248, ER 1,1246) — BUKAN 250,5 (p_final
        # tertinggi mutlak, tapi 92,5¢ di luar band) dan BUKAN
        # max-ER (242,5 @84,5¢, p_final 0,967212, ER 1,1446).
        hasil = equilibrium.cari_equilibrium(_analisis_224(), "insurance", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["mode"], "safety_first")
        self.assertEqual(hasil["garis"], 246.5)
        self.assertEqual(hasil["harga_venue_cents"], 88.5)
        self.assertEqual(hasil["p_final"], 0.995248)
        self.assertAlmostEqual(hasil["expected_return"], 1.1246, places=3)
        self.assertEqual(hasil["n_kandidat_lolos"], 7)
        self.assertTrue(hasil["dalam_band"])
        self.assertFalse(hasil["fallback_band"])
        # p_final equilibrium > p_final garis lolos lain dalam band
        # (244,5).
        ktx = equilibrium.siapkan_konteks(_analisis_224(), "insurance", CFG)
        _, _, p_final_244 = equilibrium.peluang_pada_garis(ktx, 244.5)
        self.assertGreater(hasil["p_final"], p_final_244)
        # ... meski ER-nya lebih rendah dari max-ER (242,5).
        _, _, p_final_242 = equilibrium.peluang_pada_garis(ktx, 242.5)
        self.assertLess(hasil["expected_return"], p_final_242 * (100.0 / 84.5))

    def test_mode_max_er_di_config_memilih_er(self):
        # Override config mode_insurance=max_er -> perilaku max-ER
        # + tie-break: ER tertinggi dalam band di 242,5 @84,5¢
        # (1,1446) tapi 244,5 @86,5¢ (1,1406) selisih 0,004 <
        # toleransi 0,015 -> yang lebih aman (244,5, p_final
        # 0,986614) menang. Bukti mode dikendalikan config, bukan
        # hardcode per tiket.
        cfg = copy.deepcopy(CFG)
        cfg["equilibrium"]["mode_insurance"] = "max_er"
        hasil = equilibrium.cari_equilibrium(_analisis_224(), "insurance", cfg)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["mode"], "max_er")
        self.assertEqual(hasil["garis"], 244.5)
        self.assertEqual(hasil["harga_venue_cents"], 86.5)
        self.assertEqual(hasil["p_final"], 0.986614)
        self.assertAlmostEqual(hasil["expected_return"], 1.1406, places=3)

    def test_mode_utama_safety_first_memilih_p_final(self):
        # Mode juga bisa dibalik (Utama safety-first) — bukti mode
        # murni fungsi config per tiket: Utama memilih garis p_final
        # tertinggi DALAM BAND 76–84¢ (240,5 @82,5¢, p_final
        # 0,986455), bukan max-ER dan bukan 250,5 (di luar band).
        cfg = copy.deepcopy(CFG)
        cfg["equilibrium"]["mode_main"] = "safety_first"
        hasil = equilibrium.cari_equilibrium(_analisis_224(), "main", cfg)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["mode"], "safety_first")
        self.assertEqual(hasil["garis"], 240.5)
        self.assertTrue(hasil["dalam_band"])

    def test_seri_p_final_pilih_er_tertinggi(self):
        # CDF datar di atas 240 (p 0,99): dua garis p_final seri
        # persis 0,99 -> yang ER lebih besar (248,5 @90,5¢, ER
        # 1,0939) menang atas 250,5 @92,5¢ (ER 1,0703). Kedua garis
        # di luar band Asuransi (90,5¢/92,5¢ > 89¢) -> fallback
        # band dicatat, tapi seri tetap diputuskan oleh ER.
        hasil = equilibrium.cari_equilibrium(
            self._analisis_seri(92.0), "insurance", CFG
        )
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 248.5)
        self.assertEqual(hasil["p_final"], 0.99)
        self.assertAlmostEqual(hasil["expected_return"], 1.0939, places=3)
        self.assertTrue(hasil["fallback_band"])

    def test_seri_penuh_pilih_garis_terkecil(self):
        # p_final seri + harga sama -> ER seri -> garis terkecil
        # (248,5) menang.
        hasil = equilibrium.cari_equilibrium(
            self._analisis_seri(90.0), "insurance", CFG
        )
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 248.5)
        self.assertEqual(hasil["p_final"], 0.99)
        self.assertTrue(hasil["fallback_band"])

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
        # (keduanya lolos banjir v18: P banjir 3P 99,0% >= 70%,
        # P banjir FT 79,3% >= 65%).
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

    def test_asuransi_den_sintetis(self):
        # Fixture DEN sintetis di v18 (geser bersih 8,5/12,52 +
        # banjir dua ambang + EV): Asuransi ADA di 260,5 @88,5¢
        # (p_final 0,917446, ER 1,0367, 6 garis lolos — tertinggi
        # dalam band 80–89¢); Utama ADA di 256,5 @82,5¢ (ER
        # 1,0664). REVISI KOORDINATOR: 6 garis (bukan 5) karena
        # 264,5 (volume None) kini lolos gate eksekusi — volume
        # kumulatif bukan lagi gate. Nama lama tes ini ("volume
        # mengikat") sudah tidak benar sejak koreksi banjir:
        # cakupan "volume mengikat" ada di artefak nyata
        # (TestArtefakNyata) dan di TestGateV18.
        analisis = _analisis_den()
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["mode"], "safety_first")
        self.assertEqual(hasil["garis"], 260.5)
        self.assertEqual(hasil["harga_venue_cents"], 88.5)
        self.assertEqual(hasil["p_final"], 0.917446)
        self.assertAlmostEqual(hasil["expected_return"], 1.0367, places=3)
        self.assertEqual(hasil["n_kandidat_lolos"], 6)
        self.assertFalse(hasil["thin"])
        self.assertTrue(hasil["dalam_band"])
        hasil_main = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil_main["ada"])
        self.assertEqual(hasil_main["garis"], 256.5)
        self.assertAlmostEqual(hasil_main["expected_return"], 1.0664, places=3)

    def test_asuransi_ev_mengikat(self):
        # v18 MENGGANTIKAN test_asuransi_edge_mengikat (gate edge
        # 3,5% DIHAPUS): garis lolos semua gate lain tapi EV di
        # bawah minimum -1% di semua garis -> tidak ada
        # equilibrium, gate mengikat ev, token ev_di_bawah_minimum
        # dipakai. Garis terbaik U254,5 @90,5¢ EV -5,1%.
        analisis = _analisis_ev_mengikat()
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertFalse(hasil["ada"])
        self.assertIn("ev", hasil["alasan_tidak_ada"])
        self.assertIn("ev_di_bawah_minimum", hasil["alasan_tidak_ada"])
        self.assertIn("254.5", hasil["alasan_tidak_ada"])
        self.assertIn("-5.1%", hasil["alasan_tidak_ada"])

    def test_asuransi_banjir_mengikat_tanpa_garis_tahan(self):
        # Tangga DEN dipendekkan sampai 252,5: U252,5 lolos SEMUA
        # gate lain (peluang 83,5%, p_market 83,0%, EV +1,2%) tapi
        # gagal HANYA di banjir FT (64,2% < 65%) — token
        # tidak_ada_garis_tahan_banjir dipakai (jejak audit tetap
        # nyambung dengan aturan lama). Fixture-224 tidak bisa
        # dipakai lagi untuk tes ini: dengan geser bersih, garis
        # 238,5 sudah lolos kedua banjir (FT 65,4% — tipis di atas
        # ambang), jadi tangga pendek 224 PUNYA equilibrium.
        tangga_den = _tangga_den()
        tangga = [e for e in tangga_den if e["line"] <= 252.5]
        analisis = _analisis(
            "DET@ATL_2026-11-22",
            233.0,
            19.2,
            _kaki("DET@ATL_2026-11-22", "insurance", 252.5, 0.845, 0.83, 82.0),
            _kaki("DET@ATL_2026-11-22", "main", 250.5, 0.819, 0.80, 79.0),
            tangga,
        )
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertFalse(hasil["ada"])
        self.assertIn("banjir_ft", hasil["alasan_tidak_ada"])
        self.assertIn("tidak_ada_garis_tahan_banjir", hasil["alasan_tidak_ada"])
        self.assertIn("252.5", hasil["alasan_tidak_ada"])
        self.assertIn("64.2%", hasil["alasan_tidak_ada"])

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

    def test_utama_gate_eksekusi_tapi_bukan_banjir(self):
        # v18 MENGGANTIKAN test_utama_tanpa_gate_banjir_edge_volume:
        # Utama kini PUNYA gate eksekusi (sama seperti Asuransi)
        # tapi banjir tetap WARNING-ONLY (tidak memblokir) dan thin
        # bukan gate. REVISI KOORDINATOR: gate eksekusi =
        # likuiditas + spread, bukan volume kumulatif.
        # (a) 238,5 ditandai thin dengan volume cukup ($500) ->
        # tetap lolos gate (thin bukan gate); equilibrium Utama
        # tetap 240,5 (tie-break ER, bukan karena 238,5 dicoret).
        tangga = _tangga_224()
        for entri in tangga:
            if entri["line"] == 238.5:
                entri["thin"] = True
        analisis = _analisis_224(tangga=tangga)
        ktx = equilibrium.siapkan_konteks(analisis, "main", CFG)
        baris = {
            r["line"]: r
            for r in equilibrium.nilai_semua_garis(analisis, "main", CFG, ktx=ktx)
        }
        self.assertTrue(baris[238.5]["lolos_semua"])
        self.assertTrue(baris[238.5]["thin"])
        # (b) 238,5 likuiditasnya $5 (< $30) -> gagal gate eksekusi;
        # equilibrium pindah ke 240,5 (bukan 238,5).
        for entri in tangga:
            if entri["line"] == 238.5:
                entri["liquidity"] = 5.0
        analisis = _analisis_224(tangga=tangga)
        ktx = equilibrium.siapkan_konteks(analisis, "main", CFG)
        baris = {
            r["line"]: r
            for r in equilibrium.nilai_semua_garis(analisis, "main", CFG, ktx=ktx)
        }
        self.assertFalse(baris[238.5]["lolos_semua"])
        self.assertFalse(baris[238.5]["gate"]["eksekusi"])
        hasil = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertEqual(hasil["garis"], 240.5)
        # (b2) Volume kumulatif $5 saja TIDAK memblokir: kembalikan
        # likuiditas + spread hidup, turunkan volume ke $5 -> garis
        # tetap lolos (volume = info, bukan gate).
        for entri in tangga:
            if entri["line"] == 238.5:
                entri["liquidity"] = 30000.0
                entri["volume_usd"] = 5.0
        analisis = _analisis_224(tangga=tangga)
        ktx = equilibrium.siapkan_konteks(analisis, "main", CFG)
        baris = {
            r["line"]: r
            for r in equilibrium.nilai_semua_garis(analisis, "main", CFG, ktx=ktx)
        }
        self.assertTrue(baris[238.5]["lolos_semua"])
        self.assertTrue(baris[238.5]["gate"]["eksekusi"])
        self.assertTrue(baris[238.5]["info_volume_dibawah_100"])
        # (c) Banjir warning-only: garis 234,5 gagal standar banjir
        # Asuransi (3P 65,5% < 70%, FT 34,3% < 65%) tapi TETAP
        # lolos semua gate Utama, dengan banjir_warning True.
        self.assertTrue(baris[234.5]["lolos_semua"])
        self.assertTrue(baris[234.5]["banjir_warning"])

    def test_label_mahal_tersubsumsi_gate_ev(self):
        # v18 MENGGANTIKAN test_label_mahal_tersubsumsi_gate_edge
        # (gate edge DIHAPUS): untuk Asuransi, gate EV >= -1%
        # mensubsumsi label MAHAL — MAHAL berarti EV < -2% (label
        # harga), jadi garis yang lolos EV -1% tidak mungkin MAHAL.
        # Aritmetika murni: EV >= -1% selalu > -2%.
        for p_final, harga in ((0.80, 76.0), (0.95, 90.0), (0.995, 88.5)):
            ev_pct = (p_final * (100.0 / harga) - 1.0) * 100.0
            if ev_pct >= -1.0:
                self.assertGreater(ev_pct, -2.0)
        hasil = equilibrium.cari_equilibrium(_analisis_224(), "insurance", CFG)
        self.assertEqual(hasil["price_label"], "DISKON")
        self.assertGreaterEqual(hasil["ev_pct"], -1.0)

    def test_asuransi_boleh_melompati_garis_tahan_thin(self):
        # Equilibrium menilai SEMUA garis: garis 246,5 thin dengan
        # likuiditas $12 gagal gate eksekusi ($12 < $30) dan
        # dilewati; safety-first memilih p_final tertinggi DALAM
        # BAND di antara yang lolos (244,5 @86,5¢, p_final
        # 0,986614, tidak thin). REVISI KOORDINATOR: yang
        # memblokir kini likuiditas (bukan volume $12 — volume
        # kumulatif bukan lagi gate). Keputusan lama "gate tidak
        # melompat" digantikan.
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
        for entri in tangga:
            if entri["line"] == 246.5:
                entri["liquidity"] = 12.0
        analisis = _analisis_224(tangga=tangga)
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 244.5)
        self.assertFalse(hasil["thin"])
        self.assertEqual(hasil["p_final"], 0.986614)


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
        # Identitas sama (recheck tetap cocok), isi garis baru
        # (v18: equilibrium Asuransi fixture-224 kini 246,5 dalam
        # band, bukan 250,5).
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
        # Fixture EV-mengikat v18 (tidak ada equilibrium Asuransi)
        # -> rakit_kaki mengembalikan None. Fixture edge-mengikat
        # v17 tidak bisa dipakai lagi: di v18 semua garisnya lolos
        # EV (lihat _analisis_ev_mengikat).
        analisis = _analisis_ev_mengikat()
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

    def test_den_live_ada_equilibrium_asuransi_tapi_diveto(self):
        # REVISI KOORDINATOR v18: DEN@CHI live KINI PUNYA
        # equilibrium Asuransi — U258,5 @87,5¢ (p_final 0,8723,
        # EV -0,30%, 6 garis lolos). Equilibrium adalah hitungan
        # per garis, BUKAN vonis: Denver tetap terblokir dari tiket
        # oleh vonis (veto AND / TUNGGU_LINEUP) + skip_awal
        # (pola_denver) + alokasi komposer — bukan oleh equilibrium.
        # Tes ini mengunci bahwa equilibrium TIDAK memveto Denver
        # (tugas itu milik vonis/skip), sekaligus nilainya.
        analisis = self.live["DEN@CHI_2026-11-22"]
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 258.5)
        self.assertEqual(hasil["harga_venue_cents"], 87.5)
        self.assertAlmostEqual(hasil["p_final"], 0.8723, places=4)
        self.assertAlmostEqual(hasil["ev_pct"], -0.30, places=1)
        self.assertEqual(hasil["n_kandidat_lolos"], 6)

    def test_den_live_ada_equilibrium_utama_tapi_diveto(self):
        # REVISI KOORDINATOR v18 (pasangan tes di atas, tiket
        # Utama): DEN live punya equilibrium Utama U254,5 @82,5¢
        # (p_final 0,8247, EV -0,04%, 9 garis lolos). Denver tetap
        # terblokir dari tiket oleh vonis/skip/komposer.
        analisis = self.live["DEN@CHI_2026-11-22"]
        hasil = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 254.5)
        self.assertEqual(hasil["harga_venue_cents"], 82.5)
        self.assertAlmostEqual(hasil["p_final"], 0.8247, places=4)
        self.assertAlmostEqual(hasil["ev_pct"], -0.04, places=1)
        self.assertEqual(hasil["n_kandidat_lolos"], 9)

    def test_den_verif_ada_equilibrium_kedua_tiket(self):
        # REVISI KOORDINATOR v18: DEN verif punya equilibrium di
        # kedua tiket — Asuransi U258,5 @89¢ (p_final 0,8912, EV
        # +0,13%, 7 garis lolos), Utama U254,5 @84¢ (p_final
        # 0,8485, EV +1,01%, 9 garis lolos). Blokir Denver tetap
        # tugas vonis (veto AND menyala di artefak ini) + skip_awal.
        analisis = self.verif["DEN@CHI_2026-11-22"]
        hasil_ins = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil_ins["ada"])
        self.assertEqual(hasil_ins["garis"], 258.5)
        self.assertEqual(hasil_ins["harga_venue_cents"], 89.0)
        self.assertAlmostEqual(hasil_ins["p_final"], 0.8912, places=4)
        self.assertAlmostEqual(hasil_ins["ev_pct"], 0.13, places=1)
        self.assertEqual(hasil_ins["n_kandidat_lolos"], 7)
        hasil_main = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil_main["ada"])
        self.assertEqual(hasil_main["garis"], 254.5)
        self.assertEqual(hasil_main["harga_venue_cents"], 84.0)
        self.assertAlmostEqual(hasil_main["p_final"], 0.8485, places=4)
        self.assertAlmostEqual(hasil_main["ev_pct"], 1.01, places=1)
        self.assertEqual(hasil_main["n_kandidat_lolos"], 9)

    def test_okc_verif_asuransi_vs_utama_berbeda_tujuan(self):
        # KASUS WAJIB (worker B): equilibrium Asuransi vs Utama
        # BERBEDA sesuai tujuannya. OKC@MIA verif v18 (REVISI
        # KOORDINATOR — gate eksekusi likuiditas+spread membuka
        # lebih banyak garis):
        # - Asuransi (safety-first): ADA di U248,5 @88¢, p_final
        #   0,8909, EV +1,24% — p_final tertinggi DALAM BAND
        #   80–89¢ (9 garis lolos: 242,5–258,5).
        # - Utama (max-er): ADA di U244,5 @82,5¢, p_final 0,8421,
        #   ER 1,0207 — titik paling manis DALAM BAND 76–84¢
        #   (U240,5 @75,5¢ ER-nya lebih tinggi 1,0448 tapi di
        #   bawah band — band didahulukan atas ER).
        # Di v17 Asuransi TIDAK ADA (U250,5 gagal edge +1,3% <
        # 3,5%); di v18 gate edge diganti EV (+1,49% >= -1%) dan
        # banjir dua ambang (86,9%/82,1% >= 70%/65%), sehingga
        # Asuransi terbentuk.
        analisis = self.verif["OKC@MIA_2026-11-22"]
        hasil_ins = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        hasil_main = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertEqual(hasil_ins["mode"], "safety_first")
        self.assertEqual(hasil_main["mode"], "max_er")
        self.assertTrue(hasil_ins["ada"])
        self.assertEqual(hasil_ins["garis"], 248.5)
        self.assertEqual(hasil_ins["harga_venue_cents"], 88.0)
        self.assertAlmostEqual(hasil_ins["p_final"], 0.8909, places=4)
        self.assertAlmostEqual(hasil_ins["ev_pct"], 1.24, places=1)
        self.assertEqual(hasil_ins["n_kandidat_lolos"], 9)
        self.assertTrue(hasil_ins["dalam_band"])
        self.assertTrue(hasil_main["ada"])
        self.assertEqual(hasil_main["garis"], 244.5)
        self.assertEqual(hasil_main["harga_venue_cents"], 82.5)
        self.assertAlmostEqual(hasil_main["p_final"], 0.8421, places=4)
        self.assertAlmostEqual(hasil_main["expected_return"], 1.0207, places=3)

    def test_okc_verif_equilibrium_utama(self):
        # KASUS WAJIB 2: OKC@MIA verif — equilibrium Utama ada di
        # U244,5 @82,5¢ (p_final 0,842, ER 1,0207) DALAM BAND
        # 76–84¢. U240,5 @75,5¢ ER-nya lebih tinggi (1,0448) tapi
        # di bawah band — band didahulukan atas ER (preferensi
        # seleksi, bukan gate: fallback hanya bila tidak ada garis
        # lolos dalam band). Equilibrium memilih nilai di dalam
        # band, bukan garis termahal maupun termurah.
        analisis = self.verif["OKC@MIA_2026-11-22"]
        hasil = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 244.5)
        self.assertEqual(hasil["harga_venue_cents"], 82.5)
        self.assertAlmostEqual(hasil["p_final"], 0.8421, places=4)
        self.assertAlmostEqual(hasil["expected_return"], 1.0207, places=3)
        self.assertTrue(hasil["thin"])
        self.assertTrue(hasil["dalam_band"])
        self.assertFalse(hasil["fallback_band"])
        ktx = equilibrium.siapkan_konteks(analisis, "main", CFG)
        _, _, p_final_240 = equilibrium.peluang_pada_garis(ktx, 240.5)
        er_240 = p_final_240 * (100.0 / 75.5)
        self.assertAlmostEqual(er_240, 1.0448, places=3)
        self.assertGreater(er_240, hasil["expected_return"])

    def test_okc_verif_garis_250_5_lolos_semua_gate_v18(self):
        # KASUS WAJIB v18 (perintah worker B): garis U250,5 @89,5¢
        # OKC verif (p_final 0,908) HARUS lolos SEMUA gate Asuransi
        # v18 — di v17 garis ini gagal edge (+1,3% < 3,5%). Gate
        # v18: peluang 90,8% >= 82%, p_market 89,5% >= 80%, EV
        # +1,49% >= -1%, banjir 3P 86,9% >= 70%, banjir FT 82,1%
        # >= 65%, eksekusi: likuiditas $33.013 >= $30 + spread 2¢
        # <= 5¢ + ask nyata. Equilibrium memilih U248,5 (bukan
        # 250,5) karena 89,5¢ di luar band 80–89¢.
        analisis = self.verif["OKC@MIA_2026-11-22"]
        ktx = equilibrium.siapkan_konteks(analisis, "insurance", CFG)
        baris = {
            r["line"]: r
            for r in equilibrium.nilai_semua_garis(analisis, "insurance", CFG, ktx=ktx)
        }
        baris_250 = baris[250.5]
        self.assertTrue(baris_250["lolos_semua"])
        self.assertAlmostEqual(baris_250["p_final"], 0.908341, places=5)
        self.assertAlmostEqual(baris_250["p_market"], 0.895, places=5)
        self.assertAlmostEqual(baris_250["ev_pct"], 1.49, places=1)
        self.assertAlmostEqual(baris_250["p_banjir_3p"], 0.86882, places=4)
        self.assertAlmostEqual(baris_250["p_banjir_ft"], 0.82114, places=4)
        self.assertAlmostEqual(baris_250["volume_usd"], 226.875, places=2)
        self.assertAlmostEqual(baris_250["likuiditas_usd"], 33013.26, places=1)
        self.assertEqual(baris_250["bid_cents"], 88.0)
        self.assertEqual(baris_250["ask_cents"], 90.0)
        self.assertEqual(baris_250["spread_cents"], 2.0)
        self.assertIsNone(baris_250["eksekusi_alasan"])
        self.assertTrue(all(baris_250["gate"].values()))
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertEqual(hasil["garis"], 248.5)

    def test_jankar_mereproduksi_p_final_artefak_okc_verif(self):
        # Di garis jangkar artefak nyata, p_final hasil geser
        # mereproduksi p_final kaki artefak (0,908341) — bukti
        # asumsi geser-lokasi konsisten dengan data nyata.
        analisis = self.verif["OKC@MIA_2026-11-22"]
        ktx = equilibrium.siapkan_konteks(analisis, "insurance", CFG)
        _, _, p_final = equilibrium.peluang_pada_garis(ktx, 250.5)
        self.assertAlmostEqual(p_final, 0.908341, places=5)

    def test_sepuluh_baris_v18_semua_ada_equilibrium(self):
        # REVISI KOORDINATOR v18 (MEMBALIK
        # test_sepuluh_baris_v18_tiga_asuransi_tiga_utama): dengan
        # gate eksekusi likuiditas + spread (bukan volume
        # kumulatif), equilibrium ADA di 10/10 baris untuk KEDUA
        # tiket. Gate volume adalah penghalang yang mengikat di
        # pengukuran worker B (3/10) — dan penghalang itu mengukur
        # hal yang salah (sejarah perdagangan, bukan kemampuan beli
        # sekarang). Diukur 2026-11-23 dengan config v18 (geser
        # banjir 8,5/12,52); bila config/artefak berubah, ukur
        # ulang.
        semua = list(self.live.values()) + list(self.verif.values())
        self.assertEqual(len(semua), 10)
        ada_ins = []
        ada_main = []
        for analisis in semua:
            mid = analisis.get("match_id")
            with self.subTest(match_id=mid):
                hasil_ins = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
                hasil_main = equilibrium.cari_equilibrium(analisis, "main", CFG)
                self.assertTrue(
                    hasil_ins["ada"],
                    f"Asuransi tidak ada: {hasil_ins['alasan_tidak_ada']}",
                )
                self.assertTrue(
                    hasil_main["ada"],
                    f"Utama tidak ada: {hasil_main['alasan_tidak_ada']}",
                )
                ada_ins.append(mid)
                ada_main.append(mid)
        self.assertEqual(len(ada_ins), 10)
        self.assertEqual(len(ada_main), 10)

    def test_det_live_asuransi_thin_tapi_lolos_eksekusi(self):
        # DET@ATL live: equilibrium Asuransi U245,5 @88,5¢ (p_final
        # 0,877601, EV -0,84%, banjir 82,0%/76,2%) — thin=True tapi
        # LOLOS gate eksekusi v18 (di v17 thin = hard gate, garis
        # ini dicoret). Flag info_volume_dibawah_100 True ($93 <
        # $100) — info, bukan blokir. REVISI KOORDINATOR: 5 garis
        # lolos (bukan 1) karena gate eksekusi kini likuiditas +
        # spread, bukan volume kumulatif.
        analisis = self.live["DET@ATL_2026-11-22"]
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 245.5)
        self.assertEqual(hasil["harga_venue_cents"], 88.5)
        self.assertAlmostEqual(hasil["p_final"], 0.877601, places=5)
        self.assertAlmostEqual(hasil["ev_pct"], -0.84, places=1)
        self.assertTrue(hasil["thin"])
        self.assertEqual(hasil["volume_usd"], 93.0)
        self.assertTrue(hasil["info_volume_dibawah_100"])
        self.assertEqual(hasil["n_kandidat_lolos"], 5)

    def test_orl_live_ada_equilibrium_kedua_tiket(self):
        # REVISI KOORDINATOR v18 (MEMBALIK
        # test_orl_live_tidak_ada_equilibrium): ORL@WAS live kini
        # PUNYA equilibrium di kedua tiket — Asuransi U241,5 @88¢
        # (p_final 0,8721, 1 garis lolos), Utama U235,5 @80,5¢
        # (p_final 0,7954, 3 garis lolos). Gate volume-lah yang
        # dulu memblokir keduanya.
        analisis = self.live["ORL@WAS_2026-11-22"]
        hasil_ins = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil_ins["ada"])
        self.assertEqual(hasil_ins["garis"], 241.5)
        self.assertEqual(hasil_ins["harga_venue_cents"], 88.0)
        self.assertAlmostEqual(hasil_ins["p_final"], 0.8721, places=4)
        self.assertEqual(hasil_ins["n_kandidat_lolos"], 1)
        hasil_main = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil_main["ada"])
        self.assertEqual(hasil_main["garis"], 235.5)
        self.assertEqual(hasil_main["harga_venue_cents"], 80.5)
        self.assertAlmostEqual(hasil_main["p_final"], 0.7954, places=4)
        self.assertEqual(hasil_main["n_kandidat_lolos"], 3)


class TestGateV18(unittest.TestCase):
    """Gate baru v18: band + fallback, tie-break ER, eksekusi,
    p_market, MODEL_ONLY, banjir dua ambang, banjir warning Utama."""

    def test_band_fallback_bila_tidak_ada_garis_dalam_band(self):
        # Tangga 240,5–248,5 @90,5–98,5¢ (semua di atas band
        # Asuransi 80–89¢): semua 5 garis lolos semua gate ->
        # fallback ke p_final tertinggi mutlak (248,5, p_final
        # 0,998538), fallback_band True dicatat. Band adalah
        # preferensi seleksi, bukan gate — garis di luar band
        # tetap bisa dipilih bila tidak ada yang di dalam band.
        tangga = _tangga(
            [
                (240.5, 90.0, 500.0, False),
                (242.5, 94.0, 500.0, False),
                (244.5, 96.0, 500.0, False),
                (246.5, 97.0, 500.0, False),
                (248.5, 98.0, 500.0, False),
            ]
        )
        analisis = _analisis_224(tangga=tangga)
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 248.5)
        self.assertEqual(hasil["p_final"], 0.998538)
        self.assertEqual(hasil["n_kandidat_lolos"], 5)
        self.assertFalse(hasil["dalam_band"])
        self.assertTrue(hasil["fallback_band"])

    def test_tiebreak_er_di_luar_toleransi_max_er_menang(self):
        # Selisih ER 0,053 > toleransi 0,015: max-ER menang meski
        # p_final-nya lebih rendah — 240,5 @76¢ (p 0,90, ER
        # 1,1842) mengalahkan 242,5 @84¢ (p 0,95, ER 1,1310).
        # Kebalikan test_memilih_expected_return_tertinggi (selisih
        # 0,0051 < toleransi -> yang lebih aman menang).
        analisis = {
            "format": "nba_analysis",
            "format_version": 1,
            "match_id": "TOL@ER_2026-11-22",
            "status": "OK",
            "legs": [
                _kaki("TOL@ER_2026-11-22", "insurance", 240.5, 0.9, 0.9, 76.0),
                _kaki("TOL@ER_2026-11-22", "main", 242.5, 0.95, 0.95, 84.0),
            ],
            "simulation": {
                "score_distribution": {"total": {"median": 230.0}},
                "markets": {
                    "total_under_240.5": 0.9,
                    "total_under_242.5": 0.95,
                },
            },
            "market": {
                "main_total_line": 231.5,
                "totals": [
                    {
                        "line": 240.5,
                        "side": "under",
                        "price_cents": 76.0,
                        "jup_estimated_cents": 76.0,
                        "volume_usd": 500.0,
                        "thin": False,
                        "bid_cents": 75.0,
                        "ask_cents": 76.5,
                        "liquidity": 30000.0,
                    },
                    {
                        "line": 242.5,
                        "side": "under",
                        "price_cents": 84.0,
                        "jup_estimated_cents": 84.0,
                        "volume_usd": 500.0,
                        "thin": False,
                        "bid_cents": 83.0,
                        "ask_cents": 84.5,
                        "liquidity": 30000.0,
                    },
                ],
            },
        }
        hasil = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 240.5)
        self.assertAlmostEqual(hasil["expected_return"], 1.1842, places=3)
        self.assertEqual(hasil["p_final"], 0.9)

    def test_likuiditas_min_eksekusi_max_dua_kali_stake_25(self):
        # execution: max(2 x stake, $25). Produksi: stake $15 ->
        # $30. Stake $20 -> $40; stake $10 -> $25 (batas bawah).
        self.assertEqual(equilibrium.likuiditas_min_eksekusi(CFG), 30.0)
        cfg = copy.deepcopy(CFG)
        cfg["execution"]["stake_default_usd"] = 20.0
        self.assertEqual(equilibrium.likuiditas_min_eksekusi(cfg), 40.0)
        cfg["execution"]["stake_default_usd"] = 10.0
        self.assertEqual(equilibrium.likuiditas_min_eksekusi(cfg), 25.0)

    def test_gate_eksekusi_batas_30_dolar(self):
        # REVISI KOORDINATOR v18: batas $30 kini berlaku untuk
        # LIKUIDITAS Gamma, bukan volume kumulatif. Likuiditas
        # $29,99 gagal; $30,00 lolos (batas inklusif). Likuiditas
        # None gagal (fail-closed). Volume None BUKAN lagi
        # penghalang: DEN U264,5 @94¢ (volume None, likuiditas
        # $30.000, spread 2¢) kini LOLOS gate eksekusi — volume
        # kumulatif mengukur sejarah, bukan kemampuan beli sekarang.
        tangga = _tangga_224()
        for entri in tangga:
            if entri["line"] == 246.5:
                entri["liquidity"] = 29.99
        analisis = _analisis_224(tangga=tangga)
        ktx = equilibrium.siapkan_konteks(analisis, "insurance", CFG)
        baris = {
            r["line"]: r
            for r in equilibrium.nilai_semua_garis(analisis, "insurance", CFG, ktx=ktx)
        }
        self.assertFalse(baris[246.5]["gate"]["eksekusi"])
        self.assertFalse(baris[246.5]["lolos_semua"])
        self.assertEqual(baris[246.5]["eksekusi_alasan"], "likuiditas_di_bawah_minimum")
        for entri in tangga:
            if entri["line"] == 246.5:
                entri["liquidity"] = 30.0
        analisis = _analisis_224(tangga=tangga)
        ktx = equilibrium.siapkan_konteks(analisis, "insurance", CFG)
        baris = {
            r["line"]: r
            for r in equilibrium.nilai_semua_garis(analisis, "insurance", CFG, ktx=ktx)
        }
        self.assertTrue(baris[246.5]["gate"]["eksekusi"])
        self.assertTrue(baris[246.5]["lolos_semua"])
        self.assertIsNone(baris[246.5]["eksekusi_alasan"])
        for entri in tangga:
            if entri["line"] == 246.5:
                entri["liquidity"] = None
        analisis = _analisis_224(tangga=tangga)
        ktx = equilibrium.siapkan_konteks(analisis, "insurance", CFG)
        baris = {
            r["line"]: r
            for r in equilibrium.nilai_semua_garis(analisis, "insurance", CFG, ktx=ktx)
        }
        self.assertFalse(baris[246.5]["gate"]["eksekusi"])
        self.assertEqual(baris[246.5]["eksekusi_alasan"], "likuiditas_tidak_tercatat")
        analisis_den = _analisis_den()
        ktx_den = equilibrium.siapkan_konteks(analisis_den, "insurance", CFG)
        baris_den = {
            r["line"]: r
            for r in equilibrium.nilai_semua_garis(
                analisis_den, "insurance", CFG, ktx=ktx_den
            )
        }
        self.assertIsNone(baris_den[264.5]["volume_usd"])
        self.assertTrue(baris_den[264.5]["gate"]["eksekusi"])
        self.assertIsNone(baris_den[264.5]["eksekusi_alasan"])

    def test_gate_p_market_asuransi(self):
        # Fixture-224 Asuransi: U236,5 gagal gate p_market (68,9%
        # < 80%) meski EV-nya lolos (-0,64% >= -1%); U238,5 lolos
        # (81,2% >= 80%). Gate ini HANYA Asuransi — baris Utama
        # tidak punya gate p_market.
        analisis = _analisis_224()
        ktx = equilibrium.siapkan_konteks(analisis, "insurance", CFG)
        baris = {
            r["line"]: r
            for r in equilibrium.nilai_semua_garis(analisis, "insurance", CFG, ktx=ktx)
        }
        self.assertFalse(baris[236.5]["gate"]["p_market"])
        self.assertTrue(baris[236.5]["gate"]["ev"])
        self.assertTrue(baris[238.5]["gate"]["p_market"])
        ktx_main = equilibrium.siapkan_konteks(analisis, "main", CFG)
        baris_main = equilibrium.nilai_semua_garis(analisis, "main", CFG, ktx=ktx_main)
        self.assertNotIn("p_market", baris_main[0]["gate"])

    def test_model_only_gate_p_market_tidak_dievaluasi(self):
        # MODEL_ONLY (butuh_anchor_pasar false + kedua kaki tanpa
        # p_market): gate p_market TIDAK dievaluasi (dicatat
        # p_market_gate_dievaluasi False), BUKAN fail-closed —
        # equilibrium tetap ada bila p_final + banjir + EV lolos.
        # BUKAN nilai produksi (produksi butuh_anchor_pasar true).
        cfg = copy.deepcopy(CFG)
        cfg["equilibrium"]["butuh_anchor_pasar"] = False
        analisis = _analisis_224()
        for leg in analisis["legs"]:
            leg["p_market"] = None
            leg["comparison_source"] = None
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", cfg)
        self.assertTrue(hasil["dihitung"])
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 246.5)
        self.assertFalse(hasil["p_market_gate_dievaluasi"])
        ktx = equilibrium.siapkan_konteks(analisis, "insurance", cfg)
        baris = {
            r["line"]: r
            for r in equilibrium.nilai_semua_garis(analisis, "insurance", cfg, ktx=ktx)
        }
        self.assertIsNone(baris[240.5]["p_market"])
        self.assertTrue(baris[240.5]["gate"]["p_market"])
        self.assertFalse(baris[240.5]["p_market_gate_dievaluasi"])

    def test_banjir_dua_ambang_terpisah(self):
        # DEN U252,5: lolos banjir 3P (71,6% >= 70%) tapi gagal
        # banjir FT (64,2% < 65%) -> tidak lolos (DUA ambang
        # terpisah — v17 hanya memakai yang terburuk). U254,5
        # lolos keduanya (75,1%/68,0%).
        analisis = _analisis_den()
        ktx = equilibrium.siapkan_konteks(analisis, "insurance", CFG)
        baris = {
            r["line"]: r
            for r in equilibrium.nilai_semua_garis(analisis, "insurance", CFG, ktx=ktx)
        }
        self.assertTrue(baris[252.5]["gate"]["banjir_3p"])
        self.assertFalse(baris[252.5]["gate"]["banjir_ft"])
        self.assertFalse(baris[252.5]["lolos_semua"])
        self.assertTrue(baris[254.5]["gate"]["banjir_3p"])
        self.assertTrue(baris[254.5]["gate"]["banjir_ft"])
        self.assertTrue(baris[254.5]["lolos_semua"])

    def test_utama_banjir_warning_di_hasil(self):
        # Utama dengan satu-satunya garis lolos 234,5 (banjir 3P
        # 65,5% < 70%): equilibrium TETAP ADA (banjir tidak
        # memblokir Utama) dengan banjir_warning True.
        tangga = _tangga([(234.5, 76.0, 500.0, False)])
        analisis = _analisis_224(tangga=tangga)
        hasil = equilibrium.cari_equilibrium(analisis, "main", CFG)
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["garis"], 234.5)
        self.assertTrue(hasil["banjir_warning"])


class TestGateEksekusiLikuiditasSpread(unittest.TestCase):
    """Gate eksekusi v18 (revisi koordinator): likuiditas Gamma +
    spread bid/ask + ask nyata — SATU implementasi cek_eksekusi.

    Menggantikan gate volume_usd worker B: volume kumulatif
    mengukur sejarah perdagangan, bukan kemampuan beli sekarang
    (bukti: DET U239,5 bid 79/ask 82, likuiditas $36.580, volume
    $5 — order $15 di ask pasti terisi, tapi gate volume
    memblokirnya).
    """

    @staticmethod
    def _entri(**ubah):
        entri = {
            "line": 245.5,
            "side": "under",
            "price_cents": 88.0,
            "jup_estimated_cents": 88.5,
            "volume_usd": 5.0,
            "thin": True,
            "bid_cents": 87.0,
            "ask_cents": 89.0,
            "liquidity": 30000.0,
        }
        entri.update(ubah)
        return entri

    def test_lolos_kuotasi_hidup(self):
        hasil = equilibrium.cek_eksekusi(self._entri(), CFG)
        self.assertTrue(hasil["lolos"])
        self.assertIsNone(hasil["alasan"])
        self.assertEqual(hasil["spread_cents"], 2.0)
        self.assertEqual(hasil["likuiditas_min_usd"], 30.0)

    def test_batas_likuiditas_30_dolar_inklusif(self):
        gagal = equilibrium.cek_eksekusi(self._entri(liquidity=29.99), CFG)
        self.assertFalse(gagal["lolos"])
        self.assertEqual(gagal["alasan"], "likuiditas_di_bawah_minimum")
        lolos = equilibrium.cek_eksekusi(self._entri(liquidity=30.0), CFG)
        self.assertTrue(lolos["lolos"])

    def test_likuiditas_tidak_tercatat_fail_closed(self):
        hasil = equilibrium.cek_eksekusi(self._entri(liquidity=None), CFG)
        self.assertFalse(hasil["lolos"])
        self.assertEqual(hasil["alasan"], "likuiditas_tidak_tercatat")

    def test_tanpa_kuotasi_fail_closed(self):
        for ubah in ({"bid_cents": None}, {"ask_cents": None}):
            with self.subTest(ubah=ubah):
                hasil = equilibrium.cek_eksekusi(self._entri(**ubah), CFG)
                self.assertFalse(hasil["lolos"])
                self.assertEqual(hasil["alasan"], "tanpa_kuotasi")

    def test_ask_99_bukan_ask_nyata(self):
        # Ask 99¢ = sentinel "tidak ada ask" — gagal meski spread
        # tampak sempit (bid 97 / ask 99): yang dibayar user adalah
        # ask, dan ask 99¢ berarti membayar harga maksimum.
        hasil = equilibrium.cek_eksekusi(
            self._entri(bid_cents=97.0, ask_cents=99.0), CFG
        )
        self.assertFalse(hasil["lolos"])
        self.assertEqual(hasil["alasan"], "tanpa_ask_nyata")

    def test_batas_spread_5_sen_inklusif(self):
        lolos = equilibrium.cek_eksekusi(
            self._entri(bid_cents=85.0, ask_cents=90.0), CFG
        )
        self.assertTrue(lolos["lolos"])
        self.assertEqual(lolos["spread_cents"], 5.0)
        gagal = equilibrium.cek_eksekusi(
            self._entri(bid_cents=85.0, ask_cents=90.01), CFG
        )
        self.assertFalse(gagal["lolos"])
        self.assertEqual(gagal["alasan"], "spread_terlalu_lebar")

    def test_volume_kecil_bukan_penghalang(self):
        # Volume kumulatif $5 (atau None) TIDAK memblokir bila
        # likuiditas + spread lolos — inti revisi koordinator.
        for volume in (5.0, None):
            with self.subTest(volume=volume):
                hasil = equilibrium.cek_eksekusi(self._entri(volume_usd=volume), CFG)
                self.assertTrue(hasil["lolos"])

    def test_diagnosis_eksekusi_menyebut_alasan(self):
        # Semua garis spread lebar (20¢) -> tidak ada equilibrium,
        # alasan menamai token eksekusi_tidak_lolos + spread.
        tangga = _tangga_224()
        for entri in tangga:
            harga = entri["price_cents"]
            entri["bid_cents"] = harga - 10.0
            entri["ask_cents"] = harga + 10.0
        analisis = _analisis_224(tangga=tangga)
        hasil = equilibrium.cari_equilibrium(analisis, "insurance", CFG)
        self.assertFalse(hasil["ada"])
        self.assertIn("eksekusi_tidak_lolos", hasil["alasan_tidak_ada"])
        self.assertIn("spread", hasil["alasan_tidak_ada"])


if __name__ == "__main__":
    unittest.main()
