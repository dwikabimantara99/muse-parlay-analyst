"""Tes report/nba_report — render laporan lengkap per laga NBA.

SEMUA offline: fixture artefak dibangun di sini (angka meniru contoh
live DET@ATL 2026-11-22 di out/analysis_live_det_atl.json — median
219, p74 232, garis market 225,5, kaki 233,5/237,5). Tidak ada
panggilan Odds API (modul render murni; satu-satunya dependensi
engine adalah anomaly.check_model_vs_market untuk ambang 8 poin,
yang membaca playstyle.yaml lokal).
"""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from report import nba_report as nba_report_mod

HOME = "ATL"
AWAY = "DET"
TANGGAL = "2026-11-22"
MATCH_ID = "DET@ATL_2026-11-22"
JAM = "2026-11-22T14:03:06+00:00"
SUMBER_PDF = "Official NBA Injury Report"
SUMBER_ESPN = "ESPN"


def _form5(hasil):
    """5 laga terakhir dari daftar (tanggal, lawan, kandang, W/L, pts, opp)."""
    return [
        {
            "game_date": t,
            "opponent_tricode": lawan,
            "home": kandang,
            "wl": wl,
            "pts": pts,
            "opp_pts": opp,
        }
        for t, lawan, kandang, wl, pts, opp in hasil
    ]


def _blok_tim(tricode, nama, off, deff, pace, form5, pemain, cedera=None):
    """Satu blok tim kontrak nba_brain (cukup untuk laporan)."""
    return {
        "tricode": tricode,
        "team": nama,
        "stats_season": {
            "off_rtg": off,
            "def_rtg": deff,
            "net_rtg": round(off - deff, 1),
            "pace": pace,
        },
        "stats_last10": {
            "off_rtg": off - 1.5,
            "def_rtg": deff - 0.3,
            "net_rtg": round(off - deff - 1.2, 1),
            "pace": pace - 0.03,
        },
        "form5": form5,
        "home_record": {"w": 4, "l": 3, "ppg": 119.0, "opp_ppg": 119.29},
        "road_record": {"w": 6, "l": 3, "ppg": 116.0, "opp_ppg": 111.0},
        "rest_days": 1,
        "back_to_back": False,
        "altitude_home": False,
        "players": pemain,
        "injuries": cedera or [],
    }


def _pemain(nama, bpm, menit, tricode, shrinkage=False):
    pemain = {
        "player": nama,
        "bpm": bpm,
        "mp_per_game": menit,
        "team_tricode": tricode,
    }
    if shrinkage:
        pemain["shrinkage"] = "diterapkan"
    return pemain


def _sim():
    """Dict simulasi stub (median 219, p74 232, OT 2,74%)."""
    return {
        "match_id": MATCH_ID,
        "sport": "nba",
        "iterations": 100000,
        "generated_at": JAM,
        "engine": {"name": "nba_sim", "version": "1.1.0", "seed": 7},
        "markets": {
            "moneyline_home": 0.546,
            "moneyline_away": 0.454,
            "total_under_233.5": 0.77191,
            "total_under_237.5": 0.82964,
            "total_under_219": 0.5,
        },
        "inputs_summary": {
            "home_tricode": HOME,
            "away_tricode": AWAY,
            "game_date": TANGGAL,
            "pace_game": 100.64,
            "projected_home_points": 110.11,
            "projected_away_points": 108.56,
            "projected_margin": 1.55,
            "projected_total": 218.68,
            "home_advantage_points": 1.6639,
            "back_to_back": {"home": False, "away": False, "penalty_points": -1.5164},
            "altitude_home": False,
            "sigma_margin_points": 14.4307,
            "sigma_total_points": 18.9868,
            "t_nu": 35.0,
            "bpm_replacement": -2.0,
            "base_absent_players": ["Jalen Duren", "Asa Newell"],
        },
        "score_distribution": {
            "margin": {
                "mean": 1.63,
                "std": 14.43,
                "median": 2.0,
                "p5": -22.0,
                "p25": -8.0,
                "p75": 11.0,
                "p95": 25.0,
            },
            "total": {
                "mean": 219.3,
                "std": 19.46,
                "median": 219.0,
                "p5": 188.0,
                "p25": 206.0,
                "p74": 232.0,
                "p75": 232.0,
                "p95": 251.0,
            },
            "home_points": {"mean": 110.46, "median": 110.0},
            "away_points": {"mean": 108.83, "median": 109.0},
            "ot_probability": 0.0274,
        },
        "squad_scenarios": [
            {
                "scenario": "full",
                "absent_players": [],
                "markets": {
                    "moneyline_home": 0.464,
                    "total_under_233.5": 0.741,
                    "total_under_237.5": 0.81,
                },
            },
            {
                "scenario": "missing_1",
                "absent_players": ["Asa Newell", "Jalen Duren", "Jalen Johnson"],
                "markets": {
                    "moneyline_home": 0.51,
                    "total_under_233.5": 0.76,
                    "total_under_237.5": 0.82,
                },
            },
            {
                "scenario": "doubtful_out",
                "absent_players": ["Asa Newell", "Cade Cunningham", "Jalen Duren"],
                "markets": {
                    "moneyline_home": 0.58,
                    "total_under_233.5": 0.79,
                    "total_under_237.5": 0.85,
                },
            },
        ],
    }


def _total(garis, sisi, harga, volume, thin=False, bid=None, ask=None):
    entri = {
        "line": garis,
        "side": sisi,
        "team": None,
        "price_cents": harga,
        "bid_cents": bid,
        "ask_cents": ask,
        "mid_cents": None,
        "last_cents": None,
        "volume_usd": volume,
        "liquidity": 1000.0,
        "price_source": "book" if bid is not None else "outcome_prices",
        "thin": thin,
        "market_id": f"tot-{garis}-{sisi}",
        "jup_estimated_cents": harga + 0.5 if harga is not None else None,
    }
    return entri


def _kaki(ticket, garis, p_model, p_market, p_final, harga, harga_jup, ev, label):
    return {
        "leg_id": f"{MATCH_ID}:total_under_{garis:g}:{ticket}",
        "market_type": "total_under",
        "line": garis,
        "ticket": ticket,
        "p_model": p_model,
        "p_market": p_market,
        "comparison_source": "kalshi" if p_market is not None else None,
        "p_final": p_final,
        "price_cents": harga,
        "jup_estimated_cents": harga_jup,
        "ev_pct": ev,
        "price_label": label,
        "cushion_vs_median_points": garis - 219.0,
        "cushion_vs_market_points": garis - 225.5,
        "meets": True,
        "reason": None,
        "fetched_at": JAM,
    }


def _artefak():
    """Artefak nba_analysis lengkap (status OK) untuk DET@ATL."""
    cedera_home = [
        {
            "player": "Asa Newell",
            "status": "OUT",
            "team_tricode": HOME,
            "sources": [SUMBER_PDF, SUMBER_ESPN],
            "is_injury": True,
            "reason": "Injury/Illness - Left Great Toe Surgery",
            "availability_n_sources": 2,
        }
    ]
    cedera_away = [
        {
            "player": "Jalen Duren",
            "status": "OUT",
            "team_tricode": AWAY,
            "sources": [SUMBER_PDF, SUMBER_ESPN],
            "is_injury": True,
            "reason": "Injury/Illness - Right Hamstring Strain",
            "availability_n_sources": 2,
        },
        {
            "player": "Cade Cunningham",
            "status": "QUESTIONABLE",
            "team_tricode": AWAY,
            "sources": [SUMBER_PDF, SUMBER_ESPN],
            "is_injury": True,
            "reason": "Injury/Illness - Left Knee Soreness",
            "availability_n_sources": 2,
            "conflict": {SUMBER_PDF: "PROBABLE", SUMBER_ESPN: "QUESTIONABLE"},
        },
        {
            "player": "Pemain Cadangan",
            "status": "OUT",
            "team_tricode": AWAY,
            "sources": [SUMBER_ESPN],
            "is_injury": False,
            "reason": "Rest",
            "availability_n_sources": 1,
        },
        # Data live menunjukkan entri is_injury=True dengan alasan
        # "G League - Two-Way" (bukan cedera) — teks alasan yang
        # menentukan klasifikasi, bukan flag-nya.
        {
            "player": "Pemain Two-Way",
            "status": "OUT",
            "team_tricode": AWAY,
            "sources": [SUMBER_PDF],
            "is_injury": True,
            "reason": "G League - Two-Way",
            "availability_n_sources": 1,
        },
    ]
    home = _blok_tim(
        HOME,
        "Atlanta Hawks",
        113.1,
        110.4,
        103.11,
        _form5(
            [
                ("2026-11-20", "CHA", True, "W", 111, 97),
                ("2026-11-18", "OKC", False, "W", 117, 112),
                ("2026-11-15", "MIL", False, "W", 113, 106),
                ("2026-11-13", "CHI", False, "L", 117, 125),
                ("2026-11-09", "LAL", True, "L", 114, 124),
            ]
        ),
        [
            _pemain("Jalen Johnson", 2.56, 34.77, HOME, shrinkage=True),
            _pemain("Nickeil Alexander-Walker", 0.22, 32.49, HOME),
            _pemain("Dyson Daniels", 2.28, 31.0, HOME),
            _pemain("Onyeka Okongwu", 1.5, 28.0, HOME),
            _pemain("Trae Young", 3.1, 27.5, HOME),
            _pemain("Pemain Keenam", 0.1, 15.0, HOME),
        ],
        cedera_home,
    )
    away = _blok_tim(
        AWAY,
        "Detroit Pistons",
        112.0,
        111.0,
        100.5,
        _form5(
            [
                ("2026-11-20", "MIA", True, "W", 108, 101),
                ("2026-11-18", "NYK", False, "L", 99, 110),
                ("2026-11-16", "BOS", True, "W", 115, 109),
                ("2026-11-14", "PHI", False, "L", 102, 118),
                ("2026-11-12", "CLE", False, "L", 107, 112),
            ]
        ),
        [
            _pemain("Cade Cunningham", 5.1, 35.0, AWAY),
            _pemain("Jalen Duren", 5.63, 26.69, AWAY, shrinkage=True),
            _pemain("Ausar Thompson", 1.8, 30.0, AWAY),
            _pemain("Tobias Harris", 0.9, 29.0, AWAY),
            _pemain("Duncan Robinson", -0.5, 22.0, AWAY),
        ],
        cedera_away,
    )
    return {
        "format": "nba_analysis",
        "format_version": 1,
        "match_id": MATCH_ID,
        "home_tricode": HOME,
        "away_tricode": AWAY,
        "game_date": TANGGAL,
        "start_time": "2026-11-23T07:00:00+07:00",
        "generated_at": JAM,
        "status": "OK",
        "missing": ["tournament_flag_tidak_dapat_ditentukan"],
        "sources": [
            {
                "kind": "nba_games_season",
                "source": "stats.nba.com",
                "tier": 1,
                "time": JAM,
            },
            {
                "kind": "nba_team_advanced_season",
                "source": "stats.nba.com",
                "tier": 1,
                "time": JAM,
            },
            {
                "kind": "nba_team_advanced_last10",
                "source": "stats.nba.com",
                "tier": 1,
                "time": JAM,
            },
            {
                "kind": "nba_player_impact",
                "source": "Basketball-Reference",
                "tier": 2,
                "time": JAM,
            },
            {
                "kind": "nba_injuries",
                "source": SUMBER_PDF,
                "tier": 1,
                "time": JAM,
            },
            {
                "kind": "nba_injuries",
                "source": SUMBER_ESPN,
                "tier": 2,
                "time": JAM,
            },
            {
                "kind": "polymarket_ladder",
                "source": "Polymarket CLOB",
                "tier": 2,
                "time": JAM,
            },
            {
                "kind": "kalshi_total_markets",
                "source": "Kalshi API",
                "tier": 2,
                "time": JAM,
            },
        ],
        "inputs": {
            "match": {
                "home_tricode": HOME,
                "away_tricode": AWAY,
                "game_date": TANGGAL,
                "season": "2026-27",
            },
            "home": home,
            "away": away,
            "h2h_last5": [
                {
                    "game_id": "0022600123",
                    "game_date": "2026-01-15",
                    "home_tricode": HOME,
                    "away_tricode": AWAY,
                    "home_team": "Atlanta Hawks",
                    "away_team": "Detroit Pistons",
                    "home_pts": 112,
                    "away_pts": 108,
                    "status": "Final",
                },
                {
                    "game_id": "0022600087",
                    "game_date": "2025-12-20",
                    "home_tricode": AWAY,
                    "away_tricode": HOME,
                    "home_team": "Detroit Pistons",
                    "away_team": "Atlanta Hawks",
                    "home_pts": 105,
                    "away_pts": 110,
                    "status": "Final",
                },
            ],
            "tournament": None,
            "league": {"avg_pace": 99.46, "avg_off_rtg": 113.32},
            "missing": ["tournament_flag_tidak_dapat_ditentukan"],
            "sources": [],
            "fetched_at": JAM,
        },
        "simulation": _sim(),
        "market": {
            "slug": "nba-det-atl-2026-11-22",
            "main_total_line": 225.5,
            "main_total_volume_usd": 44048.56,
            "ladder_fetched_at": JAM,
            "ladder_warnings": [],
            "moneyline_jup": {
                "home_cents": 46.0,
                "away_cents": 55.0,
                "fetched_at": JAM,
            },
            "totals": [
                _total(225.5, "over", 47.5, 44048.56, bid=47.0, ask=48.0),
                _total(225.5, "under", 52.5, 44048.56, bid=52.0, ask=53.0),
                _total(229.5, "under", 60.0, 1200.0),
                _total(233.5, "under", 68.0, 11.0, thin=True),
                _total(237.5, "under", 75.5, 9.0, thin=True),
                _total(241.5, "under", 83.0, 8.0, thin=True),
            ],
            "spreads": [
                {
                    "line": -2.5,
                    "side": "away",
                    "team": "Pistons",
                    "price_cents": 47.5,
                    "bid_cents": 47.0,
                    "ask_cents": 48.0,
                    "mid_cents": 47.5,
                    "last_cents": 48.0,
                    "volume_usd": 2700.0,
                    "liquidity": 83247.0,
                    "price_source": "book",
                    "thin": False,
                    "market_id": "7240971",
                    "jup_estimated_cents": 48.0,
                },
                {
                    "line": -4.5,
                    "side": "home",
                    "team": "Hawks",
                    "price_cents": 33.5,
                    "bid_cents": None,
                    "ask_cents": None,
                    "mid_cents": None,
                    "last_cents": None,
                    "volume_usd": 375.0,
                    "liquidity": 5000.0,
                    "price_source": "outcome_prices",
                    "thin": False,
                    "market_id": "7240972",
                    "jup_estimated_cents": 34.0,
                },
            ],
        },
        "legs": [
            _kaki(
                "insurance", 233.5, 0.77191, 0.68, 0.70757, 68.0, 68.5, 3.30, "DISKON"
            ),
            _kaki("main", 237.5, 0.82964, 0.755, 0.77739, 75.5, 76.0, 2.29, "DISKON"),
        ],
        "injuries": {
            "sources": [SUMBER_PDF, SUMBER_ESPN],
            "n_sources": 2,
            "confirmed_both": ["Asa Newell", "Jalen Duren"],
            "entries": cedera_home + cedera_away,
            "conflicts": [
                {
                    "player": "Cade Cunningham",
                    "team_tricode": AWAY,
                    "statuses": {SUMBER_PDF: "PROBABLE", SUMBER_ESPN: "QUESTIONABLE"},
                }
            ],
            "fetched_at": JAM,
        },
        "anomalies": [
            {
                "type": "total_line_vs_model",
                "model_median_total": 219.0,
                "market_total_line": 225.5,
                "gap_points": 6.5,
                "direction": "market_lebih_tinggi",
                "kenapa_beda_required": True,
                "leg_id": None,
            },
            {
                "type": "model_vs_market",
                "p_model": 0.77191,
                "p_market": 0.68,
                "diff_points": 9.191,
                "kenapa_beda_required": True,
                "leg_id": f"{MATCH_ID}:total_under_233.5:insurance",
            },
        ],
        "price_snapshots": {
            "total_under_233.5": {"cents": 68.5, "at": JAM},
            "total_under_237.5": {"cents": 76.0, "at": JAM},
        },
    }


def _recheck(verdict="NO_GO"):
    """Laporan recheck stub (meniru out/recheck_live_det_atl.json)."""
    if verdict == "GO":
        legs = [
            {
                "leg_id": f"{MATCH_ID}:total_under_233.5:insurance",
                "verdict": "TETAP_OK",
                "reasons": [],
                "old_line": 233.5,
                "new_line": 233.5,
                "old_price_cents": 68.5,
                "new_price_cents": 68.5,
                "price_move_cents": 0.0,
                "resimulated": False,
                "probability_used": "model",
                "probability_value": 0.77191,
                "kenapa_beda": {
                    "gap_points": 6.5,
                    "triggered": True,
                    "reason_found": True,
                    "reason": "cedera_baru: Jalen Duren OUT, garis market belum bergerak",
                },
            },
            {
                "leg_id": f"{MATCH_ID}:total_under_237.5:main",
                "verdict": "TETAP_OK",
                "reasons": [],
                "old_line": 237.5,
                "new_line": 237.5,
                "old_price_cents": 76.0,
                "new_price_cents": 76.0,
                "price_move_cents": 0.0,
                "resimulated": False,
                "probability_used": "model",
                "probability_value": 0.82964,
                "kenapa_beda": {
                    "gap_points": 6.5,
                    "triggered": True,
                    "reason_found": True,
                    "reason": "cedera_baru: Jalen Duren OUT, garis market belum bergerak",
                },
            },
        ]
        return {
            "format": "nba_recheck",
            "format_version": 1,
            "match_id": MATCH_ID,
            "analysis_generated_at": JAM,
            "recheck_at": "2026-11-22T14:03:25+00:00",
            "verdict": "GO",
            "resimulated": False,
            "resim_reasons": [],
            "changes": [],
            "legs": legs,
            "anomalies": [],
            "missing": [],
            "attention": [],
            "action_required": None,
        }
    return {
        "format": "nba_recheck",
        "format_version": 1,
        "match_id": MATCH_ID,
        "analysis_generated_at": JAM,
        "recheck_at": "2026-11-22T14:03:25+00:00",
        "verdict": "NO_GO",
        "resimulated": False,
        "resim_reasons": [],
        "changes": [
            {
                "kind": "market_line",
                "detail": "selisih median model vs garis market 6.5 poin "
                "(> ambang 5); tidak ditemukan alasan konkret — "
                "probabilitas Asuransi memakai harga market",
            }
        ],
        "legs": [
            {
                "leg_id": f"{MATCH_ID}:total_under_233.5:insurance",
                "verdict": "JANGAN_PASANG",
                "reasons": [
                    "condong_ke_market: harga market 68% < 74% dan "
                    "tidak ada alasan konkret"
                ],
                "old_line": 233.5,
                "new_line": 233.5,
                "old_price_cents": 68.5,
                "new_price_cents": 68.5,
                "price_move_cents": 0.0,
                "resimulated": False,
                "probability_used": "market",
                "probability_value": 0.68,
                "kenapa_beda": {
                    "gap_points": 6.5,
                    "triggered": True,
                    "reason_found": False,
                    "reason": None,
                },
            },
            {
                "leg_id": f"{MATCH_ID}:total_under_237.5:main",
                "verdict": "TETAP_OK",
                "reasons": [],
                "old_line": 237.5,
                "new_line": 237.5,
                "old_price_cents": 76.0,
                "new_price_cents": 76.0,
                "price_move_cents": 0.0,
                "resimulated": False,
                "probability_used": "model",
                "probability_value": 0.82964,
                "kenapa_beda": {
                    "gap_points": 6.5,
                    "triggered": True,
                    "reason_found": False,
                    "reason": None,
                },
            },
        ],
        "anomalies": [],
        "missing": [],
        "attention": [],
        "action_required": "jangan pasang kaki Asuransi garis 233.5 — mesin "
        "sudah menaikkan garis ke anak tangga yang lebih aman, tapi harga "
        "marketnya tetap di bawah ambang Asuransi (74%)",
    }


class TestLaporanLengkap(unittest.TestCase):
    def setUp(self):
        self.teks = nba_report_mod.render_nba_report(_artefak())

    def test_judul_dan_semua_bagian_hadir(self):
        for judul in (
            "Laporan Laga NBA: Detroit Pistons vs Atlanta Hawks",
            "Ringkasan",
            "Data tim",
            "Pemain kunci",
            "Proyeksi total",
            "Kabar pemain",
            "Bursa & harga pasar",
            "Kaki Asuransi & Utama",
            "Lima laga terakhir",
            "Pertemuan terakhir",
            "Riwayat kandang vs tandang",
            "Simulasi 100.000 pertandingan",
            "Skenario skuad",
            "Anomali",
            "Kenapa beda?",
            "Sumber data",
        ):
            self.assertIn(judul, self.teks)

    def test_angka_simulasi_dari_fixture(self):
        # Median 219, p74 232, OT 2,74%, 100.000 ulangan, ML 54,6%.
        self.assertIn("100.000 kali", self.teks)
        self.assertIn("nilai tengah (median) 219", self.teks)
        self.assertIn("74 dari 100 ulangan totalnya di bawah 232", self.teks)
        self.assertIn("90 dari 100 ulangan totalnya antara 188 dan 251", self.teks)
        self.assertIn("2,7%", self.teks)
        self.assertIn("Atlanta Hawks 54,6%", self.teks)
        self.assertIn("110 – 109", self.teks)

    def test_proyeksi_dari_inputs_summary(self):
        self.assertIn("110,1 poin", self.teks)
        self.assertIn("108,6 poin", self.teks)
        self.assertIn("total 218,7 poin", self.teks)
        self.assertIn("1,6 poin untuk Atlanta Hawks", self.teks)
        self.assertIn("100,6 serangan", self.teks)

    def test_kaki_model_pasar_akhir_dan_label(self):
        self.assertIn("Kaki Asuransi — Under 233,5", self.teks)
        self.assertIn("77,2%", self.teks)
        self.assertIn("68,0%", self.teks)
        self.assertIn("70,8%", self.teks)
        self.assertIn("DISKON", self.teks)
        self.assertIn("PEMBANDING_KALSHI", self.teks)
        self.assertIn("Kaki Utama — Under 237,5", self.teks)
        self.assertIn("83,0%", self.teks)
        self.assertIn("75,5%", self.teks)
        self.assertIn("77,7%", self.teks)
        self.assertIn("14,5 poin di atas median model", self.teks)
        self.assertIn("8 poin di atas garis market", self.teks)

    def test_data_tim_statistik_dan_rekor(self):
        self.assertIn("113,1 poin per 100 serangan", self.teks)
        self.assertIn("Di kandang: 4 menang – 3 kalah", self.teks)
        self.assertIn("rata-rata cetak 119 poin, kebobolan 119,3 poin", self.teks)
        self.assertIn("Di tandang: 6 menang – 3 kalah", self.teks)
        self.assertIn("Istirahat 1 hari", self.teks)

    def test_pemain_kunci_diurutkan_menit_dan_top5(self):
        # Cade Cunningham (35,0 menit) pertama di DET; pemain keenam
        # ATL (15,0 menit) tidak tampil karena hanya top 5.
        self.assertIn("Cade Cunningham: rating +5,1, main 35 menit per laga", self.teks)
        self.assertIn("Jalen Johnson: rating +2,6, main 34,8 menit per laga", self.teks)
        self.assertIn("angka sudah disesuaikan ke musim lalu", self.teks)
        self.assertNotIn("Pemain Keenam", self.teks)
        # Duren OUT ditandai di daftar pemain kunci.
        self.assertIn("Jalen Duren: rating +5,6, main 26,7 menit per laga", self.teks)
        self.assertIn("TIDAK MAIN", self.teks)

    def test_form5_dan_h2h(self):
        self.assertIn("5 laga terakhir: 3 menang, 2 kalah", self.teks)
        self.assertIn("5 laga terakhir: 2 menang, 3 kalah", self.teks)
        self.assertIn("20 Nov 2026, kandang vs CHA: menang 111–97", self.teks)
        self.assertIn("DET 108 – 112 ATL", self.teks)
        self.assertIn(
            "Atlanta Hawks menang 1 kali, Detroit Pistons menang 1 kali", self.teks
        )

    def test_cedera_rest_dan_konflik(self):
        self.assertIn("Jalen Duren (DET): tidak main.", self.teks)
        self.assertIn("cedera (Injury/Illness - Right Hamstring Strain)", self.teks)
        self.assertIn("Pemain Cadangan (DET): tidak main.", self.teks)
        self.assertIn("istirahat (Rest)", self.teks)
        self.assertIn("Pemain Two-Way (DET): tidak main.", self.teks)
        self.assertIn("tugas liga pengembangan (G League - Two-Way)", self.teks)
        self.assertIn("Cade Cunningham (DET): belum pasti tampil.", self.teks)
        self.assertIn("Konflik status — Cade Cunningham", self.teks)
        self.assertIn("Official NBA Injury Report bilang PROBABLE", self.teks)
        self.assertIn("ESPN bilang QUESTIONABLE", self.teks)
        self.assertIn("Asa Newell, Jalen Duren", self.teks)

    def test_market_garis_spread_moneyline_tangga(self):
        self.assertIn("Garis total utama (paling banyak dipasang): 225,5", self.teks)
        self.assertIn("$44.049", self.teks)
        self.assertIn("Harga Over 225,5: 47,5¢ (tawar 47¢ / minta 48¢)", self.teks)
        self.assertIn("Spread paling cair: Pistons -2,5 (47,5¢)", self.teks)
        self.assertIn("Harga menang/kalah di jup.ag: Atlanta Hawks 46¢", self.teks)
        self.assertIn("Under 233,5: 68¢, volume $11 — pasar tipis", self.teks)

    def test_skenario_skuad(self):
        self.assertIn("Semua pemain tersedia", self.teks)
        self.assertIn("Peluang Under 233,5 (Asuransi): 74,1%", self.teks)
        self.assertIn("1 pemain inti kandang tambahan absen", self.teks)
        self.assertIn(
            "Tambahan absen (di atas pemain yang memang sudah absen): "
            "Jalen Johnson.",
            self.teks,
        )
        self.assertIn("Semua pemain yang diragukan ikut absen", self.teks)
        self.assertIn("Cade Cunningham", self.teks)
        self.assertIn("Peluang Under 237,5 (Utama): 85,0%", self.teks)

    def test_sumber_dan_waktu_tercatat(self):
        self.assertIn("stats.nba.com, jenjang 1, 22 Nov 2026 14:03 UTC", self.teks)
        self.assertIn("Basketball-Reference, jenjang 2", self.teks)
        self.assertIn("Polymarket CLOB, jenjang 2", self.teks)
        self.assertIn("Harga pertama total_under_233.5: 68,5¢", self.teks)

    def test_anomali_diterjemahkan(self):
        self.assertIn("berbeda 6,5 poin", self.teks)
        self.assertIn("market mengharap total lebih tinggi dari model", self.teks)
        self.assertIn("berbeda 9,2 poin (model 77,2%, pasar 68,0%)", self.teks)


class TestBagianBerita(unittest.TestCase):
    """Penyisipan bagian Berita ke laporan (integrasi koordinator)."""

    def test_berita_tampil_bila_blok_news_ada(self):
        art = _artefak()
        art["news"] = {
            "status": "ok",
            "items": [
                {
                    "headline": "Bulls G Norman Powell sidelined",
                    "description": "Hamstring injury.",
                    "source": "ESPN",
                    "published": "2026-11-23T03:15:00Z",
                    "url": "https://www.espn.com/contoh",
                    "type": "HeadlineNews",
                }
            ],
        }
        teks = nba_report_mod.render_nba_report(art)
        self.assertIn("Berita", teks)
        self.assertIn("Bulls G Norman Powell sidelined", teks)
        self.assertIn("bukan angka", teks)

    def test_tanpa_blok_news_judul_tetap_hadir_dengan_penjelasan(self):
        # Artefak lama (tanpa kunci news): bagian tetap hadir, jujur
        # bahwa berita tidak tersedia di artefak itu.
        teks = nba_report_mod.render_nba_report(_artefak())
        self.assertIn("Berita", teks)
        self.assertIn("sebelum modul berita ada", teks)


class TestKenapaBeda(unittest.TestCase):
    def test_terpicu_selisih_9_poin_kesimpulan_tidak_ada_alasan(self):
        teks = nba_report_mod.render_nba_report(_artefak())
        self.assertIn("## Kenapa beda?", teks)
        self.assertIn("Kaki Asuransi — Under 233,5", teks)
        self.assertIn("selisih 9,2 poin", teks)
        self.assertIn("Cedera: 4 pemain tidak main/diragukan", teks)
        self.assertIn("Pergerakan harga: tidak terverifikasi", teks)
        self.assertIn(
            "Kesimpulan: tidak ditemukan alasan konkret dari data yang ada",
            teks,
        )

    def test_tidak_terpicu_bila_selisih_kecil_dan_tanpa_anomali(self):
        artefak = _artefak()
        # Selisih model-pasar 2,2 dan 2,0 poin (< 8); median vs garis
        # market 1,5 poin; tanpa anomali kenapa_beda_required.
        artefak["legs"][0]["p_market"] = 0.75
        artefak["legs"][1]["p_market"] = 0.81
        artefak["market"]["main_total_line"] = 220.5
        artefak["anomalies"] = []
        teks = nba_report_mod.render_nba_report(artefak)
        self.assertNotIn("Kenapa beda?", teks)

    def test_alasan_konkret_dari_recheck_dikutip(self):
        teks = nba_report_mod.render_nba_report(_artefak(), recheck=_recheck("GO"))
        self.assertIn("alasan konkret ditemukan (dari cek ulang)", teks)
        self.assertIn("Jalen Duren OUT", teks)


class TestDataIncomplete(unittest.TestCase):
    def _minimal(self):
        return {
            "format": "nba_analysis",
            "format_version": 1,
            "match_id": MATCH_ID,
            "home_tricode": HOME,
            "away_tricode": AWAY,
            "game_date": TANGGAL,
            "start_time": None,
            "generated_at": JAM,
            "status": "DATA_INCOMPLETE",
            "missing": ["inputs_gagal: semua_sumber_gagal"],
            "sources": [],
            "inputs": None,
            "simulation": None,
            "market": None,
            "legs": [],
            "injuries": {
                "sources": [],
                "n_sources": 0,
                "confirmed_both": [],
                "entries": [],
                "conflicts": [],
                "fetched_at": None,
            },
            "anomalies": [],
            "price_snapshots": {},
        }

    def test_spanduk_dan_tidak_ada_tebakan(self):
        teks = nba_report_mod.render_nba_report(self._minimal())
        self.assertIn("DATA TIDAK LENGKAP", teks)
        self.assertIn("belum bisa dipakai untuk memasang tiket", teks)
        self.assertIn("inputs_gagal: semua_sumber_gagal", teks)
        self.assertIn("Proyeksi total model: tidak terverifikasi", teks)
        self.assertIn("Data bursa: tidak terverifikasi", teks)
        self.assertIn("Simulasi: tidak terverifikasi", teks)
        self.assertIn("Tidak ada kaki Asuransi/Utama di artefak", teks)
        self.assertIn("Yang belum bisa dipastikan", teks)

    def test_json_mencatat_celah(self):
        data = nba_report_mod.render_nba_report_json(self._minimal())
        self.assertEqual(data["format"], "nba_report")
        self.assertEqual(data["status"], "DATA_INCOMPLETE")
        self.assertTrue(
            any("tidak terverifikasi" in c for c in data["tidak_terverifikasi"])
        )


class TestKekuranganArtefak(unittest.TestCase):
    def test_h2h_kosong_tidak_terverifikasi(self):
        artefak = _artefak()
        artefak["inputs"]["h2h_last5"] = []
        teks = nba_report_mod.render_nba_report(artefak)
        self.assertIn("5 pertemuan terakhir: tidak terverifikasi", teks)
        data = nba_report_mod.render_nba_report_json(artefak)
        self.assertIn(
            "5 pertemuan terakhir: tidak terverifikasi.", data["tidak_terverifikasi"]
        )

    def test_kaki_tidak_memenuhi_tanpa_garis(self):
        artefak = _artefak()
        artefak["legs"][0] = {
            "leg_id": f"{MATCH_ID}:total_under_none:insurance",
            "market_type": "total_under",
            "line": None,
            "ticket": "insurance",
            "p_model": None,
            "p_market": None,
            "comparison_source": None,
            "p_final": None,
            "price_cents": None,
            "jup_estimated_cents": None,
            "ev_pct": None,
            "price_label": None,
            "cushion_vs_median_points": None,
            "cushion_vs_market_points": None,
            "meets": False,
            "reason": "tidak_ada_garis_memenuhi",
            "fetched_at": JAM,
        }
        teks = nba_report_mod.render_nba_report(artefak)
        self.assertIn("Kaki Asuransi — tanpa garis", teks)
        self.assertIn("tidak memenuhi syarat", teks)
        self.assertIn("tidak_ada_garis_memenuhi", teks)

    def test_tanpa_pembanding_pasar_model_only(self):
        artefak = _artefak()
        artefak["legs"][0]["p_market"] = None
        artefak["legs"][0]["comparison_source"] = None
        artefak["legs"][0]["p_final"] = 0.77191
        artefak["legs"][1]["p_market"] = None
        artefak["legs"][1]["comparison_source"] = None
        artefak["legs"][1]["p_final"] = 0.82964
        artefak["anomalies"] = []
        teks = nba_report_mod.render_nba_report(artefak)
        self.assertIn("Tidak ada pembanding pasar untuk garis ini (MODEL_ONLY)", teks)
        # Tanpa p_market, "Kenapa beda?" tidak terpicu untuk kaki itu.
        self.assertNotIn("selisih 9,2 poin", teks)


class TestRecheck(unittest.TestCase):
    def test_no_go_dengan_action_required(self):
        teks = nba_report_mod.render_nba_report(_artefak(), recheck=_recheck("NO_GO"))
        self.assertIn("## Cek ulang sebelum pasang", teks)
        self.assertIn("Putusan: JANGAN PASANG.", teks)
        self.assertIn("Kaki Asuransi — Under 233,5", teks)
        self.assertIn("Putusan: Jangan pasang.", teks)
        self.assertIn("condong_ke_market: harga market 68% < 74%", teks)
        self.assertIn("Peluang yang dipakai untuk putusan: 68,0% (dari market).", teks)
        self.assertIn("Kaki Utama — Under 237,5", teks)
        self.assertIn("Putusan: Tetap OK.", teks)
        self.assertIn(
            "Yang harus dilakukan: jangan pasang kaki Asuransi garis 233.5 "
            "— mesin sudah menaikkan garis ke anak tangga yang lebih aman, "
            "tapi harga marketnya tetap di bawah ambang Asuransi (74%).",
            teks,
        )
        self.assertIn("selisih median model vs garis market 6.5 poin", teks)

    def test_verdict_tanda_hubung_juga_diterima(self):
        # "NO-GO" (tanda hubung) diterima sebagai alias "NO_GO" skema.
        recheck = _recheck("NO_GO")
        recheck["verdict"] = "NO-GO"
        teks = nba_report_mod.render_nba_report(_artefak(), recheck=recheck)
        self.assertIn("Putusan: JANGAN PASANG.", teks)

    def test_go_tanpa_action_required(self):
        teks = nba_report_mod.render_nba_report(_artefak(), recheck=_recheck("GO"))
        self.assertIn("Putusan: BOLEH PASANG.", teks)
        self.assertIn("Tidak ada tindakan khusus.", teks)
        self.assertIn("Tidak ada perubahan sejak analisis awal.", teks)

    def test_recheck_laga_beda_value_error(self):
        recheck = _recheck("GO")
        recheck["match_id"] = "BOS@LAL_2026-11-20"
        with self.assertRaises(ValueError):
            nba_report_mod.render_nba_report(_artefak(), recheck=recheck)

    def test_recheck_bukan_format_recheck_value_error(self):
        recheck = _recheck("GO")
        recheck["format"] = "nba_analysis"
        with self.assertRaises(ValueError):
            nba_report_mod.render_nba_report(_artefak(), recheck=recheck)


class TestStrukturJsonDanValidasi(unittest.TestCase):
    def test_json_sama_dengan_teks(self):
        artefak = _artefak()
        data = nba_report_mod.render_nba_report_json(artefak)
        self.assertEqual(data["format"], "nba_report")
        self.assertEqual(data["format_version"], 1)
        self.assertEqual(data["match_id"], MATCH_ID)
        self.assertEqual(data["status"], "OK")
        self.assertEqual(data["text"], nba_report_mod.render_nba_report(artefak))
        judul = [s["heading"] for s in data["sections"]]
        self.assertIn("Ringkasan", judul)
        self.assertIn("Simulasi 100.000 pertandingan", judul)
        self.assertTrue(all(isinstance(s["lines"], list) for s in data["sections"]))
        # Daftar celah: turnamen + total proyeksi skenario.
        self.assertIn(
            "Status turnamen: tidak terverifikasi.", data["tidak_terverifikasi"]
        )

    def test_analysis_bukan_dict_value_error(self):
        with self.assertRaises(ValueError):
            nba_report_mod.render_nba_report("bukan dict")
        with self.assertRaises(ValueError):
            nba_report_mod.render_nba_report(_artefak(), recheck="bukan dict")

    def test_fixture_tidak_diubah_render(self):
        artefak = _artefak()
        salinan = copy.deepcopy(artefak)
        nba_report_mod.render_nba_report(artefak, recheck=_recheck("NO_GO"))
        self.assertEqual(artefak, salinan)


def _artefak_tahap4(penilaian="wajar"):
    """Artefak Tahap 4: analisis_wajar + field baru di kaki.

    Angka meniru hasil SESUDAH DET@ATL 2026-11-22 dari
    scripts/bandingkan_racik.py (bantalan 9,36; Utama 237,5 naik
    tangga dari 235,5; Asuransi 249,5) — kecuali kaki Asuransi
    fixture tetap 233,5 agar tes render tidak bergantung pada
    seleksi ulang (yang diuji di test_nba_analysis).
    """
    artefak = _artefak()
    artefak["analisis_wajar"] = {
        "acuan_sim": 219.0,
        "garis_market": 225.5,
        "garis_harga": 237.5,
        "harga_cents": 76.0,
        "jarak_poin": 18.5,
        "bantalan_dibutuhkan_poin": 9.36,
        "penilaian": penilaian,
        "penjelasan": (
            "Acuan analisis 219 poin (garis bandar 225,5); harga 76¢ "
            "duduk di garis 237,5 — jaraknya 18,5 poin dari acuan, "
            "sementara statistik meminta bantalan 9,36 poin."
        ),
    }
    alasan = (
        "Bantalan 9,36 poin karena sebaran simulasi biasa "
        "(simpangan baku 19,46 poin), kekuatan serang kedua tim "
        "biasa saja, dan skor 5 laga terakhir biasa saja."
    )
    asuransi, utama = artefak["legs"]
    asuransi.update(
        {
            "cushion_points": 9.36,
            "cushion_reason": alasan,
            "volume_usd": 270.0,
            "thin": False,
            "climb": None,
        }
    )
    utama.update(
        {
            "cushion_points": 9.36,
            "cushion_reason": alasan,
            "volume_usd": 6.3,
            "thin": True,
            "climb": {
                "from_line": 235.5,
                "to_line": 237.5,
                "rungs": 1,
                "reason": "harga_minimum",
            },
        }
    )
    return artefak


def _bagian(data, judul):
    """Satu bagian laporan dari dict JSON berdasarkan judul."""
    for bagian in data["sections"]:
        if bagian["heading"] == judul:
            return bagian
    return None


class TestTahap4GarisBandarDanBantalan(unittest.TestCase):
    def test_bagian_garis_bandar_wajar(self):
        data = nba_report_mod.render_nba_report_json(_artefak_tahap4())
        judul = [s["heading"] for s in data["sections"]]
        # Bagian baru langsung setelah Ringkasan (laporan mulai dari
        # garis bandar).
        self.assertEqual(judul[1], "Ringkasan")
        self.assertEqual(judul[2], "Garis bandar — wajar atau tidak?")
        bagian = _bagian(data, "Garis bandar — wajar atau tidak?")
        teks = "\n".join(bagian["lines"])
        self.assertIn("225,5", teks)
        self.assertIn("219", teks)
        self.assertIn("237,5", teks)
        self.assertIn("76¢", teks)
        self.assertIn("18,5", teks)
        self.assertIn("9,36", teks)
        self.assertIn("WAJAR", teks)
        self.assertIn("Acuan analisis 219 poin", teks)

    def test_bagian_kaki_alasan_bantalan_volume_climb(self):
        data = nba_report_mod.render_nba_report_json(_artefak_tahap4())
        bagian = _bagian(data, "Kaki Asuransi & Utama")
        teks = "\n".join(bagian["lines"])
        # Alasan analis ditampilkan apa adanya (tanpa "karena" ganda).
        self.assertIn("Bantalan 9,36 poin karena sebaran simulasi biasa", teks)
        self.assertNotIn("karena Bantalan 9,36", teks)
        self.assertIn("Volume garis ini: $270", teks)
        self.assertIn("Volume garis ini: $6", teks)
        self.assertIn("pasar TIPIS", teks)
        self.assertIn(
            "Garis naik tangga dari 235,5 ke 237,5 karena harga di bawah minimum",
            teks,
        )

    def test_penjelasan_volume_per_garis(self):
        # Transparansi volume (keputusan user 12:38 WIB 2026-11-23):
        # satu kalimat menjelaskan volume laga tersebar di ratusan
        # garis sehingga garis jauh tipis — mesin mengecek volume
        # PER GARIS, bukan volume laga.
        data = nba_report_mod.render_nba_report_json(_artefak_tahap4())
        bagian = _bagian(data, "Kaki Asuransi & Utama")
        teks = "\n".join(bagian["lines"])
        self.assertIn(
            "Catatan volume: volume satu laga tersebar di ratusan "
            "garis, sehingga garis yang jauh dari garis bandar hanya "
            "ditawar segelintir orang dan harganya kurang bisa "
            "dipercaya — garis seperti itu disebut volume tipis.",
            teks,
        )

    def test_artefak_lama_tanpa_analisis_wajar_tidak_crash(self):
        # Fixture lama (_artefak tanpa field Tahap 4): bagian garis
        # bandar menulis "tidak terverifikasi", kaki tanpa alasan
        # bantalan, render tidak crash.
        data = nba_report_mod.render_nba_report_json(_artefak())
        bagian = _bagian(data, "Garis bandar — wajar atau tidak?")
        self.assertIsNotNone(bagian)
        teks = "\n".join(bagian["lines"])
        self.assertIn("tidak terverifikasi", teks)
        self.assertIn(
            "Penilaian wajar garis bandar: tidak terverifikasi.",
            data["tidak_terverifikasi"],
        )
        kaki = _bagian(data, "Kaki Asuransi & Utama")
        teks_kaki = "\n".join(kaki["lines"])
        self.assertNotIn("Bantalan +", teks_kaki)
        self.assertIn(
            "Alasan bantalan adaptif: tidak tercatat di artefak "
            "(artefak lama atau analis belum tersedia).",
            data["tidak_terverifikasi"],
        )

    def test_penilaian_di_bawah_wajar(self):
        data = nba_report_mod.render_nba_report_json(
            _artefak_tahap4(penilaian="di_bawah_wajar")
        )
        bagian = _bagian(data, "Garis bandar — wajar atau tidak?")
        teks = "\n".join(bagian["lines"])
        self.assertIn("DI BAWAH WAJAR", teks)
        self.assertNotIn("Penilaian mesin: WAJAR", teks)

    def test_penilaian_tidak_terverifikasi(self):
        data = nba_report_mod.render_nba_report_json(
            _artefak_tahap4(penilaian="tidak_terverifikasi")
        )
        bagian = _bagian(data, "Garis bandar — wajar atau tidak?")
        teks = "\n".join(bagian["lines"])
        self.assertIn("belum bisa dinilai (tidak terverifikasi)", teks)
        self.assertIn(
            "Penilaian wajar garis bandar: tidak terverifikasi.",
            data["tidak_terverifikasi"],
        )

    def test_utama_tanpa_asuransi_peringatan_laga(self):
        artefak = _artefak_tahap4()
        asuransi = artefak["legs"][0]
        asuransi.update(
            {
                "line": None,
                "meets": False,
                "reason": "tidak_ada_garis_lolos: volume_tipis",
                "p_model": None,
                "p_final": None,
                "ev_pct": None,
                "price_label": None,
                "leg_id": f"{MATCH_ID}:total_under_none:insurance",
            }
        )
        data = nba_report_mod.render_nba_report_json(artefak)
        bagian = _bagian(data, "Kaki Asuransi & Utama")
        teks = "\n".join(bagian["lines"])
        self.assertIn(
            "PERHATIAN: kaki Utama memenuhi syarat tapi kaki Asuransi "
            "tidak — laga ini tidak punya pelindung.",
            teks,
        )

    def test_tanpa_peringatan_bila_kedua_kaki_ok(self):
        data = nba_report_mod.render_nba_report_json(_artefak_tahap4())
        bagian = _bagian(data, "Kaki Asuransi & Utama")
        teks = "\n".join(bagian["lines"])
        self.assertNotIn("PERHATIAN", teks)


class TestSkenarioPanas(unittest.TestCase):
    """Bagian 'Skenario panas' di laporan (perbaikan pasca-Denver).

    Angka ekspektasi dihitung tangan dari CDF fixture (garis 219 ->
    0,5; 233,5 -> 0,77191; 237,5 -> 0,82964; interpolasi linear).
    """

    def test_hitung_otomatis_dari_artefak(self):
        teks = nba_report_mod.render_nba_report(_artefak())
        self.assertIn("Skenario panas", teks)
        # Geser dari config (8,50 / 12,52 — KOREKSI kontaminasi
        # 2026-11-23, worker B; sebelumnya 13,54 / 17,54) + setan
        # 18,07 (tidak berubah) + konservatif (225,5-219).
        # Penyimpangan dinyatakan vs garis bandar (permintaan user
        # 12:33 WIB).
        self.assertIn("dari garis bandar 225,5", teks)
        self.assertIn("banjir tripoin +8,50 poin", teks)
        self.assertIn("banjir lemparan bebas +12,52 poin", teks)
        self.assertIn("deviasi maksimal (setan tripoin) +18,07 poin", teks)
        self.assertIn("konservatif (selaras garis market) +6,50 poin", teks)
        self.assertIn("Skenario banjir terburuk: banjir lemparan bebas.", teks)
        # Under 233,5: CDF(233,5-8,50)=CDF(225,0)=61,3%;
        # CDF(233,5-12,52)=CDF(220,98)=53,7%;
        # CDF(233,5-6,5)=CDF(227)=65,0%;
        # setan CDF(233,5-18,07)=CDF(215,43) dijepit ke 50,0%.
        self.assertIn(
            "Under 233,5 (Asuransi, 68¢): normal 77,2%; banjir tripoin "
            "61,3%; banjir lemparan bebas 53,7%; konservatif 65,0%; "
            "setan 50,0%.",
            teks,
        )
        self.assertIn("TIDAK tahan banjir", teks)
        self.assertIn("1 dari 10 laga terpanas", teks)
        # Flag setan v18: kaki Asuransi TIDAK lagi berflag — normal
        # 77,2% < target Asuransi v18 82,0% (di v17 targetnya 74%,
        # jadi berflag). Flag kini di kaki Utama: normal 83,0% >=
        # target Utama 74,0% tapi setan 50,8% < 74%. ("FLAG SETAN"
        # muncul 2x di teks: 1 baris flag + 1 penyebutan di catatan
        # kaki — yang dihitung di sini baris flagnya.)
        self.assertEqual(teks.count("FLAG SETAN: kaki ini lolos normal"), 1)
        self.assertIn("lolos normal (83,0%)", teks)
        self.assertIn("setan 50,8%", teks)
        self.assertNotIn("lolos normal (77,2%)", teks)
        # Tidak ada garis tahan-setan di tangga fixture (garis tertinggi
        # 241,5 -> CDF(223,43)=58,3% < 74%).
        self.assertIn("Tidak ada garis tahan setan", teks)
        self.assertIn("tidak ada garis tahan-setan", teks)
        # v18: TIDAK ADA garis tahan banjir untuk kedua kaki — target
        # Utama naik 0,65 -> 0,74, sehingga garis tertinggi 241,5
        # (P banjir FT 69,6% < 74%) tidak lagi tahan (di v17 garis
        # itu tahan dengan target 65% — "16 poin di atas bandar").
        self.assertIn("Tidak ada garis tahan banjir", teks)
        self.assertNotIn("Garis tahan banjir itu 16 poin", teks)

    def test_membaca_stress_tersimpan_bila_ada(self):
        artefak = _artefak()
        artefak["stress"] = {
            "format": "nba_stress",
            "format_version": 1,
            "skenario": {
                "banjir_3p": {"geser_points": 20.0},
                "banjir_ft": {"geser_points": 10.0},
                "konservatif": {"geser_points": 1.0},
            },
            "banjir_terburuk": "banjir_3p",
            "kaki": [
                {
                    "line": 240.5,
                    "ticket": "insurance",
                    "price_cents": 85.0,
                    "target_probability": 0.74,
                    "p_under": {
                        "normal": 0.9,
                        "banjir_3p": 0.8,
                        "banjir_ft": 0.85,
                        "konservatif": 0.88,
                    },
                    "tahan_banjir": True,
                    "garis_tahan_banjir": {
                        "line": 240.5,
                        "price_cents": 85.0,
                        "jup_estimated_cents": 85.5,
                        "thin": True,
                        "volume_usd": None,
                    },
                }
            ],
            "cek_harga": [
                {
                    "harga_cents": 94.0,
                    "line": 250.5,
                    "p_under": {"banjir_3p": 0.92},
                }
            ],
        }
        teks = nba_report_mod.render_nba_report(artefak)
        # Nilai tersimpan dipakai, bukan hitung otomatis (20, bukan
        # 8,50 — _fmt_poin memangkas nol di belakang koma) — membuktikan
        # jalur baca-artefak.
        self.assertIn("banjir tripoin +20 poin", teks)
        self.assertIn("Skenario banjir terburuk: banjir tripoin.", teks)
        self.assertIn(
            "Under 240,5 (Asuransi, 85¢): normal 90,0%; banjir tripoin "
            "80,0%; banjir lemparan bebas 85,0%; konservatif 88,0%.",
            teks,
        )
        self.assertIn("Tahan banjir (target 74,0% tercapai", teks)
        self.assertIn(
            "Garis tahan banjir: 240,5 (85¢, jup.ag ~85,5¢) "
            "— PERHATIAN: volume garis ini tipis (volume tidak tercatat).",
            teks,
        )
        # Deviasi garis tahan vs garis bandar juga dirender dari
        # stress tersimpan: 240,5 - 225,5 = 15 poin.
        self.assertIn(
            "Garis tahan banjir itu 15 poin di atas garis bandar 225,5.",
            teks,
        )
        self.assertIn(
            "Di harga 94¢ (garis 250,5): kalau banjir terburuk, "
            "peluang Under 92,0%.",
            teks,
        )

    def test_setan_per_pemain_dirender_bila_ada(self):
        # Field setan per pemain (diisi worker setan-pemain, per
        # kaki di hasil stress) dirender sekali: total + deviasi
        # vs garis bandar.
        artefak = _artefak()
        artefak["stress"] = {
            "format": "nba_stress",
            "format_version": 1,
            "skenario": {
                "banjir_3p": {"geser_points": 8.5},
                "banjir_ft": {"geser_points": 12.52},
            },
            "banjir_terburuk": "banjir_ft",
            "kaki": [
                {
                    "line": 233.5,
                    "ticket": "insurance",
                    "price_cents": 68.0,
                    "target_probability": 0.74,
                    "p_under": {"normal": 0.772},
                    "tahan_banjir": False,
                    "total_setan_pemain": 261.5,
                    "deviasi_setan_pemain_dari_garis_bandar": 36.0,
                }
            ],
        }
        teks = nba_report_mod.render_nba_report(artefak)
        self.assertIn(
            "Setan per pemain (kalau semua pemain panas bareng): "
            "total bisa sampai 261,5 poin, 36 poin di atas garis "
            "bandar 225,5.",
            teks,
        )

    def test_setan_per_pemain_dilewati_bila_tidak_ada(self):
        # Tanpa field setan per pemain, barisnya dilewati (bukan
        # error, bukan angka karangan) — artefak lama tetap render.
        teks = nba_report_mod.render_nba_report(_artefak())
        self.assertNotIn("Setan per pemain", teks)


class TestEquilibriumSkip(unittest.TestCase):
    """Bagian baru 'Titik equilibrium dan skip dari awal'.

    SEMUA laga dilaporkan, termasuk yang di-skip beserta alasannya
    (keputusan user 2026-11-23 10:41 WIB).
    """

    def test_bagian_hadir_dan_skip_tanpa_equilibrium_v18_1(self):
        # v18.1 (MEMBALIK test_bagian_hadir_dan_skip_pola_denver):
        # fixture _artefak() (tangga terpotong di 241,5, semua garis
        # alt thin, tanpa garis tahan banjir) — pola Denver TIDAK
        # lagi cocok: syarat (1)-(3) benar tapi EV acuan U237,5
        # +2,3% > -1% (di v18 edge +1,7% < 3,5% membuat syarat (4)
        # benar). Laga TETAP DI-SKIP via (a) tidak_ada_equilibrium
        # (Asuransi terikat EV, Utama terikat eksekusi). OT kini
        # EMPIRIS (5,70%, ambang 8,5%).
        teks = nba_report_mod.render_nba_report(_artefak())
        self.assertIn("Titik equilibrium dan skip dari awal", teks)
        self.assertIn(
            "Laga ini DI-SKIP dari kedua tiket — tidak masuk Asuransi " "maupun Utama.",
            teks,
        )
        self.assertIn("Alasan: tidak ada equilibrium di kedua tiket", teks)
        self.assertNotIn("pola Denver:", teks)
        self.assertIn("Pola Denver: tidak cocok", teks)
        self.assertIn("EV garis acuan tidak kecil (+2,3%)", teks)
        self.assertIn("Tidak ada titik equilibrium Asuransi:", teks)
        self.assertIn("ev_di_bawah_minimum", teks)
        self.assertIn("Tidak ada titik equilibrium Utama:", teks)
        self.assertIn("eksekusi_tidak_lolos", teks)
        self.assertIn("bid/ask tidak tercatat", teks)
        self.assertIn(
            "Peluang overtime menurut data empiris: 5,70% (ambang skip "
            "8,5%) — di bawah ambang.",
            teks,
        )
        self.assertNotIn("Pola Denver: COCOK", teks)

    def test_varian_pola_cocok_ev_kecil(self):
        # Varian COCOK (cabang laporan "Pola Denver: COCOK" tetap
        # teruji di v18.1): harga acuan U237,5 dinaikkan ke 79,5¢
        # jup -> EV -2,2% < -1% -> keempat syarat benar -> pola
        # COCOK (pagar tidak berlaku: tidak ada garis lolos gate).
        # Skip via (a) + pola.
        artefak = copy.deepcopy(_artefak())
        for entri in artefak["market"]["totals"]:
            if entri["line"] == 237.5:
                entri["price_cents"] = 79.0
                entri["jup_estimated_cents"] = 79.5
        teks = nba_report_mod.render_nba_report(artefak)
        self.assertIn("Pola Denver: COCOK", teks)
        self.assertIn("pola Denver:", teks)
        self.assertIn("LAGA INI DI-SKIP dari kedua tiket:", teks)

    def test_spanduk_skip_di_ringkasan(self):
        # Spanduk skip muncul di Ringkasan (bukan hanya di bagian
        # baru) supaya pembaca langsung tahu laga ini tidak masuk
        # tiket mana pun. v18.1: spanduk hanya menyebut (a) —
        # pola tidak cocok (EV acuan +2,3%), jadi tidak ada alasan
        # pola di ringkasan.
        teks = nba_report_mod.render_nba_report(_artefak())
        ringkasan = teks.split("## Garis bandar")[0]
        self.assertIn("LAGA INI DI-SKIP dari kedua tiket:", ringkasan)
        self.assertIn("tidak ada equilibrium di kedua tiket", ringkasan)
        self.assertNotIn("pola Denver", ringkasan)

    def test_varian_pola_mati_tapi_tetap_skip_tanpa_equilibrium(self):
        # Tangga diperpanjang dengan garis tahan banjir TIDAK tipis
        # (249,5 @92¢, 251,5 @94¢) -> syarat pola (2) mati -> pola
        # TIDAK cocok. v18: laga TETAP DI-SKIP via (a)
        # tidak_ada_equilibrium (Asuransi terikat EV, Utama terikat
        # eksekusi) — pemicu (a) independen dari pola. Di v17 laga
        # ini tidak di-skip karena equilibrium Utama ada.
        artefak = copy.deepcopy(_artefak())
        artefak["market"]["totals"].extend(
            [
                _total(249.5, "under", 92.0, 500.0),
                _total(251.5, "under", 94.0, 500.0),
            ]
        )
        teks = nba_report_mod.render_nba_report(artefak)
        self.assertIn("LAGA INI DI-SKIP dari kedua tiket:", teks)
        self.assertIn("tidak ada equilibrium di kedua tiket", teks)
        self.assertNotIn("Pola Denver: COCOK", teks)
        self.assertIn("Pola Denver: tidak cocok", teks)
        self.assertIn("ev_di_bawah_minimum", teks)

    def test_json_memuat_bagian_equilibrium_skip(self):
        data = nba_report_mod.render_nba_report_json(_artefak())
        judul = [b["heading"] for b in data["sections"]]
        self.assertIn("Titik equilibrium dan skip dari awal", judul)
        bagian = next(
            b
            for b in data["sections"]
            if b["heading"] == "Titik equilibrium dan skip dari awal"
        )
        isi = " ".join(bagian["lines"])
        self.assertIn("DI-SKIP", isi)
        # v18.1: pola tidak cocok (EV acuan +2,3%) — baris pola
        # tetap hadir dengan alasan per syarat.
        self.assertIn("Pola Denver: tidak cocok", isi)
        self.assertIn("EV garis acuan tidak kecil", isi)

    def test_minimal_tidak_crash(self):
        # Artefak DATA_INCOMPLETE tanpa simulation/market/legs ->
        # bagian tetap dirender dengan "tidak bisa dinilai", bukan
        # crash dan bukan tebak.
        minimal = {
            "format": "nba_analysis",
            "format_version": 1,
            "match_id": MATCH_ID,
            "home_tricode": HOME,
            "away_tricode": AWAY,
            "game_date": TANGGAL,
            "start_time": None,
            "generated_at": JAM,
            "status": "DATA_INCOMPLETE",
            "missing": ["inputs_gagal: semua_sumber_gagal"],
            "sources": [],
            "inputs": None,
            "simulation": None,
            "market": None,
            "legs": [],
            "injuries": {
                "sources": [],
                "n_sources": 0,
                "confirmed_both": [],
                "entries": [],
                "conflicts": [],
                "fetched_at": None,
            },
            "anomalies": [],
            "price_snapshots": {},
        }
        teks = nba_report_mod.render_nba_report(minimal)
        self.assertIn("Titik equilibrium dan skip dari awal", teks)
        self.assertIn("tidak bisa dinilai", teks)
        self.assertNotIn("LAGA INI DI-SKIP", teks)


if __name__ == "__main__":
    unittest.main()
