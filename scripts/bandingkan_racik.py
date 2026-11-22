"""Bandingkan racikan SEBELUM vs SESUDAH Tahap 4 untuk satu laga NBA.

    python3 scripts/bandingkan_racik.py
    python3 scripts/bandingkan_racik.py --analysis out/analysis_live_det_atl.json \\
        --ladder out/poly_ladder_nba-det-atl-2026-11-22.json --out out/perbandingan_det_atl.txt

SEBELUM = kaki Asuransi + Utama dari artefak analisis tersimpan
(aturan lama: Asuransi p74 + lantai market 8; Utama +8/+12 dari
spread). SESUDAH = seleksi BARU dari input tersimpan yang sama:
analis.bantalan_adaptif (statistik laga + distribusi sim) ->
cushion.utama_line (signature baru) -> cushion.insurance_line
(garis di atas Utama) + analis.nilai_wajar.

Skrip ini 100% OFFLINE: hanya membaca dua file input tersimpan +
playstyle.yaml lokal. Tanpa network, tanpa kredit Odds API, tanpa
simulasi ulang (persentil + markets_sim diambil dari artefak).

Exit code: 0 = perbandingan lengkap tercetak (termasuk bila seleksi
baru fail-closed — itu hasil, bukan error); 2 = tidak bisa jalan
(file tidak ditemukan / artefak tidak memuat laga yang diminta /
modul analis atau signature baru cushion belum tersedia — dalam hal
ini sisi SEBELUM tetap dicetak sejauh yang bisa, lalu pesan jelas
tentang apa yang belum tersedia).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine import cushion as cushion_mod
from engine import nba_analysis as nba_analysis_mod

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ANALYSIS = REPO_ROOT / "out" / "analysis_live_det_atl.json"
DEFAULT_LADDER = REPO_ROOT / "out" / "poly_ladder_nba-det-atl-2026-11-22.json"
DEFAULT_MATCH = "DET@ATL_2026-11-22"


def _fmt_poin(nilai) -> str:
    """Format poin gaya Indonesia; '?' bila bukan angka."""
    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        return "?"
    if nilai == int(nilai):
        return str(int(nilai))
    return f"{nilai:.1f}".replace(".", ",")


def _fmt_sen(nilai) -> str:
    """Format harga sen; '?' bila bukan angka."""
    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        return "?"
    if nilai == int(nilai):
        return f"{int(nilai)}¢"
    return f"{nilai:.1f}¢".replace(".", ",")


def _fmt_usd(nilai) -> str:
    """Format dolar AS; 'tidak tercatat' bila bukan angka."""
    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        return "tidak tercatat"
    return f"${nilai:,.0f}".replace(",", ".")


def _fmt_persen(nilai) -> str:
    """Format peluang 0-1 jadi persen; '?' bila bukan angka."""
    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        return "?"
    return f"{nilai * 100.0:.1f}%".replace(".", ",")


def _angka(nilai):
    """Float hingga atau None (bool ditolak)."""
    import math

    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        return None
    if not math.isfinite(nilai):
        return None
    return float(nilai)


def _muat_json(path: Path):
    """Muat JSON; (data, None) atau (None, pesan_error)."""
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, f"tidak bisa membaca {path}: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"JSON tidak valid {path}: {exc}"


def _ambil_nba_analysis(data, match_id: str):
    """Ambil artefak nba_analysis dari output analyze / artefak langsung.

    Menerima (a) artefak nba_analysis langsung, (b) output analyze
    {"matches": [{"nba_analysis": ...}]}. Bila match_id diberikan,
    pilih laga itu; bila None, pakai laga pertama yang punya
    nba_analysis. Mengembalikan (artefak, None) atau (None, alasan).
    """
    if not isinstance(data, dict):
        return None, "file analisis bukan objek JSON"
    if data.get("format") == "nba_analysis":
        if match_id is None or data.get("match_id") == match_id:
            return data, None
        return None, f"artefak untuk {data.get('match_id')}, bukan {match_id}"
    matches = data.get("matches")
    if not isinstance(matches, list):
        return None, "file analisis bukan artefak nba_analysis / output analyze"
    for entri in matches:
        if not isinstance(entri, dict):
            continue
        artefak = entri.get("nba_analysis")
        if not isinstance(artefak, dict):
            continue
        if match_id is None or artefak.get("match_id") == match_id:
            return artefak, None
    return None, f"laga {match_id} tidak ditemukan di file analisis"


def _ambil_tangga_under(data):
    """Entri Under dari file tangga Polymarket (format fetch_poly_ladder).

    Mengembalikan (list_entri, None) atau (None, alasan). Filter sama
    dengan builder: side 'under' + line angka.
    """
    if not isinstance(data, dict):
        return None, "file tangga bukan objek JSON"
    ladders = data.get("ladders")
    if not isinstance(ladders, dict):
        return None, "file tangga tidak punya kunci 'ladders'"
    totals = ladders.get("totals")
    if not isinstance(totals, list):
        return None, "tangga tidak punya daftar 'totals'"
    entri = [
        e
        for e in totals
        if isinstance(e, dict)
        and str(e.get("side") or "").lower() == "under"
        and _angka(e.get("line")) is not None
    ]
    if not entri:
        return None, "tangga Under kosong"
    return entri, None


def _coba_muat_analis():
    """(modul_analis, None) atau (None, alasan belum tersedia)."""
    try:
        if importlib.util.find_spec("engine.analis") is None:
            return None, "modul engine/analis.py belum tersedia (pekerja A)"
    except (ImportError, ValueError) as exc:
        return None, f"modul analis tidak bisa dicari: {exc}"
    try:
        from engine import analis as analis_mod

        return analis_mod, None
    except ImportError as exc:
        return None, f"modul analis gagal diimpor: {exc}"


def _teks_kaki_lama(kaki: dict | None, nama: str) -> list[str]:
    """Baris SEBELUM untuk satu kaki tersimpan."""
    if kaki is None:
        return [f"  {nama}: tidak ada di artefak tersimpan."]
    garis = kaki.get("line")
    if garis is None or not kaki.get("meets"):
        return [
            f"  {nama}: tidak memenuhi syarat "
            f"(alasan: {kaki.get('reason') or 'tidak tercatat'})."
        ]
    return [
        f"  {nama}: Under {_fmt_poin(garis)} @ "
        f"{_fmt_sen(kaki.get('price_cents'))} "
        f"(jup {_fmt_sen(kaki.get('jup_estimated_cents'))}), "
        f"p_model {_fmt_persen(kaki.get('p_model'))}."
    ]


def _teks_kaki_baru(
    nama: str, hasil: dict, markets_sim: dict, alasan_bantalan: str | None
) -> list[str]:
    """Baris SESUDAH untuk satu hasil cushion baru."""
    if hasil is None:
        return [f"  {nama}: tidak dihitung ({alasan_bantalan})."]
    garis = _angka(hasil.get("line"))
    if garis is None or not hasil.get("meets"):
        return [f"  {nama}: TIDAK MEMENUHI — {hasil.get('reason') or 'tanpa alasan'}."]
    p_model = markets_sim.get(f"total_under_{garis:g}")
    baris = [
        f"  {nama}: Under {_fmt_poin(garis)} @ "
        f"{_fmt_sen(hasil.get('price_cents'))} "
        f"(jup {_fmt_sen(hasil.get('jup_estimated_cents'))}), "
        f"p_model {_fmt_persen(p_model)}, "
        f"volume {_fmt_usd(hasil.get('volume_usd'))}"
        + (" — TIPIS" if hasil.get("thin") is True else "")
        + "."
    ]
    climb = hasil.get("climb")
    if climb is not None and climb is not False:
        if isinstance(climb, dict):
            dari = _fmt_poin(climb.get("from_line"))
            ke = _fmt_poin(climb.get("to_line"))
            alasan = climb.get("reason")
            rungs = climb.get("rungs")
            arti = {
                "harga_minimum": "harga di bawah minimum",
                "peluang_model": "peluang model di bawah target",
                "volume_tipis": "volume tipis",
            }
            teks = f"    Naik tangga: {dari} -> {ke}"
            if isinstance(rungs, int) and not isinstance(rungs, bool) and rungs > 1:
                teks += f" ({rungs} anak tangga)"
            if isinstance(alasan, str) and alasan:
                sebab = [
                    arti.get(kode.strip(), kode.strip())
                    for kode in alasan.split("+")
                    if kode.strip()
                ]
                if sebab:
                    teks += " karena " + ", ".join(sebab)
            baris.append(teks + ".")
        elif climb is True:
            baris.append("    Naik tangga di atas garis pertama yang memenuhi.")
        else:
            baris.append(f"    Naik tangga: {climb}.")
    return baris


def bandingkan(
    analysis_path: Path, ladder_path: Path, match_id: str
) -> tuple[str, int]:
    """Jalankan perbandingan; kembalikan (teks_laporan, exit_code)."""
    baris: list[str] = []
    baris.append(f"Perbandingan racik Tahap 4 — {match_id or '(laga pertama)'}")
    baris.append(f"Analisis tersimpan: {analysis_path}")
    baris.append(f"Tangga tersimpan: {ladder_path}")
    baris.append("")

    data_analisis, galat = _muat_json(analysis_path)
    if galat is not None:
        return "\n".join(baris + [f"GAGAL: {galat}"]) + "\n", 2
    artefak, galat = _ambil_nba_analysis(data_analisis, match_id)
    if galat is not None:
        return "\n".join(baris + [f"GAGAL: {galat}"]) + "\n", 2
    data_tangga, galat = _muat_json(ladder_path)
    if galat is not None:
        return "\n".join(baris + [f"GAGAL: {galat}"]) + "\n", 2
    entri_under, galat = _ambil_tangga_under(data_tangga)
    if galat is not None:
        return "\n".join(baris + [f"GAGAL: {galat}"]) + "\n", 2

    sim = artefak.get("simulation") or {}
    dist_total = (sim.get("score_distribution") or {}).get("total") or {}
    markets_sim = sim.get("markets") or {}
    market = artefak.get("market") or {}
    main_line = _angka(market.get("main_total_line"))
    inputs_data = artefak.get("inputs") or {}
    kaki_lama = {
        kaki.get("ticket"): kaki
        for kaki in (artefak.get("legs") or [])
        if isinstance(kaki, dict)
    }

    baris.append("Konteks (dari artefak tersimpan):")
    baris.append(
        f"  Median sim: {_fmt_poin(dist_total.get('median'))}; "
        f"p74: {_fmt_poin(dist_total.get('p74'))}; "
        f"garis market: {_fmt_poin(main_line)}."
    )
    baris.append("")
    baris.append("SEBELUM (aturan lama, dari artefak tersimpan):")
    baris.extend(_teks_kaki_lama(kaki_lama.get("insurance"), "Asuransi"))
    baris.extend(_teks_kaki_lama(kaki_lama.get("main"), "Utama"))
    # Volume/thin garis lama dibaca dari tangga tersimpan (artefak
    # lama tidak membawa volume_usd/thin di kaki).
    for nama, tiket in (("Asuransi", "insurance"), ("Utama", "main")):
        kaki = kaki_lama.get(tiket)
        garis = _angka(kaki.get("line")) if kaki else None
        if garis is None:
            continue
        cocok = [e for e in entri_under if _angka(e.get("line")) == garis]
        if not cocok:
            baris.append(
                f"  Volume {nama} Under {_fmt_poin(garis)}: tidak ada di tangga."
            )
            continue
        entri = cocok[0]
        baris.append(
            f"  Volume {nama} Under {_fmt_poin(garis)}: "
            f"{_fmt_usd(entri.get('volume_usd'))}"
            + (" — TIPIS" if entri.get("thin") is True else "")
            + "."
        )
    baris.append("")

    # Statistik laga (input bantalan adaptif) — dihitung dari inputs
    # tersimpan dengan helper yang SAMA dengan builder (satu implementasi).
    stats_laga = nba_analysis_mod.stats_laga_untuk_analis(inputs_data)
    baris.append("Statistik laga (input bantalan adaptif):")
    for kunci, label in (
        ("ortg_home", "ORtg kandang (musim)"),
        ("ortg_away", "ORtg tandang (musim)"),
        ("ortg_liga_rata", "ORtg rata-rata liga"),
        ("total_rata_5laga", "Rata-rata total 5 laga terakhir"),
        ("total_rata_musim", "Rata-rata total musim ini"),
    ):
        nilai = stats_laga.get(kunci)
        baris.append(
            f"  {label}: "
            + (_fmt_poin(nilai) if nilai is not None else "tidak tersedia")
            + "."
        )
    baris.append("")

    analis_mod, galat_analis = _coba_muat_analis()
    if galat_analis is not None:
        baris.append("SESUDAH: BELUM BISA DIHITUNG")
        baris.append(f"  {galat_analis}.")
        baris.append(
            "  Sisi SEBELUM di atas tetap sah; jalankan lagi skrip ini "
            "setelah modul analis + signature baru cushion terpasang."
        )
        return "\n".join(baris) + "\n", 2
    try:
        cfg = config_mod.load_playstyle()
    except Exception as exc:  # noqa: BLE001 - config gagal = tidak bisa jalan
        baris.append("SESUDAH: BELUM BISA DIHITUNG")
        baris.append(f"  Config gagal dibaca: {exc}.")
        return "\n".join(baris) + "\n", 2

    try:
        hasil_bantalan = analis_mod.bantalan_adaptif(stats_laga, dist_total, cfg)
    except Exception as exc:  # noqa: BLE001 - analis gagal = hasil tercatat
        baris.append("SESUDAH: BELUM BISA DIHITUNG")
        baris.append(f"  bantalan_adaptif gagal: {type(exc).__name__}: {exc}.")
        return "\n".join(baris) + "\n", 2
    if hasil_bantalan is None:
        baris.append("SESUDAH (seleksi baru): FAIL-CLOSED")
        baris.append(
            "  Bantalan adaptif None (data tidak lengkap) — kedua kaki "
            "tidak memenuhi syarat, tanpa fallback ke +8."
        )
        return "\n".join(baris) + "\n", 0
    if (
        not isinstance(hasil_bantalan, dict)
        or _angka(hasil_bantalan.get("cushion_points")) is None
    ):
        baris.append("SESUDAH: BELUM BISA DIHITUNG")
        baris.append("  bantalan_adaptif mengembalikan bentuk yang tidak sah.")
        return "\n".join(baris) + "\n", 2
    bantalan = _angka(hasil_bantalan["cushion_points"])
    baris.append("SESUDAH (seleksi baru):")
    alasan = hasil_bantalan.get("alasan")
    if isinstance(alasan, str) and alasan:
        # Alasan analis sudah kalimat lengkap ("Bantalan 9,36 poin
        # karena ...") — tampilkan apa adanya, jangan ditumpuk "karena".
        baris.append(f"  Bantalan adaptif: {alasan}")
    else:
        baris.append(f"  Bantalan adaptif: +{_fmt_poin(bantalan)} poin.")
    try:
        harga_min_utama, sumber_utama = nba_analysis_mod.baca_harga_min(
            cfg, "harga_min_utama_cents"
        )
        harga_min_asuransi, sumber_asuransi = nba_analysis_mod.baca_harga_min(
            cfg, "harga_min_asuransi_cents"
        )
    except ValueError as exc:
        baris.append(f"  GAGAL: harga minimum tidak valid: {exc}.")
        return "\n".join(baris) + "\n", 2
    baris.append(
        f"  Harga minimum: Utama {_fmt_sen(harga_min_utama)} ({sumber_utama}), "
        f"Asuransi {_fmt_sen(harga_min_asuransi)} ({sumber_asuransi})."
    )
    try:
        peluang_under = nba_analysis_mod.peluang_under_dari_markets(markets_sim)
        hasil_utama = cushion_mod.utama_line(
            dist_total,
            main_line,
            entri_under,
            cfg=cfg,
            cushion_points=bantalan,
            peluang_under=peluang_under,
            harga_min_cents=harga_min_utama,
        )
        garis_utama = _angka(hasil_utama.get("line"))
        hasil_asuransi = cushion_mod.insurance_line(
            dist_total,
            main_line,
            entri_under,
            cfg=cfg,
            garis_di_atas=garis_utama,
            peluang_under=peluang_under,
            harga_min_cents=harga_min_asuransi,
        )
    except TypeError as exc:
        baris.append("  GAGAL: signature baru cushion belum terpasang:")
        baris.append(f"    {exc}.")
        baris.append(
            "  Jalankan lagi skrip ini setelah pekerja A memasang "
            "signature baru cushion.py."
        )
        return "\n".join(baris) + "\n", 2
    except (ValueError, config_mod.ConfigError) as exc:
        baris.append(f"  GAGAL: cushion gagal: {exc}.")
        return "\n".join(baris) + "\n", 2
    baris.extend(_teks_kaki_baru("Utama", hasil_utama, markets_sim, None))
    baris.extend(_teks_kaki_baru("Asuransi", hasil_asuransi, markets_sim, None))

    # Penilaian wajar garis Utama yang baru.
    harga_utama = _angka(hasil_utama.get("jup_estimated_cents"))
    if harga_utama is None:
        harga_utama = _angka(hasil_utama.get("price_cents"))
    try:
        wajar = analis_mod.nilai_wajar(
            acuan_sim=_angka(dist_total.get("median")),
            garis_market=main_line,
            garis_harga=garis_utama,
            harga_cents=harga_utama,
            bantalan_dibutuhkan_poin=bantalan,
            cfg=cfg,
        )
    except Exception as exc:  # noqa: BLE001 - nilai_wajar gagal = tercatat
        baris.append("")
        baris.append(f"Penilaian wajar: gagal dihitung ({type(exc).__name__}).")
        return "\n".join(baris) + "\n", 0
    baris.append("")
    baris.append("Penilaian wajar (garis Utama yang baru):")
    if not isinstance(wajar, dict):
        baris.append(
            "  tidak terverifikasi (nilai_wajar mengembalikan bentuk tak sah)."
        )
        return "\n".join(baris) + "\n", 0
    penilaian = wajar.get("penilaian")
    kata = {
        "wajar": "WAJAR",
        "di_bawah_wajar": "DI BAWAH WAJAR",
        "tidak_terverifikasi": "tidak terverifikasi",
    }.get(penilaian, str(penilaian))
    baris.append(
        f"  Acuan sim {_fmt_poin(wajar.get('acuan_sim'))}; garis market "
        f"{_fmt_poin(wajar.get('garis_market'))}; garis harga "
        f"{_fmt_poin(wajar.get('garis_harga'))} @ "
        f"{_fmt_sen(wajar.get('harga_cents'))}; jarak "
        f"{_fmt_poin(wajar.get('jarak_poin'))} poin; bantalan dibutuhkan "
        f"{_fmt_poin(wajar.get('bantalan_dibutuhkan_poin'))} poin."
    )
    baris.append(f"  Penilaian: {kata}.")
    penjelasan = wajar.get("penjelasan")
    if isinstance(penjelasan, str) and penjelasan:
        baris.append(f"  Alasan: {penjelasan}")
    return "\n".join(baris) + "\n", 0


def main(argv=None) -> int:
    """Entry point CLI."""
    parser = argparse.ArgumentParser(
        description="Bandingkan racik SEBELUM vs SESUDAH Tahap 4 (offline)."
    )
    parser.add_argument(
        "--analysis",
        type=Path,
        default=DEFAULT_ANALYSIS,
        help="file analisis tersimpan (output analyze / artefak nba_analysis)",
    )
    parser.add_argument(
        "--ladder",
        type=Path,
        default=DEFAULT_LADDER,
        help="file tangga Polymarket tersimpan (fetch_poly_ladder)",
    )
    parser.add_argument(
        "--match",
        default=DEFAULT_MATCH,
        help="match_id nba_analysis yang dibandingkan",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="tulis laporan perbandingan ke file ini juga (selain stdout)",
    )
    args = parser.parse_args(argv)
    teks, kode = bandingkan(args.analysis, args.ladder, args.match)
    print(teks, end="")
    if args.out is not None:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(teks, encoding="utf-8")
            print(f"(laporan juga ditulis ke {args.out})")
        except OSError as exc:
            print(f"error: tidak bisa menulis {args.out}: {exc}", file=sys.stderr)
            return 2
    return kode


if __name__ == "__main__":
    raise SystemExit(main())
