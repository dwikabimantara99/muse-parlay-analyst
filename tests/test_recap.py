"""Tes rekap: angka gabungan 2 tiket contoh harus tepat."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ledger import recap, store

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_example(name: str) -> dict:
    return json.loads((REPO_ROOT / "examples" / name).read_text(encoding="utf-8"))


class TestRecap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = store.connect(Path(self.tmp.name) / "tes.db")
        store.log_ticket(self.conn, load_example("ticket_asuransi.json"))
        store.log_ticket(self.conn, load_example("ticket_utama.json"))

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_angka_gabungan(self):
        data = recap.compute_recap(self.conn)
        settled = data["settled"]
        # Modal 60+40=100; kembali 141+0=141; untung 81-40=+41; ROI +41%.
        self.assertEqual(settled["count"], 2)
        self.assertAlmostEqual(settled["staked"], 100.0)
        self.assertAlmostEqual(settled["returned"], 141.0)
        self.assertAlmostEqual(settled["profit"], 41.0)
        self.assertAlmostEqual(settled["roi_pct"], 41.0)

    def test_per_jenis_tiket(self):
        data = recap.compute_recap(self.conn)
        ins = data["by_type"]["Asuransi"]
        self.assertEqual(ins["count"], 1)
        self.assertAlmostEqual(ins["profit"], 81.0)
        self.assertAlmostEqual(ins["roi_pct"], 135.0)
        main = data["by_type"]["Utama"]
        self.assertEqual(main["count"], 1)
        self.assertAlmostEqual(main["profit"], -40.0)
        self.assertAlmostEqual(main["roi_pct"], -100.0)

    def test_kaki(self):
        data = recap.compute_recap(self.conn)
        self.assertEqual(data["legs"]["total"], 5)
        self.assertEqual(data["legs"]["settled"], 5)
        self.assertEqual(data["legs"]["won"], 4)
        self.assertAlmostEqual(data["legs"]["win_rate_pct"], 80.0)

    def test_format_teks_memuat_angka_benar(self):
        text = recap.format_recap(recap.compute_recap(self.conn))
        self.assertIn("Untung/rugi: $+41.00", text)
        self.assertIn("ROI: +41.00%", text)
        self.assertIn("Asuransi: 1 tiket", text)
        self.assertIn("Utama: 1 tiket", text)

    def test_pending_tidak_masuk_untung_rugi(self):
        ticket = load_example("ticket_asuransi.json")
        ticket["ticket_id"] = "tkt-pending-99"
        ticket["result"] = "PENDING"
        for leg in ticket["legs"]:
            leg["result"] = None
        store.log_ticket(self.conn, ticket)
        data = recap.compute_recap(self.conn)
        self.assertEqual(data["settled"]["count"], 2)
        self.assertAlmostEqual(data["settled"]["profit"], 41.0)
        self.assertEqual(data["pending"]["count"], 1)
        self.assertAlmostEqual(data["pending"]["staked"], 60.0)

    def test_rekap_kosong_tidak_error(self):
        tmp2 = tempfile.TemporaryDirectory()
        conn2 = store.connect(Path(tmp2.name) / "kosong.db")
        data = recap.compute_recap(conn2)
        self.assertEqual(data["settled"]["count"], 0)
        self.assertEqual(data["settled"]["roi_pct"], 0.0)
        conn2.close()
        tmp2.cleanup()


if __name__ == "__main__":
    unittest.main()
