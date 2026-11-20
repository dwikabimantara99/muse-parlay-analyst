"""Tes skema JSON: contoh valid lolos, contoh rusak ditolak."""

import json
import sys
import unittest
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestSchemas(unittest.TestCase):
    def test_slate_contoh_valid(self):
        schema = load_json(REPO_ROOT / "schemas" / "slate.schema.json")
        slate = load_json(REPO_ROOT / "examples" / "slate_contoh.json")
        jsonschema.validate(instance=slate, schema=schema)

    def test_slate_tanpa_laga_ditolak(self):
        schema = load_json(REPO_ROOT / "schemas" / "slate.schema.json")
        slate = load_json(REPO_ROOT / "examples" / "slate_contoh.json")
        slate["matches"] = []
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(instance=slate, schema=schema)

    def test_tiket_contoh_valid(self):
        schema = load_json(REPO_ROOT / "schemas" / "ticket.schema.json")
        for name in ("ticket_asuransi.json", "ticket_utama.json"):
            ticket = load_json(REPO_ROOT / "examples" / name)
            jsonschema.validate(instance=ticket, schema=schema)

    def test_tiket_tanpa_modal_ditolak(self):
        schema = load_json(REPO_ROOT / "schemas" / "ticket.schema.json")
        ticket = load_json(REPO_ROOT / "examples" / "ticket_asuransi.json")
        del ticket["stake"]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(instance=ticket, schema=schema)

    def test_tiket_dengan_profit_loss_ditolak(self):
        # Untung/rugi TIDAK BOLEH diinput — selalu dihitung kode (aturan 1).
        schema = load_json(REPO_ROOT / "schemas" / "ticket.schema.json")
        ticket = load_json(REPO_ROOT / "examples" / "ticket_asuransi.json")
        ticket["profit_loss"] = 999.0
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(instance=ticket, schema=schema)

    def test_tiket_cashout_valid(self):
        schema = load_json(REPO_ROOT / "schemas" / "ticket.schema.json")
        ticket = load_json(REPO_ROOT / "examples" / "ticket_asuransi.json")
        ticket["result"] = "CASHOUT"
        ticket["cashout_amount"] = 75.0
        jsonschema.validate(instance=ticket, schema=schema)

    def test_tiket_pengali_satu_ditolak(self):
        schema = load_json(REPO_ROOT / "schemas" / "ticket.schema.json")
        ticket = load_json(REPO_ROOT / "examples" / "ticket_asuransi.json")
        ticket["multiplier"] = 1.0
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(instance=ticket, schema=schema)

    def test_leg_contoh_valid(self):
        leg_schema = load_json(REPO_ROOT / "schemas" / "leg.schema.json")
        ticket = load_json(REPO_ROOT / "examples" / "ticket_asuransi.json")
        for leg in ticket["legs"]:
            # result & price_close_cents hanya ada di tiket, bukan di leg murni.
            leg_only = {
                k: v for k, v in leg.items() if k not in ("result", "price_close_cents")
            }
            jsonschema.validate(instance=leg_only, schema=leg_schema)

    def test_leg_dengan_jup_provider_valid(self):
        leg_schema = load_json(REPO_ROOT / "schemas" / "leg.schema.json")
        ticket = load_json(REPO_ROOT / "examples" / "ticket_asuransi.json")
        leg = dict(ticket["legs"][0])
        leg.pop("result", None)
        leg.pop("price_close_cents", None)
        leg["jup_provider"] = "polymarket"
        jsonschema.validate(instance=leg, schema=leg_schema)

    def test_leg_dengan_flags_valid(self):
        leg_schema = load_json(REPO_ROOT / "schemas" / "leg.schema.json")
        ticket = load_json(REPO_ROOT / "examples" / "ticket_asuransi.json")
        leg = dict(ticket["legs"][0])
        leg.pop("result", None)
        leg.pop("price_close_cents", None)
        leg["flags"] = ["MODEL_ONLY"]
        jsonschema.validate(instance=leg, schema=leg_schema)

    def test_match_data_sumber_tanpa_tier_ditolak(self):
        schema = load_json(REPO_ROOT / "schemas" / "match_data.schema.json")
        doc = {
            "match_id": "nba-2026-11-20-lal-bos",
            "sport": "nba",
            "fetched_at": "2026-11-20T18:00:00+07:00",
            "status": "OK",
            "sources": [
                {
                    "data_kind": "nba_schedule_stats",
                    "source": "nba.com",
                    "fetched_at": "2026-11-20T18:00:00+07:00",
                }
            ],
        }
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(instance=doc, schema=schema)

    def test_match_data_dengan_labels_valid(self):
        # Ekstensi 2b (koordinator): kunci opsional "labels" untuk
        # TANPA_XG / MODEL_ONLY — aditif, dokumen lama tetap valid.
        schema = load_json(REPO_ROOT / "schemas" / "match_data.schema.json")
        doc = {
            "match_id": "epl-2026-11-21-che-lee",
            "sport": "football",
            "fetched_at": "2026-11-20T18:00:00+07:00",
            "status": "HOLD",
            "labels": ["TANPA_XG"],
            "sources": [],
        }
        jsonschema.validate(instance=doc, schema=schema)

    def test_match_data_minimal_valid(self):
        schema = load_json(REPO_ROOT / "schemas" / "match_data.schema.json")
        doc = {
            "match_id": "nba-2026-11-20-lal-bos",
            "sport": "nba",
            "fetched_at": "2026-11-20T18:00:00+07:00",
            "status": "DATA_INCOMPLETE",
            "status_reason": "cedera gagal diambil",
            "missing": ["nba_injuries"],
            "sources": [],
        }
        jsonschema.validate(instance=doc, schema=schema)

    def test_simulasi_minimal_valid(self):
        schema = load_json(REPO_ROOT / "schemas" / "simulation.schema.json")
        doc = {
            "match_id": "nba-2026-11-20-lal-bos",
            "sport": "nba",
            "iterations": 100000,
            "generated_at": "2026-11-20T18:05:00+07:00",
            "engine": {"name": "nba_sim", "version": "0.1"},
            "markets": {"moneyline_home": 0.78},
        }
        jsonschema.validate(instance=doc, schema=schema)


if __name__ == "__main__":
    unittest.main()
