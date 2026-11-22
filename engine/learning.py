"""Pelacakan hasil: baca ledger, hitung Brier + EV terealisasi per kaki.

Tahap 3 Langkah 6, pekerja A. Modul ini adalah gerbang pertama "mesin
belajar sendiri": ia mengubah catatan tiket di ledger SQLite menjadi
rekaman hasil (OUTCOME RECORD) lalu meringkasnya per pasar dan
keseluruhan. Pekerja B (kalibrasi w) dan pekerja C (laporan) memakai
kontrak OUTCOME RECORD di bawah ini — jangan ubah kuncinya tanpa
koordinasi.

KONTRAK OUTCOME RECORD (dict per kaki):
- leg_id, ticket_id: str (apa adanya dari ledger; boleh None bila kolom
  kosong).
- sport: "NBA" / "soccer" / None. Ledger menyimpan "nba" / "football"
  (schemas/ticket.schema.json) — modul ini memetakan keduanya ke
  kontrakt ini; nilai lain diteruskan apa adanya (tidak ditebak).
- market, selection: str (apa adanya dari ledger; boleh None).
- p_model, p_market, p_final: float dalam [0, 1] atau None.
- price_buy_cents, price_close_cents: float (sen) atau None.
- ev_pct: float FRAKSI (0.05 = +5%). PERHATIAN: ledger menyimpan EV
  dalam PERSEN (engine/nba_analysis.py dan engine/soccer_analysis.py
  mengalikan dengan 100.0) — modul ini membagi 100 saat membaca, supaya
  ev_prediksi_rata2 bisa dibandingkan langsung dengan
  ev_terealisasi_rata2 (fraksi). Bila suatu hari penulis ledger berubah
  ke fraksi, konversi ini harus dicabut.
- result: True (WIN), False (LOSS), atau None (belum settle).
- settled: bool — True hanya bila result bukan None.
- sumber: selalu "ledger".

ATURAN HITUNG:
- Kaki VOID/PUSH DIKELUARKAN dari semua statistik (dihitung di
  "n_dikeluarkan"). Kaki PENDING (result NULL di ledger) dihitung di
  "n_pending", masuk daftar outcomes bila ada data, tapi TIDAK masuk
  Brier/win_rate/EV — ringkasan hanya memakai kaki settled.
- Brier model/market/final dihitung dengan engine.validation.brier_score
  (dipakai ulang, bukan ditulis ulang), masing-masing hanya atas kaki
  yang punya nilai peluang itu yang valid (angka hingga dalam [0, 1]);
  nilai hilang/tidak valid diperlakukan sebagai "tidak ada" untuk Brier
  itu saja. Bila tidak ada satu pun kaki dengan nilai -> None + alasan.
- brier_climatology: Brier tebakan dasar — frekuensi kemenangan aktual
  sebagai prediksi konstan untuk semua kaki. Model yang tidak mengalahkan
  angka ini tidak membawa informasi.
- EV terealisasi per kaki (diagnostik, BUKAN P/L tiket parlay): WIN ->
  (100 / price_buy_cents - 1), LOSS -> -1, per unit modal. Kaki tanpa
  harga beli yang valid (0 < harga < 100) tidak masuk rata-rata ini.
  Ingat: satu kaki parlay tidak berdiri sendiri — angka ini hanya
  menunjukkan apakah peluang yang dibeli, rata-rata, menguntungkan
  bila dimainkan satuan, bukan hasil tiket gabungan.

KEJUJURAN DATA:
- Bila file ledger tidak ada / tabel kosong / tidak ada kaki settled,
  muat_hasil_ledger mengembalikan {"ada_data": False, ...} dengan pesan
  yang menjelaskan keadaannya — TIDAK error, TIDAK mengarang angka.
  Saat ini (belum ada tiket nyata yang settle) itu keadaan yang benar.
- Pembacaan SELALU read-only (SQLite URI mode=ro): tidak membuat file
  bila belum ada, tidak mengubah satu byte pun.
- Tidak ada fetch jaringan, tidak ada tulis file, tidak ada ubah config.
  0 kredit Odds API.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from engine import validation as validation_mod
from ledger import store as store_mod

# Pemetaan nilai sport di ledger -> nilai sport di kontrak OUTCOME RECORD.
SPORT_LEDGER_KE_KONTRAK = {"nba": "NBA", "football": "soccer"}

# Hasil kaki yang berarti "dikeluarkan dari parlay" (DECISIONS.md A).
HASIL_DIKELUARKAN = ("VOID", "PUSH")


def _angka(nilai) -> float | None:
    """Ubah nilai menjadi float hingga, atau None bila bukan angka valid."""
    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        return None
    hasil = float(nilai)
    if hasil != hasil or hasil in (float("inf"), float("-inf")):
        return None
    return hasil


def _peluang_valid(nilai) -> float | None:
    """Peluang valid: angka hingga dalam [0, 1], atau None."""
    hasil = _angka(nilai)
    if hasil is None or not 0.0 <= hasil <= 1.0:
        return None
    return hasil


def _normalisasi_sport(nilai) -> str | None:
    """Petakan sport ledger ("nba"/"football") ke kontrak ("NBA"/"soccer").

    None tetap None; nilai lain yang tidak dikenal diteruskan apa adanya
    (tidak ditebak pemetaannya).
    """
    if nilai is None:
        return None
    return SPORT_LEDGER_KE_KONTRAK.get(nilai, nilai)


def _rekam_hasil(baris: dict, hasil_kaki: bool | None) -> dict:
    """Bangun satu OUTCOME RECORD dari satu baris tabel legs.

    hasil_kaki: True (WIN), False (LOSS), atau None (belum settle).
    ev_pct ledger (persen) dikonversi ke fraksi (lihat docstring modul).
    """
    ev_persen = _angka(baris.get("ev_pct"))
    return {
        "leg_id": baris.get("leg_id"),
        "ticket_id": baris.get("ticket_id"),
        "sport": _normalisasi_sport(baris.get("sport")),
        "market": baris.get("market"),
        "selection": baris.get("selection"),
        "p_model": _peluang_valid(baris.get("p_model")),
        "p_market": _peluang_valid(baris.get("p_market")),
        "p_final": _peluang_valid(baris.get("p_final")),
        "price_buy_cents": _angka(baris.get("price_buy_cents")),
        "price_close_cents": _angka(baris.get("price_close_cents")),
        "ev_pct": (ev_persen / 100.0) if ev_persen is not None else None,
        "result": hasil_kaki,
        "settled": hasil_kaki is not None,
        "sumber": "ledger",
    }


def _hasil_kosong(db_path: Path, pesan: str) -> dict:
    """Bentuk kembalian 'belum ada data' yang jujur."""
    return {
        "ada_data": False,
        "pesan": pesan,
        "outcomes": [],
        "n_settled": 0,
        "n_pending": 0,
        "n_dikeluarkan": 0,
        "n_hasil_tidak_dikenal": 0,
        "n_kaki_total": 0,
        "n_tiket": 0,
        "db_path": str(db_path),
    }


def muat_hasil_ledger(db_path: str | Path | None = None) -> dict:
    """Baca ledger (read-only) menjadi daftar OUTCOME RECORD.

    db_path None -> ledger.db default di root repo (ledger.store).
    Mengembalikan dict dengan kunci: ada_data, pesan, outcomes,
    n_settled, n_pending, n_dikeluarkan, n_hasil_tidak_dikenal,
    n_kaki_total, n_tiket, db_path.

    - File tidak ada / tabel legs tidak ada / tidak ada kaki settled ->
      ada_data False, outcomes [], dan pesan menjelaskan keadaannya.
      Hitungan n_pending / n_dikeluarkan tetap diisi bila bisa dibaca.
    - Ada kaki settled -> ada_data True; outcomes berisi kaki settled DAN
      kaki pending (VOID/PUSH dikeluarkan; hasil tak dikenal dikeluarkan
      dan dihitung di n_hasil_tidak_dikenal).
    - Tidak pernah menulis: koneksi SQLite dibuka mode=ro, dan file yang
      belum ada tidak dibuat.
    """
    path = Path(db_path) if db_path is not None else store_mod.DEFAULT_DB_PATH
    path = path.expanduser()
    if not path.exists():
        return _hasil_kosong(
            path,
            f"ledger belum ada ({path}): belum ada tiket yang dicatat, "
            "jadi belum ada hasil untuk dipelajari.",
        )
    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        return _hasil_kosong(path, f"ledger tidak bisa dibuka read-only: {exc}")
    try:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM legs ORDER BY ticket_id, id").fetchall()
        except sqlite3.Error:
            return _hasil_kosong(
                path,
                "ledger tidak punya tabel legs (file kosong atau bukan "
                "ledger): belum ada hasil untuk dipelajari.",
            )
    finally:
        conn.close()

    outcomes: list[dict] = []
    n_settled = 0
    n_pending = 0
    n_dikeluarkan = 0
    n_tidak_dikenal = 0
    tiket_id: set = set()
    for row in rows:
        baris = dict(row)
        tiket_id.add(baris.get("ticket_id"))
        result = baris.get("result")
        if result in ("WIN", "LOSS"):
            outcomes.append(_rekam_hasil(baris, result == "WIN"))
            n_settled += 1
        elif result in HASIL_DIKELUARKAN:
            n_dikeluarkan += 1
        elif result is None or result == "PENDING":
            outcomes.append(_rekam_hasil(baris, None))
            n_pending += 1
        else:
            # Nilai result di luar skema (misal edit manual): dikeluarkan,
            # dihitung terpisah supaya tidak hilang diam-diam.
            n_tidak_dikenal += 1

    if n_settled == 0:
        hasil = _hasil_kosong(
            path,
            "belum ada kaki yang settle di ledger "
            f"({n_pending} pending, {n_dikeluarkan} VOID/PUSH dikeluarkan): "
            "belum ada hasil untuk dipelajari.",
        )
        hasil["n_pending"] = n_pending
        hasil["n_dikeluarkan"] = n_dikeluarkan
        hasil["n_hasil_tidak_dikenal"] = n_tidak_dikenal
        hasil["n_kaki_total"] = len(rows)
        hasil["n_tiket"] = len(tiket_id)
        return hasil

    return {
        "ada_data": True,
        "pesan": (
            f"{n_settled} kaki settled dari {len(tiket_id)} tiket "
            f"({n_pending} pending, {n_dikeluarkan} VOID/PUSH dikeluarkan"
            + (
                f", {n_tidak_dikenal} hasil tidak dikenal dikeluarkan"
                if n_tidak_dikenal
                else ""
            )
            + ")."
        ),
        "outcomes": outcomes,
        "n_settled": n_settled,
        "n_pending": n_pending,
        "n_dikeluarkan": n_dikeluarkan,
        "n_hasil_tidak_dikenal": n_tidak_dikenal,
        "n_kaki_total": len(rows),
        "n_tiket": len(tiket_id),
        "db_path": str(path),
    }


def _kaki_settled(outcomes: list[dict]) -> list[dict]:
    """Kaki yang sudah settle dengan hasil WIN/LOSS yang jelas."""
    return [
        o
        for o in outcomes
        if o.get("settled") is True and o.get("result") in (True, False)
    ]


def _pasangan_brier(kaki: list[dict], kunci: str) -> list[tuple[float, bool]]:
    """Pasangan (p, terjadi) untuk Brier: hanya kaki dengan nilai valid."""
    pairs: list[tuple[float, bool]] = []
    for o in kaki:
        p = _peluang_valid(o.get(kunci))
        if p is not None:
            pairs.append((p, bool(o["result"])))
    return pairs


def _brier_atau_alasan(
    kaki: list[dict], kunci: str, label: str
) -> tuple[float | None, int, str | None]:
    """Brier satu sumber peluang: (nilai, n_kaki, alasan_bila_None)."""
    pairs = _pasangan_brier(kaki, kunci)
    if not pairs:
        return None, 0, f"tidak ada kaki settled dengan {label} yang valid"
    return validation_mod.brier_score(pairs), len(pairs), None


def _ringkasan_satu(kaki: list[dict]) -> dict:
    """Ringkasan statistik satu kelompok kaki settled (murni, tanpa I/O).

    Kunci: n, win_rate, brier_model/market/final (+ n_ dan alasan_ tiap
    Brier), brier_climatology (+ alasan), ev_prediksi_rata2,
    ev_terealisasi_rata2 (+ n_ dan alasan_ tiap EV).
    Kelompok kosong (n=0): semua nilai None + alasan "belum ada kaki
    settled".
    """
    alasan_kosong = "belum ada kaki settled"
    if not kaki:
        return {
            "n": 0,
            "win_rate": None,
            "brier_model": None,
            "n_brier_model": 0,
            "alasan_brier_model": alasan_kosong,
            "brier_market": None,
            "n_brier_market": 0,
            "alasan_brier_market": alasan_kosong,
            "brier_final": None,
            "n_brier_final": 0,
            "alasan_brier_final": alasan_kosong,
            "brier_climatology": None,
            "alasan_brier_climatology": alasan_kosong,
            "ev_prediksi_rata2": None,
            "n_ev_prediksi": 0,
            "alasan_ev_prediksi": alasan_kosong,
            "ev_terealisasi_rata2": None,
            "n_ev_terealisasi": 0,
            "alasan_ev_terealisasi": alasan_kosong,
        }

    n = len(kaki)
    menang = sum(1 for o in kaki if o["result"] is True)
    win_rate = menang / n

    brier_model, n_model, alasan_model = _brier_atau_alasan(kaki, "p_model", "p_model")
    brier_market, n_market, alasan_market = _brier_atau_alasan(
        kaki, "p_market", "p_market"
    )
    brier_final, n_final, alasan_final = _brier_atau_alasan(kaki, "p_final", "p_final")
    # Klimatologi: frekuensi kemenangan aktual sebagai prediksi konstan.
    pairs_klim = [(win_rate, bool(o["result"])) for o in kaki]
    brier_climatology = validation_mod.brier_score(pairs_klim)

    ev_prediksi = [
        ev for ev in (_angka(o.get("ev_pct")) for o in kaki) if ev is not None
    ]
    if ev_prediksi:
        ev_prediksi_rata2 = sum(ev_prediksi) / len(ev_prediksi)
        n_ev_prediksi = len(ev_prediksi)
        alasan_ev_prediksi = None
    else:
        ev_prediksi_rata2 = None
        n_ev_prediksi = 0
        alasan_ev_prediksi = "tidak ada kaki settled dengan ev_pct yang valid"

    # EV terealisasi per unit modal per kaki — diagnostik, BUKAN P/L tiket.
    returns: list[float] = []
    for o in kaki:
        harga = _angka(o.get("price_buy_cents"))
        if harga is None or not 0.0 < harga < 100.0:
            continue
        returns.append((100.0 / harga - 1.0) if o["result"] is True else -1.0)
    if returns:
        ev_terealisasi_rata2 = sum(returns) / len(returns)
        n_ev_terealisasi = len(returns)
        alasan_ev_terealisasi = None
    else:
        ev_terealisasi_rata2 = None
        n_ev_terealisasi = 0
        alasan_ev_terealisasi = (
            "tidak ada kaki settled dengan harga beli yang valid (0-100 sen)"
        )

    return {
        "n": n,
        "win_rate": win_rate,
        "brier_model": brier_model,
        "n_brier_model": n_model,
        "alasan_brier_model": alasan_model,
        "brier_market": brier_market,
        "n_brier_market": n_market,
        "alasan_brier_market": alasan_market,
        "brier_final": brier_final,
        "n_brier_final": n_final,
        "alasan_brier_final": alasan_final,
        "brier_climatology": brier_climatology,
        "alasan_brier_climatology": None,
        "ev_prediksi_rata2": ev_prediksi_rata2,
        "n_ev_prediksi": n_ev_prediksi,
        "alasan_ev_prediksi": alasan_ev_prediksi,
        "ev_terealisasi_rata2": ev_terealisasi_rata2,
        "n_ev_terealisasi": n_ev_terealisasi,
        "alasan_ev_terealisasi": alasan_ev_terealisasi,
    }


def ringkasan_per_pasar(outcomes: list[dict]) -> dict:
    """Ringkasan per (sport, market): {(sport, market): ringkasan}.

    Hanya kaki settled yang dihitung; pasar tanpa kaki settled tidak
    muncul. Fungsi murni (tanpa I/O, tanpa config).
    """
    kelompok: dict[tuple, list[dict]] = {}
    for o in _kaki_settled(outcomes):
        kunci = (o.get("sport"), o.get("market"))
        kelompok.setdefault(kunci, []).append(o)
    return {kunci: _ringkasan_satu(kaki) for kunci, kaki in kelompok.items()}


def ringkasan_keseluruhan(outcomes: list[dict]) -> dict:
    """Ringkasan gabungan semua kaki settled (fungsi murni, tanpa I/O)."""
    return _ringkasan_satu(_kaki_settled(outcomes))
