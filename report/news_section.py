"""Render bagian "Berita" laporan NBA — modul news.

Fungsi di sini murni (tanpa network, tanpa config): menerima blok
`news` artefak nba_analysis dan mengembalikan (judul, baris) siap
tambah ke laporan via `_Laporan._tambah`. Bahasa Indonesia sederhana;
judul berita ditampilkan apa adanya dalam bahasa Inggris (tidak
diterjemahkan mesin — terjemahan bisa mengubah arti).

TITIK PENYISIPAN (untuk koordinator — file ini TIDAK menyentuh
report/nba_report.py sendiri agar tidak bentrok dengan worker lain):
  1. Di `report/nba_report.py`, method `_Laporan.bangun()` (baris
     370), sisipkan SATU BARIS pemanggilan setelah baris 378
     (`self._bagian_cedera()`) dan sebelum baris 379
     (`self._bagian_market()`):
         self._bagian_berita()
     Berita ditaruh sesudah Cedera karena keduanya konteks skuad
     (cedera terkonfirmasi dulu, berita sebagai bahan bacaan),
     sebelum Market/kaki yang berisi angka.
  2. Tambahkan method `_bagian_berita` di kelas `_Laporan`, di antara
     `_bagian_cedera` (baris 778) dan `_bagian_market` (baris 844):
         def _bagian_berita(self) -> None:
             \"\"\"Berita terbaru kedua tim (konteks, bukan angka).\"\"\"
             from report.news_section import bagian_berita
             judul, baris = bagian_berita(
                 self.a.get("news"),
                 self._nama_tim("home"),
                 self._nama_tim("away"),
             )
             self._tambah(judul, baris)
  3. (Opsional, polish) Di `_JENIS_PERUBAHAN` (baris 115) tambahkan
     `"news": "berita baru"` agar perubahan kind "news" dari recheck
     tampil sebagai "[berita baru]", bukan "[news]". Tanpa ini pun
     laporan tidak rusak (`_JENIS_PERUBAHAN.get` punya fallback ke
     kind mentah).
"""

from __future__ import annotations

from datetime import datetime

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


def _jam_singkat(nilai) -> str | None:
    """Format waktu ISO jadi "22 Nov 2026 14:03 UTC"; gagal -> None.

    Cermin `_jam_singkat` di report/nba_report.py (tidak diimpor
    karena fungsi itu privat di modul lain).
    """
    if not isinstance(nilai, str) or not nilai:
        return None
    try:
        parsed = datetime.fromisoformat(nilai.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        zona = ""
    elif parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0:
        zona = " UTC"
    else:
        zona = f" UTC{parsed.strftime('%z')[:3]}:{parsed.strftime('%z')[3:]}"
    tanggal = f"{parsed.day} {_BULAN[parsed.month - 1]} {parsed.year}"
    return f"{tanggal} {parsed.hour:02d}:{parsed.minute:02d}{zona}"


def _teks_item(item: dict) -> list[str]:
    """Baris teks untuk satu berita (judul + ringkasan + sumber/jam)."""
    judul = item.get("headline") or "(judul tidak tercatat)"
    if item.get("type") == "Media":
        judul = f"{judul} (video)"
    baris = [f"- {judul}"]
    ringkasan = item.get("description")
    if isinstance(ringkasan, str) and ringkasan.strip():
        baris.append(f"  {ringkasan.strip()}")
    keterangan: list[str] = []
    sumber = item.get("source")
    if isinstance(sumber, str) and sumber:
        keterangan.append(sumber)
    terbit = _jam_singkat(item.get("published"))
    if terbit:
        keterangan.append(f"terbit {terbit}")
    if keterangan:
        baris.append("  (" + ", ".join(keterangan) + ")")
    url = item.get("url")
    if isinstance(url, str) and url:
        baris.append(f"  Baca: {url}")
    return baris


def bagian_berita(
    news: dict | None, nama_kandang: str, nama_tandang: str
) -> tuple[str, list[str]]:
    """Render bagian Berita dari blok news artefak.

    news: blok `news` artefak nba_analysis (atau None bila artefak
    lama tanpa blok itu). nama_kandang/nama_tandang: nama tim untuk
    kalimat 'tidak ada berita'. Mengembalikan (judul, baris) — judul
    selalu "Berita". Empat keadaan dibedakan dengan jujur: ada
    berita, tidak ada berita, gagal ambil, dan artefak lama tanpa
    blok berita.
    """
    judul = "Berita"
    if news is None:
        return judul, [
            "Berita tidak tersedia di artefak ini (analisis dibuat "
            "sebelum modul berita ada)."
        ]
    if not isinstance(news, dict):
        return judul, ["Berita tidak bisa dibaca (bentuk data tidak dikenal)."]
    status = news.get("status")
    items = [item for item in (news.get("items") or []) if isinstance(item, dict)]
    if status == "ok":
        baris: list[str] = [
            "Berita terbaru tentang kedua tim — bahan bacaan sebelum "
            "pasang (bukan angka, tidak memengaruhi hitungan)."
        ]
        for item in items:
            baris.extend(_teks_item(item))
        if not items:
            # status ok tapi items kosong = data tidak konsisten;
            # katakan apa adanya, jangan pura-pura ada berita.
            baris.append("Tidak ada berita yang tercatat.")
        return judul, baris
    if status == "kosong":
        baris = [
            f"Tidak ada berita terbaru tentang {nama_tandang} atau {nama_kandang}."
        ]
        dicek = _jam_singkat(news.get("fetched_at"))
        sumber = news.get("sources") or []
        if dicek or sumber:
            keterangan = (
                ", ".join(str(s) for s in sumber if s) or "sumber tidak tercatat"
            )
            baris.append(
                f"(Dicek dari {keterangan}" + (f", {dicek}" if dicek else "") + ".)"
            )
        return judul, baris
    if status == "gagal":
        baris = [
            "Berita tidak bisa diambil saat analisis dibuat — cek "
            "sendiri berita terbaru sebelum pasang."
        ]
        error = news.get("error")
        if isinstance(error, str) and error and error != "tidak_diambil":
            baris.append(f"(Catatan mesin: {error}.)")
        return judul, baris
    return judul, [f"Berita tidak bisa dibaca (status tidak dikenal: {status!r})."]
