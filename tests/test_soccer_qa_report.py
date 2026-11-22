"""Tes dukungan bola di engine/qa.py + report/nba_report.py — SEMUA offline.

Artefak soccer_analysis dibangun dari fixture (tidak memanggil builder).
qa.answer(analysis, question) mengembalikan dict {"question", "intent",
"answer", "numbers", "verified"}; build_soccer_report(artefak)
mengembalikan {"format", "format_version", "match_id", "status",
"generated_from", "sections", "tidak_terverifikasi", "text"}.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import qa
from report import nba_report

HOME = "Liverpool"
AWAY = "Manchester United"
MATCH_ID = "manchester-united@liverpool_2026-11-22"
TANGGAL = "2026-11-22"


def _kaki(market_type, selection, p_model, p_market, harga, line=None):
    p_final = (
        round(0.3 * p_model + 0.7 * p_market, 3) if p_market is not None else p_model
    )
    return {
        "leg_id": f"{MATCH_ID}:{market_type}:{selection}",
        "market_type": market_type,
        "selection": selection,
        "line": line,
        "ticket": "main",
        "p_model": p_model,
        "p_market": p_market,
        "comparison_source": "kalshi" if p_market is not None else None,
        "p_final": p_final,
        "price_cents": harga,
        "jup_estimated_cents": harga,
        "ev_pct": round((p_final * (100.0 / harga) - 1.0) * 100.0, 2),
        "price_label": "WAJAR",
        "meets": True,
        "reason": None,
        "no_xg": True,
        "banned_from_insurance": True,
        "threshold_penalty_points": 5,
        "model_only": p_market is None,
    }


def _blok_cedera(entri):
    return {
        "sources": [],
        "n_sources": 0,
        "confirmed_both": [],
        "entries": entri,
        "conflicts": [],
        "fetched_at": None,
    }


def _artefak(status="HOLD", entri_cedera=None):
    return {
        "format": "soccer_analysis",
        "format_version": 1,
        "match_id": MATCH_ID,
        "home_team": HOME,
        "away_team": AWAY,
        "league": "EPL",
        "match_date": TANGGAL,
        "start_time": "2026-11-22T16:30:00+00:00",
        "generated_at": "2026-11-22T10:00:00+00:00",
        "status": status,
        "labels": ["TANPA_XG"],
        "inputs": {
            "match": {
                "home_team": HOME,
                "away_team": AWAY,
                "match_date": TANGGAL,
                "season": "2026-27",
                "league": "EPL",
                "matchweek": 11,
                "kickoff": "2026-11-22T16:30:00+00:00",
            },
            "home": {
                "team": HOME,
                "stats_season": {
                    "played": 11,
                    "w": 7,
                    "d": 2,
                    "l": 2,
                    "goals_for_per_match": 1.9,
                    "goals_against_per_match": 0.9,
                },
                "stats_last6": {
                    "played": 6,
                    "w": 4,
                    "d": 1,
                    "l": 1,
                    "goals_for_per_match": 2.0,
                    "goals_against_per_match": 0.8,
                },
                "form5": [
                    {
                        "date": "2026-11-15",
                        "opponent": "Manchester United",
                        "home": False,
                        "score": "0-2",
                        "result": "W",
                    }
                ],
                "home_record": {
                    "played": 5,
                    "w": 4,
                    "d": 1,
                    "l": 0,
                    "gf_per_match": 2.2,
                    "ga_per_match": 0.6,
                },
                "away_record": {
                    "played": 6,
                    "w": 3,
                    "d": 1,
                    "l": 2,
                    "gf_per_match": 1.7,
                    "ga_per_match": 1.2,
                },
                "attack": 1.25,
                "defence": 1.15,
                "injuries": entri_cedera or [],
            },
            "away": {
                "team": AWAY,
                "stats_season": {
                    "played": 11,
                    "w": 5,
                    "d": 3,
                    "l": 3,
                    "goals_for_per_match": 1.4,
                    "goals_against_per_match": 1.2,
                },
                "stats_last6": {
                    "played": 6,
                    "w": 2,
                    "d": 2,
                    "l": 2,
                    "goals_for_per_match": 1.3,
                    "goals_against_per_match": 1.3,
                },
                "form5": [],
                "home_record": {
                    "played": 6,
                    "w": 3,
                    "d": 2,
                    "l": 1,
                    "gf_per_match": 1.5,
                    "ga_per_match": 1.0,
                },
                "away_record": {
                    "played": 5,
                    "w": 2,
                    "d": 1,
                    "l": 2,
                    "gf_per_match": 1.2,
                    "ga_per_match": 1.4,
                },
                "attack": 0.95,
                "defence": 0.90,
                "injuries": [],
            },
            "h2h_last5": [
                {
                    "date": "2026-11-15",
                    "home": "Manchester United",
                    "away": "Liverpool",
                    "score": "0-2",
                    "home_goals": 0,
                    "away_goals": 2,
                }
            ],
            "league": {
                "avg_goals_per_team_match": 1.35,
                "n_matches": 110,
                "n_teams": 20,
            },
            "weights": {
                "season": 0.6,
                "recent": 0.4,
                "recent_matches": 6,
                "source": "config",
            },
            "injuries_status": {
                "n_sources": 0,
                "confirmed": False,
                "note": "cedera tidak terkonfirmasi",
            },
            "injury_sources_checked": [
                {
                    "source": "ESPN soccer injuries (eng.1)",
                    "status": "kosong",
                    "n_entries": 0,
                }
            ],
            "missing": ["injuries_tidak_terkonfirmasi"],
            "sources": [
                {
                    "data_kind": "football_results",
                    "source": "Premier League (JSON resmi)",
                    "tier": 1,
                    "fetched_at": "2026-11-22T10:00:00+00:00",
                }
            ],
            "fetched_at": "2026-11-22T10:00:00+00:00",
        },
        "simulation": {
            "match_id": MATCH_ID,
            "sport": "football",
            "iterations": 1000,
            "generated_at": "2026-11-22T10:00:00+00:00",
            "engine": {
                "name": "dixon-coles-fixture",
                "seed": 7,
                "version": "fixture-1",
            },
            "markets": {
                "home_win": 0.60,
                "draw": 0.22,
                "away_win": 0.18,
                "total_over_2_5": 0.62,
                "total_under_2_5": 0.38,
                "btts_yes": 0.58,
                "btts_no": 0.42,
            },
            "score_distribution": {
                "total": {"median": 2.7, "mean": 2.75, "std": 1.6},
                "home_points": {"mean": 1.6, "median": 2.0},
                "away_points": {"mean": 1.15, "median": 1.0},
            },
        },
        "fit_status": {
            "status": "menunggu_persetujuan",
            "source": "argumen",
            "fit_version": "CONTOH — fit menunggu persetujuan",
            "approved": False,
        },
        "market": {
            "source": "jup_ag_via_slate",
            "fetched_at": "2026-11-22T10:00:00+00:00",
            "moneyline": {
                "home_cents": 55.0,
                "draw_cents": 23.0,
                "away_cents": 23.0,
            },
            "totals": [
                {
                    "line": 2.5,
                    "over_cents": 64.0,
                    "under_cents": 37.0,
                }
            ],
            "btts_cents": 64.0,
            "n_markets": 7,
        },
        "price_snapshots": {},
        "legs": [
            _kaki("moneyline_home", "home", 0.60, 0.54, 55.0),
            _kaki("moneyline_draw", "draw", 0.22, 0.23, 23.0),
            _kaki("moneyline_away", "away", 0.18, 0.23, 23.0),
            _kaki("total_over", "over", 0.62, 0.645, 64.0, line=2.5),
            _kaki("total_under", "under", 0.38, 0.355, 37.0, line=2.5),
            _kaki("btts_yes", "yes", 0.58, None, 64.0),
        ],
        "injuries": _blok_cedera(entri_cedera or []),
        "anomalies": [],
        "missing": ["fit_belum_disetujui", "cedera_kurang_dari_2_sumber"],
        "sources": [],
    }


class TestQaBola(unittest.TestCase):
    def test_peluang_laga_bola(self):
        hasil = qa.answer(_artefak(), "peluang menang Liverpool?")
        self.assertEqual(hasil["intent"], "peluang_laga")
        self.assertTrue(hasil["verified"])
        self.assertIn("Liverpool", hasil["answer"])
        self.assertIn("60%", hasil["answer"])  # menang kandang
        self.assertIn("22%", hasil["answer"])  # seri
        self.assertIn("18%", hasil["answer"])  # menang tandang
        self.assertIn("TANPA_XG", hasil["answer"])
        self.assertEqual(hasil["numbers"]["moneyline_home"], 0.60)
        self.assertEqual(hasil["numbers"]["median_total_goals"], 2.7)

    def test_peluang_laga_bola_tanpa_sim(self):
        art = _artefak()
        art["simulation"] = None
        hasil = qa.answer(art, "siapa yang menang?")
        self.assertEqual(hasil["intent"], "peluang_laga")
        self.assertFalse(hasil["verified"])
        self.assertIn("tidak bisa", hasil["answer"].lower())

    def test_peluang_ot_bola_dijawab_jujur(self):
        hasil = qa.answer(_artefak(), "berapa peluang masuk OT?")
        self.assertEqual(hasil["intent"], "peluang_laga")
        self.assertIn("perpanjangan waktu", hasil["answer"])
        self.assertIn("seri", hasil["answer"])

    def test_kabar_pemain_bola_belum_terkonfirmasi(self):
        hasil = qa.answer(_artefak(), "siapa yang cedera?")
        self.assertEqual(hasil["intent"], "kabar_pemain")
        self.assertFalse(hasil["verified"])
        self.assertIn("belum terkonfirmasi", hasil["answer"])
        self.assertEqual(hasil["numbers"]["n_sumber_cedera"], 0.0)

    def test_kabar_pemain_bola_dengan_cedera(self):
        art = _artefak(
            entri_cedera=[
                {
                    "player": "Mohamed Salah",
                    "team": "Liverpool",
                    "status": "QUESTIONABLE",
                    "reason": "hamstring",
                    "sources": ["ESPN"],
                }
            ]
        )
        hasil = qa.answer(art, "siapa yang cedera?")
        self.assertEqual(hasil["intent"], "kabar_pemain")
        self.assertIn("Mohamed Salah", hasil["answer"])
        self.assertIn("diragukan", hasil["answer"])
        # Tetap jujur: baru 1 sumber, belum terkonfirmasi penuh.
        self.assertIn("belum terkonfirmasi", hasil["answer"])

    def test_intent_lain_belum_tersedia_bola(self):
        hasil = qa.answer(_artefak(), "kenapa totalnya segitu?")
        self.assertEqual(hasil["intent"], "kenapa_total")
        self.assertFalse(hasil["verified"])
        self.assertIn("belum bisa saya jawab untuk laga bola", hasil["answer"])
        # Tidak mengarang angka.
        self.assertEqual(hasil["numbers"], {})

    def test_unknown_bola_hanya_dua_intent(self):
        hasil = qa.answer(_artefak(), "asdfghjkl")
        self.assertEqual(hasil["intent"], "unknown")
        self.assertIn("diragukan tampil", hasil["answer"])  # kabar_pemain
        self.assertIn("peluang masuk OT", hasil["answer"])  # peluang_laga
        self.assertNotIn("Garis Asuransi", hasil["answer"])  # garis_teraman


class TestReportBola(unittest.TestCase):
    def test_render_memuat_bagian_utama(self):
        teks = nba_report.render_soccer_report(_artefak())
        self.assertIn("Liverpool", teks)
        self.assertIn("Manchester United", teks)
        self.assertIn("TANPA_XG", teks)
        self.assertIn("xg tidak tersedia", teks.lower())
        self.assertIn("Ringkasan", teks)
        self.assertIn("Data tim", teks)
        self.assertIn("Proyeksi gol", teks)
        self.assertIn("Kabar pemain", teks)
        self.assertIn("Kaki", teks)
        self.assertIn("Lima laga terakhir", teks)
        self.assertIn("Pertemuan terakhir", teks)
        self.assertIn("Kandang vs tandang", teks)
        self.assertIn("Sumber data", teks)
        self.assertIn("Yang belum bisa dipastikan", teks)

    def test_render_json_valid(self):
        laporan = nba_report.render_soccer_report_json(_artefak())
        self.assertEqual(laporan["format"], "soccer_report")
        self.assertEqual(laporan["format_version"], 1)
        self.assertEqual(laporan["match_id"], MATCH_ID)
        self.assertEqual(laporan["status"], "HOLD")
        judul = [b["heading"] for b in laporan["sections"]]
        self.assertIn("Kaki", judul)
        self.assertIn("Yang belum bisa dipastikan", judul)
        self.assertGreaterEqual(len(laporan["sections"]), 10)

    def test_render_tanpa_inputs_tidak_crash(self):
        art = _artefak()
        art["inputs"] = None
        art["simulation"] = None
        art["legs"] = []
        teks = nba_report.render_soccer_report(art)
        self.assertIn("tidak terverifikasi", teks.lower())

    def test_format_salah_ditolak(self):
        with self.assertRaises(ValueError):
            nba_report.build_soccer_report({"format": "nba_analysis"})
        with self.assertRaises(ValueError):
            nba_report.build_soccer_report("bukan dict")

    def test_celah_dokumentasi_narasi_bola(self):
        laporan = nba_report.build_soccer_report(_artefak())
        self.assertTrue(laporan["tidak_terverifikasi"])
        self.assertTrue(
            any("Narasi bola lengkap" in c for c in laporan["tidak_terverifikasi"]),
            laporan["tidak_terverifikasi"],
        )


if __name__ == "__main__":
    unittest.main()
