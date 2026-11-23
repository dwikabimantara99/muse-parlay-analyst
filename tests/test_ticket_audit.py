"""Tes engine/ticket_audit.py — SEMUA offline dari fixture, 0 kredit Odds API.

Fixture dibangun di dalam file ini (tidak bergantung pada out/ —
out/ gitignored, tes harus lulus di checkout bersih). Config yang
dipakai adalah playstyle.yaml repo (v14): min_leg_prob Asuransi
0,74 / Utama 0,65; lantai harga 75¢; ambang gap condong-ke-market
5,0 poin; label MAHAL bila EV < -2%; ambang edge tipis audit 5%.
"""

import copy
import math
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from engine import ticket_audit

CFG = config.load_playstyle()


def _artefak(
    match_id,
    median=220.0,
    main_line=221.5,
    markets=None,
    totals=None,
    generated_at="2026-11-22T14:24:00+00:00",
    status="OK",
):
    """Artefak nba_analysis minimal untuk tes audit."""
    return {
        "format": "nba_analysis",
        "format_version": 1,
        "match_id": match_id,
        "game_date": "2026-11-22",
        "generated_at": generated_at,
        "status": status,
        "simulation": {
            "markets": markets or {},
            "score_distribution": {"total": {"median": median}},
        },
        "market": {"main_total_line": main_line, "totals": totals or []},
    }


def _tangga(line, price_cents, volume_usd=500.0, thin=False):
    """Satu entri tangga Polymarket (side under)."""
    return {
        "line": line,
        "side": "under",
        "price_cents": price_cents,
        "volume_usd": volume_usd,
        "thin": thin,
    }


def _kaki(match_id, line, harga, p_model_gemini=None, market="total_under"):
    """Satu kaki tiket (format file tiket)."""
    kaki = {
        "leg_id": f"{match_id}:total_under_{line:g}:main",
        "match_id": match_id,
        "sport": "nba",
        "market": market,
        "selection": f"Under {line:g} ({match_id.rsplit('_', 1)[0]})",
        "jup_price_cents": harga,
        "status": "OK",
    }
    if p_model_gemini is not None:
        kaki["p_model"] = p_model_gemini
    return kaki


def _tiket(tipe, kaki_list, multiplier=2.0, stake=15.0):
    return {
        "ticket_id": f"tkt-tes-{tipe}",
        "type": tipe,
        "stake": stake,
        "multiplier": multiplier,
        "legs": kaki_list,
    }


class TestKumpulkanAnalisis(unittest.TestCase):
    def test_artefak_langsung_dan_slate(self):
        langsung = _artefak("AAA@BBB_2026-11-22")
        slate = {
            "slate_id": "s1",
            "matches": [
                {
                    "match_id": "nba-2026-11-22-ccc-ddd",
                    "nba_analysis": _artefak("CCC@DDD_2026-11-22"),
                }
            ],
        }
        per_laga, _ = ticket_audit.kumpulkan_analisis([langsung, slate])
        self.assertEqual(set(per_laga), {"AAA@BBB_2026-11-22", "CCC@DDD_2026-11-22"})

    def test_duplikat_terbaru_menang(self):
        lama = _artefak(
            "AAA@BBB_2026-11-22",
            median=220.0,
            generated_at="2026-11-22T14:24:00+00:00",
        )
        baru = _artefak(
            "AAA@BBB_2026-11-22",
            median=229.0,
            generated_at="2026-11-22T21:56:00+00:00",
        )
        per_laga, catatan = ticket_audit.kumpulkan_analisis([lama, baru])
        self.assertEqual(len(per_laga), 1)
        median, _ = ticket_audit.median_pra_laga(per_laga)
        self.assertEqual(median["AAA@BBB_2026-11-22"], 229.0)
        self.assertTrue(any("terbaru" in c for c in catatan))

    def test_duplikat_tanpa_stempel_pertama_menang(self):
        pertama = _artefak("AAA@BBB_2026-11-22", median=220.0)
        pertama.pop("generated_at")
        kedua = _artefak("AAA@BBB_2026-11-22", median=229.0)
        kedua.pop("generated_at")
        per_laga, _ = ticket_audit.kumpulkan_analisis([pertama, kedua])
        median, _ = ticket_audit.median_pra_laga(per_laga)
        self.assertEqual(median["AAA@BBB_2026-11-22"], 220.0)

    def test_dokumen_bukan_analisis_dicatat(self):
        per_laga, catatan = ticket_audit.kumpulkan_analisis([{"format": "lain"}])
        self.assertEqual(per_laga, {})
        self.assertEqual(len(catatan), 1)

    def test_median_hilang_dicatat(self):
        art = _artefak("AAA@BBB_2026-11-22")
        art["simulation"]["score_distribution"]["total"].pop("median")
        median, catatan = ticket_audit.median_pra_laga({"AAA@BBB_2026-11-22": art})
        self.assertEqual(median, {})
        self.assertTrue(any("AAA@BBB_2026-11-22" in c for c in catatan))


class TestAuditKaki(unittest.TestCase):
    def _audit(self, tiket, artefak_list):
        hasil = ticket_audit.audit_tickets(tiket, artefak_list, cfg=CFG)
        self.assertEqual(len(hasil["tickets"]), 1)
        return hasil["tickets"][0]

    def test_kaki_lolos(self):
        art = _artefak(
            "AAA@BBB_2026-11-22",
            markets={"total_under_240.5": 0.86},
            totals=[_tangga(240.5, 80.0)],
        )
        tiket = _tiket("insurance", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)])
        hasil = self._audit(tiket, [art])
        kaki = hasil["legs"][0]
        self.assertEqual(kaki["verdict"], "LOLOS")
        self.assertEqual(kaki["p_model"], 0.86)
        self.assertAlmostEqual(kaki["edge"], 0.06)
        self.assertEqual(kaki["price_label"], "DISKON")
        self.assertFalse(kaki["overpay"])
        self.assertEqual(hasil["verdict"], "GO")

    def test_edge_tepat_5_poin_bukan_perhatian(self):
        art = _artefak(
            "AAA@BBB_2026-11-22",
            markets={"total_under_240.5": 0.85},
            totals=[_tangga(240.5, 80.0)],
        )
        tiket = _tiket("insurance", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)])
        hasil = self._audit(tiket, [art])
        self.assertEqual(hasil["legs"][0]["verdict"], "LOLOS")

    def test_prob_di_bawah_minimum_jangan_pasang(self):
        art = _artefak(
            "AAA@BBB_2026-11-22",
            markets={"total_under_240.5": 0.70},
            totals=[_tangga(240.5, 80.0)],
        )
        tiket = _tiket("insurance", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)])
        hasil = self._audit(tiket, [art])
        kaki = hasil["legs"][0]
        self.assertEqual(kaki["verdict"], "JANGAN_PASANG")
        self.assertEqual(hasil["verdict"], "NO-GO")
        gate_prob = [g for g in kaki["gates"] if g["gate"] == "peluang_minimum"][0]
        self.assertFalse(gate_prob["lolos"])

    def test_prob_yang_sama_lolos_di_utama(self):
        # 0,70 < 0,74 (Asuransi) tapi >= 0,65 (Utama).
        art = _artefak(
            "AAA@BBB_2026-11-22",
            markets={"total_under_240.5": 0.70},
            totals=[_tangga(240.5, 80.0)],
        )
        tiket = _tiket("main", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)])
        hasil = self._audit(tiket, [art])
        # Edge 0,70 - 0,80 = -0,10 -> OVERPAY + MAHAL -> PERHATIAN,
        # tapi bukan JANGAN_PASANG (prob lolos ambang Utama).
        self.assertEqual(hasil["legs"][0]["verdict"], "PERHATIAN")
        self.assertEqual(hasil["verdict"], "GO")

    def test_harga_di_bawah_lantai_jangan_pasang(self):
        art = _artefak(
            "AAA@BBB_2026-11-22",
            markets={"total_under_240.5": 0.86},
            totals=[_tangga(240.5, 70.0)],
        )
        tiket = _tiket("main", [_kaki("AAA@BBB_2026-11-22", 240.5, 70.0)])
        hasil = self._audit(tiket, [art])
        self.assertEqual(hasil["legs"][0]["verdict"], "JANGAN_PASANG")
        self.assertEqual(hasil["verdict"], "NO-GO")

    def test_thin_asuransi_jangan_utama_perhatian(self):
        art = _artefak(
            "AAA@BBB_2026-11-22",
            markets={"total_under_240.5": 0.86},
            totals=[_tangga(240.5, 80.0, volume_usd=7.5, thin=True)],
        )
        ins = self._audit(
            _tiket("insurance", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)]),
            [art],
        )
        self.assertEqual(ins["legs"][0]["verdict"], "JANGAN_PASANG")
        self.assertEqual(ins["verdict"], "NO-GO")
        self.assertIn("VOLUME_TIPIS", ins["legs"][0]["flags"])
        utm = self._audit(
            _tiket("main", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)]),
            [art],
        )
        self.assertEqual(utm["legs"][0]["verdict"], "PERHATIAN")
        self.assertEqual(utm["verdict"], "GO")
        self.assertTrue(utm["peringatan"])

    def test_tangga_hilang_fail_closed(self):
        art = _artefak(
            "AAA@BBB_2026-11-22",
            markets={"total_under_240.5": 0.86},
            totals=[],
        )
        ins = self._audit(
            _tiket("insurance", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)]),
            [art],
        )
        self.assertEqual(ins["legs"][0]["verdict"], "JANGAN_PASANG")
        utm = self._audit(
            _tiket("main", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)]),
            [art],
        )
        self.assertEqual(utm["legs"][0]["verdict"], "PERHATIAN")

    def test_overpay_flag_edge_negatif(self):
        # ORL 23 Nov: P 0,78346 @ 83¢ -> edge -4,7%.
        art = _artefak(
            "ORL@WAS_2026-11-22",
            markets={"total_under_235.5": 0.78346},
            totals=[_tangga(235.5, 80.0)],
        )
        tiket = _tiket("main", [_kaki("ORL@WAS_2026-11-22", 235.5, 83.0)])
        hasil = self._audit(tiket, [art])
        kaki = hasil["legs"][0]
        self.assertTrue(kaki["overpay"])
        self.assertIn("OVERPAY", kaki["flags"])
        self.assertAlmostEqual(kaki["edge"], -0.04654, places=5)
        self.assertEqual(kaki["price_label"], "MAHAL")
        self.assertEqual(kaki["verdict"], "PERHATIAN")

    def test_edge_tipis_perhatian(self):
        # DEN Asuransi 23 Nov (bila tidak thin): edge +2,5% -> PERHATIAN.
        art = _artefak(
            "DEN@CHI_2026-11-22",
            markets={"total_under_252.5": 0.84474},
            totals=[_tangga(252.5, 81.0)],
        )
        tiket = _tiket("insurance", [_kaki("DEN@CHI_2026-11-22", 252.5, 82.0)])
        hasil = self._audit(tiket, [art])
        kaki = hasil["legs"][0]
        self.assertAlmostEqual(kaki["edge"], 0.02474, places=5)
        self.assertEqual(kaki["verdict"], "PERHATIAN")
        self.assertTrue(any("edge tipis" in a for a in kaki["alasan"]))

    def test_mahal_asuransi_jangan_pasang(self):
        # P 0,75 @ 80¢ -> EV -6,25% (MAHAL), prob lolos 0,74.
        art = _artefak(
            "AAA@BBB_2026-11-22",
            markets={"total_under_240.5": 0.75},
            totals=[_tangga(240.5, 80.0)],
        )
        tiket = _tiket("insurance", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)])
        hasil = self._audit(tiket, [art])
        self.assertEqual(hasil["legs"][0]["price_label"], "MAHAL")
        self.assertEqual(hasil["legs"][0]["verdict"], "JANGAN_PASANG")

    def test_sim_tidak_ada_data_incomplete(self):
        art = _artefak(
            "AAA@BBB_2026-11-22",
            markets={"total_under_238.5": 0.80},
            totals=[_tangga(240.5, 80.0)],
        )
        tiket = _tiket("main", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)])
        hasil = self._audit(tiket, [art])
        kaki = hasil["legs"][0]
        self.assertEqual(kaki["verdict"], "DATA_INCOMPLETE")
        self.assertIsNone(kaki["p_model"])
        self.assertIsNone(hasil["p_gabungan"])
        self.assertEqual(hasil["verdict"], "NO-GO")

    def test_artefak_tidak_ada_data_incomplete(self):
        tiket = _tiket("main", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)])
        hasil = self._audit(tiket, [])
        self.assertEqual(hasil["legs"][0]["verdict"], "DATA_INCOMPLETE")
        self.assertEqual(hasil["verdict"], "NO-GO")

    def test_pasar_bukan_total_under_data_incomplete(self):
        art = _artefak(
            "AAA@BBB_2026-11-22",
            markets={"total_under_240.5": 0.86},
            totals=[_tangga(240.5, 80.0)],
        )
        kaki = _kaki("AAA@BBB_2026-11-22", 240.5, 80.0, market="moneyline")
        tiket = _tiket("main", [kaki])
        hasil = self._audit(tiket, [art])
        self.assertEqual(hasil["legs"][0]["verdict"], "DATA_INCOMPLETE")

    def test_p_model_file_tiket_diabaikan(self):
        # File tiket mengklaim p_model 0,99 (Gemini); sim mesin 0,70.
        # Verdict memakai 0,70 (JANGAN_PASANG di Asuransi).
        art = _artefak(
            "AAA@BBB_2026-11-22",
            markets={"total_under_240.5": 0.70},
            totals=[_tangga(240.5, 80.0)],
        )
        kaki = _kaki("AAA@BBB_2026-11-22", 240.5, 80.0, p_model_gemini=0.99)
        tiket = _tiket("insurance", [kaki])
        hasil = self._audit(tiket, [art])
        kaki_hasil = hasil["legs"][0]
        self.assertEqual(kaki_hasil["p_model"], 0.70)
        self.assertEqual(kaki_hasil["p_model_file_tiket"], 0.99)
        self.assertIn("Gemini", kaki_hasil["p_model_file_tiket_catatan"])
        self.assertEqual(kaki_hasil["verdict"], "JANGAN_PASANG")

    def test_lean_ke_market_asuransi_blokir(self):
        # Median 220 vs garis market 228,5 (gap 8,5 > 5); probabilitas
        # pasar 72% < 74% -> JANGAN_PASANG di Asuransi.
        art = _artefak(
            "AAA@BBB_2026-11-22",
            median=220.0,
            main_line=228.5,
            markets={"total_under_240.5": 0.86},
            totals=[_tangga(240.5, 72.0)],
        )
        tiket = _tiket("insurance", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)])
        hasil = self._audit(tiket, [art])
        kaki = hasil["legs"][0]
        self.assertTrue(kaki["lean"]["berlaku"])
        self.assertAlmostEqual(kaki["lean"]["gap_points"], 8.5)
        self.assertAlmostEqual(kaki["lean"]["probabilitas_pasar"], 0.72)
        self.assertTrue(kaki["lean"]["di_bawah_target"])
        self.assertEqual(kaki["verdict"], "JANGAN_PASANG")

    def test_lean_ke_market_asuransi_lolos_bila_pasar_cukup(self):
        # Gap 8,5 > 5 tapi probabilitas pasar 80% >= 74% -> lolos.
        art = _artefak(
            "AAA@BBB_2026-11-22",
            median=220.0,
            main_line=228.5,
            markets={"total_under_240.5": 0.86},
            totals=[_tangga(240.5, 80.0)],
        )
        tiket = _tiket("insurance", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)])
        hasil = self._audit(tiket, [art])
        kaki = hasil["legs"][0]
        self.assertTrue(kaki["lean"]["berlaku"])
        self.assertFalse(kaki["lean"]["di_bawah_target"])
        self.assertEqual(kaki["verdict"], "LOLOS")

    def test_lean_utama_hanya_perhatian(self):
        # Gap 8,5; probabilitas pasar 60% < 65% (Utama) -> PERHATIAN.
        art = _artefak(
            "AAA@BBB_2026-11-22",
            median=220.0,
            main_line=228.5,
            markets={"total_under_240.5": 0.86},
            totals=[_tangga(240.5, 60.0)],
        )
        tiket = _tiket("main", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)])
        hasil = self._audit(tiket, [art])
        self.assertEqual(hasil["legs"][0]["verdict"], "PERHATIAN")
        self.assertEqual(hasil["verdict"], "GO")

    def test_agregat_peluang_ev_terlemah(self):
        art1 = _artefak(
            "AAA@BBB_2026-11-22",
            markets={"total_under_240.5": 0.80},
            totals=[_tangga(240.5, 75.0)],
        )
        art2 = _artefak(
            "CCC@DDD_2026-11-22",
            markets={"total_under_230.5": 0.90},
            totals=[_tangga(230.5, 75.0)],
        )
        tiket = _tiket(
            "main",
            [
                _kaki("AAA@BBB_2026-11-22", 240.5, 75.0),
                _kaki("CCC@DDD_2026-11-22", 230.5, 75.0),
            ],
            multiplier=2.0,
        )
        hasil = self._audit(tiket, [art1, art2])
        self.assertAlmostEqual(hasil["p_gabungan"], 0.72)
        self.assertAlmostEqual(hasil["ev"], 0.44)
        self.assertEqual(hasil["kaki_terlemah"]["match_id"], "AAA@BBB_2026-11-22")
        self.assertEqual(hasil["kaki_terlemah"]["p_model"], 0.80)
        self.assertEqual(hasil["verdict"], "GO")

    def test_tipe_nama_indonesia_diterima(self):
        art = _artefak(
            "AAA@BBB_2026-11-22",
            markets={"total_under_240.5": 0.86},
            totals=[_tangga(240.5, 80.0)],
        )
        tiket = _tiket("Utama", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)])
        hasil = self._audit(tiket, [art])
        self.assertEqual(hasil["type"], "main")
        self.assertEqual(hasil["legs"][0]["verdict"], "LOLOS")

    def test_tipe_tidak_dikenal_data_incomplete(self):
        art = _artefak(
            "AAA@BBB_2026-11-22",
            markets={"total_under_240.5": 0.86},
            totals=[_tangga(240.5, 80.0)],
        )
        tiket = _tiket("misteri", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)])
        hasil = self._audit(tiket, [art])
        self.assertEqual(hasil["verdict"], "NO-GO")
        self.assertEqual(hasil["legs"][0]["verdict"], "DATA_INCOMPLETE")

    def test_pasangan_insurance_main(self):
        art = _artefak(
            "AAA@BBB_2026-11-22",
            markets={"total_under_240.5": 0.86, "total_under_238.5": 0.83},
            totals=[_tangga(240.5, 80.0), _tangga(238.5, 78.0)],
        )
        dokumen = {
            "format": "ticket",
            "insurance": _tiket(
                "insurance", [_kaki("AAA@BBB_2026-11-22", 240.5, 80.0)]
            ),
            "main": _tiket("main", [_kaki("AAA@BBB_2026-11-22", 238.5, 78.0)]),
        }
        hasil = ticket_audit.audit_tickets(dokumen, [art], cfg=CFG)
        self.assertEqual(len(hasil["tickets"]), 2)
        self.assertEqual([t["type"] for t in hasil["tickets"]], ["insurance", "main"])

    def test_file_tiket_tidak_dikenali(self):
        hasil = ticket_audit.audit_tickets({"bukan": "tiket"}, [], cfg=CFG)
        self.assertIn("error", hasil)
        self.assertEqual(hasil["tickets"], [])

    def test_render_teks(self):
        art = _artefak(
            "ORL@WAS_2026-11-22",
            markets={"total_under_235.5": 0.78346},
            totals=[_tangga(235.5, 80.0)],
        )
        tiket = _tiket("main", [_kaki("ORL@WAS_2026-11-22", 235.5, 83.0)])
        hasil = ticket_audit.audit_tickets(tiket, [art], cfg=CFG)
        teks = ticket_audit.render_audit_text(hasil)
        self.assertIn("AUDIT TIKET", teks)
        self.assertIn("TIKET UTAMA", teks)
        self.assertIn("OVERPAY", teks)
        self.assertIn("Verdict: GO", teks)
        self.assertIn("simulasi mesin", teks)


class TestSharpMoveBukanDiskon(unittest.TestCase):
    """Sharp move BUKAN diskon di audit (keputusan user 2026-11-23).

    Harga tiket vs harga saat analisis untuk garis yang sama;
    |selisih| >= 3¢ -> PERHATIAN (lunak) + DISKON_DITEKAN +
    "Kenapa beda?" wajib. Pola Thunder: 75¢ -> 71¢.
    """

    def _artefak_thunder(self, harga_analisis=75.0, p_model=0.78, sumber="snapshot"):
        art = _artefak(
            "OKC@DEN_2026-11-15",
            median=224.0,
            main_line=225.5,
            markets={"total_under_227.5": p_model},
            totals=[_tangga(227.5, 75.0, volume_usd=8000.0, thin=False)],
        )
        if sumber == "snapshot":
            art["price_snapshots"] = {
                "total_under_227.5": {
                    "cents": harga_analisis,
                    "at": "2026-11-15T10:00:00+00:00",
                }
            }
        elif sumber == "kaki":
            art["legs"] = [
                {
                    "leg_id": "OKC@DEN_2026-11-15:total_under_227.5:main",
                    "market_type": "total_under",
                    "line": 227.5,
                    "ticket": "main",
                    "price_cents": harga_analisis,
                    "jup_estimated_cents": harga_analisis,
                }
            ]
        return art

    def _audit(self, art, harga_tiket, tipe="main"):
        tiket = _tiket(tipe, [_kaki("OKC@DEN_2026-11-15", 227.5, harga_tiket)])
        hasil = ticket_audit.audit_tickets(tiket, [art], cfg=CFG)
        return hasil["tickets"][0]["legs"][0]

    def _gate(self, kaki, nama):
        return next(g for g in kaki["gates"] if g["gate"] == nama)

    def test_thunder_literal_diskon_ditekan(self):
        # Pola Thunder persis: analisis 75¢, tiket 71¢ (gerak -4¢).
        # Label TIDAK BOLEH DISKON polos meski EV +9,9%.
        kaki = self._audit(self._artefak_thunder(), 71.0)
        self.assertTrue(kaki["sharp_move"])
        self.assertEqual(kaki["harga_analisis_cents"], 75.0)
        self.assertEqual(kaki["gerak_harga_cents"], -4.0)
        self.assertEqual(kaki["price_label"], "DISKON_DITEKAN")
        self.assertNotEqual(kaki["price_label"], "DISKON")
        self.assertIn("SHARP_MOVE", kaki["flags"])
        self.assertTrue(kaki["kenapa_beda_required"])
        self.assertTrue(
            any("harga bergerak tajam sejak analisis" in a for a in kaki["alasan"]),
            kaki["alasan"],
        )
        self.assertFalse(self._gate(kaki, "sharp_move")["lolos"])
        # Verdict JANGAN_PASANG di sini berasal dari gate lantai harga
        # yang sudah ada (71¢ < lantai 75¢) — BUKAN dari sharp move;
        # kontribusi sharp move sendiri lunak (lihat tes murni di bawah).
        self.assertEqual(kaki["verdict"], "JANGAN_PASANG")
        self.assertTrue(
            any("di bawah lantai" in a for a in kaki["alasan"]), kaki["alasan"]
        )

    def test_sharp_move_murni_perhatian(self):
        # Isolasi: satu-satunya alasan lunak adalah sharp move
        # (80¢ -> 76¢, gerak -4¢; harga di atas lantai, edge +6%
        # di atas ambang edge tipis, volume tidak tipis).
        kaki = self._audit(
            self._artefak_thunder(harga_analisis=80.0, p_model=0.82), 76.0
        )
        self.assertEqual(kaki["verdict"], "PERHATIAN")
        self.assertEqual(kaki["price_label"], "DISKON_DITEKAN")
        self.assertTrue(kaki["kenapa_beda_required"])
        self.assertEqual(len(kaki["alasan"]), 1)
        self.assertTrue(
            kaki["alasan"][0].startswith("harga bergerak tajam sejak analisis")
        )

    def test_harga_analisis_dari_kaki(self):
        # Tanpa snapshot: harga analisis dari kaki analisis (prioritas
        # kedua, sama seperti recheck).
        kaki = self._audit(self._artefak_thunder(sumber="kaki"), 71.0)
        self.assertTrue(kaki["sharp_move"])
        self.assertEqual(kaki["harga_analisis_cents"], 75.0)
        self.assertEqual(kaki["price_label"], "DISKON_DITEKAN")

    def test_tanpa_harga_analisis_tidak_ditekan(self):
        # Keterbatasan data (jujur): tanpa snapshot maupun harga kaki,
        # gerak tidak bisa dinilai — label TIDAK ditekan dan gate
        # mencatat tidak bisa dinilai (bukan bukti tidak ada gerak).
        kaki = self._audit(self._artefak_thunder(sumber=None), 71.0)
        self.assertFalse(kaki["sharp_move"])
        self.assertIsNone(kaki["harga_analisis_cents"])
        self.assertIsNone(kaki["gerak_harga_cents"])
        self.assertEqual(kaki["price_label"], "DISKON")
        self.assertFalse(kaki["kenapa_beda_required"])
        gate = self._gate(kaki, "sharp_move")
        self.assertIn("tidak bisa dinilai", gate["detail"])

    def test_gerak_kecil_tidak_ditekan(self):
        # Gerak 1¢ (75¢ -> 74¢) di bawah ambang sharp: bukan anomali,
        # DISKON polos boleh.
        kaki = self._audit(self._artefak_thunder(), 74.0)
        self.assertFalse(kaki["sharp_move"])
        self.assertEqual(kaki["gerak_harga_cents"], -1.0)
        self.assertEqual(kaki["price_label"], "DISKON")
        self.assertTrue(self._gate(kaki, "sharp_move")["lolos"])

    def test_tepat_ambang_sharp_ditekan(self):
        # Tepat 3¢ (75¢ -> 72¢) = sharp (>= 3¢, D9).
        kaki = self._audit(self._artefak_thunder(), 72.0)
        self.assertTrue(kaki["sharp_move"])
        self.assertEqual(kaki["price_label"], "DISKON_DITEKAN")

    def test_render_teks_penanda_sharp_move(self):
        art = self._artefak_thunder(harga_analisis=80.0, p_model=0.82)
        tiket = _tiket("main", [_kaki("OKC@DEN_2026-11-15", 227.5, 76.0)])
        hasil = ticket_audit.audit_tickets(tiket, [art], cfg=CFG)
        teks = ticket_audit.render_audit_text(hasil)
        self.assertIn("[harga bergerak tajam]", teks)
        self.assertIn("harga bergerak tajam sejak analisis", teks)


class TestAmbangEdgeTipisDariConfig(unittest.TestCase):
    """Ambang edge tipis audit dibaca dari playstyle.yaml (koordinator).

    Aturan repo: semua threshold hanya di config. Bila kunci hilang,
    default 5% dipakai dengan sumber dicatat (bukan diam-diam).
    """

    def _den_tipis(self):
        art = _artefak(
            "DEN@CHI_2026-11-22",
            markets={"total_under_252.5": 0.84474},
            totals=[_tangga(252.5, 81.0)],
        )
        tiket = _tiket("insurance", [_kaki("DEN@CHI_2026-11-22", 252.5, 82.0)])
        return tiket, [art]

    def test_ambang_dibaca_dari_config(self):
        cfg = copy.deepcopy(CFG)
        cfg["audit"]["edge_tipis_pct"] = 1.0
        tiket, arts = self._den_tipis()
        hasil = ticket_audit.audit_tickets(tiket, arts, cfg=cfg)
        self.assertEqual(hasil["ambang_edge_tipis_pct"], 1.0)
        self.assertIn("config", hasil["ambang_edge_tipis_sumber"])
        kaki = hasil["tickets"][0]["legs"][0]
        # Edge +2,47% di atas ambang 1% -> bukan perhatian lagi.
        self.assertEqual(kaki["verdict"], "LOLOS")
        self.assertFalse(any("edge tipis" in a for a in kaki["alasan"]))

    def test_kunci_hilang_pakai_default_tercatat(self):
        cfg = copy.deepcopy(CFG)
        cfg.pop("audit", None)
        tiket, arts = self._den_tipis()
        hasil = ticket_audit.audit_tickets(tiket, arts, cfg=cfg)
        self.assertEqual(hasil["ambang_edge_tipis_pct"], 5.0)
        self.assertIn("default", hasil["ambang_edge_tipis_sumber"])
        kaki = hasil["tickets"][0]["legs"][0]
        self.assertEqual(kaki["verdict"], "PERHATIAN")
        self.assertTrue(any("edge tipis" in a for a in kaki["alasan"]))


def _cdf_normal(median, sigma, garis_min, garis_max, langkah=2.0):
    """CDF total normal (median, sigma) sebagai sim markets.

    Garis-garis tangga tiap ``langkah`` poin; peluang dibulatkan
    6 desimal seperti output sim. (Duplikat kecil dari
    tests/test_ticket_composer.py — kedua file tes independen.)
    """
    markets = {}
    n = int(round((garis_max - garis_min) / langkah)) + 1
    for i in range(n):
        garis = garis_min + i * langkah
        z = (garis - median) / sigma
        p = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        markets[f"total_under_{garis:g}"] = round(p, 6)
    return markets


def _artefak_den_stress():
    """Artefak DEN@CHI sintetis (median 233, sigma 19,2).

    Jangkar P normal U252,5 = 84,5%, P banjir FT ~54,1%,
    P setan ~53,0% — mirip artefak nyata
    out/stress_den_chi_2026-11-22.json. Tangga: 252,5 tidak thin
    (supaya verdict tidak terkunci JANGAN_PASANG oleh volume).
    """
    return _artefak(
        "DEN@CHI_2026-11-22",
        median=233.0,
        main_line=236.5,
        markets=_cdf_normal(233.0, 19.2, 202.5, 278.5),
        totals=[
            _tangga(250.5, 79.0, volume_usd=500.0, thin=False),
            _tangga(252.5, 81.0, volume_usd=500.0, thin=False),
            _tangga(264.5, 94.0, volume_usd=None, thin=True),
        ],
    )


class TestAuditSkenarioPanas(unittest.TestCase):
    """P banjir + P setan per kaki di output audit (tampilan saja).

    BUKAN gate: angka-angka ini tidak memengaruhi verdict — tes
    menegaskan verdict tetap seperti tanpa tampilan stress.
    """

    def test_p_banjir_dan_p_setan_tampil_json(self):
        art = _artefak_den_stress()
        tiket = _tiket("insurance", [_kaki("DEN@CHI_2026-11-22", 252.5, 82.0)])
        hasil = ticket_audit.audit_tickets(tiket, [art], cfg=CFG)
        kaki = hasil["tickets"][0]["legs"][0]
        self.assertAlmostEqual(kaki["p_banjir"], 0.541, delta=0.01)
        self.assertAlmostEqual(kaki["p_setan"], 0.530, delta=0.01)
        self.assertIsNone(kaki["stress_alasan"])
        # Verdict tidak berubah karena tampilan stress: edge +2,5%
        # tipis -> PERHATIAN (bukan JANGAN_PASANG).
        self.assertEqual(kaki["verdict"], "PERHATIAN")

    def test_p_banjir_dan_p_setan_tampil_teks(self):
        art = _artefak_den_stress()
        tiket = _tiket("insurance", [_kaki("DEN@CHI_2026-11-22", 252.5, 82.0)])
        hasil = ticket_audit.audit_tickets(tiket, [art], cfg=CFG)
        teks = ticket_audit.render_audit_text(hasil)
        self.assertIn("banjir terburuk 54,1%", teks)
        self.assertIn("skenario setan 53,0%", teks)

    def test_kaki_utama_juga_menampilkan_p_banjir_p_setan(self):
        # Kaki Utama TIDAK kena gate banjir, tapi P banjir + P setan
        # tetap WAJIB tampil di audit.
        art = _artefak_den_stress()
        tiket = _tiket("main", [_kaki("DEN@CHI_2026-11-22", 250.5, 79.0)])
        hasil = ticket_audit.audit_tickets(tiket, [art], cfg=CFG)
        kaki = hasil["tickets"][0]["legs"][0]
        self.assertAlmostEqual(kaki["p_banjir"], 0.499, delta=0.01)
        self.assertAlmostEqual(kaki["p_setan"], 0.488, delta=0.01)
        teks = ticket_audit.render_audit_text(hasil)
        self.assertIn("banjir terburuk 49,9%", teks)
        self.assertIn("skenario setan 48,8%", teks)

    def test_garis_tiket_di_luar_kaki_analisis_tetap_dihitung(self):
        # Tiket luar (Gemini): garis 252,5 tidak ada di kaki
        # analisis (hanya kaki Utama 250,5) -> dihitung eksplisit.
        art = _artefak_den_stress()
        art["legs"] = [
            {
                "leg_id": "DEN@CHI_2026-11-22:total_under_250.5:main",
                "market_type": "total_under",
                "line": 250.5,
                "ticket": "main",
            }
        ]
        tiket = _tiket("insurance", [_kaki("DEN@CHI_2026-11-22", 252.5, 82.0)])
        hasil = ticket_audit.audit_tickets(tiket, [art], cfg=CFG)
        kaki = hasil["tickets"][0]["legs"][0]
        self.assertAlmostEqual(kaki["p_banjir"], 0.541, delta=0.01)
        self.assertAlmostEqual(kaki["p_setan"], 0.530, delta=0.01)

    def test_setan_belum_ada_tidak_crash(self):
        # Output stress tanpa kunci "setan" (sebelum Worker A
        # selesai): banjir tetap tampil, setan "belum tersedia".
        art = _artefak_den_stress()
        tiket = _tiket("insurance", [_kaki("DEN@CHI_2026-11-22", 252.5, 82.0)])
        nyata = ticket_audit.stress_mod.skenario_panas

        def tanpa_setan(*args, **kwargs):
            hasil = nyata(*args, **kwargs)
            for entri in hasil.get("kaki") or []:
                (entri.get("p_under") or {}).pop("setan", None)
            return hasil

        with mock.patch.object(
            ticket_audit.stress_mod, "skenario_panas", side_effect=tanpa_setan
        ):
            hasil = ticket_audit.audit_tickets(tiket, [art], cfg=CFG)
        kaki = hasil["tickets"][0]["legs"][0]
        self.assertAlmostEqual(kaki["p_banjir"], 0.541, delta=0.01)
        self.assertIsNone(kaki["p_setan"])
        teks = ticket_audit.render_audit_text(hasil)
        self.assertIn("banjir terburuk 54,1%", teks)
        self.assertIn("skenario setan belum tersedia", teks)

    def test_skenario_gagal_tidak_menggagalkan_audit(self):
        # skenario_panas melempar -> p None + alasan, audit tetap
        # jalan dan verdict tetap dihitung.
        art = _artefak_den_stress()
        tiket = _tiket("insurance", [_kaki("DEN@CHI_2026-11-22", 252.5, 82.0)])
        with mock.patch.object(
            ticket_audit.stress_mod,
            "skenario_panas",
            side_effect=ValueError("CDF rusak"),
        ):
            hasil = ticket_audit.audit_tickets(tiket, [art], cfg=CFG)
        kaki = hasil["tickets"][0]["legs"][0]
        self.assertIsNone(kaki["p_banjir"])
        self.assertIsNone(kaki["p_setan"])
        self.assertIn("CDF rusak", kaki["stress_alasan"])
        self.assertEqual(kaki["verdict"], "PERHATIAN")
        teks = ticket_audit.render_audit_text(hasil)
        self.assertIn("Skenario panas tidak bisa dihitung", teks)


if __name__ == "__main__":
    unittest.main()
