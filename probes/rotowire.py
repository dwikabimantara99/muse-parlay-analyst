"""Probe Rotowire cedera NBA — Tahap 2a (muse-parlay-analyst).

Jenjang 2 (cadangan cedera). Scraping HTML dengan jeda sopan. Maks 2 request.

Dijalankan sendiri: python3 probes/rotowire.py
Menulis probes/out/rotowire.json.
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
    "https://www.rotowire.com/basketball/injury-report.php",
    "https://www.rotowire.com/basketball/tables/injury-report.php",
]


def probe() -> dict:
    """Jalankan probe Rotowire; kembalikan dict hasil."""
    result = new_result("Rotowire (cedera NBA)", tier=2)
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(3.0), cache=cache)
    ok_count = 0
    for url in URLS:
        resp = client.get(url)
        result["requests"].append(_summarize(resp))
        if resp.get("status") == 200:
            ok_count += 1
            body = str(resp.get("body") or "")
            markers = [m for m in ("Out", "Questionable", "Doubtful") if m in body]
            result["data_available"].append(
                f"{url.split('/')[-1]}: {len(body)} karakter, "
                f"penanda status cedera: {markers or 'tidak ada'}"
            )
    result["accessible_from_vm"] = ok_count > 0
    result["format"] = "HTML (scraping)" if ok_count > 0 else None
    result["rate_limit"] = "UNKNOWN (tidak ada header rate limit yang terlihat)"
    if ok_count == len(URLS):
        result["verdict"] = "PAKAI"
    elif ok_count > 0:
        result["verdict"] = "CADANGAN"
        result["unknown"].append("sebagian halaman gagal (lihat requests)")
    else:
        result["verdict"] = "JANGAN"
    result["risk_notes"] = [
        "Scraping HTML: format bisa berubah; butuh tes kesehatan scraper.",
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
    path = write_result("rotowire", result)
    print(f"probe rotowire: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
