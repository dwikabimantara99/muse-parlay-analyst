"""Tes sistem vonis per laga (engine/vonis.py) + wiring komposer/laporan.

Vonis: HIJAU (kandidat Asuransi) / MENENGAH_HIJAU (kandidat Utama)
/ KUNING (skip kedua tiket) — sistem demerit + pemicu keras, aturan
persis di docstring engine/vonis.py + LAPORAN-VONIS.md.

CATATAN HIJAU: setelah veto rim protector, TIDAK ADA laga slate uji
22 Nov 2026 yang HIJAU — satu-satunya kandidat (OKC@MIA verif,
0 demerit) kena veto karena Chet Holmgren (3,0 blok/laga) OUT +
MIA pace 102,19. Tes HIJAU memakai fixture sintetis sehat
(_analisis_sehat, median 220 sigma 5 — dibekukan setelah diukur:
edge +8,2%, P banjir 94,5%, P setan 68,4%, gap +7,0, volume $500,
OT 1,9%, veto tidak menyala).

Tes artefak nyata memakai out/analysis_live_2026-11-22.json +
out/analysis_verif_tahap4_2026-11-22.json (file runtime, gitignored)
dan di-skip bila file tidak ada — pola yang sama seperti
tests/test_equilibrium.py.
"""

from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path

import config as config_mod
from engine import stress as stress_mod
from engine import ticket_composer as ticket_composer_mod
from engine import vonis as vonis_mod
from report import nba_report as nba_report_mod

CFG = config_mod.load_playstyle()
ROOT = Path(__file__).resolve().parent.parent
ARTEFAK_LIVE = ROOT / "out" / "analysis_live_2026-11-22.json"
ARTEFAK_VERIF = ROOT / "out" / "analysis_verif_tahap4_2026-11-22.json"
PEMETAAN = ROOT / "config" / "rim_protector_2026-27.json"


def _cdf_normal(median, sigma, garis_min, garis_max, langkah=2.0):
    """CDF total normal (median, sigma) sebagai sim markets."""
    markets = {}
    n = int(round((garis_max - garis_min) / langkah)) + 1
    for i in range(n):
        garis = garis_min + i * langkah
        z = (garis - median) / sigma
        p = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        markets[f"total_under_{garis:g}"] = round(p, 6)
    return markets


def _tangga(baris):
    """Tangga totals dari daftar (garis, harga, volume, thin).

    Harga jup.ag = harga Polymarket + 0,5¢ (markup tipikal).
    """
    return [
        {
            "line": garis,
            "side": "under",
            "price_cents": harga,
            "jup_estimated_cents": harga + 0.5,
            "volume_usd": volume,
            "thin": thin,
        }
        for garis, harga, volume, thin in baris
    ]


def _kaki(match_id, ticket, line, p_model, p_market, harga, **ubah):
    """Satu kaki artefak nba_analysis (bentuk _rakit_kaki)."""
    p_final = None
    if p_model is not None:
        p_final = (
            round(0.3 * p_model + 0.7 * p_market, 3)
            if p_market is not None
            else p_model
        )
    kaki = {
        "leg_id": f"{match_id}:total_under_{line:g}:{ticket}",
        "market_type": "total_under",
        "line": line,
        "p_model": p_model,
        "p_market": p_market,
        "comparison_source": "kalshi" if p_market is not None else None,
        "p_final": p_final,
        "price_cents": harga,
        "jup_estimated_cents": harga,
        "ev_pct": None,
        "price_label": None,
        "volume_usd": None,
        "thin": None,
        "ticket": ticket,
    }
    kaki.update(ubah)
    return kaki


def _analisis(
    match_id,
    median,
    sigma,
    kaki_ins,
    kaki_main,
    tangga,
    ot=0.019,
    market_line=None,
    pace_home=99.0,
    pace_away=99.0,
    injuries=None,
):
    """Artefak nba_analysis minimal dengan CDF normal penuh + tangga."""
    distribusi = {"total": {"median": median}}
    if ot is not None:
        distribusi["ot_probability"] = ot
    return {
        "format": "nba_analysis",
        "format_version": 1,
        "match_id": match_id,
        "status": "OK",
        "legs": [kaki_ins, kaki_main],
        "simulation": {
            "score_distribution": distribusi,
            "markets": _cdf_normal(median, sigma, median - 30, median + 45),
        },
        "market": {
            "main_total_line": (
                market_line if market_line is not None else median + 1.5
            ),
            "totals": tangga,
        },
        "inputs": {
            "home": {"stats_season": {"pace": pace_home}},
            "away": {"stats_season": {"pace": pace_away}},
        },
        "injuries": {"entries": injuries if injuries is not None else []},
    }


def _analisis_sehat(match_id="IND@NYK_2026-11-22"):
    """Fixture laga sehat (HIJAU, 0 demerit — nilai diukur, dibekukan).

    Median 220 sigma 5, garis bandar 221,5, pace kedua tim di bawah
    ambang veto, tidak ada cedera (veto dievaluasi, tidak menyala).
    Garis Asuransi = equilibrium Asuransi U240,5 @90,5¢ (garis di
    atasnya gagal gate edge Asuransi karena harganya 94–97¢).
    """
    tangga = _tangga(
        [
            (226.5, 76.0, 500.0, False),
            (228.5, 78.0, 500.0, False),
            (230.5, 80.0, 500.0, False),
            (232.5, 82.0, 500.0, False),
            (234.5, 84.0, 500.0, False),
            (236.5, 86.0, 500.0, False),
            (238.5, 88.0, 500.0, False),
            (240.5, 90.0, 500.0, False),
            (242.5, 94.0, 500.0, False),
            (244.5, 97.0, 500.0, False),
        ]
    )
    return _analisis(
        match_id,
        220.0,
        5.0,
        _kaki(match_id, "insurance", 240.5, 0.999, 0.93, 90.0),
        _kaki(match_id, "main", 236.5, 0.995, 0.90, 86.0),
        tangga,
        ot=0.019,
        market_line=221.5,
        pace_home=94.54,
        pace_away=101.22,
    )


def _analisis_ekor_gemuk(match_id="DEN@CHI_2026-11-22"):
    """Fixture ekor gemuk: garis Asuransi jauh + murah (mirip DEN nyata).

    Median 233 sigma 19,2, garis bandar 234,5. Semua garis tahan
    banjir dibuat tipis (equilibrium + garis tahan tidak-tipis tidak
    ada) sehingga garis Asuransi jatuh ke kaki artefak Asuransi
    U252,5 @82¢: jarak 18 poin, harga 82¢ -> sinyal ekor gemuk.
    """
    baris = []
    garis = 238.5
    while garis <= 274.5 + 1e-9:
        harga = round(55.0 + (garis - 238.5) * 1.5, 1)
        # Garis tahan banjir (>= 258,5) tipis; di bawah itu tidak tahan.
        baris.append((garis, harga, 5.0 if garis >= 258.5 else 500.0, garis >= 258.5))
        garis = round(garis + 2.0, 9)
    return _analisis(
        match_id,
        233.0,
        19.2,
        _kaki(match_id, "insurance", 252.5, 0.845, 0.83, 82.0),
        _kaki(match_id, "main", 250.5, 0.819, 0.80, 79.0),
        _tangga(baris),
        ot=0.02,
        market_line=234.5,
        pace_home=103.22,
        pace_away=98.3,
    )


def _muat_artefak(path):
    """Muat artefak slate -> {match_id: nba_analysis} (deepcopy per tes)."""
    dokumen = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        m["nba_analysis"]["match_id"]: copy.deepcopy(m["nba_analysis"])
        for m in dokumen["matches"]
    }


def _cfg_tanpa_kunci(*kunci):
    """CFG copy dengan satu kunci vonis dihapus (tes ConfigError)."""
    cfg = copy.deepcopy(CFG)
    target = cfg
    for kunci_parsial in kunci[:-1]:
        target = target[kunci_parsial]
    del target[kunci[-1]]
    return cfg


class TestVonisArtefakNyata(unittest.TestCase):
    """Vonis pada 10 baris slate uji 22 Nov 2026 (data nyata)."""

    @classmethod
    def setUpClass(cls):
        if not ARTEFAK_LIVE.exists() or not ARTEFAK_VERIF.exists():
            raise unittest.SkipTest("artefak slate uji tidak ada di out/")
        cls.live = _muat_artefak(ARTEFAK_LIVE)
        cls.verif = _muat_artefak(ARTEFAK_VERIF)

    def test_den_verif_kuning_veto_menyala(self):
        # Kasus uji WAJIB: DEN@CHI verif -> KUNING; alasan menyebut
        # pemicunya (veto Claxton + ketujuh demerit).
        hasil = vonis_mod.nilai_vonis(self.verif["DEN@CHI_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "kuning")
        self.assertEqual(hasil["indikator"]["pemicu_keras"], "veto_rim_protector")
        self.assertEqual(
            set(hasil["indikator"]["demerit"]),
            {
                "edge_kecil",
                "banjir_lemah",
                "setan_lemah",
                "volume_tipis",
                "gap_kecil",
                "ekor_gemuk",
                "total_tinggi",
            },
        )
        alasan = " ".join(hasil["alasan"])
        self.assertIn("VETO rim protector", alasan)
        self.assertIn("Nic Claxton", alasan)
        self.assertIn("1.0 blok/laga", alasan)
        veto = hasil["indikator"]["veto"]
        self.assertTrue(veto["dievaluasi"])
        self.assertTrue(veto["menyala"])
        self.assertEqual([o["player"] for o in veto["pelindung_out"]], ["Nic Claxton"])
        self.assertTrue(veto["kondisi_garis"])
        self.assertTrue(veto["kondisi_pace"])

    def test_okc_verif_kuning_hanya_karena_veto(self):
        # OKC@MIA verif: 0 demerit (sistem demerit bilang sehat) tapi
        # KUNING karena veto — Chet Holmgren (3,0 blok/laga) OUT +
        # MIA pace 102,19. Inilah nilai tambah veto.
        hasil = vonis_mod.nilai_vonis(self.verif["OKC@MIA_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "kuning")
        self.assertEqual(hasil["indikator"]["pemicu_keras"], "veto_rim_protector")
        self.assertEqual(hasil["indikator"]["demerit"], [])
        self.assertEqual(hasil["indikator"]["n_demerit"], 0)
        veto = hasil["indikator"]["veto"]
        self.assertEqual(
            [o["player"] for o in veto["pelindung_out"]], ["Chet Holmgren"]
        )
        self.assertFalse(veto["kondisi_garis"])  # garis 231,5 < 235
        self.assertTrue(veto["kondisi_pace"])  # MIA 102,19 >= 102

    def test_den_live_kuning_veto_tidak_menyala_snapshot_lama(self):
        # DEN@CHI live (snapshot lebih awal): Claxton BELUM tercatat
        # OUT — veto tidak menyala (kejujuran: veto bergantung pada
        # ketepatan waktu kabar cedera; recheck sebelum pasang adalah
        # mitigasinya). Laga tetap KUNING via 7 demerit.
        hasil = vonis_mod.nilai_vonis(self.live["DEN@CHI_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "kuning")
        self.assertIsNone(hasil["indikator"]["pemicu_keras"])
        self.assertEqual(hasil["indikator"]["n_demerit"], 7)
        veto = hasil["indikator"]["veto"]
        self.assertTrue(veto["dievaluasi"])
        self.assertFalse(veto["menyala"])
        self.assertEqual(veto["pelindung_out"], [])

    def test_det_live_kuning_ot_tinggi(self):
        hasil = vonis_mod.nilai_vonis(self.live["DET@ATL_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "kuning")
        self.assertEqual(hasil["indikator"]["pemicu_keras"], "ot_tinggi")
        self.assertGreaterEqual(hasil["indikator"]["ot_probability"], 0.028)

    def test_orl_live_kuning_edge_tidak_positif(self):
        hasil = vonis_mod.nilai_vonis(self.live["ORL@WAS_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "kuning")
        self.assertEqual(hasil["indikator"]["pemicu_keras"], "edge_tidak_positif")
        self.assertLessEqual(hasil["indikator"]["edge_terbaik"], 0.0)

    def test_dal_live_menengah_hijau_veto_tidak_menyala(self):
        # DAL@UTA: Jaren Jackson Jr. (UTA, 1,3 blok/laga) OUT tapi
        # garis 225,5 + pace 99,89 rendah -> veto TIDAK menyala
        # (kondisi lingkungan gagal). 4 demerit -> MENENGAH_HIJAU.
        hasil = vonis_mod.nilai_vonis(self.live["DAL@UTA_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "menengah_hijau")
        self.assertEqual(hasil["indikator"]["n_demerit"], 4)
        veto = hasil["indikator"]["veto"]
        self.assertTrue(veto["dievaluasi"])
        self.assertFalse(veto["menyala"])
        self.assertEqual(
            [o["player"] for o in veto["pelindung_out"]],
            ["Jaren Jackson Jr."],
        )
        self.assertFalse(veto["kondisi_garis"])
        self.assertFalse(veto["kondisi_pace"])

    def test_bos_live_menengah_hijau(self):
        hasil = vonis_mod.nilai_vonis(self.live["BOS@GSW_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "menengah_hijau")
        self.assertEqual(hasil["indikator"]["n_demerit"], 4)

    def test_distribusi_slate_nol_dua_delapan(self):
        hitung = {"hijau": 0, "menengah_hijau": 0, "kuning": 0}
        for kumpulan in (self.live, self.verif):
            for analisis in kumpulan.values():
                hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
                hitung[hasil["vonis"]] += 1
        self.assertEqual(hitung, {"hijau": 0, "menengah_hijau": 2, "kuning": 8})


class TestVonisSintetis(unittest.TestCase):
    """Vonis pada fixture sintetis (perilaku per indikator)."""

    def test_laga_sehat_hijau(self):
        # Kasus uji WAJIB (sintetis — tidak ada laga slate yang HIJAU
        # setelah veto; lihat docstring modul tes).
        hasil = vonis_mod.nilai_vonis(_analisis_sehat(), None, CFG)
        self.assertEqual(hasil["vonis"], "hijau")
        ind = hasil["indikator"]
        self.assertEqual(ind["demerit"], [])
        self.assertIsNone(ind["pemicu_keras"])
        self.assertGreaterEqual(ind["edge_terbaik"], 0.025)
        self.assertGreaterEqual(ind["p_banjir_terburuk"], 0.74)
        self.assertGreaterEqual(ind["p_setan"], 0.65)
        self.assertGreaterEqual(ind["gap_model_pasar"], 0.04)
        self.assertLessEqual(ind["gap_model_pasar"], 0.08)
        self.assertIs(ind["ekor_gemuk"], False)
        self.assertTrue(ind["veto"]["dievaluasi"])
        self.assertFalse(ind["veto"]["menyala"])
        self.assertIn("semua indikator sehat", hasil["alasan"][0])

    def test_ekor_gemuk(self):
        hasil = vonis_mod.nilai_vonis(_analisis_ekor_gemuk(), None, CFG)
        ind = hasil["indikator"]
        self.assertIs(ind["ekor_gemuk"], True)
        self.assertIn("ekor_gemuk", ind["demerit"])
        self.assertGreaterEqual(ind["jarak_garis_market_points"], 10.0)
        self.assertLessEqual(ind["garis_asuransi"]["harga_venue_cents"], 85)
        self.assertIn("ekor gemuk", " ".join(hasil["alasan"]))

    def test_volume_tipis_demerit(self):
        # Semua garis tangga tipis -> garis Asuransi (kaki artefak)
        # tipis -> satu-satunya demerit volume_tipis.
        analisis = _analisis_sehat()
        for entri in analisis["market"]["totals"]:
            entri["thin"] = True
            entri["volume_usd"] = 5.0
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertEqual(hasil["vonis"], "menengah_hijau")
        self.assertEqual(hasil["indikator"]["demerit"], ["volume_tipis"])

    def test_gap_kecil_demerit(self):
        # Jangkar pasar hampir sama dengan model -> gap kecil.
        analisis = _analisis_sehat()
        for kaki in analisis["legs"]:
            kaki["p_market"] = 0.99
            kaki["p_final"] = round(0.3 * kaki["p_model"] + 0.7 * 0.99, 3)
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertIn("gap_kecil", hasil["indikator"]["demerit"])
        self.assertLess(hasil["indikator"]["gap_model_pasar"], 0.04)

    def test_total_tinggi_demerit(self):
        analisis = _analisis_sehat()
        analisis["market"]["main_total_line"] = 236.5
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertEqual(hasil["indikator"]["demerit"], ["total_tinggi"])
        self.assertEqual(hasil["vonis"], "menengah_hijau")

    def test_hasil_stress_konsisten(self):
        analisis = _analisis_sehat()
        hasil_stress = stress_mod.skenario_panas(analisis, cfg=CFG)
        tanpa = vonis_mod.nilai_vonis(analisis, None, CFG)
        dengan = vonis_mod.nilai_vonis(analisis, hasil_stress, CFG)
        self.assertTrue(dengan["indikator"]["hasil_stress_dipakai"])
        self.assertAlmostEqual(
            dengan["indikator"]["p_banjir_terburuk"],
            tanpa["indikator"]["p_banjir_terburuk"],
            places=6,
        )
        self.assertAlmostEqual(
            dengan["indikator"]["p_setan"],
            tanpa["indikator"]["p_setan"],
            places=6,
        )
        self.assertEqual(dengan["vonis"], tanpa["vonis"])

    def test_hasil_stress_rusak_tidak_crash(self):
        hasil = vonis_mod.nilai_vonis(
            _analisis_sehat(), {"kaki": [{"line": "bukan-angka"}]}, CFG
        )
        self.assertEqual(hasil["vonis"], "hijau")
        self.assertFalse(hasil["indikator"]["hasil_stress_dipakai"])

    def test_entri_match_dibuka(self):
        analisis = _analisis_sehat()
        langsung = vonis_mod.nilai_vonis(analisis, None, CFG)
        dibungkus = vonis_mod.nilai_vonis({"nba_analysis": analisis}, None, CFG)
        self.assertEqual(dibungkus["vonis"], langsung["vonis"])
        self.assertEqual(
            dibungkus["indikator"]["demerit"], langsung["indikator"]["demerit"]
        )

    def test_bukan_dict_value_error(self):
        with self.assertRaises(ValueError):
            vonis_mod.nilai_vonis("bukan dict", None, CFG)


class TestFailClosed(unittest.TestCase):
    """Data hilang -> KUNING fail-closed (bukan crash, bukan HIJAU)."""

    def test_tanpa_cdf_kuning(self):
        analisis = _analisis_sehat()
        analisis["simulation"]["markets"] = {}
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertEqual(hasil["vonis"], "kuning")
        self.assertEqual(hasil["indikator"]["pemicu_keras"], "data_tidak_cukup")
        self.assertFalse(hasil["indikator"]["dievaluasi"])

    def test_tanpa_tangga_kuning(self):
        analisis = _analisis_sehat()
        analisis["market"]["totals"] = []
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertEqual(hasil["vonis"], "kuning")
        self.assertEqual(hasil["indikator"]["pemicu_keras"], "data_tidak_cukup")

    def test_tanpa_jangkar_pasar_kuning(self):
        analisis = _analisis_sehat()
        for kaki in analisis["legs"]:
            kaki["p_market"] = None
            kaki["p_final"] = None
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertEqual(hasil["vonis"], "kuning")
        self.assertEqual(hasil["indikator"]["pemicu_keras"], "data_tidak_cukup")

    def test_tanpa_ot_kuning(self):
        analisis = _analisis_sehat()
        del analisis["simulation"]["score_distribution"]["ot_probability"]
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertEqual(hasil["vonis"], "kuning")
        self.assertEqual(hasil["indikator"]["pemicu_keras"], "data_tidak_cukup")
        self.assertIn("ot_probability", hasil["alasan"][0])

    def test_soccer_kuning_bukan_nba(self):
        analisis = _analisis_sehat()
        analisis["format"] = "soccer_analysis"
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertEqual(hasil["vonis"], "kuning")
        self.assertEqual(hasil["indikator"]["pemicu_keras"], "bukan_nba")
        self.assertFalse(hasil["indikator"]["dievaluasi"])

    def test_tanpa_garis_bandar_indikator_sekunder_tidak_dinilai(self):
        # main_total_line hilang -> ekor + total tidak dinilai (TANPA
        # demerit); laga sehat tetap HIJAU.
        analisis = _analisis_sehat()
        analisis["market"]["main_total_line"] = None
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertEqual(hasil["vonis"], "hijau")
        self.assertIn("ekor_gemuk", hasil["indikator"]["tidak_dinilai"])
        self.assertIn("total_tinggi", hasil["indikator"]["tidak_dinilai"])
        self.assertIsNone(hasil["indikator"]["ekor_gemuk"])

    def test_config_rusak_config_error(self):
        with self.assertRaises(config_mod.ConfigError):
            vonis_mod.nilai_vonis(
                _analisis_sehat(), None, _cfg_tanpa_kunci("vonis", "edge_hijau_pct")
            )
        with self.assertRaises(config_mod.ConfigError):
            vonis_mod.nilai_vonis(
                _analisis_sehat(),
                None,
                _cfg_tanpa_kunci("vonis", "veto_pace_tinggi"),
            )


class TestVeto(unittest.TestCase):
    """Veto rim protector (hard trigger -> KUNING)."""

    @classmethod
    def setUpClass(cls):
        if not ARTEFAK_VERIF.exists():
            raise unittest.SkipTest("artefak verif tidak ada di out/")
        cls.verif = _muat_artefak(ARTEFAK_VERIF)

    def test_veto_menyala_den_verif(self):
        veto = vonis_mod.evaluasi_veto(self.verif["DEN@CHI_2026-11-22"], CFG)
        self.assertTrue(veto["dievaluasi"])
        self.assertTrue(veto["menyala"])
        self.assertEqual([o["player"] for o in veto["pelindung_out"]], ["Nic Claxton"])
        self.assertEqual(veto["pelindung_out"][0]["blk_per_game"], 1.0)
        self.assertEqual(veto["pemetaan_musim"], "2026-27")
        self.assertIn("Nic Claxton", veto["alasan"][0])

    def test_veto_tidak_menyala_bila_pelindung_main(self):
        # Claxton dihapus dari daftar cedera (seolah main) -> veto mati.
        # Laga tetap KUNING via 7 demerit — yang diuji di sini hanya veto.
        analisis = copy.deepcopy(self.verif["DEN@CHI_2026-11-22"])
        analisis["injuries"]["entries"] = [
            e
            for e in analisis["injuries"]["entries"]
            if e.get("player") != "Nic Claxton"
        ]
        veto = vonis_mod.evaluasi_veto(analisis, CFG)
        self.assertTrue(veto["dievaluasi"])
        self.assertFalse(veto["menyala"])
        self.assertEqual(veto["pelindung_out"], [])
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertEqual(hasil["vonis"], "kuning")
        self.assertNotEqual(hasil["indikator"]["pemicu_keras"], "veto_rim_protector")

    def test_veto_tidak_menyala_bila_garis_pace_rendah(self):
        # Claxton tetap OUT, tapi garis pasar + pace direndahkan ->
        # kondisi lingkungan gagal -> veto mati.
        analisis = copy.deepcopy(self.verif["DEN@CHI_2026-11-22"])
        analisis["market"]["main_total_line"] = 220.0
        for sisi in ("home", "away"):
            analisis["inputs"][sisi]["stats_season"]["pace"] = 99.0
        veto = vonis_mod.evaluasi_veto(analisis, CFG)
        self.assertTrue(veto["dievaluasi"])
        self.assertFalse(veto["menyala"])
        self.assertEqual([o["player"] for o in veto["pelindung_out"]], ["Nic Claxton"])
        self.assertFalse(veto["kondisi_garis"])
        self.assertFalse(veto["kondisi_pace"])

    def test_veto_tidak_menyala_out_satu_sumber(self):
        # Claxton OUT tapi hanya 1 sumber -> tidak terkonfirmasi.
        analisis = copy.deepcopy(self.verif["DEN@CHI_2026-11-22"])
        for entri in analisis["injuries"]["entries"]:
            if entri.get("player") == "Nic Claxton":
                entri["availability_n_sources"] = 1
                entri["sources"] = ["Official NBA Injury Report"]
        veto = vonis_mod.evaluasi_veto(analisis, CFG)
        self.assertTrue(veto["dievaluasi"])
        self.assertFalse(veto["menyala"])
        self.assertEqual(veto["pelindung_out"], [])
        diperiksa = {p["player"]: p["status"] for p in veto["pelindung_diperiksa"]}
        self.assertEqual(diperiksa["Nic Claxton"], "OUT_belum_terkonfirmasi")

    def test_veto_tidak_dievaluasi_tanpa_pemetaan(self):
        # Pemetaan kosong (tidak ada tim terpetakan) -> veto tidak
        # dievaluasi, TAPI nilai_vonis tetap jalan (demerit).
        veto = vonis_mod.evaluasi_veto(
            self.verif["DEN@CHI_2026-11-22"], CFG, pemetaan={}
        )
        self.assertFalse(veto["dievaluasi"])
        self.assertFalse(veto["menyala"])
        self.assertIsNotNone(veto["alasan_tidak_dievaluasi"])

    def test_veto_pemetaan_suntik_dan_nama_aksen(self):
        # Logika veto diuji terpisah dari file CHECK-IN: pemetaan
        # suntik + nama beraksen ("Jokić" di pemetaan vs "Jokic" di
        # data cedera) harus cocok.
        analisis = _analisis_sehat(match_id="DEN@CHI_2026-11-22")
        analisis["market"]["main_total_line"] = 236.5
        analisis["injuries"]["entries"] = [
            {
                "player": "Nikola Jokic",
                "status": "OUT",
                "team_tricode": "DEN",
                "sources": ["Official NBA Injury Report", "ESPN"],
                "availability_n_sources": 2,
            }
        ]
        pemetaan = {
            "DEN": [
                {
                    "player": "Nikola Jokić",
                    "blk_per_game": 1.0,
                    "mp_per_game": 37.1,
                    "games_played": 15,
                }
            ],
            "CHI": [
                {
                    "player": "Jalen Smith",
                    "blk_per_game": 1.1,
                    "mp_per_game": 25.3,
                    "games_played": 14,
                }
            ],
        }
        veto = vonis_mod.evaluasi_veto(analisis, CFG, pemetaan=pemetaan)
        self.assertTrue(veto["dievaluasi"])
        self.assertTrue(veto["menyala"])
        self.assertEqual([o["player"] for o in veto["pelindung_out"]], ["Nikola Jokić"])

    def test_mara_bukan_pemicu_okc(self):
        # Regresi klaim TIDAK TERVERIFIKASI "Aday Mara OUT": Mara
        # adalah pemimpin blok OKC yang MAIN — veto OKC menyala karena
        # Chet Holmgren, bukan Mara.
        veto = vonis_mod.evaluasi_veto(self.verif["OKC@MIA_2026-11-22"], CFG)
        self.assertTrue(veto["menyala"])
        self.assertNotIn("Aday Mara", [o["player"] for o in veto["pelindung_out"]])
        diperiksa = {p["player"]: p["status"] for p in veto["pelindung_diperiksa"]}
        self.assertEqual(diperiksa["Aday Mara"], "main")
        self.assertEqual(diperiksa["Chet Holmgren"], "OUT_terkonfirmasi")

    def test_veto_tidak_dievaluasi_tanpa_data_cedera(self):
        analisis = _analisis_sehat()
        del analisis["injuries"]
        veto = vonis_mod.evaluasi_veto(analisis, CFG)
        self.assertFalse(veto["dievaluasi"])
        self.assertFalse(veto["menyala"])
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertEqual(hasil["vonis"], "hijau")
        self.assertIn("veto_rim_protector", hasil["indikator"]["tidak_dinilai"])


class TestKomposerVonis(unittest.TestCase):
    """Wiring komposer: KUNING dievaluasi dikeluarkan; vonis dibawa kandidat."""

    @classmethod
    def setUpClass(cls):
        if not ARTEFAK_LIVE.exists() or not ARTEFAK_VERIF.exists():
            raise unittest.SkipTest("artefak slate uji tidak ada di out/")
        cls.live = _muat_artefak(ARTEFAK_LIVE)
        cls.verif = _muat_artefak(ARTEFAK_VERIF)

    @staticmethod
    def _ok(analisis):
        analisis = copy.deepcopy(analisis)
        analisis["status"] = "OK"
        return analisis

    def test_bos_verif_kuning_dikeluarkan_kedua_tiket(self):
        # BOS verif: KUNING 6 demerit, TIDAK kena skip_awal — vonis
        # yang mengeluarkannya (nilai tambah vonis di komposer).
        analisis = self._ok(self.verif["BOS@GSW_2026-11-22"])
        kandidat, coret = ticket_composer_mod._kumpulkan_kandidat(
            {analisis["match_id"]: analisis}, {}, CFG
        )
        self.assertEqual(kandidat["insurance"], [])
        self.assertEqual(kandidat["main"], [])
        for tiket in ("insurance", "main"):
            self.assertTrue(
                any("vonis KUNING" in c for c in coret[tiket]),
                coret[tiket],
            )

    def test_okc_verif_dikeluarkan_karena_veto(self):
        analisis = self._ok(self.verif["OKC@MIA_2026-11-22"])
        kandidat, coret = ticket_composer_mod._kumpulkan_kandidat(
            {analisis["match_id"]: analisis}, {}, CFG
        )
        self.assertEqual(kandidat["insurance"], [])
        self.assertEqual(kandidat["main"], [])
        self.assertTrue(
            any("VETO rim protector: Chet Holmgren" in c for c in coret["main"]),
            coret["main"],
        )

    def test_den_verif_dikeluarkan_veto_bila_skip_dimatikan(self):
        # DEN verif biasanya sudah kena skip_awal (pola Denver) sebelum
        # vonis; dengan skip dimatikan, veto yang mengeluarkannya.
        cfg = copy.deepcopy(CFG)
        cfg["skip_awal"]["enabled"] = False
        analisis = self._ok(self.verif["DEN@CHI_2026-11-22"])
        kandidat, coret = ticket_composer_mod._kumpulkan_kandidat(
            {analisis["match_id"]: analisis}, {}, cfg
        )
        self.assertEqual(kandidat["insurance"], [])
        self.assertEqual(kandidat["main"], [])
        self.assertTrue(
            any("VETO rim protector: Nic Claxton" in c for c in coret["main"]),
            coret["main"],
        )

    def test_kandidat_membawa_vonis_menengah_hijau(self):
        analyses = {
            "DAL@UTA_2026-11-22": self._ok(self.live["DAL@UTA_2026-11-22"]),
            "BOS@GSW_2026-11-22": self._ok(self.live["BOS@GSW_2026-11-22"]),
        }
        kandidat, _coret = ticket_composer_mod._kumpulkan_kandidat(analyses, {}, CFG)
        self.assertGreaterEqual(len(kandidat["main"]), 2)
        for kand in kandidat["main"]:
            self.assertEqual(kand["vonis"], "menengah_hijau")
            self.assertIsInstance(kand["vonis_alasan"], list)
            self.assertGreater(len(kand["vonis_alasan"]), 0)

    def test_vonis_dimatikan_tidak_ada_coret_vonis(self):
        cfg = copy.deepcopy(CFG)
        cfg["vonis"]["enabled"] = False
        analisis = self._ok(self.verif["BOS@GSW_2026-11-22"])
        kandidat, coret = ticket_composer_mod._kumpulkan_kandidat(
            {analisis["match_id"]: analisis}, {}, cfg
        )
        for tiket in ("insurance", "main"):
            self.assertFalse(
                any("vonis KUNING" in c for c in coret[tiket]),
                coret[tiket],
            )
            for kand in kandidat[tiket]:
                self.assertIsNone(kand["vonis"])


class TestLaporanVonis(unittest.TestCase):
    """Bagian _bagian_vonis di laporan (kata-kata sederhana + veto menonjol)."""

    @classmethod
    def setUpClass(cls):
        if not ARTEFAK_LIVE.exists() or not ARTEFAK_VERIF.exists():
            raise unittest.SkipTest("artefak slate uji tidak ada di out/")
        cls.live = _muat_artefak(ARTEFAK_LIVE)
        cls.verif = _muat_artefak(ARTEFAK_VERIF)

    def test_den_verif_veto_menonjol(self):
        teks = nba_report_mod.render_nba_report(
            copy.deepcopy(self.verif["DEN@CHI_2026-11-22"])
        )
        self.assertIn("Vonis laga", teks)
        self.assertIn("Vonis: KUNING", teks)
        self.assertIn("VETO — LAGA INI DIBLOKIR DARI TIKET", teks)
        self.assertIn("Nic Claxton", teks)
        # Veto tampil SEBELUM bullet demerit DI DALAM bagian Vonis
        # (menonjol, bukan terkubur) — "edge kecil" juga muncul di
        # bagian lain laporan, jadi perbandingannya dibatasi ke
        # bagian Vonis.
        bagian_vonis = teks[teks.index("Vonis laga") :]
        self.assertLess(
            bagian_vonis.index("VETO — LAGA INI DIBLOKIR"),
            bagian_vonis.index("edge kecil"),
        )
        # Cedera (bagian Kabar pemain) tampil sebelum Vonis.
        self.assertLess(teks.index("Kabar pemain"), teks.index("Vonis laga"))

    def test_dal_live_menengah_hijau(self):
        teks = nba_report_mod.render_nba_report(
            copy.deepcopy(self.live["DAL@UTA_2026-11-22"])
        )
        self.assertIn("Vonis: MENENGAH HIJAU", teks)
        self.assertNotIn("VETO — LAGA INI DIBLOKIR", teks)


class TestConfigDanPemetaan(unittest.TestCase):
    """Kunci config vonis + file pemetaan rim protector CHECK-IN."""

    def test_kunci_vonis_hadir(self):
        vonis = CFG["vonis"]
        for kunci in (
            "enabled",
            "edge_hijau_pct",
            "p_setan_hijau",
            "gap_kecil_pct",
            "ekor_jauh_points",
            "ekor_harga_rendah_cents",
            "total_tinggi_points",
            "max_demerit_menengah",
            "veto_total_tinggi_points",
            "veto_pace_tinggi",
        ):
            self.assertIn(kunci, vonis, f"vonis.{kunci} hilang dari config")
        self.assertTrue(vonis["enabled"])
        self.assertGreater(vonis["edge_hijau_pct"], 0)
        self.assertGreater(vonis["p_setan_hijau"], 0)
        self.assertLess(vonis["p_setan_hijau"], 1)
        for kunci in (
            "min_games",
            "min_mp_per_game",
            "min_blk_per_game",
            "max_per_team",
        ):
            self.assertIn(kunci, vonis["rim_protector"])

    def test_file_pemetaan_valid(self):
        self.assertTrue(PEMETAAN.exists(), "file pemetaan CHECK-IN hilang")
        dokumen = json.loads(PEMETAAN.read_text(encoding="utf-8"))
        self.assertEqual(dokumen["format"], "rim_protector")
        self.assertEqual(dokumen["season"], "2026-27")
        self.assertEqual(len(dokumen["teams"]), 30)
        chi = {p["player"]: p for p in dokumen["teams"]["CHI"]}
        self.assertIn("Nic Claxton", chi)
        self.assertEqual(chi["Nic Claxton"]["blk_per_game"], 1.0)
        okc = {p["player"]: p for p in dokumen["teams"]["OKC"]}
        self.assertEqual(okc["Chet Holmgren"]["blk_per_game"], 3.0)
        self.assertEqual(okc["Aday Mara"]["blk_per_game"], 1.7)
        for tim, daftar in dokumen["teams"].items():
            self.assertLessEqual(len(daftar), 2, tim)
            for entri in daftar:
                self.assertGreaterEqual(entri["blk_per_game"], 0.8)
                self.assertGreaterEqual(entri["mp_per_game"], 15.0)
                self.assertGreaterEqual(entri["games_played"], 3)


if __name__ == "__main__":
    unittest.main()
