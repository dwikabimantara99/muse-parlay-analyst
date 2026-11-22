"""Usulan belajar dari ringkasan hasil per pasar (Tahap 3 Langkah 6).

PRINSIP KEAMANAN: modul ini hanya MENGHASILKAN usulan teks. Ia TIDAK
PERNAH menerapkan perubahan — tidak menulis config, tidak mengubah
ambang, tidak menyentuh file. Setiap usulan berstatus
"menunggu_persetujuan" dan berlaku hanya setelah user menyetujui.

Aturan usulan (ambang di config/playstyle.yaml -> learning):

  (a) jenis "pasar": brier_model > brier_climatology DAN
      n >= learning.min_n_pasar (default 20) -> model lebih buruk dari
      sekadar menebak frekuensi dasar di pasar ini; pertimbangkan tidak
      memainkan pasar itu / menaikkan ambang pasar itu.
  (b) jenis "kalibrasi": brier_model < brier_market DAN
      n >= learning.min_n_kalibrasi_pasar (default 50) -> model
      mengalahkan market di pasar ini; pertimbangkan menaikkan w khusus
      pasar (tetap butuh persetujuan user).
  (c) jenis "ambang": ev_terealisasi_rata2 < ev_prediksi_rata2 -
      learning.ev_gap_warn (default 0,05) DAN n >= learning.min_n_pasar
      (default 20) -> EV prediksi terlalu optimis; tinjau ambang EV /
      label harga.
  (d) jenis "data": tidak ada data settled sama sekali (tidak ada kaki
      settled di outcomes DAN tidak ada entri ringkasan dengan n > 0)
      -> SATU usulan: belum ada hasil tercatat, kumpulkan data PAPER
      dulu (keyakinan "rendah", n=0).

Keyakinan dari n (learning.keyakinan_n): n < sedang_min (20) ->
"rendah"; sedang_min <= n < tinggi_min (50) -> "sedang";
n >= tinggi_min (50) -> "tinggi".

Aturan dengan nilai yang hilang (None) dilewati diam-diam untuk pasar
itu — usulan hanya dibuat dari angka yang benar-benar ada. Urutan
usulan deterministik: pasar diurutkan menurut labelnya, lalu aturan
(a) -> (b) -> (c) per pasar; id USUL-001, USUL-002, ... mengikuti
urutan itu. Kunci ringkasan boleh tuple (sport, market) atau string —
keduanya diterima, label pasar diturunkan dari kunci.
"""

from __future__ import annotations

import config

STATUS_MENUNGGU = "menunggu_persetujuan"


def _label_pasar(kunci) -> str:
    """Label pasar dari kunci ringkasan: tuple (sport, market) atau string."""
    if isinstance(kunci, (tuple, list)) and len(kunci) == 2:
        return f"{kunci[0]} / {kunci[1]}"
    return str(kunci)


def _keyakinan(n: int, ambang: dict) -> str:
    """Keyakinan dari n: < sedang_min rendah, < tinggi_min sedang, else tinggi."""
    if n < ambang["sedang_min"]:
        return "rendah"
    if n < ambang["tinggi_min"]:
        return "sedang"
    return "tinggi"


def _ada_data_settled(ringkasan: dict, outcomes) -> bool:
    """True bila ada bukti hasil tercatat: kaki settled di outcomes, atau
    entri ringkasan dengan n > 0."""
    for kaki in outcomes or []:
        if (
            isinstance(kaki, dict)
            and kaki.get("settled")
            and kaki.get("result") is not None
        ):
            return True
    for entri in (ringkasan or {}).values():
        if isinstance(entri, dict) and (entri.get("n") or 0) > 0:
            return True
    return False


def _usulan(
    nomor: int,
    jenis: str,
    judul: str,
    isi: str,
    bukti: dict,
    n: int,
    keyakinan: str,
    aksi: str,
) -> dict:
    """Satu dict usulan dengan bentuk baku (status selalu menunggu)."""
    return {
        "id": f"USUL-{nomor:03d}",
        "jenis": jenis,
        "judul": judul,
        "isi": isi,
        "bukti": bukti,
        "n": n,
        "keyakinan": keyakinan,
        "status": STATUS_MENUNGGU,
        "aksi": aksi,
    }


def hasilkan_usulan(ringkasan: dict, outcomes, cfg: dict | None = None) -> list[dict]:
    """Hasilkan daftar usulan belajar dari ringkasan per pasar.

    ringkasan: output ringkasan_per_pasar pekerja A (engine/learning.py)
    — dict per (sport, market) dengan n, brier_model, brier_market,
    brier_climatology, ev_prediksi_rata2, ev_terealisasi_rata2. Kunci
    boleh tuple (sport, market) atau string.
    outcomes: daftar dict record hasil (bentuk yang sama seperti di
    engine/calibration.py); hanya dipakai untuk aturan (d) — apakah
    sudah ada kaki settled sama sekali.
    cfg: dict playstyle (None = baca config/playstyle.yaml, hanya baca).

    Mengembalikan list dict usulan (bentuk di _usulan). List kosong
    berarti tidak ada aturan yang terpicu — bukan berarti tidak ada
    data. Fungsi ini tidak menulis apa pun ke mana pun.
    """
    cfg = cfg if cfg is not None else config.load_playstyle()
    learning = config.get_value(cfg, "learning")
    min_n_pasar = learning["min_n_pasar"]
    min_n_kalibrasi = learning["min_n_kalibrasi_pasar"]
    ev_gap_warn = learning["ev_gap_warn"]
    ambang_keyakinan = learning["keyakinan_n"]

    if not _ada_data_settled(ringkasan, outcomes):
        return [
            _usulan(
                nomor=1,
                jenis="data",
                judul="Belum ada hasil tercatat — kumpulkan data PAPER dulu",
                isi=(
                    "Belum ada satu pun kaki settled yang tercatat, jadi "
                    "belum ada yang bisa dipelajari. Mainkan PAPER dulu dan "
                    "catat hasilnya; usulan belajar baru muncul setelah ada "
                    "data settled."
                ),
                bukti={"n_settled": 0},
                n=0,
                keyakinan="rendah",
                aksi=(
                    "Kumpulkan data PAPER (catat hasil tiap kaki) sampai "
                    "sampel cukup untuk kalibrasi; tidak ada perubahan "
                    "ambang yang diusulkan."
                ),
            )
        ]

    usulan: list[dict] = []
    nomor = 0
    for kunci in sorted((ringkasan or {}).keys(), key=_label_pasar):
        entri = ringkasan[kunci]
        if not isinstance(entri, dict):
            continue
        label = _label_pasar(kunci)
        n = entri.get("n") or 0
        yakin = _keyakinan(n, ambang_keyakinan)
        brier_model = entri.get("brier_model")
        brier_market = entri.get("brier_market")
        brier_climatology = entri.get("brier_climatology")
        ev_prediksi = entri.get("ev_prediksi_rata2")
        ev_terealisasi = entri.get("ev_terealisasi_rata2")
        # (a) Model lebih buruk dari frekuensi dasar di pasar ini.
        if (
            brier_model is not None
            and brier_climatology is not None
            and brier_model > brier_climatology
            and n >= min_n_pasar
        ):
            nomor += 1
            usulan.append(
                _usulan(
                    nomor=nomor,
                    jenis="pasar",
                    judul=f"Pasar {label}: model kalah dari frekuensi dasar",
                    isi=(
                        f"Di pasar {label}, Brier model ({brier_model:.4f}) "
                        "lebih buruk dari Brier climatology "
                        f"({brier_climatology:.4f}) — sekadar menebak "
                        "frekuensi dasar lebih akurat dari model di sini."
                    ),
                    bukti={
                        "pasar": label,
                        "brier_model": brier_model,
                        "brier_climatology": brier_climatology,
                        "n": n,
                    },
                    n=n,
                    keyakinan=yakin,
                    aksi=(
                        f"Pertimbangkan tidak memainkan pasar {label} atau "
                        "menaikkan ambang peluang minimumnya — menunggu "
                        "persetujuan user."
                    ),
                )
            )
        # (b) Model mengalahkan market di pasar ini.
        if (
            brier_model is not None
            and brier_market is not None
            and brier_model < brier_market
            and n >= min_n_kalibrasi
        ):
            nomor += 1
            usulan.append(
                _usulan(
                    nomor=nomor,
                    jenis="kalibrasi",
                    judul=f"Pasar {label}: model mengalahkan market",
                    isi=(
                        f"Di pasar {label}, Brier model ({brier_model:.4f}) "
                        "lebih baik dari Brier market "
                        f"({brier_market:.4f}) atas {n} kaki settled — "
                        "model lebih akurat dari pasar di sini."
                    ),
                    bukti={
                        "pasar": label,
                        "brier_model": brier_model,
                        "brier_market": brier_market,
                        "n": n,
                    },
                    n=n,
                    keyakinan=yakin,
                    aksi=(
                        f"Pertimbangkan menaikkan w khusus pasar {label} "
                        "(model diberi bobot lebih besar) — tetap butuh "
                        "persetujuan user; w global tidak berubah."
                    ),
                )
            )
        # (c) EV prediksi terlalu optimis di pasar ini.
        if (
            ev_prediksi is not None
            and ev_terealisasi is not None
            and ev_terealisasi < ev_prediksi - ev_gap_warn
            and n >= min_n_pasar
        ):
            nomor += 1
            usulan.append(
                _usulan(
                    nomor=nomor,
                    jenis="ambang",
                    judul=f"Pasar {label}: EV prediksi terlalu optimis",
                    isi=(
                        f"Di pasar {label}, EV terealisasi rata-rata "
                        f"({ev_terealisasi:.4f}) berada "
                        f"{ev_prediksi - ev_terealisasi:.4f} di bawah EV "
                        f"prediksi rata-rata ({ev_prediksi:.4f}) — melebihi "
                        f"batas peringatan {ev_gap_warn}."
                    ),
                    bukti={
                        "pasar": label,
                        "ev_prediksi_rata2": ev_prediksi,
                        "ev_terealisasi_rata2": ev_terealisasi,
                        "selisih_ev": ev_prediksi - ev_terealisasi,
                        "ev_gap_warn": ev_gap_warn,
                        "n": n,
                    },
                    n=n,
                    keyakinan=yakin,
                    aksi=(
                        f"Tinjau ambang EV / label harga untuk pasar {label} "
                        "(mis. menaikkan ambang EV minimum atau memperketat "
                        "label DISKON) — menunggu persetujuan user."
                    ),
                )
            )
    return usulan
