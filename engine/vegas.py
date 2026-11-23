"""Vegas sanity check: susutkan median model ke arah pasar (v18).

ATURAN (proposal audit Gemini v18 §2 Q8 + §3, draf config
``calibration``): cek ini berjalan TEPAT SETELAH ``sim`` (sebelum
vonis dan equilibrium — bukan di tahap akhir Asuransi seperti aturan
condong-ke-market lama). Bila selisih |median model - garis pasar| >
``calibration.lean_to_market_gap`` (5,0 poin) DAN tidak ada sebab
cedera baru terverifikasi, median model DISUSUTKAN ke arah pasar
sebelum vonis/equilibrium dihitung.

JUMLAH PENYUSUTAN (keputusan desain worker B v18 — menunggu
keberatan user/reviewer; lihat LAPORAN-GATE-V18.md §Vegas):
setengah jarak ke pasar (``calibration.shrinkage.fraction`` 0,5,
mode "setengah_jarak"). Alasan: pasar NBA efisien — selisih besar
tanpa sebab cedera lebih mungkin berarti model yang meleset
daripada pasar yang salah — tapi model punya informasi independen
(rating, cedera, form) yang tidak boleh dibuang sepenuhnya.
Susut penuh (fraction 1,0) sama saja membuang model dan memakai
pasar mentah-mentah; susut setengah mengakui kedua belah pihak
punya informasi. KALIBRASI: kumpulkan median pra-susut +
median pasca-susut + total aktual dari slate PAPER; ukur Brier /
MAE total pada tiap fraction (0,25 / 0,5 / 0,75 / 1,0); pilih
fraction yang paling akurat, hanya atas persetujuan user.

Modul ini MURNI HITUNG: tanpa fetch, tanpa Odds API. Satu-satunya
I/O adalah baca config bila argumen cfg None. Fungsi
``sesuaikan_median`` DIPAKAI worker C di nba_analysis.py (wiring)
— JAGA signature-nya persis seperti di bawah.
"""

from __future__ import annotations

import math

import config as config_mod

# Nilai default bila kunci v18 belum ada di config (pola yang sama
# dengan _angka_config_atau_default di ticket_composer: kunci baru
# v18 mungkin belum ditulis worker A saat modul ini dipakai).
# Nilai-nilai ini BUKAN tebakan: lean_to_market_gap 5,0 = ambang
# lama market_line_check.total_gap_points yang dipakai ulang
# (proposal Gemini §3); fraction 0,5 = keputusan desain di atas.
_DEFAULT_GAP_POINTS = 5.0
_DEFAULT_FRACTION = 0.5
_DEFAULT_MODE = "setengah_jarak"

# Mode penyusutan yang dikenal. "setengah_jarak": median baru =
# median + fraction x (pasar - median). Mode lain -> ConfigError
# (fail-closed: mode yang salah diam-diam lebih buruk daripada
# error keras).
_MODE = ("setengah_jarak",)


def _angka(nilai) -> float | None:
    """Ubah nilai menjadi float berhingga, atau None bila tidak valid."""
    if isinstance(nilai, bool) or nilai is None:
        return None
    try:
        hasil = float(nilai)
    except (TypeError, ValueError):
        return None
    return hasil if math.isfinite(hasil) else None


def _cfg_angka_atau_default(cfg: dict, kunci: tuple[str, ...], default: float) -> float:
    """Baca angka dari config; kunci hilang -> default.

    Kunci ADA tapi bukan angka -> ConfigError (config rusak, bukan
    data hilang). Pola yang sama dengan _angka_config_atau_default
    di ticket_composer (kunci baru v18, integrasi paralel).
    """
    try:
        nilai = config_mod.get_value(cfg, *kunci)
    except config_mod.ConfigError:
        return default
    hasil = _angka(nilai)
    if hasil is None:
        raise config_mod.ConfigError(
            f"playstyle.yaml kunci {'.'.join(kunci)} bukan angka: {nilai!r}"
        )
    return hasil


def sesuaikan_median(
    median_model, garis_pasar, ada_sebab_cedera_baru, cfg=None
) -> dict:
    """Sesuaikan median model ke arah garis pasar bila selisihnya besar.

    ``median_model``: median total simulasi model (poin).
    ``garis_pasar``: garis total utama market (poin).
    ``ada_sebab_cedera_baru``: True bila ada sebab cedera baru
    terverifikasi yang menjelaskan selisih (dalam hal itu median
    TIDAK disusutkan — model boleh beda dari pasar karena tahu
    sesuatu yang belum diserap pasar).
    ``cfg``: dict playstyle (None = muat default).

    Mengembalikan {"median_baru", "geser", "diterapkan", "alasan"}:
    - "median_baru": median setelah penyesuaian (sama dengan median
      model bila tidak diterapkan).
    - "geser": median_baru - median_model (bertanda: positif bila
      median naik ke arah pasar, negatif bila turun; 0,0 bila tidak
      diterapkan).
    - "diterapkan": True bila penyusutan diterapkan.
    - "alasan": kalimat Bahasa Indonesia (alasan penerapan atau
      alasan tidak diterapkan — selalu terisi, untuk jejak audit).

    Median/pasar bukan angka -> ValueError. Config rusak (ambang /
    fraction bukan angka, fraction di luar 0-1, mode tidak dikenal)
    -> ConfigError (fail-closed).
    """
    median = _angka(median_model)
    pasar = _angka(garis_pasar)
    if median is None:
        raise ValueError(f"median_model harus angka, dapat: {median_model!r}")
    if pasar is None:
        raise ValueError(f"garis_pasar harus angka, dapat: {garis_pasar!r}")
    cfg = cfg if cfg is not None else config_mod.load_playstyle()
    ambang_gap = _cfg_angka_atau_default(
        cfg, ("calibration", "lean_to_market_gap"), _DEFAULT_GAP_POINTS
    )
    fraction = _cfg_angka_atau_default(
        cfg, ("calibration", "shrinkage", "fraction"), _DEFAULT_FRACTION
    )
    try:
        mode = config_mod.get_value(cfg, "calibration", "shrinkage", "mode")
    except config_mod.ConfigError:
        mode = _DEFAULT_MODE
    if not isinstance(mode, str) or mode not in _MODE:
        raise config_mod.ConfigError(
            "playstyle.yaml calibration.shrinkage.mode harus salah satu "
            f"dari {list(_MODE)}, dapat: {mode!r}"
        )
    if ambang_gap < 0:
        raise config_mod.ConfigError(
            f"playstyle.yaml calibration.lean_to_market_gap harus >= 0: {ambang_gap}"
        )
    if not 0.0 <= fraction <= 1.0:
        raise config_mod.ConfigError(
            "playstyle.yaml calibration.shrinkage.fraction harus 0-1: " f"{fraction}"
        )
    selisih = pasar - median
    gap = abs(selisih)

    def _fmt(nilai: float) -> str:
        return f"{nilai:.2f}".replace(".", ",")

    if ada_sebab_cedera_baru:
        return {
            "median_baru": median,
            "geser": 0.0,
            "diterapkan": False,
            "alasan": (
                f"selisih median vs pasar {_fmt(gap)} poin tapi ada sebab "
                "cedera baru terverifikasi — median model dipertahankan "
                "(model tahu sesuatu yang belum diserap pasar)"
            ),
        }
    if gap <= ambang_gap:
        return {
            "median_baru": median,
            "geser": 0.0,
            "diterapkan": False,
            "alasan": (
                f"selisih median vs pasar {_fmt(gap)} poin dalam batas "
                f"{_fmt(ambang_gap)} poin — median model dipertahankan"
            ),
        }
    median_baru = median + fraction * selisih
    geser = median_baru - median
    arah = "naik" if geser > 0 else "turun"
    return {
        "median_baru": median_baru,
        "geser": geser,
        "diterapkan": True,
        "alasan": (
            f"selisih median vs pasar {_fmt(gap)} poin melebihi batas "
            f"{_fmt(ambang_gap)} poin tanpa sebab cedera baru — median "
            f"disusutkan {arah} {_fmt(abs(geser))} poin ke arah pasar "
            f"(setengah jarak, fraction {fraction:g})"
        ),
    }
