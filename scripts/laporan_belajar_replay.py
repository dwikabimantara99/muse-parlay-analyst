"""Validasi replay: laporan belajar dari backtest NBA (Tahap 3 Langkah 6).

Jalankan dari root repo:
  python3 scripts/laporan_belajar_replay.py [--input out/validation_nba_rolling.json]
      [--output out/laporan_belajar_replay.txt]

Membaca ``out/validation_nba_rolling.json`` (hasil
scripts/validate_nba_model.py --rolling), membangun OUTCOME RECORD
(kontrak engine/learning.py) dari ``backtest.hasil_per_laga`` — DUA
kaki per laga: (i) moneyline kandang menang (p_home_win vs
actual_home_win), (ii) total Under pada garis median+8 (p_under vs
actual_under) — lalu menjalankan ringkasan + kalibrasi w + usulan
lewat ``cli.bangun_data_belajar`` dan menulis laporan replay ke
``out/laporan_belajar_replay.txt`` (gitignored, jangan commit).

KEJUJURAN:
- Replay = prediksi backtest atas laga lama, BUKAN tiket nyata.
  Laporan selalu berlabel "DATA REPLAY BACKTEST — BUKAN TIKET NYATA".
- TANPA harga pasar historis: p_market None untuk semua kaki replay,
  jadi perbandingan model-vs-pasar DATA_INCOMPLETE di replay dan
  kalibrasi w tidak punya cukup data (n=0) — itu hasil yang benar,
  bukan kegagalan.
- MODEL_ONLY: tanpa harga pasar, p_final = p_model (aturan config
  model_only.p_final_equals_p_model), jadi Brier gabungan sama
  dengan Brier model di replay.
- Bila file tidak punya rekor per laga (kunci "backtest" /
  "hasil_per_laga" hilang atau kosong), skrip melaporkan UNKNOWN dan
  berhenti (exit 2) TANPA menulis laporan — tidak ada angka yang
  dikarang dari ringkasan agregat.

CEK SILANG: Brier replay dibandingkan dengan Brier yang tercatat di
file validasi itu sendiri (kalibrasi.kandang_menang.brier dan
kalibrasi.under_median_plus_8.brier). Cocok = pembangunan outcome
benar; tidak cocok = PERINGATAN di stdout (laporan tetap ditulis,
  selisihnya harus diselidiki sebelum dipakai sebagai bukti).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cli as cli_mod
from report import learning_report as learning_report_mod

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "out" / "validation_nba_rolling.json"
DEFAULT_OUTPUT = REPO_ROOT / "out" / "laporan_belajar_replay.txt"

# Toleransi cek silang Brier replay vs Brier file validasi.
TOLERANSI_BRIER = 1e-6


def _peluang_valid(nilai) -> float | None:
    """Peluang valid 0-1; None bila bukan angka / di luar 0-1."""
    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        return None
    if not math.isfinite(nilai) or not 0.0 <= nilai <= 1.0:
        return None
    return float(nilai)


def _satu_outcome(
    game_id: str,
    akhiran: str,
    market: str,
    selection: str,
    p_model,
    result,
) -> dict | None:
    """Satu OUTCOME RECORD replay; None bila p/hasil tidak valid."""
    p = _peluang_valid(p_model)
    if p is None or not isinstance(result, bool):
        return None
    return {
        "leg_id": f"replay-{game_id}-{akhiran}",
        "ticket_id": None,
        "sport": "NBA",
        "market": market,
        "selection": selection,
        "p_model": p,
        # Tanpa harga pasar historis: p_market None (DATA_INCOMPLETE),
        # p_final = p_model (MODEL_ONLY).
        "p_market": None,
        "p_final": p,
        "price_buy_cents": None,
        "price_close_cents": None,
        "ev_pct": None,
        "result": result,
        "settled": True,
        "sumber": "replay",
    }


def bangun_outcome_replay(data: dict) -> tuple[list[dict], dict]:
    """Bangun outcome record dari dokumen validasi NBA (rolling).

    data: isi out/validation_nba_rolling.json (dict). Mengembalikan
    (outcomes, info): outcomes = 2 kaki per laga yang valid; info =
    {"n_laga", "n_outcome", "n_dilewati", "n_laga_tidak_valid",
    "tanggal_laga", "error"} — error str bila tidak ada rekor per laga
    (UNKNOWN: jangan mengarang dari agregat).
    """
    info: dict = {
        "n_laga": 0,
        "n_outcome": 0,
        "n_dilewati": 0,
        "n_laga_tidak_valid": 0,
        "tanggal_laga": None,
        "error": None,
    }
    backtest = data.get("backtest") if isinstance(data, dict) else None
    hasil = backtest.get("hasil_per_laga") if isinstance(backtest, dict) else None
    if not isinstance(hasil, list) or not hasil:
        info["error"] = (
            "UNKNOWN: file validasi tidak berisi rekor per laga "
            "('backtest.hasil_per_laga' hilang/kosong) — replay tidak "
            "bisa dibangun tanpa mengarang angka."
        )
        return [], info
    info["n_laga"] = len(hasil)
    info["n_dilewati"] = backtest.get("n_dilewati") or 0
    tanggal = sorted(
        str(laga.get("game_date"))
        for laga in hasil
        if isinstance(laga, dict) and laga.get("game_date")
    )
    if tanggal:
        info["tanggal_laga"] = f"{tanggal[0]} s.d. {tanggal[-1]}"
    outcomes: list[dict] = []
    for laga in hasil:
        if not isinstance(laga, dict):
            info["n_laga_tidak_valid"] += 1
            continue
        game_id = str(laga.get("game_id") or "tanpa-id")
        kandang = laga.get("home_tricode") or "?"
        tandang = laga.get("away_tricode") or "?"
        garis = laga.get("garis_under")
        garis_teks = f"{garis:g}" if isinstance(garis, (int, float)) else "?"
        kaki_ml = _satu_outcome(
            game_id,
            "ml",
            "moneyline",
            f"{kandang} menang (kandang vs {tandang})",
            laga.get("p_home_win"),
            laga.get("actual_home_win"),
        )
        kaki_under = _satu_outcome(
            game_id,
            "under",
            "total_under",
            f"Under {garis_teks}",
            laga.get("p_under"),
            laga.get("actual_under"),
        )
        if kaki_ml is None or kaki_under is None:
            info["n_laga_tidak_valid"] += 1
            continue
        outcomes.extend([kaki_ml, kaki_under])
    info["n_outcome"] = len(outcomes)
    return outcomes, info


def _cek_silang_brier(data: dict, per_pasar: dict | None) -> list[str]:
    """Bandingkan Brier replay dengan Brier file validasi.

    Mengembalikan daftar baris hasil cek (cocok / PERINGATAN).
    """
    baris: list[str] = []
    kalibrasi = data.get("kalibrasi") if isinstance(data, dict) else None
    if not isinstance(kalibrasi, dict):
        return ["cek silang Brier: file validasi tidak punya 'kalibrasi'."]
    if not isinstance(per_pasar, dict):
        return ["cek silang Brier: tidak ada ringkasan per pasar."]
    pasangan = [
        (("NBA", "moneyline"), "kandang_menang", "moneyline"),
        (("NBA", "total_under"), "under_median_plus_8", "total_under"),
    ]
    for kunci, kunci_file, label in pasangan:
        entri_file = kalibrasi.get(kunci_file)
        brier_file = entri_file.get("brier") if isinstance(entri_file, dict) else None
        entri_replay = per_pasar.get(kunci)
        brier_replay = (
            entri_replay.get("brier_model") if isinstance(entri_replay, dict) else None
        )
        if brier_file is None or brier_replay is None:
            baris.append(
                f"cek silang Brier {label}: tidak bisa dibandingkan "
                "(nilai hilang di salah satu sisi)."
            )
            continue
        selisih = abs(brier_file - brier_replay)
        if selisih <= TOLERANSI_BRIER:
            baris.append(
                f"cek silang Brier {label}: COCOK "
                f"(replay {brier_replay:.6f} = file {brier_file:.6f})."
            )
        else:
            baris.append(
                f"PERINGATAN: Brier {label} tidak cocok — replay "
                f"{brier_replay:.6f} vs file {brier_file:.6f} "
                f"(selisih {selisih:.6f}). Selidiki definisi event "
                "sebelum memakai replay ini sebagai bukti."
            )
    return baris


def main(argv: list[str] | None = None) -> int:
    """Titik masuk skrip; 0 sukses, 2 = tidak bisa jalan."""
    parser = argparse.ArgumentParser(
        prog="laporan_belajar_replay.py",
        description="Laporan belajar dari replay backtest NBA (Langkah 6).",
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="file validasi NBA (default: out/validation_nba_rolling.json)",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="file laporan replay (default: out/laporan_belajar_replay.txt)",
    )
    args = parser.parse_args(argv)
    try:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: tidak bisa membaca {args.input}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print(
            f"error: {args.input} bukan objek JSON (UNKNOWN: struktur "
            "tidak dikenal)",
            file=sys.stderr,
        )
        return 2
    outcomes, info = bangun_outcome_replay(data)
    if info.get("error") is not None:
        print(f"error: {info['error']}", file=sys.stderr)
        return 2
    catatan = (
        f"Replay backtest rolling dari {args.input} — {info['n_laga']} laga "
        f"({info['tanggal_laga']}), {info['n_outcome']} kaki "
        "(moneyline + total Under median+8 per laga)."
    )
    if info.get("n_dilewati"):
        catatan += f" {info['n_dilewati']} laga dilewati di backtest."
    if info.get("n_laga_tidak_valid"):
        catatan += (
            f" {info['n_laga_tidak_valid']} laga tidak valid dan "
            "dikeluarkan dari replay."
        )
    data_laporan, error = cli_mod.bangun_data_belajar(
        outcomes, "replay", catatan_sumber=catatan
    )
    if error is not None:
        print(f"error: {error}", file=sys.stderr)
        return 2
    teks = learning_report_mod.render_laporan_belajar(data_laporan)
    try:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(teks, encoding="utf-8")
    except OSError as exc:
        print(f"error: tidak bisa menulis {args.output}: {exc}", file=sys.stderr)
        return 2
    print(f"replay: {info['n_laga']} laga -> {info['n_outcome']} kaki")
    print(f"laporan replay ditulis ke {args.output}")
    for baris in _cek_silang_brier(data, data_laporan.get("ringkasan_per_pasar")):
        print(baris)
    kalibrasi_w = data_laporan.get("kalibrasi_w") or {}
    print(
        "kalibrasi w replay: "
        f"n={kalibrasi_w.get('n')}, cukup_data={kalibrasi_w.get('cukup_data')} "
        "(tanpa harga pasar historis — DATA_INCOMPLETE, sesuai harapan)."
    )
    usulan = data_laporan.get("usulan")
    print(f"usulan replay: {len(usulan) if isinstance(usulan, list) else 'n/a'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
