"""Probe ESPN JSON publik — Tahap 2a (muse-parlay-analyst).

Jenjang 2: NBA (skor/jadwal), sepak bola, dan cedera NBA. Maks 3 request.

Dijalankan sendiri: python3 probes/espn.py
Menulis probes/out/espn.json.
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
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard",
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries",
]


def probe() -> dict:
    """Jalankan probe ESPN; kembalikan dict hasil."""
    result = new_result("ESPN JSON publik", tier=2)
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(2.0), cache=cache)
    ok_count = 0
    for url in URLS:
        resp = client.get(url)
        result["requests"].append(_summarize(resp))
        if resp.get("status") == 200:
            ok_count += 1
            data = parse_json_body(resp)
            if isinstance(data, dict):
                events = data.get("events")
                injuries = data.get("injuries")
                detail = ""
                if isinstance(events, list):
                    detail = f"{len(events)} event"
                elif isinstance(injuries, list):
                    detail = f"{len(injuries)} tim dengan cedera"
                result["data_available"].append(
                    f"{url.split('/sports/')[1]}: JSON"
                    + (f", {detail}" if detail else "")
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
    path = write_result("espn", result)
    print(f"probe espn: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
