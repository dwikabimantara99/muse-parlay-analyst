"""Penarik Jupiter Prediction API: harga ¢ jup.ag (Tahap 2b).

Slate pasar sports dari GET /events (category=sports). Harga Yes/No
dibaca dari field `pricing` tiap pasar — nama field ini DIVERIFIKASI
dari payload asli di probes/out/cache/ (100 event, 5.720 pasar):

- `pricing.buyYesPriceUsd` — harga BELI Yes (ask), micro-USD.
- `pricing.sellYesPriceUsd` — harga JUAL Yes (bid), micro-USD.
- `pricing.buyNoPriceUsd` / `pricing.sellNoPriceUsd` — sisi No.
- 1 ¢ = 10.000 micro-USD. Nilai 0 berarti TIDAK ADA kuotasi (teramati:
  sisi No pasar 2-outcome selalu 0) dan dinormalisasi jadi None.

Harga yang dipakai sebagai yes_price_cents/no_price_cents adalah harga
BELI (ask) — harga yang dibayar user, konsisten dengan rumus EV (D7)
dan definisi jup_markup di probe (harga beli jup.ag vs midpoint).

Konvensi kandang/tandang dari judul event, DIVERIFIKASI melawan
scoreboard ESPN (cache probe 2a/2a-lanjutan): NBA "A vs. B" = A tandang,
B kandang (6/6 laga); bola "A vs. B" = A kandang, B tandang (7/7 laga
EPL). Olahraga lain: home_team/away_team = None (konvensi tidak
diverifikasi, tidak ditebak).

PAGINASI (diverifikasi live 2026-11-20): GET /events memakai window
`start`/`end` + `limit` (maks 100 — limit=200 ditolak HTTP 400 "Too
big: expected number to be <=100"); respons membawa
`pagination: {start, end, hasNext}`. Parameter `offset` DIABAIKAN
server. fetch_sports_markets memindai SEMUA halaman sampai hasNext
false atau safety cap tercapai.

TRANSPORT (temuan 2026-11-20, BUKAN bug modul ini): urllib memaksa
header `Connection: close` (urllib/request.py) dan kombinasi itu
dengan egress proxy VM ini memotong respons api.jup.ag ~50-70% dari
waktu (IncompleteRead/RemoteDisconnected; curl tanpa header itu 12/12
berhasil, dan uji CONNECT manual: tanpa header 6/6, dengan header 1/6).
Perbaikan permanen ada di ingest/common.py (di luar file ini) — modul
ini hanya me-retry tiap halaman sampai 8x sebagai mitigasi. Jangan
menghapus retry sebelum transport diperbaiki.
"""

from __future__ import annotations

import http.client
import time
import urllib.error
from datetime import UTC, datetime

from ingest.common import (
    DiskCache,
    FetchResult,
    JupiterClient,
    default_cache_dir,
    load_dotenv,
    now_iso,
    parse_json_body,
)
from ingest.matching import parse_vs_title

SOURCE = "Jupiter Prediction API"
TIER = 1
CACHE_TTL_SECONDS = 300

# Paginasi /events: ukuran halaman maksimum yang diterima API (100),
# safety cap total event per pemindaian, dan retry per halaman (mitigasi
# transport yang memotong respons — lihat docstring modul).
# Cap 10000: pindai 2026-11-20 menemukan API punya >2000 event sports
# (cap lama 2000 memotong pindaian — scan_complete=False); hasNext tetap
# mengakhiri pindaian begitu halaman habis, jadi cap hanya mengikat bila
# API benar-benar melewati 10000 event.
PAGE_SIZE = 100
MAX_EVENTS_DEFAULT = 10000
MAX_ATTEMPTS_PER_PAGE = 8
_RETRY_DELAYS = (1.0, 2.0, 4.0, 8.0, 8.0, 8.0, 8.0)

# Subcategory Jupiter yang dianggap sepak bola (di-port dari probe
# kalshi_sports + "mls"/"afc" yang teramati di slate jup.ag).
SOCCER_SUBCATEGORIES = {
    "epl",
    "lal",
    "bun",
    "fl1",
    "ucl",
    "unl",
    "bra",
    "mex",
    "tur",
    "spl",
    "chfa",
    "idn1",
    "idn2",
    "fr2",
    "qat1",
    "uzb1",
    "uae1",
    "isp",
    "nor",
    "ukr1",
    "clf",
    "mls",
    "afc",
}

_MICRO_USD_PER_CENT = 10000


def classify_sport(subcategory: str | None) -> str:
    """Klasifikasikan subcategory Jupiter jadi "nba"/"football"/"other"."""
    if subcategory == "nba":
        return "nba"
    if subcategory in SOCCER_SUBCATEGORIES:
        return "football"
    return "other"


def _price_cents(micro_usd: object) -> float | None:
    """Ubah harga micro-USD jadi ¢; None bila bukan angka/0/di luar 0-100¢."""
    if isinstance(micro_usd, bool) or not isinstance(micro_usd, (int, float)):
        return None
    if micro_usd <= 0 or micro_usd > 100 * _MICRO_USD_PER_CENT:
        return None
    return micro_usd / _MICRO_USD_PER_CENT


def _line_float(value: object) -> float | None:
    """Ubah sportsLine (string '2.5' / angka / None) jadi float."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _spread_line(market: dict) -> float | None:
    """Garis spread UNTUK TIM judul pasar (bukan garis pasar mentah).

    ``sportsLine`` adalah garis PASAR — garis untuk tim PERTAMA di
    ``outcomes`` (tim yang namanya dipakai pasar spread itu). Tiap garis
    punya DUA pasar (satu per tim sebagai favorit): pasar tim
    outcomes[0] memakai garis apa adanya (negatif = favorit), pasar tim
    outcomes[1] adalah sisi cover dan garisnya DIBALIK tandanya
    (positif). Tanpa pembalikan, dua pasar berbeda (mis. "Arsenal -2.5"
    19¢ dan "Arsenal +2.5" 99¢) jatuh ke kunci slate yang sama dan harga
    cover dibandingkan dengan pembanding -2.5 (bug demo 2b). Bila
    outcomes tidak bisa dibaca / judul tidak ada di outcomes, garis
    dipakai apa adanya (fail-open ke perilaku lama).
    """
    line = _line_float(market.get("sportsLine"))
    if line is None:
        return None
    outcomes = market.get("outcomes")
    title = market.get("title")
    if (
        isinstance(outcomes, list)
        and len(outcomes) >= 2
        and title is not None
        and str(outcomes[1]) == str(title)
        and str(outcomes[0]) != str(title)
    ):
        return -line
    return line


def _start_time_iso(event: dict) -> str | None:
    """Jam mulai event (beginAt epoch-detik) -> ISO UTC.

    None bila beginAt tidak ada / bukan angka. Dipakai slate untuk
    membedakan dua laga pasangan tim yang sama (malam ini vs rematch
    minggu depan) — tanpa ini, pasar laga yang salah bisa terpilih.
    """
    begin_at = event.get("beginAt")
    if begin_at is None:
        return None
    try:
        timestamp = float(begin_at)
    except (TypeError, ValueError):
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _home_away(event_title: str | None, sport: str) -> tuple[str | None, str | None]:
    """Kandang/tandang dari judul event (konvensi per olahraga, terverifikasi).

    NBA: "A vs. B" -> A tandang, B kandang. Bola: "A vs. B" -> A kandang,
    B tandang. Olahraga lain / judul bukan vs: (None, None).
    """
    parsed = parse_vs_title(event_title or "")
    if parsed is None:
        return (None, None)
    first, second = parsed
    if sport == "nba":
        return (second, first)
    if sport == "football":
        return (first, second)
    return (None, None)


def _normalize_market(event: dict, market: dict) -> dict:
    """Normalisasi satu pasar jup.ag mentah ke bentuk slate.

    ``clobTokenIds``/``outcomes`` diteruskan mentah (nama kunci asli
    API, sengaja bukan snake_case): polymarket.find_token_for_jup_market
    memakainya untuk memilih token Yes TANPA network (jalur 1); tanpa
    keduanya, setiap pasar memicu 1 pencarian Gamma. Kedua kunci ini
    internal — tidak masuk output slate.
    """
    metadata = event.get("metadata") or {}
    event_title = metadata.get("title")
    sport = classify_sport(event.get("subcategory"))
    home_team, away_team = _home_away(event_title, sport)
    pricing = market.get("pricing") or {}
    market_type = market.get("sportsMarketType")
    line = (
        _spread_line(market)
        if market_type == "spreads"
        else _line_float(market.get("sportsLine"))
    )
    return {
        "event_id": event.get("eventId"),
        "event_title": event_title,
        "market_id": market.get("marketId"),
        "market_type": market_type,
        "line": line,
        "provider": market.get("provider"),
        "outcome": market.get("title"),
        "yes_price_cents": _price_cents(pricing.get("buyYesPriceUsd")),
        "no_price_cents": _price_cents(pricing.get("buyNoPriceUsd")),
        "home_team": home_team,
        "away_team": away_team,
        "sport": sport,
        "league": metadata.get("league"),
        "start_time": _start_time_iso(event),
        "clobTokenIds": market.get("clobTokenIds"),
        "outcomes": market.get("outcomes"),
    }


def _get_page_with_retry(
    client: JupiterClient, params: dict[str, str]
) -> tuple[dict, int]:
    """GET satu halaman /events dengan retry atas kegagalan transport.

    Me-retry IncompleteRead/RemoteDisconnected (exception dari
    http.client yang tidak ditangkap JupiterClient) dan respons dengan
    status None (kegagalan transport yang ditangkap client). HTTP error
    (4xx/5xx) TIDAK di-retry — langsung dikembalikan. ValueError dari
    JupiterClient (path tidak diizinkan) juga tidak di-retry.

    Mengembalikan (hasil, jumlah_percobaan) — jumlah percobaan dicatat
    di extra pemindaian (observabilitas transport: bila banyak halaman
    butuh >1 percobaan, transport masih bermasalah).
    """
    last_error: str | None = None
    for attempt in range(MAX_ATTEMPTS_PER_PAGE):
        try:
            result = client.get("/events", params)
        except (http.client.HTTPException, urllib.error.URLError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            result = None
        if result is not None and result.get("status") is not None:
            return result, attempt + 1
        if result is not None:
            last_error = str(result.get("error") or "status None tanpa keterangan")
        if attempt < MAX_ATTEMPTS_PER_PAGE - 1:
            time.sleep(_RETRY_DELAYS[attempt])
    return (
        {
            "status": None,
            "error": f"transport gagal {MAX_ATTEMPTS_PER_PAGE}x: {last_error}",
            "from_cache": False,
        },
        MAX_ATTEMPTS_PER_PAGE,
    )


def fetch_sports_events(
    limit: int = MAX_EVENTS_DEFAULT, client: JupiterClient | None = None
) -> FetchResult:
    """Tarik SEMUA event sports jup.ag (mentah) dengan pagination.

    Memindai halaman 100 event sampai `pagination.hasNext` false atau
    total event mencapai `limit` (safety cap, default 10000). data =
    list event MENTAH (dict payload API, termasuk beginAt + markets).
    client: JupiterClient (di-inject untuk tes; bila None, dibuat dari
    JUPITER_API_KEY di .env dengan fallback keyless otomatis + cache
    300 dtk). Gagal (halaman gagal setelah retry / HTTP error / JSON
    tidak valid) -> ok=False + error, tidak melempar — kecuali path
    Jupiter tidak diizinkan (ValueError dari JupiterClient, tidak
    mungkin terjadi di sini karena path sudah tetap).

    extra mencatat: pages_fetched, events_scanned, scan_complete
    (True hanya bila hasNext false sebelum cap), stopped_reason
    ("semua_halaman" / "cap_tercapai" / "halaman_kosong"), mode,
    from_cache (True bila SEMUA halaman dari cache), total_attempts
    (jumlah percobaan GET halaman, termasuk retry) dan retried_pages
    (halaman yang butuh >1 percobaan). Pemanggil WAJIB memeriksa
    scan_complete sebelum menganggap data sebagai slate lengkap —
    ok=True + scan_complete=False berarti data parsial karena cap.
    """
    fetched_at = now_iso()
    if limit < 1:
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=False,
            error=f"limit harus >= 1, didapat {limit}",
        )
    if client is None:
        env = load_dotenv()
        client = JupiterClient(
            env.get("JUPITER_API_KEY") or None,
            cache=DiskCache(default_cache_dir(), CACHE_TTL_SECONDS),
        )
    events: list[dict] = []
    seen_ids: set[str] = set()
    start = 0
    pages = 0
    total_attempts = 0
    retried_pages = 0
    mode: str | None = None
    all_from_cache = True
    stopped_reason = "semua_halaman"
    while True:
        end = min(start + PAGE_SIZE, limit)
        result, attempts = _get_page_with_retry(
            client,
            {
                "category": "sports",
                "limit": str(end - start),
                "start": str(start),
                "end": str(end),
            },
        )
        pages += 1
        total_attempts += attempts
        if attempts > 1:
            retried_pages += 1
        if result.get("mode"):
            mode = result.get("mode")
        all_from_cache = all_from_cache and bool(result.get("from_cache"))
        if result.get("status") != 200:
            return FetchResult(
                source=SOURCE,
                tier=TIER,
                fetched_at=fetched_at,
                ok=False,
                error=(
                    f"Jupiter /events halaman {pages} (start={start}) "
                    f"HTTP {result.get('status')}: "
                    f"{result.get('error') or 'tanpa keterangan'}"
                ),
                extra={
                    "pages_fetched": pages,
                    "events_scanned": len(events),
                    "scan_complete": False,
                    "stopped_reason": "halaman_gagal",
                    "mode": mode,
                    "total_attempts": total_attempts,
                    "retried_pages": retried_pages,
                },
            )
        data = parse_json_body(result)
        page_events = data.get("data") if isinstance(data, dict) else None
        if not isinstance(page_events, list):
            return FetchResult(
                source=SOURCE,
                tier=TIER,
                fetched_at=fetched_at,
                ok=False,
                error="respons Jupiter bukan JSON / tanpa kunci 'data' berupa list",
                extra={
                    "pages_fetched": pages,
                    "events_scanned": len(events),
                    "scan_complete": False,
                    "stopped_reason": "respons_tidak_valid",
                    "mode": mode,
                    "total_attempts": total_attempts,
                    "retried_pages": retried_pages,
                },
            )
        for event in page_events:
            if not isinstance(event, dict):
                continue
            event_id = event.get("eventId")
            if event_id is not None and event_id in seen_ids:
                continue
            if event_id is not None:
                seen_ids.add(event_id)
            events.append(event)
        pagination = data.get("pagination") or {}
        has_next = bool(pagination.get("hasNext"))
        if len(page_events) == 0:
            stopped_reason = "halaman_kosong"
            break
        if len(events) >= limit:
            stopped_reason = "cap_tercapai" if has_next else "semua_halaman"
            break
        if not has_next:
            stopped_reason = "semua_halaman"
            break
        start = end
    scan_complete = stopped_reason == "semua_halaman"
    return FetchResult(
        source=SOURCE,
        tier=TIER,
        fetched_at=fetched_at,
        ok=True,
        data=events,
        extra={
            "mode": mode,
            "from_cache": all_from_cache,
            "pages_fetched": pages,
            "events_scanned": len(events),
            "events_returned": len(events),
            "scan_complete": scan_complete,
            "stopped_reason": stopped_reason,
            "total_attempts": total_attempts,
            "retried_pages": retried_pages,
        },
    )


def fetch_sports_markets(
    limit: int = MAX_EVENTS_DEFAULT, client: JupiterClient | None = None
) -> FetchResult:
    """Tarik SEMUA pasar sports jup.ag (ternormalisasi) dengan pagination.

    Sama dengan fetch_sports_events, tapi data = list pasar
    ternormalisasi (lihat _normalize_market). extra sama, ditambah
    markets_returned. Gagal -> ok=False + error (diteruskan dari
    fetch_sports_events).
    """
    result = fetch_sports_events(limit=limit, client=client)
    if not result.ok:
        return result
    events = result.data or []
    markets = [
        _normalize_market(event, market)
        for event in events
        for market in (event.get("markets") or [])
        if isinstance(market, dict)
    ]
    return FetchResult(
        source=result.source,
        tier=result.tier,
        fetched_at=result.fetched_at,
        ok=True,
        data=markets,
        extra={**result.extra, "markets_returned": len(markets)},
    )
