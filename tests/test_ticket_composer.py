"""Tes engine/ticket_composer.py — SEMUA offline dari fixture, 0 kredit Odds API.

Slate standar: 4 laga, tiap laga dua kaki Alt Under —
- Asuransi: Under 235.5 @ 75c, p_model 0,80, p_market 0,78 -> p_final 0,786.
  3 kaki -> pengali (100/75)^3 x 0,945 = 2,24 (target Asuransi 2,2-2,5).
- Utama: Under 231.5 @ 72c, p_model 0,76, p_market 0,74 -> p_final 0,746.
  4 kaki -> pengali (100/72)^4 x 0,945 = 3,52 (target Utama 3,5-5,0).
Median 224 vs garis market 225,5 (selisih 1,5 < 5,0 — aturan
condong-ke-market tidak terpicu) kecuali di tes condong.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from engine import ticket_composer

REPO_ROOT = Path(__file__).resolve().parent.parent
SKEMA_TIKET = json.loads((REPO_ROOT / "schemas" / "ticket.schema.json").read_text())

CFG = config.load_playstyle()

LAGA = [
    "DET@ATL_2026-11-22",
    "BOS@NYK_2026-11-22",
    "LAL@GSW_2026-11-22",
    "MIA@CHI_2026-11-22",
]
SEKARANG = "2026-11-22T13:00:00+00:00"


def label_dari_ev(ev_pct):
    """Label harga dari EV (ambang config: DISKON >= +2, MAHAL < -2)."""
    if ev_pct >= 2.0:
        return "DISKON"
    if ev_pct < -2.0:
        return "MAHAL"
    return "WAJAR"


def buat_kaki(
    match_id,
    ticket,
    line,
    p_model,
    p_market,
    harga,
    label=None,
    meets=True,
    reason=None,
    tanpa_ticket=False,
):
    """Satu kaki artefak nba_analysis (bentuk _rakit_kaki)."""
    p_final = None
    ev_pct = None
    if p_model is not None:
        # Blend w=0,3 (config blend.w_model); tanpa p_market -> MODEL_ONLY.
        p_final = (
            round(0.3 * p_model + 0.7 * p_market, 3)
            if p_market is not None
            else p_model
        )
        ev_pct = round((p_final * (100.0 / harga) - 1.0) * 100.0, 2)
    kaki = {
        "leg_id": (
            f"{match_id}:total_under_{line:g}:{ticket}"
            if line is not None
            else f"{match_id}:total_under_none:{ticket}"
        ),
        "market_type": "total_under",
        "line": line,
        "p_model": p_model,
        "p_market": p_market,
        "comparison_source": "kalshi" if p_market is not None else None,
        "p_final": p_final,
        "price_cents": harga,
        "jup_estimated_cents": harga,
        "ev_pct": ev_pct,
        "price_label": (
            label
            if label is not None
            else (label_dari_ev(ev_pct) if ev_pct is not None else None)
        ),
        "cushion_vs_median_points": 14.5,
        "cushion_vs_market_points": 8.0,
        "meets": meets,
        "reason": reason,
        "fetched_at": "2026-11-22T10:00:00+00:00",
    }
    if not tanpa_ticket:
        kaki["ticket"] = ticket
    return kaki


def buat_analisis(
    match_id,
    kaki_ins=None,
    kaki_main=None,
    median=224.0,
    garis_market=225.5,
    status="OK",
    game_date="2026-11-22",
    generated_at="2026-11-22T10:00:00+00:00",
):
    """Satu artefak nba_analysis minimal (kaki standar bila tidak diberi)."""
    if kaki_ins is None:
        kaki_ins = buat_kaki(match_id, "insurance", 235.5, 0.80, 0.78, 75.0)
    if kaki_main is None:
        kaki_main = buat_kaki(match_id, "main", 231.5, 0.76, 0.74, 72.0)
    legs = [kaki_ins, kaki_main]
    markets = {}
    for kaki in legs:
        if kaki["line"] is not None and kaki["p_model"] is not None:
            markets[f"total_under_{kaki['line']:g}"] = kaki["p_model"]
    return {
        "format": "nba_analysis",
        "format_version": 1,
        "match_id": match_id,
        "home_tricode": match_id.split("@")[1].split("_")[0],
        "away_tricode": match_id.split("@")[0],
        "game_date": game_date,
        "generated_at": generated_at,
        "status": status,
        "legs": legs,
        "simulation": {
            "score_distribution": {"total": {"median": median}},
            "markets": markets,
        },
        "market": {"main_total_line": garis_market},
    }


def slate_standar(laga=LAGA):
    """Slate 4 laga standar (semua kaki lolos, garis berbeda)."""
    return [buat_analisis(m) for m in laga]


def buat_kaki_recheck(
    kaki,
    verdict="TETAP_OK",
    reasons=None,
    prob_used="model",
    prob_value=None,
    kenapa_beda=None,
):
    """Satu kaki laporan recheck (bentuk decide())."""
    return {
        "leg_id": kaki["leg_id"],
        "verdict": verdict,
        "reasons": list(reasons or []),
        "old_line": kaki["line"],
        "new_line": kaki["line"],
        "old_price_cents": kaki["price_cents"],
        "new_price_cents": kaki["price_cents"],
        "price_move_cents": 0.0,
        "resimulated": False,
        "probability_used": prob_used,
        "probability_value": prob_value if prob_value is not None else kaki["p_final"],
        "kenapa_beda": kenapa_beda
        or {
            "gap_points": 1.5,
            "triggered": False,
            "reason_found": False,
            "reason": None,
        },
    }


def buat_recheck(analisis, putusan=None, recheck_at="2026-11-22T12:30:00+00:00"):
    """Laporan recheck untuk satu analisis.

    putusan: {ticket: (verdict, reasons, prob_used, prob_value)} —
    default semua TETAP_OK.
    """
    putusan = putusan or {}
    legs = []
    for kaki in analisis["legs"]:
        tiket = kaki.get("ticket") or kaki["leg_id"].rsplit(":", 1)[-1]
        verdict, reasons, prob_used, prob_value = putusan.get(
            tiket, ("TETAP_OK", [], "model", None)
        )
        legs.append(buat_kaki_recheck(kaki, verdict, reasons, prob_used, prob_value))
    ada_tolak = any(k["verdict"] in ("JANGAN_PASANG", "DATA_INCOMPLETE") for k in legs)
    return {
        "format": "nba_recheck",
        "format_version": 1,
        "match_id": analisis["match_id"],
        "analysis_generated_at": analisis["generated_at"],
        "recheck_at": recheck_at,
        "verdict": "NO_GO" if ada_tolak else "GO",
        "resimulated": False,
        "resim_reasons": [],
        "changes": [],
        "legs": legs,
        "anomalies": [],
        "missing": [],
        "attention": [],
        "action_required": None,
    }


def recheck_semua_ok(analyses, recheck_at="2026-11-22T12:30:00+00:00"):
    """Recheck TETAP_OK untuk semua analisis (30 menit sebelum SEKARANG)."""
    return [buat_recheck(a, recheck_at=recheck_at) for a in analyses]


class TestRacikStandar(unittest.TestCase):
    def test_dua_tiket_dari_slate_standar(self):
        analyses = slate_standar()
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        ins, main = hasil["insurance"], hasil["main"]
        self.assertIsNotNone(ins)
        self.assertIsNotNone(main)
        self.assertIsNone(hasil["insurance_reason"])
        self.assertIsNone(hasil["main_reason"])
        # Stake 50/50 dari 20.
        self.assertEqual(ins["stake"], 10)
        self.assertEqual(main["stake"], 10)
        # Pengali: Asuransi 3 kaki @75c = 2,24; Utama 4 kaki @72c = 3,52.
        self.assertAlmostEqual(ins["multiplier"], 2.24, places=2)
        self.assertAlmostEqual(main["multiplier"], 3.5166, places=3)
        self.assertEqual(len(ins["legs"]), 3)
        self.assertEqual(len(main["legs"]), 4)
        # ID unik per tanggal.
        self.assertEqual(ins["ticket_id"], "tkt-2026-11-22-ins")
        self.assertEqual(main["ticket_id"], "tkt-2026-11-22-utm")
        self.assertEqual(ins["type"], "Asuransi")
        self.assertEqual(main["type"], "Utama")
        # P menang = Π p_final (laga berbeda = independen).
        self.assertAlmostEqual(ins["metrics"]["p_win"], 0.786**3, places=3)
        self.assertAlmostEqual(main["metrics"]["p_win"], 0.746**4, places=3)
        # EV tiket = P x pengali - 1.
        self.assertAlmostEqual(
            ins["metrics"]["combined_ev_pct"], (0.786**3 * 2.24 - 1) * 100, places=1
        )
        self.assertEqual(ins["combo_spread_pct"], 5.5)
        self.assertEqual(main["combo_spread_pct"], 5.5)
        # Ringkasan menyebut kedua tiket + pengali.
        self.assertIn("ASURANSI", hasil["summary"])
        self.assertIn("UTAMA", hasil["summary"])
        self.assertIn("x2.24", hasil["summary"])
        self.assertEqual(hasil["warnings"], [])

    def test_tiket_valid_terhadap_skema(self):
        analyses = slate_standar()
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        for tiket in (hasil["insurance"], hasil["main"]):
            jsonschema.validate(instance=tiket, schema=SKEMA_TIKET)
            self.assertIsNone(ticket_composer.validate_ticket(tiket))
            for kaki in tiket["legs"]:
                self.assertEqual(kaki["sport"], "nba")
                self.assertEqual(kaki["market"], "total_under")
                self.assertEqual(kaki["status"], "OK")
                self.assertEqual(kaki["jup_provider"], "polymarket")

    def test_validate_ticket_menolak_tiket_rusak(self):
        analyses = slate_standar()
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        rusak = copy.deepcopy(hasil["insurance"])
        del rusak["stake"]
        self.assertIsNotNone(ticket_composer.validate_ticket(rusak))
        rusak = copy.deepcopy(hasil["insurance"])
        rusak["multiplier"] = 1.0
        self.assertIsNotNone(ticket_composer.validate_ticket(rusak))
        rusak = copy.deepcopy(hasil["insurance"])
        rusak["legs"] = []
        self.assertIsNotNone(ticket_composer.validate_ticket(rusak))

    def test_stake_total_wajib(self):
        analyses = slate_standar()
        with self.assertRaises(ValueError):
            ticket_composer.compose_tickets(analyses, None, CFG)
        with self.assertRaises(ValueError):
            ticket_composer.compose_tickets(analyses, None, CFG, stake_total=0)
        with self.assertRaises(ValueError):
            ticket_composer.compose_tickets(analyses, None, CFG, stake_total=-5)

    def test_tanpa_analisis(self):
        hasil = ticket_composer.compose_tickets(
            [], None, CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNone(hasil["insurance"])
        self.assertIsNone(hasil["main"])
        self.assertIn("Tidak ada analisis", hasil["insurance_reason"])

    def test_config_main_maks_5_target_4(self):
        # Perubahan config Langkah 3 (profil user 2026-11-22); versi
        # config kini 11 (Langkah 4 menambah section live, Langkah 5
        # menambah section soccer).
        self.assertEqual(CFG["meta"]["version"], 11)
        self.assertEqual(CFG["tickets"]["main"]["multiplier_max"], 5.0)
        self.assertEqual(CFG["tickets"]["main"]["target_multiplier_max"], 4.0)

    def test_kaki_tanpa_kunci_ticket_dibaca_dari_leg_id(self):
        # Laporan/kaki lama tanpa kunci "ticket" — tiket diturunkan dari
        # akhir leg_id seperti yang dilakukan CLI.
        analyses = slate_standar()
        for analisis in analyses:
            for kaki in analisis["legs"]:
                del kaki["ticket"]
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNotNone(hasil["insurance"])
        self.assertIsNotNone(hasil["main"])


class TestGarisBerbeda(unittest.TestCase):
    def test_garis_sama_hanya_masuk_asuransi(self):
        # Satu laga garis Asuransi = garis Utama (233.5); 4 laga standar.
        laga_x = "AAA@BBB_2026-11-22"
        analisis_x = buat_analisis(
            laga_x,
            kaki_ins=buat_kaki(laga_x, "insurance", 233.5, 0.80, 0.78, 75.0),
            kaki_main=buat_kaki(laga_x, "main", 233.5, 0.76, 0.74, 72.0),
        )
        analyses = [analisis_x] + slate_standar()
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        ins, main = hasil["insurance"], hasil["main"]
        self.assertIsNotNone(ins)
        self.assertIsNotNone(main)
        laga_ins = {k["match_id"] for k in ins["legs"]}
        laga_main = {k["match_id"] for k in main["legs"]}
        self.assertIn(laga_x, laga_ins)
        self.assertNotIn(laga_x, laga_main)
        self.assertIn("hanya masuk Asuransi", hasil["summary"])
        self.assertIn("garisnya sama", hasil["summary"])

    def test_garis_asuransi_lebih_rendah_dari_utama(self):
        # Artefak aneh: garis Asuransi (230.5) LEBIH RENDAH dari Utama
        # (234.5) — laga hanya boleh masuk satu tiket (Asuransi).
        laga_x = "AAA@BBB_2026-11-22"
        analisis_x = buat_analisis(
            laga_x,
            kaki_ins=buat_kaki(laga_x, "insurance", 230.5, 0.80, 0.78, 75.0),
            kaki_main=buat_kaki(laga_x, "main", 234.5, 0.76, 0.74, 72.0),
        )
        analyses = [analisis_x] + slate_standar()
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        laga_main = {k["match_id"] for k in hasil["main"]["legs"]}
        self.assertNotIn(laga_x, laga_main)
        self.assertIn("tidak lebih aman", hasil["summary"])

    def test_garis_berbeda_boleh_dua_tiket(self):
        # Slate standar: garis Asuransi 235.5 > Utama 231.5 — laga boleh
        # masuk kedua tiket.
        analyses = slate_standar()
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        laga_main = {k["match_id"] for k in hasil["main"]["legs"]}
        self.assertTrue(laga_ins & laga_main)
        for match_id in laga_ins & laga_main:
            garis_ins = next(
                k for k in hasil["insurance"]["legs"] if k["match_id"] == match_id
            )
            garis_main = next(
                k for k in hasil["main"]["legs"] if k["match_id"] == match_id
            )
            # Garis dibaca dari selection "Under <garis> (...)".
            self.assertGreater(
                float(garis_ins["selection"].split()[1]),
                float(garis_main["selection"].split()[1]),
            )


class TestCondongKeMarket(unittest.TestCase):
    def test_tanpa_recheck_market_rendah_kaki_asuransi_gugur(self):
        # Median 219 vs garis market 225,5 (selisih 6,5 > 5,0), harga
        # market 70c -> probabilitas market 0,70 < 0,74: kaki Asuransi
        # gugur, kaki Utama tetap lolos.
        laga_x = "AAA@BBB_2026-11-22"
        analisis_x = buat_analisis(
            laga_x,
            kaki_ins=buat_kaki(laga_x, "insurance", 235.5, 0.80, 0.78, 70.0),
            kaki_main=buat_kaki(laga_x, "main", 231.5, 0.76, 0.74, 72.0),
            median=219.0,
        )
        analyses = [analisis_x] + slate_standar()
        hasil = ticket_composer.compose_tickets(
            analyses, None, CFG, stake_total=20, now=SEKARANG
        )
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        laga_main = {k["match_id"] for k in hasil["main"]["legs"]}
        self.assertNotIn(laga_x, laga_ins)
        self.assertIn(laga_x, laga_main)
        self.assertIn("condong-ke-market", hasil["summary"])

    def test_tanpa_recheck_market_cukup_probabilitas_market_dipakai(self):
        # Selisih 6,5 > 5,0 tapi harga market 76c (0,76 >= 0,74): kaki
        # Asuransi lolos dengan probabilitas keputusan = harga market.
        laga_x = "AAA@BBB_2026-11-22"
        analisis_x = buat_analisis(
            laga_x,
            kaki_ins=buat_kaki(laga_x, "insurance", 235.5, 0.80, 0.78, 76.0),
            kaki_main=buat_kaki(laga_x, "main", 231.5, 0.76, 0.74, 72.0),
            median=219.0,
        )
        analyses = [analisis_x] + slate_standar(LAGA[:2])
        hasil = ticket_composer.compose_tickets(
            analyses, None, CFG, stake_total=20, now=SEKARANG
        )
        ins = hasil["insurance"]
        self.assertIsNotNone(ins)
        self.assertEqual(len(ins["legs"]), 3)
        # P menang memakai 0,76 (market) untuk laga X, bukan 0,786.
        self.assertAlmostEqual(ins["metrics"]["p_win"], 0.76 * 0.786 * 0.786, places=3)
        self.assertIn("probabilitas market", hasil["summary"])

    def test_dengan_recheck_probabilitas_market_dipakai(self):
        # Recheck sudah menerapkan condong: probability_used=market,
        # value 0,80, TETAP_OK -> peracik memakai 0,80.
        laga_x = "AAA@BBB_2026-11-22"
        analisis_x = buat_analisis(laga_x, median=219.0)
        analyses = [analisis_x] + slate_standar(LAGA[:2])
        rechecks = []
        for analisis in analyses:
            if analisis["match_id"] == laga_x:
                rechecks.append(
                    buat_recheck(
                        analisis,
                        putusan={
                            "insurance": (
                                "TETAP_OK",
                                [],
                                "market",
                                0.80,
                            )
                        },
                    )
                )
            else:
                rechecks.append(buat_recheck(analisis))
        hasil = ticket_composer.compose_tickets(
            analyses, rechecks, CFG, stake_total=20, now=SEKARANG
        )
        ins = hasil["insurance"]
        self.assertIsNotNone(ins)
        self.assertAlmostEqual(ins["metrics"]["p_win"], 0.80 * 0.786 * 0.786, places=3)


class TestFilterRecheck(unittest.TestCase):
    def test_jangan_pasang_tidak_masuk_tiket(self):
        analyses = slate_standar()
        rechecks = []
        for analisis in analyses:
            if analisis["match_id"] == LAGA[0]:
                rechecks.append(
                    buat_recheck(
                        analisis,
                        putusan={
                            "insurance": (
                                "JANGAN_PASANG",
                                ["harga market 68% < 74%"],
                                "market",
                                0.68,
                            )
                        },
                    )
                )
            else:
                rechecks.append(buat_recheck(analisis))
        hasil = ticket_composer.compose_tickets(
            analyses, rechecks, CFG, stake_total=20, now=SEKARANG
        )
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        self.assertNotIn(LAGA[0], laga_ins)
        # Kaki Utama laga yang sama tetap TETAP_OK -> masuk Utama.
        laga_main = {k["match_id"] for k in hasil["main"]["legs"]}
        self.assertIn(LAGA[0], laga_main)
        self.assertIn("JANGAN_PASANG", hasil["summary"])

    def test_data_incomplete_tidak_masuk_tiket(self):
        analyses = slate_standar()
        rechecks = []
        for analisis in analyses:
            if analisis["match_id"] == LAGA[0]:
                rechecks.append(
                    buat_recheck(
                        analisis,
                        putusan={
                            "main": (
                                "DATA_INCOMPLETE",
                                ["data cedera basi"],
                                "model",
                                None,
                            )
                        },
                    )
                )
            else:
                rechecks.append(buat_recheck(analisis))
        hasil = ticket_composer.compose_tickets(
            analyses, rechecks, CFG, stake_total=20, now=SEKARANG
        )
        # Kaki Asuransi laga yang sama tetap TETAP_OK -> masuk Asuransi.
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        self.assertIn(LAGA[0], laga_ins)
        # Hanya 3 kaki Utama tersisa -> pengali maks 2,53 < 3,5: Utama None.
        self.assertIsNone(hasil["main"])
        self.assertIn("tidak tercapai", hasil["main_reason"])
        self.assertIn("DATA_INCOMPLETE", hasil["summary"])

    def test_perhatian_masuk_dengan_tanda(self):
        analyses = slate_standar()
        rechecks = []
        for analisis in analyses:
            if analisis["match_id"] == LAGA[0]:
                rechecks.append(
                    buat_recheck(
                        analisis,
                        putusan={
                            "insurance": (
                                "PERHATIAN",
                                ["harga bergerak 2c sejak analisis awal"],
                                "model",
                                None,
                            )
                        },
                    )
                )
            else:
                rechecks.append(buat_recheck(analisis))
        hasil = ticket_composer.compose_tickets(
            analyses, rechecks, CFG, stake_total=20, now=SEKARANG
        )
        ins = hasil["insurance"]
        kaki = next(k for k in ins["legs"] if k["match_id"] == LAGA[0])
        self.assertIn("PERHATIAN", kaki["flags"])
        self.assertIn("PERHATIAN", hasil["summary"])
        self.assertIn("harga bergerak 2c", hasil["summary"])

    def test_perhatian_tanpa_alasan_ditolak(self):
        analyses = slate_standar()
        rechecks = []
        for analisis in analyses:
            if analisis["match_id"] == LAGA[0]:
                rechecks.append(
                    buat_recheck(
                        analisis,
                        putusan={"insurance": ("PERHATIAN", [], "model", None)},
                    )
                )
            else:
                rechecks.append(buat_recheck(analisis))
        hasil = ticket_composer.compose_tickets(
            analyses, rechecks, CFG, stake_total=20, now=SEKARANG
        )
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        self.assertNotIn(LAGA[0], laga_ins)

    def test_kaki_hilang_dari_recheck_ditolak(self):
        # Laporan recheck tanpa entri untuk satu kaki -> fail-closed.
        analyses = slate_standar()
        rechecks = recheck_semua_ok(analyses)
        rechecks[0]["legs"] = [
            k for k in rechecks[0]["legs"] if "insurance" not in k["leg_id"]
        ]
        hasil = ticket_composer.compose_tickets(
            analyses, rechecks, CFG, stake_total=20, now=SEKARANG
        )
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        self.assertNotIn(LAGA[0], laga_ins)


class TestTargetPengali(unittest.TestCase):
    def test_target_tidak_tercapai_none_dengan_alasan(self):
        # Hanya 2 laga: Asuransi maks 1,68 < 2,2; Utama maks 1,82 < 3,5.
        analyses = slate_standar(LAGA[:2])
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNone(hasil["insurance"])
        self.assertIsNone(hasil["main"])
        self.assertIn("x1.68", hasil["insurance_reason"])
        self.assertIn("tidak tercapai", hasil["insurance_reason"])
        self.assertIn("tidak tercapai", hasil["main_reason"])

    def test_kombinasi_tidak_pas_jendela(self):
        # Kaki Asuransi @50c: 1 kaki -> 1,89; 2 kaki -> 3,78 — tidak ada
        # kombinasi yang masuk jendela 2,2-2,5. Utama 2 kaki @50c = 3,78
        # justru masuk target.
        analyses = []
        for match_id in LAGA[:2]:
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_ins=buat_kaki(match_id, "insurance", 235.5, 0.82, 0.80, 50.0),
                    kaki_main=buat_kaki(match_id, "main", 231.5, 0.76, 0.74, 50.0),
                )
            )
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNone(hasil["insurance"])
        self.assertIn("tidak ada yang masuk target", hasil["insurance_reason"])
        self.assertIsNotNone(hasil["main"])
        self.assertAlmostEqual(hasil["main"]["multiplier"], 3.78, places=2)

    def test_satu_kaki_bila_terpaksa(self):
        # Satu laga, kaki Asuransi @40c -> pengali 2,36 (masuk target
        # sendirian); Utama @40c -> 2,36 < 3,5.
        match_id = LAGA[0]
        analyses = [
            buat_analisis(
                match_id,
                kaki_ins=buat_kaki(match_id, "insurance", 235.5, 0.82, 0.80, 40.0),
                kaki_main=buat_kaki(match_id, "main", 231.5, 0.76, 0.74, 40.0),
            )
        ]
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        ins = hasil["insurance"]
        self.assertIsNotNone(ins)
        self.assertEqual(len(ins["legs"]), 1)
        self.assertAlmostEqual(ins["multiplier"], 2.3625, places=3)
        self.assertTrue(any("hanya berisi 1 kaki" in w for w in hasil["warnings"]))
        self.assertIsNone(hasil["main"])

    def test_utama_melebihi_target_lunak_bila_terpaksa(self):
        # Kombinasi Utama yang tersedia hanya di atas 4,0 (tapi <= 5,0):
        # 3 kaki @62c -> (100/62)^3 x 0,945 = 3,96... pakai @60c:
        # 3 kaki -> 4,37 (dalam 3,5-5,0, di atas target lunak 4,0).
        analyses = []
        for match_id in LAGA[:3]:
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_ins=buat_kaki(match_id, "insurance", 235.5, 0.80, 0.78, 75.0),
                    kaki_main=buat_kaki(match_id, "main", 231.5, 0.76, 0.74, 60.0),
                )
            )
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        main = hasil["main"]
        self.assertIsNotNone(main)
        self.assertAlmostEqual(main["multiplier"], 4.375, places=2)
        self.assertLessEqual(main["multiplier"], 5.0)

    def test_mode_agresif_maks_utama_bebas(self):
        # 2 kaki Utama @40c -> 5,91x: di atas maks standar 5,0, tapi
        # boleh di mode agresif.
        analyses = []
        for match_id in LAGA[:2]:
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_ins=buat_kaki(match_id, "insurance", 235.5, 0.82, 0.80, 40.0),
                    kaki_main=buat_kaki(match_id, "main", 231.5, 0.76, 0.74, 40.0),
                )
            )
        hasil_std = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNone(hasil_std["main"])
        cfg_agresif = copy.deepcopy(CFG)
        cfg_agresif["tickets"]["mode"] = "aggressive"
        hasil_agr = ticket_composer.compose_tickets(
            analyses,
            recheck_semua_ok(analyses),
            cfg_agresif,
            stake_total=20,
            now=SEKARANG,
        )
        self.assertIsNotNone(hasil_agr["main"])
        self.assertAlmostEqual(hasil_agr["main"]["multiplier"], 5.9062, places=3)
        self.assertIn("Mode agresif", hasil_agr["summary"])


class TestMatematikaKombo(unittest.TestCase):
    def test_combo_multiplier_potongan_55_persen(self):
        # (100/80) x (100/75) x (1 - 0,055) = 1,575.
        self.assertAlmostEqual(
            ticket_composer.combo_multiplier([80.0, 75.0], 5.5), 1.575, places=9
        )
        # Tiga kaki @75c = 2,24.
        self.assertAlmostEqual(
            ticket_composer.combo_multiplier([75.0, 75.0, 75.0], 5.5), 2.24, places=9
        )

    def test_combo_multiplier_harga_tidak_valid(self):
        with self.assertRaises(ValueError):
            ticket_composer.combo_multiplier([], 5.5)
        with self.assertRaises(ValueError):
            ticket_composer.combo_multiplier([100.0], 5.5)
        with self.assertRaises(ValueError):
            ticket_composer.combo_multiplier([0.0], 5.5)

    def test_korelasi_laga_sama_pakai_persentil_sim(self):
        # Dua kaki dari satu laga (garis 230.5 & 235.5): P(keduanya
        # menang) = P(total <= 230.5) = 0,70 dari sim — bukan 0,80x0,85.
        sim_markets = {"total_under_230.5": 0.70, "total_under_235.5": 0.85}
        kaki = [
            {
                "match_id": "A",
                "line": 230.5,
                "decision_prob": 0.80,
                "sim_markets": sim_markets,
            },
            {
                "match_id": "A",
                "line": 235.5,
                "decision_prob": 0.85,
                "sim_markets": sim_markets,
            },
            {"match_id": "B", "line": 231.5, "decision_prob": 0.75, "sim_markets": {}},
        ]
        p_menang, catatan = ticket_composer.ticket_win_probability(kaki)
        self.assertAlmostEqual(p_menang, 0.70 * 0.75, places=9)
        self.assertEqual(catatan, [])

    def test_korelasi_tanpa_persentil_sim_fallback_dengan_catatan(self):
        kaki = [
            {"match_id": "A", "line": 230.5, "decision_prob": 0.80, "sim_markets": {}},
            {"match_id": "A", "line": 235.5, "decision_prob": 0.85, "sim_markets": {}},
        ]
        p_menang, catatan = ticket_composer.ticket_win_probability(kaki)
        self.assertAlmostEqual(p_menang, 0.80 * 0.85, places=9)
        self.assertEqual(len(catatan), 1)
        self.assertIn("korelasi", catatan[0])

    def test_ev_negatif_memicu_peringatan(self):
        # 4 kaki Asuransi p 0,79 @80c: EV per kaki -1,25% (WAJAR, bukan
        # MAHAL) tapi EV tiket = 0,79^4 x 2,31 - 1 = -10% -> peringatan.
        analyses = []
        for match_id in LAGA:
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_ins=buat_kaki(match_id, "insurance", 235.5, 0.79, 0.79, 80.0),
                    kaki_main=buat_kaki(match_id, "main", 231.5, 0.76, 0.74, 72.0),
                )
            )
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        ins = hasil["insurance"]
        self.assertIsNotNone(ins)
        self.assertLess(ins["metrics"]["combined_ev_pct"], 0)
        self.assertTrue(
            any("EV tiket Asuransi negatif" in w for w in hasil["warnings"])
        )


class TestPeringatanJendela(unittest.TestCase):
    def test_tanpa_recheck_sama_sekali(self):
        analyses = slate_standar()
        hasil = ticket_composer.compose_tickets(
            analyses, None, CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNotNone(hasil["insurance"])
        self.assertIsNotNone(hasil["main"])
        self.assertTrue(any("belum dicek ulang" in w for w in hasil["warnings"]))
        self.assertIn("belum dicek ulang", hasil["summary"])

    def test_recheck_basi_75_menit(self):
        analyses = slate_standar()
        rechecks = []
        for i, analisis in enumerate(analyses):
            # Laga pertama: recheck 75 menit lalu (basi); sisanya segar.
            at = "2026-11-22T11:45:00+00:00" if i == 0 else "2026-11-22T12:30:00+00:00"
            rechecks.append(buat_recheck(analisis, recheck_at=at))
        hasil = ticket_composer.compose_tickets(
            analyses, rechecks, CFG, stake_total=20, now=SEKARANG
        )
        peringatan_basi = [w for w in hasil["warnings"] if "75 menit lalu" in w]
        self.assertEqual(len(peringatan_basi), 1)
        self.assertIn(LAGA[0], peringatan_basi[0])
        self.assertIn("sebaiknya cek ulang sebelum pasang", peringatan_basi[0])

    def test_recheck_60_menit_belum_basi(self):
        # Tepat 60 menit (batas atas jendela) belum dianggap basi.
        analyses = slate_standar()
        rechecks = recheck_semua_ok(analyses, recheck_at="2026-11-22T12:00:00+00:00")
        hasil = ticket_composer.compose_tickets(
            analyses, rechecks, CFG, stake_total=20, now=SEKARANG
        )
        self.assertEqual(hasil["warnings"], [])

    def test_recheck_61_menit_basi(self):
        analyses = slate_standar()
        rechecks = recheck_semua_ok(analyses, recheck_at="2026-11-22T11:59:00+00:00")
        hasil = ticket_composer.compose_tickets(
            analyses, rechecks, CFG, stake_total=20, now=SEKARANG
        )
        self.assertTrue(any("61 menit lalu" in w for w in hasil["warnings"]))


class TestFilterLain(unittest.TestCase):
    def test_mahal_tidak_masuk_asuransi_boleh_masuk_utama(self):
        analyses = []
        for i, match_id in enumerate(LAGA):
            label = "MAHAL" if i == 0 else None
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_ins=buat_kaki(
                        match_id, "insurance", 235.5, 0.80, 0.78, 75.0, label=label
                    ),
                    kaki_main=buat_kaki(
                        match_id, "main", 231.5, 0.76, 0.74, 72.0, label=label
                    ),
                )
            )
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        self.assertNotIn(LAGA[0], laga_ins)
        kaki_main = next(k for k in hasil["main"]["legs"] if k["match_id"] == LAGA[0])
        self.assertIn("MAHAL", kaki_main["flags"])
        self.assertIn("MAHAL", hasil["summary"])

    def test_model_only_ditolak(self):
        # Kaki tanpa p_market (MODEL_ONLY) tidak bisa masuk tiket yang
        # valid terhadap skema (p_market wajib angka).
        analyses = []
        for i, match_id in enumerate(LAGA):
            if i == 0:
                analyses.append(
                    buat_analisis(
                        match_id,
                        kaki_ins=buat_kaki(
                            match_id, "insurance", 235.5, 0.80, None, 75.0
                        ),
                        kaki_main=buat_kaki(match_id, "main", 231.5, 0.76, 0.74, 72.0),
                    )
                )
            else:
                analyses.append(buat_analisis(match_id))
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        self.assertNotIn(LAGA[0], laga_ins)
        self.assertIn("MODEL_ONLY", hasil["summary"])

    def test_peluang_di_bawah_minimum_ditolak(self):
        # Asuransi p_final 0,699 < 0,74; Utama p_final 0,60 < 0,65.
        analyses = []
        for i, match_id in enumerate(LAGA):
            if i == 0:
                analyses.append(
                    buat_analisis(
                        match_id,
                        kaki_ins=buat_kaki(
                            match_id, "insurance", 235.5, 0.72, 0.69, 75.0
                        ),
                        kaki_main=buat_kaki(match_id, "main", 231.5, 0.60, 0.60, 72.0),
                    )
                )
            else:
                analyses.append(buat_analisis(match_id))
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        self.assertNotIn(LAGA[0], laga_ins)
        self.assertIsNone(hasil["main"])  # hanya 3 kaki Utama tersisa

    def test_analisis_hold_ditolak(self):
        analyses = slate_standar()
        analyses[0]["status"] = "HOLD"
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        self.assertNotIn(LAGA[0], laga_ins)
        # Hanya 3 kaki Utama tersisa -> Utama tidak terracik.
        self.assertIsNone(hasil["main"])

    def test_kaki_tidak_meets_ditolak(self):
        analyses = slate_standar()
        analyses[0]["legs"][0] = buat_kaki(
            LAGA[0],
            "insurance",
            None,
            None,
            None,
            75.0,
            meets=False,
            reason="bantalan_kurang",
        )
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        self.assertNotIn(LAGA[0], laga_ins)

    def test_dedupe_analisis_ganda_pakai_yang_terbaru(self):
        lama = buat_analisis(LAGA[0], generated_at="2026-11-22T09:00:00+00:00")
        baru = buat_analisis(
            LAGA[0],
            kaki_ins=buat_kaki(LAGA[0], "insurance", 235.5, 0.80, 0.78, 70.0),
            kaki_main=buat_kaki(LAGA[0], "main", 231.5, 0.76, 0.74, 72.0),
            generated_at="2026-11-22T11:00:00+00:00",
        )
        analyses = [lama, baru] + slate_standar(LAGA[1:])
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        # Kaki Asuransi laga pertama yang dipakai adalah yang terbaru
        # (harga 70c, bukan 75c) — bila ada di tiket.
        ins = hasil["insurance"]
        kaki = [k for k in ins["legs"] if k["match_id"] == LAGA[0]]
        if kaki:
            self.assertEqual(kaki[0]["jup_price_cents"], 70.0)
        # Main tetap 4 kaki (dedupe tidak menggandakan laga).
        self.assertEqual(len(hasil["main"]["legs"]), 4)


def buat_kaki_bola(
    match_id,
    market_type,
    selection,
    p_model,
    p_market,
    harga,
    line=None,
    ticket="main",
    no_xg=True,
    penalti=5,
):
    """Satu kaki artefak soccer_analysis (bentuk _rakit_kaki)."""
    p_final = None
    ev_pct = None
    if p_model is not None:
        p_final = (
            round(0.3 * p_model + 0.7 * p_market, 3)
            if p_market is not None
            else p_model
        )
        ev_pct = round((p_final * (100.0 / harga) - 1.0) * 100.0, 2)
    leg_id = f"{match_id}:{market_type}_{selection}:{ticket}"
    if line is not None:
        leg_id = f"{match_id}:{market_type}_{line:g}:{ticket}"
    kaki = {
        "leg_id": leg_id,
        "market_type": market_type,
        "selection": selection,
        "line": line,
        "ticket": ticket,
        "p_model": p_model,
        "p_market": p_market,
        "comparison_source": "kalshi" if p_market is not None else None,
        "p_final": p_final,
        "price_cents": harga,
        "jup_estimated_cents": harga,
        "ev_pct": ev_pct,
        "price_label": (label_dari_ev(ev_pct) if ev_pct is not None else None),
        "meets": True,
        "reason": None,
        "fetched_at": "2026-11-22T10:00:00+00:00",
        "no_xg": no_xg,
        "banned_from_insurance": no_xg,
        "model_only": p_market is None,
    }
    if penalti is not None:
        kaki["threshold_penalty_points"] = penalti
    return kaki


def buat_analisis_bola(match_id, home, away, legs, status="OK"):
    """Satu artefak soccer_analysis minimal."""
    return {
        "format": "soccer_analysis",
        "format_version": 1,
        "match_id": match_id,
        "home_team": home,
        "away_team": away,
        "league": "EPL",
        "match_date": "2026-11-22",
        "generated_at": "2026-11-22T10:00:00+00:00",
        "status": status,
        "legs": legs,
        "simulation": {
            "score_distribution": {"total": {"median": 2.7}},
            "markets": {},
        },
        "market": {"main_total_line": None},
        "labels": ["TANPA_XG"],
    }


LAGA_BOLA = [
    ("manchester-united@liverpool_2026-11-22", "Liverpool", "Manchester United"),
    ("chelsea@arsenal_2026-11-22", "Arsenal", "Chelsea"),
]


class TestTanpaXg(unittest.TestCase):
    def test_tanpa_xg_dilarang_masuk_asuransi(self):
        # Kaki TANPA_XG dengan tiket "insurance" (seolah builder salah)
        # tetap TIDAK BOLEH masuk Asuransi — penegakan memakai flag.
        kaki = buat_kaki_bola(
            LAGA_BOLA[0][0],
            "moneyline_home",
            "home",
            0.86,
            0.84,
            75.0,
            ticket="insurance",
        )
        analisis = buat_analisis_bola(
            LAGA_BOLA[0][0], LAGA_BOLA[0][1], LAGA_BOLA[0][2], [kaki]
        )
        kandidat, coret = ticket_composer._kumpulkan_kandidat(
            {LAGA_BOLA[0][0]: analisis}, {}, CFG
        )
        self.assertEqual(kandidat["insurance"], [])
        self.assertTrue(
            any("TANPA_XG" in c for c in coret["insurance"]),
            coret["insurance"],
        )

    def test_penalti_ambang_utama_lima_poin(self):
        # Ambang Utama 65% + 5 poin TANPA_XG = 70%.
        kaki_rendah = buat_kaki_bola(
            LAGA_BOLA[0][0], "moneyline_home", "home", 0.70, 0.67, 55.0
        )  # p_final = 0,679 < 0,70
        kaki_lolos = buat_kaki_bola(
            LAGA_BOLA[1][0], "moneyline_home", "home", 0.75, 0.71, 55.0
        )  # p_final = 0,722 >= 0,70
        analyses = {
            LAGA_BOLA[0][0]: buat_analisis_bola(
                LAGA_BOLA[0][0], LAGA_BOLA[0][1], LAGA_BOLA[0][2], [kaki_rendah]
            ),
            LAGA_BOLA[1][0]: buat_analisis_bola(
                LAGA_BOLA[1][0], LAGA_BOLA[1][1], LAGA_BOLA[1][2], [kaki_lolos]
            ),
        }
        kandidat, coret = ticket_composer._kumpulkan_kandidat(analyses, {}, CFG)
        self.assertEqual(len(kandidat["main"]), 1)
        self.assertEqual(kandidat["main"][0]["match_id"], LAGA_BOLA[1][0])
        self.assertTrue(
            any("TANPA_XG" in c and "70%" in c for c in coret["main"]),
            coret["main"],
        )

    def test_penalti_dibaca_dari_config_bila_kaki_tanpa_field(self):
        self.assertAlmostEqual(
            ticket_composer._penalti_no_xg({"no_xg": True}, CFG), 0.05
        )
        self.assertAlmostEqual(
            ticket_composer._penalti_no_xg({"threshold_penalty_points": 3}, CFG),
            0.03,
        )

    def test_utama_dengan_kaki_bola(self):
        # 2 kaki @ 55¢ -> pengali (100/55)^2 x 0,945 = 3,12 (target 3-5).
        analyses = []
        for match_id, home, away in LAGA_BOLA:
            kaki = buat_kaki_bola(match_id, "moneyline_home", "home", 0.75, 0.71, 55.0)
            analyses.append(buat_analisis_bola(match_id, home, away, [kaki]))
        hasil = ticket_composer.compose_tickets(
            analyses, None, CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNone(hasil["insurance"])
        self.assertIsNotNone(hasil["main"])
        main = hasil["main"]
        self.assertEqual(len(main["legs"]), 2)
        for kaki in main["legs"]:
            self.assertEqual(kaki["sport"], "football")
            self.assertEqual(kaki["market"], "moneyline_home")
            self.assertIn("TANPA_XG", kaki["flags"])
        self.assertEqual(main["legs"][0]["selection"], "Arsenal menang")
        self.assertIn("TANPA_XG", hasil["summary"])
        jsonschema.validate(instance=main, schema=SKEMA_TIKET)

    def test_korelasi_kaki_bola_fallback_dengan_catatan(self):
        kaki = [
            {
                "match_id": LAGA_BOLA[0][0],
                "line": None,
                "decision_prob": 0.72,
                "leg": {"market_type": "moneyline_home"},
                "sim_markets": {},
            },
            {
                "match_id": LAGA_BOLA[0][0],
                "line": 2.5,
                "decision_prob": 0.60,
                "leg": {"market_type": "total_under"},
                "sim_markets": {},
            },
        ]
        peluang, catatan = ticket_composer.ticket_win_probability(kaki)
        self.assertAlmostEqual(peluang, 0.72 * 0.60)
        self.assertTrue(any("tidak dihitung" in c for c in catatan))

    def test_seleksi_kaki_bola(self):
        analisis = buat_analisis_bola(
            LAGA_BOLA[0][0], LAGA_BOLA[0][1], LAGA_BOLA[0][2], []
        )
        self.assertEqual(
            ticket_composer._seleksi_kaki({"market_type": "moneyline_home"}, analisis),
            "Liverpool menang",
        )
        self.assertEqual(
            ticket_composer._seleksi_kaki({"market_type": "moneyline_draw"}, analisis),
            "Seri",
        )
        self.assertEqual(
            ticket_composer._seleksi_kaki(
                {"market_type": "total_over", "line": 2.5}, analisis
            ),
            "Over 2,5 gol",
        )
        self.assertEqual(
            ticket_composer._seleksi_kaki({"market_type": "btts_yes"}, analisis),
            "Kedua tim mencetak gol",
        )


if __name__ == "__main__":
    unittest.main()
