"""Ukur distribusi vonis per laga di slate uji nyata.

    python3 scripts/ukur_vonis.py [--out out/ukur_vonis.json]

Membaca artefak analisis (22 Nov live 7 laga + verif tahap 4 3 laga
+ artefak 23 Nov bila ada di out/analysis*2026-11-23*.json),
menjalankan engine/vonis.py nilai_vonis per laga, dan menulis JSON
+ mencetak tabel ringkasan.

Dilaporkan: distribusi vonis (HIJAU / MENENGAH_HIJAU / KUNING),
per-laga indikator kunci (garis Asuransi, edge terbaik, P banjir
terburuk, P setan, volume, gap model-vs-pasar, sinyal ekor gemuk,
OT, total bandar) + demerit + pemicu keras, dan — sebagai KONTEKS
saja (bukan bagian vonis) — putusan skip_awal per laga supaya
kelihatan di mana vonis menambah nilai di luar skip_awal.

Tanpa fetch, tanpa simulasi ulang, tanpa Odds API (0 kredit).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine import skip_awal as skip_awal_mod
from engine import vonis as vonis_mod

ROOT = Path(__file__).resolve().parent.parent

ARTEFAK = [
    ("live 22 Nov", "out/analysis_live_2026-11-22.json"),
    ("verif tahap 4", "out/analysis_verif_tahap4_2026-11-22.json"),
]


def _baca_json(relatif: str) -> dict:
    return json.loads((ROOT / relatif).read_text(encoding="utf-8"))


def _artefak_23_nov() -> list[tuple[str, str]]:
    """Artefak analisis 23 Nov bila ada (glob nama file)."""
    hasil = []
    for path in sorted(ROOT.glob("out/analysis*2026-11-23*.json")):
        hasil.append((f"23 Nov ({path.name})", f"out/{path.name}"))
    return hasil


def _fmt_persen(nilai: float | None) -> str:
    if nilai is None:
        return "?"
    return f"{nilai * 100:.1f}%".replace(".", ",")


def ukur() -> dict:
    """Jalankan pengukuran; kembalikan dict hasil lengkap."""
    cfg = config_mod.load_playstyle()
    artefak = list(ARTEFAK) + _artefak_23_nov()
    baris: list[dict] = []
    for label_artefak, relatif in artefak:
        data = _baca_json(relatif)
        for match in data.get("matches") or []:
            analysis = match.get("nba_analysis") or {}
            match_id = str(match.get("match_id") or analysis.get("match_id"))
            try:
                hasil = vonis_mod.nilai_vonis(analysis, None, cfg)
            except (ValueError, config_mod.ConfigError) as exc:
                baris.append(
                    {
                        "match_id": match_id,
                        "artefak": label_artefak,
                        "error": str(exc),
                    }
                )
                continue
            ind = hasil["indikator"]
            garis_info = ind.get("garis_asuransi") or {}
            try:
                info_skip = skip_awal_mod.evaluasi_skip_awal(analysis, cfg)
                skip_konteks = {
                    "skip": bool(info_skip.get("skip")),
                    "pemicu": list(info_skip.get("pemicu") or []),
                    "dievaluasi": bool(info_skip.get("dievaluasi")),
                }
            except (ValueError, config_mod.ConfigError) as exc:
                skip_konteks = {"skip": None, "error": str(exc)}
            baris.append(
                {
                    "match_id": match_id,
                    "artefak": label_artefak,
                    "status_analisis": analysis.get("status"),
                    "vonis": hasil["vonis"],
                    "dievaluasi": bool(ind.get("dievaluasi")),
                    "alasan": list(hasil["alasan"]),
                    "demerit": list(ind.get("demerit") or []),
                    "n_demerit": ind.get("n_demerit"),
                    "pemicu_keras": ind.get("pemicu_keras"),
                    "tidak_dinilai": list(ind.get("tidak_dinilai") or []),
                    "garis_asuransi": garis_info,
                    "edge_terbaik": ind.get("edge_terbaik"),
                    "edge_terbaik_sumber": ind.get("edge_terbaik_sumber"),
                    "p_banjir_terburuk": ind.get("p_banjir_terburuk"),
                    "banjir_terburuk": ind.get("banjir_terburuk"),
                    "p_setan": ind.get("p_setan"),
                    "gap_model_pasar": ind.get("gap_model_pasar"),
                    "ekor_gemuk": ind.get("ekor_gemuk"),
                    "jarak_garis_market_points": ind.get("jarak_garis_market_points"),
                    "ot_probability": ind.get("ot_probability"),
                    "total_market": ind.get("total_market"),
                    "veto": ind.get("veto"),
                    "garis_tahan_banjir_nonthin": ind.get("garis_tahan_banjir_nonthin"),
                    "skip_awal_konteks": skip_konteks,
                }
            )
    ok = [b for b in baris if "error" not in b]
    hijau = [b for b in ok if b["vonis"] == "hijau"]
    menengah = [b for b in ok if b["vonis"] == "menengah_hijau"]
    kuning = [b for b in ok if b["vonis"] == "kuning"]
    veto_menyala = [
        b for b in ok if isinstance(b.get("veto"), dict) and b["veto"].get("menyala")
    ]
    return {
        "format": "ukur_vonis",
        "format_version": 1,
        "config_version": cfg["meta"]["version"],
        "geser_points": {
            "banjir_3p": cfg["stress"]["banjir_3p_points"],
            "banjir_ft": cfg["stress"]["banjir_ft_points"],
            "setan": cfg["stress"]["setan_points"],
        },
        "ambang_vonis": cfg.get("vonis"),
        "artefak_dipakai": [relatif for _label, relatif in artefak],
        "catatan": (
            "DEN@CHI muncul dua kali (dua analisis berbeda atas laga "
            "yang sama: slate 22 Nov + verif tahap 4) — keduanya "
            "dilaporkan, bukan digabung diam-diam. Tidak ada artefak "
            "analisis 23 Nov di out/analysis*.json saat pengukuran "
            "ini (10 baris yang ada yang diukur). Kolom "
            "skip_awal_konteks hanya konteks (bukan bagian vonis)."
            if not _artefak_23_nov()
            else (
                "DEN@CHI muncul dua kali (dua analisis berbeda atas "
                "laga yang sama: slate 22 Nov + verif tahap 4) — "
                "keduanya dilaporkan, bukan digabung diam-diam. "
                "Kolom skip_awal_konteks hanya konteks (bukan bagian "
                "vonis)."
            )
        ),
        "ringkasan": {
            "n_baris": len(baris),
            "n_error": len(baris) - len(ok),
            "hijau": len(hijau),
            "menengah_hijau": len(menengah),
            "kuning": len(kuning),
            "match_hijau": [b["match_id"] for b in hijau],
            "match_menengah_hijau": [b["match_id"] for b in menengah],
            "match_kuning": [b["match_id"] for b in kuning],
            "veto_menyala": len(veto_menyala),
            "match_veto_menyala": [
                f"{b['match_id']} [{b['artefak']}]" for b in veto_menyala
            ],
        },
        "baris": baris,
    }


def cetak_tabel(hasil: dict) -> None:
    """Cetak tabel ringkasan ke stdout."""
    ringkasan = hasil["ringkasan"]
    print("VONIS PER LAGA (slate uji)")
    print("=" * 120)
    print(
        f"{'Laga':<24}{'Artefak':<16}{'Vonis':<16}{'Dem':>4}"
        f"{'Edge+':>8}{'Banjir':>8}{'Setan':>8}{'Gap':>7}"
        f"{'Ekor':>6}{'OT':>7}{'Skip?':>7}{'Veto?':>7}"
    )
    for b in hasil["baris"]:
        if "error" in b:
            print(f"{b['match_id']:<24} ERROR: {b['error']}")
            continue
        garis = (b["garis_asuransi"] or {}).get("line")
        gap = b["gap_model_pasar"]
        ot = b["ot_probability"]
        skip = b["skip_awal_konteks"] or {}
        veto = b.get("veto") or {}
        baris_teks = (
            f"{b['match_id']:<24}{b['artefak']:<16}{b['vonis']:<16}"
            f"{str(b['n_demerit']):>4}"
            f"{_fmt_persen(b['edge_terbaik']):>8}"
            f"{_fmt_persen(b['p_banjir_terburuk']):>8}"
            f"{_fmt_persen(b['p_setan']):>8}"
            f"{(f'{gap * 100:+.1f}'.replace('.', ',') if gap is not None else '?'):>7}"
            f"{('YA' if b['ekor_gemuk'] else 'tidak'):>6}"
            f"{(f'{ot * 100:.2f}%'.replace('.', ',') if ot is not None else '?'):>7}"
            f"{('SKIP' if skip.get('skip') else '-'):>7}"
            f"{('VETO' if veto.get('menyala') else '-'):>7}"
        )
        if garis is not None:
            baris_teks += f"  U{garis:g}"
        print(baris_teks)
        for alasan in b["alasan"]:
            print(f"{'':<24}  - {alasan}")
    print("=" * 120)
    print(
        f"Distribusi: HIJAU {ringkasan['hijau']} / MENENGAH_HIJAU "
        f"{ringkasan['menengah_hijau']} / KUNING {ringkasan['kuning']} "
        f"(dari {ringkasan['n_baris']} baris, "
        f"{ringkasan['n_error']} error)."
    )
    print(f"Artefak dipakai: {', '.join(hasil['artefak_dipakai'])}")


def main(argv: list[str] | None = None) -> int:
    """Jalankan pengukuran. 0 sukses, 2 input tidak ditemukan."""
    parser = argparse.ArgumentParser(
        description="Ukur distribusi vonis per laga di slate uji."
    )
    parser.add_argument(
        "--out",
        default="out/ukur_vonis.json",
        help="file output JSON (default: out/ukur_vonis.json)",
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
