"""Tes kerangka Tahap 2+: modul belum dibangun HARUS melempar
NotImplementedError — tidak boleh pura-pura mengembalikan data.
"""

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# (modul, fungsi) yang wajib masih berupa stub setelah Tahap 3 Langkah 1.
# engine.nba_sim.simulate + engine.markets.evaluate_markets dibangun di
# Langkah 1 (Otak NBA); engine.devig.blend dibangun worker paralel Tahap 3
# (dihapus dari daftar ini — tesnya ada di tests/test_devig.py milik
# worker itu). Sisanya tetap stub.
STUBS = [
    ("engine.football_sim", "simulate"),
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
