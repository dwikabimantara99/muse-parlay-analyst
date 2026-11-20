"""Probe ESPN odds — Tahap 2a lanjutan (muse-parlay-analyst).

Apakah scoreboard/summary ESPN memuat garis sportsbook (moneyline, spread,
total) + provider-nya? Ini kandidat pembanding p_market gratis kedua
(devig), setelah The Odds API (DECISIONS.md: urutan pembanding).

Maks 3 request BARU: scoreboard NBA besok (laga yang akan datang),
summary 1 laga NBA, summary 1 laga EPL. Scoreboard NBA + EPL hari ini
dipakai ulang dari cache probe 2a (bila masih segar).

Dijalankan sendiri: python3 probes/espn_odds.py
Menulis probes/out/espn_odds.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    DiskCache,
    HttpClient,
    RateLimiter,
    new_result,
    out_dir,
    parse_json_body,
    write_result,
)

NBA_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
)
EPL_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"
# Slate NBA "besok" (UTC) = laga malam ini waktu AS (belum mulai).
NBA_SCOREBOARD_TOMORROW = NBA_SCOREBOARD + "?dates=20261121"
NBA_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"
EPL_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/summary"


def american_to_implied_prob(odds: str | None) -> float | None:
    """Ubah odds Amerika ("-260", "+650") jadi probabilitas implisit.

    Mengembalikan None bila input bukan string odds Amerika yang valid.
    Tidak ada devig di sini — itu urusan Tahap 3.
    """
    if not isinstance(odds, str) or not odds:
        return None
    try:
        value = int(odds)
    except ValueError:
        return None
    if value == 0:
        return None
    if value < 0:
        return -value / (-value + 100.0)
    return 100.0 / (value + 100.0)


def parse_odds_entry(entry: dict) -> dict:
    """Ubah satu entri odds ESPN jadi struktur ringkas (odds 'close').

    Field yang tidak ada dicatat None (bukan ditebak). Odds mentah disimpan
    apa adanya (string Amerika); probabilitas implisit dihitung terpisah.
    """
    provider = entry.get("provider") or {}
    moneyline = entry.get("moneyline") or {}
    spread = entry.get("pointSpread") or {}
    total = entry.get("total") or {}

    def _close(section: dict, side: str) -> dict | None:
        node = section.get(side) or {}
        close = node.get("close")
        return close if isinstance(close, dict) else None

    ml_home = _close(moneyline, "home")
    ml_away = _close(moneyline, "away")
    ml_draw = _close(moneyline, "draw")
    sp_home = _close(spread, "home")
    sp_away = _close(spread, "away")
    tot_over = _close(total, "over")
    tot_under = _close(total, "under")

    # Bentuk kedua (mis. Bet 365 di summary): moneyline desimal di
    # homeTeamOdds/awayTeamOdds (odds.value, bersarang) dan drawOdds
    # (value langsung, tidak bersarang) — tanpa spread/total.
    def _decimal(node: dict | None) -> float | None:
        if not isinstance(node, dict):
            return None
        odds = node.get("odds")
        value = odds.get("value") if isinstance(odds, dict) else node.get("value")
        return value if isinstance(value, (int, float)) else None

    return {
        "provider": provider.get("name"),
        "over_under": entry.get("overUnder"),
        "moneyline": {
            "home": ml_home.get("odds") if ml_home else None,
            "away": ml_away.get("odds") if ml_away else None,
            "draw": ml_draw.get("odds") if ml_draw else None,
        },
        "moneyline_decimal": {
            "home": _decimal(entry.get("homeTeamOdds")),
            "away": _decimal(entry.get("awayTeamOdds")),
            "draw": _decimal(entry.get("drawOdds")),
        },
        "spread": {
            "home_line": sp_home.get("line") if sp_home else None,
            "home_odds": sp_home.get("odds") if sp_home else None,
            "away_line": sp_away.get("line") if sp_away else None,
            "away_odds": sp_away.get("odds") if sp_away else None,
        },
        "total": {
            "over_line": tot_over.get("line") if tot_over else None,
            "over_odds": tot_over.get("odds") if tot_over else None,
            "under_line": tot_under.get("line") if tot_under else None,
            "under_odds": tot_under.get("odds") if tot_under else None,
        },
        "details": entry.get("details"),
    }


def _analyze_scoreboard(data: dict | list | None, label: str) -> dict:
    """Hitung cakupan odds di satu respons scoreboard."""
    events = data.get("events") if isinstance(data, dict) else None
    if not isinstance(events, list):
        return {
            "label": label,
            "events": 0,
            "with_odds": 0,
            "error": "bukan JSON event",
        }
    with_odds = 0
    providers: set[str] = set()
    completeness = {"moneyline": 0, "spread": 0, "total": 0}
    examples: list[dict] = []
    first_event_id = None
    for event in events:
        if first_event_id is None:
            first_event_id = event.get("id")
        for comp in event.get("competitions", []):
            odds_list = comp.get("odds") or []
            if not odds_list:
                continue
            with_odds += 1
            parsed = parse_odds_entry(odds_list[0])
            if parsed["provider"]:
                providers.add(parsed["provider"])
            if parsed["moneyline"]["home"] and parsed["moneyline"]["away"]:
                completeness["moneyline"] += 1
            if parsed["spread"]["home_line"] and parsed["spread"]["away_line"]:
                completeness["spread"] += 1
            if parsed["total"]["over_line"] and parsed["total"]["under_line"]:
                completeness["total"] += 1
            if len(examples) < 1:
                examples.append({"event": event.get("name"), "odds": parsed})
    return {
        "label": label,
        "events": len(events),
        "with_odds": with_odds,
        "providers": sorted(providers),
        "completeness": completeness,
        "first_event_id": first_event_id,
        "example": examples[0] if examples else None,
    }


def probe() -> dict:
    """Jalankan probe ESPN odds; kembalikan dict hasil."""
    result = new_result("ESPN odds (scoreboard/summary)", tier=2)
    cache = DiskCache(out_dir() / "cache", ttl_seconds=3600)
    client = HttpClient(RateLimiter(2.0), cache=cache)
    boards: list[dict] = []

    # 1-2. Scoreboard hari ini (dipakai ulang dari cache 2a bila segar).
    for url, label in (
        (NBA_SCOREBOARD, "NBA scoreboard hari ini"),
        (EPL_SCOREBOARD, "EPL scoreboard hari ini"),
    ):
        resp = client.get(url)
        result["requests"].append(_summarize(resp))
        boards.append(_analyze_scoreboard(parse_json_body(resp), label))

    # 3. Scoreboard NBA besok (laga yang akan datang — odds biasanya ada
    # sebelum laga, hilang setelah selesai).
    resp = client.get(NBA_SCOREBOARD_TOMORROW)
    result["requests"].append(_summarize(resp))
    tomorrow = _analyze_scoreboard(parse_json_body(resp), "NBA scoreboard besok")
    boards.append(tomorrow)

    # 4. Summary 1 laga NBA yang akan datang (bila ada).
    summary_nba: dict | None = None
    if tomorrow.get("first_event_id"):
        url = f"{NBA_SUMMARY}?event={tomorrow['first_event_id']}"
        resp = client.get(url)
        result["requests"].append(_summarize(resp))
        data = parse_json_body(resp)
        summary_nba = _analyze_summary(data, "NBA summary")

    # 5. Summary 1 laga EPL (dari scoreboard hari ini).
    summary_epl: dict | None = None
    epl_first = boards[1].get("first_event_id")
    if epl_first:
        url = f"{EPL_SUMMARY}?event={epl_first}"
        resp = client.get(url)
        result["requests"].append(_summarize(resp))
        data = parse_json_body(resp)
        summary_epl = _analyze_summary(data, "EPL summary")

    result["scoreboards"] = boards
    result["summary_nba"] = summary_nba
    result["summary_epl"] = summary_epl

    total_events = sum(b.get("events", 0) for b in boards)
    total_with_odds = sum(b.get("with_odds", 0) for b in boards)
    result["accessible_from_vm"] = total_events > 0
    result["format"] = "JSON REST" if total_events > 0 else None
    result["rate_limit"] = "UNKNOWN (tidak ada header rate limit yang terlihat)"
    if total_with_odds > 0:
        providers = sorted({p for b in boards for p in b.get("providers", [])})
        result["data_available"] = [
            f"scoreboard: {total_with_odds}/{total_events} event punya odds",
            f"provider odds: {', '.join(providers) or 'UNKNOWN'}",
            "field odds: moneyline (home/away/draw), pointSpread "
            "(home/away, line + odds), total (over/under, line + odds), "
            "overUnder; odds 'open' + 'close', format Amerika",
        ]
    # Verdict: PAKAI bila odds lengkap (ML + spread + total) tersedia untuk
    # laga yang akan datang di minimal satu cabang; CADANGAN bila hanya
    # sebagian; JANGAN bila tidak ada odds sama sekali.
    upcoming = boards[2] if len(boards) > 2 else {}
    upcoming_full = (
        upcoming.get("with_odds", 0) > 0
        and upcoming.get("completeness", {}).get("moneyline", 0) > 0
        and upcoming.get("completeness", {}).get("spread", 0) > 0
        and upcoming.get("completeness", {}).get("total", 0) > 0
    )
    epl_full = (
        boards[1].get("with_odds", 0) > 0
        and boards[1].get("completeness", {}).get("moneyline", 0) > 0
        and boards[1].get("completeness", {}).get("spread", 0) > 0
        and boards[1].get("completeness", {}).get("total", 0) > 0
    )
    if upcoming_full or epl_full:
        result["verdict"] = "PAKAI"
    elif total_with_odds > 0:
        result["verdict"] = "CADANGAN"
        result["unknown"].append("odds ada tapi tidak lengkap (lihat scoreboards)")
    else:
        result["verdict"] = "JANGAN"
    result["risk_notes"] = [
        "Provider odds yang terlihat hanya satu (lihat scoreboards) — "
        "devig dari satu sportsbook saja, bukan konsensus pasar.",
        "Odds di scoreboard bisa hilang setelah laga selesai (NBA hari ini: "
        "0/4, semua laga sudah post) — fetcher 2b harus menarik SEBELUM laga.",
        "Odds format Amerika (string) — perlu konversi ke probabilitas "
        "implisit + devig di Tahap 3.",
    ]
    return result


def _analyze_summary(data: dict | list | None, label: str) -> dict:
    """Cek apakah respons summary memuat odds (semua provider dicatat)."""
    if not isinstance(data, dict):
        return {"label": label, "has_odds": False, "error": "bukan JSON"}
    odds = data.get("odds")
    location = "odds"
    if not (isinstance(odds, list) and odds):
        # Summary kadang menaruh odds di dalam header/competitions.
        header = data.get("header") or {}
        competitions = header.get("competitions") or []
        for comp in competitions:
            comp_odds = comp.get("odds") or []
            if comp_odds:
                odds = comp_odds
                location = "header.competitions"
                break
    if not (isinstance(odds, list) and odds):
        return {
            "label": label,
            "has_odds": False,
            "odds_field": data.get("odds"),
            "top_keys": sorted(data.keys())[:12],
        }
    providers = []
    for entry in odds:
        parsed = parse_odds_entry(entry)
        has_ml_american = bool(
            parsed["moneyline"]["home"] and parsed["moneyline"]["away"]
        )
        has_ml_decimal = bool(
            parsed["moneyline_decimal"]["home"] and parsed["moneyline_decimal"]["away"]
        )
        providers.append(
            {
                "provider": parsed["provider"],
                "has_moneyline": has_ml_american or has_ml_decimal,
                "moneyline_format": (
                    "american"
                    if has_ml_american
                    else "decimal" if has_ml_decimal else None
                ),
                "has_spread": bool(
                    parsed["spread"]["home_line"] and parsed["spread"]["away_line"]
                ),
                "has_total": bool(
                    parsed["total"]["over_line"] and parsed["total"]["under_line"]
                ),
                "entry_keys": sorted(entry.keys()),
            }
        )
    return {
        "label": label,
        "has_odds": True,
        "n_odds_entries": len(odds),
        "location": location,
        "providers": providers,
        "example": parse_odds_entry(odds[0]),
    }


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
    path = write_result("espn_odds", result)
    print(f"probe espn_odds: {result['verdict']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
