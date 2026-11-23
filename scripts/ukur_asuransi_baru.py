"""Ukur Asuransi baru: safety-first + tanpa kaki kembar + geser banjir bersih.

    python3 scripts/ukur_asuransi_baru.py [--out out/ukur_asuransi_baru.json]

Mengukur ulang di slate uji yang SAMA dengan ukur_equilibrium /
ukur_gate_banjir (22 Nov live + verif tahap 4; 10 baris, DEN muncul
2x) — dengan config v16 + koreksi banjir bersih (3P 8,50 / FT
12,52) + equilibrium Asuransi safety-first + aturan tanpa kaki
kembar:

- per baris: apakah kaki artefak Asuransi lolos gate banjir (geser
  bersih); equilibrium Asuransi (safety-first) + Utama (max-er);
  garis yang gagal HANYA karena thin (semua gate lain lolos) —
  seberapa sering volume menjadi penghalang pembentukan Asuransi;
  vonis laga (bila modul vonis tersedia).
- per slate gabungan (10 baris): tiket Asuransi/Utama yang terbentuk
  (safety-first + tanpa-kembar + vonis) — tiga varian: default
  (vonis aktif), tanpa vonis (flag dimatikan), vonis-alokasi-saja
  (flag dimatikan + dict vonis ditempel di artefak — menguji jalur
  cadangan _vonis_kandidat). Disjoint kedua tiket dicek eksplisit.

Artefak 23 Nov: TIDAK ADA artefak analysis 23 Nov (hanya
out/tickets_real_2026-11-23.json + file audit) — pengukuran hanya
di 10 baris 22 Nov.

Tanpa fetch, tanpa simulasi ulang, tanpa Odds API (0 kredit).
Angka dilaporkan apa adanya — bila Asuransi tetap tidak terbentuk,
itu TEMUAN, bukan alasan melonggarkan apa pun diam-diam.
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
from engine import stress as stress_mod
from engine import ticket_composer as ticket_composer_mod

try:
    from engine import vonis as vonis_mod
except ImportError:  # Modul vonis (worker lain) belum ada / berubah.
    vonis_mod = None

ROOT = Path(__file__).resolve().parent.parent

ARTEFAK = [
    ("live 22 Nov", "out/analysis_live_2026-11-22.json"),
    ("verif tahap 4", "out/analysis_verif_tahap4_2026-11-22.json"),
]

_GATE_INS_KECUALI_VOLUME = ("peluang", "lantai_harga", "banjir", "edge", "label")


def _baca_json(relatif: str) -> dict:
    return json.loads((ROOT / relatif).read_text(encoding="utf-8"))


def _ringkas_eq(hasil: dict) -> dict:
    """Ringkasan hasil cari_equilibrium untuk JSON."""
    return {
        "dihitung": bool(hasil.get("dihitung")),
        "ada": bool(hasil.get("ada")),
        "mode": hasil.get("mode"),
        "garis": hasil.get("garis"),
        "harga_venue_cents": hasil.get("harga_venue_cents"),
        "p_final": hasil.get("p_final"),
        "p_banjir_terburuk": hasil.get("p_banjir_terburuk"),
        "edge": hasil.get("edge"),
        "expected_return": hasil.get("expected_return"),
        "thin": hasil.get("thin"),
        "volume_usd": hasil.get("volume_usd"),
        "n_kandidat_lolos": hasil.get("n_kandidat_lolos"),
        "n_garis_dinilai": hasil.get("n_garis_dinilai"),
        "diagnosis_gate": hasil.get("diagnosis_gate"),
        "alasan_tidak_dihitung": hasil.get("alasan_tidak_dihitung"),
        "alasan_tidak_ada": hasil.get("alasan_tidak_ada"),
    }


def _gate_banjir_kaki_artefak(analysis: dict) -> dict:
    """Gate banjir kaki artefak Asuransi (geser bersih dari config).

    Menghitung skenario_panas dari artefak (tanpa fetch); membaca
    entri kaki Asuransi: P banjir terburuk vs target 74%.
    """
    try:
        data = stress_mod.skenario_panas(analysis)
    except Exception as exc:  # noqa: BLE001 — dicatat, bukan crash.
        return {"dihitung": False, "alasan": str(exc)}
    terburuk = data.get("banjir_terburuk")
    for kaki in data.get("kaki") or []:
        if not isinstance(kaki, dict) or kaki.get("ticket") != "insurance":
            continue
        p_under = kaki.get("p_under") or {}
        p_banjir = p_under.get(terburuk) if terburuk else None
        target = kaki.get("target_probability")
        tahan = kaki.get("garis_tahan_banjir") or {}
        return {
            "dihitung": True,
            "line": kaki.get("line"),
            "banjir_terburuk": terburuk,
            "p_banjir_terburuk": p_banjir,
            "target_probability": target,
            "lolos": (
                p_banjir is not None and target is not None and p_banjir >= target
            ),
            "tahan_banjir": bool(kaki.get("tahan_banjir")),
            "garis_tahan_banjir": tahan.get("line"),
            "garis_tahan_thin": tahan.get("thin"),
            "garis_tahan_volume_usd": tahan.get("volume_usd"),
        }
    return {"dihitung": False, "alasan": "tidak ada kaki Asuransi di stress"}


def _garis_thin_only(analysis: dict, cfg: dict) -> dict:
    """Garis Asuransi yang gagal HANYA karena thin.

    Via nilai_semua_garis: garis yang semua gate-nya lolos KECUALI
    volume (thin). Bila garis seperti itu ada tapi equilibrium
    tidak ada -> volume adalah penghalang pembentukan Asuransi di
    laga ini (binding).
    """
    nilai = equilibrium_mod.nilai_semua_garis(analysis, "insurance", cfg)
    if nilai is None:
        return {"dihitung": False, "alasan": "konteks equilibrium tidak siap"}
    thin_only = []
    for entri in nilai:
        gate = entri.get("gate") or {}
        if gate.get("volume") is False and all(
            gate.get(nama) for nama in _GATE_INS_KECUALI_VOLUME
        ):
            thin_only.append(
                {
                    "line": entri.get("line"),
                    "harga_venue_cents": entri.get("harga_venue_cents"),
                    "p_final": entri.get("p_final"),
                    "edge": entri.get("edge"),
                    "volume_usd": entri.get("volume_usd"),
                }
            )
    return {
        "dihitung": True,
        "n_garis_dinilai": len(nilai),
        "n_thin_only": len(thin_only),
        "thin_only": thin_only,
    }


def _vonis_laga(analysis: dict, cfg: dict) -> dict | None:
    """Vonis laga dari engine/vonis (None bila modul tidak ada)."""
    if vonis_mod is None:
        return None
    try:
        info = vonis_mod.nilai_vonis(analysis, None, cfg)
    except Exception as exc:  # noqa: BLE001 — dicatat, bukan crash.
        return {"error": str(exc)}
    return {
        "vonis": info.get("vonis"),
        "dievaluasi": (info.get("indikator") or {}).get("dievaluasi"),
        "alasan": list(info.get("alasan") or []),
    }


def _ukur_baris(analysis: dict, cfg: dict) -> dict:
    """Satu baris slate: gate banjir + equilibrium + thin-only + vonis + skip."""
    eq_ins = equilibrium_mod.cari_equilibrium(analysis, "insurance", cfg)
    eq_main = equilibrium_mod.cari_equilibrium(analysis, "main", cfg)
    info_skip = skip_awal_mod.evaluasi_skip_awal(
        analysis, cfg, eq_ins=eq_ins, eq_main=eq_main
    )
    thin_only = _garis_thin_only(analysis, cfg)
    return {
        "match_id": analysis.get("match_id"),
        "status": analysis.get("status"),
        "gate_banjir_kaki_artefak": _gate_banjir_kaki_artefak(analysis),
        "equilibrium_insurance": _ringkas_eq(eq_ins),
        "equilibrium_main": _ringkas_eq(eq_main),
        "thin_only": thin_only,
        "volume_mengikat": bool(
            thin_only.get("dihitung")
            and thin_only.get("n_thin_only", 0) > 0
            and not eq_ins.get("ada")
        ),
        "vonis": _vonis_laga(analysis, cfg),
        "skip": {
            "skip": bool(info_skip.get("skip")),
            "pemicu": list(info_skip.get("pemicu") or []),
            "alasan": info_skip.get("alasan"),
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


def _ukur_racik(analyses: list[dict], cfg: dict, label: str) -> dict:
    """Racik satu slate gabungan + cek disjoint eksplisit."""
    racik = ticket_composer_mod.compose_tickets(analyses, None, cfg, stake_total=20)
    ins = racik.get("insurance")
    main = racik.get("main")
    laga_ins = {k.get("match_id") for k in (ins or {}).get("legs") or []}
    laga_main = {k.get("match_id") for k in (main or {}).get("legs") or []}
    return {
        "varian": label,
        "insurance": _ringkas_tiket(ins),
        "insurance_reason": racik.get("insurance_reason"),
        "main": _ringkas_tiket(main),
        "main_reason": racik.get("main_reason"),
        "skipped_matches": racik.get("skipped_matches") or [],
        "disjoint": laga_ins.isdisjoint(laga_main),
        "laga_kembar": sorted(laga_ins & laga_main),
        "laga_insurance": sorted(laga_ins),
        "laga_main": sorted(laga_main),
    }


def _varian_vonis(analyses: list[dict], cfg: dict) -> dict:
    """Tiga varian racik: default / tanpa vonis / vonis-alokasi-saja."""
    hasil = {
        "default_vonis_aktif": _ukur_racik(analyses, cfg, "default (vonis aktif)"),
    }
    cfg_tanpa = copy.deepcopy(cfg)
    cfg_tanpa["vonis"]["enabled"] = False
    hasil["tanpa_vonis"] = _ukur_racik(
        analyses, cfg_tanpa, "tanpa vonis (flag dimatikan)"
    )
    if vonis_mod is not None:
        # Tempel dict vonis hitungan ke salinan artefak, lalu racik
        # dengan flag vonis MATI: alokasi membaca analysis["vonis"]
        # (jalur cadangan _vonis_kandidat) — KUNING dievaluasi tetap
        # di-skip, tapi oleh _alokasikan_laga, bukan _kumpulkan_kandidat.
        salinan = copy.deepcopy(analyses)
        for analisis in salinan:
            try:
                analisis["vonis"] = vonis_mod.nilai_vonis(analisis, None, cfg)
            except Exception as exc:  # noqa: BLE001 — dicatat per laga.
                analisis["vonis"] = {"error": str(exc)}
        hasil["vonis_alokasi_saja"] = _ukur_racik(
            salinan,
            cfg_tanpa,
            "vonis-alokasi-saja (flag mati + dict vonis ditempel)",
        )
    return hasil


def ukur() -> dict:
    """Jalankan pengukuran; kembalikan dict hasil lengkap."""
    cfg = config_mod.load_playstyle()
    baris: list[dict] = []
    semua_analyses: list[dict] = []
    for label_artefak, relatif in ARTEFAK:
        data = _baca_json(relatif)
        for match in data.get("matches") or []:
            analysis = match.get("nba_analysis") or {}
            semua_analyses.append(analysis)
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
    ok = [b for b in baris if "error" not in b]
    banjir = [b for b in ok if (b["gate_banjir_kaki_artefak"] or {}).get("dihitung")]
    banjir_lolos = [b for b in banjir if b["gate_banjir_kaki_artefak"]["lolos"]]
    eq_ins_ada = [b for b in ok if b["equilibrium_insurance"]["ada"]]
    eq_main_ada = [b for b in ok if b["equilibrium_main"]["ada"]]
    volume_mengikat = [b for b in ok if b["volume_mengikat"]]
    n_thin_only = sum((b["thin_only"] or {}).get("n_thin_only", 0) for b in ok)
    racik = _varian_vonis(semua_analyses, cfg)
    return {
        "format": "ukur_asuransi_baru",
        "format_version": 1,
        "config_version": cfg["meta"]["version"],
        "ambang": {
            "mode_insurance": cfg["equilibrium"]["mode_insurance"],
            "mode_main": cfg["equilibrium"]["mode_main"],
            "banjir_3p_points": cfg["stress"]["banjir_3p_points"],
            "banjir_ft_points": cfg["stress"]["banjir_ft_points"],
            "setan_points": cfg["stress"]["setan_points"],
            "min_leg_prob_insurance": cfg["tickets"]["insurance"]["min_leg_prob"],
            "min_leg_prob_main": cfg["tickets"]["main"]["min_leg_prob"],
            # v18: edge datar 3,5% diganti EV (keputusan user #2).
            "max_negative_ev_pct_insurance": cfg["tickets"]["insurance"][
                "max_negative_ev_pct"
            ],
            "max_negative_ev_pct_main": cfg["tickets"]["main"]["max_negative_ev_pct"],
            "min_volume_usd": cfg["polymarket_ladder"]["min_volume_usd"],
            "multiplier_min_insurance": cfg["tickets"]["insurance"]["multiplier_min"],
            "multiplier_max_insurance": cfg["tickets"]["insurance"]["multiplier_max"],
            "multiplier_min_main": cfg["tickets"]["main"]["multiplier_min"],
            "multiplier_max_main": cfg["tickets"]["main"]["multiplier_max"],
        },
        "catatan": (
            "Slate uji 10 baris (7 live 22 Nov + 3 verif tahap 4; "
            "DEN@CHI muncul 2x). TIDAK ADA artefak analysis 23 Nov "
            "(hanya out/tickets_real_2026-11-23.json + audit) — "
            "pengukuran hanya di 10 baris 22 Nov. Geser banjir "
            "BERSIH (3P 8,50 / FT 12,52, koreksi kontaminasi "
            "LAPORAN-ATURAN-KERAS.md §6). Equilibrium Asuransi "
            "safety-first (p_final tertinggi), Utama max-er. "
            "Thin-only = garis yang lolos SEMUA gate Asuransi "
            "kecuali volume. Volume mengikat = ada garis thin-only "
            "tapi equilibrium Asuransi tidak ada."
        ),
        "ringkasan": {
            "n_baris": len(baris),
            "n_error": len(baris) - len(ok),
            "gate_banjir_kaki_artefak_dihitung": len(banjir),
            "gate_banjir_kaki_artefak_lolos": len(banjir_lolos),
            "gate_banjir_kaki_artefak_gagal": len(banjir) - len(banjir_lolos),
            "match_banjir_lolos": [b["match_id"] for b in banjir_lolos],
            "eq_insurance_ada": len(eq_ins_ada),
            "eq_insurance_tidak_ada": len(ok) - len(eq_ins_ada),
            "eq_main_ada": len(eq_main_ada),
            "eq_main_tidak_ada": len(ok) - len(eq_main_ada),
            "match_eq_insurance_ada": [b["match_id"] for b in eq_ins_ada],
            "n_garis_thin_only_total": n_thin_only,
            "n_baris_volume_mengikat": len(volume_mengikat),
            "match_volume_mengikat": [b["match_id"] for b in volume_mengikat],
            "racik_default_insurance_terbentuk": bool(
                racik["default_vonis_aktif"]["insurance"]
            ),
            "racik_default_main_terbentuk": bool(racik["default_vonis_aktif"]["main"]),
            "racik_default_disjoint": racik["default_vonis_aktif"]["disjoint"],
        },
        "baris": baris,
        "racik": racik,
    }


def _fmt_persen(nilai: float | None, desimal: int = 1) -> str:
    if nilai is None:
        return "?"
    return f"{nilai * 100:.{desimal}f}%".replace(".", ",")


def cetak_tabel(hasil: dict) -> None:
    """Cetak tabel ringkasan ke stdout."""
    ringkasan = hasil["ringkasan"]
    print("ASURANSI BARU (safety-first + tanpa kaki kembar + geser bersih)")
    print("Slate nyata 22 Nov, 10 baris (7 live + 3 verif)")
    print("=" * 118)
    print(
        f"{'Laga':<26}{'Banjir kaki':<16}{'EQ Asuransi':<26}"
        f"{'EQ Utama':<22}{'Thin-only':>9}{'Vol ikat':>9}"
    )
    for b in hasil["baris"]:
        if "error" in b:
            print(f"{b['match_id']:<26} ERROR: {b['error']}")
            continue
        banjir = b["gate_banjir_kaki_artefak"] or {}
        teks_banjir = (
            f"{_fmt_persen(banjir.get('p_banjir_terburuk'))} "
            f"{'LOLOS' if banjir.get('lolos') else 'gagal'}"
            if banjir.get("dihitung")
            else "tidak dihitung"
        )
        eq_ins = b["equilibrium_insurance"]
        eq_main = b["equilibrium_main"]
        teks_ins = (
            f"U{eq_ins['garis']:g} @{eq_ins['harga_venue_cents']:g}c "
            f"p{_fmt_persen(eq_ins['p_final'])}"
            if eq_ins["ada"]
            else "tidak ada"
        )
        teks_main = (
            f"U{eq_main['garis']:g} @{eq_main['harga_venue_cents']:g}c"
            if eq_main["ada"]
            else "tidak ada"
        )
        print(
            f"{b['match_id']:<26}{teks_banjir:<16}{teks_ins:<26}"
            f"{teks_main:<22}"
            f"{(b['thin_only'] or {}).get('n_thin_only', '?'):>9}"
            f"{'YA' if b['volume_mengikat'] else 'tidak':>9}"
        )
    print("=" * 118)
    print(
        f"Gate banjir kaki artefak Asuransi: "
        f"{ringkasan['gate_banjir_kaki_artefak_lolos']} lolos / "
        f"{ringkasan['gate_banjir_kaki_artefak_gagal']} gagal "
        f"(dari {ringkasan['gate_banjir_kaki_artefak_dihitung']} dihitung)."
    )
    print(
        f"Equilibrium Asuransi (safety-first): "
        f"{ringkasan['eq_insurance_ada']} ada / "
        f"{ringkasan['eq_insurance_tidak_ada']} tidak ada; Utama (max-er): "
        f"{ringkasan['eq_main_ada']} ada / "
        f"{ringkasan['eq_main_tidak_ada']} tidak ada."
    )
    print(
        f"Garis thin-only (gagal HANYA karena volume): "
        f"{ringkasan['n_garis_thin_only_total']} garis di "
        f"{ringkasan['n_baris_volume_mengikat']} baris "
        f"({', '.join(ringkasan['match_volume_mengikat']) or '-'})."
    )
    for r in hasil["racik"].values():
        ins = r["insurance"]
        main = r["main"]
        print()
        print(f"RACIK [{r['varian']}]")
        print(
            "  Asuransi: "
            + (
                f"TERBENTUK x{ins['multiplier']:.2f} ({len(ins['legs'])} kaki): "
                + ", ".join(k["match_id"] for k in ins["legs"])
                if ins
                else f"tidak terbentuk ({r['insurance_reason']})"
            )
        )
        print(
            "  Utama: "
            + (
                f"TERBENTUK x{main['multiplier']:.2f} ({len(main['legs'])} kaki): "
                + ", ".join(k["match_id"] for k in main["legs"])
                if main
                else f"tidak terbentuk ({r['main_reason']})"
            )
        )
        print(
            f"  Disjoint: {'YA' if r['disjoint'] else 'TIDAK — kembar: ' + ', '.join(r['laga_kembar'])}; "
            f"di-skip: {len(r['skipped_matches'])} laga"
        )


def main(argv: list[str] | None = None) -> int:
    """Jalankan pengukuran. 0 sukses, 2 input tidak ditemukan."""
    parser = argparse.ArgumentParser(
        description="Ukur Asuransi baru di slate nyata 22 Nov."
    )
    parser.add_argument(
        "--out",
        default="out/ukur_asuransi_baru.json",
        help="file output JSON (default: out/ukur_asuransi_baru.json)",
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
