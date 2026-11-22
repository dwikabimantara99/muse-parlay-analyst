"""Tes engine/analis.py — bantalan adaptif + nilai wajar.

TANPA network, TANPA membaca out/. Angka bantalan dihitung tangan
dari rumus di docstring analis.py (bukan disalin dari output kode):
dasar = std * 0,42; serang = (ortg_rata - ortg_liga) * 0,5; form =
(total_5laga - total_musim) * 0,25; clamp [4, 20].
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import analis

# Config minimal = nilai section analis playstyle.yaml v13.
CFG_ANALIS = {
    "analis": {
        "harga_min_utama_cents": 75,
        "harga_min_asuransi_cents": 75,
        "cushion": {
            "acuan_points": 8.0,
            "std_factor": 0.42,
            "ortg_weight": 0.5,
            "form_weight": 0.25,
            "min_points": 4.0,
            "max_points": 20.0,
        },
        "wajar": {"selisih_minimum_poin": 0.0},
    }
}

# Distribusi sim DET@ATL 2026-11-22 (disalin dari
# examples/simulation_nba_ATL_DET_2026-11-22.json, score_distribution total).
DIST_DET_ATL = {
    "median": 219.0,
    "std": 19.45,
    "p5": 188.0,
    "p25": 206.0,
    "p74": 232.0,
    "p75": 232.0,
    "p95": 252.0,
}


class TestBantalanAdaptif(unittest.TestCase):
    def test_laga_biasa_sekitar_8(self):
        # std 19 (tipikal, sesuai sigma_total fit) -> dasar 7,98;
        # serang pas rata-rata liga + form datar -> bantalan 7,98 ~= 8.
        stats = {
            "ortg_home": 114.0,
            "ortg_away": 114.0,
            "ortg_liga_rata": 114.0,
            "total_rata_5laga": 225.0,
            "total_rata_musim": 225.0,
        }
        hasil = analis.bantalan_adaptif(
            stats, {"median": 219.0, "std": 19.0}, CFG_ANALIS
        )
        self.assertIsNotNone(hasil)
        assert hasil is not None
        self.assertAlmostEqual(hasil["cushion_points"], 7.98, places=2)
        self.assertEqual(hasil["acuan_points"], 8.0)
        self.assertEqual(hasil["faktor"]["tidak_terverifikasi"], [])
        self.assertTrue(hasil["faktor"]["kekuatan_serang"]["terverifikasi"])
        self.assertTrue(hasil["faktor"]["form_skor"]["terverifikasi"])
        self.assertIn("7,98", hasil["alasan"])

    def test_dua_penyerang_panas_lebih_tebal(self):
        # std 19 -> 7,98; ortg rata 117,5 vs liga 113 = +4,5 * 0,5 = +2,25;
        # form 235 vs 225 = +10 * 0,25 = +2,5 -> 12,73.
        stats = {
            "ortg_home": 118.0,
            "ortg_away": 117.0,
            "ortg_liga_rata": 113.0,
            "total_rata_5laga": 235.0,
            "total_rata_musim": 225.0,
        }
        hasil = analis.bantalan_adaptif(stats, DIST_DET_ATL, CFG_ANALIS)
        self.assertIsNotNone(hasil)
        assert hasil is not None
        # std DET@ATL 19,45 -> dasar 8,169; + 2,25 + 2,5 = 12,919.
        self.assertAlmostEqual(hasil["cushion_points"], 12.92, places=2)
        self.assertGreater(hasil["cushion_points"], 8.0)
        self.assertIn("penyerang kuat", hasil["alasan"])
        self.assertIn("5 laga terakhir", hasil["alasan"])
        faktor = hasil["faktor"]
        self.assertAlmostEqual(faktor["sebaran_sim"]["dasar_poin"], 8.17, places=2)
        self.assertAlmostEqual(
            faktor["kekuatan_serang"]["penyesuaian_poin"], 2.25, places=2
        )
        self.assertAlmostEqual(faktor["form_skor"]["penyesuaian_poin"], 2.5, places=2)

    def test_varians_rendah_lebih_tipis(self):
        # std 10 -> dasar 4,2; serang + form datar -> 4,2 (< 8, di atas min 4).
        stats = {
            "ortg_home": 114.0,
            "ortg_away": 114.0,
            "ortg_liga_rata": 114.0,
            "total_rata_5laga": 225.0,
            "total_rata_musim": 225.0,
        }
        hasil = analis.bantalan_adaptif(
            stats, {"median": 219.0, "std": 10.0}, CFG_ANALIS
        )
        self.assertIsNotNone(hasil)
        assert hasil is not None
        self.assertAlmostEqual(hasil["cushion_points"], 4.2, places=2)
        self.assertLess(hasil["cushion_points"], 8.0)
        self.assertIn("sempit", hasil["alasan"])

    def test_varians_besar_lebih_tebal(self):
        # std 25 -> dasar 10,5; serang + form datar -> 10,5.
        stats = {
            "ortg_home": 114.0,
            "ortg_away": 114.0,
            "ortg_liga_rata": 114.0,
            "total_rata_5laga": 225.0,
            "total_rata_musim": 225.0,
        }
        hasil = analis.bantalan_adaptif(
            stats, {"median": 219.0, "std": 25.0}, CFG_ANALIS
        )
        self.assertIsNotNone(hasil)
        assert hasil is not None
        self.assertAlmostEqual(hasil["cushion_points"], 10.5, places=2)
        self.assertIn("lebar", hasil["alasan"])

    def test_data_sim_hilang_kembali_none(self):
        stats = {
            "ortg_home": 114.0,
            "ortg_away": 114.0,
            "ortg_liga_rata": 114.0,
            "total_rata_5laga": 225.0,
            "total_rata_musim": 225.0,
        }
        # Median hilang -> None (jangan tebak).
        self.assertIsNone(
            analis.bantalan_adaptif(stats, {"median": None, "std": 19.0}, CFG_ANALIS)
        )
        # Std hilang -> None.
        self.assertIsNone(
            analis.bantalan_adaptif(stats, {"median": 219.0, "std": None}, CFG_ANALIS)
        )
        # Keduanya hilang -> None.
        self.assertIsNone(analis.bantalan_adaptif(stats, {}, CFG_ANALIS))

    def test_faktor_none_dilewati_dan_dicatat(self):
        # ORtg tidak ada -> faktor serang dilewati (0) + tidak terverifikasi;
        # form tetap dihitung. std 19 -> 7,98; form +10 * 0,25 = +2,5 -> 10,48.
        stats = {
            "ortg_home": None,
            "ortg_away": None,
            "ortg_liga_rata": None,
            "total_rata_5laga": 235.0,
            "total_rata_musim": 225.0,
        }
        hasil = analis.bantalan_adaptif(
            stats, {"median": 219.0, "std": 19.0}, CFG_ANALIS
        )
        self.assertIsNotNone(hasil)
        assert hasil is not None
        self.assertAlmostEqual(hasil["cushion_points"], 10.48, places=2)
        self.assertIn("kekuatan_serang", hasil["faktor"]["tidak_terverifikasi"])
        self.assertNotIn("form_skor", hasil["faktor"]["tidak_terverifikasi"])
        self.assertFalse(hasil["faktor"]["kekuatan_serang"]["terverifikasi"])
        self.assertTrue(hasil["faktor"]["form_skor"]["terverifikasi"])
        self.assertIn("tidak tersedia", hasil["alasan"])

    def test_clamp_min_dan_max(self):
        stats = {
            "ortg_home": 100.0,
            "ortg_away": 100.0,
            "ortg_liga_rata": 114.0,
            "total_rata_5laga": 200.0,
            "total_rata_musim": 225.0,
        }
        # std 5 -> dasar 2,1; serang -14 * 0,5 = -7; form -25 * 0,25 = -6,25;
        # mentah -11,15 -> clamp ke min 4,0 + dicatat.
        hasil = analis.bantalan_adaptif(
            stats, {"median": 219.0, "std": 5.0}, CFG_ANALIS
        )
        self.assertIsNotNone(hasil)
        assert hasil is not None
        self.assertEqual(hasil["cushion_points"], 4.0)
        self.assertEqual(hasil["faktor"]["dibatasi"]["ke"], "min")
        self.assertIn("dibatasi", hasil["alasan"])

        stats_panas = {
            "ortg_home": 125.0,
            "ortg_away": 125.0,
            "ortg_liga_rata": 110.0,
            "total_rata_5laga": 260.0,
            "total_rata_musim": 225.0,
        }
        # std 30 -> dasar 12,6; serang +15 * 0,5 = +7,5; form +35 * 0,25
        # = +8,75; mentah 28,85 -> clamp ke max 20,0.
        hasil = analis.bantalan_adaptif(
            stats_panas, {"median": 219.0, "std": 30.0}, CFG_ANALIS
        )
        self.assertIsNotNone(hasil)
        assert hasil is not None
        self.assertEqual(hasil["cushion_points"], 20.0)
        self.assertEqual(hasil["faktor"]["dibatasi"]["ke"], "max")

    def test_validasi(self):
        stats = {
            "ortg_home": 114.0,
            "ortg_away": 114.0,
            "ortg_liga_rata": 114.0,
            "total_rata_5laga": 225.0,
            "total_rata_musim": 225.0,
        }
        with self.assertRaises(ValueError):
            analis.bantalan_adaptif(["bukan", "dict"], DIST_DET_ATL, CFG_ANALIS)
        with self.assertRaises(ValueError):
            analis.bantalan_adaptif(stats, ["bukan", "dict"], CFG_ANALIS)
        with self.assertRaises(ValueError):
            analis.bantalan_adaptif(stats, {"median": 219.0, "std": "19"}, CFG_ANALIS)
        with self.assertRaises(ValueError):
            analis.bantalan_adaptif(stats, {"median": 219.0, "std": -5.0}, CFG_ANALIS)
        with self.assertRaises(ValueError):
            analis.bantalan_adaptif(
                {**stats, "ortg_home": "114"}, DIST_DET_ATL, CFG_ANALIS
            )

    def test_config_asli_playstyle(self):
        # Tanpa cfg eksplisit: baca playstyle.yaml v13 (nilai sama).
        stats = {
            "ortg_home": 114.0,
            "ortg_away": 114.0,
            "ortg_liga_rata": 114.0,
            "total_rata_5laga": 225.0,
            "total_rata_musim": 225.0,
        }
        hasil = analis.bantalan_adaptif(stats, {"median": 219.0, "std": 19.0})
        self.assertIsNotNone(hasil)
        assert hasil is not None
        self.assertAlmostEqual(hasil["cushion_points"], 7.98, places=2)


class TestNilaiWajar(unittest.TestCase):
    def test_wajar_contoh_user(self):
        # Contoh user: acuan 221,5, harga 75¢ di garis 229,5 (8 poin di
        # atas acuan) -> wajar bila bantalan yang diminta 8.
        hasil = analis.nilai_wajar(
            acuan_sim=221.5,
            garis_market=225.5,
            garis_harga=229.5,
            harga_cents=75,
            bantalan_dibutuhkan_poin=8.0,
            cfg=CFG_ANALIS,
        )
        self.assertEqual(hasil["penilaian"], "wajar")
        self.assertEqual(hasil["jarak_poin"], 8.0)
        self.assertEqual(hasil["acuan_sim"], 221.5)
        self.assertEqual(hasil["garis_market"], 225.5)
        self.assertEqual(hasil["garis_harga"], 229.5)
        self.assertEqual(hasil["harga_cents"], 75.0)
        self.assertEqual(hasil["bantalan_dibutuhkan_poin"], 8.0)
        self.assertIn("221,5", hasil["penjelasan"])
        self.assertIn("229,5", hasil["penjelasan"])
        self.assertIn("8", hasil["penjelasan"])
        self.assertIn("wajar", hasil["penjelasan"])

    def test_wajar_jarak_lebih_besar(self):
        # Jarak 12 > bantalan 8 -> wajar.
        hasil = analis.nilai_wajar(
            acuan_sim=219.0,
            garis_market=225.5,
            garis_harga=231.0,
            harga_cents=80,
            bantalan_dibutuhkan_poin=8.0,
            cfg=CFG_ANALIS,
        )
        self.assertEqual(hasil["penilaian"], "wajar")
        self.assertEqual(hasil["jarak_poin"], 12.0)

    def test_di_bawah_wajar(self):
        # Jarak 5 < bantalan 8 -> di bawah wajar.
        hasil = analis.nilai_wajar(
            acuan_sim=221.5,
            garis_market=225.5,
            garis_harga=226.5,
            harga_cents=75,
            bantalan_dibutuhkan_poin=8.0,
            cfg=CFG_ANALIS,
        )
        self.assertEqual(hasil["penilaian"], "di_bawah_wajar")
        self.assertEqual(hasil["jarak_poin"], 5.0)
        self.assertIn("di bawah wajar", hasil["penjelasan"])
        self.assertIn("terlalu dekat", hasil["penjelasan"])

    def test_di_bawah_wajar_laga_menuntut_lebih(self):
        # Bantalan adaptif 12,73 (dua penyerang panas): jarak 8 tidak cukup.
        hasil = analis.nilai_wajar(
            acuan_sim=221.5,
            garis_market=225.5,
            garis_harga=229.5,
            harga_cents=75,
            bantalan_dibutuhkan_poin=12.73,
            cfg=CFG_ANALIS,
        )
        self.assertEqual(hasil["penilaian"], "di_bawah_wajar")

    def test_tidak_terverifikasi_bila_input_hilang(self):
        # Acuan hilang -> tidak terverifikasi, jarak None.
        hasil = analis.nilai_wajar(
            acuan_sim=None,
            garis_market=225.5,
            garis_harga=229.5,
            harga_cents=75,
            bantalan_dibutuhkan_poin=8.0,
            cfg=CFG_ANALIS,
        )
        self.assertEqual(hasil["penilaian"], "tidak_terverifikasi")
        self.assertIsNone(hasil["jarak_poin"])
        self.assertIn("acuan_sim", hasil["penjelasan"])
        # Bantalan hilang -> tidak terverifikasi (jarak tetap dihitung).
        hasil = analis.nilai_wajar(
            acuan_sim=221.5,
            garis_market=225.5,
            garis_harga=229.5,
            harga_cents=75,
            bantalan_dibutuhkan_poin=None,
            cfg=CFG_ANALIS,
        )
        self.assertEqual(hasil["penilaian"], "tidak_terverifikasi")
        self.assertEqual(hasil["jarak_poin"], 8.0)
        self.assertIn("bantalan_dibutuhkan_poin", hasil["penjelasan"])
        # Harga hilang -> tidak terverifikasi.
        hasil = analis.nilai_wajar(
            acuan_sim=221.5,
            garis_market=225.5,
            garis_harga=229.5,
            harga_cents=None,
            bantalan_dibutuhkan_poin=8.0,
            cfg=CFG_ANALIS,
        )
        self.assertEqual(hasil["penilaian"], "tidak_terverifikasi")

    def test_validasi(self):
        with self.assertRaises(ValueError):
            analis.nilai_wajar(
                acuan_sim="221,5",
                garis_market=225.5,
                garis_harga=229.5,
                harga_cents=75,
                bantalan_dibutuhkan_poin=8.0,
                cfg=CFG_ANALIS,
            )
        with self.assertRaises(ValueError):
            analis.nilai_wajar(
                acuan_sim=221.5,
                garis_market=225.5,
                garis_harga=229.5,
                harga_cents=75,
                bantalan_dibutuhkan_poin=-1.0,
                cfg=CFG_ANALIS,
            )


if __name__ == "__main__":
    unittest.main()
