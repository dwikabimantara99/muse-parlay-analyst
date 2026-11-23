"""Tes ingest/news_nba.py — TANPA network (mock client + fixture).

Fixture dibentuk dari respons ESPN nyata yang tersimpan di
tests/fixtures/espn_news_nba_2026-11-23.json (3 artikel, probe
2026-11-23). Tes fetch memakai jam terbit relatif terhadap jam
sekarang (bukan jam fixture) agar tidak basi bila suite dijalankan
berhari-hari kemudian.
"""

import json
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from ingest import news_nba

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "espn_news_nba_2026-11-23.json"
)

CFG_NEWS = {
    "news": {
        "max_items_fetch": 50,
        "max_age_hours": 72,
        "max_items_per_match": 5,
        "cache_ttl_seconds": 600,
        "rate_gap_seconds": 1.0,
    }
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


def _artikel(
    artikel_id,
    headline,
    jam_terbit,
    teams=None,
    description=None,
    tipe="Story",
):
    """Satu artikel mentah bentuk respons ESPN."""
    return {
        "id": artikel_id,
        "headline": headline,
        "description": description,
        "published": jam_terbit,
        "lastModified": jam_terbit,
        "type": tipe,
        "premium": False,
        "links": {"web": {"href": f"https://www.espn.com/nba/story/_/id/{artikel_id}"}},
        "categories": [
            {
                "type": "team",
                "description": nama,
                "team": {"id": i + 1},
            }
            for i, nama in enumerate(teams or [])
        ],
    }


def _jam_rel(jam_lalu: float) -> str:
    """Jam ISO (UTC) sekian jam yang lalu."""
    return (datetime.now(UTC) - timedelta(hours=jam_lalu)).isoformat()


class TestParseNews(unittest.TestCase):
    def test_fixture_nyata_tiga_artikel(self):
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        artikel = news_nba.parse_news(data)
        self.assertEqual(len(artikel), 3)
        pertama = artikel[0]
        self.assertIn("Jokic", pertama["headline"])
        self.assertEqual(pertama["type"], "Recap")
        self.assertEqual(pertama["published"], "2026-11-23T03:15:33Z")
        self.assertIsNotNone(pertama["description"])
        self.assertIn("http", pertama["url"])
        tim = {t["name"] for t in pertama["teams"]}
        self.assertEqual(tim, {"Chicago Bulls", "Denver Nuggets"})
        self.assertEqual({t["id"] for t in pertama["teams"]}, {4, 7})

    def test_artikel_media_tetap_diparse(self):
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        artikel = news_nba.parse_news(data)
        media = [a for a in artikel if a["type"] == "Media"]
        self.assertEqual(len(media), 1)
        self.assertIn("Highlights", media[0]["headline"])

    def test_format_berubah_value_error(self):
        with self.assertRaises(ValueError):
            news_nba.parse_news({"bukan": "artikel"})
        with self.assertRaises(ValueError):
            news_nba.parse_news({"articles": "bukan-list"})

    def test_artikel_tanpa_headline_dilewati(self):
        data = {"articles": [{"id": 1, "headline": "  "}, {"id": 2, "headline": "Ada"}]}
        artikel = news_nba.parse_news(data)
        self.assertEqual([a["id"] for a in artikel], ["2"])

    def test_field_hilang_jadi_none_bukan_tebakan(self):
        artikel = news_nba.parse_news({"articles": [{"headline": "Judul saja"}]})
        self.assertEqual(len(artikel), 1)
        self.assertIsNone(artikel[0]["published"])
        self.assertIsNone(artikel[0]["url"])
        self.assertEqual(artikel[0]["teams"], [])
        self.assertEqual(artikel[0]["athletes"], [])


class TestArticleRelevan(unittest.TestCase):
    def test_kategori_tim_cocok(self):
        artikel = _artikel(1, "Nuggets menang", _jam_rel(1), teams=["Denver Nuggets"])
        parsed = news_nba.parse_news({"articles": [artikel]})[0]
        self.assertTrue(news_nba.article_relevan(parsed, "CHI", "DEN"))
        self.assertTrue(news_nba.article_relevan(parsed, "DEN", "CHI"))

    def test_kategori_tim_tidak_cocok(self):
        artikel = _artikel(1, "Nuggets menang", _jam_rel(1), teams=["Denver Nuggets"])
        parsed = news_nba.parse_news({"articles": [artikel]})[0]
        self.assertFalse(news_nba.article_relevan(parsed, "BOS", "NYK"))

    def test_fixture_den_chi_relevan_untuk_den_chi(self):
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        artikel = news_nba.parse_news(data)
        relevan = [a for a in artikel if news_nba.article_relevan(a, "CHI", "DEN")]
        # Recap DEN@CHI + Highlights DEN@CHI; recap DAL@UTA tidak relevan.
        self.assertEqual(len(relevan), 2)

    def test_fallback_nama_lengkap_di_judul(self):
        artikel = _artikel(
            1, "Oklahoma City Thunder menang telak", _jam_rel(1), teams=[]
        )
        parsed = news_nba.parse_news({"articles": [artikel]})[0]
        self.assertTrue(news_nba.article_relevan(parsed, "OKC", "MIA"))

    def test_julukan_saja_di_judul_tidak_cukup(self):
        # "Thunder" sebagai kata umum ("thunderous") bukan bukti tim OKC.
        artikel = _artikel(1, "Thunderous dunk menutup laga", _jam_rel(1), teams=[])
        parsed = news_nba.parse_news({"articles": [artikel]})[0]
        self.assertFalse(news_nba.article_relevan(parsed, "OKC", "MIA"))

    def test_dua_tim_los_angeles_dibedakan(self):
        artikel = _artikel(
            1, "Los Angeles Lakers menang", _jam_rel(1), teams=["Los Angeles Lakers"]
        )
        parsed = news_nba.parse_news({"articles": [artikel]})[0]
        self.assertTrue(news_nba.article_relevan(parsed, "LAL", "BOS"))
        self.assertFalse(news_nba.article_relevan(parsed, "LAC", "BOS"))


class TestFetchNewsNba(unittest.TestCase):
    def test_ok_hanya_yang_relevan_dan_terbaru_dulu(self):
        body = {
            "articles": [
                _artikel(1, "Lama", _jam_rel(5), teams=["Denver Nuggets"]),
                _artikel(2, "Baru", _jam_rel(1), teams=["Denver Nuggets"]),
                _artikel(3, "Tim lain", _jam_rel(0.5), teams=["Boston Celtics"]),
            ]
        }
        client = FakeClient({f"{news_nba.NEWS_URL}?limit=50": _resp(200, body)})
        hasil = news_nba.fetch_news_nba(
            "CHI", "DEN", "2026-11-23", client=client, cfg=CFG_NEWS
        )
        self.assertTrue(hasil.ok)
        self.assertEqual([a["headline"] for a in hasil.data], ["Baru", "Lama"])
        self.assertEqual(hasil.extra["n_fetched"], 3)
        self.assertEqual(hasil.extra["n_relevant"], 2)
        self.assertEqual(hasil.extra["n_kept"], 2)
        for item in hasil.data:
            self.assertEqual(item["source"], "ESPN")
            self.assertEqual(item["tier"], 2)
            self.assertEqual(item["time"], hasil.fetched_at)

    def test_tidak_ada_berita_ok_true_data_kosong(self):
        body = {
            "articles": [_artikel(1, "Tim lain", _jam_rel(1), teams=["Boston Celtics"])]
        }
        client = FakeClient({f"{news_nba.NEWS_URL}?limit=50": _resp(200, body)})
        hasil = news_nba.fetch_news_nba(
            "CHI", "DEN", "2026-11-23", client=client, cfg=CFG_NEWS
        )
        self.assertTrue(hasil.ok)
        self.assertEqual(hasil.data, [])

    def test_berita_lebih_tua_dari_max_age_dibuang(self):
        body = {
            "articles": [
                _artikel(1, "Sangat lama", _jam_rel(100), teams=["Denver Nuggets"]),
                _artikel(2, "Masih segar", _jam_rel(10), teams=["Denver Nuggets"]),
            ]
        }
        client = FakeClient({f"{news_nba.NEWS_URL}?limit=50": _resp(200, body)})
        hasil = news_nba.fetch_news_nba(
            "CHI", "DEN", "2026-11-23", client=client, cfg=CFG_NEWS
        )
        self.assertTrue(hasil.ok)
        self.assertEqual([a["headline"] for a in hasil.data], ["Masih segar"])

    def test_artikel_tanpa_jam_terbit_tetap_disertakan(self):
        body = {
            "articles": [
                _artikel(1, "Tanpa jam", None, teams=["Denver Nuggets"]),
            ]
        }
        client = FakeClient({f"{news_nba.NEWS_URL}?limit=50": _resp(200, body)})
        hasil = news_nba.fetch_news_nba(
            "CHI", "DEN", "2026-11-23", client=client, cfg=CFG_NEWS
        )
        self.assertTrue(hasil.ok)
        self.assertEqual(len(hasil.data), 1)
        self.assertIsNone(hasil.data[0]["published"])

    def test_cap_max_items_per_match(self):
        body = {
            "articles": [
                _artikel(i, f"Berita {i}", _jam_rel(i), teams=["Denver Nuggets"])
                for i in range(1, 9)
            ]
        }
        cfg = {"news": {**CFG_NEWS["news"], "max_items_per_match": 3}}
        client = FakeClient({f"{news_nba.NEWS_URL}?limit=50": _resp(200, body)})
        hasil = news_nba.fetch_news_nba(
            "CHI", "DEN", "2026-11-23", client=client, cfg=cfg
        )
        self.assertTrue(hasil.ok)
        self.assertEqual(len(hasil.data), 3)
        self.assertEqual(hasil.extra["n_relevant"], 8)
        self.assertEqual(hasil.extra["n_kept"], 3)

    def test_http_gagal_ok_false(self):
        client = FakeClient({f"{news_nba.NEWS_URL}?limit=50": _resp(500, "")})
        hasil = news_nba.fetch_news_nba(
            "CHI", "DEN", "2026-11-23", client=client, cfg=CFG_NEWS
        )
        self.assertFalse(hasil.ok)
        self.assertIn("http_500", hasil.error or "")

    def test_body_bukan_json_ok_false(self):
        client = FakeClient(
            {f"{news_nba.NEWS_URL}?limit=50": _resp(200, "bukan json {")}
        )
        hasil = news_nba.fetch_news_nba(
            "CHI", "DEN", "2026-11-23", client=client, cfg=CFG_NEWS
        )
        self.assertFalse(hasil.ok)
        self.assertEqual(hasil.error, "espn_format_changed")

    def test_config_hilang_ok_false_tanpa_request_http(self):
        client = FakeClient({})
        hasil = news_nba.fetch_news_nba(
            "CHI", "DEN", "2026-11-23", client=client, cfg={}
        )
        self.assertFalse(hasil.ok)
        self.assertIn("news", hasil.error or "")
        self.assertEqual(client.urls_requested, [])

    def test_config_nilai_tidak_valid_ok_false(self):
        cfg = {"news": {**CFG_NEWS["news"], "max_items_per_match": 0}}
        client = FakeClient({})
        hasil = news_nba.fetch_news_nba(
            "CHI", "DEN", "2026-11-23", client=client, cfg=cfg
        )
        self.assertFalse(hasil.ok)
        self.assertEqual(client.urls_requested, [])

    def test_argumen_tidak_valid_ok_false(self):
        client = FakeClient({})
        hasil = news_nba.fetch_news_nba(
            "", "DEN", "2026-11-23", client=client, cfg=CFG_NEWS
        )
        self.assertFalse(hasil.ok)
        hasil = news_nba.fetch_news_nba(
            "CHI", "DEN", "23-11-2026", client=client, cfg=CFG_NEWS
        )
        self.assertFalse(hasil.ok)
        self.assertEqual(client.urls_requested, [])


class TestConfigNews(unittest.TestCase):
    def test_playstyle_yaml_punya_section_news_valid(self):
        cfg = config_mod.load_playstyle()
        params = news_nba._baca_config(cfg)
        self.assertEqual(params["max_items_fetch"], 50)
        self.assertEqual(params["max_age_hours"], 72)
        self.assertEqual(params["max_items_per_match"], 5)
        self.assertEqual(params["cache_ttl_seconds"], 600)
        self.assertEqual(params["rate_gap_seconds"], 1.0)


if __name__ == "__main__":
    unittest.main()
