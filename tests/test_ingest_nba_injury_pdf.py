"""Tes ingest/nba_injury_pdf.py — TANPA network (mock + fixture sintetis).

Fixture PDF minimal dibangun di sini (stdlib saja): satu content stream
FlateDecode berisi operator Tj/TJ dengan koordinat Td, meniru bentuk
output GemBox.Document pada PDF asli (lihat docstring modul).
"""

import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import nba_injury_pdf
from ingest.common import DiskCache


def build_pdf(content_streams: list[bytes]) -> bytes:
    """Bangun PDF minimal dari list content stream (sudah FlateDecode).

    Parser modul tidak memakai xref, jadi fixture tidak butuh xref valid
    — cukup header %PDF- + objek stream.
    """
    parts = [b"%PDF-1.4\n"]
    for i, raw in enumerate(content_streams, start=1):
        compressed = zlib.compress(raw)
        header = (
            f"{i} 0 obj\n<< /Length {len(compressed)} "
            "/Filter /FlateDecode >>\nstream\n"
        ).encode("ascii")
        parts.append(header + compressed + b"\nendstream\nendobj\n")
    parts.append(b"%%EOF\n")
    return b"".join(parts)


# Content stream meniru satu halaman laporan: judul, header kolom,
# dua tim (blok), satu alasan yang membungkus ke 3 baris, footer halaman.
# Pitch baris 22 poin; bungkus berjarak 7 poin (seperti PDF asli).
SAMPLE_CONTENT = b"""BT /F0 22 Tf 288 62 Td (Injury) Tj 66 0 Td (Report:) Tj 82 0 Td (11/20/26) Tj ET
BT /F0 10 Tf 23 115 Td (Game) Tj 30 0 Td (Date) Tj 60 0 Td (Team) Tj 80 0 Td (Player) Tj 60 0 Td (Name) Tj 90 0 Td (Current) Tj 50 0 Td (Status) Tj 60 0 Td (Reason) Tj ET
BT /F0 10 Tf 23 136 Td (11/20/2026) Tj 90 0 Td (CHA@ATL) Tj 80 0 Td (Charlotte) Tj 70 0 Td (Hornets) Tj 80 0 Td (Ajayi,) Tj 50 0 Td (Michael) Tj 60 0 Td (Out) Tj 40 0 Td (G) Tj 15 0 Td (League) Tj 45 0 Td (-) Tj 15 0 Td (Two-) Tj 35 0 Td (Way) Tj ET
BT /F0 10 Tf 300 158 Td (Allen,) Tj 50 0 Td (Grayson) Tj 60 0 Td (Out) Tj 40 0 Td (Concussion) Tj 80 0 Td (Protocol) Tj ET
BT /F0 10 Tf 560 180 Td (Injury/Illness) Tj 90 0 Td (-) Tj 15 0 Td (Right) Tj 40 0 Td (Hamstring) Tj ET
BT /F0 10 Tf 300 187 Td (Williams,) Tj 60 0 Td (Grant) Tj 50 0 Td (Out) Tj ET
BT /F0 10 Tf 560 194 Td (Injury) Tj ET
BT /F0 10 Tf 23 224 Td (Atlanta) Tj 60 0 Td (Hawks) Tj 60 0 Td (Landale,) Tj 60 0 Td (Jock) Tj 50 0 Td (Out) Tj 40 0 Td (Injury/Illness) Tj 90 0 Td (-) Tj 15 0 Td (Right) Tj 40 0 Td (Great) Tj 40 0 Td (Toe) Tj 30 0 Td (Sprain) Tj ET
BT /F0 10 Tf 300 246 Td (Udeh) Tj 40 0 Td (Jr.,) Tj 35 0 Td (Ernest) Tj 55 0 Td (Questionable) Tj 80 0 Td (G) Tj 15 0 Td (League) Tj 45 0 Td (-) Tj 15 0 Td (Two-) Tj 35 0 Td (Way) Tj ET
BT /F1 10 Tf 398 545 Td (Page) Tj 22 0 Td (1) Tj 7 0 Td (of) Tj 11 0 Td (7) Tj ET
"""

SAMPLE_TEXT = """Injury Report: 11/20/26
Game Date Team Player Name Current Status Reason
11/20/2026 CHA@ATL Charlotte Hornets Ajayi, Michael Out G League - Two-Way
Allen, Grayson Out Concussion protocol
Williams, Grant Out Injury/Illness - Right Hamstring Injury
Atlanta Hawks Landale, Jock Out Injury/Illness - Right Great Toe Sprain
Udeh Jr., Ernest Questionable G League - Two-Way
Page 1 of 7
"""


class FakeClient:
    """Client palsu untuk halaman laporan (cache di direktori sementara)."""

    def __init__(self, page_body: str, status: int = 200) -> None:
        self.page_body = page_body
        self.status = status
        self.urls_requested: list[str] = []
        self.cache: DiskCache | None = None
        self._tmpdir = tempfile.TemporaryDirectory()
        self.cache = DiskCache(Path(self._tmpdir.name) / "cache", 900)

    def get(self, url: str, use_cache: bool = True) -> dict:
        """Kembalikan halaman laporan yang sudah disiapkan."""
        self.urls_requested.append(url)
        return {"status": self.status, "body": self.page_body, "error": None}

    def close(self) -> None:
        """Bersihkan direktori sementara."""
        self._tmpdir.cleanup()


class TestParsePdfText(unittest.TestCase):
    def test_pdf_sintetis_diekstrak_per_baris(self):
        text = nba_injury_pdf.parse_pdf_text(build_pdf([SAMPLE_CONTENT]))
        lines = text.splitlines()
        self.assertEqual(lines[0], "Injury Report: 11/20/26")
        self.assertIn("Charlotte Hornets Ajayi, Michael Out", text)
        # Fragmen "Two-" + "Way" digabung tanpa spasi -> "Two-Way".
        self.assertIn("G League - Two-Way", text)
        # Baris yang membungkus (3 fragmen y 180/187/194) jadi SATU baris.
        # (Urutan kata di dalam baris bisa sedikit bergeser karena fragmen
        # diurutkan per x — semua kata tetap ada.)
        wrapped = [line for line in lines if "Williams, Grant" in line]
        self.assertEqual(len(wrapped), 1)
        for word in ("Out", "Injury/Illness", "Right", "Hamstring", "Injury"):
            self.assertIn(word, wrapped[0])
        self.assertIn("Page 1 of 7", lines[-1])

    def test_bukan_pdf(self):
        with self.assertRaises(ValueError) as ctx:
            nba_injury_pdf.parse_pdf_text(b"hello world")
        self.assertIn("pdf_parse_failed", str(ctx.exception))

    def test_pdf_tanpa_stream_flate(self):
        with self.assertRaises(ValueError) as ctx:
            nba_injury_pdf.parse_pdf_text(b"%PDF-1.4\n%%EOF\n")
        self.assertIn("pdf_parse_failed", str(ctx.exception))

    def test_operator_tj_array_dan_hex(self):
        content = (
            b"BT /F0 10 Tf 100 700 Td [(Hello) 20 (World)] TJ ET\n"
            b"BT /F0 10 Tf 100 722 Td <48656C6C6F> Tj ET\n"
        )
        text = nba_injury_pdf.parse_pdf_text(build_pdf([content]))
        self.assertEqual(text.splitlines(), ["HelloWorld", "Hello"])

    def test_escape_string(self):
        content = rb"BT /F0 10 Tf 100 700 Td (Nae\051Qwan) Tj ET" + b"\n"
        # \051 oktal = ')' ; teks jadi "Nae)Qwan" — escape ditangani.
        text = nba_injury_pdf.parse_pdf_text(build_pdf([content]))
        self.assertEqual(text, "Nae)Qwan")

    def test_dua_halaman_berurutan(self):
        page1 = b"BT /F0 10 Tf 100 700 Td (PageOne) Tj ET\n"
        page2 = b"BT /F0 10 Tf 100 700 Td (PageTwo) Tj ET\n"
        text = nba_injury_pdf.parse_pdf_text(build_pdf([page1, page2]))
        self.assertEqual(text.splitlines(), ["PageOne", "PageTwo"])


class TestParseInjuries(unittest.TestCase):
    def test_parse_contoh_lengkap(self):
        injuries = nba_injury_pdf.parse_injuries(SAMPLE_TEXT)
        self.assertEqual(len(injuries), 5)
        first = injuries[0]
        self.assertEqual(first["player"], "Michael Ajayi")
        self.assertEqual(first["team"], "Charlotte Hornets")
        self.assertEqual(first["status"], "Out")
        self.assertEqual(first["detail"], "G League - Two-Way")
        # Tim dilacak dari blok: baris ke-2/3 tetap Charlotte Hornets.
        self.assertEqual(injuries[1]["player"], "Grayson Allen")
        self.assertEqual(injuries[1]["team"], "Charlotte Hornets")
        self.assertEqual(injuries[1]["detail"], "Concussion protocol")
        self.assertEqual(injuries[2]["player"], "Grant Williams")
        self.assertEqual(injuries[2]["team"], "Charlotte Hornets")
        # Blok tim baru: Atlanta Hawks.
        self.assertEqual(injuries[3]["player"], "Jock Landale")
        self.assertEqual(injuries[3]["team"], "Atlanta Hawks")
        self.assertEqual(
            injuries[3]["detail"], "Injury/Illness - Right Great Toe Sprain"
        )
        # Sufiks nama "Jr." ikut ke nama belakang.
        self.assertEqual(injuries[4]["player"], "Ernest Udeh Jr.")
        self.assertEqual(injuries[4]["status"], "Questionable")

    def test_baris_lanjutan_ditempel_ke_detail(self):
        text = (
            "Charlotte Hornets Ajayi, Michael Out Injury/Illness -\n"
            "Left Hamstring Strain\n"
        )
        injuries = nba_injury_pdf.parse_injuries(text)
        self.assertEqual(len(injuries), 1)
        self.assertEqual(
            injuries[0]["detail"], "Injury/Illness - Left Hamstring Strain"
        )

    def test_tim_tidak_dikenal_jadi_unknown(self):
        injuries = nba_injury_pdf.parse_injuries("Smith, John Out Knee Sprain\n")
        self.assertEqual(injuries[0]["team"], "UNKNOWN")
        self.assertEqual(injuries[0]["player"], "John Smith")

    def test_status_tidak_dikenal_jadi_unknown(self):
        injuries = nba_injury_pdf.parse_injuries(
            "Atlanta Hawks Smith, John Left Knee Sprain\n"
        )
        self.assertEqual(injuries[0]["status"], "UNKNOWN")

    def test_header_dan_footer_dilewati(self):
        text = (
            "Injury Report: 11/20/26 12:00 AM\n"
            "Game Date Game Time Matchup Team Player Name Current Status Reason\n"
            "Page 1 of 7\n"
        )
        self.assertEqual(nba_injury_pdf.parse_injuries(text), [])

    def test_teks_kosong(self):
        self.assertEqual(nba_injury_pdf.parse_injuries(""), [])


class TestFetchReport(unittest.TestCase):
    def test_fetch_lewat_tautan_halaman(self):
        page = (
            '<html><a href="https://ak-static.cms.nba.com/referee/injury/'
            'Injury-Report_2026-11-20_12_00AM.pdf">12:00 AM</a>'
            '<a href="https://ak-static.cms.nba.com/referee/injury/'
            'Injury-Report_2026-11-20_01_15PM.pdf">1:15 PM</a></html>'
        )
        client = FakeClient(page)
        pdf_bytes = build_pdf([SAMPLE_CONTENT])
        try:
            with mock.patch.object(
                nba_injury_pdf,
                "_download_pdf_bytes",
                return_value=(200, pdf_bytes, None),
            ) as download:
                result = nba_injury_pdf.fetch_report("2026-11-20", client=client)
            # Tautan terbaru hari itu (1:15 PM) yang dipakai, bukan 12:00 AM.
            self.assertIn("01_15PM.pdf", download.call_args[0][0])
            self.assertTrue(result.ok)
            self.assertEqual(result.source, "Official NBA Injury Report")
            self.assertEqual(result.tier, 1)
            self.assertEqual(len(result.data), 5)
            self.assertEqual(result.data[0]["player"], "Michael Ajayi")
            self.assertEqual(result.extra["n_injuries"], 5)
            self.assertFalse(result.extra["from_cache"])
        finally:
            client.close()

    def test_fetch_fallback_12am_bila_halaman_gagal(self):
        client = FakeClient("", status=500)
        pdf_bytes = build_pdf([SAMPLE_CONTENT])
        try:
            with mock.patch.object(
                nba_injury_pdf,
                "_download_pdf_bytes",
                return_value=(200, pdf_bytes, None),
            ) as download:
                result = nba_injury_pdf.fetch_report("2026-11-20", client=client)
            self.assertIn(
                "Injury-Report_2026-11-20_12_00AM.pdf", download.call_args[0][0]
            )
            self.assertTrue(result.ok)
            self.assertIsNotNone(result.extra["page_error"])
        finally:
            client.close()

    def test_fetch_pdf_gagal(self):
        client = FakeClient("")
        try:
            with mock.patch.object(
                nba_injury_pdf,
                "_download_pdf_bytes",
                return_value=(404, None, "HTTP 404"),
            ):
                result = nba_injury_pdf.fetch_report("2026-11-20", client=client)
            self.assertFalse(result.ok)
            self.assertIn("pdf_http_404", result.error or "")
        finally:
            client.close()

    def test_fetch_pdf_tidak_bisa_diparse(self):
        client = FakeClient("")
        try:
            with mock.patch.object(
                nba_injury_pdf,
                "_download_pdf_bytes",
                return_value=(200, b"bukan pdf sama sekali", None),
            ):
                result = nba_injury_pdf.fetch_report("2026-11-20", client=client)
            self.assertFalse(result.ok)
            self.assertIn("pdf_parse_failed", result.error or "")
        finally:
            client.close()

    def test_fetch_tanggal_tidak_valid(self):
        result = nba_injury_pdf.fetch_report("20-11-2026", client=FakeClient(""))
        self.assertFalse(result.ok)
        self.assertIn("tanggal_tidak_valid", result.error or "")

    def test_fetch_cache_kedua_tidak_unduh_ulang(self):
        client = FakeClient("")
        pdf_bytes = build_pdf([SAMPLE_CONTENT])
        try:
            with mock.patch.object(
                nba_injury_pdf,
                "_download_pdf_bytes",
                return_value=(200, pdf_bytes, None),
            ) as download:
                first = nba_injury_pdf.fetch_report("2026-11-20", client=client)
                second = nba_injury_pdf.fetch_report("2026-11-20", client=client)
            self.assertTrue(first.ok)
            self.assertTrue(second.ok)
            self.assertTrue(second.extra["from_cache"])
            self.assertEqual(download.call_count, 1)
            self.assertEqual(len(second.data), 5)
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
