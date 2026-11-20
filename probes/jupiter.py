"""Probe Jupiter Prediction API — Tahap 2a (muse-parlay-analyst).

Mode keyed (JUPITER_API_KEY dari .env, 1 RPS) dengan fallback keyless
(0,5 RPS) bila key ditolak. HANYA endpoint baca GET. Maks 4 request:
daftar event sports, pencarian, detail satu event, detail satu pasar.

Dijalankan sendiri: python3 probes/jupiter.py
Menulis probes/out/jupiter.json.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    DiskCache,
    JupiterClient,
    load_dotenv,
    new_result,
    out_dir,
    parse_json_body,
    repo_root,
    write_result,
)


def probe() -> dict:
    """Jalankan probe Jupiter; kembalikan dict hasil."""
    result = new_result("Jupiter Prediction API", tier=1)
    env = load_dotenv(repo_root())
    api_key = env.get("JUPITER_API_KEY") or None
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = JupiterClient(api_key, cache=cache)

    result["api_key_present"] = api_key is not None
    counts: Counter[tuple[str, str]] = Counter()
    lines: dict[str, list] = {}
    events_total = 0
    markets_total = 0

    # 1. Daftar event sports.
    resp = client.get("/events", {"category": "sports", "limit": "100"})
    result["requests"].append(_summarize(resp))
    data = parse_json_body(resp)
    events = data.get("data", []) if isinstance(data, dict) else []
    events_total = len(events)
    first_event_id = None
    first_market_id = None
    for event in events:
        if first_event_id is None:
            first_event_id = event.get("eventId")
        for market in event.get("markets", []):
            markets_total += 1
            if first_market_id is None:
                first_market_id = market.get("marketId")
            provider = market.get("provider") or "UNKNOWN"
            mtype = market.get("sportsMarketType") or "null"
            counts[(provider, mtype)] += 1
            line = market.get("sportsLine")
            if line is not None:
                lines.setdefault(mtype, []).append(line)

    # 2. Pencarian event.
    resp = client.get("/events/search", {"query": "NBA"})
    result["requests"].append(_summarize(resp))
    search_data = parse_json_body(resp)
    search_n = None
    if isinstance(search_data, dict):
        found = search_data.get("data")
        search_n = len(found) if isinstance(found, list) else None

    # 3. Detail satu event (bila ada).
    if first_event_id:
        resp = client.get(f"/events/{first_event_id}")
        result["requests"].append(_summarize(resp))

    # 4. Detail satu pasar (bila ada).
    if first_market_id:
        resp = client.get(f"/markets/{first_market_id}")
        result["requests"].append(_summarize(resp))

    result["mode_used"] = client.mode_used
    result["fallback_used"] = client.fallback_used
    result["events_returned"] = events_total
    result["markets_returned"] = markets_total
    result["search_nba_results"] = search_n
    result["provider_by_market_type"] = {
        f"{provider} | {mtype}": n for (provider, mtype), n in sorted(counts.items())
    }
    result["sports_line_samples"] = {
        mtype: sorted(set(values))[:5] for mtype, values in sorted(lines.items())
    }
    first = result["requests"][0] if result["requests"] else {}
    ok = first.get("status") == 200 and events_total > 0
    result["accessible_from_vm"] = bool(ok)
    result["format"] = "JSON REST" if ok else None
    result["rate_limit"] = (
        "keyed 1 RPS (jeda 1,1 dtk); fallback keyless 0,5 RPS (jeda 2,2 dtk)"
        if api_key
        else "keyless 0,5 RPS (jeda 2,2 dtk); tidak ada key di .env"
    )
    if ok:
        result["data_available"] = [
            "event sports + pasar (moneyline, spreads, totals, BTTS, dll.)",
            "sportsMarketType + sportsLine per pasar",
            "provider asal per pasar (polymarket/kalshi)",
            "harga beli/jual Yes/No per pasar (micro-USD)",
            "pencarian event + detail event/pasar",
        ]
        result["verdict"] = "PAKAI"
    else:
        result["verdict"] = "JANGAN"
        result["unknown"].append("alasan kegagalan event sports (lihat requests)")
    result["risk_notes"] = [
        "API masih beta (bisa berubah tanpa pemberitahuan).",
        "HANYA BACA: endpoint order/posisi/claim dilarang (DECISIONS.md K3).",
    ]
    return result


def _summarize(resp: dict) -> dict:
    """Ringkasan satu request untuk evidence (tanpa header sensitif)."""
    return {
        "url": resp.get("url"),
        "status": resp.get("status"),
        "mode": resp.get("mode"),
        "from_cache": resp.get("from_cache"),
        "elapsed_seconds": resp.get("elapsed_seconds"),
        "rate_limit_headers": resp.get("rate_limit_headers"),
        "error": resp.get("error"),
        "body_sample": str(resp.get("body") or "")[:500],
    }


def main() -> int:
    """Jalankan probe dan tulis hasilnya; kembalikan exit code."""
    result = probe()
    path = write_result("jupiter", result)
    print(f"probe jupiter: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
