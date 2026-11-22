"""Kalibrasi model: reliability buckets, Brier score, ringkasan kalibrasi.

Fungsi di sini MURNI: tanpa config, tanpa I/O, tanpa RNG. Dipakai oleh
scripts/validate_nba_model.py untuk menilai apakah peluang yang
dikeluarkan engine.nba_sim terkalibrasi — apakah event yang diprediksi
75% benar-benar terjadi ~75% dari waktu.

Definisi:

- ``reliability_buckets``: pasangan (p_prediksi, terjadi) dikelompokkan
  ke n_buckets selang peluang sama lebar ([0, 0.1), [0.1, 0.2), ...,
  [0.9, 1.0]; p = 1.0 masuk bucket terakhir). Bucket KOSONG tetap
  dicatat dengan n=0 dan mean/frekuensi None — tidak dihilangkan
  diam-diam, karena bucket kosong adalah informasi (model tidak pernah
  mengeluarkan peluang di selang itu).
- ``brier_score``: rata-rata (p_prediksi - terjadi)^2. 0 = sempurna;
  0,25 = tebakan 50% terus-menerus. Lebih kecil lebih baik.
- ``calibration_summary``: gabungan keduanya + n, mean prediksi, dan
  frekuensi aktual keseluruhan.

Semua input peluang divalidasi 0-1; di luar itu ValueError.
"""

from __future__ import annotations


def _validasi_pairs(pairs: list[tuple[float, bool]]) -> list[tuple[float, bool]]:
    """Validasi + normalisasi daftar pasangan (p_prediksi, terjadi).

    p harus angka (bukan bool) berhingga dalam [0, 1]; terjadi harus
    bool atau 0/1. Mengembalikan daftar ternormalisasi
    [(float, bool), ...]. Raise ValueError bila kosong/tidak valid.
    """
    if not isinstance(pairs, (list, tuple)) or len(pairs) == 0:
        raise ValueError("pairs harus daftar (p_prediksi, terjadi) tidak kosong")
    hasil: list[tuple[float, bool]] = []
    for item in pairs:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(f"pasangan tidak valid (harus (p, terjadi)): {item!r}")
        p_prediksi, terjadi = item
        if (
            isinstance(p_prediksi, bool)
            or not isinstance(p_prediksi, (int, float))
            or p_prediksi != p_prediksi  # NaN
            or p_prediksi in (float("inf"), float("-inf"))
            or not 0.0 <= float(p_prediksi) <= 1.0
        ):
            raise ValueError(f"p_prediksi harus angka dalam [0, 1]: {p_prediksi!r}")
        if isinstance(terjadi, bool):
            terjadi_bool = terjadi
        elif terjadi in (0, 1) and isinstance(terjadi, int):
            terjadi_bool = bool(terjadi)
        else:
            raise ValueError(f"terjadi harus bool atau 0/1: {terjadi!r}")
        hasil.append((float(p_prediksi), terjadi_bool))
    return hasil


def reliability_buckets(
    pairs: list[tuple[float, bool]], n_buckets: int = 10
) -> list[dict]:
    """Kelompokkan pasangan (p_prediksi, terjadi) ke bucket peluang.

    pairs: daftar (p_prediksi, terjadi_bool). n_buckets: jumlah selang
    sama lebar yang membagi [0, 1] (default 10).
    Mengembalikan list dict per bucket, urut dari peluang terendah:
    {"bucket": (lo, hi), "n", "mean_prediksi", "frekuensi_aktual"}.
    Bucket kosong: n=0, mean_prediksi dan frekuensi_aktual None.
    """
    data = _validasi_pairs(pairs)
    if isinstance(n_buckets, bool) or not isinstance(n_buckets, int) or n_buckets < 1:
        raise ValueError(f"n_buckets harus integer >= 1: {n_buckets!r}")
    jumlah = [0] * n_buckets
    jumlah_p = [0.0] * n_buckets
    jumlah_terjadi = [0] * n_buckets
    for p_prediksi, terjadi in data:
        indeks = min(int(p_prediksi * n_buckets), n_buckets - 1)
        jumlah[indeks] += 1
        jumlah_p[indeks] += p_prediksi
        if terjadi:
            jumlah_terjadi[indeks] += 1
    hasil: list[dict] = []
    for i in range(n_buckets):
        n = jumlah[i]
        hasil.append(
            {
                "bucket": (round(i / n_buckets, 6), round((i + 1) / n_buckets, 6)),
                "n": n,
                "mean_prediksi": (jumlah_p[i] / n) if n > 0 else None,
                "frekuensi_aktual": (jumlah_terjadi[i] / n) if n > 0 else None,
            }
        )
    return hasil


def brier_score(pairs: list[tuple[float, bool]]) -> float:
    """Brier score: rata-rata (p_prediksi - terjadi)^2. Lebih kecil lebih baik.

    0 = prediksi sempurna; 0,25 = peluang 50% terus-menerus.
    """
    data = _validasi_pairs(pairs)
    total = sum((p - (1.0 if terjadi else 0.0)) ** 2 for p, terjadi in data)
    return total / len(data)


def calibration_summary(pairs: list[tuple[float, bool]], n_buckets: int = 10) -> dict:
    """Ringkasan kalibrasi satu event.

    Mengembalikan {"n", "mean_prediksi", "frekuensi_aktual", "brier",
    "buckets": [...]} — buckets dari reliability_buckets.
    Model terkalibrasi bila mean_prediksi ~= frekuensi_aktual secara
    keseluruhan DAN di tiap bucket (mean_prediksi ~= frekuensi_aktual).
    """
    data = _validasi_pairs(pairs)
    n = len(data)
    return {
        "n": n,
        "mean_prediksi": sum(p for p, _ in data) / n,
        "frekuensi_aktual": sum(1 for _, terjadi in data if terjadi) / n,
        "brier": brier_score(data),
        "buckets": reliability_buckets(data, n_buckets=n_buckets),
    }
