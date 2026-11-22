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

TANGGA POLYMARKET — HARGA VENUE, BUKAN PEMBANDING (Tahap 3 Langkah 1,
koreksi 2026-11-22): API jup.ag (/events + /events/{id}) hanya
menampilkan 2 pasar moneyline per event NBA, TAPI UI jup.ag menampilkan
spread + total lengkap — pasarnya hidup di Polymarket (provider asal)
dan diambil dari Gamma per event lewat slug
(GET /events/slug/nba-{away}-{home}-{YYYY-MM-DD}). Fungsi
nba_slug / fetch_event_by_slug / parse_event_ladders /
resolve_slug_from_jup_event / venue_price_cents membangun tangga itu.

P2 TETAP BERLAKU, TEGAS: tangga ini adalah HARGA VENUE — harga yang
dilihat user di UI jup.ag (plus estimasi markup tipikal jup.ag) — dan
BUKAN pembanding. TIDAK ADA jalur kode di modul ini yang memberi harga
tangga sebagai p_market: tidak ada fungsi di sini yang mengembalikan
field bernama p_market. Pembanding p_market tetap sportsbook devig ->
Kalshi (di luar modul ini, DECISIONS.md P1–P4).

SEMANTIK HARGA (terverifikasi dari data DET-ATL, bukan asumsi):
- Untuk pasar O/U, outcomes = ["Over", "Under"], outcomePrices[0] =
  harga Yes Over, outcomePrices[1] = harga Yes Under, jumlahnya ≈ 1
  (parser memeriksa dan mencatat bila tidak).
- Field Gamma bestBid/bestAsk/lastTradePrice adalah kuotasi token Yes
  outcome PERTAMA (Over untuk total, tim pertama untuk moneyline).
  Harga Under = 1 − harga Over (komplemen pasar biner).
- Harga UTAMA = midpoint bid/ask ("book") bila bid+ask ada; fallback
  outcomePrices bila book tidak ada. lastTradePrice HANYA info
  (last_cents) — TIDAK PERNAH jadi harga utama, apalagi bila None
  atau di pasar tipis.
- "thin" = volume_usd < polymarket_ladder.min_volume_usd (config)
  ATAU bid/ask tidak ada; volume None -> thin. Garis Alt Under jauh
  TIPIS (volume $5–11, lastTradePrice None) — mesin wajib cek bid/ask
  + likuiditas, bukan harga terakhir.
"""

from __future__ import annotations

import json
import re
import urllib.parse

import config
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


# ── Tangga Polymarket: HARGA VENUE jup.ag (koreksi Tahap 3 Langkah 1) ──
# P2: tangga ini BUKAN pembanding. Tidak ada fungsi di bagian ini yang
# mengembalikan field bernama p_market (dijaga tes).

# Toleransi validasi jumlah outcomePrices pasar biner (harus ≈ 1,0).
_OUTCOME_SUM_TOLERANCE = 0.02

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def nba_slug(away_tricode: str, home_tricode: str, date_str: str) -> str:
    """Bangun slug Gamma untuk satu laga NBA.

    Pola: "nba-{away}-{home}-{YYYY-MM-DD}" huruf kecil, urutan
    AWAY-HOME. Terverifikasi: DET di ATL 2026-11-22 ->
    "nba-det-atl-2026-11-22" (bukti out/poly_event_det_atl.json).
    Raise ValueError bila tricode kosong atau tanggal bukan YYYY-MM-DD.
    """
    away = (away_tricode or "").strip().lower()
    home = (home_tricode or "").strip().lower()
    date = (date_str or "").strip()
    if not away or not home:
        raise ValueError("tricode tandang dan kandang tidak boleh kosong")
    if not _DATE_RE.match(date):
        raise ValueError(f"tanggal harus YYYY-MM-DD, dapat: {date_str!r}")
    return f"nba-{away}-{home}-{date}"


def resolve_slug_from_jup_event(jup_event: dict) -> str | None:
    """Ambil slug Polymarket dari metadata event jup.ag.

    Terverifikasi: metadata event jup.ag membawa "slug" +
    "series": "polymarket" (bukti out/jup_event_POLY-1338695.json:
    metadata.slug = "nba-det-atl-2026-11-22"). None bila metadata/slug
    tidak ada, atau series ada dan bukan "polymarket" — pemanggil lalu
    memakai nba_slug dari tricode tim + tanggal.
    """
    if not isinstance(jup_event, dict):
        return None
    metadata = jup_event.get("metadata")
    if not isinstance(metadata, dict):
        return None
    series = metadata.get("series")
    if series is not None and str(series).strip().lower() != "polymarket":
        return None
    slug = metadata.get("slug")
    if isinstance(slug, str) and slug.strip():
        return slug.strip()
    return None


def fetch_event_by_slug(slug: str, client: HttpClient | None = None) -> FetchResult:
    """Tarik satu event Gamma lewat slug (GET /events/slug/{slug}).

    Memakai limiter + cache modul (sama seperti fetch_orderbook).
    ok=True -> data = dict event Gamma (termasuk "markets").
    Gagal (slug kosong / HTTP bukan 200 / body bukan event) ->
    ok=False + error apa adanya, tidak melempar.
    """
    fetched_at = now_iso()
    if not isinstance(slug, str) or not slug:
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=False,
            error="slug harus string tidak kosong",
        )
    if client is None:
        client = HttpClient(
            _LIMITER,
            cache=DiskCache(default_cache_dir(), CACHE_TTL_SECONDS),
        )
    encoded = urllib.parse.quote(slug, safe="")
    resp = client.get(f"{GAMMA_BASE}/events/slug/{encoded}")
    if resp.get("status") != 200:
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=False,
            error=f"Gamma /events/slug HTTP {resp.get('status')}"
            + (f": {resp.get('error')}" if resp.get("error") else ""),
            extra={"slug": slug},
        )
    data = parse_json_body(resp)
    if not isinstance(data, dict) or not isinstance(data.get("markets"), list):
        return FetchResult(
            source=SOURCE,
            tier=TIER,
            fetched_at=fetched_at,
            ok=False,
            error="respons Gamma bukan event (tanpa daftar 'markets')",
            extra={"slug": slug},
        )
    return FetchResult(
        source=SOURCE,
        tier=TIER,
        fetched_at=fetched_at,
        ok=True,
        data=data,
        extra={
            "slug": slug,
            "n_markets": len(data["markets"]),
            "from_cache": bool(resp.get("from_cache")),
        },
    )


def venue_price_cents(poly_mid_cents: float, cfg: dict | None = None) -> float:
    """Harga venue jup.ag (ESTIMASI) = mid Polymarket + markup tipikal.

    Markup dibaca dari config "fees.jup_typical_markup_cents" (nilai
    usulan 0,5¢ = median terukur probe tambahan 3, 11 pasar, mean
    0,68¢, max 1,5¢ — DECISIONS.md 2026-11-20). Ini ESTIMASI TIPIKAL,
    bukan harga pasti per pasar: markup aktual per pasar bervariasi
    dan hanya diketahui dari kuotasi jup.ag langsung (compute_jup_markup).

    P2: ini harga VENUE (yang dilihat user di UI jup.ag), BUKAN
    pembanding — jangan pernah dipakai sebagai p_market.
    """
    cfg = cfg if cfg is not None else config.load_playstyle()
    markup = float(config.get_value(cfg, "fees", "jup_typical_markup_cents"))
    return round(float(poly_mid_cents) + markup, 3)


def _float_or_none(value: object) -> float | None:
    """Ubah nilai (string/angka/None) jadi float, None bila tidak valid."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _book_cents(market: dict) -> tuple[float | None, float | None, float | None]:
    """Bid/ask/mid (¢) token Yes outcome PERTAMA dari field Gamma.

    bestBid/bestAsk Gamma adalah kuotasi token Yes outcomes[0]
    (terverifikasi DET-ATL: O/U 225.5 bid 0,47/ask 0,48 = token Over,
    cocok dengan outcomePrices[0] 0,475). (None, None, None) bila
    bid/ask tidak ada / di luar [0, 1].
    """
    bid = _float_or_none(market.get("bestBid"))
    ask = _float_or_none(market.get("bestAsk"))
    if bid is None or ask is None:
        return (None, None, None)
    if not (0.0 <= bid <= 1.0 and 0.0 <= ask <= 1.0):
        return (None, None, None)
    return (
        round(bid * 100.0, 3),
        round(ask * 100.0, 3),
        round((bid + ask) / 2.0 * 100.0, 3),
    )


def _outcome_prices_cents(market: dict) -> list[float] | None:
    """outcomePrices Gamma (string JSON) -> list harga ¢; None bila rusak."""
    raw = _as_list(market.get("outcomePrices"))
    prices: list[float] = []
    for value in raw:
        price = _float_or_none(value)
        if price is None or not (0.0 <= price <= 1.0):
            return None
        prices.append(round(price * 100.0, 3))
    return prices or None


def _classify_market(market: dict, event_title: str) -> str | None:
    """Jenis pasar Gamma: "moneyline"/"spreads"/"totals"/None.

    Utama: field sportsMarketType Gamma (terverifikasi DET-ATL:
    totals 31, spreads 33, moneyline 1; player props memakai
    points/rebounds/assists/dst. dan BUKAN tangga laga). Fallback:
    pola question (regex yang sama dengan _gamma_match_market) bila
    field tidak ada — regex total ": O/U <n>" tidak cocok dengan
    props pemain ("Points O/U", tanpa titik dua sebelum O/U).
    """
    market_type = market.get("sportsMarketType")
    if isinstance(market_type, str) and market_type in (
        "moneyline",
        "spreads",
        "totals",
    ):
        return market_type
    question = (market.get("question") or "").strip()
    if _SPREAD_QUESTION_RE.match(question):
        return "spreads"
    if _TOTAL_QUESTION_RE.search(question):
        return "totals"
    if question and event_title and question == event_title.strip():
        return "moneyline"
    return None


def _team_sides(event: dict) -> dict[str, str]:
    """Nama tim (huruf kecil) -> "home"/"away" dari event Gamma.

    Utama: event["teams"] (field "ordering": "away"/"home",
    terverifikasi DET-ATL). Fallback: judul event "Away vs. Home".
    """
    sides: dict[str, str] = {}
    teams = event.get("teams")
    if isinstance(teams, list):
        for team in teams:
            if not isinstance(team, dict):
                continue
            name = team.get("name")
            ordering = team.get("ordering")
            if isinstance(name, str) and ordering in ("home", "away"):
                sides[name.strip().lower()] = ordering
    if not sides:
        title = event.get("title") or ""
        parts = title.split(" vs. ")
        if len(parts) == 2:
            sides[parts[0].strip().lower()] = "away"
            sides[parts[1].strip().lower()] = "home"
    return sides


def _two_outcome_book(market: dict) -> dict:
    """Kumpulkan harga mentah satu pasar 2-outcome Gamma.

    Mengembalikan outcomes (nama), outcome_prices (¢), book bid/ask/mid
    (¢, token outcomes[0]), dan last (¢, token outcomes[0]; None bila
    lastTradePrice tidak ada). Harga komplemen (sisi outcomes[1])
    dihitung pemanggil sebagai 100 − harga outcomes[0].
    """
    outcomes = [str(o) for o in _as_list(market.get("outcomes"))]
    bid, ask, mid = _book_cents(market)
    last_raw = _float_or_none(market.get("lastTradePrice"))
    last = (
        round(last_raw * 100.0, 3)
        if last_raw is not None and 0.0 <= last_raw <= 1.0
        else None
    )
    return {
        "outcomes": outcomes,
        "outcome_prices": _outcome_prices_cents(market),
        "bid0": bid,
        "ask0": ask,
        "mid0": mid,
        "last0": last,
    }


def _side_entry(
    book: dict,
    index: int,
    *,
    line: float | None,
    side: str | None,
    team: str | None,
    volume_usd: float | None,
    liquidity: float | None,
    min_volume_usd: float,
    markup_cents: float,
    market_id: str | None,
) -> dict:
    """Satu entri tangga untuk satu sisi (indeks outcome) pasar biner.

    Harga UTAMA = midpoint book bila bid+ask ada ("book"), fallback
    outcomePrices ("outcome_prices"). Sisi outcomes[1] memakai
    komplemen 100 − harga outcomes[0] (identitas pasar biner, sama
    seperti komplemen Kalshi di slate.py). last_cents HANYA info,
    tidak pernah jadi harga utama. "thin" = volume < min_volume_usd
    ATAU bid/ask tidak ada; volume None -> thin.
    """
    outcome_prices = book["outcome_prices"]
    bid0, ask0, mid0, last0 = book["bid0"], book["ask0"], book["mid0"], book["last0"]
    if index == 0:
        bid, ask, mid, last = bid0, ask0, mid0, last0
    else:
        bid = round(100.0 - ask0, 3) if ask0 is not None else None
        ask = round(100.0 - bid0, 3) if bid0 is not None else None
        mid = round(100.0 - mid0, 3) if mid0 is not None else None
        last = round(100.0 - last0, 3) if last0 is not None else None
    if mid is not None:
        price, price_source = mid, "book"
    elif outcome_prices is not None and index < len(outcome_prices):
        price, price_source = outcome_prices[index], "outcome_prices"
    else:
        price, price_source = None, None
    thin = (
        volume_usd is None or volume_usd < min_volume_usd or bid is None or ask is None
    )
    return {
        "line": line,
        "side": side,
        "team": team,
        "price_cents": price,
        "bid_cents": bid,
        "ask_cents": ask,
        "mid_cents": mid,
        "last_cents": last,
        "volume_usd": volume_usd,
        "liquidity": liquidity,
        "price_source": price_source,
        "thin": thin,
        "market_id": market_id,
        "jup_estimated_cents": (
            round(price + markup_cents, 3) if price is not None else None
        ),
    }


def parse_event_ladders(event: dict, cfg: dict | None = None) -> dict:
    """Ubah satu event Gamma jadi tangga moneyline/spread/total.

    Murni (tanpa network). Ambang dibaca dari cfg: min volume
    "polymarket_ladder.min_volume_usd" dan markup
    "fees.jup_typical_markup_cents" (cfg=None -> playstyle.yaml;
    kunci hilang -> ConfigError, fail-closed).

    Bentuk hasil: {"slug", "title", "moneyline": [...], "spreads":
    [...], "totals": [...], "warnings": [...]}. Tiap entri adalah SATU
    SISI satu garis (total: satu entri "over" + satu "under" per
    garis; moneyline: satu entri per tim; spread: satu entri per
    pasar) dengan kunci: line, side ("over"/"under"/"home"/"away",
    None bila tim tidak bisa dipetakan), team, price_cents (harga
    UTAMA), bid_cents, ask_cents, mid_cents, last_cents (info saja),
    volume_usd, liquidity, price_source ("book"/"outcome_prices"/
    None), thin, market_id, jup_estimated_cents (price + markup
    tipikal — ESTIMASI, bukan harga pasti per pasar).

    Pasar yang dilewati: tutup/tidak aktif (closed True / active
    False), player props (bukan tangga laga), dan pasar yang
    outcomes/outcomePrices-nya rusak (dicatat di "warnings").
    outcomePrices yang jumlahnya tidak ≈ 1 juga dicatat di
    "warnings" (bukan ditolak — harganya tetap dipakai apa adanya).

    P2: tangga ini HARGA VENUE (yang dilihat user di UI jup.ag),
    BUKAN pembanding — tidak ada field p_market di hasil ini.
    """
    cfg = cfg if cfg is not None else config.load_playstyle()
    min_volume_usd = float(config.get_value(cfg, "polymarket_ladder", "min_volume_usd"))
    markup_cents = float(config.get_value(cfg, "fees", "jup_typical_markup_cents"))
    title = event.get("title") or ""
    sides = _team_sides(event)
    ladders: dict = {
        "slug": event.get("slug"),
        "title": title,
        "moneyline": [],
        "spreads": [],
        "totals": [],
        "warnings": [],
    }
    markets = event.get("markets")
    if not isinstance(markets, list):
        ladders["warnings"].append("event tanpa daftar 'markets'")
        return ladders
    for market in markets:
        if not isinstance(market, dict):
            continue
        if market.get("closed") is True or market.get("active") is False:
            continue
        kind = _classify_market(market, title)
        if kind is None:
            continue
        question = (market.get("question") or "").strip()
        market_id = market.get("id")
        market_id = str(market_id) if market_id is not None else None
        volume_usd = _float_or_none(market.get("volume"))
        liquidity = _float_or_none(market.get("liquidity"))
        book = _two_outcome_book(market)
        outcomes = book["outcomes"]
        outcome_prices = book["outcome_prices"]
        if len(outcomes) != 2 or outcome_prices is None or len(outcome_prices) != 2:
            ladders["warnings"].append(
                f"pasar dilewati (outcomes/outcomePrices rusak): {question}"
            )
            continue
        if abs(sum(outcome_prices) - 100.0) > _OUTCOME_SUM_TOLERANCE * 100.0:
            ladders["warnings"].append(
                f"outcomePrices pasar '{question}' berjumlah "
                f"{sum(outcome_prices):.1f}¢ (bukan ~100¢)"
            )
        base = {
            "volume_usd": volume_usd,
            "liquidity": liquidity,
            "min_volume_usd": min_volume_usd,
            "markup_cents": markup_cents,
            "market_id": market_id,
        }
        if kind == "totals":
            match = _TOTAL_QUESTION_RE.search(question)
            line = _line_float(match.group(1)) if match else None
            lowered = [o.strip().lower() for o in outcomes]
            if line is None or "over" not in lowered or "under" not in lowered:
                ladders["warnings"].append(
                    f"pasar total dilewati (garis/outcome tidak dikenali): {question}"
                )
                continue
            idx_over, idx_under = lowered.index("over"), lowered.index("under")
            ladders["totals"].append(
                _side_entry(book, idx_over, line=line, side="over", team=None, **base)
            )
            ladders["totals"].append(
                _side_entry(book, idx_under, line=line, side="under", team=None, **base)
            )
        elif kind == "spreads":
            match = _SPREAD_QUESTION_RE.match(question)
            if not match:
                ladders["warnings"].append(
                    f"pasar spread dilewati (question tidak dikenali): {question}"
                )
                continue
            team = match.group(1).strip()
            line = _line_float(match.group(2))
            lowered = [o.strip().lower() for o in outcomes]
            if line is None or team.lower() not in lowered:
                ladders["warnings"].append(
                    f"pasar spread dilewati (garis/tim tidak dikenali): {question}"
                )
                continue
            index = lowered.index(team.lower())
            side = sides.get(team.lower())
            if side is None:
                ladders["warnings"].append(
                    f"tim spread '{team}' tidak bisa dipetakan home/away: {question}"
                )
            ladders["spreads"].append(
                _side_entry(book, index, line=line, side=side, team=team, **base)
            )
        else:  # moneyline: satu entri per tim, garis None.
            for index, team in enumerate(outcomes):
                side = sides.get(team.strip().lower())
                if side is None:
                    ladders["warnings"].append(
                        f"tim moneyline '{team}' tidak bisa dipetakan home/away"
                    )
                ladders["moneyline"].append(
                    _side_entry(book, index, line=None, side=side, team=team, **base)
                )
    ladders["totals"].sort(key=lambda e: (e["line"], e["side"]))
    ladders["spreads"].sort(key=lambda e: (e["line"], e["team"] or ""))
    return ladders


def count_event_markets(event: dict) -> dict:
    """Hitung pasar spread/total satu event Gamma (tanpa harga).

    Murni (tanpa network, tanpa cfg) — untuk check_nba_lines: putusan
    ada/tidak spread/total tidak butuh harga. Klasifikasi sama dengan
    parse_event_ladders (lewat _classify_market); pasar tutup/tidak
    aktif dan player props tidak dihitung. Garis diurutkan, unik.
    """
    title = event.get("title") or ""
    spread_lines: set[float] = set()
    total_lines: set[float] = set()
    spread_count = 0
    total_count = 0
    markets = event.get("markets")
    if not isinstance(markets, list):
        return {
            "spread_markets": 0,
            "total_markets": 0,
            "spread_lines": [],
            "total_lines": [],
        }
    for market in markets:
        if not isinstance(market, dict):
            continue
        if market.get("closed") is True or market.get("active") is False:
            continue
        kind = _classify_market(market, title)
        question = (market.get("question") or "").strip()
        if kind == "spreads":
            spread_count += 1
            match = _SPREAD_QUESTION_RE.match(question)
            line = _line_float(match.group(2)) if match else None
            if line is not None:
                spread_lines.add(line)
        elif kind == "totals":
            total_count += 1
            match = _TOTAL_QUESTION_RE.search(question)
            line = _line_float(match.group(1)) if match else None
            if line is not None:
                total_lines.add(line)
    return {
        "spread_markets": spread_count,
        "total_markets": total_count,
        "spread_lines": sorted(spread_lines),
        "total_lines": sorted(total_lines),
    }
