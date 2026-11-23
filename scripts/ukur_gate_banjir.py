"""Ukur block rate gate banjir p90 + kerapuhan setan di slate nyata.

    python3 scripts/ukur_gate_banjir.py [--out out/ukur_gate_banjir.json]

Membaca dua artefak analisis (22 Nov live + verif tahap 4), menjalankan
engine/stress.py skenario_panas untuk kaki Asuransi tiap laga, dan
menulis JSON + mencetak tabel ringkasan.

GATE BANJIR p90 (gate keras Asuransi — urusan Worker B, diukur di
sini): kaki LOLOS bila P(Under) di skenario banjir terburuk >=
tickets.insurance.min_leg_prob (0,74). FRAGILITAS SETAN (deteksi,
BUKAN gate — koreksi user 09:52 WIB): flag_setan True bila P normal
>= target tapi P setan < target — dilaporkan terpisah, TIDAK dihitung
sebagai block rate.

Kaki Asuransi diambil dari legs artefak analisis; bila kaki Asuransi
artefak tidak bergaris (DEN/BOS di artefak verif), dipakai kaki
Asuransi tiket nyata user (out/tickets_real_2026-11-23.json) dan
sumbernya dicatat per baris. DEN@CHI muncul dua kali (dua analisis
berbeda atas laga yang sama: slate 22 Nov + verif tahap 4) — keduanya
dilaporkan, bukan digabung diam-diam.

Tanpa fetch, tanpa simulasi ulang, tanpa Odds API (0 kredit).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine import stress as stress_mod

ROOT = Path(__file__).resolve().parent.parent

ARTEFAK = [
    ("live 22 Nov", "out/analysis_live_2026-11-22.json"),
    ("verif tahap 4", "out/analysis_verif_tahap4_2026-11-22.json"),
]
TIKET_NYATA = "out/tickets_real_2026-11-23.json"


def _baca_json(relatif: str) -> dict:
    return json.loads((ROOT / relatif).read_text(encoding="utf-8"))


def _kaki_asuransi_tiket_nyata() -> dict[str, dict]:
    """Kaki Asuransi tiket nyata user, dipetakan per laga.

    Kunci: "AWAY@HOME_TANGGAL" seperti match_id tiket
    ("DEN@CHI_2026-11-22"). Nilai: {"line", "price_cents"}.
    """
    data = _baca_json(TIKET_NYATA)
    hasil: dict[str, dict] = {}
    for leg in (data.get("insurance") or {}).get("legs") or []:
        if not isinstance(leg, dict):
            continue
        match_id = leg.get("match_id")
        selection = str(leg.get("selection") or "")
        if not match_id or "Under" not in selection:
            continue
        try:
            garis = float(selection.split("Under")[1].split("(")[0].strip())
        except (ValueError, IndexError):
            continue
        hasil[str(match_id)] = {
            "line": garis,
            "price_cents": leg.get("jup_price_cents"),
        }
    return hasil


def _kunci_laga(analysis: dict) -> str | None:
    """Kunci "AWAY@HOME_TANGGAL" dari artefak nba_analysis."""
    away = analysis.get("away_tricode")
    home = analysis.get("home_tricode")
    tanggal = analysis.get("game_date")
    if not away or not home or not tanggal:
        return None
    return f"{away}@{home}_{tanggal}"


def _kaki_asuransi(analysis: dict, tiket_nyata: dict[str, dict]) -> tuple[dict, str]:
    """Kaki Asuransi satu laga + sumbernya.

    Utama: legs artefak analisis (ticket insurance, bergaris).
    Cadangan: kaki Asuransi tiket nyata user. Raise ValueError bila
    tidak ada di kedua sumber.
    """
    for leg in analysis.get("legs") or []:
        if not isinstance(leg, dict) or leg.get("ticket") != "insurance":
            continue
        garis = leg.get("line")
        if isinstance(garis, (int, float)):
            return (
                {
                    "line": float(garis),
                    "ticket": "insurance",
                    "price_cents": leg.get("price_cents"),
                    "jup_estimated_cents": leg.get("jup_estimated_cents"),
                },
                "analysis",
            )
    kunci = _kunci_laga(analysis)
    if kunci is not None and kunci in tiket_nyata:
        nyata = tiket_nyata[kunci]
        return (
            {
                "line": float(nyata["line"]),
                "ticket": "insurance",
                "price_cents": nyata.get("price_cents"),
                "jup_estimated_cents": None,
            },
            "tickets_real_2026-11-23",
        )
    raise ValueError(
        f"kaki Asuransi {analysis.get('match_id')} tidak ada di artefak "
        "analisis maupun tiket nyata"
    )


def _ringkas_garis_tahan(entri: dict | None) -> dict | None:
    if entri is None:
        return None
    return {
        "line": entri.get("line"),
        "price_cents": entri.get("price_cents"),
        "jup_estimated_cents": entri.get("jup_estimated_cents"),
        "volume_usd": entri.get("volume_usd"),
        "thin": entri.get("thin"),
    }


def ukur() -> dict:
    """Jalankan pengukuran; kembalikan dict hasil lengkap."""
    cfg = config_mod.load_playstyle()
    target = float(config_mod.get_value(cfg, "tickets", "insurance", "min_leg_prob"))
    tiket_nyata = _kaki_asuransi_tiket_nyata()
    baris: list[dict] = []
    for label_artefak, relatif in ARTEFAK:
        data = _baca_json(relatif)
        for match in data.get("matches") or []:
            analysis = match.get("nba_analysis") or {}
            match_id = str(match.get("match_id") or analysis.get("match_id"))
            try:
                kaki, sumber = _kaki_asuransi(analysis, tiket_nyata)
                hasil = stress_mod.skenario_panas(analysis, kaki=[kaki], cfg=cfg)
            except (ValueError, config_mod.ConfigError) as exc:
                baris.append(
                    {
                        "match_id": match_id,
                        "artefak": label_artefak,
                        "error": str(exc),
                    }
                )
                continue
            kaki_hasil = hasil["kaki"][0]
            p_under = kaki_hasil["p_under"]
            banjir_terburuk = hasil["banjir_terburuk"]
            baris.append(
                {
                    "match_id": match_id,
                    "artefak": label_artefak,
                    "sumber_kaki": sumber,
                    "kaki_asuransi": {
                        "line": kaki_hasil["line"],
                        "price_cents": kaki_hasil["price_cents"],
                        "jup_estimated_cents": kaki_hasil["jup_estimated_cents"],
                    },
                    "target_probability": target,
                    "p_normal": p_under["normal"],
                    "p_banjir_3p": p_under["banjir_3p"],
                    "p_banjir_ft": p_under["banjir_ft"],
                    "banjir_terburuk": banjir_terburuk,
                    "p_banjir_terburuk": p_under[banjir_terburuk],
                    "p_setan": p_under["setan"],
                    "lolos_gate_banjir": bool(kaki_hasil["tahan_banjir"]),
                    "garis_tahan_banjir": _ringkas_garis_tahan(
                        kaki_hasil["garis_tahan_banjir"]
                    ),
                    "alasan_tidak_tahan_banjir": kaki_hasil[
                        "alasan_tidak_tahan_banjir"
                    ],
                    "tahan_setan": bool(kaki_hasil["tahan_setan"]),
                    "garis_tahan_setan": _ringkas_garis_tahan(
                        kaki_hasil["garis_tahan_setan"]
                    ),
                    "alasan_tidak_tahan_setan": kaki_hasil["alasan_tidak_tahan_setan"],
                    "flag_setan": bool(kaki_hasil["flag_setan"]),
                    "alasan_flag_setan": kaki_hasil["alasan_flag_setan"],
                }
            )
    ok = [b for b in baris if "error" not in b]
    lolos = [b for b in ok if b["lolos_gate_banjir"]]
    terblokir = [b for b in ok if not b["lolos_gate_banjir"]]
    ada_tahan_banjir = [b for b in ok if b["garis_tahan_banjir"] is not None]
    terflag = [b for b in ok if b["flag_setan"]]
    return {
        "format": "ukur_gate_banjir",
        "format_version": 1,
        "config_version": cfg["meta"]["version"],
        "geser_points": {
            "banjir_3p": cfg["stress"]["banjir_3p_points"],
            "banjir_ft": cfg["stress"]["banjir_ft_points"],
            "setan": cfg["stress"]["setan_points"],
        },
        "target_insurance": target,
        "catatan": (
            "Gate banjir p90 adalah gate keras Asuransi; flag_setan "
            "adalah DETEKSI kerapuhan, BUKAN gate — tidak dihitung "
            "sebagai block rate. DEN@CHI muncul dua kali (dua analisis "
            "berbeda atas laga yang sama)."
        ),
        "ringkasan": {
            "n_baris": len(baris),
            "n_error": len(baris) - len(ok),
            "lolos_gate_banjir": len(lolos),
            "terblokir_gate_banjir": len(terblokir),
            "ada_garis_tahan_banjir": len(ada_tahan_banjir),
            "tidak_ada_garis_tahan_banjir": len(ok) - len(ada_tahan_banjir),
            "flag_setan_true": len(terflag),
            "match_lolos_gate_banjir": [b["match_id"] for b in lolos],
            "match_terblokir_gate_banjir": [b["match_id"] for b in terblokir],
            "match_flag_setan": [b["match_id"] for b in terflag],
        },
        "baris": baris,
    }


def _fmt_persen(nilai: float | None) -> str:
    if nilai is None:
        return "?"
    return f"{nilai * 100:.1f}%".replace(".", ",")


def cetak_tabel(hasil: dict) -> None:
    """Cetak tabel ringkasan ke stdout."""
    ringkasan = hasil["ringkasan"]
    print("GATE BANJIR p90 (Asuransi, target 74%) + kerapuhan setan")
    print("=" * 100)
    print(
        f"{'Laga':<26}{'Artefak':<15}{'Kaki':<9}{'Normal':>8}"
        f"{'Banjir!':>8}{'Setan':>8}{'Gate':>9}{'Flag':>7}{'Tahan-banjir':>14}"
    )
    for b in hasil["baris"]:
        if "error" in b:
            print(f"{b['match_id']:<26} ERROR: {b['error']}")
            continue
        kaki = b["kaki_asuransi"]
        tahan = b["garis_tahan_banjir"]
        print(
            f"{b['match_id']:<26}{b['artefak']:<15}"
            f"U{kaki['line']:<8}"
            f"{_fmt_persen(b['p_normal']):>8}"
            f"{_fmt_persen(b['p_banjir_terburuk']):>8}"
            f"{_fmt_persen(b['p_setan']):>8}"
            f"{'LOLOS' if b['lolos_gate_banjir'] else 'BLOKIR':>9}"
            f"{'SETAN' if b['flag_setan'] else '-':>7}"
            f"{('U' + str(tahan['line'])) if tahan else 'tidak ada':>14}"
        )
    print("=" * 100)
    print(
        f"Gate banjir p90: {ringkasan['lolos_gate_banjir']} lolos / "
        f"{ringkasan['terblokir_gate_banjir']} terblokir "
        f"(dari {ringkasan['n_baris']} baris, "
        f"{ringkasan['n_error']} error)."
    )
    print(
        f"Garis tahan-banjir ada di {ringkasan['ada_garis_tahan_banjir']} "
        f"baris; tidak ada di {ringkasan['tidak_ada_garis_tahan_banjir']}."
    )
    print(
        f"Flag setan (DETEKSI, bukan gate): " f"{ringkasan['flag_setan_true']} baris."
    )


def main(argv: list[str] | None = None) -> int:
    """Jalankan pengukuran. 0 sukses, 2 input tidak ditemukan."""
    parser = argparse.ArgumentParser(
        description="Ukur block rate gate banjir p90 + kerapuhan setan."
    )
    parser.add_argument(
        "--out",
        default="out/ukur_gate_banjir.json",
        help="file output JSON (default: out/ukur_gate_banjir.json)",
    )
    args = parser.parse_args(argv)
    try:
        hasil = ukur()
    except FileNotFoundError as exc:
        print(f"input tidak ditemukan: {exc}", file=sys.stderr)
        return 2
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(hasil, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    cetak_tabel(hasil)
    print(f"\nDitulis: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
