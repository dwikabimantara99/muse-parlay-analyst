"""Tes ledger SQLite: hitung untung/rugi, catat tiket, tolak yang invalid."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ledger import store

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_example(name: str) -> dict:
    return json.loads((REPO_ROOT / "examples" / name).read_text(encoding="utf-8"))


class TestComputeProfitLoss(unittest.TestCase):
    def test_win(self):
        # 60 x 2,35 - 60 = 81
        self.assertAlmostEqual(store.compute_profit_loss(60, 2.35, "WIN"), 81.0)

    def test_loss(self):
        self.assertAlmostEqual(store.compute_profit_loss(40, 4.5, "LOSS"), -40.0)

    def test_push_dan_void_nol(self):
        self.assertEqual(store.compute_profit_loss(50, 3.0, "PUSH"), 0.0)
        self.assertEqual(store.compute_profit_loss(50, 3.0, "VOID"), 0.0)

    def test_pending_none(self):
        self.assertIsNone(store.compute_profit_loss(50, 3.0, "PENDING"))

    def test_hasil_tidak_dikenal(self):
        with self.assertRaises(store.LedgerError):
            store.compute_profit_loss(50, 3.0, "DRAW")


class TestLogTicket(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = store.connect(Path(self.tmp.name) / "tes.db")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_log_dua_tiket_contoh(self):
        store.log_ticket(self.conn, load_example("ticket_asuransi.json"))
        store.log_ticket(self.conn, load_example("ticket_utama.json"))
        tickets = store.list_tickets(self.conn)
        self.assertEqual(len(tickets), 2)

    def test_untung_rugi_dihitung_kode(self):
        store.log_ticket(self.conn, load_example("ticket_asuransi.json"))
        saved = store.get_ticket(self.conn, "tkt-contoh-01-ins")
        self.assertAlmostEqual(saved["profit_loss"], 81.0)
        store.log_ticket(self.conn, load_example("ticket_utama.json"))
        saved = store.get_ticket(self.conn, "tkt-contoh-02-utm")
        self.assertAlmostEqual(saved["profit_loss"], -40.0)

    def test_jup_provider_kaki_tersimpan(self):
        ticket = load_example("ticket_asuransi.json")
        ticket["legs"][0]["jup_provider"] = "polymarket"
        ticket["legs"][1]["jup_provider"] = "kalshi"
        store.log_ticket(self.conn, ticket)
        saved = store.get_ticket(self.conn, ticket["ticket_id"])
        self.assertEqual(saved["legs"][0]["jup_provider"], "polymarket")
        self.assertEqual(saved["legs"][1]["jup_provider"], "kalshi")

    def test_kaki_tersimpan(self):
        store.log_ticket(self.conn, load_example("ticket_asuransi.json"))
        saved = store.get_ticket(self.conn, "tkt-contoh-01-ins")
        self.assertEqual(len(saved["legs"]), 2)
        self.assertEqual(saved["legs"][0]["selection"], "Lakers ML")
        self.assertAlmostEqual(saved["legs"][0]["p_final"], 0.766)
        self.assertEqual(saved["legs"][0]["critic_light"], "GREEN")

    def test_duplikat_ditolak(self):
        store.log_ticket(self.conn, load_example("ticket_asuransi.json"))
        with self.assertRaises(store.LedgerError):
            store.log_ticket(self.conn, load_example("ticket_asuransi.json"))
        # Isi ledger tidak berubah.
        self.assertEqual(len(store.list_tickets(self.conn)), 1)

    def test_tiket_tidak_valid_ditolak(self):
        bad = load_example("ticket_asuransi.json")
        del bad["stake"]
        with self.assertRaises(store.LedgerError):
            store.log_ticket(self.conn, bad)
        self.assertEqual(len(store.list_tickets(self.conn)), 0)

    def test_settle_pending(self):
        ticket = load_example("ticket_asuransi.json")
        ticket["ticket_id"] = "tkt-pending-01"
        ticket["result"] = "PENDING"
        for leg in ticket["legs"]:
            leg["result"] = None
        store.log_ticket(self.conn, ticket)
        saved = store.get_ticket(self.conn, "tkt-pending-01")
        self.assertIsNone(saved["profit_loss"])
        profit = store.settle_ticket(
            self.conn,
            "tkt-pending-01",
            "WIN",
            {"leg-contoh-01": "WIN", "leg-contoh-02": "WIN"},
        )
        self.assertAlmostEqual(profit, 81.0)
        saved = store.get_ticket(self.conn, "tkt-pending-01")
        self.assertEqual(saved["result"], "WIN")
        self.assertAlmostEqual(saved["profit_loss"], 81.0)
        self.assertEqual(saved["legs"][0]["result"], "WIN")

    def test_settle_tiket_tidak_ada(self):
        with self.assertRaises(store.LedgerError):
            store.settle_ticket(self.conn, "tidak-ada", "WIN")


if __name__ == "__main__":
    unittest.main()
