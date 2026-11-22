"""Mesin analis: bantalan adaptif + nilai wajar (filosofi user 2026-11-23).

Mesin ini ANALIS yang menilai per laga, bukan mesin aturan kaku:

- Bantalan TIDAK kaku: "+8" hanya istilah/acuan user. Mesin menghitung
  bantalan per laga dari statistik (sebaran simulasi, kekuatan serang,
  form skor terakhir). Boleh di bawah 8 bila statistik membenarkan
  (dengan alasan tercatat), wajib di atas 8 bila laga menuntut.
- "Wajar" = jarak antara titik acuan analisis (median simulasi) dan
  garis tempat harga duduk: harga wajar bila garis itu menyediakan
  minimal bantalan yang diminta statistik.
- Mesin MENJELASKAN alasannya dengan kata-kata biasa (field "alasan" /
  "penjelasan"), bukan hanya angka.

RUMUS BANTALAN ADAPTIF (bantalan_adaptif) — NILAI AWAL, BELUM
DIKALIBRASI, menunggu kalibrasi atas data PAPER + persetujuan user:

    dasar  = std_sim * std_factor
    serang = (ortg_rata_kedua_tim - ortg_liga_rata) * ortg_weight
    form   = (total_rata_5laga - total_rata_musim) * form_weight
    bantalan = clamp(dasar + serang + form, min_points, max_points)

Alasan tiap suku:
- dasar dari sebaran sim: total yang sebarannya lebar lebih mudah
  melonjak melewati garis, jadi butuh bantalan lebih tebal. std_factor
  0,42 dipilih supaya laga biasa (std sim ~19 poin, sesuai
  sigma_total hasil fit 18,9868) memberi dasar ~8 poin = acuan user.
  Pada std ~19, 8 poin ~= 0,42 sigma -> P(Under di median+8) ~= 0,66,
  selaras dengan target peluang model Utama 65%.
- serang: dua tim penyerang kuat (rating serang di atas rata-rata
  liga) cenderung mencetak lebih banyak poin -> bantalan ditebalkan;
  dua tim penyerang lemah -> bantalan ditipiskan. ortg_weight 0,5:
  selisih 4 poin rating serang = 2 poin bantalan.
- form: skor 5 laga terakhir di atas rata-rata musim menandakan kedua
  tim sedang panas -> bantalan ditebalkan (dan sebaliknya).
  form_weight 0,25: selisih 10 poin skor = 2,5 poin bantalan.
- clamp [min_points, max_points]: bantalan tidak boleh nol (selalu
  ada ketidakpastian) dan tidak boleh tak masuk akal (garis yang
  terlalu jauh tidak ada harganya).

Fungsi di sini murni: tanpa I/O, tanpa RNG. Input tidak valid
(tipe salah) -> ValueError. Data hilang (None): faktor yang hilang
dilewati + dicatat tidak terverifikasi; bila median atau std sim
hilang, bantalan_adaptif mengembalikan None (jangan tebak) dan
nilai_wajar memberi penilaian "tidak_terverifikasi".

Semua bobot/ambang dibaca dari section "analis" playstyle.yaml
(config.py get_value — kunci hilang -> ConfigError, jangan diam-diam
memakai default dari kode).
"""

from __future__ import annotations

import math

import config


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


def _param_cushion(cfg: dict) -> dict:
    """Baca parameter rumus bantalan dari section analis.cushion."""
    kunci = (
        "acuan_points",
        "std_factor",
        "ortg_weight",
        "form_weight",
        "min_points",
        "max_points",
    )
    params = {}
    for nama in kunci:
        nilai = _validasi_angka(
            config.get_value(cfg, "analis", "cushion", nama),
            f"analis.cushion.{nama}",
        )
        params[nama] = nilai
    if params["min_points"] < 0 or params["max_points"] <= params["min_points"]:
        raise ValueError(
            "analis.cushion min/max tidak valid: "
            f"min={params['min_points']}, max={params['max_points']} "
            "(harus 0 <= min < max)"
        )
    if params["std_factor"] <= 0:
        raise ValueError(
            f"analis.cushion.std_factor tidak valid: {params['std_factor']} "
            "(harus > 0)"
        )
    return params


def _fmt(nilai: float) -> str:
    """Format angka untuk kalimat biasa (8.0 -> '8', 12.5 -> '12,5')."""
    teks = f"{nilai:.2f}".rstrip("0").rstrip(".")
    return teks.replace(".", ",")


def bantalan_adaptif(
    stats_laga: dict, distribusi_sim: dict, cfg: dict | None = None
) -> dict | None:
    """Hitung bantalan Alt Under per laga dari statistik.

    stats_laga: {"ortg_home", "ortg_away", "ortg_liga_rata",
    "total_rata_5laga", "total_rata_musim"} (float | None; yang None =
    faktor itu dilewati + dicatat tidak terverifikasi).
    distribusi_sim: {"median", "std", "p75", "p95", "p5", "p25"}
    (float | None; median atau std hilang -> None + alasan
    "data_tidak_lengkap", jangan tebak).
    cfg: dict playstyle (None = baca playstyle.yaml).

    Mengembalikan {"cushion_points", "alasan", "faktor",
    "acuan_points"} atau None bila data sim tidak lengkap.
    """
    cfg = cfg if cfg is not None else config.load_playstyle()
    if not isinstance(stats_laga, dict):
        raise ValueError(f"stats_laga harus dict, didapat {type(stats_laga).__name__}")
    if not isinstance(distribusi_sim, dict):
        raise ValueError(
            f"distribusi_sim harus dict, didapat {type(distribusi_sim).__name__}"
        )
    params = _param_cushion(cfg)

    median = _angka_atau_none(distribusi_sim.get("median"), "distribusi_sim.median")
    std = _angka_atau_none(distribusi_sim.get("std"), "distribusi_sim.std")
    p75 = _angka_atau_none(distribusi_sim.get("p75"), "distribusi_sim.p75")
    p95 = _angka_atau_none(distribusi_sim.get("p95"), "distribusi_sim.p95")
    p5 = _angka_atau_none(distribusi_sim.get("p5"), "distribusi_sim.p5")
    p25 = _angka_atau_none(distribusi_sim.get("p25"), "distribusi_sim.p25")
    if median is None or std is None:
        return None
    if std < 0:
        raise ValueError(f"distribusi_sim.std tidak valid: {std} (harus >= 0)")

    ortg_home = _angka_atau_none(stats_laga.get("ortg_home"), "stats_laga.ortg_home")
    ortg_away = _angka_atau_none(stats_laga.get("ortg_away"), "stats_laga.ortg_away")
    ortg_liga = _angka_atau_none(
        stats_laga.get("ortg_liga_rata"), "stats_laga.ortg_liga_rata"
    )
    total_5 = _angka_atau_none(
        stats_laga.get("total_rata_5laga"), "stats_laga.total_rata_5laga"
    )
    total_musim = _angka_atau_none(
        stats_laga.get("total_rata_musim"), "stats_laga.total_rata_musim"
    )

    tidak_terverifikasi: list[str] = []

    # Dasar dari sebaran sim: varians besar -> bantalan tebal.
    dasar = std * params["std_factor"]

    # Kekuatan serang: butuh ketiga angka, else faktor dilewati.
    penyesuaian_serang = 0.0
    ortg_rata = None
    selisih_ortg = None
    if ortg_home is None or ortg_away is None or ortg_liga is None:
        tidak_terverifikasi.append("kekuatan_serang")
    else:
        ortg_rata = (ortg_home + ortg_away) / 2
        selisih_ortg = ortg_rata - ortg_liga
        penyesuaian_serang = selisih_ortg * params["ortg_weight"]

    # Form skor terakhir: butuh kedua angka, else faktor dilewati.
    penyesuaian_form = 0.0
    selisih_form = None
    if total_5 is None or total_musim is None:
        tidak_terverifikasi.append("form_skor")
    else:
        selisih_form = total_5 - total_musim
        penyesuaian_form = selisih_form * params["form_weight"]

    mentah = dasar + penyesuaian_serang + penyesuaian_form
    dibatasi = None
    bantalan = mentah
    if mentah < params["min_points"]:
        bantalan = params["min_points"]
        dibatasi = {"ke": "min", "nilai_sebelum_batas": round(mentah, 2)}
    elif mentah > params["max_points"]:
        bantalan = params["max_points"]
        dibatasi = {"ke": "max", "nilai_sebelum_batas": round(mentah, 2)}
    bantalan = round(bantalan, 2)

    faktor: dict = {
        "sebaran_sim": {
            "median": median,
            "std": std,
            "p5": p5,
            "p25": p25,
            "p75": p75,
            "p95": p95,
            "dasar_poin": round(dasar, 2),
            "terverifikasi": True,
        },
        "kekuatan_serang": {
            "ortg_home": ortg_home,
            "ortg_away": ortg_away,
            "ortg_liga_rata": ortg_liga,
            "ortg_rata_kedua_tim": (
                round(ortg_rata, 2) if ortg_rata is not None else None
            ),
            "selisih_vs_liga": (
                round(selisih_ortg, 2) if selisih_ortg is not None else None
            ),
            "penyesuaian_poin": round(penyesuaian_serang, 2),
            "terverifikasi": "kekuatan_serang" not in tidak_terverifikasi,
        },
        "form_skor": {
            "total_rata_5laga": total_5,
            "total_rata_musim": total_musim,
            "selisih_poin": (
                round(selisih_form, 2) if selisih_form is not None else None
            ),
            "penyesuaian_poin": round(penyesuaian_form, 2),
            "terverifikasi": "form_skor" not in tidak_terverifikasi,
        },
        "tidak_terverifikasi": tidak_terverifikasi,
        "dibatasi": dibatasi,
    }

    # Alasan dengan kata-kata biasa.
    if std >= 22:
        sebaran_kata = "lebar"
    elif std >= 16:
        sebaran_kata = "biasa"
    else:
        sebaran_kata = "sempit"
    bagian = [
        f"Bantalan {_fmt(bantalan)} poin karena sebaran simulasi {sebaran_kata} "
        f"(simpangan baku {_fmt(std)} poin)"
    ]
    if selisih_ortg is not None:
        if selisih_ortg >= 2:
            bagian.append(
                "kedua tim penyerang kuat "
                f"(rating serang rata-rata {_fmt(ortg_rata or 0)} vs "
                f"rata-rata liga {_fmt(ortg_liga or 0)})"
            )
        elif selisih_ortg <= -2:
            bagian.append(
                "kedua tim penyerang lemah "
                f"(rating serang rata-rata {_fmt(ortg_rata or 0)} vs "
                f"rata-rata liga {_fmt(ortg_liga or 0)})"
            )
        else:
            bagian.append("kekuatan serang kedua tim biasa saja")
    if selisih_form is not None:
        if selisih_form >= 5:
            bagian.append(
                "kedua tim sama-sama mencetak banyak poin di 5 laga terakhir "
                f"(rata-rata {_fmt(total_5 or 0)} vs {_fmt(total_musim or 0)} "
                "poin semusim)"
            )
        elif selisih_form <= -5:
            bagian.append(
                "skor 5 laga terakhir di bawah rata-rata musim "
                f"(rata-rata {_fmt(total_5 or 0)} vs {_fmt(total_musim or 0)} "
                "poin semusim)"
            )
        else:
            bagian.append("skor 5 laga terakhir biasa saja")
    if tidak_terverifikasi:
        bagian.append(
            "sebagian data tidak tersedia ("
            + ", ".join(tidak_terverifikasi)
            + "), jadi faktor itu tidak dihitung"
        )
    if dibatasi is not None:
        bagian.append(
            f"hasil mentah {_fmt(mentah)} poin dibatasi ke " f"{_fmt(bantalan)} poin"
        )
    alasan = ", dan ".join(bagian) + "."
    # Rapikan: "A, dan B, dan C." -> "A, B, dan C."
    alasan = alasan.replace(", dan ", ", ", alasan.count(", dan ") - 1)

    return {
        "cushion_points": bantalan,
        "alasan": alasan,
        "faktor": faktor,
        "acuan_points": params["acuan_points"],
    }


def nilai_wajar(
    *,
    acuan_sim,
    garis_market,
    garis_harga,
    harga_cents,
    bantalan_dibutuhkan_poin,
    cfg: dict | None = None,
) -> dict:
    """Nilai apakah harga di suatu garis itu wajar menurut statistik.

    "Wajar" = jarak antara titik acuan analisis (acuan_sim, mis.
    median simulasi) dan garis tempat harga duduk (garis_harga)
    menyediakan minimal bantalan yang diminta statistik
    (bantalan_dibutuhkan_poin, dari bantalan_adaptif):
    "wajar" bila jarak_poin - bantalan_dibutuhkan_poin >=
    analis.wajar.selisih_minimum_poin (0,0); "di_bawah_wajar" bila
    jarak kurang dari yang dibutuhkan; "tidak_terverifikasi" bila
    ada input None (data hilang, jangan tebak).

    Mengembalikan {"acuan_sim", "garis_market", "garis_harga",
    "harga_cents", "jarak_poin", "bantalan_dibutuhkan_poin",
    "penilaian", "penjelasan"}. Penjelasan kata-kata biasa yang
    menyebut acuan, garis, jarak, bantalan yang dibutuhkan, dan
    kesimpulan.
    """
    cfg = cfg if cfg is not None else config.load_playstyle()
    selisih_min = _validasi_angka(
        config.get_value(cfg, "analis", "wajar", "selisih_minimum_poin"),
        "analis.wajar.selisih_minimum_poin",
    )
    acuan = _angka_atau_none(acuan_sim, "acuan_sim")
    market = _angka_atau_none(garis_market, "garis_market")
    garis = _angka_atau_none(garis_harga, "garis_harga")
    harga = _angka_atau_none(harga_cents, "harga_cents")
    bantalan = _angka_atau_none(bantalan_dibutuhkan_poin, "bantalan_dibutuhkan_poin")
    if bantalan is not None and bantalan < 0:
        raise ValueError(
            f"bantalan_dibutuhkan_poin tidak valid: {bantalan} (harus >= 0)"
        )

    hilang = [
        nama
        for nama, nilai in (
            ("acuan_sim", acuan),
            ("garis_market", market),
            ("garis_harga", garis),
            ("harga_cents", harga),
            ("bantalan_dibutuhkan_poin", bantalan),
        )
        if nilai is None
    ]
    jarak = None
    if acuan is not None and garis is not None:
        jarak = round(garis - acuan, 9)

    if hilang:
        penjelasan = (
            "Tidak bisa dinilai wajar atau tidak: data "
            + ", ".join(hilang)
            + " tidak tersedia."
        )
        if acuan is not None and garis is not None:
            penjelasan += (
                f" Acuan analisis {_fmt(acuan)} poin, garis harga "
                f"{_fmt(garis)} (jarak {_fmt(jarak or 0)} poin)."
            )
        return {
            "acuan_sim": acuan,
            "garis_market": market,
            "garis_harga": garis,
            "harga_cents": harga,
            "jarak_poin": jarak,
            "bantalan_dibutuhkan_poin": bantalan,
            "penilaian": "tidak_terverifikasi",
            "penjelasan": penjelasan,
        }

    assert jarak is not None and bantalan is not None
    assert acuan is not None and garis is not None and harga is not None
    assert market is not None
    selisih = jarak - bantalan
    if selisih >= selisih_min:
        penilaian = "wajar"
        kesimpulan = (
            "jadi harga ini wajar — garisnya memberi bantalan yang " "diminta statistik"
        )
    else:
        penilaian = "di_bawah_wajar"
        kesimpulan = (
            "jadi harga ini di bawah wajar — garisnya terlalu dekat "
            "dengan acuan, bantalan yang diminta statistik tidak terpenuhi"
        )
    penjelasan = (
        f"Acuan analisis {_fmt(acuan)} poin (garis bandar {_fmt(market)}); "
        f"harga {_fmt(harga)}¢ duduk di garis {_fmt(garis)} — jaraknya "
        f"{_fmt(jarak)} poin dari acuan, sementara statistik meminta "
        f"bantalan {_fmt(bantalan)} poin; {kesimpulan}."
    )
    return {
        "acuan_sim": acuan,
        "garis_market": market,
        "garis_harga": garis,
        "harga_cents": harga,
        "jarak_poin": jarak,
        "bantalan_dibutuhkan_poin": bantalan,
        "penilaian": penilaian,
        "penjelasan": penjelasan,
    }
