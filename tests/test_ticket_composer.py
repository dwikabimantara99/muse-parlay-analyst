"""Tes engine/ticket_composer.py — SEMUA offline dari fixture, 0 kredit Odds API.

Slate standar: 8 laga, tiap laga dua kaki Alt Under —
- Asuransi: Under 235.5 @ 75c, p_model 0,80, p_market 0,78 -> p_final 0,786.
  3 kaki -> pengali (100/75)^3 x 0,945 = 2,24 (target Asuransi 2,0-2,5,
  fondasi harga & pengali 2026-11-23). Edge kaki Asuransi standar
  0,786 - 0,75 = +3,6% (di atas gate edge minimum 3,5%).
- Utama: Under 231.5 @ 75c, p_model 0,78, p_market 0,76 -> p_final 0,766.
  5 kaki -> pengali (100/75)^5 x 0,945 = 3,98 (target Utama 3,0-5,0).
  Harga Utama >= 75c (lantai harga filosofi 2026-11-23) dan p_final
  0,766 (EV tiket positif: 0,766^5 x 3,98 - 1 = +5%). Pengali 3,98
  berada DI ATAS target lunak 3,5 (fondasi 2026-11-23), jadi Utama
  5 kaki hanya terracik bila "yakin" (recheck TETAP_OK + tanpa
  anomali + p_final >= 0,75) — tes tanpa recheck memakai kaki Utama
  @78c (5 kaki = 3,27, di dalam jendela lunak) bila butuh Utama
  terbentuk tanpa recheck.
Median 224 vs garis market 225,5 (selisih 1,5 < 5,0 — aturan
condong-ke-market tidak terpicu) kecuali di tes condong.

ATURAN TANPA KAKI KEMBAR (keputusan user 12:20 WIB 2026-11-23):
satu laga tidak boleh masuk kedua tiket — Asuransi dipilih dulu
(3 laga leg_id terkecil: BOS, DET, LAL), Utama memakai 5 laga
sisanya. Karena itu slate standar memakai 8 laga (3 + 5), bukan 5.
"""

import copy
import json
import math
import sys
import unittest
from pathlib import Path
from unittest import mock

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
    "PHX@DAL_2026-11-22",
    # 3 laga tambahan (aturan tanpa kaki kembar, 2026-11-23):
    # Asuransi memakai 3 laga leg_id terkecil (BOS, DET, LAL),
    # Utama memakai 5 sisanya — total 8 laga agar kedua tiket
    # bisa terbentuk dari slate standar. Urutan sengaja setelah
    # PHX@DAL supaya alokasi Asuransi tidak berubah.
    "SAC@UTA_2026-11-22",
    "TOR@WAS_2026-11-22",
    "WAS@CHA_2026-11-22",
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
    harga_jup=None,
    thin=None,
    cushion_points=None,
    cushion_reason=None,
    volume_usd=None,
    climb=None,
):
    """Satu kaki artefak nba_analysis (bentuk _rakit_kaki).

    ``harga`` = price_cents (Polymarket mentah); ``harga_jup`` =
    jup_estimated_cents (None = sama dengan harga). EV dihitung dari
    harga venue (jup). Field baru Tahap 4 (thin/cushion/volume/climb)
    mengikuti kontrak kaki artefak (None = tidak diketahui).
    """
    harga_venue = harga_jup if harga_jup is not None else harga
    p_final = None
    ev_pct = None
    if p_model is not None:
        # Blend w=0,3 (config blend.w_model); tanpa p_market -> MODEL_ONLY.
        p_final = (
            round(0.3 * p_model + 0.7 * p_market, 3)
            if p_market is not None
            else p_model
        )
        ev_pct = round((p_final * (100.0 / harga_venue) - 1.0) * 100.0, 2)
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
        "jup_estimated_cents": harga_venue,
        "ev_pct": ev_pct,
        "price_label": (
            label
            if label is not None
            else (label_dari_ev(ev_pct) if ev_pct is not None else None)
        ),
        "cushion_vs_median_points": 14.5,
        "cushion_vs_market_points": 8.0,
        "cushion_points": cushion_points,
        "cushion_reason": cushion_reason,
        "volume_usd": volume_usd,
        "thin": thin,
        "climb": climb,
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
    anomalies=None,
):
    """Satu artefak nba_analysis minimal (kaki standar bila tidak diberi)."""
    if kaki_ins is None:
        kaki_ins = buat_kaki(match_id, "insurance", 235.5, 0.80, 0.78, 75.0)
    if kaki_main is None:
        kaki_main = buat_kaki(match_id, "main", 231.5, 0.78, 0.76, 75.0)
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
        "anomalies": list(anomalies) if anomalies is not None else [],
    }


def slate_standar(laga=LAGA):
    """Slate standar (8 laga default; semua kaki lolos, garis berbeda)."""
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


def cfg_tanpa_lantai():
    """CFG dengan lantai harga 0 (kaki murah boleh lolos).

    Untuk tes yang menguji logika lain (subset 1 kaki, mode agresif,
    kriteria yakin) tanpa lantai harga menghalangi — lantai adalah
    nilai config, jadi tes boleh memakai varian config.
    """
    cfg = copy.deepcopy(CFG)
    cfg.setdefault("analis", {})["harga_min_utama_cents"] = 0
    cfg["analis"]["harga_min_asuransi_cents"] = 0
    return cfg


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
        # Pengali (fondasi harga & pengali 2026-11-23): Asuransi
        # 3 kaki @75c = 2,24 (target 2,0-2,5; 4 kaki = 2,99 sudah di
        # atas maks 2,5); Utama 5 kaki @75c = 3,98 (di atas lunak
        # 3,5, lolos karena "yakin": recheck TETAP_OK + tanpa anomali
        # + p_final 0,766 >= 0,75).
        self.assertAlmostEqual(ins["multiplier"], 2.24, places=3)
        self.assertAlmostEqual(main["multiplier"], 3.9822, places=3)
        self.assertEqual(len(ins["legs"]), 3)
        self.assertEqual(len(main["legs"]), 5)
        # ID unik per tanggal.
        self.assertEqual(ins["ticket_id"], "tkt-2026-11-22-ins")
        self.assertEqual(main["ticket_id"], "tkt-2026-11-22-utm")
        self.assertEqual(ins["type"], "Asuransi")
        self.assertEqual(main["type"], "Utama")
        # P menang = Π p_final (laga berbeda = independen).
        self.assertAlmostEqual(ins["metrics"]["p_win"], 0.786**3, places=3)
        self.assertAlmostEqual(main["metrics"]["p_win"], 0.766**5, places=3)
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

    def test_config_main_maks_5_target_35(self):
        # Perubahan config Langkah 3 (profil user 2026-11-22); versi
        # config kini 17 (vonis + veto rim protector + tanpa kaki
        # kembar + equilibrium Asuransi safety-first + setan per
        # pemain + koreksi banjir ke data bersih, 2026-11-23 — lihat
        # komentar playstyle.yaml).
        self.assertEqual(CFG["meta"]["version"], 17)
        self.assertEqual(CFG["tickets"]["main"]["multiplier_max"], 5.0)
        self.assertEqual(CFG["tickets"]["main"]["target_multiplier_max"], 3.5)
        self.assertEqual(CFG["tickets"]["insurance"]["multiplier_min"], 2.0)
        self.assertEqual(CFG["tickets"]["insurance"]["multiplier_max"], 2.5)
        self.assertEqual(CFG["tickets"]["insurance"]["min_edge_pct"], 3.5)
        self.assertEqual(CFG["analis"]["harga_min_utama_cents"], 75)
        self.assertEqual(CFG["analis"]["harga_min_asuransi_cents"], 75)

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


class TestTanpaKakiKembar(unittest.TestCase):
    """Aturan tanpa kaki kembar (keputusan user 12:20 WIB 2026-11-23).

    MENGGANTIKAN aturan lama "garis berbeda": dulu satu laga boleh
    masuk kedua tiket asal garis Asuransinya lebih tinggi dari garis
    Utamanya; sekarang satu laga TIDAK BOLEH masuk kedua tiket,
    apa pun garisnya. Asuransi dipilih dulu (leg_id terkecil),
    Utama memakai laga sisanya. Tes-tes di bawah ini dulunya kelas
    TestGarisBerbeda — perilakunya ditulis ulang untuk aturan baru.
    """

    def test_garis_sama_hanya_masuk_asuransi(self):
        # Satu laga garis Asuransi = garis Utama (233.5). Aturan
        # lama: masuk Asuransi karena garisnya sama. Aturan baru:
        # masuk Asuransi karena Asuransi dipilih dulu (AAA@BBB
        # leg_id terkecil) dan Utama tidak boleh memakai laga yang
        # sama — garis tidak lagi relevan.
        laga_x = "AAA@BBB_2026-11-22"
        analisis_x = buat_analisis(
            laga_x,
            kaki_ins=buat_kaki(laga_x, "insurance", 233.5, 0.80, 0.78, 75.0),
            kaki_main=buat_kaki(laga_x, "main", 233.5, 0.78, 0.76, 75.0),
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
        self.assertIn("tanpa kaki kembar", hasil["summary"])

    def test_garis_asuransi_lebih_rendah_dari_utama(self):
        # Artefak aneh: garis Asuransi (230.5) LEBIH RENDAH dari Utama
        # (234.5). Aturan lama: laga hanya masuk Asuransi karena
        # "tidak lebih aman". Aturan baru: tetap hanya Asuransi —
        # karena disjoint, bukan karena garis.
        laga_x = "AAA@BBB_2026-11-22"
        analisis_x = buat_analisis(
            laga_x,
            kaki_ins=buat_kaki(laga_x, "insurance", 230.5, 0.80, 0.78, 75.0),
            kaki_main=buat_kaki(laga_x, "main", 234.5, 0.78, 0.76, 75.0),
        )
        analyses = [analisis_x] + slate_standar()
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        laga_main = {k["match_id"] for k in hasil["main"]["legs"]}
        self.assertNotIn(laga_x, laga_main)
        self.assertIn("tanpa kaki kembar", hasil["summary"])

    def test_garis_berbeda_tetap_tidak_benar_dua_tiket(self):
        # Slate standar: garis Asuransi 235.5 > Utama 231.5 — aturan
        # LAMA mengizinkan laga masuk kedua tiket. Aturan BARU:
        # kedua tiket DISJOINT (tidak berbagi satu laga pun),
        # meski garisnya berbeda dan keduanya bagus.
        analyses = slate_standar()
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNotNone(hasil["insurance"])
        self.assertIsNotNone(hasil["main"])
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        laga_main = {k["match_id"] for k in hasil["main"]["legs"]}
        self.assertEqual(laga_ins & laga_main, set())
        self.assertEqual(len(laga_ins), 3)
        self.assertEqual(len(laga_main), 5)
        self.assertIn("tanpa kaki kembar", hasil["summary"])

    def test_garis_terbalik_det_atl_hanya_asuransi(self):
        # Kasus nyata "SEBELUM" (DET@ATL): garis Asuransi 233,5 LEBIH
        # RENDAH dari garis Utama 237,5 (terbalik). Aturan lama:
        # hanya Asuransi karena "tidak lebih aman". Aturan baru:
        # tetap hanya Asuransi — karena disjoint.
        laga_x = "AAA@BBB_2026-11-22"
        analisis_x = buat_analisis(
            laga_x,
            kaki_ins=buat_kaki(laga_x, "insurance", 233.5, 0.80, 0.78, 75.0),
            kaki_main=buat_kaki(laga_x, "main", 237.5, 0.78, 0.76, 75.0),
        )
        analyses = [analisis_x] + slate_standar()
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNotNone(hasil["insurance"])
        self.assertIsNotNone(hasil["main"])
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        laga_main = {k["match_id"] for k in hasil["main"]["legs"]}
        self.assertIn(laga_x, laga_ins)
        self.assertNotIn(laga_x, laga_main)
        self.assertIn("tanpa kaki kembar", hasil["summary"])

    def test_tanpa_asuransi_garis_utama_tidak_difilter(self):
        # Bila Asuransi tidak terbentuk sama sekali (semua kaki
        # Asuransi tipis -> dicoret), kaki Utama TIDAK difilter
        # aturan kembar — tidak ada laga Asuransi yang menjadi
        # acuan. Memakai LAGA[:5] supaya Utama tepat 5 kaki dari
        # 5 laga (bukan 5 dari 8).
        analyses = []
        for match_id in LAGA[:5]:
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_ins=buat_kaki(
                        match_id, "insurance", 233.5, 0.80, 0.78, 75.0, thin=True
                    ),
                    kaki_main=buat_kaki(match_id, "main", 237.5, 0.78, 0.76, 75.0),
                )
            )
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNone(hasil["insurance"])
        self.assertIsNotNone(hasil["main"])
        self.assertEqual(len(hasil["main"]["legs"]), 5)
        self.assertEqual({k["match_id"] for k in hasil["main"]["legs"]}, set(LAGA[:5]))

    def test_satu_laga_bagus_kedua_tiket_hanya_masuk_satu(self):
        # KASUS WAJIB (sintetik): satu laga bagus untuk kedua tiket
        # (kedua kakinya DISKON, p_final tinggi) tetap hanya masuk
        # SATU tiket — Asuransi, karena Asuransi dipilih dulu.
        laga_x = "AAA@BBB_2026-11-22"
        analisis_x = buat_analisis(
            laga_x,
            kaki_ins=buat_kaki(laga_x, "insurance", 235.5, 0.85, 0.83, 75.0),
            kaki_main=buat_kaki(laga_x, "main", 231.5, 0.84, 0.82, 75.0),
        )
        analyses = [analisis_x] + slate_standar()
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNotNone(hasil["insurance"])
        self.assertIsNotNone(hasil["main"])
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        laga_main = {k["match_id"] for k in hasil["main"]["legs"]}
        self.assertIn(laga_x, laga_ins)
        self.assertNotIn(laga_x, laga_main)
        self.assertEqual(laga_ins & laga_main, set())

    def test_fail_closed_pembagian_bikin_tiket_tidak_terbentuk(self):
        # Fail-closed: hanya 4 laga (Asuransi ambil 3, Utama sisa 1
        # -> pengali maks 1,33 < 3,0) -> Utama TIDAK terbentuk,
        # Asuransi tetap terbentuk. Mesin tidak memaksa memakai
        # ulang laga Asuransi untuk mengisi Utama.
        analyses = slate_standar(LAGA[:4])
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNotNone(hasil["insurance"])
        self.assertEqual(len(hasil["insurance"]["legs"]), 3)
        self.assertIsNone(hasil["main"])

    def test_alokasi_vonis_integrasi(self):
        # KASUS WAJIB (alokasi vonis, end-to-end): vonis dimatikan
        # di config supaya vonis hitungan worker sistem vonis tidak
        # menimpa vonis suntikan di artefak (alokasi membaca
        # analysis["vonis"] sebagai cadangan — lihat
        # _vonis_kandidat). HIJAU -> Asuransi saja; menengah-hijau
        # -> Utama saja; KUNING dievaluasi -> tidak masuk mana pun;
        # tanpa vonis -> tanpa preferensi (disjoint di subset).
        cfg = copy.deepcopy(CFG)
        cfg["vonis"]["enabled"] = False
        vonis_per_laga = {
            "AAA@BBB_2026-11-22": "menengah_hijau",
            "BOS@NYK_2026-11-22": "HIJAU",
            "DET@ATL_2026-11-22": "hijau",
            "LAL@GSW_2026-11-22": "HIJAU",
            "MIA@CHI_2026-11-22": "menengah-hijau",
            "PHX@DAL_2026-11-22": "menengah_cukup_hijau",
            "SAC@UTA_2026-11-22": "menengah_hijau",
            "TOR@WAS_2026-11-22": {
                "vonis": "kuning",
                "indikator": {"dievaluasi": True},
            },
            # WAS@CHA: tanpa vonis (tanpa preferensi).
        }
        analyses = []
        for match_id in ["AAA@BBB_2026-11-22"] + LAGA:
            analisis = buat_analisis(match_id)
            if match_id in vonis_per_laga:
                analisis["vonis"] = vonis_per_laga[match_id]
            analyses.append(analisis)
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), cfg, stake_total=20, now=SEKARANG
        )
        self.assertIsNotNone(hasil["insurance"])
        self.assertIsNotNone(hasil["main"])
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        laga_main = {k["match_id"] for k in hasil["main"]["legs"]}
        self.assertEqual(
            laga_ins,
            {"BOS@NYK_2026-11-22", "DET@ATL_2026-11-22", "LAL@GSW_2026-11-22"},
        )
        self.assertEqual(
            laga_main,
            {
                "AAA@BBB_2026-11-22",
                "MIA@CHI_2026-11-22",
                "PHX@DAL_2026-11-22",
                "SAC@UTA_2026-11-22",
                "WAS@CHA_2026-11-22",
            },
        )
        self.assertNotIn("TOR@WAS_2026-11-22", laga_ins)
        self.assertNotIn("TOR@WAS_2026-11-22", laga_main)
        self.assertEqual(laga_ins & laga_main, set())

    def test_alokasi_vonis_unit(self):
        # Unit _alokasikan_laga: tiap cabang alokasi + bentuk vonis
        # (string/dict) + KUNING-tidak-dievaluasi + vonis bentrok +
        # dict lama tidak diubah.
        def kand(match_id, tiket, vonis):
            return {"match_id": match_id, "ticket": tiket, "vonis": vonis}

        kandidat = {
            "insurance": [
                kand("HIJ@AU_2026-11-22", "insurance", "HIJAU"),
                kand("MEN@GAH_2026-11-22", "insurance", "menengah_hijau"),
                kand("KUN@ING_2026-11-22", "insurance", "KUNING"),
                kand(
                    "DAT@A_2026-11-22",
                    "insurance",
                    {"vonis": "kuning", "indikator": {"dievaluasi": False}},
                ),
                kand("BEN@TROK_2026-11-22", "insurance", "HIJAU"),
                kand("TAN@PA_2026-11-22", "insurance", None),
                kand("ANE@H_2026-11-22", "insurance", "biru"),
            ],
            "main": [
                kand("HIJ@AU_2026-11-22", "main", "hijau"),
                kand("MEN@GAH_2026-11-22", "main", "menengah_hijau"),
                kand("KUN@ING_2026-11-22", "main", "kuning"),
                kand(
                    "DAT@A_2026-11-22",
                    "main",
                    {"vonis": "kuning", "indikator": {"dievaluasi": False}},
                ),
                kand("BEN@TROK_2026-11-22", "main", "menengah_hijau"),
                kand("TAN@PA_2026-11-22", "main", None),
                kand("ANE@H_2026-11-22", "main", "biru"),
            ],
        }
        coret = {"insurance": [], "main": []}
        baru = ticket_composer._alokasikan_laga(kandidat, coret)
        ins = {k["match_id"] for k in baru["insurance"]}
        main = {k["match_id"] for k in baru["main"]}
        # HIJAU -> Asuransi saja; menengah -> Utama saja.
        self.assertIn("HIJ@AU_2026-11-22", ins)
        self.assertNotIn("HIJ@AU_2026-11-22", main)
        self.assertNotIn("MEN@GAH_2026-11-22", ins)
        self.assertIn("MEN@GAH_2026-11-22", main)
        # KUNING dievaluasi -> tidak masuk mana pun.
        self.assertNotIn("KUN@ING_2026-11-22", ins)
        self.assertNotIn("KUN@ING_2026-11-22", main)
        # KUNING-tidak-dievaluasi (KUNING-karena-data) -> tanpa
        # preferensi: kedua kandidat dipertahankan.
        self.assertIn("DAT@A_2026-11-22", ins)
        self.assertIn("DAT@A_2026-11-22", main)
        # Vonis bentrok -> tanpa preferensi + catatan di kedua coret.
        self.assertIn("BEN@TROK_2026-11-22", ins)
        self.assertIn("BEN@TROK_2026-11-22", main)
        self.assertTrue(any("bentrok" in c for c in coret["insurance"]))
        self.assertTrue(any("bentrok" in c for c in coret["main"]))
        # Tanpa vonis + vonis tidak dikenal -> tanpa preferensi.
        self.assertIn("TAN@PA_2026-11-22", ins)
        self.assertIn("TAN@PA_2026-11-22", main)
        self.assertIn("ANE@H_2026-11-22", ins)
        self.assertIn("ANE@H_2026-11-22", main)
        # Catatan alokasi tercatat.
        self.assertTrue(any("HIJAU" in c for c in coret["main"]))
        self.assertTrue(any("menengah-hijau" in c for c in coret["insurance"]))
        self.assertTrue(any("KUNING" in c for c in coret["insurance"]))
        self.assertTrue(any("KUNING" in c for c in coret["main"]))
        # Dict lama tidak diubah (alokasi mengembalikan dict baru).
        self.assertEqual(len(kandidat["insurance"]), 7)
        self.assertEqual(len(kandidat["main"]), 7)

    def test_artefak_nyata_kedua_tiket_disjoint(self):
        # KASUS WAJIB (artefak nyata): dari slate uji (7 live + 3
        # verif), kedua tiket yang terbentuk tidak berbagi satu
        # laga pun. Di-skip bila artefak tidak ada (runtime).
        semua = []
        for nama in (
            "analysis_live_2026-11-22.json",
            "analysis_verif_tahap4_2026-11-22.json",
        ):
            path = REPO_ROOT / "out" / nama
            if not path.exists():
                self.skipTest(f"out/{nama} tidak ada (runtime)")
            data = json.loads(path.read_text(encoding="utf-8"))
            semua.extend(
                match.get("nba_analysis") or {} for match in data.get("matches") or []
            )
        self.assertEqual(len(semua), 10)
        hasil = ticket_composer.compose_tickets(
            semua, None, CFG, stake_total=20, now=SEKARANG
        )
        if hasil["insurance"] is not None and hasil["main"] is not None:
            laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
            laga_main = {k["match_id"] for k in hasil["main"]["legs"]}
            self.assertEqual(laga_ins & laga_main, set())


class TestCondongKeMarket(unittest.TestCase):
    def test_tanpa_recheck_market_rendah_kaki_asuransi_gugur(self):
        # Median 219 vs garis market 225,5 (selisih 6,5 > 5,0), harga
        # market 70c -> probabilitas market 0,70 < 0,74: kaki Asuransi
        # gugur, kaki Utama tetap lolos. Harga venue 75c (jup) supaya
        # kaki lolos lantai harga — aturan condong memakai harga
        # mentah Polymarket (70c), bukan estimasi jup.ag. Kaki Utama
        # @78c (5 kaki = 3,27, di dalam jendela lunak 3,0-3,5) supaya
        # Utama tetap terracik TANPA recheck: 5 kaki @75c = 3,98
        # berada di atas target lunak 3,5 (fondasi 2026-11-23) dan
        # butuh "yakin" yang mustahil tanpa recheck.
        laga_x = "AAA@BBB_2026-11-22"
        analisis_x = buat_analisis(
            laga_x,
            kaki_ins=buat_kaki(
                laga_x, "insurance", 235.5, 0.80, 0.78, 70.0, harga_jup=75.0
            ),
            kaki_main=buat_kaki(laga_x, "main", 231.5, 0.78, 0.76, 78.0),
            median=219.0,
        )
        analyses = [analisis_x]
        for match_id in LAGA:
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_main=buat_kaki(match_id, "main", 231.5, 0.78, 0.76, 78.0),
                )
            )
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
        # p_model/p_market kaki X dinaikkan (0,84/0,82 -> p_final
        # 0,826) supaya lolos gate edge Asuransi (edge 0,826 - 0,76 =
        # +6,6% >= 3,5%; dengan p_final standar 0,786 edgenya hanya
        # +2,6% dan kaki ini dicoret gate edge sebelum condong diuji).
        # Hanya 3 laga supaya kaki X pasti masuk tiket: dengan 4 kaki
        # yang lolos, peracik memilih 3 kaki dengan peluang menang
        # tertinggi (0,786^3) dan kaki X (probabilitas keputusan 0,76)
        # tersisih dari Asuransi 3 kaki (target 2,0-2,5).
        laga_x = "AAA@BBB_2026-11-22"
        analisis_x = buat_analisis(
            laga_x,
            kaki_ins=buat_kaki(laga_x, "insurance", 235.5, 0.84, 0.82, 76.0),
            kaki_main=buat_kaki(laga_x, "main", 231.5, 0.78, 0.76, 75.0),
            median=219.0,
        )
        analyses = [analisis_x] + slate_standar(LAGA[:2])
        hasil = ticket_composer.compose_tickets(
            analyses, None, CFG, stake_total=20, now=SEKARANG
        )
        ins = hasil["insurance"]
        self.assertIsNotNone(ins)
        self.assertEqual(len(ins["legs"]), 3)
        # P menang memakai 0,76 (market) untuk laga X, bukan 0,826.
        self.assertAlmostEqual(ins["metrics"]["p_win"], 0.76 * 0.786**2, places=3)
        self.assertIn("probabilitas market", hasil["summary"])

    def test_dengan_recheck_probabilitas_market_dipakai(self):
        # Recheck sudah menerapkan condong: probability_used=market,
        # value 0,80, TETAP_OK -> peracik memakai 0,80.
        laga_x = "AAA@BBB_2026-11-22"
        analisis_x = buat_analisis(laga_x, median=219.0)
        analyses = [analisis_x] + slate_standar(LAGA[:3])
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
        # Asuransi kini 3 kaki (target 2,0-2,5, fondasi 2026-11-23):
        # kaki X (probabilitas keputusan 0,80, tertinggi) + 2 kaki
        # standar 0,786 — 4 kaki = 2,99 sudah di atas maks 2,5.
        self.assertEqual(len(ins["legs"]), 3)
        self.assertAlmostEqual(ins["metrics"]["p_win"], 0.80 * 0.786**2, places=3)


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
        # Kaki Utama DATA_INCOMPLETE tidak masuk Utama; Utama tetap
        # terracik dari 5 laga lain (aturan tanpa kaki kembar:
        # Asuransi memakai BOS/DET/LAL, Utama memakai 5 sisanya —
        # sebelum aturan ini hanya 4 kaki tersisa dan Utama None).
        self.assertIsNotNone(hasil["main"])
        laga_main = {k["match_id"] for k in hasil["main"]["legs"]}
        self.assertEqual(len(laga_main), 5)
        self.assertNotIn(LAGA[0], laga_main)
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
        # Hanya 2 laga: Asuransi maks 1,68 < 2,0; Utama maks 1,68 < 3,0.
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
        # Kaki Asuransi @78c (p_final 0,836, edge +5,6% — lolos gate
        # edge 3,5%): 3 kaki -> 1,99 (< 2,0); 4 kaki -> 2,55 (> 2,5)
        # — tidak ada kombinasi yang masuk jendela 2,0-2,5 (fondasi
        # 2026-11-23). Hanya 4 kaki Asuransi yang lolos (kaki kelima
        # meets=False); Utama 5 kaki @75c = 3,98 justru masuk target
        # (lolos "yakin" karena recheck TETAP_OK).
        analyses = []
        for i, match_id in enumerate(LAGA):
            if i == 4:
                kaki_ins = buat_kaki(
                    match_id,
                    "insurance",
                    235.5,
                    0.85,
                    0.83,
                    78.0,
                    meets=False,
                    reason="bantalan_kurang",
                )
            else:
                kaki_ins = buat_kaki(match_id, "insurance", 235.5, 0.85, 0.83, 78.0)
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_ins=kaki_ins,
                    kaki_main=buat_kaki(match_id, "main", 231.5, 0.78, 0.76, 75.0),
                )
            )
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNone(hasil["insurance"])
        self.assertIn("tidak ada yang masuk target", hasil["insurance_reason"])
        self.assertIsNotNone(hasil["main"])
        self.assertAlmostEqual(hasil["main"]["multiplier"], 3.98, places=2)

    def test_satu_kaki_bila_terpaksa(self):
        # Satu laga, kaki Asuransi @40c -> pengali 2,36 (masuk target
        # sendirian); Utama @40c -> 2,36 < 3,0. Lantai harga + target
        # Asuransi lama (2,2-2,5) dipakai lewat varian config supaya
        # logika subset 1 kaki tetap teruji — di config live, 1 kaki
        # tidak bisa membentuk tiket (maks 1,26x di lantai 75c).
        cfg = cfg_tanpa_lantai()
        cfg["tickets"]["insurance"]["multiplier_min"] = 2.2
        cfg["tickets"]["insurance"]["multiplier_max"] = 2.5
        match_id = LAGA[0]
        analyses = [
            buat_analisis(
                match_id,
                kaki_ins=buat_kaki(match_id, "insurance", 235.5, 0.82, 0.80, 40.0),
                kaki_main=buat_kaki(match_id, "main", 231.5, 0.78, 0.76, 40.0),
            )
        ]
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), cfg, stake_total=20, now=SEKARANG
        )
        ins = hasil["insurance"]
        self.assertIsNotNone(ins)
        self.assertEqual(len(ins["legs"]), 1)
        self.assertAlmostEqual(ins["multiplier"], 2.3625, places=3)
        self.assertTrue(any("hanya berisi 1 kaki" in w for w in hasil["warnings"]))
        self.assertIsNone(hasil["main"])

    def test_mode_agresif_maks_utama_bebas(self):
        # 3 laga @40c: Asuransi ambil 1 kaki (2,36x, dalam jendela),
        # Utama 2 kaki @40c -> 5,91x: di atas maks standar 5,0, tapi
        # boleh di mode agresif. Lantai harga dinonaktifkan lewat
        # varian config (kaki @40c tidak lolos lantai 75c); mode
        # agresif juga melewati kriteria "yakin" (perintah eksplisit
        # user per malam). Memakai 3 laga (bukan 2) karena aturan
        # tanpa kaki kembar: Asuransi memakai 1 laga, Utama butuh
        # 2 laga sisanya.
        cfg_std = cfg_tanpa_lantai()
        analyses = []
        for match_id in LAGA[:3]:
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_ins=buat_kaki(match_id, "insurance", 235.5, 0.82, 0.80, 40.0),
                    kaki_main=buat_kaki(match_id, "main", 231.5, 0.78, 0.76, 40.0),
                )
            )
        hasil_std = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), cfg_std, stake_total=20, now=SEKARANG
        )
        self.assertIsNone(hasil_std["main"])
        cfg_agresif = copy.deepcopy(cfg_std)
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
        # 5 kaki Utama p 0,70 @78c: pengali 3,27 (di dalam jendela
        # lunak 3,0-3,5, tanpa perlu "yakin"), EV tiket =
        # 0,70^5 x 3,27 - 1 = -45% -> peringatan EV negatif. Kaki
        # Utama boleh ber-EV negatif (MAHAL, label wajib).
        # CATATAN (gate banjir 2026-11-23): kaki Asuransi fixture ini
        # DITOLAK gate banjir — CDF fixture 2 titik menjepit P banjir
        # ke p_model kaki Utama (0,70 < 0,74) dan tidak ada tangga
        # untuk naik garis. Itu tidak memengaruhi tes ini (hanya
        # Utama yang diasersi); perilaku gate banjir diuji sendiri
        # dengan CDF realistis di TestGateBanjirAsuransi.
        # CATATAN (fondasi 2026-11-23): versi lama tes ini memakai
        # Asuransi ber-EV negatif — skenario itu kini TIDAK MUNGKIN
        # karena gate edge Asuransi: tiap kaki lolos punya edge
        # >= +3,5% sehingga faktor EV per kaki >= 1,035 dan EV tiket
        # n >= 2 kaki >= 1,035^2 x 0,945 - 1 > 0 (tiket 1 kaki juga
        # positif karena pengali >= 2,0 x p_final >= 0,74). Tes
        # dipindah ke Utama, satu-satunya tiket yang masih bisa
        # ber-EV negatif — intinya (peringatan EV negatif) tetap sama.
        analyses = []
        for match_id in LAGA:
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_ins=buat_kaki(match_id, "insurance", 235.5, 0.80, 0.78, 75.0),
                    kaki_main=buat_kaki(match_id, "main", 231.5, 0.70, 0.70, 78.0),
                )
            )
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        main = hasil["main"]
        self.assertIsNotNone(main)
        self.assertLess(main["metrics"]["combined_ev_pct"], 0)
        self.assertTrue(any("EV tiket Utama negatif" in w for w in hasil["warnings"]))


class TestPeringatanJendela(unittest.TestCase):
    def test_tanpa_recheck_sama_sekali(self):
        # Kaki Utama @78c (5 kaki = 3,27, di dalam jendela lunak
        # 3,0-3,5) supaya Utama tetap terracik TANPA recheck: 5 kaki
        # @75c = 3,98 berada di atas target lunak 3,5 (fondasi
        # 2026-11-23) dan butuh "yakin" yang mustahil tanpa recheck.
        analyses = []
        for match_id in LAGA:
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_main=buat_kaki(match_id, "main", 231.5, 0.78, 0.76, 78.0),
                )
            )
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
                        match_id, "main", 231.5, 0.78, 0.76, 75.0, label=label
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
                        kaki_main=buat_kaki(match_id, "main", 231.5, 0.78, 0.76, 75.0),
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
                        kaki_main=buat_kaki(match_id, "main", 231.5, 0.60, 0.60, 75.0),
                    )
                )
            else:
                analyses.append(buat_analisis(match_id))
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        self.assertNotIn(LAGA[0], laga_ins)
        self.assertIsNone(hasil["main"])  # hanya 4 kaki Utama tersisa

    def test_analisis_hold_ditolak(self):
        analyses = slate_standar()
        analyses[0]["status"] = "HOLD"
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        laga_ins = {k["match_id"] for k in hasil["insurance"]["legs"]}
        self.assertNotIn(LAGA[0], laga_ins)
        # Hanya 4 kaki Utama tersisa -> Utama tidak terracik.
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
            # p 0,84/0,82 -> p_final 0,826: edge 0,826 - 0,76 = +6,6%
            # (lolos gate edge Asuransi 3,5%; p_final standar 0,786
            # di harga 76c edgenya hanya +2,6% dan dicoret gate).
            # Peluang keputusan tertinggi -> pasti masuk Asuransi
            # 3 kaki, jadi asersi harga kini tanpa syarat.
            kaki_ins=buat_kaki(LAGA[0], "insurance", 235.5, 0.84, 0.82, 76.0),
            kaki_main=buat_kaki(LAGA[0], "main", 231.5, 0.78, 0.76, 75.0),
            generated_at="2026-11-22T11:00:00+00:00",
        )
        analyses = [lama, baru] + slate_standar(LAGA[1:])
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        # Kaki Asuransi laga pertama yang dipakai adalah yang terbaru
        # (harga 76c, bukan 75c).
        ins = hasil["insurance"]
        kaki = [k for k in ins["legs"] if k["match_id"] == LAGA[0]]
        self.assertEqual(len(kaki), 1)
        self.assertEqual(kaki[0]["jup_price_cents"], 76.0)
        # Main tetap 5 kaki (dedupe tidak menggandakan laga).
        self.assertEqual(len(hasil["main"]["legs"]), 5)


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


class TestLantaiHarga(unittest.TestCase):
    def _kandidat(self, analisis, cfg=None):
        return ticket_composer._kumpulkan_kandidat(
            {analisis["match_id"]: analisis}, {}, cfg or CFG
        )

    def test_main_di_bawah_lantai_dicoret(self):
        analisis = buat_analisis(
            LAGA[0],
            kaki_main=buat_kaki(LAGA[0], "main", 231.5, 0.78, 0.76, 74.0),
        )
        kandidat, coret = self._kandidat(analisis)
        self.assertEqual(kandidat["main"], [])
        self.assertTrue(any("lantai 75" in c for c in coret["main"]), coret["main"])
        # Kaki Asuransi @75 tidak ikut dicoret.
        self.assertEqual(len(kandidat["insurance"]), 1)

    def test_asuransi_di_bawah_lantai_dicoret(self):
        analisis = buat_analisis(
            LAGA[0],
            kaki_ins=buat_kaki(LAGA[0], "insurance", 235.5, 0.80, 0.78, 74.0),
        )
        kandidat, coret = self._kandidat(analisis)
        self.assertEqual(kandidat["insurance"], [])
        self.assertTrue(
            any("lantai 75" in c for c in coret["insurance"]),
            coret["insurance"],
        )

    def test_harga_tepat_di_lantai_lolos(self):
        kandidat, _coret = self._kandidat(buat_analisis(LAGA[0]))
        self.assertEqual(len(kandidat["insurance"]), 1)
        self.assertEqual(len(kandidat["main"]), 1)

    def test_fallback_price_cents_bila_tanpa_jup(self):
        # Tanpa jup_estimated_cents, lantai memakai price_cents.
        kaki_murah = buat_kaki(LAGA[0], "main", 231.5, 0.78, 0.76, 74.0)
        del kaki_murah["jup_estimated_cents"]
        analisis = buat_analisis(LAGA[0], kaki_main=kaki_murah)
        kandidat, _coret = self._kandidat(analisis)
        self.assertEqual(kandidat["main"], [])
        kaki_pas = buat_kaki(LAGA[0], "main", 231.5, 0.78, 0.76, 75.0)
        del kaki_pas["jup_estimated_cents"]
        analisis = buat_analisis(LAGA[0], kaki_main=kaki_pas)
        kandidat, _coret = self._kandidat(analisis)
        self.assertEqual(len(kandidat["main"]), 1)

    def test_lantai_dibaca_dari_config(self):
        cfg80 = copy.deepcopy(CFG)
        cfg80["analis"]["harga_min_utama_cents"] = 80
        kandidat, _coret = self._kandidat(buat_analisis(LAGA[0]), cfg80)
        self.assertEqual(kandidat["main"], [])
        cfg70 = copy.deepcopy(CFG)
        cfg70["analis"]["harga_min_utama_cents"] = 70
        analisis = buat_analisis(
            LAGA[0],
            kaki_main=buat_kaki(LAGA[0], "main", 231.5, 0.78, 0.76, 72.0),
        )
        kandidat, _coret = self._kandidat(analisis, cfg70)
        self.assertEqual(len(kandidat["main"]), 1)

    def test_lantai_default_dicatat_di_ringkasan(self):
        # Tanpa section analis di config -> default 75 dipakai +
        # sumbernya dicatat di ringkasan (bukan warnings).
        cfg = copy.deepcopy(CFG)
        del cfg["analis"]
        analyses = slate_standar()
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), cfg, stake_total=20, now=SEKARANG
        )
        self.assertIsNotNone(hasil["insurance"])
        self.assertIsNotNone(hasil["main"])
        self.assertIn("nilai default", hasil["summary"])
        self.assertIn("75¢", hasil["summary"])
        self.assertFalse(any("nilai default" in w for w in hasil["warnings"]))

    def test_lantai_tidak_berlaku_untuk_bola(self):
        # Kaki bola @55c (moneyline) TIDAK kena lantai harga NBA.
        kaki = buat_kaki_bola(
            LAGA_BOLA[0][0], "moneyline_home", "home", 0.75, 0.71, 55.0
        )
        analisis = buat_analisis_bola(
            LAGA_BOLA[0][0], LAGA_BOLA[0][1], LAGA_BOLA[0][2], [kaki]
        )
        kandidat, _coret = ticket_composer._kumpulkan_kandidat(
            {LAGA_BOLA[0][0]: analisis}, {}, CFG
        )
        self.assertEqual(len(kandidat["main"]), 1)


class TestThin(unittest.TestCase):
    def test_thin_asuransi_penghalang_keras(self):
        # Thin @80c (harga lolos lantai) tetap dicoret dari Asuransi.
        analisis = buat_analisis(
            LAGA[0],
            kaki_ins=buat_kaki(
                LAGA[0], "insurance", 235.5, 0.80, 0.78, 80.0, thin=True
            ),
        )
        kandidat, coret = ticket_composer._kumpulkan_kandidat(
            {LAGA[0]: analisis}, {}, CFG
        )
        self.assertEqual(kandidat["insurance"], [])
        self.assertTrue(
            any("volume tipis" in c for c in coret["insurance"]),
            coret["insurance"],
        )

    def test_thin_none_bukan_penghalang(self):
        # thin None (volume tidak diketahui, bentuk kaki A) -> lolos.
        analisis = buat_analisis(
            LAGA[0],
            kaki_ins=buat_kaki(
                LAGA[0], "insurance", 235.5, 0.80, 0.78, 75.0, thin=None
            ),
        )
        kandidat, _coret = ticket_composer._kumpulkan_kandidat(
            {LAGA[0]: analisis}, {}, CFG
        )
        self.assertEqual(len(kandidat["insurance"]), 1)

    def test_thin_utama_boleh_dengan_peringatan(self):
        # Satu kaki Utama tipis (vol $6,3, seperti Utama DET@ATL)
        # BOLEH masuk tiket, tapi ditandai flag + peringatan.
        # Penanda thin di LAGA[4] (PHX@DAL, di pool Utama) — bukan
        # LAGA[0] (DET@ATL kini masuk Asuransi, aturan tanpa kaki
        # kembar).
        analyses = []
        for i, match_id in enumerate(LAGA):
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_main=buat_kaki(
                        match_id,
                        "main",
                        231.5,
                        0.78,
                        0.76,
                        75.0,
                        thin=(i == 4),
                        volume_usd=6.3 if i == 4 else 5000.0,
                    ),
                )
            )
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        main = hasil["main"]
        self.assertIsNotNone(main)
        kaki_tipis = next(k for k in main["legs"] if k["match_id"] == LAGA[4])
        self.assertIn("VOLUME_TIPIS", kaki_tipis["flags"])
        self.assertTrue(
            any("volume tipis" in w for w in hasil["warnings"]),
            hasil["warnings"],
        )
        self.assertIn("volume tipis", hasil["summary"])


class TestGateEdgeAsuransi(unittest.TestCase):
    """Gate edge minimum Asuransi (insiden DEN@CHI 2026-11-23).

    Edge = p_final - harga venue/100 (definisi yang sama dengan
    _rakit_tiket). Ambang config tickets.insurance.min_edge_pct
    3,5% adalah PROPOSAL (pola D12) — titik tengah antara kaki DEN
    yang jebol (+2,5%) dan kaki selamat terendah (+4,4%).
    """

    def _kandidat(self, analisis, cfg=None):
        return ticket_composer._kumpulkan_kandidat(
            {analisis["match_id"]: analisis}, {}, cfg or CFG
        )

    def test_edge_kecil_ditolak_dari_asuransi(self):
        # Pola kaki DEN: p_final 0,786 di harga 76c -> edge +2,6%
        # (< 3,5%) -> dicoret dari Asuransi, alasan "edge_kecil".
        analisis = buat_analisis(
            LAGA[0],
            kaki_ins=buat_kaki(LAGA[0], "insurance", 235.5, 0.80, 0.78, 76.0),
        )
        kandidat, coret = self._kandidat(analisis)
        self.assertEqual(kandidat["insurance"], [])
        self.assertTrue(
            any("edge_kecil" in c for c in coret["insurance"]),
            coret["insurance"],
        )
        self.assertTrue(
            any("+2.6%" in c and "3.5%" in c for c in coret["insurance"]),
            coret["insurance"],
        )
        # Kaki Utama laga yang sama tidak ikut dicoret.
        self.assertEqual(len(kandidat["main"]), 1)

    def test_edge_cukup_lolos_asuransi(self):
        # Kaki standar: p_final 0,786 di harga 75c -> edge +3,6%
        # (>= 3,5%) -> lolos.
        kandidat, _coret = self._kandidat(buat_analisis(LAGA[0]))
        self.assertEqual(len(kandidat["insurance"]), 1)

    def test_edge_tepat_di_ambang_lolos(self):
        # Batas inklusif: edge tepat +3,5% (p_final 0,785 di harga
        # 75c) -> lolos, tidak dicoret.
        analisis = buat_analisis(
            LAGA[0],
            kaki_ins=buat_kaki(LAGA[0], "insurance", 235.5, 0.79, 0.783, 75.0),
        )
        kandidat, _coret = self._kandidat(analisis)
        self.assertEqual(len(kandidat["insurance"]), 1)

    def test_edge_kecil_tidak_menghalangi_utama(self):
        # Gate edge HANYA untuk Asuransi: kaki Utama dengan edge
        # negatif (p_final 0,70 di harga 78c -> -8,0%) tetap lolos
        # sebagai kandidat Utama (ambang Utama hanya peluang 65%).
        analisis = buat_analisis(
            LAGA[0],
            kaki_main=buat_kaki(LAGA[0], "main", 231.5, 0.70, 0.70, 78.0),
        )
        kandidat, _coret = self._kandidat(analisis)
        self.assertEqual(len(kandidat["main"]), 1)

    def test_edge_dibaca_dari_config(self):
        # Ambang 0%: kaki edge +2,6% lolos. Ambang 10%: kaki standar
        # (+3,6%) dicoret. Membuktikan gate memakai nilai config,
        # bukan angka yang ditulis di kode.
        analisis_kecil = buat_analisis(
            LAGA[0],
            kaki_ins=buat_kaki(LAGA[0], "insurance", 235.5, 0.80, 0.78, 76.0),
        )
        cfg_nol = copy.deepcopy(CFG)
        cfg_nol["tickets"]["insurance"]["min_edge_pct"] = 0
        kandidat, _coret = self._kandidat(analisis_kecil, cfg_nol)
        self.assertEqual(len(kandidat["insurance"]), 1)
        cfg_ketat = copy.deepcopy(CFG)
        cfg_ketat["tickets"]["insurance"]["min_edge_pct"] = 10
        kandidat, coret = self._kandidat(buat_analisis(LAGA[0]), cfg_ketat)
        self.assertEqual(kandidat["insurance"], [])
        self.assertTrue(
            any("edge_kecil" in c for c in coret["insurance"]),
            coret["insurance"],
        )

    def test_edge_default_bila_kunci_hilang(self):
        # Config tanpa kunci min_edge_pct -> nilai proposal default
        # 3,5% dipakai (pola yang sama dengan lantai harga / ambang
        # yakin): kaki edge +2,6% tetap dicoret.
        cfg = copy.deepcopy(CFG)
        del cfg["tickets"]["insurance"]["min_edge_pct"]
        analisis = buat_analisis(
            LAGA[0],
            kaki_ins=buat_kaki(LAGA[0], "insurance", 235.5, 0.80, 0.78, 76.0),
        )
        kandidat, coret = self._kandidat(analisis, cfg)
        self.assertEqual(kandidat["insurance"], [])
        self.assertTrue(
            any("edge_kecil" in c for c in coret["insurance"]),
            coret["insurance"],
        )

    def test_edge_gate_dalam_compose(self):
        # Compose penuh: satu kaki Asuransi edge kecil tersisih,
        # Asuransi tetap terracik dari kaki lain, alasan tercatat
        # di ringkasan.
        analyses = []
        for i, match_id in enumerate(LAGA):
            if i == 0:
                kaki_ins = buat_kaki(match_id, "insurance", 235.5, 0.80, 0.78, 76.0)
            else:
                kaki_ins = buat_kaki(match_id, "insurance", 235.5, 0.80, 0.78, 75.0)
            analyses.append(buat_analisis(match_id, kaki_ins=kaki_ins))
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        ins = hasil["insurance"]
        self.assertIsNotNone(ins)
        self.assertEqual(len(ins["legs"]), 3)
        self.assertNotIn(LAGA[0], {k["match_id"] for k in ins["legs"]})
        self.assertIn("edge_kecil", hasil["summary"])
        self.assertIsNotNone(hasil["main"])


class TestTargetPengaliBaru(unittest.TestCase):
    def test_asuransi_target_baru_tiga_kaki(self):
        # Target live 2,0-2,5 (fondasi harga & pengali 2026-11-23,
        # menggantikan 2,5-3,0): slate standar -> 3 kaki @75c = 2,24.
        analyses = slate_standar()
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        self.assertEqual(len(hasil["insurance"]["legs"]), 3)
        self.assertAlmostEqual(hasil["insurance"]["multiplier"], 2.24, places=3)

    def test_asuransi_dua_laga_tidak_cukup(self):
        # 2 laga: maks 1,68 < 2,0 -> Asuransi None. (Versi lama tes
        # ini memakai 3 laga < 2,5; dengan target baru 2,0-2,5, 3 laga
        # = 2,24 SUDAH cukup — batas "tidak cukup" kini 2 laga.)
        analyses = slate_standar(LAGA[:2])
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNone(hasil["insurance"])
        self.assertIn("tidak tercapai", hasil["insurance_reason"])

    def test_target_dibaca_dari_config(self):
        # Varian config target lama 2,2-2,5 -> 3 kaki @75c = 2,24.
        cfg = copy.deepcopy(CFG)
        cfg["tickets"]["insurance"]["multiplier_min"] = 2.2
        cfg["tickets"]["insurance"]["multiplier_max"] = 2.5
        analyses = slate_standar()
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), cfg, stake_total=20, now=SEKARANG
        )
        self.assertEqual(len(hasil["insurance"]["legs"]), 3)
        self.assertAlmostEqual(hasil["insurance"]["multiplier"], 2.24, places=2)


class TestYakinUtamaX5(unittest.TestCase):
    def _kandidat_yakin(self, p_final=0.766, verdict="TETAP_OK", anomali=False):
        return {
            "p_final": p_final,
            "recheck_verdict": verdict,
            "ada_anomali": anomali,
        }

    def test_yakin_semua_syarat_lolos(self):
        subset = [self._kandidat_yakin() for _ in range(3)]
        self.assertTrue(ticket_composer._yakin_utama(subset, 0.75))

    def test_yakin_gagal_p_final_rendah(self):
        subset = [self._kandidat_yakin(), self._kandidat_yakin(p_final=0.746)]
        self.assertFalse(ticket_composer._yakin_utama(subset, 0.75))

    def test_yakin_gagal_perhatian(self):
        subset = [self._kandidat_yakin(), self._kandidat_yakin(verdict="PERHATIAN")]
        self.assertFalse(ticket_composer._yakin_utama(subset, 0.75))

    def test_yakin_gagal_tanpa_recheck(self):
        subset = [self._kandidat_yakin(), self._kandidat_yakin(verdict=None)]
        self.assertFalse(ticket_composer._yakin_utama(subset, 0.75))

    def test_yakin_gagal_anomali(self):
        subset = [self._kandidat_yakin(), self._kandidat_yakin(anomali=True)]
        self.assertFalse(ticket_composer._yakin_utama(subset, 0.75))

    def test_yakin_subset_kosong_gagal(self):
        self.assertFalse(ticket_composer._yakin_utama([], 0.75))

    def _buat_kandidat_pilih(self, harga_list):
        return [
            {
                "harga_jup": harga,
                "decision_prob": 0.766,
                "leg": {"leg_id": f"leg-{i}-{harga:g}"},
            }
            for i, harga in enumerate(harga_list)
        ]

    def test_pilih_subset_di_atas_lunak_yakin_lolos(self):
        # 3 kaki @60c = 4,37 (> lunak 4,0): yakin -> dipilih.
        kandidat = self._buat_kandidat_pilih([60.0, 60.0, 60.0])
        subset, _maks, _pangkas, blokir = ticket_composer._pilih_subset(
            kandidat, 3.0, 5.0, 4.0, 5.5, yakin_fn=lambda s: True
        )
        self.assertIsNotNone(subset)
        self.assertEqual(len(subset), 3)
        self.assertFalse(blokir)

    def test_pilih_subset_di_atas_lunak_tidak_yakin_ditolak(self):
        kandidat = self._buat_kandidat_pilih([60.0, 60.0, 60.0])
        subset, _maks, _pangkas, blokir = ticket_composer._pilih_subset(
            kandidat, 3.0, 5.0, 4.0, 5.5, yakin_fn=lambda s: False
        )
        self.assertIsNone(subset)
        self.assertTrue(blokir)

    def test_pilih_subset_di_bawah_lunak_tidak_kena_yakin(self):
        # 3 kaki @75c = 2,24 (<= lunak 2,5): dipilih walau yakin_fn False.
        kandidat = self._buat_kandidat_pilih([75.0, 75.0, 75.0])
        subset, _maks, _pangkas, blokir = ticket_composer._pilih_subset(
            kandidat, 2.2, 2.5, 2.5, 5.5, yakin_fn=lambda s: False
        )
        self.assertIsNotNone(subset)
        self.assertFalse(blokir)

    def _slate_60c(self, p_model=0.78, p_market=0.76, laga=LAGA[:3]):
        # Kaki Utama @60c: satu-satunya subset valid adalah 3 kaki
        # (4,37x, di atas lunak) — 2 kaki hanya 2,63x < 3,0.
        # Kaki Asuransi meets=False: tanpa ini Asuransi terbentuk
        # dari 3 laga yang sama dan (aturan tanpa kaki kembar)
        # menghabiskan semua laga sehingga Utama tidak punya
        # kandidat — tes yakin ini tidak menguji Asuransi.
        analyses = []
        for match_id in laga:
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_ins=buat_kaki(
                        match_id,
                        "insurance",
                        235.5,
                        0.80,
                        0.78,
                        75.0,
                        meets=False,
                    ),
                    kaki_main=buat_kaki(
                        match_id, "main", 231.5, p_model, p_market, 60.0
                    ),
                )
            )
        return analyses

    def _racik_60c(self, analyses, rechecks):
        return ticket_composer.compose_tickets(
            analyses, rechecks, cfg_tanpa_lantai(), stake_total=20, now=SEKARANG
        )

    def test_compose_yakin_lolos_di_atas_lunak(self):
        # Semua p_final 0,766 + TETAP_OK + tanpa anomali -> 4,37 lolos
        # (di atas target lunak 3,5, fondasi 2026-11-23).
        analyses = self._slate_60c()
        hasil = self._racik_60c(analyses, recheck_semua_ok(analyses))
        self.assertIsNotNone(hasil["main"])
        self.assertAlmostEqual(hasil["main"]["multiplier"], 4.375, places=2)

    def test_compose_tidak_yakin_p_final_rendah(self):
        analyses = self._slate_60c(p_model=0.76, p_market=0.74)  # p_final 0,746
        hasil = self._racik_60c(analyses, recheck_semua_ok(analyses))
        self.assertIsNone(hasil["main"])
        self.assertIn("yakin", hasil["main_reason"])

    def test_compose_tidak_yakin_perhatian(self):
        analyses = self._slate_60c()
        rechecks = []
        for i, analisis in enumerate(analyses):
            if i == 0:
                rechecks.append(
                    buat_recheck(
                        analisis,
                        putusan={
                            "main": (
                                "PERHATIAN",
                                ["harga bergerak 2c"],
                                "model",
                                None,
                            )
                        },
                    )
                )
            else:
                rechecks.append(buat_recheck(analisis))
        hasil = self._racik_60c(analyses, rechecks)
        self.assertIsNone(hasil["main"])
        self.assertIn("yakin", hasil["main_reason"])

    def test_compose_tidak_yakin_tanpa_recheck(self):
        analyses = self._slate_60c()
        hasil = self._racik_60c(analyses, None)
        self.assertIsNone(hasil["main"])
        self.assertIn("yakin", hasil["main_reason"])

    def test_compose_tidak_yakin_anomali(self):
        analyses = self._slate_60c()
        analyses[0]["anomalies"] = [{"type": "sharp_move", "key": "x"}]
        hasil = self._racik_60c(analyses, recheck_semua_ok(analyses))
        self.assertIsNone(hasil["main"])
        self.assertIn("yakin", hasil["main_reason"])

    def test_agresif_melewati_yakin(self):
        # p_final 0,746 (tidak yakin) tapi mode agresif -> 4,37 lolos.
        analyses = self._slate_60c(p_model=0.76, p_market=0.74)
        cfg = cfg_tanpa_lantai()
        cfg["tickets"]["mode"] = "aggressive"
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), cfg, stake_total=20, now=SEKARANG
        )
        self.assertIsNotNone(hasil["main"])
        self.assertAlmostEqual(hasil["main"]["multiplier"], 4.375, places=2)

    def test_yakin_di_atas_lunak_diutamakan(self):
        # Keputusan koordinator integrasi Tahap 4 (menggantikan temuan
        # struktural pekerja B): subset yakin di atas target lunak
        # DIUTAMAKAN atas subset lunak — tanpa ini gate yakin tidak
        # pernah mengubah hasil dan x5 tidak pernah terjadi.
        # Fixture (fondasi 2026-11-23, lunak 3,5): 5 kaki Utama @79c
        # + 1 kaki @75c, semua yakin -> Utama 6 kaki = 4,09. Subset
        # lunak 5 kaki (3,07 / 3,23) punya peluang menang LEBIH
        # TINGGI (0,766^5 vs 0,766^6) tapi tetap kalah karena kelas
        # yakin di atas lunak diutamakan atas kelas lunak.
        # (Fixture lama 5x75c+1x80c tidak lagi membedakan: 5 kaki
        # @75c = 3,98 kini JUGA di atas lunak 3,5 dan yakin, sehingga
        # menang lewat peluang menang — bukan lewat kelas.)
        analyses = []
        for i, match_id in enumerate(LAGA + ["AAA@BBB_2026-11-22"]):
            harga_main = 75.0 if i == 5 else 79.0
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_main=buat_kaki(
                        match_id, "main", 231.5, 0.78, 0.76, harga_main
                    ),
                )
            )
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        main = hasil["main"]
        self.assertIsNotNone(main)
        self.assertEqual(len(main["legs"]), 6)
        self.assertAlmostEqual(main["multiplier"], 4.0948, places=3)

    def test_tidak_yakin_di_atas_lunak_tetap_kalah_dari_lunak(self):
        # Satu kaki tidak yakin (p_final 0,70 < ambang yakin 0,75) ->
        # subset 6 kaki (4,36) tidak yakin -> dipangkas -> subset
        # lunak menang (5 kaki, 3,40x). Pasangan dari
        # test_yakin_di_atas_lunak.
        # Fixture (fondasi 2026-11-23, lunak 3,5): 5 kaki Utama @78c
        # + 1 kaki @75c. Subset 5 kaki tanpa kaki tidak-yakin =
        # 4x78c+1x75c = 3,40 (di dalam jendela lunak, peluang menang
        # tertinggi di kelasnya). Fixture lama (5x75c+1x80c, pemenang
        # 3,73) tidak lagi membedakan: 3,73 kini JUGA di atas lunak
        # 3,5 dan menang lewat kelas yakin, bukan lewat kelas lunak.
        analyses = []
        for i, match_id in enumerate(LAGA + ["AAA@BBB_2026-11-22"]):
            harga_main = 75.0 if i == 5 else 78.0
            p_model, p_market = (0.70, 0.70) if i == 0 else (0.78, 0.76)
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_main=buat_kaki(
                        match_id, "main", 231.5, p_model, p_market, harga_main
                    ),
                )
            )
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        main = hasil["main"]
        self.assertIsNotNone(main)
        self.assertEqual(len(main["legs"]), 5)
        self.assertLessEqual(main["multiplier"], 3.5)
        self.assertAlmostEqual(main["multiplier"], 3.4040, places=3)
        self.assertEqual(len(main["legs"]), 5)


class TestUtamaTakTerlindungi(unittest.TestCase):
    def test_peringatan_saat_asuransi_tidak_terbentuk(self):
        # Bentuk kasus 22 Nov (out/tickets_2026-11-22.json): Utama
        # terracik, Asuransi tidak — dulu warnings KOSONG, kini WAJIB
        # ada peringatan "Tiket Utama tidak terlindungi".
        analyses = []
        for match_id in LAGA:
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_ins=buat_kaki(match_id, "insurance", 235.5, 0.80, 0.78, 70.0),
                )
            )
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNotNone(hasil["main"])
        self.assertIsNone(hasil["insurance"])
        peringatan = [w for w in hasil["warnings"] if "tidak terlindungi" in w]
        self.assertEqual(len(peringatan), 1)
        self.assertIn("Tiket Utama tidak terlindungi", peringatan[0])
        self.assertIn("tidak ada uang yang kembali dari Asuransi", peringatan[0])
        self.assertIn("Tiket Utama tidak terlindungi", hasil["summary"])
        self.assertIn("tidak ada uang yang kembali dari Asuransi", hasil["summary"])

    def test_tanpa_peringatan_bila_kedua_tiket_terbentuk(self):
        analyses = slate_standar()
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNotNone(hasil["insurance"])
        self.assertIsNotNone(hasil["main"])
        self.assertFalse(any("tidak terlindungi" in w for w in hasil["warnings"]))

    def test_tanpa_peringatan_bila_keduanya_none(self):
        analyses = slate_standar(LAGA[:2])
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        self.assertIsNone(hasil["insurance"])
        self.assertIsNone(hasil["main"])
        self.assertFalse(any("tidak terlindungi" in w for w in hasil["warnings"]))


class TestFieldBaruKaki(unittest.TestCase):
    def test_field_baru_disalin_ke_tiket_dan_valid_skema(self):
        climb = {
            "from_line": 233.5,
            "to_line": 237.5,
            "rungs": 2,
            "reason": "harga_minimum",
        }
        analyses = []
        for i, match_id in enumerate(LAGA):
            analyses.append(
                buat_analisis(
                    match_id,
                    kaki_ins=buat_kaki(
                        match_id,
                        "insurance",
                        235.5,
                        0.80,
                        0.78,
                        75.0,
                        thin=False,
                        cushion_points=8.5,
                        cushion_reason="karena sebaran sim lebar",
                        volume_usd=270.0,
                        climb=climb,
                    ),
                    kaki_main=buat_kaki(
                        match_id,
                        "main",
                        231.5,
                        0.78,
                        0.76,
                        75.0,
                        thin=(i == 4),
                        cushion_points=8.5,
                        cushion_reason="karena sebaran sim lebar",
                        volume_usd=6.3 if i == 4 else 5000.0,
                        climb=climb if i == 4 else None,
                    ),
                )
            )
        hasil = ticket_composer.compose_tickets(
            analyses, recheck_semua_ok(analyses), CFG, stake_total=20, now=SEKARANG
        )
        for tiket in (hasil["insurance"], hasil["main"]):
            self.assertIsNotNone(tiket)
            jsonschema.validate(instance=tiket, schema=SKEMA_TIKET)
            self.assertIsNone(ticket_composer.validate_ticket(tiket))
            for kaki in tiket["legs"]:
                self.assertEqual(kaki["cushion_points"], 8.5)
                self.assertEqual(kaki["cushion_reason"], "karena sebaran sim lebar")
                self.assertIsNotNone(kaki["volume_usd"])
        # Kaki tipis + climb dicari di LAGA[4] (PHX@DAL, di pool
        # Utama) — bukan LAGA[0] (DET@ATL kini masuk Asuransi,
        # aturan tanpa kaki kembar).
        kaki_tipis = next(k for k in hasil["main"]["legs"] if k["match_id"] == LAGA[4])
        self.assertTrue(kaki_tipis["thin"])
        self.assertEqual(
            kaki_tipis["climb"],
            {
                "from_line": 233.5,
                "to_line": 237.5,
                "rungs": 2,
                "reason": "harga_minimum",
            },
        )
        self.assertIn("VOLUME_TIPIS", kaki_tipis["flags"])

    def test_salin_climb(self):
        self.assertIsNone(ticket_composer._salin_climb(None))
        self.assertIsNone(ticket_composer._salin_climb("naik"))
        self.assertIsNone(ticket_composer._salin_climb(2))
        self.assertEqual(
            ticket_composer._salin_climb(
                {
                    "from_line": 233.5,
                    "to_line": 237.5,
                    "rungs": 2,
                    "reason": "x",
                }
            ),
            {
                "from_line": 233.5,
                "to_line": 237.5,
                "rungs": 2,
                "reason": "x",
            },
        )
        # rungs bukan int -> None; kunci tak dikenal dibuang.
        self.assertEqual(
            ticket_composer._salin_climb(
                {"from_line": 233.5, "rungs": "dua", "aneh": 1}
            ),
            {
                "from_line": 233.5,
                "to_line": None,
                "rungs": None,
                "reason": None,
            },
        )


def _cdf_normal(median, sigma, garis_min, garis_max, langkah=2.0):
    """CDF total normal (median, sigma) sebagai sim markets.

    Garis-garis tangga tiap ``langkah`` poin; peluang dibulatkan
    6 desimal seperti output sim. Dipakai tes gate banjir supaya
    putusan gate diuji pada CDF realistis (bukan CDF 2 titik).
    """
    markets = {}
    n = int(round((garis_max - garis_min) / langkah)) + 1
    for i in range(n):
        garis = garis_min + i * langkah
        z = (garis - median) / sigma
        p = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        markets[f"total_under_{garis:g}"] = round(p, 6)
    return markets


def _tangga_banjir(baris):
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


def buat_analisis_banjir(
    match_id,
    median,
    sigma,
    kaki_ins,
    kaki_main,
    tangga,
    garis_market=None,
    garis_min=None,
    garis_max=None,
):
    """Artefak nba_analysis dengan CDF normal penuh + tangga.

    Berawal dari ``buat_analisis`` lalu mengganti sim markets
    dengan CDF normal (median, sigma) dan market.totals dengan
    tangga yang diberikan — bentuk yang dipakai gate banjir.
    """
    analisis = buat_analisis(
        match_id,
        kaki_ins=kaki_ins,
        kaki_main=kaki_main,
        median=median,
        garis_market=garis_market if garis_market is not None else median + 1.5,
    )
    analisis["simulation"]["markets"] = _cdf_normal(
        median,
        sigma,
        garis_min if garis_min is not None else median - 30,
        garis_max if garis_max is not None else median + 45,
    )
    analisis["market"]["totals"] = tangga
    return analisis


def _tangga_den():
    """Tangga DEN@CHI sintetis (garis 238,5–274,5; garis >= 258,5 thin).

    Harga naik dengan garis; 252,5 @82¢, 264,5 @94¢ (mirip artefak
    nyata stress_den_chi_2026-11-22.json).

    KALIBRASI ULANG (koreksi banjir 2026-11-23, worker B): dengan
    geser bersih (banjir FT 12,52, bukan 17,54), garis tahan banjir
    pertama turun dari 264,5 ke 258,5 — ambang thin ikut turun
    supaya fixture tetap setia pada DEN nyata (semua garis tahan
    banjir thin) dan kasus wajib "DEN ditolak" tetap teruji.
    """
    baris = []
    garis = 238.5
    while garis <= 274.5 + 1e-9:
        harga = round(55.0 + (garis - 238.5) * 1.5, 1)
        baris.append((garis, harga, 500.0, garis >= 258.5))
        garis = round(garis + 2.0, 9)
    # Harga kunci disamakan dengan artefak nyata.
    for i, (garis, _, volume, thin) in enumerate(baris):
        if abs(garis - 252.5) < 1e-9:
            baris[i] = (garis, 82.0, volume, thin)
        if abs(garis - 264.5) < 1e-9:
            baris[i] = (garis, 94.0, None, True)
    return _tangga_banjir(baris)


class TestGateBanjirAsuransi(unittest.TestCase):
    """Gate skenario banjir Asuransi (R1, insiden DEN@CHI 2026-11-23).

    CATATAN FIXTURE: slate standar file ini memakai CDF 2 titik
    (hanya garis kedua kakinya), sehingga P banjir terjepit
    (clamp) ke p_model kaki Utama — kaki standar lolos gate bukan
    karena tahan banjir, melainkan karena CDF-nya degenerat. Tes
    gate di sini memakai CDF realistis (normal penuh + tangga)
    supaya putusan gate benar-benar diuji; tes lain file ini tidak
    menguji gate banjir.
    """

    def _kandidat(self, analisis, cfg=None):
        return ticket_composer._kumpulkan_kandidat(
            {analisis["match_id"]: analisis}, {}, cfg or CFG
        )

    def test_den_ditolak_gate_banjir(self):
        # Kasus wajib: DEN@CHI 23 Nov — U252,5 (P banjir FT ~64%)
        # harus DITOLAK dari Asuransi; garis tahan-banjir 258,5–
        # 266,5 (5 garis) semuanya thin -> SKIP (bukan dipaksakan),
        # alasan tercatat. Median 233, sigma 19,2 (jangkar P normal
        # 252,5 = 84,5%). Nilai geser bersih (banjir FT 12,52):
        # P banjir 64,2% (sebelum koreksi 54,1%), garis tahan
        # pertama 258,5 (sebelum koreksi 264,5).
        analisis = buat_analisis_banjir(
            LAGA[0],
            233.0,
            19.2,
            kaki_ins=buat_kaki(LAGA[0], "insurance", 252.5, 0.845, 0.83, 82.0),
            kaki_main=buat_kaki(LAGA[0], "main", 250.5, 0.819, 0.80, 79.0),
            tangga=_tangga_den(),
        )
        kandidat, coret = self._kandidat(analisis)
        self.assertEqual(kandidat["insurance"], [])
        alasan = " ".join(coret["insurance"])
        # Penolakan sekarang via equilibrium (tidak ada garis yang
        # lolos semua gate); gate banjir komposer tetap jalan sebagai
        # pertahanan berlapis di atasnya.
        self.assertIn("equilibrium", alasan)
        self.assertIn("258.5", alasan)
        self.assertIn("volume tipis", alasan)
        self.assertIn("64.2%", alasan)
        # Kaki Utama laga yang sama tidak kena gate banjir — garisnya
        # adalah titik equilibrium Utama (U254,5 @79,5¢, ER tertinggi
        # di antara garis yang lolos lantai harga), bukan garis
        # artefak U250,5.
        self.assertEqual(len(kandidat["main"]), 1)
        self.assertEqual(kandidat["main"][0]["line"], 254.5)
        self.assertEqual(kandidat["main"][0]["leg"]["climb"]["reason"], "equilibrium")

    def test_garis_tahan_banjir_dipakai_bila_tidak_thin(self):
        # Median 224, sigma 5: kaki artefak U240,5 (P banjir 78,7%,
        # lolos) -> equilibrium safety-first memilih 250,5 (p_final
        # tertinggi di antara garis yang lolos semua gate, 92,5¢,
        # tidak thin) -> masuk kandidat dengan climb tercatat.
        # PERUBAHAN PERILAKU (safety-first + koreksi banjir,
        # 2026-11-23): sebelumnya (max-ER + geser lama) equilibrium
        # memilih 246,5 — garis tahan-banjir termurah sekaligus ER
        # tertinggi; kini garis tahan pertama adalah 240,5 dan
        # safety-first memilih garis PALING AMAN (250,5), bukan
        # yang termurah. p_final DIHITUNG ULANG di garis baru
        # 0,999612 (bukan 0,927 garis lama).
        tangga = _tangga_banjir(
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
        # p_final = 0,3*0,99 + 0,7*0,90 = 0,927; edge di 88,5¢
        # (harga venue garis naik) = +4,2% -> lolos gate edge.
        analisis = buat_analisis_banjir(
            LAGA[0],
            224.0,
            5.0,
            kaki_ins=buat_kaki(LAGA[0], "insurance", 240.5, 0.99, 0.90, 82.0),
            kaki_main=buat_kaki(LAGA[0], "main", 236.5, 0.99, 0.90, 78.0),
            tangga=tangga,
        )
        kandidat, _coret = self._kandidat(analisis)
        self.assertEqual(len(kandidat["insurance"]), 1)
        kand = kandidat["insurance"][0]
        self.assertEqual(kand["line"], 250.5)
        self.assertEqual(kand["harga_jup"], 92.5)
        self.assertEqual(
            kand["leg"]["climb"],
            {
                "from_line": 240.5,
                "to_line": 250.5,
                "rungs": 5,
                "reason": "equilibrium",
            },
        )
        # p_final dihitung ulang di garis baru: p_model CDF(250,5)
        # 1,0, p_market CDF(250,5 - delta 10,0) 0,999445,
        # blend w=0,3 -> 0,999612 (bukan 0,927 garis lama).
        self.assertEqual(kand["p_final"], 0.999612)

    def test_kaki_lolos_banjir_tetap_diterima(self):
        # Median 224, sigma 5: U252,5 P banjir 98,6% -> lolos tanpa
        # naik garis (climb None).
        analisis = buat_analisis_banjir(
            LAGA[0],
            224.0,
            5.0,
            kaki_ins=buat_kaki(LAGA[0], "insurance", 252.5, 0.99, 0.97, 88.0),
            kaki_main=buat_kaki(LAGA[0], "main", 236.5, 0.99, 0.90, 78.0),
            tangga=[],
        )
        kandidat, _coret = self._kandidat(analisis)
        self.assertEqual(len(kandidat["insurance"]), 1)
        self.assertEqual(kandidat["insurance"][0]["line"], 252.5)
        self.assertIsNone(kandidat["insurance"][0]["leg"].get("climb"))

    def test_tanpa_garis_tahan_banjir_skip(self):
        # Tangga berhenti di 238,5 (di bawah garis tahan 240,5
        # dengan geser bersih — sebelum koreksi tangga berhenti di
        # 244,5, di bawah garis tahan 246,5) -> SKIP dengan alasan
        # tidak_ada_garis_tahan_banjir.
        tangga = _tangga_banjir(
            [
                (232.5, 74.0, 500.0, False),
                (234.5, 76.0, 500.0, False),
                (236.5, 78.0, 500.0, False),
                (238.5, 80.0, 500.0, False),
            ]
        )
        analisis = buat_analisis_banjir(
            LAGA[0],
            224.0,
            5.0,
            kaki_ins=buat_kaki(LAGA[0], "insurance", 240.5, 0.99, 0.90, 82.0),
            kaki_main=buat_kaki(LAGA[0], "main", 236.5, 0.99, 0.90, 78.0),
            tangga=tangga,
        )
        kandidat, coret = self._kandidat(analisis)
        self.assertEqual(kandidat["insurance"], [])
        self.assertTrue(
            any("tidak_ada_garis_tahan_banjir" in c for c in coret["insurance"]),
            coret["insurance"],
        )

    def test_equilibrium_memakai_garis_tebal_di_atas_garis_tahan_thin(self):
        # PERUBAHAN PERILAKU (equilibrium; menggantikan
        # test_garis_tahan_banjir_thin_skip_meski_garis_atas_tebal):
        # garis tahan 246,5 thin, garis di atasnya tebal. Aturan
        # lama (climb) TIDAK melompat dan SKIP; equilibrium menilai
        # SEMUA garis dan safety-first memilih 250,5 @92,5¢
        # (p_final tertinggi di antara yang lolos, tidak thin).
        # Keputusan lama "gate tidak melompat" (LAPORAN-ATURAN-KERAS
        # §7.1) hanya masuk akal di dalam mekanisme climb dan
        # digantikan oleh equilibrium. Thin tetap hard gate
        # Asuransi: garis thin sendiri tidak pernah dipilih.
        tangga = _tangga_banjir(
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
        analisis = buat_analisis_banjir(
            LAGA[0],
            224.0,
            5.0,
            kaki_ins=buat_kaki(LAGA[0], "insurance", 240.5, 0.99, 0.90, 82.0),
            kaki_main=buat_kaki(LAGA[0], "main", 236.5, 0.99, 0.90, 78.0),
            tangga=tangga,
        )
        kandidat, coret = self._kandidat(analisis)
        self.assertEqual(len(kandidat["insurance"]), 1)
        kand = kandidat["insurance"][0]
        self.assertEqual(kand["line"], 250.5)
        self.assertEqual(kand["harga_jup"], 92.5)
        self.assertFalse(kand["thin"])
        self.assertEqual(kand["p_final"], 0.999612)
        self.assertEqual(
            kand["leg"]["climb"],
            {
                "from_line": 240.5,
                "to_line": 250.5,
                "rungs": 5,
                "reason": "equilibrium",
            },
        )
        self.assertEqual(coret["insurance"], [])

    def test_utama_tidak_kena_gate_banjir(self):
        # Kaki Utama dengan P banjir 49,8% (< 65%) tetap lolos —
        # gate banjir HANYA untuk Asuransi. (Garis Utama 236,5:
        # dengan geser bersih, P banjir di 240,5 sudah 78,7% —
        # garis lama 240,5 tidak lagi membuktikan apa-apa, jadi
        # fixture dipindah ke 236,5 supaya kakinya benar-benar
        # gagal banjir; koreksi banjir 2026-11-23, worker B.)
        tangga = _tangga_banjir([(236.5, 78.0, 500.0, False)])
        analisis = buat_analisis_banjir(
            LAGA[0],
            224.0,
            5.0,
            kaki_ins=buat_kaki(
                LAGA[0],
                "insurance",
                240.5,
                0.99,
                0.90,
                82.0,
                meets=False,
                reason="bantalan_kurang",
            ),
            kaki_main=buat_kaki(LAGA[0], "main", 236.5, 0.99, 0.90, 78.0),
            tangga=tangga,
        )
        kandidat, _coret = self._kandidat(analisis)
        self.assertEqual(len(kandidat["main"]), 1)
        self.assertEqual(kandidat["main"][0]["line"], 236.5)

    def test_skenario_tidak_bisa_dihitung_fail_closed(self):
        # Artefak tanpa sim markets (CDF tidak bisa dibangun) ->
        # kaki Asuransi ditolak fail-closed; Utama tetap lolos.
        analisis = buat_analisis(LAGA[0])
        analisis["simulation"]["markets"] = {}
        kandidat, coret = self._kandidat(analisis)
        self.assertEqual(kandidat["insurance"], [])
        self.assertTrue(
            any("tidak bisa dihitung" in c for c in coret["insurance"]),
            coret["insurance"],
        )
        self.assertEqual(len(kandidat["main"]), 1)

    def test_stress_dihitung_sekali_per_laga(self):
        # skenario_panas dipanggil sekali per match_id, bukan per
        # kaki (8 laga standar -> 8 panggilan).
        analyses = slate_standar()
        nyata = ticket_composer.stress_mod.skenario_panas
        with mock.patch.object(
            ticket_composer.stress_mod, "skenario_panas", wraps=nyata
        ) as tiruan:
            ticket_composer.compose_tickets(
                analyses,
                recheck_semua_ok(analyses),
                CFG,
                stake_total=20,
                now=SEKARANG,
            )
        self.assertEqual(tiruan.call_count, len(analyses))

    def test_config_kunci_hilang_config_error(self):
        cfg = copy.deepcopy(CFG)
        del cfg["tickets"]["insurance"]["stress_gate_scenario"]
        with self.assertRaises(config.ConfigError):
            ticket_composer.compose_tickets(
                slate_standar(), None, cfg, stake_total=20, now=SEKARANG
            )

    def test_config_nilai_tidak_dikenal_config_error(self):
        cfg = copy.deepcopy(CFG)
        cfg["tickets"]["insurance"]["stress_gate_scenario"] = "banjir"
        with self.assertRaises(config.ConfigError):
            ticket_composer.compose_tickets(
                slate_standar(), None, cfg, stake_total=20, now=SEKARANG
            )

    def test_racik_penuh_dengan_kaki_naik_garis(self):
        # End-to-end: 10 laga, semua kaki Asuransi naik garis ke
        # 250,5 @92,5¢ (titik equilibrium safety-first — p_final
        # tertinggi di antara garis yang lolos semua gate); 10 kaki
        # -> pengali 2,06 (target 2,0–2,5; 9 kaki hanya 1,91).
        # Tiket mencatat climb alasan "equilibrium" di tiap
        # kakinya (dulu "banjir" — equilibrium menggantikan
        # mekanisme climb banjir).
        # (Garis naik itu mahal — Asuransi butuh banyak kaki, sesuai
        # arahan user "tumpuk banyak kaki di harga tinggi".)
        # PERUBAHAN (safety-first, 2026-11-23): sebelumnya (max-ER)
        # 7 kaki naik ke 246,5 @88,5¢ (pengali 2,22); kini garis
        # paling aman 250,5 @92,5¢ butuh 10 kaki untuk mencapai
        # x2 — konsekuensi jujur safety-first, didokumentasikan di
        # LAPORAN-ASURANSI-BARU.md.
        tangga = _tangga_banjir(
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
        laga = LAGA + ["UTA@MIN_2026-11-22", "SAS@POR_2026-11-22"]
        analyses = [
            buat_analisis_banjir(
                match_id,
                224.0,
                5.0,
                kaki_ins=buat_kaki(match_id, "insurance", 240.5, 0.99, 0.90, 82.0),
                kaki_main=buat_kaki(match_id, "main", 236.5, 0.99, 0.90, 78.0),
                tangga=tangga,
            )
            for match_id in laga
        ]
        hasil = ticket_composer.compose_tickets(
            analyses,
            recheck_semua_ok(analyses),
            CFG,
            stake_total=20,
            now=SEKARANG,
        )
        tiket = hasil["insurance"]
        self.assertIsNotNone(tiket)
        self.assertEqual(len(tiket["legs"]), 10)
        for kaki in tiket["legs"]:
            # Format seleksi tiket NBA: "Under 250.5 (TIM@TIM)".
            self.assertTrue(
                kaki["selection"].startswith("Under 250.5"),
                kaki["selection"],
            )
            self.assertEqual(
                kaki["climb"],
                {
                    "from_line": 240.5,
                    "to_line": 250.5,
                    "rungs": 5,
                    "reason": "equilibrium",
                },
            )
            self.assertEqual(kaki["jup_price_cents"], 92.5)


class TestEquilibriumSkipIntegrasi(unittest.TestCase):
    """Integrasi equilibrium + skip di komposer (end-to-end).

    Tes artefak nyata memakai out/analysis_live_2026-11-22.json
    (file runtime, gitignored) dan di-skip bila file tidak ada.
    """

    @classmethod
    def setUpClass(cls):
        path = REPO_ROOT / "out" / "analysis_live_2026-11-22.json"
        cls.path_artefak = path
        cls.analyses = None
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            cls.analyses = [
                match.get("nba_analysis") or {} for match in data.get("matches") or []
            ]

    def _butuh_artefak(self):
        if self.analyses is None:
            self.skipTest("out/analysis_live_2026-11-22.json tidak ada (runtime)")

    def test_skip_den_artefak_nyata_di_komposer(self):
        # DEN@CHI live di-skip dari kedua tiket di komposer (pola
        # Denver) — tidak ada kandidat DEN di tiket mana pun, dan
        # entri skip tercatat dengan pemicu + alasan.
        self._butuh_artefak()
        hasil = ticket_composer.compose_tickets(
            self.analyses, None, CFG, stake_total=20, now=SEKARANG
        )
        di_skip = {
            entri["match_id"]: entri for entri in hasil.get("skipped_matches") or []
        }
        self.assertIn("DEN@CHI_2026-11-22", di_skip)
        entri_den = di_skip["DEN@CHI_2026-11-22"]
        self.assertEqual(entri_den["pemicu"], ["pola_denver"])
        self.assertIn("pola Denver", entri_den["alasan"])
        # Tidak ada kaki DEN di kandidat mana pun.
        per_laga = ticket_composer._terbaru_per_laga(self.analyses, "generated_at")
        kandidat, _coret = ticket_composer._kumpulkan_kandidat(per_laga, {}, CFG)
        for tiket in ("insurance", "main"):
            self.assertNotIn(
                "DEN@CHI_2026-11-22",
                [k["match_id"] for k in kandidat[tiket]],
            )
        # Blok skip tampil di ringkasan.
        self.assertIn("LAGA YANG DI-SKIP DARI AWAL", hasil["summary"])
        self.assertIn("DEN@CHI_2026-11-22", hasil["summary"])

    def test_flag_dimatikan_perilaku_lama_persis(self):
        # A/B: dengan ketiga flag dimatikan (equilibrium, skip_awal,
        # vonis), komposer berperilaku persis seperti aturan lama —
        # tidak ada skipped_matches, DET@ATL kembali jadi kandidat
        # Utama (U237,5, aturan lama tidak mengenal skip OT), dan
        # BOS@GSW HILANG dari kandidat Utama (kaki artefaknya
        # U219,5 di bawah lantai 75¢ — equilibrium-lah yang
        # menyelamatkannya ke U223,5).
        # Flag vonis ikut dimatikan: vonis adalah gate baru (worker
        # sistem vonis) — DET@ATL bervonis KUNING (dievaluasi) dan
        # akan dikeluarkan dari kandidat bila vonis aktif. "Perilaku
        # lama" berarti SEMUA gate baru mati.
        self._butuh_artefak()
        cfg_lama = copy.deepcopy(CFG)
        cfg_lama["equilibrium"]["enabled"] = False
        cfg_lama["skip_awal"]["enabled"] = False
        cfg_lama["vonis"]["enabled"] = False
        hasil_lama = ticket_composer.compose_tickets(
            self.analyses, None, cfg_lama, stake_total=20, now=SEKARANG
        )
        self.assertEqual(hasil_lama.get("skipped_matches"), [])
        self.assertNotIn("LAGA YANG DI-SKIP DARI AWAL", hasil_lama["summary"])
        per_laga = ticket_composer._terbaru_per_laga(self.analyses, "generated_at")
        kandidat_lama, _ = ticket_composer._kumpulkan_kandidat(per_laga, {}, cfg_lama)
        main_lama = {k["match_id"]: k for k in kandidat_lama["main"]}
        self.assertIn("DET@ATL_2026-11-22", main_lama)
        self.assertEqual(main_lama["DET@ATL_2026-11-22"]["line"], 237.5)
        self.assertNotIn("BOS@GSW_2026-11-22", main_lama)
        # Aturan baru: DET hilang (skip OT), BOS hadir (equilibrium).
        kandidat_baru, _ = ticket_composer._kumpulkan_kandidat(per_laga, {}, CFG)
        main_baru = {k["match_id"]: k for k in kandidat_baru["main"]}
        self.assertNotIn("DET@ATL_2026-11-22", main_baru)
        self.assertIn("BOS@GSW_2026-11-22", main_baru)
        self.assertEqual(main_baru["BOS@GSW_2026-11-22"]["line"], 223.5)
        self.assertEqual(
            main_baru["BOS@GSW_2026-11-22"]["leg"]["climb"]["reason"],
            "equilibrium",
        )

    def test_kaki_equilibrium_leg_id_tidak_berubah(self):
        # Kaki equilibrium BOS@GSW memakai leg_id kaki artefak
        # (recheck tetap bisa mencocokkan kaki yang digeser
        # garisnya).
        self._butuh_artefak()
        artefak_bos = next(
            a for a in self.analyses if a.get("match_id") == "BOS@GSW_2026-11-22"
        )
        leg_id_artifak = next(
            leg["leg_id"] for leg in artefak_bos["legs"] if leg.get("ticket") == "main"
        )
        per_laga = ticket_composer._terbaru_per_laga(self.analyses, "generated_at")
        kandidat, _ = ticket_composer._kumpulkan_kandidat(per_laga, {}, CFG)
        kand_bos = next(
            k for k in kandidat["main"] if k["match_id"] == "BOS@GSW_2026-11-22"
        )
        self.assertEqual(kand_bos["leg"]["leg_id"], leg_id_artifak)
        self.assertEqual(kand_bos["line"], 223.5)

    def test_skip_ot_sintetis_di_komposer(self):
        # Laga dengan OT sim 3,0% di-skip komposer (pemicu
        # ot_tinggi) meski kakinya lolos semua gate — tanpa
        # bergantung pada artefak runtime.
        analisis = buat_analisis_banjir(
            LAGA[0],
            224.0,
            5.0,
            kaki_ins=buat_kaki(LAGA[0], "insurance", 240.5, 0.99, 0.90, 82.0),
            kaki_main=buat_kaki(LAGA[0], "main", 236.5, 0.99, 0.90, 78.0),
            tangga=_tangga_banjir(
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
        )
        analisis["simulation"]["score_distribution"]["ot_probability"] = 0.03
        hasil = ticket_composer.compose_tickets(
            [analisis], None, CFG, stake_total=20, now=SEKARANG
        )
        self.assertEqual(len(hasil.get("skipped_matches") or []), 1)
        entri = hasil["skipped_matches"][0]
        self.assertEqual(entri["match_id"], LAGA[0])
        self.assertEqual(entri["pemicu"], ["ot_tinggi"])
        self.assertIsNone(hasil["insurance"])
        self.assertIsNone(hasil["main"])


class TestGateSkenarioUnit(unittest.TestCase):
    """Tes unit _gate_skenario + _kaki_naik_garis (tanpa artefak)."""

    def _hasil_stress(self, **ubah):
        hasil = {
            "banjir_terburuk": "banjir_ft",
            "kaki": [],
        }
        hasil.update(ubah)
        return hasil

    def _entri(self, **ubah):
        entri = {
            "line": 252.5,
            "ticket": "insurance",
            "p_under": {
                "normal": 0.845,
                "banjir_3p": 0.62,
                "banjir_ft": 0.54,
                "setan": 0.53,
                "konservatif": 0.80,
            },
            "tahan_banjir": False,
            "garis_tahan_banjir": {
                "line": 264.5,
                "price_cents": 94.0,
                "jup_estimated_cents": 94.5,
                "volume_usd": None,
                "thin": True,
            },
            "alasan_tidak_tahan_banjir": None,
            "tahan_setan": False,
            "garis_tahan_setan": {
                "line": 266.5,
                "price_cents": 95.0,
                "jup_estimated_cents": 95.5,
                "volume_usd": 400.0,
                "thin": False,
            },
            "alasan_tidak_tahan_setan": None,
        }
        entri.update(ubah)
        return entri

    def test_lolos_bila_p_banjir_di_atas_ambang(self):
        entri = self._entri()
        entri["p_under"] = dict(entri["p_under"], banjir_ft=0.80)
        putusan, p, garis, alasan = ticket_composer._gate_skenario(
            self._hasil_stress(), entri, "banjir_terburuk", 0.74
        )
        self.assertEqual((putusan, p, garis, alasan), ("lolos", 0.80, None, None))

    def test_naik_bila_gagal_tapi_ada_garis_tahan(self):
        putusan, p, garis, alasan = ticket_composer._gate_skenario(
            self._hasil_stress(), self._entri(), "banjir_terburuk", 0.74
        )
        self.assertEqual(putusan, "naik")
        self.assertEqual(p, 0.54)
        self.assertEqual(garis["line"], 264.5)
        self.assertIsNone(alasan)

    def test_tolak_bila_tidak_ada_garis_tahan(self):
        entri = self._entri(
            garis_tahan_banjir=None,
            alasan_tidak_tahan_banjir="tidak ada garis tangga yang lolos",
        )
        putusan, p, garis, alasan = ticket_composer._gate_skenario(
            self._hasil_stress(), entri, "banjir_terburuk", 0.74
        )
        self.assertEqual(putusan, "tolak")
        self.assertEqual(p, 0.54)
        self.assertIsNone(garis)
        self.assertIn("tidak ada garis tangga yang lolos", alasan)

    def test_tolak_bila_p_tidak_tersedia(self):
        entri = self._entri()
        entri["p_under"] = {"normal": 0.845}
        putusan, p, garis, alasan = ticket_composer._gate_skenario(
            self._hasil_stress(), entri, "banjir_terburuk", 0.74
        )
        self.assertEqual(putusan, "tolak")
        self.assertIsNone(p)
        self.assertIsNone(garis)
        self.assertIn("banjir_ft", alasan)

    def test_skenario_setan_memakai_kunci_setan(self):
        # Cabang "setan" (parameter skenario): P + garis dari kunci
        # setan, bukan banjir.
        putusan, p, garis, alasan = ticket_composer._gate_skenario(
            self._hasil_stress(), self._entri(), "setan", 0.74
        )
        self.assertEqual(putusan, "naik")
        self.assertEqual(p, 0.53)
        self.assertEqual(garis["line"], 266.5)
        self.assertIsNone(alasan)

    def test_skenario_setan_hilang_fail_closed(self):
        # Output stress tanpa kunci "setan" (sebelum Worker A
        # selesai) -> tolak, bukan lolos diam-diam.
        entri = self._entri()
        p_under = dict(entri["p_under"])
        del p_under["setan"]
        entri["p_under"] = p_under
        putusan, p, garis, _alasan = ticket_composer._gate_skenario(
            self._hasil_stress(), entri, "setan", 0.74
        )
        self.assertEqual(putusan, "tolak")
        self.assertIsNone(p)
        self.assertIsNone(garis)

    def test_skenario_tidak_dikenal_value_error(self):
        with self.assertRaises(ValueError):
            ticket_composer._gate_skenario(
                self._hasil_stress(), self._entri(), "hujan", 0.74
            )

    def test_kaki_naik_garis_dasar(self):
        kaki = buat_kaki(LAGA[0], "insurance", 240.5, 0.98, 0.90, 82.0)
        tangga = _tangga_banjir(
            [
                (240.5, 82.0, 500.0, False),
                (242.5, 84.0, 500.0, False),
                (244.5, 86.0, 500.0, False),
                (246.5, 88.0, 500.0, False),
                (248.5, 80.0, 500.0, False),
            ]
        )
        baru = ticket_composer._kaki_naik_garis(
            kaki,
            {
                "line": 248.5,
                "price_cents": 80.0,
                "jup_estimated_cents": 80.5,
                "volume_usd": 500.0,
                "thin": False,
            },
            tangga,
        )
        self.assertIsNotNone(baru)
        self.assertEqual(baru["line"], 248.5)
        self.assertEqual(baru["jup_estimated_cents"], 80.5)
        self.assertEqual(
            baru["climb"],
            {"from_line": 240.5, "to_line": 248.5, "rungs": 4, "reason": "banjir"},
        )
        # Kaki asal tidak berubah.
        self.assertEqual(kaki["line"], 240.5)
        self.assertIsNone(kaki.get("climb"))

    def test_kaki_naik_garis_dirangkai_dengan_climb_cushion(self):
        kaki = buat_kaki(
            LAGA[0],
            "insurance",
            240.5,
            0.98,
            0.90,
            82.0,
            climb={
                "from_line": 236.5,
                "to_line": 240.5,
                "rungs": 2,
                "reason": "harga_minimum",
            },
        )
        tangga = _tangga_banjir(
            [
                (236.5, 78.0, 500.0, False),
                (238.5, 80.0, 500.0, False),
                (240.5, 82.0, 500.0, False),
                (242.5, 84.0, 500.0, False),
                (244.5, 86.0, 500.0, False),
                (246.5, 88.0, 500.0, False),
                (248.5, 80.0, 500.0, False),
            ]
        )
        baru = ticket_composer._kaki_naik_garis(
            kaki,
            {
                "line": 248.5,
                "price_cents": 80.0,
                "jup_estimated_cents": 80.5,
                "volume_usd": 500.0,
                "thin": False,
            },
            tangga,
        )
        self.assertEqual(
            baru["climb"],
            {
                "from_line": 236.5,
                "to_line": 248.5,
                "rungs": 6,
                "reason": "harga_minimum+banjir",
            },
        )

    def test_kaki_naik_garis_tolak_garis_tidak_lebih_tinggi(self):
        kaki = buat_kaki(LAGA[0], "insurance", 240.5, 0.98, 0.90, 82.0)
        self.assertIsNone(
            ticket_composer._kaki_naik_garis(kaki, {"line": 240.5}, _tangga_banjir([]))
        )
        self.assertIsNone(
            ticket_composer._kaki_naik_garis(kaki, {"line": 238.5}, _tangga_banjir([]))
        )


if __name__ == "__main__":
    unittest.main()
