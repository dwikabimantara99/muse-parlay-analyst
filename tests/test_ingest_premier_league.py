"""Tes ingest.premier_league — tanpa network (client palsu)."""

import json
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import premier_league


def _fixture(home, away, kickoff, status="U", matchweek=12):
    """Satu fixture mentah PL (struktur dari cache probe 2a)."""
    return {
        "gameweek": {"gameweek": float(matchweek)},
        "kickoff": {
            "millis": float(kickoff.timestamp() * 1000),
            "label": kickoff.strftime("%a %d %b %Y, %H:%M"),
        },
        "teams": [
            {"team": {"name": home, "shortName": home}, "score": None},
            {"team": {"name": away, "shortName": away}, "score": None},
        ],
        "status": status,
    }


class FakeClient:
    """Client palsu: halaman fixtures kronologis (arsip 1992 s.d. 2027)."""

    def __init__(self, pages, status=200, body_override=None):
        self.pages = pages
        self.status = status
        self.body_override = body_override
        self.calls = []

    def get(self, url, use_cache=True):
        self.calls.append(url)
        import urllib.parse

        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        page = int(query.get("page", ["0"])[0])
        if self.body_override is not None:
            body = self.body_override
        else:
            content = self.pages[page] if page < len(self.pages) else []
            body = json.dumps(
                {
                    "pageInfo": {
                        "page": page,
                        "numPages": len(self.pages),
                        "pageSize": 2,
                        "numEntries": sum(len(p) for p in self.pages),
                    },
                    "content": content,
                }
            )
        return {"status": self.status, "body": body, "error": None}


def _pages():
    """6 halaman x 2 fixture: 1992, 2000, 2010, 2020, lalu Nov 2026, 2027."""
    d = lambda *a: datetime(*a, tzinfo=UTC)  # noqa: E731
    return [
        [
            _fixture("Arsenal", "Norwich City", d(1992, 8, 15, 15), "C", 1),
            _fixture("Chelsea", "Oldham Athletic", d(1992, 8, 16, 15), "C", 1),
        ],
        [
            _fixture("Arsenal", "Chelsea", d(2000, 1, 1, 15), "C", 20),
            _fixture("Arsenal", "Chelsea", d(2010, 1, 1, 15), "C", 20),
        ],
        [
            _fixture("Arsenal", "Chelsea", d(2020, 1, 1, 15), "C", 20),
            _fixture("Arsenal", "Chelsea", d(2026, 11, 19, 20), "U", 12),
        ],
        [
            _fixture("Arsenal", "Chelsea", d(2026, 11, 20, 20), "U", 12),
            _fixture("Arsenal", "Chelsea", d(2026, 11, 21, 17, 30), "U", 12),
        ],
        [
            _fixture("Arsenal", "Chelsea", d(2026, 11, 22, 16), "U", 12),
            _fixture("Arsenal", "Chelsea", d(2026, 12, 1, 20), "U", 13),
        ],
        [
            _fixture("Arsenal", "Chelsea", d(2027, 5, 1, 15), "U", 35),
            _fixture("Arsenal", "Chelsea", d(2027, 5, 15, 15), "U", 38),
        ],
    ]


class TestParseFixtures(unittest.TestCase):
    def test_field_terbaca(self):
        kickoff = datetime(2026, 11, 21, 17, 30, tzinfo=UTC)
        payload = {"content": [_fixture("Arsenal", "Chelsea", kickoff, "U", 12)]}
        parsed = premier_league.parse_fixtures(payload)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["home_team"], "Arsenal")
        self.assertEqual(parsed[0]["away_team"], "Chelsea")
        self.assertEqual(parsed[0]["kickoff"], "2026-11-21T17:30:00+00:00")
        self.assertEqual(parsed[0]["status"], "U")
        self.assertEqual(parsed[0]["matchweek"], 12)

    def test_fixture_rusak_dilewati(self):
        payload = {
            "content": [
                {"teams": [], "kickoff": {"millis": 1000}},
                {"teams": [{"team": {"name": "A"}}, {"team": {"name": "B"}}]},
                {"teams": [{"team": {"name": "A"}}], "kickoff": {"millis": 1}},
                "bukan dict",
            ]
        }
        self.assertEqual(premier_league.parse_fixtures(payload), [])

    def test_payload_bukan_dict(self):
        self.assertEqual(premier_league.parse_fixtures(None), [])
        self.assertEqual(premier_league.parse_fixtures([]), [])


class TestFetchFixtures(unittest.TestCase):
    def test_menemukan_fixture_di_jendela(self):
        client = FakeClient(_pages())
        now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
        result = premier_league.fetch_fixtures(
            client=client, now=now, window_days=7, page_size=2
        )
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.source, "Premier League (JSON resmi)")
        self.assertEqual(result.tier, 1)
        dates = sorted(f["kickoff"][:10] for f in result.data)
        self.assertEqual(
            dates, ["2026-11-19", "2026-11-20", "2026-11-21", "2026-11-22"]
        )
        # Fixture 1992 TIDAK PERNAH kembali (arsip tidak bocor ke slate).
        self.assertTrue(all("1992" not in f["kickoff"] for f in result.data))

    def test_tanpa_fixture_di_jendela(self):
        client = FakeClient(_pages())
        now = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
        result = premier_league.fetch_fixtures(
            client=client, now=now, window_days=7, page_size=2
        )
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data, [])

    def test_http_gagal(self):
        client = FakeClient(_pages(), status=500)
        result = premier_league.fetch_fixtures(
            client=client, now=datetime(2026, 11, 20, tzinfo=UTC), page_size=2
        )
        self.assertFalse(result.ok)
        self.assertIn("http_500", result.error)

    def test_body_bukan_json(self):
        client = FakeClient(_pages(), body_override="bukan json")
        result = premier_league.fetch_fixtures(
            client=client, now=datetime(2026, 11, 20, tzinfo=UTC), page_size=2
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "body_bukan_json")


def _fpl_payload():
    """Payload bootstrap-static mini: 2 tim, status a/i/d/s/u + aneh."""
    return {
        "teams": [
            {"id": 3, "name": "Arsenal"},
            {"id": 8, "name": "Chelsea"},
        ],
        "elements": [
            {
                "first_name": "Bukayo",
                "second_name": "Saka",
                "team": 3,
                "status": "i",
                "news": "Thigh injury - Expected back 20 Dec",
                "chance_of_playing_next_round": 0,
            },
            {
                "first_name": "Cole",
                "second_name": "Palmer",
                "team": 8,
                "status": "d",
                "news": "Groin injury",
                "chance_of_playing_next_round": 75,
            },
            {
                "first_name": "Moises",
                "second_name": "Caicedo",
                "team": 8,
                "status": "s",
                "news": "Suspended until 29 Nov",
                "chance_of_playing_next_round": None,
            },
            {
                "first_name": "Levi",
                "second_name": "Colwill",
                "team": 8,
                "status": "u",
                "news": "",
                "chance_of_playing_next_round": None,
            },
            # Pemain tersedia (a) bukan cedera -> dilewati.
            {
                "first_name": "Declan",
                "second_name": "Rice",
                "team": 3,
                "status": "a",
                "news": "",
                "chance_of_playing_next_round": 100,
            },
            # Kode status tidak dikenal -> diteruskan apa adanya.
            {
                "first_name": "Aneh",
                "second_name": "Sekali",
                "team": 3,
                "status": "x",
                "news": "Misterius",
                "chance_of_playing_next_round": None,
            },
            # Tanpa nama / tim tidak dikenal -> dilewati.
            {
                "first_name": "",
                "second_name": "",
                "team": 3,
                "status": "i",
                "news": "Tanpa nama",
                "chance_of_playing_next_round": None,
            },
            {
                "first_name": "Tim",
                "second_name": "Hilang",
                "team": 99,
                "status": "i",
                "news": "Tim tidak ada",
                "chance_of_playing_next_round": None,
            },
        ],
    }


class FplClient:
    """Client palsu FPL: mengembalikan satu body/status tetap."""

    def __init__(self, status=200, body=""):
        self.status = status
        self.body = body
        self.calls = []

    def get(self, url, use_cache=True):
        self.calls.append(url)
        return {"status": self.status, "body": self.body, "error": None}


class TestParseFplInjuries(unittest.TestCase):
    def test_status_dipetakan_dan_detail_dibuat(self):
        parsed = premier_league.parse_fpl_injuries(_fpl_payload())
        self.assertEqual(len(parsed), 5)
        by_player = {row["player"]: row for row in parsed}
        self.assertEqual(by_player["Bukayo Saka"]["status"], "Out")
        self.assertEqual(by_player["Bukayo Saka"]["team"], "Arsenal")
        self.assertIn("Thigh injury", by_player["Bukayo Saka"]["detail"])
        self.assertIn("0%", by_player["Bukayo Saka"]["detail"])
        self.assertEqual(by_player["Cole Palmer"]["status"], "Doubtful")
        self.assertIn("75%", by_player["Cole Palmer"]["detail"])
        self.assertEqual(by_player["Moises Caicedo"]["status"], "Suspended")
        self.assertEqual(by_player["Levi Colwill"]["status"], "Unavailable")
        self.assertIsNone(by_player["Levi Colwill"]["detail"])
        self.assertEqual(by_player["Aneh Sekali"]["status"], "x")
        self.assertNotIn("Declan Rice", by_player)

    def test_payload_bukan_dict(self):
        self.assertEqual(premier_league.parse_fpl_injuries(None), [])
        self.assertEqual(premier_league.parse_fpl_injuries([]), [])


class TestFetchInjuriesFpl(unittest.TestCase):
    def test_sukses(self):
        client = FplClient(body=json.dumps(_fpl_payload()))
        result = premier_league.fetch_injuries_fpl(client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.source, "Fantasy Premier League API")
        self.assertEqual(result.tier, 1)
        self.assertEqual(len(result.data), 5)
        self.assertEqual(client.calls, [premier_league.FPL_URL])

    def test_http_gagal(self):
        client = FplClient(status=500, body="")
        result = premier_league.fetch_injuries_fpl(client=client)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "http_500")

    def test_body_bukan_json(self):
        client = FplClient(body="bukan json")
        result = premier_league.fetch_injuries_fpl(client=client)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "body_bukan_json")

    def test_payload_tanpa_elements(self):
        client = FplClient(body=json.dumps({"teams": []}))
        result = premier_league.fetch_injuries_fpl(client=client)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "fpl_payload_kosong")


if __name__ == "__main__":
    unittest.main()
