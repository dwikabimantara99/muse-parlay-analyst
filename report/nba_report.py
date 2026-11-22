"""Laporan lengkap per laga NBA (Tahap 3 Langkah 3).

Satu laga -> satu teks laporan Bahasa Indonesia sehari-hari, tanpa
jargon, dari artefak ``nba_analysis`` (format_version 1) dan — bila
diberikan — laporan ``nba_recheck``. Modul ini MURNI RENDER: tidak ada
fetch, tidak ada simulasi ulang, tidak ada panggilan Odds API, dan
tidak ada angka yang ditebak. Datum yang tidak ada di artefak ditulis
"tidak terverifikasi" dan dicatat di daftar kekurangan laporan.

Isi laporan (urut): judul + status, ringkasan, data tim, pemain kunci,
proyeksi total, kabar pemain (cedera/ketersediaan), bursa & harga
pasar, kaki Asuransi & Utama, 5 laga terakhir, 5 pertemuan terakhir,
kandang vs tandang, simulasi 100.000 pertandingan (+ skenario skuad),
anomali, "Kenapa beda?" (bila |model - pasar| > 8 poin — ambang dari
playstyle.yaml lewat engine/anomaly.py — atau artefak menandai
kenapa_beda_required), cek ulang (bila recheck diberikan), sumber
data, dan daftar yang belum bisa dipastikan.

SPESIFIKASI WIRING (untuk koordinator — subcommand ``cli.py laporan``):
  from report import nba_report as nba_report_mod

  # analysis: dict artefak nba_analysis (boleh dari _ambil_nba_analysis
  # yang sudah ada di cli.py — menerima artefak langsung atau output
  # analyze + --match). recheck: dict laporan nba_recheck (opsional,
  # dari file --recheck; match_id harus sama dengan analysis).
  teks = nba_report_mod.render_nba_report(analysis, recheck=None)
  data = nba_report_mod.render_nba_report_json(analysis, recheck=None)
  # data: {"format": "nba_report", "format_version": 1, "match_id",
  #   "status", "generated_from", "sections": [{"heading", "lines"}],
  #   "tidak_terverifikasi": [...], "text": <teks yang sama>}
  # CLI yang disarankan: cli.py laporan --analysis <file>
  #   [--match <id>] [--recheck <file>] [--out <file>] [--json]
  #   (cetak teks ke stdout atau --out; --json menulis data di atas).
  # Exit code yang disarankan: 0 sukses, 2 bila file tidak bisa dibaca
  # atau artefak tidak valid (meniru cmd_recheck).
"""

from __future__ import annotations

import json
import math
from datetime import datetime

from engine import anomaly as anomaly_mod

FORMAT = "nba_report"
FORMAT_VERSION = 1

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

_TIKET = {"insurance": "Asuransi", "main": "Utama"}
_STATUS_ARTEFAK = {
    "OK": "Lengkap",
    "HOLD": "Ditahan",
    "DATA_INCOMPLETE": "Data tidak lengkap",
}
_STATUS_PEMAIN = {
    "OUT": "tidak main",
    "DOUBTFUL": "diragukan tampil",
    "QUESTIONABLE": "belum pasti tampil",
    "PROBABLE": "kemungkinan besar tampil",
    "AVAILABLE": "tersedia",
}
# Skema recheck memakai "NO_GO" (garis bawah); "NO-GO" diterima juga.
_VERDIK_TIKET = {
    "GO": "BOLEH PASANG",
    "NO_GO": "JANGAN PASANG",
    "NO-GO": "JANGAN PASANG",
}
_VERDIK_KAKI = {
    "TETAP_OK": "Tetap OK",
    "PERHATIAN": "Perhatian",
    "JANGAN_PASANG": "Jangan pasang",
    "DATA_INCOMPLETE": "Data tidak lengkap",
}
_JENIS_PERUBAHAN = {
    "injury": "cedera",
    "price": "harga",
    "market_line": "garis market",
    "stale": "data basi",
    "fetch_error": "gagal ambil data",
}
# Arti nama skenario standar — selaras _skenario_standar di
# engine/nba_sim.py: missing_1 = (1 kandang, 0 tandang) pemain inti
# TAMBAHAN yang absen; missing_2 = (1, 1); missing_4 = (2, 2).
# Angka di nama adalah pemain inti tambahan, BUKAN total pemain absen.
_SKENARIO = {
    "full": "Semua pemain tersedia",
    "missing_1": "1 pemain inti kandang tambahan absen",
    "missing_2": "1 pemain inti tiap tim tambahan absen",
    "missing_4": "2 pemain inti tiap tim tambahan absen",
    "doubtful_out": "Semua pemain yang diragukan ikut absen",
}
# Urutan tampil status cedera (paling serius dulu).
_URUTAN_STATUS = {"OUT": 0, "DOUBTFUL": 1, "QUESTIONABLE": 2, "PROBABLE": 3}


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


def _fmt_poin(nilai, desimal: int = 1) -> str | None:
    """Format angka poin gaya Indonesia: 233.5 -> "233,5"; 219.0 -> "219"."""
    angka = _angka(nilai)
    if angka is None:
        return None
    if angka == int(angka):
        return str(int(angka))
    return f"{angka:.{desimal}f}".replace(".", ",")


def _fmt_persen(nilai, desimal: int = 1) -> str | None:
    """Format peluang 0-1 jadi persen: 0.77191 -> "77,2%"."""
    angka = _peluang(nilai)
    if angka is None:
        return None
    return f"{angka * 100.0:.{desimal}f}%".replace(".", ",")


def _fmt_sen(nilai) -> str | None:
    """Format harga sen: 68.5 -> "68,5¢"; 68.0 -> "68¢"."""
    angka = _angka(nilai)
    if angka is None:
        return None
    if angka == int(angka):
        return f"{int(angka)}¢"
    return f"{angka:.1f}¢".replace(".", ",")


def _fmt_usd(nilai) -> str | None:
    """Format dolar AS: 44048.56 -> "$44.049" (ribuan dipisah titik)."""
    angka = _angka(nilai)
    if angka is None:
        return None
    return f"${angka:,.0f}".replace(",", ".")


def _fmt_bpm(nilai) -> str | None:
    """Format BPM bertanda: 2.56 -> "+2,6"; -0.4 -> "-0,4"."""
    angka = _angka(nilai)
    if angka is None:
        return None
    return f"{angka:+.1f}".replace(".", ",")


def _tanggal_singkat(nilai) -> str | None:
    """Format tanggal YYYY-MM-DD jadi "22 Nov 2026"; gagal -> mentah/None."""
    if not isinstance(nilai, str) or not nilai:
        return None
    try:
        parsed = datetime.strptime(nilai[:10], "%Y-%m-%d")
    except ValueError:
        return nilai
    return f"{parsed.day} {_BULAN[parsed.month - 1]} {parsed.year}"


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


def _teks_alasan_cedera(entri: dict) -> str:
    """Klasifikasi alasan absen dalam kata sederhana + teks mentah sumber.

    Klasifikasi hanya dari kata kunci alasan/sumber — tidak ada
    terjemahan medis yang dikarang; teks asli sumber selalu ditampilkan.
    """
    alasan = entri.get("reason")
    teks = str(alasan) if isinstance(alasan, str) and alasan else ""
    rendah = teks.lower()
    # Kata kunci alasan didahulukan atas flag is_injury: data live
    # menunjukkan entri is_injury=True dengan alasan "G League -
    # Two-Way" (bukan cedera) — teks alasan yang menentukan.
    if "rest" in rendah:
        golongan = "istirahat"
    elif "personal" in rendah:
        golongan = "urusan pribadi"
    elif "two-way" in rendah or "g league" in rendah:
        golongan = "tugas liga pengembangan"
    elif "suspend" in rendah:
        golongan = "skorsing"
    elif entri.get("is_injury") is True:
        golongan = "cedera"
    elif teks:
        golongan = "alasan lain"
    else:
        return "alasan tidak tercatat"
    return f"{golongan} ({teks})" if teks else golongan


class _Laporan:
    """Perakit laporan satu laga dari artefak analisis (+ recheck)."""

    def __init__(self, analysis: dict, recheck: dict | None):
        """Simpan artefak + siapkan penampung bagian dan kekurangan."""
        self.a = analysis
        self.r = recheck
        self.bagian: list[dict] = []
        self.celah: list[str] = []
        inputs = analysis.get("inputs")
        self.inputs = inputs if isinstance(inputs, dict) else None
        sim = analysis.get("simulation")
        self.sim = sim if isinstance(sim, dict) else None
        market = analysis.get("market")
        self.market = market if isinstance(market, dict) else None
        legs = analysis.get("legs")
        self.legs = legs if isinstance(legs, list) else []
        injuries = analysis.get("injuries")
        self.injuries = injuries if isinstance(injuries, dict) else {}

    # -- utilitas -----------------------------------------------------

    def _tambah(self, judul: str, baris: list[str]) -> None:
        """Tambah satu bagian (judul + daftar baris teks)."""
        self.bagian.append({"heading": judul, "lines": list(baris)})

    def _celah(self, teks: str) -> None:
        """Catat satu kekurangan (dedup, urutan kemunculan dipertahankan)."""
        if teks not in self.celah:
            self.celah.append(teks)

    def _sumber(self, kind: str) -> list[dict]:
        """Entri artefak sources untuk satu data_kind (boleh kosong)."""
        hasil = []
        for entri in self.a.get("sources") or []:
            if isinstance(entri, dict) and entri.get("kind") == kind:
                hasil.append(entri)
        return hasil

    def _teks_sumber(self, kind: str) -> str:
        """Teks "(sumber: X, jenjang N, jam ...)" untuk satu data_kind."""
        entri_list = self._sumber(kind)
        if not entri_list:
            return " (sumber tidak tercatat di artefak)"
        bagian = []
        for entri in entri_list:
            jam = _jam_singkat(entri.get("time")) or "jam tidak tercatat"
            bagian.append(f"{entri.get('source')}, jenjang {entri.get('tier')}, {jam}")
        return " (sumber: " + "; ".join(bagian) + ")"

    def _blok_tim(self, sisi: str) -> dict | None:
        """Blok tim "home"/"away" dari inputs; None bila tidak ada."""
        if self.inputs is None:
            return None
        blok = self.inputs.get(sisi)
        return blok if isinstance(blok, dict) else None

    def _nama_tim(self, sisi: str) -> str:
        """Nama lengkap tim; fallback ke tricode."""
        blok = self._blok_tim(sisi)
        if blok is not None and isinstance(blok.get("team"), str) and blok["team"]:
            return blok["team"]
        tricode = self.a.get(f"{sisi}_tricode")
        return str(tricode) if tricode else sisi

    def _tricode(self, sisi: str) -> str:
        """Tricode tim; fallback ke nama sisi."""
        tricode = self.a.get(f"{sisi}_tricode")
        return str(tricode) if tricode else sisi

    def _median_total(self) -> float | None:
        """Median total dari simulasi; None bila tidak ada."""
        if self.sim is None:
            return None
        dist = self.sim.get("score_distribution") or {}
        total = dist.get("total") if isinstance(dist, dict) else None
        if not isinstance(total, dict):
            return None
        return _angka(total.get("median"))

    def _garis_utama(self) -> float | None:
        """Garis total utama market; None bila tidak ada."""
        if self.market is None:
            return None
        return _angka(self.market.get("main_total_line"))

    def _entri_cedera(self) -> list[dict]:
        """Entri cedera gabungan (urut: OUT dulu, lalu abjad nama)."""
        entri = self.injuries.get("entries") or []
        entri = [e for e in entri if isinstance(e, dict)]
        return sorted(
            entri,
            key=lambda e: (
                _URUTAN_STATUS.get(str(e.get("status") or "").upper(), 9),
                str(e.get("player") or ""),
            ),
        )

    def _status_pemain(self, nama: str) -> dict | None:
        """Entri cedera satu pemain (cocok nama persis); None bila sehat."""
        for entri in self._entri_cedera():
            if entri.get("player") == nama:
                return entri
        return None

    def _ringkasan_sim(self) -> dict:
        """inputs_summary simulasi (dict kosong bila tidak ada)."""
        if self.sim is None:
            return {}
        ringkasan = self.sim.get("inputs_summary")
        return ringkasan if isinstance(ringkasan, dict) else {}

    # -- perakitan ----------------------------------------------------

    def bangun(self) -> dict:
        """Rakit semua bagian; kembalikan dict laporan terstruktur + teks."""
        self._bagian_judul()
        self._bagian_ringkasan()
        self._bagian_data_tim()
        self._bagian_pemain_kunci()
        self._bagian_proyeksi()
        self._bagian_cedera()
        self._bagian_market()
        self._bagian_kaki()
        self._bagian_form5()
        self._bagian_h2h()
        self._bagian_kandang_tandang()
        self._bagian_simulasi()
        self._bagian_anomali()
        self._bagian_kenapa_beda()
        if self.r is not None:
            self._bagian_recheck()
        self._bagian_sumber()
        if self.celah:
            self._tambah(
                "Yang belum bisa dipastikan",
                [f"- {celah}" for celah in self.celah],
            )
        teks = self._render_teks()
        return {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "match_id": self.a.get("match_id"),
            "status": self.a.get("status"),
            "generated_from": self.a.get("generated_at"),
            "sections": self.bagian,
            "tidak_terverifikasi": list(self.celah),
            "text": teks,
        }

    def _render_teks(self) -> str:
        """Gabung bagian jadi satu teks (judul # lalu ## per bagian)."""
        potongan = []
        for i, bagian in enumerate(self.bagian):
            awalan = "#" if i == 0 else "##"
            potongan.append(f"{awalan} {bagian['heading']}")
            potongan.extend(bagian["lines"])
            potongan.append("")
        return "\n".join(potongan).rstrip() + "\n"

    # -- bagian: judul + ringkasan ------------------------------------

    def _bagian_judul(self) -> None:
        """Judul laga + tanggal + status data (+ spanduk bila bermasalah)."""
        tandang = self._nama_tim("away")
        kandang = self._nama_tim("home")
        tanggal = _tanggal_singkat(self.a.get("game_date")) or "tanggal tidak tercatat"
        baris = [f"Tanggal laga: {tanggal}."]
        mulai = _jam_singkat(self.a.get("start_time"))
        if mulai:
            baris.append(f"Jam mulai: {mulai}.")
        dibuat = _jam_singkat(self.a.get("generated_at"))
        if dibuat:
            baris.append(f"Laporan ini dibuat dari analisis {dibuat}.")
        status = self.a.get("status")
        baris.append(
            f"Status data: {_STATUS_ARTEFAK.get(status, status or 'tidak tercatat')}."
        )
        hilang = [str(m) for m in self.a.get("missing") or []]
        if status == "DATA_INCOMPLETE":
            baris.append("")
            baris.append(
                "DATA TIDAK LENGKAP — laporan ini belum bisa dipakai "
                "untuk memasang tiket."
            )
            if hilang:
                baris.append(
                    "Yang bermasalah (catatan mesin): " + "; ".join(hilang) + "."
                )
        elif status == "HOLD":
            baris.append("")
            baris.append(
                "DITAHAN — analisis belum siap dipakai. Periksa bagian "
                '"Yang belum bisa dipastikan" di bawah.'
            )
            if hilang:
                baris.append("Alasan (catatan mesin): " + "; ".join(hilang) + ".")
        self._tambah(f"Laporan Laga NBA: {tandang} vs {kandang}", baris)

    def _bagian_ringkasan(self) -> None:
        """Ringkasan singkat: median vs garis market + kedua kaki."""
        baris: list[str] = []
        median = self._median_total()
        garis = self._garis_utama()
        if median is not None and garis is not None:
            selisih = garis - median
            arah = (
                "market mengharap total lebih tinggi dari model"
                if selisih > 0
                else (
                    "model mengharap total lebih tinggi dari market"
                    if selisih < 0
                    else "model dan market sepakat soal total"
                )
            )
            baris.append(
                f"Model memperkirakan total tengah-tengah (median) "
                f"{_fmt_poin(median)} poin; pasar memasang garis "
                f"{_fmt_poin(garis)} — {arah} "
                f"(selisih {_fmt_poin(abs(selisih))} poin)."
            )
        elif median is not None:
            baris.append(
                f"Model memperkirakan total tengah-tengah (median) "
                f"{_fmt_poin(median)} poin; garis market tidak ada di artefak."
            )
            self._celah("Garis total market: tidak terverifikasi.")
        else:
            baris.append("Proyeksi total model: tidak terverifikasi.")
            self._celah("Proyeksi total model: tidak terverifikasi.")
        for kaki in self.legs:
            nama = _TIKET.get(kaki.get("ticket"), str(kaki.get("ticket") or "?"))
            garis_kaki = _angka(kaki.get("line"))
            if garis_kaki is None or not kaki.get("meets"):
                alasan = kaki.get("reason") or "tidak tercatat"
                baris.append(
                    f"Kaki {nama}: tidak memenuhi syarat " f"(alasan mesin: {alasan})."
                )
                continue
            model = _fmt_persen(kaki.get("p_model"))
            pasar = _fmt_persen(kaki.get("p_market"))
            akhir = _fmt_persen(kaki.get("p_final"))
            label = kaki.get("price_label")
            teks_pasar = (
                f"pasar {pasar} ({kaki.get('comparison_source')})"
                if pasar
                else "pasar tidak ada pembanding"
            )
            baris.append(
                f"Kaki {nama} Under {_fmt_poin(garis_kaki)}: model "
                f"{model or 'tidak tercatat'} | {teks_pasar} | akhir "
                f"{akhir or 'tidak tercatat'}" + (f" — {label}." if label else ".")
            )
        if not self.legs:
            baris.append("Tidak ada kaki Asuransi/Utama di artefak.")
            self._celah("Kaki Asuransi/Utama: tidak ada di artefak.")
        if self.r is not None:
            putusan = _VERDIK_TIKET.get(self.r.get("verdict"), self.r.get("verdict"))
            baris.append(f"Cek ulang sebelum pasang: {putusan}.")
        self._tambah("Ringkasan", baris)

    # -- bagian: tim + pemain -----------------------------------------

    def _bagian_data_tim(self) -> None:
        """Statistik tiap tim: musim, 10 laga terakhir, istirahat."""
        baris: list[str] = []
        for sisi, peran in (("away", "tandang"), ("home", "kandang")):
            nama = self._nama_tim(sisi)
            tri = self._tricode(sisi)
            blok = self._blok_tim(sisi)
            baris.append(f"### {nama} ({tri}) — {peran}")
            if blok is None:
                baris.append("- Data tim: tidak terverifikasi.")
                self._celah(f"Data tim {nama}: tidak terverifikasi.")
                continue
            musim = blok.get("stats_season") or {}
            baris.append(
                "- Musim ini: serangan "
                f"{_fmt_poin(musim.get('off_rtg')) or '?'} poin per "
                "100 serangan; pertahanan "
                f"{_fmt_poin(musim.get('def_rtg')) or '?'}; selisih "
                f"{_fmt_poin(musim.get('net_rtg')) or '?'}; tempo "
                f"{_fmt_poin(musim.get('pace')) or '?'} serangan per laga."
                + self._teks_sumber("nba_team_advanced_season")
            )
            terakhir = blok.get("stats_last10") or {}
            baris.append(
                "- 10 laga terakhir: serangan "
                f"{_fmt_poin(terakhir.get('off_rtg')) or '?'}; pertahanan "
                f"{_fmt_poin(terakhir.get('def_rtg')) or '?'}; selisih "
                f"{_fmt_poin(terakhir.get('net_rtg')) or '?'}; tempo "
                f"{_fmt_poin(terakhir.get('pace')) or '?'}."
                + self._teks_sumber("nba_team_advanced_last10")
            )
            istirahat = blok.get("rest_days")
            b2b = blok.get("back_to_back")
            if istirahat is not None:
                baris.append(f"- Istirahat {istirahat} hari sejak laga terakhir.")
            if b2b is True:
                baris.append(
                    "- Main dua malam beruntun (laga kemarin juga main) — "
                    "model mengurangi proyeksi poin tim ini."
                )
            elif b2b is False:
                baris.append("- Tidak main dua malam beruntun.")
            if istirahat is None and b2b is None:
                baris.append("- Jadwal istirahat: tidak terverifikasi.")
                self._celah(f"Jadwal istirahat {nama}: tidak terverifikasi.")
            if blok.get("altitude_home") is True:
                baris.append("- Bermain di kota dataran tinggi.")
        self._tambah("Data tim", baris)

    def _bagian_pemain_kunci(self) -> None:
        """5 pemain dengan menit terbanyak per tim (BPM + menit + status)."""
        baris = [
            "Rating di bawah ini adalah BPM — perkiraan nilai tambah pemain "
            "per 100 serangan dibanding pemain rata-rata. Makin tinggi makin "
            "bagus; 0 berarti rata-rata. Diurutkan dari yang paling lama main."
        ]
        for sisi in ("away", "home"):
            nama_tim = self._nama_tim(sisi)
            blok = self._blok_tim(sisi)
            baris.append(f"### {nama_tim}")
            pemain = []
            if blok is not None:
                pemain = [p for p in (blok.get("players") or []) if isinstance(p, dict)]
            if not pemain:
                baris.append("- Rating pemain: tidak terverifikasi.")
                self._celah(f"Rating pemain {nama_tim}: tidak terverifikasi.")
                continue
            pemain.sort(key=lambda p: _angka(p.get("mp_per_game")) or 0.0, reverse=True)
            for p in pemain[:5]:
                nama = p.get("player") or "tidak bernama"
                bpm = _fmt_bpm(p.get("bpm"))
                menit = _fmt_poin(p.get("mp_per_game"))
                teks = f"- {nama}: rating {bpm or '?'}"
                if menit:
                    teks += f", main {menit} menit per laga"
                if p.get("shrinkage") == "diterapkan":
                    teks += " (angka sudah disesuaikan ke musim lalu)"
                cedera = self._status_pemain(nama)
                if cedera is not None:
                    status = _STATUS_PEMAIN.get(
                        str(cedera.get("status") or "").upper(),
                        str(cedera.get("status") or ""),
                    )
                    teks += f" — {status.upper()}"
                    teks += f" ({_teks_alasan_cedera(cedera)})"
                baris.append(teks + "." + self._teks_sumber("nba_player_impact"))
        self._tambah("Pemain kunci", baris)

    def _bagian_proyeksi(self) -> None:
        """Proyeksi poin model: total, selisih, tempo, penyesuaian."""
        ringkasan = self._ringkasan_sim()
        baris: list[str] = []
        total = _angka(ringkasan.get("projected_total"))
        kandang_pts = _angka(ringkasan.get("projected_home_points"))
        tandang_pts = _angka(ringkasan.get("projected_away_points"))
        margin = _angka(ringkasan.get("projected_margin"))
        if total is None:
            baris.append("Proyeksi total model: tidak terverifikasi.")
            self._celah("Proyeksi total model: tidak terverifikasi.")
            self._tambah("Proyeksi total", baris)
            return
        if kandang_pts is not None and tandang_pts is not None:
            baris.append(
                f"Model memperkirakan {self._nama_tim('home')} mencetak "
                f"{_fmt_poin(kandang_pts)} poin dan "
                f"{self._nama_tim('away')} mencetak {_fmt_poin(tandang_pts)} "
                f"poin — total {_fmt_poin(total)} poin."
            )
        else:
            baris.append(f"Model memperkirakan total {_fmt_poin(total)} poin.")
        if margin is not None:
            unggul = self._nama_tim("home") if margin > 0 else self._nama_tim("away")
            baris.append(
                f"Selisih yang diperkirakan: {_fmt_poin(abs(margin))} poin "
                f"untuk {unggul}."
            )
        pace = _angka(ringkasan.get("pace_game"))
        if pace is not None:
            baris.append(f"Tempo laga diperkirakan {_fmt_poin(pace)} serangan per tim.")
        kandang_adv = _angka(ringkasan.get("home_advantage_points"))
        if kandang_adv is not None:
            baris.append(
                f"Keuntungan main di kandang: +{_fmt_poin(kandang_adv)} poin "
                f"untuk {self._nama_tim('home')}."
            )
        b2b = ringkasan.get("back_to_back") or {}
        if isinstance(b2b, dict):
            denda = _angka(b2b.get("penalty_points"))
            tim_b2b = [
                self._nama_tim(s) for s in ("home", "away") if b2b.get(s) is True
            ]
            if tim_b2b and denda is not None:
                baris.append(
                    "Hukuman main dua malam beruntun "
                    f"({_fmt_poin(denda)} poin) berlaku untuk: "
                    + ", ".join(tim_b2b)
                    + "."
                )
        sigma_total = _angka(ringkasan.get("sigma_total_points"))
        if sigma_total is not None:
            baris.append(
                "Sebaran total (simpangan baku): "
                f"{_fmt_poin(sigma_total)} poin — total akhir sering "
                "berbeda belasan poin dari proyeksi ini."
            )
        absen = ringkasan.get("base_absent_players") or []
        if isinstance(absen, list) and absen:
            baris.append(
                f"Model sudah menghitung {len(absen)} pemain absen: "
                + ", ".join(str(n) for n in absen)
                + "."
            )
        if ringkasan.get("tournament") is None and (
            "tournament_flag_tidak_dapat_ditentukan"
            in [str(m) for m in self.a.get("missing") or []]
        ):
            baris.append(
                "Status turnamen (NBA Cup/Playoff): tidak terverifikasi — "
                "tidak ada penyesuaian turnamen di proyeksi."
            )
            self._celah("Status turnamen: tidak terverifikasi.")
        mesin = self.sim.get("engine") if self.sim else None
        nama_mesin = (
            mesin.get("name") if isinstance(mesin, dict) else None
        ) or "nba_sim"
        dibuat = _jam_singkat(self.sim.get("generated_at")) if self.sim else None
        baris.append(
            f"Proyeksi ini berasal dari simulasi {nama_mesin}"
            + (f", dibuat {dibuat}." if dibuat else ".")
        )
        self._tambah("Proyeksi total", baris)

    # -- bagian: cedera + market + kaki ---------------------------------

    def _bagian_cedera(self) -> None:
        """Kabar pemain: siapa tidak main/diragukan + alasan + sumber."""
        baris: list[str] = []
        sumber = self.injuries.get("sources") or []
        n_sumber = self.injuries.get("n_sources")
        if n_sumber is None:
            n_sumber = len(sumber)
        diambil = _jam_singkat(self.injuries.get("fetched_at"))
        if sumber:
            baris.append(
                f"Dicek dari {n_sumber} sumber: "
                + ", ".join(str(s) for s in sumber)
                + (f" (diambil {diambil})." if diambil else ".")
            )
        else:
            baris.append("Kabar cedera: tidak terverifikasi (tidak ada sumber).")
            self._celah("Kabar cedera: tidak terverifikasi (tidak ada sumber).")
        if isinstance(n_sumber, int) and 0 < n_sumber < 2:
            baris.append(
                "Peringatan: kabar cedera hanya dari 1 sumber — belum "
                "dicek silang (aturan mesin butuh 2 sumber)."
            )
        entri = self._entri_cedera()
        if not entri and sumber:
            baris.append(
                "Tidak ada pemain yang dilaporkan cedera, istirahat, "
                "atau diragukan — semua pemain tersedia menurut data "
                "yang diambil."
            )
        for cedera in entri:
            nama = cedera.get("player") or "tidak bernama"
            tri = cedera.get("team_tricode") or ""
            status = _STATUS_PEMAIN.get(
                str(cedera.get("status") or "").upper(),
                str(cedera.get("status") or ""),
            )
            teks = f"- {nama} ({tri}): {status}."
            teks += f" Alasan: {_teks_alasan_cedera(cedera)}."
            daftar_sumber = cedera.get("sources") or []
            if daftar_sumber:
                teks += " Sumber: " + ", ".join(str(s) for s in daftar_sumber) + "."
            baris.append(teks)
        dikonfirmasi = self.injuries.get("confirmed_both") or []
        if dikonfirmasi:
            baris.append(
                "Pemain yang dipastikan tidak main/diragukan oleh 2 sumber: "
                + ", ".join(str(n) for n in dikonfirmasi)
                + "."
            )
        konflik = self.injuries.get("conflicts") or []
        for item in konflik:
            if not isinstance(item, dict):
                continue
            status_map = item.get("statuses") or {}
            if not isinstance(status_map, dict) or not status_map:
                continue
            pasangan = "; ".join(
                f"{sumber} bilang {status}" for sumber, status in status_map.items()
            )
            baris.append(
                f"Konflik status — {item.get('player')} "
                f"({item.get('team_tricode') or '?'}): {pasangan}. "
                "Keduanya ditampilkan, mesin tidak memilih diam-diam."
            )
        self._tambah("Kabar pemain (cedera & ketersediaan)", baris)

    def _bagian_market(self) -> None:
        """Bursa: garis total utama, spread, moneyline, tangga Under."""
        baris: list[str] = []
        if self.market is None:
            baris.append("Data bursa: tidak terverifikasi.")
            self._celah("Data bursa: tidak terverifikasi.")
            self._tambah("Bursa & harga pasar", baris)
            return
        sumber_teks = self._teks_sumber("polymarket_ladder")
        garis = self._garis_utama()
        volume = _angka(self.market.get("main_total_volume_usd"))
        total_entri = [
            e for e in (self.market.get("totals") or []) if isinstance(e, dict)
        ]
        if garis is not None:
            teks = f"Garis total utama (paling banyak dipasang): {_fmt_poin(garis)}"
            if volume is not None:
                teks += f" — volume {_fmt_usd(volume)}"
            teks += "." + sumber_teks
            baris.append(teks)
            for sisi in ("over", "under"):
                entri = next(
                    (
                        e
                        for e in total_entri
                        if _angka(e.get("line")) == garis
                        and str(e.get("side") or "").lower() == sisi
                    ),
                    None,
                )
                if entri is not None:
                    harga = _fmt_sen(entri.get("price_cents"))
                    bid = _fmt_sen(entri.get("bid_cents"))
                    ask = _fmt_sen(entri.get("ask_cents"))
                    teks_harga = (
                        f"- Harga {sisi.capitalize()} {_fmt_poin(garis)}: {harga}"
                    )
                    if bid and ask:
                        teks_harga += f" (tawar {bid} / minta {ask})"
                    if entri.get("thin") is True:
                        teks_harga += " — pasar tipis"
                    baris.append(teks_harga + ".")
        else:
            baris.append("Garis total utama: tidak terverifikasi.")
            self._celah("Garis total utama: tidak terverifikasi.")
        spread_entri = [
            e
            for e in (self.market.get("spreads") or [])
            if isinstance(e, dict) and _angka(e.get("line")) is not None
        ]
        if spread_entri:
            utama = max(spread_entri, key=lambda e: _angka(e.get("volume_usd")) or 0.0)
            garis_spread = _angka(utama.get("line"))
            vol_spread = _angka(utama.get("volume_usd"))
            teks = (
                f"Spread paling cair: {utama.get('team') or '?'} "
                f"{f'{garis_spread:+g}'.replace('.', ',')} "
                f"({_fmt_sen(utama.get('price_cents'))})"
            )
            if vol_spread is not None:
                teks += f", volume {_fmt_usd(vol_spread)}"
            baris.append(teks + ".")
        else:
            baris.append("Spread: tidak ada di artefak.")
            self._celah("Spread: tidak ada di artefak.")
        moneyline = self.market.get("moneyline_jup")
        if isinstance(moneyline, dict):
            kandang_c = _fmt_sen(moneyline.get("home_cents"))
            tandang_c = _fmt_sen(moneyline.get("away_cents"))
            baris.append(
                f"Harga menang/kalah di jup.ag: {self._nama_tim('home')} "
                f"{kandang_c}, {self._nama_tim('away')} {tandang_c}."
            )
        else:
            baris.append("Harga menang/kalah jup.ag: tidak ada di artefak.")
            self._celah("Harga menang/kalah jup.ag: tidak ada di artefak.")
        under = [
            e
            for e in total_entri
            if str(e.get("side") or "").lower() == "under"
            and _angka(e.get("line")) is not None
        ]
        under.sort(key=lambda e: _angka(e.get("line")))
        if garis is not None:
            # Tangga memuat garis babak (mis. 53,5) tanpa penanda babak —
            # hanya garis setingkat/di atas garis utama yang relevan
            # untuk kaki Under dan ditampilkan di sini.
            tampil = [e for e in under if _angka(e.get("line")) >= garis]
            tersembunyi = len(under) - len(tampil)
        else:
            tampil, tersembunyi = under, 0
        if tampil:
            baris.append("Tangga Under (garis — harga — volume):")
            for entri in tampil:
                garis_e = _fmt_poin(entri.get("line"))
                harga = _fmt_sen(entri.get("price_cents"))
                vol = _angka(entri.get("volume_usd"))
                teks = f"- Under {garis_e}: {harga}"
                if vol is not None:
                    teks += f", volume {_fmt_usd(vol)}"
                if entri.get("thin") is True:
                    teks += " — pasar tipis (harga bisa melompat)"
                baris.append(teks + ".")
            if tersembunyi > 0:
                baris.append(
                    f"(+ {tersembunyi} garis Under lain di bawah garis "
                    "utama tidak ditampilkan.)"
                )
        peringatan = self.market.get("ladder_warnings") or []
        for item in peringatan:
            baris.append(f"Peringatan tangga: {item}")
        self._tambah("Bursa & harga pasar", baris)

    def _bagian_kaki(self) -> None:
        """Kaki Asuransi & Utama: model | pasar | akhir + label harga."""
        baris: list[str] = []
        if not self.legs:
            baris.append("Tidak ada kaki di artefak.")
            self._celah("Kaki Asuransi/Utama: tidak ada di artefak.")
            self._tambah("Kaki Asuransi & Utama", baris)
            return
        median = self._median_total()
        garis_market = self._garis_utama()
        for kaki in self.legs:
            nama = _TIKET.get(kaki.get("ticket"), str(kaki.get("ticket") or "?"))
            garis_kaki = _angka(kaki.get("line"))
            judul = (
                f"### Kaki {nama} — Under {_fmt_poin(garis_kaki)}"
                if garis_kaki is not None
                else f"### Kaki {nama} — tanpa garis"
            )
            baris.append(judul)
            if garis_kaki is None or not kaki.get("meets"):
                alasan = kaki.get("reason") or "tidak tercatat"
                baris.append(
                    f"- Kaki ini tidak memenuhi syarat (alasan mesin: {alasan})."
                )
                continue
            model = _fmt_persen(kaki.get("p_model"))
            pasar = _fmt_persen(kaki.get("p_market"))
            akhir = _fmt_persen(kaki.get("p_final"))
            baris.append(f"- Peluang menurut model: {model or 'tidak tercatat'}.")
            if pasar:
                sumber = kaki.get("comparison_source") or "tidak tercatat"
                teks = f"- Peluang menurut pasar ({sumber}): {pasar}."
                if sumber == "kalshi":
                    teks += " (label PEMBANDING_KALSHI — pembanding Kalshi.)"
                baris.append(teks)
            else:
                baris.append(
                    "- Tidak ada pembanding pasar untuk garis ini "
                    "(MODEL_ONLY) — peluang akhir sama dengan peluang model."
                )
            baris.append(
                f"- Peluang akhir (gabungan model dan pasar): "
                f"{akhir or 'tidak tercatat'}."
            )
            harga_jup = _fmt_sen(kaki.get("jup_estimated_cents"))
            harga_poly = _fmt_sen(kaki.get("price_cents"))
            if harga_jup:
                baris.append(f"- Harga di jup.ag (perkiraan): {harga_jup}.")
            if harga_poly:
                baris.append(f"- Harga Polymarket: {harga_poly}.")
            ev = _angka(kaki.get("ev_pct"))
            label = kaki.get("price_label")
            if ev is not None:
                teks_ev = f"- Nilai (EV): {ev:+.1f}%".replace(".", ",")
                if label == "DISKON":
                    teks_ev += " — DISKON (harga lebih murah dari peluangnya)."
                elif label == "MAHAL":
                    teks_ev += " — MAHAL (harga lebih mahal dari peluangnya)."
                elif label == "WAJAR":
                    teks_ev += " — WAJAR (harga sesuai peluangnya)."
                else:
                    teks_ev += "."
                baris.append(teks_ev)
            bantalan_median = _angka(kaki.get("cushion_vs_median_points"))
            bantalan_market = _angka(kaki.get("cushion_vs_market_points"))
            if bantalan_median is not None and median is not None:
                baris.append(
                    "- Bantalan: "
                    f"{_fmt_poin(bantalan_median)} poin di atas median model "
                    f"({_fmt_poin(median)})."
                )
            if bantalan_market is not None and garis_market is not None:
                baris.append(
                    "- Bantalan: "
                    f"{_fmt_poin(bantalan_market)} poin di atas garis market "
                    f"({_fmt_poin(garis_market)})."
                )
            baris.append("- Memenuhi syarat: ya.")
        self._tambah("Kaki Asuransi & Utama", baris)

    # -- bagian: form, H2H, kandang/tandang, simulasi -------------------

    def _bagian_form5(self) -> None:
        """5 laga terakhir tiap tim (dari form5 di inputs)."""
        baris: list[str] = []
        for sisi in ("away", "home"):
            nama_tim = self._nama_tim(sisi)
            blok = self._blok_tim(sisi)
            laga = []
            if blok is not None:
                laga = [g for g in (blok.get("form5") or []) if isinstance(g, dict)]
            baris.append(f"### {nama_tim}")
            if not laga:
                baris.append("- 5 laga terakhir: tidak terverifikasi.")
                self._celah(f"5 laga terakhir {nama_tim}: tidak terverifikasi.")
                continue
            menang = sum(1 for g in laga if str(g.get("wl") or "").upper() == "W")
            kalah = sum(1 for g in laga if str(g.get("wl") or "").upper() == "L")
            baris.append(
                f"- {len(laga)} laga terakhir: {menang} menang, {kalah} kalah."
                + self._teks_sumber("nba_games_season")
            )
            for g in laga:
                tanggal = (
                    _tanggal_singkat(g.get("game_date")) or "tanggal tidak tercatat"
                )
                lawan = g.get("opponent_tricode") or "?"
                tempat = "kandang" if g.get("home") is True else "tandang"
                hasil = (
                    "menang"
                    if str(g.get("wl") or "").upper() == "W"
                    else (
                        "kalah"
                        if str(g.get("wl") or "").upper() == "L"
                        else "hasil tidak tercatat"
                    )
                )
                pts = _angka(g.get("pts"))
                opp = _angka(g.get("opp_pts"))
                skor = (
                    f" {int(pts)}–{int(opp)}"
                    if pts is not None and opp is not None
                    else " (skor tidak tercatat)"
                )
                baris.append(f"- {tanggal}, {tempat} vs {lawan}: {hasil}{skor}.")
        self._tambah("Lima laga terakhir", baris)

    def _bagian_h2h(self) -> None:
        """5 pertemuan terakhir kedua tim (dari h2h_last5 di inputs)."""
        baris: list[str] = []
        h2h = []
        if self.inputs is not None:
            h2h = [
                g for g in (self.inputs.get("h2h_last5") or []) if isinstance(g, dict)
            ]
        if not h2h:
            baris.append(
                "5 pertemuan terakhir: tidak terverifikasi — tidak ada "
                "data pertemuan di artefak."
            )
            self._celah("5 pertemuan terakhir: tidak terverifikasi.")
            self._tambah("Pertemuan terakhir", baris)
            return
        menang_kandang = 0
        menang_tandang = 0
        for g in h2h:
            tanggal = _tanggal_singkat(g.get("game_date")) or "tanggal tidak tercatat"
            kandang_tri = g.get("home_tricode") or "?"
            tandang_tri = g.get("away_tricode") or "?"
            pts_k = _angka(g.get("home_pts"))
            pts_t = _angka(g.get("away_pts"))
            if pts_k is not None and pts_t is not None:
                skor = f"{tandang_tri} {int(pts_t)} – {int(pts_k)} {kandang_tri}"
                if pts_k > pts_t:
                    pemenang = self._nama_tim("home")
                    menang_kandang += 1
                elif pts_t > pts_k:
                    pemenang = self._nama_tim("away")
                    menang_tandang += 1
                else:
                    pemenang = "seri"
                baris.append(
                    f"- {tanggal} (di {kandang_tri}): {skor}. " f"Pemenang: {pemenang}."
                )
            else:
                baris.append(
                    f"- {tanggal}: {tandang_tri} vs {kandang_tri} "
                    "(skor tidak tercatat)."
                )
        baris.append(
            f"Dari {len(h2h)} pertemuan tercatat: "
            f"{self._nama_tim('home')} menang {menang_kandang} kali, "
            f"{self._nama_tim('away')} menang {menang_tandang} kali."
            + self._teks_sumber("nba_games_season")
        )
        self._tambah("Pertemuan terakhir", baris)

    def _bagian_kandang_tandang(self) -> None:
        """Riwayat kandang-tandang tiap tim (rekor + rata-rata poin)."""
        baris: list[str] = []
        for sisi in ("away", "home"):
            nama_tim = self._nama_tim(sisi)
            blok = self._blok_tim(sisi)
            baris.append(f"### {nama_tim}")
            for kunci, label in (
                ("home_record", "Di kandang"),
                ("road_record", "Di tandang"),
            ):
                rekor = blok.get(kunci) if blok is not None else None
                if not isinstance(rekor, dict):
                    baris.append(f"- {label}: tidak terverifikasi.")
                    self._celah(
                        f"Rekor {label.lower()} {nama_tim}: tidak terverifikasi."
                    )
                    continue
                menang = rekor.get("w")
                kalah = rekor.get("l")
                ppg = _fmt_poin(rekor.get("ppg"))
                opp_ppg = _fmt_poin(rekor.get("opp_ppg"))
                teks = f"- {label}: {menang} menang – {kalah} kalah"
                if ppg and opp_ppg:
                    teks += f"; rata-rata cetak {ppg} poin, kebobolan {opp_ppg} poin"
                baris.append(teks + "." + self._teks_sumber("nba_games_season"))
        self._tambah("Riwayat kandang vs tandang", baris)

    def _bagian_simulasi(self) -> None:
        """Hasil simulasi 100.000x: total, OT, moneyline, skenario skuad."""
        baris: list[str] = []
        if self.sim is None:
            baris.append("Simulasi: tidak terverifikasi.")
            self._celah("Simulasi 100.000x: tidak terverifikasi.")
            self._tambah("Simulasi 100.000 pertandingan", baris)
            return
        iterasi = self.sim.get("iterations")
        if isinstance(iterasi, int) and not isinstance(iterasi, bool):
            baris.append(
                f"Mesin mengulang laga ini {iterasi:,} kali dengan kondisi "
                "yang sama.".replace(",", ".")
            )
        else:
            baris.append(
                "Mesin mengulang laga ini berkali-kali (jumlah ulangan "
                "tidak tercatat di artefak)."
            )
        mesin = self.sim.get("engine") or {}
        if isinstance(mesin, dict):
            seed = mesin.get("seed")
            baris.append(
                f"Mesin simulasi: {mesin.get('name') or 'nba_sim'} "
                f"v{mesin.get('version') or '?'}"
                + (
                    f", seed {seed} (ulangan bisa diulang persis)."
                    if seed is not None
                    else "."
                )
            )
        dist = self.sim.get("score_distribution") or {}
        total = dist.get("total") if isinstance(dist, dict) else None
        if isinstance(total, dict):
            mean = _fmt_poin(total.get("mean"))
            median = _fmt_poin(total.get("median"))
            p74 = _fmt_poin(total.get("p74"))
            p5 = _fmt_poin(total.get("p5"))
            p95 = _fmt_poin(total.get("p95"))
            std = _fmt_poin(total.get("std"))
            if mean and median:
                baris.append(
                    f"Total poin: rata-rata {mean}; nilai tengah (median) {median}."
                )
            if p74:
                baris.append(f"74 dari 100 ulangan totalnya di bawah {p74} poin.")
            if p5 and p95:
                baris.append(
                    f"90 dari 100 ulangan totalnya antara {p5} dan {p95} poin."
                )
            if std:
                baris.append(f"Sebaran total (simpangan baku): {std} poin.")
        else:
            baris.append("Sebaran total simulasi: tidak terverifikasi.")
            self._celah("Sebaran total simulasi: tidak terverifikasi.")
        ot = _peluang(dist.get("ot_probability")) if isinstance(dist, dict) else None
        if ot is not None:
            baris.append(
                f"Peluang laga masuk babak tambahan (overtime): " f"{_fmt_persen(ot)}."
            )
        kandang_pts = dist.get("home_points") if isinstance(dist, dict) else None
        tandang_pts = dist.get("away_points") if isinstance(dist, dict) else None
        med_k = (
            _angka(kandang_pts.get("median")) if isinstance(kandang_pts, dict) else None
        )
        med_t = (
            _angka(tandang_pts.get("median")) if isinstance(tandang_pts, dict) else None
        )
        if med_k is not None and med_t is not None:
            baris.append(
                f"Perkiraan skor tengah-tengah: {self._nama_tim('home')} "
                f"{int(med_k)} – {int(med_t)} {self._nama_tim('away')}."
            )
        markets = self.sim.get("markets") or {}
        ml_kandang = _fmt_persen(markets.get("moneyline_home"))
        ml_tandang = _fmt_persen(markets.get("moneyline_away"))
        if ml_kandang and ml_tandang:
            baris.append(
                f"Peluang menang (model): {self._nama_tim('home')} {ml_kandang}; "
                f"{self._nama_tim('away')} {ml_tandang}."
            )
        margin = dist.get("margin") if isinstance(dist, dict) else None
        if isinstance(margin, dict):
            med_m = _fmt_poin(margin.get("median"))
            p5_m = _fmt_poin(margin.get("p5"))
            p95_m = _fmt_poin(margin.get("p95"))
            if med_m:
                teks = (
                    f"Selisih skor tengah-tengah (kandang dikurangi tandang): "
                    f"{med_m} poin"
                )
                if p5_m and p95_m:
                    teks += f"; kisaran 90% ulangan: {p5_m} sampai {p95_m}"
                baris.append(teks + ".")
        self._tambah("Simulasi 100.000 pertandingan", baris)
        self._bagian_skenario_skuad()

    def _bagian_skenario_skuad(self) -> None:
        """Skenario skuad: peluang Under per kaki bila pemain absen."""
        baris: list[str] = []
        if self.sim is None:
            return
        skenario_list = self.sim.get("squad_scenarios") or []
        if not skenario_list:
            baris.append("Skenario skuad: tidak ada di artefak.")
            self._celah("Skenario skuad: tidak ada di artefak.")
            self._tambah("Skenario skuad", baris)
            return
        dasar = set(self._ringkasan_sim().get("base_absent_players") or [])
        garis_kaki = [
            (kaki, _angka(kaki.get("line")))
            for kaki in self.legs
            if _angka(kaki.get("line")) is not None
        ]
        for skenario in skenario_list:
            if not isinstance(skenario, dict):
                continue
            nama = skenario.get("scenario") or "?"
            arti = _SKENARIO.get(nama, nama)
            absen = [str(n) for n in (skenario.get("absent_players") or [])]
            tambahan = sorted(set(absen) - dasar)
            teks = f"### {arti}"
            baris.append(teks)
            if nama == "full":
                baris.append("- Tidak ada pemain absen.")
            elif tambahan:
                baris.append(
                    "- Tambahan absen (di atas pemain yang memang sudah absen): "
                    + ", ".join(tambahan)
                    + "."
                )
            elif absen:
                baris.append("- Pemain absen: " + ", ".join(absen) + ".")
            else:
                baris.append("- Tidak ada pemain absen.")
            markets = skenario.get("markets") or {}
            ml = _fmt_persen(markets.get("moneyline_home"))
            if ml:
                baris.append(f"- Peluang {self._nama_tim('home')} menang: {ml}.")
            for kaki, garis in garis_kaki:
                kunci = f"total_under_{garis:g}"
                peluang = _fmt_persen(markets.get(kunci))
                nama_kaki = _TIKET.get(
                    kaki.get("ticket"), str(kaki.get("ticket") or "?")
                )
                if peluang:
                    baris.append(
                        f"- Peluang Under {_fmt_poin(garis)} ({nama_kaki}): {peluang}."
                    )
                else:
                    baris.append(
                        f"- Peluang Under {_fmt_poin(garis)} ({nama_kaki}): "
                        "tidak tercatat di skenario ini."
                    )
        baris.append(
            "Catatan: skenario hanya membawa peluang, bukan proyeksi total — "
            "total proyeksi tiap skenario tidak ada di artefak."
        )
        self._celah(
            "Total proyeksi per skenario skuad: tidak ada di artefak "
            "(skenario hanya membawa peluang)."
        )
        self._tambah("Skenario skuad", baris)

    # -- bagian: anomali + "Kenapa beda?" + recheck + sumber ------------

    def _teks_anomali(self, anomali: dict) -> str | None:
        """Satu anomali jadi kalimat sederhana; None bila jenis tak dikenal."""
        tipe = anomali.get("type")
        if tipe == "total_line_vs_model":
            gap = _fmt_poin(anomali.get("gap_points"))
            median = _fmt_poin(anomali.get("model_median_total"))
            garis = _fmt_poin(anomali.get("market_total_line"))
            arah = (
                "market mengharap total lebih tinggi dari model"
                if anomali.get("direction") == "market_lebih_tinggi"
                else "model mengharap total lebih tinggi dari market"
            )
            return (
                f"Garis market ({garis}) dan median model ({median}) "
                f"berbeda {gap} poin — {arah}."
            )
        if tipe == "cushion_tidak_dikonfirmasi_market":
            garis_alt = _fmt_poin(anomali.get("alt_line"))
            model_c = _fmt_poin(anomali.get("model_cushion_points"))
            market_c = _fmt_poin(anomali.get("market_cushion_points"))
            syarat = _fmt_poin(anomali.get("required_cushion_points"))
            return (
                f"Bantalan garis {garis_alt} cukup menurut model "
                f"({model_c} poin) tapi hanya {market_c} poin menurut "
                f"garis market — di bawah syarat {syarat} poin."
            )
        if tipe == "model_vs_market":
            model = _fmt_persen(anomali.get("p_model"))
            pasar = _fmt_persen(anomali.get("p_market"))
            selisih = _fmt_poin(anomali.get("diff_points"))
            return (
                f"Model dan pasar berbeda {selisih} poin "
                f"(model {model}, pasar {pasar})."
            )
        if tipe == "jup_vs_market":
            jup = _fmt_sen(anomali.get("jup_cents"))
            pasar = _fmt_persen(anomali.get("p_market"))
            selisih = _fmt_poin(anomali.get("diff_points"))
            return (
                f"Harga jup.ag ({jup}) berbeda {selisih} poin dari "
                f"peluang pasar ({pasar})."
            )
        if tipe == "sharp_move":
            awal = _fmt_sen(anomali.get("first_cents"))
            kini = _fmt_sen(anomali.get("now_cents"))
            gerak = _fmt_poin(anomali.get("delta_cents"))
            return f"Harga bergerak tajam: dari {awal} ke {kini} (gerak {gerak}¢)."
        if tipe == "model_optimis_harga_melawan":
            model = _fmt_persen(anomali.get("p_model_under"))
            gerak = _fmt_poin(anomali.get("price_delta_cents"))
            return f"Model optimis Under ({model}) tapi harga Under turun " f"{gerak}¢."
        return None

    def _bagian_anomali(self) -> None:
        """Anomali dari artefak, diterjemahkan ke kalimat sederhana."""
        anomali_list = [
            a for a in (self.a.get("anomalies") or []) if isinstance(a, dict)
        ]
        if not anomali_list:
            return
        baris = ["Mesin menemukan hal-hal berikut yang patut diperhatikan:"]
        for anomali in anomali_list:
            teks = self._teks_anomali(anomali)
            if teks is None:
                teks = f"Anomali {anomali.get('type')}: " + json.dumps(
                    anomali, ensure_ascii=False, sort_keys=True
                )
            leg_id = anomali.get("leg_id")
            if leg_id:
                kaki = next((k for k in self.legs if k.get("leg_id") == leg_id), None)
                if kaki is not None:
                    nama = _TIKET.get(
                        kaki.get("ticket"), str(kaki.get("ticket") or "?")
                    )
                    garis = _fmt_poin(kaki.get("line"))
                    teks += (
                        f" (kaki {nama}" + (f" Under {garis}" if garis else "") + ")"
                    )
            baris.append(f"- {teks}")
        self._tambah("Anomali", baris)

    def _pemicu_kenapa_beda(self) -> list[tuple[dict, dict | None]]:
        """Kaki yang memicu "Kenapa beda?" (|model - pasar| > 8 poin).

        Ambang dibaca dari playstyle.yaml lewat
        engine.anomaly.check_model_vs_market; bila config tidak bisa
        dibaca, fallback ke anomali model_vs_market di artefak.
        """
        pemicu = []
        anomali_artefak = [
            a for a in (self.a.get("anomalies") or []) if isinstance(a, dict)
        ]
        for kaki in self.legs:
            model = _peluang(kaki.get("p_model"))
            pasar = _peluang(kaki.get("p_market"))
            if model is None or pasar is None:
                continue
            hasil = None
            try:
                hasil = anomaly_mod.check_model_vs_market(model, pasar)
            except Exception:  # noqa: BLE001 - config rusak -> fallback artefak
                hasil = None
            if hasil is not None:
                pemicu.append((kaki, hasil))
                continue
            for anomali in anomali_artefak:
                if anomali.get("type") == "model_vs_market" and anomali.get(
                    "leg_id"
                ) == kaki.get("leg_id"):
                    pemicu.append((kaki, anomali))
                    break
        return pemicu

    def _kenapa_beda_recheck(self, leg_id: str | None) -> dict | None:
        """Blok kenapa_beda recheck untuk satu leg_id; None bila tak ada."""
        if self.r is None:
            return None
        for kaki in self.r.get("legs") or []:
            if isinstance(kaki, dict) and kaki.get("leg_id") == leg_id:
                blok = kaki.get("kenapa_beda")
                return blok if isinstance(blok, dict) else None
        return None

    def _bagian_kenapa_beda(self) -> None:
        """Bagian wajib bila model dan pasar berbeda jauh.

        Isi dari data saja (keputusan user 2026-11-21): cedera terbaru,
        pergerakan harga, kualitas data model, konteks jadwal. Bila
        tidak ada alasan konkret: tulis begitu — jangan mengarang.
        """
        pemicu = self._pemicu_kenapa_beda()
        anomali_wajib = [
            a
            for a in (self.a.get("anomalies") or [])
            if isinstance(a, dict) and a.get("kenapa_beda_required") is True
        ]
        recheck_terpicu = False
        if self.r is not None:
            for kaki in self.r.get("legs") or []:
                blok = kaki.get("kenapa_beda") if isinstance(kaki, dict) else None
                if isinstance(blok, dict) and blok.get("triggered") is True:
                    recheck_terpicu = True
                    break
        if not pemicu and not anomali_wajib and not recheck_terpicu:
            return
        baris = [
            "Model dan pasar berbeda jauh — bagian ini wajib dibaca "
            "sebelum memasang. Semua yang diperiksa di bawah ini berasal "
            "dari data; yang tidak ada datanya ditulis tidak terverifikasi."
        ]
        for kaki, anomali in pemicu:
            nama = _TIKET.get(kaki.get("ticket"), str(kaki.get("ticket") or "?"))
            garis = _fmt_poin(kaki.get("line"))
            model = _fmt_persen(kaki.get("p_model"))
            pasar = _fmt_persen(kaki.get("p_market"))
            selisih = None
            if anomali is not None:
                selisih = _fmt_poin(anomali.get("diff_points"))
            if selisih is None:
                selisih = _fmt_poin(
                    abs(_peluang(kaki.get("p_model")) - _peluang(kaki.get("p_market")))
                    * 100.0
                )
            baris.append(f"### Kaki {nama} — Under {garis}")
            baris.append(
                f"- Model: {model} — Pasar "
                f"({kaki.get('comparison_source') or 'tidak tercatat'}): "
                f"{pasar} — selisih {selisih} poin."
            )
            baris.append("- Yang diperiksa dari data:")
            cedera_penting = [
                e
                for e in self._entri_cedera()
                if str(e.get("status") or "").upper() in ("OUT", "DOUBTFUL")
            ]
            if cedera_penting:
                nama_pemain = ", ".join(str(e.get("player")) for e in cedera_penting)
                baris.append(
                    f"  - Cedera: {len(cedera_penting)} pemain tidak "
                    f"main/diragukan ({nama_pemain}) — sudah masuk hitungan "
                    "model."
                )
            else:
                baris.append("  - Cedera: tidak ada pemain inti yang absen/diragukan.")
            konflik = self.injuries.get("conflicts") or []
            if konflik:
                baris.append(
                    "  - Ada konflik status cedera antar sumber "
                    "(lihat bagian Kabar pemain) — data cedera tidak bulat."
                )
            median = self._median_total()
            garis_market = self._garis_utama()
            if median is not None and garis_market is not None:
                baris.append(
                    f"  - Garis: median model {_fmt_poin(median)} vs garis "
                    f"market {_fmt_poin(garis_market)} — selisih "
                    f"{_fmt_poin(abs(garis_market - median))} poin."
                )
            gerak_harga = None
            if self.r is not None:
                for kaki_r in self.r.get("legs") or []:
                    if isinstance(kaki_r, dict) and kaki_r.get("leg_id") == kaki.get(
                        "leg_id"
                    ):
                        gerak_harga = _angka(kaki_r.get("price_move_cents"))
            if gerak_harga is not None:
                gerak_teks = f"{gerak_harga:+.1f}¢".replace(".", ",")
                baris.append(
                    "  - Harga bergerak "
                    f"{gerak_teks} sejak analisis awal (dari cek ulang)."
                )
            else:
                baris.append(
                    "  - Pergerakan harga: tidak terverifikasi — artefak "
                    "hanya membawa harga pertama."
                )
                self._celah(
                    "Pergerakan harga sejak analisis awal: tidak "
                    "terverifikasi (artefak hanya membawa harga pertama)."
                )
            hilang = [str(m) for m in self.a.get("missing") or []]
            if hilang:
                baris.append(
                    "  - Kualitas data model: ada catatan hilang — "
                    + "; ".join(hilang)
                    + "."
                )
            n_sumber = self.injuries.get("n_sources")
            if isinstance(n_sumber, int) and n_sumber < 2:
                baris.append(
                    "  - Kualitas data model: kabar cedera hanya dari "
                    f"{n_sumber} sumber (belum dicek silang)."
                )
            for sisi in ("home", "away"):
                blok = self._blok_tim(sisi)
                if blok is not None and blok.get("back_to_back") is True:
                    baris.append(
                        f"  - Jadwal: {self._nama_tim(sisi)} main dua malam "
                        "beruntun."
                    )
            blok_kb = self._kenapa_beda_recheck(kaki.get("leg_id"))
            if blok_kb is not None and blok_kb.get("reason_found") is True:
                alasan = blok_kb.get("reason") or "alasan konkret (tidak dirinci)"
                baris.append(
                    "- Kesimpulan: alasan konkret ditemukan (dari cek ulang): "
                    f"{alasan}."
                )
            elif blok_kb is not None and blok_kb.get("triggered") is True:
                baris.append(
                    "- Kesimpulan: cek ulang tidak menemukan alasan konkret — "
                    "aturan condong-ke-market memakai probabilitas pasar "
                    "untuk kaki Asuransi."
                )
            else:
                baris.append(
                    "- Kesimpulan: tidak ditemukan alasan konkret dari data "
                    "yang ada — selisih ini bisa jadi peluang, tapi tetap "
                    "hati-hati."
                )
        if not pemicu and (anomali_wajib or recheck_terpicu):
            baris.append(
                "- Tidak ada kaki yang selisih model-pasarnya melewati 8 "
                "poin, tapi mesin menandai anomali yang wajib dijelaskan "
                "(lihat bagian Anomali)."
            )
            baris.append(
                "- Kesimpulan: tidak ditemukan alasan konkret dari data "
                "yang ada — selisih ini bisa jadi peluang, tapi tetap "
                "hati-hati."
            )
        self._tambah("Kenapa beda?", baris)

    def _bagian_recheck(self) -> None:
        """Putusan cek ulang: GO/NO-GO + per kaki + yang harus dilakukan."""
        r = self.r
        baris: list[str] = []
        putusan = _VERDIK_TIKET.get(r.get("verdict"), r.get("verdict"))
        dicek = _jam_singkat(r.get("recheck_at"))
        baris.append(f"Putusan: {putusan}." + (f" (dicek {dicek})" if dicek else ""))
        if r.get("resimulated") is True:
            alasan = r.get("resim_reasons") or []
            baris.append(
                "Simulasi dihitung ulang karena: "
                + (", ".join(str(a) for a in alasan) if alasan else "tidak dirinci")
                + "."
            )
        else:
            baris.append(
                "Simulasi tidak dihitung ulang (tidak ada perubahan material)."
            )
        perubahan = [c for c in (r.get("changes") or []) if isinstance(c, dict)]
        if perubahan:
            baris.append("Perubahan sejak analisis awal:")
            for item in perubahan:
                jenis = _JENIS_PERUBAHAN.get(item.get("kind"), item.get("kind"))
                baris.append(f"- [{jenis}] {item.get('detail')}")
        else:
            baris.append("Tidak ada perubahan sejak analisis awal.")
        kaki_recheck = [k for k in (r.get("legs") or []) if isinstance(k, dict)]
        for kaki_r in kaki_recheck:
            leg_id = kaki_r.get("leg_id") or ""
            tiket = kaki_r.get("ticket")
            if tiket is None and ":" in leg_id:
                tiket = leg_id.rsplit(":", 1)[-1]
            nama = _TIKET.get(tiket, str(tiket or "?"))
            garis_lama = _angka(kaki_r.get("old_line"))
            garis_baru = _angka(kaki_r.get("new_line"))
            judul = f"### Kaki {nama}"
            if garis_lama is not None:
                judul += f" — Under {_fmt_poin(garis_lama)}"
            baris.append(judul)
            putusan_kaki = _VERDIK_KAKI.get(
                kaki_r.get("verdict"), kaki_r.get("verdict")
            )
            baris.append(f"- Putusan: {putusan_kaki}.")
            for alasan in kaki_r.get("reasons") or []:
                baris.append(f"- Alasan: {alasan}.")
            if garis_baru is not None and garis_lama != garis_baru:
                baris.append(
                    f"- Garis berubah: {_fmt_poin(garis_lama)} -> "
                    f"{_fmt_poin(garis_baru)}."
                )
            harga_lama = _fmt_sen(kaki_r.get("old_price_cents"))
            harga_baru = _fmt_sen(kaki_r.get("new_price_cents"))
            gerak = _angka(kaki_r.get("price_move_cents"))
            if harga_lama and harga_baru:
                teks = f"- Harga: {harga_lama} -> {harga_baru}"
                if gerak is not None:
                    teks += f" (gerak {gerak:+.1f}¢)".replace(".", ",")
                baris.append(teks + ".")
            dipakai = kaki_r.get("probability_used")
            nilai = _fmt_persen(kaki_r.get("probability_value"))
            if dipakai and nilai:
                baris.append(
                    f"- Peluang yang dipakai untuk putusan: {nilai} "
                    f"(dari {dipakai})."
                )
        perhatian = r.get("attention") or []
        for item in perhatian:
            baris.append(f"Perhatian: {item}")
        aksi = r.get("action_required")
        if isinstance(aksi, str) and aksi:
            baris.append(f"Yang harus dilakukan: {aksi}.")
        else:
            baris.append("Tidak ada tindakan khusus.")
        self._tambah("Cek ulang sebelum pasang", baris)

    def _bagian_sumber(self) -> None:
        """Daftar sumber data artefak + snapshot harga pertama."""
        baris: list[str] = []
        sumber = self.a.get("sources") or []
        if sumber:
            for entri in sumber:
                if not isinstance(entri, dict):
                    continue
                jam = _jam_singkat(entri.get("time")) or "jam tidak tercatat"
                baris.append(
                    f"- {entri.get('kind')}: {entri.get('source')} "
                    f"(jenjang {entri.get('tier')}), {jam}."
                )
        else:
            baris.append("Tidak ada daftar sumber di artefak.")
            self._celah("Daftar sumber data: tidak ada di artefak.")
        snapshot = self.a.get("price_snapshots") or {}
        if isinstance(snapshot, dict) and snapshot:
            for kunci in sorted(snapshot):
                entri = snapshot[kunci]
                if not isinstance(entri, dict):
                    continue
                baris.append(
                    f"- Harga pertama {kunci}: {_fmt_sen(entri.get('cents'))} "
                    f"(dicatat {_jam_singkat(entri.get('at'))})."
                )
        self._tambah("Sumber data", baris)


def build_nba_report(analysis: dict, recheck: dict | None = None) -> dict:
    """Rakit laporan terstruktur satu laga NBA (dict, JSON-serializable).

    analysis: dict artefak ``nba_analysis`` v1. recheck: dict laporan
    ``nba_recheck`` v1 (opsional; match_id harus sama dengan analysis).
    Mengembalikan {"format", "format_version", "match_id", "status",
    "generated_from", "sections", "tidak_terverifikasi", "text"}.
    Melempar ValueError bila analysis/recheck bukan dict, recheck
    bukan format nba_recheck, atau match_id keduanya berbeda.
    """
    if not isinstance(analysis, dict):
        raise ValueError(f"analysis harus dict, bukan {type(analysis).__name__}")
    if recheck is not None:
        if not isinstance(recheck, dict):
            raise ValueError(f"recheck harus dict, bukan {type(recheck).__name__}")
        if recheck.get("format") != "nba_recheck":
            raise ValueError(
                "recheck harus artefak format 'nba_recheck', bukan "
                f"{recheck.get('format')!r}"
            )
        if recheck.get("match_id") != analysis.get("match_id"):
            raise ValueError(
                "recheck untuk laga "
                f"{recheck.get('match_id')}, bukan {analysis.get('match_id')}"
            )
    return _Laporan(analysis, recheck).bangun()


def render_nba_report(analysis: dict, recheck: dict | None = None) -> str:
    """Render laporan lengkap satu laga NBA jadi teks mudah dibaca.

    analysis: dict artefak ``nba_analysis`` v1. recheck: dict laporan
    ``nba_recheck`` v1 (opsional). Lihat build_nba_report untuk kontrak
    lengkap; ValueError bila input tidak valid.
    """
    return build_nba_report(analysis, recheck)["text"]


def render_nba_report_json(analysis: dict, recheck: dict | None = None) -> dict:
    """Render laporan lengkap satu laga NBA jadi dict terstruktur.

    Sama seperti build_nba_report (alias nama sesuai kontrak langkah 3):
    {"format", "format_version", "match_id", "status", "generated_from",
    "sections", "tidak_terverifikasi", "text"}.
    """
    return build_nba_report(analysis, recheck)
