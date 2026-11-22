"""Tes ingest/bbref.py — TANPA network (mock client + fixture HTML).

Fixture HTML meniru tabel advanced-team di halaman liga BBRef
(leagues/NBA_2026.html, diambil live 2026-11-20): dua baris tim + baris
League Average di <tfoot> yang harus dilewati.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import bbref

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "nba_brain"


def _load_fixture_html(name: str) -> str:
    """Muat fixture HTML (cuplikan halaman nyata, lihat tests/fixtures)."""
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeClient:
    """Client palsu: get() mengembalikan respons yang sudah disiapkan."""

    def __init__(self, responses: dict[str, dict]) -> None:
        self.responses = responses
        self.urls_requested: list[str] = []

    def get(self, url: str, use_cache: bool = True) -> dict:
        """Kembalikan respons untuk URL (default: 404)."""
        self.urls_requested.append(url)
        return self.responses.get(url, {"status": 404, "body": "", "error": None})


def _resp(status: int, body: str) -> dict:
    return {"status": status, "body": body, "error": None}


ADVANCED_HTML = """<html><body>
<table class="stats_table" id="advanced-team">
<thead><tr>
<th data-stat="ranker">Rk</th><th data-stat="team">Team</th>
<th data-stat="wins">W</th><th data-stat="losses">L</th>
<th data-stat="off_rtg">ORtg</th><th data-stat="def_rtg">DRtg</th>
<th data-stat="net_rtg">NRtg</th><th data-stat="pace">Pace</th>
</tr></thead>
<tbody>
<tr><th data-stat="ranker">1</th>
<td data-stat="team"><a href="/teams/OKC/2026.html">Oklahoma City Thunder</a>*</td>
<td data-stat="age">25.2</td><td data-stat="wins">64</td><td data-stat="losses">18</td>
<td data-stat="mov">11.15</td><td data-stat="off_rtg">118.9</td>
<td data-stat="def_rtg">107.7</td><td data-stat="net_rtg">+11.2</td>
<td data-stat="pace">99.3</td><td data-stat="ts_pct">.599</td></tr>
<tr><th data-stat="ranker">2</th>
<td data-stat="team"><a href="/teams/PHI/2026.html">Philadelphia 76ers</a></td>
<td data-stat="age">26.8</td><td data-stat="wins">13</td><td data-stat="losses">3</td>
<td data-stat="mov">8.40</td><td data-stat="off_rtg">118.2</td>
<td data-stat="def_rtg">109.8</td><td data-stat="net_rtg">+8.4</td>
<td data-stat="pace">100.1</td><td data-stat="ts_pct"></td></tr>
</tbody>
<tfoot><tr><th data-stat="ranker"></th>
<td data-stat="team">League Average</td>
<td data-stat="off_rtg">115.8</td><td data-stat="def_rtg">115.8</td>
<td data-stat="pace">99.4</td></tr></tfoot>
</table>
</body></html>
"""


class TestParseAdvancedTable(unittest.TestCase):
    def test_parse_dua_tim(self):
        teams = bbref.parse_advanced_table(ADVANCED_HTML)
        self.assertEqual(len(teams), 2)
        okc = teams[0]
        # "*" playoff dibuang dari nama tim.
        self.assertEqual(okc["team"], "Oklahoma City Thunder")
        self.assertEqual(okc["wins"], 64)
        self.assertEqual(okc["losses"], 18)
        self.assertEqual(okc["age"], 25.2)
        self.assertEqual(okc["mov"], 11.15)
        self.assertEqual(okc["off_rtg"], 118.9)
        self.assertEqual(okc["def_rtg"], 107.7)
        # "+11.2" diparsing jadi float 11.2.
        self.assertEqual(okc["net_rtg"], 11.2)
        self.assertEqual(okc["pace"], 99.3)
        self.assertEqual(okc["ts_pct"], 0.599)
        phi = teams[1]
        self.assertEqual(phi["team"], "Philadelphia 76ers")
        # Sel kosong jadi None.
        self.assertIsNone(phi["ts_pct"])
        # Baris League Average (tfoot) dilewati.
        self.assertNotIn("League Average", [t["team"] for t in teams])

    def test_tabel_tidak_ada_format_changed(self):
        with self.assertRaises(ValueError) as ctx:
            bbref.parse_advanced_table("<html><body>tidak ada tabel</body></html>")
        self.assertEqual(str(ctx.exception), "bbref_format_changed")

    def test_kolom_wajib_hilang_format_changed(self):
        html = ADVANCED_HTML.replace('data-stat="pace"', 'data-stat="pace_x"')
        with self.assertRaises(ValueError) as ctx:
            bbref.parse_advanced_table(html)
        self.assertEqual(str(ctx.exception), "bbref_format_changed")

    def test_angka_koma_ribuan(self):
        self.assertEqual(bbref._to_number("764,842"), 764842)
        self.assertEqual(bbref._to_number("+11.2"), 11.2)
        self.assertEqual(bbref._to_number(".599"), 0.599)
        self.assertIsNone(bbref._to_number(""))
        self.assertIsNone(bbref._to_number("abc"))


class TestFetchTeamAdvanced(unittest.TestCase):
    def test_fetch_ok(self):
        url = "https://www.basketball-reference.com/leagues/NBA_2026.html"
        client = FakeClient({url: _resp(200, ADVANCED_HTML)})
        result = bbref.fetch_team_advanced(client=client)
        self.assertTrue(result.ok)
        self.assertEqual(result.source, "Basketball-Reference")
        self.assertEqual(result.tier, 2)
        self.assertEqual(len(result.data), 2)
        self.assertEqual(result.extra["season"], 2026)
        self.assertEqual(result.extra["n_teams"], 2)
        self.assertEqual(client.urls_requested, [url])

    def test_fetch_musim_2027(self):
        url = "https://www.basketball-reference.com/leagues/NBA_2027.html"
        client = FakeClient({url: _resp(200, ADVANCED_HTML)})
        result = bbref.fetch_team_advanced(season=2027, client=client)
        self.assertTrue(result.ok)
        self.assertEqual(result.extra["season"], 2027)

    def test_fetch_http_gagal(self):
        result = bbref.fetch_team_advanced(client=FakeClient({}))
        self.assertFalse(result.ok)
        self.assertIn("http_404", result.error or "")

    def test_fetch_format_berubah(self):
        url = "https://www.basketball-reference.com/leagues/NBA_2026.html"
        client = FakeClient({url: _resp(200, "<html>halaman berubah</html>")})
        result = bbref.fetch_team_advanced(client=client)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "bbref_format_changed")


# HTML sintetis kecil: satu pemain pindah tim (2 baris tim + 1 baris TOT).
PLAYER_TOT_HTML = """<html><body>
<table class="stats_table" id="advanced">
<thead><tr>
<th data-stat="name_display">Player</th><th data-stat="team_name_abbr">Tm</th>
<th data-stat="games">G</th><th data-stat="mp">MP</th><th data-stat="bpm">BPM</th>
</tr></thead>
<tbody>
<tr><td data-stat="name_display">Pemain Pindah</td>
<td data-stat="team_name_abbr">CHO</td><td data-stat="games">10</td>
<td data-stat="mp">200</td><td data-stat="bpm">1.5</td></tr>
<tr><td data-stat="name_display">Pemain Pindah</td>
<td data-stat="team_name_abbr">MIA</td><td data-stat="games">5</td>
<td data-stat="mp">100</td><td data-stat="bpm">2.0</td></tr>
<tr><td data-stat="name_display">Pemain Pindah</td>
<td data-stat="team_name_abbr">TOT</td><td data-stat="games">15</td>
<td data-stat="mp">300</td><td data-stat="bpm">1.7</td></tr>
</tbody>
</table>
</body></html>
"""


class TestParsePlayerAdvanced(unittest.TestCase):
    def test_parse_empat_pemain_fixture(self):
        html = _load_fixture_html("bbref_player_advanced_sample.html")
        players = bbref.parse_player_advanced(html)
        # 4 pemain; baris "League Average" di fixture dilewati.
        self.assertEqual(len(players), 4)
        trae = players[0]
        self.assertEqual(trae["player"], "Trae Young")
        self.assertEqual(trae["team"], "WAS")
        self.assertEqual(trae["mp"], 596)
        self.assertAlmostEqual(trae["mp_per_game"], 596 / 17)
        self.assertEqual(trae["bpm"], -1.6)
        # Tricode BBRef dipetakan ke tricode stats.nba.com.
        randle = [p for p in players if p["player"] == "Julius Randle"][0]
        self.assertEqual(randle["team"], "BKN")
        booker = [p for p in players if p["player"] == "Devin Booker"][0]
        self.assertEqual(booker["team"], "PHX")
        self.assertNotIn("League Average", [p["player"] for p in players])

    def test_tabel_dalam_komentar_tetap_terbaca(self):
        html = _load_fixture_html("bbref_player_advanced_sample.html")
        commented = html.replace(
            '<table class="stats_table sortable soc" id="advanced">',
            '<!--<table class="stats_table sortable soc" id="advanced">',
        ).replace("</table>", "</table>-->")
        players = bbref.parse_player_advanced(commented)
        self.assertEqual(len(players), 4)
        self.assertEqual(players[0]["player"], "Trae Young")

    def test_baris_tot_dilewati(self):
        players = bbref.parse_player_advanced(PLAYER_TOT_HTML)
        self.assertEqual(len(players), 2)
        self.assertEqual({p["team"] for p in players}, {"CHA", "MIA"})
        # CHO (BBRef) dipetakan ke CHA (stats.nba.com).
        cho = [p for p in players if p["team"] == "CHA"][0]
        self.assertEqual(cho["mp"], 200)
        self.assertAlmostEqual(cho["mp_per_game"], 20.0)
        self.assertEqual(cho["bpm"], 1.5)

    def test_tabel_tidak_ada_format_changed(self):
        with self.assertRaises(ValueError) as ctx:
            bbref.parse_player_advanced("<html><body>tidak ada tabel</body></html>")
        self.assertEqual(str(ctx.exception), "bbref_format_changed")

    def test_kolom_wajib_hilang_format_changed(self):
        html = _load_fixture_html("bbref_player_advanced_sample.html")
        html = html.replace('data-stat="bpm"', 'data-stat="bpm_x"')
        with self.assertRaises(ValueError) as ctx:
            bbref.parse_player_advanced(html)
        self.assertEqual(str(ctx.exception), "bbref_format_changed")

    def test_mp_kosong_jadi_none(self):
        html = PLAYER_TOT_HTML.replace(
            '<td data-stat="mp">100</td>', '<td data-stat="mp"></td>'
        )
        players = bbref.parse_player_advanced(html)
        mia = [p for p in players if p["team"] == "MIA"][0]
        self.assertIsNone(mia["mp"])
        self.assertIsNone(mia["mp_per_game"])
        self.assertEqual(mia["bpm"], 2.0)


class TestFetchPlayerAdvanced(unittest.TestCase):
    def test_fetch_ok(self):
        url = "https://www.basketball-reference.com/leagues/NBA_2027_advanced.html"
        html = _load_fixture_html("bbref_player_advanced_sample.html")
        client = FakeClient({url: _resp(200, html)})
        result = bbref.fetch_player_advanced(client=client)
        self.assertTrue(result.ok)
        self.assertEqual(result.source, "Basketball-Reference")
        self.assertEqual(result.tier, 2)
        self.assertEqual(len(result.data), 4)
        self.assertEqual(result.extra["season"], 2027)
        self.assertEqual(result.extra["n_players"], 4)
        self.assertEqual(client.urls_requested, [url])

    def test_fetch_musim_2026(self):
        url = "https://www.basketball-reference.com/leagues/NBA_2026_advanced.html"
        html = _load_fixture_html("bbref_player_advanced_sample.html")
        client = FakeClient({url: _resp(200, html)})
        result = bbref.fetch_player_advanced(season=2026, client=client)
        self.assertTrue(result.ok)
        self.assertEqual(result.extra["season"], 2026)

    def test_fetch_http_gagal(self):
        result = bbref.fetch_player_advanced(client=FakeClient({}))
        self.assertFalse(result.ok)
        self.assertIn("http_404", result.error or "")

    def test_fetch_format_berubah(self):
        url = "https://www.basketball-reference.com/leagues/NBA_2027_advanced.html"
        client = FakeClient({url: _resp(200, "<html>halaman berubah</html>")})
        result = bbref.fetch_player_advanced(client=client)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "bbref_format_changed")


if __name__ == "__main__":
    unittest.main()
