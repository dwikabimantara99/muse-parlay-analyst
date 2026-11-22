"""Tes cli.py belajar + fixture sintetis + skrip replay (Tahap 3 Langkah 6).

SEMUA offline: DB ledger dibangun di tempfile via ledger.store; fixture
sintetis dibaca dari tests/fixtures/; skrip replay diuji lewat builder
murni + file out/validation_nba_rolling.json bila ada (gitignored —
tes file-nyata di-skip bila tidak ada). Tidak ada panggilan Odds API.
"""

import argparse
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cli
from engine import calibration as calibration_mod
from engine import learning as learning_mod
from engine import proposals as proposals_mod
from ledger import store

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_SINTETIS = REPO_ROOT / "tests" / "fixtures" / "sintetis_belajar_kaki.json"
FILE_VALIDASI_ROLLING = REPO_ROOT / "out" / "validation_nba_rolling.json"

_SPEK_REPLAY = importlib.util.spec_from_file_location(
    "laporan_belajar_replay",
    REPO_ROOT / "scripts" / "laporan_belajar_replay.py",
)
replay_mod = importlib.util.module_from_spec(_SPEK_REPLAY)
_SPEK_REPLAY.loader.exec_module(replay_mod)


def _args_belajar(db=None, keluaran=None, contoh_sintetis=False):
    """Namespace argparse untuk cmd_belajar."""
    return argparse.Namespace(
        db=db or str(REPO_ROOT / "ledger.db"),
        keluaran=keluaran,
        contoh_sintetis=contoh_sintetis,
    )


def _jalankan_belajar(args):
    """Jalankan cmd_belajar, kembalikan (exit_code, stdout, stderr)."""
    buf_out, buf_err = io.StringIO(), io.StringIO()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        code = cli.cmd_belajar(args)
    return code, buf_out.getvalue(), buf_err.getvalue()


def _kaki_tiket(
    leg_id,
    match_id,
    sport,
    market,
    selection,
    p_model,
    p_market,
    p_final,
    harga,
    ev_pct_persen,
    result=None,
):
    """Satu kaki tiket (bentuk schemas/ticket.schema.json)."""
    return {
        "leg_id": leg_id,
        "match_id": match_id,
        "sport": sport,
        "market": market,
        "selection": selection,
        "p_model": p_model,
        "p_market": p_market,
        "p_final": p_final,
        "jup_price_cents": harga,
        "edge": 0.01,
        "ev_pct": ev_pct_persen,
        "status": "OK",
        "result": result,
    }


def _tiket(ticket_id, jenis, result, legs):
    """Satu tiket (multiplier > 1 sesuai skema)."""
    return {
        "ticket_id": ticket_id,
        "type": jenis,
        "stake": 10.0,
        "multiplier": 2.0,
        "result": result,
        "legs": legs,
    }


def _brier(pasangan):
    """Brier hitung tangan (verifikasi independen, tanpa modul repo)."""
    return sum((p - (1.0 if y else 0.0)) ** 2 for p, y in pasangan) / len(pasangan)


class TestBelajarTanpaData(unittest.TestCase):
    def test_db_tidak_ada_laporan_belum_ada_data_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "tidak-ada.db")
            code, out, _ = _jalankan_belajar(_args_belajar(db=db))
            self.assertEqual(code, 0)
            self.assertIn("Belum ada hasil tercatat", out)
            self.assertIn("cli.py log --file", out)
            # Belajar TIDAK BOLEH membuat file ledger (baca read-only).
            self.assertFalse(Path(db).exists())

    def test_db_kosong_laporan_belum_ada_data_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "kosong.db"
            conn = store.connect(db_path)
            conn.close()
            code, out, _ = _jalankan_belajar(_args_belajar(db=str(db_path)))
            self.assertEqual(code, 0)
            self.assertIn("Belum ada hasil tercatat", out)

    def test_db_hanya_pending_laporan_belum_ada_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "pending.db"
            conn = store.connect(db_path)
            store.log_ticket(
                conn,
                _tiket(
                    "tkt-pending-01",
                    "Utama",
                    "PENDING",
                    [
                        _kaki_tiket(
                            "leg-p1",
                            "nba-2026-11-22-det-atl",
                            "nba",
                            "total_under",
                            "Under 237.5",
                            0.8,
                            0.7,
                            0.73,
                            70,
                            4.0,
                            result=None,
                        )
                    ],
                ),
            )
            conn.close()
            code, out, _ = _jalankan_belajar(_args_belajar(db=str(db_path)))
            self.assertEqual(code, 0)
            self.assertIn("Belum ada hasil tercatat", out)
            self.assertIn("1 kaki yang masih menunggu hasil", out)


class TestBelajarDenganDBSintetis(unittest.TestCase):
    """DB tempfile dengan 4 kaki settled + 1 pending; angka dicek tangan."""

    # Kaki settled (p_model, p_market, p_final, harga, ev_persen, hasil):
    #  T1 (WIN): total_under 0.8/0.6/0.66, 60sen, 10% — WIN (x2)
    #  T2 (LOSS): moneyline 0.7/0.5/0.56, 50sen, 5% — WIN + LOSS
    # Brier model hitung tangan: (0.04+0.04+0.09+0.49)/4 = 0.165
    # Brier pasar: (0.16+0.16+0.25+0.25)/4 = 0.205
    # Brier gabungan: (0.1156+0.1156+0.1936+0.3136)/4 = 0.1846
    # Klimatologi: win 3/4 -> 0.75*0.25 = 0.1875
    # EV prediksi: (0.10+0.10+0.05+0.05)/4 = 0.075
    # EV nyata: (2/3+2/3+1-1)/4 = 1/3

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "sintetis.db"
        conn = store.connect(self.db_path)
        store.log_ticket(
            conn,
            _tiket(
                "tkt-sin-01",
                "Asuransi",
                "WIN",
                [
                    _kaki_tiket(
                        "leg-s1",
                        "nba-2026-11-22-a",
                        "nba",
                        "total_under",
                        "Under 237.5",
                        0.8,
                        0.6,
                        0.66,
                        60,
                        10.0,
                        "WIN",
                    ),
                    _kaki_tiket(
                        "leg-s2",
                        "nba-2026-11-22-b",
                        "nba",
                        "total_under",
                        "Under 229.5",
                        0.8,
                        0.6,
                        0.66,
                        60,
                        10.0,
                        "WIN",
                    ),
                ],
            ),
        )
        store.log_ticket(
            conn,
            _tiket(
                "tkt-sin-02",
                "Utama",
                "LOSS",
                [
                    _kaki_tiket(
                        "leg-s3",
                        "nba-2026-11-22-c",
                        "nba",
                        "moneyline",
                        "kandang menang",
                        0.7,
                        0.5,
                        0.56,
                        50,
                        5.0,
                        "WIN",
                    ),
                    _kaki_tiket(
                        "leg-s4",
                        "nba-2026-11-22-d",
                        "nba",
                        "moneyline",
                        "kandang menang",
                        0.7,
                        0.5,
                        0.56,
                        50,
                        5.0,
                        "LOSS",
                    ),
                ],
            ),
        )
        store.log_ticket(
            conn,
            _tiket(
                "tkt-sin-03",
                "Utama",
                "PENDING",
                [
                    _kaki_tiket(
                        "leg-s5",
                        "nba-2026-11-22-e",
                        "nba",
                        "total_under",
                        "Under 233.5",
                        0.75,
                        0.65,
                        0.68,
                        65,
                        4.0,
                        None,
                    )
                ],
            ),
        )
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_laporan_memuat_angka_yang_benar(self):
        code, out, _ = _jalankan_belajar(_args_belajar(db=str(self.db_path)))
        self.assertEqual(code, 0)
        self.assertIn("Dari 4 kaki yang sudah selesai, 3 menang (75,0%)", out)
        self.assertIn("Brier model: 0,1650.", out)
        self.assertIn("Brier pasar: 0,2050.", out)
        self.assertIn("Brier gabungan (model + pasar): 0,1846.", out)
        self.assertIn("0,1875", out)  # Brier tebakan dasar
        self.assertIn("EV yang diperkirakan: +7,5%.", out)
        self.assertIn("EV yang benar-benar terjadi: +33,3%.", out)
        self.assertIn("1 kaki masih menunggu hasil", out)
        self.assertIn("berasal dari 3 tiket", out)

    def test_brier_sesuai_hitung_tangan(self):
        hasil = learning_mod.muat_hasil_ledger(self.db_path)
        self.assertTrue(hasil["ada_data"])
        self.assertEqual(hasil["n_settled"], 4)
        self.assertEqual(hasil["n_pending"], 1)
        ringkasan = learning_mod.ringkasan_keseluruhan(hasil["outcomes"])
        settled = [o for o in hasil["outcomes"] if o["settled"]]
        self.assertAlmostEqual(
            ringkasan["brier_model"],
            _brier([(o["p_model"], o["result"]) for o in settled]),
            places=9,
        )
        self.assertAlmostEqual(ringkasan["brier_model"], 0.165, places=9)
        self.assertAlmostEqual(ringkasan["brier_market"], 0.205, places=9)
        self.assertAlmostEqual(ringkasan["brier_final"], 0.1846, places=9)
        self.assertAlmostEqual(ringkasan["brier_climatology"], 0.1875, places=9)

    def test_per_pasar_dan_tanpa_usulan(self):
        code, out, _ = _jalankan_belajar(_args_belajar(db=str(self.db_path)))
        self.assertEqual(code, 0)
        self.assertIn("### NBA — Total Under (2 kaki)", out)
        self.assertIn("### NBA — Menang/Kalah (2 kaki)", out)
        # n=4 < min_legs_w 50 -> belum ada rekomendasi w.
        self.assertIn("Belum ada rekomendasi bobot baru.", out)
        # n per pasar < ambang usulan -> tidak ada usulan.
        self.assertIn("Tidak ada usulan saat ini", out)


class TestBelajarContohSintetis(unittest.TestCase):
    def test_contoh_sintetis_berlabel_dan_exit_0(self):
        code, out, _ = _jalankan_belajar(_args_belajar(contoh_sintetis=True))
        self.assertEqual(code, 0)
        self.assertIn("DATA SINTETIS — BUKAN HASIL NYATA", out)
        self.assertIn("Dari 62 kaki yang sudah selesai, 35 menang (56,5%)", out)
        self.assertIn("Rekomendasi: ubah bobot model menjadi 0,75.", out)
        self.assertIn("belum diterapkan — menunggu persetujuanmu", out)
        self.assertIn("[USUL-001]", out)
        self.assertIn("[USUL-002]", out)

    def test_keluaran_menulis_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            keluaran = str(Path(tmp) / "sub" / "laporan.txt")
            code, out, _ = _jalankan_belajar(
                _args_belajar(keluaran=keluaran, contoh_sintetis=True)
            )
            self.assertEqual(code, 0)
            self.assertIn(f"laporan belajar ditulis ke {keluaran}", out)
            teks = Path(keluaran).read_text(encoding="utf-8")
            self.assertIn("DATA SINTETIS — BUKAN HASIL NYATA", teks)
            self.assertIn("Dari 62 kaki yang sudah selesai", teks)
            # Isi file sama dengan yang dicetak ke stdout.
            _, out_stdout, _ = _jalankan_belajar(_args_belajar(contoh_sintetis=True))

            # stdout = teks + newline dari print(); tanggal dibuat bisa
            # berbeda detik — bandingkan tanpa baris tanggal.
            def _tanpa_tanggal(t):
                # print() menambah "\n" di stdout; file tidak.
                return "\n".join(
                    b for b in t.splitlines() if not b.startswith("Laporan ini dibuat")
                ).strip()

            self.assertEqual(_tanpa_tanggal(teks), _tanpa_tanggal(out_stdout))

    def test_keluaran_tanpa_data_juga_menulis_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "tidak-ada.db")
            keluaran = str(Path(tmp) / "laporan.txt")
            code, out, _ = _jalankan_belajar(_args_belajar(db=db, keluaran=keluaran))
            self.assertEqual(code, 0)
            self.assertIn(
                "Belum ada hasil tercatat", Path(keluaran).read_text(encoding="utf-8")
            )

    def test_main_dispatch_belajar(self):
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            code = cli.main(["belajar", "--contoh-sintetis"])
        self.assertEqual(code, 0)
        self.assertIn("DATA SINTETIS", buf_out.getvalue())


class TestBangunDataBelajar(unittest.TestCase):
    def setUp(self):
        self._modul_asli = cli._modul_belajar

    def tearDown(self):
        cli._modul_belajar = self._modul_asli

    def test_data_lengkap_dari_fixture(self):
        kaki = json.loads(FIXTURE_SINTETIS.read_text(encoding="utf-8"))["kaki"]
        data, error = cli.bangun_data_belajar(kaki, "sintetis")
        self.assertIsNone(error)
        self.assertTrue(data["ada_data"])
        self.assertEqual(data["ringkasan"]["n"], 62)
        self.assertEqual(data["kalibrasi_w"]["w_rekomendasi"], 0.75)
        self.assertTrue(data["kalibrasi_w"]["cukup_data"])
        self.assertEqual(len(data["usulan"]), 2)
        self.assertEqual(data["modul_belum_tersedia"], [])

    def test_modul_kalibrasi_usulan_hilang_data_none(self):
        kaki = json.loads(FIXTURE_SINTETIS.read_text(encoding="utf-8"))["kaki"]
        cli._modul_belajar = lambda: (
            learning_mod,
            None,
            None,
            ["engine.calibration", "engine.proposals"],
        )
        data, error = cli.bangun_data_belajar(kaki, "sintetis")
        self.assertIsNone(error)
        self.assertIsNone(data["kalibrasi_w"])
        self.assertIsNone(data["usulan"])
        self.assertEqual(
            data["modul_belum_tersedia"],
            ["engine.calibration", "engine.proposals"],
        )
        # Laporan tetap jalan, bagiannya ditandai belum tersedia.
        from report import learning_report as learning_report_mod

        teks = learning_report_mod.render_laporan_belajar(data)
        self.assertIn("modul kalibrasi belum tersedia", teks)
        self.assertIn("modul usulan belum terpasang", teks)

    def test_modul_learning_hilang_error(self):
        data, error = cli.bangun_data_belajar(
            [], "ledger", modul=(None, None, None, [])
        )
        self.assertIsNone(data)
        self.assertIn("engine/learning.py", error)

    def test_cmd_belajar_learning_hilang_exit_2(self):
        cli._modul_belajar = lambda: (
            None,
            calibration_mod,
            proposals_mod,
            ["engine.learning"],
        )
        code, _, err = _jalankan_belajar(_args_belajar(contoh_sintetis=True))
        self.assertEqual(code, 2)
        self.assertIn("engine/learning.py", err)


class TestFixtureSintetis(unittest.TestCase):
    """Sifat rancangan fixture dicek dari angka sebenarnya (bukan asumsi)."""

    @classmethod
    def setUpClass(cls):
        dokumen = json.loads(FIXTURE_SINTETIS.read_text(encoding="utf-8"))
        cls.kaki = dokumen["kaki"]
        cls.per_pasar = learning_mod.ringkasan_per_pasar(cls.kaki)
        cls.total = learning_mod.ringkasan_keseluruhan(cls.kaki)
        cls.kalibrasi = calibration_mod.rekomendasi_w(cls.kaki)
        cls.usulan = proposals_mod.hasilkan_usulan(cls.per_pasar, cls.kaki)

    def test_jumlah_dan_pasar(self):
        self.assertEqual(len(self.kaki), 62)
        self.assertEqual(
            {k: v["n"] for k, v in self.per_pasar.items()},
            {
                ("NBA", "total_under"): 24,
                ("NBA", "moneyline"): 20,
                ("soccer", "1X2"): 8,
                ("soccer", "over_under"): 6,
                ("soccer", "btts"): 4,
            },
        )

    def test_total_under_model_mengalahkan_market(self):
        r = self.per_pasar[("NBA", "total_under")]
        self.assertLess(r["brier_model"], r["brier_market"])
        self.assertAlmostEqual(r["brier_model"], 0.158125, places=6)
        self.assertAlmostEqual(r["brier_market"], 0.333125, places=6)

    def test_moneyline_model_kalah_dari_tebakan_dasar(self):
        r = self.per_pasar[("NBA", "moneyline")]
        self.assertGreater(r["brier_model"], r["brier_climatology"])
        self.assertAlmostEqual(r["brier_model"], 0.4, places=9)
        self.assertAlmostEqual(r["brier_climatology"], 0.24, places=9)

    def test_kalibrasi_w_jawaban_bisa_dicek(self):
        # Optimum grid 0,75 — diverifikasi independen (hitung tangan
        # Brier blend per w + optimum kontinu w* = 0,7376).
        self.assertTrue(self.kalibrasi["cukup_data"])
        self.assertEqual(self.kalibrasi["n"], 62)
        self.assertEqual(self.kalibrasi["w_rekomendasi"], 0.75)
        self.assertEqual(self.kalibrasi["w_saat_ini"], 0.3)
        self.assertFalse(self.kalibrasi["diterapkan"])
        self.assertTrue(self.kalibrasi["butuh_persetujuan_user"])
        self.assertAlmostEqual(
            self.kalibrasi["brier_blend_w_rekomendasi"], 0.27101129, places=6
        )
        self.assertAlmostEqual(
            self.kalibrasi["brier_blend_w_saat_ini"], 0.27830594, places=6
        )

        # Cek independen: Brier blend w=0,75 < tetangga grid 0,70/0,80.
        def _brier_blend(w):
            return _brier(
                [
                    (
                        w * k["p_model"] + (1 - w) * k["p_market"],
                        k["result"],
                    )
                    for k in self.kaki
                ]
            )

        self.assertLess(_brier_blend(0.75), _brier_blend(0.70))
        self.assertLess(_brier_blend(0.75), _brier_blend(0.80))
        self.assertAlmostEqual(
            _brier_blend(0.75),
            self.kalibrasi["brier_blend_w_rekomendasi"],
            places=9,
        )

    def test_usulan_dua_untuk_moneyline(self):
        self.assertEqual(len(self.usulan), 2)
        self.assertEqual([u["jenis"] for u in self.usulan], ["pasar", "ambang"])
        self.assertEqual([u["id"] for u in self.usulan], ["USUL-001", "USUL-002"])
        self.assertTrue(all(u["status"] == "menunggu_persetujuan" for u in self.usulan))

    def test_p_final_dan_ev_konsisten(self):
        for k in self.kaki:
            p_final_harapan = round(0.3 * k["p_model"] + 0.7 * k["p_market"], 4)
            self.assertEqual(k["p_final"], p_final_harapan)
            ev_harapan = round(k["p_final"] * (100.0 / k["price_buy_cents"]) - 1.0, 4)
            self.assertEqual(k["ev_pct"], ev_harapan)
            self.assertTrue(k["settled"])
            self.assertEqual(k["sumber"], "sintetis")


class TestReplayBelajar(unittest.TestCase):
    def test_bangun_outcome_dari_dokumen_kecil(self):
        dokumen = {
            "backtest": {
                "n_laga": 2,
                "n_dilewati": 0,
                "hasil_per_laga": [
                    {
                        "game_id": "001",
                        "game_date": "2025-04-08",
                        "home_tricode": "CHA",
                        "away_tricode": "MEM",
                        "p_home_win": 0.22,
                        "actual_home_win": False,
                        "p_under": 0.66,
                        "actual_under": True,
                        "garis_under": 234.0,
                    },
                    {
                        "game_id": "002",
                        "game_date": "2025-04-08",
                        "home_tricode": "CLE",
                        "away_tricode": "CHI",
                        "p_home_win": 0.76,
                        "actual_home_win": True,
                        "p_under": 0.66,
                        "actual_under": False,
                        "garis_under": 247.0,
                    },
                ],
            }
        }
        outcomes, info = replay_mod.bangun_outcome_replay(dokumen)
        self.assertEqual(len(outcomes), 4)
        self.assertEqual(info["n_laga"], 2)
        self.assertIsNone(info["error"])
        ml = [o for o in outcomes if o["market"] == "moneyline"]
        under = [o for o in outcomes if o["market"] == "total_under"]
        self.assertEqual(len(ml), 2)
        self.assertEqual(len(under), 2)
        self.assertEqual(ml[0]["p_model"], 0.22)
        self.assertIs(ml[0]["result"], False)
        self.assertIsNone(ml[0]["p_market"])
        self.assertEqual(ml[0]["p_final"], 0.22)  # MODEL_ONLY
        self.assertEqual(under[0]["selection"], "Under 234")
        self.assertTrue(all(o["settled"] for o in outcomes))
        self.assertTrue(all(o["sumber"] == "replay" for o in outcomes))

    def test_tanpa_rekor_per_laga_unknown(self):
        for dokumen in ({}, {"backtest": {}}, {"backtest": {"hasil_per_laga": []}}):
            outcomes, info = replay_mod.bangun_outcome_replay(dokumen)
            self.assertEqual(outcomes, [])
            self.assertIn("UNKNOWN", info["error"])

    def test_laga_tidak_valid_dilewati(self):
        dokumen = {
            "backtest": {
                "hasil_per_laga": [
                    {
                        "game_id": "001",
                        "p_home_win": 1.5,  # peluang tidak valid
                        "actual_home_win": True,
                        "p_under": 0.66,
                        "actual_under": True,
                        "garis_under": 234.0,
                    },
                    {
                        "game_id": "002",
                        "p_home_win": 0.5,
                        "actual_home_win": True,
                        "p_under": 0.6,
                        "actual_under": False,
                        "garis_under": 230.0,
                    },
                ]
            }
        }
        outcomes, info = replay_mod.bangun_outcome_replay(dokumen)
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(info["n_laga_tidak_valid"], 1)

    @unittest.skipUnless(
        FILE_VALIDASI_ROLLING.exists(),
        "out/validation_nba_rolling.json tidak ada (gitignored, runtime)",
    )
    def test_file_nyata_brier_cocok_dengan_kalibrasi(self):
        dokumen = json.loads(FILE_VALIDASI_ROLLING.read_text(encoding="utf-8"))
        outcomes, info = replay_mod.bangun_outcome_replay(dokumen)
        self.assertEqual(info["n_laga"], 150)
        self.assertEqual(len(outcomes), 300)
        self.assertIsNone(info["error"])
        per_pasar = learning_mod.ringkasan_per_pasar(outcomes)
        kalibrasi = dokumen["kalibrasi"]
        self.assertAlmostEqual(
            per_pasar[("NBA", "moneyline")]["brier_model"],
            kalibrasi["kandang_menang"]["brier"],
            places=6,
        )
        self.assertAlmostEqual(
            per_pasar[("NBA", "total_under")]["brier_model"],
            kalibrasi["under_median_plus_8"]["brier"],
            places=6,
        )
        # Tanpa harga pasar: kalibrasi w tidak cukup data, tanpa usulan.
        w = calibration_mod.rekomendasi_w(outcomes)
        self.assertEqual(w["n"], 0)
        self.assertFalse(w["cukup_data"])
        self.assertIsNone(w["w_rekomendasi"])
        self.assertEqual(proposals_mod.hasilkan_usulan(per_pasar, outcomes), [])

    @unittest.skipUnless(
        FILE_VALIDASI_ROLLING.exists(),
        "out/validation_nba_rolling.json tidak ada (gitignored, runtime)",
    )
    def test_main_replay_menulis_laporan(self):
        with tempfile.TemporaryDirectory() as tmp:
            keluaran = str(Path(tmp) / "laporan_replay.txt")
            buf_out = io.StringIO()
            with redirect_stdout(buf_out):
                code = replay_mod.main(
                    ["--input", str(FILE_VALIDASI_ROLLING), "--output", keluaran]
                )
            self.assertEqual(code, 0)
            self.assertIn("COCOK", buf_out.getvalue())
            teks = Path(keluaran).read_text(encoding="utf-8")
            self.assertIn("DATA REPLAY BACKTEST — BUKAN TIKET NYATA", teks)
            self.assertIn("Dari 300 kaki yang sudah selesai", teks)
            self.assertIn("Brier model: 0,1983.", teks)
            self.assertIn("Brier model: 0,2199.", teks)


if __name__ == "__main__":
    unittest.main()
