"""Rekap ledger — Blueprint §9 (perintah /rekap).

Menampilkan untung/rugi, ROI, dan performa per jenis tiket. Semua angka
dihitung dari tabel SQLite di sini — tidak ada angka dari tempat lain.
Hanya tiket yang sudah settled (WIN/LOSS/PUSH/VOID) yang masuk hitungan
untung/rugi; tiket PENDING dilaporkan terpisah.
"""

from __future__ import annotations

import sqlite3


def compute_recap(conn: sqlite3.Connection) -> dict:
    """Agregasi ledger menjadi satu dict angka.

    ROI = untung/rugi / total modal tiket settled * 100.
    """
    recap: dict = {
        "settled": {"count": 0, "staked": 0.0, "returned": 0.0, "profit": 0.0},
        "pending": {"count": 0, "staked": 0.0},
        "by_type": {},
        "legs": {"total": 0, "settled": 0, "won": 0},
    }

    for row in conn.execute("SELECT * FROM tickets"):
        ticket_type = row["type"]
        stake = float(row["stake"])
        per_type = recap["by_type"].setdefault(
            ticket_type,
            {"count": 0, "staked": 0.0, "returned": 0.0, "profit": 0.0},
        )
        if row["result"] == "PENDING":
            recap["pending"]["count"] += 1
            recap["pending"]["staked"] += stake
            continue
        profit = float(row["profit_loss"])
        returned = stake + profit
        recap["settled"]["count"] += 1
        recap["settled"]["staked"] += stake
        recap["settled"]["returned"] += returned
        recap["settled"]["profit"] += profit
        per_type["count"] += 1
        per_type["staked"] += stake
        per_type["returned"] += returned
        per_type["profit"] += profit

    staked = recap["settled"]["staked"]
    recap["settled"]["roi_pct"] = (
        (recap["settled"]["profit"] / staked * 100.0) if staked else 0.0
    )
    for per_type in recap["by_type"].values():
        t_staked = per_type["staked"]
        per_type["roi_pct"] = (
            (per_type["profit"] / t_staked * 100.0) if t_staked else 0.0
        )

    for row in conn.execute("SELECT result FROM legs"):
        recap["legs"]["total"] += 1
        if row["result"] is not None:
            recap["legs"]["settled"] += 1
            if row["result"] == "WIN":
                recap["legs"]["won"] += 1
    settled_legs = recap["legs"]["settled"]
    recap["legs"]["win_rate_pct"] = (
        (recap["legs"]["won"] / settled_legs * 100.0) if settled_legs else 0.0
    )
    return recap


def format_recap(recap: dict) -> str:
    """Format rekap menjadi teks Bahasa Indonesia untuk terminal/Telegram."""
    settled = recap["settled"]
    pending = recap["pending"]
    legs = recap["legs"]
    lines = [
        "🧾 REKAP LEDGER",
        f"Tiket selesai: {settled['count']}",
        f"Total modal: ${settled['staked']:.2f}",
        f"Total kembali: ${settled['returned']:.2f}",
        f"Untung/rugi: ${settled['profit']:+.2f}",
        f"ROI: {settled['roi_pct']:+.2f}%",
        "",
        "Per jenis tiket:",
    ]
    for ticket_type in sorted(recap["by_type"]):
        per_type = recap["by_type"][ticket_type]
        lines.append(
            f"  {ticket_type}: {per_type['count']} tiket | "
            f"modal ${per_type['staked']:.2f} | "
            f"untung/rugi ${per_type['profit']:+.2f} | "
            f"ROI {per_type['roi_pct']:+.2f}%"
        )
    lines += [
        "",
        f"Kaki: {legs['total']} total, {legs['settled']} selesai, "
        f"{legs['won']} menang ({legs['win_rate_pct']:.1f}%)",
        f"Tiket pending: {pending['count']} "
        f"(modal ${pending['staked']:.2f} belum dihitung)",
    ]
    return "\n".join(lines)
