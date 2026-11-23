"""Probe Google News RSS sebagai cadangan berita NBA — modul news.

RSS publik tanpa kunci, kueri per tim. Maks 1 request.

Dijalankan sendiri: python3 probes/probe_news_google.py
Menulis probes/out/probe_news_google.json.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
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

# Kueri contoh: satu tim (Thunder) — membuktikan pencarian per tim.
URL_RSS = (
    "https://news.google.com/rss/search"
    "?q=Oklahoma%20City%20Thunder%20NBA&hl=en-US&gl=US&ceid=US:en"
)


def probe() -> dict:
    """Jalankan probe Google News RSS; kembalikan dict hasil."""
    result = new_result("Google News RSS", tier=3)
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(2.0), cache=cache)

    resp = client.get(URL_RSS)
    result["requests"].append(_summarize(resp))
    body = str(resp.get("body") or "")
    items: list[dict] = []
    if resp.get("status") == 200 and body:
        try:
            root = ET.fromstring(body)
            for item in root.findall(".//item"):
                items.append(
                    {
                        "title": item.findtext("title"),
                        "pubDate": item.findtext("pubDate"),
                        "source": (
                            item.find("source").text
                            if item.find("source") is not None
                            else None
                        ),
                    }
                )
        except ET.ParseError as exc:
            result["unknown"].append(f"RSS tidak bisa di-parse: {exc}")
    if items:
        result["data_available"].append(f"RSS kueri Thunder: {len(items)} item")
        contoh = items[0]
        result["data_available"].append(
            "contoh: " + str(contoh.get("title"))[:120] + f" ({contoh.get('source')})"
        )
        sumber = sorted({str(i.get("source")) for i in items if i.get("source")})
        result["data_available"].append(
            f"penerbit terwakili: {len(sumber)} (mis. " + ", ".join(sumber[:5]) + ")"
        )

    result["accessible_from_vm"] = bool(items)
    result["format"] = "RSS XML" if items else None
    result["rate_limit"] = "UNKNOWN (tidak ada header rate limit yang terlihat)"
    for req in result["requests"]:
        headers = req.get("rate_limit_headers") or {}
        if headers:
            result["rate_limit"] = f"header: {headers}"
    if items:
        result["verdict"] = "CADANGAN"
        result["risk_notes"].append(
            "Agregator (bukan sumber primer): judul + penerbit + tanggal "
            "saja; ringkasan berupa cuplikan HTML, bukan teks bersih."
        )
        result["risk_notes"].append(
            "Kueri per tim = 1 request per tim per laga (2 request per "
            "laga); feed liga ESPN hanya 1 request untuk semua laga."
        )
        result["risk_notes"].append(
            "Tidak dipakai sekarang — hanya dicatat sebagai cadangan bila "
            "ESPN gagal di masa depan."
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
    path = write_result("probe_news_google", result)
    print(f"probe news google: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
