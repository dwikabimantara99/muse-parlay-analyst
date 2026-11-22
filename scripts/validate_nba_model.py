"""Validasi Otak NBA: backtest + kalibrasi + uji kepekaan (Tahap 3 Langkah 1).

Jalankan dari root repo:
  python3 scripts/validate_nba_model.py [--per-musim 50] [--iterations 100000]

Tiga bagian:

  (a) BACKTEST. ~150 laga historis (50 terbaru per musim, 3 musim)
      disimulasikan penuh 100.000x, base case saja (scenarios=[]).
      Dua event per laga: (i) kandang menang, (ii) Under pada
      median+8 poin (bantalan Alt Under). Per laga dipakai dua pass
      dengan seed yang sama: pass 1 (lines=None) mengambil median
      total, pass 2 mengambil P(Under) pada garis median+8 yang
      dibulatkan ke 0,5 — seed sama berarti noise sama, jadi peluang
      Under itu persis dari draws yang sama.
  (b) KALIBRASI. Dari hasil backtest: reliability buckets + Brier
      model untuk kedua event (engine.validation). Brier PASAR:
      DATA_INCOMPLETE — tidak ada harga pasar historis.
  (c) KEPEKAAN. Satu laga nyata (DET @ ATL 2026-11-22): basis vs
      bintang absen, pace +/-2, sigma_total +/-20%, tanpa penalti
      B2B. Seed tetap di semua variasi agar perbandingan adil
      (common random numbers).

Inputs backtest dibangun dari data/nba_history/games_all.json +
ratings_bbref (statistik musim kedua tim, rata-rata liga, B2B dari
selisih tanggal, altitude dari tricode kandang DEN/UTA — otomatis
oleh engine). KETERBATASAN (dicatat di JSON + laporan): rating
musim penuh (bias look-ahead, sama seperti fit); last10 per tanggal
+ cedera per tanggal TIDAK tersedia untuk laga lama, jadi simulate()
fallback ke statistik musim dan tanpa penyesuaian pemain absen.

MODE ROLLING (--rolling; patch 1b, temuan auditor 1): backtest
memakai rating rolling point-in-time dari
scripts/fit_nba_params.py (bangun_rating_rolling) — stats_season +
stats_last10 per laga dari box score sebelum tanggal laga, prior
rating BBRef musim sebelumnya, lg_avg per tanggal. Dalam mode ini
keterbatasan look-ahead HILANG dan bobot resensi 60/40 beroperasi
(last10 statistik tim tersedia); yang TETAP tidak tersedia adalah
cedera per tanggal (backtest tetap tanpa penyesuaian pemain absen).
Subset laga SAMA dengan run v1 (50 terbaru/musim) agar Brier
sebanding. Uji kepekaan tidak berubah (inputs live, bukan historis).

Hasil ditulis ke out/validation_nba.json (gitignored) + ringkasan
di-print. TIDAK memanggil Odds API / API jup.ag. Satu-satunya
panggilan network: SATU kali ingest.nba_brain.fetch_match_inputs
(sumber gratis keyless, ter-cache) untuk inputs uji kepekaan — dan
hanya bila cache out/sensitivity_inputs_det_atl.json belum ada.
Mode rolling menambah fetch box score + prior BBRef BILA cache
data/nba_history/ belum ada (gratis, keyless).
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import math
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine import nba_sim, validation

REPO_ROOT = Path(__file__).resolve().parent.parent

# Laga nyata untuk uji kepekaan + seed tetapnya.
LAGA_KEPEKAAN = {"home": "ATL", "away": "DET", "game_date": "2026-11-22"}
SEED_KEPEKAAN = 20261122
# Bantalan Alt Under (poin di atas median proyeksi total).
BANTALAN_UNDER = 8.0

KETERBATASAN = [
    "Bias look-ahead: rating musim penuh BBRef 'melihat masa depan' "
    "(dihitung dari semua laga musim itu, termasuk laga yang "
    "diproyeksikan) — sama seperti fit; residual sedikit terlalu kecil.",
    "stats_last10 per tanggal TIDAK tersedia untuk laga historis — "
    "simulate() fallback ke statistik musim saja (bobot resensi 60/40 "
    "tidak beroperasi; efektif 100% musim).",
    "Cedera per tanggal TIDAK tersedia untuk laga historis — backtest "
    "tanpa penyesuaian pemain absen (tidak ada pemain OUT di input).",
    "B2B dari tanggal kalender saja (main sehari sebelumnya) — tidak "
    "membedakan B2B kandang/tandang/perjalanan jauh.",
    "Brier pasar DATA_INCOMPLETE: tidak ada harga pasar historis "
    "(sportsbook/bursa) untuk laga-laga backtest, jadi Brier model "
    "tidak bisa dibandingkan dengan Brier pasar.",
    "sigma_total mencakup varians OT (lihat LAPORAN-FIT-NBA.md §4) — "
    "sedikit konservatif untuk Under.",
    "Subset ~150 laga: tiap bucket kalibrasi berisi sedikit laga, "
    "jadi frekuensi aktual per bucket punya ketidakpastian besar — "
    "hasil ini gambaran, bukan bukti kalibrasi.",
]

# Keterbatasan mode rolling (--rolling): look-ahead hilang dan last10
# statistik tim tersedia; cedera per tanggal tetap tidak tersedia.
KETERBATASAN_ROLLING = [
    "TANPA bias look-ahead: rating rolling point-in-time (hanya laga "
    "sebelum tanggal laga; prior = rating BBRef musim sebelumnya, "
    "shrinkage K=10 laga; last10 di-shrink ke rating musim).",
    "Bobot resensi 60/40 BEROPERASI (stats_last10 statistik tim "
    "tersedia dari box score) — berbeda dari run v1 (100% musim).",
    "Cedera per tanggal TIDAK tersedia untuk laga historis — backtest "
    "tanpa penyesuaian pemain absen (tidak ada pemain OUT di input).",
    "B2B dari tanggal kalender saja (main sehari sebelumnya) — tidak "
    "membedakan B2B kandang/tandang/perjalanan jauh.",
    "Brier pasar DATA_INCOMPLETE: tidak ada harga pasar historis "
    "(sportsbook/bursa) untuk laga-laga backtest, jadi Brier model "
    "tidak bisa dibandingkan dengan Brier pasar.",
    "sigma_total mencakup varians OT (lihat LAPORAN-FIT-NBA.md §4) — "
    "sedikit konservatif untuk Under.",
    "Subset ~150 laga: tiap bucket kalibrasi berisi sedikit laga, "
    "jadi frekuensi aktual per bucket punya ketidakpastian besar — "
    "hasil ini gambaran, bukan bukti kalibrasi.",
]


def _muat_modul_fit():
    """Muat scripts/fit_nba_params.py (pakai ulang peta tim + deteksi B2B)."""
    path = REPO_ROOT / "scripts" / "fit_nba_params.py"
    spek = importlib.util.spec_from_file_location("fit_nba_params", path)
    modul = importlib.util.module_from_spec(spek)
    spek.loader.exec_module(modul)
    return modul


def load_ratings(data_dir: Path, seasons: list[str]) -> dict:
    """Muat rating musim penuh BBRef per musim dari data/nba_history/.

    Mengembalikan {musim: {tricode: {off_rtg, def_rtg, net_rtg, pace}}}.
    File ratings_bbref_{musim}.json berisi list mentah BBRef (sama
    seperti yang ditulis scripts/fit_nba_params.py).
    """
    modul_fit = _muat_modul_fit()
    peta_tim = modul_fit.BBREF_TEAM_TRICODES
    ratings: dict[str, dict[str, dict[str, float]]] = {}
    for musim in seasons:
        path = data_dir / f"ratings_bbref_{musim}.json"
        if not path.exists():
            raise RuntimeError(f"file rating tidak ditemukan: {path}")
        mentah = json.loads(path.read_text(encoding="utf-8"))
        per_tim: dict[str, dict[str, float]] = {}
        for tim in mentah:
            tricode = peta_tim.get(tim.get("team"))
            if tricode is None:
                continue
            per_tim[tricode] = {
                "off_rtg": tim.get("off_rtg"),
                "def_rtg": tim.get("def_rtg"),
                "net_rtg": tim.get("net_rtg"),
                "pace": tim.get("pace"),
            }
        ratings[musim] = per_tim
    return ratings


def load_games(data_dir: Path) -> list[dict]:
    """Muat game log gabungan dari data/nba_history/games_all.json."""
    path = data_dir / "games_all.json"
    if not path.exists():
        raise RuntimeError(f"file game log tidak ditemukan: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError(f"file game log harus berisi list: {path}")
    return data


def pilih_subset(games: list[dict], per_musim: int = 50) -> list[dict]:
    """Pilih subset backtest: N laga TERBARU per musim (stratified).

    N terbaru per musim memberi cakupan lintas musim sekaligus laga
    paling mutakhir di tiap musim. Hasil diurutkan tanggal menaik.
    """
    per_musim_dict: dict[str, list[dict]] = {}
    for game in games:
        musim = str(game.get("season"))
        per_musim_dict.setdefault(musim, []).append(game)
    subset: list[dict] = []
    for musim in sorted(per_musim_dict):
        laga_musim = sorted(
            per_musim_dict[musim],
            key=lambda g: str(g.get("game_date") or ""),
            reverse=True,
        )
        subset.extend(laga_musim[:per_musim])
    subset.sort(key=lambda g: str(g.get("game_date") or ""))
    return subset


def bangun_inputs(
    game: dict,
    rating_musim: dict[str, dict[str, float]],
    lg_avg_off_rtg: float,
    b2b: dict[str, bool],
    rolling_laga: dict | None = None,
) -> dict:
    """Bangun inputs minimal simulate() untuk satu laga historis.

    Mode v1 (rolling_laga=None): stats_season dari rating musim
    penuh; stats_last10 TIDAK ADA (simulate fallback ke musim —
    lihat KETERBATASAN); tanpa pemain dan tanpa cedera (data per
    tanggal tidak tersedia). B2B dari peta deteksi tanggal; altitude
    otomatis dari tricode kandang di engine.
    Mode rolling (rolling_laga dari bangun_rating_rolling): stats_season
    + stats_last10 dari rating rolling per laga (bobot resensi
    beroperasi); rating_musim/lg_avg_off_rtg diabaikan — lg_avg
    diambil dari rolling_laga.
    """
    home = game["home_tricode"]
    away = game["away_tricode"]
    game_id = str(game.get("game_id"))

    def _blok(tricode: str) -> dict:
        if rolling_laga is not None:
            sisi = "home" if tricode == home else "away"
            data_tim = rolling_laga[sisi]
            return {
                "tricode": tricode,
                "stats_season": dict(data_tim["stats_season"]),
                "stats_last10": dict(data_tim["stats_last10"]),
                "back_to_back": bool(b2b.get(f"{game_id}:{tricode}", False)),
                "players": [],
                "injuries": [],
            }
        rating = rating_musim[tricode]
        return {
            "tricode": tricode,
            "stats_season": {
                "off_rtg": rating["off_rtg"],
                "def_rtg": rating["def_rtg"],
                "pace": rating["pace"],
            },
            "back_to_back": bool(b2b.get(f"{game_id}:{tricode}", False)),
            "players": [],
            "injuries": [],
        }

    lg_avg = (
        rolling_laga["lg_avg_off_rtg"] if rolling_laga is not None else lg_avg_off_rtg
    )
    return {
        "home": _blok(home),
        "away": _blok(away),
        "league": {"avg_off_rtg": lg_avg},
        "match": {
            "game_date": game.get("game_date"),
            "season": game.get("season"),
        },
    }


def _garis_setengah(poin: float) -> float:
    """Bulatkan ke 0,5 terdekat (cara yang sama dengan garis default sim)."""
    return math.floor(poin * 2.0 + 0.5) / 2.0


def evaluasi_laga(
    game: dict,
    inputs: dict,
    cfg: dict,
    seed: int,
    iterations: int,
) -> dict:
    """Simulasikan satu laga historis (dua pass, seed sama) + nilai event.

    Pass 1 (lines=None): median total + peluang kandang menang.
    Pass 2 (garis median+8): peluang Under pada garis itu.
    Mengembalikan record per laga (prediksi + aktual).
    """
    hasil1 = nba_sim.simulate(
        inputs, cfg=cfg, scenarios=[], seed=seed, iterations=iterations
    )
    median_total = hasil1["score_distribution"]["total"]["median"]
    garis = _garis_setengah(median_total + BANTALAN_UNDER)
    hasil2 = nba_sim.simulate(
        inputs,
        cfg=cfg,
        lines={"totals": [garis]},
        scenarios=[],
        seed=seed,
        iterations=iterations,
    )
    home_pts = float(game["home_pts"])
    away_pts = float(game["away_pts"])
    total_aktual = home_pts + away_pts
    p_under = hasil2["markets"][f"total_under_{garis:g}"]
    return {
        "game_id": str(game.get("game_id")),
        "game_date": game.get("game_date"),
        "season": game.get("season"),
        "home_tricode": game["home_tricode"],
        "away_tricode": game["away_tricode"],
        "home_pts": home_pts,
        "away_pts": away_pts,
        "actual_total": total_aktual,
        "projected_total": hasil1["inputs_summary"]["projected_total"],
        "median_total": median_total,
        "garis_under": garis,
        "p_home_win": round(hasil1["markets"]["moneyline_home"], 6),
        "actual_home_win": home_pts > away_pts,
        "p_under": round(p_under, 6),
        "actual_under": total_aktual < garis,
        "b2b_home": bool(inputs["home"]["back_to_back"]),
        "b2b_away": bool(inputs["away"]["back_to_back"]),
    }


def jalankan_backtest(
    games_subset: list[dict],
    games_semua: list[dict],
    ratings: dict[str, dict[str, dict[str, float]]],
    cfg: dict,
    iterations: int,
    rolling: dict | None = None,
) -> dict:
    """Jalankan backtest atas subset laga; kembalikan hasil + waktu tempuh.

    games_semua dipakai untuk deteksi B2B (butuh jadwal penuh tiap
    tim). Seed per laga = int(game_id) — deterministik, beda tiap laga.
    Laga tanpa rating/skor dilewati + dicatat alasannya.
    rolling: bila diberikan (dict game_id -> data dari
    bangun_rating_rolling), inputs memakai rating rolling per laga
    dan `ratings` diabaikan.
    """
    modul_fit = _muat_modul_fit()
    b2b = modul_fit.detect_back_to_back(games_semua)
    lg_avg: dict[str, float] = {}
    if rolling is None:
        for musim, per_tim in ratings.items():
            nilai = [
                r["off_rtg"] for r in per_tim.values() if r.get("off_rtg") is not None
            ]
            lg_avg[musim] = statistics.fmean(nilai) if nilai else None
    hasil_per_laga: list[dict] = []
    dilewati: list[dict] = []
    mulai = time.perf_counter()
    for game in games_subset:
        musim = str(game.get("season"))
        home = game.get("home_tricode")
        away = game.get("away_tricode")
        alasan = None
        data_rolling = None
        if rolling is not None:
            data_rolling = rolling.get(str(game.get("game_id")))
            if data_rolling is None:
                alasan = "rating rolling tidak ada"
            elif game.get("home_pts") is None or game.get("away_pts") is None:
                alasan = "skor aktual hilang"
            inputs = (
                bangun_inputs(
                    game,
                    {},
                    data_rolling["lg_avg_off_rtg"],
                    b2b,
                    rolling_laga=data_rolling,
                )
                if alasan is None
                else None
            )
        else:
            rating_musim = ratings.get(musim)
            if rating_musim is None:
                alasan = f"rating musim {musim} tidak ada"
            elif home not in rating_musim or away not in rating_musim:
                alasan = f"rating tim hilang ({home}/{away})"
            elif game.get("home_pts") is None or game.get("away_pts") is None:
                alasan = "skor aktual hilang"
            elif any(
                rating_musim[t].get(k) is None
                for t in (home, away)
                for k in ("off_rtg", "def_rtg", "pace")
            ):
                alasan = f"rating tidak lengkap ({home}/{away})"
            inputs = (
                bangun_inputs(game, rating_musim, lg_avg[musim], b2b)
                if alasan is None
                else None
            )
        if alasan is not None:
            dilewati.append({"game_id": str(game.get("game_id")), "alasan": alasan})
            continue
        try:
            seed = int(str(game.get("game_id")))
        except (ValueError, TypeError):
            seed = abs(hash(str(game.get("game_id")))) % (2**31)
        hasil_per_laga.append(evaluasi_laga(game, inputs, cfg, seed, iterations))
    waktu = time.perf_counter() - mulai
    return {
        "n_laga": len(hasil_per_laga),
        "n_dilewati": len(dilewati),
        "waktu_detik": round(waktu, 1),
        "hasil_per_laga": hasil_per_laga,
        "dilewati": dilewati,
    }


def _ringkas_kalibrasi(ringkasan: dict) -> dict:
    """Bulatkan angka ringkasan kalibrasi untuk JSON (6 desimal)."""
    return {
        "n": ringkasan["n"],
        "mean_prediksi": round(ringkasan["mean_prediksi"], 6),
        "frekuensi_aktual": round(ringkasan["frekuensi_aktual"], 6),
        "brier": round(ringkasan["brier"], 6),
        "buckets": [
            {
                "bucket": list(b["bucket"]),
                "n": b["n"],
                "mean_prediksi": (
                    round(b["mean_prediksi"], 6)
                    if b["mean_prediksi"] is not None
                    else None
                ),
                "frekuensi_aktual": (
                    round(b["frekuensi_aktual"], 6)
                    if b["frekuensi_aktual"] is not None
                    else None
                ),
            }
            for b in ringkasan["buckets"]
        ],
    }


def _dampak_pemain(
    pemain: dict, bpm_scale: float, bpm_replacement: float, w_last10: float
) -> float:
    """Dampak poin satu pemain — DELEGASI ke engine.nba_sim._dampak_pemain.

    Rumus tunggal di engine (patch langkah 1b, perbaikan 2): dampak =
    (BPM - bpm_replacement) x (mp_per_game/48) x bpm_scale x
    faktor_overlap, faktor_overlap = 1 - w_last10 x missed_last10/10
    (missed_last10 None -> faktor 1,0). Skrip ini SENGAJA tidak punya
    salinan rumus sendiri: memakai fungsi engine yang sama berarti
    pemeringkatan bintang di sini TIDAK BISA drift dari sim (bila
    engine mengubah signature-nya, skrip ini gagal LOUD di sini,
    bukan diam-diam memakai rumus lama). Hanya nilai dampak yang
    dipakai (catatan overlap dibuang — pemeringkatan hanya butuh
    nilainya). w_last10 = bobot resensi last10 yang SUDAH
    dinormalisasi (sama seperti yang dipakai simulate()).
    """
    dampak, _catatan = nba_sim._dampak_pemain(
        pemain, bpm_scale, bpm_replacement, w_last10
    )
    return dampak


def _bintang_teratas(
    inputs: dict, bpm_scale: float, bpm_replacement: float, w_last10: float
) -> dict[str, str | None]:
    """Bintang teratas tiap tim yang masih tersedia (dampak terbesar).

    Tersedia = ada di daftar pemain dan tidak berstatus OUT.
    Dampak memakai rumus engine (lihat _dampak_pemain).
    Mengembalikan {"home": nama|None, "away": nama|None}.
    """
    hasil: dict[str, str | None] = {}
    for sisi in ("home", "away"):
        blok = inputs.get(sisi) or {}
        status_out = {
            c.get("player")
            for c in blok.get("injuries") or []
            if isinstance(c.get("status"), str) and c["status"].upper() == "OUT"
        }
        terbaik: str | None = None
        dampak_terbaik = float("-inf")
        for pemain in blok.get("players") or []:
            nama = pemain.get("player")
            if not isinstance(nama, str) or nama in status_out:
                continue
            dampak = _dampak_pemain(pemain, bpm_scale, bpm_replacement, w_last10)
            if dampak > dampak_terbaik:
                dampak_terbaik = dampak
                terbaik = nama
        hasil[sisi] = terbaik
    return hasil


def _apakah_b2b(blok: dict) -> bool:
    """Apakah blok tim ini B2B (flag, atau rest_days 0)."""
    flag = blok.get("back_to_back")
    if flag is not None:
        return bool(flag)
    return blok.get("rest_days") == 0


def ambil_inputs_kepekaan(cache_path: Path) -> tuple[dict, str]:
    """Ambil inputs laga DET @ ATL 2026-11-22 (cache dulu, fetch bila perlu).

    Bila cache ada, dipakai (tanpa network). Bila tidak ada, SATU
    panggilan ingest.nba_brain.fetch_match_inputs, lalu disimpan ke
    cache agar run berikutnya tidak fetch lagi. Mengembalikan
    (inputs, keterangan_sumber).
    """
    if cache_path.exists():
        inputs = json.loads(cache_path.read_text(encoding="utf-8"))
        return inputs, f"cache lokal {cache_path} (tanpa network)"
    from ingest.nba_brain import fetch_match_inputs

    result = fetch_match_inputs(
        home_tricode=LAGA_KEPEKAAN["home"],
        away_tricode=LAGA_KEPEKAAN["away"],
        game_date=LAGA_KEPEKAAN["game_date"],
    )
    if not result.ok:
        raise RuntimeError(f"fetch_match_inputs gagal: {result.error}")
    inputs = result.data
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(inputs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return inputs, (
        "fetch_match_inputs (SATU panggilan, sumber gratis keyless) — "
        f"disimpan ke cache {cache_path}"
    )


def jalankan_kepekaan(inputs: dict, cfg: dict, seed: int, iterations: int) -> dict:
    """Uji kepekaan pada satu laga nyata: basis vs 6 variasi (seed tetap).

    Variasi: (1) bintang teratas tiap tim absen, (2) pace +2 kedua tim,
    (3) pace -2 kedua tim, (4) sigma_total +20%, (5) sigma_total -20%,
    (6) tanpa penalti B2B (dilewati bila laga bukan B2B).
    Tiap variasi dua pass (seed sama): pass 1 median total, pass 2
    P(Under) pada garis median+8 variasi itu DAN pada garis basis —
    agar terlihat perubahan peluang pada garis yang sama.
    """
    bpm_scale = float(config_mod.get_value(cfg, "simulation", "nba", "bpm_scale"))
    bpm_replacement = float(
        config_mod.get_value(cfg, "simulation", "nba", "bpm_replacement")
    )
    # Bobot resensi dinormalisasi seperti simulate() — w_last10 yang
    # masuk faktor overlap adalah bobot TERNORMALISASI (0,4).
    w_musim = float(config_mod.get_value(cfg, "simulation", "nba", "recency", "season"))
    w_terakhir = float(
        config_mod.get_value(cfg, "simulation", "nba", "recency", "last10")
    )
    total_bobot = w_musim + w_terakhir
    if total_bobot <= 0:
        raise config_mod.ConfigError("bobot recency harus berjumlah > 0")
    w_last10 = w_terakhir / total_bobot

    def _jalankan(inputs_var: dict, cfg_var: dict) -> dict:
        """Satu variasi, pass 1: median total + peluang kandang menang."""
        hasil1 = nba_sim.simulate(
            inputs_var,
            cfg=cfg_var,
            scenarios=[],
            seed=seed,
            iterations=iterations,
        )
        return {
            "median_total": hasil1["score_distribution"]["total"]["median"],
            "projected_total": hasil1["inputs_summary"]["projected_total"],
            "p_home_win": round(hasil1["markets"]["moneyline_home"], 6),
        }

    def _p_under(inputs_var: dict, cfg_var: dict, garis: list) -> dict:
        """Pass 2: P(Under) pada daftar garis (seed sama dengan pass 1)."""
        hasil2 = nba_sim.simulate(
            inputs_var,
            cfg=cfg_var,
            lines={"totals": garis},
            scenarios=[],
            seed=seed,
            iterations=iterations,
        )
        return {g: round(hasil2["markets"][f"total_under_{g:g}"], 6) for g in garis}

    # Daftar variasi: (nama, deskripsi, inputs, cfg).
    variasi_def: list[tuple[str, str, dict, dict]] = []
    variasi_dilewati: list[dict] = []
    bintang = _bintang_teratas(inputs, bpm_scale, bpm_replacement, w_last10)
    if bintang["home"] is None and bintang["away"] is None:
        variasi_dilewati.append(
            {
                "nama": "bintang_absen",
                "alasan": "tidak ada pemain dengan data BPM/menit di kedua tim",
            }
        )
    else:
        # Bintang absen diterapkan lewat INPUTS (status OUT di daftar
        # cedera), bukan lewat scenarios — agar median total variasi
        # ini terukur langsung dari base case-nya sendiri.
        inputs_bintang = copy.deepcopy(inputs)
        for sisi, nama in (
            ("home", bintang["home"]),
            ("away", bintang["away"]),
        ):
            if nama is not None:
                inputs_bintang[sisi].setdefault("injuries", []).append(
                    {"player": nama, "status": "OUT"}
                )
        variasi_def.append(
            (
                "bintang_absen",
                "bintang teratas tiap tim absen: "
                f"kandang {bintang['home'] or '-'}, "
                f"tandang {bintang['away'] or '-'}",
                inputs_bintang,
                cfg,
            )
        )
    for delta, label in ((2.0, "pace_plus_2"), (-2.0, "pace_min_2")):
        inputs_pace = copy.deepcopy(inputs)
        for sisi in ("home", "away"):
            blok = inputs_pace[sisi]
            blok["stats_season"]["pace"] += delta
            if blok.get("stats_last10", {}).get("pace") is not None:
                blok["stats_last10"]["pace"] += delta
        variasi_def.append(
            (
                label,
                f"pace kedua tim {'+' if delta > 0 else ''}{delta:g} "
                "(musim + last10)",
                inputs_pace,
                cfg,
            )
        )
    for faktor, label in ((1.2, "sigma_total_plus_20"), (0.8, "sigma_total_min_20")):
        cfg_sigma = copy.deepcopy(cfg)
        lama = cfg_sigma["simulation"]["nba"]["sigma_total_points"]
        cfg_sigma["simulation"]["nba"]["sigma_total_points"] = lama * faktor
        variasi_def.append(
            (
                label,
                f"sigma_total {lama} -> {round(lama * faktor, 4)} "
                f"({'+' if faktor > 1 else ''}{round((faktor - 1) * 100):g}%)",
                inputs,
                cfg_sigma,
            )
        )
    b2b_laga = _apakah_b2b(inputs.get("home") or {}) or _apakah_b2b(
        inputs.get("away") or {}
    )
    if b2b_laga:
        cfg_tanpa_b2b = copy.deepcopy(cfg)
        cfg_tanpa_b2b["simulation"]["nba"]["back_to_back_penalty_points"] = 0.0
        variasi_def.append(
            (
                "tanpa_b2b",
                "penalti B2B dinolkan (laga ini B2B untuk salah satu tim)",
                inputs,
                cfg_tanpa_b2b,
            )
        )
    else:
        variasi_dilewati.append(
            {
                "nama": "tanpa_b2b",
                "alasan": "laga ini bukan B2B untuk kedua tim — variasi dilewati",
            }
        )

    # Basis dulu (garis basis dipakai semua variasi sebagai pembanding).
    basis = _jalankan(inputs, cfg)
    garis_basis = _garis_setengah(basis["median_total"] + BANTALAN_UNDER)
    p_basis = _p_under(inputs, cfg, [garis_basis])
    basis_out = {
        "nama": "basis",
        "deskripsi": "inputs nyata, config apa adanya",
        "median_total": basis["median_total"],
        "projected_total": basis["projected_total"],
        "p_home_win": basis["p_home_win"],
        "garis_under_sendiri": garis_basis,
        "p_under_garis_sendiri": p_basis[garis_basis],
        "p_under_garis_basis": p_basis[garis_basis],
        "delta_median_vs_basis": 0.0,
    }

    hasil_variasi = [basis_out]
    for nama, deskripsi, inputs_var, cfg_var in variasi_def:
        jalan = _jalankan(inputs_var, cfg_var)
        garis_sendiri = _garis_setengah(jalan["median_total"] + BANTALAN_UNDER)
        garis_pass2 = [garis_sendiri]
        if garis_basis != garis_sendiri:
            garis_pass2.append(garis_basis)
        peluang = _p_under(inputs_var, cfg_var, garis_pass2)
        hasil_variasi.append(
            {
                "nama": nama,
                "deskripsi": deskripsi,
                "median_total": jalan["median_total"],
                "projected_total": jalan["projected_total"],
                "p_home_win": jalan["p_home_win"],
                "garis_under_sendiri": garis_sendiri,
                "p_under_garis_sendiri": peluang[garis_sendiri],
                "p_under_garis_basis": peluang[garis_basis],
                "delta_median_vs_basis": round(
                    jalan["median_total"] - basis["median_total"], 2
                ),
            }
        )

    return {
        "laga": (
            f"{LAGA_KEPEKAAN['away']} @ {LAGA_KEPEKAAN['home']} "
            f"({LAGA_KEPEKAAN['game_date']})"
        ),
        "seed": seed,
        "iterations": iterations,
        "b2b_home": _apakah_b2b(inputs.get("home") or {}),
        "b2b_away": _apakah_b2b(inputs.get("away") or {}),
        "garis_basis": garis_basis,
        "variasi": hasil_variasi,
        "variasi_dilewati": variasi_dilewati,
    }


def _cetak_tabel_kalibrasi(judul: str, ringkasan: dict) -> None:
    """Cetak tabel reliability buckets satu event ke stdout."""
    print(f"\n{judul} (n={ringkasan['n']})")
    print(
        f"  mean prediksi {ringkasan['mean_prediksi']:.3f} | "
        f"frekuensi aktual {ringkasan['frekuensi_aktual']:.3f} | "
        f"Brier {ringkasan['brier']:.4f}"
    )
    print("  bucket        n   mean_pred  frek_aktual")
    for b in ringkasan["buckets"]:
        lo, hi = b["bucket"]
        mean = f"{b['mean_prediksi']:.3f}" if b["mean_prediksi"] is not None else "-"
        frek = (
            f"{b['frekuensi_aktual']:.3f}" if b["frekuensi_aktual"] is not None else "-"
        )
        print(f"  [{lo:.1f}-{hi:.1f})  {b['n']:>4}  {mean:>9}  {frek:>11}")


def main(argv: list[str] | None = None) -> int:
    """Jalankan validasi dari CLI. 0 sukses, 2 data/config tidak tersedia."""
    parser = argparse.ArgumentParser(
        description="Validasi Otak NBA: backtest + kalibrasi + uji kepekaan."
    )
    parser.add_argument(
        "--data-dir",
        default="data/nba_history",
        help="direktori data historis (default: data/nba_history)",
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        default=["2024-25", "2025-26", "2026-27"],
        help="musim yang dipakai (default: 2024-25 2025-26 2026-27)",
    )
    parser.add_argument(
        "--per-musim",
        type=int,
        default=50,
        help="laga terbaru per musim untuk backtest (default: 50)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100000,
        help="iterasi simulasi per laga (default: 100000)",
    )
    parser.add_argument(
        "--out",
        default="out/validation_nba.json",
        help="file JSON hasil (default: out/validation_nba.json)",
    )
    parser.add_argument(
        "--inputs-cache",
        default="out/sensitivity_inputs_det_atl.json",
        help="cache inputs uji kepekaan (default: "
        "out/sensitivity_inputs_det_atl.json)",
    )
    parser.add_argument(
        "--tanpa-kepekaan",
        action="store_true",
        help="lewati uji kepekaan (hanya backtest + kalibrasi)",
    )
    parser.add_argument(
        "--rolling",
        action="store_true",
        help="mode rolling point-in-time (patch 1b): backtest memakai "
        "rating rolling dari box score, bukan rating musim penuh",
    )
    parser.add_argument(
        "--boxscores-file",
        default=None,
        help="JSON box score gabungan (mode rolling; bila tidak ada, "
        "cache/fetch per musim dari data dir)",
    )
    args = parser.parse_args(argv)
    data_dir = REPO_ROOT / args.data_dir
    out_path = REPO_ROOT / args.out
    cache_path = REPO_ROOT / args.inputs_cache

    try:
        cfg = config_mod.load_playstyle()
    except config_mod.ConfigError as exc:
        print(f"config tidak lengkap: {exc}", file=sys.stderr)
        return 2
    try:
        games_semua = load_games(data_dir)
        rolling_data = None
        info_rolling = None
        if args.rolling:
            modul_fit = _muat_modul_fit()
            w_musim = float(
                config_mod.get_value(cfg, "simulation", "nba", "recency", "season")
            )
            w_last10 = float(
                config_mod.get_value(cfg, "simulation", "nba", "recency", "last10")
            )
            boxscores = modul_fit.load_boxscores(
                args.seasons, args.boxscores_file, data_dir
            )
            priors = modul_fit.load_prior_ratings(args.seasons, data_dir)
            rolling_data, info_rolling = modul_fit.bangun_rating_rolling(
                games_semua, boxscores, priors, w_musim, w_last10
            )
            ratings = {}
        else:
            ratings = load_ratings(data_dir, args.seasons)
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"validasi dibatalkan: {exc}", file=sys.stderr)
        return 2

    subset = pilih_subset(games_semua, per_musim=args.per_musim)
    print(
        f"backtest: {len(subset)} laga "
        f"({args.per_musim} terbaru per musim: {', '.join(args.seasons)}), "
        f"{args.iterations} iterasi, base case saja"
        + (" [rating rolling point-in-time]" if args.rolling else "")
    )
    backtest = jalankan_backtest(
        subset, games_semua, ratings, cfg, args.iterations, rolling=rolling_data
    )
    print(
        f"backtest selesai: {backtest['n_laga']} laga, "
        f"dilewati {backtest['n_dilewati']}, "
        f"waktu {backtest['waktu_detik']} dtk"
    )

    per_laga = backtest["hasil_per_laga"]
    pairs_home = [(r["p_home_win"], r["actual_home_win"]) for r in per_laga]
    pairs_under = [(r["p_under"], r["actual_under"]) for r in per_laga]
    kal_home = validation.calibration_summary(pairs_home)
    kal_under = validation.calibration_summary(pairs_under)

    kepekaan = None
    sumber_inputs = None
    if not args.tanpa_kepekaan:
        try:
            inputs, sumber_inputs = ambil_inputs_kepekaan(cache_path)
        except Exception as exc:  # runner CLI: laporkan jelas, jangan traceback
            print(f"uji kepekaan dibatalkan: {exc}", file=sys.stderr)
            kepekaan = {"status": "DATA_INCOMPLETE", "alasan": str(exc)}
        if kepekaan is None:
            print("uji kepekaan: DET @ ATL 2026-11-22 ...")
            try:
                kepekaan = jalankan_kepekaan(
                    inputs, cfg, SEED_KEPEKAAN, args.iterations
                )
            except Exception as exc:  # runner CLI: laporkan jelas
                print(f"uji kepekaan gagal: {exc}", file=sys.stderr)
                kepekaan = {"status": "DATA_INCOMPLETE", "alasan": str(exc)}
            else:
                kepekaan["sumber_inputs"] = sumber_inputs

    hasil = {
        "generated_at": datetime.now(UTC).isoformat(),
        "engine": {"name": "nba_sim", "version": nba_sim.ENGINE_VERSION},
        "ratings_mode": "rolling" if args.rolling else "musim_penuh",
        "metode": {
            "subset": (
                f"{args.per_musim} laga terbaru per musim "
                f"({', '.join(args.seasons)})"
            ),
            "ratings": (
                "rolling point-in-time: stats musim-berjalan + "
                "last10-berjalan dari box score sebelum tanggal laga; "
                "prior rating BBRef musim sebelumnya, shrinkage K=10; "
                "lg_avg per tanggal"
                if args.rolling
                else "rating musim penuh BBRef (bias look-ahead)"
            ),
            "iterations": args.iterations,
            "scenarios": "base case saja (scenarios=[])",
            "seed_backtest": "int(game_id), deterministik per laga",
            "event_kandang_menang": "P(kandang menang) vs W/L aktual",
            "event_under": (
                "P(total < median_proyeksi+8) vs aktual — bantalan "
                "Alt Under 8 poin; garis dibulatkan ke 0,5"
            ),
            "dua_pass": (
                "pass 1 (lines=None) mengambil median total; pass 2 "
                "mengambil P(Under) pada garis median+8 dengan seed "
                "yang sama (noise sama)"
            ),
        },
        "keterbatasan": KETERBATASAN_ROLLING if args.rolling else KETERBATASAN,
        "rolling_info": info_rolling,
        "backtest": backtest,
        "kalibrasi": {
            "kandang_menang": _ringkas_kalibrasi(kal_home),
            "under_median_plus_8": _ringkas_kalibrasi(kal_under),
            "brier_pasar": "DATA_INCOMPLETE",
            "brier_pasar_alasan": (
                "tidak ada harga pasar historis (sportsbook/bursa) "
                "untuk laga-laga backtest"
            ),
        },
        "kepekaan": kepekaan,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(hasil, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    _cetak_tabel_kalibrasi("KALIBRASI — kandang menang", kal_home)
    _cetak_tabel_kalibrasi("KALIBRASI — Under (median+8)", kal_under)
    print("\nBrier pasar: DATA_INCOMPLETE (tidak ada harga pasar historis)")
    if kepekaan is not None and kepekaan.get("status") != "DATA_INCOMPLETE":
        print(
            f"\nKEPEKAAN — {kepekaan['laga']} (garis basis {kepekaan['garis_basis']})"
        )
        print("  variasi              median  dMedian  P(U@sendiri)  P(U@basis)")
        for v in kepekaan["variasi"]:
            print(
                f"  {v['nama']:<20} {v['median_total']:>6.1f} "
                f"{v['delta_median_vs_basis']:>+7.1f}  "
                f"{v['p_under_garis_sendiri']:>12.3f}  "
                f"{v['p_under_garis_basis']:>10.3f}"
            )
        for d in kepekaan["variasi_dilewati"]:
            print(f"  dilewati {d['nama']}: {d['alasan']}")
    print(f"\nhasil ditulis ke {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
