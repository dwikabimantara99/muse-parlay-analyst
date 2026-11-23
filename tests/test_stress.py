"""Tes engine/stress.py — TANPA network, TANPA membaca out/.

Semua fixture dibangun di dalam file ini (CDF sintetis + tangga
sintetis), jadi tes lulus di checkout bersih — KECUALI TestDenChiSetan
(kasus uji wajib DEN@CHI dari artefak nyata; dilewati bila artefak
tidak ada). Angka ekspektasi dihitung tangan dari definisi di
docstring engine/stress.py (P_skenario(Under L) = CDF(L - geser),
interpolasi linear).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine import stress

# Config minimal: hanya kunci yang dibaca engine/stress.py.
CFG = {
    "stress": {
        "banjir_3p_points": 10.0,
        "banjir_ft_points": 15.0,
        "setan_points": 25.0,
    },
    "tickets": {
        "insurance": {"min_leg_prob": 0.74},
        "main": {"min_leg_prob": 0.65},
    },
}

# CDF sintetis (garis -> P(Under)): 200.5: 0,10; 210.5: 0,30;
# 220.5: 0,50; 230.5: 0,70; 240.5: 0,85; 250.5: 0,95.
MARKETS = {
    "moneyline_home": 0.6,
    "moneyline_away": 0.4,
    "total_under_200.5": 0.10,
    "total_over_200.5": 0.90,
    "total_under_210.5": 0.30,
    "total_under_220.5": 0.50,
    "total_under_230.5": 0.70,
    "total_under_240.5": 0.85,
    "total_under_250.5": 0.95,
}

# Tangga sintetis (sisi Under + satu entri Over untuk uji filter).
TANGGA = [
    {
        "line": 250.5,
        "side": "under",
        "price_cents": 90.0,
        "jup_estimated_cents": 90.5,
        "volume_usd": 5.0,
        "thin": True,
    },
    {
        "line": 230.5,
        "side": "under",
        "price_cents": 70.0,
        "jup_estimated_cents": 70.5,
        "volume_usd": 500.0,
        "thin": False,
    },
    {
        "line": 240.5,
        "side": "over",
        "price_cents": 20.0,
        "jup_estimated_cents": 20.5,
        "volume_usd": 500.0,
        "thin": False,
    },
    {
        "line": 240.5,
        "side": "under",
        "price_cents": 80.0,
        "jup_estimated_cents": 80.5,
        "volume_usd": 800.0,
        "thin": False,
    },
    {
        "line": 260.5,
        "side": "under",
        "price_cents": 95.0,
        "jup_estimated_cents": 95.5,
        "volume_usd": None,
        "thin": True,
    },
]


def _analysis(median=220.5, garis_market=224.5, tangga=None, legs=None):
    """Artefak nba_analysis minimal untuk tes (hanya blok yang dibaca)."""
    return {
        "match_id": "XXX@YYY_2026-11-22",
        "simulation": {
            "markets": dict(MARKETS),
            "score_distribution": {"total": {"median": median}},
        },
        "market": {
            "main_total_line": garis_market,
            "totals": list(TANGGA if tangga is None else tangga),
        },
        "legs": (
            legs
            if legs is not None
            else [
                {"line": 240.5, "ticket": "insurance", "price_cents": 80.0},
            ]
        ),
    }


class TestCdf(unittest.TestCase):
    def test_ekstrak_cdf_terurut_naik(self):
        cdf = stress.cdf_total_dari_markets(MARKETS)
        self.assertEqual(
            cdf,
            [
                (200.5, 0.10),
                (210.5, 0.30),
                (220.5, 0.50),
                (230.5, 0.70),
                (240.5, 0.85),
                (250.5, 0.95),
            ],
        )

    def test_tanpa_kunci_total_under_gagal(self):
        with self.assertRaises(ValueError):
            stress.cdf_total_dari_markets({"moneyline_home": 0.6})

    def test_peluang_di_luar_0_1_gagal(self):
        with self.assertRaises(ValueError):
            stress.cdf_total_dari_markets({"total_under_200.5": 1.5})

    def test_garis_kunci_tidak_valid_gagal(self):
        with self.assertRaises(ValueError):
            stress.cdf_total_dari_markets({"total_under_bukan_angka": 0.5})


class TestGeser(unittest.TestCase):
    def test_geser_nol_sama_dengan_cdf(self):
        cdf = stress.cdf_total_dari_markets(MARKETS)
        self.assertEqual(stress.p_under_digeser(cdf, 230.5, 0.0), 0.70)

    def test_geser_tepat_di_garis_tersimpan(self):
        cdf = stress.cdf_total_dari_markets(MARKETS)
        # CDF(240,5 - 10) = CDF(230,5) = 0,70.
        self.assertEqual(stress.p_under_digeser(cdf, 240.5, 10.0), 0.70)

    def test_interpolasi_linear_tengah_interval(self):
        cdf = stress.cdf_total_dari_markets(MARKETS)
        # CDF(240,5 - 15) = CDF(225,5) = 0,50 + 0,5 x (0,70-0,50) = 0,60.
        self.assertAlmostEqual(stress.p_under_digeser(cdf, 240.5, 15.0), 0.60)

    def test_dijepit_di_luar_jangkauan(self):
        cdf = stress.cdf_total_dari_markets(MARKETS)
        self.assertEqual(stress.p_under_digeser(cdf, 100.5, 0.0), 0.10)
        self.assertEqual(stress.p_under_digeser(cdf, 300.5, 0.0), 0.95)

    def test_geser_negatif_boleh(self):
        cdf = stress.cdf_total_dari_markets(MARKETS)
        # CDF(240,5 - (-4)) = CDF(244,5) = 0,85 + 0,4 x 0,10 = 0,89.
        self.assertAlmostEqual(stress.p_under_digeser(cdf, 240.5, -4.0), 0.89)


class TestTangga(unittest.TestCase):
    def test_hanya_under_dan_terurut(self):
        tangga = stress.tangga_under({"totals": TANGGA})
        self.assertEqual([e["line"] for e in tangga], [230.5, 240.5, 250.5, 260.5])

    def test_market_tanpa_tangga_kosong(self):
        self.assertEqual(stress.tangga_under(None), [])
        self.assertEqual(stress.tangga_under({}), [])


class TestGarisTahanBanjir(unittest.TestCase):
    def test_garis_terkecil_yang_lolos(self):
        cdf = stress.cdf_total_dari_markets(MARKETS)
        tangga = stress.tangga_under({"totals": TANGGA})
        # Target 0,74, geser 15: 240,5 -> CDF(225,5)=0,60 gagal;
        # 250,5 -> CDF(235,5)=0,70+0,5x0,15=0,775 lolos.
        entri = stress.garis_tahan_banjir(tangga, cdf, 15.0, 0.74)
        self.assertEqual(entri["line"], 250.5)
        self.assertEqual(entri["price_cents"], 90.0)

    def test_tidak_ada_garis_lolos_none(self):
        cdf = stress.cdf_total_dari_markets(MARKETS)
        tangga = stress.tangga_under({"totals": TANGGA})
        self.assertIsNone(stress.garis_tahan_banjir(tangga, cdf, 15.0, 0.99))


class TestGarisUntukHarga(unittest.TestCase):
    def test_harga_terdekat(self):
        tangga = stress.tangga_under({"totals": TANGGA})
        self.assertEqual(stress.garis_untuk_harga(tangga, 82.0)["line"], 240.5)
        self.assertEqual(stress.garis_untuk_harga(tangga, 94.0)["line"], 260.5)

    def test_seri_memilih_garis_lebih_kecil(self):
        tangga = stress.tangga_under({"totals": TANGGA})
        # 85 tepat di tengah 80 dan 90 -> garis 240,5 (lebih kecil).
        self.assertEqual(stress.garis_untuk_harga(tangga, 85.0)["line"], 240.5)

    def test_tanpa_entri_berharga_none(self):
        tangga = [
            {
                "line": 240.5,
                "side": "under",
                "price_cents": None,
                "jup_estimated_cents": None,
            }
        ]
        self.assertIsNone(stress.garis_untuk_harga(tangga, 82.0))


class TestSkenarioPanas(unittest.TestCase):
    def test_end_to_end_kaki_asuransi(self):
        hasil = stress.skenario_panas(_analysis(), cfg=CFG)
        self.assertEqual(hasil["format"], "nba_stress")
        self.assertEqual(hasil["banjir_terburuk"], "banjir_ft")
        self.assertEqual(hasil["geser_banjir_terburuk_points"], 15.0)
        self.assertEqual(hasil["skenario"]["konservatif"]["geser_points"], 4.0)
        self.assertEqual(hasil["skenario"]["setan"]["geser_points"], 25.0)
        kaki = hasil["kaki"]
        self.assertEqual(len(kaki), 1)
        self.assertEqual(kaki[0]["target_probability"], 0.74)
        # Normal 0,85; 3P CDF(230,5)=0,70; FT CDF(225,5)=0,60;
        # setan CDF(215,5)=0,30+0,5x0,20=0,40;
        # konservatif CDF(236,5)=0,70+0,6x0,15=0,79.
        self.assertEqual(
            kaki[0]["p_under"],
            {
                "normal": 0.85,
                "banjir_3p": 0.70,
                "banjir_ft": 0.60,
                "setan": 0.40,
                "konservatif": 0.79,
            },
        )
        self.assertFalse(kaki[0]["tahan_banjir"])
        tahan = kaki[0]["garis_tahan_banjir"]
        self.assertEqual(tahan["line"], 250.5)
        self.assertEqual(tahan["price_cents"], 90.0)
        self.assertTrue(tahan["thin"])
        self.assertIsNone(kaki[0]["alasan_tidak_tahan_banjir"])
        # Setan: 0,40 < 0,74 -> tidak tahan; garis tahan-setan:
        # 250,5 -> CDF(225,5)=0,60 gagal; 260,5 -> CDF(235,5)=0,775 lolos.
        self.assertFalse(kaki[0]["tahan_setan"])
        tahan_setan = kaki[0]["garis_tahan_setan"]
        self.assertEqual(tahan_setan["line"], 260.5)
        self.assertEqual(tahan_setan["price_cents"], 95.0)
        self.assertIsNone(kaki[0]["alasan_tidak_tahan_setan"])
        # Flag setan: normal 0,85 >= 0,74 tapi setan 0,40 < 0,74.
        self.assertTrue(kaki[0]["flag_setan"])
        alasan_flag = kaki[0]["alasan_flag_setan"]
        self.assertIn("85.0%", alasan_flag)
        self.assertIn("40.0%", alasan_flag)
        self.assertIn("selisih -45.0%", alasan_flag)

    def test_kaki_utama_target_065(self):
        analysis = _analysis(
            legs=[
                {"line": 240.5, "ticket": "main", "price_cents": 80.0},
            ]
        )
        hasil = stress.skenario_panas(analysis, cfg=CFG)
        kaki = hasil["kaki"][0]
        self.assertEqual(kaki["target_probability"], 0.65)
        # Banjir terburuk 0,60 < 0,65 -> tidak tahan; garis tahan:
        # 240,5 -> 0,60 gagal; 250,5 -> 0,775 lolos.
        self.assertFalse(kaki["tahan_banjir"])
        self.assertEqual(kaki["garis_tahan_banjir"]["line"], 250.5)
        # Setan 0,40 < 0,65 -> tidak tahan; garis tahan-setan 260,5
        # (250,5 -> CDF(225,5)=0,60 gagal; 260,5 -> 0,775 lolos).
        self.assertFalse(kaki["tahan_setan"])
        self.assertEqual(kaki["garis_tahan_setan"]["line"], 260.5)
        self.assertTrue(kaki["flag_setan"])

    def test_kaki_tahan_banjir_bila_garis_tinggi(self):
        analysis = _analysis(
            legs=[
                {"line": 260.5, "ticket": "main", "price_cents": 95.0},
            ]
        )
        hasil = stress.skenario_panas(analysis, cfg=CFG)
        kaki = hasil["kaki"][0]
        # FT: CDF(245,5) = 0,85 + 0,5 x 0,10 = 0,90 >= 0,65.
        self.assertAlmostEqual(kaki["p_under"]["banjir_ft"], 0.90)
        self.assertTrue(kaki["tahan_banjir"])
        self.assertEqual(kaki["garis_tahan_banjir"]["line"], 250.5)
        # Setan: CDF(235,5) = 0,70 + 0,5 x 0,15 = 0,775 >= 0,65 ->
        # tahan setan, TIDAK di-flag (bukan kerapuhan tersembunyi).
        self.assertAlmostEqual(kaki["p_under"]["setan"], 0.775)
        self.assertTrue(kaki["tahan_setan"])
        self.assertEqual(kaki["garis_tahan_setan"]["line"], 260.5)
        self.assertFalse(kaki["flag_setan"])
        self.assertIsNone(kaki["alasan_flag_setan"])

    def test_tidak_ada_garis_tahan_banjir_dinyatakan(self):
        tangga_pendek = [e for e in TANGGA if e["line"] <= 240.5]
        hasil = stress.skenario_panas(_analysis(tangga=tangga_pendek), cfg=CFG)
        kaki = hasil["kaki"][0]
        self.assertFalse(kaki["tahan_banjir"])
        self.assertIsNone(kaki["garis_tahan_banjir"])
        self.assertIn("tidak ada garis tangga", kaki["alasan_tidak_tahan_banjir"])
        # Setan: tidak ada garis yang lolos -> None + alasan setan.
        self.assertFalse(kaki["tahan_setan"])
        self.assertIsNone(kaki["garis_tahan_setan"])
        self.assertIn("tidak ada garis tahan-setan", kaki["alasan_tidak_tahan_setan"])
        # Flag tetap dihitung (tidak butuh tangga).
        self.assertTrue(kaki["flag_setan"])

    def test_kaki_eksplisit_dan_cek_harga(self):
        kaki = [{"line": 240.5, "ticket": "insurance", "price_cents": 82.0}]
        hasil = stress.skenario_panas(
            _analysis(legs=[]), kaki=kaki, harga_cek=[82.0], cfg=CFG
        )
        self.assertEqual(len(hasil["kaki"]), 1)
        self.assertEqual(hasil["kaki"][0]["price_cents"], 82.0)
        cek = hasil["cek_harga"][0]
        self.assertEqual(cek["harga_cents"], 82.0)
        self.assertEqual(cek["line"], 240.5)
        self.assertEqual(cek["p_under"]["banjir_ft"], 0.60)
        # Cek harga ikut membawa skenario setan (CDF(215,5)=0,40).
        self.assertEqual(cek["p_under"]["setan"], 0.40)

    def test_kaki_tanpa_garis_dilewati_dan_dicatat(self):
        analysis = _analysis(
            legs=[
                {"line": None, "ticket": "insurance", "price_cents": None},
                {"line": 240.5, "ticket": "main", "price_cents": 80.0},
            ]
        )
        hasil = stress.skenario_panas(analysis, cfg=CFG)
        self.assertEqual(len(hasil["kaki"]), 1)
        self.assertTrue(any("tanpa garis" in c for c in hasil["catatan"]))

    def test_tiket_tidak_dikenal_gagal(self):
        with self.assertRaises(ValueError):
            stress.skenario_panas(
                _analysis(),
                kaki=[{"line": 240.5, "ticket": "bukan_tiket"}],
                cfg=CFG,
            )

    def test_tanpa_simulasi_gagal(self):
        with self.assertRaises(ValueError):
            stress.skenario_panas({"match_id": "x"}, cfg=CFG)

    def test_tanpa_garis_market_konservatif_kosong(self):
        hasil = stress.skenario_panas(_analysis(garis_market=None), cfg=CFG)
        self.assertIsNone(hasil["skenario"]["konservatif"]["geser_points"])
        self.assertIsNone(hasil["kaki"][0]["p_under"]["konservatif"])
        self.assertTrue(any("konservatif" in c for c in hasil["catatan"]))

    def test_garis_market_di_bawah_median_geser_negatif(self):
        hasil = stress.skenario_panas(_analysis(garis_market=216.5), cfg=CFG)
        self.assertEqual(hasil["skenario"]["konservatif"]["geser_points"], -4.0)
        # CDF(240,5+4) = CDF(244,5) = 0,89.
        self.assertAlmostEqual(hasil["kaki"][0]["p_under"]["konservatif"], 0.89)

    def test_tanpa_tangga_garis_tahan_none(self):
        hasil = stress.skenario_panas(_analysis(tangga=[]), cfg=CFG)
        kaki = hasil["kaki"][0]
        self.assertIsNone(kaki["garis_tahan_banjir"])
        self.assertIn("tangga", kaki["alasan_tidak_tahan_banjir"])
        self.assertIsNone(kaki["garis_tahan_setan"])
        self.assertIn("tangga", kaki["alasan_tidak_tahan_setan"])
        # P(Under) tetap dihitung (tidak butuh tangga).
        self.assertEqual(kaki["p_under"]["normal"], 0.85)
        self.assertEqual(kaki["p_under"]["setan"], 0.40)
        self.assertTrue(kaki["flag_setan"])

    def test_kunci_config_hilang_gagal(self):
        with self.assertRaises(config_mod.ConfigError):
            stress.skenario_panas(_analysis(), cfg={"tickets": CFG["tickets"]})

    def test_kunci_setan_hilang_gagal(self):
        # Fail-closed: tanpa stress.setan_points, TIDAK ada default
        # dari kode (kunci banjir saja tidak cukup).
        cfg_tanpa_setan = {
            "stress": {
                "banjir_3p_points": 10.0,
                "banjir_ft_points": 15.0,
            },
            "tickets": CFG["tickets"],
        }
        with self.assertRaises(config_mod.ConfigError):
            stress.skenario_panas(_analysis(), cfg=cfg_tanpa_setan)

    def test_geser_setan_dibaca_dari_config(self):
        # Geser setan yang berbeda memberi P(setan) yang berbeda —
        # membuktikan nilainya berasal dari config, bukan hardcode.
        cfg_kecil = {
            "stress": {
                "banjir_3p_points": 10.0,
                "banjir_ft_points": 15.0,
                "setan_points": 5.0,
            },
            "tickets": CFG["tickets"],
        }
        hasil = stress.skenario_panas(_analysis(), cfg=cfg_kecil)
        # CDF(240,5-5) = CDF(235,5) = 0,70 + 0,5 x 0,15 = 0,775.
        self.assertEqual(hasil["kaki"][0]["p_under"]["setan"], 0.775)
        self.assertEqual(hasil["skenario"]["setan"]["geser_points"], 5.0)
        # 0,775 >= 0,74 -> tahan setan, tidak di-flag.
        self.assertTrue(hasil["kaki"][0]["tahan_setan"])
        self.assertFalse(hasil["kaki"][0]["flag_setan"])

    def test_geser_negatif_gagal(self):
        cfg_buruk = {
            "stress": {
                "banjir_3p_points": -1.0,
                "banjir_ft_points": 15.0,
                "setan_points": 25.0,
            },
            "tickets": CFG["tickets"],
        }
        with self.assertRaises(config_mod.ConfigError):
            stress.skenario_panas(_analysis(), cfg=cfg_buruk)

    def test_geser_setan_negatif_gagal(self):
        cfg_buruk = {
            "stress": {
                "banjir_3p_points": 10.0,
                "banjir_ft_points": 15.0,
                "setan_points": -1.0,
            },
            "tickets": CFG["tickets"],
        }
        with self.assertRaises(config_mod.ConfigError):
            stress.skenario_panas(_analysis(), cfg=cfg_buruk)

    def test_flag_setan_tidak_aktif_bila_normal_sudah_gagal(self):
        # Kaki 230,5 Asuransi: normal 0,70 < 0,74 (sudah gagal di
        # dunia normal) -> BUKAN kerapuhan tersembunyi, tidak di-flag
        # walau setan juga gagal (CDF(205,5)=0,20).
        analysis = _analysis(
            legs=[
                {"line": 230.5, "ticket": "insurance", "price_cents": 70.0},
            ]
        )
        hasil = stress.skenario_panas(analysis, cfg=CFG)
        kaki = hasil["kaki"][0]
        self.assertEqual(kaki["p_under"]["normal"], 0.70)
        self.assertEqual(kaki["p_under"]["setan"], 0.20)
        self.assertFalse(kaki["flag_setan"])
        self.assertIsNone(kaki["alasan_flag_setan"])


class TestDenChiSetan(unittest.TestCase):
    """Kasus uji wajib DEN@CHI 23 Nov 2026 (insiden banjir tripoin).

    Pengecualian dari aturan "tanpa membaca out/" di file ini: kasus
    ini WAJIB memakai artefak nyata (mandat koordinator). Dilewati
    bila artefak tidak ada (checkout bersih tetap hijau). Config yang
    dipakai adalah playstyle.yaml repo (v15, setan_points 18,07) —
    bila nilai config berubah, angka di sini harus diperbarui secara
    sadar.

    Yang diuji (koreksi user 09:52 WIB): setan MENANDAI kedua kaki
    DEN sebagai rapuh (flag_setan True) — deteksi sejak awal. BUKAN
    setan yang menolak DEN dari Asuransi; penolakan itu lewat GATE
    BANJIR p90 (Worker B), yang di sini hanya dicatat sebagai fakta
    (tahan_banjir False).
    """

    ARTEFAK = (
        Path(__file__).resolve().parent.parent
        / "out"
        / "analysis_verif_tahap4_2026-11-22.json"
    )

    def _den_chi(self):
        import json

        data = json.loads(self.ARTEFAK.read_text(encoding="utf-8"))
        for match in data["matches"]:
            if "den-chi" in match["match_id"]:
                return match["nba_analysis"]
        self.fail("DEN@CHI tidak ada di artefak verif tahap 4")

    @unittest.skipUnless(
        ARTEFAK.exists(), "artefak verif tahap 4 tidak ada di checkout ini"
    )
    def test_kedua_kaki_den_di_flag_setan(self):
        cfg = config_mod.load_playstyle()
        self.assertEqual(cfg["stress"]["setan_points"], 18.07)
        kaki = [
            {"line": 252.5, "ticket": "insurance", "price_cents": 82.0},
            {"line": 250.5, "ticket": "main", "price_cents": 79.0},
        ]
        hasil = stress.skenario_panas(self._den_chi(), kaki=kaki, cfg=cfg)
        self.assertEqual(hasil["skenario"]["setan"]["geser_points"], 18.07)
        by_ticket = {k["ticket"]: k for k in hasil["kaki"]}

        asuransi = by_ticket["insurance"]
        # Pola DEN: lolos normal (84,5% >= 82%) tapi jebol di setan.
        self.assertAlmostEqual(asuransi["p_under"]["normal"], 0.84474, places=4)
        self.assertAlmostEqual(asuransi["p_under"]["setan"], 0.53154, places=4)
        self.assertLess(asuransi["p_under"]["setan"], 0.82)
        self.assertTrue(asuransi["flag_setan"])
        self.assertIn("84.5%", asuransi["alasan_flag_setan"])
        self.assertIn("53.2%", asuransi["alasan_flag_setan"])
        # v18: TIDAK ADA garis tahan-setan Asuransi — target naik
        # 0,74 -> 0,82, dan garis tertinggi tangga (264,5) hanya
        # mencapai P(setan) 75,7% < 82% (di v17 garis itu tahan
        # dengan target 74%).
        self.assertIsNone(asuransi["garis_tahan_setan"])
        self.assertIsNotNone(asuransi["alasan_tidak_tahan_setan"])
        # Fakta (bukan vonis dari tes ini): DEN juga gagal gate banjir.
        self.assertFalse(asuransi["tahan_banjir"])

        utama = by_ticket["main"]
        self.assertAlmostEqual(utama["p_under"]["normal"], 0.81829, places=4)
        self.assertAlmostEqual(utama["p_under"]["setan"], 0.491474, places=4)
        self.assertLess(utama["p_under"]["setan"], 0.74)
        self.assertTrue(utama["flag_setan"])
        # v18: garis tahan-setan Utama NAIK ke 264,5 @94¢ (di v17:
        # 258,5 @88,5¢) karena target Utama naik 0,65 -> 0,74.
        tahan_utama = utama["garis_tahan_setan"]
        self.assertEqual(tahan_utama["line"], 264.5)
        self.assertEqual(tahan_utama["price_cents"], 94.0)
        self.assertFalse(utama["tahan_banjir"])


if __name__ == "__main__":
    unittest.main()
