#!/usr/bin/env python3
"""Satu pintu masuk muse-parlay-analyst (Blueprint §10, SOP §5).

    python cli.py analyze --input slate.json   # Tahap 2+ (belum tersedia)
    python cli.py recheck --ticket <id>        # Tahap 5  (belum tersedia)
    python cli.py log --file ticket.json       # Tahap 1  ✓
    python cli.py log --settle <id> --result WIN|LOSS|PUSH|VOID|CASHOUT
        [--cashout-amount <usd>] [--leg-result <leg_id>=<hasil> ...]
    python cli.py recap [--json]

Exit code: 0 sukses, 1 error (input tidak valid / ledger gagal),
2 fitur belum tersedia di tahap ini.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from ledger import recap as recap_mod  # noqa: E402
from ledger import store  # noqa: E402

NOT_IMPLEMENTED = 2


def _db_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--db",
        default=str(store.DEFAULT_DB_PATH),
        help="path file SQLite ledger (default: ledger.db di root repo)",
    )


def cmd_analyze(args: argparse.Namespace) -> int:
    print(
        "analyze belum tersedia: Tahap 2 (data) dan Tahap 3 (mesin hitung) "
        "belum dibangun. Lihat README.md untuk status tahapan.",
        file=sys.stderr,
    )
    return NOT_IMPLEMENTED


def cmd_recheck(args: argparse.Namespace) -> int:
    print(
        "recheck belum tersedia: Tahap 5 (Telegram) belum dibangun. "
        "Lihat README.md untuk status tahapan.",
        file=sys.stderr,
    )
    return NOT_IMPLEMENTED


def _parse_leg_results(raw: list[str] | None) -> dict[str, str]:
    """Ubah ['leg-01=WIN', ...] menjadi {leg_id: hasil}. Format salah -> error."""
    parsed: dict[str, str] = {}
    for item in raw or []:
        if "=" not in item:
            raise ValueError(f"format --leg-result salah: {item!r} (pakai ID=HASIL)")
        leg_id, result = item.split("=", 1)
        parsed[leg_id.strip()] = result.strip().upper()
    return parsed


def cmd_log(args: argparse.Namespace) -> int:
    conn = store.connect(args.db)
    if args.settle:
        try:
            leg_results = _parse_leg_results(args.leg_result)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        try:
            profit = store.settle_ticket(
                conn, args.settle, args.result,
                leg_results=leg_results,
                cashout_amount=args.cashout_amount,
            )
        except store.LedgerError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        saved = store.get_ticket(conn, args.settle)
        extra = ""
        if saved and saved.get("multiplier_original") is not None:
            extra = (f" (pengali dihitung ulang {saved['multiplier_original']}"
                     f"x -> {saved['multiplier']:.4f}x karena kaki VOID/PUSH)")
        print(f"tiket {args.settle} diselesaikan: {saved['result']}, "
              f"untung/rugi ${profit:+.2f}{extra}")
        return 0

    if not args.file:
        print("error: pakai --file ticket.json atau --settle <id> --result ...",
              file=sys.stderr)
        return 1
    try:
        ticket = json.loads(Path(args.file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: tidak bisa membaca {args.file}: {exc}", file=sys.stderr)
        return 1
    try:
        ticket_id = store.log_ticket(conn, ticket)
    except store.LedgerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    saved = store.get_ticket(conn, ticket_id)
    profit = saved["profit_loss"] if saved else None
    profit_text = f"${profit:+.2f}" if profit is not None else "pending"
    extra = ""
    if saved and saved.get("multiplier_original") is not None:
        extra = (f", pengali awal {saved['multiplier_original']}x "
                 f"(dihitung ulang karena kaki VOID/PUSH)")
    print(f"tiket {ticket_id} dicatat ({saved['type']}, "
          f"modal ${saved['stake']:.2f}, pengali {saved['multiplier']}x, "
          f"hasil {saved['result']}, untung/rugi {profit_text}{extra})")
    return 0


def cmd_recap(args: argparse.Namespace) -> int:
    conn = store.connect(args.db)
    data = recap_mod.compute_recap(conn)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(recap_mod.format_recap(data))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="muse-parlay-analyst — satu pintu masuk (Blueprint §10).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="analisis slate (Tahap 2+)")
    p_analyze.add_argument("--input", required=True, help="file slate.json")
    p_analyze.set_defaults(func=cmd_analyze)

    p_recheck = sub.add_parser("recheck", help="cek ulang tiket (Tahap 5)")
    p_recheck.add_argument("--ticket", required=True, help="id tiket")
    p_recheck.set_defaults(func=cmd_recheck)

    p_log = sub.add_parser("log", help="catat / selesaikan tiket (Tahap 1)")
    p_log.add_argument("--file", help="file ticket.json (sesuai skema)")
    p_log.add_argument("--settle", metavar="TICKET_ID",
                       help="selesaikan tiket PENDING")
    p_log.add_argument("--result",
                       choices=["WIN", "LOSS", "PUSH", "VOID", "CASHOUT"],
                       help="hasil untuk --settle")
    p_log.add_argument("--cashout-amount", type=float, default=None,
                       help="jumlah cashout USD (wajib bila --result CASHOUT)")
    p_log.add_argument("--leg-result", action="append", default=None,
                       metavar="LEG_ID=HASIL",
                       help="hasil per kaki, boleh diulang: --leg-result leg-01=WIN")
    _db_arg(p_log)
    p_log.set_defaults(func=cmd_log)

    p_recap = sub.add_parser("recap", help="rekap untung/rugi (Tahap 1)")
    p_recap.add_argument("--json", action="store_true",
                         help="keluarkan JSON, bukan teks")
    _db_arg(p_recap)
    p_recap.set_defaults(func=cmd_recap)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "log" and args.settle and not args.result:
        print("error: --settle butuh --result WIN|LOSS|PUSH|VOID|CASHOUT",
              file=sys.stderr)
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
