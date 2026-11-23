"""Tes Patch #2b v18.1: komposer Asuransi optimasi gabungan + fallback (b).

Perangkap Plafon 88,5¢ (REFERENSI-PATCH-V18-1-GEMINI.md §1 Patch #2):
di T2 v18, ketiga kaki Asuransi terkunci di 88,5¢ (safety-first)
sehingga pengali maks hanya x1,36 — tiket tidak terbentuk padahal
garis 82–84¢ yang lolos 100% gate tersedia. Patch #2b: komposer
memilih kombinasi dari SEMUA garis valid (1 garis per laga, 2–6
kaki) yang MEMAKSIMALKAN peluang cair gabungan (max Π P_final,
dihitung dalam log) dengan pengali bersih di [2,00x, 2,50x],
menggunakan DP atas bucket log-pengali (bukan brute force).

Fallback (b) — KEPUTUSAN USER 2026-11-23 15:52 WIB (DECISIONS.md,
mengikat): bila tidak ada kombinasi >= 2,00x tanpa melanggar gate,
komposer MELAPORKAN opsi terbaik di [1,80x, 1,99x] sebagai OPSI
BERLABEL (bukan tiket): lengkap dengan pengali, peluang cair
gabungan (joint P_final), detail per kaki, dan alasan tidak
mencapai x2. Opsi ini TIDAK punya ticket_id/type, TIDAK masuk
insurance_reason sebagai tiket, dan TIDAK BOLEH lolos ke ledger
sebagai tiket. Keputusan pasang di tangan user.

Fixture (angka dihitung mesin, diverifikasi tangan di skrip
scratch — lihat LAPORAN-V18-1-B.md):
- Perangkap (sigma 5, median 224): garis valid per laga 238,5–246,5
  (harga venue 80,5–88,5¢); default_eq plafon 88,5¢. 4 laga:
  jalur lama 4×88,5¢ = x1,54 (gagal); optimum DP 4×82,5¢ = x2,04
  (peluang cair gabungan 0,7476).
- Fallback (sigma 11, median 224): garis valid per laga 242,5–246,5
  (84,5–88,5¢). 4 laga: kombinasi terbaik di bawah x2 adalah
  3×84,5¢ + 1×86,5¢ = x1,81 (peluang cair gabungan 0,7831).
"""

from __future__ import annotations

import copy
import math
import tempfile
import time
import unittest
from pathlib import Path

import config
from engine import equilibrium, ticket_composer
from ledger import store

CFG = config.load_playstyle()
SEKARANG = "2026-11-22T13:00:00+00:00"

LAGA_4 = [
    "DET@ATL_2026-11-22",
    "BOS@NYK_2026-11-22",
    "LAL@GSW_2026-11-22",
    "MIA@CHI_2026-11-22",
]

LAGA_12 = LAGA_4 + [
    "PHX@DAL_2026-11-22",
    "SAC@UTA_2026-11-22",
    "TOR@WAS_2026-11-22",
    "WAS@CHA_2026-11-22",
    "OKC@MIA_2026-11-22",
    "ORL@WAS_2026-11-22",
    "IND@NYK_2026-11-22",
    "DAL@UTA_2026-11-22",
]

# 14 laga untuk tes tanpa-kembar: Asuransi mengambil 6 laga
# (optimum DP), Utama butuh 8 laga sisanya (8 kaki @82,5¢ = x4,41;
# 6 kaki sisanya hanya x3,00 — tidak cukup untuk target x3,00).
LAGA_14 = LAGA_12 + [
    "CLE@MIL_2026-11-22",
    "MEM@HOU_2026-11-22",
]


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
    """Tangga totals dari daftar (garis, harga, volume, thin)."""
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


def _tangga_224():
    """Tangga fixture median 224 (garis 232,5–250,5, langkah 2 poin)."""
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


def _tangga_halus():
    """Tangga langkah 1 poin (uji beban DP): garis 236,5–250,5.

    Harga venue 78,5–90,5¢; garis valid per laga (sigma 5) ada 9
    (238,5–246,5, harga venue 80,5–88,5¢) — DP menghadapi 9 varian
    per laga, bukan 5.
    """
    baris = []
    garis = 236.5
    while garis <= 250.5 + 1e-9:
        harga = round(78.0 + (garis - 236.5) * 1.0, 1)
        baris.append((garis, harga, 500.0, False))
        garis = round(garis + 1.0, 9)
    return _tangga(baris)


def _kaki(match_id, ticket, line, p_model, p_market, harga):
    """Satu kaki artefak nba_analysis (bentuk _rakit_kaki).

    Kaki membawa bukti eksekusi (likuiditas $30.000 + bid harga-1 /
    ask harga+0,5, spread 1,5¢ — pola tests/test_ticket_composer.
    buat_kaki) supaya lolos gate eksekusi v18 juga tanpa tangga.
    """
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
        "volume_usd": 500.0,
        "thin": False,
        "liquidity_usd": 30000.0,
        "bid_cents": harga - 1.0,
        "ask_cents": harga + 0.5,
        "climb": None,
        "meets": True,
        "reason": None,
        "fetched_at": "2026-11-22T10:00:00+00:00",
        "ticket": ticket,
    }


def _analisis(match_id, sigma=5.0, tangga=None):
    """Artefak nba_analysis median 224 + CDF penuh + tangga."""
    return {
        "format": "nba_analysis",
        "format_version": 1,
        "match_id": match_id,
        "home_tricode": match_id.split("@")[1].split("_")[0],
        "away_tricode": match_id.split("@")[0],
        "game_date": "2026-11-22",
        "generated_at": "2026-11-22T10:00:00+00:00",
        "status": "OK",
        "legs": [
            _kaki(match_id, "insurance", 240.5, 0.99, 0.90, 82.0),
            _kaki(match_id, "main", 236.5, 0.99, 0.90, 78.0),
        ],
        "simulation": {
            "score_distribution": {"total": {"median": 224.0}},
            "markets": _cdf_normal(224.0, sigma, 224.0 - 30, 224.0 + 45),
        },
        "market": {
            "main_total_line": 225.5,
            "totals": tangga if tangga is not None else _tangga_224(),
        },
        "anomalies": [],
    }


def _analisis_tanpa_tangga(match_id, harga_ins=78.0, harga_main=75.0):
    """Artefak tanpa tangga (jalur fallback v18 — kaki artefak saja).

    Mirip tests/test_ticket_composer.buat_analisis: sim markets
    hanya 2 titik (garis kedua kaki), tanpa market.totals sehingga
    equilibrium tidak dihitung.
    """
    kaki_ins = _kaki(match_id, "insurance", 235.5, 0.85, 0.83, harga_ins)
    kaki_main = _kaki(match_id, "main", 231.5, 0.78, 0.76, harga_main)
    markets = {}
    for kaki in (kaki_ins, kaki_main):
        markets[f"total_under_{kaki['line']:g}"] = kaki["p_model"]
    return {
        "format": "nba_analysis",
        "format_version": 1,
        "match_id": match_id,
        "home_tricode": match_id.split("@")[1].split("_")[0],
        "away_tricode": match_id.split("@")[0],
        "game_date": "2026-11-22",
        "generated_at": "2026-11-22T10:00:00+00:00",
        "status": "OK",
        "legs": [kaki_ins, kaki_main],
        "simulation": {
            "score_distribution": {"total": {"median": 224.0}},
            "markets": markets,
        },
        "market": {"main_total_line": 225.5},
        "anomalies": [],
    }


def _kaki_recheck(kaki, verdict="TETAP_OK"):
    """Satu kaki laporan recheck (bentuk decide())."""
    return {
        "leg_id": kaki["leg_id"],
        "verdict": verdict,
        "reasons": [],
        "old_line": kaki["line"],
        "new_line": kaki["line"],
        "old_price_cents": kaki["price_cents"],
        "new_price_cents": kaki["price_cents"],
        "price_move_cents": 0.0,
        "resimulated": False,
        "probability_used": "model",
        "probability_value": kaki["p_final"],
        "kenapa_beda": {
            "gap_points": 1.5,
            "triggered": False,
            "reason_found": False,
            "reason": None,
        },
    }


def _recheck_semua_ok(analyses, recheck_at="2026-11-22T12:30:00+00:00"):
    """Recheck TETAP_OK untuk semua analisis."""
    hasil = []
    for analisis in analyses:
        hasil.append(
            {
                "format": "nba_recheck",
                "format_version": 1,
                "match_id": analisis["match_id"],
                "analysis_generated_at": analisis["generated_at"],
                "recheck_at": recheck_at,
                "verdict": "GO",
                "resimulated": False,
                "resim_reasons": [],
                "changes": [],
                "legs": [_kaki_recheck(k) for k in analisis["legs"]],
                "anomalies": [],
                "missing": [],
                "attention": [],
                "action_required": None,
            }
        )
    return hasil


def _slate(laga, sigma=5.0, tangga=None):
    """Slate fixture (satu artefak per laga, parameter sama)."""
    return [_analisis(m, sigma=sigma, tangga=tangga) for m in laga]


class TestPerangkapPlafon(unittest.TestCase):
    """Regresi: komposer mencapai >= 2,00x dari garis valid (bukan x1,36)."""

    def test_empat_laga_mencapai_x2_dari_garis_valid(self):
        # JALUR LAMA (v18): 4 kaki default_eq @88,5¢ -> pengali maks
        # x1,54 -> tiket tidak terbentuk (dibuktikan skrip scratch
        # sebelum patch). JALUR BARU: DP memilih 4×82,5¢ = x2,04
        # (peluang cair gabungan 0,9298^4 = 0,7476) — kombinasi
        # optimal: 3×82,5+1×84,5 hanya x1,99 (< 2,00), jadi
        # 4×82,5 adalah satu-satunya 4-kaki di jendela dengan
        # peluang gabungan tertinggi.
        analyses = _slate(LAGA_4, sigma=5.0)
        hasil = ticket_composer.compose_tickets(
            analyses, None, CFG, stake_total=20, now=SEKARANG
        )
        ins = hasil["insurance"]
        self.assertIsNotNone(ins, hasil.get("insurance_reason"))
        self.assertIsNone(hasil["insurance_reason"])
        self.assertIsNone(hasil.get("insurance_fallback_option"))
        self.assertEqual(len(ins["legs"]), 4)
        self.assertGreaterEqual(ins["multiplier"], 2.00)
        self.assertLessEqual(ins["multiplier"], 2.50)
        self.assertAlmostEqual(ins["multiplier"], 2.04, places=2)
        harga = sorted(k["jup_price_cents"] for k in ins["legs"])
        self.assertEqual(harga, [82.5, 82.5, 82.5, 82.5])
        # BUKAN terkunci di plafon 88,5¢.
        self.assertNotIn(88.5, harga)
        self.assertAlmostEqual(ins["metrics"]["p_win"], 0.9298**4, places=3)

    def test_flag_dimatikan_perilaku_lama_persis(self):
        # expose_all_valid_lines_to_composer=false -> jalur
        # _pilih_subset v18: 4 kaki @88,5¢, pengali maks x1,54,
        # tiket tidak terbentuk, TANPA opsi fallback (jalur lama
        # tidak mengenal fallback).
        cfg = copy.deepcopy(CFG)
        cfg["tickets"]["insurance"]["expose_all_valid_lines_to_composer"] = False
        analyses = _slate(LAGA_4, sigma=5.0)
        hasil = ticket_composer.compose_tickets(
            analyses, None, cfg, stake_total=20, now=SEKARANG
        )
        self.assertIsNone(hasil["insurance"])
        self.assertIn("x1.54", hasil["insurance_reason"])
        self.assertIn("tidak tercapai", hasil["insurance_reason"])
        self.assertIsNone(hasil.get("insurance_fallback_option"))


class TestFallbackB(unittest.TestCase):
    """Fallback (b): opsi berlabel di [1,80x, 1,99x], BUKAN tiket."""

    def test_opsi_dilaporkan_bila_tiket_x2_tidak_terbentuk(self):
        # 4 laga sigma 11: garis valid termurah 84,5¢; kombinasi
        # terbaik di bawah x2 adalah 3×84,5¢ + 1×86,5¢ = x1,81
        # (peluang cair gabungan 0,9358^3 × 0,9555 = 0,7831) —
        # mengalahkan 4×84,5¢ (x1,85, peluang 0,7670) karena
        # tujuan DP adalah peluang cair gabungan, bukan pengali.
        analyses = _slate(LAGA_4, sigma=11.0)
        hasil = ticket_composer.compose_tickets(
            analyses, None, CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNone(hasil["insurance"])
        self.assertIn("tidak tercapai", hasil["insurance_reason"])
        opsi = hasil.get("insurance_fallback_option")
        self.assertIsNotNone(opsi)
        self.assertEqual(opsi["label"], "OPSI_DI_BAWAH_TARGET")
        self.assertGreaterEqual(opsi["multiplier"], 1.80)
        self.assertLessEqual(opsi["multiplier"], 1.99)
        self.assertAlmostEqual(opsi["multiplier"], 1.81, places=2)
        self.assertIn("joint_p_final", opsi)
        self.assertAlmostEqual(opsi["joint_p_final"], 0.7831, places=3)
        self.assertEqual(len(opsi["legs"]), 4)
        harga = sorted(k["harga_venue_cents"] for k in opsi["legs"])
        self.assertEqual(harga, [84.5, 84.5, 84.5, 86.5])
        for kaki in opsi["legs"]:
            self.assertIn("match_id", kaki)
            self.assertIn("line", kaki)
            self.assertIn("p_final", kaki)
            self.assertGreaterEqual(kaki["p_final"], 0.82)
        self.assertIn("alasan", opsi)
        self.assertIn("2.00", opsi["alasan"])
        # Ringkasan menampilkan opsi sebagai BUKAN tiket.
        self.assertIn("BUKAN TIKET", hasil["summary"])
        self.assertIn("x1.81", hasil["summary"])

    def test_opsi_bukan_tiket_dan_tidak_bisa_masuk_ledger(self):
        analyses = _slate(LAGA_4, sigma=11.0)
        hasil = ticket_composer.compose_tickets(
            analyses, None, CFG, stake_total=20, now=SEKARANG
        )
        opsi = hasil.get("insurance_fallback_option")
        self.assertIsNotNone(opsi)
        # BUKAN tiket: tanpa ticket_id/type/stake.
        self.assertNotIn("ticket_id", opsi)
        self.assertNotIn("type", opsi)
        self.assertNotIn("stake", opsi)
        # Gagal validasi skema tiket (bukan bentuk tiket).
        self.assertIsNotNone(ticket_composer.validate_ticket(opsi))
        # Ledger menolaknya (validasi skema dulu, sebelum insert).
        with tempfile.TemporaryDirectory() as tmp:
            conn = store.connect(Path(tmp) / "tes.db")
            try:
                with self.assertRaises(store.LedgerError):
                    store.log_ticket(conn, opsi)
                self.assertIsNone(
                    store.get_ticket(conn, opsi.get("ticket_id") or "tidak-ada")
                )
            finally:
                conn.close()

    def test_batas_atas_fallback_199_tidak_termasuk_19916(self):
        # Presisi batas: 3 kaki @78¢ = x1,9916 — DI ATAS 1,99,
        # jadi BUKAN opsi fallback (dan bukan tiket: < 2,00);
        # 4 kaki @78¢ = x2,55 di atas maks 2,50. Alasan tetap
        # "tidak ada yang masuk target" seperti tes lama.
        analyses = [_analisis_tanpa_tangga(m) for m in LAGA_4]
        hasil = ticket_composer.compose_tickets(
            analyses,
            _recheck_semua_ok(analyses),
            CFG,
            stake_total=20,
            now=SEKARANG,
        )
        self.assertIsNone(hasil["insurance"])
        self.assertIn("tidak ada yang masuk target", hasil["insurance_reason"])
        self.assertIsNone(hasil.get("insurance_fallback_option"))

    def test_tidak_ada_opsi_bila_maks_di_bawah_180(self):
        # 2 laga perangkap: pengali maks 2×80,5¢ = x1,46 < 1,80 —
        # tidak ada tiket DAN tidak ada opsi; alasan menyebut
        # pengali maksimum yang tercapai.
        analyses = _slate(LAGA_4[:2], sigma=5.0)
        hasil = ticket_composer.compose_tickets(
            analyses, None, CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNone(hasil["insurance"])
        self.assertIsNone(hasil.get("insurance_fallback_option"))
        self.assertIn("x1.46", hasil["insurance_reason"])
        self.assertIn("tidak tercapai", hasil["insurance_reason"])


class TestTanpaKembarV181(unittest.TestCase):
    """Tanpa kaki kembar tetap ditegakkan pada jalur DP."""

    def test_kedua_tiket_disjoint(self):
        # 14 laga sigma 5: Asuransi mengambil 6 laga (optimum DP:
        # 5×88,5¢ + 1×86,5¢ = x2,01, peluang cair gabungan 0,9631 —
        # dengan banyak laga tersedia, DP memaksimalkan peluang
        # gabungan lewat kaki-kaki mahal, BUKAN lewat 4 kaki murah),
        # Utama memakai 8 laga sisanya (8×82,5¢ = x4,41, lolos
        # "yakin" karena recheck TETAP_OK) — tidak ada match_id
        # yang muncul di kedua tiket.
        analyses = _slate(LAGA_14, sigma=5.0)
        hasil = ticket_composer.compose_tickets(
            analyses,
            _recheck_semua_ok(analyses),
            CFG,
            stake_total=20,
            now=SEKARANG,
        )
        ins, main = hasil["insurance"], hasil["main"]
        self.assertIsNotNone(ins, hasil.get("insurance_reason"))
        self.assertIsNotNone(main, hasil.get("main_reason"))
        self.assertEqual(len(ins["legs"]), 6)
        self.assertAlmostEqual(ins["multiplier"], 2.01, places=2)
        laga_ins = {k["match_id"] for k in ins["legs"]}
        laga_main = {k["match_id"] for k in main["legs"]}
        self.assertEqual(len(laga_ins), 6)
        self.assertEqual(laga_ins & laga_main, set())


class TestGarisDariValidLines(unittest.TestCase):
    """Semua garis kombinasi berasal dari valid_lines (gate tidak longgar)."""

    def test_semua_garis_kombinasi_berasal_dari_valid_lines(self):
        analyses = _slate(LAGA_4, sigma=5.0)
        hasil = ticket_composer.compose_tickets(
            analyses, None, CFG, stake_total=20, now=SEKARANG
        )
        ins = hasil["insurance"]
        self.assertIsNotNone(ins)
        per_laga = {a["match_id"]: a for a in analyses}
        for kaki in ins["legs"]:
            analisis = per_laga[kaki["match_id"]]
            valid = equilibrium.garis_valid_asuransi(analisis, CFG)
            garis_valid = [e["garis"] for e in valid]
            garis_kaki = float(kaki["selection"].split()[1])
            self.assertIn(
                garis_kaki,
                garis_valid,
                f"{kaki['match_id']} garis {garis_kaki} bukan garis valid",
            )
            # Gate Asuransi tetap ditegakkan pada kaki terpilih.
            self.assertGreaterEqual(kaki["p_final"], 0.82)
            self.assertGreaterEqual(kaki["p_market"], 0.80)
            self.assertGreaterEqual(kaki["ev_pct"], -1.0)

    def test_varian_di_luar_valid_lines_ditolak(self):
        # Validasi fail-closed: varian yang garisnya tidak ada di
        # valid_lines laga itu ditolak (bukan dipakai diam-diam).
        per_laga = ticket_composer._terbaru_per_laga(
            _slate(LAGA_4[:1], sigma=5.0), "generated_at"
        )
        kandidat, _ = ticket_composer._kumpulkan_kandidat(per_laga, {}, CFG)
        kand = kandidat["insurance"][0]
        self.assertTrue(kand.get("valid_lines"))
        # Varian tiruan di garis 250,5 (lolos gate tapi DI LUAR band
        # -> bukan garis valid) harus ditolak validator.
        varian_palsu = copy.deepcopy(kand)
        varian_palsu["line"] = 250.5
        varian_palsu["harga_jup"] = 92.5
        self.assertFalse(
            ticket_composer._varian_dalam_valid_lines(varian_palsu, kand["valid_lines"])
        )
        # Varian asli (garis valid) lolos validator.
        varian_asli = ticket_composer._varian_kandidat_asuransi(kand, CFG)
        self.assertTrue(varian_asli)
        for varian in varian_asli:
            self.assertTrue(
                ticket_composer._varian_dalam_valid_lines(varian, kand["valid_lines"])
            )


class TestRuntimeDP(unittest.TestCase):
    """Runtime komposer pada slate sintetis 10 laga (target < 5 detik)."""

    def test_runtime_slate_10_laga(self):
        # 10 laga × 9 garis valid per laga (tangga langkah 1 poin)
        # — ruang kombinasi naif 10^9; DP bucket harus jauh di
        # bawah batas longgar 30 detik (target operasional < 5 dtk).
        analyses = _slate(LAGA_12[:10], sigma=5.0, tangga=_tangga_halus())
        mulai = time.perf_counter()
        hasil = ticket_composer.compose_tickets(
            analyses, None, CFG, stake_total=20, now=SEKARANG
        )
        durasi = time.perf_counter() - mulai
        print(f"\n[ritme] compose 10 laga × 9 garis valid: {durasi:.2f} detik")
        self.assertLess(durasi, 30.0)
        ins = hasil["insurance"]
        self.assertIsNotNone(ins, hasil.get("insurance_reason"))
        self.assertGreaterEqual(ins["multiplier"], 2.00)
        self.assertLessEqual(ins["multiplier"], 2.50)


class TestConfigPatch2(unittest.TestCase):
    """Kunci config Patch #2 (section tickets.insurance saja)."""

    def test_kunci_baru_patch2(self):
        ins = CFG["tickets"]["insurance"]
        self.assertIs(ins["expose_all_valid_lines_to_composer"], True)
        self.assertEqual(
            ins["composer_objective"],
            "max_joint_p_final_within_target_multiplier",
        )
        self.assertEqual(ins["target_multiplier_fallback_min"], 1.80)

    def test_target_asuransi_tetap_dan_version_tetap(self):
        # Target Asuransi [2,00x, 2,50x] TETAP; version config
        # tetap 18 (koordinator yang bump ke v18.1).
        ins = CFG["tickets"]["insurance"]
        self.assertEqual(ins["multiplier_min"], 2.0)
        self.assertEqual(ins["multiplier_max"], 2.5)
        self.assertEqual(CFG["meta"]["version"], 18.1)


class TestPeringatanTumpangTindihOpsi(unittest.TestCase):
    """Opsi fallback yang berbagi laga dengan Utama diperingatkan."""

    def test_opsi_berbagi_laga_dengan_utama_diperingatkan(self):
        opsi = {
            "label": "OPSI_DI_BAWAH_TARGET",
            "multiplier": 1.81,
            "joint_p_final": 0.78,
            "legs": [
                {"match_id": "DET@ATL_2026-11-22"},
                {"match_id": "BOS@NYK_2026-11-22"},
            ],
            "alasan": "tidak ada kombinasi >= x2,00",
        }
        subset_main = [
            {"match_id": "BOS@NYK_2026-11-22"},
            {"match_id": "LAL@GSW_2026-11-22"},
        ]
        peringatan = ticket_composer._peringatan_tumpang_tindih_opsi(opsi, subset_main)
        self.assertIsNotNone(peringatan)
        self.assertIn("BOS@NYK_2026-11-22", peringatan)
        self.assertNotIn("DET@ATL_2026-11-22", peringatan)
        self.assertNotIn("LAL@GSW_2026-11-22", peringatan)

    def test_tanpa_tumpang_tindih_tanpa_peringatan(self):
        opsi = {
            "label": "OPSI_DI_BAWAH_TARGET",
            "multiplier": 1.81,
            "joint_p_final": 0.78,
            "legs": [{"match_id": "DET@ATL_2026-11-22"}],
            "alasan": "tidak ada kombinasi >= x2,00",
        }
        subset_main = [{"match_id": "LAL@GSW_2026-11-22"}]
        self.assertIsNone(
            ticket_composer._peringatan_tumpang_tindih_opsi(opsi, subset_main)
        )
        self.assertIsNone(
            ticket_composer._peringatan_tumpang_tindih_opsi(None, subset_main)
        )


if __name__ == "__main__":
    unittest.main()
