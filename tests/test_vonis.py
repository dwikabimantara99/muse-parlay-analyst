"""Tes sistem vonis v18 per laga (engine/vonis.py) + wiring komposer/laporan.

Vonis v18: HIJAU (kandidat Asuransi — 0 veto + <=1 demerit + >=1
rem alami) / MENENGAH_HIJAU (<=3 demerit) / KUNING (>=4 demerit
atau pemicu keras: veto / OT empiris) / TUNGGU_LINEUP (bintang
masih Questionable). Demerit v18 (6): tail_fragility (gabungan),
total_tinggi, gap_besar, ekor_gemuk (diperketat), foul_tinggi,
spread_tipis. DIHAPUS dari v17: demerit edge_kecil, banjir_lemah,
setan_lemah, volume_tipis, gap_kecil + pemicu keras
edge_tidak_positif + pemicu OT sim 2,8% — tes yang mengunci
perilaku v17 itu diperbarui/dihapus dengan alasan di bawah + di
LAPORAN-VONIS-V18.md.

Distribusi slate uji 22 Nov v18 (diukur): HIJAU 5 / MENENGAH_HIJAU
0 / KUNING 1 (DEN verif, veto) / TUNGGU_LINEUP 4 (OKC live, DEN
live, IND, OKC verif). v17: HIJAU 0 / MENENGAH 2 / KUNING 8.

CATATAN HIJAU: fixture sehat sintetis (_analisis_sehat, median 220
sigma 5 — nilai diukur, dibekukan) HIJAU dengan 1 demerit gap_besar
(gap model-vs-pasar +13,9% di garis Asuransi U238,5 — CDF sempit
sigma 5 vs harga tangga; P banjir 3P 97,7% / FT 88,4%, P setan
53,3%, edge terbaik +8,2%, OT empiris 3,35% pada spread 15,0,
veto dievaluasi dan tidak menyala — v18.1: IND + NYK terpetakan
(tier fallback) sehingga rem paint_utuh ikut menyala; di v18 veto
tidak dievaluasi karena kedua tim belum terpetakan).

Tes artefak nyata memakai out/analysis_live_2026-11-22.json +
out/analysis_verif_tahap4_2026-11-22.json (file runtime, gitignored)
dan di-skip bila file tidak ada — pola yang sama seperti
tests/test_equilibrium.py. Tes nilai_vonis pada artefak nyata
memakai fetch USG live (cache satu-proses) HANYA bila ada pemain
Questionable/OUT yang butuh USG; tes sintetis yang butuh USG
memakai mock (deterministik).
"""

from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path
from unittest import mock

import config as config_mod
from engine import stress as stress_mod
from engine import ticket_composer as ticket_composer_mod
from engine import vonis as vonis_mod
from ingest import pemain_usg as pemain_usg_mod
from ingest.common import FetchResult
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
    Kuotasi default hidup (bid harga-1 / ask harga+0,5) +
    likuiditas $30.000 — garis fixture lolos gate eksekusi v18
    kecuali tes mengubahnya eksplisit (revisi koordinator).
    """
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
    margin=15.0,
    def_rtg_home=None,
    def_rtg_away=None,
    ftr_home=None,
    ftr_away=None,
    players_home=None,
    players_away=None,
):
    """Artefak nba_analysis minimal dengan CDF normal penuh + tangga.

    v18: ``margin`` (median margin sim) WAJIB ada — spread adalah
    data wajib vonis (None = spread tidak bisa dibaca -> KUNING
    data_tidak_cukup). ``def_rtg_*``/``ftr_*`` mengisi stats_season
    (None = field tidak ada -> indikator terkait tidak_dievaluasi).
    ``players_*`` mengisi inputs pemain (bpm/mp_per_game untuk
    timing gate + rem pencetak utama + aturan gap).
    """
    distribusi = {"total": {"median": median}}
    if ot is not None:
        distribusi["ot_probability"] = ot
    if margin is not None:
        distribusi["margin"] = {"median": margin}
    stats_home = {"pace": pace_home}
    stats_away = {"pace": pace_away}
    if def_rtg_home is not None:
        stats_home["def_rtg"] = def_rtg_home
    if def_rtg_away is not None:
        stats_away["def_rtg"] = def_rtg_away
    if ftr_home is not None:
        stats_home["ftr"] = ftr_home
    if ftr_away is not None:
        stats_away["ftr"] = ftr_away
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
            "home": {
                "stats_season": stats_home,
                "players": players_home or [],
            },
            "away": {
                "stats_season": stats_away,
                "players": players_away or [],
            },
        },
        "injuries": {"entries": injuries if injuries is not None else []},
    }


def _analisis_sehat(match_id="IND@NYK_2026-11-22"):
    """Fixture laga sehat (v18.1: MENENGAH_HIJAU, 2 demerit — nilai
    diukur).

    Median 220 sigma 5, garis bandar 221,5, spread 15,0, pace
    kandang 94,54 (rem pace_lambat) + selaras pasar (gap 1,5 poin,
    total 221,5 <= 228). Garis Asuransi = equilibrium Asuransi
    U238,5 @88,5¢. v18.1 (Patch #5a): demerit kedua adalah
    tail_fragility di garis REFERENSI U232,5 @82,5¢ (banjir FT
    50,0% < 67% — CDF sempit sigma 5 membuat garis 82¢ ini rapuh
    banjir; di garis Asuransi banjir tetap 97,7%/88,4%). v18.1:
    veto DIEVALUASI (IND + NYK terpetakan tier fallback) dan
    tidak menyala — rem paint_utuh ikut menyala; di v18 veto
    tidak dievaluasi (kedua tim belum terpetakan). FTr/DRtg tidak
    ada (indikator terkait tidak_dievaluasi).
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
    """Fixture ekor lebar (median 233 sigma 19,2, mirip DEN nyata).

    v18: dengan tangga normal, garis Asuransi = equilibrium
    Asuransi U256,5 @82,5¢ (jarak 22,0 tapi harga > 80¢) -> ekor
    gemuk TIDAK memicu. Untuk memicu ekor gemuk, tes memakai
    varian semua-garis-thin: equilibrium tidak ada, garis Asuransi
    jatuh ke kaki artefak U252,5 @76,5¢ (jarak 18,0, harga <= 80¢).
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
    """CFG copy dengan satu kunci dihapus (tes ConfigError)."""
    cfg = copy.deepcopy(CFG)
    target = cfg
    for kunci_parsial in kunci[:-1]:
        target = target[kunci_parsial]
    del target[kunci[-1]]
    return cfg


def _usg_fetch_result(pemain):
    """FetchResult USG mock (deterministik — tanpa jaringan)."""
    return FetchResult(
        source="stats.nba.com",
        tier=1,
        fetched_at="2026-11-23T00:00:00+00:00",
        ok=True,
        data=pemain,
        error=None,
        extra={},
    )


class TestVonisArtefakNyata(unittest.TestCase):
    """Vonis pada 10 baris slate uji 22 Nov 2026 (data nyata, v18)."""

    @classmethod
    def setUpClass(cls):
        if not ARTEFAK_LIVE.exists() or not ARTEFAK_VERIF.exists():
            raise unittest.SkipTest("artefak slate uji tidak ada di out/")
        cls.live = _muat_artefak(ARTEFAK_LIVE)
        cls.verif = _muat_artefak(ARTEFAK_VERIF)

    def test_den_verif_kuning_veto_menyala(self):
        # Kasus uji WAJIB: DEN@CHI verif -> KUNING via veto AND
        # (Claxton OUT + garis 236,5 + pace 103,22); 1 demerit
        # (total_tinggi) + 1 rem (pace_lambat). REVISI KOORDINATOR:
        # tail_fragility HILANG — garis Asuransi kini equilibrium
        # U258,5 (banjir 81,1%/75,1% di atas ambang demerit 72%/67%),
        # bukan garis artefak yang lebih rendah.
        hasil = vonis_mod.nilai_vonis(self.verif["DEN@CHI_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "kuning")
        self.assertEqual(hasil["indikator"]["pemicu_keras"], "veto_rim_protector")
        self.assertEqual(hasil["indikator"]["demerit"], ["total_tinggi"])
        self.assertEqual(hasil["indikator"]["rem_alami"]["terpenuhi"], ["pace_lambat"])
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

    def test_okc_verif_tunggu_lineup_bukan_veto(self):
        # v18: OKC@MIA verif BUKAN lagi KUNING-veto (veto AND tidak
        # menyala: garis 231,5 < 232,0 — hanya pace yang menyala ->
        # peringatan parsial). Vonisnya TUNGGU_LINEUP: Giannis
        # Questionable (BPM +9,0).
        hasil = vonis_mod.nilai_vonis(self.verif["OKC@MIA_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "tunggu_lineup")
        self.assertIsNone(hasil["indikator"]["pemicu_keras"])
        gate = hasil["indikator"]["timing_gate"]
        self.assertTrue(gate["tunggu"])
        self.assertEqual(
            [b["player"] for b in gate["bintang"]], ["Giannis Antetokounmpo"]
        )
        veto = hasil["indikator"]["veto"]
        self.assertTrue(veto["dievaluasi"])
        self.assertFalse(veto["menyala"])
        self.assertTrue(veto["peringatan_parsial"])
        self.assertEqual(veto["kondisi_menyala"], ["pace"])
        self.assertEqual(
            [o["player"] for o in veto["pelindung_out"]], ["Chet Holmgren"]
        )

    def test_okc_live_tunggu_lineup_dua_bintang(self):
        # OKC@MIA live: Giannis (BPM +9,0) + SGA (BPM +9,4)
        # Questionable -> TUNGGU_LINEUP.
        hasil = vonis_mod.nilai_vonis(self.live["OKC@MIA_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "tunggu_lineup")
        gate = hasil["indikator"]["timing_gate"]
        self.assertEqual(
            {b["player"] for b in gate["bintang"]},
            {"Giannis Antetokounmpo", "Shai Gilgeous-Alexander"},
        )

    def test_den_live_tunggu_lineup_powell(self):
        # DEN@CHI live: Norman Powell Questionable (USG 26,0%,
        # 29,5 mnt, BPM +0,2 — lolos kualifikasi jalur USG) ->
        # TUNGGU_LINEUP. Veto tidak menyala (Claxton belum OUT di
        # snapshot live — kejujuran ketepatan waktu kabar cedera).
        hasil = vonis_mod.nilai_vonis(self.live["DEN@CHI_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "tunggu_lineup")
        gate = hasil["indikator"]["timing_gate"]
        self.assertEqual([b["player"] for b in gate["bintang"]], ["Norman Powell"])
        veto = hasil["indikator"]["veto"]
        self.assertTrue(veto["dievaluasi"])
        self.assertFalse(veto["menyala"])
        self.assertEqual(veto["pelindung_out"], [])

    def test_ind_live_tunggu_lineup_kat_siakam(self):
        hasil = vonis_mod.nilai_vonis(self.live["IND@NYK_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "tunggu_lineup")
        gate = hasil["indikator"]["timing_gate"]
        self.assertEqual(
            {b["player"] for b in gate["bintang"]},
            {"Karl-Anthony Towns", "Pascal Siakam"},
        )

    def test_det_live_hijau_spread_tipis(self):
        # v18: DET@ATL BUKAN lagi KUNING-ot_tinggi (OT empiris 5,70%
        # < 8,5%) — HIJAU dengan 1 demerit spread_tipis (spread
        # 2,0) + 2 rem (pertahanan Top-10 + pace lambat).
        hasil = vonis_mod.nilai_vonis(self.live["DET@ATL_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "hijau")
        self.assertEqual(hasil["indikator"]["demerit"], ["spread_tipis"])
        self.assertIsNone(hasil["indikator"]["pemicu_keras"])
        self.assertEqual(
            hasil["indikator"]["rem_alami"]["terpenuhi"],
            ["pertahanan_top10", "pace_lambat"],
        )
        self.assertAlmostEqual(hasil["indikator"]["p_ot_empiris"], 0.05695, places=5)
        self.assertAlmostEqual(hasil["indikator"]["ot_probability"], 0.0289, places=4)

    def test_orl_live_hijau_satu_demerit_referensi(self):
        # v18.1 (Patch #5a — MEMBALIK test_orl_live_hijau_nol_demerit):
        # ORL@WAS tetap HIJAU, tapi kini membawa 1 demerit
        # tail_fragility: di garis Asuransi EQ U241,5 banjir
        # 74,5%/67,4% (di atas ambang demerit 72%/67%), tapi di
        # garis REFERENSI U237,5 @84,0¢ banjir 67,5%/59,6% (di
        # bawah ambang). Inilah pemulihan yang dimaksud Patch #5a:
        # laga tanggung kembali tercatat rapuh, bukan 0 demerit.
        hasil = vonis_mod.nilai_vonis(self.live["ORL@WAS_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "hijau")
        self.assertEqual(hasil["indikator"]["demerit"], ["tail_fragility"])
        self.assertEqual(
            hasil["indikator"]["rem_alami"]["terpenuhi"],
            ["pace_lambat", "selaras_pasar"],
        )
        self.assertEqual(
            hasil["indikator"]["garis_referensi_tail_fragility"]["line"], 237.5
        )

    def test_dal_live_hijau_veto_tidak_menyala(self):
        # DAL@UTA: Jaren Jackson Jr. (UTA, 1,3 blok/laga) OUT tapi
        # garis 225,5 + pace 99,89 rendah -> veto TIDAK menyala
        # (kedua kondisi lingkungan gagal). 0 demerit + 1 rem
        # (pertahanan Top-10) -> HIJAU. REVISI KOORDINATOR:
        # tail_fragility HILANG — garis Asuransi kini equilibrium
        # U246,5 (banjir 86,4%/81,6% di atas ambang demerit); gap
        # model-vs-pasar kini 6,47% (< 8%) sehingga tidak ada
        # investigasi Lauri Markkanen lagi (dulu gap +12,3% di
        # garis acuan lama -> investigasi).
        hasil = vonis_mod.nilai_vonis(self.live["DAL@UTA_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "hijau")
        self.assertEqual(hasil["indikator"]["demerit"], [])
        self.assertEqual(
            hasil["indikator"]["rem_alami"]["terpenuhi"], ["pertahanan_top10"]
        )
        self.assertAlmostEqual(hasil["indikator"]["gap_model_pasar"], 0.0647, places=4)
        self.assertEqual(hasil["indikator"]["investigasi"], [])
        veto = hasil["indikator"]["veto"]
        self.assertTrue(veto["dievaluasi"])
        self.assertFalse(veto["menyala"])
        self.assertEqual(
            [o["player"] for o in veto["pelindung_out"]],
            ["Jaren Jackson Jr."],
        )
        self.assertFalse(veto["kondisi_garis"])
        self.assertFalse(veto["kondisi_pace"])

    def test_bos_live_hijau_nol_demerit(self):
        hasil = vonis_mod.nilai_vonis(self.live["BOS@GSW_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "hijau")
        self.assertEqual(hasil["indikator"]["demerit"], [])
        self.assertEqual(
            hasil["indikator"]["rem_alami"]["terpenuhi"],
            ["pertahanan_top10", "pace_lambat"],
        )

    def test_bos_verif_hijau_empat_rem(self):
        # BOS@GSW verif: 0 demerit + 4 rem — termasuk
        # pencetak_utama_out (Paul George + Stephen Curry OUT) dan
        # paint_utuh_blowout_atau_ftr_rendah. Brandon Williams
        # (USG 25,9%) DITOLAK dari rem-3 karena BPM negatif.
        hasil = vonis_mod.nilai_vonis(self.verif["BOS@GSW_2026-11-22"], None, CFG)
        self.assertEqual(hasil["vonis"], "hijau")
        self.assertEqual(hasil["indikator"]["demerit"], [])
        self.assertEqual(
            hasil["indikator"]["rem_alami"]["terpenuhi"],
            [
                "pertahanan_top10",
                "pace_lambat",
                "pencetak_utama_out",
                "paint_utuh_blowout_atau_ftr_rendah",
            ],
        )
        rem3 = hasil["indikator"]["rem_alami"]["rincian"]["pencetak_utama_out"]
        self.assertEqual(
            rem3["pencetak_out_per_tim"],
            {"away": ["Paul George"], "home": ["Stephen Curry"]},
        )
        self.assertEqual(rem3["usg_ditolak"], {"Brandon Williams": "bpm_negatif"})

    def test_distribusi_slate_lima_nol_satu_empat(self):
        hitung = {"hijau": 0, "menengah_hijau": 0, "kuning": 0, "tunggu_lineup": 0}
        for kumpulan in (self.live, self.verif):
            for analisis in kumpulan.values():
                hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
                hitung[hasil["vonis"]] += 1
        self.assertEqual(
            hitung,
            {"hijau": 5, "menengah_hijau": 0, "kuning": 1, "tunggu_lineup": 4},
        )


class TestVonisSintetis(unittest.TestCase):
    """Vonis pada fixture sintetis (perilaku per indikator)."""

    def test_laga_sehat_menengah_dua_demerit_v18_1(self):
        # v18.1 (Patch #5a — MEMBALIK
        # test_laga_sehat_hijau_satu_demerit_gap): fixture sehat
        # kini MENENGAH_HIJAU dengan 2 demerit — gap_besar (gap
        # +13,9% > 8%) + tail_fragility di garis REFERENSI U232,5
        # @82,5¢ (banjir FT 50,0% < 67%; di garis Asuransi banjir
        # tetap 97,7%/88,4% — nilai beku di bawah tidak berubah).
        # + 3 rem.
        hasil = vonis_mod.nilai_vonis(_analisis_sehat(), None, CFG)
        self.assertEqual(hasil["vonis"], "menengah_hijau")
        ind = hasil["indikator"]
        self.assertEqual(ind["demerit"], ["tail_fragility", "gap_besar"])
        self.assertEqual(ind["n_demerit"], 2)
        self.assertIsNone(ind["pemicu_keras"])
        self.assertEqual(
            ind["rem_alami"]["terpenuhi"],
            ["pace_lambat", "paint_utuh_blowout_atau_ftr_rendah", "selaras_pasar"],
        )
        self.assertGreaterEqual(ind["p_banjir_3p"], 0.72)
        self.assertGreaterEqual(ind["p_banjir_ft"], 0.67)
        self.assertAlmostEqual(ind["p_banjir_3p"], 0.97725, places=5)
        self.assertAlmostEqual(ind["p_banjir_ft"], 0.883962, places=5)
        self.assertAlmostEqual(ind["gap_model_pasar"], 0.139353, places=5)
        self.assertGreaterEqual(ind["edge_terbaik"], 0.08)  # info saja
        self.assertEqual(ind["garis_asuransi"]["line"], 238.5)
        self.assertEqual(ind["garis_asuransi"]["sumber"], "equilibrium Asuransi")
        self.assertEqual(ind["garis_referensi_tail_fragility"]["line"], 232.5)
        self.assertIn("rapuh banjir", " ".join(hasil["alasan"]))
        self.assertIn("foul_tinggi", ind["tidak_dinilai"])  # FTr tidak ada

    def test_ekor_gemuk_varian_thin(self):
        # Varian semua-garis-thin: equilibrium tidak ada (semua
        # garis gagal gate eksekusi — likuiditas $5), garis
        # Asuransi jatuh ke kaki artefak U252,5 @76,5¢ (jarak 18,0
        # >= 16, harga <= 80¢) -> ekor_gemuk + tail_fragility.
        # REVISI KOORDINATOR: yang mematikan equilibrium kini
        # likuiditas $5 (volume $5 saja tidak lagi mematikan).
        analisis = _analisis_ekor_gemuk()
        for entri in analisis["market"]["totals"]:
            entri["thin"] = True
            entri["volume_usd"] = 5.0
            entri["liquidity"] = 5.0
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        ind = hasil["indikator"]
        self.assertIs(ind["ekor_gemuk"], True)
        self.assertIn("ekor_gemuk", ind["demerit"])
        self.assertGreaterEqual(ind["jarak_garis_market_points"], 16.0)
        self.assertLessEqual(ind["garis_asuransi"]["harga_venue_cents"], 80)
        self.assertEqual(ind["garis_asuransi"]["sumber"], "kaki Asuransi artefak")
        self.assertIn("ekor gemuk", " ".join(hasil["alasan"]))

    def test_ekor_gemuk_tidak_memicu_harga_mahal(self):
        # Tangga normal: garis Asuransi U256,5 @82,5¢ (jarak 22,0
        # tapi harga > 80¢) -> ekor gemuk TIDAK memicu (ambang
        # diperketat v18: 16 poin DAN <= 80¢).
        hasil = vonis_mod.nilai_vonis(_analisis_ekor_gemuk(), None, CFG)
        ind = hasil["indikator"]
        self.assertIs(ind["ekor_gemuk"], False)
        self.assertNotIn("ekor_gemuk", ind["demerit"])
        self.assertGreaterEqual(ind["jarak_garis_market_points"], 16.0)

    def test_volume_bukan_demerit_v18(self):
        # DIHAPUS v17 -> v18: volume tipis BUKAN demerit lagi
        # (volume hanya info + gate komposer, bukan vonis). Semua
        # garis thin -> vonis tidak berubah dari baseline fixture
        # (v18.1: MENENGAH_HIJAU, 2 demerit gap + tail), tanpa
        # demerit volume_tipis.
        analisis = _analisis_sehat()
        for entri in analisis["market"]["totals"]:
            entri["thin"] = True
            entri["volume_usd"] = 5.0
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertEqual(hasil["vonis"], "menengah_hijau")
        self.assertNotIn("volume_tipis", hasil["indikator"]["demerit"])
        self.assertTrue(hasil["indikator"]["garis_asuransi"]["thin"])

    def test_gap_besar_demerit(self):
        # Fixture sehat: gap +13,9% > 8% tanpa cedera berdampak ->
        # demerit gap_besar (satu-satunya demerit).
        hasil = vonis_mod.nilai_vonis(_analisis_sehat(), None, CFG)
        self.assertIn("gap_besar", hasil["indikator"]["demerit"])
        self.assertGreater(hasil["indikator"]["gap_model_pasar"], 0.08)
        self.assertEqual(hasil["indikator"]["investigasi"], [])

    def test_gap_besar_dengan_cedera_jadi_investigasi(self):
        # Gap besar + pemain berdampak OUT terkonfirmasi (BPM +3,0)
        # -> investigasi, BUKAN demerit.
        analisis = _analisis_sehat()
        analisis["injuries"]["entries"] = [
            {
                "player": "Bintang Out",
                "status": "OUT",
                "team_tricode": "IND",
                "availability_n_sources": 2,
                "sources": ["Official NBA Injury Report", "ESPN"],
            }
        ]
        analisis["inputs"]["away"]["players"] = [
            {
                "player": "Bintang Out",
                "bpm": 3.0,
                "team_tricode": "IND",
                "mp_per_game": 30.0,
            }
        ]
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertNotIn("gap_besar", hasil["indikator"]["demerit"])
        # v18.1: tail_fragility di garis referensi TETAP ada
        # (independen dari investigasi gap) -> 1 demerit, HIJAU.
        self.assertEqual(hasil["indikator"]["demerit"], ["tail_fragility"])
        self.assertEqual(hasil["vonis"], "hijau")
        self.assertEqual(len(hasil["indikator"]["investigasi"]), 1)
        self.assertIn("Bintang Out", hasil["indikator"]["investigasi"][0])

    def test_total_tinggi_demerit_tetap_hijau(self):
        # Garis bandar 236,5 >= 235 -> demerit total_tinggi; total 2
        # demerit (gap_besar + total_tinggi) -> MENENGAH_HIJAU.
        # (v17: 1 demerit -> menengah_hijau karena HIJAU butuh 0.)
        analisis = _analisis_sehat()
        analisis["market"]["main_total_line"] = 236.5
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertIn("total_tinggi", hasil["indikator"]["demerit"])
        self.assertEqual(hasil["vonis"], "menengah_hijau")

    def test_foul_tinggi_demerit(self):
        # FTr kedua tim 0,32 -> gabungan 0,32 >= p80 0,308111.
        analisis = _analisis_sehat()
        analisis["inputs"]["home"]["stats_season"]["ftr"] = 0.32
        analisis["inputs"]["away"]["stats_season"]["ftr"] = 0.32
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertIn("foul_tinggi", hasil["indikator"]["demerit"])
        self.assertAlmostEqual(hasil["indikator"]["ftr_gabungan"], 0.32, places=6)
        self.assertEqual(
            hasil["indikator"]["ftr_per_tim"], {"away": 0.32, "home": 0.32}
        )

    def test_foul_rata_rata_bukan_maks(self):
        # "Gabungan" = RATA-RATA kedua tim: 0,40 + 0,20 -> 0,30 <
        # p80 -> TIDAK demerit (bila memakai maks, 0,40 akan kena).
        analisis = _analisis_sehat()
        analisis["inputs"]["home"]["stats_season"]["ftr"] = 0.40
        analisis["inputs"]["away"]["stats_season"]["ftr"] = 0.20
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertNotIn("foul_tinggi", hasil["indikator"]["demerit"])
        self.assertAlmostEqual(hasil["indikator"]["ftr_gabungan"], 0.30, places=6)

    def test_spread_tipis_demerit(self):
        # Spread 2,0 <= 3,0 -> demerit spread_tipis.
        analisis = _analisis_sehat()
        analisis["simulation"]["score_distribution"]["margin"] = {"median": 2.0}
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertIn("spread_tipis", hasil["indikator"]["demerit"])
        self.assertEqual(hasil["indikator"]["spread_points"], 2.0)
        self.assertAlmostEqual(hasil["indikator"]["p_ot_empiris"], 0.05695, places=5)

    def test_lima_demerit_kuning_tanpa_pemicu_keras(self):
        # 5 demerit (tail, total, ekor, foul, spread) -> KUNING
        # lewat jumlah demerit (>= 4), BUKAN pemicu keras.
        # Equilibrium dimatikan via likuiditas $5 (REVISI
        # KOORDINATOR — volume $5 saja tidak lagi mematikan)
        # supaya garis Asuransi jatuh ke kaki artefak U252,5.
        analisis = _analisis_ekor_gemuk()
        for entri in analisis["market"]["totals"]:
            entri["thin"] = True
            entri["volume_usd"] = 5.0
            entri["liquidity"] = 5.0
        analisis["simulation"]["score_distribution"]["margin"] = {"median": 2.0}
        analisis["market"]["main_total_line"] = 236.5
        analisis["inputs"]["home"]["stats_season"]["ftr"] = 0.32
        analisis["inputs"]["away"]["stats_season"]["ftr"] = 0.32
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertEqual(hasil["vonis"], "kuning")
        self.assertIsNone(hasil["indikator"]["pemicu_keras"])
        self.assertEqual(
            hasil["indikator"]["demerit"],
            [
                "tail_fragility",
                "total_tinggi",
                "ekor_gemuk",
                "foul_tinggi",
                "spread_tipis",
            ],
        )

    def test_hasil_stress_konsisten(self):
        # P banjir + P setan sama dengan/tanpa hasil_stress (fallback
        # CDF menghitung hal yang sama). hasil_stress_dipakai False
        # di sini: skenario_panas menghitung kaki artefak (240,5 /
        # 236,5), bukan garis equilibrium 238,5 — vonis memakai CDF.
        analisis = _analisis_sehat()
        hasil_stress = stress_mod.skenario_panas(analisis, cfg=CFG)
        tanpa = vonis_mod.nilai_vonis(analisis, None, CFG)
        dengan = vonis_mod.nilai_vonis(analisis, hasil_stress, CFG)
        self.assertFalse(dengan["indikator"]["hasil_stress_dipakai"])
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

    def test_hasil_stress_dipakai_bila_garis_cocok(self):
        # Hasil stress yang memuat garis Asuransi (238,5) DIPAKAI:
        # P banjir suntik 0,50/0,60 dilaporkan di indikator. v18.1:
        # demerit tail_fragility kini dinilai di garis REFERENSI
        # (U232,5) — bukan dari P suntik ini — tapi asersi demerit
        # tetap berlaku karena referensi juga rapuh.
        analisis = _analisis_sehat()
        hasil_stress = {
            "banjir_terburuk": "banjir_3p",
            "kaki": [
                {
                    "line": 238.5,
                    "p_under": {
                        "banjir_3p": 0.50,
                        "banjir_ft": 0.60,
                        "setan": 0.40,
                    },
                }
            ],
        }
        hasil = vonis_mod.nilai_vonis(analisis, hasil_stress, CFG)
        self.assertTrue(hasil["indikator"]["hasil_stress_dipakai"])
        self.assertEqual(hasil["indikator"]["p_banjir_3p"], 0.50)
        self.assertEqual(hasil["indikator"]["p_banjir_ft"], 0.60)
        self.assertEqual(hasil["indikator"]["p_setan"], 0.40)
        self.assertIn("tail_fragility", hasil["indikator"]["demerit"])

    def test_hasil_stress_rusak_tidak_crash(self):
        # Stress rusak -> fallback CDF, vonis sama dengan baseline
        # tanpa stress (v18.1: MENENGAH_HIJAU).
        hasil = vonis_mod.nilai_vonis(
            _analisis_sehat(), {"kaki": [{"line": "bukan-angka"}]}, CFG
        )
        baseline = vonis_mod.nilai_vonis(_analisis_sehat(), None, CFG)
        self.assertEqual(hasil["vonis"], baseline["vonis"])
        self.assertEqual(
            hasil["indikator"]["demerit"], baseline["indikator"]["demerit"]
        )
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


class TestRemAlami(unittest.TestCase):
    """Kelima rem alami v18 (satu per satu + aturan HIJAU)."""

    def test_pertahanan_top10(self):
        analisis = _analisis_sehat()
        analisis["inputs"]["home"]["stats_season"]["def_rtg"] = 110.0
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        rem = hasil["indikator"]["rem_alami"]
        self.assertIn("pertahanan_top10", rem["terpenuhi"])
        self.assertEqual(rem["rincian"]["pertahanan_top10"]["tim"], ["home"])

    def test_pertahanan_top10_gagal_drtg_tinggi(self):
        analisis = _analisis_sehat()
        analisis["inputs"]["home"]["stats_season"]["def_rtg"] = 118.0
        analisis["inputs"]["away"]["stats_season"]["def_rtg"] = 117.0
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        rem = hasil["indikator"]["rem_alami"]
        self.assertIn("pertahanan_top10", rem["gagal"])

    def test_pace_lambat_arah_benar(self):
        # Pace LAMBAT = angka KECIL: 94,54 <= 98,91 terpenuhi.
        hasil = vonis_mod.nilai_vonis(_analisis_sehat(), None, CFG)
        self.assertIn("pace_lambat", hasil["indikator"]["rem_alami"]["terpenuhi"])
        # Pace cepat kedua tim -> gagal.
        analisis = _analisis_sehat()
        analisis["inputs"]["home"]["stats_season"]["pace"] = 102.0
        analisis["inputs"]["away"]["stats_season"]["pace"] = 101.0
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertIn("pace_lambat", hasil["indikator"]["rem_alami"]["gagal"])

    def test_pencetak_utama_out_mock_usg(self):
        # Kedua tim kehilangan pencetak USG >= 25% OUT terkonfirmasi
        # (mock USG deterministik).
        analisis = _analisis_sehat()
        analisis["injuries"]["entries"] = [
            {
                "player": "Skorer Tandang",
                "status": "OUT",
                "team_tricode": "IND",
                "availability_n_sources": 2,
                "sources": ["Official NBA Injury Report", "ESPN"],
            },
            {
                "player": "Skorer Kandang",
                "status": "OUT",
                "team_tricode": "NYK",
                "availability_n_sources": 2,
                "sources": ["Official NBA Injury Report", "ESPN"],
            },
        ]
        analisis["inputs"]["away"]["players"] = [
            {
                "player": "Skorer Tandang",
                "bpm": 1.0,
                "team_tricode": "IND",
                "mp_per_game": 30.0,
            }
        ]
        analisis["inputs"]["home"]["players"] = [
            {
                "player": "Skorer Kandang",
                "bpm": 1.0,
                "team_tricode": "NYK",
                "mp_per_game": 30.0,
            }
        ]
        usg = _usg_fetch_result(
            [
                {"player": "Skorer Tandang", "team": "IND", "usg_pct": 0.27},
                {"player": "Skorer Kandang", "team": "NYK", "usg_pct": 0.26},
            ]
        )
        with mock.patch.object(
            pemain_usg_mod, "fetch_pemain_usg_cached", return_value=usg
        ):
            hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        rem = hasil["indikator"]["rem_alami"]
        self.assertIn("pencetak_utama_out", rem["terpenuhi"])
        self.assertEqual(
            rem["rincian"]["pencetak_utama_out"]["pencetak_out_per_tim"],
            {"away": ["Skorer Tandang"], "home": ["Skorer Kandang"]},
        )

    def test_pencetak_utama_out_ditolak_bpm_negatif(self):
        # Skorer USG 27% tapi BPM -3,0 -> DITOLAK kualifikasi jalur
        # USG -> rem gagal (satu sisi tidak punya pencetak).
        analisis = _analisis_sehat()
        analisis["injuries"]["entries"] = [
            {
                "player": "Skorer Tandang",
                "status": "OUT",
                "team_tricode": "IND",
                "availability_n_sources": 2,
                "sources": ["Official NBA Injury Report", "ESPN"],
            },
            {
                "player": "Skorer Kandang",
                "status": "OUT",
                "team_tricode": "NYK",
                "availability_n_sources": 2,
                "sources": ["Official NBA Injury Report", "ESPN"],
            },
        ]
        analisis["inputs"]["away"]["players"] = [
            {
                "player": "Skorer Tandang",
                "bpm": -3.0,
                "team_tricode": "IND",
                "mp_per_game": 30.0,
            }
        ]
        analisis["inputs"]["home"]["players"] = [
            {
                "player": "Skorer Kandang",
                "bpm": 1.0,
                "team_tricode": "NYK",
                "mp_per_game": 30.0,
            }
        ]
        usg = _usg_fetch_result(
            [
                {"player": "Skorer Tandang", "team": "IND", "usg_pct": 0.27},
                {"player": "Skorer Kandang", "team": "NYK", "usg_pct": 0.26},
            ]
        )
        with mock.patch.object(
            pemain_usg_mod, "fetch_pemain_usg_cached", return_value=usg
        ):
            hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        rem = hasil["indikator"]["rem_alami"]
        self.assertIn("pencetak_utama_out", rem["gagal"])
        self.assertEqual(
            rem["rincian"]["pencetak_utama_out"]["usg_ditolak"],
            {"Skorer Tandang": "bpm_negatif"},
        )

    def test_paint_utuh_blowout(self):
        # DEN@CHI (kedua tim terpetakan, tidak ada pelindung OUT) +
        # spread 15,0 >= 8,5 -> cabang blowout terpenuhi.
        analisis = _analisis_sehat(match_id="DEN@CHI_2026-11-22")
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        rem = hasil["indikator"]["rem_alami"]
        self.assertIn("paint_utuh_blowout_atau_ftr_rendah", rem["terpenuhi"])
        rincian = rem["rincian"]["paint_utuh_blowout_atau_ftr_rendah"]
        self.assertIs(rincian["cabang_blowout"], True)

    def test_paint_ftr_rendah(self):
        # Kedua tim FTr 0,20 < p50 0,274398 -> cabang FTr rendah
        # terpenuhi (walau spread 5,0 bukan blowout + veto tidak
        # dievaluasi karena IND/NYK tak terpetakan).
        analisis = _analisis_sehat()
        analisis["simulation"]["score_distribution"]["margin"] = {"median": 5.0}
        analisis["inputs"]["home"]["stats_season"]["ftr"] = 0.20
        analisis["inputs"]["away"]["stats_season"]["ftr"] = 0.20
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        rem = hasil["indikator"]["rem_alami"]
        self.assertIn("paint_utuh_blowout_atau_ftr_rendah", rem["terpenuhi"])
        rincian = rem["rincian"]["paint_utuh_blowout_atau_ftr_rendah"]
        self.assertIs(rincian["cabang_ftr_rendah"], True)

    def test_selaras_pasar(self):
        # |median 220 - pasar 221,5| = 1,5 <= 5,0 DAN pasar <= 228.
        hasil = vonis_mod.nilai_vonis(_analisis_sehat(), None, CFG)
        self.assertIn("selaras_pasar", hasil["indikator"]["rem_alami"]["terpenuhi"])
        # Pasar jauh (226,0; gap 6,0) -> gagal.
        analisis = _analisis_sehat()
        analisis["market"]["main_total_line"] = 226.0
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertIn("selaras_pasar", hasil["indikator"]["rem_alami"]["gagal"])

    def test_tanpa_rem_tidak_hijau(self):
        # 1 demerit (gap_besar) + 0 rem -> MENENGAH_HIJAU, bukan
        # HIJAU (HIJAU butuh >= 1 rem alami).
        analisis = _analisis_sehat()
        analisis["simulation"]["score_distribution"]["margin"] = {"median": 5.0}
        analisis["inputs"]["home"]["stats_season"] = {
            "pace": 102.0,
            "def_rtg": 118.0,
            "ftr": 0.29,
        }
        analisis["inputs"]["away"]["stats_season"] = {
            "pace": 101.0,
            "def_rtg": 117.0,
            "ftr": 0.29,
        }
        analisis["market"]["main_total_line"] = 226.0
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertEqual(hasil["vonis"], "menengah_hijau")
        self.assertEqual(hasil["indikator"]["rem_alami"]["terpenuhi"], [])
        self.assertEqual(
            hasil["indikator"]["rem_alami"]["gagal"],
            [
                "pertahanan_top10",
                "pace_lambat",
                "pencetak_utama_out",
                "paint_utuh_blowout_atau_ftr_rendah",
                "selaras_pasar",
            ],
        )

    def test_rem_tidak_dievaluasi_bukan_gagal(self):
        # Tanpa DRtg kedua tim, rem pertahanan "tidak_dievaluasi"
        # (bukan gagal) — tercatat di tidak_dinilai sebagai
        # rem_pertahanan_top10.
        hasil = vonis_mod.nilai_vonis(_analisis_sehat(), None, CFG)
        rem = hasil["indikator"]["rem_alami"]
        self.assertIn("pertahanan_top10", rem["tidak_dievaluasi"])
        self.assertIn("rem_pertahanan_top10", hasil["indikator"]["tidak_dinilai"])


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

    def test_tanpa_spread_kuning(self):
        # v18: spread (|median margin|) adalah data WAJIB (menggantikan
        # ot_probability sim v17 sebagai data wajib OT).
        analisis = _analisis_sehat()
        del analisis["simulation"]["score_distribution"]["margin"]
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertEqual(hasil["vonis"], "kuning")
        self.assertEqual(hasil["indikator"]["pemicu_keras"], "data_tidak_cukup")
        self.assertIn("spread", hasil["alasan"][0])

    def test_tanpa_ot_sim_tidak_mengubah_vonis(self):
        # v18: ot_probability sim BUKAN lagi data wajib (hanya info).
        # Menghapusnya tidak mengubah vonis (v18.1: baseline
        # fixture MENENGAH_HIJAU); p_ot_empiris tetap dihitung
        # dari spread.
        analisis = _analisis_sehat()
        del analisis["simulation"]["score_distribution"]["ot_probability"]
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        baseline = vonis_mod.nilai_vonis(_analisis_sehat(), None, CFG)
        self.assertEqual(hasil["vonis"], baseline["vonis"])
        self.assertIsNone(hasil["indikator"]["ot_probability"])
        self.assertAlmostEqual(hasil["indikator"]["p_ot_empiris"], 0.0335, places=4)

    def test_soccer_kuning_bukan_nba(self):
        analisis = _analisis_sehat()
        analisis["format"] = "soccer_analysis"
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertEqual(hasil["vonis"], "kuning")
        self.assertEqual(hasil["indikator"]["pemicu_keras"], "bukan_nba")
        self.assertFalse(hasil["indikator"]["dievaluasi"])

    def test_tanpa_garis_bandar_indikator_sekunder_tidak_dinilai(self):
        # main_total_line hilang -> ekor + total tidak dinilai (TANPA
        # demerit); vonis tetap baseline fixture (v18.1:
        # MENENGAH_HIJAU, 2 demerit gap + tail).
        analisis = _analisis_sehat()
        analisis["market"]["main_total_line"] = None
        hasil = vonis_mod.nilai_vonis(analisis, None, CFG)
        self.assertEqual(hasil["vonis"], "menengah_hijau")
        self.assertIn("ekor_gemuk", hasil["indikator"]["tidak_dinilai"])
        self.assertIn("total_tinggi", hasil["indikator"]["tidak_dinilai"])
        self.assertIsNone(hasil["indikator"]["ekor_gemuk"])

    def test_config_rusak_config_error(self):
        with self.assertRaises(config_mod.ConfigError):
            vonis_mod.nilai_vonis(
                _analisis_sehat(),
                None,
                _cfg_tanpa_kunci("vonis", "tail_fragility", "p_flood_3p_below"),
            )
        with self.assertRaises(config_mod.ConfigError):
            vonis_mod.nilai_vonis(
                _analisis_sehat(),
                None,
                _cfg_tanpa_kunci("vonis", "veto", "total_tinggi_points"),
            )
        with self.assertRaises(config_mod.ConfigError):
            vonis_mod.nilai_vonis(
                _analisis_sehat(),
                None,
                _cfg_tanpa_kunci("vonis", "tunggu_lineup", "usg_bintang"),
            )


class TestVeto(unittest.TestCase):
    """Veto rim protector (hard trigger -> KUNING).

    Logika AND diuji tuntas di tests/test_veto_and.py; di sini
    hanya integrasi veto <-> nilai_vonis.
    """

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
        # Laga jadi HIJAU (1 demerit total_tinggi + rem pace_lambat,
        # bukan KUNING — v17: KUNING via 7 demerit; v18 hanya 1
        # demerit karena tail_fragility hilang di garis equilibrium
        # U258,5 — REVISI KOORDINATOR).
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
        self.assertEqual(hasil["vonis"], "hijau")
        self.assertEqual(hasil["indikator"]["demerit"], ["total_tinggi"])
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
        # data cedera) harus cocok. Pace kandang fixture 94,54 < 100,5
        # tapi pace tandang 101,22 >= 100,5 -> kondisi pace menyala.
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

    def test_mara_bukan_pemicu_okc_parsial(self):
        # Regresi klaim TIDAK TERVERIFIKASI "Aday Mara OUT": Mara
        # adalah pemimpin blok OKC yang MAIN. v18: veto OKC TIDAK
        # menyala (garis 231,5 < 232,0 — hanya pace) -> peringatan
        # parsial; Holmgren tetap OUT_terkonfirmasi.
        veto = vonis_mod.evaluasi_veto(self.verif["OKC@MIA_2026-11-22"], CFG)
        self.assertTrue(veto["dievaluasi"])
        self.assertFalse(veto["menyala"])
        self.assertTrue(veto["peringatan_parsial"])
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
        # v18.1: baseline fixture MENENGAH_HIJAU (2 demerit gap +
        # tail); veto tetap tercatat tidak_dinilai.
        self.assertEqual(hasil["vonis"], "menengah_hijau")
        self.assertIn("veto_rim_protector", hasil["indikator"]["tidak_dinilai"])


class TestKomposerVonis(unittest.TestCase):
    """Wiring komposer: KUNING/TUNGGU dikeluarkan; vonis dibawa kandidat."""

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

    def test_okc_verif_tunggu_dikeluarkan_kedua_tiket(self):
        # OKC verif (TUNGGU_LINEUP, Giannis) dikeluarkan dari kedua
        # tiket dengan alasan timing gate (bukan veto — v17).
        analisis = self._ok(self.verif["OKC@MIA_2026-11-22"])
        kandidat, coret = ticket_composer_mod._kumpulkan_kandidat(
            {analisis["match_id"]: analisis}, {}, CFG
        )
        self.assertEqual(kandidat["insurance"], [])
        self.assertEqual(kandidat["main"], [])
        for tiket in ("insurance", "main"):
            self.assertTrue(
                any("TUNGGU_LINEUP" in c for c in coret[tiket]),
                coret[tiket],
            )
            self.assertTrue(
                any("Giannis Antetokounmpo" in c for c in coret[tiket]),
                coret[tiket],
            )

    def test_den_verif_dikeluarkan_veto_bila_skip_dimatikan(self):
        # DEN verif biasanya sudah kena skip_awal (pola Denver +
        # tidak ada equilibrium) sebelum vonis; dengan skip dimatikan,
        # veto yang mengeluarkannya.
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

    def test_kandidat_membawa_vonis_hijau(self):
        # DET live (HIJAU, lolos skip_awal) jadi kandidat kedua tiket
        # dengan vonis hijau + alasan.
        analisis = self._ok(self.live["DET@ATL_2026-11-22"])
        kandidat, _coret = ticket_composer_mod._kumpulkan_kandidat(
            {analisis["match_id"]: analisis}, {}, CFG
        )
        self.assertEqual(len(kandidat["insurance"]), 1)
        self.assertEqual(len(kandidat["main"]), 1)
        for tiket in ("insurance", "main"):
            kand = kandidat[tiket][0]
            self.assertEqual(kand["vonis"], "hijau")
            self.assertIsInstance(kand["vonis_alasan"], list)
            self.assertGreater(len(kand["vonis_alasan"]), 0)

    def test_vonis_dimatikan_tidak_ada_coret_vonis(self):
        cfg = copy.deepcopy(CFG)
        cfg["vonis"]["enabled"] = False
        analisis = self._ok(self.live["DET@ATL_2026-11-22"])
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
        # (menonjol, bukan terkubur) — demerit pertama v18 adalah
        # "total tinggi" (tail_fragility hilang di garis equilibrium
        # U258,5 — revisi koordinator; v17: "edge kecil" — demerit
        # itu dihapus).
        bagian_vonis = teks[teks.index("Vonis laga") :]
        self.assertLess(
            bagian_vonis.index("VETO — LAGA INI DIBLOKIR"),
            bagian_vonis.index("total tinggi"),
        )
        # Cedera (bagian Kabar pemain) tampil sebelum Vonis.
        self.assertLess(teks.index("Kabar pemain"), teks.index("Vonis laga"))

    def test_dal_live_hijau(self):
        teks = nba_report_mod.render_nba_report(
            copy.deepcopy(self.live["DAL@UTA_2026-11-22"])
        )
        self.assertIn("Vonis: HIJAU", teks)
        self.assertNotIn("VETO — LAGA INI DIBLOKIR", teks)

    def test_okc_verif_tunggu_lineup(self):
        teks = nba_report_mod.render_nba_report(
            copy.deepcopy(self.verif["OKC@MIA_2026-11-22"])
        )
        self.assertIn("Vonis: TUNGGU LINEUP", teks)
        self.assertIn("Giannis Antetokounmpo", teks)


class TestConfigDanPemetaan(unittest.TestCase):
    """Kunci config vonis v18 + file pemetaan rim protector CHECK-IN."""

    def test_kunci_vonis_hadir(self):
        vonis = CFG["vonis"]
        for kunci in (
            "enabled",
            "tail_fragility",
            "total_tinggi_points",
            "ekor_gemuk",
            "foul",
            "spread_tipis_max",
            "hijau_max_demerits",
            "menengah_max_demerits",
            "rem_alami",
            "veto",
            "tiga_pa_rate_top10_cutoff",
            "tunggu_lineup",
        ):
            self.assertIn(kunci, vonis, f"vonis.{kunci} hilang dari config")
        self.assertTrue(vonis["enabled"])
        self.assertEqual(vonis["hijau_max_demerits"], 1)
        self.assertEqual(vonis["menengah_max_demerits"], 3)
        self.assertEqual(vonis["total_tinggi_points"], 235.0)
        self.assertEqual(vonis["tail_fragility"]["p_flood_3p_below"], 0.72)
        self.assertEqual(vonis["tail_fragility"]["p_flood_ft_below"], 0.67)
        self.assertEqual(vonis["ekor_gemuk"]["min_offset_points"], 16.0)
        self.assertEqual(vonis["ekor_gemuk"]["max_price_cents"], 80)
        self.assertEqual(vonis["spread_tipis_max"], 3.0)
        self.assertEqual(vonis["veto"]["logic"], "AND")
        self.assertEqual(vonis["veto"]["total_tinggi_points"], 232.0)
        self.assertEqual(vonis["veto"]["pace_tinggi"], 100.5)
        for kunci in (
            "min_games",
            "min_mp_per_game",
            "min_blk_per_game",
            "max_per_team",
            "position_filter",
        ):
            self.assertIn(kunci, vonis["veto"]["rim_protector"])
        self.assertEqual(
            vonis["veto"]["rim_protector"]["position_filter"],
            ["C", "PF", "F-C", "C-F"],
        )
        self.assertEqual(vonis["tunggu_lineup"]["usg_bintang"], 0.24)
        self.assertEqual(vonis["tunggu_lineup"]["bpm_bintang"], 2.0)
        self.assertEqual(vonis["tunggu_lineup"]["mp_min_rotasi"], 10.0)
        self.assertEqual(vonis["tunggu_lineup"]["bpm_min_jalur_usg"], 0.0)

    def test_kunci_v17_dihapus(self):
        vonis = CFG["vonis"]
        for kunci in (
            "edge_hijau_pct",
            "p_setan_hijau",
            "gap_kecil_pct",
            "ekor_jauh_points",
            "ekor_harga_rendah_cents",
            "max_demerit_menengah",
            "veto_total_tinggi_points",
            "veto_pace_tinggi",
            "rim_protector",
        ):
            self.assertNotIn(kunci, vonis, f"vonis.{kunci} harus dihapus di v18")
        self.assertNotIn("min_edge_pct", CFG["tickets"]["insurance"])
        self.assertNotIn("skip_ot_prob", CFG["ot_seleksi"])

    def test_kunci_tiket_dan_eksekusi_v18(self):
        ins = CFG["tickets"]["insurance"]
        self.assertEqual(ins["multiplier_min"], 2.0)
        self.assertEqual(ins["multiplier_max"], 2.5)
        self.assertEqual(ins["min_leg_prob"], 0.82)
        self.assertEqual(ins["flood_3p_min"], 0.70)
        self.assertEqual(ins["flood_ft_min"], 0.65)
        self.assertEqual(ins["max_negative_ev_pct"], -1.0)
        self.assertTrue(ins["must_cover_total_stake"])
        main = CFG["tickets"]["main"]
        self.assertEqual(main["min_leg_prob"], 0.74)
        self.assertEqual(main["max_negative_ev_pct"], -2.0)
        self.assertEqual(main["multiplier_min"], 3.0)
        self.assertEqual(main["multiplier_max"], 5.0)
        self.assertEqual(CFG["execution"]["min_liquidity_multiplier"], 2.0)
        self.assertEqual(CFG["execution"]["liquidity_hard_min_usd"], 25.0)
        self.assertEqual(CFG["execution"]["stake_default_usd"], 15.0)
        self.assertEqual(CFG["ot_seleksi"]["mode"], "empiris")
        self.assertEqual(CFG["ot_seleksi"]["base_rate_ot"], 0.0575)
        self.assertEqual(CFG["ot_seleksi"]["hard_skip_ot_prob"], 0.085)
        self.assertEqual(CFG["meta"]["version"], 18.1)

    def test_file_pemetaan_valid(self):
        self.assertTrue(PEMETAAN.exists(), "file pemetaan CHECK-IN hilang")
        dokumen = json.loads(PEMETAAN.read_text(encoding="utf-8"))
        self.assertEqual(dokumen["format"], "rim_protector")
        self.assertEqual(dokumen["season"], "2026-27")
        self.assertEqual(dokumen["position_source"], "Basketball-Reference")
        # v18.1 (Patch #3): 30 dari 30 tim terpetakan — 9 tim yang
        # kosong di v18 (21/30) kini terisi tier fallback (BLK >=
        # 0,7, top-1 big). Lantai BLK mengikuti tier: primer >= 1,0,
        # fallback >= 0,7.
        self.assertEqual(len(dokumen["teams"]), 30)
        chi = {p["player"]: p for p in dokumen["teams"]["CHI"]}
        self.assertIn("Nic Claxton", chi)
        self.assertEqual(chi["Nic Claxton"]["blk_per_game"], 1.0)
        self.assertEqual(chi["Nic Claxton"]["pos"], "C")
        okc = {p["player"]: p for p in dokumen["teams"]["OKC"]}
        self.assertEqual(okc["Chet Holmgren"]["blk_per_game"], 3.0)
        self.assertEqual(okc["Aday Mara"]["blk_per_game"], 1.7)
        semua = [p["player"] for daftar in dokumen["teams"].values() for p in daftar]
        for guard in ("Cade Cunningham", "Tyrese Haliburton", "Jamal Murray"):
            self.assertNotIn(guard, semua)
        for tim, daftar in dokumen["teams"].items():
            self.assertLessEqual(len(daftar), 2, tim)
            for entri in daftar:
                self.assertIn(entri["pos"], ["C", "PF", "F-C", "C-F"])
                self.assertIn(entri.get("tier"), ("primary", "fallback"))
                lantai_blk = 1.0 if entri["tier"] == "primary" else 0.7
                self.assertGreaterEqual(entri["blk_per_game"], lantai_blk)
                self.assertGreaterEqual(entri["mp_per_game"], 18.0)
                self.assertGreaterEqual(entri["games_played"], 3)


if __name__ == "__main__":
    unittest.main()
