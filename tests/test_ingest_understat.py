"""Tes ingest.understat — gate status + parser (tanpa network)."""

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import understat

NOW = datetime(2026, 11, 20, 16, 0, tzinfo=UTC)

SYNTHETIC_HTML = """<html><head><script>
var teamsData = JSON.parse('{"1": {"id": 1, "title": "Arsenal", "history": [{"xG": 1.8}]}, "2": {"id": 2, "title": "Chelsea", "history": []}}');
var datesData = JSON.parse('[]');
</script></head></html>"""


class FakeClient:
    """Client palsu: satu respons tetap."""

    def __init__(self, status=200, body=""):
        self.status = status
        self.body = body
        self.calls = []

    def get(self, url, use_cache=True):
        self.calls.append(url)
        return {"status": self.status, "body": self.body, "error": None}


class TestReadStatus(unittest.TestCase):
    def test_file_valid(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(
                {"checked_at": "2026-11-20T16:01:05+00:00", "status": "up"},
                handle,
            )
            path = handle.name
        record = understat.read_status(path)
        self.assertEqual(record["status"], "up")
        Path(path).unlink()

    def test_file_hilang(self):
        record = understat.read_status("/tmp/tidak-ada-understat-status.json")
        self.assertEqual(record["status"], "unknown")
        self.assertIsNone(record["checked_at"])

    def test_file_rusak(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write("{bukan json")
            path = handle.name
        record = understat.read_status(path)
        self.assertEqual(record["status"], "unknown")
        Path(path).unlink()

    def test_tanpa_kunci_status(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"checked_at": "2026-11-20T16:01:05+00:00"}, handle)
            path = handle.name
        record = understat.read_status(path)
        self.assertEqual(record["status"], "unknown")
        Path(path).unlink()


class TestIsAvailable(unittest.TestCase):
    def _check(self, record):
        with mock.patch.object(understat, "read_status", return_value=record):
            return understat.is_available(now=NOW)

    def test_up_dan_segar(self):
        ok, reason = self._check(
            {
                "status": "up",
                "checked_at": (NOW - timedelta(hours=1)).isoformat(),
            }
        )
        self.assertTrue(ok, reason)

    def test_maintenance(self):
        ok, reason = self._check(
            {"status": "maintenance", "checked_at": NOW.isoformat()}
        )
        self.assertFalse(ok)
        self.assertIn("maintenance", reason)

    def test_up_tapi_basi(self):
        ok, reason = self._check(
            {
                "status": "up",
                "checked_at": (NOW - timedelta(hours=25)).isoformat(),
            }
        )
        self.assertFalse(ok)
        self.assertIn("basi", reason)

    def test_batas_24_jam_pas(self):
        ok, _ = self._check(
            {
                "status": "up",
                "checked_at": (NOW - timedelta(hours=24)).isoformat(),
            }
        )
        self.assertTrue(ok)

    def test_unknown(self):
        ok, _ = self._check({"status": "unknown", "checked_at": None})
        self.assertFalse(ok)

    def test_checked_at_tidak_bisa_dibaca(self):
        ok, reason = self._check({"status": "up", "checked_at": "kemarin"})
        self.assertFalse(ok)
        self.assertIn("tidak bisa dibaca", reason)

    def test_checked_at_di_masa_depan(self):
        ok, _ = self._check(
            {
                "status": "up",
                "checked_at": (NOW + timedelta(hours=1)).isoformat(),
            }
        )
        self.assertFalse(ok)


class TestParseTeamsData(unittest.TestCase):
    def test_html_sintetis(self):
        data = understat.parse_teams_data(SYNTHETIC_HTML)
        self.assertEqual(data["1"]["title"], "Arsenal")
        self.assertEqual(data["1"]["history"][0]["xG"], 1.8)
        self.assertEqual(data["2"]["title"], "Chelsea")

    def test_escape_js(self):
        # Backslash + apostrof di dalam string JSON.parse('...').
        escaped = "L" + chr(92) + "'Equipe"
        html = (
            "<script>var teamsData = JSON.parse('"
            '{"1": {"title": "' + escaped + '"}}'
            "');</script>"
        )
        data = understat.parse_teams_data(html)
        self.assertEqual(data["1"]["title"], "L'Equipe")

    def test_tanpa_penanda(self):
        with self.assertRaises(ValueError):
            understat.parse_teams_data("<html>kosong</html>")

    def test_json_rusak(self):
        with self.assertRaises(ValueError):
            understat.parse_teams_data(
                "<script>var teamsData = JSON.parse('{rusak');</script>"
            )

    def test_bukan_dict(self):
        with self.assertRaises(ValueError):
            understat.parse_teams_data(
                "<script>var teamsData = JSON.parse('[1, 2]');</script>"
            )


class TestFetchXg(unittest.TestCase):
    def test_gate_tertutup_tanpa_network(self):
        client = FakeClient(body=SYNTHETIC_HTML)
        with mock.patch.object(
            understat,
            "is_available",
            return_value=(False, "status 'maintenance' (bukan 'up')"),
        ):
            result = understat.fetch_xg(client=client)
        self.assertFalse(result.ok)
        self.assertTrue(result.error.startswith("understat_not_available:"))
        self.assertEqual(client.calls, [])

    def test_gate_terbuka_parse_ok(self):
        client = FakeClient(body=SYNTHETIC_HTML)
        with mock.patch.object(understat, "is_available", return_value=(True, "up")):
            result = understat.fetch_xg(client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.source, "Understat")
        self.assertEqual(result.tier, 2)
        self.assertEqual(result.data["1"]["title"], "Arsenal")
        self.assertIn("understat.com/league/EPL/2025", client.calls[0])

    def test_halaman_maintenance_ditolak(self):
        client = FakeClient(body="<html>We will come back soon</html>")
        with mock.patch.object(understat, "is_available", return_value=(True, "up")):
            result = understat.fetch_xg(client=client)
        self.assertFalse(result.ok)
        self.assertIn("maintenance", result.error)

    def test_http_gagal(self):
        client = FakeClient(status=500, body="")
        with mock.patch.object(understat, "is_available", return_value=(True, "up")):
            result = understat.fetch_xg(client=client)
        self.assertFalse(result.ok)
        self.assertIn("http_500", result.error)


if __name__ == "__main__":
    unittest.main()
