"""Memilih garis Alt Under Asuransi & Utama dari tangga market (Tahap 3).

Aturan garis (keputusan user 2026-11-22, DECISIONS.md "Patch langkah 1b
disetujui + bantalan Asuransi dari target peluang"):

- ASURANSI: garis terkecil dari tangga market yang memenuhi DUA syarat:
  (a) garis >= persentil ke-74 distribusi total simulasi 100.000x —
  garis pada persentil ke-74 berarti P_model(Under pada garis itu)
  ~= 0,74 menurut distribusi empiris (BUKAN rumus analitik terpisah);
  DAN (b) garis >= garis market + market_cushion_floor_points (8) —
  lantai "batas bawah bandar". Bila tidak ada garis tangga yang
  memenuhi keduanya, kaki TIDAK memenuhi syarat Asuransi (meets=False
  + alasan) — jangan dipaksakan ke garis lain.
- UTAMA: garis terkecil dari tangga yang >= max(median model, garis
  market) + bantalan, dengan bantalan 8 (atau 12 bila spread <= 2,5)
  — aturan D10 yang sudah ada (playstyle.yaml filters.nba_alt_under).

Fallback p74: pekerja lain sedang menambahkan p74 ke output simulasi
(nba_sim.py) secara paralel. Bila dict persentil belum memuat p74,
modul ini memakai interpolasi linear antara median (p50) dan p75 pada
kuantil target — didokumentasikan di hasil sebagai
p_target_source="interpolasi_median_p75" (bukan "p74"). Koordinator
memverifikasi saat integrasi; begitu p74 tersedia, nilai persentil
asli yang dipakai (tanpa interpolasi).

Parameter baru (LAPORKAN ke koordinator — BELUM ada di playstyle.yaml,
modul ini memakai nilai default yang disetujui user sampai koordinator
menambahkannya ke filters.nba_alt_under):
  insurance_target_probability = 0,74
  market_cushion_floor_points = 8
Nilai default ini BUKAN ambang karangan: keduanya adalah keputusan
user 2026-11-22. Bila kunci sudah ada di config, nilai config yang
dipakai (dan divalidasi); bila belum ada, default di atas yang dipakai
+ dicatat di hasil ("*_source": "default").

Fungsi di sini murni: tanpa I/O, tanpa RNG. Input tidak valid
(tipe salah) -> ValueError. Data hilang (None) -> meets=False dengan
alasan, bukan exception — data hilang adalah keadaan operasional
(DATA_INCOMPLETE), bukan bug pemanggil.
"""

from __future__ import annotations

import math

import config

# Default sementara sampai koordinator menambahkan kedua kunci ini ke
# playstyle.yaml filters.nba_alt_under (keputusan user 2026-11-22).
# JANGAN ubah angka ini tanpa persetujuan user.
DEFAULT_INSURANCE_TARGET_PROBABILITY = 0.74
DEFAULT_MARKET_CUSHION_FLOOR_POINTS = 8.0

# Kuantil jangkar yang tersedia di output simulasi (nba_sim.py):
# median = p50, p75. Interpolasi hanya sah di antara keduanya.
_Q_MEDIAN = 0.50
_Q_P75 = 0.75
_Q_P74 = 0.74


def _validasi_angka(nilai, nama: str) -> float:
    """Pastikan nilai adalah angka hingga (bukan bool)."""
    if (
        isinstance(nilai, bool)
        or not isinstance(nilai, (int, float))
        or not math.isfinite(nilai)
    ):
        raise ValueError(f"{nama} tidak valid: {nilai!r} (harus angka hingga)")
    return float(nilai)


def _angka_atau_none(nilai, nama: str) -> float | None:
    """Angka hingga, atau None bila nilai None (data hilang)."""
    if nilai is None:
        return None
    return _validasi_angka(nilai, nama)


def _baca_param_baru(cfg: dict, kunci: str, default: float) -> tuple[float, str]:
    """Baca parameter bantalan baru dari filters.nba_alt_under.

    Mengembalikan (nilai, sumber) dengan sumber "config" bila kunci
    ada di config, "default" bila belum ada (koordinator belum
    menambahkan). Nilai yang ada divalidasi (>= 0); nilai tidak valid
    -> ValueError.
    """
    section = cfg.get("filters", {}).get("nba_alt_under", {})
    if not isinstance(section, dict) or kunci not in section:
        return default, "default"
    nilai = section[kunci]
    if (
        isinstance(nilai, bool)
        or not isinstance(nilai, (int, float))
        or not math.isfinite(nilai)
        or nilai < 0
    ):
        raise ValueError(
            f"filters.nba_alt_under.{kunci} tidak valid: {nilai!r} "
            "(harus angka hingga >= 0)"
        )
    return float(nilai), "config"


def _parse_tangga(ladder) -> list[dict]:
    """Normalisasi tangga jadi list {line, price_cents, jup_estimated_cents}.

    Menerima list angka (garis saja, tanpa harga) atau list dict
    bentuk baris tangga Polymarket ({"line", "price_cents",
    "jup_estimated_cents", ...}). Baris malformed -> ValueError.
    """
    if not isinstance(ladder, (list, tuple)):
        raise ValueError(f"ladder harus list, didapat {type(ladder).__name__}")
    parsed = []
    for i, baris in enumerate(ladder):
        if isinstance(baris, (int, float)):
            # bool ikut masuk (subclass int) tapi ditolak _validasi_angka.
            parsed.append(
                {
                    "line": _validasi_angka(baris, f"ladder[{i}]"),
                    "price_cents": None,
                    "jup_estimated_cents": None,
                }
            )
        elif isinstance(baris, dict):
            parsed.append(
                {
                    "line": _validasi_angka(baris.get("line"), f"ladder[{i}].line"),
                    "price_cents": _angka_atau_none(
                        baris.get("price_cents"), f"ladder[{i}].price_cents"
                    ),
                    "jup_estimated_cents": _angka_atau_none(
                        baris.get("jup_estimated_cents"),
                        f"ladder[{i}].jup_estimated_cents",
                    ),
                }
            )
        else:
            raise ValueError(
                f"ladder[{i}] tidak valid: {baris!r} (harus angka atau dict)"
            )
    return parsed


def _pilih_garis_terkecil(parsed: list[dict], required: float) -> dict | None:
    """Baris tangga dengan garis terkecil yang >= required (atau None)."""
    kandidat = [baris for baris in parsed if baris["line"] >= required]
    if not kandidat:
        return None
    return min(kandidat, key=lambda baris: baris["line"])


def _p_target(
    percentiles: dict, target: float
) -> tuple[float | None, str | None, str | None]:
    """Nilai persentil total pada kuantil target.

    Mengembalikan (nilai, sumber, alasan_gagal). Sumber "p74" bila
    p74 tersedia dan target == 0,74; "interpolasi_median_p75" bila
    dihitung dari median + p75. Gagal -> (None, None, alasan).
    """
    if not isinstance(percentiles, dict):
        raise ValueError(
            f"percentiles harus dict, didapat {type(percentiles).__name__}"
        )
    p74 = _angka_atau_none(percentiles.get("p74"), "percentiles.p74")
    if target == _Q_P74 and p74 is not None:
        return p74, "p74", None
    median = _angka_atau_none(percentiles.get("median"), "percentiles.median")
    p75 = _angka_atau_none(percentiles.get("p75"), "percentiles.p75")
    if median is None or p75 is None:
        return None, None, "persentil_tidak_lengkap"
    if not (_Q_MEDIAN <= target <= _Q_P75):
        return None, None, "target_di_luar_jangkauan_persentil"
    # Interpolasi linear antara (p50, median) dan (p75, p75).
    fraksi = (target - _Q_MEDIAN) / (_Q_P75 - _Q_MEDIAN)
    return median + fraksi * (p75 - median), "interpolasi_median_p75", None


def _hasil_tidak_memenuhi(alasan: str, dasar: dict) -> dict:
    """Hasil meets=False dengan alasan + semua field diagnosis."""
    hasil = dict(dasar)
    hasil.update(
        {
            "line": None,
            "meets": False,
            "reason": alasan,
            "price_cents": None,
            "jup_estimated_cents": None,
            "cushion_vs_market_points": None,
            "cushion_vs_median_points": None,
        }
    )
    return hasil


def insurance_line(
    percentiles: dict,
    market_line,
    ladder,
    cfg: dict | None = None,
) -> dict:
    """Pilih garis Alt Under Asuransi dari tangga market.

    percentiles: dict persentil total sim {"p74"?, "median", "p75"}
    (bentuk dist_total nba_sim.py). market_line: garis total market.
    ladder: tangga Under (list angka atau list dict baris Polymarket).
    cfg: dict playstyle (None = baca playstyle.yaml).

    Garis terpilih = garis terkecil dari tangga yang >= max(p_target,
    market_line + market_cushion_floor_points). Bila tidak ada garis
    yang memenuhi -> meets=False + alasan (kaki tidak memenuhi syarat
    Asuransi). Harga garis terpilih dilaporkan bila tangga membawanya.
    """
    cfg = cfg if cfg is not None else config.load_playstyle()
    if not isinstance(percentiles, dict):
        raise ValueError(
            f"percentiles harus dict, didapat {type(percentiles).__name__}"
        )
    target, target_source = _baca_param_baru(
        cfg, "insurance_target_probability", DEFAULT_INSURANCE_TARGET_PROBABILITY
    )
    if not (0.0 < target < 1.0):
        raise ValueError(
            "insurance_target_probability tidak valid: "
            f"{target!r} (harus di antara 0 dan 1)"
        )
    floor, floor_source = _baca_param_baru(
        cfg, "market_cushion_floor_points", DEFAULT_MARKET_CUSHION_FLOOR_POINTS
    )
    median = _angka_atau_none(percentiles.get("median"), "percentiles.median")
    garis_market = _angka_atau_none(market_line, "market_line")
    parsed = _parse_tangga(ladder)

    dasar: dict = {
        "target_probability": target,
        "target_probability_source": target_source,
        "market_cushion_floor_points": floor,
        "market_cushion_floor_source": floor_source,
        "median": median,
        "market_line": garis_market,
        "p_target": None,
        "p_target_source": None,
        "market_floor": None,
        "required_line": None,
    }
    if garis_market is None:
        return _hasil_tidak_memenuhi("garis_market_tidak_ada", dasar)
    p_target, p_source, alasan = _p_target(percentiles, target)
    if alasan is not None:
        return _hasil_tidak_memenuhi(alasan, dasar)
    assert p_target is not None
    market_floor = round(garis_market + floor, 9)
    required = round(max(p_target, market_floor), 9)
    dasar.update(
        {
            "p_target": round(p_target, 9),
            "p_target_source": p_source,
            "market_floor": market_floor,
            "required_line": required,
        }
    )
    if not parsed:
        return _hasil_tidak_memenuhi("tangga_kosong", dasar)
    pilihan = _pilih_garis_terkecil(parsed, required)
    if pilihan is None:
        return _hasil_tidak_memenuhi("tidak_ada_garis_memenuhi", dasar)
    garis = pilihan["line"]
    dasar.update(
        {
            "line": garis,
            "meets": True,
            "reason": None,
            "price_cents": pilihan["price_cents"],
            "jup_estimated_cents": pilihan["jup_estimated_cents"],
            "cushion_vs_market_points": round(garis - garis_market, 9),
            "cushion_vs_median_points": (
                round(garis - median, 9) if median is not None else None
            ),
        }
    )
    return dasar


def utama_line(
    percentiles: dict,
    market_line,
    ladder,
    spread=None,
    cfg: dict | None = None,
) -> dict:
    """Pilih garis Alt Under Utama dari tangga market (aturan D10).

    percentiles: dict persentil total sim (dipakai "median").
    market_line: garis total market. ladder: tangga Under.
    spread: spread absolut laga (|spread pasar|); None = tidak
    diketahui -> bantalan 8 (bukan 12 — aturan +12 hanya bila
    terbukti spread <= 2,5; lihat catatan di bawah).
    cfg: dict playstyle (None = baca playstyle.yaml).

    Garis terpilih = garis terkecil dari tangga yang >= max(median,
    garis market) + bantalan, bantalan 12 bila spread <= 2,5 else 8
    (filters.nba_alt_under.min_cushion_points[_close_spread] +
    close_spread_threshold — kunci yang sudah ada di playstyle.yaml).

    CATATAN spread None: memakai bantalan 8 saat spread tidak
    diketahui adalah pilihan yang didokumentasikan di sini, bukan
    fail-closed yang sempurna — bila spread ternyata rapat (<= 2,5),
    bantalan seharusnya 12. Pemanggil yang tidak tahu spread harus
    sadar akan hal ini; bila ragu, kirim spread-nya.
    """
    cfg = cfg if cfg is not None else config.load_playstyle()
    bantalan_biasa = _validasi_angka(
        config.get_value(cfg, "filters", "nba_alt_under", "min_cushion_points"),
        "filters.nba_alt_under.min_cushion_points",
    )
    bantalan_rapat = _validasi_angka(
        config.get_value(
            cfg, "filters", "nba_alt_under", "min_cushion_points_close_spread"
        ),
        "filters.nba_alt_under.min_cushion_points_close_spread",
    )
    ambang_spread = _validasi_angka(
        config.get_value(cfg, "filters", "nba_alt_under", "close_spread_threshold"),
        "filters.nba_alt_under.close_spread_threshold",
    )
    if not isinstance(percentiles, dict):
        raise ValueError(
            f"percentiles harus dict, didapat {type(percentiles).__name__}"
        )
    median = _angka_atau_none(percentiles.get("median"), "percentiles.median")
    garis_market = _angka_atau_none(market_line, "market_line")
    spread_abs = None
    if spread is not None:
        spread_abs = abs(_validasi_angka(spread, "spread"))
    parsed = _parse_tangga(ladder)

    bantalan = (
        bantalan_rapat
        if spread_abs is not None and spread_abs <= ambang_spread
        else bantalan_biasa
    )
    dasar: dict = {
        "median": median,
        "market_line": garis_market,
        "spread": spread_abs,
        "cushion_points": bantalan,
        "base_line": None,
        "required_line": None,
    }
    if median is None:
        return _hasil_tidak_memenuhi("median_tidak_ada", dasar)
    if garis_market is None:
        return _hasil_tidak_memenuhi("garis_market_tidak_ada", dasar)
    base = max(median, garis_market)
    required = round(base + bantalan, 9)
    dasar.update({"base_line": base, "required_line": required})
    if not parsed:
        return _hasil_tidak_memenuhi("tangga_kosong", dasar)
    pilihan = _pilih_garis_terkecil(parsed, required)
    if pilihan is None:
        return _hasil_tidak_memenuhi("tidak_ada_garis_memenuhi", dasar)
    garis = pilihan["line"]
    dasar.update(
        {
            "line": garis,
            "meets": True,
            "reason": None,
            "price_cents": pilihan["price_cents"],
            "jup_estimated_cents": pilihan["jup_estimated_cents"],
            "cushion_vs_market_points": round(garis - garis_market, 9),
            "cushion_vs_median_points": round(garis - median, 9),
        }
    )
    return dasar
