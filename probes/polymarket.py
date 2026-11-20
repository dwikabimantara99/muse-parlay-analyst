"""Probe API publik Polymarket — Tahap 2a (muse-parlay-analyst).

Tanpa key. Maks 3 request: Gamma events, Gamma markets, CLOB markets.

Dijalankan sendiri: python3 probes/polymarket.py
Menulis probes/out/polymarket.json.
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
    parse_json_body,
    write_result,
)

URLS = [
    "https://gamma-api.polymarket.com/events?limit=5&active=true",
    "https://gamma-api.polymarket.com/markets?limit=5&active=true",
    "https://clob.polymarket.com/markets?limit=5",
]


def probe() -> dict:
    """Jalankan probe Polymarket; kembalikan dict hasil."""
    result = new_result("Polymarket API", tier=2)
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(2.0), cache=cache)
    ok_count = 0
    for url in URLS:
        resp = client.get(url)
        result["requests"].append(_summarize(resp))
        if resp.get("status") == 200:
            ok_count += 1
            data = parse_json_body(resp)
            if isinstance(data, list) and data:
                result["data_available"].append(
                    f"{url.split('/')[2]}{url.split('?')[0].split('.com')[1]}: "
                    f"{len(data)} item, kunci contoh: "
                    f"{sorted(data[0].keys())[:8]}"
                )
    result["accessible_from_vm"] = ok_count > 0
    result["format"] = "JSON REST" if ok_count > 0 else None
    result["rate_limit"] = "UNKNOWN (tidak ada header rate limit yang terlihat)"
    for req in result["requests"]:
        headers = req.get("rate_limit_headers") or {}
        if headers:
            result["rate_limit"] = f"header: {headers}"
    if ok_count == len(URLS):
        result["verdict"] = "PAKAI"
    elif ok_count > 0:
        result["verdict"] = "CADANGAN"
        result["unknown"].append("sebagian endpoint gagal (lihat requests)")
    else:
        result["verdict"] = "JANGAN"
    result["risk_notes"] = [
        "Pembanding independen (P2): hanya dipakai bila provider asal pasar "
        "jup.ag BUKAN polymarket.",
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
    path = write_result("polymarket", result)
    print(f"probe polymarket: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
