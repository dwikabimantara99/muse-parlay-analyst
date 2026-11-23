"""Memilih garis Alt Under Asuransi & Utama dari tangga market (Tahap 3).

Aturan garis (filosofi user 2026-11-23, menggantikan D10 kaku 8/12
poin berbasis spread — kunci config lama min_cushion_points,
min_cushion_points_close_spread, close_spread_threshold, dan
market_cushion_floor_points DIHAPUS di playstyle.yaml versi 13):

- UTAMA: garis terkecil dari tangga yang >= max(median model, garis
  market) + cushion_points, dengan cushion_points BANTALAN ADAPTIF
  dari engine/analis.py (dihitung per laga dari statistik, bukan
  aturan kaku). Bila cushion_points None -> meets=False alasan
  "bantalan_adaptif_tidak_tersedia" (TIDAK ada fallback ke aturan
  lama — aturan lama dihapus). Lalu NAIK TANGGA HARGA: bila
  harga_min_cents diberikan, naik anak tangga sampai
  jup_estimated_cents (fallback price_cents) >= harga_min_cents.
  Garis tipis BOLEH untuk Utama tapi dicatat thin=True (peringatan,
  bukan penghalang).
- ASURANSI: garis terkecil dari tangga yang memenuhi SEMUA syarat:
  (a) garis >= persentil ke-74 distribusi total simulasi 100.000x
  (lewat _p_target — garis pada persentil ke-74 berarti
  P_model(Under pada garis itu) ~= 0,74 menurut distribusi empiris);
  (b) garis DI ATAS garis Utama (garis_di_atas) bila diberikan —
  Asuransi harus lebih tebal dari Utama di laga yang sama;
  lalu naik tangga selama ada syarat gagal: harga jup <
  harga_min_cents (bila diberikan), P_model(garis) <
  insurance_target_probability (0,74 dari config), atau garis TIPIS
  (volume = PENGHALANG KERAS — lewati garis tipis). Bila tidak ada
  anak tangga yang lolos -> meets=False + alasan yang menyebut
  syarat mana yang gagal.

P_model(garis): dari peluang_under (dict garis -> probabilitas,
mis. simulation["markets"]["total_under_{garis}"]) bila diberikan;
bila tidak, interpolasi linear dari persentil (p50/p74/p75/p95)
dengan p_source="interpolasi_persentil" tercatat. Garis di luar
jangkauan persentil -> p None + batas bawah dari jangkar persentil
terdekat (mis. garis di atas p75 berarti P > 0,75 — cukup untuk
memenuhi target 0,74 walau nilai pastinya tidak diketahui).

Volume: _parse_tangga MEMPERTAHANKAN volume_usd + thin tiap baris
(volume None -> thin True). Sebelumnya keduanya dibuang — itu
sebabnya garis tipis lolos diam-diam. v18 (revisi koordinator):
liquidity + bid_cents + ask_cents juga dipertahankan (bukti gate
eksekusi — diteruskan ke kaki artefak).

Fallback p74: bila dict persentil belum memuat p74, modul ini
memakai interpolasi linear antara median (p50) dan p75 pada kuantil
target — didokumentasikan di hasil sebagai
p_target_source="interpolasi_median_p75" (bukan "p74").

Fungsi di sini murni: tanpa I/O, tanpa RNG. Input tidak valid
(tipe salah) -> ValueError. Data hilang (None) -> meets=False dengan
alasan, bukan exception — data hilang adalah keadaan operasional
(DATA_INCOMPLETE), bukan bug pemanggil.
"""

from __future__ import annotations

import math

import config

# Default sementara sampai koordinator menambahkan kunci ini ke
# playstyle.yaml filters.nba_alt_under (keputusan user 2026-11-22).
# JANGAN ubah angka ini tanpa persetujuan user. (Kunci ini SUDAH ada
# di playstyle.yaml versi 13; default hanya untuk cfg minimal di tes.)
DEFAULT_INSURANCE_TARGET_PROBABILITY = 0.74

# Kuantil jangkar yang tersedia di output simulasi (nba_sim.py):
# median = p50, p74, p75, p95. Interpolasi hanya sah di antara jangkar.
_Q_MEDIAN = 0.50
_Q_P74 = 0.74
_Q_P75 = 0.75
_Q_P95 = 0.95

# Nama syarat Asuransi untuk alasan gagal (urutan tetap di pesan).
_SYARAT_HARGA = "harga_minimum"
_SYARAT_PELUANG = "peluang_model"
_SYARAT_VOLUME = "volume_tipis"


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
    ada di config, "default" bila belum ada. Nilai yang ada
    divalidasi (>= 0); nilai tidak valid -> ValueError.
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


def _baca_min_volume(cfg: dict) -> float | None:
    """Lantai volume tipis dari polymarket_ladder.min_volume_usd.

    None bila section/kunci tidak ada (cfg minimal) — thin hanya
    dari flag eksplisit baris tangga atau volume None.
    """
    section = cfg.get("polymarket_ladder", {})
    if not isinstance(section, dict) or "min_volume_usd" not in section:
        return None
    return _validasi_angka(
        section["min_volume_usd"], "polymarket_ladder.min_volume_usd"
    )


def _parse_tangga(ladder, min_volume_usd: float | None = None) -> list[dict]:
    """Normalisasi tangga jadi list {line, price_cents, jup_estimated_cents,
    volume_usd, thin, liquidity, bid_cents, ask_cents}.

    Menerima list angka (garis saja, tanpa harga/volume -> thin True)
    atau list dict bentuk baris tangga Polymarket ({"line",
    "price_cents", "jup_estimated_cents", "volume_usd", "thin",
    "liquidity", "bid_cents", "ask_cents", ...}). Baris malformed ->
    ValueError. Flag "thin" baris DIPERTAHANKAN (dari ingest, yang
    menghitungnya dari volume + bid/ask); bila baris tidak membawa
    flag thin, dihitung dari volume vs min_volume_usd bila tersedia.
    Volume None -> thin True (likuiditas tidak diketahui = tipis).
    liquidity/bid_cents/ask_cents DIPERTAHANKAN (v18, revisi
    koordinator: bukti gate eksekusi — diteruskan ke kaki artefak).
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
                    "volume_usd": None,
                    "thin": True,
                    "liquidity": None,
                    "bid_cents": None,
                    "ask_cents": None,
                }
            )
        elif isinstance(baris, dict):
            volume = _angka_atau_none(
                baris.get("volume_usd"), f"ladder[{i}].volume_usd"
            )
            thin_mentah = baris.get("thin")
            if thin_mentah is not None and not isinstance(thin_mentah, bool):
                raise ValueError(
                    f"ladder[{i}].thin tidak valid: {thin_mentah!r} (harus bool)"
                )
            if volume is None:
                thin = True
            elif thin_mentah is not None:
                thin = thin_mentah
            elif min_volume_usd is not None:
                thin = volume < min_volume_usd
            else:
                thin = False
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
                    "volume_usd": volume,
                    "thin": thin,
                    "liquidity": _angka_atau_none(
                        baris.get("liquidity"), f"ladder[{i}].liquidity"
                    ),
                    "bid_cents": _angka_atau_none(
                        baris.get("bid_cents"), f"ladder[{i}].bid_cents"
                    ),
                    "ask_cents": _angka_atau_none(
                        baris.get("ask_cents"), f"ladder[{i}].ask_cents"
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


def _harga_efektif(baris: dict) -> float | None:
    """Harga jup.ag estimasi (fallback harga Polymarket), atau None."""
    if baris["jup_estimated_cents"] is not None:
        return baris["jup_estimated_cents"]
    return baris["price_cents"]


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


def _jangkar_persentil(percentiles: dict) -> list[tuple[float, float]]:
    """Jangkar (garis, kuantil) dari persentil yang tersedia, urut garis."""
    pasangan = (
        ("median", _Q_MEDIAN),
        ("p74", _Q_P74),
        ("p75", _Q_P75),
        ("p95", _Q_P95),
    )
    jangkar = []
    for nama, kuantil in pasangan:
        nilai = _angka_atau_none(percentiles.get(nama), f"percentiles.{nama}")
        if nilai is not None:
            jangkar.append((nilai, kuantil))
    # Jangkar ganda di garis yang sama: pakai kuantil terbesar (monoton).
    gabung: dict[float, float] = {}
    for garis, kuantil in jangkar:
        gabung[garis] = max(kuantil, gabung.get(garis, 0.0))
    return sorted(gabung.items())


def _validasi_peluang_under(peluang_under) -> dict | None:
    """Validasi dict peluang_under (garis -> probabilitas 0-1)."""
    if peluang_under is None:
        return None
    if not isinstance(peluang_under, dict):
        raise ValueError(
            f"peluang_under harus dict, didapat {type(peluang_under).__name__}"
        )
    bersih: dict[float, float] = {}
    for garis, prob in peluang_under.items():
        garis_f = _validasi_angka(garis, "peluang_under key")
        prob_f = _validasi_angka(prob, f"peluang_under[{garis!r}]")
        if not 0.0 <= prob_f <= 1.0:
            raise ValueError(
                f"peluang_under[{garis!r}] tidak valid: {prob_f} (harus 0-1)"
            )
        bersih[garis_f] = prob_f
    return bersih


def _p_model_pada_garis(
    percentiles: dict, peluang_under: dict | None, garis: float
) -> dict:
    """P_model(Under pada garis): nilai, sumber, dan batas bawah.

    Mengembalikan {"p", "source", "batas_bawah"}:
    - peluang_under memuat garis -> p persis, source "peluang_under".
    - else interpolasi linear antar jangkar persentil (p50/p74/p75/p95)
      bila garis di dalam jangkauan -> source "interpolasi_persentil".
    - else p None, source "di_luar_jangkauan_persentil"; batas_bawah =
      kuantil jangkar terbesar di bawah garis (mis. garis di atas p75
      -> batas_bawah 0,75: P > 0,75 walau nilai pastinya tak diketahui),
      atau None bila tidak ada jangkar di bawah garis.
    """
    if peluang_under is not None and garis in peluang_under:
        p = peluang_under[garis]
        return {"p": p, "source": "peluang_under", "batas_bawah": p}
    jangkar = _jangkar_persentil(percentiles)
    if not jangkar:
        return {"p": None, "source": "di_luar_jangkauan_persentil", "batas_bawah": None}
    if garis < jangkar[0][0]:
        return {"p": None, "source": "di_luar_jangkauan_persentil", "batas_bawah": None}
    if garis > jangkar[-1][0]:
        return {
            "p": None,
            "source": "di_luar_jangkauan_persentil",
            "batas_bawah": jangkar[-1][1],
        }
    for (garis_bawah, q_bawah), (garis_atas, q_atas) in zip(
        jangkar, jangkar[1:], strict=False
    ):
        if garis_bawah <= garis <= garis_atas:
            if garis_atas == garis_bawah:
                p = q_atas
            else:
                fraksi = (garis - garis_bawah) / (garis_atas - garis_bawah)
                p = q_bawah + fraksi * (q_atas - q_bawah)
            p = round(p, 9)
            return {"p": p, "source": "interpolasi_persentil", "batas_bawah": p}
    # Garis tepat di jangkar terakhir (kasus tepi loop di atas).
    return {
        "p": jangkar[-1][1],
        "source": "interpolasi_persentil",
        "batas_bawah": jangkar[-1][1],
    }


def _memenuhi_target_p(p_info: dict, target: float) -> bool:
    """Apakah P_model(garis) memenuhi target (nilai atau batas bawah)?"""
    if p_info["p"] is not None:
        return p_info["p"] >= target
    if p_info["batas_bawah"] is not None:
        return p_info["batas_bawah"] >= target
    return False  # tidak terverifikasi -> fail-closed


def _climb_dari_urut(
    urut: list[dict], dari: dict, ke: dict, alasan: str
) -> dict | None:
    """Dict climb {from_line, to_line, rungs, reason} atau None bila tak naik."""
    if dari["line"] == ke["line"]:
        return None
    indeks = {id(baris): i for i, baris in enumerate(urut)}
    return {
        "from_line": dari["line"],
        "to_line": ke["line"],
        "rungs": indeks[id(ke)] - indeks[id(dari)],
        "reason": alasan,
    }


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
            "volume_usd": None,
            "thin": None,
            "liquidity": None,
            "bid_cents": None,
            "ask_cents": None,
            "climb": None,
            "p_model_pada_garis": None,
            "p_model_source": None,
            "p_model_batas_bawah": None,
        }
    )
    return hasil


def insurance_line(
    percentiles: dict,
    market_line,
    ladder,
    cfg: dict | None = None,
    garis_di_atas=None,
    peluang_under: dict | None = None,
    harga_min_cents=None,
) -> dict:
    """Pilih garis Alt Under Asuransi dari tangga market.

    percentiles: dict persentil total sim {"p74"?, "median", "p75",
    "p95"?} (bentuk dist_total nba_sim.py). market_line: garis total
    market. ladder: tangga Under (list angka atau list dict baris
    Polymarket, termasuk volume_usd + thin). cfg: dict playstyle
    (None = baca playstyle.yaml). garis_di_atas: garis Utama — Asuransi
    harus LEBIH TINGGI dari garis ini (None = tanpa syarat).
    peluang_under: dict garis -> P_model(Under) dari simulasi (None =
    interpolasi dari persentil). harga_min_cents: harga jup minimum
    (None = tanpa syarat harga; pemanggil meneruskan
    analis.harga_min_asuransi_cents dari config).

    Garis terpilih = garis terkecil dari tangga yang >= p74-target DAN
    > garis_di_atas, lalu naik tangga selama ada syarat gagal: harga
    < harga_min_cents, P_model < insurance_target_probability (0,74),
    atau garis tipis (penghalang keras). Bila tidak ada anak tangga
    yang lolos -> meets=False + alasan yang menyebut syarat mana yang
    gagal.
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
    median = _angka_atau_none(percentiles.get("median"), "percentiles.median")
    garis_market = _angka_atau_none(market_line, "market_line")
    atas = _angka_atau_none(garis_di_atas, "garis_di_atas")
    harga_min = _angka_atau_none(harga_min_cents, "harga_min_cents")
    if harga_min is not None and not (0.0 < harga_min <= 100.0):
        raise ValueError(f"harga_min_cents tidak valid: {harga_min} (harus 0-100)")
    peluang_bersih = _validasi_peluang_under(peluang_under)
    min_volume = _baca_min_volume(cfg)
    parsed = _parse_tangga(ladder, min_volume)

    dasar: dict = {
        "target_probability": target,
        "target_probability_source": target_source,
        "median": median,
        "market_line": garis_market,
        "p_target": None,
        "p_target_source": None,
        "required_line": None,
        "garis_di_atas": atas,
        "harga_min_cents": harga_min,
        "min_volume_usd": min_volume,
    }
    if garis_market is None:
        return _hasil_tidak_memenuhi("garis_market_tidak_ada", dasar)
    p_target, p_source, alasan = _p_target(percentiles, target)
    if alasan is not None:
        return _hasil_tidak_memenuhi(alasan, dasar)
    assert p_target is not None
    required = round(p_target, 9)
    dasar.update(
        {
            "p_target": round(p_target, 9),
            "p_target_source": p_source,
            "required_line": required,
        }
    )
    if not parsed:
        return _hasil_tidak_memenuhi("tangga_kosong", dasar)
    urut = sorted(parsed, key=lambda baris: baris["line"])
    kandidat = [
        baris
        for baris in urut
        if baris["line"] >= required and (atas is None or baris["line"] > atas)
    ]
    if not kandidat:
        return _hasil_tidak_memenuhi("tidak_ada_garis_memenuhi", dasar)

    gagal_kondisi: set[str] = set()
    pilihan = None
    p_terpilih = None
    rungs_dicoba = len(kandidat)
    for idx, baris in enumerate(kandidat):
        gagal: list[str] = []
        harga = _harga_efektif(baris)
        if harga_min is not None and (harga is None or harga < harga_min):
            gagal.append(_SYARAT_HARGA)
        p_info = _p_model_pada_garis(percentiles, peluang_bersih, baris["line"])
        if not _memenuhi_target_p(p_info, target):
            gagal.append(_SYARAT_PELUANG)
        if baris["thin"]:
            gagal.append(_SYARAT_VOLUME)
        if not gagal:
            pilihan = baris
            p_terpilih = p_info
            rungs_dicoba = idx + 1
            break
        gagal_kondisi.update(gagal)
    if pilihan is None or p_terpilih is None:
        urutan = [_SYARAT_HARGA, _SYARAT_PELUANG, _SYARAT_VOLUME]
        gagal_nama = [nama for nama in urutan if nama in gagal_kondisi]
        dasar["syarat_gagal"] = gagal_nama
        dasar["rungs_dicoba"] = rungs_dicoba
        return _hasil_tidak_memenuhi(
            "tidak_ada_garis_lolos: " + ", ".join(gagal_nama), dasar
        )

    garis = pilihan["line"]
    alasan_naik = "+".join(
        nama
        for nama in [_SYARAT_HARGA, _SYARAT_PELUANG, _SYARAT_VOLUME]
        if nama in gagal_kondisi
    )
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
            "volume_usd": pilihan["volume_usd"],
            "thin": pilihan["thin"],
            "liquidity": pilihan["liquidity"],
            "bid_cents": pilihan["bid_cents"],
            "ask_cents": pilihan["ask_cents"],
            "climb": _climb_dari_urut(urut, kandidat[0], pilihan, alasan_naik),
            "p_model_pada_garis": p_terpilih["p"],
            "p_model_source": p_terpilih["source"],
            "p_model_batas_bawah": p_terpilih["batas_bawah"],
            "syarat_gagal": [],
            "rungs_dicoba": rungs_dicoba,
        }
    )
    return dasar


def utama_line(
    percentiles: dict,
    market_line,
    ladder,
    cfg: dict | None = None,
    cushion_points=None,
    peluang_under: dict | None = None,
    harga_min_cents=None,
) -> dict:
    """Pilih garis Alt Under Utama dari tangga market (bantalan adaptif).

    percentiles: dict persentil total sim (dipakai "median" + jangkar
    untuk P_model). market_line: garis total market. ladder: tangga
    Under. cfg: dict playstyle (None = baca playstyle.yaml).
    cushion_points: bantalan adaptif dari engine/analis.py
    (bantalan_adaptif); None -> meets=False alasan
    "bantalan_adaptif_tidak_tersedia" (TIDAK ada fallback ke aturan
    lama — aturan 8/12 berbasis spread dihapus). peluang_under: dict
    garis -> P_model(Under) untuk pelaporan (None = interpolasi dari
    persentil). harga_min_cents: harga jup minimum — naik tangga dari
    garis bantalan sampai harga >= minimum (None = tanpa syarat
    harga; pemanggil meneruskan analis.harga_min_utama_cents dari
    config).

    Garis terpilih = garis terkecil dari tangga yang >= max(median,
    garis market) + cushion_points, lalu naik tangga harga bila perlu.
    Garis tipis BOLEH untuk Utama tapi dicatat thin=True (peringatan,
    bukan penghalang).
    """
    cfg = cfg if cfg is not None else config.load_playstyle()
    if not isinstance(percentiles, dict):
        raise ValueError(
            f"percentiles harus dict, didapat {type(percentiles).__name__}"
        )
    median = _angka_atau_none(percentiles.get("median"), "percentiles.median")
    garis_market = _angka_atau_none(market_line, "market_line")
    bantalan = _angka_atau_none(cushion_points, "cushion_points")
    if bantalan is not None and bantalan < 0:
        raise ValueError(f"cushion_points tidak valid: {bantalan} (harus >= 0)")
    harga_min = _angka_atau_none(harga_min_cents, "harga_min_cents")
    if harga_min is not None and not (0.0 < harga_min <= 100.0):
        raise ValueError(f"harga_min_cents tidak valid: {harga_min} (harus 0-100)")
    peluang_bersih = _validasi_peluang_under(peluang_under)
    min_volume = _baca_min_volume(cfg)
    parsed = _parse_tangga(ladder, min_volume)

    dasar: dict = {
        "median": median,
        "market_line": garis_market,
        "cushion_points": bantalan,
        "harga_min_cents": harga_min,
        "min_volume_usd": min_volume,
        "base_line": None,
        "required_line": None,
    }
    if bantalan is None:
        return _hasil_tidak_memenuhi("bantalan_adaptif_tidak_tersedia", dasar)
    if median is None:
        return _hasil_tidak_memenuhi("median_tidak_ada", dasar)
    if garis_market is None:
        return _hasil_tidak_memenuhi("garis_market_tidak_ada", dasar)
    base = max(median, garis_market)
    required = round(base + bantalan, 9)
    dasar.update({"base_line": base, "required_line": required})
    if not parsed:
        return _hasil_tidak_memenuhi("tangga_kosong", dasar)
    urut = sorted(parsed, key=lambda baris: baris["line"])
    garis_bantalan = _pilih_garis_terkecil(urut, required)
    if garis_bantalan is None:
        return _hasil_tidak_memenuhi("tidak_ada_garis_memenuhi", dasar)

    pilihan = garis_bantalan
    if harga_min is not None:
        for baris in urut:
            if baris["line"] < garis_bantalan["line"]:
                continue
            harga = _harga_efektif(baris)
            if harga is not None and harga >= harga_min:
                pilihan = baris
                break
        else:
            dasar["garis_bantalan"] = garis_bantalan["line"]
            return _hasil_tidak_memenuhi("harga_minimum_tidak_tercapai", dasar)

    garis = pilihan["line"]
    p_info = _p_model_pada_garis(percentiles, peluang_bersih, garis)
    dasar.update(
        {
            "line": garis,
            "meets": True,
            "reason": None,
            "price_cents": pilihan["price_cents"],
            "jup_estimated_cents": pilihan["jup_estimated_cents"],
            "cushion_vs_market_points": round(garis - garis_market, 9),
            "cushion_vs_median_points": round(garis - median, 9),
            "volume_usd": pilihan["volume_usd"],
            "thin": pilihan["thin"],
            "liquidity": pilihan["liquidity"],
            "bid_cents": pilihan["bid_cents"],
            "ask_cents": pilihan["ask_cents"],
            "climb": _climb_dari_urut(urut, garis_bantalan, pilihan, _SYARAT_HARGA),
            "p_model_pada_garis": p_info["p"],
            "p_model_source": p_info["source"],
            "p_model_batas_bawah": p_info["batas_bawah"],
        }
    )
    return dasar
