"""Probe Basketball-Reference — Tahap 2a (muse-parlay-analyst).

Jenjang 2: statistik tim/pemain NBA (BPM, menit, on/off). Scraping HTML
dengan jeda sopan (BBRef dikenal membatasi request agresif). Maks 2 request.

Dijalankan sendiri: python3 probes/bbref.py
Menulis probes/out/bbref.json.
"""

from __future__ import annotations

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

URLS = [
    "https://www.basketball-reference.com/leagues/NBA_2026_standings.html",
    "https://www.basketball-reference.com/leagues/NBA_2026_advanced.html",
]


def probe() -> dict:
    """Jalankan probe Basketball-Reference; kembalikan dict hasil."""
    result = new_result("Basketball-Reference", tier=2)
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(4.0), cache=cache)
    ok_count = 0
    for url in URLS:
        resp = client.get(url)
        result["requests"].append(_summarize(resp))
        if resp.get("status") == 200:
            ok_count += 1
            body = str(resp.get("body") or "")
            markers = [m for m in ("BPM", "MP", "On/Off") if m in body]
            result["data_available"].append(
                f"{url.split('/')[-1]}: HTML {len(body)} karakter, "
                f"penanda ditemukan: {markers or 'tidak ada'}"
            )
    result["accessible_from_vm"] = ok_count > 0
    result["format"] = "HTML (scraping)" if ok_count > 0 else None
    result["rate_limit"] = (
        "Tidak dipublikasikan; BBRef dikenal membatasi request agresif "
        "(probe memakai jeda 4 dtk)"
    )
    if ok_count == len(URLS):
        result["verdict"] = "PAKAI"
    elif ok_count > 0:
        result["verdict"] = "CADANGAN"
        result["unknown"].append("sebagian halaman gagal (lihat requests)")
    else:
        result["verdict"] = "JANGAN"
    result["risk_notes"] = [
        "Scraping HTML: format bisa berubah; butuh tes kesehatan scraper.",
        "Patuhi batas situs: jeda antar request, cache agresif.",
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
    path = write_result("bbref", result)
    print(f"probe bbref: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
