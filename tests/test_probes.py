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

from probes import common

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
