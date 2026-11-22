"""Cek pasar spread/total NBA di jup.ag (Tahap 2b).

Probe tambahan menemukan 0 pasar NBA spread/total di 100 event pertama
jup.ag, padahal Alt Under NBA adalah pasar utama user. Script ini
memindai SEMUA event sports Jupiter (fetch berpaginasi), memfilter event
NBA, dan melaporkan per laga: ada/tidak pasar spread/total, jumlah
pasar, garis-garisnya, dan jam tip-off.

KOREKSI 2026-11-22 (Tahap 3 Langkah 1): API jup.ag hanya menampilkan 2
pasar moneyline per event — putusan "ada/tidak spread/total" dari API
jup.ag saja SALAH (6 pemindaian 0 pasar padahal UI jup.ag menampilkan
spread/total lengkap dari Polymarket). Sejak koreksi ini, tiap laga
juga dicek tangganya di Polymarket Gamma (resolve slug dari metadata
event jup.ag -> fetch event -> hitung pasar spread/total); putusan
has_spread/has_total adalah gabungan (jup.ag ATAU Polymarket), dan
angka jup.ag-only tetap tersimpan terpisah (spread_markets /
total_markets per laga, games_with_spread_jup / games_with_total_jup
agregat). Laga yang slug-nya tidak ada di metadata atau fetch
Gamma-nya gagal dicatat apa adanya (poly_checked False + poly_error)
— bukan dianggap tidak punya pasar.

Jalankan: python -m ingest.check_nba_lines [--date YYYY-MM-DD] [--out PATH]

--date: hanya laga dengan tip-off pada tanggal UTC itu (bila tidak
  diisi: semua laga NBA). --out: path laporan JSON (default
  out/nba_lines_check_<timestamp>.json). Ringkasan dicetak ke stdout.

Pasar spread/total yang dihitung HANYA sportsMarketType persis
"spreads"/"totals" (full game); pasar paruh waktu (first_half_*,
second_half_*) tidak dihitung. Pasar mungkin baru dibuka dekat
tip-off — recheck_schedule menghitung jam cek ulang 3 jam dan 1 jam
sebelum tip-off tiap laga.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ingest import polymarket
from ingest.common import now_iso, repo_root
from ingest.jupiter import fetch_sports_events
from ingest.matching import parse_vs_title


def _tip_off_iso(event: dict) -> str | None:
    """Jam tip-off event (beginAt epoch-detik string) -> ISO UTC.

    None bila beginAt tidak ada / bukan angka.
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


def _line_float(value: object) -> float | None:
    """Ubah sportsLine (string/angka/None) jadi float."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def scan_nba_lines(events: list[dict]) -> dict:
    """Ringkasan pasar spread/total NBA dari daftar event jup.ag mentah.

    Murni (tanpa network). Hanya event subcategory "nba" yang judulnya
    format "Tim A vs. Tim B" yang dihitung sebagai laga; event NBA lain
    (mis. futures MVP) dihitung di nba_events tapi bukan laga.
    """
    games: list[dict] = []
    nba_events = 0
    total_spread_markets = 0
    total_total_markets = 0
    all_spread_lines: set[float] = set()
    all_total_lines: set[float] = set()
    for event in events:
        if not isinstance(event, dict) or event.get("subcategory") != "nba":
            continue
        nba_events += 1
        metadata = event.get("metadata") or {}
        title = metadata.get("title") or ""
        parsed = parse_vs_title(title)
        if parsed is None:
            continue
        away_team, home_team = parsed  # NBA: tandang dulu, kandang kedua.
        markets = event.get("markets") or []
        spread_lines: set[float] = set()
        total_lines: set[float] = set()
        spread_count = 0
        total_count = 0
        for market in markets:
            if not isinstance(market, dict):
                continue
            market_type = market.get("sportsMarketType")
            line = _line_float(market.get("sportsLine"))
            if market_type == "spreads":
                spread_count += 1
                if line is not None:
                    spread_lines.add(line)
            elif market_type == "totals":
                total_count += 1
                if line is not None:
                    total_lines.add(line)
        total_spread_markets += spread_count
        total_total_markets += total_count
        all_spread_lines |= spread_lines
        all_total_lines |= total_lines
        games.append(
            {
                "event_id": event.get("eventId"),
                "event_title": title,
                "tip_off": _tip_off_iso(event),
                "home_team": home_team,
                "away_team": away_team,
                "n_markets": len(markets),
                "spread_markets": spread_count,
                "total_markets": total_count,
                "spread_lines": sorted(spread_lines),
                "total_lines": sorted(total_lines),
                "has_spread": spread_count > 0,
                "has_total": total_count > 0,
            }
        )
    games_with_spread = sum(1 for g in games if g["has_spread"])
    games_with_total = sum(1 for g in games if g["has_total"])
    return {
        "nba_events": nba_events,
        "nba_games": len(games),
        "games": games,
        "games_with_spread": games_with_spread,
        "games_with_total": games_with_total,
        "games_without_spread_total": sum(
            1 for g in games if not g["has_spread"] and not g["has_total"]
        ),
        "total_spread_markets": total_spread_markets,
        "total_total_markets": total_total_markets,
        "spread_lines_all": sorted(all_spread_lines),
        "total_lines_all": sorted(all_total_lines),
    }


def enrich_scan_with_poly_ladders(
    scan: dict, events: list[dict], fetch_event=None
) -> dict:
    """Perkaya hasil pindai jup.ag dengan tangga Polymarket per laga.

    Network: satu fetch Gamma per laga yang slug-nya diketahui
    (fetch_event di-inject untuk tes; default
    polymarket.fetch_event_by_slug). Slug diambil dari metadata event
    jup.ag (resolve_slug_from_jup_event); bila tidak ada, laga itu
    dicatat poly_checked False (bukan ditebak lewat nba_slug — tanggal
    slug memakai tanggal laga ET yang tidak bisa diturunkan pasti
    dari beginAt UTC).

    Per laga ditambah: poly_slug, poly_checked, poly_error,
    poly_spread_markets, poly_total_markets, poly_spread_lines,
    poly_total_lines. has_spread/has_total menjadi gabungan (jup.ag
    ATAU Polymarket); angka jup.ag-only tersimpan di
    games_with_spread_jup / games_with_total_jup. Laga yang fetch
    Gamma-nya gagal tetap memakai angka jup.ag-nya (bukan 0 paksa)
    dengan poly_error tercatat. Mengembalikan scan yang sama
    (dimutasi di tempat).
    """
    by_id = {event.get("eventId"): event for event in events if isinstance(event, dict)}
    fetch = fetch_event or polymarket.fetch_event_by_slug
    scan["games_with_spread_jup"] = scan["games_with_spread"]
    scan["games_with_total_jup"] = scan["games_with_total"]
    checked = 0
    poly_spread_total = 0
    poly_total_total = 0
    all_poly_spread: set[float] = set()
    all_poly_total: set[float] = set()
    for game in scan["games"]:
        event = by_id.get(game["event_id"])
        slug = polymarket.resolve_slug_from_jup_event(event) if event else None
        game["poly_slug"] = slug
        game["poly_spread_markets"] = 0
        game["poly_total_markets"] = 0
        game["poly_spread_lines"] = []
        game["poly_total_lines"] = []
        if slug is None:
            game["poly_checked"] = False
            game["poly_error"] = "slug_polymarket_tidak_ada_di_metadata_jup"
            continue
        result = fetch(slug)
        if not result.ok:
            game["poly_checked"] = False
            game["poly_error"] = result.error
            continue
        counts = polymarket.count_event_markets(result.data or {})
        game["poly_checked"] = True
        game["poly_error"] = None
        game["poly_spread_markets"] = counts["spread_markets"]
        game["poly_total_markets"] = counts["total_markets"]
        game["poly_spread_lines"] = counts["spread_lines"]
        game["poly_total_lines"] = counts["total_lines"]
        game["has_spread"] = game["has_spread"] or counts["spread_markets"] > 0
        game["has_total"] = game["has_total"] or counts["total_markets"] > 0
        checked += 1
        poly_spread_total += counts["spread_markets"]
        poly_total_total += counts["total_markets"]
        all_poly_spread |= set(counts["spread_lines"])
        all_poly_total |= set(counts["total_lines"])
    scan["poly_games_checked"] = checked
    scan["poly_total_spread_markets"] = poly_spread_total
    scan["poly_total_total_markets"] = poly_total_total
    scan["poly_spread_lines_all"] = sorted(all_poly_spread)
    scan["poly_total_lines_all"] = sorted(all_poly_total)
    scan["games_with_spread"] = sum(1 for g in scan["games"] if g["has_spread"])
    scan["games_with_total"] = sum(1 for g in scan["games"] if g["has_total"])
    scan["games_without_spread_total"] = sum(
        1 for g in scan["games"] if not g["has_spread"] and not g["has_total"]
    )
    return scan


def _parse_iso(value: str | None) -> datetime | None:
    """Parse ISO 8601 (dengan 'Z') jadi datetime; None bila gagal."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def recheck_schedule(games: list[dict]) -> list[dict]:
    """Jadwal cek ulang per laga: 3 jam dan 1 jam sebelum tip-off.

    Murni (tanpa network). Laga tanpa tip-off yang bisa di-parse
    mendapat kedua jam None (tidak bisa dijadwalkan — dicatat apa adanya).
    """
    schedule = []
    for game in games:
        tip_off = _parse_iso(game.get("tip_off"))
        schedule.append(
            {
                "event_id": game.get("event_id"),
                "event_title": game.get("event_title"),
                "tip_off": game.get("tip_off"),
                "recheck_3h_before": (
                    (tip_off - timedelta(hours=3)).isoformat()
                    if tip_off is not None
                    else None
                ),
                "recheck_1h_before": (
                    (tip_off - timedelta(hours=1)).isoformat()
                    if tip_off is not None
                    else None
                ),
            }
        )
    return schedule


def _print_summary(report: dict) -> None:
    """Cetak ringkasan hasil pindai ke stdout (Bahasa Indonesia)."""
    if not report["ok"]:
        print(f"PINDAI GAGAL: {report.get('error')}")
        print(f"extra: {json.dumps(report.get('fetch_extra', {}))}")
        return
    scan = report["scan"]
    fetch_extra = report.get("fetch_extra", {})
    print(
        f"Pindai {report['scanned_at']}: "
        f"{fetch_extra.get('events_scanned')} event sports "
        f"({fetch_extra.get('pages_fetched')} halaman, "
        f"lengkap={fetch_extra.get('scan_complete')})"
    )
    if report.get("date_filter"):
        print(f"Filter tanggal (UTC): {report['date_filter']}")
    print(
        f"NBA: {scan['nba_events']} event, {scan['nba_games']} laga; "
        f"dengan spread: {scan['games_with_spread']}, "
        f"dengan total: {scan['games_with_total']}, "
        f"tanpa spread/total: {scan['games_without_spread_total']}"
    )
    print(
        f"Pasar spread: {scan['total_spread_markets']} "
        f"(garis: {scan['spread_lines_all']}); "
        f"pasar total: {scan['total_total_markets']} "
        f"(garis: {scan['total_lines_all']})"
    )
    if "poly_games_checked" in scan:
        print(
            f"Polymarket: {scan['poly_games_checked']}/{scan['nba_games']} laga "
            f"tercek tangganya; pasar spread {scan['poly_total_spread_markets']}, "
            f"pasar total {scan['poly_total_total_markets']} "
            f"(jup.ag-only: spread {scan['games_with_spread_jup']} laga, "
            f"total {scan['games_with_total_jup']} laga)"
        )
    for game in scan["games"]:
        poly_text = ""
        if "poly_checked" in game:
            if game["poly_checked"]:
                poly_text = (
                    f"; poly spread {game['poly_spread_markets']} "
                    f"{game['poly_spread_lines']}, total "
                    f"{game['poly_total_markets']} {game['poly_total_lines']}"
                )
            else:
                poly_text = f"; poly tidak tercek ({game['poly_error']})"
        print(
            f"- {game['event_title']} (tip-off {game['tip_off']}): "
            f"spread {game['spread_markets']} {game['spread_lines']}, "
            f"total {game['total_markets']} {game['total_lines']}{poly_text}"
        )


def main(argv: list[str] | None = None) -> int:
    """Jalankan pemindaian NBA spread/total; tulis laporan JSON.

    Mengembalikan 0 bila pindai berhasil (walau 0 pasar ditemukan —
    itu hasil, bukan error), 1 bila fetch gagal.
    """
    parser = argparse.ArgumentParser(
        description="Pindai pasar spread/total NBA di jup.ag."
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Hanya laga dengan tip-off pada tanggal UTC ini (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Path laporan JSON (default out/nba_lines_check_<timestamp>.json).",
    )
    args = parser.parse_args(argv)
    scanned_at = now_iso()
    result = fetch_sports_events()
    if not result.ok:
        report = {
            "ok": False,
            "error": result.error,
            "scanned_at": scanned_at,
            "fetch_extra": result.extra,
            "date_filter": args.date,
        }
        _print_summary(report)
        return 1
    scan = scan_nba_lines(result.data or [])
    if args.date is not None:
        # Filter tanggal UTC tip-off; laga tanpa tip-off yang bisa
        # di-parse dikeluarkan (tanggalnya tidak bisa diverifikasi).
        scan = _filter_by_date(scan, args.date)
    # Cek tangga Polymarket per laga (koreksi 2026-11-22): API jup.ag
    # saja tidak cukup untuk putusan ada/tidak spread/total.
    scan = enrich_scan_with_poly_ladders(scan, result.data or [])
    schedule = recheck_schedule(scan["games"])
    report = {
        "ok": True,
        "scanned_at": scanned_at,
        "scan": scan,
        "recheck_schedule": schedule,
        "fetch_extra": result.extra,
        "date_filter": args.date,
    }
    if args.out:
        out_path = Path(args.out)
    else:
        timestamp = scanned_at.replace(":", "").replace("-", "")
        timestamp = timestamp.split(".")[0].replace("+0000", "Z")
        out_path = repo_root() / "out" / f"nba_lines_check_{timestamp}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _print_summary(report)
    print(f"Laporan: {out_path}")
    return 0


def _filter_by_date(scan: dict, date: str) -> dict:
    """Filter hasil pindai ke laga dengan tip-off tanggal UTC `date`.

    Menghitung ulang semua agregat dari laga yang lolos filter.
    """
    games = []
    for game in scan["games"]:
        tip_off = _parse_iso(game.get("tip_off"))
        if tip_off is not None and tip_off.date().isoformat() == date:
            games.append(game)
    all_spread: set[float] = set()
    all_total: set[float] = set()
    for game in games:
        all_spread |= set(game["spread_lines"])
        all_total |= set(game["total_lines"])
    return {
        "nba_events": scan["nba_events"],
        "nba_games": len(games),
        "games": games,
        "games_with_spread": sum(1 for g in games if g["has_spread"]),
        "games_with_total": sum(1 for g in games if g["has_total"]),
        "games_without_spread_total": sum(
            1 for g in games if not g["has_spread"] and not g["has_total"]
        ),
        "total_spread_markets": sum(g["spread_markets"] for g in games),
        "total_total_markets": sum(g["total_markets"] for g in games),
        "spread_lines_all": sorted(all_spread),
        "total_lines_all": sorted(all_total),
    }


if __name__ == "__main__":
    sys.exit(main())
