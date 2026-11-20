"""Tes ujung-ke-ujung cli.py lewat subprocess (seperti dipakai user)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "cli.py"


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO_ROOT),
    )


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "cli.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_log_dua_tiket_lalu_recap(self):
        for name in ("ticket_asuransi.json", "ticket_utama.json"):
            res = run_cli(
                "log", "--file", str(REPO_ROOT / "examples" / name),
                "--db", self.db,
            )
            self.assertEqual(res.returncode, 0, res.stderr)
        res = run_cli("recap", "--db", self.db)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Untung/rugi: $+41.00", res.stdout)
        self.assertIn("ROI: +41.00%", res.stdout)

    def test_recap_json_bisa_di_parse(self):
        run_cli("log", "--file",
                str(REPO_ROOT / "examples" / "ticket_asuransi.json"),
                "--db", self.db)
        res = run_cli("recap", "--db", self.db, "--json")
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertAlmostEqual(data["settled"]["profit"], 81.0)

    def test_log_file_tidak_valid_gagal(self):
        bad = Path(self.tmp.name) / "bad.json"
        bad.write_text('{"ticket_id": "x"}', encoding="utf-8")
        res = run_cli("log", "--file", str(bad), "--db", self.db)
        self.assertEqual(res.returncode, 1)
        self.assertIn("error", res.stderr.lower())

    def test_log_duplikat_gagal(self):
        ticket = str(REPO_ROOT / "examples" / "ticket_asuransi.json")
        self.assertEqual(
            run_cli("log", "--file", ticket, "--db", self.db).returncode, 0
        )
        res = run_cli("log", "--file", ticket, "--db", self.db)
        self.assertEqual(res.returncode, 1)

    def test_analyze_belum_tersedia(self):
        res = run_cli("analyze", "--input",
                      str(REPO_ROOT / "examples" / "slate_contoh.json"))
        self.assertEqual(res.returncode, 2)
        self.assertIn("Tahap 2", res.stderr)

    def test_recheck_belum_tersedia(self):
        res = run_cli("recheck", "--ticket", "tkt-contoh-01-ins")
        self.assertEqual(res.returncode, 2)
        self.assertIn("Tahap 5", res.stderr)

    def test_settle_lewat_cli(self):
        ticket = json.loads(
            (REPO_ROOT / "examples" / "ticket_asuransi.json").read_text(
                encoding="utf-8"
            )
        )
        ticket["ticket_id"] = "tkt-cli-pending"
        ticket["result"] = "PENDING"
        for leg in ticket["legs"]:
            leg["result"] = None
        pending_file = Path(self.tmp.name) / "pending.json"
        pending_file.write_text(json.dumps(ticket), encoding="utf-8")
        self.assertEqual(
            run_cli("log", "--file", str(pending_file), "--db", self.db)
            .returncode,
            0,
        )
        res = run_cli("log", "--settle", "tkt-cli-pending", "--result", "WIN",
                      "--db", self.db)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("$+81.00", res.stdout)


if __name__ == "__main__":
    unittest.main()
