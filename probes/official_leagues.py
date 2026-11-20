"""Probe data resmi liga sepak bola — Tahap 2a (muse-parlay-analyst).

Jenjang 1: SATU script, enam pengecekan (satu request per liga) untuk
mencari endpoint JSON publik masing-masing liga. Yang tidak ada dicatat
apa adanya (bukan ditebak).

Dijalankan sendiri: python3 probes/official_leagues.py
Menulis probes/out/official_leagues.json.
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

# Satu URL kandidat per liga + URL coba-ulang (beranda) bila kandidat pertama
# gagal. Kandidat dipilih dari endpoint yang dikenal publik; hasil
# 404/non-JSON dicatat apa adanya, bukan kegagalan probe.
LEAGUES = [
    (
        "Premier League",
        "https://footballapi.pulselive.com/football/fixtures"
        "?comps=1&page=0&pageSize=5&sort=asc",
        None,
    ),
    (
        "UEFA",
        "https://www.uefa.com/uefachampionsleague/fixtures/",
        "https://www.uefa.com/uefachampionsleague/",
    ),
    (
        "LaLiga",
        "https://www.laliga.com/en-GB/matches/laliga-ea-sports",
        "https://www.laliga.com/en-GB",
    ),
    (
        "Serie A",
        "https://www.legaseriea.it/en/serie-a/fixtures",
        "https://www.legaseriea.it/en",
    ),
    (
        "Bundesliga",
        "https://www.bundesliga.com/en/bundesliga/matches",
        None,
    ),
    (
        "Ligue 1",
        "https://www.ligue1.com/matches",
        "https://www.ligue1.com/",
    ),
]


def probe() -> dict:
    """Jalankan probe enam liga resmi; kembalikan dict hasil."""
    result = new_result("Situs/data resmi liga (bola)", tier=1)
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(2.0), cache=cache)
    per_league: dict[str, dict] = {}
    json_found = 0
    reachable = 0
    for name, url, retry_url in LEAGUES:
        resp = client.get(url)
        result["requests"].append(_summarize(resp, name))
        status = resp.get("status")
        body = str(resp.get("body") or "")
        tried_url = url
        # Bila kandidat pertama gagal, coba sekali lagi dengan beranda liga.
        if status != 200 and retry_url is not None:
            resp = client.get(retry_url)
            result["requests"].append(_summarize(resp, name))
            status = resp.get("status")
            body = str(resp.get("body") or "")
            tried_url = retry_url
        is_json = parse_json_body(resp) is not None
        if status == 200:
            reachable += 1
        if status == 200 and is_json:
            json_found += 1
        content_type = (resp.get("headers") or {}).get("Content-Type", "")
        per_league[name] = {
            "url": tried_url,
            "first_url": url,
            "status": status,
            "content_type": content_type,
            "is_json": bool(is_json),
            "body_chars": len(body),
            "has_next_data": "__NEXT_DATA__" in body,
            "error": resp.get("error"),
        }
        if status == 200 and is_json:
            result["data_available"].append(
                f"{name}: endpoint JSON publik terverifikasi"
            )
        elif status == 200:
            result["data_available"].append(
                f"{name}: halaman terjangkau, format {content_type or 'UNKNOWN'} "
                "(bukan JSON langsung)"
            )
    result["per_league"] = per_league
    result["accessible_from_vm"] = reachable > 0
    result["format"] = "campuran: JSON (bila ada) + HTML" if reachable > 0 else None
    result["rate_limit"] = "UNKNOWN (tidak ada header rate limit yang terlihat)"
    if json_found >= 3:
        result["verdict"] = "PAKAI"
    elif reachable > 0:
        result["verdict"] = "CADANGAN"
        result["unknown"].append(
            f"hanya {json_found}/6 liga dengan endpoint JSON terverifikasi; "
            "sisanya perlu penelusuran lanjutan di 2b (atau pakai jenjang 2)"
        )
    else:
        result["verdict"] = "JANGAN"
    result["risk_notes"] = [
        "Situs resmi liga umumnya tidak menyediakan API JSON publik yang "
        "stabil; halaman HTML/JS berat dan bisa berubah.",
        "xG resmi hampir tidak ada — rantai xG tetap Understat → "
        "Sofascore/FotMob (B4).",
    ]
    return result


def _summarize(resp: dict, name: str) -> dict:
    """Ringkasan satu request untuk evidence (tanpa header sensitif)."""
    return {
        "league": name,
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
    path = write_result("official_leagues", result)
    print(f"probe official_leagues: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
