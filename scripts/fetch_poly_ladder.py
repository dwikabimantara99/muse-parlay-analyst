"""Runner CLI: tarik tangga Polymarket satu laga NBA.

    python3 scripts/fetch_poly_ladder.py --slug nba-det-atl-2026-11-22
    python3 scripts/fetch_poly_ladder.py --away DET --home ATL --date 2026-11-22

Fetch event Gamma lewat slug, parse tangga (moneyline/spread/total),
print ringkasan (garis total + harga Under + volume + flag thin) dan
tulis JSON lengkap ke out/poly_ladder_<slug>.json (out/ gitignored).

Tangga ini HARGA VENUE (yang dilihat user di UI jup.ag), BUKAN
pembanding p_market (P2, DECISIONS.md) — jangan dipakai sebagai
pembanding di mana pun.

Config: ambang dibaca dari playstyle.yaml
(polymarket_ladder.min_volume_usd, fees.jup_typical_markup_cents).
--min-volume-usd / --markup-cents meng-override config (untuk
verifikasi sebelum koordinator menambahkan kunci config; nilai
override dicetak di ringkasan). Tanpa override dan kunci config
belum ada -> berhenti dengan pesan jelas (exit 2), bukan default
diam-diam.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from ingest import polymarket
from ingest.common import now_iso, repo_root


def _build_cfg(min_volume_usd: float | None, markup_cents: float | None) -> dict:
    """Muat playstyle; terapkan override CLI bila diberikan."""
    cfg = config.load_playstyle()
    if min_volume_usd is not None:
        cfg = copy.deepcopy(cfg)
        cfg.setdefault("polymarket_ladder", {})["min_volume_usd"] = min_volume_usd
    if markup_cents is not None:
        cfg = copy.deepcopy(cfg)
        cfg.setdefault("fees", {})["jup_typical_markup_cents"] = markup_cents
    return cfg


def _print_summary(slug: str, ladders: dict, min_volume_usd: float) -> None:
    """Cetak ringkasan tangga ke stdout (Bahasa Indonesia)."""
    print(f"Tangga Polymarket: {ladders.get('title')} ({slug})")
    print(
        f"Moneyline: {len(ladders['moneyline'])} entri; "
        f"spread: {len(ladders['spreads'])} pasar; "
        f"total: {len(ladders['totals']) // 2} garis"
    )
    print(f"Ambang thin: volume < ${min_volume_usd:,.0f} (atau tanpa bid/ask)")
    print("Garis total (Under):")
    unders = [e for e in ladders["totals"] if e["side"] == "under"]
    for entry in unders:
        price = entry["price_cents"]
        price_text = f"{price:.1f}¢" if price is not None else "tidak ada harga"
        volume = entry["volume_usd"]
        volume_text = f"${volume:,.2f}" if volume is not None else "tidak ada volume"
        thin_text = "THIN" if entry["thin"] else "ok"
        print(
            f"  U {entry['line']}: {price_text} "
            f"(jup est. {entry['jup_estimated_cents']}¢, "
            f"vol {volume_text}, {entry['price_source']}, {thin_text})"
        )
    for warning in ladders["warnings"]:
        print(f"PERINGATAN: {warning}")


def main(argv: list[str] | None = None) -> int:
    """Jalankan fetch + parse tangga. 0 sukses, 1 fetch gagal,
    2 argumen/config tidak valid."""
    parser = argparse.ArgumentParser(
        description="Tarik tangga Polymarket satu laga NBA (harga venue)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--slug", default=None, help="slug Gamma, misal nba-det-atl-2026-11-22"
    )
    group.add_argument(
        "--away",
        default=None,
        help="tricode tim tandang (dipakai bersama --home/--date)",
    )
    parser.add_argument("--home", default=None, help="tricode tim kandang")
    parser.add_argument("--date", default=None, help="tanggal laga YYYY-MM-DD")
    parser.add_argument(
        "--min-volume-usd",
        type=float,
        default=None,
        help="override polymarket_ladder.min_volume_usd (USD)",
    )
    parser.add_argument(
        "--markup-cents",
        type=float,
        default=None,
        help="override fees.jup_typical_markup_cents (¢)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="file output (default out/poly_ladder_<slug>.json)",
    )
    args = parser.parse_args(argv)
    if args.slug:
        slug = args.slug.strip().lower()
    else:
        if not args.home or not args.date:
            parser.error("--away butuh --home dan --date")
        try:
            slug = polymarket.nba_slug(args.away, args.home, args.date)
        except ValueError as exc:
            print(f"Slug tidak valid: {exc}", file=sys.stderr)
            return 2
    try:
        cfg = _build_cfg(args.min_volume_usd, args.markup_cents)
        min_volume_usd = float(
            config.get_value(cfg, "polymarket_ladder", "min_volume_usd")
        )
        # Validasi markup ada sebelum fetch (fail-closed, bukan default).
        config.get_value(cfg, "fees", "jup_typical_markup_cents")
    except config.ConfigError as exc:
        print(
            f"Config belum lengkap: {exc}. Tambahkan kunci ke "
            "config/playstyle.yaml (koordinator) atau pakai "
            "--min-volume-usd / --markup-cents.",
            file=sys.stderr,
        )
        return 2
    result = polymarket.fetch_event_by_slug(slug)
    if not result.ok:
        print(f"Fetch Gamma gagal: {result.error}", file=sys.stderr)
        return 1
    ladders = polymarket.parse_event_ladders(result.data, cfg=cfg)
    _print_summary(slug, ladders, min_volume_usd)
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = repo_root() / "out" / f"poly_ladder_{slug}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "slug": slug,
        "fetched_at": now_iso(),
        "from_cache": result.extra.get("from_cache"),
        "ladders": ladders,
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"JSON: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
