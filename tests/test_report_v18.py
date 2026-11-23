"""Tes laporan 3 lapis + kalimat Skenario Mati (v18).

Mengunci struktur bagian Vonis di report/nba_report.py:
Lapisan 1 "Yang menentukan vonis" (pemblokir keras), Lapisan 2
"Catatan kualitas" (demerit), Lapisan 3 "Info tambahan (tidak
mengubah vonis)". Kalimat Skenario Mati dihitung tangan dari blok
setan_pemain (median 220, poin 3P normal 80, percobaan 70, garis
240,5 -> ambang 47,9%, normal 38,1%).

Tes render memakai artefak DAL live tersimpan sebagai basis +
nilai_vonis di-mock (vonis adalah modul worker A — tes ini
mengunci TAMPILAN, bukan hitungan vonis).
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from unittest import mock

from report import nba_report as report_mod

ROOT = Path(__file__).resolve().parents[1]
ARTEFAK_LIVE = ROOT / "out" / "analysis_live_2026-11-22.json"
ARTEFAK_VERIF = ROOT / "out" / "analysis_verif_tahap4_2026-11-22.json"


def _muat_artefak(jalur: Path) -> dict:
    dokumen = json.loads(jalur.read_text(encoding="utf-8"))
    return {
        m["nba_analysis"]["match_id"]: m["nba_analysis"] for m in dokumen["matches"]
    }


def _hasil_vonis(
    vonis: str,
    alasan: list[str],
    dievaluasi: bool = True,
    indikator: dict | None = None,
) -> dict:
    ind = {"dievaluasi": dievaluasi, "veto": {"menyala": False}}
    if indikator:
        ind.update(indikator)
    return {"vonis": vonis, "alasan": list(alasan), "indikator": ind}


class TestKlasifikasiAlasanVonis(unittest.TestCase):
    """_klasifikasi_alasan_vonis: kalimat -> lapis yang benar."""

    def test_veto_dan_ot_ekstrem_lapis_1(self):
        hasil = _hasil_vonis(
            "kuning",
            [
                "VETO rim protector: Nic Claxton (CHI) OUT",
                "potensi overtime ekstrem: peluang OT empiris 9.00% >= ambang 8.5%",
            ],
            indikator={"p_ot_empiris": 0.09},
        )
        lapis_1, lapis_2, lapis_3 = report_mod._klasifikasi_alasan_vonis(hasil)
        self.assertEqual(len(lapis_1), 2)
        self.assertEqual(lapis_2, [])
        self.assertEqual(lapis_3, [])

    def test_data_tidak_cukup_dan_tunggu_lineup_lapis_1(self):
        hasil = _hasil_vonis(
            "kuning",
            ["data_tidak_cukup: konteks tidak siap"],
            dievaluasi=False,
        )
        lapis_1, _, _ = report_mod._klasifikasi_alasan_vonis(hasil)
        self.assertEqual(len(lapis_1), 1)
        hasil2 = _hasil_vonis(
            "tunggu_lineup",
            ["TUNGGU_LINEUP: Giannis masih Questionable — bintang"],
        )
        lapis_1b, _, _ = report_mod._klasifikasi_alasan_vonis(hasil2)
        self.assertEqual(len(lapis_1b), 1)

    def test_demerit_lapis_2(self):
        hasil = _hasil_vonis(
            "menengah_hijau",
            [
                "rapuh banjir: peluang Under di garis U250.5 — banjir 3P 68.2% < 72%",
                "total tinggi: garis bandar 236.5 (ambang 235)",
                "model jauh dari pasar tanpa penjelasan cedera: gap +9.1 poin",
                "ekor gemuk: garis U250.5 jauh di atas total pasar",
                "lingkungan foul tinggi: FTr gabungan 0.300 >= p80",
                "spread tipis: |spread| 1.5 poin <= 2.0",
                "rem alami terpenuhi: pace lambat (Bottom-12)",
                "semua indikator sehat: 1 demerit (maks 1), rem alami: pertahanan Top-10",
                "edge kecil: edge +1.0% di bawah minimum (bentuk v17)",
            ],
        )
        lapis_1, lapis_2, lapis_3 = report_mod._klasifikasi_alasan_vonis(hasil)
        self.assertEqual(lapis_1, [])
        self.assertEqual(len(lapis_2), 9)
        self.assertEqual(lapis_3, [])

    def test_volume_investigasi_tidak_dinilai_lapis_3(self):
        hasil = _hasil_vonis(
            "menengah_hijau",
            [
                "volume garis tipis: $6 di bawah ambang (bentuk v17)",
                "gap besar ada penjelasan: model jauh dari pasar tapi ada cedera",
                "tidak dinilai (data sekunder hilang): foul_tinggi — vonis dihitung dari indikator lain.",
            ],
        )
        lapis_1, lapis_2, lapis_3 = report_mod._klasifikasi_alasan_vonis(hasil)
        self.assertEqual(lapis_1, [])
        self.assertEqual(lapis_2, [])
        self.assertEqual(len(lapis_3), 3)

    def test_ot_biasa_lapis_2_bukan_lapis_1(self):
        # Kalimat OT tanpa peluang ekstrem (5,4%) -> catatan kualitas.
        hasil = _hasil_vonis(
            "menengah_hijau",
            ["risiko overtime: peluang OT 5.4%"],
            indikator={"p_ot_empiris": 0.054},
        )
        lapis_1, lapis_2, _ = report_mod._klasifikasi_alasan_vonis(hasil)
        self.assertEqual(lapis_1, [])
        self.assertEqual(len(lapis_2), 1)

    def test_kalimat_tidak_dikenal_lapis_2(self):
        # Default aman: kalimat baru yang belum dikenali tampil
        # sebagai catatan kualitas (terlihat, bukan pemblokir keras).
        hasil = _hasil_vonis("menengah_hijau", ["sesuatu yang baru dari vonis"])
        _, lapis_2, _ = report_mod._klasifikasi_alasan_vonis(hasil)
        self.assertEqual(lapis_2, ["sesuatu yang baru dari vonis"])


class TestKalimatSkenarioMati(unittest.TestCase):
    """_kalimat_skenario_mati: hitung tangan + fallback + omit."""

    def _analisis(self, garis: float = 240.5, setan: dict | None = None) -> dict:
        analisis: dict = {
            "legs": [
                {
                    "leg_id": "ins",
                    "ticket": "insurance",
                    "line": garis,
                    "market_type": "total_under",
                }
            ]
        }
        if setan is not None:
            analisis["setan_pemain"] = setan
        return analisis

    def _setan_ok(self) -> dict:
        return {
            "status": "ok",
            "median_total": 220.0,
            "poin_3p_normal_gabungan": 80.0,
            "percobaan_3p_diharapkan_gabungan": 70.0,
        }

    def test_hitung_tangan_dari_blok_setan(self):
        # Poin non-3P normal = 220 - 80 = 140. Ambang =
        # (240,5 - 140) / (3 x 70) = 100,5/210 = 47,857% -> 47,9%.
        # Normal = 80/210 = 38,095% -> 38,1%.
        kalimat = report_mod._kalimat_skenario_mati(
            self._analisis(setan=self._setan_ok()),
            _hasil_vonis(
                "hijau",
                [],
                indikator={"garis_asuransi": {"line": 240.5}},
            ),
        )
        self.assertIsNotNone(kalimat)
        assert kalimat is not None
        self.assertIn("47,9%", kalimat)
        self.assertIn("38,1%", kalimat)
        self.assertIn("Under 240,5", kalimat)
        self.assertIn("70 percobaan", kalimat)

    def test_garis_dari_kaki_artefak_bila_vonis_tanpa_garis(self):
        kalimat = report_mod._kalimat_skenario_mati(
            self._analisis(setan=self._setan_ok()),
            _hasil_vonis("hijau", [], indikator={}),
        )
        self.assertIsNotNone(kalimat)
        assert kalimat is not None
        self.assertIn("47,9%", kalimat)

    def test_ambang_lebih_dari_satu_pakai_fallback(self):
        # Garis 360: ambang (360-140)/210 = 1,048 > 1 -> tidak
        # bermakna, pakai fallback P banjir/setan.
        kalimat = report_mod._kalimat_skenario_mati(
            self._analisis(garis=360.0, setan=self._setan_ok()),
            _hasil_vonis(
                "hijau",
                [],
                indikator={
                    "garis_asuransi": {"line": 360.0},
                    "p_banjir_terburuk": 0.611,
                    "p_setan": 0.497,
                },
            ),
        )
        self.assertIsNotNone(kalimat)
        assert kalimat is not None
        self.assertIn("61,1%", kalimat)
        self.assertIn("49,7%", kalimat)

    def test_tanpa_blok_setan_fallback_p_banjir(self):
        kalimat = report_mod._kalimat_skenario_mati(
            self._analisis(),
            _hasil_vonis(
                "hijau",
                [],
                indikator={
                    "garis_asuransi": {"line": 240.5},
                    "p_banjir_3p": 0.688,
                    "p_banjir_ft": 0.611,
                    "p_setan": 0.497,
                },
            ),
        )
        self.assertIsNotNone(kalimat)
        assert kalimat is not None
        # Fallback memakai yang terburuk dari 3P/FT: 61,1%.
        self.assertIn("61,1%", kalimat)
        self.assertIn("49,7%", kalimat)

    def test_blok_setan_gagal_pakai_fallback(self):
        setan = dict(self._setan_ok(), status="gagal")
        kalimat = report_mod._kalimat_skenario_mati(
            self._analisis(setan=setan),
            _hasil_vonis(
                "hijau",
                [],
                indikator={
                    "garis_asuransi": {"line": 240.5},
                    "p_banjir_terburuk": 0.611,
                },
            ),
        )
        self.assertIsNotNone(kalimat)
        assert kalimat is not None
        self.assertIn("61,1%", kalimat)

    def test_tidak_bisa_dihitung_tidak_ditampilkan(self):
        # Tanpa blok setan + tanpa P banjir/setan -> None (kalimat
        # tidak ditampilkan, bukan dikarang).
        kalimat = report_mod._kalimat_skenario_mati(
            self._analisis(),
            _hasil_vonis("hijau", [], indikator={"garis_asuransi": {"line": 240.5}}),
        )
        self.assertIsNone(kalimat)

    def test_tanpa_garis_tidak_ditampilkan(self):
        kalimat = report_mod._kalimat_skenario_mati(
            {"legs": []},
            _hasil_vonis("hijau", [], indikator={}),
        )
        self.assertIsNone(kalimat)


class TestBagianVonisTigaLapis(unittest.TestCase):
    """Render penuh dengan nilai_vonis di-mock (kunci tampilan)."""

    @classmethod
    def setUpClass(cls):
        if not ARTEFAK_LIVE.exists():
            raise unittest.SkipTest("artefak slate uji tidak ada di out/")
        cls.dal = _muat_artefak(ARTEFAK_LIVE)["DAL@UTA_2026-11-22"]

    def _render_dengan_vonis(self, hasil_vonis: dict, analisis: dict | None = None):
        basis = copy.deepcopy(analisis if analisis is not None else self.dal)
        with mock.patch.object(
            report_mod.vonis_mod, "nilai_vonis", return_value=hasil_vonis
        ):
            return report_mod.render_nba_report(basis)

    def _bagian_vonis(self, teks: str) -> str:
        mulai = teks.index("Vonis laga")
        return teks[mulai:]

    def test_urutan_lapis_1_2_3(self):
        hasil = _hasil_vonis(
            "kuning",
            [
                "VETO rim protector: Nic Claxton (CHI) OUT",
                "rapuh banjir: peluang Under di garis U250.5 — banjir 3P 68.2% < 72%",
                "volume garis tipis: $6 (bentuk v17)",
            ],
            indikator={
                "veto": {
                    "menyala": True,
                    "alasan": ["VETO rim protector: Nic Claxton (CHI) OUT"],
                },
                "garis_asuransi": {"line": 250.5, "harga_venue_cents": 78.5},
            },
        )
        teks = self._render_dengan_vonis(hasil)
        bagian = self._bagian_vonis(teks)
        self.assertIn("Vonis: KUNING", bagian)
        self.assertIn("Yang menentukan vonis:", bagian)
        self.assertIn("Catatan kualitas:", bagian)
        self.assertIn("Info tambahan (tidak mengubah vonis):", bagian)
        self.assertLess(
            bagian.index("Yang menentukan vonis:"),
            bagian.index("Catatan kualitas:"),
        )
        self.assertLess(
            bagian.index("Catatan kualitas:"),
            bagian.index("Info tambahan (tidak mengubah vonis):"),
        )

    def test_veto_menonjol_sebelum_demerit(self):
        # Preseden test_vonis.py: VETO tampil SEBELUM bullet demerit
        # di dalam bagian Vonis ("edge kecil" bentuk v17).
        hasil = _hasil_vonis(
            "kuning",
            [
                "VETO rim protector: Nic Claxton (CHI) OUT",
                "edge kecil: edge +1.0% di bawah minimum (bentuk v17)",
            ],
            indikator={
                "veto": {
                    "menyala": True,
                    "alasan": ["VETO rim protector: Nic Claxton (CHI) OUT"],
                },
            },
        )
        teks = self._render_dengan_vonis(hasil)
        bagian = self._bagian_vonis(teks)
        self.assertIn("VETO — LAGA INI DIBLOKIR DARI TIKET", bagian)
        self.assertLess(
            bagian.index("VETO — LAGA INI DIBLOKIR"),
            bagian.index("edge kecil"),
        )

    def test_headline_tunggu_lineup(self):
        hasil = _hasil_vonis(
            "tunggu_lineup",
            ["TUNGGU_LINEUP: Giannis masih Questionable — bintang"],
        )
        teks = self._render_dengan_vonis(hasil)
        bagian = self._bagian_vonis(teks)
        self.assertIn("Vonis: TUNGGU LINEUP", bagian)
        self.assertIn("Yang menentukan vonis:", bagian)

    def test_skenario_mati_hijau_dengan_blok_setan(self):
        analisis = copy.deepcopy(self.dal)
        analisis["setan_pemain"] = {
            "status": "ok",
            "median_total": 220.0,
            "poin_3p_normal_gabungan": 80.0,
            "percobaan_3p_diharapkan_gabungan": 70.0,
        }
        hasil = _hasil_vonis(
            "hijau",
            ["semua indikator sehat: 1 demerit (maks 1), rem alami: pertahanan Top-10"],
            indikator={"garis_asuransi": {"line": 240.5}},
        )
        teks = self._render_dengan_vonis(hasil, analisis=analisis)
        bagian = self._bagian_vonis(teks)
        self.assertIn("Vonis: HIJAU", bagian)
        self.assertIn("Skenario mati kaki ini", bagian)
        self.assertIn("47,9%", bagian)
        self.assertIn("38,1%", bagian)

    def test_skenario_mati_tidak_tampil_bila_bukan_hijau(self):
        analisis = copy.deepcopy(self.dal)
        analisis["setan_pemain"] = {
            "status": "ok",
            "median_total": 220.0,
            "poin_3p_normal_gabungan": 80.0,
            "percobaan_3p_diharapkan_gabungan": 70.0,
        }
        hasil = _hasil_vonis(
            "menengah_hijau",
            ["rapuh banjir: peluang Under di garis U250.5 — banjir 3P 68.2% < 72%"],
            indikator={"garis_asuransi": {"line": 240.5}},
        )
        teks = self._render_dengan_vonis(hasil, analisis=analisis)
        bagian = self._bagian_vonis(teks)
        self.assertNotIn("Skenario mati", bagian)

    def test_mahal_masuk_lapis_1(self):
        analisis = copy.deepcopy(self.dal)
        for leg in analisis.get("legs") or []:
            if leg.get("ticket") == "insurance":
                leg["line"] = 234.5
                leg["price_label"] = "MAHAL"
        hasil = _hasil_vonis(
            "menengah_hijau",
            ["rapuh banjir: peluang Under di garis U234.5 — banjir 3P 68.8% < 72%"],
            indikator={"garis_asuransi": {"line": 234.5}},
        )
        teks = self._render_dengan_vonis(hasil, analisis=analisis)
        bagian = self._bagian_vonis(teks)
        self.assertIn("Yang menentukan vonis:", bagian)
        self.assertIn("MAHAL", bagian)
        self.assertLess(
            bagian.index("MAHAL"),
            bagian.index("Catatan kualitas:"),
        )


class TestBagianVonisArtefakNyata(unittest.TestCase):
    """Render artefak nyata tanpa mock (vonis v18 worker A).

    Mengunci struktur lapis pada data nyata; vonisnya sendiri
    (HIJAU/KUNING/TUNGGU_LINEUP) adalah perilaku worker A — bila A
    mengubah ambang vonis, tes ini harus diukur ulang.
    """

    @classmethod
    def setUpClass(cls):
        if not ARTEFAK_LIVE.exists() or not ARTEFAK_VERIF.exists():
            raise unittest.SkipTest("artefak slate uji tidak ada di out/")
        cls.live = _muat_artefak(ARTEFAK_LIVE)
        cls.verif = _muat_artefak(ARTEFAK_VERIF)

    def test_den_verif_veto_di_lapis_1(self):
        teks = report_mod.render_nba_report(
            copy.deepcopy(self.verif["DEN@CHI_2026-11-22"])
        )
        bagian = teks[teks.index("Vonis laga") :]
        self.assertIn("Vonis: KUNING", bagian)
        self.assertIn("VETO — LAGA INI DIBLOKIR DARI TIKET", bagian)
        self.assertIn("Nic Claxton", bagian)
        self.assertIn("Yang menentukan vonis:", bagian)
        self.assertLess(
            bagian.index("VETO — LAGA INI DIBLOKIR"),
            bagian.index("Catatan kualitas:"),
        )

    def test_okc_verif_tunggu_lineup(self):
        teks = report_mod.render_nba_report(
            copy.deepcopy(self.verif["OKC@MIA_2026-11-22"])
        )
        bagian = teks[teks.index("Vonis laga") :]
        self.assertIn("Vonis: TUNGGU LINEUP", bagian)
        self.assertIn("Giannis Antetokounmpo", bagian)

    def test_dal_live_hijau_dengan_skenario_mati_fallback(self):
        # DAL live HIJAU di vonis v18 (diukur 2026-11-23); artefak
        # tanpa blok setan_pemain -> kalimat Skenario Mati fallback
        # dari P banjir/setan. REVISI KOORDINATOR: garis yang
        # dinilai kini equilibrium U246,5 (bukan kaki artefak
        # U234,5) — banjir FT 81,6%, setan 73,1%.
        teks = report_mod.render_nba_report(
            copy.deepcopy(self.live["DAL@UTA_2026-11-22"])
        )
        bagian = teks[teks.index("Vonis laga") :]
        self.assertIn("Vonis: HIJAU", bagian)
        self.assertIn("Skenario mati kaki Under 246,5", bagian)
        self.assertIn("81,6%", bagian)
        self.assertIn("73,1%", bagian)


if __name__ == "__main__":
    unittest.main()
