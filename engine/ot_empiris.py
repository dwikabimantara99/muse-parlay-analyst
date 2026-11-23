"""Probabilitas overtime EMPIRIS (v18 — menggantikan pemicu sim 2,8%).

Latar (audit Gemini §1.4, TERVERIFIKASI main agent): pemicu keras
v17 (ot_probability sim >= 0,028) CACAT — kap teoretis P(OT) sim di
spread 0 hanya 2,74% (densitas t(35) di 0 = 0,3961 / 14,4307),
jadi ambang 2,8% BERADA DI ATAS kap dan hanya mendeteksi noise
Monte Carlo (kasus DET@ATL 2,89%). Sim MEREMEHKAN OT (1,7–2,9% vs
laju nyata NBA ~5,5–6,0%) karena strategi clutch Q4 — foul
sengaja, tembakan 3 poin tim tertinggal, timeout — tidak dimodelkan
sim (sim hanya melempar dua skor independen lalu melihat seri).

RUMUS v18 (engine ini):
    p_ot(spread) = base_rate_ot x exp(-spread^2 / (2 x sigma_margin^2))
- spread = |median margin sim| (poin) — selisih skor yang
  diharapkan; makin tipis spread, makin tinggi peluang OT.
- base_rate_ot = laju dasar OT NBA (config ot_seleksi.base_rate_ot,
  0,0575 = PRIOR titik tengah 5,5–6,0%, BUKAN hasil fit — lihat
  di bawah).
- sigma_margin = simulation.nba.sigma_margin_points (14,4307,
  HASIL FIT rolling n=2.701 — dipakai ulang, bukan parameter baru).
- Bentuk exp(-spread^2/2σ^2) adalah rasio densitas normal margin
  di 0 antara laga berselisih `spread` vs laga imbang: peluang seri
  sebanding dengan densitas margin di 0. Ini SATU-SATUNYA bagian
  rumus yang berbentuk "model" — dan bentuknya mengikuti sim yang
  sama (margin ~ Normal(spread, sigma_margin)).

KENAPA BUKAN FIT: gamelog stats.nba.com (leaguegamefinder — sumber
fit 2.701 laga) TIDAK membawa flag OT (hanya PTS/WL/MATCHUP);
tidak ada data (spread, OT/tidak) di repo untuk mem-fit laju dasar
atau sensitivitas spread. base_rate_ot 0,0575 adalah PRIOR dari
angka umum NBA (~5,5–6,0%, dipakai Gemini §1.4) yang
DIDOKUMENTASIKAN sebagai prior. RENCANA FIT: kumpulkan flag OT per
laga selesai (boxscore BBRef / ESPN — tiap laga dicatat OT/tidak +
spread penutupnya), lalu fit laju dasar + laju per pita spread;
berlaku hanya atas persetujuan user (pola D12).

TEMUAN JUJUR — HARD-SKIP DORMAN: dengan rumus ini, p_ot MAKSIMUM
(spread 0) = base_rate_ot = 0,0575, DI BAWAH ambang hard-skip
config (0,085). Artinya hard-skip OT v18 TIDAK PERNAH menyala
sampai kalibrasi ledger menyediakan laju OT per pita spread (yang
bisa menaikkan laju laga pick'em di atas 0,085) ATAU ambang
diturunkan atas persetujuan user. Ini DISEJANGA: gate yang tidak
bisa dibuktikan tidak boleh membunuh laga diam-diam. Ambang 0,085
(Gemini §3, "mis. spread <= 1,5 + pace/clutch tinggi") dipasang
tanpa analisis densitas ini — dan analisis densitas menunjukkan
laju pick'em yang konsisten dengan laju liga 5,75% adalah ~5,75%
sendiri (bukan 8,5%+): pengali clutch ~2x atas densitas sim
(2,77%) memberi 5,5%, dan rasio densitas spread-0 vs spread-rata
hanya ~1,07x. Laga pick'em TIDAK 1,5x lebih rawan OT dari laga
rata-rata — klaim itu butuh data pita spread, bukan asumsi.

PACE: probabilitas_ot_empiris menerima pace_tercepat untuk API
mendatang, tapi v18 TIDAK memakainya: tidak ada hubungan
pace -> OT yang terukur (argumen kedua arah sama masuk akalnya —
pace tinggi berarti lebih banyak possession sehingga margin lebih
menyebar [OT lebih jarang] TAPI juga lebih banyak stoppage/clutch
[OT lebih sering]). Parameter dicatat di hasil evaluasi untuk
kalibrasi mendatang, bukan dihitung dalam rumus. JANGAN menambah
faktor pace tanpa data.

Modul ini MURNI HITUNG: tanpa fetch, tanpa Odds API. Satu-satunya
I/O adalah baca config bila argumen cfg None.
"""

from __future__ import annotations

import math

import config as config_mod


def _angka(nilai) -> float | None:
    """Ubah nilai menjadi float berhingga, atau None bila tidak valid."""
    if isinstance(nilai, bool) or nilai is None:
        return None
    try:
        hasil = float(nilai)
    except (TypeError, ValueError):
        return None
    return hasil if math.isfinite(hasil) else None


def _muat_cfg(cfg: dict | None) -> dict:
    if cfg is not None:
        return cfg
    return config_mod.load_playstyle()


def _ambang(cfg: dict, *kunci: str) -> float:
    """Ambil ambang numerik dari config; hilang/tidak valid -> ConfigError."""
    nilai = config_mod.get_value(cfg, *kunci)
    hasil = _angka(nilai)
    if hasil is None:
        raise config_mod.ConfigError(
            f"playstyle.yaml kunci {'.'.join(kunci)} bukan angka: {nilai!r}"
        )
    return hasil


def baca_spread(analysis: dict) -> float | None:
    """Spread laga (poin, >= 0) = |median margin sim|.

    Lokasi kanonik: simulation.score_distribution.margin.median
    (ditulis engine/nba_sim.py). Fallback: margin.mean (varian
    artefak lama) — bila keduanya ada, median menang (median lebih
    kokoh terhadap ekor sim). None bila keduanya tidak ada / tidak
    valid. Spread adalah SELISIH SKOR YANG DIHARAPKAN (bukan garis
    spread pasar): garis pasar tidak dipakai karena garis spread
    utama tidak ditandai di tangga (market.spreads hanya daftar
    garis tanpa penanda "utama").
    """
    if not isinstance(analysis, dict):
        return None
    sim = analysis.get("simulation")
    if not isinstance(sim, dict):
        return None
    dist = sim.get("score_distribution")
    if not isinstance(dist, dict):
        return None
    margin = dist.get("margin")
    if not isinstance(margin, dict):
        return None
    median = _angka(margin.get("median"))
    if median is not None:
        return abs(median)
    mean = _angka(margin.get("mean"))
    if mean is not None:
        return abs(mean)
    return None


def baca_ambang_hard_skip(cfg: dict | None = None) -> float:
    """Ambang hard-skip OT empiris dari config (0-1, ConfigError bila rusak)."""
    cfg = _muat_cfg(cfg)
    ambang = _ambang(cfg, "ot_seleksi", "hard_skip_ot_prob")
    if not 0.0 <= ambang <= 1.0:
        raise config_mod.ConfigError(
            "playstyle.yaml ot_seleksi.hard_skip_ot_prob di luar 0-1: " f"{ambang!r}"
        )
    return ambang


def _validasi_konfigurasi(cfg: dict) -> tuple[float, float]:
    """Validasi config OT empiris (fail-closed) -> (base_rate, sigma).

    Mode HARUS "empiris", base_rate_ot di (0,1), sigma_margin > 0.
    Dipakai probabilitas_ot_empiris DAN evaluasi_ot — evaluasi_ot
    memvalidasi di muka supaya config rusak ketahuan bahkan bila
    spread tidak ada (bukan baru ketahuan saat spread ada).
    """
    mode = config_mod.get_value(cfg, "ot_seleksi", "mode")
    if mode != "empiris":
        raise config_mod.ConfigError(
            "playstyle.yaml ot_seleksi.mode harus 'empiris' untuk "
            f"OT empiris: {mode!r}"
        )
    base_rate = _ambang(cfg, "ot_seleksi", "base_rate_ot")
    if not 0.0 < base_rate < 1.0:
        raise config_mod.ConfigError(
            f"playstyle.yaml ot_seleksi.base_rate_ot di luar (0,1): {base_rate!r}"
        )
    sigma = _ambang(cfg, "simulation", "nba", "sigma_margin_points")
    if sigma <= 0:
        raise config_mod.ConfigError(
            "playstyle.yaml simulation.nba.sigma_margin_points harus > 0: " f"{sigma!r}"
        )
    return base_rate, sigma


def probabilitas_ot_empiris(
    spread_points: float, cfg: dict | None = None, pace_tercepat: float | None = None
) -> float:
    """Peluang OT empiris satu laga dari spread-nya (0-1).

    ``spread_points``: |median margin| dalam poin (>= 0; nilai
    negatif dibaca nilai absolutnya — spread adalah jarak, bukan
    arah). ``cfg``: dict playstyle (default: dibaca dari file).
    ``pace_tercepat``: pace musim tim tercepat — DITERIMA tapi
    TIDAK DIPAKAI di v18 (lihat docstring modul: tidak ada hubungan
    pace -> OT yang terukur; parameter dipertahankan untuk
    kalibrasi mendatang).

    Rumus: base_rate_ot x exp(-spread^2 / (2 x sigma_margin^2)).
    base_rate_ot dari ot_seleksi.base_rate_ot (prior 0,0575);
    sigma_margin dari simulation.nba.sigma_margin_points (HASIL FIT
    14,4307). Mode config ot_seleksi.mode HARUS "empiris" (nilai
    lain -> ConfigError — fail-closed: rumus ini hanya berlaku
    untuk mode empiris). spread None / bukan angka / tidak hingga
    -> ValueError (pemanggil yang mencatat "tidak dievaluasi").
    """
    spread = _angka(spread_points)
    if spread is None:
        raise ValueError(f"spread_points harus angka berhingga: {spread_points!r}")
    cfg = _muat_cfg(cfg)
    base_rate, sigma = _validasi_konfigurasi(cfg)
    p_ot = base_rate * math.exp(-(abs(spread) ** 2) / (2.0 * sigma * sigma))
    return min(max(p_ot, 0.0), 1.0)


def evaluasi_ot(
    analysis: dict, cfg: dict | None = None, pace_tercepat: float | None = None
) -> dict:
    """Evaluasi OT empiris satu laga dari artefaknya.

    Mengembalikan dict {"dievaluasi", "spread_points", "p_ot_empiris",
    "p_ot_sim", "ambang_hard_skip", "hard_skip", "pace_tercepat",
    "alasan_tidak_dievaluasi"} — "dievaluasi" False bila spread
    tidak bisa dibaca (median/mean margin hilang); p_ot_sim (bila
    ada di artefak) dicatat sebagai INFO perbandingan, bukan dipakai
    keputusan. "hard_skip" True hanya bila p_ot_empiris >= ambang
    (dengan rumus v18, tidak pernah — lihat docstring modul).
    Config rusak -> ConfigError (fail-closed, seperti ambang lain).
    """
    cfg = _muat_cfg(cfg)
    ambang = baca_ambang_hard_skip(cfg)
    # Validasi mode + laju dasar + sigma DI MUKA: config rusak harus
    # ketahuan bahkan bila spread tidak ada (fail-closed).
    _validasi_konfigurasi(cfg)
    hasil: dict = {
        "dievaluasi": False,
        "spread_points": None,
        "p_ot_empiris": None,
        "p_ot_sim": None,
        "ambang_hard_skip": ambang,
        "hard_skip": False,
        "pace_tercepat": pace_tercepat,
        "alasan_tidak_dievaluasi": None,
    }
    # p_ot_sim (info saja): lokasi kanonik + fallback artefak lama.
    sim = analysis.get("simulation") if isinstance(analysis, dict) else None
    if isinstance(sim, dict):
        dist = sim.get("score_distribution")
        if isinstance(dist, dict):
            p_sim = _angka(dist.get("ot_probability"))
            if p_sim is not None and 0.0 <= p_sim <= 1.0:
                hasil["p_ot_sim"] = p_sim
        if hasil["p_ot_sim"] is None:
            p_sim = _angka(sim.get("ot_probability"))
            if p_sim is not None and 0.0 <= p_sim <= 1.0:
                hasil["p_ot_sim"] = p_sim
    spread = baca_spread(analysis)
    if spread is None:
        hasil["alasan_tidak_dievaluasi"] = (
            "spread tidak bisa dibaca (median/mean margin sim tidak ada)"
        )
        return hasil
    hasil["spread_points"] = spread
    hasil["p_ot_empiris"] = probabilitas_ot_empiris(
        spread, cfg, pace_tercepat=pace_tercepat
    )
    hasil["dievaluasi"] = True
    hasil["hard_skip"] = hasil["p_ot_empiris"] >= ambang
    return hasil
