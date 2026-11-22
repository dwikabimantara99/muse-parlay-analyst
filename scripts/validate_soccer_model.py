"""Validasi model Dixon-Coles sepak bola: holdout + rolling (Tahap 3 Langkah 5).

Dua bagian (pola yang sama dengan scripts/validate_nba_model.py):

  (a) HOLDOUT MUSIM PENUH. Fit atas musim <= 2024/25 (gabungan, tim =
      satu entitas lintas musim) -> prediksi SEMUA laga musim 2025/26.
      Tim promosi yang tidak ada di data fit diprediksi dengan
      attack = defence = 1,0 (dicatat, bukan dikarang).
  (b) ROLLING POINT-IN-TIME (pola 1b — JANGAN ulangi kesalahan
      look-ahead langkah 1 NBA). Musim 2025/26 dibagi 38 ronde
      (10 laga per ronde, urut tanggal). Untuk ronde r, fit HANYA
      dari laga dengan tanggal < tanggal pertama ronde r (semua musim
      sejak 2022/23), lalu prediksi laga ronde r. Fit tiap ronde
      memakai warm start dari fit ronde sebelumnya (hanya ~10 laga
      baru) agar runtime wajar. Klimatologi tiap ronde juga
      point-in-time (frekuensi dasar dari data latih ronde itu saja).

Metrik (per laga, lalu dirata-rata):
  - Brier 1X2: rata-rata (p-o)^2 atas 3 hasil; pembanding: klimatologi
    (frekuensi dasar) dan tebakan 1/3 (Brier = 2/3 persis).
  - Brier Over/Under 2.5 + akurasi (prediksi Over bila p_over > 0,5);
    pembanding klimatologi (frekuensi Over dasar).
  - Brier BTTS; pembanding klimatologi (frekuensi BTTS dasar).
  - Bonus: akurasi 1X2 (argmax) + ringkasan kalibrasi O/U dan BTTS
    (engine.validation.calibration_summary).

Data: CSV football-data.co.uk lokal di data/ (hanya kolom hasil).
TIDAK memanggil Odds API / API jup.ag. TIDAK memakai odds Pinnacle
(stale sejak 23/07/2025) — jadi Brier PASAR adalah DATA_INCOMPLETE:
tidak ada harga pasar historis yang bisa dipakai sebagai pembanding.

Jalankan dari root repo:
  python3 scripts/validate_soccer_model.py [--leagues EPL LaLiga]
      [--seasons-fit 2223 2324 2425] [--season-uji 2526]
      [--data-dir data] [--out out/validation_soccer.json]
      [--out-rolling out/validation_soccer_rolling.json]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import validation as validasi_mod
from ingest import football_data

REPO_ROOT = Path(__file__).resolve().parent.parent

# Laga per ronde (10 laga x 38 ronde = 380 laga satu musim penuh).
LAGA_PER_RONDE = 10

KETERBATASAN = [
    "Brier pasar DATA_INCOMPLETE: tidak ada harga pasar historis yang "
    "dipakai — odds Pinnacle di CSV stale sejak 23/07/2025 dan TIDAK "
    "dipakai, jadi Brier model tidak bisa dibandingkan dengan Brier pasar.",
    "Kekuatan tim fit adalah gabungan lintas musim (satu entitas per tim) "
    "— skuad berubah antar musim, jadi kekuatan agak basi untuk tim yang "
    "banyak berubah.",
    "Tim promosi tanpa sejarah di data fit diprediksi dengan attack = "
    "defence = 1,0 (rata-rata liga) — terutama memengaruhi ronde awal.",
    "Tidak ada penyesuaian cedera/absensi, jadwal padat, atau motivasi — "
    "model hanya membaca skor historis.",
    "Satu musim holdout (380 laga) adalah gambaran, bukan bukti — "
    "selisih Brier kecil antar model bisa jadi noise.",
]


def _muat_modul_fit():
    """Muat scripts/fit_soccer_params.py (pakai ulang fit + prediksi)."""
    path = REPO_ROOT / "scripts" / "fit_soccer_params.py"
    spek = importlib.util.spec_from_file_location("fit_soccer_params", path)
    modul = importlib.util.module_from_spec(spek)
    spek.loader.exec_module(modul)
    return modul


def brier_1x2(pairs: list[tuple[tuple[float, float, float], int]]) -> float:
    """Brier multi-kelas 1X2: rata-rata sum_c (p_c - o_c)^2.

    pairs: ((p_home, p_draw, p_away), outcome) dengan outcome 0=kandang
    menang, 1=seri, 2=tandang menang. Raise ValueError bila kosong /
    peluang tidak valid / tidak berjumlah ~1.
    """
    if not pairs:
        raise ValueError("pairs 1X2 tidak boleh kosong")
    total = 0.0
    for peluang, hasil in pairs:
        if len(peluang) != 3:
            raise ValueError(f"peluang 1X2 harus 3 nilai: {peluang!r}")
        if hasil not in (0, 1, 2):
            raise ValueError(f"outcome 1X2 harus 0/1/2: {hasil!r}")
        jumlah = 0.0
        for p in peluang:
            if (
                isinstance(p, bool)
                or not isinstance(p, (int, float))
                or not math.isfinite(p)
                or not 0.0 <= p <= 1.0
            ):
                raise ValueError(f"peluang 1X2 tidak valid: {p!r}")
            jumlah += p
        if abs(jumlah - 1.0) > 1e-5:
            # Toleransi 1e-5: record per laga menyimpan peluang yang
            # sudah dibulatkan 6 desimal (galat jumlah maks 1,5e-6).
            raise ValueError(f"peluang 1X2 harus berjumlah 1: {jumlah}")
        for c in range(3):
            o = 1.0 if hasil == c else 0.0
            total += (peluang[c] - o) ** 2
    return total / len(pairs)


def frekuensi_dasar(laga_latih: list[dict]) -> dict:
    """Frekuensi dasar (klimatologi) dari data latih.

    Mengembalikan p_home_win/p_draw/p_away_win/p_over_2.5/p_btts.
    Raise ValueError bila data latih kosong.
    """
    if not laga_latih:
        raise ValueError("data latih kosong — klimatologi tidak bisa dihitung")
    n = len(laga_latih)
    menang_kandang = sum(1 for m in laga_latih if m["home_goals"] > m["away_goals"])
    seri = sum(1 for m in laga_latih if m["home_goals"] == m["away_goals"])
    menang_tandang = n - menang_kandang - seri
    over = sum(1 for m in laga_latih if m["home_goals"] + m["away_goals"] > 2.5)
    btts = sum(1 for m in laga_latih if m["home_goals"] > 0 and m["away_goals"] > 0)
    return {
        "p_home_win": menang_kandang / n,
        "p_draw": seri / n,
        "p_away_win": menang_tandang / n,
        "p_over_2.5": over / n,
        "p_btts": btts / n,
        "n_latih": n,
    }


def bagi_ronde(
    laga_musim: list[dict], ukuran: int = LAGA_PER_RONDE
) -> list[list[dict]]:
    """Bagi laga satu musim jadi ronde-ronde urut tanggal (10 laga/ronde).

    Laga diurutkan tanggal menaik dulu; ronde = potongan berurutan.
    Ronde terakhir boleh lebih kecil bila jumlah laga bukan kelipatan.
    """
    urut = sorted(laga_musim, key=lambda m: (m["date"], m["home_team"], m["away_team"]))
    return [urut[i : i + ukuran] for i in range(0, len(urut), ukuran)]


def _outcome_1x2(laga: dict) -> int:
    """0 = kandang menang, 1 = seri, 2 = tandang menang."""
    if laga["home_goals"] > laga["away_goals"]:
        return 0
    if laga["home_goals"] == laga["away_goals"]:
        return 1
    return 2


def evaluasi_laga(modul_fit, hasil_fit: dict, laga: dict, klim: dict) -> dict:
    """Prediksi satu laga + nilai terhadap hasil aktual + klimatologi."""
    pred = modul_fit.prediksi_laga(hasil_fit, laga["home_team"], laga["away_team"])
    outcome = _outcome_1x2(laga)
    over_aktual = laga["home_goals"] + laga["away_goals"] > 2.5
    btts_aktual = laga["home_goals"] > 0 and laga["away_goals"] > 0
    return {
        "date": laga["date"],
        "season": laga["season_label"],
        "home_team": laga["home_team"],
        "away_team": laga["away_team"],
        "home_goals": laga["home_goals"],
        "away_goals": laga["away_goals"],
        "outcome_1x2": outcome,
        "p_home_win": round(pred["home_win"], 6),
        "p_draw": round(pred["draw"], 6),
        "p_away_win": round(pred["away_win"], 6),
        "p_over_2.5": round(pred["over_2.5"], 6),
        "p_btts": round(pred["btts_yes"], 6),
        "actual_over_2.5": over_aktual,
        "actual_btts": btts_aktual,
        "lambda_home": round(pred["lambda_home"], 4),
        "lambda_away": round(pred["lambda_away"], 4),
        "tim_tidak_dikenal": pred["tim_tidak_dikenal"],
        "klim_p_home_win": round(klim["p_home_win"], 6),
        "klim_p_draw": round(klim["p_draw"], 6),
        "klim_p_away_win": round(klim["p_away_win"], 6),
        "klim_p_over_2.5": round(klim["p_over_2.5"], 6),
        "klim_p_btts": round(klim["p_btts"], 6),
    }


def hitung_metrik(records: list[dict]) -> dict:
    """Hitung semua metrik validasi dari daftar record per laga."""
    if not records:
        raise ValueError("tidak ada record laga untuk dihitung metriknya")
    pairs_model = [
        (
            (r["p_home_win"], r["p_draw"], r["p_away_win"]),
            r["outcome_1x2"],
        )
        for r in records
    ]
    pairs_klim = [
        (
            (r["klim_p_home_win"], r["klim_p_draw"], r["klim_p_away_win"]),
            r["outcome_1x2"],
        )
        for r in records
    ]
    pairs_sepertiga = [
        ((1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0), r["outcome_1x2"]) for r in records
    ]
    pairs_over_model = [(r["p_over_2.5"], r["actual_over_2.5"]) for r in records]
    pairs_over_klim = [(r["klim_p_over_2.5"], r["actual_over_2.5"]) for r in records]
    pairs_btts_model = [(r["p_btts"], r["actual_btts"]) for r in records]
    pairs_btts_klim = [(r["klim_p_btts"], r["actual_btts"]) for r in records]
    n = len(records)
    akurasi_over = (
        sum(1 for r in records if (r["p_over_2.5"] > 0.5) == r["actual_over_2.5"]) / n
    )
    akurasi_1x2 = (
        sum(
            1
            for r in records
            if max(
                range(3),
                key=lambda c: (r["p_home_win"], r["p_draw"], r["p_away_win"])[c],
            )
            == r["outcome_1x2"]
        )
        / n
    )
    kal_over = validasi_mod.calibration_summary(pairs_over_model)
    kal_btts = validasi_mod.calibration_summary(pairs_btts_model)

    def _selisih_berpasangan(pairs_a, pairs_b):
        """Selisih Brier berpasangan (A - B) + SE + z (uji t sederhana).

        pairs_a/pairs_b: daftar ((p_home, p_draw, p_away), outcome) atau
        daftar (p, terjadi) — dipakai untuk 1X2 (multi-kelas) dan O/U
        + BTTS (biner). z = mean/SE; |z| > 2 kira-kira signifikan 5%.
        """
        selisih = []
        for a, b in zip(pairs_a, pairs_b, strict=True):
            if isinstance(a[0], tuple):
                # Multi-kelas 1X2: ((p_h, p_d, p_a), outcome).
                outcome = a[1]
                brier_a = sum(
                    (p - (1.0 if outcome == c else 0.0)) ** 2
                    for c, p in enumerate(a[0])
                )
                brier_b = sum(
                    (p - (1.0 if outcome == c else 0.0)) ** 2
                    for c, p in enumerate(b[0])
                )
            else:
                # Biner: (p, terjadi).
                brier_a = (a[0] - (1.0 if a[1] else 0.0)) ** 2
                brier_b = (b[0] - (1.0 if b[1] else 0.0)) ** 2
            selisih.append(brier_a - brier_b)
        mean = statistics.fmean(selisih)
        se = (
            statistics.stdev(selisih) / math.sqrt(len(selisih))
            if len(selisih) > 1
            else 0.0
        )
        return {
            "mean": round(mean, 6),
            "se": round(se, 6),
            "z": round(mean / se, 2) if se > 0 else None,
        }

    return {
        "n": n,
        "brier_1x2": {
            "model": round(brier_1x2(pairs_model), 6),
            "klimatologi": round(brier_1x2(pairs_klim), 6),
            "tebakan_sepertiga": round(brier_1x2(pairs_sepertiga), 6),
            "selisih_model_vs_klim": _selisih_berpasangan(pairs_model, pairs_klim),
        },
        "akurasi_1x2_argmax": round(akurasi_1x2, 6),
        "brier_over_2.5": {
            "model": round(validasi_mod.brier_score(pairs_over_model), 6),
            "klimatologi": round(validasi_mod.brier_score(pairs_over_klim), 6),
            "selisih_model_vs_klim": _selisih_berpasangan(
                pairs_over_model, pairs_over_klim
            ),
        },
        "akurasi_over_2.5": round(akurasi_over, 6),
        "frekuensi_over_aktual": round(
            sum(1 for r in records if r["actual_over_2.5"]) / n, 6
        ),
        "brier_btts": {
            "model": round(validasi_mod.brier_score(pairs_btts_model), 6),
            "klimatologi": round(validasi_mod.brier_score(pairs_btts_klim), 6),
            "selisih_model_vs_klim": _selisih_berpasangan(
                pairs_btts_model, pairs_btts_klim
            ),
        },
        "frekuensi_btts_aktual": round(
            sum(1 for r in records if r["actual_btts"]) / n, 6
        ),
        "kalibrasi_over_2.5": {
            "mean_prediksi": round(kal_over["mean_prediksi"], 6),
            "frekuensi_aktual": round(kal_over["frekuensi_aktual"], 6),
            "brier": round(kal_over["brier"], 6),
        },
        "kalibrasi_btts": {
            "mean_prediksi": round(kal_btts["mean_prediksi"], 6),
            "frekuensi_aktual": round(kal_btts["frekuensi_aktual"], 6),
            "brier": round(kal_btts["brier"], 6),
        },
        "n_laga_tim_tidak_dikenal": sum(1 for r in records if r["tim_tidak_dikenal"]),
    }


def jalankan_holdout(
    modul_fit,
    liga: str,
    laga_latih: list[dict],
    laga_uji: list[dict],
) -> dict:
    """Holdout: fit atas laga_latih -> prediksi semua laga_uji."""
    mulai = time.perf_counter()
    hasil_fit = modul_fit.fit_dixon_coles(laga_latih)
    klim = frekuensi_dasar(laga_latih)
    records = [evaluasi_laga(modul_fit, hasil_fit, laga, klim) for laga in laga_uji]
    waktu = time.perf_counter() - mulai
    return {
        "liga": liga,
        "n_latih": len(laga_latih),
        "n_uji": len(laga_uji),
        "waktu_detik": round(waktu, 1),
        "fit": {
            "rho": round(hasil_fit["rho"], 4),
            "avg_home_goals": round(hasil_fit["avg_home_goals"], 4),
            "avg_away_goals": round(hasil_fit["avg_away_goals"], 4),
            "home_advantage_ratio": round(hasil_fit["home_advantage_ratio"], 4),
            "loglik": round(hasil_fit["loglik"], 2),
            "n_sweeps": hasil_fit["n_sweeps"],
            "converged": hasil_fit["converged"],
        },
        "klimatologi_latih": {
            k: round(v, 6) if isinstance(v, float) else v for k, v in klim.items()
        },
        "metrik": hitung_metrik(records),
        "hasil_per_laga": records,
    }


def jalankan_rolling(
    modul_fit,
    liga: str,
    laga_latih_awal: list[dict],
    laga_uji: list[dict],
) -> dict:
    """Rolling point-in-time: per ronde, fit dari laga SEBELUM ronde itu.

    laga_latih_awal: semua laga musim fit (sebelum musim uji).
    laga_uji: semua laga musim uji, dibagi ronde urut tanggal.
    """
    mulai = time.perf_counter()
    ronde_list = bagi_ronde(laga_uji)
    semua_records: list[dict] = []
    per_ronde: list[dict] = []
    warm_start = None
    latih_berjalan = list(laga_latih_awal)
    for nomor, ronde in enumerate(ronde_list, start=1):
        tanggal_uji = min(m["date"] for m in ronde)
        # Point-in-time: HANYA laga dengan tanggal < tanggal uji.
        latih = [m for m in latih_berjalan if m["date"] < tanggal_uji]
        hasil_fit = modul_fit.fit_dixon_coles(latih, warm_start=warm_start)
        warm_start = hasil_fit
        klim = frekuensi_dasar(latih)
        records = [evaluasi_laga(modul_fit, hasil_fit, laga, klim) for laga in ronde]
        metrik_ronde = hitung_metrik(records)
        per_ronde.append(
            {
                "ronde": nomor,
                "tanggal_uji": tanggal_uji,
                "n_latih": len(latih),
                "n_uji": len(ronde),
                "rho": round(hasil_fit["rho"], 4),
                "n_sweeps": hasil_fit["n_sweeps"],
                "converged": hasil_fit["converged"],
                "brier_1x2_model": metrik_ronde["brier_1x2"]["model"],
                "brier_1x2_klimatologi": metrik_ronde["brier_1x2"]["klimatologi"],
                "brier_over_2.5_model": metrik_ronde["brier_over_2.5"]["model"],
                "brier_btts_model": metrik_ronde["brier_btts"]["model"],
            }
        )
        semua_records.extend(records)
        latih_berjalan.extend(ronde)
    waktu = time.perf_counter() - mulai
    return {
        "liga": liga,
        "n_ronde": len(ronde_list),
        "n_latih_awal": len(laga_latih_awal),
        "n_uji": len(laga_uji),
        "waktu_detik": round(waktu, 1),
        "metrik": hitung_metrik(semua_records),
        "per_ronde": per_ronde,
        "hasil_per_laga": semua_records,
    }


def _cek_silang_fit_json(hasil_holdout: dict, path_fit: Path) -> dict | None:
    """Bandingkan rho fit holdout vs out/fit_soccer_params.json (bila ada).

    Kedua fit memakai data + kode yang sama, jadi nilainya HARUS sama
    (selisih hanya dari pembulatan JSON 4 desimal). Selisih besar
    berarti ada yang tidak konsisten — dilaporkan, bukan disembunyikan.
    """
    if not path_fit.exists():
        return {"status": "DILEWATI", "alasan": f"file tidak ada: {path_fit}"}
    try:
        data_fit = json.loads(path_fit.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "DILEWATI", "alasan": f"tidak bisa dibaca: {exc}"}
    cek = {}
    for liga, hasil in hasil_holdout.items():
        pooled = ((data_fit.get("leagues") or {}).get(liga) or {}).get("pooled")
        if not pooled:
            cek[liga] = {"status": "DILEWATI", "alasan": "pooled tidak ada di JSON fit"}
            continue
        cek[liga] = {
            "rho_holdout": hasil["fit"]["rho"],
            "rho_fit_json": pooled.get("rho"),
            "selisih_rho": round(hasil["fit"]["rho"] - pooled.get("rho", 0.0), 4),
            "avg_home_holdout": hasil["fit"]["avg_home_goals"],
            "avg_home_fit_json": pooled.get("avg_home_goals"),
        }
    return cek


def main(argv: list[str] | None = None) -> int:
    """Jalankan validasi dari CLI. 0 sukses, 2 data tidak tersedia."""
    parser = argparse.ArgumentParser(
        description="Validasi model Dixon-Coles: holdout + rolling point-in-time."
    )
    parser.add_argument(
        "--leagues",
        nargs="+",
        default=["EPL", "LaLiga"],
        help="liga yang divalidasi (default: EPL LaLiga)",
    )
    parser.add_argument(
        "--seasons-fit",
        nargs="+",
        default=["2223", "2324", "2425"],
        help="musim latih (default: 2223 2324 2425)",
    )
    parser.add_argument(
        "--season-uji",
        default="2526",
        help="musim uji holdout/rolling (default: 2526)",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="direktori CSV hasil (default: data)",
    )
    parser.add_argument(
        "--out",
        default="out/validation_soccer.json",
        help="file JSON holdout (default: out/validation_soccer.json)",
    )
    parser.add_argument(
        "--out-rolling",
        default="out/validation_soccer_rolling.json",
        help="file JSON rolling (default: out/validation_soccer_rolling.json)",
    )
    parser.add_argument(
        "--tanpa-rolling",
        action="store_true",
        help="hanya holdout (lewati rolling)",
    )
    args = parser.parse_args(argv)
    data_dir = REPO_ROOT / args.data_dir
    out_path = REPO_ROOT / args.out
    out_rolling_path = REPO_ROOT / args.out_rolling
    modul_fit = _muat_modul_fit()

    holdout: dict[str, dict] = {}
    rolling: dict[str, dict] = {}
    for liga in args.leagues:
        try:
            laga_latih, _ = football_data.muat_musim(data_dir, liga, args.seasons_fit)
            laga_uji, _ = football_data.muat_musim(data_dir, liga, [args.season_uji])
        except (FileNotFoundError, ValueError) as exc:
            print(f"validasi dibatalkan ({liga}): {exc}", file=sys.stderr)
            return 2
        print(
            f"{liga} holdout: fit {len(laga_latih)} laga "
            f"({', '.join(football_data.label_musim(m) for m in args.seasons_fit)}) "
            f"-> prediksi {len(laga_uji)} laga "
            f"{football_data.label_musim(args.season_uji)} ..."
        )
        holdout[liga] = jalankan_holdout(modul_fit, liga, laga_latih, laga_uji)
        m = holdout[liga]["metrik"]
        print(
            f"  Brier 1X2 model {m['brier_1x2']['model']} vs klim "
            f"{m['brier_1x2']['klimatologi']} vs 1/3 "
            f"{m['brier_1x2']['tebakan_sepertiga']}; "
            f"Brier O/U {m['brier_over_2.5']['model']} vs klim "
            f"{m['brier_over_2.5']['klimatologi']}; "
            f"Brier BTTS {m['brier_btts']['model']} vs klim "
            f"{m['brier_btts']['klimatologi']} "
            f"({holdout[liga]['waktu_detik']} dtk)"
        )
        if not args.tanpa_rolling:
            print(f"{liga} rolling: {len(laga_uji)} laga, refit per ronde ...")
            rolling[liga] = jalankan_rolling(modul_fit, liga, laga_latih, laga_uji)
            mr = rolling[liga]["metrik"]
            print(
                f"  Brier 1X2 model {mr['brier_1x2']['model']} vs klim "
                f"{mr['brier_1x2']['klimatologi']}; "
                f"Brier O/U {mr['brier_over_2.5']['model']} vs klim "
                f"{mr['brier_over_2.5']['klimatologi']}; "
                f"Brier BTTS {mr['brier_btts']['model']} vs klim "
                f"{mr['brier_btts']['klimatologi']} "
                f"({rolling[liga]['waktu_detik']} dtk)"
            )

    dasar = {
        "generated_at": datetime.now(UTC).isoformat(),
        "engine": {"name": "football_sim (Dixon-Coles)", "version": "1.0.0"},
        "metode": {
            "musim_latih": [football_data.label_musim(m) for m in args.seasons_fit],
            "musim_uji": football_data.label_musim(args.season_uji),
            "sumber_data": (
                "football-data.co.uk (CSV lokal di data/; hanya kolom hasil FTHG/FTAG)"
            ),
            "brier_1x2": "rata-rata (p-o)^2 atas 3 hasil",
            "brier_pasar": "DATA_INCOMPLETE (odds Pinnacle stale sejak "
            "23/07/2025, tidak dipakai)",
        },
        "keterbatasan": KETERBATASAN,
    }
    hasil_holdout = {
        **dasar,
        "mode": "holdout musim penuh",
        "cek_silang_fit_json": _cek_silang_fit_json(
            holdout, REPO_ROOT / "out" / "fit_soccer_params.json"
        ),
        "hasil": holdout,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(hasil_holdout, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"hasil holdout ditulis ke {out_path}")
    if not args.tanpa_rolling:
        hasil_rolling = {
            **dasar,
            "mode": (
                "rolling point-in-time: per ronde, fit hanya dari laga "
                "SEBELUM tanggal pertama ronde itu (warm start dari fit "
                "ronde sebelumnya)"
            ),
            "hasil": rolling,
        }
        out_rolling_path.parent.mkdir(parents=True, exist_ok=True)
        out_rolling_path.write_text(
            json.dumps(hasil_rolling, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"hasil rolling ditulis ke {out_rolling_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
