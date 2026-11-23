"""Tes Patch #1 v18.1 — skip_awal pola Denver (engine/skip_awal.py).

Perubahan v18.1 (REFERENSI-PATCH-V18-1-GEMINI.md §1 Patch #1):
(a) syarat (4) edge < 3,5% -> EV < -1% (max_ev_for_weak_flag);
(b) "non-thin" -> lolos gate eksekusi (cek_eksekusi), BUKAN flag
    thin volume kumulatif — di syarat (2) dan (3);
(c) flag setan memakai setan per pemain v18 (total_setan_pemain -
    median) bila blok setan_pemain ada, fallback setan generik +
    catatan bila tidak ada;
(d) PAGAR ANTI-REDUNDANSI: bila laga tidak kena Hard Veto DAN punya
    >= 1 garis lolos 6 gate Equilibrium Asuransi, pola hanya boleh
    menyala bila ketiganya benar: (1) garis Asuransi rapuh vs
    setan pemain, (2) total pasar >= 232,0, (3) tidak ada garis
    valid yang tahan banjir maupun setan.

Tes artefak nyata memakai out/analysis_live_2026-11-22.json +
out/analysis_verif_tahap4_2026-11-22.json (file runtime,
gitignored) dan di-skip bila file tidak ada.
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
    mengubahnya eksplisit.
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
    """Artefak nba_analysis minimal dengan CDF normal penuh + tangga."""
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


def _analisis_pola_denver_v18_1(match_id="DEN@CHI_2026-11-22"):
    """Fixture pola Denver v18.1: keempat syarat benar (logika baru).

    Median 233, sigma 19,2. Garis acuan 252,5 @84,5¢ jup:
    P normal 84,5%, P setan (generik, tanpa blok setan_pemain)
    53,0%, p_final ~0,807 -> EV ~-4,5% (< -1%). Acuan +
    garis tahan banjir 264,5-270,5 gagal gate eksekusi
    (likuiditas $5); flag thin dipertahankan (bahan asersi
    cari_garis_acuan lama). Equilibrium ADA di kedua tiket
    (U262,5) — skip hanya via pola (b). Pagar TIDAK berlaku:
    veto tidak bisa dievaluasi (tanpa data cedera).
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
        ot=0.02,
    )


def _analisis_pagar(total_setan_pemain=260.0, match_id="PAG@AR_2026-11-22"):
    """Fixture pagar: pola cocok + pagar BERLAKU + ketiganya benar.

    Median 240, sigma 19,2, pasar 241,5. Garis acuan 258,5
    @88,5¢ jup (p_final ~0,826 -> EV ~-6,7%) gagal eksekusi
    (likuiditas $5); satu-satunya garis lolos 6 gate Asuransi
    adalah 260,5 @84,5¢ (EQ) — garis di atasnya gagal eksekusi.
    Setan per pemain total 260,0 (geser 20,0): P setan di EQ
    51,0% < 55% (pagar (1) benar); pasar 241,5 >= 232 (pagar
    (2) benar); 260,5 tahan banjir tapi TIDAK tahan setan
    (51,0% < 55%) dan tidak ada garis valid lain (pagar (3)
    benar). Blok veto disuntik: dievaluasi + tidak menyala.
    Hasil: pola BERDIRI, skip via pola_denver.
    """
    tangga = _tangga(
        [
            (250.5, 70.0, 500.0, False),
            (252.5, 72.0, 500.0, False),
            (254.5, 74.0, 500.0, False),
            (256.5, 76.0, 500.0, False),
            (258.5, 88.0, 500.0, False, {"liquidity": 5.0}),
            (260.5, 84.0, 500.0, False),
            (262.5, 86.0, 500.0, False, {"liquidity": 5.0}),
            (264.5, 88.0, 500.0, False, {"liquidity": 5.0}),
            (266.5, 90.0, 500.0, False, {"liquidity": 5.0}),
            (268.5, 92.0, 500.0, False, {"liquidity": 5.0}),
            (270.5, 94.0, 500.0, False, {"liquidity": 5.0}),
        ]
    )
    analisis = _analisis(
        match_id,
        240.0,
        19.2,
        _kaki(match_id, "insurance", 260.5, 0.857, 0.85, 84.0),
        _kaki(match_id, "main", 258.5, 0.832, 0.824, 80.0),
        tangga,
        ot=0.02,
    )
    analisis["setan_pemain"] = {"total_setan_pemain": total_setan_pemain}
    analisis["veto"] = {"dievaluasi": True, "menyala": False}
    return analisis


def _muat_artefak(path):
    """Analisis per laga dari satu file artefak (dict match_id -> dict)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    hasil = {}
    for match in data.get("matches") or []:
        analysis = match.get("nba_analysis") or {}
        if analysis.get("match_id"):
            hasil[analysis["match_id"]] = analysis
    return hasil


def _cfg_ubah(*kunci_nilai):
    """CFG + perubahan (kunci-tuple, nilai) — mis. (\"skip_awal\",
    \"pola_denver\", \"use_ev_instead_of_flat_edge\"), False."""
    cfg = copy.deepcopy(CFG)
    for kunci, nilai in kunci_nilai:
        node = cfg
        for bagian in kunci[:-1]:
            node = node[bagian]
        node[kunci[-1]] = nilai
    return cfg


class TestSyarat4EV(unittest.TestCase):
    """Syarat (4) v18.1: EV < -1%, BUKAN edge < 3,5%."""

    def test_keempat_syarat_benar_skip_via_ev(self):
        hasil = skip_awal.evaluasi_skip_awal(_analisis_pola_denver_v18_1(), CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertTrue(hasil["skip"])
        self.assertEqual(hasil["pemicu"], ["pola_denver"])
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
        self.assertNotIn("edge_kecil", pola["syarat"])
        acuan = pola["garis_acuan"]
        self.assertEqual(acuan["garis"], 252.5)
        self.assertLess(acuan["ev"], -0.01)
        self.assertAlmostEqual(acuan["ev"], -0.045, places=2)
        self.assertEqual(acuan["n_tahan_banjir"], 4)
        self.assertEqual(acuan["n_tahan_banjir_nonthin"], 0)

    def test_ev_besar_mematikan_syarat4(self):
        # Harga acuan 252,5 diturunkan ke 60¢ -> EV +33% -> syarat
        # (4) mati -> pola tidak cocok. (Di v18, manipulasi yang
        # sama mematikan syarat edge; kini yang dinilai EV.)
        analisis = _analisis_pola_denver_v18_1()
        for entri in analisis["market"]["totals"]:
            if entri["line"] == 252.5:
                entri["price_cents"] = 60.0
                entri["jup_estimated_cents"] = 60.5
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertFalse(hasil["pola_denver"]["syarat"]["ev_kecil"])
        self.assertFalse(hasil["pola_denver"]["cocok"])
        self.assertFalse(hasil["skip"])

    def test_ev_di_atas_ambang_tapi_edge_kecil_tidak_memicu(self):
        # PEMBEDA EV vs edge: acuan 252,5 @80,5¢ jup -> edge
        # +0,2% (< 3,5%, syarat v18 BENAR) tapi EV +0,2% (> -1%,
        # syarat v18.1 SALAH) -> pola tidak cocok. Ini memperbaiki
        # kelemahan jujur v18 (edge datar hampir selalu benar di
        # garis mahal).
        analisis = _analisis_pola_denver_v18_1()
        for entri in analisis["market"]["totals"]:
            if entri["line"] == 252.5:
                entri["price_cents"] = 80.0
                entri["jup_estimated_cents"] = 80.5
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        pola = hasil["pola_denver"]
        self.assertLess(pola["garis_acuan"]["edge"], 0.035)
        self.assertGreater(pola["garis_acuan"]["ev"], -0.01)
        self.assertFalse(pola["syarat"]["ev_kecil"])
        self.assertFalse(pola["cocok"])
        self.assertFalse(hasil["skip"])

    def test_mode_legacy_edge(self):
        # Reversibilitas satu baris config: flag EV false -> syarat
        # (4) kembali ke edge_kecil (kunci edge_kecil_pct dibaca).
        cfg = _cfg_ubah(
            (
                ("skip_awal", "pola_denver", "use_ev_instead_of_flat_edge"),
                False,
            )
        )
        hasil = skip_awal.evaluasi_skip_awal(_analisis_pola_denver_v18_1(), cfg)
        pola = hasil["pola_denver"]
        self.assertIn("edge_kecil", pola["syarat"])
        self.assertNotIn("ev_kecil", pola["syarat"])
        self.assertTrue(pola["syarat"]["edge_kecil"])  # edge -3,8%
        self.assertTrue(pola["cocok"])

    def test_kunci_ev_hilang_config_error(self):
        cfg = copy.deepcopy(CFG)
        del cfg["skip_awal"]["pola_denver"]["max_ev_for_weak_flag"]
        with self.assertRaises(config.ConfigError):
            skip_awal.evaluasi_skip_awal(_analisis_pola_denver_v18_1(), cfg)
        cfg = copy.deepcopy(CFG)
        del cfg["skip_awal"]["pola_denver"]["use_ev_instead_of_flat_edge"]
        with self.assertRaises(config.ConfigError):
            skip_awal.evaluasi_skip_awal(_analisis_pola_denver_v18_1(), cfg)


class TestCekEksekusi(unittest.TestCase):
    """Syarat (2)/(3) v18.1: cek_eksekusi, BUKAN flag thin."""

    def test_syarat2_mati_garis_tahan_bisa_dibeli(self):
        # Garis tahan banjir 266,5 dipulihkan likuiditasnya
        # ($30.000) -> bisa dibeli -> syarat (2) mati.
        analisis = _analisis_pola_denver_v18_1()
        for entri in analisis["market"]["totals"]:
            if entri["line"] == 266.5:
                entri["liquidity"] = 30000.0
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertFalse(
            hasil["pola_denver"]["syarat"]["tidak_ada_tahan_banjir_nonthin"]
        )
        self.assertFalse(hasil["pola_denver"]["cocok"])
        self.assertFalse(hasil["skip"])

    def test_syarat2_flag_thin_saja_tidak_cukup(self):
        # PEMBEDA v18.1: garis tahan banjir 266,5 dibuat TIDAK
        # thin (flag + volume) tapi likuiditas TETAP $5 (gagal
        # eksekusi) -> syarat (2) TETAP benar. Flag thin diabaikan;
        # yang dinilai gate eksekusi. (Di v18, manipulasi ini
        # mematikan syarat (2).)
        analisis = _analisis_pola_denver_v18_1()
        for entri in analisis["market"]["totals"]:
            if entri["line"] == 266.5:
                entri["thin"] = False
                entri["volume_usd"] = 500.0
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertTrue(
            hasil["pola_denver"]["syarat"]["tidak_ada_tahan_banjir_nonthin"]
        )
        self.assertTrue(hasil["pola_denver"]["cocok"])

    def test_syarat3_mati_acuan_bisa_dibeli(self):
        # Likuiditas acuan dipulihkan -> lolos eksekusi -> syarat
        # (3) mati (meski flag thin tetap True).
        analisis = _analisis_pola_denver_v18_1()
        for entri in analisis["market"]["totals"]:
            if entri["line"] == 252.5:
                entri["liquidity"] = 30000.0
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertFalse(hasil["pola_denver"]["syarat"]["garis_acuan_thin"])
        self.assertFalse(hasil["pola_denver"]["cocok"])
        self.assertFalse(hasil["skip"])

    def test_syarat3_acuan_ask_99_gagal_eksekusi(self):
        # Acuan likuiditas $30.000 + flag TIDAK thin, tapi ask 99¢
        # (sentinel "tidak ada ask") -> gagal eksekusi -> syarat
        # (3) benar. (Di v18, flag tidak-thin membuat syarat (3)
        # salah — tes ini membedakan logika baru dari lama.)
        analisis = _analisis_pola_denver_v18_1()
        for entri in analisis["market"]["totals"]:
            if entri["line"] == 252.5:
                entri["liquidity"] = 30000.0
                entri["thin"] = False
                entri["volume_usd"] = 500.0
                entri["ask_cents"] = 99.0
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertTrue(hasil["pola_denver"]["syarat"]["garis_acuan_thin"])
        self.assertTrue(hasil["pola_denver"]["cocok"])

    def test_mode_legacy_thin(self):
        # Reversibilitas: flag cek_eksekusi false -> syarat (2)/(3)
        # kembali ke flag thin. Acuan dibuat TIDAK thin tapi
        # likuiditas tetap $5: legacy -> syarat (3) SALAH (flag
        # bilang tebal); v18.1 -> syarat (3) BENAR (eksekusi gagal).
        analisis = _analisis_pola_denver_v18_1()
        for entri in analisis["market"]["totals"]:
            if entri["line"] == 252.5:
                entri["thin"] = False
                entri["volume_usd"] = 500.0
        cfg = _cfg_ubah(
            (
                ("skip_awal", "pola_denver", "use_cek_eksekusi_for_thin"),
                False,
            )
        )
        hasil = skip_awal.evaluasi_skip_awal(analisis, cfg)
        self.assertFalse(hasil["pola_denver"]["syarat"]["garis_acuan_thin"])
        self.assertFalse(hasil["pola_denver"]["cocok"])
        hasil_baru = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertTrue(hasil_baru["pola_denver"]["syarat"]["garis_acuan_thin"])
        self.assertTrue(hasil_baru["pola_denver"]["cocok"])


class TestSetanPemain(unittest.TestCase):
    """Syarat (1) v18.1: setan per pemain, fallback generik."""

    def test_setan_pemain_memadamkan_flag(self):
        # PEMBEDA: total setan pemain 234,0 (geser 1,0 dari median
        # 233) -> P setan di acuan 83,2% >= 82% -> flag MATI,
        # padahal setan generik (geser 18,07) memberi 53,0% (flag
        # hidup). Pola tidak cocok.
        analisis = _analisis_pola_denver_v18_1()
        analisis["setan_pemain"] = {"total_setan_pemain": 234.0}
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        pola = hasil["pola_denver"]
        self.assertFalse(pola["syarat"]["flag_setan"])
        self.assertEqual(pola["detail"]["setan_sumber"], "pemain")
        self.assertAlmostEqual(pola["garis_acuan"]["p_setan_efektif"], 0.832, places=2)
        self.assertFalse(pola["cocok"])
        self.assertFalse(hasil["skip"])

    def test_setan_pemain_flag_hidup(self):
        # Total setan pemain 260,0 (geser 27,0) -> P setan di
        # acuan 34,8% < 82% -> flag hidup, sumber "pemain".
        analisis = _analisis_pola_denver_v18_1()
        analisis["setan_pemain"] = {"total_setan_pemain": 260.0}
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        pola = hasil["pola_denver"]
        self.assertTrue(pola["syarat"]["flag_setan"])
        self.assertEqual(pola["detail"]["setan_sumber"], "pemain")
        self.assertAlmostEqual(pola["garis_acuan"]["p_setan_efektif"], 0.348, places=2)
        self.assertTrue(pola["cocok"])

    def test_tanpa_blok_setan_fallback_generik(self):
        # Artefak lama tanpa blok setan_pemain -> fallback setan
        # generik + dicatat, TIDAK crash.
        hasil = skip_awal.evaluasi_skip_awal(_analisis_pola_denver_v18_1(), CFG)
        pola = hasil["pola_denver"]
        self.assertEqual(pola["detail"]["setan_sumber"], "generik")
        self.assertIsNotNone(pola["detail"]["setan_fallback"])
        self.assertAlmostEqual(pola["garis_acuan"]["p_setan_efektif"], 0.53, places=2)
        self.assertTrue(pola["syarat"]["flag_setan"])

    def test_blok_setan_rusak_fallback_generik(self):
        # Blok ada tapi total bukan angka -> fallback generik.
        analisis = _analisis_pola_denver_v18_1()
        analisis["setan_pemain"] = {"total_setan_pemain": "bukan-angka"}
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        pola = hasil["pola_denver"]
        self.assertEqual(pola["detail"]["setan_sumber"], "generik")
        self.assertTrue(pola["syarat"]["flag_setan"])
        self.assertTrue(pola["cocok"])

    def test_flag_setan_pemain_nonaktif(self):
        # Flag v18.1 false -> setan generik dipakai meski blok ada.
        analisis = _analisis_pola_denver_v18_1()
        analisis["setan_pemain"] = {"total_setan_pemain": 234.0}
        cfg = _cfg_ubah(
            (
                ("skip_awal", "pola_denver", "use_demon_per_player_v18"),
                False,
            )
        )
        hasil = skip_awal.evaluasi_skip_awal(analisis, cfg)
        pola = hasil["pola_denver"]
        self.assertEqual(pola["detail"]["setan_sumber"], "generik")
        self.assertTrue(pola["syarat"]["flag_setan"])
        self.assertTrue(pola["cocok"])

    def test_setan_pemain_disabled_di_config(self):
        # Kill-switch setan_pemain.enabled false -> generik dipakai
        # meski blok ada (cermin stress.skenario_panas).
        analisis = _analisis_pola_denver_v18_1()
        analisis["setan_pemain"] = {"total_setan_pemain": 234.0}
        cfg = _cfg_ubah((("setan_pemain", "enabled"), False))
        hasil = skip_awal.evaluasi_skip_awal(analisis, cfg)
        pola = hasil["pola_denver"]
        self.assertEqual(pola["detail"]["setan_sumber"], "generik")
        self.assertTrue(pola["syarat"]["flag_setan"])


class TestPagarAntiRedundansi(unittest.TestCase):
    """Pagar v18.1: pola hanya menyala bila 3 syarat pagar benar."""

    def test_pagar_berlaku_ketiga_syarat_benar_pola_berdiri(self):
        hasil = skip_awal.evaluasi_skip_awal(_analisis_pagar(), CFG)
        pola = hasil["pola_denver"]
        self.assertTrue(pola["cocok_tanpa_pagar"])
        self.assertTrue(pola["cocok"])
        pagar = pola["pagar"]
        self.assertTrue(pagar["berlaku"])
        self.assertFalse(pagar["memblokir"])
        self.assertEqual(
            pagar["syarat"],
            {
                "garis_asuransi_rapuh_setan": True,
                "total_pasar_tinggi": True,
                "tidak_ada_garis_valid_tahan": True,
            },
        )
        self.assertEqual(pagar["garis_asuransi"], 260.5)
        self.assertTrue(hasil["skip"])
        self.assertEqual(hasil["pemicu"], ["pola_denver"])

    def test_pagar_memblokir_garis_asuransi_tidak_rapuh(self):
        # Fixture pola v18.1 + veto disuntik (tidak menyala) +
        # garis lolos gate ADA (EQ 262,5): pagar BERLAKU, tapi
        # garis Asuransi TIDAK rapuh vs setan (P setan di 262,5
        # 72,3% >= 55%; median setan 251,07 < 262,5) DAN ada garis
        # valid yang tahan banjir+setan -> pagar MEMBLOKIR pola.
        analisis = _analisis_pola_denver_v18_1()
        analisis["veto"] = {"dievaluasi": True, "menyala": False}
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        pola = hasil["pola_denver"]
        self.assertTrue(pola["cocok_tanpa_pagar"])
        self.assertFalse(pola["cocok"])
        pagar = pola["pagar"]
        self.assertTrue(pagar["berlaku"])
        self.assertTrue(pagar["memblokir"])
        self.assertFalse(pagar["syarat"]["garis_asuransi_rapuh_setan"])
        self.assertTrue(pagar["syarat"]["total_pasar_tinggi"])
        self.assertFalse(pagar["syarat"]["tidak_ada_garis_valid_tahan"])
        self.assertFalse(hasil["skip"])
        self.assertEqual(hasil["pemicu"], [])

    def test_pagar_tidak_berlaku_veto_menyala(self):
        # Veto menyala -> pagar TIDAK berlaku -> pola berdiri.
        analisis = _analisis_pagar()
        analisis["veto"] = {"dievaluasi": True, "menyala": True}
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        pola = hasil["pola_denver"]
        self.assertFalse(pola["pagar"]["berlaku"])
        self.assertTrue(pola["cocok"])
        self.assertTrue(hasil["skip"])

    def test_pagar_tidak_berlaku_veto_tidak_diketahui(self):
        # Veto tidak dievaluasi -> tidak bisa dipastikan "tidak
        # kena veto" -> pagar TIDAK berlaku -> pola berdiri.
        analisis = _analisis_pagar()
        analisis["veto"] = {"dievaluasi": False, "menyala": False}
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        self.assertFalse(hasil["pola_denver"]["pagar"]["berlaku"])
        self.assertTrue(hasil["pola_denver"]["cocok"])
        # Tanpa blok veto + tanpa data cedera (fixture pola):
        # evaluasi veto live gagal -> pagar juga tidak berlaku.
        hasil2 = skip_awal.evaluasi_skip_awal(_analisis_pola_denver_v18_1(), CFG)
        self.assertFalse(hasil2["pola_denver"]["pagar"]["berlaku"])
        self.assertTrue(hasil2["pola_denver"]["cocok"])

    def test_pagar_tidak_berlaku_tanpa_garis_lolos_gate(self):
        # Semua garis gagal eksekusi -> tidak ada garis lolos 6
        # gate -> pagar TIDAK berlaku -> pola berdiri (pemicu (a)
        # ikut menyala karena equilibrium tidak ada).
        analisis = _analisis_pagar()
        for entri in analisis["market"]["totals"]:
            entri["liquidity"] = 5.0
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        pola = hasil["pola_denver"]
        self.assertFalse(pola["pagar"]["berlaku"])
        self.assertTrue(pola["cocok"])
        self.assertIn("pola_denver", hasil["pemicu"])
        self.assertIn("tidak_ada_equilibrium", hasil["pemicu"])

    def test_pagar_syarat2_total_pasar_rendah_memblokir(self):
        # Ambang total pasar dinaikkan ke 250,0 (cfg) -> pasar
        # 241,5 < 250 -> syarat pagar (2) SALAH (sendirian) ->
        # pagar memblokir.
        cfg = _cfg_ubah(
            (
                ("skip_awal", "pola_denver", "min_market_total_for_pattern"),
                250.0,
            )
        )
        hasil = skip_awal.evaluasi_skip_awal(_analisis_pagar(), cfg)
        pola = hasil["pola_denver"]
        self.assertTrue(pola["pagar"]["berlaku"])
        self.assertTrue(pola["pagar"]["memblokir"])
        self.assertTrue(pola["pagar"]["syarat"]["garis_asuransi_rapuh_setan"])
        self.assertFalse(pola["pagar"]["syarat"]["total_pasar_tinggi"])
        self.assertTrue(pola["pagar"]["syarat"]["tidak_ada_garis_valid_tahan"])
        self.assertFalse(pola["cocok"])
        self.assertFalse(hasil["skip"])

    def test_pagar_syarat1_ambang_setan_rendah_memblokir(self):
        # Ambang kerapuhan setan diturunkan ke 0,10 (cfg) -> P
        # setan di EQ 51,0% >= 10% DAN median setan 260,0 < 260,5
        # -> syarat pagar (1) SALAH -> pagar memblokir. (Ambang
        # yang sama juga membuat 260,5 "tahan setan" sehingga
        # syarat (3) ikut salah — dicatat, bukan disembunyikan.)
        cfg = _cfg_ubah(
            (
                ("skip_awal", "pola_denver", "demon_p_fragile_threshold"),
                0.10,
            )
        )
        hasil = skip_awal.evaluasi_skip_awal(_analisis_pagar(), cfg)
        pola = hasil["pola_denver"]
        self.assertTrue(pola["pagar"]["berlaku"])
        self.assertTrue(pola["pagar"]["memblokir"])
        self.assertFalse(pola["pagar"]["syarat"]["garis_asuransi_rapuh_setan"])
        self.assertFalse(pola["pagar"]["syarat"]["tidak_ada_garis_valid_tahan"])
        self.assertFalse(pola["cocok"])

    def test_pagar_syarat3_garis_valid_tahan_memblokir(self):
        # Garis 264,5 dibuat bisa dibeli @78,5¢ jup (di bawah
        # lantai 80¢ sehingga BUKAN EQ, tapi valid untuk pagar:
        # eksekusi lolos + EV +14%): tahan banjir (79,8%/73,4%)
        # DAN tahan setan (59,3% >= 55%) -> syarat pagar (3)
        # SALAH (sendirian) -> pagar memblokir. Pola sendiri
        # tetap cocok (264,5 bukan tahan-banjir syarat (2):
        # P banjir terburuk 73,4% < 82%).
        analisis = _analisis_pagar()
        for entri in analisis["market"]["totals"]:
            if entri["line"] == 264.5:
                entri["price_cents"] = 78.0
                entri["jup_estimated_cents"] = 78.5
                entri["bid_cents"] = 77.0
                entri["ask_cents"] = 78.5
                entri["liquidity"] = 30000.0
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        pola = hasil["pola_denver"]
        self.assertTrue(pola["cocok_tanpa_pagar"])
        self.assertTrue(pola["pagar"]["berlaku"])
        self.assertTrue(pola["pagar"]["memblokir"])
        self.assertTrue(pola["pagar"]["syarat"]["garis_asuransi_rapuh_setan"])
        self.assertTrue(pola["pagar"]["syarat"]["total_pasar_tinggi"])
        self.assertFalse(pola["pagar"]["syarat"]["tidak_ada_garis_valid_tahan"])
        self.assertFalse(pola["cocok"])
        self.assertFalse(hasil["skip"])

    def test_pagar_veto_live_tanpa_blok(self):
        # Tanpa blok veto di artefak, pagar mengevaluasi veto
        # LANGSUNG via vonis.evaluasi_veto: IND@NYK terpetakan
        # (tier fallback), tidak ada rim protector OUT -> veto
        # dievaluasi + tidak menyala -> pagar berlaku + pola
        # berdiri (ketiga syarat pagar benar).
        analisis = _analisis_pagar(match_id="IND@NYK_2026-11-22")
        del analisis["veto"]
        analisis["injuries"] = {"entries": []}
        analisis["inputs"] = {"away": {"players": []}, "home": {"players": []}}
        hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
        pola = hasil["pola_denver"]
        self.assertTrue(pola["pagar"]["berlaku"])
        self.assertFalse(pola["pagar"]["memblokir"])
        self.assertTrue(pola["cocok"])
        self.assertTrue(hasil["skip"])


@unittest.skipUnless(
    ARTEFAK_LIVE.exists() and ARTEFAK_VERIF.exists(),
    "artefak out/analysis_live_2026-11-22.json / "
    "out/analysis_verif_tahap4_2026-11-22.json tidak ada (runtime)",
)
class TestArtefakNyataV18_1(unittest.TestCase):
    """Target Patch #1 di artefak nyata 22 Nov (10 baris).

    HASIL UKUR (2026-11-23, substitusi harfiah spek): pola
    Denver menyala 0/10 — termasuk DEN@CHI live, yang TIDAK
    lagi di-skip via pola (S2/S3/S4 mati: semua garis tangga
    artefak live lolos cek_eksekusi karena likuiditas $23-32
    ribu + spread 3-5¢, dan EV acuan ~0% > -1%). Ini KONFLIK
    dengan target tugas ("DEN@CHI wajib tetap di-skip") —
    dilaporkan apa adanya ke koordinator, BUKAN ditutup-tutupi
    dengan retune ambang. DEN live tetap terblokir fungsional
    via TUNGGU_LINEUP (Norman Powell Questionable); DEN verif
    terblokir veto (Claxton OUT).
    """

    @classmethod
    def setUpClass(cls):
        cls.live = _muat_artefak(ARTEFAK_LIVE)
        cls.verif = _muat_artefak(ARTEFAK_VERIF)

    def test_den_live_tidak_di_skip_pola_denver_v18_1(self):
        # KONFLIK TARGET (lihat docstring kelas): DEN live lolos
        # dari pola — S1 benar, S2/S3/S4 salah.
        hasil = skip_awal.evaluasi_skip_awal(self.live["DEN@CHI_2026-11-22"], CFG)
        self.assertTrue(hasil["dievaluasi"])
        self.assertFalse(hasil["skip"])
        self.assertEqual(hasil["pemicu"], [])
        pola = hasil["pola_denver"]
        self.assertTrue(pola["dievaluasi"])
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

    def test_den_verif_tidak_di_skip_pola_tapi_veto_menyala(self):
        # DEN verif: pola tidak cocok, TAPI veto rim protector
        # MENYALA (Nic Claxton OUT) -> terblokir di vonis (KUNING),
        # bukan di skip_awal.
        hasil = skip_awal.evaluasi_skip_awal(self.verif["DEN@CHI_2026-11-22"], CFG)
        self.assertFalse(hasil["skip"])
        self.assertEqual(hasil["pemicu"], [])
        self.assertFalse(hasil["pola_denver"]["cocok"])
        veto = vonis_mod.evaluasi_veto(self.verif["DEN@CHI_2026-11-22"], CFG)
        self.assertTrue(veto["dievaluasi"])
        self.assertTrue(veto["menyala"])
        self.assertIn("Nic Claxton", [o["player"] for o in veto["pelindung_out"]])

    def test_okc_orl_ind_live_tidak_di_skip_pola(self):
        # TARGET TERCAPAI: ketiga laga ini TIDAK lagi kena skip
        # pola Denver (di v18 ketiganya di-skip via pola).
        for match_id, syarat_benar in (
            (
                "OKC@MIA_2026-11-22",
                {"flag_setan", "tidak_ada_tahan_banjir_nonthin"},
            ),
            (
                "ORL@WAS_2026-11-22",
                {"flag_setan", "tidak_ada_tahan_banjir_nonthin", "ev_kecil"},
            ),
            ("IND@NYK_2026-11-22", {"flag_setan"}),
        ):
            with self.subTest(match_id=match_id):
                hasil = skip_awal.evaluasi_skip_awal(self.live[match_id], CFG)
                self.assertFalse(hasil["skip"])
                self.assertEqual(hasil["pemicu"], [])
                pola = hasil["pola_denver"]
                self.assertFalse(pola["cocok"])
                benar = {k for k, v in pola["syarat"].items() if v}
                self.assertEqual(benar, syarat_benar)

    def test_bos_verif_tidak_di_skip_v18_1(self):
        # BOS verif di-skip via pola di v18; di v18.1 lolos.
        hasil = skip_awal.evaluasi_skip_awal(self.verif["BOS@GSW_2026-11-22"], CFG)
        self.assertFalse(hasil["skip"])
        self.assertEqual(hasil["pemicu"], [])
        self.assertFalse(hasil["pola_denver"]["cocok"])

    def test_nol_dari_sepuluh_baris_di_skip_pola(self):
        # Rekap v18.1: 0/10 baris di-skip via pola Denver (v18:
        # 6/10). Tidak ada pemicu sama sekali di slate ini.
        semua = [("live", m, a) for m, a in self.live.items()] + [
            ("verif", m, a) for m, a in self.verif.items()
        ]
        self.assertEqual(len(semua), 10)
        for sumber, match_id, analisis in semua:
            with self.subTest(sumber=sumber, match_id=match_id):
                hasil = skip_awal.evaluasi_skip_awal(analisis, CFG)
                self.assertEqual(hasil["pemicu"], [])
                self.assertFalse(hasil["pola_denver"]["cocok"])


if __name__ == "__main__":
    unittest.main()
