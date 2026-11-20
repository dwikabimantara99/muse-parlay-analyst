"""Probe Kalshi sports — Tahap 2a lanjutan (muse-parlay-analyst).

Petakan pasar NBA & bola di Kalshi (moneyline, spread, total), lalu cocokkan
dengan slate jup.ag HARI INI: berapa % pasar jup.ag (NBA + bola) yang punya
padanan Kalshi (event + jenis pasar + garis yang sama)? Kalshi = pembanding
independen sah untuk pasar jup.ag asal Polymarket (P2/P3).

Slate jup.ag dipakai ulang dari cache probe 2a (bila masih segar); bila
cache kedaluwarsa, JupiterClient akan request baru (maks 1 di probe ini).
Request baru ke Kalshi: maks 15 (NBA events + markets, spread/total
events + contoh pasar, EPL events + markets, uji series EPL spread/total,
LaLiga events).

Pencocokan nama tim: Kalshi memakai nama KOTA untuk NBA ("Charlotte") dan
nama SINGKAT untuk bola ("Newcastle"), sementara jup.ag memakai nama
julukan ("Hornets") dan nama resmi ("Newcastle United FC"). Normalisasi
+ pemetaan julukan->kota NBA + alias bola tercatat di modul ini dan
diuji di tests/test_probes.py.

Dijalankan sendiri: python3 probes/kalshi_sports.py
Menulis probes/out/kalshi_sports.json.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    DiskCache,
    HttpClient,
    JupiterClient,
    RateLimiter,
    load_dotenv,
    new_result,
    out_dir,
    parse_json_body,
    repo_root,
    write_result,
)

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Series yang diuji keberadaannya (limit kecil dulu). Pola penamaan
# KX<liga>GAME terkonfirmasi dari KXLIGAMXGAME di probe 2a.
SERIES_CANDIDATES = [
    ("KXNBASPREAD", "NBA spread"),
    ("KXNBATOTAL", "NBA total"),
    ("KXEPLGAME", "EPL game"),
    ("KXLALIGAGAME", "LaLiga game"),
    ("KXEPLSPREAD", "EPL spread"),
    ("KXEPLTOTAL", "EPL total"),
]

# Subcategory Jupiter yang dianggap sepak bola untuk pencocokan.
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
}

# Kata pengisi nama klub yang dibuang saat normalisasi (sebagai kata utuh,
# di posisi mana pun): FC/CF/SC/AFC/RC/RCD = bentuk badan klub; "club";
# "united" (Kalshi menulis "Newcastle", bukan "Newcastle United");
# "de" (preposisi Spanyol/Portugal: "Celta de Vigo" = "Celta Vigo").
_FILLER_WORDS = {"fc", "cf", "sc", "afc", "rc", "rcd", "club", "united", "de"}

# Julukan NBA -> nama kota versi Kalshi (30 tim; Kalshi membedakan dua tim
# Los Angeles dengan "Los Angeles L" / "Los Angeles C"). Dipakai HANYA
# untuk pencocokan NBA (tidak untuk bola — "Spurs" juga nama Tottenham).
NBA_NICKNAME_TO_CITY = {
    "hawks": "atlanta",
    "celtics": "boston",
    "nets": "brooklyn",
    "hornets": "charlotte",
    "bulls": "chicago",
    "cavaliers": "cleveland",
    "mavericks": "dallas",
    "nuggets": "denver",
    "pistons": "detroit",
    "warriors": "golden state",
    "rockets": "houston",
    "pacers": "indiana",
    "clippers": "los angeles c",
    "lakers": "los angeles l",
    "grizzlies": "memphis",
    "heat": "miami",
    "bucks": "milwaukee",
    "timberwolves": "minnesota",
    "pelicans": "new orleans",
    "knicks": "new york",
    "thunder": "oklahoma city",
    "magic": "orlando",
    "76ers": "philadelphia",
    "suns": "phoenix",
    "trail blazers": "portland",
    "kings": "sacramento",
    "spurs": "san antonio",
    "raptors": "toronto",
    "jazz": "utah",
    "wizards": "washington",
}

# Alias bola (nama jup.ag ternormalisasi -> nama Kalshi), diturunkan dari
# judul event Kalshi yang teramati di slate ini — BUKAN daftar umum.
# "Athletic Club" (Bilbao) dan "RCD Espanyol de Barcelona" memakai nama
# kota/singkat di Kalshi.
SOCCER_ALIASES = {
    "athletic": "bilbao",
    "espanyol barcelona": "espanyol",
}


def normalize_team(name: str) -> str:
    """Normalisasi nama tim: huruf kecil, buang tanda baca + kata pengisi.

    "United"/"City" TIDAK dibuang keduanya — hanya "united" yang dibuang
    (Kalshi menulis "Newcastle"); "city" dipertahankan agar Manchester
    City tetap berbeda dari Manchester United ("manchester").
    """
    text = name.lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    tokens = [t for t in text.split() if t not in _FILLER_WORDS]
    return " ".join(tokens)


def normalize_nba_team(name: str) -> str:
    """Normalisasi nama tim NBA ke nama kota versi Kalshi."""
    normalized = normalize_team(name)
    return NBA_NICKNAME_TO_CITY.get(normalized, normalized)


def normalize_soccer_team(name: str) -> str:
    """Normalisasi nama tim bola + alias yang teramati di Kalshi."""
    normalized = normalize_team(name)
    return SOCCER_ALIASES.get(normalized, normalized)


def parse_vs_title(title: str) -> tuple[str, str] | None:
    """Pecah judul "Tim A vs. Tim B" jadi (tim_a, tim_b) mentah.

    Mengembalikan None bila judul bukan format lawan-vs-lawan.
    Normalisasi dilakukan pemanggil (NBA/bola berbeda).
    """
    if not isinstance(title, str):
        return None
    for sep in (" vs. ", " vs ", " v "):
        if sep in title:
            left, right = title.split(sep, 1)
            return (left.strip(), right.strip())
    return None


def same_game_nba(title_a: str, title_b: str) -> bool:
    """Apakah dua judul merujuk ke laga NBA yang sama (urutan tim bebas)?"""
    parsed_a = parse_vs_title(title_a)
    parsed_b = parse_vs_title(title_b)
    if parsed_a is None or parsed_b is None:
        return False
    teams_a = {normalize_nba_team(t) for t in parsed_a}
    teams_b = {normalize_nba_team(t) for t in parsed_b}
    return teams_a == teams_b


def same_game_soccer(title_a: str, title_b: str) -> bool:
    """Apakah dua judul merujuk ke laga bola yang sama (urutan tim bebas)?"""
    parsed_a = parse_vs_title(title_a)
    parsed_b = parse_vs_title(title_b)
    if parsed_a is None or parsed_b is None:
        return False
    teams_a = {normalize_soccer_team(t) for t in parsed_a}
    teams_b = {normalize_soccer_team(t) for t in parsed_b}
    return teams_a == teams_b


def parse_kalshi_spread_title(title: str) -> tuple[str, float] | None:
    """Parse judul pasar spread Kalshi.

    Dua format teramati: bola "<Tim> wins by more than X goals?" dan NBA
    "<Tim> wins by over X points". Mengembalikan (nama tim
    ternormalisasi, garis) atau None bila format tidak cocok. Garis
    Kalshi selalu positif (X = kemenangan > X gol/poin).
    """
    if not isinstance(title, str):
        return None
    match = re.match(
        r"^(.+?) wins by (?:more than|over) ([\d.]+) (?:goals|points)\??$",
        title,
    )
    if not match:
        return None
    try:
        return (normalize_soccer_team(match.group(1)), float(match.group(2)))
    except ValueError:
        return None


def parse_kalshi_total_title(title: str) -> float | None:
    """Parse judul pasar total Kalshi: "Will over X goals be scored?".

    Mengembalikan garis (float) atau None. Kalshi hanya punya pasar Over —
    Under adalah sisi No dari pasar Over yang sama.
    """
    if not isinstance(title, str):
        return None
    match = re.match(r"^Will over ([\d.]+) goals be scored\?$", title)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _strip_series_suffix(title: str) -> str:
    """Buang akhiran series dari judul event Kalshi (": Spread", dll.)."""
    return re.sub(r": (Spread|Total Goals|Total Points)$", "", title)


def _line_float(value: object) -> float | None:
    """Ubah sportsLine jup.ag (string '2.5' / angka / None) jadi float."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def probe() -> dict:
    """Jalankan probe Kalshi sports; kembalikan dict hasil."""
    result = new_result("Kalshi sports (NBA & bola)", tier=2)
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(2.0), cache=cache)

    # --- Slate jup.ag hari ini (dari cache 2a bila segar) ---
    env = load_dotenv(repo_root())
    jupiter = JupiterClient(env.get("JUPITER_API_KEY") or None, cache=cache)
    jup_resp = jupiter.get("/events", {"category": "sports", "limit": "100"})
    result["requests"].append(_summarize(jup_resp))
    jup_data = parse_json_body(jup_resp)
    jup_events = jup_data.get("data", []) if isinstance(jup_data, dict) else []
    jup_from_cache = bool(jup_resp.get("from_cache"))

    nba_games: list[dict] = []
    epl_games: list[dict] = []
    laliga_games: list[dict] = []
    other_soccer_games: list[dict] = []
    for event in jup_events:
        title = (event.get("metadata") or {}).get("title") or ""
        markets = event.get("markets", [])
        if parse_vs_title(title) is None:
            continue
        entry = {
            "title": title,
            "event_id": event.get("eventId"),
            "subcategory": event.get("subcategory"),
            "markets": [
                {
                    "title": m.get("title"),
                    "type": m.get("sportsMarketType"),
                    "line": m.get("sportsLine"),
                }
                for m in markets
            ],
        }
        sub = event.get("subcategory")
        if sub == "nba":
            nba_games.append(entry)
        elif sub == "epl":
            epl_games.append(entry)
        elif sub == "lal":
            laliga_games.append(entry)
        elif sub in SOCCER_SUBCATEGORIES:
            other_soccer_games.append(entry)
    result["jupiter_slate"] = {
        "events_total": len(jup_events),
        "from_cache": jup_from_cache,
        "nba_games": len(nba_games),
        "epl_games": len(epl_games),
        "laliga_games": len(laliga_games),
        "other_soccer_games": len(other_soccer_games),
        "nba_titles": [g["title"] for g in nba_games],
        "epl_titles": [g["title"] for g in epl_games],
        "laliga_titles": [g["title"] for g in laliga_games],
    }

    # --- Kalshi: NBA events + markets ---
    kalshi_series: dict[str, dict] = {}

    resp = client.get(
        f"{KALSHI_BASE}/events?series_ticker=KXNBAGAME&status=open&limit=200"
    )
    result["requests"].append(_summarize(resp))
    nba_events = _items(parse_json_body(resp), "events")
    kalshi_series["KXNBAGAME"] = {
        "label": "NBA game (moneyline)",
        "exists": len(nba_events) > 0,
        "events_open": len(nba_events),
        "event_titles": [e.get("title") for e in nba_events[:30]],
        "sample_event_keys": sorted(nba_events[0].keys()) if nba_events else [],
    }

    resp = client.get(
        f"{KALSHI_BASE}/markets?series_ticker=KXNBAGAME&status=open&limit=200"
    )
    result["requests"].append(_summarize(resp))
    nba_markets = _items(parse_json_body(resp), "markets")
    kalshi_series["KXNBAGAME"]["markets_open"] = len(nba_markets)
    if nba_markets:
        sample = nba_markets[0]
        kalshi_series["KXNBAGAME"]["sample_market_keys"] = sorted(sample.keys())
        # HARGA KALSHI: field-nya bernama *_dollars (string dolar, 4
        # desimal) — nama lama yes_bid/yes_ask TIDAK ADA di respons ini.
        kalshi_series["KXNBAGAME"]["sample_market"] = {
            k: sample.get(k)
            for k in (
                "ticker",
                "event_ticker",
                "title",
                "yes_bid_dollars",
                "yes_ask_dollars",
                "last_price_dollars",
                "volume_fp",
            )
            if k in sample
        }
        kalshi_series["KXNBAGAME"]["markets_priced"] = (
            f"{sum(1 for m in nba_markets if m.get('yes_bid_dollars') is not None and m.get('yes_ask_dollars') is not None)}"
            f"/{len(nba_markets)}"
        )

    # --- Kalshi: verifikasi harga via 1 pasar tunggal + orderbook ---
    tonight = [m for m in nba_markets if "26NOV20" in (m.get("event_ticker") or "")]
    price_check: dict = {"checked": False}
    if tonight:
        ticker = tonight[0].get("ticker")
        resp = client.get(f"{KALSHI_BASE}/markets/{ticker}")
        result["requests"].append(_summarize(resp))
        single = parse_json_body(resp)
        market = single.get("market") if isinstance(single, dict) else None
        resp = client.get(f"{KALSHI_BASE}/markets/{ticker}/orderbook?depth=5")
        result["requests"].append(_summarize(resp))
        book = parse_json_body(resp)
        orderbook = book.get("orderbook_fp") if isinstance(book, dict) else None
        price_check = {
            "checked": True,
            "ticker": ticker,
            "title": tonight[0].get("title"),
            "single_market_http": result["requests"][-2].get("status"),
            "orderbook_http": result["requests"][-1].get("status"),
            "yes_bid_dollars": (market or {}).get("yes_bid_dollars"),
            "yes_ask_dollars": (market or {}).get("yes_ask_dollars"),
            "last_price_dollars": (market or {}).get("last_price_dollars"),
            "orderbook_yes_levels": len((orderbook or {}).get("yes_dollars", [])),
            "orderbook_no_levels": len((orderbook or {}).get("no_dollars", [])),
        }
    kalshi_series["KXNBAGAME"]["price_check"] = price_check

    # --- Kalshi: NBA spread/total (events penuh + contoh pasar spread) ---
    spread_events: list[dict] = []
    total_events: list[dict] = []
    resp = client.get(
        f"{KALSHI_BASE}/events?series_ticker=KXNBASPREAD&status=open&limit=200"
    )
    result["requests"].append(_summarize(resp))
    spread_events = _items(parse_json_body(resp), "events")
    kalshi_series["KXNBASPREAD"] = {
        "label": "NBA spread",
        "exists": len(spread_events) > 0,
        "events_open": len(spread_events),
        "event_titles": [e.get("title") for e in spread_events[:10]],
    }
    resp = client.get(
        f"{KALSHI_BASE}/markets?series_ticker=KXNBASPREAD&status=open&limit=5"
    )
    result["requests"].append(_summarize(resp))
    spread_markets = _items(parse_json_body(resp), "markets")
    if spread_markets:
        kalshi_series["KXNBASPREAD"]["sample_markets"] = [
            {
                k: m.get(k)
                for k in (
                    "ticker",
                    "title",
                    "yes_bid_dollars",
                    "yes_ask_dollars",
                    "last_price_dollars",
                )
                if k in m
            }
            for m in spread_markets[:5]
        ]
    resp = client.get(
        f"{KALSHI_BASE}/events?series_ticker=KXNBATOTAL&status=open&limit=200"
    )
    result["requests"].append(_summarize(resp))
    total_events = _items(parse_json_body(resp), "events")
    kalshi_series["KXNBATOTAL"] = {
        "label": "NBA total",
        "exists": len(total_events) > 0,
        "events_open": len(total_events),
        "event_titles": [e.get("title") for e in total_events[:10]],
    }

    # --- Kalshi: EPL events + markets, uji series spread/total EPL ---
    epl_events: list[dict] = []
    resp = client.get(
        f"{KALSHI_BASE}/events?series_ticker=KXEPLGAME&status=open&limit=200"
    )
    result["requests"].append(_summarize(resp))
    epl_events = _items(parse_json_body(resp), "events")
    kalshi_series["KXEPLGAME"] = {
        "label": "EPL game (moneyline)",
        "exists": len(epl_events) > 0,
        "events_open": len(epl_events),
        "event_titles": [e.get("title") for e in epl_events[:30]],
    }
    resp = client.get(
        f"{KALSHI_BASE}/markets?series_ticker=KXEPLGAME&status=open&limit=200"
    )
    result["requests"].append(_summarize(resp))
    epl_markets = _items(parse_json_body(resp), "markets")
    kalshi_series["KXEPLGAME"]["markets_open"] = len(epl_markets)
    if epl_markets:
        kalshi_series["KXEPLGAME"]["sample_market"] = {
            k: epl_markets[0].get(k)
            for k in (
                "ticker",
                "event_ticker",
                "title",
                "yes_bid_dollars",
                "yes_ask_dollars",
                "last_price_dollars",
            )
            if k in epl_markets[0]
        }
        kalshi_series["KXEPLGAME"]["markets_priced"] = (
            f"{sum(1 for m in epl_markets if m.get('yes_bid_dollars') is not None and m.get('yes_ask_dollars') is not None)}"
            f"/{len(epl_markets)}"
        )
        # Berapa pasar per event? 1 = moneyline saja; >1 = ada jenis lain.
        from collections import Counter

        per_event = Counter(m.get("event_ticker") for m in epl_markets)
        kalshi_series["KXEPLGAME"]["markets_per_event"] = dict(
            Counter(per_event.values())
        )
    # --- Kalshi: EPL spread/total (events + markets penuh, untuk
    # pencocokan per garis dengan pasar jup.ag) ---
    epl_spread_events: list[dict] = []
    epl_spread_markets: list[dict] = []
    epl_total_events: list[dict] = []
    epl_total_markets: list[dict] = []
    for ticker, label in (
        ("KXEPLSPREAD", "EPL spread"),
        ("KXEPLTOTAL", "EPL total"),
    ):
        resp = client.get(
            f"{KALSHI_BASE}/events?series_ticker={ticker}&status=open&limit=200"
        )
        result["requests"].append(_summarize(resp))
        events = _items(parse_json_body(resp), "events")
        resp = client.get(
            f"{KALSHI_BASE}/markets?series_ticker={ticker}&status=open&limit=200"
        )
        result["requests"].append(_summarize(resp))
        markets = _items(parse_json_body(resp), "markets")
        kalshi_series[ticker] = {
            "label": label,
            "exists": len(events) > 0,
            "events_open": len(events),
            "markets_open": len(markets),
            "event_titles": [e.get("title") for e in events[:10]],
            "sample_markets": [
                {
                    k: m.get(k)
                    for k in ("ticker", "title", "yes_bid", "yes_ask")
                    if k in m
                }
                for m in markets[:4]
            ],
        }
        if ticker == "KXEPLSPREAD":
            epl_spread_events, epl_spread_markets = events, markets
        else:
            epl_total_events, epl_total_markets = events, markets

    # --- Kalshi: LaLiga events penuh ---
    laliga_events: list[dict] = []
    resp = client.get(
        f"{KALSHI_BASE}/events?series_ticker=KXLALIGAGAME&status=open&limit=200"
    )
    result["requests"].append(_summarize(resp))
    laliga_events = _items(parse_json_body(resp), "events")
    kalshi_series["KXLALIGAGAME"] = {
        "label": "LaLiga game (moneyline)",
        "exists": len(laliga_events) > 0,
        "events_open": len(laliga_events),
        "event_titles": [e.get("title") for e in laliga_events[:30]],
    }
    result["kalshi_series"] = kalshi_series

    # --- Pencocokan: pasar jup.ag vs padanan Kalshi ---
    kalshi_nba_titles = [e.get("title") or "" for e in nba_events]
    kalshi_epl_titles = [e.get("title") or "" for e in epl_events]
    kalshi_laliga_titles = [e.get("title") or "" for e in laliga_events]

    def _match_moneyline(
        games: list[dict], kalshi_titles: list[str], nba: bool
    ) -> dict:
        total = 0
        matched = 0
        matched_games: list[str] = []
        unmatched_games: list[str] = []
        for game in games:
            ml = [m for m in game["markets"] if m["type"] == "moneyline"]
            if not ml:
                continue
            is_match = any(
                (same_game_nba if nba else same_game_soccer)(game["title"], t)
                for t in kalshi_titles
            )
            total += len(ml)
            if is_match:
                matched += len(ml)
                matched_games.append(game["title"])
            else:
                unmatched_games.append(game["title"])
        return {
            "jup_markets": total,
            "matched": matched,
            "pct": round(100 * matched / total, 1) if total else None,
            "matched_games": matched_games,
            "unmatched_games": unmatched_games,
        }

    nba_ml = _match_moneyline(nba_games, kalshi_nba_titles, nba=True)
    epl_ml = _match_moneyline(epl_games, kalshi_epl_titles, nba=False)
    laliga_ml = _match_moneyline(laliga_games, kalshi_laliga_titles, nba=False)
    other_ml_total = sum(
        1 for g in other_soccer_games for m in g["markets"] if m["type"] == "moneyline"
    )

    # Spread/total: jup.ag NBA hari ini TIDAK punya pasar spread/total
    # (hanya moneyline), jadi pencocokan spread/total NBA = N/A.
    nba_spread_total_jup = sum(
        1 for g in nba_games for m in g["markets"] if m["type"] in ("spreads", "totals")
    )

    # Pencocokan EPL spread/total PER GARIS: jup.ag spread (tim, garis
    # mis. -1.5) padan dengan Kalshi "<Tim> wins by more than 1.5 goals?";
    # jup.ag totals (Over/Under, garis) padan dengan Kalshi "Will over X
    # goals be scored?" (Under = sisi No dari pasar Over yang sama).
    spread_event_titles = {
        e.get("event_ticker"): e.get("title") or "" for e in epl_spread_events
    }
    total_event_titles = {
        e.get("event_ticker"): e.get("title") or "" for e in epl_total_events
    }
    kalshi_spread_keys: set[tuple[frozenset, str, float]] = set()
    for market in epl_spread_markets:
        parsed = parse_kalshi_spread_title(market.get("title") or "")
        teams = parse_vs_title(
            _strip_series_suffix(
                spread_event_titles.get(market.get("event_ticker"), "")
            )
        )
        if parsed and teams:
            game_key = frozenset(normalize_soccer_team(t) for t in teams)
            kalshi_spread_keys.add((game_key, parsed[0], parsed[1]))
    kalshi_total_keys: set[tuple[frozenset, float]] = set()
    for market in epl_total_markets:
        line = parse_kalshi_total_title(market.get("title") or "")
        teams = parse_vs_title(
            _strip_series_suffix(total_event_titles.get(market.get("event_ticker"), ""))
        )
        if line is not None and teams:
            game_key = frozenset(normalize_soccer_team(t) for t in teams)
            kalshi_total_keys.add((game_key, line))
    epl_spread_total = 0
    epl_spread_matched = 0
    epl_total_total = 0
    epl_total_matched = 0
    kalshi_spread_lines: set[float] = set()
    kalshi_total_lines: set[float] = set()
    for _, _, line in kalshi_spread_keys:
        kalshi_spread_lines.add(line)
    for _, line in kalshi_total_keys:
        kalshi_total_lines.add(line)
    for game in epl_games:
        teams = parse_vs_title(game["title"])
        if teams is None:
            continue
        game_key = frozenset(normalize_soccer_team(t) for t in teams)
        for market in game["markets"]:
            line = _line_float(market.get("line"))
            if market["type"] == "spreads":
                epl_spread_total += 1
                team = normalize_soccer_team(market.get("title") or "")
                if (
                    line is not None
                    and (game_key, team, abs(line)) in kalshi_spread_keys
                ):
                    epl_spread_matched += 1
            elif market["type"] == "totals":
                epl_total_total += 1
                if line is not None and (game_key, line) in kalshi_total_keys:
                    epl_total_matched += 1
    # Likuiditas: berapa pasar Kalshi spread/total EPL yang punya bid+ask.
    priced_spread = sum(
        1
        for m in epl_spread_markets
        if m.get("yes_bid_dollars") is not None and m.get("yes_ask_dollars") is not None
    )
    priced_total = sum(
        1
        for m in epl_total_markets
        if m.get("yes_bid_dollars") is not None and m.get("yes_ask_dollars") is not None
    )

    result["matching"] = {
        "nba_moneyline": nba_ml,
        "epl_moneyline": epl_ml,
        "laliga_moneyline": laliga_ml,
        "other_soccer_moneyline": {
            "jup_markets": other_ml_total,
            "matched": 0,
            "note": "tidak ada series Kalshi untuk liga-liga ini di slate "
            "hari ini (Bundesliga, Serie A, Ligue 1, UCL, dll. — di luar "
            "cakupan probe; hanya EPL + LaLiga yang diuji)",
        },
        "nba_spreads_totals": {
            "jup_markets": nba_spread_total_jup,
            "note": "jup.ag TIDAK punya pasar spread/total NBA di slate "
            "ini (hanya moneyline) — pencocokan N/A, walau Kalshi punya "
            "series KXNBASPREAD + KXNBATOTAL",
            "kalshi_spread_events": len(spread_events),
            "kalshi_total_events": len(total_events),
        },
        "epl_spreads": {
            "jup_markets": epl_spread_total,
            "matched": epl_spread_matched,
            "pct": (
                round(100 * epl_spread_matched / epl_spread_total, 1)
                if epl_spread_total
                else None
            ),
            "kalshi_lines": sorted(kalshi_spread_lines),
            "kalshi_markets_priced": f"{priced_spread}/{len(epl_spread_markets)}",
            "note": "Kalshi hanya punya garis 1.5/2.5 (lihat kalshi_lines) "
            "— pasar jup.ag di garis lain tidak punya padanan",
        },
        "epl_totals": {
            "jup_markets": epl_total_total,
            "matched": epl_total_matched,
            "pct": (
                round(100 * epl_total_matched / epl_total_total, 1)
                if epl_total_total
                else None
            ),
            "kalshi_lines": sorted(kalshi_total_lines),
            "kalshi_markets_priced": f"{priced_total}/{len(epl_total_markets)}",
            "note": "Kalshi hanya punya pasar Over (Under = sisi No); "
            "garis Kalshi 0.5-5.5, jup.ag sampai 8.5",
        },
    }

    total_ml = nba_ml["jup_markets"] + epl_ml["jup_markets"] + laliga_ml["jup_markets"]
    total_matched = nba_ml["matched"] + epl_ml["matched"] + laliga_ml["matched"]
    result["accessible_from_vm"] = len(nba_events) > 0 or len(nba_markets) > 0
    result["format"] = "JSON REST" if result["accessible_from_vm"] else None
    result["rate_limit"] = "UNKNOWN (tidak ada header rate limit yang terlihat)"
    for req in result["requests"]:
        headers = req.get("rate_limit_headers") or {}
        if headers:
            result["rate_limit"] = f"header: {headers}"
    result["data_available"] = [
        f"NBA moneyline: {nba_ml['matched']}/{nba_ml['jup_markets']} pasar "
        "jup.ag tercocokkan di Kalshi",
        f"EPL moneyline: {epl_ml['matched']}/{epl_ml['jup_markets']} pasar "
        "jup.ag tercocokkan di Kalshi",
        f"LaLiga moneyline: {laliga_ml['matched']}/{laliga_ml['jup_markets']} "
        "pasar jup.ag tercocokkan di Kalshi",
        f"EPL spreads: {epl_spread_matched}/{epl_spread_total} pasar jup.ag "
        "tercocokkan per garis di Kalshi",
        f"EPL totals: {epl_total_matched}/{epl_total_total} pasar jup.ag "
        "tercocokkan per garis di Kalshi",
        f"Kalshi NBA spread: {len(spread_events)} event, "
        f"total: {len(total_events)} event (jup.ag NBA tanpa spread/total)",
    ]
    if total_ml and total_matched == total_ml:
        result["verdict"] = "PAKAI"
    elif total_matched > 0:
        result["verdict"] = "CADANGAN"
        result["unknown"].append("cakupan Kalshi tidak penuh (lihat matching)")
    else:
        result["verdict"] = "JANGAN"
        result["unknown"].append("tidak ada pasar jup.ag yang tercocokkan")
    result["risk_notes"] = [
        "Pencocokan berdasarkan nama tim (normalisasi + pemetaan julukan "
        "NBA + alias bola) — bukan ID resmi; fetcher 2b wajib memvalidasi "
        "pasangan event sebelum memakai harga Kalshi sebagai pembanding.",
        "Kalshi EPL punya spread/total tapi garisnya terbatas (spread "
        "1.5/2.5, total Over 0.5-5.5) — pasar jup.ag di luar garis itu "
        "tetap butuh pembanding sportsbook (Odds API / ESPN odds). "
        "LaLiga spread/total tidak diuji di probe ini.",
        "Field harga Kalshi bernama *_dollars (string dolar, mis. "
        "'0.1200') — nama lama yes_bid/yes_ask TIDAK ADA di API ini; "
        "fetcher 2b wajib memakai *_dollars (lihat price_check).",
        "Pasar Kalshi tanpa bid/ask (lihat kalshi_markets_priced) harus "
        "ditolak fetcher 2b, bukan memakai last_price basi.",
        "Harga Kalshi (yes_bid_dollars/yes_ask_dollars, string dolar) vs "
        "harga jup.ag: selisihnya adalah pembanding, BUKAN edge langsung — "
        "perlu devig/blend Tahap 3.",
    ]
    return result


def _items(data: dict | list | None, key: str) -> list:
    """Ambil list item dari respons JSON Kalshi (atau [] bila tidak ada)."""
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return data[key]
    return []


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
    path = write_result("kalshi_sports", result)
    print(f"probe kalshi_sports: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
