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

    CATATAN v18: syarat (4) DIPERTAHANKAN berbasis edge, BUKAN
    diubah ke EV — alasan: (i) mengubahnya butuh ubah tes pola
    Denver + test_config.py (di luar ruang lingkup worker A v18);
    (ii) di dalam konjungsi 4-syarat, edge adalah sinyal lemah,
    bukan gerbang — cacat edge-datar (pelajaran v18) paling
    menggigit di gerbang, dan gerbang Asuransi SUDAH diganti ke
    EV (max_negative_ev_pct). Konversi ke EV dicatat sebagai
    tindak lanjut: EV = p_final x (100/harga) - 1 vs ambang
    DISKON price_labels.diskon_min_ev_pct (+2%). KELEMAHAN JUJUR:
    pada harga tinggi edge menyusut mekanis, jadi syarat (4)
    hampir selalu benar untuk garis acuan mahal — konjungsi
    efektif jadi 3 syarat di sana.
    "Volume tipis" juga terkandung di (2): garis tahan-banjir yang
    ada semuanya thin berarti garis yang selamat tidak bisa dibeli.
    Garis acuan = garis tangga Under terendah dengan P normal >=
    target Asuransi (engine/equilibrium.cari_garis_acuan) — pada
    tangga monoton naik, ini sekaligus garis termurah.
(c) ot_tinggi — potensi OT tinggi: probabilitas OT EMPIRIS
    (engine/ot_empiris.py: laju dasar liga x penyesuaian spread)
    >= ot_seleksi.hard_skip_ot_prob (INITIAL 0,085, v18).
    Pemicu keras v17 (ot_probability sim >= 0,028) DIHAPUS:
    ot_prob sim tidak pernah mencapai 2,74% (kap teoretis,
    0/2.701 laga kalibrasi melewati 2,74%) — ambang 2,8% di atas
    kap, jadi tidak pernah memicu kecuali artefak cacat. OT sim
    tetap dicatat sebagai info di hasil["ot"]["ot_probability"].
    KEPUTUSAN: SKIP (bukan bantalan lebih besar) — OT menambah
    loncatan diskret ~20+ poin yang SUDAH dimodelkan sim dalam
    distribusi total; risiko sisa adalah model MEREMEHKAN OT
    (nilai sim 1,7–2,9% vs laju OT historis NBA ~5–6%), yang
    tidak bisa diperbaiki oleh bantalan yang dihitung dari model
    yang sama. KEJUJURAN: DEN@CHI (yang benar-benar OT) punya
    ot_prob sim hanya 2,36%/2,13% — TIDAK kena aturan v17;
    Denver ditangkap pola_denver, bukan aturan OT. CATATAN
    KEJUJURAN v18: di bawah rumus empiris, hard-skip 0,085
    TIDAK TERCAPAI (p_ot maks pada spread 0 = laju dasar 0,0575
    < 0,085) — gerbang ini dormant sampai kalibrasi ledger
    memberi laju OT per kelompok spread atau ambang diturunkan
    atas persetujuan user. Lihat engine/ot_empiris.py.

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
from engine import ot_empiris as ot_empiris_mod

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
    """Apakah potensi OT laga ini tinggi? -> (tinggi, p_ot, ambang).

    v18: ``p_ot`` adalah probabilitas OT EMPIRIS
    (engine/ot_empiris.py, dari spread |median margin|), BUKAN
    ot_probability sim. ``tinggi`` None bila spread tidak ada di
    artefak (tidak bisa dinilai — bukan bukti aman). Ambang dari
    ot_seleksi.hard_skip_ot_prob (ConfigError bila kunci hilang
    atau mode bukan "empiris").
    """
    cfg = _muat_cfg(cfg)
    hasil = ot_empiris_mod.evaluasi_ot(analysis, cfg)
    ambang = ot_empiris_mod.baca_ambang_hard_skip(cfg)
    if not hasil["dievaluasi"]:
        return None, None, ambang
    return hasil["hard_skip"], hasil["p_ot_empiris"], ambang


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
            "p_ot_empiris": None,
            "spread_points": None,
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
    # v18: ot_prob di sini adalah p OT EMPIRIS (dari spread);
    # ot_probability sim dicatat sebagai info di hasil["ot"].
    ot_tinggi, ot_prob, ambang_ot = potensi_ot_tinggi(analysis, cfg)
    _evaluasi_ot = ot_empiris_mod.evaluasi_ot(analysis, cfg)
    hasil["ot"] = {
        "ot_probability": baca_ot_probability(analysis),
        "p_ot_empiris": ot_prob,
        "spread_points": _evaluasi_ot.get("spread_points"),
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
    # OT selalu bisa dinilai bila spread (|median margin|) ada;
    # equilibrium/pola butuh CDF + tangga + jangkar.
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
            f"potensi overtime tinggi (peluang OT empiris "
            f"{ot_prob * 100:.2f}% >= ambang "
            f"{ambang_ot * 100:.1f}%, spread "
            f"{_evaluasi_ot.get('spread_points')} poin) — laga "
            "praktis imbang, babak tambahan menambah ~20 poin dan "
            "membunuh kaki Under"
        )
    hasil["pemicu"] = pemicu
    hasil["skip"] = bool(pemicu)
    if pemicu:
        # Tanpa awalan "SKIP ..." — pemanggil yang memberi bingkai
        # ("SKIP dari awal — ..." di komposer, "LAGA INI DI-SKIP ..."
        # di laporan) supaya tidak ada duplikasi.
        hasil["alasan"] = "; ".join(alasan_bagian) + "."
    return hasil
