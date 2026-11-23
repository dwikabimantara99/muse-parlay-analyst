"""Tes Patch #3 v18.1: peta rim protector 21/30 -> 30/30 + tier fallback.

Konteks (LAPORAN-V18-1-C.md): diagnosa live 2026-11-23 membuktikan
9 tim yang hilang (ATL, DET, GSW, HOU, IND, LAC, NYK, ORL, PHX)
BUKAN karena mapping tricode atau normalisasi nama — join posisi
berhasil 14-16/14-17 pemain per tim dan PHO->PHX terbukti jalan —
melainkan karena TIDAK ADA big rotasi tim-tim itu yang mencapai
BLK >= 1,0 (terbaik 0,8-0,9). Perbaikannya adalah tier fallback
terukur (BLK >= 0,7, MP >= 18, top-1 big) + label tier transparan.

Tes cakupan membaca config/rim_protector_2026-27.json yang
di-commit (bukan fixture) — peta yang di-regenerasi script adalah
artefak yang dipakai veto di produksi.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import config as config_mod
from scripts import fetch_rim_protector as frp

ROOT = Path(__file__).resolve().parent.parent
PEMETAAN = ROOT / "config" / "rim_protector_2026-27.json"

POSISI_BIG = ["C", "PF", "F-C", "C-F"]

# 20 tim slate 24 Nov (tugas koordinator v18.1): minimum mutlak —
# semuanya wajib terpetakan walau target 30/30 tidak tercapai.
TIM_SLATE_24_NOV = {
    "MEM",
    "CHA",
    "POR",
    "PHI",
    "OKC",
    "IND",
    "MIL",
    "TOR",
    "BKN",
    "MIN",
    "CLE",
    "CHI",
    "PHX",
    "NOP",
    "LAC",
    "HOU",
    "UTA",
    "LAL",
    "SAS",
    "SAC",
}

# 9 tim yang hilang di peta v18 (21/30).
TIM_HILANG_V18 = {"ATL", "DET", "GSW", "HOU", "IND", "LAC", "NYK", "ORL", "PHX"}


def _pemain(nama, tim, gp, mp, blk, pos):
    """Satu baris pemain blok (skema parse_stats_nba_blok)."""
    return {
        "player": nama,
        "team": tim,
        "games_played": gp,
        "mp_per_game": mp,
        "blk_per_game": blk,
        "pos": pos,
        "source": "fixture",
    }


class TestTurunkanPemetaanFallback(unittest.TestCase):
    """Tier fallback di turunkan_pemetaan (fail-first v18.1)."""

    def test_fallback_mengisi_tim_tanpa_pemain_primer(self):
        """Tim yang 0 pemain primer dapat top-1 big fallback (BLK 0,7)."""
        pemain = [
            # ATL v18: big terbaik 0,8 blok — gagal primer, lolos fallback.
            _pemain("Onyeka Okongwu", "ATL", 17, 30.9, 0.8, "C"),
            _pemain("Jalen Johnson", "ATL", 14, 34.2, 0.5, "PF"),
        ]
        pemetaan, _tanpa = frp.turunkan_pemetaan(
            pemain,
            3,
            18.0,
            1.0,
            2,
            POSISI_BIG,
            fallback_enabled=True,
            fallback_min_mp=18.0,
            fallback_min_blk=0.7,
        )
        self.assertIn("ATL", pemetaan)
        self.assertEqual(len(pemetaan["ATL"]), 1)
        self.assertEqual(pemetaan["ATL"][0]["player"], "Onyeka Okongwu")
        self.assertEqual(pemetaan["ATL"][0]["tier"], "fallback")

    def test_fallback_hanya_top1_walau_beberapa_lolos(self):
        """Fallback mengambil top-1 saja (bukan max_per_team)."""
        pemain = [
            _pemain("Alperen Sengun", "HOU", 15, 33.0, 0.9, "C"),
            _pemain("Jabari Smith Jr.", "HOU", 17, 33.3, 0.9, "PF"),
            _pemain("Tari Eason", "HOU", 17, 24.9, 0.9, "PF"),
        ]
        pemetaan, _tanpa = frp.turunkan_pemetaan(
            pemain,
            3,
            18.0,
            1.0,
            2,
            POSISI_BIG,
            fallback_enabled=True,
            fallback_min_mp=18.0,
            fallback_min_blk=0.7,
        )
        self.assertEqual(len(pemetaan["HOU"]), 1)
        # Seri BPG 0,9 -> menit terbesar menang (Jabari 33,3).
        self.assertEqual(pemetaan["HOU"][0]["player"], "Jabari Smith Jr.")
        self.assertEqual(pemetaan["HOU"][0]["tier"], "fallback")

    def test_fallback_tidak_menyentuh_tim_yang_punya_primer(self):
        """Tim dengan >= 1 pemain primer TIDAK dapat entri fallback."""
        pemain = [
            _pemain("Victor Wembanyama", "SAS", 17, 30.3, 3.9, "C"),
            _pemain("Big Cadangan", "SAS", 15, 20.0, 0.8, "C"),
        ]
        pemetaan, _tanpa = frp.turunkan_pemetaan(
            pemain,
            3,
            18.0,
            1.0,
            2,
            POSISI_BIG,
            fallback_enabled=True,
            fallback_min_mp=18.0,
            fallback_min_blk=0.7,
        )
        self.assertEqual(len(pemetaan["SAS"]), 1)
        self.assertEqual(pemetaan["SAS"][0]["player"], "Victor Wembanyama")
        self.assertEqual(pemetaan["SAS"][0]["tier"], "primary")

    def test_entri_primer_berlabel_primary(self):
        """Entri primer berlabel tier 'primary' (konsisten, transparan)."""
        pemain = [_pemain("Rudy Gobert", "MIN", 16, 29.4, 1.1, "C")]
        pemetaan, _tanpa = frp.turunkan_pemetaan(
            pemain,
            3,
            18.0,
            1.0,
            2,
            POSISI_BIG,
            fallback_enabled=True,
            fallback_min_mp=18.0,
            fallback_min_blk=0.7,
        )
        self.assertEqual(pemetaan["MIN"][0]["tier"], "primary")

    def test_fallback_menghormati_filter_posisi(self):
        """Guard/wing BLK tinggi TIDAK boleh jadi fallback (cacat v17)."""
        pemain = [
            # DET v18: Cade (PG, 0,9) + Huerter (SG, 0,9) di atas big.
            _pemain("Cade Cunningham", "DET", 15, 34.8, 0.9, "PG"),
            _pemain("Kevin Huerter", "DET", 16, 27.0, 0.9, "SG"),
            _pemain("Paul Reed", "DET", 16, 26.1, 0.9, "C"),
        ]
        pemetaan, _tanpa = frp.turunkan_pemetaan(
            pemain,
            3,
            18.0,
            1.0,
            2,
            POSISI_BIG,
            fallback_enabled=True,
            fallback_min_mp=18.0,
            fallback_min_blk=0.7,
        )
        self.assertEqual(len(pemetaan["DET"]), 1)
        self.assertEqual(pemetaan["DET"][0]["player"], "Paul Reed")
        self.assertEqual(pemetaan["DET"][0]["pos"], "C")

    def test_fallback_menghormati_min_games_dan_menit(self):
        """Fallback tetap mensyaratkan GP >= min_games + MP >= 18.

        Jalen Duren (DET, 1,0 blok tapi GP=2) dan Isaiah Jackson
        (LAC, 1,1 blok tapi MP=17,7) tetap TIDAK teridentifikasi —
        keterbatasan yang didokumentasikan, bukan dilonggarkan.
        """
        pemain = [
            _pemain("Jalen Duren", "DET", 2, 19.1, 1.0, "C"),
            _pemain("Isaiah Jackson", "LAC", 14, 17.7, 1.1, "C"),
            _pemain("Brook Lopez", "LAC", 15, 24.6, 0.9, "C"),
        ]
        pemetaan, _tanpa = frp.turunkan_pemetaan(
            pemain,
            3,
            18.0,
            1.0,
            2,
            POSISI_BIG,
            fallback_enabled=True,
            fallback_min_mp=18.0,
            fallback_min_blk=0.7,
        )
        self.assertNotIn("DET", pemetaan)
        self.assertEqual(pemetaan["LAC"][0]["player"], "Brook Lopez")

    def test_fallback_dimatikan_tidak_mengisi_tim_kosong(self):
        """fallback_enabled=False -> perilaku v18 (tim kosong hilang)."""
        pemain = [_pemain("Onyeka Okongwu", "ATL", 17, 30.9, 0.8, "C")]
        pemetaan, _tanpa = frp.turunkan_pemetaan(
            pemain, 3, 18.0, 1.0, 2, POSISI_BIG, fallback_enabled=False
        )
        self.assertNotIn("ATL", pemetaan)

    def test_tim_tetap_kosong_tanpa_big_fallback(self):
        """Tim tanpa big yang lolos ambang fallback tetap tanpa entri.

        TIDAK ada pemain yang dikarang: veto tidak_dievaluasi untuk
        tim itu (perilaku fail-closed dipertahankan).
        """
        pemain = [
            _pemain("Small Ball Lima", "XXX", 15, 30.0, 0.6, "C"),
            _pemain("Wing Blok", "XXX", 15, 30.0, 0.9, "SF"),
        ]
        pemetaan, _tanpa = frp.turunkan_pemetaan(
            pemain,
            3,
            18.0,
            1.0,
            2,
            POSISI_BIG,
            fallback_enabled=True,
            fallback_min_mp=18.0,
            fallback_min_blk=0.7,
        )
        self.assertNotIn("XXX", pemetaan)


class TestNormalisasiNamaDanTricode(unittest.TestCase):
    """Join posisi antar-sumber: normalisasi nama + mapping tricode."""

    def test_normalisasi_melucuti_aksen_dan_meringkas_spasi(self):
        self.assertEqual(frp.normalisasi_nama("Nikola Jokić"), "nikola jokic")
        self.assertEqual(frp.normalisasi_nama("Alperen Şengün"), "alperen sengun")
        self.assertEqual(
            frp.normalisasi_nama("Yanic Konan Niederhäuser"),
            "yanic konan niederhauser",
        )
        self.assertEqual(
            frp.normalisasi_nama("  P.J.   Washington "), "p.j. washington"
        )

    def test_gabung_posisi_mencocokkan_lintas_aksen(self):
        """Pemain stats.nba.com beraksen cocok dengan pos BBRef."""
        pemain = [_pemain("Nikola Jokić", "DEN", 15, 37.1, 1.0, None)]
        posisi = {("nikola jokic", "DEN"): "C"}
        frp.gabung_posisi(pemain, posisi)
        self.assertEqual(pemain[0]["pos"], "C")

    def test_parse_bbref_memetakan_tricode(self):
        """BBRef PHO/BRK/CHO -> PHX/BKN/CHA (konvensi stats.nba.com)."""
        html = """
        <table id="per_game_stats"><tbody>
        <tr><td data-stat="name_display">Khaman Maluach</td>
        <td data-stat="team_name_abbr">PHO</td>
        <td data-stat="games">15</td><td data-stat="mp_per_g">18.5</td>
        <td data-stat="blk_per_g">0.8</td><td data-stat="pos">C</td></tr>
        <tr><td data-stat="name_display">Day'Ron Sharpe</td>
        <td data-stat="team_name_abbr">BRK</td>
        <td data-stat="games">15</td><td data-stat="mp_per_g">23.8</td>
        <td data-stat="blk_per_g">1.2</td><td data-stat="pos">C</td></tr>
        <tr><td data-stat="name_display">Ryan Kalkbrenner</td>
        <td data-stat="team_name_abbr">CHO</td>
        <td data-stat="games">15</td><td data-stat="mp_per_g">18.2</td>
        <td data-stat="blk_per_g">1.1</td><td data-stat="pos">C</td></tr>
        </tbody></table>
        """
        hasil = frp.parse_bbref_blok(html)
        tim = {entri["player"]: entri["team"] for entri in hasil}
        self.assertEqual(tim["Khaman Maluach"], "PHX")
        self.assertEqual(tim["Day'Ron Sharpe"], "BKN")
        self.assertEqual(tim["Ryan Kalkbrenner"], "CHA")


class TestConfigFallback(unittest.TestCase):
    """Kunci fallback di config/playstyle.yaml (section hard_vetoes)."""

    def test_kunci_fallback_ada_dan_sesuai_spesifikasi(self):
        cfg = config_mod.load_playstyle()
        self.assertIs(
            config_mod.get_value(
                cfg, "hard_vetoes", "rim_protector_veto", "fallback_tier_enabled"
            ),
            True,
        )
        self.assertEqual(
            config_mod.get_value(
                cfg,
                "hard_vetoes",
                "rim_protector_veto",
                "fallback_min_minutes_pg",
            ),
            18.0,
        )
        self.assertEqual(
            config_mod.get_value(
                cfg, "hard_vetoes", "rim_protector_veto", "fallback_min_bpg"
            ),
            0.7,
        )


class TestCakupanPetaRegenerasi(unittest.TestCase):
    """Cakupan peta yang di-regenerasi (membaca JSON yang di-commit)."""

    @classmethod
    def setUpClass(cls):
        if not PEMETAAN.exists():
            raise unittest.SkipTest(f"peta tidak ada: {PEMETAAN}")
        cls.dokumen = json.loads(PEMETAAN.read_text(encoding="utf-8"))

    def test_peta_30_dari_30_tim(self):
        tim = self.dokumen.get("teams") or {}
        self.assertEqual(len(tim), 30, f"tim terpetakan: {sorted(tim)}")

    def test_sembilan_tim_hilang_v18_kini_terpetakan(self):
        tim = self.dokumen.get("teams") or {}
        hilang = TIM_HILANG_V18 - set(tim)
        self.assertEqual(hilang, set(), f"masih hilang: {sorted(hilang)}")

    def test_seluruh_tim_slate_24_nov_terpetakan(self):
        tim = self.dokumen.get("teams") or {}
        hilang = TIM_SLATE_24_NOV - set(tim)
        self.assertEqual(hilang, set(), f"tim slate 24 Nov hilang: {sorted(hilang)}")

    def test_setiap_entri_berlabel_tier_dan_posisi_big(self):
        """Tiap entri: tier primary/fallback + pos big (tanpa guard)."""
        tim = self.dokumen.get("teams") or {}
        for tricode, daftar in tim.items():
            self.assertIsInstance(daftar, list, tricode)
            self.assertGreater(len(daftar), 0, tricode)
            for entri in daftar:
                self.assertIn(
                    entri.get("tier"),
                    ("primary", "fallback"),
                    f"{tricode} {entri.get('player')}",
                )
                self.assertIn(
                    entri.get("pos"),
                    POSISI_BIG,
                    f"{tricode} {entri.get('player')}: pos {entri.get('pos')}",
                )
                self.assertGreaterEqual(entri["blk_per_game"], 0.7, entri)
                self.assertGreaterEqual(entri["mp_per_game"], 18.0, entri)
                self.assertGreaterEqual(entri["games_played"], 3, entri)

    def test_entri_fallback_maksimal_satu_per_tim(self):
        """Fallback top-1: paling banyak 1 entri fallback per tim."""
        tim = self.dokumen.get("teams") or {}
        for tricode, daftar in tim.items():
            n_fallback = sum(1 for e in daftar if e.get("tier") == "fallback")
            self.assertLessEqual(n_fallback, 1, tricode)
            if n_fallback:
                # Tim fallback murni: tidak ada entri primer di tim itu.
                self.assertEqual(len(daftar), 1, tricode)

    def test_rule_json_mencatat_parameter_fallback(self):
        rule = self.dokumen.get("rule") or {}
        fallback = rule.get("fallback") or {}
        self.assertIs(fallback.get("enabled"), True)
        self.assertEqual(fallback.get("min_mp_per_game"), 18.0)
        self.assertEqual(fallback.get("min_blk_per_game"), 0.7)


if __name__ == "__main__":
    unittest.main()
