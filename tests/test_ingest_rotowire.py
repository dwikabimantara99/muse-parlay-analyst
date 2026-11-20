"""Tes ingest/rotowire.py — TANPA network (mock client + fixture).

Fixture dibentuk dari respons asli endpoint tabel Rotowire yang diambil
live 2026-11-20 (5 baris; 2 baris dipakai di sini).
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import rotowire


class FakeClient:
    """Client palsu: get() mengembalikan respons yang sudah disiapkan."""

    def __init__(self, responses: dict[str, dict]) -> None:
        self.responses = responses
        self.urls_requested: list[str] = []

    def get(self, url: str, use_cache: bool = True) -> dict:
        """Kembalikan respons untuk URL (default: 404)."""
        self.urls_requested.append(url)
        return self.responses.get(url, {"status": 404, "body": "", "error": None})


def _resp(status: int, body: object) -> dict:
    return {
        "status": status,
        "body": body if isinstance(body, str) else json.dumps(body),
        "error": None,
    }


TABLES_FIXTURE = [
    {
        "ID": "5249",
        "URL": "/basketball/player/precious-achiuwa-5249",
        "firstname": "Precious",
        "lastname": "Achiuwa",
        "player": "Precious Achiuwa",
        "team": "SAC",
        "position": "F",
        "injury": "Lower Leg",
        "status": "Doubtful",
        "rDate": "<i>Subscribers Only</i>",
    },
    {
        "ID": "3445",
        "URL": "/basketball/player/steven-adams-3445",
        "firstname": "Steven",
        "lastname": "Adams",
        "player": "Steven Adams",
        "team": "HOU",
        "position": "C",
        "injury": "Quadriceps",
        "status": "Questionable",
        "rDate": "<i>Subscribers Only</i>",
    },
]


class TestParseInjuryRows(unittest.TestCase):
    def test_parse_dua_baris(self):
        injuries = rotowire.parse_injury_rows(TABLES_FIXTURE)
        self.assertEqual(len(injuries), 2)
        self.assertEqual(injuries[0]["player"], "Precious Achiuwa")
        self.assertEqual(injuries[0]["team"], "SAC")
        self.assertEqual(injuries[0]["status"], "Doubtful")
        # rDate "Subscribers Only" TIDAK ditambahkan ke detail.
        self.assertEqual(injuries[0]["detail"], "Lower Leg")
        self.assertEqual(injuries[1]["player"], "Steven Adams")
        self.assertEqual(injuries[1]["detail"], "Quadriceps")

    def test_rdate_asli_ditambahkan(self):
        rows = [dict(TABLES_FIXTURE[0], rDate="Nov 25")]
        injuries = rotowire.parse_injury_rows(rows)
        self.assertEqual(injuries[0]["detail"], "Lower Leg; est. return Nov 25")

    def test_nama_dari_firstname_lastname(self):
        rows = [dict(TABLES_FIXTURE[0])]
        del rows[0]["player"]
        injuries = rotowire.parse_injury_rows(rows)
        self.assertEqual(injuries[0]["player"], "Precious Achiuwa")

    def test_payload_bukan_list_format_changed(self):
        with self.assertRaises(ValueError) as ctx:
            rotowire.parse_injury_rows({"error": "The TEAM parameter is required."})
        self.assertEqual(str(ctx.exception), "rotowire_format_changed")

    def test_baris_tanpa_kolom_wajib_format_changed(self):
        with self.assertRaises(ValueError) as ctx:
            rotowire.parse_injury_rows([{"player": "X", "team": "SAC"}])
        self.assertEqual(str(ctx.exception), "rotowire_format_changed")

    def test_baris_bukan_dict_format_changed(self):
        with self.assertRaises(ValueError) as ctx:
            rotowire.parse_injury_rows(["bukan dict"])
        self.assertEqual(str(ctx.exception), "rotowire_format_changed")

    def test_list_kosong_ok(self):
        self.assertEqual(rotowire.parse_injury_rows([]), [])


class TestFetchInjuries(unittest.TestCase):
    def test_fetch_ok(self):
        client = FakeClient({rotowire.TABLES_URL: _resp(200, TABLES_FIXTURE)})
        result = rotowire.fetch_injuries(client=client)
        self.assertTrue(result.ok)
        self.assertEqual(result.source, "Rotowire")
        self.assertEqual(result.tier, 2)
        self.assertEqual(len(result.data), 2)
        self.assertEqual(result.extra["n_rows"], 2)
        self.assertIn("paywall", result.extra["paywall_note"].lower())
        self.assertEqual(client.urls_requested, [rotowire.TABLES_URL])

    def test_fetch_http_gagal(self):
        result = rotowire.fetch_injuries(client=FakeClient({}))
        self.assertFalse(result.ok)
        self.assertIn("http_404", result.error or "")

    def test_fetch_format_berubah(self):
        client = FakeClient(
            {
                rotowire.TABLES_URL: _resp(
                    200, {"error": "The TEAM parameter is required."}
                )
            }
        )
        result = rotowire.fetch_injuries(client=client)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "rotowire_format_changed")

    def test_fetch_bukan_json(self):
        client = FakeClient(
            {rotowire.TABLES_URL: _resp(200, "<html>bukan json</html>")}
        )
        result = rotowire.fetch_injuries(client=client)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "rotowire_format_changed")


if __name__ == "__main__":
    unittest.main()
