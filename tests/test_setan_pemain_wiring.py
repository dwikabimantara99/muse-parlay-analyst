"""Tes wiring setan per pemain ke artefak analyze — TANPA network, TANPA membaca out/.

Celah yang ditutup tes ini (ditemukan koordinator saat integrasi build
vonis + setan per pemain, 2026-11-23): engine/stress.skenario_panas SUDAH
membaca analysis["setan_pemain"] bila ada, tapi TIDAK ADA pemanggil
produksi yang mengisi blok itu — analyze tidak pernah mengambil data
pemain, jadi demon selalu fallback ke setan umum +18,07 dan laporan
tidak pernah menampilkan total setan per pemain. Build ini menutupnya:
engine/nba_analysis.py Tahap 5c mengambil data pemain (sekali per
proses, cache) + menghitung demon per laga + melampirkannya ke artefak.

Semua fixture dibangun di dalam file ini, jadi tes lulus di checkout
bersih. Angka ekspektasi dihitung tangan dari definisi di docstring
engine/setan_pemain.py (total setan = median - poin 3P normal +
poin 3P setan; poin setan = percobaan yang diharapkan x % terbaik
liga x 3).
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import nba_analysis as na
from engine import stress
from ingest import pemain_3p as p3p
from ingest.common import FetchResult

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
    "setan_pemain": {
        "enabled": True,
        "pct_terbaik_min_total_3pa": 50,
        "ambang_menit_rotasi": 10.0,
    },
}

# CDF sintetis (sama seperti tests/test_stress.py).
MARKETS = {
    "moneyline_home": 0.6,
    "moneyline_away": 0.4,
    "total_under_200.5": 0.10,
    "total_under_210.5": 0.30,
    "total_under_220.5": 0.50,
    "total_under_230.5": 0.70,
    "total_under_240.5": 0.85,
    "total_under_250.5": 0.95,
}

TANGGA = [
    {"line": 250.5, "side": "under", "price_cents": 90.0, "thin": True},
    {"line": 230.5, "side": "under", "price_cents": 70.0, "thin": False},
    {"line": 240.5, "side": "under", "price_cents": 80.0, "thin": False},
]


def _pemain(nama, tim, gp, menit, fg3a, pct):
    """Satu baris pemain skema ingest/pemain_3p.py (sama seperti test_setan_pemain)."""
    return {
        "player": nama,
        "team": tim,
        "games_played": gp,
        "mp_per_game": menit,
        "fg3a_per_game": fg3a,
        "fg3_per_game": round(fg3a * pct, 2) if pct is not None else None,
        "fg3_pct": pct,
        "fg3a_total": fg3a * gp if gp is not None else None,
        "bbref_slug": None,
        "source": "stats.nba.com",
    }


# Fixture pemain AAA vs BBB (+ C1 di tim lain, penentu % terbaik liga).
# % terbaik liga = 0.50 (C1, fg3a_total 80 >= 50).
# Semua main: percobaan 6+4+5+2 = 17; poin normal
# (6x0.40 + 4x0.30 + 5x0.45 + 2x0.35) x 3 = 19.65; poin setan
# 17 x 0.50 x 3 = 25.50. Median 220.5 -> total setan 226.35.
PEMAIN_FIXTURE = [
    _pemain("A1", "AAA", 10, 30.0, 6.0, 0.40),
    _pemain("A2", "AAA", 10, 25.0, 4.0, 0.30),
    _pemain("B1", "BBB", 10, 28.0, 5.0, 0.45),
    _pemain("B2", "BBB", 10, 12.0, 2.0, 0.35),
    _pemain("C1", "CCC", 10, 30.0, 8.0, 0.50),
]


def _analysis(median=220.5, garis_market=224.5, setan_pemain=None):
    """Artefak nba_analysis minimal untuk tes skenario_panas."""
    artefak = {
        "match_id": "BBB@AAA_2026-11-22",
        "simulation": {
            "markets": dict(MARKETS),
            "score_distribution": {"total": {"median": median}},
        },
        "market": {
            "main_total_line": garis_market,
            "totals": list(TANGGA),
        },
        "legs": [{"line": 240.5, "ticket": "insurance", "price_cents": 80.0}],
    }
    if setan_pemain is not None:
        artefak["setan_pemain"] = setan_pemain
    return artefak


def _hasil_fetch_ok(pemain=None):
    return FetchResult(
        "stats.nba.com",
        2,
        "2026-11-23T05:00:00+00:00",
        True,
        data=list(PEMAIN_FIXTURE if pemain is None else pemain),
    )


def _hasil_fetch_gagal():
    return FetchResult(
        "stats.nba.com",
        2,
        "2026-11-23T05:00:00+00:00",
        False,
        error="stats.nba.com timeout; BBRef timeout",
    )


class TestSkenarioPanasMembacaBlokArtefak(unittest.TestCase):
    def test_blok_setan_pemain_dipakai_tanpa_kwarg(self):
        """Kasus kunci: skenario_panas memakai analysis['setan_pemain']."""
        hasil = stress.skenario_panas(
            _analysis(
                setan_pemain={
                    "status": "ok",
                    "total_setan_pemain": 250.0,
                    "geser_setan_pemain": 29.5,
                    "deviasi_setan_pemain_dari_garis_bandar": 25.5,
                }
            ),
            cfg=CFG,
        )
        self.assertTrue(hasil["setan_pemain_dipakai"])
        self.assertEqual(hasil["skenario"]["setan"]["sumber_setan"], "pemain")
        # Geser = total setan - median = 250.0 - 220.5 = 29.5.
        self.assertEqual(hasil["skenario"]["setan"]["geser_points"], 29.5)
        self.assertEqual(hasil["skenario"]["setan"]["total_setan_pemain"], 250.0)
        kaki = hasil["kaki"][0]
        self.assertEqual(kaki["total_setan_pemain"], 250.0)
        # Total setan 250.0 > garis kaki 240.5 -> flag rapuh.
        self.assertTrue(kaki["flag_setan_pemain"])

    def test_tanpa_blok_fallback_ke_setan_umum(self):
        hasil = stress.skenario_panas(_analysis(), cfg=CFG)
        self.assertFalse(hasil["setan_pemain_dipakai"])
        self.assertEqual(hasil["skenario"]["setan"]["sumber_setan"], "umum")
        self.assertEqual(hasil["skenario"]["setan"]["geser_points"], 25.0)
        self.assertIsNone(hasil["skenario"]["setan"]["total_setan_pemain"])

    def test_blok_gagal_tidak_dipakai(self):
        hasil = stress.skenario_panas(
            _analysis(
                setan_pemain={"status": "gagal", "error": "fetch pemain 3P gagal"}
            ),
            cfg=CFG,
        )
        self.assertFalse(hasil["setan_pemain_dipakai"])
        self.assertEqual(hasil["skenario"]["setan"]["sumber_setan"], "umum")


class TestBlokSetanPemain(unittest.TestCase):
    def _artefak(self, entries=None):
        return {"injuries": {"entries": list(entries or [])}}

    def test_ok_total_dihitung_tangan(self):
        with mock.patch.object(
            p3p, "fetch_pemain_3p_cached", return_value=_hasil_fetch_ok()
        ):
            blok = na._blok_setan_pemain(
                "AAA",
                "BBB",
                220.5,
                224.5,
                self._artefak(),
                CFG,
                "2026-11-23T05:00:00+00:00",
                "2026-11-23",
            )
        self.assertEqual(blok["status"], "ok")
        self.assertIsNone(blok["error"])
        # 220.5 - 19.65 + 25.50 = 226.35 (lihat catatan fixture).
        self.assertAlmostEqual(blok["total_setan_pemain"], 226.35, places=2)
        self.assertAlmostEqual(blok["geser_setan_pemain"], 5.85, places=2)
        # Deviasi vs garis bandar: 226.35 - 224.5 = 1.85.
        self.assertAlmostEqual(
            blok["deviasi_setan_pemain_dari_garis_bandar"], 1.85, places=2
        )
        self.assertEqual(blok["sources"], ["stats.nba.com"])

    def test_pemain_out_dikeluarkan_dari_percobaan(self):
        # B1 OUT: percobaan 17 -> 12; poin normal 19.65 -> 12.90;
        # poin setan 25.50 -> 18.00; total 220.5 - 12.90 + 18.00 = 225.60.
        with mock.patch.object(
            p3p, "fetch_pemain_3p_cached", return_value=_hasil_fetch_ok()
        ):
            blok = na._blok_setan_pemain(
                "AAA",
                "BBB",
                220.5,
                224.5,
                self._artefak(
                    [{"player": "B1", "status": "OUT", "team_tricode": "BBB"}]
                ),
                CFG,
                "2026-11-23T05:00:00+00:00",
                "2026-11-23",
            )
        self.assertEqual(blok["status"], "ok")
        self.assertAlmostEqual(blok["total_setan_pemain"], 225.60, places=2)

    def test_fetch_gagal_jadi_blok_gagal_bukan_lempar(self):
        with mock.patch.object(
            p3p, "fetch_pemain_3p_cached", return_value=_hasil_fetch_gagal()
        ):
            blok = na._blok_setan_pemain(
                "AAA",
                "BBB",
                220.5,
                224.5,
                self._artefak(),
                CFG,
                "2026-11-23T05:00:00+00:00",
                "2026-11-23",
            )
        self.assertEqual(blok["status"], "gagal")
        self.assertIn("timeout", blok["error"])
        self.assertIsNone(blok.get("total_setan_pemain"))

    def test_nonaktif_tanpa_fetch(self):
        cfg_mati = {
            **CFG,
            "setan_pemain": {**CFG["setan_pemain"], "enabled": False},
        }
        panggilan = mock.Mock(return_value=_hasil_fetch_ok())
        with mock.patch.object(p3p, "fetch_pemain_3p_cached", panggilan):
            blok = na._blok_setan_pemain(
                "AAA",
                "BBB",
                220.5,
                224.5,
                self._artefak(),
                cfg_mati,
                "2026-11-23T05:00:00+00:00",
                "2026-11-23",
            )
        self.assertEqual(blok["status"], "nonaktif")
        panggilan.assert_not_called()

    def test_median_none_jadi_blok_gagal(self):
        panggilan = mock.Mock(return_value=_hasil_fetch_ok())
        with mock.patch.object(p3p, "fetch_pemain_3p_cached", panggilan):
            blok = na._blok_setan_pemain(
                "AAA",
                "BBB",
                None,
                224.5,
                self._artefak(),
                CFG,
                "2026-11-23T05:00:00+00:00",
                "2026-11-23",
            )
        self.assertEqual(blok["status"], "gagal")
        self.assertEqual(blok["error"], "median_tidak_ada")
        panggilan.assert_not_called()


class TestMusimNbaDariTanggal(unittest.TestCase):
    def test_oktober_musim_tahun_itu(self):
        self.assertEqual(na._musim_nba_dari_tanggal("2026-11-23"), "2026-27")
        self.assertEqual(na._musim_nba_dari_tanggal("2027-10-20"), "2027-28")

    def test_januari_musim_tahun_sebelumnya(self):
        self.assertEqual(na._musim_nba_dari_tanggal("2027-03-15"), "2026-27")
        self.assertEqual(na._musim_nba_dari_tanggal("2026-09-30"), "2025-26")

    def test_tanggal_rusak_value_error(self):
        with self.assertRaises(ValueError):
            na._musim_nba_dari_tanggal("bukan-tanggal")


class TestCachePemain3p(unittest.TestCase):
    def setUp(self):
        p3p.bersihkan_cache_pemain_3p()
        self.addCleanup(p3p.bersihkan_cache_pemain_3p)

    def test_satu_tarikan_untuk_dua_panggilan(self):
        panggilan = mock.Mock(return_value=_hasil_fetch_ok())
        with mock.patch.object(p3p, "fetch_pemain_3p", panggilan):
            pertama = p3p.fetch_pemain_3p_cached(season="2026-27")
            kedua = p3p.fetch_pemain_3p_cached(season="2026-27")
        self.assertEqual(panggilan.call_count, 1)
        self.assertIs(pertama, kedua)

    def test_musim_beda_tarikan_beda(self):
        panggilan = mock.Mock(return_value=_hasil_fetch_ok())
        with mock.patch.object(p3p, "fetch_pemain_3p", panggilan):
            p3p.fetch_pemain_3p_cached(season="2026-27")
            p3p.fetch_pemain_3p_cached(season="2025-26")
        self.assertEqual(panggilan.call_count, 2)

    def test_hasil_gagal_tidak_di_cache(self):
        panggilan = mock.Mock(return_value=_hasil_fetch_gagal())
        with mock.patch.object(p3p, "fetch_pemain_3p", panggilan):
            p3p.fetch_pemain_3p_cached(season="2026-27")
            p3p.fetch_pemain_3p_cached(season="2026-27")
        self.assertEqual(panggilan.call_count, 2)


class TestSkemaMenerimaBlokSetanPemain(unittest.TestCase):
    def test_blok_ok_valid(self):
        artefak = na.minimal_nba_analysis(
            "BBB@AAA_2026-11-23", "AAA", "BBB", "2026-11-23", []
        )
        artefak["setan_pemain"] = {
            "status": "ok",
            "total_setan_pemain": 226.35,
            "geser_setan_pemain": 5.85,
            "deviasi_setan_pemain_dari_garis_bandar": 1.85,
            "sources": ["stats.nba.com"],
            "tier": 2,
            "fetched_at": "2026-11-23T05:00:00+00:00",
            "error": None,
        }
        self.assertIsNone(na.validate_nba_analysis(artefak))

    def test_blok_gagal_valid(self):
        artefak = na.minimal_nba_analysis(
            "BBB@AAA_2026-11-23", "AAA", "BBB", "2026-11-23", []
        )
        artefak["setan_pemain"] = {
            "status": "gagal",
            "sources": [],
            "tier": None,
            "fetched_at": "2026-11-23T05:00:00+00:00",
            "error": "fetch pemain 3P gagal",
        }
        self.assertIsNone(na.validate_nba_analysis(artefak))


if __name__ == "__main__":
    unittest.main()
