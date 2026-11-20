"""Probe Understat xG — Tahap 2a (muse-parlay-analyst).

Jenjang 2: xG 5 liga top Eropa. Understat tidak punya API publik resmi;
data tertanam sebagai JSON di dalam halaman HTML. Maks 2 request.

Dijalankan sendiri: python3 probes/understat.py
Menulis probes/out/understat.json.
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
    "https://understat.com/league/EPL/2025",
    "https://understat.com/league/La_liga/2025",
]


def probe() -> dict:
    """Jalankan probe Understat; kembalikan dict hasil."""
    result = new_result("Understat (xG)", tier=2)
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(3.0), cache=cache)
    ok_count = 0
    maintenance = False
    for url in URLS:
        resp = client.get(url)
        result["requests"].append(_summarize(resp))
        if resp.get("status") == 200:
            body = str(resp.get("body") or "")
            if "We will come back soon" in body:
                # Halaman maintenance (HTTP 200 tapi bukan data).
                maintenance = True
                result["data_available"].append(
                    f"{url.split('/')[-2]}/{url.split('/')[-1]}: "
                    "halaman maintenance 'We will come back soon'"
                )
                continue
            ok_count += 1
            markers = [m for m in ("teamsData", "datesData", "xG") if m in body]
            result["data_available"].append(
                f"{url.split('/')[-2]}/{url.split('/')[-1]}: "
                f"HTML {len(body)} karakter, "
                f"penanda JSON tertanam: {markers or 'tidak ada'}"
            )
    result["accessible_from_vm"] = ok_count > 0
    result["format"] = "HTML + JSON tertanam" if ok_count > 0 else None
    result["rate_limit"] = "UNKNOWN (tidak ada header rate limit yang terlihat)"
    if maintenance and ok_count == 0:
        result["verdict"] = "JANGAN"
        result["unknown"].append(
            "situs sedang maintenance saat probe (2026-11-20) — perlu "
            "dicek ulang di 2b; status bisa berubah"
        )
    elif ok_count == len(URLS):
        result["verdict"] = "PAKAI"
    elif ok_count > 0:
        result["verdict"] = "CADANGAN"
        result["unknown"].append("sebagian halaman gagal (lihat requests)")
    else:
        result["verdict"] = "JANGAN"
    result["risk_notes"] = [
        "Tidak ada API resmi: parsing JSON tertanam di HTML, rapuh bila "
        "format halaman berubah; butuh tes kesehatan scraper.",
        "Hanya 5 liga top Eropa; liga lain butuh sumber lain.",
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
    path = write_result("understat", result)
    print(f"probe understat: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
