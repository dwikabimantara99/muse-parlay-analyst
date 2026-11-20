"""Probe jup_markup — Tahap 2a lanjutan (muse-parlay-analyst).

Bandingkan harga jup.ag vs midpoint orderbook Polymarket (CLOB) untuk pasar
yang SAMA. Ini BUKAN edge — ini mengukur biaya tambahan jup.ag (DECISIONS.md:
jup_markup dicatat per pasar).

Pencocokan lewat clobTokenIds yang dibawa tiap pasar jup.ag. Token Yes yang
benar dipilih dari indeks judul pasar di dalam `outcomes` (pasar 2-outcome
seperti moneyline NBA MEMBAGI satu pasangan token: pasar tim kedua memakai
token [1], bukan [0] — memakai [0] untuk keduanya menghasilkan markup
palsu ~15-37¢, sudah dibuktikan di run pertama probe ini).
Slate jup.ag dipakai ulang dari cache probe 2a (bila masih segar).

Sampel deterministik, maks 12 pasar: 2 laga NBA (moneyline, 4 pasar),
1 laga EPL moneyline (3 pasar), 1 laga EPL totals 2.5 (Over+Under),
1 laga EPL spreads ±1.5 (2 pasar).

Dijalankan sendiri: python3 probes/jup_markup.py
Menulis probes/out/jup_markup.json.
"""

from __future__ import annotations

import statistics
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

CLOB_BASE = "https://clob.polymarket.com"
MAX_MARKETS = 12


def micro_usd_to_cents(value: int | float | None) -> float | None:
    """Ubah harga micro-USD (jup.ag) jadi ¢. None bila input bukan angka."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return value / 10000.0


def line_as_float(value: object) -> float | None:
    """Ubah sportsLine (string '2.5' / angka / None) jadi float."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def yes_token_id(market: dict) -> tuple[str | None, int | None, str]:
    """Pilih token Yes Polymarket untuk satu pasar jup.ag.

    Aturan: cari indeks judul pasar (atau nama tim) di dalam `outcomes`;
    token Yes = clobTokenIds[indeks]. Bila judul tidak ada di outcomes
    (pasar biner mandiri, outcomes = ["Yes", "No"]), pakai [0].
    Mengembalikan (token_id, indeks, cara_pemilihan).
    """
    tokens = market.get("clobTokenIds") or []
    outcomes = market.get("outcomes") or []
    title = market.get("title")
    team = (market.get("team") or {}).get("name")
    for candidate in (title, team):
        if candidate and candidate in outcomes:
            index = outcomes.index(candidate)
            if index < len(tokens):
                return tokens[index], index, "indeks judul di outcomes"
    if tokens:
        return tokens[0], 0, "fallback [0] (judul tidak ada di outcomes)"
    return None, None, "tidak ada clobTokenIds"


def book_midpoint(book: dict | None) -> float | None:
    """Midpoint orderbook CLOB dalam ¢ (0-100).

    Midpoint = (bid terbaik + ask terbaik) / 2. Mengembalikan None bila
    sisi bid atau ask kosong / harga tidak valid.
    """
    if not isinstance(book, dict):
        return None
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    try:
        best_bid = max(float(b["price"]) for b in bids)
        best_ask = min(float(a["price"]) for a in asks)
    except (KeyError, TypeError, ValueError):
        return None
    if not (0.0 <= best_bid <= 1.0 and 0.0 <= best_ask <= 1.0):
        return None
    return (best_bid + best_ask) / 2.0 * 100.0


def book_spread(book: dict | None) -> float | None:
    """Lebar bid-ask orderbook CLOB dalam ¢. None bila tidak valid."""
    if not isinstance(book, dict):
        return None
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    try:
        best_bid = max(float(b["price"]) for b in bids)
        best_ask = min(float(a["price"]) for a in asks)
    except (KeyError, TypeError, ValueError):
        return None
    if not (0.0 <= best_bid <= 1.0 and 0.0 <= best_ask <= 1.0):
        return None
    return (best_ask - best_bid) * 100.0


def compute_markup(jup_buy_cents: float, midpoint_cents: float) -> float:
    """jup_markup (¢) = harga beli jup.ag − midpoint Polymarket."""
    return jup_buy_cents - midpoint_cents


def _select_sample(events: list[dict]) -> list[dict]:
    """Pilih sampel pasar deterministik dari slate jup.ag (maks 12)."""
    sample: list[dict] = []

    def _add(event: dict, market: dict, note: str) -> None:
        if len(sample) >= MAX_MARKETS:
            return
        sample.append(
            {
                "event_title": (event.get("metadata") or {}).get("title"),
                "event_id": event.get("eventId"),
                "market_id": market.get("marketId"),
                "market_title": market.get("title"),
                "team_name": (market.get("team") or {}).get("name"),
                "type": market.get("sportsMarketType"),
                "line": market.get("sportsLine"),
                "outcomes": market.get("outcomes") or [],
                "buy_yes_micro_usd": (market.get("pricing") or {}).get(
                    "buyYesPriceUsd"
                ),
                "sell_yes_micro_usd": (market.get("pricing") or {}).get(
                    "sellYesPriceUsd"
                ),
                "clob_token_ids": market.get("clobTokenIds") or [],
                "note": note,
            }
        )

    nba_games = [
        e
        for e in events
        if e.get("subcategory") == "nba" and len(e.get("markets", [])) == 2
    ]
    for event in nba_games[:2]:
        for market in event.get("markets", []):
            _add(event, market, "NBA moneyline")

    epl_games = [
        e
        for e in events
        if e.get("subcategory") == "epl" and len(e.get("markets", [])) > 50
    ]
    if epl_games:
        first = epl_games[0]
        for market in first.get("markets", []):
            if market.get("sportsMarketType") == "moneyline":
                _add(first, market, "EPL moneyline")
        for market in first.get("markets", []):
            if (
                market.get("sportsMarketType") == "totals"
                and line_as_float(market.get("sportsLine")) == 2.5
            ):
                _add(first, market, "EPL totals 2.5")
        seen_spreads: set[tuple[str | None, float | None]] = set()
        for market in first.get("markets", []):
            line = line_as_float(market.get("sportsLine"))
            key = (market.get("title"), line)
            if (
                market.get("sportsMarketType") == "spreads"
                and line in (1.5, -1.5)
                and key not in seen_spreads
            ):
                seen_spreads.add(key)
                _add(first, market, "EPL spreads ±1.5")
    return sample


def probe() -> dict:
    """Jalankan probe jup_markup; kembalikan dict hasil."""
    result = new_result("jup_markup (jup.ag vs Polymarket CLOB)", tier=2)
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(1.5), cache=cache)

    # --- Slate jup.ag (dari cache 2a bila segar) ---
    env = load_dotenv(repo_root())
    jupiter = JupiterClient(env.get("JUPITER_API_KEY") or None, cache=cache)
    jup_resp = jupiter.get("/events", {"category": "sports", "limit": "100"})
    result["requests"].append(_summarize(jup_resp))
    jup_data = parse_json_body(jup_resp)
    events = jup_data.get("data", []) if isinstance(jup_data, dict) else []
    sample = _select_sample(events)
    result["sample_size"] = len(sample)
    result["jupiter_from_cache"] = bool(jup_resp.get("from_cache"))

    # --- Midpoint CLOB per pasar sampel ---
    per_market: list[dict] = []
    markups: list[float] = []
    for entry in sample:
        record = {
            k: v for k, v in entry.items() if k not in ("clob_token_ids", "outcomes")
        }
        token_id, token_index, how = yes_token_id(
            {
                "title": entry["market_title"],
                "team": {"name": entry["team_name"]},
                "outcomes": entry["outcomes"],
                "clobTokenIds": entry["clob_token_ids"],
            }
        )
        record["token_id"] = token_id
        record["token_index"] = token_index
        record["token_selection"] = how
        jup_buy = micro_usd_to_cents(entry["buy_yes_micro_usd"])
        jup_sell = micro_usd_to_cents(entry["sell_yes_micro_usd"])
        record["jup_buy_yes_cents"] = jup_buy
        record["jup_sell_yes_cents"] = jup_sell
        record["jup_spread_cents"] = (
            round(jup_buy - jup_sell, 3)
            if jup_buy is not None and jup_sell is not None
            else None
        )
        midpoint = None
        clob_spread = None
        midpoint_source = None
        if token_id and jup_buy is not None:
            resp = client.get(f"{CLOB_BASE}/book?token_id={token_id}")
            result["requests"].append(_summarize(resp))
            book = parse_json_body(resp)
            midpoint = book_midpoint(book if isinstance(book, dict) else None)
            clob_spread = book_spread(book if isinstance(book, dict) else None)
            if midpoint is not None:
                midpoint_source = "book"
            else:
                # Fallback: endpoint midpoint langsung (1 request ekstra).
                resp2 = client.get(f"{CLOB_BASE}/midpoint?token_id={token_id}")
                result["requests"].append(_summarize(resp2))
                data2 = parse_json_body(resp2)
                if isinstance(data2, dict) and data2.get("mid") is not None:
                    try:
                        midpoint = float(data2["mid"]) * 100.0
                        midpoint_source = "midpoint"
                    except (TypeError, ValueError):
                        midpoint = None
        record["midpoint_cents"] = round(midpoint, 3) if midpoint is not None else None
        record["clob_spread_cents"] = (
            round(clob_spread, 3) if clob_spread is not None else None
        )
        record["midpoint_source"] = midpoint_source
        if midpoint is not None and jup_buy is not None:
            record["jup_markup_cents"] = round(compute_markup(jup_buy, midpoint), 3)
            markups.append(record["jup_markup_cents"])
        else:
            record["jup_markup_cents"] = None
            record["unmatched_reason"] = (
                "tidak ada clobTokenIds"
                if not token_id
                else (
                    "harga jup.ag tidak ada"
                    if jup_buy is None
                    else "orderbook kosong / midpoint tidak didapat"
                )
            )
        per_market.append(record)
    result["per_market"] = per_market

    n_matched = len(markups)
    n_unmatched = len(per_market) - n_matched
    result["summary"] = {
        "n_sampled": len(sample),
        "n_matched": n_matched,
        "n_unmatched": n_unmatched,
        "median_markup_cents": (
            round(statistics.median(markups), 3) if markups else None
        ),
        "mean_markup_cents": round(statistics.mean(markups), 3) if markups else None,
        "min_markup_cents": round(min(markups), 3) if markups else None,
        "max_markup_cents": round(max(markups), 3) if markups else None,
        "unmatched_reasons": sorted(
            {
                r.get("unmatched_reason", "?")
                for r in per_market
                if r.get("jup_markup_cents") is None
            }
        ),
    }
    result["accessible_from_vm"] = n_matched > 0
    result["format"] = "JSON REST" if n_matched > 0 else None
    result["rate_limit"] = "UNKNOWN (tidak ada header rate limit yang terlihat)"
    if n_matched >= len(sample) // 2 and n_matched > 0:
        result["data_available"] = [
            f"{n_matched}/{len(sample)} pasar tercocokkan dengan midpoint CLOB",
            f"median jup_markup: {result['summary']['median_markup_cents']}¢ "
            f"(min {result['summary']['min_markup_cents']}¢, "
            f"max {result['summary']['max_markup_cents']}¢)",
            "jup_markup per pasar tersimpan di per_market (field "
            "jup_markup_cents); lebar bid-ask CLOB di clob_spread_cents",
        ]
        result["verdict"] = "PAKAI"
    elif n_matched > 0:
        result["verdict"] = "CADANGAN"
        result["unknown"].append("sebagian pasar tak tercocokkan (lihat summary)")
    else:
        result["verdict"] = "JANGAN"
        result["unknown"].append("tidak ada pasar yang tercocokkan")
    result["risk_notes"] = [
        "jup_markup BUKAN edge — ini biaya tambahan jup.ag vs Polymarket; "
        "jangan dipakai sebagai sinyal beli.",
        "Midpoint CLOB dan harga jup.ag diambil pada jam yang sedikit "
        "berbeda (jup.ag dari cache 2a) — markup mengandung selisih waktu; "
        "fetcher 2b/3 harus mengambil keduanya sedekat mungkin.",
        "Harga jup.ag yang dipakai = buyYes (ask); midpoint = tengah "
        "bid/ask Polymarket — definisi ini dicatat agar konsisten. "
        "Bandingkan jup_markup dengan setengah lebar CLOB "
        "(clob_spread_cents / 2): bila keduanya mirip, jup.ag praktis "
        "tidak menambah biaya di atas spread Polymarket.",
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
    path = write_result("jup_markup", result)
    print(f"probe jup_markup: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
