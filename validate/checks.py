"""Validasi kelengkapan & umur data per laga — Tahap 2b.

Menilai satu dict MatchData menjadi OK / HOLD / DATA_INCOMPLETE.

ATURAN (kontrak 2b — SOP langkah 3, DECISIONS.md B2/B3):

1. Cedera 0 sumber -> DATA_INCOMPLETE. Sumber cedera dihitung dari entri
   ``sources[]`` dengan ``data_kind`` cedera/lineup (``nba_injuries``,
   ``football_lineup_injuries``), dihitung per nama sumber yang berbeda.
2. Cedera 1 sumber -> HOLD ("B2 butuh 2 sumber": cedera & lineup wajib
   dicek silang minimal 2 sumber).
3. Stats kosong -> DATA_INCOMPLETE.
4. ``market_prices`` kosong (tidak ada harga jup.ag) -> DATA_INCOMPLETE.
5. Cedera/lineup lebih tua dari ``stale_hours`` -> HOLD ("basi"). Yang
   dinilai adalah ``fetched_at`` TERBARU di antara sumber cedera/lineup:
   bila sumber paling segar pun sudah basi, datanya basi. ``fetched_at``
   yang tidak bisa dibaca diperlakukan sebagai basi (tidak bisa dibuktikan
   segar).
6. ``p_market`` kosong di semua pasar BUKAN incompleteness — ditangani
   label MODEL_ONLY di slate builder (DECISIONS.md D2), bukan di sini.

Precedence: DATA_INCOMPLETE mengalahkan HOLD; HOLD mengalahkan OK.
``status_reason`` di MatchData adalah gabungan semua alasan (dipisah "; ").
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# data_kind (kunci sources.yaml) yang membawa data cedera/lineup.
INJURY_DATA_KINDS = frozenset({"nba_injuries", "football_lineup_injuries"})


def _parse_time(value: object) -> datetime | None:
    """Parse ISO 8601 menjadi datetime ber-timezone; None bila gagal."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def validate_match_data(
    match: dict,
    stale_hours_injury_lineup: float,
    now: datetime | None = None,
) -> dict:
    """Nilai satu laga -> {"status": "OK"|"HOLD"|"DATA_INCOMPLETE", "reasons": [...]}.

    ``stale_hours_injury_lineup`` dibaca dari config (playstyle.yaml ->
    ``data.stale_hours_injury_lineup``), bukan dari kode. ``now`` bisa
    di-inject (untuk tes); default jam sekarang (UTC).
    """
    reasons_incomplete: list[str] = []
    reasons_hold: list[str] = []
    sources = match.get("sources") or []
    injury_sources = [
        entry
        for entry in sources
        if isinstance(entry, dict) and entry.get("data_kind") in INJURY_DATA_KINDS
    ]
    distinct_sources = {
        entry.get("source") for entry in injury_sources if entry.get("source")
    }

    # Aturan 1-2: jumlah sumber cedera.
    if len(distinct_sources) == 0:
        reasons_incomplete.append("cedera: 0 sumber (B2 butuh min 2 sumber)")
    elif len(distinct_sources) == 1:
        reasons_hold.append("cedera: hanya 1 sumber (B2 butuh 2 sumber)")

    # Aturan 3: stats kosong.
    if not match.get("stats"):
        reasons_incomplete.append("stats kosong")

    # Aturan 4: tidak ada harga jup.ag.
    if not match.get("market_prices"):
        reasons_incomplete.append("market_prices kosong (tidak ada harga jup.ag)")

    # Aturan 5: kebasian cedera/lineup (hanya bila ada sumbernya).
    if injury_sources:
        moment = now or datetime.now(UTC)
        fetched_times = [
            _parse_time(entry.get("fetched_at")) for entry in injury_sources
        ]
        readable = [time for time in fetched_times if time is not None]
        if not readable:
            reasons_hold.append("cedera/lineup: jam pengambilan tidak bisa dibaca")
        else:
            newest = max(readable)
            if moment - newest > timedelta(hours=stale_hours_injury_lineup):
                reasons_hold.append(
                    "cedera/lineup basi " f"(>{stale_hours_injury_lineup:g} jam)"
                )

    if reasons_incomplete:
        status = "DATA_INCOMPLETE"
    elif reasons_hold:
        status = "HOLD"
    else:
        status = "OK"
    return {"status": status, "reasons": reasons_incomplete + reasons_hold}
