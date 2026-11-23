"""Tes engine/live_status.py — status tiket live + proyeksi total akhir.

SEMUA offline dari fixture sintetis, 0 kredit Odds API. Semua angka
harapan dihitung tangan (aritmetikanya ditulis di komentar per tes) —
bukan hasil menjalankan kode yang diuji.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from engine import live_status

CFG = config.load_playstyle()


def buat_live(
    match_id="DET@ATL_2026-11-22",
    status="berjalan",
    period=2,
    clock_display="12:00",
    seconds_remaining=1440,
    home_score=60,
    away_score=56,
):
    """Satu dict LiveGame (kontrak pekerja A)."""
    tim = match_id.split("_")[0] if "_" in match_id else match_id
    away, home = tim.split("@") if "@" in tim else ("AWAY", "HOME")
    return {
        "match_id": match_id,
        "espn_game_id": "401000001",
        "home_abbr": home,
        "away_abbr": away,
        "home_team": f"Tim {home}",
        "away_team": f"Tim {away}",
        "status": status,
        "period": period,
        "clock_display": clock_display,
        "seconds_remaining": seconds_remaining,
        "home_score": home_score,
        "away_score": away_score,
        "line_scores": [],
        "stats": {},
        "fetched_at": "2026-11-22T13:00:00Z",
        "source": "espn",
    }


def buat_kaki(
    match_id="DET@ATL_2026-11-22",
    garis=237.5,
    market="total_under",
    leg_id="leg-1",
    selection=None,
):
    """Satu kaki tiket (bentuk peracik: garis di dalam selection)."""
    tim = match_id.split("_")[0] if "_" in match_id else match_id
    if selection is None:
        selection = f"Under {garis:g} ({tim})"
    return {
        "leg_id": leg_id,
        "match_id": match_id,
        "sport": "nba",
        "market": market,
        "selection": selection,
        "p_model": 0.80,
        "p_market": 0.78,
        "p_final": 0.786,
        "jup_price_cents": 75,
        "edge": 0.036,
        "ev_pct": 3.2,
        "status": "OK",
    }


def buat_tiket(kaki, tipe="Utama", ticket_id="tkt-2026-11-22-utm"):
    """Satu dict tiket minimal (sesuai ticket.schema.json)."""
    return {
        "ticket_id": ticket_id,
        "type": tipe,
        "stake": 10,
        "multiplier": 3.5,
        "combo_spread_pct": 5.5,
        "legs": kaki,
        "metrics": {},
        "notes": None,
        "option_label": None,
        "slate_id": None,
        "placed_at": None,
        "result": "PENDING",
        "cashout_amount": None,
    }


class TestProjectFinalTotal(unittest.TestCase):
    def test_proyeksi_blend(self):
        # Laga berjalan 24 menit (sisa 24 menit), total 118 (60+58),
        # median pra-laga 226. live_rate = 118/24 = 4,9167; pregame_rate
        # = 226/48 = 4,7083; w_live = 24/48 = 0,5; campuran = 4,8125;
        # projected = 118 + 4,8125*24 = 118 + 115,5 = 233,5.
        game = buat_live(home_score=60, away_score=58)
        hasil = live_status.project_final_total(game, 226, CFG)
        self.assertEqual(hasil["method"], "blend")
        self.assertAlmostEqual(hasil["projected_total"], 233.5, places=6)
        self.assertAlmostEqual(hasil["live_rate_ppm"], 118 / 24, places=4)
        self.assertAlmostEqual(hasil["pregame_rate_ppm"], 226 / 48, places=4)
        self.assertEqual(hasil["minutes_elapsed"], 24.0)
        self.assertEqual(hasil["minutes_remaining"], 24.0)
        self.assertFalse(hasil["ot_risk"])

    def test_proyeksi_live_rate_only(self):
        # Laga yang sama tanpa median: projected = 118 + (118/24)*24
        # = 118 + 118 = 236,0; metode live_rate_only + catatan.
        game = buat_live(home_score=60, away_score=58)
        hasil = live_status.project_final_total(game, None, CFG)
        self.assertEqual(hasil["method"], "live_rate_only")
        self.assertAlmostEqual(hasil["projected_total"], 236.0, places=6)
        self.assertIsNone(hasil["pregame_rate_ppm"])
        self.assertTrue(any("pra-laga" in n for n in hasil["notes"]))

    def test_proyeksi_final(self):
        # Laga selesai: projected = total akhir 220 (112+108), metode
        # final, elapsed 48 menit, sisa 0, tanpa risiko OT.
        game = buat_live(
            status="selesai",
            period=4,
            seconds_remaining=0,
            home_score=112,
            away_score=108,
        )
        hasil = live_status.project_final_total(game, 226, CFG)
        self.assertEqual(hasil["method"], "final")
        self.assertEqual(hasil["projected_total"], 220)
        self.assertEqual(hasil["minutes_elapsed"], 48.0)
        self.assertEqual(hasil["minutes_remaining"], 0.0)
        self.assertFalse(hasil["ot_risk"])

    def test_proyeksi_final_ot(self):
        # Laga selesai di OT ke-1 (period 5): elapsed = 48 + 5 = 53 menit.
        game = buat_live(
            status="selesai",
            period=5,
            seconds_remaining=0,
            home_score=120,
            away_score=118,
        )
        hasil = live_status.project_final_total(game, None, CFG)
        self.assertEqual(hasil["method"], "final")
        self.assertEqual(hasil["projected_total"], 238)
        self.assertEqual(hasil["minutes_elapsed"], 53.0)
        self.assertAlmostEqual(hasil["live_rate_ppm"], 238 / 53, places=4)

    def test_proyeksi_belum_mulai(self):
        # Laga belum mulai: tidak ada proyeksi (metode None), elapsed 0,
        # sisa 48 menit.
        game = buat_live(
            status="belum_mulai",
            period=None,
            clock_display=None,
            seconds_remaining=None,
            home_score=None,
            away_score=None,
        )
        hasil = live_status.project_final_total(game, 226, CFG)
        self.assertIsNone(hasil["projected_total"])
        self.assertIsNone(hasil["method"])
        self.assertEqual(hasil["minutes_elapsed"], 0.0)
        self.assertEqual(hasil["minutes_remaining"], 48.0)
        self.assertFalse(hasil["ot_risk"])

    def test_proyeksi_ot(self):
        # OT ke-1 (period 5), jam 1:30 tersisa, total 206 (104+102).
        # elapsed = 48 + 5 - 1,5 = 51,5 menit; sisa 1,5 menit.
        # live_rate = 206/51,5 = 4,0; w_live = 51,5/48 dijepit 1,0;
        # projected = 206 + 4,0*1,5 = 212,0. Selisih 2 <= 3 dan sisa
        # 1,5 <= 2,0 menit -> ot_risk True (risiko OT berikutnya).
        game = buat_live(
            period=5,
            clock_display="1:30",
            seconds_remaining=0,
            home_score=104,
            away_score=102,
        )
        hasil = live_status.project_final_total(game, 226, CFG)
        self.assertEqual(hasil["method"], "blend")
        self.assertAlmostEqual(hasil["projected_total"], 212.0, places=6)
        self.assertEqual(hasil["minutes_elapsed"], 51.5)
        self.assertEqual(hasil["minutes_remaining"], 1.5)
        self.assertAlmostEqual(hasil["live_rate_ppm"], 4.0, places=6)
        self.assertTrue(hasil["ot_risk"])
        self.assertTrue(any("OT" in n for n in hasil["notes"]))

    def test_proyeksi_ot_fallback_seconds_remaining(self):
        # OT dengan jam tidak terurai ("End OT") tapi seconds_remaining
        # = 90 detik (valid, 0 < 90 <= 300): dipakai sebagai sisa OT.
        # Angka sama dengan test_proyeksi_ot: projected 212,0.
        game = buat_live(
            period=5,
            clock_display="End OT",
            seconds_remaining=90,
            home_score=104,
            away_score=102,
        )
        hasil = live_status.project_final_total(game, 226, CFG)
        self.assertAlmostEqual(hasil["projected_total"], 212.0, places=6)
        self.assertEqual(hasil["minutes_remaining"], 1.5)
        self.assertTrue(hasil["ot_risk"])

    def test_proyeksi_ot_risk_regulasi(self):
        # Kuarter 4, sisa 90 detik (1,5 menit), total 218 (110+108),
        # median 226. elapsed = 46,5; live_rate = 218/46,5 = 4,68817;
        # pregame_rate = 4,70833; w = 46,5/48 = 0,96875; campuran =
        # 0,96875*4,68817 + 0,03125*4,70833 = 4,68880; projected =
        # 218 + 4,68880*1,5 = 225,033. Selisih 2 <= 3, sisa 1,5 <= 2,0
        # -> ot_risk True.
        game = buat_live(
            period=4,
            clock_display="1:30",
            seconds_remaining=90,
            home_score=110,
            away_score=108,
        )
        hasil = live_status.project_final_total(game, 226, CFG)
        self.assertEqual(hasil["method"], "blend")
        self.assertAlmostEqual(hasil["projected_total"], 225.03, places=2)
        self.assertTrue(hasil["ot_risk"])

    def test_proyeksi_tanpa_ot_risk_selisih_lebar(self):
        # Sisa 90 detik tapi selisih 7 poin (> 3): ot_risk False.
        game = buat_live(
            period=4,
            clock_display="1:30",
            seconds_remaining=90,
            home_score=115,
            away_score=108,
        )
        hasil = live_status.project_final_total(game, 226, CFG)
        self.assertFalse(hasil["ot_risk"])

    def test_proyeksi_kurang_satu_menit(self):
        # Laga baru berjalan 10 detik (sisa 2870 detik): elapsed 1/6
        # menit < 1 menit -> tidak ada proyeksi, alasannya tercatat.
        game = buat_live(
            period=1,
            clock_display="11:50",
            seconds_remaining=2870,
            home_score=2,
            away_score=0,
        )
        hasil = live_status.project_final_total(game, 226, CFG)
        self.assertIsNone(hasil["projected_total"])
        self.assertIsNone(hasil["method"])
        self.assertTrue(any("1 menit" in n for n in hasil["notes"]))

    def test_proyeksi_skor_tidak_ada(self):
        # Laga berjalan tapi skor None: tidak ada proyeksi.
        game = buat_live(home_score=None, away_score=None)
        hasil = live_status.project_final_total(game, 226, CFG)
        self.assertIsNone(hasil["projected_total"])
        self.assertTrue(any("Skor" in n for n in hasil["notes"]))

    def test_proyeksi_jam_fallback(self):
        # seconds_remaining None, period 3, jam 6:00: sisa = (4-3)*720
        # + 360 = 1080 detik = 18 menit; elapsed 30 menit. Total 145
        # (75+70); live_rate = 145/30 = 4,8333; tanpa median: projected
        # = 145 + 4,8333*18 = 145 + 87 = 232,0.
        game = buat_live(
            period=3,
            clock_display="6:00",
            seconds_remaining=None,
            home_score=75,
            away_score=70,
        )
        hasil = live_status.project_final_total(game, None, CFG)
        self.assertEqual(hasil["method"], "live_rate_only")
        self.assertAlmostEqual(hasil["projected_total"], 232.0, places=6)
        self.assertEqual(hasil["minutes_elapsed"], 30.0)
        self.assertEqual(hasil["minutes_remaining"], 18.0)

    def test_proyeksi_status_tidak_dikenal(self):
        game = buat_live(status="ditunda")
        hasil = live_status.project_final_total(game, 226, CFG)
        self.assertIsNone(hasil["projected_total"])
        self.assertTrue(any("tidak dikenal" in n for n in hasil["notes"]))

    def test_proyeksi_median_tidak_valid(self):
        # Median negatif (-5) diperlakukan seolah tidak ada: metode
        # live_rate_only + catatan, bukan angka karangan.
        game = buat_live(home_score=60, away_score=58)
        hasil = live_status.project_final_total(game, -5, CFG)
        self.assertEqual(hasil["method"], "live_rate_only")
        self.assertAlmostEqual(hasil["projected_total"], 236.0, places=6)
        self.assertIsNone(hasil["pregame_rate_ppm"])


class TestEvaluateLeg(unittest.TestCase):
    # Laga dasar: 24 menit berjalan, sisa 24 menit, total 116 (60+56);
    # tanpa median, projected = 116 + (116/24)*24 = 232,0.
    def test_leg_aman_di_batas(self):
        # Garis 238: margin = 238 - 232 = 6,0 = ambang aman -> AMAN.
        leg = buat_kaki(garis=238)
        hasil = live_status.evaluate_leg(leg, buat_live(), None, CFG)
        self.assertEqual(hasil["status"], "AMAN")
        self.assertEqual(hasil["line"], 238)
        self.assertAlmostEqual(hasil["projected_total"], 232.0, places=6)
        self.assertAlmostEqual(hasil["margin_points"], 6.0, places=6)

    def test_leg_waspada_di_batas(self):
        # Garis 234: margin = 234 - 232 = 2,0 = ambang waspada -> WASPADA.
        leg = buat_kaki(garis=234)
        hasil = live_status.evaluate_leg(leg, buat_live(), None, CFG)
        self.assertEqual(hasil["status"], "WASPADA")
        self.assertAlmostEqual(hasil["margin_points"], 2.0, places=6)

    def test_leg_waspada_di_bawah_aman(self):
        # Garis 237,9: margin 5,9 (< 6,0, >= 2,0) -> WASPADA.
        leg = buat_kaki(garis=237.9)
        hasil = live_status.evaluate_leg(leg, buat_live(), None, CFG)
        self.assertEqual(hasil["status"], "WASPADA")
        self.assertAlmostEqual(hasil["margin_points"], 5.9, places=6)

    def test_leg_terancam(self):
        # Garis 233,5: margin 1,5 (< 2,0) -> TERANCAM. Garis 230:
        # margin -2,0 (proyeksi di atas garis) -> TERANCAM juga.
        for garis in (233.5, 230):
            leg = buat_kaki(garis=garis)
            hasil = live_status.evaluate_leg(leg, buat_live(), None, CFG)
            self.assertEqual(hasil["status"], "TERANCAM", garis)
        leg = buat_kaki(garis=230)
        hasil = live_status.evaluate_leg(leg, buat_live(), None, CFG)
        self.assertAlmostEqual(hasil["margin_points"], -2.0, places=6)

    def test_leg_kalah_saat_total_berjalan_lewat_garis(self):
        # Insiden DEN@CHI 2026-11-23: laga berjalan, total 116, garis
        # 110 — total berjalan sudah di atas garis, Under sudah pasti
        # kalah (total hanya bisa naik). Dulu: TERANCAM.
        leg = buat_kaki(garis=110)
        hasil = live_status.evaluate_leg(leg, buat_live(), None, CFG)
        self.assertEqual(hasil["status"], "KALAH")
        self.assertAlmostEqual(hasil["margin_points"], -122.0, places=6)

    def test_leg_total_berjalan_pas_garis_belum_kalah(self):
        # Total berjalan 116 = garis 116: belum pasti kalah (sisa laga
        # tanpa poin = push) -> tetap dari proyeksi (232, margin -116).
        leg = buat_kaki(garis=116)
        hasil = live_status.evaluate_leg(leg, buat_live(), None, CFG)
        self.assertEqual(hasil["status"], "TERANCAM")

    def test_leg_blend_vs_live_only(self):
        # Laga total 118, garis 237,5. Dengan median 226 (blend):
        # projected 233,5, margin 4,0 -> WASPADA. Tanpa median:
        # projected 236,0, margin 1,5 -> TERANCAM.
        game = buat_live(home_score=60, away_score=58)
        leg = buat_kaki(garis=237.5)
        dengan_median = live_status.evaluate_leg(leg, game, 226, CFG)
        self.assertEqual(dengan_median["status"], "WASPADA")
        self.assertAlmostEqual(dengan_median["margin_points"], 4.0, places=6)
        tanpa_median = live_status.evaluate_leg(leg, game, None, CFG)
        self.assertEqual(tanpa_median["status"], "TERANCAM")
        self.assertAlmostEqual(tanpa_median["margin_points"], 1.5, places=6)

    def test_leg_menang_kalah_push(self):
        # Laga selesai, total akhir 220 (112+108). Garis 237,5 -> MENANG
        # (margin 17,5); garis 219,5 -> KALAH (margin -0,5); garis 220
        # -> PUSH (margin 0,0; total sama dengan garis adalah seri).
        game = buat_live(
            status="selesai",
            period=4,
            seconds_remaining=0,
            home_score=112,
            away_score=108,
        )
        menang = live_status.evaluate_leg(buat_kaki(garis=237.5), game, None, CFG)
        self.assertEqual(menang["status"], "MENANG")
        self.assertAlmostEqual(menang["margin_points"], 17.5, places=6)
        self.assertEqual(menang["projected_total"], 220)
        kalah = live_status.evaluate_leg(buat_kaki(garis=219.5), game, None, CFG)
        self.assertEqual(kalah["status"], "KALAH")
        self.assertAlmostEqual(kalah["margin_points"], -0.5, places=6)
        push = live_status.evaluate_leg(buat_kaki(garis=220), game, None, CFG)
        self.assertEqual(push["status"], "PUSH")
        self.assertAlmostEqual(push["margin_points"], 0.0, places=6)
        self.assertTrue(any("push" in n for n in push["notes"]))

    def test_leg_belum_mulai(self):
        game = buat_live(
            status="belum_mulai",
            period=None,
            clock_display=None,
            seconds_remaining=None,
            home_score=None,
            away_score=None,
        )
        hasil = live_status.evaluate_leg(buat_kaki(), game, 226, CFG)
        self.assertEqual(hasil["status"], "BELUM_MULAI")
        self.assertIsNone(hasil["projected_total"])
        self.assertIsNone(hasil["margin_points"])
        self.assertEqual(hasil["line"], 237.5)

    def test_leg_garis_tak_terurai(self):
        # Selection tanpa "Under <angka>" -> DATA_INCOMPLETE, line None.
        leg = buat_kaki(selection="Lakers ML")
        hasil = live_status.evaluate_leg(leg, buat_live(), None, CFG)
        self.assertEqual(hasil["status"], "DATA_INCOMPLETE")
        self.assertIsNone(hasil["line"])
        self.assertTrue(any("tidak bisa diurai" in n for n in hasil["notes"]))

    def test_leg_pasar_bukan_total_under(self):
        # Market moneyline (meski selection-nya "Under ...") -> DATA_INCOMPLETE.
        leg = buat_kaki(market="moneyline")
        hasil = live_status.evaluate_leg(leg, buat_live(), None, CFG)
        self.assertEqual(hasil["status"], "DATA_INCOMPLETE")
        self.assertIsNone(hasil["line"])

    def test_leg_laga_tak_ditemukan(self):
        # live_game None: garis tetap terurai (237,5), status DATA_INCOMPLETE.
        hasil = live_status.evaluate_leg(buat_kaki(), None, None, CFG)
        self.assertEqual(hasil["status"], "DATA_INCOMPLETE")
        self.assertEqual(hasil["line"], 237.5)
        self.assertTrue(any("tidak ditemukan" in n for n in hasil["notes"]))

    def test_leg_tanpa_proyeksi(self):
        # Laga baru 10 detik: proyeksi tidak ada -> DATA_INCOMPLETE.
        game = buat_live(
            period=1,
            clock_display="11:50",
            seconds_remaining=2870,
            home_score=2,
            away_score=0,
        )
        hasil = live_status.evaluate_leg(buat_kaki(), game, 226, CFG)
        self.assertEqual(hasil["status"], "DATA_INCOMPLETE")
        self.assertIsNone(hasil["projected_total"])

    def test_leg_ot_risk_diteruskan(self):
        # OT, selisih 2, sisa 1,5 menit: ot_risk True diteruskan ke kaki;
        # status tetap dari margin (212 vs garis 237,5 -> AMAN).
        game = buat_live(
            period=5,
            clock_display="1:30",
            seconds_remaining=0,
            home_score=104,
            away_score=102,
        )
        hasil = live_status.evaluate_leg(buat_kaki(garis=237.5), game, 226, CFG)
        self.assertTrue(hasil["ot_risk"])
        self.assertEqual(hasil["status"], "AMAN")


class TestEvaluateTicket(unittest.TestCase):
    def test_tiket_kaki_terburuk(self):
        # 4 kaki: AMAN (garis 238), WASPADA (234), TERANCAM (230),
        # MENANG (selesai 220 vs 237,5) -> status tiket TERANCAM.
        games = {
            "DET@ATL_2026-11-22": buat_live("DET@ATL_2026-11-22"),
            "BOS@GSW_2026-11-22": buat_live("BOS@GSW_2026-11-22"),
            "IND@NYK_2026-11-22": buat_live("IND@NYK_2026-11-22"),
            "DAL@UTA_2026-11-22": buat_live(
                "DAL@UTA_2026-11-22",
                status="selesai",
                period=4,
                seconds_remaining=0,
                home_score=112,
                away_score=108,
            ),
        }
        tiket = buat_tiket(
            [
                buat_kaki("DET@ATL_2026-11-22", garis=238, leg_id="leg-1"),
                buat_kaki("BOS@GSW_2026-11-22", garis=234, leg_id="leg-2"),
                buat_kaki("IND@NYK_2026-11-22", garis=230, leg_id="leg-3"),
                buat_kaki("DAL@UTA_2026-11-22", garis=237.5, leg_id="leg-4"),
            ]
        )
        hasil = live_status.evaluate_ticket(tiket, games, None, CFG)
        self.assertEqual(hasil["status"], "TERANCAM")
        self.assertEqual(hasil["ticket_id"], "tkt-2026-11-22-utm")
        self.assertEqual(hasil["type"], "Utama")
        self.assertEqual(
            [k["status"] for k in hasil["legs"]],
            ["AMAN", "WASPADA", "TERANCAM", "MENANG"],
        )
        # Catatan campuran: 1 kaki selesai, 3 belum.
        self.assertTrue(any("sudah selesai" in n for n in hasil["notes"]))

    def test_tiket_semua_menang(self):
        games = {
            "DET@ATL_2026-11-22": buat_live(
                "DET@ATL_2026-11-22",
                status="selesai",
                period=4,
                seconds_remaining=0,
                home_score=112,
                away_score=108,
            ),
            "BOS@GSW_2026-11-22": buat_live(
                "BOS@GSW_2026-11-22",
                status="selesai",
                period=4,
                seconds_remaining=0,
                home_score=110,
                away_score=105,
            ),
        }
        tiket = buat_tiket(
            [
                buat_kaki("DET@ATL_2026-11-22", garis=237.5, leg_id="leg-1"),
                buat_kaki("BOS@GSW_2026-11-22", garis=237.5, leg_id="leg-2"),
            ]
        )
        hasil = live_status.evaluate_ticket(tiket, games, None, CFG)
        self.assertEqual(hasil["status"], "MENANG")

    def test_tiket_satu_kalah(self):
        # Satu kaki KALAH (selesai 220 vs garis 219,5) + satu AMAN ->
        # tiket KALAH (satu kaki kalah = tiket parlay kalah).
        games = {
            "DET@ATL_2026-11-22": buat_live(
                "DET@ATL_2026-11-22",
                status="selesai",
                period=4,
                seconds_remaining=0,
                home_score=112,
                away_score=108,
            ),
            "BOS@GSW_2026-11-22": buat_live("BOS@GSW_2026-11-22"),
        }
        tiket = buat_tiket(
            [
                buat_kaki("DET@ATL_2026-11-22", garis=219.5, leg_id="leg-1"),
                buat_kaki("BOS@GSW_2026-11-22", garis=238, leg_id="leg-2"),
            ]
        )
        hasil = live_status.evaluate_ticket(tiket, games, None, CFG)
        self.assertEqual(hasil["status"], "KALAH")

    def test_tiket_campuran_selesai_belum(self):
        # Satu kaki MENANG + satu AMAN -> tiket AMAN (kaki selesai tidak
        # menarik status ke bawah) + catatan campuran.
        games = {
            "DET@ATL_2026-11-22": buat_live(
                "DET@ATL_2026-11-22",
                status="selesai",
                period=4,
                seconds_remaining=0,
                home_score=112,
                away_score=108,
            ),
            "BOS@GSW_2026-11-22": buat_live("BOS@GSW_2026-11-22"),
        }
        tiket = buat_tiket(
            [
                buat_kaki("DET@ATL_2026-11-22", garis=237.5, leg_id="leg-1"),
                buat_kaki("BOS@GSW_2026-11-22", garis=238, leg_id="leg-2"),
            ]
        )
        hasil = live_status.evaluate_ticket(tiket, games, None, CFG)
        self.assertEqual(hasil["status"], "AMAN")
        self.assertTrue(any("sudah selesai" in n for n in hasil["notes"]))

    def test_tiket_semua_belum_mulai(self):
        games = {
            "DET@ATL_2026-11-22": buat_live(
                "DET@ATL_2026-11-22",
                status="belum_mulai",
                period=None,
                clock_display=None,
                seconds_remaining=None,
                home_score=None,
                away_score=None,
            ),
        }
        tiket = buat_tiket([buat_kaki("DET@ATL_2026-11-22")])
        hasil = live_status.evaluate_ticket(tiket, games, None, CFG)
        self.assertEqual(hasil["status"], "BELUM_MULAI")

    def test_tiket_laga_tak_ditemukan(self):
        # Kaki kedua laganya tidak ada di data live -> kaki DATA_INCOMPLETE
        # dan tiket DATA_INCOMPLETE (kaki lainnya AMAN).
        games = {"DET@ATL_2026-11-22": buat_live("DET@ATL_2026-11-22")}
        tiket = buat_tiket(
            [
                buat_kaki("DET@ATL_2026-11-22", garis=238, leg_id="leg-1"),
                buat_kaki("BOS@GSW_2026-11-22", garis=238, leg_id="leg-2"),
            ]
        )
        hasil = live_status.evaluate_ticket(tiket, games, None, CFG)
        self.assertEqual(hasil["status"], "DATA_INCOMPLETE")
        self.assertEqual(hasil["legs"][1]["status"], "DATA_INCOMPLETE")
        self.assertTrue(any("BOS@GSW" in n for n in hasil["notes"]))

    def test_tiket_push_semua(self):
        # Kedua kaki total akhir == garis -> tiket PUSH.
        games = {
            "DET@ATL_2026-11-22": buat_live(
                "DET@ATL_2026-11-22",
                status="selesai",
                period=4,
                seconds_remaining=0,
                home_score=112,
                away_score=108,
            ),
            "BOS@GSW_2026-11-22": buat_live(
                "BOS@GSW_2026-11-22",
                status="selesai",
                period=4,
                seconds_remaining=0,
                home_score=120,
                away_score=112,
            ),
        }
        tiket = buat_tiket(
            [
                buat_kaki("DET@ATL_2026-11-22", garis=220, leg_id="leg-1"),
                buat_kaki("BOS@GSW_2026-11-22", garis=232, leg_id="leg-2"),
            ]
        )
        hasil = live_status.evaluate_ticket(tiket, games, None, CFG)
        self.assertEqual(hasil["status"], "PUSH")

    def test_tiket_push_campur_menang(self):
        # Satu PUSH + satu MENANG -> tiket MENANG + catatan push.
        games = {
            "DET@ATL_2026-11-22": buat_live(
                "DET@ATL_2026-11-22",
                status="selesai",
                period=4,
                seconds_remaining=0,
                home_score=112,
                away_score=108,
            ),
            "BOS@GSW_2026-11-22": buat_live(
                "BOS@GSW_2026-11-22",
                status="selesai",
                period=4,
                seconds_remaining=0,
                home_score=110,
                away_score=105,
            ),
        }
        tiket = buat_tiket(
            [
                buat_kaki("DET@ATL_2026-11-22", garis=220, leg_id="leg-1"),
                buat_kaki("BOS@GSW_2026-11-22", garis=237.5, leg_id="leg-2"),
            ]
        )
        hasil = live_status.evaluate_ticket(tiket, games, None, CFG)
        self.assertEqual(hasil["status"], "MENANG")
        self.assertTrue(any("push" in n for n in hasil["notes"]))

    def test_tiket_median_pregame(self):
        # Median pra-laga dipakai per laga: dengan median 226, projected
        # 233,5 (margin 4,0 -> WASPADA); tanpa median, projected 236,0
        # (margin 1,5 -> TERANCAM).
        games = {
            "DET@ATL_2026-11-22": buat_live(
                "DET@ATL_2026-11-22",
                home_score=60,
                away_score=58,
            ),
        }
        tiket = buat_tiket([buat_kaki("DET@ATL_2026-11-22", garis=237.5)])
        dengan = live_status.evaluate_ticket(
            tiket,
            games,
            {"DET@ATL_2026-11-22": 226},
            CFG,
        )
        self.assertEqual(dengan["status"], "WASPADA")
        tanpa = live_status.evaluate_ticket(tiket, games, None, CFG)
        self.assertEqual(tanpa["status"], "TERANCAM")


class TestRenderLiveStatus(unittest.TestCase):
    def test_render_terancam(self):
        # Total berjalan 119 (61+58), 24 menit berjalan/sisa: projected
        # = 119 + (119/24)*24 = 238,0 vs garis 237,5 -> TERANCAM.
        games = {
            "DET@ATL_2026-11-22": buat_live(
                "DET@ATL_2026-11-22",
                home_score=61,
                away_score=58,
            ),
        }
        tiket = buat_tiket([buat_kaki("DET@ATL_2026-11-22", garis=237.5)])
        hasil = live_status.evaluate_ticket(tiket, games, None, CFG)
        teks = live_status.render_live_status(hasil)
        self.assertIn("Tiket Utamamu terancam — 1 kaki terancam.", teks)
        self.assertIn(
            "Kaki DET@ATL terancam — proyeksi total 238 vs garis 237,5",
            teks,
        )

    def test_render_aman(self):
        games = {
            mid: buat_live(mid)
            for mid in (
                "DET@ATL_2026-11-22",
                "BOS@GSW_2026-11-22",
                "IND@NYK_2026-11-22",
                "DAL@UTA_2026-11-22",
            )
        }
        tiket = buat_tiket(
            [
                buat_kaki(mid, garis=238, leg_id=f"leg-{i}")
                for i, mid in enumerate(games, start=1)
            ]
        )
        hasil = live_status.evaluate_ticket(tiket, games, None, CFG)
        teks = live_status.render_live_status(hasil)
        self.assertIn("Tiket Utamamu masih hijau — 4 kaki aman.", teks)
        self.assertIn(
            "Kaki DET@ATL aman — proyeksi total 232 vs garis 238",
            teks,
        )

    def test_render_menang(self):
        games = {
            "DET@ATL_2026-11-22": buat_live(
                "DET@ATL_2026-11-22",
                status="selesai",
                period=4,
                seconds_remaining=0,
                home_score=112,
                away_score=108,
            ),
        }
        tiket = buat_tiket([buat_kaki("DET@ATL_2026-11-22", garis=237.5)])
        hasil = live_status.evaluate_ticket(tiket, games, None, CFG)
        teks = live_status.render_live_status(hasil)
        self.assertIn("Tiket Utamamu menang — semua kaki menang.", teks)
        self.assertIn(
            "Kaki DET@ATL menang — total akhir 220 di bawah garis 237,5",
            teks,
        )

    def test_render_dengan_anomali(self):
        # anomalies_by_match: string dan dict (kunci 'pesan') sama-sama
        # dirender; None berarti diabaikan (lihat test_render_aman).
        games = {"DET@ATL_2026-11-22": buat_live("DET@ATL_2026-11-22")}
        tiket = buat_tiket([buat_kaki("DET@ATL_2026-11-22", garis=238)])
        hasil = live_status.evaluate_ticket(tiket, games, None, CFG)
        anomali = {
            "DET@ATL_2026-11-22": [
                "Tembakan tiga angka Hawks jauh di atas rata-rata.",
                {"pesan": "Laju skor kuarter 3 melonjak."},
            ],
        }
        teks = live_status.render_live_status(hasil, anomali)
        self.assertIn("Tembakan tiga angka Hawks jauh di atas rata-rata.", teks)
        self.assertIn("Laju skor kuarter 3 melonjak.", teks)

    def test_render_data_incomplete(self):
        games = {}
        tiket = buat_tiket([buat_kaki("DET@ATL_2026-11-22", garis=237.5)])
        hasil = live_status.evaluate_ticket(tiket, games, None, CFG)
        teks = live_status.render_live_status(hasil)
        self.assertIn("Tiket Utamamu belum bisa dinilai", teks)
        self.assertIn("tidak ditemukan di data live", teks)


class TestAmbangDariConfig(unittest.TestCase):
    def test_ambang_dari_config(self):
        # Ambang dibaca dari cfg, bukan angka keras di kode: dengan
        # status_margin_aman_points = 10,0, margin 6,0 jadi WASPADA.
        cfg_kustom = {
            "live": {
                "status_margin_aman_points": 10.0,
                "status_margin_waspada_points": 2.0,
                "ot_risk_margin_points": 3,
                "ot_risk_minutes_remaining": 2.0,
                "anomaly_min_minutes_elapsed": 12,
                "anomaly_fg3_rate_multiplier": 1.5,
                "anomaly_ft_rate_multiplier": 1.5,
                "anomaly_scoring_rate_multiplier": 1.15,
            },
        }
        hasil = live_status.evaluate_leg(
            buat_kaki(garis=238),
            buat_live(),
            None,
            cfg_kustom,
        )
        self.assertEqual(hasil["status"], "WASPADA")

    def test_config_hilang_melempar(self):
        # cfg tanpa section live -> ConfigError (gagal keras, bukan
        # default diam-diam) saat menilai kaki laga yang berjalan.
        with self.assertRaises(config.ConfigError):
            live_status.evaluate_leg(buat_kaki(), buat_live(), None, {})


if __name__ == "__main__":
    unittest.main()
