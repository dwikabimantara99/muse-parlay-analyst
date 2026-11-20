"""Tes kerangka Tahap 2+: modul belum dibangun HARUS melempar
NotImplementedError — tidak boleh pura-pura mengembalikan data.
"""

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# (modul, fungsi) yang wajib masih berupa stub di Tahap 1.
STUBS = [
    ("ingest.espn", "fetch"),
    ("ingest.nba_injury_pdf", "fetch"),
    ("ingest.bbref", "fetch"),
    ("ingest.understat", "fetch"),
    ("ingest.sofascore", "fetch"),
    ("ingest.fotmob", "fetch"),
    ("ingest.jupiter", "fetch"),
    ("ingest.polymarket", "fetch"),
    ("ingest.kalshi", "fetch"),
    ("ingest.odds_api", "fetch"),
    ("validate.checks", "validate_match_data"),
    ("engine.nba_sim", "simulate"),
    ("engine.football_sim", "simulate"),
    ("engine.markets", "evaluate_markets"),
    ("engine.devig", "blend"),
    ("optimizer.tickets", "optimize"),
    ("critic.critic", "critique"),
    ("critic.validate_numbers", "validate_numbers"),
    ("report.telegram", "format_report"),
]


class TestStubs(unittest.TestCase):
    def test_semua_stub_melempar_not_implemented(self):
        for module_name, func_name in STUBS:
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                func = getattr(module, func_name)
                with self.assertRaises(NotImplementedError):
                    func()


if __name__ == "__main__":
    unittest.main()
