"""Probe FotMob — Tahap 2a (muse-parlay-analyst).

Jenjang 2: statistik/xG/lineup bola via API tidak resmi FotMob.
Base URL saat ini: https://www.fotmob.com/api/data/ (path /api/ lama
mengembalikan 404 — terverifikasi di probe pertama, 2026-11-20).
Maks 2 request: laga hari ini + liga EPL (id 47).

Dijalankan sendiri: python3 probes/fotmob.py
Menulis probes/out/fotmob.json.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
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


def probe() -> dict:
    """Jalankan probe FotMob; kembalikan dict hasil."""
    result = new_result("FotMob", tier=2)
    today = datetime.now(UTC).strftime("%Y%m%d")
    urls = [
        f"https://www.fotmob.com/api/data/matches?date={today}",
        "https://www.fotmob.com/api/data/leagues?id=47",
    ]
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(3.0), cache=cache)
    ok_count = 0
    for url in urls:
        resp = client.get(url)
        result["requests"].append(_summarize(resp))
        if resp.get("status") == 200:
            ok_count += 1
            data = parse_json_body(resp)
            if isinstance(data, dict):
                leagues = data.get("leagues")
                detail = ""
                if isinstance(leagues, list):
                    detail = f"{len(leagues)} liga"
                result["data_available"].append(
                    f"{url.split('/api/')[1][:40]}: JSON"
                    + (f", {detail}" if detail else "")
                    + f", kunci atas: {sorted(data.keys())[:8]}"
                )
    result["accessible_from_vm"] = ok_count > 0
    result["format"] = "JSON REST (API tidak resmi)" if ok_count > 0 else None
    result["rate_limit"] = "UNKNOWN (tidak ada header rate limit yang terlihat)"
    for req in result["requests"]:
        headers = req.get("rate_limit_headers") or {}
        if headers:
            result["rate_limit"] = f"header: {headers}"
    if ok_count == len(urls):
        result["verdict"] = "PAKAI"
    elif ok_count > 0:
        result["verdict"] = "CADANGAN"
        result["unknown"].append("sebagian endpoint gagal (lihat requests)")
    else:
        result["verdict"] = "JANGAN"
    result["risk_notes"] = [
        "API tidak resmi/tidak didokumentasikan: bisa berubah atau diblokir "
        "tanpa pemberitahuan; butuh tes kesehatan.",
        "Ketentuan FotMob melarang pengambilan otomatis tanpa izin — "
        "pemakaian perlu diputuskan user (risiko ToS).",
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
    path = write_result("fotmob", result)
    print(f"probe fotmob: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
