"""Tes report/learning_report — render laporan belajar (Tahap 3 Langkah 6).

SEMUA offline: data laporan dibangun dengan tangan di sini (angka
diketahui, bukan dari modul A/B) supaya render diuji terpisah dari
perhitungan ringkasan. Tidak ada panggilan Odds API (modul render
murni; tidak ada dependensi engine/config).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from report import learning_report as learning_report_mod


def _ringkasan(
    n=10,
    win_rate=0.7,
    brier_model=0.2,
    brier_market=0.25,
    brier_final=0.22,
    brier_climatology=0.21,
    ev_prediksi=0.05,
    ev_terealisasi=0.03,
):
    """Satu dict ringkasan (bentuk ringkasan_keseluruhan pekerja A)."""
    return {
        "n": n,
        "win_rate": win_rate,
        "brier_model": brier_model,
        "n_brier_model": n,
        "alasan_brier_model": None,
        "brier_market": brier_market,
        "n_brier_market": n,
        "alasan_brier_market": None,
        "brier_final": brier_final,
        "n_brier_final": n,
        "alasan_brier_final": None,
        "brier_climatology": brier_climatology,
        "alasan_brier_climatology": None,
        "ev_prediksi_rata2": ev_prediksi,
        "n_ev_prediksi": n,
        "alasan_ev_prediksi": None,
        "ev_terealisasi_rata2": ev_terealisasi,
        "n_ev_terealisasi": n,
        "alasan_ev_terealisasi": None,
    }


def _kalibrasi(
    w_saat_ini=0.3,
    w_rekomendasi=0.75,
    brier_saat_ini=0.2783,
    brier_rekomendasi=0.271,
    n=62,
    cukup_data=True,
    alasan="w optimal 0.75 (Brier 0.2710) vs w saat ini 0.3 (Brier 0.2783); n=62",
):
    """Satu dict kalibrasi_w (bentuk rekomendasi_w pekerja B)."""
    return {
        "w_saat_ini": w_saat_ini,
        "w_rekomendasi": w_rekomendasi,
        "brier_model": 0.2736,
        "brier_market": 0.2917,
        "brier_blend_w_saat_ini": brier_saat_ini,
        "brier_blend_w_rekomendasi": brier_rekomendasi,
        "n": n,
        "cukup_data": cukup_data,
        "alasan": alasan,
        "diterapkan": False,
        "butuh_persetujuan_user": True,
    }


def _usulan(
    nomor=1,
    jenis="pasar",
    judul="Pasar NBA / moneyline: model kalah dari frekuensi dasar",
    n=20,
    keyakinan="sedang",
):
    """Satu dict usulan (bentuk hasilkan_usulan pekerja B)."""
    return {
        "id": f"USUL-{nomor:03d}",
        "jenis": jenis,
        "judul": judul,
        "isi": "Di pasar NBA / moneyline, Brier model lebih buruk dari Brier climatology.",
        "bukti": {
            "pasar": "NBA / moneyline",
            "brier_model": 0.4,
            "brier_climatology": 0.24,
            "n": n,
        },
        "n": n,
        "keyakinan": keyakinan,
        "status": "menunggu_persetujuan",
        "aksi": "Pertimbangkan tidak memainkan pasar NBA / moneyline.",
    }


def _data_lengkap(sumber_data="ledger", **overrides):
    """Data laporan lengkap dengan angka yang diketahui."""
    data = {
        "sumber_data": sumber_data,
        "ada_data": True,
        "pesan": "10 kaki settled dari 3 tiket (1 pending, 0 VOID/PUSH dikeluarkan).",
        "ringkasan": _ringkasan(),
        "ringkasan_per_pasar": {
            ("NBA", "total_under"): _ringkasan(
                n=6,
                win_rate=0.8333,
                brier_model=0.15,
                brier_market=0.3,
                brier_final=0.25,
                brier_climatology=0.1389,
                ev_prediksi=0.06,
                ev_terealisasi=0.28,
            ),
            ("NBA", "moneyline"): _ringkasan(
                n=4,
                win_rate=0.5,
                brier_model=0.275,
                brier_market=0.175,
                brier_final=0.2,
                brier_climatology=0.25,
                ev_prediksi=0.035,
                ev_terealisasi=-0.1,
            ),
        },
        "kalibrasi_w": _kalibrasi(),
        "usulan": [_usulan()],
        "n_settled": 10,
        "n_pending": 1,
        "n_dikeluarkan": 0,
        "n_hasil_tidak_dikenal": 0,
        "n_tiket": 3,
        "dibuat_pada": "2026-11-22T15:53:00+00:00",
        "catatan_sumber": None,
        "modul_belum_tersedia": [],
    }
    data.update(overrides)
    return data


class TestLabelSumber(unittest.TestCase):
    def test_label_sintetis_di_judul_ringkasan_keterbatasan(self):
        teks = learning_report_mod.render_laporan_belajar(
            _data_lengkap(sumber_data="sintetis")
        )
        label = learning_report_mod.LABEL_SINTETIS
        judul = teks.split("\n")[0]
        self.assertIn(label, judul)
        ringkasan = teks.split("## Ringkasan")[1].split("## ")[0]
        self.assertIn(label, ringkasan)
        keterbatasan = teks.split("## Keterbatasan")[1]
        self.assertIn(label, keterbatasan)
        self.assertGreaterEqual(teks.count(label), 3)

    def test_label_replay_di_judul_ringkasan_keterbatasan(self):
        teks = learning_report_mod.render_laporan_belajar(
            _data_lengkap(sumber_data="replay")
        )
        label = learning_report_mod.LABEL_REPLAY
        judul = teks.split("\n")[0]
        self.assertIn(label, judul)
        ringkasan = teks.split("## Ringkasan")[1].split("## ")[0]
        self.assertIn(label, ringkasan)
        keterbatasan = teks.split("## Keterbatasan")[1]
        self.assertIn(label, keterbatasan)
        self.assertGreaterEqual(teks.count(label), 3)

    def test_ledger_tanpa_label_sintetis_atau_replay(self):
        teks = learning_report_mod.render_laporan_belajar(_data_lengkap())
        self.assertNotIn(learning_report_mod.LABEL_SINTETIS, teks)
        self.assertNotIn(learning_report_mod.LABEL_REPLAY, teks)

    def test_label_sintetis_juga_di_laporan_tanpa_data(self):
        data = _data_lengkap(sumber_data="sintetis", ada_data=False, ringkasan=None)
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertIn(learning_report_mod.LABEL_SINTETIS, teks.split("\n")[0])


class TestLaporanTanpaData(unittest.TestCase):
    def test_belum_ada_hasil_tercatat(self):
        teks = learning_report_mod.render_laporan_belajar(
            {
                "sumber_data": "ledger",
                "ada_data": False,
                "pesan": "ledger belum ada: belum ada tiket yang dicatat.",
                "n_pending": 0,
                "n_dikeluarkan": 0,
            }
        )
        self.assertIn("Belum ada hasil tercatat", teks)
        self.assertIn("cli.py log --file", teks)
        self.assertIn("cli.py log --settle", teks)
        self.assertIn("cli.py belajar", teks)

    def test_tanpa_data_tidak_memuat_angka_karangan(self):
        teks = learning_report_mod.render_laporan_belajar(
            {"sumber_data": "ledger", "ada_data": False, "pesan": "belum ada data."}
        )
        self.assertNotIn("Brier", teks)
        self.assertNotIn("%", teks)
        self.assertNotIn("kaki yang sudah selesai", teks)
        self.assertNotIn("0,", teks)

    def test_tanpa_data_dengan_pending_menampilkan_pending(self):
        teks = learning_report_mod.render_laporan_belajar(
            {"sumber_data": "ledger", "ada_data": False, "n_pending": 3}
        )
        self.assertIn("3 kaki yang masih menunggu hasil", teks)

    def test_data_kosong_atau_bukan_dict_tidak_crash(self):
        for data in ({}, None, "bukan dict", []):
            teks = learning_report_mod.render_laporan_belajar(data)
            self.assertIn("Belum ada hasil tercatat", teks)

    def test_ada_data_tapi_ringkasan_none_tetap_laporan_tanpa_data(self):
        teks = learning_report_mod.render_laporan_belajar(
            _data_lengkap(ada_data=True, ringkasan=None)
        )
        self.assertIn("Belum ada hasil tercatat", teks)


class TestRingkasan(unittest.TestCase):
    def test_angka_ringkasan_benar(self):
        teks = learning_report_mod.render_laporan_belajar(_data_lengkap())
        self.assertIn("Dari 10 kaki yang sudah selesai, 7 menang (70,0%)", teks)
        self.assertIn("Brier model: 0,2000.", teks)
        self.assertIn("Brier pasar: 0,2500.", teks)
        self.assertIn("Brier gabungan (model + pasar): 0,2200.", teks)
        self.assertIn("Brier tebakan dasar", teks)
        self.assertIn("0,2100", teks)
        self.assertIn("EV yang diperkirakan: +5,0%.", teks)
        self.assertIn("EV yang benar-benar terjadi: +3,0%.", teks)
        self.assertIn("1 kaki masih menunggu hasil", teks)
        self.assertIn("berasal dari 3 tiket", teks)

    def test_verdik_model_lebih_tepat_dari_pasar(self):
        teks = learning_report_mod.render_laporan_belajar(_data_lengkap())
        self.assertIn("model lebih tepat dari pasar", teks)

    def test_verdik_pasar_lebih_tepat_dari_model(self):
        data = _data_lengkap(ringkasan=_ringkasan(brier_model=0.3, brier_market=0.2))
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertIn("pasar lebih tepat dari model", teks)

    def test_tanpa_brier_pasar_belum_bisa_dibandingkan(self):
        data = _data_lengkap(ringkasan=_ringkasan(brier_market=None, brier_final=None))
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertIn("Brier pasar: tidak ada datanya", teks)
        self.assertIn("belum bisa dibandingkan", teks)

    def test_peringatan_model_kalah_dari_tebakan_dasar(self):
        data = _data_lengkap(
            ringkasan=_ringkasan(brier_model=0.3, brier_climatology=0.21)
        )
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertIn("model kalah dari tebakan dasar", teks)

    def test_tanpa_ev_tidak_ada_baris_ev(self):
        data = _data_lengkap(
            ringkasan=_ringkasan(ev_prediksi=None, ev_terealisasi=None),
            ringkasan_per_pasar={
                ("NBA", "total_under"): _ringkasan(
                    n=6, ev_prediksi=None, ev_terealisasi=None
                ),
            },
        )
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertNotIn("EV yang diperkirakan", teks)
        self.assertNotIn("EV yang benar-benar terjadi", teks)


class TestPerPasar(unittest.TestCase):
    def test_label_pasar_dan_verdik(self):
        teks = learning_report_mod.render_laporan_belajar(_data_lengkap())
        self.assertIn("### NBA — Total Under (6 kaki)", teks)
        self.assertIn("Menang 5 dari 6 kaki (83,3%).", teks)
        self.assertIn("### NBA — Menang/Kalah (4 kaki)", teks)
        # Total Under: model 0,15 < pasar 0,30 -> model lebih jago.
        # Moneyline: model 0,275 > pasar 0,175 -> pasar lebih jago.
        self.assertIn("Di pasar ini, model lebih jago dari pasar.", teks)
        self.assertIn("Di pasar ini, pasar lebih jago dari model.", teks)

    def test_kunci_string_juga_dikenali(self):
        data = _data_lengkap(
            ringkasan_per_pasar={
                "NBA/total_under": _ringkasan(n=6),
                "soccer / btts": _ringkasan(n=4),
            }
        )
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertIn("### NBA — Total Under (6 kaki)", teks)
        self.assertIn("### Bola — Kedua tim cetak gol (BTTS) (4 kaki)", teks)

    def test_pasar_tak_dikenal_tampil_mentah_tanpa_crash(self):
        data = _data_lengkap(
            ringkasan_per_pasar={("NBA", "pasar_aneh"): _ringkasan(n=2)}
        )
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertIn("NBA — pasar_aneh", teks)

    def test_peringatan_sampel_kecil_per_pasar(self):
        teks = learning_report_mod.render_laporan_belajar(_data_lengkap())
        self.assertIn("Sampel masih kecil (di bawah 20 kaki)", teks)

    def test_tanpa_brier_pasar_di_pasar(self):
        data = _data_lengkap(
            ringkasan_per_pasar={
                ("NBA", "total_under"): _ringkasan(n=6, brier_market=None)
            }
        )
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertIn("Brier pasar: tidak ada datanya.", teks)
        self.assertIn("belum bisa dibandingkan di pasar ini", teks)


class TestKalibrasiW(unittest.TestCase):
    def test_rekomendasi_menunggu_persetujuan(self):
        teks = learning_report_mod.render_laporan_belajar(_data_lengkap())
        self.assertIn("Bobot model sekarang: 0,30.", teks)
        self.assertIn("Rekomendasi: ubah bobot model menjadi 0,75.", teks)
        self.assertIn("Brier gabungan dengan bobot rekomendasi: 0,2710.", teks)
        self.assertIn("belum diterapkan — menunggu persetujuanmu", teks)
        self.assertIn("tidak pernah berubah sendiri", teks)

    def test_w_sudah_terbaik_tidak_ada_rekomendasi(self):
        data = _data_lengkap(
            kalibrasi_w=_kalibrasi(w_rekomendasi=0.3, alasan="sama dengan w saat ini")
        )
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertIn("sudah yang terbaik menurut data", teks)
        self.assertNotIn("belum diterapkan — menunggu persetujuanmu", teks)

    def test_data_belum_cukup_tidak_ada_rekomendasi(self):
        data = _data_lengkap(
            kalibrasi_w=_kalibrasi(
                w_rekomendasi=None,
                brier_rekomendasi=None,
                n=4,
                cukup_data=False,
                alasan="sampel belum cukup (n=4, butuh >=50)",
            )
        )
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertIn("Belum ada rekomendasi bobot baru.", teks)
        self.assertIn("sampel belum cukup (n=4, butuh >=50)", teks)

    def test_modul_kalibrasi_belum_tersedia(self):
        data = _data_lengkap(kalibrasi_w=None)
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertIn("modul kalibrasi belum tersedia", teks)


class TestUsulan(unittest.TestCase):
    def test_usulan_dirender_lengkap(self):
        teks = learning_report_mod.render_laporan_belajar(_data_lengkap())
        self.assertIn("[USUL-001] Pasar NBA / moneyline", teks)
        self.assertIn("Brier model 0,4000", teks)
        self.assertIn("Brier tebakan dasar 0,2400", teks)
        self.assertIn("sampel 20 kaki", teks)
        self.assertIn("keyakinan sedang", teks)
        self.assertIn("menunggu persetujuan", teks)
        self.assertIn("Yang diusulkan:", teks)

    def test_tidak_ada_usulan(self):
        data = _data_lengkap(usulan=[])
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertIn("Tidak ada usulan saat ini", teks)

    def test_modul_usulan_belum_tersedia(self):
        data = _data_lengkap(usulan=None)
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertIn("modul usulan belum terpasang", teks)

    def test_bukti_ev_diformat_persen(self):
        usulan_ev = _usulan(
            nomor=2,
            jenis="ambang",
            judul="Pasar NBA / moneyline: EV prediksi terlalu optimis",
        )
        usulan_ev["bukti"] = {
            "pasar": "NBA / moneyline",
            "ev_prediksi_rata2": 0.1364,
            "ev_terealisasi_rata2": -0.2727,
            "selisih_ev": 0.4091,
            "ev_gap_warn": 0.05,
            "n": 20,
        }
        data = _data_lengkap(usulan=[usulan_ev])
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertIn("EV prediksi rata-rata +13,6%", teks)
        self.assertIn("EV nyata rata-rata -27,3%", teks)
        self.assertIn("Selisih EV +40,9%", teks)


class TestKeterbatasan(unittest.TestCase):
    def test_sampel_kecil_dicatat(self):
        teks = learning_report_mod.render_laporan_belajar(_data_lengkap())
        self.assertIn("Sampel masih kecil (10 kaki)", teks)

    def test_sampel_besar_tidak_dicatat_kecil(self):
        data = _data_lengkap(
            ringkasan=_ringkasan(n=62, win_rate=0.5645),
            ringkasan_per_pasar={
                ("NBA", "total_under"): _ringkasan(n=31),
                ("NBA", "moneyline"): _ringkasan(n=31),
            },
        )
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertNotIn("Sampel masih kecil", teks)

    def test_replay_mencatat_tanpa_harga_pasar(self):
        data = _data_lengkap(
            sumber_data="replay",
            ringkasan=_ringkasan(brier_market=None),
            catatan_sumber="Replay backtest rolling dari file X — 150 laga.",
        )
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertIn("Tidak ada harga pasar historis", teks)
        self.assertIn("Replay backtest rolling dari file X", teks)
        self.assertIn("peluang akhir sama dengan peluang model", teks)

    def test_modul_belum_tersedia_dicatat(self):
        data = _data_lengkap(
            kalibrasi_w=None,
            usulan=None,
            modul_belum_tersedia=["engine.calibration", "engine.proposals"],
        )
        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertIn("engine.calibration, engine.proposals", teks)


if __name__ == "__main__":
    unittest.main()
