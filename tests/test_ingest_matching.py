"""Tes ingest/matching.py — normalisasi + pencocokan nama tim (murni).

TANPA network. Kasus diambil dari probe kalshi_sports (nama Kalshi vs
jup.ag yang teramati di slate).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import matching


class TestNormalizeTeam(unittest.TestCase):
    def test_buang_kata_pengisi(self):
        self.assertEqual(matching.normalize_team("Chelsea FC", "football"), "chelsea")
        self.assertEqual(
            matching.normalize_team("AFC Bournemouth", "football"), "bournemouth"
        )
        self.assertEqual(
            matching.normalize_team("Newcastle United FC", "football"), "newcastle"
        )
        self.assertEqual(
            matching.normalize_team("RC Celta de Vigo", "football"), "celta vigo"
        )
        self.assertEqual(
            matching.normalize_team("Manchester City FC", "football"),
            "manchester city",
        )
        self.assertEqual(
            matching.normalize_team("Sunderland AFC", "football"), "sunderland"
        )

    def test_nba_julukan_ke_kota(self):
        self.assertEqual(matching.normalize_team("Hornets", "nba"), "charlotte")
        self.assertEqual(matching.normalize_team("Lakers", "nba"), "los angeles l")
        self.assertEqual(matching.normalize_team("Clippers", "nba"), "los angeles c")
        self.assertEqual(matching.normalize_team("Trail Blazers", "nba"), "portland")
        self.assertEqual(matching.normalize_team("76ers", "nba"), "philadelphia")
        self.assertEqual(matching.normalize_team("Spurs", "nba"), "san antonio")
        # Nama kota dibiarkan apa adanya.
        self.assertEqual(matching.normalize_team("Chicago", "nba"), "chicago")

    def test_nba_30_tim_terpetakan(self):
        self.assertEqual(len(matching.NBA_NICKNAME_TO_CITY), 30)
        self.assertEqual(len(matching.NBA_TRICODE_TO_CITY), 30)

    def test_nba_tricode_ke_kota(self):
        # Rotowire menulis tricode ("LAL"); tricode terverifikasi di
        # stats_nba.TEAM_TRICODES.
        self.assertEqual(matching.normalize_team("LAL", "nba"), "los angeles l")
        self.assertEqual(matching.normalize_team("LAC", "nba"), "los angeles c")
        self.assertEqual(matching.normalize_team("GSW", "nba"), "golden state")
        self.assertEqual(matching.normalize_team("BKN", "nba"), "brooklyn")
        self.assertEqual(matching.normalize_team("CHA", "nba"), "charlotte")
        self.assertEqual(matching.normalize_team("NOP", "nba"), "new orleans")
        self.assertEqual(matching.normalize_team("NYK", "nba"), "new york")

    def test_nba_nama_lengkap_ke_kota(self):
        # stats.nba.com / ESPN / PDF cedera / BBRef menulis nama lengkap.
        self.assertEqual(
            matching.normalize_team("Los Angeles Lakers", "nba"), "los angeles l"
        )
        self.assertEqual(matching.normalize_team("LA Clippers", "nba"), "los angeles c")
        self.assertEqual(
            matching.normalize_team("Los Angeles Clippers", "nba"),
            "los angeles c",
        )
        self.assertEqual(
            matching.normalize_team("Golden State Warriors", "nba"), "golden state"
        )
        self.assertEqual(
            matching.normalize_team("Portland Trail Blazers", "nba"), "portland"
        )
        self.assertEqual(
            matching.normalize_team("Philadelphia 76ers", "nba"), "philadelphia"
        )
        self.assertEqual(
            matching.normalize_team("Oklahoma City Thunder", "nba"), "oklahoma city"
        )
        self.assertEqual(
            matching.normalize_team("New Orleans Pelicans", "nba"), "new orleans"
        )

    def test_nba_ketiga_bentuk_satu_kanonik(self):
        # 30 tim: nama lengkap + julukan + tricode -> kota kanonik yang sama.
        teams = [
            ("Atlanta Hawks", "Hawks", "ATL", "atlanta"),
            ("Boston Celtics", "Celtics", "BOS", "boston"),
            ("Brooklyn Nets", "Nets", "BKN", "brooklyn"),
            ("Charlotte Hornets", "Hornets", "CHA", "charlotte"),
            ("Chicago Bulls", "Bulls", "CHI", "chicago"),
            ("Cleveland Cavaliers", "Cavaliers", "CLE", "cleveland"),
            ("Dallas Mavericks", "Mavericks", "DAL", "dallas"),
            ("Denver Nuggets", "Nuggets", "DEN", "denver"),
            ("Detroit Pistons", "Pistons", "DET", "detroit"),
            ("Golden State Warriors", "Warriors", "GSW", "golden state"),
            ("Houston Rockets", "Rockets", "HOU", "houston"),
            ("Indiana Pacers", "Pacers", "IND", "indiana"),
            ("LA Clippers", "Clippers", "LAC", "los angeles c"),
            ("Los Angeles Lakers", "Lakers", "LAL", "los angeles l"),
            ("Memphis Grizzlies", "Grizzlies", "MEM", "memphis"),
            ("Miami Heat", "Heat", "MIA", "miami"),
            ("Milwaukee Bucks", "Bucks", "MIL", "milwaukee"),
            ("Minnesota Timberwolves", "Timberwolves", "MIN", "minnesota"),
            ("New Orleans Pelicans", "Pelicans", "NOP", "new orleans"),
            ("New York Knicks", "Knicks", "NYK", "new york"),
            ("Oklahoma City Thunder", "Thunder", "OKC", "oklahoma city"),
            ("Orlando Magic", "Magic", "ORL", "orlando"),
            ("Philadelphia 76ers", "76ers", "PHI", "philadelphia"),
            ("Phoenix Suns", "Suns", "PHX", "phoenix"),
            ("Portland Trail Blazers", "Trail Blazers", "POR", "portland"),
            ("Sacramento Kings", "Kings", "SAC", "sacramento"),
            ("San Antonio Spurs", "Spurs", "SAS", "san antonio"),
            ("Toronto Raptors", "Raptors", "TOR", "toronto"),
            ("Utah Jazz", "Jazz", "UTA", "utah"),
            ("Washington Wizards", "Wizards", "WAS", "washington"),
        ]
        self.assertEqual(len(teams), 30)
        for full, nickname, tricode, city in teams:
            with self.subTest(team=full):
                self.assertEqual(matching.normalize_team(full, "nba"), city)
                self.assertEqual(matching.normalize_team(nickname, "nba"), city)
                self.assertEqual(matching.normalize_team(tricode, "nba"), city)

    def test_bola_alias_teramati(self):
        self.assertEqual(matching.normalize_team("Athletic Club", "football"), "bilbao")
        self.assertEqual(
            matching.normalize_team("RCD Espanyol de Barcelona", "football"),
            "espanyol",
        )

    def test_spurs_tidak_dipetakan_di_bola(self):
        # "Spurs" juga nama Tottenham — pemetaan julukan NBA HANYA untuk NBA.
        # Di bola, "Spurs"/"Tottenham" dipetakan ke nama lengkap Tottenham.
        self.assertEqual(
            matching.normalize_team("Spurs", "football"), "tottenham hotspur"
        )
        self.assertEqual(
            matching.normalize_team("Tottenham", "football"), "tottenham hotspur"
        )

    def test_bola_bentuk_pendek_fpl(self):
        # Bentuk pendek FPL (terverifikasi live 2026-11-20) -> nama lengkap.
        self.assertEqual(
            matching.normalize_team("Man City", "football"), "manchester city"
        )
        self.assertEqual(matching.normalize_team("Man Utd", "football"), "manchester")
        self.assertEqual(
            matching.normalize_team("Nott'm Forest", "football"),
            "nottingham forest",
        )
        self.assertEqual(
            matching.normalize_team("Brighton", "football"), "brighton hove albion"
        )
        # "and" dibuang: Odds API "Brighton and Hove Albion" = ESPN
        # "Brighton & Hove Albion".
        self.assertEqual(
            matching.normalize_team("Brighton and Hove Albion", "football"),
            "brighton hove albion",
        )
        self.assertEqual(
            matching.normalize_team("Brighton & Hove Albion", "football"),
            "brighton hove albion",
        )

    def test_sport_lain_normalisasi_dasar(self):
        self.assertEqual(matching.normalize_team("Hornets", "other"), "hornets")
        self.assertEqual(matching.normalize_team("Chelsea FC", "other"), "chelsea")

    def test_bukan_string(self):
        self.assertEqual(matching.normalize_team(None, "nba"), "")
        self.assertEqual(matching.normalize_team(123, "nba"), "")


class TestTeamsMatch(unittest.TestCase):
    def test_cocok_lintas_sumber(self):
        self.assertTrue(matching.teams_match("Hornets", "Charlotte", "nba"))
        self.assertTrue(matching.teams_match("Lakers", "Los Angeles L", "nba"))
        self.assertTrue(
            matching.teams_match("Newcastle United FC", "Newcastle", "football")
        )
        self.assertTrue(matching.teams_match("Athletic Club", "Bilbao", "football"))

    def test_cocok_lintas_bentuk_nba(self):
        # Julukan vs nama lengkap vs tricode: semua bentuk sumber 2b.
        self.assertTrue(matching.teams_match("LAL", "Los Angeles Lakers", "nba"))
        self.assertTrue(matching.teams_match("Lakers", "Los Angeles Lakers", "nba"))
        self.assertTrue(matching.teams_match("GSW", "Golden State Warriors", "nba"))
        self.assertTrue(matching.teams_match("LAC", "LA Clippers", "nba"))
        self.assertTrue(
            matching.teams_match("Trail Blazers", "Portland Trail Blazers", "nba")
        )

    def test_cocok_bentuk_pendek_fpl_dengan_nama_lengkap(self):
        self.assertTrue(matching.teams_match("Man City", "Manchester City", "football"))
        self.assertTrue(
            matching.teams_match("Man Utd", "Manchester United", "football")
        )
        self.assertTrue(matching.teams_match("Spurs", "Tottenham Hotspur", "football"))
        self.assertTrue(
            matching.teams_match("Nott'm Forest", "Nottingham Forest", "football")
        )
        self.assertTrue(
            matching.teams_match("Brighton", "Brighton & Hove Albion", "football")
        )
        self.assertTrue(matching.teams_match("Leeds", "Leeds United", "football"))
        self.assertTrue(
            matching.teams_match("Newcastle", "Newcastle United", "football")
        )

    def test_tidak_cocok(self):
        self.assertFalse(matching.teams_match("Hornets", "Atlanta", "nba"))
        self.assertFalse(matching.teams_match("Lakers", "Clippers", "nba"))
        self.assertFalse(matching.teams_match("LAL", "LA Clippers", "nba"))
        self.assertFalse(matching.teams_match("LAL", "Los Angeles Clippers", "nba"))
        self.assertFalse(
            matching.teams_match("Man City", "Manchester United", "football")
        )
        self.assertFalse(matching.teams_match("Brighton", "Brentford", "football"))

    def test_kosong_tidak_pernah_cocok(self):
        self.assertFalse(matching.teams_match("", "", "nba"))
        self.assertFalse(matching.teams_match("Hornets", "", "nba"))


class TestParseVsTitle(unittest.TestCase):
    def test_format_vs(self):
        self.assertEqual(
            matching.parse_vs_title("Wizards vs. Bulls"), ("Wizards", "Bulls")
        )
        self.assertEqual(
            matching.parse_vs_title("Chelsea vs Leeds United"),
            ("Chelsea", "Leeds United"),
        )

    def test_bukan_vs(self):
        self.assertIsNone(matching.parse_vs_title("NBA: 2027 Champion"))
        self.assertIsNone(matching.parse_vs_title(""))
        self.assertIsNone(matching.parse_vs_title(None))


if __name__ == "__main__":
    unittest.main()
