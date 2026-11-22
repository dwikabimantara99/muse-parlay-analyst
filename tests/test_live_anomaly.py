"""Tes engine/live_anomaly.py + fetcher baseline ingest/bbref.py.

TANPA network (mock client + fixture HTML) — kecuali verifikasi replay
nyata yang dijalankan manual satu kali (lihat laporan pekerja C).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import live_anomaly as anomaly_mod
from ingest import bbref

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Section live: dari config/playstyle.yaml (pekerja B) — nilai dipakai
# tes ini sama dengan yang tertulis di tugas langkah 4.
LIVE_CFG = {
    "live": {
        "status_margin_aman_points": 6.0,
        "status_margin_waspada_points": 2.0,
        "anomaly_min_minutes_elapsed": 12,
        "anomaly_fg3_rate_multiplier": 1.5,
        "anomaly_ft_rate_multiplier": 1.5,
        "anomaly_scoring_rate_multiplier": 1.15,
        "ot_risk_margin_points": 3,
        "ot_risk_minutes_remaining": 2.0,
    }
}

# Baseline nyata musim 2026-27 (replay 2026-11-22): DET 35.47 3PA +
# 24.60 FTA per laga; ATL 42.88 3PA + 20.38 FTA per laga.
BASELINES = {
    "DET": {"fg3a_per_game": 35.47, "fta_per_game": 24.60},
    "ATL": {"fg3a_per_game": 42.88, "fta_per_game": 20.38},
}


def _game(
    home_fg3a=10,
    away_fg3a=10,
    home_fta=5,
    away_fta=5,
    stats=True,
    period=2,
    seconds_remaining=1440,
):
    """LiveGame DET@ATL pada menit ke-24 (kuarter 2, 12:00 tersisa)."""
    game = {
        "match_id": "DET@ATL_2026-11-22",
        "espn_game_id": "401810001",
        "home_abbr": "ATL",
        "away_abbr": "DET",
        "home_team": "Atlanta Hawks",
        "away_team": "Detroit Pistons",
        "status": "berjalan",
        "period": period,
        "clock_display": "12:00",
        "seconds_remaining": seconds_remaining,
        "home_score": 50,
        "away_score": 50,
        "line_scores": None,
        "stats": None,
        "fetched_at": "2026-11-22T00:00:00+00:00",
        "source": "ESPN",
    }
    if stats:
        game["stats"] = {
            "ATL": {
                "fg3_made": 5,
                "fg3_attempted": home_fg3a,
                "ft_made": 4,
                "ft_attempted": home_fta,
            },
            "DET": {
                "fg3_made": 4,
                "fg3_attempted": away_fg3a,
                "ft_made": 4,
                "ft_attempted": away_fta,
            },
        }
    return game


def _proj(minutes=24.0, live_ppm=4.17, pregame_ppm=4.5625):
    return {
        "projected_total": 200.0,
        "method": "test",
        "live_rate_ppm": live_ppm,
        "pregame_rate_ppm": pregame_ppm,
        "minutes_elapsed": minutes,
        "minutes_remaining": 48.0 - minutes,
        "ot_risk": False,
        "notes": [],
    }


def _tipe(anomalies):
    return [a["type"] for a in anomalies]


class TestDetectAnomalies(unittest.TestCase):
    def test_hujan_3pt_terpicu(self):
        # 60x 3PA dalam 24 menit -> laju 120/48 mnt; baseline gabungan
        # 78.35 x 1.5 = 117.5 -> terpicu.
        game = _game(home_fg3a=30, away_fg3a=30)
        anoms, skip = anomaly_mod.detect_anomalies(game, BASELINES, _proj(), LIVE_CFG)
        self.assertIn("hujan_3pt", _tipe(anoms))
        hujan = [a for a in anoms if a["type"] == "hujan_3pt"][0]
        self.assertAlmostEqual(hujan["numbers"]["laju_per_48"], 120.0)
        self.assertAlmostEqual(hujan["numbers"]["baseline_gabungan_per_laga"], 78.35)
        self.assertIn("Under", hujan["implication"])

    def test_hujan_3pt_di_bawah_ambang(self):
        # 50x 3PA dalam 24 menit -> laju 100 < 117.5 -> tidak terpicu.
        game = _game(home_fg3a=25, away_fg3a=25)
        anoms, _ = anomaly_mod.detect_anomalies(game, BASELINES, _proj(), LIVE_CFG)
        self.assertNotIn("hujan_3pt", _tipe(anoms))

    def test_hujan_3pt_tepat_di_ambang_terpicu(self):
        # Baseline bulat 40+40=80, ambang 120; 60x 3PA dalam 24 menit
        # -> laju tepat 120 -> terpicu (>=, bukan >).
        baselines = {
            "DET": {"fg3a_per_game": 40.0, "fta_per_game": 20.0},
            "ATL": {"fg3a_per_game": 40.0, "fta_per_game": 20.0},
        }
        game = _game(home_fg3a=30, away_fg3a=30)
        anoms, _ = anomaly_mod.detect_anomalies(game, baselines, _proj(), LIVE_CFG)
        self.assertIn("hujan_3pt", _tipe(anoms))

    def test_ft_berlebihan_terpicu(self):
        # 40x FTA dalam 24 menit -> laju 80/48 mnt; baseline gabungan
        # 44.98 x 1.5 = 67.47 -> terpicu.
        game = _game(home_fta=20, away_fta=20)
        anoms, _ = anomaly_mod.detect_anomalies(game, BASELINES, _proj(), LIVE_CFG)
        self.assertIn("ft_berlebihan", _tipe(anoms))

    def test_ft_berlebihan_di_bawah_ambang(self):
        game = _game(home_fta=5, away_fta=5)
        anoms, _ = anomaly_mod.detect_anomalies(game, BASELINES, _proj(), LIVE_CFG)
        self.assertNotIn("ft_berlebihan", _tipe(anoms))

    def test_laju_skor_tinggi_terpicu(self):
        # Live 5.30 ppm vs pra-laga 4.5625 x 1.15 = 5.247 -> terpicu.
        anoms, _ = anomaly_mod.detect_anomalies(
            _game(), BASELINES, _proj(live_ppm=5.30), LIVE_CFG
        )
        self.assertIn("laju_skor_tinggi", _tipe(anoms))

    def test_laju_skor_di_bawah_ambang(self):
        anoms, _ = anomaly_mod.detect_anomalies(
            _game(), BASELINES, _proj(live_ppm=4.17), LIVE_CFG
        )
        self.assertNotIn("laju_skor_tinggi", _tipe(anoms))

    def test_tidak_ada_anomali_bila_semua_normal(self):
        anoms, skip = anomaly_mod.detect_anomalies(
            _game(), BASELINES, _proj(), LIVE_CFG
        )
        self.assertEqual(anoms, [])
        self.assertEqual(skip, [])

    def test_sampel_kecil_semua_dilewati(self):
        # 10 menit < minimum 12 -> tidak ada anomali, 3 dilewati.
        game = _game(home_fg3a=30, away_fg3a=30, period=1, seconds_remaining=2280)
        anoms, skip = anomaly_mod.detect_anomalies(
            game, BASELINES, _proj(minutes=10.0, live_ppm=9.0), LIVE_CFG
        )
        self.assertEqual(anoms, [])
        self.assertEqual(
            sorted(s["type"] for s in skip),
            ["ft_berlebihan", "hujan_3pt", "laju_skor_tinggi"],
        )
        self.assertIn("sampel_terlalu_kecil", skip[0]["reason"])

    def test_tepat_12_menit_dievaluasi(self):
        game = _game(home_fg3a=30, away_fg3a=30)
        anoms, skip = anomaly_mod.detect_anomalies(
            game, BASELINES, _proj(minutes=12.0), LIVE_CFG
        )
        # 60x 3PA dalam 12 menit -> laju 240, jauh di atas ambang.
        self.assertIn("hujan_3pt", _tipe(anoms))

    def test_stats_none_3pt_dan_ft_dilewati(self):
        game = _game(stats=False)
        anoms, skip = anomaly_mod.detect_anomalies(game, BASELINES, _proj(), LIVE_CFG)
        dilewati = {s["type"]: s["reason"] for s in skip}
        self.assertIn("hujan_3pt", dilewati)
        self.assertIn("ft_berlebihan", dilewati)
        self.assertNotIn("laju_skor_tinggi", dilewati)

    def test_baseline_hilang_dilewati(self):
        # Hanya baseline DET; ATL hilang -> 3PT + FT dilewati.
        game = _game(home_fg3a=30, away_fg3a=30)
        anoms, skip = anomaly_mod.detect_anomalies(
            game, {"DET": BASELINES["DET"]}, _proj(), LIVE_CFG
        )
        dilewati = {s["type"]: s["reason"] for s in skip}
        self.assertIn("hujan_3pt", dilewati)
        self.assertIn("ATL", dilewati["hujan_3pt"])
        self.assertNotIn("hujan_3pt", _tipe(anoms))

    def test_baselines_list_mentah_diindeks(self):
        mentah = [
            {"tricode": "DET", "fg3a_per_game": 35.47, "fta_per_game": 24.60},
            {"tricode": "ATL", "fg3a_per_game": 42.88, "fta_per_game": 20.38},
        ]
        game = _game(home_fg3a=30, away_fg3a=30)
        anoms, _ = anomaly_mod.detect_anomalies(game, mentah, _proj(), LIVE_CFG)
        self.assertIn("hujan_3pt", _tipe(anoms))

    def test_pregame_rate_hilang_laju_dilewati(self):
        anoms, skip = anomaly_mod.detect_anomalies(
            _game(), BASELINES, _proj(pregame_ppm=None), LIVE_CFG
        )
        dilewati = {s["type"] for s in skip}
        self.assertIn("laju_skor_tinggi", dilewati)
        self.assertNotIn("laju_skor_tinggi", _tipe(anoms))

    def test_menit_dari_live_game_bila_projection_tanpa_menit(self):
        # Projection tanpa minutes_elapsed -> dihitung dari
        # seconds_remaining (1440 -> 24 menit); 3PT tetap terpicu.
        proj = _proj()
        del proj["minutes_elapsed"]
        game = _game(home_fg3a=30, away_fg3a=30)
        anoms, _ = anomaly_mod.detect_anomalies(game, BASELINES, proj, LIVE_CFG)
        self.assertIn("hujan_3pt", _tipe(anoms))

    def test_config_hilang_fail_closed(self):
        with self.assertRaises(ValueError):
            anomaly_mod.detect_anomalies(_game(), BASELINES, _proj(), {"live": {}})


class TestMinutesElapsed(unittest.TestCase):
    def test_reguler(self):
        self.assertAlmostEqual(anomaly_mod.minutes_elapsed_dari_live(_game()), 24.0)

    def test_ot_tidak_diketahui(self):
        game = _game(period=5, seconds_remaining=150)
        self.assertIsNone(anomaly_mod.minutes_elapsed_dari_live(game))

    def test_tanpa_field(self):
        self.assertIsNone(anomaly_mod.minutes_elapsed_dari_live({}))


class TestFormatAnomalies(unittest.TestCase):
    def test_tanpa_anomali(self):
        teks = anomaly_mod.format_anomalies([], [], "DET@ATL_2026-11-22")
        self.assertIn("tidak ada anomali", teks)

    def test_dengan_anomali_dan_skip(self):
        anoms, skip = anomaly_mod.detect_anomalies(
            _game(home_fg3a=30, away_fg3a=30, stats=True),
            {"DET": BASELINES["DET"]},
            _proj(),
            LIVE_CFG,
        )
        teks = anomaly_mod.format_anomalies(anoms, skip, "DET@ATL_2026-11-22")
        # Baseline ATL hilang -> 3PT dilewati (bukan terpicu).
        self.assertIn("dilewati", teks)

    def test_hanya_skip_judul_pemeriksaan(self):
        # Tanpa anomali nyata, judulnya "Pemeriksaan" (bukan "Anomali")
        # agar yang dilewati tidak terbaca sebagai peringatan.
        teks = anomaly_mod.format_anomalies(
            [],
            [{"type": "hujan_3pt", "reason": "sampel_terlalu_kecil"}],
            "DET@ATL_2026-11-22",
        )
        self.assertIn("Pemeriksaan DET@ATL_2026-11-22:", teks)
        self.assertNotIn("Anomali", teks)
        self.assertIn("dilewati", teks)


class FakeClient:
    """Client palsu: get() mengembalikan respons yang sudah disiapkan."""

    def __init__(self, responses: dict[str, dict]) -> None:
        self.responses = responses
        self.urls_requested: list[str] = []

    def get(self, url: str, use_cache: bool = True) -> dict:
        self.urls_requested.append(url)
        return self.responses.get(url, {"status": 404, "body": "", "error": None})


def _resp(status: int, body: str) -> dict:
    return {"status": status, "body": body, "error": None}


class TestFetchShootingBaselines(unittest.TestCase):
    def test_parse_tabel_dalam_komentar(self):
        html = (FIXTURES / "live_anomaly_totals.html").read_text(encoding="utf-8")
        teams = bbref.parse_team_shooting_totals(html)
        self.assertEqual(len(teams), 2)
        det = [t for t in teams if t["tricode"] == "DET"][0]
        self.assertEqual(det["games"], 15)
        self.assertAlmostEqual(det["fg3a_per_game"], 532 / 15)
        self.assertAlmostEqual(det["fta_per_game"], 369 / 15)
        atl = [t for t in teams if t["tricode"] == "ATL"][0]
        self.assertAlmostEqual(atl["fg3a_per_game"], 686 / 16)
        self.assertAlmostEqual(atl["fta_per_game"], 326 / 16)

    def test_fetcher_memakai_halaman_utama_liga(self):
        # Koreksi sumber: tabel totals tim ada di halaman UTAMA liga,
        # bukan halaman _totals.html (yang hanya memuat tabel pemain).
        html = (FIXTURES / "live_anomaly_totals.html").read_text(encoding="utf-8")
        url = "https://www.basketball-reference.com/leagues/NBA_2027.html"
        client = FakeClient({url: _resp(200, html)})
        hasil = bbref.fetch_team_shooting_baselines(season=2027, client=client)
        self.assertTrue(hasil.ok, hasil.error)
        self.assertEqual(hasil.extra["n_teams"], 2)
        self.assertEqual(hasil.extra["table_id"], "totals-team")
        self.assertEqual(client.urls_requested, [url])

    def test_fetcher_http_gagal(self):
        client = FakeClient({})
        hasil = bbref.fetch_team_shooting_baselines(season=2027, client=client)
        self.assertFalse(hasil.ok)
        self.assertIn("http_404", hasil.error or "")

    def test_parse_format_berubah(self):
        with self.assertRaises(ValueError):
            bbref.parse_team_shooting_totals("<html><body>kosong</body></html>")

    def test_tricode_bbref_dipetakan(self):
        html = """<html><body><table id="totals-team"><tbody>
<tr><td data-stat="team"><a href="/teams/BRK/2027.html">Brooklyn Nets</a></td>
<td data-stat="g">10</td><td data-stat="fg3a">400</td>
<td data-stat="fta">200</td></tr>
</tbody></table></body></html>"""
        teams = bbref.parse_team_shooting_totals(html)
        self.assertEqual(teams[0]["tricode"], "BKN")
        self.assertAlmostEqual(teams[0]["fg3a_per_game"], 40.0)


if __name__ == "__main__":
    unittest.main()
