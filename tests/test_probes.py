"""Tes unit untuk probes/common.py + tes import tiap modul probe.

TANPA network dan TANPA API key: semua tes ini memakai jam/tidur injeksi,
cache di direktori sementara, dan mock untuk JupiterClient._request.
Import modul probe tidak boleh memicu request jaringan apa pun.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from probes import (
    check_understat,
    common,
    espn_odds,
    football_data,
    jup_markup,
    kalshi_sports,
)

PROBE_MODULES = [
    "jupiter",
    "polymarket",
    "kalshi",
    "odds_api",
    "nba_com",
    "espn",
    "bbref",
    "nba_injury_report",
    "rotowire",
    "understat",
    "sofascore",
    "fotmob",
    "official_leagues",
    "espn_odds",
    "kalshi_sports",
    "jup_markup",
    "football_data",
    "understat_recheck",
    "check_understat",
    "run_all",
]


class FakeClock:
    """Jam yang bisa dimajukan manual + pencatat tidur (untuk RateLimiter)."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class TestRateLimiter(unittest.TestCase):
    def test_panggilan_pertama_tidak_tidur(self):
        clock = FakeClock()
        limiter = common.RateLimiter(2.0, time_fn=clock.time, sleep_fn=clock.sleep)
        self.assertEqual(limiter.wait("a.example"), 0.0)
        self.assertEqual(clock.slept, [])

    def test_panggilan_kedua_cepat_tidur_sisa_jeda(self):
        clock = FakeClock()
        limiter = common.RateLimiter(2.0, time_fn=clock.time, sleep_fn=clock.sleep)
        limiter.wait("a.example")
        clock.now += 0.5  # baru 0,5 dtk berlalu, jeda minimum 2 dtk
        slept = limiter.wait("a.example")
        self.assertAlmostEqual(slept, 1.5)
        self.assertEqual(clock.slept, [1.5])

    def test_panggilan_setelah_jeda_tidak_tidur(self):
        clock = FakeClock()
        limiter = common.RateLimiter(2.0, time_fn=clock.time, sleep_fn=clock.sleep)
        limiter.wait("a.example")
        clock.now += 2.5
        self.assertEqual(limiter.wait("a.example"), 0.0)
        self.assertEqual(clock.slept, [])

    def test_host_berbeda_tidak_saling_tunggu(self):
        clock = FakeClock()
        limiter = common.RateLimiter(2.0, time_fn=clock.time, sleep_fn=clock.sleep)
        limiter.wait("a.example")
        self.assertEqual(limiter.wait("b.example"), 0.0)
        self.assertEqual(clock.slept, [])


class TestDiskCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = common.DiskCache(self.tmp.name, ttl_seconds=3600)

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip(self):
        value = {"status": 200, "body": "hello"}
        self.cache.set("https://x.example/a", value)
        self.assertEqual(self.cache.get("https://x.example/a"), value)

    def test_url_tidak_ada_kembali_none(self):
        self.assertIsNone(self.cache.get("https://x.example/tidak-ada"))

    def test_entri_kedaluwarsa_kembali_none(self):
        expired = common.DiskCache(self.tmp.name, ttl_seconds=-1)
        expired.set("https://x.example/a", {"status": 200})
        self.assertIsNone(expired.get("https://x.example/a"))

    def test_kunci_deterministik_dan_berbeda_per_url(self):
        key_a = common.DiskCache.key_for("https://x.example/a")
        key_b = common.DiskCache.key_for("https://x.example/b")
        self.assertEqual(key_a, common.DiskCache.key_for("https://x.example/a"))
        self.assertNotEqual(key_a, key_b)
        self.assertEqual(len(key_a), 64)  # SHA-256 heksadesimal

    def test_file_rusak_kembali_none(self):
        key = common.DiskCache.key_for("https://x.example/a")
        Path(self.tmp.name, f"{key}.json").write_text("bukan json {", encoding="utf-8")
        self.assertIsNone(self.cache.get("https://x.example/a"))


class TestLoadDotenv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_komentar_kutip_dan_baris_kosong(self):
        (self.root / ".env").write_text(
            "# komentar\n"
            "JUPITER_API_KEY=jup_contoh\n"
            "KOSONG=\n"
            "BERKUTIP='nilai spasi'\n"
            "\n"
            "TANPA_NILAI\n",
            encoding="utf-8",
        )
        values = common.load_dotenv(self.root)
        self.assertEqual(values["JUPITER_API_KEY"], "jup_contoh")
        self.assertEqual(values["KOSONG"], "")
        self.assertEqual(values["BERKUTIP"], "nilai spasi")
        self.assertNotIn("TANPA_NILAI", values)

    def test_file_tidak_ada_kembali_kosong(self):
        self.assertEqual(common.load_dotenv(self.root), {})

    def test_nilai_mengandung_tanda_sama_dengan(self):
        (self.root / ".env").write_text("KUNCI=abc=def\n", encoding="utf-8")
        self.assertEqual(common.load_dotenv(self.root)["KUNCI"], "abc=def")


class TestHeaderHelpers(unittest.TestCase):
    def test_header_sensitif_dibuang(self):
        safe = common._safe_headers(
            {
                "Content-Type": "application/json",
                "Authorization": "Bearer rahasia",
                "x-api-key": "kunci-rahasia",
                "Cookie": "sesi=abc",
                "X-RateLimit-Limit": "600",
            }
        )
        self.assertEqual(
            safe, {"Content-Type": "application/json", "X-RateLimit-Limit": "600"}
        )

    def test_header_rate_limit_diekstrak(self):
        found = common.rate_limit_headers(
            {
                "Content-Type": "application/json",
                "x-ratelimit-limit": "600",
                "x-ratelimit-remaining": "550",
                "Retry-After": "0",
            }
        )
        self.assertEqual(
            found,
            {
                "x-ratelimit-limit": "600",
                "x-ratelimit-remaining": "550",
                "Retry-After": "0",
            },
        )


class TestHttpClientCacheHit(unittest.TestCase):
    def test_get_dari_cache_tanpa_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = common.DiskCache(tmp, ttl_seconds=3600)
            url = "https://x.example/a"
            cache.set(url, {"status": 200, "body": "dari-cache"})
            client = common.HttpClient(common.RateLimiter(0), cache=cache)
            # urlopen dipatch agar tes gagal bila network benar-benar dipanggil.
            with mock.patch(
                "urllib.request.urlopen",
                side_effect=AssertionError("network tidak boleh dipanggil"),
            ):
                result = client.get(url)
            self.assertTrue(result["from_cache"])
            self.assertEqual(result["body"], "dari-cache")
            self.assertEqual(result["status"], 200)


class TestJupiterClient(unittest.TestCase):
    def test_path_dilarang_ditolak_tanpa_network(self):
        client = common.JupiterClient(api_key="palsu")
        for path in (
            "/orders",
            "/positions",
            "/claim",
            "/events/123/orders",
            "/markets/abc/claim",
            "/events/search/extra",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                client.get(path)

    def test_path_baca_diterima_dan_mode_keyed(self):
        client = common.JupiterClient(api_key="palsu")
        fake = {"status": 200, "body": "{}", "error": None}
        with mock.patch.object(
            common.JupiterClient, "_request", return_value=dict(fake)
        ) as req:
            result = client.get("/events", params={"category": "sports"})
        self.assertEqual(result["mode"], "keyed")
        self.assertEqual(client.mode_used, "keyed")
        self.assertFalse(client.fallback_used)
        req.assert_called_once()

    def test_fallback_keyless_saat_401(self):
        client = common.JupiterClient(api_key="palsu")
        calls = [
            {"status": 401, "body": "unauthorized", "error": None},
            {"status": 200, "body": "{}", "error": None},
        ]
        with mock.patch.object(
            common.JupiterClient, "_request", side_effect=calls
        ) as req:
            result = client.get("/events/abc")
        self.assertEqual(result["mode"], "keyless")
        self.assertEqual(client.mode_used, "keyless")
        self.assertTrue(client.fallback_used)
        self.assertEqual(req.call_count, 2)

    def test_tanpa_key_langsung_keyless(self):
        client = common.JupiterClient(api_key=None)
        fake = {"status": 200, "body": "{}", "error": None}
        with mock.patch.object(
            common.JupiterClient, "_request", return_value=dict(fake)
        ) as req:
            result = client.get("/markets/abc")
        self.assertEqual(result["mode"], "keyless")
        self.assertFalse(client.fallback_used)
        req.assert_called_once()


class TestResultHelpers(unittest.TestCase):
    def test_new_result_punya_semua_kunci(self):
        result = common.new_result("Contoh", 2)
        for key in (
            "source",
            "tier",
            "probed_at",
            "accessible_from_vm",
            "format",
            "rate_limit",
            "data_available",
            "risk_notes",
            "requests",
            "verdict",
            "unknown",
        ):
            self.assertIn(key, result)
        self.assertEqual(result["source"], "Contoh")
        self.assertEqual(result["tier"], 2)

    def test_parse_json_body(self):
        self.assertEqual(common.parse_json_body({"body": '{"a": 1}'}), {"a": 1})
        self.assertEqual(common.parse_json_body({"body": "[1, 2]"}), [1, 2])
        self.assertIsNone(common.parse_json_body({"body": "bukan json"}))
        self.assertIsNone(common.parse_json_body({"body": ""}))
        self.assertIsNone(common.parse_json_body({}))


class TestJupMarkup(unittest.TestCase):
    def test_micro_usd_ke_cents(self):
        self.assertEqual(jup_markup.micro_usd_to_cents(430000), 43.0)
        self.assertEqual(jup_markup.micro_usd_to_cents(0), 0.0)
        self.assertIsNone(jup_markup.micro_usd_to_cents(None))
        self.assertIsNone(jup_markup.micro_usd_to_cents("430000"))
        self.assertIsNone(jup_markup.micro_usd_to_cents(True))

    def test_line_as_float(self):
        self.assertEqual(jup_markup.line_as_float("2.5"), 2.5)
        self.assertEqual(jup_markup.line_as_float(-1.5), -1.5)
        self.assertIsNone(jup_markup.line_as_float(None))
        self.assertIsNone(jup_markup.line_as_float("bukan-angka"))

    def test_yes_token_id_pasar_dua_outcome_berbagi_token(self):
        # Moneyline NBA: dua pasar berbagi satu pasangan token; pasar tim
        # kedua memakai token [1] (memakai [0] memberi markup palsu).
        market = {
            "title": "Bulls",
            "team": {"name": "Bulls"},
            "outcomes": ["Wizards", "Bulls"],
            "clobTokenIds": ["token-yes", "token-no"],
        }
        token, index, _ = jup_markup.yes_token_id(market)
        self.assertEqual(token, "token-no")
        self.assertEqual(index, 1)
        market["title"] = "Wizards"
        market["team"] = {"name": "Wizards"}
        token, index, _ = jup_markup.yes_token_id(market)
        self.assertEqual(token, "token-yes")
        self.assertEqual(index, 0)

    def test_yes_token_id_pasar_biner_mandiri_fallback_nol(self):
        market = {
            "title": "Chelsea FC",
            "team": {"name": "Chelsea FC"},
            "outcomes": ["Yes", "No"],
            "clobTokenIds": ["token-yes", "token-no"],
        }
        token, index, how = jup_markup.yes_token_id(market)
        self.assertEqual(token, "token-yes")
        self.assertEqual(index, 0)
        self.assertIn("fallback", how)

    def test_yes_token_id_tanpa_token(self):
        token, index, _ = jup_markup.yes_token_id(
            {"title": "X", "outcomes": ["X", "Y"], "clobTokenIds": []}
        )
        self.assertIsNone(token)
        self.assertIsNone(index)

    def test_book_midpoint_dan_spread(self):
        book = {
            "bids": [{"price": "0.42", "size": "100"}, {"price": "0.41", "size": "50"}],
            "asks": [{"price": "0.43", "size": "80"}, {"price": "0.44", "size": "10"}],
        }
        self.assertAlmostEqual(jup_markup.book_midpoint(book), 42.5)
        self.assertAlmostEqual(jup_markup.book_spread(book), 1.0)
        self.assertIsNone(jup_markup.book_midpoint({"bids": [], "asks": book["asks"]}))
        self.assertIsNone(jup_markup.book_midpoint({"bids": book["bids"], "asks": []}))
        self.assertIsNone(
            jup_markup.book_midpoint({"bids": [{"price": "x"}], "asks": []})
        )
        self.assertIsNone(jup_markup.book_midpoint(None))

    def test_compute_markup(self):
        self.assertAlmostEqual(jup_markup.compute_markup(43.0, 42.5), 0.5)
        self.assertAlmostEqual(jup_markup.compute_markup(25.0, 25.5), -0.5)


class TestKalshiMatching(unittest.TestCase):
    def test_normalize_team_buang_kata_pengisi(self):
        self.assertEqual(kalshi_sports.normalize_team("Chelsea FC"), "chelsea")
        self.assertEqual(kalshi_sports.normalize_team("AFC Bournemouth"), "bournemouth")
        self.assertEqual(
            kalshi_sports.normalize_team("Newcastle United FC"), "newcastle"
        )
        self.assertEqual(kalshi_sports.normalize_team("RC Celta de Vigo"), "celta vigo")
        self.assertEqual(
            kalshi_sports.normalize_team("Manchester City FC"), "manchester city"
        )
        self.assertEqual(kalshi_sports.normalize_team("Sunderland AFC"), "sunderland")

    def test_normalize_nba_team_julukan_ke_kota(self):
        self.assertEqual(kalshi_sports.normalize_nba_team("Hornets"), "charlotte")
        self.assertEqual(kalshi_sports.normalize_nba_team("Lakers"), "los angeles l")
        self.assertEqual(kalshi_sports.normalize_nba_team("Clippers"), "los angeles c")
        self.assertEqual(kalshi_sports.normalize_nba_team("Trail Blazers"), "portland")
        self.assertEqual(kalshi_sports.normalize_nba_team("76ers"), "philadelphia")
        # Nama kota dibiarkan apa adanya.
        self.assertEqual(kalshi_sports.normalize_nba_team("Chicago"), "chicago")

    def test_normalize_soccer_team_alias(self):
        self.assertEqual(kalshi_sports.normalize_soccer_team("Athletic Club"), "bilbao")
        self.assertEqual(
            kalshi_sports.normalize_soccer_team("RCD Espanyol de Barcelona"),
            "espanyol",
        )

    def test_parse_vs_title(self):
        self.assertEqual(
            kalshi_sports.parse_vs_title("Wizards vs. Bulls"),
            ("Wizards", "Bulls"),
        )
        self.assertEqual(
            kalshi_sports.parse_vs_title("Chelsea vs Leeds United"),
            ("Chelsea", "Leeds United"),
        )
        self.assertIsNone(kalshi_sports.parse_vs_title("NBA: 2027 Champion"))

    def test_same_game_nba_kota_vs_julukan(self):
        self.assertTrue(
            kalshi_sports.same_game_nba("Hornets vs. Hawks", "Charlotte vs Atlanta")
        )
        self.assertTrue(
            kalshi_sports.same_game_nba(
                "Kings vs. Lakers", "Sacramento vs Los Angeles L"
            )
        )
        # Urutan tim bebas.
        self.assertTrue(
            kalshi_sports.same_game_nba("Hawks vs. Hornets", "Charlotte vs Atlanta")
        )
        self.assertFalse(
            kalshi_sports.same_game_nba("Hornets vs. Hawks", "Charlotte vs Boston")
        )
        # Lakers vs Clippers tidak boleh tertukar.
        self.assertFalse(
            kalshi_sports.same_game_nba(
                "Kings vs. Lakers", "Sacramento vs Los Angeles C"
            )
        )

    def test_same_game_soccer(self):
        self.assertTrue(
            kalshi_sports.same_game_soccer(
                "Chelsea FC vs. Leeds United FC", "Chelsea vs Leeds United"
            )
        )
        self.assertTrue(
            kalshi_sports.same_game_soccer(
                "Athletic Club vs. RCD Espanyol de Barcelona",
                "Bilbao vs Espanyol",
            )
        )
        self.assertTrue(
            kalshi_sports.same_game_soccer(
                "AFC Bournemouth vs. Nottingham Forest FC",
                "Bournemouth vs Nottingham Forest",
            )
        )
        self.assertFalse(
            kalshi_sports.same_game_soccer(
                "Chelsea FC vs. Leeds United FC", "Chelsea vs Arsenal"
            )
        )

    def test_parse_kalshi_spread_title(self):
        # Format NBA: "wins by over X points".
        self.assertEqual(
            kalshi_sports.parse_kalshi_spread_title("Utah wins by over 7.5 points"),
            ("utah", 7.5),
        )
        # Format bola: "wins by more than X goals?".
        self.assertEqual(
            kalshi_sports.parse_kalshi_spread_title(
                "Chelsea wins by more than 1.5 goals?"
            ),
            ("chelsea", 1.5),
        )
        self.assertIsNone(kalshi_sports.parse_kalshi_spread_title("Utah wins"))
        self.assertIsNone(kalshi_sports.parse_kalshi_spread_title(""))

    def test_parse_kalshi_total_title(self):
        self.assertEqual(
            kalshi_sports.parse_kalshi_total_title("Will over 2.5 goals be scored?"),
            2.5,
        )
        self.assertIsNone(
            kalshi_sports.parse_kalshi_total_title("Will under 2.5 goals be scored?")
        )
        self.assertIsNone(kalshi_sports.parse_kalshi_total_title(""))


class TestUnderstatStatus(unittest.TestCase):
    def test_maintenance(self):
        self.assertEqual(
            check_understat.classify_status(200, "<html>We will come back soon</html>"),
            "maintenance",
        )

    def test_up(self):
        self.assertEqual(
            check_understat.classify_status(
                200, "<html>var teamsData = {}; var datesData = {};</html>"
            ),
            "up",
        )

    def test_unknown(self):
        self.assertEqual(
            check_understat.classify_status(200, "<html>halaman lain</html>"),
            "unknown",
        )

    def test_down(self):
        self.assertEqual(check_understat.classify_status(503, ""), "down")
        self.assertEqual(check_understat.classify_status(404, ""), "down")
        self.assertEqual(
            check_understat.classify_status(None, "", error="URLError"), "down"
        )


class TestEspnOdds(unittest.TestCase):
    def test_american_to_implied_prob(self):
        self.assertAlmostEqual(espn_odds.american_to_implied_prob("-260"), 260 / 360)
        self.assertAlmostEqual(espn_odds.american_to_implied_prob("+650"), 100 / 750)
        self.assertIsNone(espn_odds.american_to_implied_prob("0"))
        self.assertIsNone(espn_odds.american_to_implied_prob("abc"))
        self.assertIsNone(espn_odds.american_to_implied_prob(None))

    def test_parse_odds_entry_draftkings(self):
        entry = {
            "provider": {"name": "DraftKings"},
            "overUnder": 2.5,
            "moneyline": {
                "home": {"close": {"odds": "-260"}},
                "away": {"close": {"odds": "+650"}},
                "draw": {"close": {"odds": "+425"}},
            },
            "pointSpread": {
                "home": {"close": {"line": "-1.5", "odds": "-105"}},
                "away": {"close": {"line": "+1.5", "odds": "-130"}},
            },
            "total": {
                "over": {"close": {"line": "o2.5", "odds": "+120"}},
                "under": {"close": {"line": "u2.5", "odds": "-145"}},
            },
        }
        parsed = espn_odds.parse_odds_entry(entry)
        self.assertEqual(parsed["provider"], "DraftKings")
        self.assertEqual(parsed["moneyline"]["home"], "-260")
        self.assertEqual(parsed["moneyline"]["draw"], "+425")
        self.assertEqual(parsed["spread"]["home_line"], "-1.5")
        self.assertEqual(parsed["total"]["under_odds"], "-145")

    def test_parse_odds_entry_bet365_desimal(self):
        entry = {
            "provider": {"name": "Bet 365"},
            "homeTeamOdds": {"odds": {"summary": "4/11", "value": 1.364}},
            "awayTeamOdds": {"odds": {"summary": "6/1", "value": 7.0}},
            "drawOdds": {"summary": "17/4", "value": 5.25},
        }
        parsed = espn_odds.parse_odds_entry(entry)
        self.assertEqual(parsed["provider"], "Bet 365")
        self.assertEqual(parsed["moneyline_decimal"]["home"], 1.364)
        self.assertEqual(parsed["moneyline_decimal"]["away"], 7.0)
        self.assertEqual(parsed["moneyline_decimal"]["draw"], 5.25)
        self.assertIsNone(parsed["moneyline"]["home"])
        self.assertIsNone(parsed["spread"]["home_line"])

    def test_parse_odds_entry_kosong(self):
        parsed = espn_odds.parse_odds_entry({})
        self.assertIsNone(parsed["provider"])
        self.assertIsNone(parsed["moneyline"]["home"])
        self.assertIsNone(parsed["moneyline_decimal"]["home"])
        self.assertIsNone(parsed["total"]["over_line"])


class TestFootballData(unittest.TestCase):
    def test_pinnacle_columns(self):
        header = [
            "Div",
            "Date",
            "PSH",
            "PSD",
            "PSA",
            "PSCH",
            "PSCD",
            "PSCA",
            "P>2.5",
            "P<2.5",
            "B365H",
        ]
        found = football_data.pinnacle_columns(header)
        self.assertEqual(found["1x2_open"], ["PSH", "PSD", "PSA"])
        self.assertEqual(found["1x2_close"], ["PSCH", "PSCD", "PSCA"])
        self.assertEqual(found["over_under_2_5"], ["P>2.5", "P<2.5"])
        found = football_data.pinnacle_columns(["Div", "Date", "B365H"])
        self.assertEqual(found["1x2_open"], [])
        self.assertEqual(found["over_under_2_5"], [])

    def test_parse_csv_sample(self):
        text = (
            "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,PSH,PSD,PSA\n"
            "E0,15/08/2025,Liverpool,Bournemouth,4,2,1.28,6.56,9.07\n"
            "E0,16/08/2025,Man United,Fulham,1,0,1.63,4.38,5.3\n"
        )
        parsed = football_data.parse_csv_sample(text)
        self.assertEqual(parsed["n_rows"], 2)
        self.assertIn("PSH", parsed["header"])
        self.assertEqual(parsed["sample_row"]["HomeTeam"], "Liverpool")
        self.assertEqual(parsed["sample_row"]["PSH"], "1.28")
        self.assertEqual(football_data.parse_csv_sample("")["n_rows"], 0)

    def test_leagues_from_data_page(self):
        html = (
            "<html><body><table>"
            "<tr><td>England Football Results</td></tr>"
            "<tr><td>Spain Football Results</td></tr>"
            "<tr><td>Football Betting</td></tr>"
            "</table></body></html>"
        )
        self.assertEqual(
            football_data.leagues_from_data_page(html), ["England", "Spain"]
        )


class TestProbeImports(unittest.TestCase):
    def test_semua_modul_probe_bisa_diimpor_tanpa_network(self):
        import importlib

        with mock.patch(
            "urllib.request.urlopen",
            side_effect=AssertionError("import tidak boleh memanggil network"),
        ):
            for name in PROBE_MODULES:
                with self.subTest(module=name):
                    module = importlib.import_module(f"probes.{name}")
                    self.assertIsNotNone(module)


if __name__ == "__main__":
    unittest.main()
