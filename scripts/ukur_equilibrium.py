"""Ukur titik equilibrium + skip dari awal di slate nyata.

    python3 scripts/ukur_equilibrium.py [--out out/ukur_equilibrium.json]

Membaca dua artefak analisis yang SAMA dengan ukur_gate_banjir
(22 Nov live + verif tahap 4; 10 baris, DEN muncul 2x), menjalankan
engine/equilibrium.py + engine/skip_awal.py per laga, dan
membandingkan hasil racik komposer ATURAN BARU (equilibrium + skip)
vs ATURAN LAMA (kedua flag config dimatikan — perilaku lama persis)
per slate.

Tanpa fetch, tanpa simulasi ulang, tanpa Odds API (0 kredit).
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine import equilibrium as equilibrium_mod
from engine import skip_awal as skip_awal_mod
from engine import ticket_composer as ticket_composer_mod

ROOT = Path(__file__).resolve().parent.parent

ARTEFAK = [
    ("live 22 Nov", "out/analysis_live_2026-11-22.json"),
    ("verif tahap 4", "out/analysis_verif_tahap4_2026-11-22.json"),
]


def _baca_json(relatif: str) -> dict:
    return json.loads((ROOT / relatif).read_text(encoding="utf-8"))


def _ringkas_eq(hasil: dict) -> dict:
    """Ringkasan hasil cari_equilibrium untuk JSON (tanpa format)."""
    return {
        "dihitung": bool(hasil.get("dihitung")),
        "ada": bool(hasil.get("ada")),
        "garis": hasil.get("garis"),
        "harga_venue_cents": hasil.get("harga_venue_cents"),
        "p_model": hasil.get("p_model"),
        "p_market": hasil.get("p_market"),
        "p_final": hasil.get("p_final"),
        "p_banjir_terburuk": hasil.get("p_banjir_terburuk"),
        "p_setan": hasil.get("p_setan"),
        "edge": hasil.get("edge"),
        "ev_pct": hasil.get("ev_pct"),
        "expected_return": hasil.get("expected_return"),
        "price_label": hasil.get("price_label"),
        "thin": hasil.get("thin"),
        "volume_usd": hasil.get("volume_usd"),
        "geser_pasar": hasil.get("geser_pasar"),
        "n_kandidat_lolos": hasil.get("n_kandidat_lolos"),
        "n_garis_dinilai": hasil.get("n_garis_dinilai"),
        "diagnosis_gate": hasil.get("diagnosis_gate"),
        "alasan_tidak_dihitung": hasil.get("alasan_tidak_dihitung"),
        "alasan_tidak_ada": hasil.get("alasan_tidak_ada"),
    }


def _ringkas_kaki_artifak(analysis: dict) -> dict:
    """Kaki artefak per tiket (garis/harga/p_final — pembanding)."""
    hasil: dict[str, dict | None] = {"insurance": None, "main": None}
    for leg in analysis.get("legs") or []:
        if not isinstance(leg, dict):
            continue
        tiket = leg.get("ticket")
        if tiket not in hasil:
            continue
        hasil[tiket] = {
            "line": leg.get("line"),
            "jup_estimated_cents": leg.get("jup_estimated_cents"),
            "price_cents": leg.get("price_cents"),
            "p_model": leg.get("p_model"),
            "p_market": leg.get("p_market"),
            "p_final": leg.get("p_final"),
            "thin": leg.get("thin"),
            "meets": leg.get("meets"),
            "reason": leg.get("reason"),
        }
    return hasil


def _ukur_baris(analysis: dict, cfg: dict) -> dict:
    """Equilibrium + skip satu laga (artefak apa pun statusnya)."""
    eq_ins = equilibrium_mod.cari_equilibrium(analysis, "insurance", cfg)
    eq_main = equilibrium_mod.cari_equilibrium(analysis, "main", cfg)
    info_skip = skip_awal_mod.evaluasi_skip_awal(
        analysis, cfg, eq_ins=eq_ins, eq_main=eq_main
    )
    pola = info_skip.get("pola_denver") or {}
    acuan = pola.get("garis_acuan") or {}
    return {
        "match_id": analysis.get("match_id"),
        "status": analysis.get("status"),
        "ot_probability": (info_skip.get("ot") or {}).get("ot_probability"),
        "ot_ambang": (info_skip.get("ot") or {}).get("ambang"),
        "ot_tinggi": (info_skip.get("ot") or {}).get("tinggi"),
        "kaki_artifak": _ringkas_kaki_artifak(analysis),
        "equilibrium_insurance": _ringkas_eq(eq_ins),
        "equilibrium_main": _ringkas_eq(eq_main),
        "skip": {
            "dievaluasi": bool(info_skip.get("dievaluasi")),
            "alasan_tidak_dievaluasi": info_skip.get("alasan_tidak_dievaluasi"),
            "skip": bool(info_skip.get("skip")),
            "pemicu": list(info_skip.get("pemicu") or []),
            "alasan": info_skip.get("alasan"),
        },
        "pola_denver": {
            "dievaluasi": bool(pola.get("dievaluasi")),
            "cocok": bool(pola.get("cocok")),
            "syarat": pola.get("syarat") or {},
            "ambang_edge": pola.get("ambang_edge"),
            "garis_acuan": {
                "garis": acuan.get("garis"),
                "harga_venue_cents": acuan.get("harga_venue_cents"),
                "thin": acuan.get("thin"),
                "p_normal": acuan.get("p_normal"),
                "p_setan": acuan.get("p_setan"),
                "flag_setan": acuan.get("flag_setan"),
                "p_final": acuan.get("p_final"),
                "edge": acuan.get("edge"),
                "garis_tahan_banjir": acuan.get("garis_tahan_banjir"),
                "n_tahan_banjir": acuan.get("n_tahan_banjir"),
                "n_tahan_banjir_nonthin": acuan.get("n_tahan_banjir_nonthin"),
            },
        },
    }


def _ringkas_tiket(tiket: dict | None) -> dict | None:
    if tiket is None:
        return None
    return {
        "multiplier": tiket.get("multiplier"),
        "stake": tiket.get("stake"),
        "p_win": (tiket.get("metrics") or {}).get("p_win"),
        "combined_ev_pct": (tiket.get("metrics") or {}).get("combined_ev_pct"),
        "legs": [
            {
                "match_id": leg.get("match_id"),
                "selection": leg.get("selection"),
                "jup_price_cents": leg.get("jup_price_cents"),
                "p_final": leg.get("p_final"),
                "climb": leg.get("climb"),
            }
            for leg in tiket.get("legs") or []
        ],
    }


def _ukur_slate(analyses: list[dict], cfg_baru: dict) -> dict:
    """Racik satu slate dengan aturan baru vs aturan lama."""
    cfg_lama = copy.deepcopy(cfg_baru)
    cfg_lama["equilibrium"]["enabled"] = False
    cfg_lama["skip_awal"]["enabled"] = False
    hasil: dict[str, dict] = {}
    for label, cfg in (("baru", cfg_baru), ("lama", cfg_lama)):
        per_laga = ticket_composer_mod._terbaru_per_laga(analyses, "generated_at")
        skipped: list[dict] = []
        kandidat, _coret = ticket_composer_mod._kumpulkan_kandidat(
            per_laga, {}, cfg, skipped=skipped
        )
        racik = ticket_composer_mod.compose_tickets(analyses, None, cfg, stake_total=20)
        hasil[label] = {
            "n_kandidat_insurance": len(kandidat["insurance"]),
            "n_kandidat_main": len(kandidat["main"]),
            "kandidat_insurance": [
                {
                    "match_id": k["match_id"],
                    "line": k.get("line"),
                    "harga_jup": k.get("harga_jup"),
                    "p_final": k.get("p_final"),
                    "climb": (k.get("leg") or {}).get("climb"),
                }
                for k in kandidat["insurance"]
            ],
            "kandidat_main": [
                {
                    "match_id": k["match_id"],
                    "line": k.get("line"),
                    "harga_jup": k.get("harga_jup"),
                    "p_final": k.get("p_final"),
                    "climb": (k.get("leg") or {}).get("climb"),
                }
                for k in kandidat["main"]
            ],
            "skipped_matches": racik.get("skipped_matches") or [],
            "insurance": _ringkas_tiket(racik.get("insurance")),
            "insurance_reason": racik.get("insurance_reason"),
            "main": _ringkas_tiket(racik.get("main")),
            "main_reason": racik.get("main_reason"),
        }
    return hasil


def ukur() -> dict:
    """Jalankan pengukuran; kembalikan dict hasil lengkap."""
    cfg = config_mod.load_playstyle()
    baris: list[dict] = []
    slate: list[dict] = []
    for label_artefak, relatif in ARTEFAK:
        data = _baca_json(relatif)
        analyses = []
        for match in data.get("matches") or []:
            analysis = match.get("nba_analysis") or {}
            analyses.append(analysis)
            try:
                hasil_baris = _ukur_baris(analysis, cfg)
            except (ValueError, config_mod.ConfigError) as exc:
                baris.append(
                    {
                        "match_id": match.get("match_id"),
                        "artefak": label_artefak,
                        "error": str(exc),
                    }
                )
                continue
            hasil_baris["artefak"] = label_artefak
            baris.append(hasil_baris)
        slate.append(
            {
                "artefak": label_artefak,
                "file": relatif,
                "n_laga": len(analyses),
                "n_status_ok": sum(1 for a in analyses if a.get("status") == "OK"),
                "racik": _ukur_slate(analyses, cfg),
            }
        )
    ok = [b for b in baris if "error" not in b]
    eq_ins_ada = [b for b in ok if b["equilibrium_insurance"]["ada"]]
    eq_main_ada = [b for b in ok if b["equilibrium_main"]["ada"]]
    di_skip = [b for b in ok if b["skip"]["skip"]]
    pola = [b for b in ok if "pola_denver" in b["skip"]["pemicu"]]
    ot = [b for b in ok if "ot_tinggi" in b["skip"]["pemicu"]]
    tanpa_eq = [b for b in ok if "tidak_ada_equilibrium" in b["skip"]["pemicu"]]
    return {
        "format": "ukur_equilibrium",
        "format_version": 1,
        "config_version": cfg["meta"]["version"],
        "ambang": {
            "min_leg_prob_insurance": cfg["tickets"]["insurance"]["min_leg_prob"],
            "min_leg_prob_main": cfg["tickets"]["main"]["min_leg_prob"],
            "min_p_market_insurance": cfg["tickets"]["insurance"]["min_p_market"],
            # v18: edge datar 3,5% diganti EV (keputusan user #2);
            # gate banjir tunggal stress_gate_scenario diganti dua
            # ambang flood_3p_min/flood_ft_min.
            "max_negative_ev_pct_insurance": cfg["tickets"]["insurance"][
                "max_negative_ev_pct"
            ],
            "max_negative_ev_pct_main": cfg["tickets"]["main"]["max_negative_ev_pct"],
            "floor_harga_cents": cfg["analis"]["harga_min_asuransi_cents"],
            "flood_3p_min_insurance": cfg["tickets"]["insurance"]["flood_3p_min"],
            "flood_ft_min_insurance": cfg["tickets"]["insurance"]["flood_ft_min"],
            "geser_banjir_terburuk": max(
                cfg["stress"]["banjir_3p_points"],
                cfg["stress"]["banjir_ft_points"],
            ),
            "setan_points": cfg["stress"]["setan_points"],
            "pola_denver_edge_kecil_pct": cfg["skip_awal"]["pola_denver"][
                "edge_kecil_pct"
            ],
            # v18: skip_ot_prob v17 dihapus — OT empiris, hard-skip
            # hanya bila p_ot empiris >= hard_skip_ot_prob.
            "ot_empiris_base_rate": cfg["ot_seleksi"]["base_rate_ot"],
            "ot_empiris_hard_skip": cfg["ot_seleksi"]["hard_skip_ot_prob"],
        },
        "catatan": (
            "Baris yang sama dengan ukur_gate_banjir (10 baris: 7 live "
            "22 Nov + 3 verif tahap 4; DEN@CHI muncul 2x). v18: "
            "Equilibrium Asuransi memakai p_final >= 0,82 + p_market "
            ">= 0,80 + banjir 3P >= 70% / FT >= 65% + EV >= -1% + "
            "gate eksekusi volume; Utama p_final >= 0,74 + EV >= -2% "
            "+ banjir warning-only. Skip (a) butuh equilibrium TIDAK "
            "ADA di KEDUA tiket. "
            "Racik 'lama' = kedua flag equilibrium/skip_awal dimatikan "
            "(perilaku lama persis)."
        ),
        "ringkasan": {
            "n_baris": len(baris),
            "n_error": len(baris) - len(ok),
            "eq_insurance_ada": len(eq_ins_ada),
            "eq_insurance_tidak_ada": len(ok) - len(eq_ins_ada),
            "eq_main_ada": len(eq_main_ada),
            "eq_main_tidak_ada": len(ok) - len(eq_main_ada),
            "di_skip": len(di_skip),
            "tidak_di_skip": len(ok) - len(di_skip),
            "skip_pola_denver": len(pola),
            "skip_ot_tinggi": len(ot),
            "skip_tidak_ada_equilibrium": len(tanpa_eq),
            "match_eq_insurance_ada": [b["match_id"] for b in eq_ins_ada],
            "match_eq_main_ada": [b["match_id"] for b in eq_main_ada],
            "match_di_skip": [b["match_id"] for b in di_skip],
            "match_skip_pola_denver": [b["match_id"] for b in pola],
            "match_skip_ot_tinggi": [b["match_id"] for b in ot],
        },
        "baris": baris,
        "slate": slate,
    }


def _fmt_persen(nilai: float | None, desimal: int = 1) -> str:
    if nilai is None:
        return "?"
    return f"{nilai * 100:.{desimal}f}%".replace(".", ",")


def cetak_tabel(hasil: dict) -> None:
    """Cetak tabel ringkasan ke stdout."""
    ringkasan = hasil["ringkasan"]
    print("TITIK EQUILIBRIUM + SKIP DARI AWAL (slate nyata 22 Nov, 10 baris)")
    print("=" * 110)
    print(f"{'Laga':<26}{'EQ Asuransi':<22}{'EQ Utama':<22}{'OT':>7}{'Skip':<14}")
    for b in hasil["baris"]:
        if "error" in b:
            print(f"{b['match_id']:<26} ERROR: {b['error']}")
            continue
        eq_ins = b["equilibrium_insurance"]
        eq_main = b["equilibrium_main"]
        teks_ins = (
            f"U{eq_ins['garis']:g} @{eq_ins['harga_venue_cents']:g}c"
            if eq_ins["ada"]
            else "tidak ada"
        )
        teks_main = (
            f"U{eq_main['garis']:g} @{eq_main['harga_venue_cents']:g}c"
            if eq_main["ada"]
            else "tidak ada"
        )
        print(
            f"{b['match_id']:<26}{teks_ins:<22}{teks_main:<22}"
            f"{_fmt_persen(b['ot_probability'], 2):>7}"
            f"{','.join(b['skip']['pemicu']) or '-':<14}"
        )
    print("=" * 110)
    print(
        f"Equilibrium Asuransi: {ringkasan['eq_insurance_ada']} ada / "
        f"{ringkasan['eq_insurance_tidak_ada']} tidak ada; Utama: "
        f"{ringkasan['eq_main_ada']} ada / "
        f"{ringkasan['eq_main_tidak_ada']} tidak ada."
    )
    print(
        f"Di-skip: {ringkasan['di_skip']} "
        f"(pola Denver {ringkasan['skip_pola_denver']}, OT "
        f"{ringkasan['skip_ot_tinggi']}, tanpa equilibrium "
        f"{ringkasan['skip_tidak_ada_equilibrium']}); tidak di-skip: "
        f"{ringkasan['tidak_di_skip']}."
    )
    for s in hasil["slate"]:
        print()
        print(f"SLATE {s['artefak']} ({s['n_laga']} laga, {s['n_status_ok']} OK)")
        for label in ("baru", "lama"):
            r = s["racik"][label]
            ins = r["insurance"]
            main = r["main"]
            print(
                f"  aturan {label}: Asuransi "
                + (
                    f"TERBENTUK x{ins['multiplier']:.2f} ({len(ins['legs'])} kaki)"
                    if ins
                    else "tidak terbentuk"
                )
                + f" [{r['n_kandidat_insurance']} kandidat]; Utama "
                + (
                    f"TERBENTUK x{main['multiplier']:.2f} ({len(main['legs'])} kaki)"
                    if main
                    else "tidak terbentuk"
                )
                + f" [{r['n_kandidat_main']} kandidat]; "
                f"di-skip: {len(r['skipped_matches'])}"
            )


def main(argv: list[str] | None = None) -> int:
    """Jalankan pengukuran. 0 sukses, 2 input tidak ditemukan."""
    parser = argparse.ArgumentParser(
        description="Ukur titik equilibrium + skip dari awal di slate nyata."
    )
    parser.add_argument(
        "--out",
        default="out/ukur_equilibrium.json",
        help="file output JSON (default: out/ukur_equilibrium.json)",
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
