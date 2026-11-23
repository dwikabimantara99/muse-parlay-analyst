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
    eksplisit — bukan perasaan), v18.1:
    (1) flag_setan pada garis acuan: P normal >= target Asuransi
        tapi P setan EFEKTIF < target — setan per pemain v18
        (total_setan_pemain - median) bila blok setan_pemain ada,
        fallback setan generik + catatan bila tidak ada;
    (2) tidak ada garis yang LOLOS GATE EKSEKUSI yang tahan banjir
        pada target Asuransi ("rapuh banjir di semua garis yang
        bisa dibeli" — cek_eksekusi menggantikan flag thin volume
        kumulatif);
    (3) garis acuan TIDAK lolos gate eksekusi (dulu: "volume
        tipis" dari flag thin);
    (4) EV kecil pada garis acuan: EV = p_final x (100/harga) - 1
        < skip_awal.pola_denver.max_ev_for_weak_flag (-1% —
        selaras gate EV Asuransi). Mode legacy (flag
        use_ev_instead_of_flat_edge false) kembali ke edge <
        edge_kecil_pct 3,5% (reversibilitas satu baris config).

    CATATAN v18.1: konversi syarat (4) ke EV (tindak lanjut yang
    dicatat di v18) SUDAH dilakukan — kelemahan jujur v18 (edge
    datar hampir selalu benar di garis acuan mahal sehingga
    konjungsi efektif jadi 3 syarat) diperbaiki: di garis mahal,
    EV yang membedakan kaki murah dari kaki mahal.
    PAGAR ANTI-REDUNDANSI (v18.1): bila laga TIDAK kena Hard Veto
    DAN punya >= 1 garis yang lolos 6 gate Equilibrium Asuransi
    (peluang + p_market + banjir 3P + banjir FT + EV + eksekusi —
    TANPA lantai harga), pola hanya boleh menyala bila KETIGANYA
    benar: (1) garis Asuransi rapuh vs setan pemain (P setan <
    demon_p_fragile_threshold 0,55 INITIAL ATAU median setan >
    garis Asuransi), (2) total pasar >=
    min_market_total_for_pattern 232,0, (3) tidak ada garis valid
    (cek_eksekusi lolos + EV >= -1%) yang tahan banjir maupun
    setan. Bila pagar TIDAK berlaku (veto menyala / veto tidak
    bisa dievaluasi / tidak ada garis lolos gate / data pagar
    hilang), pola 4-syarat berjalan apa adanya (dengan substitusi
    EV + cek_eksekusi + setan pemain) — pagar tidak pernah
    MEMBUAT pola menyala, hanya bisa memblokirnya.
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
from engine import stress as stress_mod
from engine import vonis as vonis_mod

# Nama pemicu (token stabil untuk laporan + JSON ukur).
PEMICU_TIDAK_ADA_EQUILIBRIUM = "tidak_ada_equilibrium"
PEMICU_POLA_DENVER = "pola_denver"
PEMICU_OT_TINGGI = "ot_tinggi"

# Gate Equilibrium Asuransi yang dipakai pagar anti-redundansi:
# 6 gate spek v18.1 — TANPA lantai_harga (bukan bagian daftar spek).
_GATE_PAGAR = ("peluang", "p_market", "banjir_3p", "banjir_ft", "ev", "eksekusi")


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


def _cfg_bool(cfg: dict, *kunci: str) -> bool:
    """Nilai config boolean (ConfigError bila hilang/bukan bool)."""
    nilai = config_mod.get_value(cfg, *kunci)
    if not isinstance(nilai, bool):
        raise config_mod.ConfigError(
            "playstyle.yaml " + ".".join(kunci) + f" harus boolean: {nilai!r}"
        )
    return nilai


def _cfg_angka(cfg: dict, *kunci: str) -> float:
    """Nilai config angka (ConfigError bila hilang/bukan angka)."""
    nilai = _angka(config_mod.get_value(cfg, *kunci))
    if nilai is None:
        raise config_mod.ConfigError(
            "playstyle.yaml " + ".".join(kunci) + " tidak valid"
        )
    return nilai


def _setan_pemain_diaktifkan(cfg: dict) -> bool:
    """Apakah setan per pemain diaktifkan (cermin
    stress._setan_pemain_diaktifkan).

    Section hilang -> True (kompatibel dengan config lama); section
    ada tapi bukan mapping / kunci enabled hilang / enabled bukan
    bool -> ConfigError (kill-switch tidak boleh ambigu).
    """
    section = cfg.get("setan_pemain")
    if section is None:
        return True
    if not isinstance(section, dict):
        raise config_mod.ConfigError("playstyle.yaml setan_pemain harus mapping")
    if "enabled" not in section:
        raise config_mod.ConfigError(
            "playstyle.yaml setan_pemain.enabled tidak ditemukan"
        )
    nilai = section["enabled"]
    if not isinstance(nilai, bool):
        raise config_mod.ConfigError(
            f"playstyle.yaml setan_pemain.enabled harus boolean: {nilai!r}"
        )
    return nilai


def _geser_setan_efektif(
    analysis: dict, cfg: dict, ktx: dict, use_demon: bool
) -> tuple[float, str, float | None, str | None]:
    """Geser setan efektif pola Denver -> (geser, sumber, total, alasan).

    ``sumber`` "pemain" bila flag v18.1 hidup + kill-switch
    setan_pemain.enabled hidup + blok analysis["setan_pemain"]
    membawa total_setan_pemain numerik + median sim ada — geser =
    total - median (cermin stress.skenario_panas). Selain itu
    "generik" (ktx["geser_setan"]) + alasan fallback tercatat
    (artefak lama tanpa blok tidak crash).
    """
    geser_generik = ktx["geser_setan"]
    if not use_demon:
        return (
            geser_generik,
            "generik",
            None,
            "setan per pemain dinonaktifkan di config pola Denver "
            "(use_demon_per_player_v18=false) — memakai setan umum",
        )
    if not _setan_pemain_diaktifkan(cfg):
        return (
            geser_generik,
            "generik",
            None,
            "setan per pemain dinonaktifkan di config "
            "(setan_pemain.enabled=false) — memakai setan umum",
        )
    data = analysis.get("setan_pemain")
    if not isinstance(data, dict):
        return (
            geser_generik,
            "generik",
            None,
            "data setan per pemain tidak tersedia — memakai setan umum",
        )
    total = _angka(data.get("total_setan_pemain"))
    if total is None:
        return (
            geser_generik,
            "generik",
            None,
            "data setan per pemain tanpa total_setan_pemain numerik — "
            "memakai setan umum",
        )
    median = ktx.get("median")
    if median is None:
        return (
            geser_generik,
            "generik",
            None,
            "median total simulasi tidak ada di artefak — geser setan "
            "per pemain tidak bisa dihitung, memakai setan umum",
        )
    return total - median, "pemain", total, None


def _evaluasi_pagar(
    analysis: dict,
    cfg: dict,
    ktx: dict,
    eq_ins: dict | None,
    geser_setan: float,
    median_setan: float | None,
    demon_p_rapuh: float,
    min_market_total: float,
) -> dict:
    """Pagar anti-redundansi v18.1 (hanya bila pola 4-syarat cocok).

    Pagar BERLAKU bila laga dipastikan TIDAK kena Hard Veto DAN
    punya >= 1 garis yang lolos 6 gate Equilibrium Asuransi.
    Veto dibaca dari blok analysis["veto"] bila dievaluasi, else
    dievaluasi langsung via vonis.evaluasi_veto (artefak lama
    tanpa blok veto). Bila berlaku, pola hanya berdiri bila
    ketiga syarat pagar benar: (1) garis Asuransi rapuh vs setan
    (P setan efektif < demon_p_rapuh ATAU median setan > garis
    Asuransi), (2) total pasar >= min_market_total, (3) tidak ada
    garis valid (gate eksekusi + EV lolos) yang tahan banjir
    (gate banjir 3P + FT lolos) maupun setan (P setan efektif >=
    demon_p_rapuh). Garis Asuransi = garis EQ bila ada, else garis
    lolos p_final tertinggi. Kondisi yang tak bisa dievaluasi
    karena data hilang -> pagar tidak dievaluasi (pola berdiri
    apa adanya). Pagar tidak pernah MEMBUAT pola menyala — hanya
    bisa memblokirnya.
    """
    pagar = {
        "berlaku": False,
        "memblokir": False,
        "alasan": None,
        "syarat": {},
        "veto_dievaluasi": None,
        "veto_menyala": None,
        "veto_sumber": None,
        "n_garis_lolos_gate": None,
        "garis_asuransi": None,
        "p_setan_garis_asuransi": None,
        "median_setan": median_setan,
        "garis_market": ktx.get("garis_market"),
        "garis_valid_tahan": None,
    }
    # 1. Veto: blok artefak bila dievaluasi, else evaluasi live.
    veto_blok = analysis.get("veto")
    if isinstance(veto_blok, dict) and veto_blok.get("dievaluasi") is True:
        veto_dievaluasi = True
        veto_menyala = bool(veto_blok.get("menyala"))
        veto_sumber = "blok_artefak"
    else:
        hasil_veto = vonis_mod.evaluasi_veto(analysis, cfg)
        veto_dievaluasi = bool(hasil_veto.get("dievaluasi"))
        veto_menyala = bool(hasil_veto.get("menyala"))
        veto_sumber = "evaluasi_live"
    pagar["veto_dievaluasi"] = veto_dievaluasi
    pagar["veto_menyala"] = veto_menyala
    pagar["veto_sumber"] = veto_sumber
    if not veto_dievaluasi:
        pagar["alasan"] = (
            "pagar tidak berlaku: veto tidak bisa dievaluasi "
            "(tidak bisa dipastikan laga bebas veto)"
        )
        return pagar
    if veto_menyala:
        pagar["alasan"] = "pagar tidak berlaku: laga kena Hard Veto"
        return pagar
    # 2. Garis lolos 6 gate Equilibrium Asuransi.
    nilai = equilibrium_mod.nilai_semua_garis(analysis, "insurance", cfg, ktx=ktx)
    if nilai is None:
        pagar["alasan"] = (
            "pagar tidak berlaku: garis tangga tidak bisa dinilai "
            "(tanpa konteks equilibrium)"
        )
        return pagar
    lolos = [n for n in nilai if all(n["gate"].get(g) for g in _GATE_PAGAR)]
    pagar["n_garis_lolos_gate"] = len(lolos)
    if not lolos:
        pagar["alasan"] = (
            "pagar tidak berlaku: tidak ada garis yang lolos semua "
            "gate Equilibrium Asuransi"
        )
        return pagar
    pagar["berlaku"] = True
    # Garis Asuransi: EQ bila ada, else garis lolos p_final tertinggi.
    garis_eq = None
    if eq_ins is not None and eq_ins.get("ada"):
        garis_eq = _angka(eq_ins.get("garis"))
    if garis_eq is None:
        garis_eq = max(lolos, key=lambda n: n["p_final"])["line"]
    pagar["garis_asuransi"] = garis_eq
    # (1) Garis Asuransi rapuh vs setan.
    p_setan_eq = stress_mod.p_under_digeser(ktx["cdf"], garis_eq, geser_setan)
    pagar["p_setan_garis_asuransi"] = round(p_setan_eq, 6)
    rapuh = bool(
        p_setan_eq < demon_p_rapuh
        or (median_setan is not None and median_setan > garis_eq)
    )
    # (2) Total pasar tinggi.
    garis_market = ktx.get("garis_market")
    if garis_market is None:
        pagar["berlaku"] = False
        pagar["alasan"] = "pagar tidak dievaluasi: garis pasar tidak ada di artefak"
        return pagar
    pasar_tinggi = bool(garis_market >= min_market_total)
    # (3) Tidak ada garis valid yang tahan banjir maupun setan.
    # "Valid" = gate eksekusi + EV lolos; "tahan banjir" = gate
    # banjir 3P + FT lolos (ambang dari config, lewat gate);
    # "tahan setan" = P setan efektif >= demon_p_rapuh.
    garis_valid_tahan = None
    for n in nilai:
        gate = n["gate"]
        if not (gate.get("ev") and gate.get("eksekusi")):
            continue
        if not (gate.get("banjir_3p") and gate.get("banjir_ft")):
            continue
        p_setan_garis = stress_mod.p_under_digeser(ktx["cdf"], n["line"], geser_setan)
        if p_setan_garis >= demon_p_rapuh:
            garis_valid_tahan = n["line"]
            break
    pagar["garis_valid_tahan"] = garis_valid_tahan
    pagar["syarat"] = {
        "garis_asuransi_rapuh_setan": rapuh,
        "total_pasar_tinggi": pasar_tinggi,
        "tidak_ada_garis_valid_tahan": garis_valid_tahan is None,
    }
    pagar["memblokir"] = not all(pagar["syarat"].values())
    if pagar["memblokir"]:
        gagal = [k for k, v in pagar["syarat"].items() if not v]
        pagar["alasan"] = (
            "pagar memblokir pola (syarat pagar gagal: " + ", ".join(gagal) + ")"
        )
    else:
        pagar["alasan"] = "pagar berlaku, ketiga syarat pagar benar — pola berdiri"
    return pagar


def _evaluasi_pola_denver(
    analysis: dict,
    cfg: dict,
    ktx: dict | None = None,
    eq_ins: dict | None = None,
) -> dict:
    """Evaluasi keempat syarat pola Denver v18.1 (konjungsi) + pagar.

    Mengembalikan {"dievaluasi", "cocok", "cocok_tanpa_pagar",
    "alasan", "syarat", "ambang_edge", "ambang_ev", "garis_acuan",
    "detail", "pagar"} — "syarat" memuat nilai tiap syarat (kunci
    syarat (4) "ev_kecil" di mode EV, "edge_kecil" di mode legacy);
    "garis_acuan" adalah hasil cari_garis_acuan DITAMBAH kunci
    v18.1 (p_setan_efektif, setan_sumber, ev, eksekusi_lolos,
    eksekusi_alasan, n_tahan_banjir_bisa_dibeli); "detail" angka
    audit (geser/sumber setan, EV acuan, jumlah garis tahan
    banjir yang bisa dibeli); "pagar" hasil _evaluasi_pagar
    (hanya dievaluasi bila keempat syarat cocok). "cocok" False
    bila pagar berlaku + memblokir; "cocok_tanpa_pagar" mencatat
    konjungsi mentahnya. "dievaluasi" False bila garis acuan
    tidak bisa dihitung, p_final/harga acuan tidak ada (EV tidak
    bisa dinilai — tanpa jangkar pasar), atau config rusak.
    """
    use_ev = _cfg_bool(cfg, "skip_awal", "pola_denver", "use_ev_instead_of_flat_edge")
    use_cek = _cfg_bool(cfg, "skip_awal", "pola_denver", "use_cek_eksekusi_for_thin")
    use_demon = _cfg_bool(cfg, "skip_awal", "pola_denver", "use_demon_per_player_v18")
    max_ev = _cfg_angka(cfg, "skip_awal", "pola_denver", "max_ev_for_weak_flag")
    demon_p_rapuh = _cfg_angka(
        cfg, "skip_awal", "pola_denver", "demon_p_fragile_threshold"
    )
    min_market_total = _cfg_angka(
        cfg, "skip_awal", "pola_denver", "min_market_total_for_pattern"
    )
    ambang = _cfg_angka(cfg, "tickets", "insurance", "min_leg_prob")
    if not -1.0 <= max_ev <= 1.0:
        raise config_mod.ConfigError(
            "playstyle.yaml skip_awal.pola_denver.max_ev_for_weak_flag "
            f"di luar [-1, 1]: {max_ev}"
        )
    if not 0.0 < demon_p_rapuh < 1.0:
        raise config_mod.ConfigError(
            "playstyle.yaml skip_awal.pola_denver.demon_p_fragile_threshold "
            f"di luar (0, 1): {demon_p_rapuh}"
        )
    if min_market_total < 0:
        raise config_mod.ConfigError(
            "playstyle.yaml skip_awal.pola_denver.min_market_total_for_pattern "
            f"negatif: {min_market_total}"
        )
    ambang_edge = None
    if not use_ev:
        edge_kecil_pct = _cfg_angka(cfg, "skip_awal", "pola_denver", "edge_kecil_pct")
        ambang_edge = edge_kecil_pct / 100.0
    if ktx is None:
        ktx = equilibrium_mod.siapkan_konteks(analysis, "insurance", cfg)
    acuan = equilibrium_mod.cari_garis_acuan(analysis, cfg, ktx=ktx)
    kunci_s4 = "ev_kecil" if use_ev else "edge_kecil"
    hasil = {
        "dievaluasi": False,
        "cocok": False,
        "cocok_tanpa_pagar": False,
        "alasan": None,
        "syarat": {
            "flag_setan": None,
            "tidak_ada_tahan_banjir_nonthin": None,
            "garis_acuan_thin": None,
            kunci_s4: None,
        },
        "ambang_edge": ambang_edge,
        "ambang_ev": max_ev,
        "garis_acuan": acuan,
        "detail": {},
        "pagar": {
            "berlaku": False,
            "memblokir": False,
            "alasan": "pola tidak dievaluasi",
            "syarat": {},
        },
    }
    if not acuan.get("dihitung"):
        hasil["alasan"] = (
            "pola Denver tidak bisa dinilai: garis acuan tidak bisa "
            f"dihitung ({acuan.get('alasan') or 'tanpa alasan'})"
        )
        return hasil
    if acuan.get("p_final") is None:
        hasil["alasan"] = (
            "pola Denver tidak bisa dinilai: p_final garis acuan "
            "tidak bisa dihitung (tanpa jangkar pasar)"
        )
        return hasil
    harga = acuan.get("harga_venue_cents")
    if harga is None or not 0.0 < harga < 100.0:
        hasil["alasan"] = (
            "pola Denver tidak bisa dinilai: harga venue garis acuan "
            f"tidak valid ({harga!r}) — EV tidak bisa dihitung"
        )
        return hasil
    garis = acuan["garis"]
    p_normal = acuan["p_normal"]
    tangga = ktx.get("tangga") or []
    # (1) Flag setan — setan per pemain v18, fallback generik.
    geser_setan, sumber_setan, total_setan, alasan_fallback = _geser_setan_efektif(
        analysis, cfg, ktx, use_demon
    )
    p_setan_efektif = stress_mod.p_under_digeser(ktx["cdf"], garis, geser_setan)
    flag_setan = bool(p_normal >= ambang and p_setan_efektif < ambang)
    median_sim = ktx.get("median")
    median_setan = (
        total_setan
        if sumber_setan == "pemain"
        else (median_sim + geser_setan if median_sim is not None else None)
    )

    # (2)/(3) "Bisa dibeli" — cek_eksekusi (v18.1) / flag thin (legacy).
    def _bisa_dibeli(entri: dict) -> bool:
        if use_cek:
            return bool(equilibrium_mod.cek_eksekusi(entri, cfg)["lolos"])
        return entri.get("thin") is not True

    tahan_banjir = [
        entri
        for entri in tangga
        if stress_mod.p_under_digeser(
            ktx["cdf"], float(entri["line"]), ktx["geser_banjir_terburuk"]
        )
        >= ambang
    ]
    tahan_bisa_dibeli = [e for e in tahan_banjir if _bisa_dibeli(e)]
    s2 = not tahan_bisa_dibeli
    entri_acuan = None
    for entri in tangga:
        if abs(float(entri["line"]) - garis) < 1e-9:
            entri_acuan = entri
            break
    eksekusi_acuan = {"lolos": None, "alasan": None}
    if entri_acuan is None:
        # Tidak seharusnya terjadi (acuan diambil dari tangga yang
        # sama) — fallback ke flag thin + catat, bukan crash.
        s3 = acuan.get("thin") is True
        eksekusi_acuan = {
            "lolos": None,
            "alasan": "entri_acuan_tidak_ditemukan_di_tangga",
        }
    elif use_cek:
        eksekusi_acuan = equilibrium_mod.cek_eksekusi(entri_acuan, cfg)
        s3 = not eksekusi_acuan["lolos"]
    else:
        s3 = acuan.get("thin") is True
    # (4) EV kecil (v18.1) / edge kecil (legacy).
    ev_acuan = acuan["p_final"] * (100.0 / harga) - 1.0
    s4 = ev_acuan < max_ev if use_ev else acuan["edge"] < ambang_edge
    syarat = {
        "flag_setan": flag_setan,
        "tidak_ada_tahan_banjir_nonthin": s2,
        "garis_acuan_thin": s3,
        kunci_s4: s4,
    }
    hasil["syarat"] = syarat
    acuan = dict(acuan)
    acuan.update(
        {
            "p_setan_efektif": round(p_setan_efektif, 6),
            "setan_sumber": sumber_setan,
            "ev": round(ev_acuan, 6),
            "eksekusi_lolos": eksekusi_acuan["lolos"],
            "eksekusi_alasan": eksekusi_acuan["alasan"],
            "n_tahan_banjir_bisa_dibeli": len(tahan_bisa_dibeli),
        }
    )
    hasil["garis_acuan"] = acuan
    hasil["detail"] = {
        "geser_setan_efektif": round(geser_setan, 2),
        "setan_sumber": sumber_setan,
        "setan_fallback": alasan_fallback,
        "total_setan_pemain": total_setan,
        "median_setan": median_setan,
        "p_setan_efektif": round(p_setan_efektif, 6),
        "ev_acuan": round(ev_acuan, 6),
        "n_tahan_banjir": len(tahan_banjir),
        "n_tahan_banjir_bisa_dibeli": len(tahan_bisa_dibeli),
        "eksekusi_acuan_alasan": eksekusi_acuan["alasan"],
    }
    hasil["dievaluasi"] = True
    hasil["cocok_tanpa_pagar"] = all(syarat.values())
    hasil["cocok"] = hasil["cocok_tanpa_pagar"]
    if not hasil["cocok_tanpa_pagar"]:
        hasil["pagar"] = {
            "berlaku": False,
            "memblokir": False,
            "alasan": "pola tidak cocok — pagar tidak dievaluasi",
            "syarat": {},
        }
        return hasil
    # Pola cocok -> pagar anti-redundansi.
    pagar = _evaluasi_pagar(
        analysis,
        cfg,
        ktx,
        eq_ins,
        geser_setan,
        median_setan,
        demon_p_rapuh,
        min_market_total,
    )
    hasil["pagar"] = pagar
    if pagar["berlaku"] and pagar["memblokir"]:
        hasil["cocok"] = False
        hasil["alasan"] = "pola Denver cocok tapi DIPAGAR anti-redundansi: " + (
            pagar["alasan"] or "tanpa alasan"
        )
        return hasil
    tahan = acuan.get("garis_tahan_banjir") or {}
    teks_tahan = ""
    if tahan.get("line") is not None:
        if use_cek:
            teks_tahan = (
                f"; garis tahan-banjir U{tahan['line']:g} gagal gate " "eksekusi"
            )
        else:
            teks_tahan = (
                f"; garis tahan-banjir U{tahan['line']:g} "
                f"{'tipis' if tahan.get('thin') else 'tidak ditemukan yang tebal'}"
            )
    if use_cek:
        teks_acuan = f", garis acuan U{garis:g} tidak bisa dibeli" + (
            f" ({eksekusi_acuan['alasan']})" if eksekusi_acuan["alasan"] else ""
        )
    else:
        teks_acuan = f", garis acuan U{garis:g} volume tipis"
    if use_ev:
        teks_s4 = f", dan EV kecil ({ev_acuan * 100:+.1f}% < " f"{max_ev * 100:+.1f}%)"
    else:
        teks_s4 = (
            f", dan edge kecil ({acuan['edge'] * 100:+.1f}% < "
            f"{ambang_edge * 100:.1f}%)"
        )
    hasil["alasan"] = (
        "pola Denver: kaki lolos normal tapi jebol di deviasi "
        f"maksimal (P normal {p_normal * 100:.1f}% vs "
        f"P setan {p_setan_efektif * 100:.1f}%"
        + (" (per pemain)" if sumber_setan == "pemain" else "")
        + "), tidak ada garis yang bisa dibeli yang tahan banjir"
        + teks_tahan
        + teks_acuan
        + teks_s4
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
            "cocok_tanpa_pagar": False,
            "alasan": None,
            "syarat": {},
            "detail": {},
            "pagar": {
                "berlaku": False,
                "memblokir": False,
                "alasan": "pola tidak dievaluasi",
                "syarat": {},
            },
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
    # (b) pola Denver (eq_ins diteruskan untuk pagar anti-redundansi).
    pola = _evaluasi_pola_denver(analysis, cfg, ktx=ktx, eq_ins=eq_ins)
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
