"""Probe berita NBA dari ESPN JSON publik — modul news.

Endpoint liga (site.api.espn.com) + endpoint per-tim (diduga).
Maks 3 request.

Dijalankan sendiri: python3 probes/probe_news_espn.py
Menulis probes/out/probe_news_espn.json.
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

# Endpoint berita liga NBA (limit 5: cukup untuk membuktikan bentuk).
URL_LIGA = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news?limit=5"
# Endpoint per-tim (diduga dari pola injuries/scoreboard; dibuktikan di sini).
# ID 25 = Oklahoma City Thunder (dari scoreboard 2026-11-24).
URL_TIM = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/25/news?limit=3"
)
# Limit besar: membuktikan parameter limit dihormati + rentang umur feed.
URL_LIMIT = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news?limit=50"


def probe() -> dict:
    """Jalankan probe berita ESPN; kembalikan dict hasil."""
    result = new_result("ESPN NBA news (site.api.espn.com)", tier=2)
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(2.0), cache=cache)

    resp_liga = client.get(URL_LIGA)
    result["requests"].append(_summarize(resp_liga))
    data_liga = parse_json_body(resp_liga) if resp_liga.get("status") == 200 else None
    artikel_liga = data_liga.get("articles") if isinstance(data_liga, dict) else None
    if isinstance(artikel_liga, list) and artikel_liga:
        result["data_available"].append(
            f"news liga: {len(artikel_liga)} artikel (limit=5)"
        )
        contoh = artikel_liga[0]
        result["data_available"].append("contoh: " + str(contoh.get("headline"))[:120])
        kategori = contoh.get("categories") or []
        jenis_kategori = sorted(
            {str(c.get("type")) for c in kategori if isinstance(c, dict)}
        )
        result["data_available"].append(
            "kategori artikel: " + ", ".join(jenis_kategori)
        )
        tim = [
            c.get("description")
            for c in kategori
            if isinstance(c, dict) and c.get("type") == "team"
        ]
        result["data_available"].append(
            "tim di kategori contoh: " + (", ".join(str(t) for t in tim) or "tidak ada")
        )

    resp_tim = client.get(URL_TIM)
    result["requests"].append(_summarize(resp_tim))
    data_tim = parse_json_body(resp_tim) if resp_tim.get("status") == 200 else None
    if isinstance(data_tim, dict) and isinstance(data_tim.get("articles"), list):
        result["data_available"].append(
            f"news per-tim (OKC): {len(data_tim['articles'])} artikel"
        )
    else:
        result["unknown"].append(
            "endpoint per-tim mengembalikan "
            f"status {resp_tim.get('status')} tanpa daftar artikel "
            "(body kosong di probe ini) — filter per-tim harus dilakukan "
            "di sisi klien dari feed liga"
        )

    resp_limit = client.get(URL_LIMIT)
    result["requests"].append(_summarize(resp_limit))
    data_limit = (
        parse_json_body(resp_limit) if resp_limit.get("status") == 200 else None
    )
    artikel_limit = data_limit.get("articles") if isinstance(data_limit, dict) else None
    if isinstance(artikel_limit, list) and artikel_limit:
        terbit = sorted(
            str(a.get("published")) for a in artikel_limit if a.get("published")
        )
        result["data_available"].append(
            f"news liga limit=50: {len(artikel_limit)} artikel, "
            f"terbit {terbit[0][:10]} s.d. {terbit[-1][:10]}"
            if terbit
            else f"news liga limit=50: {len(artikel_limit)} artikel"
        )
        from collections import Counter

        jenis = Counter(str(a.get("type")) for a in artikel_limit)
        result["data_available"].append(
            "jenis artikel limit=50: "
            + ", ".join(f"{k} {v}" for k, v in sorted(jenis.items()))
        )

    result["accessible_from_vm"] = isinstance(artikel_liga, list) and bool(artikel_liga)
    result["format"] = "JSON REST" if result["accessible_from_vm"] else None
    result["rate_limit"] = "UNKNOWN (tidak ada header rate limit yang terlihat)"
    for req in result["requests"]:
        headers = req.get("rate_limit_headers") or {}
        if headers:
            result["rate_limit"] = f"header: {headers}"
    if result["accessible_from_vm"]:
        result["verdict"] = "PAKAI"
        result["risk_notes"].append(
            "Artikel tipe 'Media' adalah sorotan video (judul tetap "
            "informatif, tapi bukan teks berita)."
        )
        result["risk_notes"].append(
            "Bahasa Inggris — laporan menampilkan judul asli + "
            "penjelasan Indonesia (tidak diterjemahkan mesin)."
        )
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
    path = write_result("probe_news_espn", result)
    print(f"probe news espn: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
