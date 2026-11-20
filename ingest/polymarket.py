"""Penarik Polymarket: orderbook CLOB + pencari token (Tahap 2b).

Dipakai untuk jup_markup (harga jup.ag vs midpoint orderbook Polymarket
untuk pasar yang SAMA) — BUKAN edge, melainkan biaya tambahan jup.ag.
Polymarket TIDAK dipakai sebagai pembanding p_market untuk pasar jup.ag
asal Polymarket (P2) — itu harga yang sama, bukan pembanding.

Endpoint CLOB PERSIS seperti probe jup_markup:
- GET https://clob.polymarket.com/book?token_id=<id>
- fallback GET https://clob.polymarket.com/midpoint?token_id=<id>
  bila orderbook kosong / midpoint tidak didapat.

PERANGKAP TOKEN (dibuktikan probe): pasar 2-outcome MEMBAGI satu
pasangan token — token Yes dipilih dari INDEKS judul pasar di dalam
`outcomes`, bukan selalu [0]. Memakai [0] untuk kedua tim menghasilkan
markup palsu ~15-37¢.

Pencarian pasar via Gamma API: endpoint /markets?search= dan
/markets?condition_id= MENGABAIKAN parameternya (diverifikasi live
2026-11-20 — mengembalikan daftar tak terfilter). Yang BEKERJA adalah
GET https://gamma-api.polymarket.com/public-search?q=<judul event>,
yang mengembalikan event BESERTA seluruh pasarnya (clobTokenIds cocok
persis dengan payload jup.ag).
"""

from __future__ import annotations

import json
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

SOURCE = "Polymarket CLOB"
TIER = 2
CACHE_TTL_SECONDS = 300
CLOB_BASE = "https://clob.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"

_SPREAD_QUESTION_RE = re.compile(r"^Spread:\s*(.+?)\s*\(([+-]?[\d.]+)\)$")
_TOTAL_QUESTION_RE = re.compile(r": O/U\s+([\d.]+)\s*$")


def compute_jup_markup(jup_price_cents: float, mid_cents: float) -> float:
    """jup_markup (¢) = harga beli jup.ag − midpoint Polymarket.

    Murni (tanpa network). BUKAN edge — ukuran biaya tambahan jup.ag.
    """
    return jup_price_cents - mid_cents


def _as_list(value: object) -> list:
    """Ubah nilai jadi list: list apa adanya, string JSON di-parse."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _select_token(
    outcomes: object, tokens: object, candidates: list[str | None]
) -> tuple[str | None, int | None, str]:
    """Pilih token Yes dari pasangan token lewat indeks judul di outcomes.

    candidates: judul-judul yang dicoba berurutan (judul pasar, nama tim,
    outcome). Bila tidak ada yang cocok (pasar biner mandiri, outcomes =
    ["Yes", "No"]), pakai token [0]. Mengembalikan (token, indeks, cara).
    """
    outcome_list = [str(o) for o in _as_list(outcomes)]
    token_list = [str(t) for t in _as_list(tokens)]
    for candidate in candidates:
        if candidate and candidate in outcome_list:
            index = outcome_list.index(candidate)
            if index < len(token_list):
                return token_list[index], index, "indeks judul di outcomes"
    if token_list:
        return token_list[0], 0, "fallback [0] (judul tidak ada di outcomes)"
    return None, None, "tidak ada clobTokenIds"


def yes_token_id(market: dict) -> tuple[str | None, int | None, str]:
    """Pilih token Yes Polymarket untuk satu pasar jup.ag (mentah).

    Di-port dari probes/jup_markup.py. market: dict payload jup.ag
    (title/team/outcomes/clobTokenIds) atau pasar Gamma (question/
    outcomes/clobTokenIds sebagai string JSON).
    """
    candidates = [
        market.get("title"),
        (
            (market.get("team") or {}).get("name")
            if isinstance(market.get("team"), dict)
            else None
        ),
        market.get("outcome"),
    ]
    return _select_token(market.get("outcomes"), market.get("clobTokenIds"), candidates)


def _best_bid_ask(book: dict | None) -> tuple[float | None, float | None]:
    """Bid terbaik + ask terbaik orderbook CLOB (0-1); (None, None) bila kosong."""
    if not isinstance(book, dict):
        return (None, None)
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    try:
        best_bid = max(float(b["price"]) for b in bids)
        best_ask = min(float(a["price"]) for a in asks)
    except (KeyError, TypeError, ValueError):
        return (None, None)
    if not (0.0 <= best_bid <= 1.0 and 0.0 <= best_ask <= 1.0):
        return (None, None)
    return (best_bid, best_ask)


# Satu limiter untuk SEMUA request modul ini (dibagi semua pemanggilan):
# membuat RateLimiter baru per panggilan berarti tidak ada jeda antar
# panggilan — slate memanggil fetcher berkali-kali (Kalshi: 3 series;
# Polymarket: 1x per pasar) dan API membalas 429 (teramati: Kalshi total
# EPL 429 saat demo 2b). RateLimiter.wait() melacak per host, jadi satu
# limiter aman untuk beberapa host modul ini.
_LIMITER = RateLimiter(0.5)


def fetch_orderbook(token_id: str, client: HttpClient | None = None) -> FetchResult:
    """Tarik orderbook CLOB satu token; kembalikan bid/ask/mid/spread (¢).

    Bila orderbook kosong/tidak valid, fallback ke endpoint /midpoint
    (mid saja; bid/ask/spread None). Gagal -> ok=False + error, tidak
    melempar.
    """
    fetched_at = now_iso()
    if not isinstance(token_id, str) or not token_id:
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=False,
            error="token_id harus string tidak kosong",
        )
    if client is None:
        client = HttpClient(
            _LIMITER,
            cache=DiskCache(default_cache_dir(), CACHE_TTL_SECONDS),
        )
    encoded = urllib.parse.quote(token_id, safe="")
    resp = client.get(f"{CLOB_BASE}/book?token_id={encoded}")
    book = parse_json_body(resp) if resp.get("status") == 200 else None
    bid, ask = _best_bid_ask(book if isinstance(book, dict) else None)
    if bid is not None and ask is not None:
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=True,
            data={
                "bid_cents": round(bid * 100.0, 3),
                "ask_cents": round(ask * 100.0, 3),
                "mid_cents": round((bid + ask) / 2.0 * 100.0, 3),
                "spread_cents": round((ask - bid) * 100.0, 3),
            },
            extra={
                "source": "book",
                "from_cache": bool(resp.get("from_cache")),
            },
        )
    resp2 = client.get(f"{CLOB_BASE}/midpoint?token_id={encoded}")
    data2 = parse_json_body(resp2) if resp2.get("status") == 200 else None
    mid = None
    if isinstance(data2, dict) and data2.get("mid") is not None:
        try:
            mid = float(data2["mid"])
        except (TypeError, ValueError):
            mid = None
    if mid is not None and 0.0 <= mid <= 1.0:
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=True,
            data={
                "bid_cents": None,
                "ask_cents": None,
                "mid_cents": round(mid * 100.0, 3),
                "spread_cents": None,
            },
            extra={
                "source": "midpoint",
                "from_cache": bool(resp2.get("from_cache")),
            },
        )
    return FetchResult(
        source=SOURCE,
        tier=TIER,
        fetched_at=fetched_at,
        ok=False,
        error="orderbook kosong / midpoint tidak didapat "
        f"(book HTTP {resp.get('status')}, midpoint HTTP {resp2.get('status')})",
    )


def _gamma_match_market(
    markets: list, market_type: str | None, outcome: str | None, line: float | None
) -> dict | None:
    """Cari pasar Gamma yang sama dengan pasar jup.ag (ternormalisasi).

    moneyline: question == judul event, outcomes memuat outcome.
    spreads: question "Spread: <Tim> (<garis>)" dengan tim + garis sama.
    totals: question "...: O/U <garis>" dengan garis sama, outcomes
    memuat outcome ("Over"/"Under"). Jenis lain -> None.
    """
    if outcome is None:
        return None
    outcome_lower = outcome.strip().lower()
    for market in markets:
        if not isinstance(market, dict):
            continue
        question = (market.get("question") or "").strip()
        outcomes = [str(o).strip().lower() for o in _as_list(market.get("outcomes"))]
        if market_type == "moneyline":
            if outcome_lower in outcomes and question:
                return market
        elif market_type == "spreads" and line is not None:
            match = _SPREAD_QUESTION_RE.match(question)
            if not match:
                continue
            try:
                gamma_line = float(match.group(2))
            except ValueError:
                continue
            if (
                match.group(1).strip().lower() == outcome_lower
                and gamma_line == line
                and outcome_lower in outcomes
            ):
                return market
        elif market_type == "totals" and line is not None:
            match = _TOTAL_QUESTION_RE.search(question)
            if not match:
                continue
            try:
                gamma_line = float(match.group(1))
            except ValueError:
                continue
            if gamma_line == line and outcome_lower in outcomes:
                return market
    return None


def _line_float(value: object) -> float | None:
    """Ubah garis (string/angka/None) jadi float."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def find_token_for_jup_market(
    jup_market: dict, client: HttpClient | None = None
) -> str | None:
    """Cari token Yes Polymarket untuk satu pasar jup.ag.

    Jalur 1 (tanpa network): pasar mentah jup.ag membawa clobTokenIds —
    token dipilih dari indeks judul di outcomes (perangkap token).
    Jalur 2 (Gamma): pasar ternormalisasi (tanpa clobTokenIds) dicari
    lewat public-search berdasarkan judul event, lalu pasarnya dicocokkan
    dari jenis + outcome + garis. Mengembalikan None bila tidak ditemukan
    / ambigu / network gagal (tidak melempar).
    """
    tokens = jup_market.get("clobTokenIds")
    if tokens:
        token, _, _ = yes_token_id(jup_market)
        return token
    metadata = jup_market.get("metadata") or {}
    event_title = jup_market.get("event_title") or metadata.get("title")
    outcome = jup_market.get("outcome") or jup_market.get("title")
    market_type = jup_market.get("market_type") or jup_market.get("sportsMarketType")
    line = _line_float(jup_market.get("line") or jup_market.get("sportsLine"))
    if not event_title or not outcome:
        return None
    if client is None:
        client = HttpClient(
            _LIMITER,
            cache=DiskCache(default_cache_dir(), CACHE_TTL_SECONDS),
        )
    query = urllib.parse.quote(str(event_title))
    resp = client.get(f"{GAMMA_BASE}/public-search?q={query}")
    if resp.get("status") != 200:
        return None
    data = parse_json_body(resp)
    events = data.get("events") if isinstance(data, dict) else None
    if not isinstance(events, list):
        return None
    wanted = str(event_title).strip().lower()
    matches = [
        event
        for event in events
        if isinstance(event, dict)
        and str(event.get("title") or "").strip().lower() == wanted
    ]
    if len(matches) != 1:
        # 0 = tidak ditemukan; >1 = ambigu (tim yang sama main berkali-kali)
        # — fail-closed, jangan tebak.
        return None
    gamma_markets = matches[0].get("markets")
    if not isinstance(gamma_markets, list):
        return None
    if market_type == "moneyline":
        # Moneyline Gamma: question == judul event.
        gamma_markets = [
            m
            for m in gamma_markets
            if isinstance(m, dict)
            and str(m.get("question") or "").strip().lower() == wanted
        ]
    gamma_market = _gamma_match_market(gamma_markets, market_type, outcome, line)
    if gamma_market is None:
        return None
    token, _, _ = _select_token(
        gamma_market.get("outcomes"),
        gamma_market.get("clobTokenIds"),
        [outcome],
    )
    return token
