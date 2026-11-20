"""Probe cek ulang Understat — Tahap 2a lanjutan (muse-parlay-analyst).

Apakah Understat masih maintenance (probe 2a, 2026-11-20)? Request FRESH
(tanpa cache) agar statusnya benar-benar saat ini, bukan status lama.

Untuk pengecekan harian otomatis, pakai probes/check_understat.py (1 request
ringan, menulis probes/out/understat_status.json + health log).

Dijalankan sendiri: python3 probes/understat_recheck.py
Menulis probes/out/understat_recheck.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_understat import classify_status
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
    """Jalankan cek ulang Understat; kembalikan dict hasil."""
    result = new_result("Understat (cek ulang)", tier=2)
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(3.0), cache=cache)
    statuses: list[str] = []
    for url in URLS:
        # use_cache=False: recheck harus segar, bukan status lama.
        resp = client.get(url, use_cache=False)
        result["requests"].append(_summarize(resp))
        body = str(resp.get("body") or "")
        status = classify_status(resp.get("status"), body, resp.get("error"))
        statuses.append(status)
        league = f"{url.split('/')[-2]}/{url.split('/')[-1]}"
        markers = [m for m in ("teamsData", "datesData", "xG") if m in body]
        result["data_available"].append(
            f"{league}: status={status}, HTTP {resp.get('status')}, "
            f"{len(body)} karakter, penanda JSON tertanam: {markers or 'tidak ada'}"
        )
    result["statuses"] = statuses
    result["accessible_from_vm"] = "up" in statuses
    result["format"] = "HTML + JSON tertanam" if "up" in statuses else None
    result["rate_limit"] = "UNKNOWN (tidak ada header rate limit yang terlihat)"
    if all(s == "up" for s in statuses):
        result["verdict"] = "PAKAI"
        result["risk_notes"] = [
            "Understat KEMBALI — fetcher 2b boleh mengaktifkan lagi rantai "
            "xG (lihat check_understat.py untuk mekanisme harian).",
        ]
    elif "maintenance" in statuses and "up" not in statuses:
        result["verdict"] = "JANGAN"
        result["unknown"].append(
            "situs masih maintenance saat cek ulang — rantai xG tetap "
            "putus, aturan B4 (TANPA_XG) tetap berlaku; cek harian "
            "otomatis (check_understat.py) akan mendeteksi bila kembali"
        )
    elif "up" in statuses:
        result["verdict"] = "CADANGAN"
        result["unknown"].append("sebagian liga up, sebagian tidak")
    else:
        result["verdict"] = "JANGAN"
        result["unknown"].append("status tidak dapat dipastikan (lihat requests)")
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
    path = write_result("understat_recheck", result)
    print(f"probe understat_recheck: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
