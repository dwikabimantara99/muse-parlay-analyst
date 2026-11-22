"""Menilai pasar dari satu hasil simulasi (Blueprint §5).

Satu simulasi untuk semua pasar: moneyline, spread, dan total dihitung
dari draws (pasangan skor kandang-tandang) yang sama, sehingga
keterkaitan antar kaki dalam satu laga terhitung otomatis.

Definisi (draw = satu pasangan skor (kandang, tandang)):

- ``moneyline_home`` = P(kandang > tandang); ``moneyline_away`` =
  P(tandang > kandang). Seri (tidak ada pemenang setelah OT) tidak
  dihitung di keduanya, sehingga jumlahnya bisa < 1.
- ``spread_home_L`` = P(margin + L > 0), margin = kandang − tandang,
  L garis bertanda dari sudut kandang. Contoh: L = −5.5 berarti
  kandang harus menang > 5,5 poin; L = +5.5 berarti kandang boleh
  kalah sampai 5 poin. Push (margin + L == 0) dihitung BUKAN menang.
- ``total_under_L`` = P(total < L); ``total_over_L`` = P(total > L).
  Push (total == L) dihitung bukan menang di keduanya.

Fungsi di sini murni: tanpa config, tanpa I/O, tanpa RNG.
"""

from __future__ import annotations

import math


def _validasi_draws(draws: list[tuple[float, float]]) -> None:
    """Pastikan draws adalah daftar pasangan skor berhingga tidak kosong."""
    if not isinstance(draws, (list, tuple)) or len(draws) == 0:
        raise ValueError("draws harus daftar pasangan skor tidak kosong")
    for draw in draws:
        if (
            not isinstance(draw, (list, tuple))
            or len(draw) != 2
            or any(
                isinstance(skor, bool)
                or not isinstance(skor, (int, float))
                or not math.isfinite(skor)
                for skor in draw
            )
        ):
            raise ValueError(f"draw tidak valid (harus pasangan angka): {draw!r}")


def _validasi_garis(lines: dict | None) -> tuple[list[float], list[float]]:
    """Ambil + validasi daftar garis spread/total dari argumen lines."""
    if lines is None:
        return [], []
    if not isinstance(lines, dict):
        raise ValueError(f"lines harus dict, didapat {type(lines).__name__}")
    hasil: list[list[float]] = []
    for kunci in ("spreads", "totals"):
        daftar = lines.get(kunci) or []
        if not isinstance(daftar, (list, tuple)):
            raise ValueError(f"lines[{kunci!r}] harus daftar angka")
        angka: list[float] = []
        for nilai in daftar:
            if (
                isinstance(nilai, bool)
                or not isinstance(nilai, (int, float))
                or not math.isfinite(nilai)
            ):
                raise ValueError(f"garis tidak valid di lines[{kunci!r}]: {nilai!r}")
            angka.append(float(nilai))
        hasil.append(angka)
    return hasil[0], hasil[1]


def evaluate_markets(
    draws: list[tuple[float, float]], lines: dict | None = None
) -> dict[str, float]:
    """Nilai semua pasar dari satu daftar draws simulasi.

    draws: daftar pasangan (skor kandang, skor tandang), satu per
    iterasi simulasi. lines: {"spreads": [...], "totals": [...]} —
    garis yang diminta; bila None/{} hanya moneyline yang dinilai.

    Mengembalikan dict peluang 0–1 dengan kunci "moneyline_home",
    "moneyline_away", "spread_home_<garis>" (misal "spread_home_-5.5",
    "spread_home_+5.5"), "total_under_<garis>", "total_over_<garis>".
    """
    _validasi_draws(draws)
    spreads, totals = _validasi_garis(lines)
    n = len(draws)

    menang_kandang = 0
    menang_tandang = 0
    hitung_spread = [0] * len(spreads)
    hitung_under = [0] * len(totals)
    hitung_over = [0] * len(totals)
    for skor_kandang, skor_tandang in draws:
        margin = skor_kandang - skor_tandang
        total = skor_kandang + skor_tandang
        if margin > 0:
            menang_kandang += 1
        elif margin < 0:
            menang_tandang += 1
        for i, garis in enumerate(spreads):
            if margin + garis > 0:
                hitung_spread[i] += 1
        for i, garis in enumerate(totals):
            if total < garis:
                hitung_under[i] += 1
            elif total > garis:
                hitung_over[i] += 1

    peluang: dict[str, float] = {
        "moneyline_home": menang_kandang / n,
        "moneyline_away": menang_tandang / n,
    }
    for garis, hitung in zip(spreads, hitung_spread, strict=True):
        peluang[f"spread_home_{garis:+g}"] = hitung / n
    for garis, bawah, atas in zip(totals, hitung_under, hitung_over, strict=True):
        peluang[f"total_under_{garis:g}"] = bawah / n
        peluang[f"total_over_{garis:g}"] = atas / n
    return peluang
