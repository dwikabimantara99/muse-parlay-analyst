"""Probe football-data.co.uk — Tahap 2a lanjutan (muse-parlay-analyst).

Cek CSV historis (hasil + odds Pinnacle) untuk liga utama. Ini untuk
KALIBRASI Tahap 3 (fit parameter simulasi dari data historis), BUKAN data
live. Maks 3 request: halaman daftar data + 1-2 file CSV contoh.

Dijalankan sendiri: python3 probes/football_data.py
Menulis probes/out/football_data.json.
"""

from __future__ import annotations

import csv
import io
import re
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

DATA_PAGE = "https://www.football-data.co.uk/data.php"
BASE = "https://www.football-data.co.uk"

# Kolom odds Pinnacle yang diharapkan (nama persis di file CSV).
PINNACLE_1X2_OPEN = ("PSH", "PSD", "PSA")
PINNACLE_1X2_CLOSE = ("PSCH", "PSCD", "PSCA")
PINNACLE_OU_OPEN = ("P>2.5", "P<2.5")


def pinnacle_columns(header: list[str]) -> dict[str, list[str]]:
    """Kelompokkan kolom odds Pinnacle yang ada di header CSV."""
    found = {
        "1x2_open": [c for c in PINNACLE_1X2_OPEN if c in header],
        "1x2_close": [c for c in PINNACLE_1X2_CLOSE if c in header],
        "over_under_2_5": [c for c in PINNACLE_OU_OPEN if c in header],
    }
    return found


def parse_csv_sample(text: str) -> dict:
    """Parse teks CSV: header, jumlah baris data, kolom, contoh baris."""
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return {"header": [], "n_rows": 0, "columns": [], "sample_row": None}
    header = [h.strip() for h in rows[0]]
    data_rows = [r for r in rows[1:] if r and any(c.strip() for c in r)]
    sample = None
    if data_rows:
        sample = {
            header[i]: data_rows[0][i]
            for i in range(min(len(header), len(data_rows[0])))
        }
    return {
        "header": header,
        "n_rows": len(data_rows),
        "columns": header,
        "sample_row": sample,
    }


def _csv_links_from_data_page(html: str) -> list[str]:
    """Ekstrak tautan .csv dari halaman data.php (href relatif/absolut)."""
    hrefs = re.findall(r'href="([^"]+\.csv[^"]*)"', html, flags=re.I)
    seen: list[str] = []
    for href in hrefs:
        if href not in seen:
            seen.append(href)
    return seen


def leagues_from_data_page(html: str) -> list[str]:
    """Ekstrak daftar liga dari teks halaman data.php.

    Halaman ini menautkan file CSV lewat halaman per negara ("Country
    Links"), bukan tautan .csv langsung — jadi daftar liga diambil dari
    teks ("England Football Results", dst.). Hanya nama negara yang
    tercatat; kode file (E0, D1, ...) TIDAK ditebak dari sini.
    """
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    leagues: list[str] = []
    for line in text.splitlines():
        match = re.match(r"(.+?) Football Results$", line.strip())
        if match and match.group(1) not in leagues:
            leagues.append(match.group(1))
    return leagues


def probe() -> dict:
    """Jalankan probe football-data.co.uk; kembalikan dict hasil."""
    result = new_result("football-data.co.uk (CSV historis)", tier=2)
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(2.0), cache=cache)

    # 1. Halaman daftar data.
    resp = client.get(DATA_PAGE)
    result["requests"].append(_summarize(resp))
    html = str(resp.get("body") or "")
    links = _csv_links_from_data_page(html) if resp.get("status") == 200 else []
    result["csv_links_found"] = len(links)
    result["csv_link_samples"] = links[:10]
    # Daftar liga dari teks halaman (tautan CSV ada di halaman per negara).
    result["leagues_listed"] = (
        leagues_from_data_page(html) if resp.get("status") == 200 else []
    )
    result["coverage_claim"] = (
        "32 seasons results | 27 seasons betting odds | 27 seasons match "
        "stats; hingga 22 divisi liga Eropa sejak 1993/94; odds sejak "
        "2000/01; 16 divisi non-Eropa sejak 2012/13 (klaim halaman data.php)"
        if resp.get("status") == 200
        else None
    )

    # Pilih 2 CSV contoh: EPL musim berjalan + EPL musim lalu (bila tautan
    # ditemukan di halaman; kalau tidak, pola URL standar mmz4281/<musim>/).
    # Musim berjalan 2025/26 = "2526", musim lalu 2024/25 = "2425".
    chosen: list[str] = []
    for link in links:
        if re.search(r"2526/E0\.csv$", link) or re.search(r"2425/E0\.csv$", link):
            chosen.append(link)
    if not chosen:
        # Pola URL standar situs ini (akan diverifikasi lewat status HTTP).
        chosen = ["mmz4281/2526/E0.csv", "mmz4281/2425/E0.csv"]
        result["unknown"].append(
            "tautan CSV tidak ada di data.php (tautan file ada di halaman "
            "per negara) — memakai pola URL standar mmz4281/<musim>/E0.csv "
            "(diverifikasi lewat HTTP 200); pola ini baru terverifikasi "
            "untuk E0, liga lain belum diunduh"
        )
    files: list[dict] = []
    for link in chosen[:2]:
        url = link if link.startswith("http") else f"{BASE}/{link.lstrip('/')}"
        resp = client.get(url)
        result["requests"].append(_summarize(resp))
        entry: dict = {
            "url": url,
            "status": resp.get("status"),
            "bytes": len(str(resp.get("body") or "").encode("utf-8")),
        }
        if resp.get("status") == 200:
            parsed = parse_csv_sample(str(resp.get("body") or ""))
            entry["n_rows"] = parsed["n_rows"]
            entry["n_columns"] = len(parsed["header"])
            entry["pinnacle_columns"] = pinnacle_columns(parsed["header"])
            entry["has_pinnacle_1x2"] = bool(entry["pinnacle_columns"]["1x2_open"])
            entry["has_pinnacle_ou"] = bool(entry["pinnacle_columns"]["over_under_2_5"])
            entry["sample_row"] = parsed["sample_row"]
            # Hitung berapa baris yang punya odds Pinnacle 1X2 lengkap.
            header = parsed["header"]
            idx = [header.index(c) for c in PINNACLE_1X2_OPEN if c in header]
            if len(idx) == 3:
                reader = csv.reader(io.StringIO(str(resp.get("body") or "")))
                rows = list(reader)[1:]
                complete = sum(
                    1
                    for r in rows
                    if len(r) > max(idx) and all(r[i].strip() for i in idx)
                )
                entry["rows_with_pinnacle_1x2"] = complete
        files.append(entry)
    result["files"] = files

    ok_files = [f for f in files if f.get("status") == 200]
    with_pinnacle = [f for f in ok_files if f.get("has_pinnacle_1x2")]
    result["accessible_from_vm"] = bool(ok_files)
    result["format"] = "CSV" if ok_files else None
    result["rate_limit"] = "UNKNOWN (tidak ada header rate limit yang terlihat)"
    if with_pinnacle:
        result["data_available"] = [
            f"{len(ok_files)} file CSV terunduh, {len(with_pinnacle)} "
            "dengan kolom odds Pinnacle 1X2",
            "kolom Pinnacle: PSH/PSD/PSA (open), PSCH/PSCD/PSCA (close), "
            "P>2.5/P<2.5 (over/under) — bila ada di file (lihat files)",
            "dipakai untuk kalibrasi Tahap 3 (fit parameter dari 2-3 musim "
            "histori), BUKAN data live",
        ]
        result["verdict"] = "PAKAI"
    elif ok_files:
        result["verdict"] = "CADANGAN"
        result["unknown"].append("CSV terunduh tapi tanpa kolom Pinnacle")
    else:
        result["verdict"] = "JANGAN"
        result["unknown"].append("tidak ada file CSV yang berhasil diunduh")
    result["risk_notes"] = [
        "Data historis saja — musim berjalan belum lengkap (baris tanpa "
        "odds = laga yang belum dimainkan); kalibrasi Tahap 3 memakai "
        "musim yang sudah selesai.",
        "PERINGATAN PINNACLE (dari halaman data.php): sejak 23/07/2025 API "
        "publik Pinnacle tidak andal sehingga odds Pinnacle di situs ini "
        "'systematically out of date' dan 'should be used with caution' — "
        "kalibrasi Tahap 3 sebaiknya memakai odds Pinnacle dari musim "
        "selesai SEBELUM 23/07/2025 (mis. 2024/25) atau memvalidasi dulu.",
        "KETENTUAN PAKAI (data.php): data 'intended for private individuals "
        "only, NOT commercial or data training products using automated "
        "bots/scrapers/AI' — pemakaian untuk proyek pribadi ini perlu "
        "diputuskan user (seperti FotMob, tapi klausanya tentang produk "
        "komersial/AI, bukan larangan mutlak pengambilan otomatis).",
        "Situs ini gratis tapi tanpa API resmi — URL file bisa berubah; "
        "fetcher kalibrasi harus memvalidasi header sebelum memakai.",
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
    path = write_result("football_data", result)
    print(f"probe football_data: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
