"""Devig (hilangkan vig sportsbook) + blend model-pasar (Tahap 2b/3).

`american_to_decimal` dan `devig` dibangun di Tahap 2b (dipakai untuk
menghitung p_market dari odds sportsbook). `blend` dibangun di Tahap 3
(Langkah 1, Otak NBA): menggabungkan p_model dan p_market dengan bobot
w dari playstyle.yaml -> blend.w_model.

Rumus devig (Blueprint §5c, digeneralisasi ke n outcome):
  p_no-vig(A) = (1/odds_A) / Σ(1/odds_i)

Rumus blend (Blueprint §5c + keputusan user 2026-11-21):
  p_final = w * p_model + (1 - w) * p_market
  Bila p_market tidak ada (MODEL_ONLY, D2): p_final = p_model.
"""

from __future__ import annotations

import math

import config


def american_to_decimal(american: int | float) -> float:
    """Ubah odds Amerika jadi odds desimal.

    Positif (+150): 1 + american/100. Negatif (-110): 1 + 100/|american|.
    Melempar ValueError bila bukan angka, 0, tidak hingga, atau |x| < 100
    (bukan harga Amerika yang valid).
    """
    if (
        isinstance(american, bool)
        or not isinstance(american, (int, float))
        or not math.isfinite(american)
        or american == 0
        or abs(american) < 100
    ):
        raise ValueError(f"odds Amerika tidak valid: {american!r}")
    if american > 0:
        return 1.0 + american / 100.0
    return 1.0 + 100.0 / abs(american)


def devig(odds: list[float], odds_format: str = "decimal") -> list[float]:
    """Hilangkan vig dari daftar odds -> peluang no-vig (jumlah = 1).

    odds_format: "decimal" (odds > 1) atau "american" (mis. -110, +150).
    Rumus Blueprint §5c: tiap peluang implisit (1/odds) dibagi totalnya.
    Melempar ValueError bila daftar kosong, format tidak dikenal, atau
    ada odds yang tidak valid.
    """
    if odds_format not in ("decimal", "american"):
        raise ValueError(
            f"odds_format harus 'decimal' atau 'american', didapat {odds_format!r}"
        )
    if not isinstance(odds, (list, tuple)) or len(odds) == 0:
        raise ValueError("odds harus daftar tidak kosong")
    decimals: list[float] = []
    for odd in odds:
        if odds_format == "american":
            decimals.append(american_to_decimal(odd))
        else:
            if (
                isinstance(odd, bool)
                or not isinstance(odd, (int, float))
                or not math.isfinite(odd)
                or odd <= 1.0
            ):
                raise ValueError(f"odds desimal tidak valid: {odd!r} (harus > 1)")
            decimals.append(float(odd))
    implied = [1.0 / decimal for decimal in decimals]
    total = sum(implied)
    return [p / total for p in implied]


def _validasi_peluang(nilai, nama: str) -> float:
    """Pastikan nilai adalah peluang desimal 0–1 yang hingga.

    Melempar ValueError bila bukan angka, bool, tidak hingga, atau di
    luar 0–1. Mengembalikan nilai sebagai float.
    """
    if (
        isinstance(nilai, bool)
        or not isinstance(nilai, (int, float))
        or not math.isfinite(nilai)
        or not 0.0 <= nilai <= 1.0
    ):
        raise ValueError(f"{nama} tidak valid: {nilai!r} (harus peluang 0–1)")
    return float(nilai)


def blend(p_model, p_market, cfg: dict | None = None) -> dict:
    """Gabung peluang model dan pasar -> p_final (Blueprint §5c, D2).

    p_final = w * p_model + (1 - w) * p_market, dengan w dari
    playstyle.yaml -> blend.w_model (cfg opsional, untuk tes).
    Bila p_market None (MODEL_ONLY, D2): p_final = p_model.
    Mengembalikan dict {"p_final", "p_model", "p_market", "w_model",
    "model_only"}. Melempar ValueError bila p_model None/tidak valid,
    p_market tidak valid, atau w di luar 0–1.
    """
    if p_model is None:
        raise ValueError("p_model wajib ada (model tidak boleh kosong)")
    p_model = _validasi_peluang(p_model, "p_model")
    if p_market is not None:
        p_market = _validasi_peluang(p_market, "p_market")
    cfg = cfg if cfg is not None else config.load_playstyle()
    w = _validasi_peluang(config.get_value(cfg, "blend", "w_model"), "blend.w_model")
    if p_market is None:
        return {
            "p_final": p_model,
            "p_model": p_model,
            "p_market": None,
            "w_model": w,
            "model_only": True,
        }
    return {
        "p_final": w * p_model + (1.0 - w) * p_market,
        "p_model": p_model,
        "p_market": p_market,
        "w_model": w,
        "model_only": False,
    }
