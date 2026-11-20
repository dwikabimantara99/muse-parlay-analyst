"""Penarik JSON resmi Premier League (jadwal/fixtures EPL) — Tahap 2b.

Jenjang 1 (DECISIONS.md B + koreksi pasca probe 2a): JSON resmi Premier
League UTAMA untuk EPL. Endpoint PERSIS dari probes/official_leagues.py
(terverifikasi HTTP 200 + JSON, 2026-11-20)::

    https://footballapi.pulselive.com/football/fixtures
    ?comps=1&page=0&pageSize=5&sort=asc

MASALAH PAGINASI (dari evidence probe): endpoint mengembalikan SEMUA
fixtures EPL sejak 1992 (13.546 entri) terurut menaik berdasarkan kickoff,
jadi halaman 0 berisi fixtures 1992 — bukan fixtures hari ini. Modul ini
TIDAK menebak parameter baru (mis. filter musim): ia memakai parameter
halaman yang sama dari URL probe (``page``/``pageSize``/``sort``) dan
mencari halaman yang memuat fixtures di sekitar "sekarang" dengan
pencarian biner berdasarkan kickoff. Hanya fixtures dalam jendela
±``window_days`` dari sekarang yang dikembalikan, agar fixtures basi
(mis. 1992) tidak pernah tercocokkan ke laga hari ini.

Struktur fixture (dari respons probe yang tersimpan di cache probe):
``teams[0]`` = kandang, ``teams[1]`` = tandang, ``kickoff.millis`` =
kickoff (milidetik UTC), ``status`` = kode status apa adanya (mis. "C"
selesai, "U" dijadwalkan), ``gameweek.gameweek`` = pekan pertandingan.

Tidak ada ``fetch_teams()``: tidak ada endpoint tim resmi yang
terverifikasi probe — nama tim hanya muncul bersarang di dalam fixtures.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .common import (
    DiskCache,
    FetchResult,
    HttpClient,
    RateLimiter,
    default_cache_dir,
    now_iso,
    parse_json_body,
)

SOURCE = "Premier League (JSON resmi)"
TIER = 1
BASE_URL = "https://footballapi.pulselive.com/football/fixtures"

# Cache 1800 detik + jeda 1 detik antar request (kontrak 2b).
CACHE_TTL_SECONDS = 1800
MIN_GAP_SECONDS = 1.0

# Batas halaman yang diambil setelah halaman target ditemukan (pengaman
# agar satu panggilan tidak pernah mengunduh seluruh arsip).
MAX_PAGES_AFTER_TARGET = 5


def _fixtures_url(page: int, page_size: int) -> str:
    """URL satu halaman fixtures (parameter sama seperti URL probe)."""
    return f"{BASE_URL}?comps=1&page={page}&pageSize={page_size}&sort=asc"


# Satu limiter untuk SEMUA request modul ini (dibagi semua pemanggilan):
# membuat RateLimiter baru per panggilan berarti tidak ada jeda antar
# panggilan — slate memanggil fetcher berkali-kali (Kalshi: 3 series;
# Polymarket: 1x per pasar) dan API membalas 429 (teramati: Kalshi total
# EPL 429 saat demo 2b). RateLimiter.wait() melacak per host, jadi satu
# limiter aman untuk beberapa host modul ini.
_LIMITER = RateLimiter(MIN_GAP_SECONDS)


def _default_client() -> HttpClient:
    """Client default: jeda 1 detik, cache 1800 detik."""
    cache = DiskCache(default_cache_dir(), ttl_seconds=CACHE_TTL_SECONDS)
    return HttpClient(_LIMITER, cache=cache)


def parse_fixtures(payload: dict) -> list[dict]:
    """Ubah payload JSON fixtures menjadi list fixture ternormalisasi.

    Setiap fixture: ``home_team``, ``away_team``, ``kickoff`` (ISO 8601
    UTC), ``status`` (kode apa adanya dari API, bisa None), ``matchweek``
    (int, bisa None). Fixture tanpa dua tim atau tanpa kickoff dilewati
    (tidak bisa dipakai) — bukan ditebak.
    """
    fixtures: list[dict] = []
    if not isinstance(payload, dict):
        return fixtures
    for item in payload.get("content") or []:
        if not isinstance(item, dict):
            continue
        teams = item.get("teams") or []
        if len(teams) < 2:
            continue
        home = (teams[0].get("team") or {}).get("name") or (
            teams[0].get("team") or {}
        ).get("shortName")
        away = (teams[1].get("team") or {}).get("name") or (
            teams[1].get("team") or {}
        ).get("shortName")
        if not home or not away:
            continue
        kickoff = item.get("kickoff") or {}
        millis = kickoff.get("millis")
        if millis is None:
            continue
        try:
            kickoff_iso = datetime.fromtimestamp(
                float(millis) / 1000, tz=UTC
            ).isoformat()
        except (TypeError, ValueError, OverflowError):
            continue
        gameweek = item.get("gameweek") or {}
        matchweek = gameweek.get("gameweek")
        fixtures.append(
            {
                "home_team": home,
                "away_team": away,
                "kickoff": kickoff_iso,
                "status": item.get("status"),
                "matchweek": int(matchweek) if matchweek is not None else None,
            }
        )
    return fixtures


def _kickoff_range_millis(payload: dict) -> tuple[float | None, float | None]:
    """Kickoff (milidetik) paling awal & akhir di satu halaman, atau None."""
    lowest: float | None = None
    highest: float | None = None
    if not isinstance(payload, dict):
        return lowest, highest
    for item in payload.get("content") or []:
        if not isinstance(item, dict):
            continue
        millis = (item.get("kickoff") or {}).get("millis")
        if millis is None:
            continue
        try:
            value = float(millis)
        except (TypeError, ValueError):
            continue
        lowest = value if lowest is None else min(lowest, value)
        highest = value if highest is None else max(highest, value)
    return lowest, highest


def _fetch_page(
    client: HttpClient, page: int, page_size: int
) -> tuple[dict | None, str | None]:
    """Ambil satu halaman; kembalikan (payload, error)."""
    result = client.get(_fixtures_url(page, page_size))
    if result.get("status") != 200:
        return None, (
            f"http_{result.get('status')}: {result.get('error') or 'tanpa body'}"
        )
    payload = parse_json_body(result)
    if not isinstance(payload, dict):
        return None, "body_bukan_json"
    return payload, None


def fetch_fixtures(
    client: HttpClient | None = None,
    now: datetime | None = None,
    window_days: int = 7,
    page_size: int = 100,
) -> FetchResult:
    """Ambil fixtures EPL di sekitar sekarang (jendela ±``window_days``).

    Mencari halaman yang memuat fixtures masa kini dengan pencarian biner
    berdasarkan kickoff (halaman terurut menaik), lalu mengambil halaman
    itu dan halaman-halaman berikutnya sampai jendela tertutup. Mengambil
    halaman 0 saja tidak cukup: arsip dimulai dari 1992.

    ``now`` bisa di-inject (untuk tes); default jam sekarang (UTC).
    """
    fetched_at = now_iso()
    moment = now or datetime.now(UTC)
    window_start = (moment - timedelta(days=window_days)).timestamp() * 1000
    window_end = (moment + timedelta(days=window_days)).timestamp() * 1000
    http = client or _default_client()

    first_page, error = _fetch_page(http, 0, page_size)
    if error is not None:
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=False,
            error=error,
        )
    page_info = first_page.get("pageInfo") or {}
    try:
        num_pages = int(page_info.get("numPages") or 1)
    except (TypeError, ValueError):
        num_pages = 1
    pages_fetched = 1

    # Pencarian biner: halaman pertama yang kickoff akhirnya >= awal jendela.
    # Halaman kosong diperlakukan sebagai "terlalu awal" (lanjut ke kanan).
    low, high = 0, max(num_pages - 1, 0)
    target_page = high
    while low <= high:
        mid = (low + high) // 2
        if mid == 0:
            payload = first_page
        else:
            payload, error = _fetch_page(http, mid, page_size)
            pages_fetched += 1
            if error is not None:
                return FetchResult(
                    source=SOURCE,
                    tier=TIER,
                    fetched_at=fetched_at,
                    ok=False,
                    error=error,
                )
        _, highest = _kickoff_range_millis(payload)
        if highest is None or highest < window_start:
            low = mid + 1
        else:
            target_page = mid
            high = mid - 1

    # Kumpulkan halaman dari target sampai akhir jendela terlampaui.
    fixtures: list[dict] = []
    page = target_page
    collected = 0
    while page < num_pages and collected < MAX_PAGES_AFTER_TARGET:
        if page == 0:
            payload = first_page
        else:
            # Halaman target mungkin sudah diambil saat pencarian biner —
            # cache membuatnya murah untuk diambil lagi.
            payload, error = _fetch_page(http, page, page_size)
            pages_fetched += 1
            if error is not None:
                return FetchResult(
                    source=SOURCE,
                    tier=TIER,
                    fetched_at=fetched_at,
                    ok=False,
                    error=error,
                )
        lowest, _ = _kickoff_range_millis(payload)
        if lowest is not None and lowest > window_end:
            break
        fixtures.extend(parse_fixtures(payload))
        collected += 1
        page += 1

    in_window = [
        fixture
        for fixture in fixtures
        if window_start
        <= datetime.fromisoformat(fixture["kickoff"]).timestamp() * 1000
        <= window_end
    ]
    return FetchResult(
        source=SOURCE,
        tier=TIER,
        fetched_at=fetched_at,
        ok=True,
        data=in_window,
        extra={"pages_fetched": pages_fetched, "window_days": window_days},
    )


# ---------------------------------------------------------------------------
# Cedera/ketersediaan pemain — Fantasy Premier League API (bootstrap-static)
# ---------------------------------------------------------------------------
# Sumber BARU ditemukan saat integrasi 2b (koordinator, 2026-11-20): endpoint
# ESPN injuries selalu mengembalikan list kosong (bukan sumber nyata), dan
# Rotowire gratis mengabaikan filter liga — sehingga tanpa sumber ini laga
# bola selalu DATA_INCOMPLETE ("cedera: 0 sumber"). FPL API adalah produk
# resmi Premier League yang sama (fantasy.premierleague.com), gratis, tanpa
# key, terstruktur (672 pemain, 20 tim, status a/u/i/d/s — diverifikasi
# live 2026-11-20). Dicatat tier 1 dengan nama sumber "Fantasy Premier
# League API". BELUM ADA di sources.yaml v3 — butuh ratifikasi user (lihat
# laporan 2b). Hanya pemain non-"a" yang dilaporkan (pemain tersedia bukan
# cedera); kode status yang tidak dikenal diteruskan apa adanya.
FPL_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_SOURCE = "Fantasy Premier League API"
FPL_STATUS_LABELS = {
    "i": "Out",
    "d": "Doubtful",
    "s": "Suspended",
    "u": "Unavailable",
}


def parse_fpl_injuries(payload: dict) -> list[dict]:
    """Parse payload FPL bootstrap-static -> list cedera/ketersediaan.

    Murni (tanpa network). Entri: {player, team, status, detail}. ``detail``
    adalah teks news FPL + peluang main laga berikut bila ada. Baris tanpa
    nama pemain atau tanpa tim yang dikenal dilewati.
    """
    if not isinstance(payload, dict):
        return []
    teams = {
        entry["id"]: entry.get("name")
        for entry in payload.get("teams", []) or []
        if isinstance(entry, dict) and isinstance(entry.get("id"), int)
    }
    injuries: list[dict] = []
    for element in payload.get("elements", []) or []:
        if not isinstance(element, dict):
            continue
        status_code = element.get("status")
        if status_code in (None, "a"):
            continue
        first = str(element.get("first_name") or "").strip()
        second = str(element.get("second_name") or "").strip()
        name = f"{first} {second}".strip()
        team = teams.get(element.get("team"))
        if not name or not team:
            continue
        news = str(element.get("news") or "").strip()
        chance = element.get("chance_of_playing_next_round")
        detail = news
        if isinstance(chance, (int, float)):
            suffix = f"(peluang main laga berikut: {chance:g}%)"
            detail = f"{news} {suffix}".strip() if news else suffix
        injuries.append(
            {
                "player": name,
                "team": team,
                "status": FPL_STATUS_LABELS.get(status_code, str(status_code)),
                "detail": detail or None,
            }
        )
    return injuries


def fetch_injuries_fpl(
    client: HttpClient | None = None,
) -> FetchResult:
    """Tarik cedera/ketersediaan pemain EPL dari Fantasy Premier League API.

    Satu request GET (response ~1,8 MB, di-cache 30 menit). Gagal -> ok=False
    + error (``http_<status>``, ``body_bukan_json``, ``fpl_payload_kosong``).
    """
    http = client or _default_client()
    try:
        response = http.get(FPL_URL)
    except (TimeoutError, OSError, ValueError) as exc:
        return FetchResult(
            source=FPL_SOURCE,
            tier=TIER,
            fetched_at=now_iso(),
            ok=False,
            error=f"network: {type(exc).__name__}",
        )
    if response.get("status") != 200:
        return FetchResult(
            source=FPL_SOURCE,
            tier=TIER,
            fetched_at=now_iso(),
            ok=False,
            error=f"http_{response.get('status')}",
        )
    payload = parse_json_body(response)
    if payload is None:
        return FetchResult(
            source=FPL_SOURCE,
            tier=TIER,
            fetched_at=now_iso(),
            ok=False,
            error="body_bukan_json",
        )
    if not isinstance(payload, dict) or "elements" not in payload:
        return FetchResult(
            source=FPL_SOURCE,
            tier=TIER,
            fetched_at=now_iso(),
            ok=False,
            error="fpl_payload_kosong",
        )
    return FetchResult(
        source=FPL_SOURCE,
        tier=TIER,
        fetched_at=now_iso(),
        ok=True,
        data=parse_fpl_injuries(payload),
    )
