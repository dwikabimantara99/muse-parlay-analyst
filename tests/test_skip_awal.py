"""Tes skip dari awal (engine/skip_awal.py).

Tiga pemicu (satu cukup untuk skip dari KEDUA tiket):
(a) tidak_ada_equilibrium — equilibrium tidak ada di kedua tiket;
(b) pola_denver — konjungsi 4 syarat (flag setan + tidak ada garis
    yang bisa dibeli yang tahan banjir + garis acuan gagal gate
    eksekusi + EV kecil) — v18.1: syarat (4) EV (bukan edge),
    "non-thin" = lolos cek_eksekusi (bukan flag thin), flag setan
    memakai setan per pemain bila blok ada; + pagar anti-redundansi
    (lihat tests/test_skip_awal_v18_1.py).
(c) ot_tinggi — probabilitas OT EMPIRIS (engine/ot_empiris.py,
    dari spread |median margin|) >= ambang
    ot_seleksi.hard_skip_ot_prob (0,085 INITIAL, v18). Pemicu keras
    v17 (ot_probability sim >= 0,028) DIHAPUS. OT sim dicatat
    sebagai info saja. KEJUJURAN: hard-skip 0,085 tidak tercapai
    di bawah rumus v18 (p_ot maks 0,0575) — tes pemicu memakai
    cfg ambang-diturunkan (0,05) untuk menguji jalurnya.

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
from engine import vonis as vonis_mod

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
    """Tangga totals dari daftar (garis, harga, volume, thin[, ubah]).

    Harga jup.ag = harga Polymarket + 0,5¢ (markup tipikal).
    Kuotasi default hidup (bid harga-1 / ask harga+0,5) +
    likuiditas $30.000 — garis fixture lolos gate eksekusi v18
    kecuali elemen ke-5 (dict ubah, mis. {"liquidity": 5.0})
    mengubahnya eksplisit (revisi koordinator + v18.1).
    """
    hasil = []
    for baris_satu in baris:
        garis, harga, volume, thin = baris_satu[:4]
        ubah = baris_satu[4] if len(baris_satu) > 4 else {}
        entri = {
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
        entri.update(ubah)
        hasil.append(entri)
    return hasil


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
    match_id,
    median,
    sigma,
    kaki_ins,
    kaki_main,
    tangga,
    ot=None,
    langkah=2.0,
    margin=None,
):
    """Artefak nba_analysis minimal dengan CDF normal penuh + tangga.

    ``margin``: median margin sim (|margin| = spread untuk OT
    empiris v18); None = tidak ada distribusi margin (OT tidak
    bisa dinilai). ``ot``: ot_probability sim (info saja di v18).
    """
    markets = _cdf_normal(median, sigma, median - 30, median + 45, langkah)
    distribusi = {"total": {"median": median}}
    if ot is not None:
        distribusi["ot_probability"] = ot
    if margin is not None:
        distribusi["margin"] = {"median": margin}
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


def _cfg_ambang_ot_rendah():
    """CFG + hard_skip_ot_prob 0,05 (untuk menguji JALUR hard-skip
    — dengan ambang v18 0,085, tidak ada spread yang memicu; lihat
    TestHardSkipDormant di test_ot_empiris.py)."""
    cfg = copy.deepcopy(CFG)
    cfg["ot_seleksi"]["hard_skip_ot_prob"] = 0.05
    return cfg


def _analisis_pola_denver(match_id="DEN@CHI_2026-11-22", ot=0.02, margin=None):
    """Fixture pola Denver: keempat syarat benar (median 233, sigma 19,2).

    v18.1: garis acuan 252,5 @84,5¢ jup (P normal 84,5%, P setan
    generik 53,0% — tanpa blok setan_pemain, p_final ~0,807 ->
    EV ~-4,5% < -1%) — harganya dinaikkan dari 78¢ ke 84¢ supaya
    syarat (4) EV tetap benar. Garis acuan + garis tahan banjir
    264,5–270,5 (4 garis) gagal gate eksekusi (likuiditas $5);
    flag thin dipertahankan (bahan asersi cari_garis_acuan lama:
    n_tahan_banjir_nonthin == 0). Equilibrium ADA di kedua tiket
    (U262,5) — skip hanya via pola (b), bukan via (a). OT 2,0%
    (di bawah ambang) — bukan via (c). Pagar TIDAK berlaku: veto
    tidak bisa dievaluasi (tanpa data cedera).
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
            (252.5, 84.0, 20.0, True, {"liquidity": 5.0}),
            (254.5, 78.0, 500.0, False),
            (256.5, 80.0, 500.0, False),
            (258.5, 82.0, 10.0, True),
            (260.5, 84.0, 10.0, True),
            (262.5, 86.0, 10.0, True),
            (264.5, 94.0, 10.0, True, {"liquidity": 5.0}),
            (266.5, 95.0, 10.0, True, {"liquidity": 5.0}),
            (268.5, 96.0, 10.0, True, {"liquidity": 5.0}),
            (270.5, 97.0, 10.0, True, {"liquidity": 5.0}),
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
        margin=margin,
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
                "ev_kecil": True,
            },
        )
        acuan = pola["garis_acuan"]
        self.assertEqual(acuan["garis"], 252.5)
        self.assertTrue(acuan["thin"])
        self.assertAlmostEqual(acuan["p_normal"], 0.84485, places=4)
        self.assertAlmostEqual(acuan["p_setan"], 0.53, places=2)
        self.assertLess(acuan["ev"], -0.01)
        self.assertEqual(acuan["n_tahan_banjir"], 4)
        self.assertEqual(acuan["n_tahan_banjir_nonthin"], 0)
        self.assertEqual(acuan["n_tahan_banjir_bisa_dibeli"], 0)

    def test_syarat2_mati_ada_garis_tahan_tebal(self):
        # v18.1: satu garis tahan banjir dipulihkan likuiditasnya
        # ($30.000 — lolos gate eksekusi) -> syarat (2) mati ->
        # pola tidak cocok -> tidak di-skip. (Di v18, yang diubah
        # flag thin; kini yang dinilai gate eksekusi.)
        analisis = _analisis_pola_denver()
        for entri in analisis["market"]["totals"]:
            if entri["line"] == 266.5:
                entri["thin"] = False
                entri["volume_usd"] = 500.0
                entri["liquidity"] = 30000.0
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertFalse(
            hasil["pola_denver"]["syarat"]["tidak_ada_tahan_banjir_nonthin"]
        )
        self.assertFalse(hasil["pola_denver"]["cocok"])
        self.assertFalse(hasil["skip"])

    def test_syarat3_mati_garis_acuan_tebal(self):
        # v18.1: garis acuan (252,5) dipulihkan likuiditasnya
        # ($30.000 — lolos gate eksekusi) -> syarat (3) mati ->
        # pola tidak cocok -> tidak di-skip.
        analisis = _analisis_pola_denver()
        for entri in analisis["market"]["totals"]:
            if entri["line"] == 252.5:
                entri["thin"] = False
                entri["volume_usd"] = 500.0
                entri["liquidity"] = 30000.0
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertFalse(hasil["pola_denver"]["syarat"]["garis_acuan_thin"])
        self.assertFalse(hasil["pola_denver"]["cocok"])
        self.assertFalse(hasil["skip"])

    def test_syarat4_mati_ev_besar(self):
        # v18.1: harga garis acuan (252,5) diturunkan ke 60¢ -> EV
        # +33% (>= -1%) -> syarat (4) mati -> pola tidak cocok.
        analisis = _analisis_pola_denver()
        for entri in analisis["market"]["totals"]:
            if entri["line"] == 252.5:
                entri["price_cents"] = 60.0
                entri["jup_estimated_cents"] = 60.5
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertFalse(hasil["pola_denver"]["syarat"]["ev_kecil"])
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
                # v18.1: 250,5 @99,5¢ jup (ask 99,5¢ -> gagal gate
                # eksekusi; EV -1,9% < -1%) supaya syarat (2)-(4)
                # tetap benar di logika baru.
                (250.5, 99.0, 10.0, True),
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
        self.assertTrue(syarat["ev_kecil"])
        self.assertFalse(hasil["pola_denver"]["cocok"])
        # v18.1: laga ini di-skip via (a) — equilibrium TIDAK ada
        # (250,5 gagal eksekusi; 230,5 gagal peluang) — tapi TIDAK
        # via pola: syarat (1) sendirian memblokir pola.
        self.assertNotIn("pola_denver", hasil["pemicu"])
        self.assertEqual(hasil["pemicu"], ["tidak_ada_equilibrium"])
        self.assertTrue(hasil["skip"])

    def test_syarat1_kontrol_cdf_normal_flag_hidup(self):
        # Kontrol tes di atas: tangga jarang yang sama dengan CDF
        # normal (sigma 19,2) -> flag hidup -> pola cocok -> skip.
        # v18: median 232,0 (bukan 233,0) supaya garis 250,5
        # mencapai target Asuransi 0,82 (P 0,8321); dengan median
        # 233,0, P(250,5) = 0,819 < 0,82 sehingga garis acuan
        # tidak ada dan pola tidak bisa dinilai. Pemicu v18 dua:
        # pola + (a) (tangga jarang tidak punya equilibrium).
        match_id = "JAR@ANG_2026-11-22"
        tangga = _tangga(
            [
                (230.5, 70.0, 500.0, False),
                # v18.1: 250,5 @99,5¢ jup (ask 99,5¢ -> gagal gate
                # eksekusi; EV -17,2% < -1%) supaya syarat (2)-(4)
                # tetap benar di logika baru.
                (250.5, 99.0, 10.0, True),
            ]
        )
        analisis = _analisis(
            match_id,
            232.0,
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
        self.assertEqual(hasil["pemicu"], ["tidak_ada_equilibrium", "pola_denver"])


class TestOT(unittest.TestCase):
    """Pemicu (c): potensi OT EMPIRIS tinggi -> skip (bukan bantalan).

    v18: keputusan dari p_ot empiris (spread), bukan ot_prob sim.
    Ambang v18 0,085 tidak tercapai rumus (p_ot maks 0,0575) — tes
    jalur pemicu memakai cfg ambang-diturunkan 0,05.
    """

    def test_ambang_batas_cfg_rendah(self):
        # Ambang 0,05 (>=, inklusif): spread 0 (0,0575) kena,
        # spread 15 (0,0335) tidak.
        cfg = _cfg_ambang_ot_rendah()
        analisis = _analisis_pola_denver(margin=0.0)
        tinggi, ot, ambang = skip_awal.potensi_ot_tinggi(analisis, cfg)
        self.assertTrue(tinggi)
        self.assertEqual(ot, 0.0575)
        self.assertEqual(ambang, 0.05)
        analisis = _analisis_pola_denver(margin=15.0)
        tinggi, _, _ = skip_awal.potensi_ot_tinggi(analisis, cfg)
        self.assertFalse(tinggi)

    def test_ambang_v18_dormant_pickem_tidak_tinggi(self):
        # Dengan ambang v18 0,085, bahkan laga pick'em (spread 0)
        # tidak tinggi — gerbang dormant (lihat test_ot_empiris).
        analisis = _analisis_pola_denver(margin=0.0)
        tinggi, ot, ambang = skip_awal.potensi_ot_tinggi(analisis, CFG)
        self.assertFalse(tinggi)
        self.assertEqual(ot, 0.0575)
        self.assertEqual(ambang, 0.085)

    def test_det_tidak_skip_via_ot(self):
        # KASUS WAJIB v18: DET@ATL (spread 2,0, ot sim 2,89%)
        # TIDAK di-skip via OT. Di v17, ot sim 2,89% >= 2,8%
        # memicu skip; di v18, p_ot empiris(2,0) = 0,0570 < 0,085.
        # Fixture ini laga normal (equilibrium kedua tiket ada,
        # bukan pola Denver) -> tidak ada pemicu sama sekali.
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
            margin=2.0,
        )
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertFalse(hasil["skip"])
        self.assertEqual(hasil["pemicu"], [])
        self.assertEqual(hasil["ot"]["p_ot_empiris"], 0.056950409501032494)
        self.assertEqual(hasil["ot"]["ot_probability"], 0.0289)
        self.assertEqual(hasil["ot"]["spread_points"], 2.0)

    def test_ot_tinggi_skip_dengan_alasan_cfg_rendah(self):
        # Jalur pemicu (ambang-diturunkan 0,05): laga normal +
        # spread 0 -> skip HANYA via ot_tinggi, alasan menyebut
        # peluang OT EMPIRIS + spread.
        analisis = _analisis(
            "PICK@EM_2026-11-22",
            224.0,
            5.0,
            _kaki("PICK@EM_2026-11-22", "insurance", 240.5, 0.99, 0.90, 82.0),
            _kaki("PICK@EM_2026-11-22", "main", 236.5, 0.99, 0.90, 78.0),
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
            margin=0.0,
        )
        hasil = skip_awal.evaluasi_skip_awal(analisis, _cfg_ambang_ot_rendah())
        self.assertTrue(hasil["skip"])
        self.assertEqual(hasil["pemicu"], ["ot_tinggi"])
        self.assertIn("overtime", hasil["alasan"])
        self.assertIn("5.75%", hasil["alasan"])
        self.assertIn("empiris", hasil["alasan"])

    def test_tanpa_margin_tidak_bisa_dinilai(self):
        # Tanpa distribusi margin (spread tidak ada), OT tidak
        # bisa dinilai — BUKAN bukti aman. ot sim yang ada (0,02)
        # tidak lagi dipakai sebagai pemicu.
        analisis = _analisis_pola_denver(ot=0.02, margin=None)
        tinggi, ot, ambang = skip_awal.potensi_ot_tinggi(analisis, CFG)
        self.assertIsNone(tinggi)
        self.assertIsNone(ot)
        self.assertEqual(ambang, 0.085)

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
        cfg["ot_seleksi"]["hard_skip_ot_prob"] = 1.5
        with self.assertRaises(config.ConfigError):
            skip_awal.potensi_ot_tinggi(_analisis_pola_denver(), cfg)
        cfg = copy.deepcopy(CFG)
        del cfg["ot_seleksi"]["hard_skip_ot_prob"]
        with self.assertRaises(config.ConfigError):
            skip_awal.potensi_ot_tinggi(_analisis_pola_denver(), cfg)
        cfg = copy.deepcopy(CFG)
        cfg["ot_seleksi"]["mode"] = "sim"
        with self.assertRaises(config.ConfigError):
            skip_awal.potensi_ot_tinggi(_analisis_pola_denver(), cfg)

    def test_pemicu_ganda_pola_dan_ot(self):
        # Fixture pola Denver + OT tinggi (ambang-diturunkan,
        # spread 0) -> kedua pemicu tercatat. v18.1: fixture
        # sudah memenuhi keempat syarat pola (acuan 252,5 @84,5¢
        # jup, EV -4,5%) tanpa manipulasi harga tambahan.
        analisis = _analisis_pola_denver(margin=0.0)
        hasil = skip_awal.evaluasi_skip_awal(analisis, _cfg_ambang_ot_rendah())
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
        # — garis acuan tidak thin dan bisa dibeli. v18.1: garis
        # acuan 252,5 @82¢, EV +1,8% (tidak kecil) — syarat (4)
        # kini SALAH (di v18 edge +0,95% < 3,5% membuat syarat (4)
        # benar — kelemahan edge datar yang diperbaiki EV). Hanya
        # artefak NYATA yang memicu pola; tes kasus wajib harus
        # memakai artefak nyata, bukan fixture ini. (Juga
        # membuktikan pola tidak memukul semua laga.)
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
        # v18.1: EV di acuan 252,5 (+1,8%) TIDAK kecil — syarat
        # (4) salah. Ini MEMPERBAIKI kelemahan jujur v18 (edge
        # +0,95% < 3,5% membuat syarat (4) benar di garis mahal);
        # pola tetap tidak cocok (syarat (3) dan (4) mati).
        self.assertFalse(syarat["ev_kecil"])
        self.assertFalse(hasil["pola_denver"]["cocok"])


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
        # Tanpa CDF/tangga tapi OT bisa dinilai (spread ada) ->
        # dievaluasi. Dengan ambang-diturunkan (0,05) + spread 0 ->
        # skip via (c). Tanpa CDF/tangga dan OT rendah -> dievaluasi
        # tapi tidak skip.
        dasar = {
            "format": "nba_analysis",
            "format_version": 1,
            "match_id": "OT@SAJA_2026-11-22",
            "status": "OK",
            "legs": [],
            "simulation": {
                "score_distribution": {
                    "total": {"median": 230.0},
                    "margin": {"median": 0.0},
                    "ot_probability": 0.03,
                },
                "markets": {},
            },
            "market": {"main_total_line": 231.5, "totals": []},
        }
        hasil = skip_awal.evaluasi_skip_awal(dasar, _cfg_ambang_ot_rendah())
        self.assertTrue(hasil["dievaluasi"])
        self.assertTrue(hasil["skip"])
        self.assertEqual(hasil["pemicu"], ["ot_tinggi"])
        dasar["simulation"]["score_distribution"]["margin"]["median"] = 15.0
        hasil = skip_awal.evaluasi_skip_awal(dasar, _cfg_ambang_ot_rendah())
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

    def test_den_live_tidak_di_skip_pola_v18_1(self):
        # v18.1 (MEMBALIK test_den_live_di_skip_pola_denver):
        # DEN@CHI live TIDAK lagi di-skip via pola Denver — hanya
        # syarat (1) yang benar: (2) salah (garis tahan banjir
        # 266,5 lolos cek_eksekusi: likuiditas $23-32 ribu +
        # spread 3-5¢ — flag thin lama vacuous karena semua garis
        # tangga artefak live bervolume None), (3) salah (acuan
        # U254,5 @82,5¢ lolos cek_eksekusi), (4) salah (EV acuan
        # -0,04% > -1%). KONFLIK dengan target tugas ("DEN wajib
        # tetap di-skip") — dilaporkan apa adanya, BUKAN ditutup
        # dengan retune ambang. DEN live tetap terblokir fungsional
        # via TUNGGU_LINEUP (Norman Powell Questionable).
        hasil = skip_awal.evaluasi_skip_awal(self.live["DEN@CHI_2026-11-22"], CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertFalse(hasil["skip"])
        self.assertEqual(hasil["pemicu"], [])
        pola = hasil["pola_denver"]
        self.assertFalse(pola["cocok"])
        self.assertEqual(
            pola["syarat"],
            {
                "flag_setan": True,
                "tidak_ada_tahan_banjir_nonthin": False,
                "garis_acuan_thin": False,
                "ev_kecil": False,
            },
        )
        acuan = pola["garis_acuan"]
        self.assertEqual(acuan["garis"], 254.5)
        self.assertAlmostEqual(acuan["p_normal"], 0.84326, places=4)
        self.assertAlmostEqual(acuan["p_setan_efektif"], 0.529406, places=4)
        self.assertAlmostEqual(acuan["ev"], -0.0004, places=3)

    def test_den_verif_tidak_di_skip_pola_tapi_veto_menyala(self):
        # v18.1 (MEMBALIK test_den_verif_di_skip_pola_denver):
        # DEN@CHI verif TIDAK di-skip via pola — tapi veto rim
        # protector MENYALA (Nic Claxton OUT) sehingga laga
        # terblokir di vonis (KUNING), bukan di skip_awal.
        hasil = skip_awal.evaluasi_skip_awal(self.verif["DEN@CHI_2026-11-22"], CFG)
        self.assertFalse(hasil["skip"])
        self.assertEqual(hasil["pemicu"], [])
        self.assertFalse(hasil["pola_denver"]["cocok"])
        veto = vonis_mod.evaluasi_veto(self.verif["DEN@CHI_2026-11-22"], CFG)
        self.assertTrue(veto["dievaluasi"])
        self.assertTrue(veto["menyala"])
        self.assertIn("Nic Claxton", [o["player"] for o in veto["pelindung_out"]])

    def test_den_ot_tidak_tinggi_kejujuran(self):
        # KEJUJURAN: DEN@CHI yang benar-benar masuk OT punya
        # ot_prob sim hanya 2,36% (live) / 2,13% (verif) — dan
        # p_ot EMPIRIS 4,93% (live, spread 8,0) / 4,30% (verif,
        # spread 11,0) — keduanya di bawah ambang 8,5%. Aturan OT
        # TIDAK menangkap Denver; di v18 Denver ditangkap
        # pola_denver, di v18.1 pola tidak lagi menangkapnya
        # (lihat test_den_live_tidak_di_skip_pola_v18_1).
        for analisis in (
            self.live["DEN@CHI_2026-11-22"],
            self.verif["DEN@CHI_2026-11-22"],
        ):
            tinggi, ot, _ = skip_awal.potensi_ot_tinggi(analisis, CFG)
            self.assertFalse(tinggi)
            self.assertLess(ot, 0.085)
        _, ot_live, _ = skip_awal.potensi_ot_tinggi(
            self.live["DEN@CHI_2026-11-22"], CFG
        )
        self.assertEqual(ot_live, 0.049309653310985156)
        _, ot_verif, _ = skip_awal.potensi_ot_tinggi(
            self.verif["DEN@CHI_2026-11-22"], CFG
        )
        self.assertEqual(ot_verif, 0.04300265719247792)

    def test_okc_verif_tidak_di_skip(self):
        # KONTROL NORMAL (kasus wajib 2): OKC@MIA verif TIDAK
        # di-skip — garis tahan banjir yang bisa dibeli ADA (5
        # garis) dan EV di garis acuan tidak kecil (+6,6%).
        hasil = skip_awal.evaluasi_skip_awal(self.verif["OKC@MIA_2026-11-22"], CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertFalse(hasil["skip"])
        self.assertEqual(hasil["pemicu"], [])
        syarat = hasil["pola_denver"]["syarat"]
        self.assertFalse(syarat["tidak_ada_tahan_banjir_nonthin"])
        self.assertFalse(syarat["ev_kecil"])

    def test_det_live_tidak_skip_via_ot(self):
        # KASUS WAJIB v18: DET@ATL live TIDAK di-skip — sama sekali.
        # Di v17, ot sim 2,89% >= 2,8% memicu skip via ot_tinggi
        # (satu-satunya pemicu OT di 10 baris); di v18, p_ot
        # empiris(2,0) = 0,0570 < 0,085, dan pola Denver pun tidak
        # cocok (ada garis tahan banjir tidak-tipis). OT sim 2,89%
        # tetap tercatat sebagai info.
        hasil = skip_awal.evaluasi_skip_awal(self.live["DET@ATL_2026-11-22"], CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertFalse(hasil["skip"])
        self.assertEqual(hasil["pemicu"], [])
        self.assertNotIn("ot_tinggi", hasil["pemicu"])
        self.assertAlmostEqual(hasil["ot"]["ot_probability"], 0.0289, places=4)
        self.assertAlmostEqual(
            hasil["ot"]["p_ot_empiris"], 0.056950409501032494, places=12
        )
        self.assertFalse(hasil["ot"]["tinggi"])

    def test_dal_dan_bos_live_tidak_di_skip(self):
        # v18.1: DAL@UTA + BOS@GSW live TIDAK di-skip — pola tidak
        # cocok (EV di garis acuan DAL +6,0% / BOS +8,2% >= -1%)
        # DAN equilibrium ADA di kedua tiket. Laga "bagus" yang
        # bisa dibeli tidak di-skip.
        for match_id in ("DAL@UTA_2026-11-22", "BOS@GSW_2026-11-22"):
            with self.subTest(match_id=match_id):
                hasil = skip_awal.evaluasi_skip_awal(self.live[match_id], CFG)
                self.assertFalse(hasil["skip"])
                self.assertEqual(hasil["pemicu"], [])
                self.assertFalse(hasil["pola_denver"]["cocok"])
                self.assertFalse(hasil["pola_denver"]["syarat"]["ev_kecil"])
                self.assertTrue(hasil["equilibrium"]["insurance"]["ada"])
                self.assertTrue(hasil["equilibrium"]["main"]["ada"])

    def test_nol_dari_sepuluh_baris_di_skip_v18_1(self):
        # Rekap v18.1 (MEMBALIK test_enam_dari_sepuluh_baris_di_skip):
        # 0/10 baris di-skip — TIDAK ADA pemicu sama sekali di slate
        # ini. v18: 6 di-skip via pola (DEN live+verif, OKC/ORL/IND
        # live, BOS verif); di v18.1 keenamnya lolos dari pola
        # (substitusi EV + cek_eksekusi + setan pemain). OT tetap
        # dormant (p_ot maks 0,057 < ambang 0,085).
        semua = [("live", m, a) for m, a in self.live.items()] + [
            ("verif", m, a) for m, a in self.verif.items()
        ]
        self.assertEqual(len(semua), 10)
        for sumber, match_id, analisis in semua:
            with self.subTest(sumber=sumber, match_id=match_id):
                hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
                self.assertNotIn("ot_tinggi", hasil["pemicu"])
                self.assertEqual(hasil["pemicu"], [])
                self.assertFalse(hasil["pola_denver"]["cocok"])


if __name__ == "__main__":
    unittest.main()
