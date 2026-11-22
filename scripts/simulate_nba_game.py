"""Runner CLI: simulasi satu laga NBA dari data nyata.

    python3 scripts/simulate_nba_game.py ATL DET 2026-11-22 [--seed 7]

Mengambil input laga via ingest.nba_brain.fetch_match_inputs (kontrak
worker data Tahap 3), menjalankan engine.nba_sim.simulate (100.000x),
dan menulis JSON ke examples/simulation_nba_<HOME>_<AWAY>_<tanggal>.json
+ print ringkasan.

ASUMSI signature (sesuaikan bila worker data memakai signature lain):
  fetch_match_inputs(home_tricode=..., away_tricode=...,
                     game_date=...) -> FetchResult (data = dict input
  simulasi sesuai kontrak di engine/nba_sim.py).

Bila ingest.nba_brain belum tersedia, script berhenti dengan pesan
jelas (exit 2), bukan traceback misterius.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import nba_sim


def main(argv: list[str] | None = None) -> int:
    """Jalankan simulasi satu laga. 0 sukses, 2 input/modul belum tersedia."""
    parser = argparse.ArgumentParser(
        description="Simulasi satu laga NBA (100.000x) dari data nyata."
    )
    parser.add_argument("home_tricode", help="tricode tim kandang, misal ATL")
    parser.add_argument("away_tricode", help="tricode tim tandang, misal DET")
    parser.add_argument("game_date", help="tanggal laga YYYY-MM-DD")
    parser.add_argument("--seed", type=int, default=None, help="seed RNG")
    parser.add_argument(
        "--out",
        default=None,
        help="file output (default: examples/simulation_nba_<H>_<A>_<tgl>.json)",
    )
    args = parser.parse_args(argv)
    home = args.home_tricode.upper()
    away = args.away_tricode.upper()

    try:
        from ingest.nba_brain import fetch_match_inputs
    except ImportError as exc:
        print(
            "ingest.nba_brain belum tersedia (kontrak worker data Tahap 3) "
            "— runner ini baru bisa dipakai setelah worker data selesai. "
            f"Detail teknis: {exc}",
            file=sys.stderr,
        )
        return 2
    try:
        result = fetch_match_inputs(
            home_tricode=home, away_tricode=away, game_date=args.game_date
        )
    except TypeError as exc:
        print(
            "fetch_match_inputs menolak argumen yang dipakai runner ini "
            "(home_tricode/away_tricode/game_date) — signature worker data "
            f"berbeda, sesuaikan scripts/simulate_nba_game.py. Detail: {exc}",
            file=sys.stderr,
        )
        return 2
    if not result.ok:
        print(f"pengambilan input laga gagal: {result.error}", file=sys.stderr)
        return 2

    try:
        hasil = nba_sim.simulate(result.data, seed=args.seed)
    except Exception as exc:  # runner CLI: laporkan jelas, jangan traceback
        print(f"simulasi gagal: {exc}", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parent.parent
    out_path = (
        Path(args.out)
        if args.out
        else repo_root
        / "examples"
        / f"simulation_nba_{home}_{away}_{args.game_date}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(hasil, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ringkasan = hasil["inputs_summary"]
    pasar = hasil["markets"]
    print(f"laga: {away} @ {home} ({args.game_date})")
    print(
        f"proyeksi: {away} {ringkasan['projected_away_points']} - "
        f"{ringkasan['projected_home_points']} {home} "
        f"(total {ringkasan['projected_total']}, "
        f"margin {ringkasan['projected_margin']})"
    )
    print(
        f"moneyline: kandang {pasar['moneyline_home']:.1%}, "
        f"tandang {pasar['moneyline_away']:.1%}"
    )
    print(
        "peluang OT: "
        f"{hasil['score_distribution']['ot_probability']:.1%} | "
        f"waktu: {ringkasan['elapsed_seconds']} dtk "
        f"({hasil['iterations']} iterasi)"
    )
    print(f"hasil ditulis ke {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
