"""Tes engine/proposals.py (Tahap 3 Langkah 6).

Tiap aturan (a)-(d) diuji terpicu dan tidak terpicu pada fixture yang
tepat. TANPA network. Satu tes memakai cfg=None untuk membuktikan
section learning di playstyle.yaml terbaca.
"""

import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import proposals

REPO_ROOT = Path(__file__).resolve().parent.parent
PLAYSTYLE = REPO_ROOT / "config" / "playstyle.yaml"

CFG = {
    "learning": {
        "min_n_pasar": 20,
        "min_n_kalibrasi_pasar": 50,
        "ev_gap_warn": 0.05,
        "keyakinan_n": {"sedang_min": 20, "tinggi_min": 50},
    }
}


def _entri(
    n=20,
    brier_model=0.20,
    brier_market=0.20,
    brier_climatology=0.25,
    ev_prediksi_rata2=0.05,
    ev_terealisasi_rata2=0.05,
):
    """Satu entri ringkasan_per_pasar pekerja A. Default: tidak ada
    aturan yang terpicu (model = market, model < climatology, EV sama)."""
    return {
        "n": n,
        "brier_model": brier_model,
        "brier_market": brier_market,
        "brier_climatology": brier_climatology,
        "ev_prediksi_rata2": ev_prediksi_rata2,
        "ev_terealisasi_rata2": ev_terealisasi_rata2,
    }


def _kaki_settled(i=0):
    return {
        "leg_id": f"LEG-{i:03d}",
        "ticket_id": "TIKET-1",
        "sport": "nba",
        "market": "total_under",
        "selection": "Under 225.5",
        "p_model": 0.7,
        "p_market": 0.7,
        "p_final": 0.7,
        "price_buy_cents": 70,
        "price_close_cents": 72,
        "ev_pct": 0.0,
        "result": True,
        "settled": True,
        "sumber": "fixture",
    }


def _hash_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class TestAturanPasar(unittest.TestCase):
    def test_terpicu(self):
        # Brier model 0,30 > climatology 0,25, n=20 -> usulan "pasar",
        # keyakinan sedang (20 <= n < 50).
        ringkasan = {("nba", "total_under"): _entri(brier_model=0.30)}
        hasil = proposals.hasilkan_usulan(
            ringkasan, [_kaki_settled()], cfg=copy.deepcopy(CFG)
        )
        self.assertEqual(len(hasil), 1)
        usul = hasil[0]
        self.assertEqual(usul["id"], "USUL-001")
        self.assertEqual(usul["jenis"], "pasar")
        self.assertEqual(usul["n"], 20)
        self.assertEqual(usul["keyakinan"], "sedang")
        self.assertEqual(usul["status"], "menunggu_persetujuan")
        self.assertEqual(usul["bukti"]["brier_model"], 0.30)
        self.assertEqual(usul["bukti"]["brier_climatology"], 0.25)
        self.assertIn("nba / total_under", usul["judul"])

    def test_tidak_terpicu_n_kecil(self):
        # n=19 < min_n_pasar 20 -> tidak ada usulan (dan bukan usulan
        # "data": ada data settled).
        ringkasan = {("nba", "total_under"): _entri(n=19, brier_model=0.30)}
        hasil = proposals.hasilkan_usulan(
            ringkasan, [_kaki_settled()], cfg=copy.deepcopy(CFG)
        )
        self.assertEqual(hasil, [])

    def test_tidak_terpicu_brier_baik(self):
        # Model 0,20 < climatology 0,25 -> model lebih baik dari tebakan
        # frekuensi dasar, tidak ada usulan.
        ringkasan = {("nba", "total_under"): _entri(brier_model=0.20)}
        hasil = proposals.hasilkan_usulan(
            ringkasan, [_kaki_settled()], cfg=copy.deepcopy(CFG)
        )
        self.assertEqual(hasil, [])

    def test_keyakinan_tinggi_n_50(self):
        ringkasan = {("nba", "total_under"): _entri(n=50, brier_model=0.30)}
        hasil = proposals.hasilkan_usulan(
            ringkasan, [_kaki_settled()], cfg=copy.deepcopy(CFG)
        )
        self.assertEqual(len(hasil), 1)
        self.assertEqual(hasil[0]["keyakinan"], "tinggi")


class TestAturanKalibrasi(unittest.TestCase):
    def test_terpicu(self):
        # Model 0,15 < market 0,22, n=50; climatology 0,20 agar aturan
        # (a) tidak ikut terpicu (0,15 < 0,20).
        ringkasan = {
            ("nba", "total_under"): _entri(
                n=50, brier_model=0.15, brier_market=0.22, brier_climatology=0.20
            )
        }
        hasil = proposals.hasilkan_usulan(
            ringkasan, [_kaki_settled()], cfg=copy.deepcopy(CFG)
        )
        self.assertEqual(len(hasil), 1)
        usul = hasil[0]
        self.assertEqual(usul["jenis"], "kalibrasi")
        self.assertEqual(usul["keyakinan"], "tinggi")
        self.assertEqual(usul["status"], "menunggu_persetujuan")
        self.assertEqual(usul["bukti"]["brier_model"], 0.15)
        self.assertEqual(usul["bukti"]["brier_market"], 0.22)

    def test_tidak_terpicu_n_49(self):
        ringkasan = {
            ("nba", "total_under"): _entri(
                n=49, brier_model=0.15, brier_market=0.22, brier_climatology=0.20
            )
        }
        hasil = proposals.hasilkan_usulan(
            ringkasan, [_kaki_settled()], cfg=copy.deepcopy(CFG)
        )
        self.assertEqual(hasil, [])

    def test_tidak_terpicu_model_kalah_dari_market(self):
        ringkasan = {
            ("nba", "total_under"): _entri(
                n=50, brier_model=0.25, brier_market=0.22, brier_climatology=0.30
            )
        }
        hasil = proposals.hasilkan_usulan(
            ringkasan, [_kaki_settled()], cfg=copy.deepcopy(CFG)
        )
        self.assertEqual(hasil, [])


class TestAturanAmbang(unittest.TestCase):
    def test_terpicu(self):
        # EV terealisasi 0,02 vs prediksi 0,10: selisih 0,08 > 0,05.
        ringkasan = {
            ("nba", "total_under"): _entri(
                ev_prediksi_rata2=0.10, ev_terealisasi_rata2=0.02
            )
        }
        hasil = proposals.hasilkan_usulan(
            ringkasan, [_kaki_settled()], cfg=copy.deepcopy(CFG)
        )
        self.assertEqual(len(hasil), 1)
        usul = hasil[0]
        self.assertEqual(usul["jenis"], "ambang")
        self.assertEqual(usul["keyakinan"], "sedang")
        self.assertAlmostEqual(usul["bukti"]["selisih_ev"], 0.08)
        self.assertEqual(usul["bukti"]["ev_gap_warn"], 0.05)

    def test_tidak_terpicu_selisih_di_bawah_ambang(self):
        # Selisih 0,049 < 0,05 -> tidak terpicu.
        ringkasan = {
            ("nba", "total_under"): _entri(
                ev_prediksi_rata2=0.10, ev_terealisasi_rata2=0.051
            )
        }
        hasil = proposals.hasilkan_usulan(
            ringkasan, [_kaki_settled()], cfg=copy.deepcopy(CFG)
        )
        self.assertEqual(hasil, [])

    def test_tidak_terpicu_n_kecil(self):
        ringkasan = {
            ("nba", "total_under"): _entri(
                n=19, ev_prediksi_rata2=0.10, ev_terealisasi_rata2=0.02
            )
        }
        hasil = proposals.hasilkan_usulan(
            ringkasan, [_kaki_settled()], cfg=copy.deepcopy(CFG)
        )
        self.assertEqual(hasil, [])


class TestAturanData(unittest.TestCase):
    def test_tanpa_data_sama_sekali(self):
        hasil = proposals.hasilkan_usulan({}, [], cfg=copy.deepcopy(CFG))
        self.assertEqual(len(hasil), 1)
        usul = hasil[0]
        self.assertEqual(usul["id"], "USUL-001")
        self.assertEqual(usul["jenis"], "data")
        self.assertEqual(usul["n"], 0)
        self.assertEqual(usul["keyakinan"], "rendah")
        self.assertEqual(usul["status"], "menunggu_persetujuan")
        self.assertIn("PAPER", usul["isi"])

    def test_kaki_belum_settled_tetap_tanpa_data(self):
        kaki = _kaki_settled()
        kaki["settled"] = False
        kaki["result"] = None
        hasil = proposals.hasilkan_usulan({}, [kaki], cfg=copy.deepcopy(CFG))
        self.assertEqual(len(hasil), 1)
        self.assertEqual(hasil[0]["jenis"], "data")


class TestBentukDanKeamanan(unittest.TestCase):
    def test_id_unik_berurutan_dan_status(self):
        # Dua pasar, masing-masing memicu (a) + (c) -> 4 usulan, id
        # berurutan, urutan deterministik menurut label pasar.
        ringkasan = {
            ("nba", "total_under"): _entri(
                brier_model=0.30, ev_prediksi_rata2=0.10, ev_terealisasi_rata2=0.02
            ),
            ("epl", "btts_yes"): _entri(
                brier_model=0.30, ev_prediksi_rata2=0.10, ev_terealisasi_rata2=0.02
            ),
        }
        hasil = proposals.hasilkan_usulan(
            ringkasan, [_kaki_settled()], cfg=copy.deepcopy(CFG)
        )
        self.assertEqual(
            [u["id"] for u in hasil], ["USUL-001", "USUL-002", "USUL-003", "USUL-004"]
        )
        self.assertEqual(len({u["id"] for u in hasil}), 4)
        self.assertTrue(all(u["status"] == "menunggu_persetujuan" for u in hasil))
        # Urutan: epl dulu (label "epl / btts_yes" < "nba / ..."), lalu
        # aturan (a) sebelum (c) di tiap pasar.
        self.assertEqual(
            [(u["bukti"]["pasar"], u["jenis"]) for u in hasil],
            [
                ("epl / btts_yes", "pasar"),
                ("epl / btts_yes", "ambang"),
                ("nba / total_under", "pasar"),
                ("nba / total_under", "ambang"),
            ],
        )

    def test_pasar_dan_kalibrasi_bisa_bersamaan(self):
        # climatology 0,10 < model 0,15 < market 0,22, n=50: model kalah
        # dari frekuensi dasar TAPI menang lawan market -> (a) + (b).
        ringkasan = {
            ("nba", "total_under"): _entri(
                n=50, brier_model=0.15, brier_market=0.22, brier_climatology=0.10
            )
        }
        hasil = proposals.hasilkan_usulan(
            ringkasan, [_kaki_settled()], cfg=copy.deepcopy(CFG)
        )
        self.assertEqual([u["jenis"] for u in hasil], ["pasar", "kalibrasi"])

    def test_kunci_string_diterima(self):
        ringkasan = {"nba/total_under": _entri(brier_model=0.30)}
        hasil = proposals.hasilkan_usulan(
            ringkasan, [_kaki_settled()], cfg=copy.deepcopy(CFG)
        )
        self.assertEqual(len(hasil), 1)
        self.assertEqual(hasil[0]["bukti"]["pasar"], "nba/total_under")

    def test_nilai_none_dilewati(self):
        # brier_climatology None -> aturan (a) dilewati; EV None ->
        # aturan (c) dilewati. Tidak ada usulan, tidak ada crash.
        ringkasan = {
            ("nba", "total_under"): _entri(
                brier_model=0.30,
                brier_climatology=None,
                ev_prediksi_rata2=None,
                ev_terealisasi_rata2=None,
            )
        }
        hasil = proposals.hasilkan_usulan(
            ringkasan, [_kaki_settled()], cfg=copy.deepcopy(CFG)
        )
        self.assertEqual(hasil, [])

    def test_tidak_mengubah_input_atau_file(self):
        ringkasan = {
            ("nba", "total_under"): _entri(
                brier_model=0.30, ev_prediksi_rata2=0.10, ev_terealisasi_rata2=0.02
            )
        }
        outcomes = [_kaki_settled()]
        cfg = copy.deepcopy(CFG)
        ringkasan_sebelum = copy.deepcopy(ringkasan)
        outcomes_sebelum = copy.deepcopy(outcomes)
        cfg_sebelum = copy.deepcopy(cfg)
        hash_sebelum = _hash_file(PLAYSTYLE)
        proposals.hasilkan_usulan(ringkasan, outcomes, cfg=cfg)
        proposals.hasilkan_usulan(ringkasan, outcomes, cfg=None)
        self.assertEqual(ringkasan, ringkasan_sebelum)
        self.assertEqual(outcomes, outcomes_sebelum)
        self.assertEqual(cfg, cfg_sebelum)
        self.assertEqual(_hash_file(PLAYSTYLE), hash_sebelum)

    def test_cfg_none_memakai_playstyle_asli(self):
        # Section learning di playstyle.yaml terbaca (min_n_pasar 20).
        ringkasan = {("nba", "total_under"): _entri(brier_model=0.30)}
        hasil = proposals.hasilkan_usulan(ringkasan, [_kaki_settled()], cfg=None)
        self.assertEqual(len(hasil), 1)
        self.assertEqual(hasil[0]["jenis"], "pasar")


if __name__ == "__main__":
    unittest.main()
