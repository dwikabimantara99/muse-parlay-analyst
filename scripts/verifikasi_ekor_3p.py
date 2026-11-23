"""Verifikasi ekor 3P: DEN@CHI vs OKC@MIA, model lama vs model baru.

Menjawab pertanyaan wajib item 4: apakah model baru (sigma_total per
laga dari laju 3PA) melihat DEN@CHI 22 Nov 2026 lebih berisiko SEJAK
AWAL dibanding model lama (sigma global)? Dan apakah model baru
mengacaukan laga biasa (OKC@MIA, 22 Nov 2026)?

INPUT = INPUT PRA-LAGA ASLI: paket inputs nba_brain yang tersimpan di
out/analysis_verif_tahap4_2026-11-22.json (sim pra-laga 21:57 UTC,
22 Nov 2026 — run yang sama dengan yang dipakai audit tiket nyata:
median 233, P(Under 252,5) 84,47% untuk DEN@CHI) — statistik musim +
last10 + pemain + cedera + rest_days yang SAMA PERSIS dengan yang
dipakai sim pra-laga historis itu. Satu-satunya penambahan adalah blok "tembakan_3p" per tim (laju 3PA + 3P% dari
laga sebelum 22 Nov 2026, scripts/fit_ekor_3p.py laju_3pa_sebelum —
kuantitas yang SAMA dengan yang akan diisi ingest.nba_brain dari
BBRef totals-team musim berjalan; BBRef per 22 Nov pra-laga memuat
laga s.d. 21 Nov, identik dengan leaguegamefinder s.d. 21 Nov).
Skenario "lama" HARUS mereproduksi angka historis (median 233,
P(Under 252,5) ~84,5%) — bila tidak, ada drift config/input yang
harus dijelaskan, bukan ditutup-tutupi.

SKENARIO PER LAGA (seed + iterasi sama — common random numbers,
jadi perbedaan antar skenario murni dari sigma):
  - "lama": config TANPA section ekor_3p + input TANPA tembakan_3p
    (perilaku persis sebelum item ini).
  - "baru_produksi": config playstyle.yaml apa adanya (slope_aktif 0)
    + input DENGAN tembakan_3p.
  - "kontrafaktual_binomial": slope_aktif = slope binomial teoritis
    (+2,0689 dari out/fit_ekor_3p.json) — "bagaimana bila mekanisme
    binomial dipakai apa adanya".
  - "kontrafaktual_fit": slope_aktif = slope fit (-0,3364) — "bagaimana
    bila nilai fit dipakai apa adanya (tanpa ambang signifikansi)".
  - "sintetis_3pa_tinggi" (hanya DEN@CHI): input sama, tapi laju 3PA
    kedua tim diganti 45,0/laga (gabungan 90,0) + slope binomial —
    membuktikan mesinnya BEKERJA (sigma membesar ke arah yang
    dimaksud) walau slope produksi 0. Diberi label SINTETIS jelas.

METRIK: median/mean/std/p95 total, P(Under 252,5), P(Under 250,5),
P(total >= 264,5) (garis tahan-banjir Asuransi historis), P(total >=
296) (total akhir aktual DEN@CHI), P(Under 252,5 | banjir_3p) dan
P(Under 252,5 | setan) via engine/stress.py (geser dari config).

KONTEKS AKTUAL (bukan hasil sim): DEN@CHI berakhir 296 (OT),
42 tripoin masuk dari 90 percobaan; OKC@MIA berakhir 236
(MIA 123 – OKC 113). Total akhir DEN@CHI dari laporan insiden;
OKC@MIA dari cache leaguegamefinder 22 Nov 2026.

Jalankan dari root repo:
  python3 scripts/verifikasi_ekor_3p.py [--out out/verifikasi_ekor_3p.json]
  [--iterations 100000] [--seed 20261122]
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine import nba_sim
from engine import stress as stress_mod

REPO_ROOT = Path(__file__).resolve().parent.parent


def _muat_skrip(nama: str):
    """Muat modul dari scripts/ (bukan package) via importlib."""
    spek = importlib.util.spec_from_file_location(
        nama, REPO_ROOT / "scripts" / f"{nama}.py"
    )
    modul = importlib.util.module_from_spec(spek)
    spek.loader.exec_module(modul)
    return modul


fit_ekor_3p = _muat_skrip("fit_ekor_3p")

SEASONS = ["2024-25", "2025-26", "2026-27"]
TANGGAL_UJI = "2026-11-22"
ANALYSIS_FILE = "out/analysis_verif_tahap4_2026-11-22.json"
# Garis tangga untuk CDF total (mencakup garis tiket historis,
# garis tahan-banjir, dan total akhir aktual).
GARIS_TOTAL = [222.5, 230.5, 238.5, 246.5, 250.5, 252.5, 258.5, 264.5, 296.5]

# match_id di file analysis -> label + konteks aktual.
LAGA_UJI = {
    "nba-2026-11-22-den-chi": {
        "label": "DEN@CHI",
        "total_akhir": 296,
        "catatan_aktual": "OT; 42 tripoin masuk dari 90 percobaan (DEN 17-35, CHI 25-55)",
        "median_historis": 233,
        "p_under_2525_historis": 0.8447,
    },
    "nba-2026-11-22-okc-mia": {
        "label": "OKC@MIA",
        "total_akhir": 236,
        "catatan_aktual": "MIA 123 – OKC 113",
        "median_historis": 220,
        "p_under_2525_historis": 0.95067,
    },
}


def muat_inputs_asli(analysis_path: Path) -> dict[str, dict]:
    """Muat paket inputs pra-laga asli dari file analysis tersimpan.

    Mengembalikan {match_id: inputs}. Raise RuntimeError bila file
    tidak ada / laga uji tidak ditemukan / inputs tidak lengkap.
    """
    if not analysis_path.exists():
        raise RuntimeError(f"file analysis tidak ditemukan: {analysis_path}")
    data = json.loads(analysis_path.read_text(encoding="utf-8"))
    hasil = {}
    for match in data.get("matches", []):
        match_id = match.get("match_id")
        if match_id not in LAGA_UJI:
            continue
        inputs = (match.get("nba_analysis") or {}).get("inputs")
        if not isinstance(inputs, dict) or "home" not in inputs or "away" not in inputs:
            raise RuntimeError(f"inputs {match_id} tidak lengkap di {analysis_path}")
        hasil[match_id] = copy.deepcopy(inputs)
    hilang = [mid for mid in LAGA_UJI if mid not in hasil]
    if hilang:
        raise RuntimeError(f"laga uji tidak ditemukan di {analysis_path}: {hilang}")
    return hasil


def tambah_tembakan_3p(inputs: dict, fg3a_records: list[dict]) -> dict:
    """Tambahkan blok tembakan_3p point-in-time ke kedua blok tim.

    Laju dihitung dari laga sebelum TANGGAL_UJI (scripts/fit_ekor_3p
    laju_3pa_sebelum, ambang MIN_LAGA_UNTUK_LAJU yang sama dengan
    fit). Sumber dicatat apa adanya (stats.nba.com tier 1 —
    rekonstruksi; produksi memakai BBRef tier 2 atas kuantitas yang
    sama). Mengembalikan inputs baru (tidak mengubah argumen).
    """
    riwayat: dict[str, list[dict]] = {}
    for rec in fg3a_records:
        if str(rec.get("season")) == "2026-27":
            riwayat.setdefault(str(rec.get("tricode")), []).append(rec)
    hasil = copy.deepcopy(inputs)
    for kunci in ("home", "away"):
        blok = hasil[kunci]
        laju = fit_ekor_3p.laju_3pa_sebelum(
            riwayat.get(blok["tricode"], []),
            TANGGAL_UJI,
            fit_ekor_3p.MIN_LAGA_UNTUK_LAJU,
        )
        if laju is None:
            blok["tembakan_3p"] = None
            continue
        blok["tembakan_3p"] = {
            "fg3a_per_game": round(laju["fg3a_per_game"], 4),
            "fg3_per_game": None,
            "fg3_pct": (
                round(laju["fg3_pct"], 4) if laju["fg3_pct"] is not None else None
            ),
            "games": laju["n_laga"],
            "source": "stats.nba.com",
            "tier": 1,
            "fetched_at": "rekonstruksi point-in-time (laga sebelum 2026-11-22)",
        }
    return hasil


def _metrik(hasil_sim: dict, geser_banjir: float, geser_setan: float) -> dict:
    """Metrik perbandingan dari satu hasil simulate()."""
    markets = hasil_sim["markets"]
    dist_total = hasil_sim["score_distribution"]["total"]
    cdf = stress_mod.cdf_total_dari_markets(markets)
    return {
        "median_total": dist_total["median"],
        "mean_total": dist_total["mean"],
        "std_total": dist_total["std"],
        "p95_total": dist_total["p95"],
        "p_under_252.5": markets.get("total_under_252.5"),
        "p_under_250.5": markets.get("total_under_250.5"),
        "p_total_lebih_264.5": (
            round(1.0 - markets["total_under_264.5"], 6)
            if "total_under_264.5" in markets
            else None
        ),
        "p_total_lebih_296": (
            round(1.0 - markets["total_under_296.5"], 6)
            if "total_under_296.5" in markets
            else None
        ),
        "p_under_252.5_banjir_3p": round(
            stress_mod.p_under_digeser(cdf, 252.5, geser_banjir), 6
        ),
        "p_under_252.5_setan": round(
            stress_mod.p_under_digeser(cdf, 252.5, geser_setan), 6
        ),
        "sigma_total_dipakai": hasil_sim["inputs_summary"]["sigma_total_points"],
        "sigma_total_global": hasil_sim["inputs_summary"]["sigma_total_global_points"],
        "ekor_3p": hasil_sim["inputs_summary"]["ekor_3p"],
        "ot_probability": hasil_sim["score_distribution"]["ot_probability"],
    }


def main(argv: list[str] | None = None) -> int:
    """Jalankan verifikasi dari CLI. 0 sukses, 2 data tidak tersedia."""
    parser = argparse.ArgumentParser(
        description="Verifikasi ekor 3P: DEN@CHI vs OKC@MIA, lama vs baru."
    )
    parser.add_argument(
        "--out",
        default="out/verifikasi_ekor_3p.json",
        help="file JSON hasil verifikasi (default: out/verifikasi_ekor_3p.json)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100000,
        help="iterasi simulasi per skenario (default: 100000)",
    )
    parser.add_argument(
        "--seed", type=int, default=20261122, help="seed RNG (default: 20261122)"
    )
    args = parser.parse_args(argv)
    repo_root = REPO_ROOT
    data_dir = repo_root / "data" / "nba_history"
    cache_dir = repo_root / "out" / "cache"
    out_path = repo_root / args.out

    try:
        cfg = config_mod.load_playstyle()
        geser_banjir = float(config_mod.get_value(cfg, "stress", "banjir_3p_points"))
        geser_setan = float(config_mod.get_value(cfg, "stress", "setan_points"))
        fit_json = json.loads(
            (repo_root / "out" / "fit_ekor_3p.json").read_text(encoding="utf-8")
        )
        slope_fit = float(fit_json["regresi"]["varians_total_vs_3pa"]["slope"])
        slope_binomial = float(fit_json["slope_binomial_teoritis"]["value"])
        inputs_asli = muat_inputs_asli(repo_root / ANALYSIS_FILE)
        fg3a_records, _info_fg3a = fit_ekor_3p.muat_fg3a(SEASONS, data_dir, cache_dir)
    except (config_mod.ConfigError, RuntimeError, OSError, KeyError, ValueError) as exc:
        print(f"verifikasi dibatalkan: {exc}", file=sys.stderr)
        return 2

    lines = {"spreads": [], "totals": GARIS_TOTAL}
    cfg_lama = copy.deepcopy(cfg)
    cfg_lama.pop("ekor_3p", None)
    cfg_binomial = copy.deepcopy(cfg)
    cfg_binomial["ekor_3p"]["slope_aktif"] = slope_binomial
    cfg_fit = copy.deepcopy(cfg)
    cfg_fit["ekor_3p"]["slope_aktif"] = slope_fit

    hasil: dict = {
        "tanggal_uji": TANGGAL_UJI,
        "seed": args.seed,
        "iterations": args.iterations,
        "sumber_inputs": (
            f"{ANALYSIS_FILE} (paket inputs nba_brain pra-laga asli, "
            "sim 22 Nov 2026 21:57 UTC — run yang sama dengan audit "
            "tiket nyata) + blok tembakan_3p point-in-time dari "
            "leaguegamefinder (laga sebelum 22 Nov 2026)"
        ),
        "slope_fit": slope_fit,
        "slope_binomial_teoritis": slope_binomial,
        "slope_produksi": cfg.get("ekor_3p", {}).get("slope_aktif"),
        "geser_banjir_3p_points": geser_banjir,
        "geser_setan_points": geser_setan,
        "laga": {},
    }
    for match_id, konteks in LAGA_UJI.items():
        label = konteks["label"]
        inputs = tambah_tembakan_3p(inputs_asli[match_id], fg3a_records)
        inputs_tanpa_3p = copy.deepcopy(inputs)
        inputs_tanpa_3p["home"]["tembakan_3p"] = None
        inputs_tanpa_3p["away"]["tembakan_3p"] = None
        skenario = {}
        skenario["lama"] = _metrik(
            nba_sim.simulate(
                inputs_tanpa_3p,
                cfg=cfg_lama,
                lines=lines,
                seed=args.seed,
                iterations=args.iterations,
            ),
            geser_banjir,
            geser_setan,
        )
        skenario["baru_produksi"] = _metrik(
            nba_sim.simulate(
                inputs,
                cfg=cfg,
                lines=lines,
                seed=args.seed,
                iterations=args.iterations,
            ),
            geser_banjir,
            geser_setan,
        )
        skenario["kontrafaktual_binomial"] = _metrik(
            nba_sim.simulate(
                inputs,
                cfg=cfg_binomial,
                lines=lines,
                seed=args.seed,
                iterations=args.iterations,
            ),
            geser_banjir,
            geser_setan,
        )
        skenario["kontrafaktual_fit"] = _metrik(
            nba_sim.simulate(
                inputs,
                cfg=cfg_fit,
                lines=lines,
                seed=args.seed,
                iterations=args.iterations,
            ),
            geser_banjir,
            geser_setan,
        )
        if label == "DEN@CHI":
            inputs_sintetis = copy.deepcopy(inputs)
            for blok in (inputs_sintetis["home"], inputs_sintetis["away"]):
                blok["tembakan_3p"] = {
                    "fg3a_per_game": 45.0,
                    "fg3_per_game": None,
                    "fg3_pct": None,
                    "games": 15,
                    "source": "SINTETIS (bukan data)",
                    "tier": None,
                    "fetched_at": None,
                }
            skenario["sintetis_3pa_tinggi_binomial"] = _metrik(
                nba_sim.simulate(
                    inputs_sintetis,
                    cfg=cfg_binomial,
                    lines=lines,
                    seed=args.seed,
                    iterations=args.iterations,
                ),
                geser_banjir,
                geser_setan,
            )
            skenario["sintetis_3pa_tinggi_binomial"]["label_sintetis"] = (
                "BUKAN DATA: laju 3PA kedua tim diganti 45,0/laga "
                "(gabungan 90,0) untuk membuktikan mesin penskalaan bekerja"
            )
        hasil["laga"][label] = {
            "aktual_total_akhir": konteks["total_akhir"],
            "catatan_aktual": konteks["catatan_aktual"],
            "median_historis": konteks["median_historis"],
            "p_under_2525_historis": konteks["p_under_2525_historis"],
            "tiga_pa_kandang": (
                inputs["home"]["tembakan_3p"]["fg3a_per_game"]
                if inputs["home"]["tembakan_3p"]
                else None
            ),
            "tiga_pa_tandang": (
                inputs["away"]["tembakan_3p"]["fg3a_per_game"]
                if inputs["away"]["tembakan_3p"]
                else None
            ),
            "skenario": skenario,
        }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(hasil, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for label, data_laga in hasil["laga"].items():
        print(
            f"\n== {label} (total akhir aktual: {data_laga['aktual_total_akhir']}) =="
        )
        print(
            f"   3PA pra-laga: tandang {data_laga['tiga_pa_tandang']}, "
            f"kandang {data_laga['tiga_pa_kandang']}, "
            f"gabungan {data_laga['tiga_pa_tandang'] + data_laga['tiga_pa_kandang']:.2f}"
        )
        if data_laga["median_historis"] is not None:
            print(
                f"   historis pra-laga: median {data_laga['median_historis']}, "
                f"P(Under 252,5) {data_laga['p_under_2525_historis']}"
            )
        header = (
            f"   {'skenario':<32} {'sigma':>6} {'median':>7} {'std':>6} "
            f"{'p95':>6} {'P(U252,5)':>10} {'P(>=264,5)':>11} {'P(>=296)':>8} "
            f"{'P(U252,5|banjir)':>16}"
        )
        print(header)
        for nama, metrik in data_laga["skenario"].items():
            print(
                f"   {nama:<32} {metrik['sigma_total_dipakai']:>6.2f} "
                f"{metrik['median_total']:>7.1f} {metrik['std_total']:>6.2f} "
                f"{metrik['p95_total']:>6.1f} {metrik['p_under_252.5']:>10.4f} "
                f"{metrik['p_total_lebih_264.5']:>11.4f} "
                f"{metrik['p_total_lebih_296']:>8.4f} "
                f"{metrik['p_under_252.5_banjir_3p']:>16.4f}"
            )
    print(f"\nhasil verifikasi ditulis ke {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
