"""Tes timing gate v18 + parser USG/FTr/3PAr + cutoff FIT liga.

Timing gate (engine/vonis.py::cek_tunggu_lineup): bintang =
pemain QUESTIONABLE dengan USG >= 0,24 ATAU BPM >= +2,0.
BPM dibaca dulu (tanpa fetch); USG ditarik malas (lazy) hanya
untuk pemain Questionable yang belum lolos lewat BPM — bila
fetch gagal -> fallback BPM saja + dicatat.

Kasus wajib artefak: IND@NYK live (Karl-Anthony Towns +
Pascal Siakam Questionable -> tunggu=True).

Parser: ingest/pemain_usg.py (stats.nba.com USG_PCT pecahan +
BBRef usg_pct persen -> pecahan) dan ingest/stats_nba.py
parse_team_base (FTr + 3PAr).

Cutoff FIT: dihitung ulang dari snapshot
out/fit_cutoff_liga_v18.json (n=30 tim, tarikan 2026-11-23) dan
dibandingkan dengan config — snapshot di-skip bila tidak ada.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from unittest import mock

import config
from engine import vonis
from ingest import pemain_usg as pemain_usg_mod
from ingest import stats_nba as stats_nba_mod

CFG = config.load_playstyle()
ROOT = Path(__file__).resolve().parent.parent
ARTEFAK_LIVE = ROOT / "out" / "analysis_live_2026-11-22.json"
SNAPSHOT_CUTOFF = ROOT / "out" / "fit_cutoff_liga_v18.json"


def _analisis(cedera, pemain):
    """Artefak minimal untuk timing gate."""
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


class TestCekTungguLineup(unittest.TestCase):
    """cek_tunggu_lineup pada fixture sintetis."""

    def test_bintang_lewat_bpm_tanpa_fetch(self):
        # KAT: BPM 5,4 >= 2,0 -> bintang tanpa butuh USG. Fetch
        # dipaksa gagal — bila dipanggil, tes ini error.
        analisis = _analisis(
            [_q("Karl-Anthony Towns", "NYK")],
            [_pemain("Karl-Anthony Towns", 5.4, "NYK")],
        )
        with mock.patch.object(
            pemain_usg_mod,
            "fetch_pemain_usg_cached",
            side_effect=RuntimeError("fetch tidak boleh dipanggil"),
        ):
            hasil = vonis.cek_tunggu_lineup(analisis, CFG)
        self.assertTrue(hasil["tunggu"])
        self.assertEqual(len(hasil["bintang"]), 1)
        self.assertEqual(hasil["bintang"][0]["player"], "Karl-Anthony Towns")
        self.assertEqual(hasil["bintang"][0]["bpm"], 5.4)
        self.assertIsNone(hasil["usg_sumber"])

    def test_bintang_lewat_usg_suntik(self):
        # Siakam: BPM 1,42 < 2,0 tapi USG 0,278 >= 0,24 -> bintang.
        analisis = _analisis([_q("Pascal Siakam")], [_pemain("Pascal Siakam", 1.42)])
        hasil = vonis.cek_tunggu_lineup(
            analisis, CFG, usg_pemain={"Pascal Siakam": 0.278}
        )
        self.assertTrue(hasil["tunggu"])
        self.assertEqual(hasil["bintang"][0]["player"], "Pascal Siakam")
        self.assertEqual(hasil["bintang"][0]["usg"], 0.278)
        self.assertEqual(hasil["usg_sumber"], "suntik")

    def test_bintang_lewat_usg_list_entri(self):
        analisis = _analisis([_q("Pascal Siakam")], [_pemain("Pascal Siakam", 1.42)])
        hasil = vonis.cek_tunggu_lineup(
            analisis,
            CFG,
            usg_pemain=[{"player": "Pascal Siakam", "usg_pct": 0.278}],
        )
        self.assertTrue(hasil["tunggu"])
        self.assertEqual(hasil["bintang"][0]["usg"], 0.278)

    def test_bukan_bintang_tidak_tunggu(self):
        # OG Anunoby: BPM 0,38 + USG 0,203 — keduanya di bawah ambang.
        analisis = _analisis(
            [_q("OG Anunoby", "NYK")],
            [_pemain("OG Anunoby", 0.38, "NYK")],
        )
        hasil = vonis.cek_tunggu_lineup(analisis, CFG, usg_pemain={"OG Anunoby": 0.203})
        self.assertFalse(hasil["tunggu"])
        self.assertEqual(hasil["bintang"], [])
        self.assertTrue(hasil["dievaluasi"])

    def test_usg_tinggi_tapi_bukan_rotasi_bukan_bintang(self):
        # Felix Okpara (nyata, ORL@WAS): USG 25,0% tapi hanya 1,67
        # mnt/laga -> bukan rotasi -> bukan bintang.
        analisis = _analisis(
            [_q("Felix Okpara", "WAS")],
            [_pemain("Felix Okpara", -6.7, "WAS", mp=1.67)],
        )
        hasil = vonis.cek_tunggu_lineup(
            analisis, CFG, usg_pemain={"Felix Okpara": 0.25}
        )
        self.assertFalse(hasil["tunggu"])
        self.assertEqual(hasil["diperiksa"][0]["usg_ditolak"], "bukan_rotasi")

    def test_usg_tinggi_tapi_bpm_negatif_bukan_bintang(self):
        # RayJ Dennis (nyata, DET@ATL): USG 26,7%, 11,5 mnt (rotasi)
        # tapi BPM -3,2 (net-negatif) -> bukan bintang.
        analisis = _analisis(
            [_q("RayJ Dennis", "ATL")],
            [_pemain("RayJ Dennis", -3.2, "ATL", mp=11.5)],
        )
        hasil = vonis.cek_tunggu_lineup(
            analisis, CFG, usg_pemain={"RayJ Dennis": 0.267}
        )
        self.assertFalse(hasil["tunggu"])
        self.assertEqual(hasil["diperiksa"][0]["usg_ditolak"], "bpm_negatif")

    def test_usg_tinggi_tanpa_data_menit_tidak_lolos(self):
        # Tanpa mp_per_game di artefak, jalur USG tidak aktif (USG
        # tanpa menit tidak bisa ditafsirkan).
        analisis = _analisis(
            [_q("Tanpa Menit")],
            [{"player": "Tanpa Menit", "bpm": 1.0, "team_tricode": "IND"}],
        )
        hasil = vonis.cek_tunggu_lineup(analisis, CFG, usg_pemain={"Tanpa Menit": 0.28})
        self.assertFalse(hasil["tunggu"])
        self.assertEqual(hasil["diperiksa"][0]["usg_ditolak"], "mp_tidak_ada")

    def test_usg_tinggi_tanpa_bpm_lolos(self):
        # BPM hilang (tidak ada di inputs) -> lantai BPM dilewati
        # (tidak ada bukti negatif); mp rotasi + USG tinggi cukup.
        analisis = _analisis(
            [_q("Tanpa Bpm")],
            [
                {
                    "player": "Tanpa Bpm",
                    "team_tricode": "IND",
                    "mp_per_game": 28.0,
                }
            ],
        )
        hasil = vonis.cek_tunggu_lineup(analisis, CFG, usg_pemain={"Tanpa Bpm": 0.28})
        self.assertTrue(hasil["tunggu"])
        self.assertEqual(hasil["bintang"][0]["player"], "Tanpa Bpm")

    def test_ambang_batas_inklusif(self):
        # USG tepat 0,24 dan BPM tepat +2,0 lolos (>=).
        analisis = _analisis(
            [_q("Pemain Usg"), _q("Pemain Bpm")],
            [_pemain("Pemain Usg", 0.0), _pemain("Pemain Bpm", 2.0)],
        )
        hasil = vonis.cek_tunggu_lineup(analisis, CFG, usg_pemain={"Pemain Usg": 0.24})
        self.assertTrue(hasil["tunggu"])
        self.assertEqual(
            {b["player"] for b in hasil["bintang"]},
            {"Pemain Usg", "Pemain Bpm"},
        )
        # Di bawah ambang sedikit: tidak lolos.
        analisis = _analisis([_q("Pemain Usg")], [_pemain("Pemain Usg", 0.0)])
        hasil = vonis.cek_tunggu_lineup(analisis, CFG, usg_pemain={"Pemain Usg": 0.239})
        self.assertFalse(hasil["tunggu"])

    def test_hanya_questionable_yang_dihitung(self):
        # Bintang OUT / PROBABLE tidak memicu timing gate (OUT
        # sudah pasti tidak main; PROBABLE hampir pasti main).
        analisis = _analisis(
            [
                {"player": "Bintang Out", "status": "OUT", "team_tricode": "IND"},
                {
                    "player": "Bintang Probable",
                    "status": "PROBABLE",
                    "team_tricode": "IND",
                },
            ],
            [_pemain("Bintang Out", 5.0), _pemain("Bintang Probable", 5.0)],
        )
        hasil = vonis.cek_tunggu_lineup(analisis, CFG)
        self.assertFalse(hasil["tunggu"])
        self.assertEqual(hasil["alasan"], ["tidak ada pemain berstatus Questionable"])

    def test_tanpa_data_cedera_tidak_dievaluasi(self):
        analisis = {"format": "nba_analysis", "match_id": "TES@TES_2026-11-22"}
        hasil = vonis.cek_tunggu_lineup(analisis, CFG)
        self.assertFalse(hasil["dievaluasi"])
        self.assertFalse(hasil["tunggu"])

    def test_fetch_gagal_fallback_bpm(self):
        # Fetch USG gagal: bintang BPM tetap terdeteksi, pemain
        # USG-only tidak — dan kegagalan DICATAT (bukan disembunyikan).
        analisis = _analisis(
            [_q("Karl-Anthony Towns", "NYK"), _q("Pascal Siakam")],
            [
                _pemain("Karl-Anthony Towns", 5.4, "NYK"),
                _pemain("Pascal Siakam", 1.42),
            ],
        )
        with mock.patch.object(
            pemain_usg_mod,
            "fetch_pemain_usg_cached",
            side_effect=RuntimeError("jaringan putus"),
        ):
            hasil = vonis.cek_tunggu_lineup(analisis, CFG)
        self.assertTrue(hasil["tunggu"])
        self.assertEqual(
            [b["player"] for b in hasil["bintang"]], ["Karl-Anthony Towns"]
        )
        self.assertEqual(hasil["usg_sumber"], "tidak_tersedia")
        self.assertIn("gagal", hasil["usg_catatan"])
        self.assertTrue(any("fallback BPM" in a for a in hasil["alasan"]))

    def test_ambang_hilang_config_error(self):
        cfg = copy.deepcopy(CFG)
        del cfg["vonis"]["tunggu_lineup"]["usg_bintang"]
        with self.assertRaises(config.ConfigError):
            vonis.cek_tunggu_lineup(_analisis([_q("A")], []), cfg)


class TestPemainUsg(unittest.TestCase):
    """Parser ingest/pemain_usg.py."""

    def test_parse_stats_nba_pecahan(self):
        data = {
            "resultSets": [
                {
                    "headers": ["PLAYER_NAME", "TEAM_ABBREVIATION", "GP", "USG_PCT"],
                    "rowSet": [
                        ["Karl-Anthony Towns", "NYK", 15, 0.252],
                        ["Pascal Siakam", "IND", 16, 0.278],
                    ],
                }
            ]
        }
        pemain = pemain_usg_mod.parse_stats_nba_usg(data)
        self.assertEqual(len(pemain), 2)
        self.assertEqual(pemain[0]["usg_pct"], 0.252)
        self.assertEqual(pemain[0]["source"], "stats.nba.com")
        self.assertEqual(
            pemain_usg_mod.peta_usg(pemain),
            {"Karl-Anthony Towns": 0.252, "Pascal Siakam": 0.278},
        )

    def test_parse_stats_nba_format_berubah(self):
        with self.assertRaises(ValueError):
            pemain_usg_mod.parse_stats_nba_usg({"resultSets": []})
        with self.assertRaises(ValueError):
            pemain_usg_mod.parse_stats_nba_usg(
                {"resultSets": [{"headers": ["PLAYER_NAME"], "rowSet": []}]}
            )

    def test_parse_bbref_persen_jadi_pecahan(self):
        # usg_pct BBRef dalam PERSEN (27,8) -> pecahan (0,278).
        html = """
        <table id="advanced"><tbody>
        <tr><th data-stat="name_display">Pascal Siakam</th>
        <td data-stat="team_name_abbr">IND</td>
        <td data-stat="games">16</td>
        <td data-stat="usg_pct">27.8</td></tr>
        <tr><th data-stat="name_display">Karl-Anthony Towns</th>
        <td data-stat="team_name_abbr">NYK</td>
        <td data-stat="games">15</td>
        <td data-stat="usg_pct">25.2</td></tr>
        </tbody></table>
        """
        pemain = pemain_usg_mod.parse_bbref_usg(html)
        self.assertEqual(len(pemain), 2)
        self.assertEqual(pemain[0]["usg_pct"], 0.278)
        self.assertEqual(pemain[1]["usg_pct"], 0.252)
        self.assertEqual(pemain[0]["source"], "Basketball-Reference")

    def test_parse_bbref_tricode_dipetakan(self):
        html = """
        <table id="advanced"><tbody>
        <tr><th data-stat="name_display">Pemain Nets</th>
        <td data-stat="team_name_abbr">BRK</td>
        <td data-stat="games">10</td>
        <td data-stat="usg_pct">20.0</td></tr>
        </tbody></table>
        """
        pemain = pemain_usg_mod.parse_bbref_usg(html)
        self.assertEqual(pemain[0]["team"], "BKN")

    def test_peta_usg_lewati_none(self):
        pemain = [
            {"player": "Ada", "usg_pct": 0.25},
            {"player": "Tidak Ada", "usg_pct": None},
            {"player": None, "usg_pct": 0.30},
        ]
        self.assertEqual(pemain_usg_mod.peta_usg(pemain), {"Ada": 0.25})


class TestParseTeamBase(unittest.TestCase):
    """ingest/stats_nba.parse_team_base: FTr + 3PAr."""

    def _data(self, baris):
        return {
            "resultSets": [
                {
                    "name": "LeagueDashTeamStats",
                    "headers": ["TEAM_ID", "TEAM_NAME", "FGA", "FTA", "FG3A"],
                    "rowSet": baris,
                }
            ]
        }

    def test_rasio_dihitung(self):
        tim = stats_nba_mod.parse_team_base(
            self._data([[1610612737, "Atlanta Hawks", 96.0, 20.5, 43.3]])
        )
        self.assertEqual(len(tim), 1)
        self.assertAlmostEqual(tim[0]["ftr"], 20.5 / 96.0, places=12)
        self.assertAlmostEqual(tim[0]["tiga_pa_rate"], 43.3 / 96.0, places=12)
        self.assertEqual(tim[0]["tricode"], "ATL")

    def test_fga_nol_rasio_none(self):
        # FGA 0/hilang -> rasio None (bukan 0).
        tim = stats_nba_mod.parse_team_base(
            self._data([[1610612737, "Atlanta Hawks", 0, 20.5, 43.3]])
        )
        self.assertIsNone(tim[0]["ftr"])
        self.assertIsNone(tim[0]["tiga_pa_rate"])

    def test_resultset_hilang_value_error(self):
        with self.assertRaises(ValueError):
            stats_nba_mod.parse_team_base({"resultSets": []})


def _persentil_linear(nilai_urut, q):
    """Persentil interpolasi linear (metode numpy default)."""
    n = len(nilai_urut)
    pos = q * (n - 1)
    bawah = int(pos // 1)
    atas = min(bawah + 1, n - 1)
    fraksi = pos - bawah
    return nilai_urut[bawah] * (1 - fraksi) + nilai_urut[atas] * fraksi


@unittest.skipUnless(
    SNAPSHOT_CUTOFF.exists(),
    "snapshot out/fit_cutoff_liga_v18.json tidak ada (runtime)",
)
class TestCutoffFitLiga(unittest.TestCase):
    """Cutoff FIT liga: hitung ulang dari snapshot vs config."""

    @classmethod
    def setUpClass(cls):
        cls.snap = json.loads(SNAPSHOT_CUTOFF.read_text(encoding="utf-8"))
        cls.tim = list(cls.snap["teams"].values())

    def test_provenance_snapshot(self):
        self.assertEqual(self.snap["n_teams"], 30)
        self.assertEqual(len(self.tim), 30)
        self.assertEqual(self.snap["season"], "2026-27")
        self.assertIsNotNone(self.snap["fetched_at"])
        for entri in self.tim:
            for kunci in ("def_rtg", "pace", "ftr", "tiga_pa_rate"):
                self.assertIsNotNone(entri[kunci], (entri, kunci))

    def test_drtg_top10_cutoff(self):
        # Top-10 = 10 nilai DRtg terkecil; cutoff = nilai ke-10.
        drtg = sorted(t["def_rtg"] for t in self.tim)
        self.assertEqual(drtg[9], 112.9)
        self.assertEqual(CFG["vonis"]["rem_alami"]["drtg_top10_cutoff"], 112.9)

    def test_pace_bottom12_cutoff(self):
        # Bottom-12 = 12 nilai pace terkecil (pace lambat = angka
        # kecil); cutoff = nilai ke-12.
        pace = sorted(t["pace"] for t in self.tim)
        self.assertEqual(pace[11], 98.91)
        self.assertEqual(CFG["vonis"]["rem_alami"]["pace_bottom12_cutoff"], 98.91)

    def test_ftr_p80_p50(self):
        ftr = sorted(t["ftr"] for t in self.tim)
        p80 = _persentil_linear(ftr, 0.80)
        p50 = _persentil_linear(ftr, 0.50)
        self.assertAlmostEqual(p80, 0.308111, places=6)
        self.assertAlmostEqual(p50, 0.274398, places=6)
        self.assertAlmostEqual(CFG["vonis"]["foul"]["ftr_p80"], p80, places=6)
        self.assertAlmostEqual(CFG["vonis"]["foul"]["ftr_p50"], p50, places=6)

    def test_tiga_par_top10_cutoff(self):
        # Top-10 = 10 nilai 3PAr terbesar; cutoff = nilai ke-10.
        tiga_par = sorted(t["tiga_pa_rate"] for t in self.tim)
        self.assertAlmostEqual(tiga_par[-10], 0.457207, places=6)
        self.assertAlmostEqual(
            CFG["vonis"]["tiga_pa_rate_top10_cutoff"],
            tiga_par[-10],
            places=6,
        )

    def test_snapshot_cutoff_cocok_hitung_ulang(self):
        cutoff = self.snap["cutoff"]
        ftr = sorted(t["ftr"] for t in self.tim)
        self.assertAlmostEqual(
            cutoff["ftr_p80"], _persentil_linear(ftr, 0.80), places=12
        )
        self.assertAlmostEqual(
            cutoff["ftr_p50"], _persentil_linear(ftr, 0.50), places=12
        )


@unittest.skipUnless(
    ARTEFAK_LIVE.exists(),
    "artefak out/analysis_live_2026-11-22.json tidak ada (runtime)",
)
class TestArtefakNyata(unittest.TestCase):
    """Kasus wajib timing gate di artefak live 22 Nov."""

    @classmethod
    def setUpClass(cls):
        data = json.loads(ARTEFAK_LIVE.read_text(encoding="utf-8"))
        cls.live = {
            (m.get("nba_analysis") or {}).get("match_id"): m.get("nba_analysis") or {}
            for m in data.get("matches") or []
        }

    def test_ind_nyk_tunggu_lewat_bpm(self):
        # KASUS WAJIB: IND@NYK -> tunggu=True. KAT (BPM 5,4)
        # terdeteksi lewat BPM; Siakam (BPM 1,42) lewat USG 0,278.
        # USG disuntik (deterministik) — fetch live tidak dipakai
        # di tes unit; fetch live sudah diverifikasi manual
        # 2026-11-23 (474 pemain, stats.nba.com).
        analisis = self.live["IND@NYK_2026-11-22"]
        hasil = vonis.cek_tunggu_lineup(
            analisis,
            CFG,
            usg_pemain={
                "Pascal Siakam": 0.278,
                "OG Anunoby": 0.203,
                "Jordan Clarkson": 0.20,
            },
        )
        self.assertTrue(hasil["tunggu"])
        nama_bintang = {b["player"] for b in hasil["bintang"]}
        self.assertIn("Karl-Anthony Towns", nama_bintang)
        self.assertIn("Pascal Siakam", nama_bintang)
        self.assertNotIn("OG Anunoby", nama_bintang)
        self.assertNotIn("Jordan Clarkson", nama_bintang)

    def test_ind_nyk_kat_saja_tanpa_usg(self):
        # Dengan USG kosong (tidak ada data USG), KAT tetap
        # membuat tunggu=True lewat BPM — gate tidak buta total
        # saat data USG hilang.
        analisis = self.live["IND@NYK_2026-11-22"]
        hasil = vonis.cek_tunggu_lineup(analisis, CFG, usg_pemain={})
        self.assertTrue(hasil["tunggu"])
        self.assertEqual(
            [b["player"] for b in hasil["bintang"]],
            ["Karl-Anthony Towns"],
        )

    def test_det_tidak_tunggu_pemain_pinggiran(self):
        # KUALIFIKASI JALUR USG (nyata): RayJ Dennis ATL Questionable
        # dengan USG 26,7% — tapi BPM -3,2 -> bukan bintang, DET
        # tidak tunggu_lineup. USG disuntik (deterministik).
        analisis = self.live["DET@ATL_2026-11-22"]
        hasil = vonis.cek_tunggu_lineup(
            analisis, CFG, usg_pemain={"RayJ Dennis": 0.267}
        )
        self.assertFalse(hasil["tunggu"])
        self.assertEqual(hasil["bintang"], [])
        diperiksa = {d["player"]: d for d in hasil["diperiksa"]}
        self.assertEqual(diperiksa["RayJ Dennis"]["usg_ditolak"], "bpm_negatif")

    def test_orl_tidak_tunggu_pemain_pinggiran(self):
        # KUALIFIKASI JALUR USG (nyata): Felix Okpara WAS Questionable
        # dengan USG 25,0% — tapi hanya 1,67 mnt/laga -> bukan
        # rotasi -> bukan bintang, ORL tidak tunggu_lineup.
        analisis = self.live["ORL@WAS_2026-11-22"]
        hasil = vonis.cek_tunggu_lineup(
            analisis, CFG, usg_pemain={"Felix Okpara": 0.25}
        )
        self.assertFalse(hasil["tunggu"])
        self.assertEqual(hasil["bintang"], [])
        diperiksa = {d["player"]: d for d in hasil["diperiksa"]}
        self.assertEqual(diperiksa["Felix Okpara"]["usg_ditolak"], "bukan_rotasi")


if __name__ == "__main__":
    unittest.main()
