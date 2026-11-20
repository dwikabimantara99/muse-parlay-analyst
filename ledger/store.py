"""Ledger SQLite — Blueprint §9 + DECISIONS.md (bagian A).

Dua tabel utama:

- ``tickets``: id, waktu, jenis (Asuransi/Utama), modal, pengali, hasil,
  untung/rugi. Untung/rugi SELALU dihitung kode dari modal x pengali x hasil
  (aturan kerja 1) — tidak pernah diambil dari input.
- ``legs``: ticket_id, laga, pasar, p_model, p_pasar, p_akhir, harga_beli,
  harga_tutup, hasil, lampu kritikus.

Aturan kaki VOID/PUSH (DECISIONS.md A): kaki VOID/PUSH dikeluarkan, pengali
tiket dihitung ulang dari kaki sisanya (rumus DECISIONS.md D8). Tiket tidak
otomatis VOID — kecuali semua kakinya VOID/PUSH. Pengali awal disimpan di
``multiplier_original`` sebagai jejak audit.

Hasil CASHOUT: untung/rugi = cashout_amount - modal. ``cashout_amount``
wajib diisi saat hasil CASHOUT.

File database default: ``ledger.db`` di root repo (masuk .gitignore).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "ledger.db"
TICKET_SCHEMA_PATH = REPO_ROOT / "schemas" / "ticket.schema.json"

TICKET_TYPES = ("Asuransi", "Utama")
TICKET_RESULTS = ("WIN", "LOSS", "PUSH", "VOID", "PENDING", "CASHOUT")
LEG_RESULTS = ("WIN", "LOSS", "PUSH", "VOID")
# Kaki dengan hasil ini dikeluarkan dari parlay (DECISIONS.md A).
VOID_PUSH_RESULTS = ("VOID", "PUSH")

TICKETS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    placed_at TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('Asuransi', 'Utama')),
    stake REAL NOT NULL CHECK (stake > 0),
    /* Pengali > 0 (bukan > 1): pengali hitung ulang bisa <= 1 pada kasus
       ekstrem (satu kaki favorit berat tersisa setelah VOID) — itu hasil
       hitung yang jujur, bukan kesalahan. Skema input tiket tetap menuntut
       pengali awal > 1. */
    multiplier REAL NOT NULL CHECK (multiplier > 0),
    result TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (result IN ('WIN', 'LOSS', 'PUSH', 'VOID', 'PENDING', 'CASHOUT')),
    profit_loss REAL,
    cashout_amount REAL,
    multiplier_original REAL,
    settled_at TEXT,
    slate_id TEXT,
    option_label TEXT,
    combo_spread_pct REAL,
    notes TEXT
);
"""

LEGS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS legs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL REFERENCES tickets(id),
    leg_id TEXT,
    match_id TEXT,
    sport TEXT,
    market TEXT,
    selection TEXT,
    p_model REAL,
    p_market REAL,
    p_final REAL,
    price_buy_cents REAL,
    price_close_cents REAL,
    edge REAL,
    ev_pct REAL,
    status TEXT,
    filter_reason TEXT,
    anomaly_reason TEXT,
    critic_light TEXT,
    flags_json TEXT,
    result TEXT
);
CREATE INDEX IF NOT EXISTS idx_legs_ticket_id ON legs(ticket_id);
"""

SCHEMA_SQL = TICKETS_SCHEMA_SQL + LEGS_SCHEMA_SQL


class LedgerError(Exception):
    """Tiket tidak valid, duplikat, atau operasi ledger gagal."""


def compute_profit_loss(
    stake: float,
    multiplier: float,
    result: str,
    cashout_amount: float | None = None,
) -> float | None:
    """Hitung untung/rugi tiket dari modal, pengali, dan hasil.

    WIN     -> stake * multiplier - stake (modal kembali + untung)
    LOSS    -> -stake
    PUSH / VOID -> 0.0 (modal kembali utuh)
    CASHOUT -> cashout_amount - stake (cashout_amount wajib diisi)
    PENDING -> None (belum ada hasil, jangan dihitung)
    """
    if result == "WIN":
        return stake * multiplier - stake
    if result == "LOSS":
        return -stake
    if result in ("PUSH", "VOID"):
        return 0.0
    if result == "CASHOUT":
        if cashout_amount is None:
            raise LedgerError("hasil CASHOUT wajib menyertakan cashout_amount")
        return cashout_amount - stake
    if result == "PENDING":
        return None
    raise LedgerError(f"hasil tiket tidak dikenal: {result!r}")


def recompute_multiplier(
    prices_cents: list[float], combo_spread_pct: float
) -> float:
    """Hitung ulang pengali dari harga ¢ kaki-kaki yang tersisa.

    Rumus DECISIONS.md D8: Π(100 / harga_¢_i) × (1 − spread/100).
    Daftar kosong = tidak ada kaki tersisa -> LedgerError (panggil hanya
    kalau masih ada kaki; kalau semua kaki VOID/PUSH, tiket jadi VOID).
    """
    if not prices_cents:
        raise LedgerError(
            "tidak bisa menghitung ulang pengali: tidak ada kaki tersisa"
        )
    product = 1.0
    for price in prices_cents:
        if price is None or price <= 0 or price >= 100:
            raise LedgerError(f"harga ¢ tidak valid untuk hitung ulang: {price!r}")
        product *= 100.0 / price
    return product * (1.0 - combo_spread_pct / 100.0)


def _resolve_spread(ticket_spread: float | None) -> float:
    """Spread untuk hitung ulang pengali: spread tiket bila ada, kalau tidak
    default dari playstyle.yaml. Jangan menebak angka lain."""
    if ticket_spread is not None:
        return float(ticket_spread)
    import config as config_mod

    cfg = config_mod.load_playstyle()
    return float(config_mod.get_value(cfg, "combo", "spread_cut_pct"))


def _migrate(conn: sqlite3.Connection) -> None:
    """Migrasikan database lama (Tahap 1) ke skema sekarang.

    - Tambah kolom cashout_amount & multiplier_original bila belum ada.
    - Bangun ulang tabel tickets bila CHECK result belum mengenal CASHOUT
      (data dipertahankan; kolom baru diisi NULL).
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tickets)")}
    if "cashout_amount" not in cols:
        conn.execute("ALTER TABLE tickets ADD COLUMN cashout_amount REAL")
    if "multiplier_original" not in cols:
        conn.execute("ALTER TABLE tickets ADD COLUMN multiplier_original REAL")
    leg_cols = {row[1] for row in conn.execute("PRAGMA table_info(legs)")}
    if "flags_json" not in leg_cols:
        conn.execute("ALTER TABLE legs ADD COLUMN flags_json TEXT")
    sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'tickets'"
    ).fetchone()
    if sql_row is not None and "CASHOUT" not in (sql_row[0] or ""):
        conn.execute("ALTER TABLE tickets RENAME TO tickets_old")
        conn.executescript(TICKETS_SCHEMA_SQL)
        conn.execute(
            """
            INSERT INTO tickets
                (id, placed_at, type, stake, multiplier, result,
                 profit_loss, cashout_amount, multiplier_original,
                 settled_at, slate_id, option_label, combo_spread_pct, notes)
            SELECT id, placed_at, type, stake, multiplier, result,
                 profit_loss, cashout_amount, multiplier_original,
                 settled_at, slate_id, option_label, combo_spread_pct, notes
            FROM tickets_old
            """
        )
        conn.execute("DROP TABLE tickets_old")
    conn.commit()


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Buka koneksi SQLite + pastikan skema ada. Buat file bila belum ada.

    Database lama dimigrasikan otomatis (lihat _migrate).
    """
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    _migrate(conn)
    conn.commit()
    return conn


def _load_ticket_schema() -> dict:
    return json.loads(TICKET_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_ticket(ticket: dict) -> None:
    """Validasi tiket terhadap schemas/ticket.schema.json.

    Raise LedgerError bila tidak lolos — tiket seperti itu TIDAK BOLEH
    masuk ledger.
    """
    try:
        jsonschema.validate(instance=ticket, schema=_load_ticket_schema())
    except jsonschema.ValidationError as exc:
        raise LedgerError(f"tiket tidak lolos skema: {exc.message}") from exc


def _check_consistency(result: str, leg_results: list) -> None:
    """Tolak hasil tiket yang bertentangan dengan hasil kaki-kakinya.

    - WIN tapi ada kaki LOSS -> tidak konsisten.
    - LOSS tapi semua kaki yang sudah selesai WIN -> tidak konsisten.
    Kaki VOID/PUSH dan kaki belum selesai tidak dihitung. Hasil lain
    (PUSH/VOID/CASHOUT/PENDING) tidak diperiksa — itu keputusan pencatat.
    """
    settled = [r for r in leg_results if r is not None and r not in VOID_PUSH_RESULTS]
    if result == "WIN" and "LOSS" in settled:
        raise LedgerError("hasil tiket WIN tapi ada kaki LOSS")
    if result == "LOSS" and settled and all(r == "WIN" for r in settled):
        raise LedgerError("hasil tiket LOSS tapi semua kaki yang selesai WIN")


def _apply_void_push(
    legs: list[dict], multiplier: float, combo_spread_pct: float | None
) -> tuple[float, float | None, bool]:
    """Terapkan aturan VOID/PUSH (DECISIONS.md A) pada daftar kaki.

    legs: dict per kaki dengan kunci 'result' dan 'price_cents'.
    Mengembalikan (multiplier_baru, multiplier_original, semua_void).
    - Ada kaki VOID/PUSH dan masih ada kaki tersisa -> pengali dihitung
      ulang dari kaki sisanya, pengali awal dikembalikan sebagai
      multiplier_original.
    - Semua kaki VOID/PUSH -> semua_void True, pengali tidak berubah.
    - Tidak ada kaki VOID/PUSH -> pengali tidak berubah.
    """
    void_legs = [leg for leg in legs if leg.get("result") in VOID_PUSH_RESULTS]
    if not void_legs:
        return multiplier, None, False
    remaining = [leg for leg in legs if leg.get("result") not in VOID_PUSH_RESULTS]
    if not remaining:
        return multiplier, None, True
    spread = _resolve_spread(combo_spread_pct)
    prices = [leg["price_cents"] for leg in remaining]
    return recompute_multiplier(prices, spread), multiplier, False


def log_ticket(conn: sqlite3.Connection, ticket: dict) -> str:
    """Catat satu tiket + kaki-kakinya ke ledger.

    - Tiket divalidasi terhadap skema dulu; gagal = ditolak.
    - Untung/rugi dihitung di sini, bukan dari input (input tidak punya
      field profit_loss — skema menolak additionalProperties).
    - Kaki VOID/PUSH: pengali dihitung ulang dari kaki sisanya; pengali
      awal disimpan di multiplier_original. Semua kaki VOID/PUSH tapi
      hasil tiket bukan VOID/PUSH -> ditolak (tidak konsisten).
    - CASHOUT wajib menyertakan cashout_amount.
    - Duplikat id ditolak (tidak menimpa diam-diam).
    Mengembalikan id tiket.
    """
    validate_ticket(ticket)
    ticket_id = ticket["ticket_id"]
    result = ticket.get("result", "PENDING")
    cashout_amount = ticket.get("cashout_amount")
    stake = float(ticket["stake"])
    multiplier = float(ticket["multiplier"])

    legs_for_calc = [
        {"result": leg.get("result"), "price_cents": leg.get("jup_price_cents")}
        for leg in ticket["legs"]
    ]
    multiplier, multiplier_original, all_void = _apply_void_push(
        legs_for_calc, multiplier, ticket.get("combo_spread_pct")
    )
    if all_void and result not in ("VOID", "PUSH"):
        raise LedgerError(
            f"semua kaki {ticket_id!r} VOID/PUSH tapi hasil tiket {result!r}"
        )
    _check_consistency(result, [leg.get("result") for leg in ticket["legs"]])
    profit_loss = compute_profit_loss(stake, multiplier, result, cashout_amount)
    placed_at = ticket.get("placed_at") or datetime.now(timezone.utc).isoformat()
    settled_at = placed_at if result != "PENDING" else None

    try:
        conn.execute(
            """
            INSERT INTO tickets
                (id, placed_at, type, stake, multiplier, result,
                 profit_loss, cashout_amount, multiplier_original,
                 settled_at, slate_id, option_label,
                 combo_spread_pct, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                placed_at,
                ticket["type"],
                stake,
                multiplier,
                result,
                profit_loss,
                cashout_amount,
                multiplier_original,
                settled_at,
                ticket.get("slate_id"),
                ticket.get("option_label"),
                ticket.get("combo_spread_pct"),
                ticket.get("notes"),
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise LedgerError(f"tiket {ticket_id!r} sudah ada di ledger") from exc

    for leg in ticket["legs"]:
        conn.execute(
            """
            INSERT INTO legs
                (ticket_id, leg_id, match_id, sport, market, selection,
                 p_model, p_market, p_final, price_buy_cents,
                 price_close_cents, edge, ev_pct, status, filter_reason,
                 anomaly_reason, critic_light, flags_json, result)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                leg.get("leg_id"),
                leg.get("match_id"),
                leg.get("sport"),
                leg.get("market"),
                leg.get("selection"),
                leg.get("p_model"),
                leg.get("p_market"),
                leg.get("p_final"),
                leg.get("jup_price_cents"),
                leg.get("price_close_cents"),
                leg.get("edge"),
                leg.get("ev_pct"),
                leg.get("status"),
                leg.get("filter_reason"),
                leg.get("anomaly_reason"),
                leg.get("critic_light"),
                json.dumps(leg.get("flags") or []),
                leg.get("result"),
            ),
        )
    conn.commit()
    return ticket_id


def settle_ticket(
    conn: sqlite3.Connection,
    ticket_id: str,
    result: str,
    leg_results: dict[str, str] | None = None,
    cashout_amount: float | None = None,
) -> float | None:
    """Tetapkan hasil tiket (dan opsional hasil per kaki).

    leg_results: {leg_id: 'WIN'|'LOSS'|'PUSH'|'VOID'}.
    cashout_amount: wajib bila result CASHOUT.

    Kaki VOID/PUSH: pengali dihitung ulang dari kaki sisanya (DECISIONS.md
    A); kalau semua kaki VOID/PUSH, hasil tiket menjadi VOID (kecuali
    CASHOUT yang dihormati apa adanya). Hasil tiket yang bertentangan
    dengan hasil kaki ditolak.
    Mengembalikan untung/rugi yang dihitung. Raise LedgerError bila tiket
    tidak ada, kaki tidak ada, atau input tidak konsisten.
    """
    if result not in TICKET_RESULTS or result == "PENDING":
        raise LedgerError(
            "hasil settlement harus WIN/LOSS/PUSH/VOID/CASHOUT, "
            f"bukan {result!r}"
        )
    row = conn.execute(
        "SELECT stake, multiplier, multiplier_original, combo_spread_pct"
        " FROM tickets WHERE id = ?",
        (ticket_id,),
    ).fetchone()
    if row is None:
        raise LedgerError(f"tiket tidak ditemukan: {ticket_id!r}")

    for leg_id, leg_result in (leg_results or {}).items():
        if leg_result not in LEG_RESULTS:
            raise LedgerError(f"hasil kaki tidak dikenal: {leg_result!r}")
        cursor = conn.execute(
            "UPDATE legs SET result = ? WHERE ticket_id = ? AND leg_id = ?",
            (leg_result, ticket_id, leg_id),
        )
        if cursor.rowcount == 0:
            raise LedgerError(
                f"kaki tidak ditemukan di tiket {ticket_id!r}: {leg_id!r}"
            )

    legs = conn.execute(
        "SELECT leg_id, price_buy_cents, result FROM legs"
        " WHERE ticket_id = ? ORDER BY id",
        (ticket_id,),
    ).fetchall()
    legs_for_calc = [
        {"result": leg["result"], "price_cents": leg["price_buy_cents"]}
        for leg in legs
    ]
    multiplier = float(row["multiplier"])
    multiplier_original = row["multiplier_original"]
    multiplier, new_original, all_void = _apply_void_push(
        legs_for_calc, multiplier, row["combo_spread_pct"]
    )
    if new_original is not None and multiplier_original is None:
        multiplier_original = new_original
    if all_void and result != "CASHOUT":
        result = "VOID"
    _check_consistency(result, [leg["result"] for leg in legs])
    profit_loss = compute_profit_loss(
        float(row["stake"]), multiplier, result, cashout_amount
    )
    conn.execute(
        """
        UPDATE tickets SET result = ?, profit_loss = ?,
            cashout_amount = ?, multiplier = ?,
            multiplier_original = ?, settled_at = ? WHERE id = ?
        """,
        (
            result,
            profit_loss,
            cashout_amount,
            multiplier,
            multiplier_original,
            datetime.now(timezone.utc).isoformat(),
            ticket_id,
        ),
    )
    conn.commit()
    return profit_loss


def get_ticket(conn: sqlite3.Connection, ticket_id: str) -> dict | None:
    """Ambil satu tiket + kaki-kakinya, atau None bila tidak ada."""
    row = conn.execute(
        "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
    ).fetchone()
    if row is None:
        return None
    ticket = dict(row)
    legs = conn.execute(
        "SELECT * FROM legs WHERE ticket_id = ? ORDER BY id", (ticket_id,)
    ).fetchall()
    parsed_legs = []
    for leg in legs:
        leg_dict = dict(leg)
        leg_dict["flags"] = json.loads(leg_dict.pop("flags_json") or "[]")
        parsed_legs.append(leg_dict)
    ticket["legs"] = parsed_legs
    return ticket


def list_tickets(conn: sqlite3.Connection) -> list[dict]:
    """Semua tiket, diurutkan dari yang terbaru."""
    rows = conn.execute(
        "SELECT * FROM tickets ORDER BY placed_at DESC, id DESC"
    ).fetchall()
    return [dict(row) for row in rows]
