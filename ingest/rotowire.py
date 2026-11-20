"""Penarik Rotowire: cedera NBA (jenjang 2, cadangan).

TEMUAN STRUKTUR (terverifikasi dari cache probe 2a + panggilan live
2026-11-20): halaman utama injury-report.php TIDAK memuat data pemain di
HTML-nya — tabel dimuat lewat JavaScript dari endpoint data halaman itu
sendiri, /basketball/tables/injury-report.php?team=ALL&pos=ALL, yang
mengembalikan JSON (kolom: player, firstname, lastname, team, position,
injury, status, rDate). Fetcher ini memanggil endpoint data itu langsung
(GET biasa, parameter yang sama dengan yang dipakai halaman) — bukan
menebak API lain. Penanda "Out" yang ditemukan probe di HTML halaman
utama berasal dari teks navigasi/FAQ, BUKAN data cedera, jadi tidak
dipakai sebagai tes kesehatan.

BATAS PAYWALL (terverifikasi live 2026-11-20): endpoint gratis hanya
mengembalikan segelintir pemain (5 baris saat itu) — halaman sendiri
menyatakan "We've only included a handful of injured players above. Log
in ... to see all injured players." Kolom rDate selalu
"<i>Subscribers Only</i>" untuk akun gratis. Karena itu Rotowire hanya
sumber cek-silang parsial; jumlah baris dicatat di extra["n_rows"] agar
pemanggil tahu cakupannya, bukan mengira daftar lengkap.
"""

from __future__ import annotations

import re

from ingest.common import (
    DiskCache,
    FetchResult,
    HttpClient,
    RateLimiter,
    default_cache_dir,
    now_iso,
    parse_json_body,
)

SOURCE = "Rotowire"
TIER = 2
CACHE_TTL_SECONDS = 900
RATE_GAP_SECONDS = 2.0

# Endpoint data tabel cedera (dipakai halaman injury-report.php sendiri).
TABLES_URL = (
    "https://www.rotowire.com/basketball/tables/injury-report.php" "?team=ALL&pos=ALL"
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


# Satu limiter untuk SEMUA request modul ini (dibagi semua pemanggilan):
# membuat RateLimiter baru per panggilan berarti tidak ada jeda antar
# panggilan — slate memanggil fetcher berkali-kali (Kalshi: 3 series;
# Polymarket: 1x per pasar) dan API membalas 429 (teramati: Kalshi total
# EPL 429 saat demo 2b). RateLimiter.wait() melacak per host, jadi satu
# limiter aman untuk beberapa host modul ini.
_LIMITER = RateLimiter(RATE_GAP_SECONDS)


def _default_client() -> HttpClient:
    """Buat HttpClient default (jeda 2 dtk, cache 900 dtk)."""
    return HttpClient(
        _LIMITER,
        cache=DiskCache(default_cache_dir(), CACHE_TTL_SECONDS),
    )


def parse_injury_rows(payload: object) -> list[dict]:
    """Ubah payload JSON endpoint tabel Rotowire jadi list cedera.

    Setiap entri: {player, team, status, detail}. detail = nama cedera
    (kolom injury); tanggal perkiraan kembali ditambahkan bila tersedia
    (kolom rDate gratis selalu "Subscribers Only" sehingga tidak
    ditambahkan). ValueError("rotowire_format_changed") bila payload
    bukan list JSON dengan kolom yang diharapkan (tes kesehatan scraper).
    """
    if not isinstance(payload, list):
        raise ValueError("rotowire_format_changed")
    injuries = []
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError("rotowire_format_changed")
        player = row.get("player")
        if not player:
            first = row.get("firstname") or ""
            last = row.get("lastname") or ""
            player = f"{first} {last}".strip() or None
        team = row.get("team")
        status = row.get("status")
        if not player or not team or not status:
            raise ValueError("rotowire_format_changed")
        detail = row.get("injury") or None
        return_date = row.get("rDate")
        if isinstance(return_date, str):
            return_date = _HTML_TAG_RE.sub("", return_date).strip()
            if return_date and "Subscribers Only" not in return_date:
                detail = (
                    f"{detail}; est. return {return_date}"
                    if detail
                    else (f"est. return {return_date}")
                )
        injuries.append(
            {
                "player": player,
                "team": team,
                "status": status,
                "detail": detail,
            }
        )
    return injuries


def fetch_injuries(client: HttpClient | None = None) -> FetchResult:
    """Ambil daftar cedera NBA dari Rotowire (endpoint tabel JSON).

    data: list cedera {player, team, status, detail}. CATATAN: versi
    gratis hanya mengembalikan segelintir pemain (paywall) — lihat
    docstring modul dan extra["n_rows"]. Fetch/format gagal -> ok=False
    dengan error (tidak melempar).
    """
    fetched_at = now_iso()
    resp = (client or _default_client()).get(TABLES_URL)
    if resp.get("status") != 200:
        return FetchResult(
            SOURCE,
            TIER,
            fetched_at,
            False,
            error=f"http_{resp.get('status')}: {resp.get('error') or 'rotowire gagal'}",
        )
    payload = parse_json_body(resp)
    try:
        injuries = parse_injury_rows(payload)
    except ValueError as exc:
        return FetchResult(SOURCE, TIER, fetched_at, False, error=str(exc))
    return FetchResult(
        SOURCE,
        TIER,
        fetched_at,
        True,
        data=injuries,
        extra={
            "n_rows": len(injuries),
            "paywall_note": (
                "Rotowire gratis hanya menampilkan segelintir pemain "
                "(pesan paywall di halaman utama); daftar ini parsial, "
                "bukan daftar cedera lengkap."
            ),
        },
    )
