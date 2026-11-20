"""Cek harian otomatis Understat — Tahap 2a lanjutan (muse-parlay-analyst).

Script non-interaktif, 1 request ringan ke halaman liga EPL Understat.
Menulis status ke probes/out/understat_status.json (ditimpa tiap cek) dan
menambah satu baris JSON ke probes/out/understat_health.log (riwayat).

RE-AKTIVASI OTOMATIS (mekanisme, bukan janji):
- Fetcher 2b membaca probes/out/understat_status.json SEBELUM memakai
  Understat di rantai xG.
- Bila status == "up" DAN checked_at masih dalam 24 jam terakhir, Understat
  aktif lagi di rantai xG (aturan B4 dicabut untuk laga yang punya xG).
- Bila status maintenance/down/unknown ATAU checked_at sudah lewat 24 jam,
  Understat dianggap mati — bola jalan dengan aturan B4 (TANPA_XG).
- Script ini TIDAK mengubah sources.yaml atau config apa pun; ia hanya
  mencatat status. Keputusan "pakai xG" tetap di tangan fetcher yang
  membaca status ini.

Jadwal yang disarankan: 1x sehari (cron), misal tiap 08:00 WIB:
  0 8 * * * cd ~/workspace/projects/muse-parlay-analyst && python3 probes/check_understat.py

Dijalankan sendiri: python3 probes/check_understat.py
Exit code selalu 0 (ini health check; statusnya ada di file output).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import HttpClient, RateLimiter, now_iso, out_dir

CHECK_URL = "https://understat.com/league/EPL/2025"
MAINTENANCE_TEXT = "We will come back soon"
UP_MARKERS = ("teamsData", "datesData")
STATUS_FILE = "understat_status.json"
HEALTH_LOG = "understat_health.log"


def classify_status(http_status: int | None, body: str, error: object = None) -> str:
    """Klasifikasikan status Understat dari satu respons.

    - "up": HTTP 200, ada penanda JSON tertanam (teamsData/datesData),
      tanpa teks maintenance.
    - "maintenance": HTTP 200 dengan teks "We will come back soon".
    - "down": HTTP bukan 200, atau error jaringan.
    - "unknown": HTTP 200 tapi tidak ada penanda up maupun maintenance.
    """
    if error is not None or http_status is None:
        return "down"
    if http_status != 200:
        return "down"
    if MAINTENANCE_TEXT in body:
        return "maintenance"
    if any(marker in body for marker in UP_MARKERS):
        return "up"
    return "unknown"


def check() -> dict:
    """Jalankan satu cek Understat; kembalikan dict status."""
    client = HttpClient(RateLimiter(0))
    resp = client.get(CHECK_URL, use_cache=False)
    body = str(resp.get("body") or "")
    status = classify_status(resp.get("status"), body, resp.get("error"))
    markers_found = [m for m in UP_MARKERS if m in body]
    return {
        "checked_at": now_iso(),
        "status": status,
        "evidence": {
            "url": CHECK_URL,
            "http_status": resp.get("status"),
            "body_chars": len(body),
            "markers_found": markers_found,
            "maintenance_text_found": MAINTENANCE_TEXT in body,
            "error": resp.get("error"),
        },
    }


def main() -> int:
    """Jalankan cek, tulis status + log; kembalikan exit code 0."""
    record = check()
    directory = out_dir()
    status_path = directory / STATUS_FILE
    status_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log_path = directory / HEALTH_LOG
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(
        f"understat: {record['status']} "
        f"(checked_at {record['checked_at']}) -> {status_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
