"""Penarik Kalshi API: harga pasar pembanding (Tahap 2b).

Series (terverifikasi probe 2a lanjutan): NBA KXNBAGAME/KXNBASPREAD/
KXNBATOTAL; EPL KXEPLGAME/KXEPLSPREAD/KXEPLTOTAL; LaLiga KXLALIGAGAME
(moneyline saja — spread/total LaLiga tidak diuji probe).

HARGA: field-nya bernama `*_dollars` (string dolar, 4 desimal) —
nama lama yes_bid/yes_ask TIDAK ADA di API ini. Harga dipakai dari
bid/ask Yes; JANGAN memakai last_price (teramati 0.0000 padahal
bid/ask ada). Pasar tanpa bid+ask DITOLAK (tidak masuk data), bukan
diisi last_price basi.

Format judul pasar (terverifikasi dari cache probe + 1 panggilan live
2026-11-20 untuk total NBA):
- moneyline: "<Tim> wins" (NBA + bola); seri EPL/LaLiga:
  "Tie is the result".
- spread: "<Tim> wins by more than X goals?" (bola) /
  "<Tim> wins by over X points" (NBA). Garis Kalshi selalu POSITIF
  (X = kemenangan > X); garis jup.ag untuk tim yang sama NEGATIF
  (mis. -1.5) — pekerja integrasi wajib menyamakan tanda.
- total: "Will over X goals be scored?" (bola) /
  "Full Game: Over X points scored" (NBA). Kalshi hanya punya pasar
  Over — Under adalah sisi No dari pasar Over yang sama.

Kandang/tandang dari judul event (konvensi terverifikasi melawan
scoreboard ESPN): NBA "A vs B" = A tandang, B kandang; bola "A vs B"
= A kandang, B tandang.

PAGINASI: endpoint /events dan /markets dibatasi 200 item per panggilan
dan mengembalikan `cursor` bila masih ada item (terverifikasi live
2026-11-20: KXNBASPREAD + KXNBATOTAL masing-masing 200 pasar dengan
cursor tidak kosong — tanpa paginasi, pasar di luar 200 pertama
hilang). Fetcher mengikuti cursor sampai habis (maks 10 halaman =
2.000 item per series).
"""

from __future__ import annotations

import re
import urllib.parse

from ingest.common import (
    DiskCache,
    FetchResult,
    HttpClient,
    RateLimiter,
    default_cache_dir,
    now_iso,
    parse_json_body,
)
from ingest.matching import normalize_team, parse_vs_title

SOURCE = "Kalshi API"
TIER = 2
CACHE_TTL_SECONDS = 300
BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
PAGE_LIMIT = 200
MAX_PAGES = 10  # safety cap paginasi cursor (10 x 200 = 2.000 item).

# (liga, jenis pasar) -> series_ticker Kalshi.
SERIES = {
    ("nba", "moneyline"): "KXNBAGAME",
    ("nba", "spread"): "KXNBASPREAD",
    ("nba", "total"): "KXNBATOTAL",
    ("epl", "moneyline"): "KXEPLGAME",
    ("epl", "spread"): "KXEPLSPREAD",
    ("epl", "total"): "KXEPLTOTAL",
    ("laliga", "moneyline"): "KXLALIGAGAME",
}

LEAGUES = {"nba", "epl", "laliga"}

_SPREAD_TITLE_RE = re.compile(
    r"^(.+?) wins by (?:more than|over) ([\d.]+) (?:goals|points)\??$"
)
_TOTAL_SOCCER_RE = re.compile(r"^Will over ([\d.]+) goals be scored\?$")
_TOTAL_NBA_RE = re.compile(r"^Full Game: Over ([\d.]+) points scored$")
_MONEYLINE_RE = re.compile(r"^(.+) wins$")
_SERIES_SUFFIX_RE = re.compile(r": (Spread|Total Goals|Total Points)$")


def kalshi_probability(market: dict) -> float:
    """Peluang Yes dari midpoint bid/ask (dolar) satu pasar Kalshi.

    Murni (tanpa network). Melempar ValueError bila bid/ask tidak ada,
    bukan angka, atau di luar 0-1. TIDAK PERNAH memakai last_price.
    """
    try:
        bid = float(market["yes_bid_dollars"])
        ask = float(market["yes_ask_dollars"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "pasar Kalshi tanpa yes_bid_dollars/yes_ask_dollars yang valid"
        ) from exc
    if not (0.0 <= bid <= 1.0 and 0.0 <= ask <= 1.0):
        raise ValueError(f"bid/ask Kalshi di luar 0-1: bid={bid}, ask={ask}")
    return (bid + ask) / 2.0


def _strip_series_suffix(title: str) -> str:
    """Buang akhiran series dari judul event Kalshi (": Spread", dll.)."""
    return _SERIES_SUFFIX_RE.sub("", title)


def _event_home_away(event_title: str, league: str) -> tuple[str | None, str | None]:
    """Kandang/tandang dari judul event Kalshi (konvensi per olahraga)."""
    parsed = parse_vs_title(_strip_series_suffix(event_title))
    if parsed is None:
        return (None, None)
    first, second = parsed
    if league == "nba":
        return (second, first)
    return (first, second)


def _team_side(
    team: str, home: str | None, away: str | None, league: str
) -> str | None:
    """Sisi ("home"/"away") sebuah tim dalam satu event, atau None."""
    sport = "nba" if league == "nba" else "football"
    normalized = normalize_team(team, sport)
    if home is not None and normalized == normalize_team(home, sport):
        return "home"
    if away is not None and normalized == normalize_team(away, sport):
        return "away"
    return None


def _has_bid_ask(market: dict) -> bool:
    """Apakah pasar punya bid+ask Yes yang bisa dipakai (bukan last_price)."""
    try:
        bid = float(market["yes_bid_dollars"])
        ask = float(market["yes_ask_dollars"])
    except (KeyError, TypeError, ValueError):
        return False
    return 0.0 <= bid <= 1.0 and 0.0 <= ask <= 1.0


def _parse_moneyline(market: dict, league: str) -> dict | None:
    """Parse pasar moneyline -> (line, side) atau None bila tak dikenal."""
    title = market.get("title") or ""
    if title == "Tie is the result":
        return {"line": None, "side": "draw", "team": None}
    match = _MONEYLINE_RE.match(title)
    if not match:
        return None
    return {"line": None, "side": None, "team": match.group(1)}


def _parse_spread(market: dict, league: str) -> dict | None:
    """Parse pasar spread -> (line, side) atau None bila tak dikenal."""
    title = market.get("title") or ""
    match = _SPREAD_TITLE_RE.match(title)
    if not match:
        return None
    try:
        line = float(match.group(2))
    except ValueError:
        return None
    return {"line": line, "side": None, "team": match.group(1)}


def _parse_total(market: dict, league: str) -> dict | None:
    """Parse pasar total -> (line, side) atau None bila tak dikenal."""
    title = market.get("title") or ""
    for pattern in (_TOTAL_SOCCER_RE, _TOTAL_NBA_RE):
        match = pattern.match(title)
        if match:
            try:
                return {"line": float(match.group(1)), "side": "over", "team": None}
            except ValueError:
                return None
    return None


_PARSERS = {
    "moneyline": _parse_moneyline,
    "spread": _parse_spread,
    "total": _parse_total,
}


def _fetch_list(client: HttpClient, url: str, key: str) -> tuple[list, str | None, int]:
    """GET satu endpoint list Kalshi + ikuti cursor; kembalikan (item, error, halaman).

    Satu halaman = 200 item; respons membawa `cursor` (string kosong =
    habis). Berhenti di MAX_PAGES halaman (item selebihnya hilang —
    dicatat di extra pemanggil lewat pages_fetched).
    """
    items: list = []
    cursor: str | None = None
    pages = 0
    for _ in range(MAX_PAGES):
        page_url = url
        if cursor:
            page_url = f"{url}&cursor={urllib.parse.quote(cursor, safe='')}"
        resp = client.get(page_url)
        pages += 1
        if resp.get("status") != 200:
            return (
                [],
                f"Kalshi {url.split('/v2/')[-1].split('?')[0]} "
                f"HTTP {resp.get('status')}: "
                f"{resp.get('error') or 'tanpa keterangan'}",
                pages,
            )
        data = parse_json_body(resp)
        if not isinstance(data, dict) or not isinstance(data.get(key), list):
            return (
                [],
                f"respons Kalshi bukan JSON / tanpa kunci '{key}' berupa list",
                pages,
            )
        items.extend(data[key])
        cursor = data.get("cursor") or None
        if not cursor:
            break
    return items, None, pages


# Satu limiter untuk SEMUA request modul ini (dibagi semua pemanggilan):
# membuat RateLimiter baru per panggilan berarti tidak ada jeda antar
# panggilan — slate memanggil fetcher berkali-kali (Kalshi: 3 series;
# Polymarket: 1x per pasar) dan API membalas 429 (teramati: Kalshi total
# EPL 429 saat demo 2b). RateLimiter.wait() melacak per host, jadi satu
# limiter aman untuk beberapa host modul ini.
_LIMITER = RateLimiter(1.0)


def _fetch_markets(
    league: str, market_type: str, client: HttpClient | None
) -> FetchResult:
    """Tarik + normalisasi pasar Kalshi untuk satu (liga, jenis pasar)."""
    fetched_at = now_iso()
    if league not in LEAGUES:
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=False,
            error=f"liga tidak didukung: {league!r} "
            f"(harus salah satu dari {sorted(LEAGUES)})",
        )
    series = SERIES.get((league, market_type))
    if series is None:
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=False,
            error=f"series Kalshi tidak tersedia untuk {league}/{market_type} "
            "(tidak diuji probe — LaLiga hanya moneyline)",
        )
    if client is None:
        client = HttpClient(
            _LIMITER,
            cache=DiskCache(default_cache_dir(), CACHE_TTL_SECONDS),
        )
    events, error, event_pages = _fetch_list(
        client,
        f"{BASE_URL}/events?series_ticker={series}&status=open&limit={PAGE_LIMIT}",
        "events",
    )
    if error is not None:
        return FetchResult(
            source=SOURCE, tier=TIER, fetched_at=fetched_at, ok=False, error=error
        )
    markets, error, market_pages = _fetch_list(
        client,
        f"{BASE_URL}/markets?series_ticker={series}&status=open&limit={PAGE_LIMIT}",
        "markets",
    )
    if error is not None:
        return FetchResult(
            source=SOURCE, tier=TIER, fetched_at=fetched_at, ok=False, error=error
        )
    event_titles = {
        event.get("event_ticker"): event.get("title") or ""
        for event in events
        if isinstance(event, dict)
    }
    parser = _PARSERS[market_type]
    data: list[dict] = []
    skipped_no_price = 0
    skipped_unparsed = 0
    for market in markets:
        if not isinstance(market, dict):
            continue
        if not _has_bid_ask(market):
            skipped_no_price += 1
            continue
        parsed = parser(market, league)
        if parsed is None:
            skipped_unparsed += 1
            continue
        event_title = event_titles.get(market.get("event_ticker"), "")
        home_team, away_team = _event_home_away(event_title, league)
        side = parsed["side"]
        if side is None and parsed["team"] is not None:
            side = _team_side(parsed["team"], home_team, away_team, league)
        data.append(
            {
                "market_ticker": market.get("ticker"),
                "event_ticker": market.get("event_ticker"),
                "title": market.get("title"),
                "league": league,
                "market_type": market_type,
                "home_team": home_team,
                "away_team": away_team,
                "line": parsed["line"],
                "side": side,
                "yes_bid_dollars": market.get("yes_bid_dollars"),
                "yes_ask_dollars": market.get("yes_ask_dollars"),
                # Passthrough mentah: slate memakainya untuk membedakan
                # dua laga pasangan tim yang sama (malam ini vs rematch
                # minggu depan) — expiration ≈ jam mulai + durasi laga.
                "expiration_time": market.get("expiration_time"),
            }
        )
    return FetchResult(
        source=SOURCE,
        tier=TIER,
        fetched_at=fetched_at,
        ok=True,
        data=data,
        extra={
            "series_ticker": series,
            "events_open": len(events),
            "markets_open": len(markets),
            "event_pages": event_pages,
            "market_pages": market_pages,
            "skipped_no_bid_ask": skipped_no_price,
            "skipped_unparsed_title": skipped_unparsed,
        },
    )


def fetch_moneyline_markets(
    league: str, client: HttpClient | None = None
) -> FetchResult:
    """Tarik pasar moneyline Kalshi untuk satu liga ("nba"/"epl"/"laliga").

    Gagal -> ok=False + error, tidak melempar.
    """
    return _fetch_markets(league, "moneyline", client)


def fetch_spread_markets(league: str, client: HttpClient | None = None) -> FetchResult:
    """Tarik pasar spread Kalshi untuk satu liga ("nba"/"epl").

    LaLiga tidak punya series spread yang teruji -> ok=False. Gagal ->
    ok=False + error, tidak melempar.
    """
    return _fetch_markets(league, "spread", client)


def fetch_total_markets(league: str, client: HttpClient | None = None) -> FetchResult:
    """Tarik pasar total Kalshi untuk satu liga ("nba"/"epl").

    LaLiga tidak punya series total yang teruji -> ok=False. Gagal ->
    ok=False + error, tidak melempar.
    """
    return _fetch_markets(league, "total", client)
