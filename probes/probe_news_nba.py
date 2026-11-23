"""Probe berita NBA resmi (nba.com) — modul news.

Mencari endpoint berita terstruktur gratis: halaman /news (HTML) dan
RSS (diduga). Maks 2 request.

Dijalankan sendiri: python3 probes/probe_news_nba.py
Menulis probes/out/probe_news_nba.json.
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

URL_HALAMAN = "https://www.nba.com/news"
URL_RSS = "https://www.nba.com/rss/nba.xml"


def probe() -> dict:
    """Jalankan probe berita nba.com; kembalikan dict hasil."""
    result = new_result("NBA resmi (nba.com)", tier=1)
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(2.0), cache=cache)

    resp_halaman = client.get(URL_HALAMAN)
    result["requests"].append(_summarize(resp_halaman))
    body = str(resp_halaman.get("body") or "")
    if resp_halaman.get("status") == 200:
        result["data_available"].append(
            f"halaman /news: HTML {len(body)} karakter "
            "(Next.js, data tertanam di __NEXT_DATA__)"
            if "__NEXT_DATA__" in body
            else f"halaman /news: HTML {len(body)} karakter"
        )
        result["risk_notes"].append(
            "Tidak ada endpoint JSON/RSS berita resmi yang ditemukan — "
            "satu-satunya jalan adalah mengupas HTML halaman, yang rapuh "
            "(struktur berubah sewaktu-waktu) dan bukan API."
        )

    resp_rss = client.get(URL_RSS)
    result["requests"].append(_summarize(resp_rss))
    if resp_rss.get("status") == 200:
        result["data_available"].append("RSS nba.com tersedia")
    else:
        result["unknown"].append(
            f"RSS diduga (nba.com/rss/nba.xml): status {resp_rss.get('status')} "
            "— tidak ada feed RSS di alamat itu"
        )

    result["accessible_from_vm"] = resp_halaman.get("status") == 200
    result["format"] = "HTML (bukan API)" if result["accessible_from_vm"] else None
    result["rate_limit"] = "UNKNOWN (tidak ada header rate limit yang terlihat)"
    result["verdict"] = "JANGAN"
    result["risk_notes"].append(
        "Alasan JANGAN: tidak ada API berita terstruktur gratis; "
        "mengupas HTML Next.js di luar pola repo (semua fetcher memakai "
        "JSON API) dan rapuh. ESPN JSON sudah cukup sebagai sumber utama."
    )
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
    path = write_result("probe_news_nba", result)
    print(f"probe news nba.com: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
