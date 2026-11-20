"""Jalankan semua probe Tahap 2a berurutan dengan jeda sopan.

Menulis probes/out/summary.json (ringkasan verdict tiap sumber).
Setiap probe juga menulis file JSON-nya sendiri di probes/out/.

Dijalankan: python3 probes/run_all.py
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bbref
import espn
import fotmob
import jupiter
import kalshi
import nba_com
import nba_injury_report
import odds_api
import official_leagues
import polymarket
import rotowire
import sofascore
import understat
from common import now_iso, out_dir, write_result

# (nama file output, modul probe). Urutan: harga dulu, lalu NBA, lalu bola.
PROBES = [
    ("jupiter", jupiter),
    ("polymarket", polymarket),
    ("kalshi", kalshi),
    ("odds_api", odds_api),
    ("nba_com", nba_com),
    ("espn", espn),
    ("bbref", bbref),
    ("nba_injury_report", nba_injury_report),
    ("rotowire", rotowire),
    ("understat", understat),
    ("sofascore", sofascore),
    ("fotmob", fotmob),
    ("official_leagues", official_leagues),
]

GAP_BETWEEN_PROBES = 3.0


def run_all() -> dict:
    """Jalankan semua probe; kembalikan dict ringkasan."""
    summary: dict = {
        "probed_at": now_iso(),
        "probes": {},
    }
    for name, module in PROBES:
        try:
            result = module.probe()
            write_result(name, result)
            summary["probes"][name] = {
                "source": result.get("source"),
                "tier": result.get("tier"),
                "accessible_from_vm": result.get("accessible_from_vm"),
                "verdict": result.get("verdict"),
                "requests": len(result.get("requests", [])),
            }
            print(f"[{name}] {result.get('verdict')}", flush=True)
        except Exception:
            summary["probes"][name] = {
                "source": name,
                "tier": None,
                "accessible_from_vm": False,
                "verdict": "ERROR",
                "error": traceback.format_exc(limit=3),
            }
            print(f"[{name}] ERROR", flush=True)
        time.sleep(GAP_BETWEEN_PROBES)
    return summary


def main() -> int:
    """Jalankan semua probe dan tulis summary.json; kembalikan exit code."""
    summary = run_all()
    path = out_dir() / "summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"summary -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
