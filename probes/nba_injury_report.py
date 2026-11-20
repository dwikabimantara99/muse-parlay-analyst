"""Probe Official NBA Injury Report — Tahap 2a (muse-parlay-analyst).

DECISIONS.md D4: cari URL resmi & jadwal update-nya di nba.com dan VERIFIKASI.
Jangan mengasumsikan URL. Strategi: ambil halaman cedera nba.com, ekstrak
tautan PDF/laporan dari HTML-nya, lalu coba tautan pertama yang menjanjikan.
Kandidat tambahan: beranda official.nba.com dan widget JSON stats.nba.com.
Kalau tidak ditemukan, catat UNKNOWN + apa yang sudah dicoba.

Dijalankan sendiri: python3 probes/nba_injury_report.py
Menulis probes/out/nba_injury_report.json.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    DiskCache,
    HttpClient,
    RateLimiter,
    new_result,
    out_dir,
    write_result,
)

INJURIES_PAGE = "https://www.nba.com/injuries"
EXTRA_CANDIDATES = [
    "https://official.nba.com/",
    "https://stats.nba.com/js/data/widgets/injuries.json",
]
HREF_RE = re.compile(r'href="([^"]+)"', re.I)


def _schedule_sentences(html: str) -> list[str]:
    """Ambil kalimat jadwal update dari HTML (teks polos, tanpa script)."""
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    # Samarkan titik di "a.m."/"p.m." agar tidak memotong kalimat.
    text = text.replace("a.m.", "am").replace("p.m.", "pm")
    found: list[str] = []
    for pattern in (
        r"[^.]{0,200}continual basis[^.]{0,200}\.",
        r"[^.]{0,200}between 11 am[^.]{0,300}\.",
    ):
        for match in re.finditer(pattern, text, re.I):
            sentence = match.group(0).strip()
            if sentence and sentence not in found:
                found.append(sentence)
    return found[:3]


def probe() -> dict:
    """Jalankan probe Injury Report; kembalikan dict hasil."""
    result = new_result("Official NBA Injury Report", tier=1)
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(2.0), cache=cache)
    tried: list[str] = []

    # 1. Halaman cedera nba.com — cari tautan PDF/laporan di HTML-nya.
    resp = client.get(INJURIES_PAGE)
    tried.append(INJURIES_PAGE)
    result["requests"].append(_summarize(resp))
    body = str(resp.get("body") or "")
    pdf_links = sorted(
        {
            href
            for href in HREF_RE.findall(body)
            if "pdf" in href.lower() or "injur" in href.lower()
        }
    )
    result["links_found_on_injuries_page"] = pdf_links[:10]
    result["update_schedule_mentions"] = _schedule_sentences(body)

    # 2. Kandidat tambahan: beranda official.nba.com + widget JSON.
    extra_links: list[str] = []
    for candidate in EXTRA_CANDIDATES:
        resp = client.get(candidate)
        tried.append(candidate)
        result["requests"].append(_summarize(resp))
        cbody = str(resp.get("body") or "")
        extra_links.extend(
            href
            for href in HREF_RE.findall(cbody)
            if "pdf" in href.lower() or "injur" in href.lower()
        )
        if resp.get("status") == 200 and candidate.endswith(".json"):
            result["data_available"].append(
                "widget JSON stats.nba.com injuries.json: HTTP 200 "
                f"({len(cbody)} karakter)"
            )
    pdf_links = sorted(set(pdf_links) | set(extra_links))
    result["links_found_on_extra_pages"] = extra_links[:10]

    # 3. Utamakan tautan HALAMAN laporan cedera (mengandung "injury-report"
    # tapi bukan PDF), lalu ekstrak tautan PDF dari halaman itu. Bila tidak
    # ada halaman seperti itu, pakai tautan PDF pertama.
    pdf_url = None
    page_url = None
    page_candidates = [
        href
        for href in pdf_links
        if "injury-report" in href.lower() and ".pdf" not in href.lower()
    ]
    # Utamakan halaman musim berjalan (2026-27); bila tidak ada, pakai yang
    # terakhir (terurut alfabetis = musim terbaru).
    for href in page_candidates:
        if "2026-27" in href:
            page_url = href
            break
    if page_url is None and page_candidates:
        page_url = page_candidates[-1]
    if page_url is not None:
        if page_url.startswith("/"):
            page_url = "https://official.nba.com" + page_url
        tried.append(page_url)
        resp = client.get(page_url)
        result["requests"].append(_summarize(resp))
        result["official_report_page_url"] = page_url
        result["official_report_page_status"] = resp.get("status")
        pbody = str(resp.get("body") or "")
        page_pdf_links = [
            href for href in HREF_RE.findall(pbody) if ".pdf" in href.lower()
        ]
        result["links_found_on_report_page"] = page_pdf_links[:10]
        result["update_schedule_mentions"] = _schedule_sentences(pbody)
        # Utamakan PDF yang URL-nya mengandung "injur" (itu laporan
        # cederanya, bukan dokumen lain di sidebar halaman).
        for href in page_pdf_links:
            if "injur" in href.lower():
                pdf_url = href
                break
        if pdf_url is None and page_pdf_links:
            pdf_url = page_pdf_links[0]
    if pdf_url is None:
        for href in pdf_links:
            if ".pdf" in href.lower():
                pdf_url = href
                break
    if pdf_url is not None:
        if pdf_url.startswith("/"):
            pdf_url = "https://official.nba.com" + pdf_url
        tried.append(pdf_url)
        resp = client.get(pdf_url)
        result["requests"].append(_summarize(resp))
        content_type = (resp.get("headers") or {}).get("Content-Type", "")
        result["official_pdf_url"] = pdf_url
        result["official_pdf_status"] = resp.get("status")
        result["official_pdf_content_type"] = content_type
    else:
        result["official_pdf_url"] = None
        result["unknown"].append(
            "tidak ada tautan PDF laporan cedera di halaman yang diambil"
        )

    result["urls_tried"] = tried
    any_ok = any(r.get("status") == 200 for r in result["requests"])
    result["accessible_from_vm"] = any_ok
    result["format"] = "PDF (bila tautan ditemukan) / HTML / JSON"
    result["rate_limit"] = "UNKNOWN"
    if result.get("official_pdf_status") == 200:
        result["data_available"] = [
            "PDF Official NBA Injury Report (terverifikasi bisa diunduh)",
        ]
        result["verdict"] = "PAKAI"
    elif any_ok:
        result["verdict"] = "JANGAN"
        result["unknown"].append(
            "URL resmi PDF tidak ditemukan: nba.com/injuries 404, "
            "tidak ada tautan PDF di halaman yang diambil; "
            "jadwal update juga tidak ditemukan"
        )
    else:
        result["verdict"] = "JANGAN"
        result["unknown"].append("tidak ada kandidat yang bisa diakses")
    if not result["update_schedule_mentions"]:
        result["unknown"].append(
            "jadwal update laporan tidak ditemukan di halaman yang diambil"
        )
    result["risk_notes"] = [
        "PDF harus di-parse otomatis; format PDF bisa berubah.",
        "Cedera wajib dicek silang minimal 2 sumber (B2): ESPN + Rotowire.",
    ]
    return result


def _summarize(resp: dict) -> dict:
    """Ringkasan satu request untuk evidence (tanpa header sensitif)."""
    return {
        "url": resp.get("url"),
        "status": resp.get("status"),
        "from_cache": resp.get("from_cache"),
        "elapsed_seconds": resp.get("elapsed_seconds"),
        "rate_limit_headers": resp.get("rate_limit_headers"),
        "error": resp.get("error"),
        "body_sample": str(resp.get("body") or "")[:500],
    }


def main() -> int:
    """Jalankan probe dan tulis hasilnya; kembalikan exit code."""
    result = probe()
    path = write_result("nba_injury_report", result)
    print(f"probe nba_injury_report: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
