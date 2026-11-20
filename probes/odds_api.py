"""Probe The Odds API — Tahap 2a (muse-parlay-analyst).

TIDAK ADA key (ODDS_API_KEY belum disediakan user). Probe ini HANYA
memastikan endpoint terjangkau dan mencatat bahwa key dibutuhkan
(ekspektasi 401 tanpa key). JANGAN mengarang key.

Dijalankan sendiri: python3 probes/odds_api.py
Menulis probes/out/odds_api.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    DiskCache,
    HttpClient,
    RateLimiter,
    load_dotenv,
    new_result,
    out_dir,
    repo_root,
    write_result,
)

URLS = [
    "https://api.the-odds-api.com/v4/sports/",
    "https://api.the-odds-api.com/v4/sports/basketball_nba/odds?regions=eu",
]


def probe() -> dict:
    """Jalankan probe The Odds API; kembalikan dict hasil."""
    result = new_result("The Odds API", tier=2)
    env = load_dotenv(repo_root())
    key_present = bool(env.get("ODDS_API_KEY"))
    result["api_key_present"] = key_present
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(2.0), cache=cache)
    saw_401 = False
    reachable = False
    for url in URLS:
        resp = client.get(url)
        result["requests"].append(_summarize(resp))
        status = resp.get("status")
        if status is not None:
            reachable = True
        if status == 401:
            saw_401 = True
    result["accessible_from_vm"] = reachable
    result["format"] = "JSON REST (butuh key)"
    result["rate_limit"] = (
        "450 kredit/bulan, peringatan 80% (DECISIONS.md D3) — "
        "belum bisa diverifikasi tanpa key"
    )
    if key_present:
        result["unknown"].append("key ada di .env tapi probe ini tidak memakainya")
    if saw_401:
        result["data_available"] = ["endpoint terjangkau; key dibutuhkan (401)"]
        result["verdict"] = "CADANGAN"
        result["risk_notes"] = [
            "Butuh ODDS_API_KEY dari user sebelum bisa dipakai (D3).",
            "1 panggilan bisa makan beberapa kredit; cache 30 menit, "
            "maks 2 panggilan per analisis.",
        ]
    elif reachable:
        result["verdict"] = "CADANGAN"
        result["unknown"].append("respons bukan 401 — lihat requests")
    else:
        result["verdict"] = "JANGAN"
        result["unknown"].append("endpoint tidak terjangkau dari VM")
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
    path = write_result("odds_api", result)
    print(f"probe odds_api: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
