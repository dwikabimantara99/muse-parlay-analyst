"""Tes ingest/live_nba.py — TANPA network (mock client + fixture).

Fixture respons ESPN ASLI (diambil 2026-11-22 lewat fetcher modul ini):
- live_nba_scoreboard_2026-11-21.json: scoreboard 6 laga selesai 21 Nov 2026 (AS).
- live_nba_summary_401910023.json: summary MIL@PHI (401910023).
Fixture simulasi laga berjalan (tidak ada laga live saat tes ditulis):
- live_nba_scoreboard_live_sim.json: 1 laga berjalan Q3 + 1 belum mulai
  + 1 selesai, meniru struktur respons asli.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import live_nba
from ingest.common import RateLimiter

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Kunci kontrak LiveGame — PERSIS, jangan diubah (dipakai pekerja B/C).
LIVE_GAME_KEYS = {
    "match_id",
    "espn_game_id",
    "home_abbr",
    "away_abbr",
    "home_team",
    "away_team",
    "status",
    "period",
    "clock_display",
    "seconds_remaining",
    "home_score",
    "away_score",
    "line_scores",
    "stats",
    "fetched_at",
    "source",
}


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


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _event(
    event_id="401910099",
    state="in",
    period=3,
    clock="5:32",
    home_score="81",
    away_score="78",
    date="2026-11-21T19:30Z",
    home_lines=None,
    away_lines=None,
):
    return {
        "id": event_id,
        "date": date,
        "name": "Boston Celtics at New York Knicks",
        "status": {
            "clock": 332.0,
            "displayClock": clock,
            "period": period,
            "type": {"id": "2", "name": "STATUS_IN_PROGRESS", "state": state},
        },
        "competitions": [
            {
                "id": event_id,
                "competitors": [
                    {
                        "homeAway": "home",
                        "linescores": [
                            {"displayValue": str(v)} for v in (home_lines or [])
                        ],
                        "score": home_score,
                        "team": {
                            "abbreviation": "NY",
                            "displayName": "New York Knicks",
                        },
                    },
                    {
                        "homeAway": "away",
                        "linescores": [
                            {"displayValue": str(v)} for v in (away_lines or [])
                        ],
                        "score": away_score,
                        "team": {
                            "abbreviation": "BOS",
                            "displayName": "Boston Celtics",
                        },
                    },
                ],
            }
        ],
    }


class TestParseLiveScoreboardRealFixture(unittest.TestCase):
    def test_enam_laga_selesai_21_nov(self):
        data = _load_fixture("live_nba_scoreboard_2026-11-21.json")
        games = live_nba.parse_live_scoreboard(data, date_str="2026-11-21")
        self.assertEqual(len(games), 6)
        self.assertTrue(all(g["status"] == "selesai" for g in games))
        self.assertTrue(all(g["seconds_remaining"] == 0 for g in games))
        self.assertTrue(all(g["period"] == 4 for g in games))
        self.assertTrue(all(g["clock_display"] is None for g in games))
        self.assertTrue(all(g["stats"] is None for g in games))
        self.assertTrue(all(g["source"] == "espn_scoreboard" for g in games))

    def test_skor_akhir_mil_phi(self):
        data = _load_fixture("live_nba_scoreboard_2026-11-21.json")
        games = live_nba.parse_live_scoreboard(data, date_str="2026-11-21")
        by_id = {g["match_id"]: g for g in games}
        game = by_id["MIL@PHI_2026-11-21"]
        self.assertEqual(game["espn_game_id"], "401910023")
        self.assertEqual(game["home_abbr"], "PHI")
        self.assertEqual(game["away_abbr"], "MIL")
        self.assertEqual(game["home_team"], "Philadelphia 76ers")
        self.assertEqual(game["away_team"], "Milwaukee Bucks")
        self.assertEqual(game["home_score"], 132)
        self.assertEqual(game["away_score"], 129)
        self.assertEqual(game["line_scores"]["PHI"], [29, 31, 38, 34])
        self.assertEqual(game["line_scores"]["MIL"], [30, 29, 33, 37])
        # Jumlah kuarter cocok dengan skor akhir (cek konsistensi).
        self.assertEqual(sum(game["line_scores"]["PHI"]), 132)
        self.assertEqual(sum(game["line_scores"]["MIL"]), 129)

    def test_semua_laga_21_nov(self):
        data = _load_fixture("live_nba_scoreboard_2026-11-21.json")
        games = live_nba.parse_live_scoreboard(data, date_str="2026-11-21")
        scores = {g["match_id"]: (g["away_score"], g["home_score"]) for g in games}
        self.assertEqual(
            scores,
            {
                "MIL@PHI_2026-11-21": (129, 132),
                "POR@NYK_2026-11-21": (96, 97),
                "LAC@DAL_2026-11-21": (100, 110),
                "MEM@MIN_2026-11-21": (95, 104),
                "NOP@SAS_2026-11-21": (91, 114),
                "BOS@SAC_2026-11-21": (96, 97),
            },
        )

    def test_kunci_kontrak_persis(self):
        data = _load_fixture("live_nba_scoreboard_2026-11-21.json")
        games = live_nba.parse_live_scoreboard(data, date_str="2026-11-21")
        for game in games:
            self.assertEqual(set(game.keys()), LIVE_GAME_KEYS)


class TestParseLiveScoreboardSim(unittest.TestCase):
    def test_laga_berjalan_q3(self):
        data = _load_fixture("live_nba_scoreboard_live_sim.json")
        games = live_nba.parse_live_scoreboard(data, date_str="2026-11-21")
        game = next(g for g in games if g["match_id"] == "BOS@NYK_2026-11-21")
        self.assertEqual(game["status"], "berjalan")
        self.assertEqual(game["period"], 3)
        self.assertEqual(game["clock_display"], "5:32")
        # Q3 5:32 -> 1 kuarter penuh (720) + 332 detik = 1052.
        self.assertEqual(game["seconds_remaining"], 1052)
        self.assertEqual(game["home_score"], 81)
        self.assertEqual(game["away_score"], 78)
        self.assertEqual(game["line_scores"]["NYK"], [28, 30, 23])
        self.assertEqual(game["line_scores"]["BOS"], [25, 29, 24])

    def test_laga_belum_mulai(self):
        data = _load_fixture("live_nba_scoreboard_live_sim.json")
        games = live_nba.parse_live_scoreboard(data, date_str="2026-11-21")
        game = next(g for g in games if g["match_id"] == "LAL@GSW_2026-11-21")
        self.assertEqual(game["status"], "belum_mulai")
        self.assertIsNone(game["period"])
        self.assertIsNone(game["clock_display"])
        self.assertIsNone(game["seconds_remaining"])
        # ESPN mengirim skor "0" untuk laga belum mulai — parser None.
        self.assertIsNone(game["home_score"])
        self.assertIsNone(game["away_score"])
        self.assertEqual(game["line_scores"], {"GSW": [], "LAL": []})

    def test_laga_selesai_sim(self):
        data = _load_fixture("live_nba_scoreboard_live_sim.json")
        games = live_nba.parse_live_scoreboard(data, date_str="2026-11-21")
        game = next(g for g in games if g["match_id"] == "MIL@PHI_2026-11-21")
        self.assertEqual(game["status"], "selesai")
        self.assertEqual(game["seconds_remaining"], 0)
        self.assertEqual(game["home_score"], 132)

    def test_tiga_status_dalam_satu_tanggal(self):
        data = _load_fixture("live_nba_scoreboard_live_sim.json")
        games = live_nba.parse_live_scoreboard(data, date_str="2026-11-21")
        self.assertEqual(len(games), 3)
        self.assertEqual(
            {g["status"] for g in games}, {"berjalan", "belum_mulai", "selesai"}
        )


class TestMatchId(unittest.TestCase):
    def test_match_id_dari_date_str(self):
        games = live_nba.parse_live_scoreboard(
            {"events": [_event()]}, date_str="2026-11-21"
        )
        self.assertEqual(games[0]["match_id"], "BOS@NYK_2026-11-21")

    def test_match_id_fallback_tanggal_event_zona_timur(self):
        # Tanpa date_str: date UTC 2026-11-22T00:30Z = 21 Nov malam di AS.
        event = _event(date="2026-11-22T00:30Z")
        games = live_nba.parse_live_scoreboard({"events": [event]})
        self.assertEqual(games[0]["match_id"], "BOS@NYK_2026-11-21")

    def test_match_id_date_str_tidak_valid_fallback_event(self):
        event = _event(date="2026-11-21T19:30Z")
        games = live_nba.parse_live_scoreboard(
            {"events": [event]}, date_str="bukan-tanggal"
        )
        self.assertEqual(games[0]["match_id"], "BOS@NYK_2026-11-21")


class TestSecondsRemaining(unittest.TestCase):
    def test_q1_12_00(self):
        self.assertEqual(live_nba.compute_seconds_remaining(1, "12:00", "in"), 2880)

    def test_q4_2_00(self):
        self.assertEqual(live_nba.compute_seconds_remaining(4, "2:00", "in"), 120)

    def test_selesai_nol(self):
        self.assertEqual(live_nba.compute_seconds_remaining(4, "0.0", "post"), 0)

    def test_belum_mulai_none(self):
        self.assertIsNone(live_nba.compute_seconds_remaining(None, "0.0", "pre"))

    def test_ot_nol(self):
        self.assertEqual(live_nba.compute_seconds_remaining(5, "2:30", "in"), 0)

    def test_q3_5_32(self):
        self.assertEqual(live_nba.compute_seconds_remaining(3, "5:32", "in"), 1052)

    def test_jam_detik_polos(self):
        # displayClock detik polos ("45.2") di akhir kuarter.
        self.assertEqual(live_nba.compute_seconds_remaining(4, "45.2", "in"), 45)

    def test_jam_tidak_dikenal_none(self):
        self.assertIsNone(live_nba.compute_seconds_remaining(2, "??", "in"))
        self.assertIsNone(live_nba.compute_seconds_remaining(2, None, "in"))
        self.assertIsNone(live_nba.compute_seconds_remaining(None, "5:00", "in"))

    def test_parser_memakai_helper(self):
        games = live_nba.parse_live_scoreboard(
            {"events": [_event(state="in", period=1, clock="12:00")]},
            date_str="2026-11-21",
        )
        self.assertEqual(games[0]["seconds_remaining"], 2880)
        games = live_nba.parse_live_scoreboard(
            {"events": [_event(state="in", period=5, clock="2:30")]},
            date_str="2026-11-21",
        )
        self.assertEqual(games[0]["seconds_remaining"], 0)
        self.assertEqual(games[0]["period"], 5)


class TestParseRobustness(unittest.TestCase):
    def test_format_berubah_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            live_nba.parse_live_scoreboard({})
        self.assertEqual(str(ctx.exception), "espn_format_changed")
        with self.assertRaises(ValueError):
            live_nba.parse_live_scoreboard({"events": "bukan-list"})
        with self.assertRaises(ValueError):
            live_nba.parse_live_scoreboard(None)

    def test_event_rusak_dilewati(self):
        good = _event()
        broken_no_id = _event(event_id="")
        broken_no_teams = {"id": "999", "date": "2026-11-21T19:30Z"}
        broken_state = _event(event_id="401910101", state="misterius")
        games = live_nba.parse_live_scoreboard(
            {
                "events": [broken_no_id, broken_no_teams, broken_state, good],
            },
            date_str="2026-11-21",
        )
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]["match_id"], "BOS@NYK_2026-11-21")

    def test_fallback_camelcase_line_scores(self):
        # Bila ESPN mengubah casing jadi "lineScores"/"value", parser
        # tetap membaca lewat fallback.
        event = _event(home_lines=[28, 30, 23], away_lines=[25, 29, 24])
        for competitor in event["competitions"][0]["competitors"]:
            lines = competitor.pop("linescores")
            competitor["lineScores"] = [
                {"value": entry["displayValue"]} for entry in lines
            ]
        games = live_nba.parse_live_scoreboard(
            {"events": [event]}, date_str="2026-11-21"
        )
        self.assertEqual(games[0]["line_scores"]["NYK"], [28, 30, 23])
        self.assertEqual(games[0]["line_scores"]["BOS"], [25, 29, 24])

    def test_skor_string_jadi_int(self):
        games = live_nba.parse_live_scoreboard(
            {"events": [_event(home_score="81", away_score="78")]},
            date_str="2026-11-21",
        )
        self.assertEqual(games[0]["home_score"], 81)
        self.assertIsInstance(games[0]["home_score"], int)

    def test_fetched_at_dari_argumen(self):
        games = live_nba.parse_live_scoreboard(
            {"events": [_event()]},
            date_str="2026-11-21",
            fetched_at="2026-11-22T14:00:00+00:00",
        )
        self.assertEqual(games[0]["fetched_at"], "2026-11-22T14:00:00+00:00")


class TestParseGameSummary(unittest.TestCase):
    def test_fixture_asli_mil_phi(self):
        data = _load_fixture("live_nba_summary_401910023.json")
        stats = live_nba.parse_game_summary(data)
        self.assertEqual(
            stats["MIL"],
            {
                "fg3_made": 16,
                "fg3_attempted": 44,
                "ft_made": 17,
                "ft_attempted": 18,
            },
        )
        self.assertEqual(
            stats["PHI"],
            {
                "fg3_made": 9,
                "fg3_attempted": 28,
                "ft_made": 33,
                "ft_attempted": 37,
            },
        )

    def test_stat_hilang_jadi_none(self):
        data = {
            "boxscore": {
                "teams": [
                    {
                        "team": {"abbreviation": "BOS"},
                        "statistics": [
                            {
                                "name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted",
                                "displayValue": "10-30",
                            }
                        ],
                    }
                ]
            }
        }
        stats = live_nba.parse_game_summary(data)
        self.assertEqual(
            stats["BOS"],
            {
                "fg3_made": 10,
                "fg3_attempted": 30,
                "ft_made": None,
                "ft_attempted": None,
            },
        )

    def test_display_value_rusak_jadi_none(self):
        data = {
            "boxscore": {
                "teams": [
                    {
                        "team": {"abbreviation": "BOS"},
                        "statistics": [
                            {
                                "name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted",
                                "displayValue": "rusak",
                            },
                            {
                                "name": "freeThrowsMade-freeThrowsAttempted",
                                "displayValue": "5-6",
                            },
                        ],
                    }
                ]
            }
        }
        stats = live_nba.parse_game_summary(data)
        self.assertIsNone(stats["BOS"]["fg3_made"])
        self.assertIsNone(stats["BOS"]["fg3_attempted"])
        self.assertEqual(stats["BOS"]["ft_made"], 5)
        self.assertEqual(stats["BOS"]["ft_attempted"], 6)

    def test_format_berubah_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            live_nba.parse_game_summary({})
        self.assertEqual(str(ctx.exception), "espn_format_changed")
        with self.assertRaises(ValueError):
            live_nba.parse_game_summary({"boxscore": {"teams": "bukan-list"}})
        with self.assertRaises(ValueError):
            live_nba.parse_game_summary(None)


class TestFetchLiveGames(unittest.TestCase):
    def test_url_dan_hasil_ok(self):
        client = FakeClient(
            {
                "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20261121": _resp(
                    200, {"events": [_event()]}
                )
            }
        )
        result = live_nba.fetch_live_games("2026-11-21", client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.extra["n_games"], 1)
        self.assertEqual(result.data[0]["match_id"], "BOS@NYK_2026-11-21")
        self.assertEqual(result.data[0]["fetched_at"], result.fetched_at)
        self.assertEqual(
            client.urls_requested,
            [
                "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20261121"
            ],
        )

    def test_tanggal_tidak_valid(self):
        result = live_nba.fetch_live_games("21-11-2026", client=FakeClient({}))
        self.assertFalse(result.ok)
        self.assertIn("tanggal_tidak_valid", result.error)

    def test_http_gagal(self):
        result = live_nba.fetch_live_games("2026-11-21", client=FakeClient({}))
        self.assertFalse(result.ok)
        self.assertIn("http_404", result.error)

    def test_body_bukan_json(self):
        client = FakeClient(
            {
                "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20261121": _resp(
                    200, "bukan json {"
                )
            }
        )
        result = live_nba.fetch_live_games("2026-11-21", client=client)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "espn_format_changed")


class TestFetchGameStats(unittest.TestCase):
    def test_url_dan_hasil_ok(self):
        summary = _load_fixture("live_nba_summary_401910023.json")
        client = FakeClient(
            {
                "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401910023": _resp(
                    200, summary
                )
            }
        )
        result = live_nba.fetch_game_stats("401910023", client=client)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.data["MIL"]["fg3_made"], 16)
        self.assertEqual(result.extra["n_teams"], 2)

    def test_game_id_kosong(self):
        result = live_nba.fetch_game_stats("", client=FakeClient({}))
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "espn_game_id_kosong")

    def test_http_gagal(self):
        result = live_nba.fetch_game_stats("401910023", client=FakeClient({}))
        self.assertFalse(result.ok)
        self.assertIn("http_404", result.error)


class TestLimiterBerbagi(unittest.TestCase):
    def test_default_client_memakai_limiter_modul(self):
        first = live_nba._default_client()
        second = live_nba._default_client()
        self.assertIs(first.rate_limiter, second.rate_limiter)
        self.assertIs(first.rate_limiter, live_nba._LIMITER)
        self.assertIsInstance(live_nba._LIMITER, RateLimiter)


class TestPemetaanSingkatanEspn(unittest.TestCase):
    """Singkatan ESPN dipetakan ke tricode repo (keputusan koordinator).

    6 tim berbeda: GS->GSW, NY->NYK, NO->NOP, SA->SAS, UTAH->UTA,
    WSH->WAS.
    """

    def _event_minimal(self, event_id, home_abbr, away_abbr):
        def kompetitor(home_away, abbr):
            return {
                "homeAway": home_away,
                "score": "100",
                "linescores": [{"displayValue": "25"}] * 4,
                "team": {"abbreviation": abbr, "displayName": abbr},
            }

        return {
            "id": event_id,
            "date": "2026-11-21T19:30Z",
            "status": {
                "period": 4,
                "type": {"state": "post"},
            },
            "competitions": [
                {
                    "competitors": [
                        kompetitor("home", home_abbr),
                        kompetitor("away", away_abbr),
                    ]
                }
            ],
        }

    def test_enam_tim_dipetakan(self):
        data = {
            "events": [
                self._event_minimal("1", "GS", "LAL"),
                self._event_minimal("2", "NY", "BOS"),
                self._event_minimal("3", "SA", "NO"),
                self._event_minimal("4", "WSH", "MIA"),
                self._event_minimal("5", "UTAH", "DAL"),
            ]
        }
        games = live_nba.parse_live_scoreboard(data, date_str="2026-11-21")
        by_id = {g["match_id"]: g for g in games}
        self.assertEqual(
            sorted(by_id),
            [
                "BOS@NYK_2026-11-21",
                "DAL@UTA_2026-11-21",
                "LAL@GSW_2026-11-21",
                "MIA@WAS_2026-11-21",
                "NOP@SAS_2026-11-21",
            ],
        )
        self.assertEqual(by_id["LAL@GSW_2026-11-21"]["home_abbr"], "GSW")
        self.assertEqual(by_id["NOP@SAS_2026-11-21"]["away_abbr"], "NOP")
        self.assertEqual(by_id["MIA@WAS_2026-11-21"]["home_abbr"], "WAS")
        self.assertEqual(by_id["DAL@UTA_2026-11-21"]["home_abbr"], "UTA")
        self.assertEqual(
            by_id["BOS@NYK_2026-11-21"]["line_scores"]["NYK"], [25, 25, 25, 25]
        )

    def test_summary_memakai_tricode(self):
        data = {
            "boxscore": {
                "teams": [
                    {
                        "team": {"abbreviation": "NY"},
                        "statistics": [
                            {
                                "name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted",
                                "displayValue": "9-28",
                            },
                            {
                                "name": "freeThrowsMade-freeThrowsAttempted",
                                "displayValue": "33-37",
                            },
                        ],
                    },
                    {
                        "team": {"abbreviation": "BOS"},
                        "statistics": [
                            {
                                "name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted",
                                "displayValue": "16-44",
                            },
                            {
                                "name": "freeThrowsMade-freeThrowsAttempted",
                                "displayValue": "17-18",
                            },
                        ],
                    },
                ]
            }
        }
        stats = live_nba.parse_game_summary(data)
        self.assertEqual(
            stats["NYK"],
            {
                "fg3_made": 9,
                "fg3_attempted": 28,
                "ft_made": 33,
                "ft_attempted": 37,
            },
        )
        self.assertIn("BOS", stats)


if __name__ == "__main__":
    unittest.main()
