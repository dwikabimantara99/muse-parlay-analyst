"""Laporan belajar mesin parlay (Tahap 3 Langkah 6).

Satu laporan teks Bahasa Indonesia sehari-hari, tanpa jargon, dari
data hasil belajar yang dirakit ``cli.py belajar`` (atau
``scripts/laporan_belajar_replay.py``). Modul ini MURNI RENDER: tidak
ada fetch, tidak ada hitung ulang statistik, tidak ada panggilan
Odds API, dan tidak ada angka yang ditebak. Datum yang tidak ada
ditulis "tidak ada datanya" / "belum bisa dibandingkan".

Kontrak ``data`` (dict) untuk ``render_laporan_belajar``:

  sumber_data: "ledger" | "replay" | "sintetis".
  ada_data: bool — False berarti belum ada kaki settled yang tercatat.
  pesan: str | None — pesan dari muat_hasil_ledger (bila dari ledger).
  ringkasan: dict | None — ringkasan_keseluruhan (n, win_rate,
    brier_model/market/final/climatology, ev_prediksi_rata2,
    ev_terealisasi_rata2, beserta n_* dan alasan_*).
  ringkasan_per_pasar: dict | None — ringkasan_per_pasar; kunci boleh
    tuple (sport, market) atau string ("NBA/total_under" atau
    "NBA / total_under").
  kalibrasi_w: dict | None — rekomendasi_w; None berarti modul
    kalibrasi belum tersedia (bukan "tidak ada rekomendasi").
  usulan: list | None — hasilkan_usulan; None berarti modul usulan
    belum tersedia; list kosong berarti tidak ada aturan yang terpicu.
  n_settled, n_pending, n_dikeluarkan: int.
  n_hasil_tidak_dikenal, n_tiket: int | None (bila diketahui).
  dibuat_pada: str | None — waktu ISO laporan dirakit.
  catatan_sumber: str | None — konteks sumber (mis. file replay).
  modul_belum_tersedia: list[str] — modul Langkah 6 yang belum ada
    saat laporan dirakit (mis. ["calibration"]).

LABEL SUMBER: bila sumber_data "sintetis" atau "replay", label
"DATA SINTETIS — BUKAN HASIL NYATA" / "DATA REPLAY BACKTEST — BUKAN
TIKET NYATA" SELALU muncul di judul, di bagian Ringkasan, dan di
bagian Keterbatasan — tidak boleh ada keluaran tanpa label itu.

ISTILAH: "Skor Brier" dijelaskan sekali di laporan (ukuran seberapa
tepat tebakan peluang; makin kecil makin bagus; 0 = sempurna).
"Tebakan dasar" = selalu menebak peluang menang rata-rata kelompok
(brier_climatology). EV dalam persen per unit modal.
"""

from __future__ import annotations

import math
from datetime import datetime

FORMAT = "learning_report"
FORMAT_VERSION = 1

LABEL_SINTETIS = "DATA SINTETIS — BUKAN HASIL NYATA"
LABEL_REPLAY = "DATA REPLAY BACKTEST — BUKAN TIKET NYATA"

_BULAN = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "Mei",
    "Jun",
    "Jul",
    "Agu",
    "Sep",
    "Okt",
    "Nov",
    "Des",
]

# (sport, market) -> label Indonesia. Sport dinormalisasi huruf kecil;
# market dicocokkan apa adanya. Kunci tak dikenal ditampilkan mentah.
_LABEL_PASAR = {
    ("nba", "total_under"): "NBA — Total Under",
    ("nba", "moneyline"): "NBA — Menang/Kalah",
    ("soccer", "1x2"): "Bola — 1X2 (kandang/seri/tandang)",
    ("soccer", "moneyline"): "Bola — Menang/Kalah",
    ("soccer", "over_under"): "Bola — Over/Under gol",
    ("soccer", "totals"): "Bola — Over/Under gol",
    ("soccer", "btts"): "Bola — Kedua tim cetak gol (BTTS)",
    ("soccer", "btts_yes"): "Bola — Kedua tim cetak gol (BTTS)",
}

# Selisih Brier di bawah ini dianggap "hampir sama" (tampilan saja —
# bukan ambang strategi; selisih sekecil ini adalah noise pada sampel
# kecil, jadi laporan tidak mengklaim "lebih jago" dari selisih itu).
_EPSILON_BRIER = 0.005

# Label bukti usulan (kunci dict bukti -> label tampilan).
_LABEL_BUKTI = {
    "brier_model": "Brier model",
    "brier_market": "Brier pasar",
    "brier_final": "Brier gabungan",
    "brier_climatology": "Brier tebakan dasar",
    "ev_prediksi_rata2": "EV prediksi rata-rata",
    "ev_terealisasi_rata2": "EV nyata rata-rata",
    "selisih_ev": "Selisih EV",
    "ev_gap_warn": "Batas peringatan selisih EV",
}


def _angka(nilai) -> float | None:
    """Ubah nilai jadi float hingga; None bila bukan angka (bool ditolak)."""
    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        return None
    if not math.isfinite(nilai):
        return None
    return float(nilai)


def _peluang(nilai) -> float | None:
    """Ubah nilai jadi peluang 0-1; None bila bukan angka / di luar 0-1."""
    angka = _angka(nilai)
    if angka is None or not 0.0 <= angka <= 1.0:
        return None
    return angka


def _bilangan_bulat(nilai) -> int | None:
    """Ubah nilai jadi int; None bila bukan bilangan bulat."""
    if isinstance(nilai, bool) or not isinstance(nilai, int):
        return None
    return nilai


def _fmt_brier(nilai) -> str | None:
    """Format skor Brier 4 desimal koma: 0.198308 -> "0,1983"."""
    angka = _angka(nilai)
    if angka is None:
        return None
    return f"{angka:.4f}".replace(".", ",")


def _fmt_persen(nilai, desimal: int = 1) -> str | None:
    """Format peluang 0-1 jadi persen: 0.77191 -> "77,2%"."""
    angka = _peluang(nilai)
    if angka is None:
        return None
    return f"{angka * 100.0:.{desimal}f}%".replace(".", ",")


def _fmt_ev(nilai) -> str | None:
    """Format EV fraksi jadi persen bertanda: 0.1364 -> "+13,6%"."""
    angka = _angka(nilai)
    if angka is None:
        return None
    return f"{angka * 100.0:+.{1}f}%".replace(".", ",")


def _fmt_bobot(nilai) -> str | None:
    """Format bobot w 2 desimal koma: 0.75 -> "0,75"."""
    angka = _angka(nilai)
    if angka is None:
        return None
    return f"{angka:.2f}".replace(".", ",")


def _jam_singkat(nilai) -> str | None:
    """Format waktu ISO jadi "22 Nov 2026 14:03 UTC"; gagal -> mentah/None."""
    if not isinstance(nilai, str) or not nilai:
        return None
    try:
        parsed = datetime.fromisoformat(nilai.replace("Z", "+00:00"))
    except ValueError:
        return nilai
    if parsed.tzinfo is None:
        zona = ""
    elif parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0:
        zona = " UTC"
    else:
        zona = f" UTC{parsed.strftime('%z')[:3]}:{parsed.strftime('%z')[3:]}"
    tanggal = f"{parsed.day} {_BULAN[parsed.month - 1]} {parsed.year}"
    return f"{tanggal} {parsed.hour:02d}:{parsed.minute:02d}{zona}"


def _label_sumber(sumber_data: str | None) -> str | None:
    """Label peringatan sumber non-ledger; None untuk ledger/tak dikenal."""
    if sumber_data == "sintetis":
        return LABEL_SINTETIS
    if sumber_data == "replay":
        return LABEL_REPLAY
    return None


def _urai_kunci_pasar(kunci) -> tuple[str | None, str | None]:
    """Urai kunci ringkasan per pasar jadi (sport, market).

    Menerima tuple/list 2 elemen, atau string "sport/market" /
    "sport / market". Gagal -> (None, None).
    """
    if isinstance(kunci, (tuple, list)) and len(kunci) == 2:
        sport, market = kunci
        return (
            str(sport) if sport is not None else None,
            str(market) if market is not None else None,
        )
    if isinstance(kunci, str) and "/" in kunci:
        sport, market = kunci.split("/", 1)
        return sport.strip() or None, market.strip() or None
    return None, None


def _label_pasar(kunci) -> str:
    """Label Indonesia satu pasar dari kunci ringkasan."""
    sport, market = _urai_kunci_pasar(kunci)
    if sport is not None and market is not None:
        label = _LABEL_PASAR.get((sport.lower(), market.lower()))
        if label is not None:
            return label
        return f"{sport} — {market}"
    return str(kunci)


def _banding_lebih_baik(nilai_a, nilai_b) -> str | None:
    """Bandingkan dua skor Brier (lebih kecil lebih baik).

    Mengembalikan "a" bila a lebih baik, "b" bila b lebih baik, "sama"
    bila selisih < epsilon, None bila salah satu tidak ada.
    """
    a = _angka(nilai_a)
    b = _angka(nilai_b)
    if a is None or b is None:
        return None
    if abs(a - b) < _EPSILON_BRIER:
        return "sama"
    return "a" if a < b else "b"


class _Laporan:
    """Perakit laporan belajar dari data hasil (dict kontrak di atas)."""

    def __init__(self, data: dict):
        """Simpan data + siapkan penampung bagian."""
        self.d = data if isinstance(data, dict) else {}
        self.bagian: list[dict] = []
        self.sumber = self.d.get("sumber_data")
        self.label = _label_sumber(self.sumber)
        self.ada_data = self.d.get("ada_data") is True
        ringkasan = self.d.get("ringkasan")
        self.ringkasan = ringkasan if isinstance(ringkasan, dict) else None
        per_pasar = self.d.get("ringkasan_per_pasar")
        self.per_pasar = per_pasar if isinstance(per_pasar, dict) else {}
        self.kalibrasi = self.d.get("kalibrasi_w")
        if not isinstance(self.kalibrasi, dict):
            self.kalibrasi = None
        self.usulan = self.d.get("usulan")

    # -- utilitas -----------------------------------------------------

    def _tambah(self, judul: str, baris: list[str]) -> None:
        """Tambah satu bagian (judul + daftar baris teks)."""
        self.bagian.append({"heading": judul, "lines": list(baris)})

    def _render_teks(self) -> str:
        """Gabung bagian jadi satu teks (judul # lalu ## per bagian)."""
        potongan = []
        for i, bagian in enumerate(self.bagian):
            awalan = "#" if i == 0 else "##"
            potongan.append(f"{awalan} {bagian['heading']}")
            potongan.extend(bagian["lines"])
            potongan.append("")
        return "\n".join(potongan).rstrip() + "\n"

    # -- perakitan ----------------------------------------------------

    def bangun(self) -> str:
        """Rakit semua bagian; kembalikan teks laporan lengkap."""
        self._bagian_judul()
        if not self.ada_data or self.ringkasan is None:
            self._bagian_belum_ada_data()
            return self._render_teks()
        self._bagian_ringkasan()
        self._bagian_per_pasar()
        self._bagian_kalibrasi_w()
        self._bagian_usulan()
        self._bagian_keterbatasan()
        return self._render_teks()

    # -- bagian: judul + belum ada data --------------------------------

    def _bagian_judul(self) -> None:
        """Judul + label sumber (bila sintetis/replay) + waktu dibuat."""
        judul = "Laporan Belajar Mesin Parlay"
        if self.label is not None:
            judul += f" — {self.label}"
        baris: list[str] = []
        if self.label is not None:
            baris.append(self.label + ".")
            if self.sumber == "sintetis":
                baris.append(
                    "Angka di laporan ini berasal dari data buatan untuk "
                    "demo dan tes — bukan hasil taruhan nyata."
                )
            else:
                baris.append(
                    "Angka di laporan ini berasal dari prediksi model atas "
                    "laga lama (backtest) — bukan tiket nyata."
                )
        dibuat = _jam_singkat(self.d.get("dibuat_pada"))
        if dibuat:
            baris.append(f"Laporan ini dibuat {dibuat}.")
        if self.sumber == "ledger":
            baris.append("Sumber data: catatan tiket di ledger.")
        elif self.sumber == "replay":
            baris.append("Sumber data: hasil backtest model (replay).")
        elif self.sumber == "sintetis":
            baris.append("Sumber data: kaki sintetis (buatan).")
        self._tambah(judul, baris)

    def _bagian_belum_ada_data(self) -> None:
        """Laporan singkat jujur bila belum ada hasil tercatat.

        Tidak memuat angka hasil apa pun — karena memang belum ada yang
        bisa dihitung.
        """
        baris = ["Belum ada hasil tercatat — belum ada yang bisa dipelajari."]
        pesan = self.d.get("pesan")
        if isinstance(pesan, str) and pesan:
            baris.append(pesan)
        n_pending = _bilangan_bulat(self.d.get("n_pending"))
        if n_pending:
            baris.append(
                f"Ada {n_pending} kaki yang masih menunggu hasil " "(belum selesai)."
            )
        baris.append("")
        baris.append("Yang perlu terjadi dulu:")
        baris.append(
            "- Catat tiket PAPER ke ledger (perintah: "
            "python3 cli.py log --file tiket.json)."
        )
        baris.append(
            "- Setelah laganya selesai, selesaikan tiketnya (perintah: "
            "python3 cli.py log --settle <id_tiket> --result WIN/LOSS "
            "--leg-result <id_kaki>=WIN/LOSS)."
        )
        baris.append(
            "- Setelah ada kaki yang selesai, jalankan lagi perintah ini: "
            "python3 cli.py belajar."
        )
        self._tambah("Ringkasan", baris)

    # -- bagian: ringkasan ----------------------------------------------

    def _bagian_ringkasan(self) -> None:
        """Ringkasan singkat: kaki settled, menang, Brier, EV."""
        assert self.ringkasan is not None
        r = self.ringkasan
        baris: list[str] = []
        if self.label is not None:
            baris.append(f"{self.label}.")
        n = _bilangan_bulat(r.get("n")) or 0
        win_rate = _peluang(r.get("win_rate"))
        if win_rate is not None and n > 0:
            menang = round(win_rate * n)
            baris.append(
                f"Dari {n} kaki yang sudah selesai, {menang} menang "
                f"({_fmt_persen(win_rate)}) dan {n - menang} kalah."
            )
        else:
            baris.append(f"Kaki yang sudah selesai: {n}.")
        n_pending = _bilangan_bulat(self.d.get("n_pending"))
        n_dikeluarkan = _bilangan_bulat(self.d.get("n_dikeluarkan"))
        if n_pending:
            baris.append(
                f"Selain itu, {n_pending} kaki masih menunggu hasil "
                "(tidak masuk hitungan di bawah)."
            )
        if n_dikeluarkan:
            baris.append(f"{n_dikeluarkan} kaki VOID/PUSH dikeluarkan dari hitungan.")
        n_tiket = _bilangan_bulat(self.d.get("n_tiket"))
        if n_tiket:
            baris.append(f"Kaki-kaki itu berasal dari {n_tiket} tiket.")
        baris.append("")
        baris.append(
            "Skor Brier mengukur seberapa tepat tebakan peluang — makin "
            "kecil makin bagus (0 berarti sempurna; 0,25 berarti sama "
            "dengan menebak 50% terus-menerus)."
        )
        brier_model = _fmt_brier(r.get("brier_model"))
        brier_market = _fmt_brier(r.get("brier_market"))
        brier_final = _fmt_brier(r.get("brier_final"))
        brier_clim = _fmt_brier(r.get("brier_climatology"))
        if brier_model is not None:
            baris.append(f"- Brier model: {brier_model}.")
        else:
            baris.append("- Brier model: tidak ada datanya.")
        if brier_market is not None:
            baris.append(f"- Brier pasar: {brier_market}.")
        else:
            baris.append(
                "- Brier pasar: tidak ada datanya (tidak ada harga pasar "
                "yang tercatat)."
            )
        if brier_final is not None:
            baris.append(f"- Brier gabungan (model + pasar): {brier_final}.")
        if brier_clim is not None:
            baris.append(
                f"- Brier tebakan dasar (sekadar menebak peluang menang "
                f"rata-rata): {brier_clim}."
            )
        hasil_banding = _banding_lebih_baik(r.get("brier_model"), r.get("brier_market"))
        if hasil_banding == "a":
            baris.append("Secara keseluruhan, model lebih tepat dari pasar.")
        elif hasil_banding == "b":
            baris.append("Secara keseluruhan, pasar lebih tepat dari model.")
        elif hasil_banding == "sama":
            baris.append("Secara keseluruhan, model dan pasar hampir sama tepatnya.")
        else:
            baris.append(
                "Model dan pasar belum bisa dibandingkan — salah satunya "
                "tidak ada datanya."
            )
        hasil_clim = _banding_lebih_baik(
            r.get("brier_model"), r.get("brier_climatology")
        )
        if hasil_clim == "b":
            baris.append(
                "Perhatian: model kalah dari tebakan dasar — sekadar "
                "menebak peluang menang rata-rata lebih tepat dari model."
            )
        ev_prediksi = _fmt_ev(r.get("ev_prediksi_rata2"))
        ev_nyata = _fmt_ev(r.get("ev_terealisasi_rata2"))
        if ev_prediksi is not None or ev_nyata is not None:
            baris.append("")
            baris.append(
                "EV (nilai harapan) di bawah ini per unit modal, bila tiap "
                "kaki dimainkan satuan — bukan untung/rugi tiket parlay."
            )
            if ev_prediksi is not None:
                baris.append(f"- EV yang diperkirakan: {ev_prediksi}.")
            if ev_nyata is not None:
                baris.append(f"- EV yang benar-benar terjadi: {ev_nyata}.")
        self._tambah("Ringkasan", baris)

    # -- bagian: per pasar ----------------------------------------------

    def _bagian_per_pasar(self) -> None:
        """Per pasar: di mana model lebih jago, di mana tidak (+ n)."""
        baris: list[str] = []
        if not self.per_pasar:
            baris.append("Tidak ada ringkasan per pasar.")
            self._tambah("Per pasar", baris)
            return
        for kunci in sorted(self.per_pasar, key=_label_pasar):
            entri = self.per_pasar[kunci]
            if not isinstance(entri, dict):
                continue
            label = _label_pasar(kunci)
            n = _bilangan_bulat(entri.get("n")) or 0
            baris.append(f"### {label} ({n} kaki)")
            win_rate = _peluang(entri.get("win_rate"))
            if win_rate is not None and n > 0:
                menang = round(win_rate * n)
                baris.append(
                    f"- Menang {menang} dari {n} kaki " f"({_fmt_persen(win_rate)})."
                )
            brier_model = _fmt_brier(entri.get("brier_model"))
            brier_market = _fmt_brier(entri.get("brier_market"))
            brier_clim = _fmt_brier(entri.get("brier_climatology"))
            if brier_model is not None:
                baris.append(f"- Brier model: {brier_model}.")
            if brier_market is not None:
                baris.append(f"- Brier pasar: {brier_market}.")
            else:
                baris.append("- Brier pasar: tidak ada datanya.")
            if brier_clim is not None:
                baris.append(f"- Brier tebakan dasar: {brier_clim}.")
            hasil_banding = _banding_lebih_baik(
                entri.get("brier_model"), entri.get("brier_market")
            )
            if hasil_banding == "a":
                baris.append("- Di pasar ini, model lebih jago dari pasar.")
            elif hasil_banding == "b":
                baris.append("- Di pasar ini, pasar lebih jago dari model.")
            elif hasil_banding == "sama":
                baris.append("- Di pasar ini, model dan pasar hampir sama jagonya.")
            else:
                baris.append(
                    "- Model dan pasar belum bisa dibandingkan di pasar "
                    "ini (tidak ada harga pasar)."
                )
            hasil_clim = _banding_lebih_baik(
                entri.get("brier_model"), entri.get("brier_climatology")
            )
            if hasil_clim == "b":
                baris.append(
                    "- Model kalah dari tebakan dasar di pasar ini — "
                    "pasar ini perlu ditinjau."
                )
            elif hasil_clim == "a":
                baris.append("- Model lebih baik dari tebakan dasar di pasar ini.")
            elif hasil_clim == "sama":
                baris.append(
                    "- Model sama dengan tebakan dasar di pasar ini "
                    "(selisihnya terlalu kecil untuk disimpulkan)."
                )
            ev_prediksi = _fmt_ev(entri.get("ev_prediksi_rata2"))
            ev_nyata = _fmt_ev(entri.get("ev_terealisasi_rata2"))
            if ev_prediksi is not None and ev_nyata is not None:
                baris.append(
                    f"- EV yang diperkirakan {ev_prediksi}, EV yang "
                    f"benar-benar terjadi {ev_nyata}."
                )
            if n < 20:
                baris.append(
                    "- Sampel masih kecil (di bawah 20 kaki) — kesimpulan "
                    "untuk pasar ini belum kuat."
                )
        self._tambah("Per pasar", baris)

    # -- bagian: kalibrasi w ----------------------------------------------

    def _bagian_kalibrasi_w(self) -> None:
        """Kalibrasi bobot model (w): saat ini, rekomendasi, status."""
        baris: list[str] = []
        if self.kalibrasi is None:
            baris.append(
                "Kalibrasi bobot model (w) belum bisa dihitung — modul "
                "kalibrasi belum tersedia."
            )
            self._tambah("Kalibrasi bobot model (w)", baris)
            return
        k = self.kalibrasi
        baris.append(
            "Bobot model (w) menentukan seberapa besar suara model dalam "
            "peluang akhir: peluang akhir = w × peluang model + "
            "(1 − w) × peluang pasar."
        )
        w_saat_ini = _fmt_bobot(k.get("w_saat_ini"))
        if w_saat_ini is not None:
            baris.append(f"- Bobot model sekarang: {w_saat_ini}.")
        n = _bilangan_bulat(k.get("n"))
        if n is not None:
            baris.append(
                f"- Kaki yang dipakai kalibrasi (punya peluang model dan "
                f"pasar): {n}."
            )
        brier_saat_ini = _fmt_brier(k.get("brier_blend_w_saat_ini"))
        if brier_saat_ini is not None:
            baris.append(f"- Brier gabungan dengan bobot sekarang: {brier_saat_ini}.")
        w_rekomendasi = k.get("w_rekomendasi")
        if k.get("cukup_data") is True and w_rekomendasi is not None:
            w_rek = _fmt_bobot(w_rekomendasi)
            brier_rek = _fmt_brier(k.get("brier_blend_w_rekomendasi"))
            if _angka(w_rekomendasi) == _angka(k.get("w_saat_ini")):
                baris.append(
                    "- Bobot yang sekarang sudah yang terbaik menurut "
                    "data — tidak ada perubahan yang diusulkan."
                )
            else:
                baris.append(f"- Rekomendasi: ubah bobot model menjadi {w_rek}.")
                if brier_rek is not None:
                    baris.append(
                        f"- Brier gabungan dengan bobot rekomendasi: " f"{brier_rek}."
                    )
                baris.append(
                    "Rekomendasi ini belum diterapkan — menunggu " "persetujuanmu."
                )
        else:
            baris.append("- Belum ada rekomendasi bobot baru.")
        alasan = k.get("alasan")
        if isinstance(alasan, str) and alasan:
            baris.append(f"- Alasan (catatan mesin): {alasan}.")
        baris.append(
            "Bobot tidak pernah berubah sendiri — perubahan hanya terjadi "
            "setelah kamu menyetujuinya."
        )
        self._tambah("Kalibrasi bobot model (w)", baris)

    # -- bagian: usulan ---------------------------------------------------

    def _bagian_usulan(self) -> None:
        """Usulan yang menunggu persetujuan (judul + bukti + n + keyakinan)."""
        baris: list[str] = []
        if self.usulan is None:
            baris.append(
                "Usulan belajar belum tersedia — modul usulan belum " "terpasang."
            )
            self._tambah("Usulan yang menunggu persetujuan", baris)
            return
        if not isinstance(self.usulan, list) or not self.usulan:
            baris.append(
                "Tidak ada usulan saat ini — tidak ada aturan belajar "
                "yang terpicu dari data ini."
            )
            self._tambah("Usulan yang menunggu persetujuan", baris)
            return
        baris.append(
            "Usulan di bawah ini HANYA usulan — tidak ada yang berubah "
            "sampai kamu menyetujuinya."
        )
        for item in self.usulan:
            if not isinstance(item, dict):
                continue
            usulan_id = item.get("id") or "?"
            judul = item.get("judul") or "Usulan tanpa judul"
            baris.append(f"### [{usulan_id}] {judul}")
            isi = item.get("isi")
            if isinstance(isi, str) and isi:
                baris.append(f"- {isi}")
            bukti = item.get("bukti")
            teks_bukti = _format_bukti(bukti)
            if teks_bukti:
                baris.append(f"- Bukti: {teks_bukti}.")
            n = _bilangan_bulat(item.get("n"))
            keyakinan = item.get("keyakinan")
            rincian = []
            if n is not None:
                rincian.append(f"sampel {n} kaki")
            if isinstance(keyakinan, str) and keyakinan:
                rincian.append(f"keyakinan {keyakinan}")
            status = item.get("status")
            if status == "menunggu_persetujuan":
                rincian.append("status: menunggu persetujuan")
            elif isinstance(status, str) and status:
                rincian.append(f"status: {status}")
            if rincian:
                baris.append("- " + "; ".join(rincian) + ".")
            aksi = item.get("aksi")
            if isinstance(aksi, str) and aksi:
                baris.append(f"- Yang diusulkan: {aksi}")
        self._tambah("Usulan yang menunggu persetujuan", baris)

    # -- bagian: keterbatasan ----------------------------------------------

    def _bagian_keterbatasan(self) -> None:
        """Keterbatasan jujur: sumber data, sampel, tanpa harga pasar."""
        baris: list[str] = []
        if self.label is not None:
            baris.append(f"- {self.label}.")
        if self.sumber == "sintetis":
            baris.append(
                "- Angka di laporan ini berasal dari data buatan untuk "
                "demo dan tes. Jangan dipakai untuk keputusan taruhan."
            )
        elif self.sumber == "replay":
            baris.append(
                "- Angka di laporan ini berasal dari prediksi backtest "
                "atas laga lama, bukan tiket nyata yang dipasang."
            )
            baris.append(
                "- Tidak ada harga pasar historis untuk laga-laga "
                "backtest, jadi perbandingan model-vs-pasar tidak "
                "tersedia di replay."
            )
            baris.append(
                "- Di replay, peluang akhir sama dengan peluang model "
                "(tanpa harga pasar, tidak ada yang digabung) — jadi "
                "Brier gabungan sama dengan Brier model."
            )
            catatan = self.d.get("catatan_sumber")
            if isinstance(catatan, str) and catatan:
                baris.append(f"- {catatan}")
        n = None
        if self.ringkasan is not None:
            n = _bilangan_bulat(self.ringkasan.get("n"))
        if n is not None and n < 50:
            baris.append(
                f"- Sampel masih kecil ({n} kaki) — kesimpulan belum "
                "kuat. Kalibrasi bobot butuh sampel yang lebih besar."
            )
        if self.ringkasan is not None and self.ringkasan.get("brier_market") is None:
            baris.append(
                "- Tidak ada harga pasar yang tercatat, jadi model dan "
                "pasar belum bisa dibandingkan."
            )
        baris.append(
            "- Skor Brier mengukur ketepatan peluang, bukan untung/rugi "
            "uang. EV per kaki adalah diagnostik bila kaki dimainkan "
            "satuan, bukan hasil tiket parlay."
        )
        baris.append(
            "- Tidak ada usulan di laporan ini yang diterapkan otomatis; "
            "semua menunggu persetujuanmu."
        )
        modul_hilang = self.d.get("modul_belum_tersedia")
        if isinstance(modul_hilang, list) and modul_hilang:
            baris.append(
                "- Modul yang belum tersedia saat laporan dibuat: "
                + ", ".join(str(m) for m in modul_hilang)
                + " — bagiannya ditandai di atas."
            )
        self._tambah("Keterbatasan", baris)


def _format_bukti(bukti) -> str | None:
    """Format dict bukti usulan jadi satu baris angka yang bisa dibaca.

    Kunci yang dikenal diberi label Indonesia; kunci lain ditampilkan
    "kunci: nilai" apa adanya. Kunci "pasar" dan "n" dilewati (sudah
    tampil di judul / rincian sampel).
    """
    if not isinstance(bukti, dict) or not bukti:
        return None
    potongan: list[str] = []
    for kunci in sorted(bukti):
        if kunci in ("pasar", "n"):
            continue
        nilai = bukti[kunci]
        label = _LABEL_BUKTI.get(kunci, str(kunci))
        if kunci.startswith("brier_"):
            teks = _fmt_brier(nilai)
            potongan.append(f"{label} {teks}" if teks else f"{label}: tidak ada")
        elif kunci.startswith("ev_") or kunci == "selisih_ev":
            teks = _fmt_ev(nilai)
            potongan.append(f"{label} {teks}" if teks else f"{label}: tidak ada")
        elif isinstance(nilai, bool):
            potongan.append(f"{label}: {'ya' if nilai else 'tidak'}")
        elif isinstance(nilai, (int, float, str)):
            potongan.append(f"{label}: {nilai}")
    return "; ".join(potongan) if potongan else None


def render_laporan_belajar(data: dict) -> str:
    """Render laporan belajar dari data hasil (kontrak di docstring modul).

    Fungsi murni: tidak membaca file, tidak memanggil API. Bila
    ``data`` bukan dict atau tidak ada data, kembalikan laporan
    "belum ada hasil tercatat" yang jujur — tidak pernah mengarang
    angka.
    """
    if not isinstance(data, dict):
        data = {}
    return _Laporan(data).bangun()
