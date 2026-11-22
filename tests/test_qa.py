"""Tes engine/qa.py — tanya-jawab soal laga/analisis NBA. SEMUA offline.

Artefak fixture dirakit dari simulasi NYATA (nba_sim.simulate, iterasi
kecil, seed 7) + kaki/anomali dari fungsi engine asli (devig.blend,
price_labels, anomaly) supaya artefak konsisten dengan dirinya sendiri.
Sim ulang di tes memakai iterations kecil lewat argumen iterations=
pada answer() (default produksi 20.000 — lihat qa.RESIM_ITERATIONS).
0 kredit Odds API; tidak ada tulis ke out/ atau data/.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine import anomaly as anomaly_mod
from engine import devig as devig_mod
from engine import nba_sim as nba_sim_mod
from engine import price_labels as price_labels_mod
from engine import qa as qa_mod

CFG = config_mod.load_playstyle()

HOME = "ATL"
AWAY = "DET"
TANGGAL = "2026-11-22"
MATCH_ID = "DET@ATL_2026-11-22"

SUMBER_PDF = "Official NBA Injury Report"
SUMBER_ESPN = "ESPN injuries"


def _blok_tim(tricode, nama, off, deff, pace, pemain, cedera=None):
    """Satu blok tim kontrak nba_brain (cukup untuk simulasi nyata)."""
    return {
        "tricode": tricode,
        "team": nama,
        "stats_season": {
            "off_rtg": off,
            "def_rtg": deff,
            "net_rtg": off - deff,
            "pace": pace,
        },
        "stats_last10": {
            "off_rtg": off + 1.0,
            "def_rtg": deff - 1.0,
            "net_rtg": off - deff + 2.0,
            "pace": pace + 1.0,
        },
        "form5": [],
        "home_record": {"w": 5, "l": 3, "ppg": 110.0, "opp_ppg": 108.0},
        "road_record": {"w": 4, "l": 4, "ppg": 109.0, "opp_ppg": 109.0},
        "rest_days": 1,
        "back_to_back": False,
        "altitude_home": False,
        "players": pemain,
        "injuries": cedera or [],
    }


def _pemain(nama, bpm, mp, tricode):
    return {
        "player": nama,
        "bpm": bpm,
        "mp_per_game": mp,
        "team_tricode": tricode,
    }


def _inputs():
    """Inputs DET@ATL: Dyson Daniels OUT, Cade QUESTIONABLE, Duren DOUBTFUL."""
    home = _blok_tim(
        HOME,
        "Atlanta Hawks",
        114.0,
        112.0,
        100.0,
        [
            _pemain("Jalen Johnson", 4.0, 32.0, HOME),
            _pemain("Dyson Daniels", 2.0, 28.0, HOME),
        ],
        cedera=[
            {
                "player": "Dyson Daniels",
                "status": "OUT",
                "team_tricode": HOME,
                "reason": "Left Ankle Sprain",
                "sources": [SUMBER_PDF, SUMBER_ESPN],
            }
        ],
    )
    away = _blok_tim(
        AWAY,
        "Detroit Pistons",
        113.0,
        113.0,
        99.0,
        [
            _pemain("Cade Cunningham", 5.0, 34.0, AWAY),
            _pemain("Jalen Duren", 3.0, 26.0, AWAY),
        ],
        cedera=[
            {
                "player": "Cade Cunningham",
                "status": "QUESTIONABLE",
                "team_tricode": AWAY,
                "reason": "Right Knee Soreness",
                "sources": [SUMBER_ESPN],
            },
            {
                "player": "Jalen Duren",
                "status": "DOUBTFUL",
                "team_tricode": AWAY,
                "reason": "rest",
                "sources": [SUMBER_ESPN],
            },
        ],
    )
    return {
        "match": {
            "home_tricode": HOME,
            "away_tricode": AWAY,
            "game_date": TANGGAL,
            "season": "2026-27",
        },
        "home": home,
        "away": away,
        "h2h_last5": [],
        "tournament": None,
        "league": {"avg_pace": 99.5, "avg_off_rtg": 113.0},
        "missing": [],
        "sources": [
            {
                "data_kind": "nba_injuries",
                "source": SUMBER_PDF,
                "tier": 1,
                "fetched_at": "2026-11-22T12:00:00+00:00",
            },
            {
                "data_kind": "nba_injuries",
                "source": SUMBER_ESPN,
                "tier": 2,
                "fetched_at": "2026-11-22T12:00:00+00:00",
            },
        ],
        "fetched_at": "2026-11-22T12:00:00+00:00",
    }


def _kaki(ticket, garis, p_model, p_market, median, garis_market):
    """Satu leg Alt Under (blend + EV + label dari fungsi engine asli)."""
    p_final = devig_mod.blend(p_model, p_market, CFG)["p_final"]
    harga_jup = 67.0 if ticket == "insurance" else 76.0
    harga_poly = 66.5 if ticket == "insurance" else 75.5
    ev_pct = (p_final * (100.0 / harga_jup) - 1.0) * 100.0
    return {
        "leg_id": f"{MATCH_ID}:total_under_{garis:g}:{ticket}",
        "market_type": "total_under",
        "line": garis,
        "ticket": ticket,
        "p_model": p_model,
        "p_market": p_market,
        "comparison_source": "kalshi" if p_market is not None else None,
        "p_final": p_final,
        "price_cents": harga_poly,
        "jup_estimated_cents": harga_jup,
        "ev_pct": ev_pct,
        "price_label": price_labels_mod.label_for_ev(ev_pct, CFG),
        "cushion_vs_median_points": round(garis - median, 2),
        "cushion_vs_market_points": round(garis - garis_market, 2),
        "meets": True,
        "reason": None,
        "fetched_at": "2026-11-22T13:00:00+00:00",
    }


def _artefak(garis_market=225.5, selisih_p_market=0.02, status="OK", n_sumber=2):
    """Artefak nba_analysis fixture (sim nyata, seed 7, 500 iterasi)."""
    inputs = _inputs()
    sim = nba_sim_mod.simulate(
        inputs,
        cfg=CFG,
        lines={"totals": [233.5, 237.5]},
        scenarios=[],
        seed=7,
        iterations=500,
    )
    median = sim["score_distribution"]["total"]["median"]
    p_ins = sim["markets"]["total_under_233.5"]
    p_main = sim["markets"]["total_under_237.5"]
    legs = [
        _kaki(
            "insurance", 233.5, p_ins, p_ins - selisih_p_market, median, garis_market
        ),
        _kaki("main", 237.5, p_main, p_main - selisih_p_market, median, garis_market),
    ]
    anomalies = []
    anomali_garis = anomaly_mod.check_total_line_vs_model(median, garis_market, CFG)
    if anomali_garis is not None:
        anomalies.append({**anomali_garis, "leg_id": None})
    for leg in legs:
        anomali = anomaly_mod.check_model_vs_market(
            leg["p_model"], leg["p_market"], CFG
        )
        if anomali is not None:
            anomalies.append({**anomali, "leg_id": leg["leg_id"]})
    return {
        "format": "nba_analysis",
        "format_version": 1,
        "match_id": MATCH_ID,
        "home_tricode": HOME,
        "away_tricode": AWAY,
        "game_date": TANGGAL,
        "start_time": "2026-11-23T07:00:00+07:00",
        "generated_at": "2026-11-22T13:00:00+00:00",
        "status": status,
        "missing": [],
        "sources": [],
        "inputs": inputs,
        "simulation": sim,
        "market": {
            "slug": "nba-det-atl-2026-11-22",
            "main_total_line": garis_market,
            "main_total_volume_usd": 41964.0,
            "ladder_fetched_at": "2026-11-22T12:00:00+00:00",
            "ladder_warnings": [],
            "moneyline_jup": None,
            "totals": [
                {"line": 233.5, "side": "under", "price_cents": 66.5},
                {"line": 237.5, "side": "under", "price_cents": 75.5},
            ],
            "spreads": [],
        },
        "legs": legs,
        "injuries": {
            "sources": [SUMBER_PDF, SUMBER_ESPN][:n_sumber],
            "n_sources": n_sumber,
            "confirmed_both": ["Dyson Daniels"] if n_sumber >= 2 else [],
            "entries": [
                {
                    "player": "Dyson Daniels",
                    "status": "OUT",
                    "team_tricode": HOME,
                    "reason": "Left Ankle Sprain",
                    "sources": [SUMBER_PDF, SUMBER_ESPN][:n_sumber],
                },
                {
                    "player": "Cade Cunningham",
                    "status": "QUESTIONABLE",
                    "team_tricode": AWAY,
                    "reason": "Right Knee Soreness",
                    "sources": [SUMBER_ESPN],
                },
                {
                    "player": "Jalen Duren",
                    "status": "DOUBTFUL",
                    "team_tricode": AWAY,
                    "reason": "rest",
                    "is_injury": False,
                    "sources": [SUMBER_ESPN],
                },
            ],
            "conflicts": [],
            "fetched_at": "2026-11-22T12:00:00+00:00",
        },
        "anomalies": anomalies,
        "price_snapshots": {},
    }


def _artefak_minimal():
    """Artefak DATA_INCOMPLETE: tanpa sim, inputs, dan kaki."""
    return {
        "format": "nba_analysis",
        "format_version": 1,
        "match_id": MATCH_ID,
        "home_tricode": HOME,
        "away_tricode": AWAY,
        "game_date": TANGGAL,
        "start_time": None,
        "generated_at": "2026-11-22T13:00:00+00:00",
        "status": "DATA_INCOMPLETE",
        "missing": ["simulasi_gagal"],
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


def _median(artefak):
    return artefak["simulation"]["score_distribution"]["total"]["median"]


class TestFormatHasil(unittest.TestCase):
    def test_kunci_hasil_dan_tipe(self):
        hasil = qa_mod.answer(_artefak(), "Kenapa totalnya 219?", CFG)
        self.assertEqual(
            set(hasil), {"question", "intent", "answer", "numbers", "verified"}
        )
        self.assertEqual(hasil["question"], "Kenapa totalnya 219?")
        self.assertIsInstance(hasil["answer"], str)
        self.assertIsInstance(hasil["numbers"], dict)
        self.assertIsInstance(hasil["verified"], bool)

    def test_angka_numbers_semua_numerik(self):
        # "numbers" hanya angka (atau dict angka untuk dampak per pemain).
        hasil = qa_mod.answer(_artefak(), "Kenapa totalnya 219?", CFG)
        for nilai in hasil["numbers"].values():
            if isinstance(nilai, dict):
                for sub in nilai.values():
                    self.assertIsInstance(sub, (int, float))
            else:
                self.assertIsInstance(nilai, (int, float))

    def test_pertanyaan_kosong_unknown(self):
        hasil = qa_mod.answer(_artefak(), "   ", CFG)
        self.assertEqual(hasil["intent"], "unknown")

    def test_artefak_bukan_dict_tidak_meledak(self):
        hasil = qa_mod.answer(None, "Kenapa totalnya 219?", CFG)
        self.assertEqual(hasil["intent"], "kenapa_total")
        self.assertFalse(hasil["verified"])
        self.assertIn("tidak terverifikasi", hasil["answer"])


class TestDetectIntent(unittest.TestCase):
    def test_semua_intent(self):
        kasus = [
            ("Kenapa totalnya 219?", "kenapa_total"),
            ("Dari mana angka totalnya?", "kenapa_total"),
            ("Apa jadinya kalau Cade Cunningham absen?", "bagaimana_jika_absen"),
            ("Kalau Jalen Johnson tidak main, bagaimana?", "bagaimana_jika_absen"),
            ("Garis Asuransi mana yang paling aman?", "garis_teraman"),
            ("Garis mana yang sebaiknya dipilih?", "garis_teraman"),
            ("Siapa yang diragukan tampil?", "kabar_pemain"),
            ("Bagaimana kabar Cade Cunningham?", "kabar_pemain"),
            ("Siapa yang cedera?", "kabar_pemain"),
            ("Kenapa model dan market beda?", "kenapa_beda_model_market"),
            ("Berapa peluang masuk OT?", "peluang_laga"),
            ("Siapa yang lebih mungkin menang?", "peluang_laga"),
            ("Siapa pelatih Hawks?", "unknown"),
        ]
        for pertanyaan, harap in kasus:
            with self.subTest(pertanyaan=pertanyaan):
                self.assertEqual(qa_mod.detect_intent(pertanyaan), harap)

    def test_peluang_total_bukan_pertanyaan_ot(self):
        # "ot" di "total" tidak boleh memicu intent peluang_laga.
        self.assertEqual(
            qa_mod.detect_intent("Berapa peluang total di bawah 233?"), "unknown"
        )


class TestKenapaTotal(unittest.TestCase):
    def test_menguraikan_komponen_dari_sim_dan_inputs(self):
        artefak = _artefak()
        hasil = qa_mod.answer(artefak, "Kenapa totalnya 219?", CFG)
        self.assertEqual(hasil["intent"], "kenapa_total")
        self.assertTrue(hasil["verified"])
        median = _median(artefak)
        self.assertEqual(hasil["numbers"]["median_total"], median)
        self.assertIn("projected_total", hasil["numbers"])
        self.assertIn("pace_game", hasil["numbers"])
        self.assertIn("home_off_rtg", hasil["numbers"])
        self.assertIn("away_def_rtg", hasil["numbers"])
        self.assertIn("home_advantage_points", hasil["numbers"])
        # Dampak absen Dyson Daniels = (2 - (-2)) x 28/48 = 2,33 poin.
        dampak = hasil["numbers"]["absent_impacts"]["Dyson Daniels"]
        self.assertAlmostEqual(dampak, 2.33, places=2)
        self.assertAlmostEqual(hasil["numbers"]["absent_total_points"], 2.33, places=2)
        self.assertIn("Dyson Daniels", hasil["answer"])
        self.assertIn("tidak ada tim yang main dua malam", hasil["answer"].lower())

    def test_tanpa_inputs_komponen_tidak_terverifikasi(self):
        artefak = _artefak()
        artefak["inputs"] = None
        hasil = qa_mod.answer(artefak, "Kenapa totalnya 219?", CFG)
        self.assertEqual(hasil["intent"], "kenapa_total")
        self.assertFalse(hasil["verified"])
        self.assertIn("tidak terverifikasi", hasil["answer"])
        # Angka sim tetap dilaporkan (median ada).
        self.assertIn("median_total", hasil["numbers"])

    def test_tanpa_simulasi_tidak_terverifikasi(self):
        hasil = qa_mod.answer(_artefak_minimal(), "Kenapa totalnya 219?", CFG)
        self.assertFalse(hasil["verified"])
        self.assertIn("tidak terverifikasi", hasil["answer"])


class TestBagaimanaJikaAbsen(unittest.TestCase):
    def test_sim_ulang_pemain_sehat_median_turun(self):
        # Dampak Jalen Johnson = (4 - (-2)) x 32/48 = 4 poin: median
        # sim ulang harus turun (noise berpasangan, seed sama).
        hasil = qa_mod.answer(
            _artefak(), "Apa jadinya kalau Jalen Johnson absen?", CFG, iterations=500
        )
        self.assertEqual(hasil["intent"], "bagaimana_jika_absen")
        self.assertTrue(hasil["verified"])
        self.assertIn("sim ulang", hasil["answer"].lower())
        self.assertEqual(hasil["numbers"]["resim_iterations"], 500.0)
        self.assertLess(
            hasil["numbers"]["median_baru"], hasil["numbers"]["median_dasar"]
        )
        self.assertLess(hasil["numbers"]["delta_median_points"], -1.0)
        self.assertLess(hasil["numbers"]["delta_moneyline_home_points"], 0.0)

    def test_nama_belakang_saja_cukup_bila_unik(self):
        hasil = qa_mod.answer(
            _artefak(), "Apa jadinya kalau Johnson absen?", CFG, iterations=200
        )
        self.assertEqual(hasil["intent"], "bagaimana_jika_absen")
        self.assertTrue(hasil["verified"])
        self.assertIn("Jalen Johnson", hasil["answer"])

    def test_pemain_sudah_out_tidak_sim_ulang(self):
        hasil = qa_mod.answer(
            _artefak(), "Apa jadinya kalau Dyson Daniels absen?", CFG, iterations=200
        )
        self.assertEqual(hasil["intent"], "bagaimana_jika_absen")
        self.assertTrue(hasil["verified"])
        self.assertIn("sudah dihitung absen", hasil["answer"])
        self.assertNotIn("resim_iterations", hasil["numbers"])

    def test_pemain_tidak_dikenal_tidak_terverifikasi(self):
        hasil = qa_mod.answer(
            _artefak(), "Apa jadinya kalau LeBron James absen?", CFG, iterations=200
        )
        self.assertEqual(hasil["intent"], "bagaimana_jika_absen")
        self.assertFalse(hasil["verified"])
        self.assertIn("tidak terverifikasi", hasil["answer"])

    def test_tanpa_inputs_tidak_terverifikasi(self):
        hasil = qa_mod.answer(
            _artefak_minimal(),
            "Apa jadinya kalau Cade Cunningham absen?",
            CFG,
            iterations=200,
        )
        self.assertFalse(hasil["verified"])
        self.assertIn("tidak terverifikasi", hasil["answer"])

    def test_default_resim_20000_iterasi(self):
        self.assertEqual(qa_mod.RESIM_ITERATIONS, 20000)


class TestGarisTeraman(unittest.TestCase):
    def test_memilih_p_final_tertinggi(self):
        artefak = _artefak()
        hasil = qa_mod.answer(artefak, "Garis Asuransi mana yang paling aman?", CFG)
        self.assertEqual(hasil["intent"], "garis_teraman")
        self.assertTrue(hasil["verified"])
        # Garis Utama 237,5 peluangnya lebih tinggi dari Asuransi 233,5.
        self.assertEqual(hasil["numbers"]["recommended_line"], 237.5)
        self.assertIn("237,5", hasil["answer"])
        self.assertIn("233,5", hasil["answer"])  # kaki lain ikut dibandingkan
        self.assertIn("p_final_main", hasil["numbers"])

    def test_tidak_ada_garis_memenuhi_dijawab_jujur(self):
        artefak = _artefak()
        for leg in artefak["legs"]:
            leg["meets"] = False
            leg["line"] = None
            leg["reason"] = "tidak_ada_garis_memenuhi"
            leg["p_model"] = None
            leg["p_final"] = None
        hasil = qa_mod.answer(artefak, "Garis mana yang sebaiknya dipilih?", CFG)
        self.assertEqual(hasil["intent"], "garis_teraman")
        self.assertTrue(hasil["verified"])  # data ada; jawaban negatif yang jujur
        self.assertIn("Tidak ada garis", hasil["answer"])

    def test_tanpa_kaki_tidak_terverifikasi(self):
        hasil = qa_mod.answer(
            _artefak_minimal(), "Garis mana yang sebaiknya dipilih?", CFG
        )
        self.assertFalse(hasil["verified"])
        self.assertIn("tidak terverifikasi", hasil["answer"])


class TestKabarPemain(unittest.TestCase):
    def test_siapa_yang_diragukan(self):
        hasil = qa_mod.answer(_artefak(), "Siapa yang diragukan tampil?", CFG)
        self.assertEqual(hasil["intent"], "kabar_pemain")
        self.assertTrue(hasil["verified"])
        self.assertIn("Cade Cunningham", hasil["answer"])
        self.assertIn("Jalen Duren", hasil["answer"])
        self.assertIn("Dyson Daniels", hasil["answer"])  # pasti absen disebut juga
        self.assertEqual(hasil["numbers"]["n_diragukan"], 2.0)
        self.assertEqual(hasil["numbers"]["n_pasti_absen"], 1.0)

    def test_kabar_pemain_spesifik(self):
        hasil = qa_mod.answer(_artefak(), "Bagaimana kabar Cade Cunningham?", CFG)
        self.assertEqual(hasil["intent"], "kabar_pemain")
        self.assertTrue(hasil["verified"])
        self.assertIn("diragukan", hasil["answer"])
        self.assertIn("Right Knee Soreness", hasil["answer"])
        self.assertEqual(hasil["numbers"]["player_n_sources"], 1.0)

    def test_kabar_rest_disebut_alasannya(self):
        hasil = qa_mod.answer(_artefak(), "Bagaimana kabar Jalen Duren?", CFG)
        self.assertTrue(hasil["verified"])
        self.assertIn("rest", hasil["answer"])

    def test_pemain_sehat_tanpa_entri_cedera(self):
        hasil = qa_mod.answer(_artefak(), "Bagaimana kabar Jalen Johnson?", CFG)
        self.assertTrue(hasil["verified"])
        self.assertIn("tersedia", hasil["answer"])

    def test_pemain_tidak_dikenal_tidak_terverifikasi(self):
        hasil = qa_mod.answer(_artefak(), "Bagaimana kabar LeBron James?", CFG)
        self.assertFalse(hasil["verified"])
        self.assertIn("tidak terverifikasi", hasil["answer"])

    def test_tanpa_blok_cedera_tidak_terverifikasi(self):
        artefak = _artefak()
        del artefak["injuries"]
        hasil = qa_mod.answer(artefak, "Siapa yang diragukan tampil?", CFG)
        self.assertFalse(hasil["verified"])
        self.assertIn("tidak terverifikasi", hasil["answer"])

    def test_tanpa_entri_cedera_dijawab_jujur(self):
        artefak = _artefak()
        artefak["injuries"]["entries"] = []
        hasil = qa_mod.answer(artefak, "Siapa yang diragukan tampil?", CFG)
        self.assertTrue(hasil["verified"])
        self.assertIn("Tidak ada kabar cedera", hasil["answer"])


class TestKenapaBeda(unittest.TestCase):
    def test_gap_besar_tanpa_alasan_kesimpulan_c(self):
        # Garis market = median + 9 (gap 9 > ambang 5) + selisih peluang
        # 12 poin (> ambang 8); data bersih -> "tidak ditemukan alasan".
        median = _median(_artefak())
        artefak = _artefak(garis_market=median + 9.0, selisih_p_market=0.12)
        hasil = qa_mod.answer(artefak, "Kenapa model dan market beda?", CFG)
        self.assertEqual(hasil["intent"], "kenapa_beda_model_market")
        self.assertTrue(hasil["verified"])
        self.assertAlmostEqual(hasil["numbers"]["gap_points"], 9.0, places=2)
        self.assertIn("tidak ditemukan alasan", hasil["answer"])
        self.assertIn("condong-ke-market", hasil["answer"])

    def test_gap_besar_dengan_kelemahan_data_kesimpulan_b(self):
        median = _median(_artefak())
        artefak = _artefak(
            garis_market=median + 9.0,
            selisih_p_market=0.12,
            status="HOLD",
            n_sumber=1,
        )
        hasil = qa_mod.answer(artefak, "Kenapa model dan market beda?", CFG)
        self.assertTrue(hasil["verified"])
        self.assertIn("kurang data", hasil["answer"])
        self.assertIn("1 sumber", hasil["answer"])

    def test_gap_kecil_tidak_ada_yang_dijawab(self):
        median = _median(_artefak())
        artefak = _artefak(garis_market=median + 2.0, selisih_p_market=0.02)
        hasil = qa_mod.answer(artefak, "Kenapa model dan market beda?", CFG)
        self.assertTrue(hasil["verified"])
        self.assertIn("tidak jauh berbeda", hasil["answer"])

    def test_tanpa_median_atau_garis_tidak_terverifikasi(self):
        hasil = qa_mod.answer(_artefak_minimal(), "Kenapa model dan market beda?", CFG)
        self.assertFalse(hasil["verified"])
        self.assertIn("tidak terverifikasi", hasil["answer"])


class TestPeluangLaga(unittest.TestCase):
    def test_peluang_ot(self):
        artefak = _artefak()
        hasil = qa_mod.answer(artefak, "Berapa peluang masuk OT?", CFG)
        self.assertEqual(hasil["intent"], "peluang_laga")
        self.assertTrue(hasil["verified"])
        ot = artefak["simulation"]["score_distribution"]["ot_probability"]
        self.assertEqual(hasil["numbers"]["ot_probability"], ot)
        self.assertIn("perpanjangan waktu", hasil["answer"])

    def test_peluang_menang_kandang(self):
        artefak = _artefak()
        hasil = qa_mod.answer(artefak, "Siapa yang lebih mungkin menang?", CFG)
        self.assertEqual(hasil["intent"], "peluang_laga")
        self.assertTrue(hasil["verified"])
        self.assertEqual(
            hasil["numbers"]["moneyline_home"],
            artefak["simulation"]["markets"]["moneyline_home"],
        )
        self.assertIn("dijagokan", hasil["answer"])

    def test_tanpa_simulasi_tidak_terverifikasi(self):
        hasil = qa_mod.answer(_artefak_minimal(), "Berapa peluang masuk OT?", CFG)
        self.assertFalse(hasil["verified"])
        self.assertIn("tidak terverifikasi", hasil["answer"])


class TestUnknown(unittest.TestCase):
    def test_pertanyaan_tidak_dikenal_menawarkan_daftar(self):
        hasil = qa_mod.answer(_artefak(), "Siapa pelatih Hawks?", CFG)
        self.assertEqual(hasil["intent"], "unknown")
        self.assertTrue(hasil["verified"])
        self.assertIn("tidak mengerti", hasil["answer"])
        self.assertIn("Kenapa totalnya 219?", hasil["answer"])
        self.assertIn("Siapa yang diragukan tampil?", hasil["answer"])
        self.assertEqual(hasil["numbers"], {})

    def test_supported_questions_enam_jenis(self):
        intents = {item["intent"] for item in qa_mod.SUPPORTED_QUESTIONS}
        self.assertEqual(
            intents,
            {
                "kenapa_total",
                "bagaimana_jika_absen",
                "garis_teraman",
                "kabar_pemain",
                "kenapa_beda_model_market",
                "peluang_laga",
            },
        )


if __name__ == "__main__":
    unittest.main()
