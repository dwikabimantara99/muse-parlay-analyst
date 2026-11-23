"""Tes report/news_section.py — render murni, tanpa network/config."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from report.news_section import bagian_berita


def _item(headline, **overrides):
    item = {
        "headline": headline,
        "description": "Ringkasan berita.",
        "published": "2026-11-23T03:15:33Z",
        "url": "https://www.espn.com/nba/story/_/id/1",
        "type": "Story",
        "source": "ESPN",
    }
    item.update(overrides)
    return item


class TestBagianBerita(unittest.TestCase):
    def test_ok_dengan_item(self):
        judul, baris = bagian_berita(
            {
                "status": "ok",
                "items": [_item("Jokic cetak triple-double")],
                "sources": ["ESPN"],
                "fetched_at": "2026-11-23T04:00:00+00:00",
                "error": None,
            },
            "Denver Nuggets",
            "Chicago Bulls",
        )
        teks = "\n".join(baris)
        self.assertEqual(judul, "Berita")
        self.assertIn("Jokic cetak triple-double", teks)
        self.assertIn("Ringkasan berita.", teks)
        self.assertIn("ESPN", teks)
        self.assertIn("23 Nov 2026 03:15 UTC", teks)
        self.assertIn("https://www.espn.com/nba/story/_/id/1", teks)
        self.assertIn("bukan angka", teks)

    def test_item_media_dilabeli_video(self):
        _, baris = bagian_berita(
            {
                "status": "ok",
                "items": [
                    _item(
                        "Nuggets vs Bulls: Highlights",
                        type="Media",
                        description=None,
                        url=None,
                    )
                ],
                "sources": ["ESPN"],
                "fetched_at": "2026-11-23T04:00:00+00:00",
                "error": None,
            },
            "Denver Nuggets",
            "Chicago Bulls",
        )
        self.assertIn("- Nuggets vs Bulls: Highlights (video)", baris)

    def test_ok_tanpa_item_dikatakan_apa_adanya(self):
        _, baris = bagian_berita(
            {
                "status": "ok",
                "items": [],
                "sources": ["ESPN"],
                "fetched_at": None,
                "error": None,
            },
            "Denver Nuggets",
            "Chicago Bulls",
        )
        self.assertIn("Tidak ada berita yang tercatat.", baris)

    def test_kosong(self):
        judul, baris = bagian_berita(
            {
                "status": "kosong",
                "items": [],
                "sources": ["ESPN"],
                "fetched_at": "2026-11-23T04:00:00+00:00",
                "error": None,
            },
            "Denver Nuggets",
            "Chicago Bulls",
        )
        teks = "\n".join(baris)
        self.assertEqual(judul, "Berita")
        self.assertIn(
            "Tidak ada berita terbaru tentang Chicago Bulls atau Denver Nuggets.", teks
        )
        self.assertIn("ESPN", teks)
        self.assertIn("23 Nov 2026 04:00 UTC", teks)

    def test_gagal_dengan_error(self):
        _, baris = bagian_berita(
            {
                "status": "gagal",
                "items": [],
                "sources": [],
                "fetched_at": "2026-11-23T04:00:00+00:00",
                "error": "http_500: espn gagal",
            },
            "Denver Nuggets",
            "Chicago Bulls",
        )
        teks = "\n".join(baris)
        self.assertIn("Berita tidak bisa diambil", teks)
        self.assertIn("cek sendiri berita terbaru sebelum pasang", teks)
        self.assertIn("http_500", teks)

    def test_gagal_tidak_diambil_tanpa_catatan_mesin(self):
        _, baris = bagian_berita(
            {
                "status": "gagal",
                "items": [],
                "sources": [],
                "fetched_at": None,
                "error": "tidak_diambil",
            },
            "Denver Nuggets",
            "Chicago Bulls",
        )
        teks = "\n".join(baris)
        self.assertIn("Berita tidak bisa diambil", teks)
        self.assertNotIn("tidak_diambil", teks)

    def test_none_artefak_lama(self):
        _, baris = bagian_berita(None, "Denver Nuggets", "Chicago Bulls")
        self.assertIn(
            "Berita tidak tersedia di artefak ini (analisis dibuat "
            "sebelum modul berita ada).",
            baris,
        )

    def test_bukan_dict(self):
        _, baris = bagian_berita("rusak", "Denver Nuggets", "Chicago Bulls")
        self.assertIn("Berita tidak bisa dibaca (bentuk data tidak dikenal).", baris)

    def test_status_tidak_dikenal(self):
        _, baris = bagian_berita(
            {
                "status": "aneh",
                "items": [],
                "sources": [],
                "fetched_at": None,
                "error": None,
            },
            "Denver Nuggets",
            "Chicago Bulls",
        )
        self.assertIn("status tidak dikenal: 'aneh'", "\n".join(baris))

    def test_jam_terbit_rusak_tidak_merusak_render(self):
        _, baris = bagian_berita(
            {
                "status": "ok",
                "items": [_item("Judul", published="bukan-jam", url=None)],
                "sources": ["ESPN"],
                "fetched_at": None,
                "error": None,
            },
            "Denver Nuggets",
            "Chicago Bulls",
        )
        teks = "\n".join(baris)
        self.assertIn("Judul", teks)
        self.assertIn("(ESPN)", teks)


if __name__ == "__main__":
    unittest.main()
