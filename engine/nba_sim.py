"""Simulasi NBA 100.000x: Student-t + OT + skenario skuad (Blueprint §5a).

RUMUS PROYEKSI (persis; dipakai juga oleh scripts/fit_nba_params.py
untuk memproyeksikan laga historis):

1. Statistik gabungan tiap tim, per field (off_rtg, def_rtg, pace):
     stat = w_musim * stat_musim + w_terakhir * stat_last10
   dengan w dari config simulation.nba.recency (dinormalisasi agar
   jumlahnya 1). Bila nilai last10 hilang, dipakai nilai musim saja
   untuk field itu + dicatat di inputs_summary.
2. Pace laga: pace = (pace_kandang + pace_tandang) / 2.
3. Rata-rata liga (lg): inputs["league"]["avg_off_rtg"]; bila None,
   rata-rata keempat rating gabungan (off+def kedua tim) + dicatat.
4. Efisiensi melawan lawan:
     off_kandang = off_rtg_kandang + (def_rtg_tandang - lg)
     off_tandang = off_rtg_tandang + (def_rtg_kandang - lg)
   (Lawan yang pertahanannya buruk — def_rtg di atas rata-rata liga —
   membuat tim mencetak LEBIH banyak. Tanda ini penting: dengan tanda
   terbalik, margin proyeksi menjadi selisih (off+def), bukan selisih
   net rating — bug ini tertangkap oleh fit data nyata 2026-11-22.)
5. Rata-rata poin:
     mu_kandang = off_kandang * pace / 100
     mu_tandang = off_tandang * pace / 100
6. Penyesuaian (semua nilai dari config simulation.nba):
   - home advantage: mu_kandang += HA/2, mu_tandang -= HA/2 (total
     tidak berubah; pembagian setengah-setengah adalah pilihan desain
     yang didokumentasikan, bukan hasil fit).
   - ketinggian (kandang DEN/UTA): seperti HA dengan nilai ALT.
   - turnamen (bila inputs["tournament"] ada): seperti HA dengan nilai
     turnamen (saat ini 0 — belum ada data).
   - back-to-back: mu_tim += penalti_B2B bila tim itu B2B. Penalti
     disimpan BERTANDA (hasil fit = selisih residual, negatif bila tim
     B2B mencetak lebih sedikit), jadi ditambahkan, bukan dikurang.
   - pemain absen: mu_tim -= jumlah dampak pemain absen tim itu,
     dampak = (BPM - BPM_replacement) x (mp_per_game / 48) x bpm_scale
     x faktor_overlap (patch langkah 1b, temuan auditor 2).
     BPM_replacement = simulation.nba.bpm_replacement (-2,0 dari
     literatur Basketball-Reference: pemain absen diganti pemain level
     pengganti, bukan pemain nol — tanpa ini, pemain cadangan BPM
     negatif yang absen justru MENAIKKAN proyeksi tim).
     faktor_overlap = 1 - w_last10 x (missed_last10 / 10), dengan
     w_last10 = bobot resensi last10 yang sudah dinormalisasi dan
     missed_last10 = jumlah dari 10 laga terakhir TIM yang tidak
     dimainkan pemain itu (field opsional `missed_last10` per dict
     pemain, diisi ingest.player_gamelog). Alasan: rating tim sudah
     mengandung 40% last10, jadi pemain yang sudah absen di last10
     terhitung ganda bila dampaknya dikurangi penuh. Bila
     missed_last10 hilang/tidak valid -> faktor 1,0 (perilaku lama) +
     catatan di inputs_summary.notes (hanya untuk pemain yang memang
     absen di base case). Pemain skenario hipotetis yang saat ini
     sehat: faktor 1,0 — asumsi yang didokumentasikan (mereka bermain
     di last10, jadi missed_last10-nya ~0).

SEBARAN (per iterasi, sebelum OT):
     skor_kandang = mu_kandang + s_umum * Tc + s_tim * Th
     skor_tandang = mu_tandang + s_umum * Tc + s_tim * Ta
  Tc, Th, Ta ~ Student-t(nu) independen, diskalakan ke varians 1.
  s_tim = sigma_margin / akar(2);
  s_umum = akar((sigma_total^2 - sigma_margin^2) / 4).
  Dengan struktur ini Var(margin) = sigma_margin^2 dan
  Var(total) = sigma_total^2 persis (bila sigma_total >= sigma_margin;
  bila tidak, s_umum = 0 + dicatat). Skor dibulatkan ke bilangan bulat
  (floor(x + 0,5)) dan dijepit ke >= 0.
  Noise yang sama dipakai untuk semua skenario (common random numbers):
  perbedaan antar skenario murni dari skenarionya, bukan dari noise.

OVERTIME: bila seri setelah 48 menit, mainkan periode 5 menit
(overtime_minutes dari config): poin OT tiap tim =
  mu_tim x (5/48) + noise Student-t dengan skala x akar(5/48)
  (varians sebanding durasi — asumsi yang didokumentasikan).
  Diulangi sampai ada pemenang, maks ot_max_periods periode.

SKENARIO SKUAD (bila argumen scenarios None, dibangun dari config
simulation.nba.squad_scenarios):
  - "full": tidak ada yang absen — semua pemain inti bermain, termasuk
    yang berstatus OUT (hipotesis kekuatan penuh).
  - "missing_1": pemain inti teratas KANDANG yang masih tersedia absen.
  - "missing_2": teratas kandang + teratas tandang absen.
  - "missing_4": 2 teratas tiap tim absen.
  missing_N selalu DI ATAS pemain yang memang sudah OUT (base case).
  "Pemain inti teratas" = dampak terbesar ((BPM - replacement) x menit
  x faktor overlap), bukan menit terbanyak. "Tersedia" = ada di daftar
  pemain dan tidak berstatus OUT.
  Base case (markets utama): pemain OUT absen; QUESTIONABLE/DOUBTFUL
  bermain, TAPI bila ada pemain inti QUESTIONABLE/DOUBTFUL, dibuatkan
  skenario tambahan "doubtful_out" (mereka absen di atas base case).
  Skenario kustom (argumen scenarios) = {"name", "home_out": [...],
  "away_out": [...]}: nama-nama itu absen di atas base case, kecuali
  nama "full" yang berarti tidak ada yang absen. Nama pemain yang
  tidak ada di daftar pemain dicatat di inputs_summary dan diabaikan
  (dampaknya tidak bisa dihitung tanpa BPM/menit).

GARIS (argumen lines): {"spreads": [...], "totals": [...]}. Bila None,
hanya moneyline + total pada median proyeksi (garis = total proyeksi
base case, dibulatkan ke 0,5 terdekat).

DATA TIDAK LENGKAP: bila statistik musim yang dibutuhkan hilang ->
  ValueError("data_tidak_lengkap: ..."). Tidak ada tebakan.
PARAMETER BELUM DIFIT: bila parameter config masih null ->
  config.ConfigError("parameter_belum_difit: ...") (D12).
"""

from __future__ import annotations

import math
import random
import statistics
import time
from datetime import UTC, datetime

import config as config_mod
from engine import markets

ENGINE_VERSION = "1.1.0"

# Tim yang kandangnya di ketinggian (Denver ~1600 m, Salt Lake City
# ~1300 m). Dipakai hanya bila flag altitude_home tidak ada di input.
ALTITUDE_TRICODES = frozenset({"DEN", "UTA"})

# Status cedera yang berarti pemain PASTI absen di base case.
STATUS_ABSEN = frozenset({"OUT"})
# Status yang berarti pemain diragukan: bermain di base case, tapi
# dibuatkan skenario tambahan "doubtful_out" bila pemainnya inti.
STATUS_DIRAGUKAN = frozenset({"QUESTIONABLE", "DOUBTFUL"})

# Field statistik tim yang dipakai proyeksi.
_FIELD_STAT = ("off_rtg", "def_rtg", "pace")


def project_points(
    home_stats: dict[str, float],
    away_stats: dict[str, float],
    league_avg_off_rtg: float,
) -> tuple[float, float, float]:
    """Proyeksi rata-rata poin kedua tim dari rating gabungan.

    home_stats/away_stats: dict off_rtg/def_rtg/pace yang SUDAH
    digabung (musim + last10) oleh pemanggil. league_avg_off_rtg:
    rata-rata ORtg liga (atau fallback-nya, lihat docstring modul).
    Mengembalikan (mu_kandang, mu_tandang, pace_laga). Rumus persis
    ada di docstring modul (langkah 2-5). Dipakai juga oleh
    scripts/fit_nba_params.py agar proyeksi fit dan simulasi identik.
    """
    pace_laga = (home_stats["pace"] + away_stats["pace"]) / 2.0
    off_kandang = home_stats["off_rtg"] + (away_stats["def_rtg"] - league_avg_off_rtg)
    off_tandang = away_stats["off_rtg"] + (home_stats["def_rtg"] - league_avg_off_rtg)
    mu_kandang = off_kandang * pace_laga / 100.0
    mu_tandang = off_tandang * pace_laga / 100.0
    return mu_kandang, mu_tandang, pace_laga


def _student_t_draw(rng: random.Random, nu: float) -> float:
    """Satu draw Student-t(nu) yang diskalakan ke varians 1.

    t = Z / sqrt(V/nu), Z ~ N(0,1), V ~ chi-kuadrat(nu) =
    Gamma(nu/2, skala 2). Dibagi sqrt(nu/(nu-2)) agar variansnya 1
    (syarat nu > 2). Stdlib saja: gauss + gammavariate.
    """
    z = rng.gauss(0.0, 1.0)
    v = rng.gammavariate(nu / 2.0, 2.0)
    if v <= 0.0:
        v = 1e-12
    return z / math.sqrt(v / nu) / math.sqrt(nu / (nu - 2.0))


def _kuantil(nilai_urut: list[float], q: float) -> float:
    """Kuantil q (0-1) dari daftar yang sudah terurut (interpolasi linear)."""
    n = len(nilai_urut)
    pos = q * (n - 1)
    bawah = int(pos)
    atas = min(bawah + 1, n - 1)
    frac = pos - bawah
    return nilai_urut[bawah] * (1.0 - frac) + nilai_urut[atas] * frac


def _param_numerik(cfg: dict, *kunci: str) -> float:
    """Ambil satu parameter numerik dari config.

    Raise ConfigError bila kunci hilang (via get_value), nilainya None
    (parameter belum difit — D12), atau bukan angka.
    """
    nilai = config_mod.get_value(cfg, *kunci)
    if nilai is None:
        raise config_mod.ConfigError(
            "parameter_belum_difit: "
            + ".".join(kunci)
            + " masih null — fit dulu dengan scripts/fit_nba_params.py "
            "dan minta persetujuan user (D12)"
        )
    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        raise config_mod.ConfigError(
            f"parameter bukan angka: {'.'.join(kunci)} = {nilai!r}"
        )
    return float(nilai)


def _combined_stats(
    blok: dict,
    w_musim: float,
    w_terakhir: float,
    label_tim: str,
    catatan: list[str],
) -> dict[str, float]:
    """Gabung statistik musim + last10 satu tim (bobot resensi).

    Raise ValueError("data_tidak_lengkap: ...") bila statistik musim
    yang dibutuhkan hilang. Bila nilai last10 hilang, dipakai nilai
    musim saja untuk field itu + dicatat.
    """
    musim = blok.get("stats_season") or {}
    terakhir = blok.get("stats_last10") or {}
    gabung: dict[str, float] = {}
    for field in _FIELD_STAT:
        nilai_musim = musim.get(field)
        if nilai_musim is None:
            raise ValueError(
                f"data_tidak_lengkap: stats_season.{field} {label_tim} hilang"
            )
        nilai_terakhir = terakhir.get(field)
        if nilai_terakhir is None:
            catatan.append(
                f"stats_last10.{field} {label_tim} hilang — " "dipakai nilai musim saja"
            )
            gabung[field] = float(nilai_musim)
        else:
            gabung[field] = w_musim * float(nilai_musim) + w_terakhir * float(
                nilai_terakhir
            )
    return gabung


def _faktor_overlap(pemain: dict, w_last10: float) -> tuple[float, str | None]:
    """Faktor koreksi tumpang-tindih last10: 1 - w_last10 x missed/10.

    missed_last10 = jumlah dari 10 laga terakhir tim yang tidak
    dimainkan pemain itu (int 0-10, field opsional per dict pemain).
    Bila hilang/tidak valid -> faktor 1,0 (perilaku lama) + catatan
    (str) yang harus diteruskan pemanggil ke inputs_summary.notes;
    bila valid -> (faktor, None).
    """
    nama = pemain.get("player") or "pemain_tidak_dikenal"
    missed = pemain.get("missed_last10")
    if missed is None:
        return 1.0, (
            f"missed_last10 {nama} tidak ada — koreksi tumpang-tindih "
            "tidak diterapkan (faktor 1,0)"
        )
    if isinstance(missed, bool) or not isinstance(missed, int) or not 0 <= missed <= 10:
        return 1.0, (
            f"missed_last10 {nama} tidak valid ({missed!r}) — koreksi "
            "tumpang-tindih tidak diterapkan (faktor 1,0)"
        )
    return 1.0 - w_last10 * (missed / 10.0), None


def _dampak_pemain(
    pemain: dict, bpm_scale: float, bpm_replacement: float, w_last10: float
) -> tuple[float, str | None]:
    """Dampak poin satu pemain absen + catatan overlap (bila ada).

    dampak = (BPM - BPM_replacement) x (mp_per_game / 48) x bpm_scale
    x faktor_overlap. Pemain di bawah replacement level (BPM < -2,0)
    berdampak NEGATIF: absennya justru sedikit menaikkan proyeksi,
    karena penggantinya (level -2,0) lebih baik darinya — itu jawaban
    jujur model, bukan bug. BPM/menit yang hilang dihitung 0 (pemain
    tanpa data tidak memengaruhi proyeksi).
    """
    bpm = pemain.get("bpm")
    mp = pemain.get("mp_per_game")
    if bpm is None or mp is None:
        return 0.0, None
    faktor, catatan = _faktor_overlap(pemain, w_last10)
    dampak = (float(bpm) - bpm_replacement) * (float(mp) / 48.0) * bpm_scale * faktor
    return dampak, catatan


def _pemain_inti(
    blok: dict, bpm_scale: float, bpm_replacement: float, w_last10: float
) -> tuple[list[tuple[str, float]], dict[str, str]]:
    """Pemain inti tim, urut dampak menurun + catatan overlap per nama.

    "Inti teratas" = dampak terbesar, bukan menit terbanyak — bintang
    adalah pemain yang ketidakhadirannya paling mengubah proyeksi.
    Catatan dikembalikan terpisah (dict nama -> catatan) agar pemanggil
    hanya mencatatnya untuk pemain yang memang absen, bukan semua
    pemain di daftar.
    """
    inti: list[tuple[str, float]] = []
    catatan: dict[str, str] = {}
    for pemain in blok.get("players") or []:
        nama = pemain.get("player")
        if not isinstance(nama, str) or not nama:
            continue
        dampak, note = _dampak_pemain(pemain, bpm_scale, bpm_replacement, w_last10)
        inti.append((nama, dampak))
        if note is not None:
            catatan[nama] = note
    inti.sort(key=lambda item: item[1], reverse=True)
    return inti, catatan


def _status_cedera(blok: dict) -> dict[str, str]:
    """Peta nama pemain -> status cedera (huruf besar) di blok tim."""
    status: dict[str, str] = {}
    for cedera in blok.get("injuries") or []:
        nama = cedera.get("player")
        st = cedera.get("status")
        if isinstance(nama, str) and isinstance(st, str):
            status[nama] = st.upper()
    return status


def _apakah_b2b(blok: dict) -> bool:
    """Apakah tim ini back-to-back: flag back_to_back, atau rest_days 0."""
    flag = blok.get("back_to_back")
    if flag is not None:
        return bool(flag)
    return blok.get("rest_days") == 0


def _ambil_teratas(
    inti: list[tuple[str, float]], absen: set[str], jumlah: int
) -> list[str]:
    """Ambil N nama teratas dari daftar inti yang belum absen."""
    if jumlah <= 0:
        return []
    hasil: list[str] = []
    for nama, _dampak in inti:
        if nama in absen:
            continue
        hasil.append(nama)
        if len(hasil) >= jumlah:
            break
    return hasil


def _skenario_standar(
    nama: str,
    inti_kandang: list[tuple[str, float]],
    inti_tandang: list[tuple[str, float]],
    absen_kandang: set[str],
    absen_tandang: set[str],
) -> tuple[list[str], list[str]]:
    """Bangun daftar absen satu skenario standar (lihat docstring modul)."""
    if nama == "full":
        return [], []
    pola = {"missing_1": (1, 0), "missing_2": (1, 1), "missing_4": (2, 2)}
    if nama not in pola:
        raise ValueError(f"skenario standar tidak dikenal: {nama!r}")
    n_kandang, n_tandang = pola[nama]
    tambah_kandang = _ambil_teratas(inti_kandang, absen_kandang, n_kandang)
    tambah_tandang = _ambil_teratas(inti_tandang, absen_tandang, n_tandang)
    return (
        sorted(absen_kandang | set(tambah_kandang)),
        sorted(absen_tandang | set(tambah_tandang)),
    )


def _simulasi_satu_skenario(
    mu_kandang: float,
    mu_tandang: float,
    noise: tuple[list[float], list[float], list[float]],
    sigma_umum: float,
    sigma_tim: float,
    nu: float,
    ot_frac: float,
    ot_max: int,
    rng: random.Random,
) -> tuple[list[tuple[float, float]], int]:
    """Jalankan satu skenario: kembalikan (draws, jumlah laga yang OT).

    draws: daftar (skor kandang, skor tandang) bilangan bulat (sebagai
    float), satu per iterasi, sudah termasuk OT bila ada.
    """
    n = len(noise[0])
    umum, idio_kandang, idio_tandang = noise
    mu_ot_kandang = mu_kandang * ot_frac
    mu_ot_tandang = mu_tandang * ot_frac
    skala_ot = math.sqrt(ot_frac)
    sigma_umum_ot = sigma_umum * skala_ot
    sigma_tim_ot = sigma_tim * skala_ot
    floor = math.floor
    t_draw = _student_t_draw
    draws: list[tuple[float, float]] = []
    ot_count = 0
    for i in range(n):
        h = mu_kandang + sigma_umum * umum[i] + sigma_tim * idio_kandang[i]
        a = mu_tandang + sigma_umum * umum[i] + sigma_tim * idio_tandang[i]
        hi = floor(h + 0.5)
        ai = floor(a + 0.5)
        if hi < 0:
            hi = 0
        if ai < 0:
            ai = 0
        if hi == ai:
            ot_count += 1
            periode = 0
            while hi == ai and periode < ot_max:
                periode += 1
                tc = t_draw(rng, nu)
                th = t_draw(rng, nu)
                ta = t_draw(rng, nu)
                ot_h = floor(
                    mu_ot_kandang + sigma_umum_ot * tc + sigma_tim_ot * th + 0.5
                )
                ot_a = floor(
                    mu_ot_tandang + sigma_umum_ot * tc + sigma_tim_ot * ta + 0.5
                )
                hi += max(ot_h, 0)
                ai += max(ot_a, 0)
        draws.append((float(hi), float(ai)))
    return draws, ot_count


def simulate(
    inputs: dict,
    cfg: dict | None = None,
    lines: dict | None = None,
    scenarios: list[dict] | None = None,
    seed: int | None = None,
    iterations: int | None = None,
) -> dict:
    """Simulasi satu laga NBA, hasil valid terhadap simulation.schema.json.

    inputs: dict hasil ingest.nba_brain.fetch_match_inputs (lihat
      kontrak di docstring modul: blok home/away, match, league, ...).
    cfg: dict playstyle (default: dibaca dari config/playstyle.yaml).
    lines: {"spreads": [...], "totals": [...]}; bila None, hanya
      moneyline + total pada median proyeksi (lihat docstring modul).
    scenarios: daftar skenario kustom {"name", "home_out", "away_out"};
      bila None, skenario standar dari config + "doubtful_out" bila ada.
    seed: bila diberikan, hasil deterministik (random.Random(seed)).
    iterations: jumlah iterasi; bila None, dari config
      simulation.iterations (100000). Tes unit memakai nilai kecil.
    """
    mulai = time.perf_counter()
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ValueError(f"seed harus integer atau None, didapat {seed!r}")
    if not isinstance(inputs, dict):
        raise ValueError("data_tidak_lengkap: inputs harus dict")
    blok_kandang = inputs.get("home")
    blok_tandang = inputs.get("away")
    if not isinstance(blok_kandang, dict) or not isinstance(blok_tandang, dict):
        raise ValueError("data_tidak_lengkap: blok home/away hilang")

    cfg = cfg if cfg is not None else config_mod.load_playstyle()
    if iterations is None:
        iterations = int(_param_numerik(cfg, "simulation", "iterations"))
    if (
        isinstance(iterations, bool)
        or not isinstance(iterations, int)
        or iterations < 1
    ):
        raise ValueError(f"iterations harus integer >= 1, didapat {iterations!r}")
    sigma_margin = _param_numerik(cfg, "simulation", "nba", "sigma_margin_points")
    sigma_total = _param_numerik(cfg, "simulation", "nba", "sigma_total_points")
    nu = _param_numerik(cfg, "simulation", "nba", "t_nu")
    bpm_scale = _param_numerik(cfg, "simulation", "nba", "bpm_scale")
    bpm_replacement = _param_numerik(cfg, "simulation", "nba", "bpm_replacement")
    home_adv = _param_numerik(cfg, "simulation", "nba", "home_advantage_points")
    b2b_penalty = _param_numerik(
        cfg, "simulation", "nba", "back_to_back_penalty_points"
    )
    altitude_adj = _param_numerik(
        cfg, "simulation", "nba", "altitude_adjustment_points"
    )
    tourney_adj = _param_numerik(
        cfg, "simulation", "nba", "tournament_adjustment_points"
    )
    ot_minutes = _param_numerik(cfg, "simulation", "nba", "overtime_minutes")
    ot_max = int(_param_numerik(cfg, "simulation", "nba", "ot_max_periods"))
    w_musim = _param_numerik(cfg, "simulation", "nba", "recency", "season")
    w_terakhir = _param_numerik(cfg, "simulation", "nba", "recency", "last10")
    daftar_skenario = config_mod.get_value(cfg, "simulation", "nba", "squad_scenarios")
    if sigma_margin <= 0 or sigma_total <= 0:
        raise config_mod.ConfigError("sigma_margin/total harus > 0")
    if nu <= 2:
        raise config_mod.ConfigError("t_nu harus > 2 (varians t tak hingga bila <= 2)")
    if ot_minutes <= 0 or ot_max < 1:
        raise config_mod.ConfigError("overtime_minutes > 0 dan ot_max_periods >= 1")
    total_bobot = w_musim + w_terakhir
    if total_bobot <= 0:
        raise config_mod.ConfigError("bobot recency harus berjumlah > 0")
    w_musim /= total_bobot
    w_terakhir /= total_bobot
    if not isinstance(daftar_skenario, list) or not all(
        isinstance(nama, str) for nama in daftar_skenario
    ):
        raise config_mod.ConfigError("squad_scenarios harus daftar string")

    catatan: list[str] = []
    tricode_kandang = blok_kandang.get("tricode") or "UNK"
    tricode_tandang = blok_tandang.get("tricode") or "UNK"
    stat_kandang = _combined_stats(
        blok_kandang, w_musim, w_terakhir, tricode_kandang, catatan
    )
    stat_tandang = _combined_stats(
        blok_tandang, w_musim, w_terakhir, tricode_tandang, catatan
    )
    liga = inputs.get("league") or {}
    lg_avg = liga.get("avg_off_rtg")
    if lg_avg is None:
        lg_avg = (
            stat_kandang["off_rtg"]
            + stat_kandang["def_rtg"]
            + stat_tandang["off_rtg"]
            + stat_tandang["def_rtg"]
        ) / 4.0
        catatan.append(
            "league.avg_off_rtg hilang — dipakai rata-rata keempat rating tim"
        )
    mu_kandang, mu_tandang, pace_laga = project_points(
        stat_kandang, stat_tandang, float(lg_avg)
    )

    # Penyesuaian konteks (nilai dari config; lihat docstring modul).
    mu_kandang += home_adv / 2.0
    mu_tandang -= home_adv / 2.0
    di_ketinggian = bool(blok_kandang.get("altitude_home")) or (
        tricode_kandang in ALTITUDE_TRICODES
    )
    if di_ketinggian:
        mu_kandang += altitude_adj / 2.0
        mu_tandang -= altitude_adj / 2.0
    turnamen = inputs.get("tournament")
    if turnamen:
        mu_kandang += tourney_adj / 2.0
        mu_tandang -= tourney_adj / 2.0
    b2b_kandang = _apakah_b2b(blok_kandang)
    b2b_tandang = _apakah_b2b(blok_tandang)
    if (
        blok_kandang.get("back_to_back") is None
        and blok_kandang.get("rest_days") is None
    ):
        catatan.append(
            "back_to_back kandang tidak diketahui — penalti tidak diterapkan"
        )
    if (
        blok_tandang.get("back_to_back") is None
        and blok_tandang.get("rest_days") is None
    ):
        catatan.append(
            "back_to_back tandang tidak diketahui — penalti tidak diterapkan"
        )
    if b2b_kandang:
        mu_kandang += b2b_penalty
    if b2b_tandang:
        mu_tandang += b2b_penalty

    # Pemain inti + cedera.
    inti_kandang, catatan_kandang = _pemain_inti(
        blok_kandang, bpm_scale, bpm_replacement, w_terakhir
    )
    inti_tandang, catatan_tandang = _pemain_inti(
        blok_tandang, bpm_scale, bpm_replacement, w_terakhir
    )
    dampak_kandang = dict(inti_kandang)
    dampak_tandang = dict(inti_tandang)
    cedera_kandang = _status_cedera(blok_kandang)
    cedera_tandang = _status_cedera(blok_tandang)
    absen_kandang = {nama for nama, st in cedera_kandang.items() if st in STATUS_ABSEN}
    absen_tandang = {nama for nama, st in cedera_tandang.items() if st in STATUS_ABSEN}
    for nama in sorted(absen_kandang | absen_tandang):
        if nama not in dampak_kandang and nama not in dampak_tandang:
            catatan.append(
                f"pemain OUT tanpa data BPM/menit: {nama} "
                "(dampak absen tidak bisa dihitung, dihitung 0)"
            )
        # Catatan overlap hanya untuk pemain yang memang absen di base
        # case (bukan semua pemain di daftar — pemain sehat tidak
        # memengaruhi proyeksi lewat jalur ini).
        note = catatan_kandang.get(nama) or catatan_tandang.get(nama)
        if note is not None:
            catatan.append(note)
    diragukan_kandang = [
        nama
        for nama, _d in inti_kandang
        if cedera_kandang.get(nama) in STATUS_DIRAGUKAN
    ]
    diragukan_tandang = [
        nama
        for nama, _d in inti_tandang
        if cedera_tandang.get(nama) in STATUS_DIRAGUKAN
    ]

    def _mu_dengan_absen(absen_h: list[str], absen_a: list[str]) -> tuple[float, float]:
        """Rata-rata poin setelah mengurangi dampak pemain absen."""
        mu_h = mu_kandang - sum(dampak_kandang.get(n, 0.0) for n in absen_h)
        mu_a = mu_tandang - sum(dampak_tandang.get(n, 0.0) for n in absen_a)
        return mu_h, mu_a

    # Base case: pemain OUT absen.
    mu_base_h, mu_base_a = _mu_dengan_absen(
        sorted(absen_kandang), sorted(absen_tandang)
    )

    # Garis default (bila lines None): moneyline + total pada median
    # proyeksi base case, dibulatkan ke 0,5 terdekat.
    lines_efektif: dict = lines if lines is not None else {}
    if lines is None:
        total_median = mu_base_h + mu_base_a
        garis_default = math.floor(total_median * 2.0 + 0.5) / 2.0
        lines_efektif = {"spreads": [], "totals": [garis_default]}

    # Daftar skenario: (nama, absen kandang, absen tandang).
    daftar: list[tuple[str, list[str], list[str]]] = []
    if scenarios is None:
        for nama in daftar_skenario:
            absen_h, absen_a = _skenario_standar(
                nama,
                inti_kandang,
                inti_tandang,
                absen_kandang,
                absen_tandang,
            )
            daftar.append((nama, absen_h, absen_a))
        if diragukan_kandang or diragukan_tandang:
            daftar.append(
                (
                    "doubtful_out",
                    sorted(absen_kandang | set(diragukan_kandang)),
                    sorted(absen_tandang | set(diragukan_tandang)),
                )
            )
    else:
        for skenario in scenarios:
            if not isinstance(skenario, dict) or "name" not in skenario:
                raise ValueError(f"skenario tidak valid: {skenario!r}")
            nama = skenario["name"]
            if nama == "full":
                daftar.append(("full", [], []))
                continue
            absen_h = set(absen_kandang)
            absen_a = set(absen_tandang)
            for nama_pemain in skenario.get("home_out") or []:
                if nama_pemain in dampak_kandang:
                    absen_h.add(nama_pemain)
                else:
                    catatan.append(
                        f"skenario {nama!r}: pemain kandang tidak dikenal "
                        f"(diabaikan): {nama_pemain}"
                    )
            for nama_pemain in skenario.get("away_out") or []:
                if nama_pemain in dampak_tandang:
                    absen_a.add(nama_pemain)
                else:
                    catatan.append(
                        f"skenario {nama!r}: pemain tandang tidak dikenal "
                        f"(diabaikan): {nama_pemain}"
                    )
            daftar.append((nama, sorted(absen_h), sorted(absen_a)))

    # Sebaran: komponen umum + idiosinkratik (lihat docstring modul).
    sigma_tim = sigma_margin / math.sqrt(2.0)
    var_umum = (sigma_total * sigma_total - sigma_margin * sigma_margin) / 4.0
    if var_umum < 0:
        catatan.append(
            "sigma_total < sigma_margin — komponen umum diset 0 "
            "(varians total tidak bisa di bawah varians margin)"
        )
        sigma_umum = 0.0
    else:
        sigma_umum = math.sqrt(var_umum)
    ot_frac = ot_minutes / 48.0

    rng = random.Random(seed)
    noise: tuple[list[float], list[float], list[float]] = (
        [_student_t_draw(rng, nu) for _ in range(iterations)],
        [_student_t_draw(rng, nu) for _ in range(iterations)],
        [_student_t_draw(rng, nu) for _ in range(iterations)],
    )

    # Base case.
    draws_base, ot_base = _simulasi_satu_skenario(
        mu_base_h,
        mu_base_a,
        noise,
        sigma_umum,
        sigma_tim,
        nu,
        ot_frac,
        ot_max,
        rng,
    )
    markets_base = {
        kunci: round(nilai, 6)
        for kunci, nilai in markets.evaluate_markets(draws_base, lines_efektif).items()
    }
    margin = sorted(h - a for h, a in draws_base)
    total = sorted(h + a for h, a in draws_base)
    skor_kandang = sorted(h for h, _a in draws_base)
    skor_tandang = sorted(a for _h, a in draws_base)
    dist_margin = {
        "mean": round(statistics.mean(margin), 2),
        "std": round(statistics.pstdev(margin), 2),
        "median": round(_kuantil(margin, 0.5), 2),
        "p5": round(_kuantil(margin, 0.05), 2),
        "p25": round(_kuantil(margin, 0.25), 2),
        "p75": round(_kuantil(margin, 0.75), 2),
        "p95": round(_kuantil(margin, 0.95), 2),
    }
    dist_total = {
        "mean": round(statistics.mean(total), 2),
        "std": round(statistics.pstdev(total), 2),
        "median": round(_kuantil(total, 0.5), 2),
        "p5": round(_kuantil(total, 0.05), 2),
        "p25": round(_kuantil(total, 0.25), 2),
        # p74: KONTRAK modul cushion (patch 1b perbaikan 3) — garis Alt
        # Under Asuransi = garis market terkecil dengan P(Under) >= 74%.
        "p74": round(_kuantil(total, 0.74), 2),
        "p75": round(_kuantil(total, 0.75), 2),
        "p95": round(_kuantil(total, 0.95), 2),
    }

    # Skenario skuad (noise yang sama — common random numbers).
    hasil_skenario: list[dict] = []
    for nama, absen_h, absen_a in daftar:
        mu_h, mu_a = _mu_dengan_absen(absen_h, absen_a)
        draws_sken, _ot = _simulasi_satu_skenario(
            mu_h,
            mu_a,
            noise,
            sigma_umum,
            sigma_tim,
            nu,
            ot_frac,
            ot_max,
            rng,
        )
        markets_sken = {
            kunci: round(nilai, 6)
            for kunci, nilai in markets.evaluate_markets(
                draws_sken, lines_efektif
            ).items()
        }
        hasil_skenario.append(
            {
                "scenario": nama,
                "absent_players": sorted(set(absen_h) | set(absen_a)),
                "markets": markets_sken,
            }
        )

    selesai = time.perf_counter()
    pertandingan = inputs.get("match") or {}
    tanggal = pertandingan.get("game_date") or "tanggal_tidak_diketahui"
    return {
        "match_id": f"{tricode_tandang}@{tricode_kandang}_{tanggal}",
        "sport": "nba",
        "iterations": iterations,
        "generated_at": datetime.now(UTC).isoformat(),
        "engine": {
            "name": "nba_sim",
            "version": ENGINE_VERSION,
            "seed": seed,
        },
        "markets": markets_base,
        "inputs_summary": {
            "home_tricode": tricode_kandang,
            "away_tricode": tricode_tandang,
            "game_date": tanggal,
            "season": pertandingan.get("season"),
            "pace_game": round(pace_laga, 2),
            "league_avg_off_rtg": round(float(lg_avg), 2),
            "league_avg_pace": liga.get("avg_pace"),
            "projected_home_points": round(mu_base_h, 2),
            "projected_away_points": round(mu_base_a, 2),
            "projected_margin": round(mu_base_h - mu_base_a, 2),
            "projected_total": round(mu_base_h + mu_base_a, 2),
            "recency_weights": {
                "season": round(w_musim, 3),
                "last10": round(w_terakhir, 3),
            },
            "home_advantage_points": home_adv,
            "back_to_back": {
                "home": b2b_kandang,
                "away": b2b_tandang,
                "penalty_points": b2b_penalty,
            },
            "altitude_home": di_ketinggian,
            "altitude_adjustment_points": altitude_adj if di_ketinggian else 0.0,
            "tournament": turnamen,
            "tournament_adjustment_points": tourney_adj if turnamen else 0.0,
            "sigma_margin_points": sigma_margin,
            "sigma_total_points": sigma_total,
            "t_nu": nu,
            "bpm_scale": bpm_scale,
            "bpm_replacement": bpm_replacement,
            "base_absent_players": sorted(absen_kandang | absen_tandang),
            "elapsed_seconds": round(selesai - mulai, 3),
            "notes": catatan,
        },
        "score_distribution": {
            "margin": dist_margin,
            "total": dist_total,
            "home_points": {
                "mean": round(statistics.mean(skor_kandang), 2),
                "median": round(_kuantil(skor_kandang, 0.5), 2),
            },
            "away_points": {
                "mean": round(statistics.mean(skor_tandang), 2),
                "median": round(_kuantil(skor_tandang, 0.5), 2),
            },
            "ot_probability": round(ot_base / iterations, 4),
        },
        "squad_scenarios": hasil_skenario,
    }
