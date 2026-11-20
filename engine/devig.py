"""Devig (hilangkan vig sportsbook) + blend model-pasar (Tahap 2b/3).

`american_to_decimal` dan `devig` dibangun di Tahap 2b (dipakai untuk
menghitung p_market dari odds sportsbook). `blend` tetap stub Tahap 3
— sengaja melempar NotImplementedError sampai tahapnya dibangun.

Rumus devig (Blueprint §5c, digeneralisasi ke n outcome):
  p_no-vig(A) = (1/odds_A) / Σ(1/odds_i)
"""

from __future__ import annotations

import math


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


def blend(*args, **kwargs):
    """Devig, blend model-pasar, edge, dan deteksi anomali."""
    raise NotImplementedError(
        "engine.devig belum tersedia (Tahap 3). "
        "Jangan dipakai sampai tahapnya selesai dan dites."
    )
