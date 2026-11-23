"""Tes Patch #5 v18.1 — vonis (MENENGAH_HIJAU + simetri D7).

(a) Demerit tail_fragility dievaluasi pada GARIS REFERENSI STANDAR
= garis tangga terendah dengan harga venue >= 82¢ yang LOLOS gate
eksekusi (cek_eksekusi) — BUKAN di plafon equilibrium Asuransi
(~88,5¢). Bila tidak ada garis yang memenuhi, fallback ke garis
Asuransi + dicatat di indikator["garis_referensi_tail_fragility"].
(b) Simetri D7: filter menit minimal mp >= 15,0
(vonis.tunggu_lineup.min_minutes_pg_all_paths) diterapkan pada
KEDUA jalur bintang TUNGGU_LINEUP (USG >= 24% DAN BPM >= +2,0).
mp hilang -> jalur tidak lolos (sama seperti jalur USG v18).
"""

from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path

import config as config_mod
from engine import vonis as vonis_mod

CFG = config_mod.load_playstyle()
ROOT = Path(__file__).resolve().parent.parent
ARTEFAK_LIVE = ROOT / "out" / "analysis_live_2026-11-22.json"
ARTEFAK_VERIF = ROOT / "out" / "analysis_verif_tahap4_2026-11-22.json"


def _cdf_normal(median, sigma, garis_min, garis_max, langkah=2.0):
    markets = {}
    n = int(round((garis_max - garis_min) / langkah)) + 1
    for i in range(n):
        garis = garis_min + i * langkah
        z = (garis - median) / sigma
        p = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        markets[f"total_under_{garis:g}"] = round(p, 6)
    return markets


def _tangga(baris):
    return [
        {
            "line": garis,
            "side": "under",
            "price_cents": harga,
            "jup_estimated_cents": harga + 0.5,
            "volume_usd": volume,
            "thin": thin,
            "bid_cents": harga - 1.0,
            "ask_cents": harga + 0.5,
            "liquidity": 30000.0,
        }
        for garis, harga, volume, thin in baris
    ]


def _kaki(match_id, ticket, line, p_model, p_market, harga):
    p_final = round(0.3 * p_model + 0.7 * p_market, 3)
    return {
        "leg_id": f"{match_id}:{ticket}",
        "market_type": "total_under",
        "line": line,
        "p_model": p_model,
        "p_market": p_market,
        "comparison_source": "kalshi",
        "p_final": p_final,
        "price_cents": harga,
        "jup_estimated_cents": harga,
        "ev_pct": None,
        "price_label": None,
        "volume_usd": None,
        "thin": None,
        "ticket": ticket,
    }


def _analisis_pemisah(margin=15.0, harga_datar=False, garis_sampah=False):
    """Fixture DEN-like tempat EQ dan garis referensi BERBEDA vonis.

    Median 233 sigma 19,2, pasar 234,5. Kemiringan harga 2,17¢/2pt:
    garis referensi (jup >= 82¢ terendah yang lolos eksekusi) =
    U250,5 @82,0¢ dengan P banjir 3P 68,0% / FT 60,2% (RAPUH —
    di bawah 72%/67%); equilibrium Asuransi = U256,5 @88,5¢ dengan
    P banjir 3P 78,2% / FT 71,6% (TAHAN). Di v18 (demerit di EQ),
    laga ini 0 demerit; di v18.1, 1 demerit tail_fragility.
    ``margin`` 2,0 menambah demerit spread_tipis -> 2 demerit ->
    MENENGAH_HIJAU (di v18 tetap HIJAU dengan 1 demerit).
    ``harga_datar``: semua harga jup < 82¢ -> fallback referensi
    ke garis Asuransi. ``garis_sampah``: satu garis jauh U117,5
    @82,5¢ yang gagal eksekusi (ask 99¢, likuiditas $3,80) —
    referensi TIDAK boleh jatuh ke sana.
    """
    baris = []
    garis = 240.5
    while garis <= 270.5 + 1e-9:
        if harga_datar:
            harga = round(70.0 + (garis - 240.5) * 0.3, 2)
        else:
            harga = round(81.5 + (garis - 250.5) * 2.17 / 2.0, 2)
        baris.append((garis, harga, 500.0, False))
        garis = round(garis + 2.0, 9)
    tangga = _tangga(baris)
    if garis_sampah:
        tangga.append(
            {
                "line": 117.5,
                "side": "under",
                "price_cents": 82.0,
                "jup_estimated_cents": 82.5,
                "volume_usd": None,
                "thin": True,
                "bid_cents": 65.0,
                "ask_cents": 99.0,
                "liquidity": 3.8,
            }
        )
        tangga.sort(key=lambda e: float(e["line"]))
    match_id = "DEN@CHI_2026-11-22"
    return {
        "format": "nba_analysis",
        "format_version": 1,
        "match_id": match_id,
        "status": "OK",
        "legs": [
            _kaki(match_id, "insurance", 252.5, 0.845, 0.83, 82.0),
            _kaki(match_id, "main", 250.5, 0.819, 0.80, 79.0),
        ],
        "simulation": {
            "score_distribution": {
                "total": {"median": 233.0},
                "ot_probability": 0.02,
                "margin": {"median": margin},
            },
            "markets": _cdf_normal(233.0, 19.2, 203.0, 278.0),
        },
        "market": {"main_total_line": 234.5, "totals": tangga},
        "inputs": {
            "home": {"stats_season": {"pace": 103.22}, "players": []},
            "away": {"stats_season": {"pace": 98.3}, "players": []},
        },
        "injuries": {"entries": []},
    }


def _muat_artefak(path):
    dokumen = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        m["nba_analysis"]["match_id"]: copy.deepcopy(m["nba_analysis"])
        for m in dokumen["matches"]
    }


def _analisis_timing(cedera, pemain):
    return {
        "format": "nba_analysis",
        "match_id": "IND@NYK_2026-11-22",
        "game_date": "2026-11-22",
        "injuries": {"entries": cedera},
        "inputs": {
            "away": {"players": pemain},
            "home": {"players": []},
        },
    }


def _q(nama, tim="IND"):
    return {"player": nama, "status": "QUESTIONABLE", "team_tricode": tim}


def _pemain(nama, bpm, tim="IND", mp=30.0):
    return {"player": nama, "bpm": bpm, "team_tricode": tim, "mp_per_game": mp}


class TestGarisReferensiTailFragility(unittest.TestCase):
    """(a) Demerit tail_fragility di garis referensi ~82¢."""

    def test_demerit_menyala_di_referensi_tapi_tidak_di_eq(self):
        # Di v18 (demerit di EQ 88,5¢): 0 demerit. Di v18.1
        # (demerit di referensi 82¢): tail_fragility menyala.
        hasil = vonis_mod.nilai_vonis(_analisis_pemisah(), None, CFG)
        self.assertEqual(hasil["vonis"], "hijau")  # 1 demerit + rem
        self.assertIn("tail_fragility", hasil["indikator"]["demerit"])
        ref = hasil["indikator"]["garis_referensi_tail_fragility"]
        self.assertEqual(ref["line"], 250.5)
        self.assertAlmostEqual(ref["harga_venue_cents"], 82.0)
        self.assertFalse(ref["fallback_ke_equilibrium"])
        self.assertAlmostEqual(ref["p_banjir_3p"], 0.680, places=2)
        self.assertAlmostEqual(ref["p_banjir_ft"], 0.602, places=2)
        # Indikator P banjir di garis Asuransi TIDAK berubah
        # (tetap di EQ — dipakai alasan HIJAU + laporan).
        self.assertAlmostEqual(hasil["indikator"]["p_banjir_3p"], 0.782, places=2)
        self.assertAlmostEqual(hasil["indikator"]["p_banjir_ft"], 0.716, places=2)
        self.assertEqual(hasil["indikator"]["garis_asuransi"]["line"], 256.5)

    def test_dua_demerit_jadi_menengah_hijau(self):
        # Referensi rapuh + spread tipis = 2 demerit -> vonis
        # MENENGAH_HIJAU (di v18: HIJAU dengan 1 demerit) —
        # pemulihan tier yang dimaksud Patch #5a.
        hasil = vonis_mod.nilai_vonis(_analisis_pemisah(margin=2.0), None, CFG)
        self.assertEqual(hasil["vonis"], "menengah_hijau")
        self.assertEqual(
            sorted(hasil["indikator"]["demerit"]),
            ["spread_tipis", "tail_fragility"],
        )

    def test_tanpa_garis_82_fallback_ke_eq_dan_dicatat(self):
        # Semua harga < 82¢ -> referensi = garis Asuransi (EQ),
        # dicatat sebagai fallback (bukan diam-diam).
        hasil = vonis_mod.nilai_vonis(_analisis_pemisah(harga_datar=True), None, CFG)
        ref = hasil["indikator"]["garis_referensi_tail_fragility"]
        self.assertTrue(ref["fallback_ke_equilibrium"])
        self.assertEqual(ref["line"], hasil["indikator"]["garis_asuransi"]["line"])
        self.assertNotIn("tail_fragility", hasil["indikator"]["demerit"])

    def test_garis_sampah_tidak_jadi_referensi(self):
        # Garis jauh U117,5 @82,5¢ gagal eksekusi (ask 99¢) -> TIDAK
        # boleh jadi referensi; referensi tetap U250,5 yang nyata.
        hasil = vonis_mod.nilai_vonis(_analisis_pemisah(garis_sampah=True), None, CFG)
        ref = hasil["indikator"]["garis_referensi_tail_fragility"]
        self.assertEqual(ref["line"], 250.5)
        self.assertFalse(ref["fallback_ke_equilibrium"])
        self.assertIn("tail_fragility", hasil["indikator"]["demerit"])

    def test_ambang_referensi_dari_config(self):
        # Harga minimum referensi dari config: dengan 0,90, garis
        # referensi naik ke garis >= 90¢ (U262,5 @92,9¢ — tahan
        # banjir) -> demerit padam.
        cfg = copy.deepcopy(CFG)
        cfg["vonis"]["tail_fragility_reference_price_min"] = 0.90
        hasil = vonis_mod.nilai_vonis(_analisis_pemisah(), None, cfg)
        ref = hasil["indikator"]["garis_referensi_tail_fragility"]
        self.assertGreaterEqual(ref["harga_venue_cents"], 90.0)
        self.assertNotIn("tail_fragility", hasil["indikator"]["demerit"])

    def test_kunci_referensi_hilang_config_error(self):
        cfg = copy.deepcopy(CFG)
        del cfg["vonis"]["tail_fragility_reference_price_min"]
        with self.assertRaises(config_mod.ConfigError):
            vonis_mod.nilai_vonis(_analisis_pemisah(), None, cfg)

    def test_config_kunci_hadir(self):
        self.assertEqual(CFG["vonis"]["tail_fragility_reference_price_min"], 0.82)


class TestReferensiArtefakNyata(unittest.TestCase):
    """(a) pada artefak nyata 22 Nov (nilai diukur)."""

    @classmethod
    def setUpClass(cls):
        cls.live = _muat_artefak(ARTEFAK_LIVE)

    def test_orl_live_dapat_demerit_tapi_tetap_hijau(self):
        # ORL@WAS: EQ U241,5 tahan (74,5%/67,4%) tapi referensi
        # U237,5 @84,0¢ rapuh (67,5%/59,6%) -> 1 demerit, vonis
        # tetap HIJAU (maks 1 + rem alami).
        hasil = vonis_mod.nilai_vonis(self.live["ORL@WAS_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "hijau")
        self.assertEqual(hasil["indikator"]["demerit"], ["tail_fragility"])
        ref = hasil["indikator"]["garis_referensi_tail_fragility"]
        self.assertEqual(ref["line"], 237.5)
        self.assertAlmostEqual(ref["harga_venue_cents"], 84.0)

    def test_det_live_tetap_hijau_satu_demerit(self):
        # DET@ATL: referensi U241,5 @83,0¢ tahan (76,2%/69,3%) ->
        # tanpa demerit tambahan; demerit tetap [spread_tipis].
        hasil = vonis_mod.nilai_vonis(self.live["DET@ATL_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "hijau")
        self.assertEqual(hasil["indikator"]["demerit"], ["spread_tipis"])
        ref = hasil["indikator"]["garis_referensi_tail_fragility"]
        self.assertEqual(ref["line"], 241.5)


class TestSimetriD7(unittest.TestCase):
    """(b) mp >= 15,0 simetris di kedua jalur TUNGGU_LINEUP."""

    def test_bpm_mp_12_bukan_bintang(self):
        # Jalur BPM dengan mp 12,0 (< 15,0): BUKAN bintang — di v18
        # (tanpa filter menit di jalur BPM) ini TUNGGU_LINEUP.
        analisis = _analisis_timing(
            [_q("Bintang Muda")],
            [_pemain("Bintang Muda", 5.0, mp=12.0)],
        )
        hasil = vonis_mod.cek_tunggu_lineup(analisis, CFG)
        self.assertFalse(hasil["tunggu"])
        self.assertEqual(hasil["bintang"], [])
        self.assertEqual(hasil["diperiksa"][0]["bpm_ditolak"], "bukan_rotasi")

    def test_bpm_mp_15_bintang_batas_inklusif(self):
        analisis = _analisis_timing(
            [_q("Bintang Muda")],
            [_pemain("Bintang Muda", 5.0, mp=15.0)],
        )
        hasil = vonis_mod.cek_tunggu_lineup(analisis, CFG)
        self.assertTrue(hasil["tunggu"])
        self.assertEqual(hasil["bintang"][0]["player"], "Bintang Muda")

    def test_bpm_tanpa_menit_bukan_bintang(self):
        # mp hilang di jalur BPM -> tidak lolos (simetris dengan
        # jalur USG: menit tidak bisa ditafsirkan).
        analisis = _analisis_timing(
            [_q("Tanpa Menit")],
            [{"player": "Tanpa Menit", "bpm": 5.0, "team_tricode": "IND"}],
        )
        hasil = vonis_mod.cek_tunggu_lineup(analisis, CFG)
        self.assertFalse(hasil["tunggu"])
        self.assertEqual(hasil["diperiksa"][0]["bpm_ditolak"], "mp_tidak_ada")

    def test_usg_mp_12_bukan_bintang(self):
        # Jalur USG dengan mp 12,0: di v18 lolos (ambang 10,0);
        # di v18.1 ditolak (ambang simetris 15,0).
        analisis = _analisis_timing(
            [_q("Pemain Usg")],
            [_pemain("Pemain Usg", 1.0, mp=12.0)],
        )
        hasil = vonis_mod.cek_tunggu_lineup(
            analisis, CFG, usg_pemain={"Pemain Usg": 0.28}
        )
        self.assertFalse(hasil["tunggu"])
        self.assertEqual(hasil["diperiksa"][0]["usg_ditolak"], "bukan_rotasi")

    def test_usg_mp_15_bintang_batas_inklusif(self):
        analisis = _analisis_timing(
            [_q("Pemain Usg")],
            [_pemain("Pemain Usg", 1.0, mp=15.0)],
        )
        hasil = vonis_mod.cek_tunggu_lineup(
            analisis, CFG, usg_pemain={"Pemain Usg": 0.28}
        )
        self.assertTrue(hasil["tunggu"])
        self.assertEqual(hasil["bintang"][0]["player"], "Pemain Usg")

    def test_usg_mp_10_bukan_bintang(self):
        # mp tepat 10,0 (ambang lama) kini ditolak di timing gate.
        analisis = _analisis_timing(
            [_q("Pemain Usg")],
            [_pemain("Pemain Usg", 1.0, mp=10.0)],
        )
        hasil = vonis_mod.cek_tunggu_lineup(
            analisis, CFG, usg_pemain={"Pemain Usg": 0.28}
        )
        self.assertFalse(hasil["tunggu"])

    def test_simetri_pemain_sama_kedua_jalur(self):
        # Pemain yang sama (BPM +5,0, USG 28%, mp 12,0) ditolak di
        # KEDUA jalur dengan alasan yang sama — tidak ada jalur
        # yang lolos lewat celah menit.
        analisis = _analisis_timing(
            [_q("Dua Jalur")],
            [_pemain("Dua Jalur", 5.0, mp=12.0)],
        )
        hasil = vonis_mod.cek_tunggu_lineup(
            analisis, CFG, usg_pemain={"Dua Jalur": 0.28}
        )
        self.assertFalse(hasil["tunggu"])
        self.assertEqual(hasil["diperiksa"][0]["bpm_ditolak"], "bukan_rotasi")

    def test_ambang_dari_config(self):
        cfg = copy.deepcopy(CFG)
        cfg["vonis"]["tunggu_lineup"]["min_minutes_pg_all_paths"] = 10.0
        analisis = _analisis_timing(
            [_q("Pemain Usg")],
            [_pemain("Pemain Usg", 1.0, mp=12.0)],
        )
        hasil = vonis_mod.cek_tunggu_lineup(
            analisis, cfg, usg_pemain={"Pemain Usg": 0.28}
        )
        self.assertTrue(hasil["tunggu"])

    def test_kunci_hilang_config_error(self):
        cfg = copy.deepcopy(CFG)
        del cfg["vonis"]["tunggu_lineup"]["min_minutes_pg_all_paths"]
        with self.assertRaises(config_mod.ConfigError):
            vonis_mod.cek_tunggu_lineup(
                _analisis_timing([_q("A")], [_pemain("A", 5.0)]), cfg
            )

    def test_config_kunci_hadir(self):
        self.assertEqual(
            CFG["vonis"]["tunggu_lineup"]["min_minutes_pg_all_paths"], 15.0
        )
        # mp_min_rotasi 10,0 TETAP ada (dipakai definisi pemain
        # berdampak di luar timing gate: rem alami + gap besar).
        self.assertEqual(CFG["vonis"]["tunggu_lineup"]["mp_min_rotasi"], 10.0)


class TestSimetriArtefakNyata(unittest.TestCase):
    """(b) bintang nyata (mp >= 29) tetap memicu TUNGGU_LINEUP."""

    @classmethod
    def setUpClass(cls):
        cls.live = _muat_artefak(ARTEFAK_LIVE)

    def test_den_live_tetap_tunggu_powell(self):
        hasil = vonis_mod.nilai_vonis(self.live["DEN@CHI_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "tunggu_lineup")

    def test_ind_live_tetap_tunggu_kat_siakam(self):
        hasil = vonis_mod.nilai_vonis(self.live["IND@NYK_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "tunggu_lineup")

    def test_okc_live_tetap_tunggu_dua_bintang(self):
        hasil = vonis_mod.nilai_vonis(self.live["OKC@MIA_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "tunggu_lineup")


if __name__ == "__main__":
    unittest.main()
