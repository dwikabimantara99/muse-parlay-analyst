"""Probe nba.com / stats.nba.com — Tahap 2a (muse-parlay-analyst).

Jenjang 1 (resmi): jadwal, statistik, live data NBA. Maks 3 request:
scoreboard hari ini (CDN), klasemen (stats.nba.com), scoreboard v2.
stats.nba.com dikenal sering memblokir IP cloud — dicatat apa adanya.

Dijalankan sendiri: python3 probes/nba_com.py
Menulis probes/out/nba_com.json.
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

# Header yang biasa dipakai klien stats.nba.com (tanpa kredensial).
STATS_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
}

URLS = [
    (
        "https://cdn.nba.com/static/json/liveData/scoreboard/"
        "todaysScoreboard_00.json",
        None,
    ),
    (
        "https://stats.nba.com/stats/leaguestandingsv3?LeagueID=00"
        "&Season=2025-26&SeasonType=Regular%20Season",
        STATS_HEADERS,
    ),
    (
        "https://stats.nba.com/stats/scoreboardv2?GameDate=11/20/2026"
        "&LeagueID=00&DayOffset=0",
        STATS_HEADERS,
    ),
]


def probe() -> dict:
    """Jalankan probe nba.com; kembalikan dict hasil."""
    result = new_result("nba.com / stats.nba.com", tier=1)
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    ok_count = 0
    for url, extra in URLS:
        client = HttpClient(RateLimiter(2.0), cache=cache, extra_headers=extra or {})
        resp = client.get(url)
        result["requests"].append(_summarize(resp))
        if resp.get("status") == 200:
            ok_count += 1
            data = parse_json_body(resp)
            if isinstance(data, dict):
                result["data_available"].append(
                    f"{url.split('.com/')[1][:60]}: JSON, "
                    f"kunci atas: {sorted(data.keys())[:8]}"
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
        "stats.nba.com dikenal memblokir IP cloud/server — bila gagal, "
        "ESPN (jenjang 2) jadi utama untuk jadwal/statistik.",
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
    path = write_result("nba_com", result)
    print(f"probe nba_com: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
