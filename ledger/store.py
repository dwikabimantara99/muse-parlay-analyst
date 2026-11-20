"""Ledger SQLite — Blueprint §9.

Dua tabel utama:

- ``tickets``: id, waktu, jenis (Asuransi/Utama), modal, pengali, hasil,
  untung/rugi. Untung/rugi SELALU dihitung kode dari modal x pengali x hasil
  (aturan kerja 1) — tidak pernah diambil dari input.
- ``legs``: ticket_id, laga, pasar, p_model, p_pasar, p_akhir, harga_beli,
  harga_tutup, hasil, lampu kritikus.

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
TICKET_RESULTS = ("WIN", "LOSS", "PUSH", "VOID", "PENDING")
LEG_RESULTS = ("WIN", "LOSS", "PUSH", "VOID")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    placed_at TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('Asuransi', 'Utama')),
    stake REAL NOT NULL CHECK (stake > 0),
    multiplier REAL NOT NULL CHECK (multiplier > 1),
    result TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (result IN ('WIN', 'LOSS', 'PUSH', 'VOID', 'PENDING')),
    profit_loss REAL,
    settled_at TEXT,
    slate_id TEXT,
    option_label TEXT,
    combo_spread_pct REAL,
    notes TEXT
);
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
    result TEXT
);
CREATE INDEX IF NOT EXISTS idx_legs_ticket_id ON legs(ticket_id);
"""


class LedgerError(Exception):
    """Tiket tidak valid, duplikat, atau operasi ledger gagal."""


def compute_profit_loss(stake: float, multiplier: float, result: str) -> float | None:
    """Hitung untung/rugi tiket dari modal, pengali, dan hasil.

    WIN  -> stake * multiplier - stake (modal kembali + untung)
    LOSS -> -stake
    PUSH / VOID -> 0.0 (modal kembali utuh)
    PENDING -> None (belum ada hasil, jangan dihitung)
    """
    if result == "WIN":
        return stake * multiplier - stake
    if result == "LOSS":
        return -stake
    if result in ("PUSH", "VOID"):
        return 0.0
    if result == "PENDING":
        return None
    raise LedgerError(f"hasil tiket tidak dikenal: {result!r}")


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Buka koneksi SQLite + pastikan skema ada. Buat file bila belum ada."""
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
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


def log_ticket(conn: sqlite3.Connection, ticket: dict) -> str:
    """Catat satu tiket + kaki-kakinya ke ledger.

    - Tiket divalidasi terhadap skema dulu; gagal = ditolak.
    - Untung/rugi dihitung di sini, bukan dari input (input tidak punya
      field profit_loss — skema menolak additionalProperties).
    - Duplikat id ditolak (tidak menimpa diam-diam).
    Mengembalikan id tiket.
    """
    validate_ticket(ticket)
    ticket_id = ticket["ticket_id"]
    result = ticket.get("result", "PENDING")
    profit_loss = compute_profit_loss(
        float(ticket["stake"]), float(ticket["multiplier"]), result
    )
    placed_at = ticket.get("placed_at") or datetime.now(timezone.utc).isoformat()
    settled_at = placed_at if result != "PENDING" else None

    try:
        conn.execute(
            """
            INSERT INTO tickets
                (id, placed_at, type, stake, multiplier, result,
                 profit_loss, settled_at, slate_id, option_label,
                 combo_spread_pct, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                placed_at,
                ticket["type"],
                float(ticket["stake"]),
                float(ticket["multiplier"]),
                result,
                profit_loss,
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
                 anomaly_reason, critic_light, result)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
) -> float | None:
    """Tetapkan hasil tiket PENDING (dan opsional hasil per kaki).

    leg_results: {leg_id: 'WIN'|'LOSS'|'PUSH'|'VOID'}.
    Mengembalikan untung/rugi yang dihitung. Raise LedgerError bila tiket
    tidak ada atau result tidak valid.
    """
    if result not in TICKET_RESULTS or result == "PENDING":
        raise LedgerError(
            f"hasil settlement harus WIN/LOSS/PUSH/VOID, bukan {result!r}"
        )
    row = conn.execute(
        "SELECT stake, multiplier, result FROM tickets WHERE id = ?",
        (ticket_id,),
    ).fetchone()
    if row is None:
        raise LedgerError(f"tiket tidak ditemukan: {ticket_id!r}")
    profit_loss = compute_profit_loss(
        float(row["stake"]), float(row["multiplier"]), result
    )
    conn.execute(
        """
        UPDATE tickets SET result = ?, profit_loss = ?,
            settled_at = ? WHERE id = ?
        """,
        (result, profit_loss, datetime.now(timezone.utc).isoformat(), ticket_id),
    )
    for leg_id, leg_result in (leg_results or {}).items():
        if leg_result not in LEG_RESULTS:
            raise LedgerError(f"hasil kaki tidak dikenal: {leg_result!r}")
        conn.execute(
            "UPDATE legs SET result = ? WHERE ticket_id = ? AND leg_id = ?",
            (leg_result, ticket_id, leg_id),
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
    ticket["legs"] = [dict(leg) for leg in legs]
    return ticket


def list_tickets(conn: sqlite3.Connection) -> list[dict]:
    """Semua tiket, diurutkan dari yang terbaru."""
    rows = conn.execute(
        "SELECT * FROM tickets ORDER BY placed_at DESC, id DESC"
    ).fetchall()
    return [dict(row) for row in rows]
