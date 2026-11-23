"""Skip dari awal (keputusan user 2026-11-23 10:22 + 10:41 WIB).

Prinsip user: lebih baik MENGHINDARI laga seperti Denver daripada
mencari garis yang tahan. Laga yang dari awal sudah tidak masuk akal
(perhitungannya anomali / tidak normal) atau punya potensi masuk
overtime di-SKIP dari KEDUA tiket — bukan dipaksakan dengan garis
yang lebih tinggi. Pertahanan utama terhadap laga anomali adalah
SELEKSI, bukan harga/garis (bukti: total akhir DEN@CHI 296 menjebol
bahkan garis tahan-banjir 264,5 @94¢).

Tiga pemicu (SATU pemicu positif cukup untuk skip):
(a) tidak_ada_equilibrium — equilibrium TIDAK ADA di KEDUA tiket
    (dihitung sungguh-sungguh, bukan gagal hitung). Bila satu tiket
    punya equilibrium, laga itu masih punya kaki yang masuk akal —
    tidak skip via (a). Keputusan desain (menunggu keberatan).
(b) pola_denver — KONJUNGSI 4 syarat, semua harus benar (definisi
    eksplisit — bukan perasaan):
    (1) flag_setan pada garis acuan: P normal >= target Asuransi
        tapi P setan < target (kaki lolos normal, jebol di deviasi
        maksimal — pola DEN@CHI);
    (2) tidak ada garis TIDAK-TIPIS yang tahan banjir pada target
        Asuransi ("rapuh banjir di semua garis wajar" — garis wajar
        = garis yang bisa dibeli, yaitu tidak thin);
    (3) garis acuan thin ("volume tipis" pada garis wajar laga itu);
    (4) edge kecil pada garis acuan: edge implied (p_final − harga
        venue) < skip_awal.pola_denver.edge_kecil_pct (INITIAL 3,5 —
        cermin proposal D12).
    "Volume tipis" juga terkandung di (2): garis tahan-banjir yang
    ada semuanya thin berarti garis yang selamat tidak bisa dibeli.
    Garis acuan = garis tangga Under terendah dengan P normal >=
    target Asuransi (engine/equilibrium.cari_garis_acuan) — pada
    tangga monoton naik, ini sekaligus garis termurah.
(c) ot_tinggi — potensi OT tinggi: ot_probability sim >=
    ot_seleksi.skip_ot_prob (INITIAL 0,028). KEPUTUSAN: SKIP (bukan
    bantalan lebih besar) — OT menambah loncatan diskret ~20+ poin
    yang SUDAH dimodelkan sim dalam distribusi total; risiko sisa
    adalah model MEREMEHKAN OT (nilai sim 1,7–2,9% vs laju OT
    historis NBA ~5–6%), yang tidak bisa diperbaiki oleh bantalan
    yang dihitung dari model yang sama. Ambang 0,028 ≈ plafon
    teoretis peluang seri laga imbang di bawah sigma_margin hasil
    fit (1/(14,4307·√(2π)) ≈ 0,0277) — hanya laga yang praktis
    imbang yang kena skip. KEJUJURAN: DEN@CHI (yang benar-benar OT)
    punya ot_prob sim hanya 2,36%/2,13% — TIDAK kena aturan ini;
    Denver ditangkap pola_denver, bukan aturan OT.

TANPA DATA -> "tidak dievaluasi", BUKAN skip: skip adalah klaim
positif soal laga, bukan default saat data hilang. Bila CDF/tangga/
jangkar tidak ada, pola_denver + equilibrium tidak bisa dinilai
(alasan tercatat); gate per kaki tetap fail-closed seperti
sebelumnya (komposer yang menolak kaki tanpa data).

Modul ini MURNI HITUNG: tanpa fetch, tanpa simulasi ulang, tanpa
Odds API. Satu-satunya I/O adalah baca config bila argumen cfg None.
"""

from __future__ import annotations

import math

import config as config_mod
from engine import equilibrium as equilibrium_mod

# Nama pemicu (token stabil untuk laporan + JSON ukur).
PEMICU_TIDAK_ADA_EQUILIBRIUM = "tidak_ada_equilibrium"
PEMICU_POLA_DENVER = "pola_denver"
PEMICU_OT_TINGGI = "ot_tinggi"


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


def baca_ot_probability(analysis: dict) -> float | None:
    """Peluang OT sim satu laga (None bila tidak ada di artefak).

    Lokasi kanonik: simulation.score_distribution.ot_probability
    (ditulis engine/nba_sim.py). Fallback: simulation.ot_probability
    (varian artefak lama) — bila keduanya ada, yang kanonik menang.
    """
    sim = analysis.get("simulation")
    if not isinstance(sim, dict):
        return None
    dist = sim.get("score_distribution")
    if isinstance(dist, dict):
        nilai = _angka(dist.get("ot_probability"))
        if nilai is not None and 0.0 <= nilai <= 1.0:
            return nilai
    nilai = _angka(sim.get("ot_probability"))
    if nilai is not None and 0.0 <= nilai <= 1.0:
        return nilai
    return None


def potensi_ot_tinggi(
    analysis: dict, cfg: dict | None = None
) -> tuple[bool | None, float | None, float]:
    """Apakah potensi OT laga ini tinggi? -> (tinggi, ot_prob, ambang).

    ``tinggi`` None bila ot_probability tidak ada di artefak (tidak
    bisa dinilai — bukan bukti aman). Ambang dari
    ot_seleksi.skip_ot_prob (ConfigError bila kunci hilang).
    """
    cfg = _muat_cfg(cfg)
    ambang = config_mod.get_value(cfg, "ot_seleksi", "skip_ot_prob")
    ambang_f = _angka(ambang)
    if ambang_f is None or not 0.0 <= ambang_f <= 1.0:
        raise config_mod.ConfigError(
            f"playstyle.yaml ot_seleksi.skip_ot_prob tidak valid: {ambang!r}"
        )
    ot = baca_ot_probability(analysis)
    if ot is None:
        return None, None, ambang_f
    return ot >= ambang_f, ot, ambang_f


def _evaluasi_pola_denver(analysis: dict, cfg: dict, ktx: dict | None = None) -> dict:
    """Evaluasi keempat syarat pola Denver (konjungsi).

    Mengembalikan {"dievaluasi", "cocok", "alasan", "syarat": {...},
    "garis_acuan": {...}} — "syarat" memuat nilai tiap syarat +
    angka mentahnya supaya keputusan bisa diaudit per syarat.
    "dievaluasi" False bila garis acuan tidak bisa dihitung atau
    edge tidak bisa dinilai (tanpa jangkar pasar).
    """
    edge_kecil_pct = config_mod.get_value(
        cfg, "skip_awal", "pola_denver", "edge_kecil_pct"
    )
    edge_kecil = _angka(edge_kecil_pct)
    if edge_kecil is None:
        raise config_mod.ConfigError(
            "playstyle.yaml skip_awal.pola_denver.edge_kecil_pct "
            f"tidak valid: {edge_kecil_pct!r}"
        )
    ambang_edge = edge_kecil / 100.0
    acuan = equilibrium_mod.cari_garis_acuan(analysis, cfg, ktx=ktx)
    hasil = {
        "dievaluasi": False,
        "cocok": False,
        "alasan": None,
        "syarat": {
            "flag_setan": None,
            "tidak_ada_tahan_banjir_nonthin": None,
            "garis_acuan_thin": None,
            "edge_kecil": None,
        },
        "ambang_edge": ambang_edge,
        "garis_acuan": acuan,
    }
    if not acuan.get("dihitung"):
        hasil["alasan"] = (
            "pola Denver tidak bisa dinilai: garis acuan tidak bisa "
            f"dihitung ({acuan.get('alasan') or 'tanpa alasan'})"
        )
        return hasil
    if acuan.get("edge") is None:
        hasil["alasan"] = (
            "pola Denver tidak bisa dinilai: edge garis acuan tidak "
            "bisa dihitung (tanpa jangkar pasar)"
        )
        return hasil
    syarat = {
        "flag_setan": bool(acuan.get("flag_setan")),
        "tidak_ada_tahan_banjir_nonthin": not acuan.get("ada_tahan_banjir_nonthin"),
        "garis_acuan_thin": acuan.get("thin") is True,
        "edge_kecil": acuan["edge"] < ambang_edge,
    }
    hasil["syarat"] = syarat
    hasil["dievaluasi"] = True
    hasil["cocok"] = all(syarat.values())
    if hasil["cocok"]:
        tahan = acuan.get("garis_tahan_banjir") or {}
        teks_tahan = ""
        if tahan.get("line") is not None:
            teks_tahan = (
                f"; garis tahan-banjir U{tahan['line']:g} "
                f"{'tipis' if tahan.get('thin') else 'tidak ditemukan yang tebal'}"
            )
        hasil["alasan"] = (
            "pola Denver: kaki lolos normal tapi jebol di deviasi "
            f"maksimal (P normal {acuan['p_normal'] * 100:.1f}% vs "
            f"P setan {acuan['p_setan'] * 100:.1f}%), tidak ada garis "
            f"tidak-tipis yang tahan banjir{teks_tahan}, garis acuan "
            f"U{acuan['garis']:g} volume tipis, dan edge kecil "
            f"({acuan['edge'] * 100:+.1f}% < {edge_kecil:.1f}%)"
        )
    return hasil


def evaluasi_skip_awal(
    analysis: dict,
    cfg: dict | None = None,
    eq_ins: dict | None = None,
    eq_main: dict | None = None,
    ktx: dict | None = None,
) -> dict:
    """Evaluasi skip-dari-awal satu laga NBA.

    ``eq_ins``/``eq_main`` opsional: hasil ``equilibrium.
    cari_equilibrium`` yang sudah dihitung pemanggil (komposer) —
    bila tidak diberikan, dihitung di sini. ``ktx`` opsional:
    konteks equilibrium (dipakai ulang untuk pola Denver).
    Mengembalikan dict {"match_id", "dievaluasi", "skip", "pemicu",
    "alasan", "ot", "pola_denver", "equilibrium"} — "pemicu" daftar
    token pemicu yang positif (bisa lebih dari satu); "alasan" teks
    gabungan Bahasa Indonesia untuk laporan. Laga BUKAN NBA
    (format soccer_analysis) -> dievaluasi False (skip_awal hanya
    untuk NBA total Under).
    """
    if not isinstance(analysis, dict):
        raise ValueError("analysis harus dict")
    cfg = _muat_cfg(cfg)
    match_id = analysis.get("match_id")
    hasil = {
        "match_id": match_id,
        "dievaluasi": False,
        "alasan_tidak_dievaluasi": None,
        "skip": False,
        "pemicu": [],
        "alasan": None,
        "ot": {
            "ot_probability": None,
            "ambang": None,
            "tinggi": None,
        },
        "pola_denver": {
            "dievaluasi": False,
            "cocok": False,
            "alasan": None,
            "syarat": {},
        },
        "equilibrium": {
            "insurance": None,
            "main": None,
        },
    }
    if analysis.get("format") == "soccer_analysis":
        hasil["alasan_tidak_dievaluasi"] = (
            "skip dari awal hanya untuk laga NBA (bola tidak punya "
            "model stress/OT yang sama)"
        )
        return hasil
    # (c) OT — dinilai dulu (tidak butuh CDF/tangga).
    ot_tinggi, ot_prob, ambang_ot = potensi_ot_tinggi(analysis, cfg)
    hasil["ot"] = {
        "ot_probability": ot_prob,
        "ambang": ambang_ot,
        "tinggi": ot_tinggi,
    }
    # Equilibrium kedua tiket (hitung bila belum diberikan).
    if eq_ins is None:
        eq_ins = equilibrium_mod.cari_equilibrium(analysis, "insurance", cfg)
    if eq_main is None:
        eq_main = equilibrium_mod.cari_equilibrium(analysis, "main", cfg)
    hasil["equilibrium"]["insurance"] = {
        "dihitung": bool(eq_ins.get("dihitung")),
        "ada": bool(eq_ins.get("ada")),
        "garis": eq_ins.get("garis"),
        "harga_venue_cents": eq_ins.get("harga_venue_cents"),
        "p_final": eq_ins.get("p_final"),
        "expected_return": eq_ins.get("expected_return"),
        "alasan_tidak_dihitung": eq_ins.get("alasan_tidak_dihitung"),
        "alasan_tidak_ada": eq_ins.get("alasan_tidak_ada"),
    }
    hasil["equilibrium"]["main"] = {
        "dihitung": bool(eq_main.get("dihitung")),
        "ada": bool(eq_main.get("ada")),
        "garis": eq_main.get("garis"),
        "harga_venue_cents": eq_main.get("harga_venue_cents"),
        "p_final": eq_main.get("p_final"),
        "expected_return": eq_main.get("expected_return"),
        "alasan_tidak_dihitung": eq_main.get("alasan_tidak_dihitung"),
        "alasan_tidak_ada": eq_main.get("alasan_tidak_ada"),
    }
    # (b) pola Denver.
    pola = _evaluasi_pola_denver(analysis, cfg, ktx=ktx)
    hasil["pola_denver"] = pola
    # "Dievaluasi" = minimal satu dari (a)/(b)/(c) bisa dinilai.
    # OT selalu bisa dinilai bila ot_prob ada; equilibrium/pola butuh
    # CDF + tangga + jangkar.
    eq_dinilai = bool(eq_ins.get("dihitung")) and bool(eq_main.get("dihitung"))
    bisa_dinilai = ot_tinggi is not None or eq_dinilai or bool(pola.get("dievaluasi"))
    if not bisa_dinilai:
        alasan = (
            eq_ins.get("alasan_tidak_dihitung")
            or "data tidak cukup (tanpa CDF/tangga/jangkar pasar/OT)"
        )
        hasil["alasan_tidak_dievaluasi"] = (
            f"skip dari awal tidak bisa dinilai: {alasan}"
        )
        return hasil
    hasil["dievaluasi"] = True
    pemicu: list[str] = []
    alasan_bagian: list[str] = []
    # (a) tidak ada equilibrium di KEDUA tiket.
    if eq_dinilai and not eq_ins.get("ada") and not eq_main.get("ada"):
        pemicu.append(PEMICU_TIDAK_ADA_EQUILIBRIUM)
        alasan_bagian.append(
            "tidak ada equilibrium di kedua tiket (tidak ada garis "
            "yang lolos semua gate untuk Asuransi maupun Utama)"
        )
    # (b) pola Denver.
    if pola.get("dievaluasi") and pola.get("cocok"):
        pemicu.append(PEMICU_POLA_DENVER)
        alasan_bagian.append(pola.get("alasan") or "pola Denver")
    # (c) potensi OT tinggi.
    if ot_tinggi is True:
        pemicu.append(PEMICU_OT_TINGGI)
        alasan_bagian.append(
            f"potensi overtime tinggi (peluang OT sim "
            f"{ot_prob * 100:.2f}% >= ambang "
            f"{ambang_ot * 100:.1f}%) — laga praktis imbang, babak "
            "tambahan menambah ~20 poin dan membunuh kaki Under"
        )
    hasil["pemicu"] = pemicu
    hasil["skip"] = bool(pemicu)
    if pemicu:
        # Tanpa awalan "SKIP ..." — pemanggil yang memberi bingkai
        # ("SKIP dari awal — ..." di komposer, "LAGA INI DI-SKIP ..."
        # di laporan) supaya tidak ada duplikasi.
        hasil["alasan"] = "; ".join(alasan_bagian) + "."
    return hasil
