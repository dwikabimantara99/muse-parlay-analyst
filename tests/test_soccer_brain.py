"""Tes ingest/soccer_brain — SEMUA offline.

fetch_pl_results + check_espn_soccer_injuries di-stub
(unittest.mock); hitung_attack_defence, parse_pl_results, dan
_baca_bobot dipakai ASLI. Nilai harapan dihitung tangan di tes ini
(arimatika independen, bukan memanggil kode yang dites).
"""

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from ingest import soccer_brain as sb_mod
from ingest.common import FetchResult, now_iso

REPO_ROOT = Path(__file__).resolve().parent.parent
CFG = config_mod.load_playstyle()

LIV = "Liverpool"
MUN = "Manchester United"
ARS = "Arsenal"
CHE = "Chelsea"
TANGGAL = "2026-11-22"

BOBOT = {"season": 0.6, "recent": 0.4, "recent_matches": 6}


def _hasil(tanggal, home, away, hg, ag, pekan=11):
    """Satu entri hasil kontrak parse_pl_results."""
    return {
        "home_team": home,
        "away_team": away,
        "kickoff": f"{tanggal}T15:00:00+00:00",
        "status": "C",
        "matchweek": pekan,
        "home_goals": float(hg),
        "away_goals": float(ag),
        "season_label": "English Premier League Season 2026/2027",
    }


# 5 hasil (setiap tim <= 6 laga -> laju musim == laju 6 terakhir).
# Total gol 11 dari 5 laga -> rata-rata liga 11/(2*5) = 1,1.
HASIL_5 = [
    _hasil("2026-11-07", LIV, ARS, 2, 0),
    _hasil("2026-11-08", MUN, CHE, 1, 1),
    _hasil("2026-11-14", ARS, CHE, 3, 1),
    _hasil("2026-11-15", MUN, LIV, 0, 2),
    _hasil("2026-11-21", CHE, LIV, 1, 0),
]

# 4 hasil awal musim untuk Liverpool (total 7 laga -> uji jendela 6).
HASIL_AWAL = [
    _hasil("2026-08-16", LIV, CHE, 4, 0, pekan=1),
    _hasil("2026-08-23", ARS, LIV, 0, 0, pekan=2),
    _hasil("2026-08-30", LIV, MUN, 1, 1, pekan=3),
    _hasil("2026-09-12", CHE, LIV, 2, 2, pekan=4),
]

HASIL_9 = HASIL_AWAL + HASIL_5

FIXTURE_TARGET = {
    "home_team": LIV,
    "away_team": MUN,
    "kickoff": "2026-11-22T16:30:00+00:00",
    "status": "U",
    "matchweek": 11,
    "home_goals": None,
    "away_goals": None,
    "season_label": "English Premier League Season 2026/2027",
}


def _ok(source, tier, data):
    return FetchResult(
        source=source, tier=tier, fetched_at=now_iso(), ok=True, data=data
    )


def _fail(source, tier, error):
    return FetchResult(
        source=source, tier=tier, fetched_at=now_iso(), ok=False, error=error
    )


class TestParsePlResults(unittest.TestCase):
    def test_parse_dengan_skor(self):
        payload = {
            "content": [
                {
                    "teams": [
                        {"team": {"name": "Liverpool"}, "score": 2.0},
                        {"team": {"name": "Arsenal"}, "score": 0.0},
                    ],
                    "kickoff": {"millis": 1763568000000.0},
                    "status": "C",
                    "gameweek": {
                        "gameweek": 11,
                        "compSeason": {
                            "label": "English Premier League Season 2026/2027"
                        },
                    },
                },
                {
                    "teams": [
                        {"team": {"name": "Liverpool"}},
                        {"team": {"name": "Manchester United"}},
                    ],
                    "kickoff": {"millis": 1763829000000.0},
                    "status": "U",
                    "gameweek": {"gameweek": 11, "compSeason": {}},
                },
                {"teams": [{"team": {"name": "Solo"}}]},  # dilewati
            ]
        }
        hasil = sb_mod.parse_pl_results(payload)
        self.assertEqual(len(hasil), 2)
        self.assertEqual(hasil[0]["home_goals"], 2.0)
        self.assertEqual(hasil[0]["away_goals"], 0.0)
        self.assertEqual(hasil[0]["status"], "C")
        self.assertEqual(
            hasil[0]["season_label"], "English Premier League Season 2026/2027"
        )
        self.assertIsNone(hasil[1]["home_goals"])
        self.assertIsNone(hasil[1]["away_goals"])
        self.assertEqual(hasil[1]["status"], "U")

    def test_parse_bukan_dict(self):
        self.assertEqual(sb_mod.parse_pl_results(None), [])
        self.assertEqual(sb_mod.parse_pl_results({"content": None}), [])


class TestBacaBobot(unittest.TestCase):
    def test_dari_config_asli(self):
        params, sumber = sb_mod._baca_bobot(CFG)
        self.assertEqual(sumber, "config")
        self.assertEqual(params["season"], 0.6)
        self.assertEqual(params["recent"], 0.4)
        self.assertEqual(params["recent_matches"], 6)
        self.assertEqual(params["results_window_days"], 150)

    def test_default_bila_kunci_hilang(self):
        params, sumber = sb_mod._baca_bobot({})
        self.assertEqual(sumber, "default")
        self.assertEqual(params["season"], 0.6)
        self.assertEqual(params["results_window_days"], 150)

    def test_bobot_tidak_valid(self):
        cfg = {"simulation": {"football": {"xg_weight_season": 1.5}}}
        with self.assertRaises(ValueError):
            sb_mod._baca_bobot(cfg)
        cfg = {"simulation": {"football": {"recent_matches": 0}}}
        with self.assertRaises(ValueError):
            sb_mod._baca_bobot(cfg)
        cfg = {
            "simulation": {
                "football": {"xg_weight_season": 0.0, "xg_weight_recent": 0.0}
            }
        }
        with self.assertRaises(ValueError):
            sb_mod._baca_bobot(cfg)


class TestLaju(unittest.TestCase):
    def test_campuran_60_40(self):
        musim = {
            "goals_for_per_match": 2.0,
            "goals_against_per_match": 1.0,
        }
        terakhir = {
            "goals_for_per_match": 1.0,
            "goals_against_per_match": 2.0,
        }
        laju_gol, laju_kebobolan = sb_mod._laju(musim, terakhir, BOBOT)
        self.assertAlmostEqual(laju_gol, 0.6 * 2.0 + 0.4 * 1.0)
        self.assertAlmostEqual(laju_kebobolan, 0.6 * 1.0 + 0.4 * 2.0)

    def test_satu_sisi_hilang(self):
        musim = {"goals_for_per_match": None, "goals_against_per_match": None}
        terakhir = {"goals_for_per_match": 1.5, "goals_against_per_match": 0.5}
        laju_gol, laju_kebobolan = sb_mod._laju(musim, terakhir, BOBOT)
        self.assertEqual(laju_gol, 1.5)
        self.assertEqual(laju_kebobolan, 0.5)
        laju_gol, laju_kebobolan = sb_mod._laju(musim, musim, BOBOT)
        self.assertIsNone(laju_gol)
        self.assertIsNone(laju_kebobolan)


class TestHitungAttackDefence(unittest.TestCase):
    def test_rumus_dan_normalisasi(self):
        # Hitung tangan (independen): rata-rata liga 1,1.
        # LIV: GF 4/3, GA 1/3. MUN: GF 0,5, GA 1,5.
        # ARS: GF 1,5, GA 1,5. CHE: GF 1,0, GA 4/3.
        # defence = KEBOCORAN (Dixon-Coles): laju kebobolan /
        # rata-rata liga — tim yang paling sedikit kebobolan (LIV)
        # mendapat defence TERKECIL.
        rata = 11.0 / 10.0
        attack_mentah = {
            LIV: (4.0 / 3.0) / rata,
            MUN: 0.5 / rata,
            ARS: 1.5 / rata,
            CHE: 1.0 / rata,
        }
        defence_mentah = {
            LIV: (1.0 / 3.0) / rata,
            MUN: 1.5 / rata,
            ARS: 1.5 / rata,
            CHE: (4.0 / 3.0) / rata,
        }
        rata_a = sum(attack_mentah.values()) / 4
        rata_d = sum(defence_mentah.values()) / 4
        hasil = sb_mod.hitung_attack_defence(HASIL_5, [LIV, MUN, ARS, CHE], BOBOT)
        for tim in (LIV, MUN, ARS, CHE):
            self.assertAlmostEqual(
                hasil[tim]["attack"], attack_mentah[tim] / rata_a, places=6, msg=tim
            )
            self.assertAlmostEqual(
                hasil[tim]["defence"],
                defence_mentah[tim] / rata_d,
                places=6,
                msg=tim,
            )
            self.assertIsNone(hasil[tim]["alasan"])
        # Rata-rata ternormalisasi = 1 persis.
        mean_a = sum(hasil[t]["attack"] for t in (LIV, MUN, ARS, CHE)) / 4
        mean_d = sum(hasil[t]["defence"] for t in (LIV, MUN, ARS, CHE)) / 4
        self.assertAlmostEqual(mean_a, 1.0, places=9)
        self.assertAlmostEqual(mean_d, 1.0, places=9)
        # Konvensi kebocoran: LIV paling sedikit kebobolan -> defence
        # terkecil (< 1); MUN/ARS paling banyak kebobolan -> > 1.
        self.assertLess(hasil[LIV]["defence"], 1.0)
        self.assertGreater(hasil[MUN]["defence"], 1.0)
        self.assertGreater(hasil[ARS]["defence"], 1.0)

    def test_tanpa_kebobolan_defence_nol(self):
        # Tim yang belum pernah kebobolan: defence 0,0 (nilai sah —
        # kebocoran nol), BUKAN None; simetris dengan attack 0,0.
        hasil = [_hasil("2026-11-07", LIV, ARS, 2, 0)]
        out = sb_mod.hitung_attack_defence(hasil, [LIV, ARS], BOBOT)
        self.assertEqual(out[LIV]["defence"], 0.0)
        self.assertIsNone(out[LIV]["alasan"])
        self.assertIsNotNone(out[LIV]["attack"])
        # ARS kebobolan 2 gol dalam 1 laga: defence mentah 2,0,
        # rata-rata (0,0 + 2,0)/2 = 1,0 -> ternormalisasi 2,0.
        self.assertAlmostEqual(out[ARS]["defence"], 2.0, places=9)

    def test_belum_main(self):
        out = sb_mod.hitung_attack_defence(HASIL_5, ["Tim Fiktif"], BOBOT)
        self.assertIsNone(out["Tim Fiktif"]["attack"])
        self.assertIsNone(out["Tim Fiktif"]["defence"])
        self.assertEqual(out["Tim Fiktif"]["alasan"], "belum_main")

    def test_jendela_6_laga(self):
        # Liverpool 7 laga: 6 terakhir (tanpa 2026-08-16) GF 7, GA 4.
        hasil = sb_mod.hitung_attack_defence(HASIL_9, [LIV], BOBOT)
        # Laju gol LIV = 0,6*(11/7) + 0,4*(7/6); laju kebobolan
        # = 0,6*(4/7) + 0,4*(4/6). attack/defence ternormalisasi
        # terhadap liga (nilai mentah dibagi rata-rata) — di sini
        # hanya LIV yang diminta, tapi normalisasi memakai SEMUA tim
        # di hasil; cukup pastikan nilainya ada + masuk akal.
        self.assertIsNotNone(hasil[LIV]["attack"])
        self.assertIsNotNone(hasil[LIV]["defence"])
        self.assertGreater(hasil[LIV]["attack"], 1.0)
        # LIV hanya kebobolan 4 gol dalam 7 laga -> kebocoran < 1.
        self.assertLess(hasil[LIV]["defence"], 1.0)


class TestBuildTeamBlock(unittest.TestCase):
    def test_statistik_dan_form(self):
        missing: list = []
        attack_defence = sb_mod.hitung_attack_defence(HASIL_9, [LIV], BOBOT)
        blok = sb_mod._build_team_block(
            LIV, "home", HASIL_9, BOBOT, attack_defence, missing
        )
        self.assertEqual(blok["stats_season"]["played"], 7)
        # LIV: W 4 (R1,R4,R6,R8? tidak — R8 seri) -> hitung:
        # menang: R1 (2-0), R4 (2-0), R6 (4-0); seri: R7,R8,R9;
        # kalah: R5. -> 3-3-1.
        self.assertEqual(
            (
                blok["stats_season"]["w"],
                blok["stats_season"]["d"],
                blok["stats_season"]["l"],
            ),
            (3, 3, 1),
        )
        self.assertAlmostEqual(blok["stats_season"]["goals_for_per_match"], 11.0 / 7.0)
        self.assertEqual(blok["stats_last6"]["played"], 6)
        self.assertAlmostEqual(blok["stats_last6"]["goals_for_per_match"], 7.0 / 6.0)
        self.assertEqual(len(blok["form5"]), 5)
        # Form terbaru dulu: R5 (2026-11-21, kalah 0-1).
        self.assertEqual(blok["form5"][0]["result"], "L")
        self.assertEqual(blok["form5"][0]["opponent"], CHE)
        self.assertFalse(blok["form5"][0]["home"])
        # Rekor kandang LIV: R1,R6,R8 -> 2 menang 1 seri.
        self.assertEqual(
            (
                blok["home_record"]["w"],
                blok["home_record"]["d"],
                blok["home_record"]["l"],
            ),
            (2, 1, 0),
        )
        self.assertEqual(blok["injuries"], [])

    def test_hasil_none(self):
        missing: list = []
        blok = sb_mod._build_team_block(LIV, "home", None, BOBOT, None, missing)
        self.assertIsNone(blok["stats_season"]["goals_for_per_match"])
        self.assertIsNone(blok["attack"])
        self.assertIn("home.stats_season", missing)
        self.assertIn("home.attack", missing)


class TestMusimDariLabel(unittest.TestCase):
    def test_label(self):
        self.assertEqual(
            sb_mod._musim_dari_label(
                "English Premier League Season 2026/2027", date(2026, 11, 22)
            ),
            "2026-27",
        )

    def test_fallback_tanggal(self):
        self.assertEqual(sb_mod._musim_dari_label(None, date(2026, 11, 22)), "2026-27")
        self.assertEqual(sb_mod._musim_dari_label(None, date(2027, 3, 1)), "2026-27")
        self.assertEqual(sb_mod._musim_dari_label(None, date(2027, 8, 15)), "2027-28")


class TestFetchMatchInputs(unittest.TestCase):
    def _stub_pl_ok(self):
        return _ok("Premier League (JSON resmi)", 1, HASIL_9 + [FIXTURE_TARGET])

    def _stub_espn_kosong(self):
        return _ok("ESPN", 2, [])

    def test_jalur_bahagia(self):
        with (
            mock.patch.object(
                sb_mod, "fetch_pl_results", return_value=self._stub_pl_ok()
            ),
            mock.patch.object(
                sb_mod,
                "check_espn_soccer_injuries",
                return_value=self._stub_espn_kosong(),
            ),
        ):
            hasil = sb_mod.fetch_match_inputs(LIV, MUN, TANGGAL, cfg=CFG)
        self.assertTrue(hasil.ok)
        data = hasil.data
        self.assertEqual(data["match"]["season"], "2026-27")
        self.assertEqual(data["match"]["matchweek"], 11)
        self.assertEqual(data["match"]["kickoff"], "2026-11-22T16:30:00+00:00")
        self.assertEqual(data["home"]["stats_season"]["played"], 7)
        self.assertIsNotNone(data["home"]["attack"])
        self.assertIsNotNone(data["home"]["defence"])
        self.assertIsNotNone(data["away"]["attack"])
        # H2H LIV-MUN: R4 + R8 = 2 pertemuan.
        self.assertEqual(len(data["h2h_last5"]), 2)
        self.assertEqual(data["h2h_last5"][0]["match_date"], "2026-11-15")
        # Liga: 9 laga, total gol = 11 + (4+0+0+0+1+1+2+2) = 21.
        self.assertEqual(data["league"]["n_matches"], 9)
        self.assertAlmostEqual(data["league"]["avg_goals_per_team_match"], 21.0 / 18.0)
        # Cedera: 0 sumber, tidak terkonfirmasi (B2).
        self.assertEqual(data["injuries_status"]["n_sources"], 0)
        self.assertFalse(data["injuries_status"]["confirmed"])
        self.assertIn("injuries_tidak_terkonfirmasi", data["missing"])
        self.assertEqual(data["home"]["injuries"], [])
        # Jejak penyelidikan sumber cedera tercatat.
        sumber_dicek = {e["source"] for e in data["injury_sources_checked"]}
        self.assertIn("ESPN injuries (eng.1)", sumber_dicek)
        self.assertIn("Fantasy Premier League API", sumber_dicek)
        self.assertEqual(data["weights"]["source"], "config")

    def test_cedera_espn_terisi_suatu_hari(self):
        # Bila ESPN suatu hari mengisi daftar cedera, entri relevan
        # masuk blok tim sebagai sumber ke-1 (tetap < 2 -> HOLD).
        entri = [
            {
                "player": "Pemain Cedera",
                "team": "Liverpool",
                "status": "Out",
            },
            {"player": "Pemain Lain", "team": "Arsenal", "status": "Out"},
        ]
        with (
            mock.patch.object(
                sb_mod, "fetch_pl_results", return_value=self._stub_pl_ok()
            ),
            mock.patch.object(
                sb_mod, "check_espn_soccer_injuries", return_value=_ok("ESPN", 2, entri)
            ),
        ):
            hasil = sb_mod.fetch_match_inputs(LIV, MUN, TANGGAL, cfg=CFG)
        data = hasil.data
        self.assertEqual(data["injuries_status"]["n_sources"], 1)
        self.assertFalse(data["injuries_status"]["confirmed"])
        self.assertEqual(len(data["home"]["injuries"]), 1)
        self.assertEqual(data["home"]["injuries"][0]["player"], "Pemain Cedera")
        self.assertEqual(data["away"]["injuries"], [])

    def test_pl_gagal_espn_cadangan(self):
        from ingest import espn as espn_mod

        game = {
            "game_id": "1",
            "home_team": LIV,
            "away_team": MUN,
            "start_time": "2026-11-22T16:30Z",
            "status": "Scheduled",
            "league": "eng.1",
        }
        with (
            mock.patch.object(
                sb_mod,
                "fetch_pl_results",
                return_value=_fail("Premier League (JSON resmi)", 1, "http_500"),
            ),
            mock.patch.object(
                espn_mod, "fetch_scoreboard", return_value=_ok("ESPN", 2, [game])
            ),
            mock.patch.object(
                sb_mod,
                "check_espn_soccer_injuries",
                return_value=self._stub_espn_kosong(),
            ),
        ):
            hasil = sb_mod.fetch_match_inputs(LIV, MUN, TANGGAL, cfg=CFG)
        # Sebagian berhasil: ok=True, fixture ada, statistik hilang.
        self.assertTrue(hasil.ok)
        self.assertEqual(hasil.data["match"]["kickoff"], "2026-11-22T16:30Z")
        self.assertIsNone(hasil.data["home"]["stats_season"]["goals_for_per_match"])
        self.assertIn("home.stats_season", hasil.data["missing"])
        self.assertIn("football_results", hasil.data["missing"])

    def test_semua_gagal(self):
        from ingest import espn as espn_mod

        with (
            mock.patch.object(
                sb_mod,
                "fetch_pl_results",
                return_value=_fail("Premier League (JSON resmi)", 1, "http_500"),
            ),
            mock.patch.object(
                espn_mod,
                "fetch_scoreboard",
                return_value=_fail("ESPN", 2, "http_500"),
            ),
            mock.patch.object(
                sb_mod,
                "check_espn_soccer_injuries",
                return_value=_fail("ESPN", 2, "http_500"),
            ),
        ):
            hasil = sb_mod.fetch_match_inputs(LIV, MUN, TANGGAL, cfg=CFG)
        self.assertFalse(hasil.ok)
        self.assertIn("semua_sumber_gagal", hasil.error)

    def test_liga_tidak_didukung(self):
        hasil = sb_mod.fetch_match_inputs(
            "Real Madrid", "Barcelona", TANGGAL, league="LaLiga", cfg=CFG
        )
        self.assertFalse(hasil.ok)
        self.assertIn("liga_tidak_didukung", hasil.error)

    def test_input_tidak_valid(self):
        hasil = sb_mod.fetch_match_inputs(LIV, LIV, TANGGAL, cfg=CFG)
        self.assertFalse(hasil.ok)
        hasil = sb_mod.fetch_match_inputs(LIV, MUN, "22-11-2026", cfg=CFG)
        self.assertFalse(hasil.ok)
        hasil = sb_mod.fetch_match_inputs("", MUN, TANGGAL, cfg=CFG)
        self.assertFalse(hasil.ok)

    def test_config_bobot_rusak(self):
        cfg = {"simulation": {"football": {"xg_weight_season": 2.0}}}
        with self.assertRaises(ValueError):
            sb_mod.fetch_match_inputs(LIV, MUN, TANGGAL, cfg=cfg)


if __name__ == "__main__":
    unittest.main()
