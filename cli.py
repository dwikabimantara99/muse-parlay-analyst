#!/usr/bin/env python3
"""Satu pintu masuk muse-parlay-analyst (Blueprint §10, SOP §5).

    python cli.py analyze --input slate.json [--out out.json]
        # Tahap 2b ✓ — tarik data (SOP langkah 2-3), tulis
        # out/analysis_<slate_id>.json. Simulasi/tiket Tahap 3+.
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


def _validate_slate(slate: dict) -> str | None:
    """Validasi slate input terhadap schemas/slate.schema.json.

    Mengembalikan pesan error, atau None bila valid. Bila ``jsonschema``
    tidak tersedia, pakai validasi minimal (required-field) + peringatan
    ke stderr.
    """
    try:
        import jsonschema
    except ImportError:
        print(
            "peringatan: jsonschema tidak tersedia — validasi minimal "
            "(required-field) saja",
            file=sys.stderr,
        )
        for key in ("slate_id", "created_at_wib", "matches"):
            if key not in slate:
                return f"slate kehilangan kunci wajib: {key}"
        if not isinstance(slate.get("matches"), list) or not slate["matches"]:
            return "slate.matches harus list tidak kosong"
        for entry in slate["matches"]:
            for key in ("match_id", "sport", "league", "home", "away", "start_time"):
                if key not in entry:
                    return f"laga kehilangan kunci wajib: {key}"
        return None
    schema_path = REPO_ROOT / "schemas" / "slate.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"tidak bisa membaca skema slate: {exc}"
    try:
        jsonschema.validate(slate, schema)
    except jsonschema.ValidationError as exc:
        return f"slate tidak valid: {exc.message}"
    return None


def _slate_date(match: dict, sport: str | None = None) -> str | None:
    """Tanggal (YYYY-MM-DD) dari start_time satu laga; None bila tidak sah.

    NBA: tanggal US Eastern — stats.nba.com memakai tanggal Eastern, jadi
    start_time WIB yang jatuh dini hari (mis. 08:00 WIB) adalah laga malam
    sebelumnya di AS. Sport lain: tanggal apa adanya dari start_time
    (pencocokan fixture bola toleran ±1 hari).
    """
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    try:
        parsed = datetime.fromisoformat(match["start_time"])
    except (KeyError, TypeError, ValueError):
        return None
    if sport == "nba":
        if parsed.tzinfo is None:
            # Skema slate mewajibkan zona waktu; bila hilang, anggap UTC.
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    return parsed.date().isoformat()


def _league_code(league: str | None) -> str:
    """Kode liga fetcher dari nama liga slate ('Premier League' -> 'EPL')."""
    mapping = {
        "Premier League": "EPL",
        "EPL": "EPL",
        "LaLiga": "LaLiga",
        "La Liga": "LaLiga",
    }
    return mapping.get(str(league or ""), str(league or "EPL"))


def cmd_analyze(args: argparse.Namespace) -> int:
    """Jalankan analisis slate Tahap 2b: tarik data + validasi (SOP langkah 2-3).

    Input slate divalidasi skema, ditolak bila ``confirmed_by_user`` bukan
    true (SOP langkah 1). Laga dikelompokkan per sport; tanggal per sport
    = tanggal start_time laga pertama sport itu — NBA dikonversi ke tanggal
    US Eastern (stats.nba.com memakai tanggal Eastern). Bila laga lintas
    tanggal, laga di tanggal lain tetap diproses — pencocokan berbasis tim,
    tapi pencarian jadwal memakai tanggal sport itu. Satu file output JSON
    ditulis (default ``out/analysis_<slate_id>.json``) + ringkasan tercetak.
    """
    try:
        slate = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: tidak bisa membaca {args.input}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(slate, dict):
        print("error: slate harus berupa objek JSON", file=sys.stderr)
        return 1
    error = _validate_slate(slate)
    if error is not None:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if slate.get("confirmed_by_user") is not True:
        print(
            "error: slate belum dikonfirmasi user (confirmed_by_user bukan "
            "true) — analisis tidak jalan (SOP langkah 1: tampilkan tabel "
            "dulu, tunggu user balas 'ok')",
            file=sys.stderr,
        )
        return 1

    from ingest.slate import build_slate

    by_sport: dict[str, list[dict]] = {}
    for entry in slate["matches"]:
        by_sport.setdefault(entry["sport"], []).append(entry)

    all_matches: list[dict] = []
    summary = {
        "matches": 0,
        "ok": 0,
        "data_incomplete": 0,
        "hold": 0,
        "model_only": 0,
        "tanpa_xg": 0,
    }
    odds_api = {"calls": 0, "credits_used": 0}
    for sport, entries in sorted(by_sport.items()):
        date = _slate_date(entries[0], sport)
        if date is None:
            print(
                f"error: start_time laga pertama {sport} tidak bisa dibaca: "
                f"{entries[0].get('start_time')!r}",
                file=sys.stderr,
            )
            return 1
        league = _league_code(entries[0].get("league"))
        try:
            if sport == "football":
                result = build_slate(sport, date, matches=entries, league=league)
            else:
                result = build_slate(sport, date, matches=entries)
        except (ValueError, RuntimeError) as exc:
            print(f"error: gagal merakit slate {sport}: {exc}", file=sys.stderr)
            return 1
        all_matches.extend(result["matches"])
        for key in summary:
            summary[key] += result["summary"][key]
        odds_api["calls"] += result["odds_api"]["calls"]
        odds_api["credits_used"] += result["odds_api"]["credits_used"]

    from datetime import UTC, datetime

    output = {
        "slate_id": slate["slate_id"],
        "generated_at": datetime.now(UTC).isoformat(),
        "matches": all_matches,
        "summary": summary,
        "odds_api": odds_api,
    }
    out_path = Path(
        args.out or (REPO_ROOT / "out" / f"analysis_{slate['slate_id']}.json")
    )
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"error: tidak bisa menulis {out_path}: {exc}", file=sys.stderr)
        return 1
    print(
        f"slate {slate['slate_id']}: {summary['matches']} laga "
        f"(OK {summary['ok']}, HOLD {summary['hold']}, "
        f"DATA_INCOMPLETE {summary['data_incomplete']})"
    )
    print(
        f"MODEL_ONLY: {summary['model_only']} laga | "
        f"TANPA_XG: {summary['tanpa_xg']} laga"
    )
    print(
        f"Odds API: {odds_api['calls']} panggilan, "
        f"{odds_api['credits_used']} kredit"
    )
    for entry in all_matches:
        labels = ",".join(entry.get("labels") or [])
        label_text = f" [{labels}]" if labels else ""
        print(f"  {entry['match_id']}: {entry['status']}{label_text}")
    print(f"output: {out_path}")
    return 0


def cmd_recheck(args: argparse.Namespace) -> int:
    """Cek ulang tiket sebelum laga (belum tersedia — Tahap 5)."""
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
    """Catat tiket dari file JSON, atau selesaikan tiket PENDING."""
    conn = store.connect(args.db)
    if args.settle:
        try:
            leg_results = _parse_leg_results(args.leg_result)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        try:
            profit = store.settle_ticket(
                conn,
                args.settle,
                args.result,
                leg_results=leg_results,
                cashout_amount=args.cashout_amount,
            )
        except store.LedgerError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        saved = store.get_ticket(conn, args.settle)
        extra = ""
        if saved and saved.get("multiplier_original") is not None:
            extra = (
                f" (pengali dihitung ulang {saved['multiplier_original']}"
                f"x -> {saved['multiplier']:.4f}x karena kaki VOID/PUSH)"
            )
        print(
            f"tiket {args.settle} diselesaikan: {saved['result']}, "
            f"untung/rugi ${profit:+.2f}{extra}"
        )
        return 0

    if not args.file:
        print(
            "error: pakai --file ticket.json atau --settle <id> --result ...",
            file=sys.stderr,
        )
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
        extra = (
            f", pengali awal {saved['multiplier_original']}x "
            f"(dihitung ulang karena kaki VOID/PUSH)"
        )
    print(
        f"tiket {ticket_id} dicatat ({saved['type']}, "
        f"modal ${saved['stake']:.2f}, pengali {saved['multiplier']}x, "
        f"hasil {saved['result']}, untung/rugi {profit_text}{extra})"
    )
    return 0


def cmd_recap(args: argparse.Namespace) -> int:
    """Tampilkan rekap untung/rugi ledger (teks atau JSON)."""
    conn = store.connect(args.db)
    data = recap_mod.compute_recap(conn)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(recap_mod.format_recap(data))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Bangun parser argumen CLI (analyze / recheck / log / recap)."""
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="muse-parlay-analyst — satu pintu masuk (Blueprint §10).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="analisis slate (Tahap 2b: tarik data)")
    p_analyze.add_argument("--input", required=True, help="file slate.json")
    p_analyze.add_argument(
        "--out",
        default=None,
        help="file output JSON (default: out/analysis_<slate_id>.json)",
    )
    p_analyze.set_defaults(func=cmd_analyze)

    p_recheck = sub.add_parser("recheck", help="cek ulang tiket (Tahap 5)")
    p_recheck.add_argument("--ticket", required=True, help="id tiket")
    p_recheck.set_defaults(func=cmd_recheck)

    p_log = sub.add_parser("log", help="catat / selesaikan tiket (Tahap 1)")
    p_log.add_argument("--file", help="file ticket.json (sesuai skema)")
    p_log.add_argument("--settle", metavar="TICKET_ID", help="selesaikan tiket PENDING")
    p_log.add_argument(
        "--result",
        choices=["WIN", "LOSS", "PUSH", "VOID", "CASHOUT"],
        help="hasil untuk --settle",
    )
    p_log.add_argument(
        "--cashout-amount",
        type=float,
        default=None,
        help="jumlah cashout USD (wajib bila --result CASHOUT)",
    )
    p_log.add_argument(
        "--leg-result",
        action="append",
        default=None,
        metavar="LEG_ID=HASIL",
        help="hasil per kaki, boleh diulang: --leg-result leg-01=WIN",
    )
    _db_arg(p_log)
    p_log.set_defaults(func=cmd_log)

    p_recap = sub.add_parser("recap", help="rekap untung/rugi (Tahap 1)")
    p_recap.add_argument(
        "--json", action="store_true", help="keluarkan JSON, bukan teks"
    )
    _db_arg(p_recap)
    p_recap.set_defaults(func=cmd_recap)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Titik masuk CLI; mengembalikan exit code (0 sukses, 1 error, 2 belum tersedia)."""
    args = build_parser().parse_args(argv)
    if args.command == "log" and args.settle and not args.result:
        print(
            "error: --settle butuh --result WIN|LOSS|PUSH|VOID|CASHOUT", file=sys.stderr
        )
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
