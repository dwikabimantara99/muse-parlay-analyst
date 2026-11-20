"""Tes DECISIONS.md A: kaki VOID/PUSH (pengali hitung ulang) + CASHOUT."""

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ledger import store

REPO_ROOT = Path(__file__).resolve().parent.parent

OLD_TICKETS_SQL = """
CREATE TABLE tickets (
    id TEXT PRIMARY KEY,
    placed_at TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('Asuransi', 'Utama')),
    stake REAL NOT NULL CHECK (stake > 0),
    multiplier REAL NOT NULL CHECK (multiplier > 1),
    result TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (result IN ('WIN', 'LOSS', 'PUSH', 'VOID', 'PENDING')),
    profit_loss REAL,
    settled_at TEXT,
    slate_id TEXT,
    option_label TEXT,
    combo_spread_pct REAL,
    notes TEXT
);
CREATE TABLE legs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL REFERENCES tickets(id),
    leg_id TEXT,
    match_id TEXT,
    sport TEXT,
    market TEXT,
    selection TEXT,
    p_model REAL,
    p_market REAL,
    p_final REAL,
    price_buy_cents REAL,
    price_close_cents REAL,
    edge REAL,
    ev_pct REAL,
    status TEXT,
    filter_reason TEXT,
    anomaly_reason TEXT,
    critic_light TEXT,
    result TEXT
);
"""


def make_leg(leg_id, price, result=None):
    return {
        "leg_id": leg_id,
        "match_id": "nba-2026-11-20-lal-bos",
        "sport": "nba",
        "market": "moneyline",
        "selection": f"Leg {leg_id}",
        "p_model": 0.75,
        "p_market": 0.74,
        "p_final": 0.743,
        "jup_price_cents": price,
        "edge": 0.003,
        "ev_pct": 1.0,
        "status": "OK",
        "result": result,
    }


def make_ticket(ticket_id, legs, result="PENDING", stake=50.0, multiplier=3.0, **extra):
    ticket = {
        "ticket_id": ticket_id,
        "type": "Utama",
        "stake": stake,
        "multiplier": multiplier,
        "combo_spread_pct": 5.5,
        "legs": legs,
        "result": result,
    }
    ticket.update(extra)
    return ticket


class TestRecomputeMultiplier(unittest.TestCase):
    def test_dua_kaki(self):
        # (100/74) x (100/78) x 0.945 = 1.6372...
        self.assertAlmostEqual(
            store.recompute_multiplier([74, 78], 5.5), 1.63721, places=4
        )

    def test_satu_kaki(self):
        self.assertAlmostEqual(
            store.recompute_multiplier([66], 5.5),
            (100 / 66) * 0.945,
            places=6,
        )

    def test_kosong_melempar(self):
        with self.assertRaises(store.LedgerError):
            store.recompute_multiplier([], 5.5)

    def test_harga_tidak_valid_melempar(self):
        with self.assertRaises(store.LedgerError):
            store.recompute_multiplier([0], 5.5)
        with self.assertRaises(store.LedgerError):
            store.recompute_multiplier([None], 5.5)


class TestVoidPush(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = store.connect(Path(self.tmp.name) / "tes.db")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_log_kaki_void_pengali_dihitung_ulang(self):
        legs = [
            make_leg("leg-a", 74, "WIN"),
            make_leg("leg-b", 78, "VOID"),
            make_leg("leg-c", 66, "WIN"),
        ]
        store.log_ticket(self.conn, make_ticket("tkt-void-1", legs, result="WIN"))
        saved = store.get_ticket(self.conn, "tkt-void-1")
        # Sisa kaki 74 & 66: (100/74)x(100/66)x0.945 = 1.9349...
        self.assertAlmostEqual(saved["multiplier"], 1.93490, places=4)
        self.assertEqual(saved["multiplier_original"], 3.0)
        # Untung: 50 x 1.9349 - 50 = 46.74...
        self.assertAlmostEqual(saved["profit_loss"], 46.7448, places=2)

    def test_log_semua_kaki_void_jadi_void(self):
        legs = [make_leg("leg-a", 74, "VOID"), make_leg("leg-b", 78, "PUSH")]
        store.log_ticket(self.conn, make_ticket("tkt-void-all", legs, result="VOID"))
        saved = store.get_ticket(self.conn, "tkt-void-all")
        self.assertEqual(saved["result"], "VOID")
        self.assertEqual(saved["profit_loss"], 0.0)

    def test_log_semua_kaki_void_tapi_win_ditolak(self):
        legs = [make_leg("leg-a", 74, "VOID"), make_leg("leg-b", 78, "VOID")]
        with self.assertRaises(store.LedgerError):
            store.log_ticket(self.conn, make_ticket("tkt-void-bad", legs, result="WIN"))

    def test_settle_dengan_kaki_void(self):
        legs = [make_leg("leg-a", 74), make_leg("leg-b", 78), make_leg("leg-c", 66)]
        store.log_ticket(self.conn, make_ticket("tkt-settle-void", legs))
        profit = store.settle_ticket(
            self.conn,
            "tkt-settle-void",
            "WIN",
            {"leg-a": "WIN", "leg-b": "VOID", "leg-c": "WIN"},
        )
        self.assertAlmostEqual(profit, 46.7448, places=2)
        saved = store.get_ticket(self.conn, "tkt-settle-void")
        self.assertAlmostEqual(saved["multiplier"], 1.93490, places=4)
        self.assertEqual(saved["multiplier_original"], 3.0)

    def test_settle_semua_kaki_void_jadi_void(self):
        legs = [make_leg("leg-a", 74), make_leg("leg-b", 78)]
        store.log_ticket(self.conn, make_ticket("tkt-settle-allvoid", legs))
        profit = store.settle_ticket(
            self.conn,
            "tkt-settle-allvoid",
            "WIN",
            {"leg-a": "VOID", "leg-b": "PUSH"},
        )
        self.assertEqual(profit, 0.0)
        saved = store.get_ticket(self.conn, "tkt-settle-allvoid")
        self.assertEqual(saved["result"], "VOID")

    def test_settle_kaki_tidak_ada_ditolak(self):
        legs = [make_leg("leg-a", 74)]
        store.log_ticket(self.conn, make_ticket("tkt-bad-leg", legs))
        with self.assertRaises(store.LedgerError):
            store.settle_ticket(
                self.conn, "tkt-bad-leg", "WIN", {"leg-tidak-ada": "WIN"}
            )


class TestConsistency(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = store.connect(Path(self.tmp.name) / "tes.db")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_win_dengan_kaki_loss_ditolak(self):
        legs = [make_leg("leg-a", 74, "WIN"), make_leg("leg-b", 78, "LOSS")]
        with self.assertRaises(store.LedgerError):
            store.log_ticket(
                self.conn, make_ticket("tkt-inkonsisten", legs, result="WIN")
            )

    def test_loss_padahal_semua_kaki_win_ditolak(self):
        legs = [make_leg("leg-a", 74, "WIN"), make_leg("leg-b", 78, "WIN")]
        with self.assertRaises(store.LedgerError):
            store.log_ticket(
                self.conn, make_ticket("tkt-inkonsisten-2", legs, result="LOSS")
            )


class TestCashout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = store.connect(Path(self.tmp.name) / "tes.db")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_compute_cashout(self):
        self.assertAlmostEqual(
            store.compute_profit_loss(60, 2.35, "CASHOUT", 75.0), 15.0
        )
        self.assertAlmostEqual(
            store.compute_profit_loss(60, 2.35, "CASHOUT", 45.0), -15.0
        )

    def test_cashout_tanpa_jumlah_melempar(self):
        with self.assertRaises(store.LedgerError):
            store.compute_profit_loss(60, 2.35, "CASHOUT", None)

    def test_log_cashout(self):
        legs = [make_leg("leg-a", 74, "WIN")]
        store.log_ticket(
            self.conn,
            make_ticket(
                "tkt-cashout-1", legs, result="CASHOUT", stake=60.0, cashout_amount=75.0
            ),
        )
        saved = store.get_ticket(self.conn, "tkt-cashout-1")
        self.assertAlmostEqual(saved["profit_loss"], 15.0)
        self.assertEqual(saved["cashout_amount"], 75.0)

    def test_log_cashout_tanpa_jumlah_ditolak(self):
        legs = [make_leg("leg-a", 74, "WIN")]
        with self.assertRaises(store.LedgerError):
            store.log_ticket(
                self.conn,
                make_ticket("tkt-cashout-bad", legs, result="CASHOUT", stake=60.0),
            )

    def test_settle_cashout(self):
        legs = [make_leg("leg-a", 74)]
        store.log_ticket(self.conn, make_ticket("tkt-cashout-2", legs, stake=60.0))
        profit = store.settle_ticket(
            self.conn, "tkt-cashout-2", "CASHOUT", cashout_amount=45.0
        )
        self.assertAlmostEqual(profit, -15.0)
        saved = store.get_ticket(self.conn, "tkt-cashout-2")
        self.assertEqual(saved["result"], "CASHOUT")
        self.assertEqual(saved["cashout_amount"], 45.0)


class TestMigration(unittest.TestCase):
    def test_db_lama_dimigrasikan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "lama.db"
            raw = sqlite3.connect(db_path)
            raw.executescript(OLD_TICKETS_SQL)
            raw.execute(
                "INSERT INTO tickets (id, placed_at, type, stake, multiplier,"
                " result, profit_loss) VALUES ('tkt-lama', '2026-11-20',"
                " 'Utama', 40, 4.5, 'LOSS', -40.0)"
            )
            raw.commit()
            raw.close()
            # connect() harus memigrasikan tanpa menghilangkan data.
            conn = store.connect(db_path)
            saved = store.get_ticket(conn, "tkt-lama")
            self.assertEqual(saved["stake"], 40.0)
            self.assertAlmostEqual(saved["profit_loss"], -40.0)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(tickets)")}
            self.assertIn("cashout_amount", cols)
            self.assertIn("multiplier_original", cols)
            # CASHOUT sekarang bisa dipakai di DB lama.
            conn.execute(
                "INSERT INTO tickets (id, placed_at, type, stake, multiplier,"
                " result, profit_loss, cashout_amount) VALUES ('tkt-baru',"
                " '2026-11-20', 'Utama', 60, 2.35, 'CASHOUT', 15.0, 75.0)"
            )
            conn.commit()
            self.assertEqual(store.get_ticket(conn, "tkt-baru")["result"], "CASHOUT")
            conn.close()


if __name__ == "__main__":
    unittest.main()
