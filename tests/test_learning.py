"""Tes engine/learning.py: muat ledger + ringkasan Brier/EV per kaki.

Angka harapan dihitung tangan (lihat komentar di tiap tes) — bukan dari
output modul. DB tes dibuat dengan ledger.store.connect (skema asli)
lalu diisi lewat INSERT langsung supaya kasus tepi (result NULL, VOID,
PUSH, nilai tak dikenal) bisa dikontrol persis.
"""

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import learning
from ledger import store

KUNCI_OUTCOME = {
    "leg_id",
    "ticket_id",
    "sport",
    "market",
    "selection",
    "p_model",
    "p_market",
    "p_final",
    "price_buy_cents",
    "price_close_cents",
    "ev_pct",
    "result",
    "settled",
    "sumber",
}


def _tiket(conn, ticket_id, result="PENDING"):
    conn.execute(
        "INSERT INTO tickets (id, placed_at, type, stake, multiplier, result)"
        " VALUES (?, '2026-11-22T00:00:00Z', 'Utama', 10.0, 2.0, ?)",
        (ticket_id, result),
    )


def _kaki(
    conn,
    ticket_id,
    leg_id,
    sport,
    market,
    p_model,
    p_market,
    p_final,
    harga_beli,
    ev_persen,
    result,
):
    """Sisipkan satu kaki. ev_persen dalam PERSEN (satuan ledger)."""
    conn.execute(
        "INSERT INTO legs (ticket_id, leg_id, match_id, sport, market,"
        " selection, p_model, p_market, p_final, price_buy_cents,"
        " price_close_cents, edge, ev_pct, status, result)"
        " VALUES (?, ?, 'm1', ?, ?, 'sel', ?, ?, ?, ?, NULL, 0.0, ?,"
        " 'OK', ?)",
        (
            ticket_id,
            leg_id,
            sport,
            market,
            p_model,
            p_market,
            p_final,
            harga_beli,
            ev_persen,
            result,
        ),
    )


def _db_fixture(path):
    """DB dengan 4 kaki settled + 1 pending + 1 VOID + 1 PUSH.

    Kaki settled (ev_pct ledger dalam persen):
    1. nba/total_under, p 0.8/0.7/0.75, harga 80, ev +5.0, WIN
    2. nba/total_under, p 0.6/None/0.6, harga 50, ev -2.0, LOSS
    3. football/double_chance, p 0.9/0.85/0.88, harga 90, ev +10.0, WIN
    4. football/double_chance, p 0.4/0.5/0.45, harga 40, ev None, LOSS
    """
    conn = store.connect(path)
    _tiket(conn, "tkt-1")
    _tiket(conn, "tkt-2")
    _tiket(conn, "tkt-3")
    _kaki(conn, "tkt-1", "leg-1", "nba", "total_under", 0.8, 0.7, 0.75, 80, 5.0, "WIN")
    _kaki(
        conn, "tkt-1", "leg-2", "nba", "total_under", 0.6, None, 0.6, 50, -2.0, "LOSS"
    )
    _kaki(
        conn,
        "tkt-2",
        "leg-3",
        "football",
        "double_chance",
        0.9,
        0.85,
        0.88,
        90,
        10.0,
        "WIN",
    )
    _kaki(
        conn,
        "tkt-2",
        "leg-4",
        "football",
        "double_chance",
        0.4,
        0.5,
        0.45,
        40,
        None,
        "LOSS",
    )
    _kaki(
        conn,
        "tkt-2",
        "leg-5",
        "football",
        "double_chance",
        0.7,
        0.7,
        0.7,
        70,
        3.0,
        None,
    )
    _kaki(conn, "tkt-3", "leg-6", "nba", "moneyline", 0.6, 0.6, 0.6, 60, 1.0, "VOID")
    _kaki(conn, "tkt-3", "leg-7", "nba", "moneyline", 0.6, 0.6, 0.6, 60, 1.0, "PUSH")
    conn.commit()
    return conn


def _outcome(
    leg_id="leg-x",
    sport="NBA",
    market="total_under",
    p_model=0.8,
    p_market=0.7,
    p_final=0.75,
    harga=80.0,
    ev_pct=0.05,
    result=True,
    settled=True,
):
    """Satu OUTCOME RECORD sesuai kontrak (ev_pct dalam FRAKSI)."""
    return {
        "leg_id": leg_id,
        "ticket_id": "tkt-x",
        "sport": sport,
        "market": market,
        "selection": "sel",
        "p_model": p_model,
        "p_market": p_market,
        "p_final": p_final,
        "price_buy_cents": harga,
        "price_close_cents": None,
        "ev_pct": ev_pct,
        "result": result,
        "settled": settled,
        "sumber": "ledger",
    }


class TestMuatHasilLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_db_tidak_ada(self):
        path = self.dir / "tidak-ada.db"
        hasil = learning.muat_hasil_ledger(path)
        self.assertFalse(hasil["ada_data"])
        self.assertEqual(hasil["outcomes"], [])
        self.assertEqual(hasil["n_settled"], 0)
        self.assertIn("belum ada", hasil["pesan"])
        # Membaca tidak boleh membuat file.
        self.assertFalse(path.exists())

    def test_db_tanpa_kaki(self):
        path = self.dir / "kosong.db"
        conn = store.connect(path)
        conn.close()
        hasil = learning.muat_hasil_ledger(path)
        self.assertFalse(hasil["ada_data"])
        self.assertEqual(hasil["n_kaki_total"], 0)

    def test_db_tanpa_tabel_legs(self):
        path = self.dir / "bukan-ledger.db"
        sqlite3.connect(path).close()
        hasil = learning.muat_hasil_ledger(path)
        self.assertFalse(hasil["ada_data"])
        self.assertEqual(hasil["outcomes"], [])

    def test_hanya_pending(self):
        path = self.dir / "pending.db"
        conn = store.connect(path)
        _tiket(conn, "tkt-p")
        _kaki(
            conn, "tkt-p", "leg-p1", "nba", "total_under", 0.8, 0.7, 0.75, 80, 5.0, None
        )
        _kaki(
            conn, "tkt-p", "leg-p2", "nba", "total_under", 0.6, 0.6, 0.6, 60, 1.0, None
        )
        conn.commit()
        conn.close()
        hasil = learning.muat_hasil_ledger(path)
        self.assertFalse(hasil["ada_data"])
        self.assertEqual(hasil["n_pending"], 2)
        self.assertEqual(hasil["n_settled"], 0)
        self.assertEqual(hasil["outcomes"], [])

    def test_void_push_dikeluarkan_dan_pending_dihitung(self):
        path = self.dir / "fixture.db"
        conn = _db_fixture(path)
        conn.close()
        hasil = learning.muat_hasil_ledger(path)
        self.assertTrue(hasil["ada_data"])
        self.assertEqual(hasil["n_settled"], 4)
        self.assertEqual(hasil["n_pending"], 1)
        self.assertEqual(hasil["n_dikeluarkan"], 2)
        self.assertEqual(hasil["n_kaki_total"], 7)
        self.assertEqual(hasil["n_tiket"], 3)
        # outcomes: 4 settled + 1 pending; VOID/PUSH tidak ada.
        self.assertEqual(len(hasil["outcomes"]), 5)
        leg_ids = {o["leg_id"] for o in hasil["outcomes"]}
        self.assertNotIn("leg-6", leg_ids)
        self.assertNotIn("leg-7", leg_ids)

    def test_kontrak_outcome_record(self):
        path = self.dir / "fixture.db"
        conn = _db_fixture(path)
        conn.close()
        hasil = learning.muat_hasil_ledger(path)
        by_id = {o["leg_id"]: o for o in hasil["outcomes"]}
        for o in hasil["outcomes"]:
            self.assertEqual(set(o.keys()), KUNCI_OUTCOME)
            self.assertEqual(o["sumber"], "ledger")
        # Sport dinormalisasi nba->NBA, football->soccer.
        self.assertEqual(by_id["leg-1"]["sport"], "NBA")
        self.assertEqual(by_id["leg-3"]["sport"], "soccer")
        # ev_pct persen ledger -> fraksi kontrak: 5.0% -> 0.05.
        self.assertAlmostEqual(by_id["leg-1"]["ev_pct"], 0.05)
        self.assertAlmostEqual(by_id["leg-2"]["ev_pct"], -0.02)
        self.assertIsNone(by_id["leg-4"]["ev_pct"])
        # result/settled: WIN->True, LOSS->False, pending->None/False.
        self.assertIs(by_id["leg-1"]["result"], True)
        self.assertIs(by_id["leg-1"]["settled"], True)
        self.assertIs(by_id["leg-2"]["result"], False)
        self.assertIs(by_id["leg-5"]["result"], None)
        self.assertIs(by_id["leg-5"]["settled"], False)
        # p_market None diteruskan sebagai None.
        self.assertIsNone(by_id["leg-2"]["p_market"])

    def test_tidak_menulis_file(self):
        path = self.dir / "fixture.db"
        conn = _db_fixture(path)
        conn.close()
        sebelum = path.read_bytes()
        learning.muat_hasil_ledger(path)
        learning.muat_hasil_ledger(path)
        self.assertEqual(path.read_bytes(), sebelum)

    def test_hasil_tidak_dikenal_dikeluarkan(self):
        path = self.dir / "aneh.db"
        conn = store.connect(path)
        _tiket(conn, "tkt-a")
        _kaki(
            conn,
            "tkt-a",
            "leg-ok",
            "nba",
            "total_under",
            0.8,
            0.7,
            0.75,
            80,
            5.0,
            "WIN",
        )
        # Nilai result di luar skema (hanya mungkin lewat edit manual):
        # kolom legs.result tidak punya CHECK, jadi INSERT langsung bisa.
        _kaki(
            conn,
            "tkt-a",
            "leg-aneh",
            "nba",
            "total_under",
            0.8,
            0.7,
            0.75,
            80,
            5.0,
            "DRAW",
        )
        conn.commit()
        conn.close()
        hasil = learning.muat_hasil_ledger(path)
        self.assertTrue(hasil["ada_data"])
        self.assertEqual(hasil["n_settled"], 1)
        self.assertEqual(hasil["n_hasil_tidak_dikenal"], 1)
        leg_ids = {o["leg_id"] for o in hasil["outcomes"]}
        self.assertNotIn("leg-aneh", leg_ids)


class TestRingkasan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "fixture.db"
        conn = _db_fixture(path)
        conn.close()
        self.outcomes = learning.muat_hasil_ledger(path)["outcomes"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_brier_hitung_tangan(self):
        r = learning.ringkasan_keseluruhan(self.outcomes)
        self.assertEqual(r["n"], 4)
        self.assertAlmostEqual(r["win_rate"], 0.5)
        # Brier model: (0.04+0.36+0.01+0.16)/4 = 0.57/4.
        self.assertAlmostEqual(r["brier_model"], 0.1425)
        self.assertEqual(r["n_brier_model"], 4)
        # Brier market (kaki 2 tanpa p_market):
        # (0.09+0.0225+0.25)/3 = 0.3625/3.
        self.assertAlmostEqual(r["brier_market"], 0.3625 / 3)
        self.assertEqual(r["n_brier_market"], 3)
        # Brier final: (0.0625+0.36+0.0144+0.2025)/4 = 0.6394/4.
        self.assertAlmostEqual(r["brier_final"], 0.15985)
        self.assertEqual(r["n_brier_final"], 4)
        # Klimatologi: prediksi konstan 0.5, hasil 2 menang 2 kalah -> 0.25.
        self.assertAlmostEqual(r["brier_climatology"], 0.25)

    def test_ev_hitung_tangan(self):
        r = learning.ringkasan_keseluruhan(self.outcomes)
        # EV prediksi (fraksi): (0.05 - 0.02 + 0.10)/3; kaki 4 tanpa ev.
        self.assertAlmostEqual(r["ev_prediksi_rata2"], 0.13 / 3)
        self.assertEqual(r["n_ev_prediksi"], 3)
        # EV terealisasi: WIN 80c -> 0.25; LOSS -> -1; WIN 90c -> 1/9;
        # LOSS -> -1. Rata-rata = (0.25 - 1 + 1/9 - 1)/4.
        self.assertAlmostEqual(
            r["ev_terealisasi_rata2"], (0.25 - 1.0 + 1.0 / 9.0 - 1.0) / 4.0
        )
        self.assertEqual(r["n_ev_terealisasi"], 4)

    def test_kaki_tanpa_p_market_tidak_masuk_brier_market(self):
        r = learning.ringkasan_keseluruhan(self.outcomes)
        self.assertEqual(r["n_brier_model"], 4)
        self.assertEqual(r["n_brier_market"], 3)
        self.assertIsNone(r["alasan_brier_model"])
        self.assertIsNone(r["alasan_brier_market"])

    def test_per_pasar(self):
        per = learning.ringkasan_per_pasar(self.outcomes)
        self.assertEqual(
            set(per.keys()), {("NBA", "total_under"), ("soccer", "double_chance")}
        )
        # Pasar moneyline hanya punya VOID/PUSH -> tidak muncul.
        nba = per[("NBA", "total_under")]
        self.assertEqual(nba["n"], 2)
        self.assertAlmostEqual(nba["win_rate"], 0.5)
        # Brier model NBA: (0.04+0.36)/2 = 0.2.
        self.assertAlmostEqual(nba["brier_model"], 0.2)
        # Brier market NBA: hanya kaki 1 -> (0.7-1)^2 = 0.09.
        self.assertAlmostEqual(nba["brier_market"], 0.09)
        self.assertEqual(nba["n_brier_market"], 1)
        # Brier final NBA: (0.0625+0.36)/2 = 0.21125.
        self.assertAlmostEqual(nba["brier_final"], 0.21125)
        self.assertAlmostEqual(nba["brier_climatology"], 0.25)
        # EV prediksi NBA: (0.05-0.02)/2 = 0.015.
        self.assertAlmostEqual(nba["ev_prediksi_rata2"], 0.015)
        # EV terealisasi NBA: (0.25-1)/2 = -0.375.
        self.assertAlmostEqual(nba["ev_terealisasi_rata2"], -0.375)

        bola = per[("soccer", "double_chance")]
        self.assertEqual(bola["n"], 2)
        # Brier model bola: (0.01+0.16)/2 = 0.085.
        self.assertAlmostEqual(bola["brier_model"], 0.085)
        # Brier market bola: (0.0225+0.25)/2 = 0.13625.
        self.assertAlmostEqual(bola["brier_market"], 0.13625)
        # Brier final bola: (0.0144+0.2025)/2 = 0.10845.
        self.assertAlmostEqual(bola["brier_final"], 0.10845)
        # EV prediksi bola: hanya kaki 3 (0.10); kaki 4 tanpa ev.
        self.assertAlmostEqual(bola["ev_prediksi_rata2"], 0.10)
        self.assertEqual(bola["n_ev_prediksi"], 1)
        # EV terealisasi bola: (1/9 - 1)/2.
        self.assertAlmostEqual(bola["ev_terealisasi_rata2"], (1.0 / 9.0 - 1.0) / 2.0)

    def test_ringkasan_kosong(self):
        r = learning.ringkasan_keseluruhan([])
        self.assertEqual(r["n"], 0)
        self.assertIsNone(r["win_rate"])
        self.assertIsNone(r["brier_model"])
        self.assertIsNone(r["brier_market"])
        self.assertIsNone(r["brier_final"])
        self.assertIsNone(r["brier_climatology"])
        self.assertIsNone(r["ev_prediksi_rata2"])
        self.assertIsNone(r["ev_terealisasi_rata2"])
        self.assertIn("belum ada", r["alasan_brier_model"])
        self.assertEqual(learning.ringkasan_per_pasar([]), {})

    def test_brier_tanpa_nilai_jadi_none_dengan_alasan(self):
        outcomes = [
            _outcome("leg-1", p_market=None, result=True),
            _outcome("leg-2", p_market=None, result=False),
        ]
        r = learning.ringkasan_keseluruhan(outcomes)
        self.assertIsNone(r["brier_market"])
        self.assertEqual(r["n_brier_market"], 0)
        self.assertIn("p_market", r["alasan_brier_market"])
        # Brier model tetap terhitung: ((0.8-1)^2+(0.8-0)^2)/2 = 0.34.
        self.assertAlmostEqual(r["brier_model"], 0.34)

    def test_ev_tanpa_harga_beli_jadi_none_dengan_alasan(self):
        outcomes = [
            _outcome("leg-1", harga=None, ev_pct=0.05, result=True),
            _outcome("leg-2", harga=None, ev_pct=-0.02, result=False),
        ]
        r = learning.ringkasan_keseluruhan(outcomes)
        self.assertIsNone(r["ev_terealisasi_rata2"])
        self.assertEqual(r["n_ev_terealisasi"], 0)
        self.assertIn("harga beli", r["alasan_ev_terealisasi"])
        # EV prediksi tetap terhitung: (0.05-0.02)/2 = 0.015.
        self.assertAlmostEqual(r["ev_prediksi_rata2"], 0.015)

    def test_pending_tidak_masuk_ringkasan(self):
        outcomes = [
            _outcome("leg-1", result=True, settled=True),
            _outcome("leg-2", result=None, settled=False),
            _outcome("leg-3", result=None, settled=False),
        ]
        r = learning.ringkasan_keseluruhan(outcomes)
        self.assertEqual(r["n"], 1)
        self.assertAlmostEqual(r["win_rate"], 1.0)
        # Semua menang -> klimatologi (prediksi konstan 1.0) sempurna.
        self.assertAlmostEqual(r["brier_climatology"], 0.0)
        per = learning.ringkasan_per_pasar(outcomes)
        self.assertEqual(per[("NBA", "total_under")]["n"], 1)


if __name__ == "__main__":
    unittest.main()
