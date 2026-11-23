"""Tes Patch #2a v18.1: equilibrium mengembalikan SEMUA garis valid Asuransi.

Perangkap Plafon 88,5¢ (REFERENSI-PATCH-V18-1-GEMINI.md §1 Patch #2):
safety-first dalam band 80–89¢ SELALU memetik garis plafon (P_final
monoton naik terhadap harga) — di T2 v18 ketiga kaki Asuransi terkunci
di 88,5¢ sehingga pengali maks hanya x1,36. Perbaikannya: equilibrium
mengembalikan seluruh garis valid (``garis_valid_asuransi``) supaya
komposer bisa memilih kombinasi optimal lintas garis — TANPA
melonggarkan satu pun gate.

Kontrak ``garis_valid_asuransi(analysis, cfg, ktx=None)``:
- Mengembalikan daftar entri garis DALAM band Asuransi (80–89¢, dari
  config tickets.insurance.preferred_price_band) yang lolos 100% gate
  Asuransi v18 (p_final >= 0,82, p_market >= 0,80, banjir 3P >= 70%,
  banjir FT >= 65%, EV >= -1%, cek_eksekusi lolos) — dibangun di atas
  ``nilai_semua_garis`` (tidak ada duplikasi logika gate).
- Tiap entri memuat minimal: garis, harga_venue_cents, p_final,
  p_market, ev_pct, p_banjir_3p, p_banjir_ft.
- [] bila dihitung tapi tidak ada garis valid; None bila konteks tidak
  bisa disiapkan (tanpa CDF / tangga / jangkar — sama seperti
  ``nilai_semua_garis``).
- ``cari_equilibrium`` TIDAK berubah perilakunya: garis plafon
  safety-first tetap disimpan sebagai default_eq untuk laporan
  individu (backward compatible).

Fixture: median 224, sigma 5, jangkar ins U240,5 p_market 0,90,
tangga 232,5–250,5 (pola yang sama dengan test_equilibrium.py).
Garis yang lolos semua gate v18 (dihitung mesin, diverifikasi
tangan di skrip scratch): 238,5–250,5; dalam band 80–89¢:
238,5 / 240,5 / 242,5 / 244,5 / 246,5 (harga venue 80,5–88,5¢).
Default safety-first tetap U246,5 @88,5¢ — itulah perangkapnya.
"""

from __future__ import annotations

import copy
import math
import unittest

import config
from engine import equilibrium

CFG = config.load_playstyle()


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

    Harga jup.ag = harga Polymarket + 0,5¢; kuotasi hidup
    (bid harga-1 / ask harga+0,5, spread 1,5¢) + likuiditas Gamma
    $30.000 — garis fixture lolos gate eksekusi v18.
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


def _kaki(match_id, ticket, line, p_model, p_market, harga):
    """Satu kaki artefak nba_analysis (bentuk _rakit_kaki)."""
    p_final = round(0.3 * p_model + 0.7 * p_market, 3)
    ev_pct = round((p_final * (100.0 / harga) - 1.0) * 100.0, 2)
    return {
        "leg_id": f"{match_id}:total_under_{line:g}:{ticket}",
        "market_type": "total_under",
        "line": line,
        "p_model": p_model,
        "p_market": p_market,
        "comparison_source": "kalshi",
        "p_final": p_final,
        "price_cents": harga,
        "jup_estimated_cents": harga,
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


def _analisis(match_id, median, sigma, tangga):
    """Artefak nba_analysis minimal dengan CDF normal penuh + tangga."""
    return {
        "format": "nba_analysis",
        "format_version": 1,
        "match_id": match_id,
        "status": "OK",
        "legs": [
            _kaki(match_id, "insurance", 240.5, 0.99, 0.90, 82.0),
            _kaki(match_id, "main", 236.5, 0.99, 0.90, 78.0),
        ],
        "simulation": {
            "score_distribution": {"total": {"median": median}},
            "markets": _cdf_normal(median, sigma, median - 30, median + 45),
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


def _analisis_224(match_id="DET@ATL_2026-11-22", sigma=5.0):
    """Fixture median 224 (jangkar ins U240,5 p_market 0,90)."""
    return _analisis(match_id, 224.0, sigma, _tangga_224())


class TestGarisValidAsuransi(unittest.TestCase):
    """garis_valid_asuransi mengembalikan SEMUA garis lolos dalam band."""

    def test_semua_garis_lolos_dalam_band(self):
        # 5 garis lolos semua gate v18 DALAM band 80–89¢ (harga venue
        # 80,5–88,5¢) — bukan hanya plafon 88,5¢.
        valid = equilibrium.garis_valid_asuransi(_analisis_224(), CFG)
        self.assertIsNotNone(valid)
        self.assertEqual(
            [e["garis"] for e in valid],
            [238.5, 240.5, 242.5, 244.5, 246.5],
        )
        self.assertEqual(
            [e["harga_venue_cents"] for e in valid],
            [80.5, 82.5, 84.5, 86.5, 88.5],
        )

    def test_entri_memuat_kunci_wajib_dan_nilai_benar(self):
        valid = equilibrium.garis_valid_asuransi(_analisis_224(), CFG)
        wajib = (
            "garis",
            "harga_venue_cents",
            "p_final",
            "p_market",
            "ev_pct",
            "p_banjir_3p",
            "p_banjir_ft",
        )
        for entri in valid:
            for kunci in wajib:
                self.assertIn(kunci, entri)
                self.assertIsNotNone(entri[kunci])
        # Spot-check U240,5 (nilai dihitung mesin, diverifikasi tangan):
        # p_final 0,9298; p_market 0,90 (jangkar); EV +12,7%.
        u240 = next(e for e in valid if e["garis"] == 240.5)
        self.assertAlmostEqual(u240["p_final"], 0.9298, places=4)
        self.assertAlmostEqual(u240["p_market"], 0.90, places=4)
        self.assertAlmostEqual(u240["ev_pct"], 12.7, places=1)
        self.assertGreaterEqual(u240["p_banjir_3p"], 0.70)
        self.assertGreaterEqual(u240["p_banjir_ft"], 0.65)

    def test_garis_lolos_di_luar_band_tidak_masuk(self):
        # U248,5 @90,5¢ dan U250,5 @92,5¢ LOLOS semua gate v18 tapi
        # DI ATAS band 89¢ -> bukan garis valid Asuransi (band adalah
        # batas himpunan valid_lines, bukan gate equilibrium).
        valid = equilibrium.garis_valid_asuransi(_analisis_224(), CFG)
        garis = [e["garis"] for e in valid]
        self.assertNotIn(248.5, garis)
        self.assertNotIn(250.5, garis)
        for entri in valid:
            self.assertGreaterEqual(entri["harga_venue_cents"], 80.0)
            self.assertLessEqual(entri["harga_venue_cents"], 89.0)

    def test_garis_gagal_gate_tidak_masuk(self):
        # U236,5 @78,5¢ gagal peluang + p_market + banjir FT;
        # U238,5 lolos — batasnya tajam di antara keduanya.
        valid = equilibrium.garis_valid_asuransi(_analisis_224(), CFG)
        garis = [e["garis"] for e in valid]
        self.assertNotIn(236.5, garis)
        self.assertIn(238.5, garis)

    def test_semua_entri_lolos_semua_gate(self):
        # Properti: tiap entri valid_lines lolos 100% gate Asuransi
        # (dibuktikan dari dict gate nilai_semua_garis — tidak ada
        # garis yang "hampir lolos" menyelinap masuk).
        valid = equilibrium.garis_valid_asuransi(_analisis_224(), CFG)
        self.assertTrue(valid)
        for entri in valid:
            self.assertTrue(entri["lolos_semua"])
            self.assertTrue(all(entri["gate"].values()))
            self.assertGreaterEqual(entri["p_final"], 0.82)
            self.assertGreaterEqual(entri["p_market"], 0.80)
            self.assertGreaterEqual(entri["ev_pct"], -1.0)
            self.assertGreaterEqual(entri["p_banjir_3p"], 0.70)
            self.assertGreaterEqual(entri["p_banjir_ft"], 0.65)

    def test_band_dibaca_dari_config(self):
        # Band sempit [82, 86] -> hanya 240,5 (@82,5¢) + 242,5
        # (@84,5¢); 238,5 (@80,5¢) + 244,5/246,5 keluar.
        cfg = copy.deepcopy(CFG)
        cfg["tickets"]["insurance"]["preferred_price_band"] = [82, 86]
        valid = equilibrium.garis_valid_asuransi(_analisis_224(), cfg)
        self.assertEqual([e["garis"] for e in valid], [240.5, 242.5])

    def test_kosong_bila_tidak_ada_yang_lolos(self):
        # Fixture EV-mengikat: semua garis gagal EV (harga 90–97¢
        # terlalu mahal) -> [] (dihitung, bukan None).
        tangga = _tangga(
            [
                (254.5, 90.0, 500.0, False),
                (256.5, 93.0, 500.0, False),
                (258.5, 95.0, 500.0, False),
                (260.5, 97.0, 500.0, False),
            ]
        )
        analisis = _analisis("DET@ATL_2026-11-22", 233.0, 19.2, tangga)
        self.assertEqual(equilibrium.garis_valid_asuransi(analisis, CFG), [])

    def test_none_tanpa_konteks(self):
        # Tanpa tangga -> konteks tidak siap -> None (sama seperti
        # nilai_semua_garis), bukan [] (tidak ada klaim "tidak ada").
        analisis = _analisis_224()
        analisis["market"] = {"main_total_line": 225.5}
        self.assertIsNone(equilibrium.garis_valid_asuransi(analisis, CFG))
        analisis2 = _analisis_224()
        del analisis2["simulation"]
        self.assertIsNone(equilibrium.garis_valid_asuransi(analisis2, CFG))

    def test_memakai_ktx_yang_diberikan(self):
        # ktx dari siapkan_konteks dipakai ulang (pemanggil yang
        # sudah menghitungnya — mis. komposer — tidak menghitung
        # CDF + tangga dua kali).
        analisis = _analisis_224()
        ktx = equilibrium.siapkan_konteks(analisis, "insurance", CFG)
        self.assertTrue(ktx["ok"])
        valid = equilibrium.garis_valid_asuransi(analisis, CFG, ktx=ktx)
        self.assertEqual(
            [e["garis"] for e in valid],
            [238.5, 240.5, 242.5, 244.5, 246.5],
        )


class TestDefaultEqTidakBerubah(unittest.TestCase):
    """Backward compat: cari_equilibrium tetap safety-first plafon."""

    def test_cari_equilibrium_tetap_memilih_plafon(self):
        # Garis plafon safety-first TETAP disimpan sebagai default_eq
        # untuk laporan individu — Patch #2 tidak mengubah perilaku
        # cari_equilibrium (komposer yang berubah, bukan equilibrium
        # per kaki).
        hasil = equilibrium.cari_equilibrium(_analisis_224(), "insurance", CFG)
        self.assertTrue(hasil["dihitung"])
        self.assertTrue(hasil["ada"])
        self.assertEqual(hasil["mode"], "safety_first")
        self.assertEqual(hasil["garis"], 246.5)
        self.assertEqual(hasil["harga_venue_cents"], 88.5)
        self.assertAlmostEqual(hasil["p_final"], 0.995248, places=6)
        self.assertEqual(hasil["n_kandidat_lolos"], 7)

    def test_nilai_semua_garis_tidak_berubah(self):
        # nilai_semua_garis (fondasi valid_lines) mengembalikan hasil
        # yang sama seperti sebelum patch: 10 garis dinilai, 7 lolos.
        nilai = equilibrium.nilai_semua_garis(_analisis_224(), "insurance", CFG)
        self.assertEqual(len(nilai), 10)
        lolos = [n for n in nilai if n["lolos_semua"]]
        self.assertEqual(len(lolos), 7)
        self.assertEqual(
            [n["line"] for n in lolos],
            [238.5, 240.5, 242.5, 244.5, 246.5, 248.5, 250.5],
        )


if __name__ == "__main__":
    unittest.main()
