"""Penarik The Odds API: odds sportsbook untuk devig (Tahap 2b).

Satu panggilan per sport_key (D3: cache 30 menit, maks 2 panggilan per
analisis, region eu, Pinnacle). Bentuk respons mengikuti dokumentasi
The Odds API v4 (list event + bookmakers) — terverifikasi 1 panggilan
oleh koordinator 2026-11-20 22:54 WIB (NBA h2h eu, 9 event, Pinnacle
tersedia, 1 kredit/panggilan, sisa 499/500).

KEAMANAN: apiKey dikirim sebagai query param, jadi URL request mentah
TIDAK PERNAH masuk cache — kunci cache adalah URL TANPA apiKey, dan
hasil yang di-cache menyimpan URL yang sudah dibersihkan itu. Nilai
key tidak pernah di-print/di-log.

Kredit: header x-requests-last -> FetchResult.credits_used;
x-requests-remaining -> extra. Bila respons dari cache, credits_used = 0
(panggilan ini tidak memakai kredit) dan extra memuat from_cache=True
(angka requests_remaining di situ adalah nilai basi dari panggilan asli).

LARANGAN: modul ini tidak pernah dipanggil dari tes dengan network —
tes memakai client injeksi + fixture.
"""

from __future__ import annotations

import urllib.parse

from ingest.common import (
    DiskCache,
    FetchResult,
    HttpClient,
    RateLimiter,
    default_cache_dir,
    load_dotenv,
    now_iso,
    parse_json_body,
)

SOURCE = "The Odds API"
TIER = 2
CACHE_TTL_SECONDS = 1800  # D3: 30 menit
BASE_URL = "https://api.the-odds-api.com/v4"

# sport_key yang didukung mesin (NBA + EPL saja di Tahap 2b).
SUPPORTED_SPORTS = {"basketball_nba", "soccer_epl"}


def _request_url(sport_key: str, markets: str, regions: str, api_key: str) -> str:
    """URL request lengkap (memuat apiKey — JANGAN di-cache apa adanya)."""
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
    }
    return f"{BASE_URL}/sports/{sport_key}/odds?{urllib.parse.urlencode(params)}"


def _cache_url(sport_key: str, markets: str, regions: str) -> str:
    """URL untuk kunci cache — sama dengan URL request TANPA apiKey."""
    params = {"regions": regions, "markets": markets, "oddsFormat": "decimal"}
    return f"{BASE_URL}/sports/{sport_key}/odds?{urllib.parse.urlencode(params)}"


def _header_value(headers: dict, name: str) -> str | None:
    """Ambil header respons tanpa peduli kapitalisasi kunci."""
    for key, value in headers.items():
        if key.lower() == name.lower():
            return str(value)
    return None


def _header_int(headers: dict, name: str) -> int | None:
    """Ambil header respons sebagai int; None bila tidak ada/bukan angka."""
    value = _header_value(headers, name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _normalize_outcome(outcome: dict) -> dict | None:
    """Normalisasi satu outcome; None bila tidak ada harga desimal valid."""
    price = outcome.get("price")
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        return None
    point = outcome.get("point")
    if point is not None:
        try:
            point = float(point)
        except (TypeError, ValueError):
            point = None
    return {"name": outcome.get("name"), "price": float(price), "point": point}


def _normalize_event(event: dict) -> dict:
    """Normalisasi satu event Odds API ke bentuk slate."""
    bookmakers = []
    for book in event.get("bookmakers") or []:
        if not isinstance(book, dict):
            continue
        markets = []
        for market in book.get("markets") or []:
            if not isinstance(market, dict):
                continue
            outcomes = []
            for outcome in market.get("outcomes") or []:
                if not isinstance(outcome, dict):
                    continue
                normalized = _normalize_outcome(outcome)
                if normalized is not None:
                    outcomes.append(normalized)
            markets.append({"key": market.get("key"), "outcomes": outcomes})
        bookmakers.append(
            {"key": book.get("key"), "title": book.get("title"), "markets": markets}
        )
    return {
        "event_id": event.get("id"),
        "sport_key": event.get("sport_key"),
        "home_team": event.get("home_team"),
        "away_team": event.get("away_team"),
        "commence_time": event.get("commence_time"),
        "bookmakers": bookmakers,
    }


def _result_from_response(resp: dict, fetched_at: str, from_cache: bool) -> FetchResult:
    """Bangun FetchResult dari dict respons HttpClient (live / cache)."""
    headers = resp.get("headers") or {}
    if not isinstance(headers, dict):
        headers = {}
    credits = _header_int(headers, "x-requests-last") or 0
    remaining = _header_value(headers, "x-requests-remaining")
    extra: dict = {"from_cache": from_cache}
    if remaining is not None:
        extra["requests_remaining"] = remaining
    if resp.get("status") != 200:
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=False,
            error=(
                f"The Odds API HTTP {resp.get('status')}: "
                f"{resp.get('error') or 'tanpa keterangan'}"
            ),
            credits_used=credits,
            extra=extra,
        )
    data = parse_json_body(resp)
    if not isinstance(data, list):
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=False,
            error="respons The Odds API bukan JSON list event",
            credits_used=credits,
            extra=extra,
        )
    events = [_normalize_event(e) for e in data if isinstance(e, dict)]
    return FetchResult(
        source=SOURCE,
        tier=TIER,
        fetched_at=fetched_at,
        ok=True,
        data=events,
        # Respons cache tidak memakai kredit baru.
        credits_used=0 if from_cache else credits,
        extra={**extra, "events_returned": len(events)},
    )


# Satu limiter untuk SEMUA request modul ini (dibagi semua pemanggilan):
# membuat RateLimiter baru per panggilan berarti tidak ada jeda antar
# panggilan — slate memanggil fetcher berkali-kali (Kalshi: 3 series;
# Polymarket: 1x per pasar) dan API membalas 429 (teramati: Kalshi total
# EPL 429 saat demo 2b). RateLimiter.wait() melacak per host, jadi satu
# limiter aman untuk beberapa host modul ini.
_LIMITER = RateLimiter(2.0)


def fetch_odds(
    sport_key: str,
    markets: str = "h2h,spreads,totals",
    regions: str = "eu",
    client: HttpClient | None = None,
    api_key: str | None = None,
) -> FetchResult:
    """Tarik odds sportsbook untuk satu sport_key.

    sport_key: "basketball_nba" / "soccer_epl". markets/regions mengikuti
    parameter API (default h2h+spreads+totals, region eu). client:
    HttpClient (di-inject untuk tes; bila None, dibuat dengan cache
    30 menit). api_key: ODDS_API_KEY (untuk tes; bila None dibaca dari
    .env). Gagal -> ok=False + error, tidak melempar.
    """
    fetched_at = now_iso()
    if sport_key not in SUPPORTED_SPORTS:
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=False,
            error=f"sport_key tidak didukung: {sport_key!r} "
            f"(harus salah satu dari {sorted(SUPPORTED_SPORTS)})",
        )
    if api_key is None:
        api_key = load_dotenv().get("ODDS_API_KEY") or None
    if not api_key:
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=False,
            error="ODDS_API_KEY tidak ada di .env",
        )
    cache: DiskCache | None = None
    if client is None:
        cache = DiskCache(default_cache_dir(), CACHE_TTL_SECONDS)
        client = HttpClient(_LIMITER)
    cache_url = _cache_url(sport_key, markets, regions)
    if cache is not None:
        cached = cache.get(cache_url)
        if cached is not None:
            return _result_from_response(
                {**cached, "from_cache": True}, fetched_at, True
            )
    url = _request_url(sport_key, markets, regions, api_key)
    resp = client.get(url, use_cache=False)
    result = _result_from_response(resp, fetched_at, False)
    if cache is not None and resp.get("status") == 200:
        # Simpan hasil dengan URL TANPA apiKey (lihat _cache_url).
        cache.set(cache_url, {**resp, "url": cache_url})
    return result
