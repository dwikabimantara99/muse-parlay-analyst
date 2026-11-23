"""Verifikasi live setan per pemain (DEN@CHI 22 Nov 2026).

Menarik data pemain 3P NYATA (stats.nba.com, fallback BBRef — 0 kredit
Odds API), menghitung total setan per pemain untuk DEN@CHI dari artefak
verifikasi tahap 4, dan membandingkannya dengan setan umum (+18,07)
serta hasil aktual (total 296). Menulis out/verifikasi_setan_pemain.json
(gitignored) + mencetak ringkasan.

CATATAN KEJUJURAN (point-in-time): data musim berjalan yang ditarik
hari ini SUDAH mencakup laga DEN@CHI itu sendiri (22 Nov) — verifikasi
ini bukan rekonstruksi pra-laga yang sempurna. Perkiraan kontaminasi
dicatat di output (perbandingan percobaan yang diharapkan vs total tim
pra-laga 71,59 dari LAPORAN-EKOR-3P.md §8.1) — lihat
LAPORAN-SETAN-PEMAIN.md §5.

Penggunaan: python3 scripts/verifikasi_setan_pemain.py [--no-fetch]
(--no-fetch memakai cache DiskCache bila masih berlaku; tanpa flag
pun cache dipakai bila belum kedaluwarsa).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine import setan_pemain as sp_mod
from engine import stress as stress_mod
from ingest import pemain_3p as p3p_mod

ARTEFAK = (
    Path(__file__).resolve().parent.parent
    / "out"
    / "analysis_verif_tahap4_2026-11-22.json"
)
OUTPUT = Path(__file__).resolve().parent.parent / "out" / "verifikasi_setan_pemain.json"

# Total 3PA tim pra-laga (sebelum 22 Nov) dari LAPORAN-EKOR-3P.md §8.1 —
# pembanding untuk mengukur kontaminasi point-in-time.
TIGA_PA_PRALAGA = {"DEN": 30.86, "CHI": 40.73}

# Hasil aktual laga (untuk konteks, bukan target).
TOTAL_AKTUAL = 296.0


def _den_chi() -> dict:
    data = json.loads(ARTEFAK.read_text(encoding="utf-8"))
    for match in data["matches"]:
        if "den-chi" in match["match_id"]:
            return match["nba_analysis"]
    raise SystemExit("DEN@CHI tidak ada di artefak verif tahap 4")


def main() -> int:
    """Jalankan verifikasi live; 0 bila sukses, 1 bila fetch gagal."""
    cfg = config_mod.load_playstyle()
    analysis = _den_chi()
    median = analysis["simulation"]["score_distribution"]["total"]["median"]
    garis_bandar = analysis["market"]["main_total_line"]

    hasil_fetch = p3p_mod.fetch_pemain_3p()
    if not hasil_fetch.ok:
        print(f"FETCH GAGAL: {hasil_fetch.error}")
        return 1
    pemain = hasil_fetch.data or []
    print(
        f"fetch pemain 3P OK: {len(pemain)} pemain, sumber={hasil_fetch.extra.get('source_used')}, "
        f"fallback={hasil_fetch.extra.get('fallback')}"
    )

    # Cross-check BBRef (sumber fallback): jumlah 3PA rotasi DEN/CHI
    # harus mendekati stats.nba.com bila kedua sumber sepakat.
    cross_check: dict = {}
    bbref = p3p_mod.fetch_pemain_3p_bbref()
    if bbref.ok:
        ambang = float(cfg["setan_pemain"]["ambang_menit_rotasi"])
        for tim in ("DEN", "CHI"):
            for label, daftar in (
                ("stats_nba", pemain),
                ("bbref", bbref.data or []),
            ):
                rotasi = [
                    p
                    for p in daftar
                    if p.get("team") == tim and (p.get("mp_per_game") or 0) >= ambang
                ]
                cross_check[f"{tim}_{label}_rotasi_n"] = len(rotasi)
                cross_check[f"{tim}_{label}_rotasi_3pa"] = round(
                    sum(p.get("fg3a_per_game") or 0 for p in rotasi), 2
                )
        cross_check["bbref_n_players"] = len(bbref.data or [])
    else:
        cross_check["bbref_error"] = bbref.error

    absen = sp_mod.pemain_absen_dari_artefak(analysis)
    print(f"pemain OUT dari artefak ({len(absen)}): {sorted(absen)}")

    hasil_setan = sp_mod.hitung_setan_pemain(
        pemain,
        "CHI",
        "DEN",
        median,
        garis_bandar=garis_bandar,
        pemain_absen=absen,
        cfg=cfg,
    )
    kaki = [
        {"line": 252.5, "ticket": "insurance", "price_cents": 82.0},
        {"line": 250.5, "ticket": "main", "price_cents": 79.0},
    ]
    hasil_stress = stress_mod.skenario_panas(
        analysis, kaki=kaki, cfg=cfg, setan_pemain=hasil_setan
    )
    # Setan umum (fallback) untuk perbandingan.
    hasil_umum = stress_mod.skenario_panas(analysis, kaki=kaki, cfg=cfg)

    # Point-in-time: BBRef tertinggal satu laga dari stats.nba.com
    # (GP tiap pemain DEN/CHI tepat 1 lebih sedikit — laga 22 Nov
    # belum masuk saat ditarik), sehingga demon dari data BBRef adalah
    # perkiraan pra-laga yang jujur. Selisihnya vs demon stats.nba.com
    # mengukur kontaminasi look-ahead.
    setan_bbref: dict | None = None
    if bbref.ok:
        hasil_bbref = sp_mod.hitung_setan_pemain(
            bbref.data or [],
            "CHI",
            "DEN",
            median,
            garis_bandar=garis_bandar,
            pemain_absen=absen,
            cfg=cfg,
        )
        setan_bbref = {
            "total_setan_pemain": hasil_bbref["total_setan_pemain"],
            "geser_setan_pemain": hasil_bbref["geser_setan_pemain"],
            "deviasi_setan_pemain_dari_garis_bandar": hasil_bbref[
                "deviasi_setan_pemain_dari_garis_bandar"
            ],
            "percobaan_3p_diharapkan_gabungan": hasil_bbref[
                "percobaan_3p_diharapkan_gabungan"
            ],
            "pct_terbaik_liga": hasil_bbref["pct_terbaik_liga"],
            "selisih_vs_stats_nba": round(
                hasil_bbref["total_setan_pemain"] - hasil_setan["total_setan_pemain"],
                2,
            ),
            "catatan": hasil_bbref["catatan"],
        }

    # Sensitivitas terhadap ambang percobaan minimum % terbaik liga.
    sensitivitas = {}
    for ambang in (25, 50, 75, 100, 150):
        info = sp_mod.pct_terbaik_liga(pemain, ambang)
        if info is None:
            sensitivitas[str(ambang)] = None
            continue
        cfg_sens = {
            "setan_pemain": {
                "pct_terbaik_min_total_3pa": ambang,
                "ambang_menit_rotasi": float(
                    cfg["setan_pemain"]["ambang_menit_rotasi"]
                ),
            }
        }
        hasil_sens = sp_mod.hitung_setan_pemain(
            pemain,
            "CHI",
            "DEN",
            median,
            garis_bandar=garis_bandar,
            pemain_absen=absen,
            cfg=cfg_sens,
        )
        sensitivitas[str(ambang)] = {
            "pct_terbaik": info["pct"],
            "player": info["player"],
            "team": info["team"],
            "total_3pa": info["total_3pa"],
            "total_setan_pemain": hasil_sens["total_setan_pemain"],
        }

    # Perbandingan slate: demon pemain vs demon umum untuk dua laga
    # lain di artefak yang sama (OKC@MIA, BOS@GSW).
    slate: dict = {}
    data_slate = json.loads(ARTEFAK.read_text(encoding="utf-8"))
    for match in data_slate["matches"]:
        if "den-chi" in match["match_id"]:
            continue
        na = match["nba_analysis"]
        med = na["simulation"]["score_distribution"]["total"]["median"]
        garis = na["market"]["main_total_line"]
        absen_laga = sp_mod.pemain_absen_dari_artefak(na)
        try:
            hasil_laga = sp_mod.hitung_setan_pemain(
                pemain,
                na["home_tricode"],
                na["away_tricode"],
                med,
                garis_bandar=garis,
                pemain_absen=absen_laga,
                cfg=cfg,
            )
        except ValueError as exc:
            slate[match["match_id"]] = {"error": str(exc)}
            continue
        slate[match["match_id"]] = {
            "median": med,
            "garis_bandar": garis,
            "total_setan_pemain": hasil_laga["total_setan_pemain"],
            "total_setan_umum": round(med + float(cfg["stress"]["setan_points"]), 2),
            "selisih_pemain_vs_umum": round(
                hasil_laga["total_setan_pemain"]
                - (med + float(cfg["stress"]["setan_points"])),
                2,
            ),
            "deviasi_vs_garis_bandar": hasil_laga[
                "deviasi_setan_pemain_dari_garis_bandar"
            ],
            "percobaan_diharapkan": hasil_laga["percobaan_3p_diharapkan_gabungan"],
            "n_rotasi_main": (
                hasil_laga["tim"]["kandang"]["n_pemain_rotasi_main"]
                + hasil_laga["tim"]["tandang"]["n_pemain_rotasi_main"]
            ),
        }

    total_setan = hasil_setan["total_setan_pemain"]
    keluaran = {
        "fetch": {
            "source_used": hasil_fetch.extra.get("source_used"),
            "fallback": hasil_fetch.extra.get("fallback"),
            "n_players": len(pemain),
            "fetched_at": hasil_fetch.fetched_at,
        },
        "cross_check_bbref": cross_check,
        "pemain_absen": sorted(absen),
        "setan_pemain": hasil_setan,
        "setan_pemain_bbref_point_in_time": setan_bbref,
        "stress_pemain": {
            "setan_pemain_dipakai": hasil_stress["setan_pemain_dipakai"],
            "geser_setan": hasil_stress["skenario"]["setan"]["geser_points"],
            "kaki": hasil_stress["kaki"],
        },
        "stress_umum": {
            "geser_setan": hasil_umum["skenario"]["setan"]["geser_points"],
            "kaki": [
                {
                    "line": k["line"],
                    "ticket": k["ticket"],
                    "p_setan": k["p_under"]["setan"],
                    "flag_setan": k["flag_setan"],
                }
                for k in hasil_umum["kaki"]
            ],
        },
        "sensitivitas_ambang_pct_terbaik": sensitivitas,
        "slate_lain": slate,
        "pembanding": {
            "median_sim": median,
            "garis_bandar": garis_bandar,
            "total_setan_umum": round(median + float(cfg["stress"]["setan_points"]), 2),
            "total_setan_pemain": total_setan,
            "selisih_pemain_vs_umum": round(
                total_setan - (median + float(cfg["stress"]["setan_points"])), 2
            ),
            "total_aktual": TOTAL_AKTUAL,
            "selisih_aktual_vs_setan_pemain": round(TOTAL_AKTUAL - total_setan, 2),
            "tiga_pa_pralaga_tim": TIGA_PA_PRALAGA,
            "tiga_pa_pralaga_gabungan": round(sum(TIGA_PA_PRALAGA.values()), 2),
            "percobaan_diharapkan_gabungan": hasil_setan[
                "percobaan_3p_diharapkan_gabungan"
            ],
        },
    }
    OUTPUT.write_text(
        json.dumps(keluaran, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"\nmedian sim: {median}; garis bandar: {garis_bandar}")
    print(
        f"total setan PEMAIN: {total_setan} (geser {hasil_setan['geser_setan_pemain']:+.2f})"
    )
    print(
        f"total setan UMUM: {keluaran['pembanding']['total_setan_umum']} "
        f"(selisih pemain-vs-umum {keluaran['pembanding']['selisih_pemain_vs_umum']:+.2f})"
    )
    print(
        f"total AKTUAL: {TOTAL_AKTUAL} (di atas setan pemain {TOTAL_AKTUAL - total_setan:+.2f})"
    )
    for k in hasil_stress["kaki"]:
        print(
            f"kaki U{k['line']} ({k['ticket']}): flag_setan_pemain={k['flag_setan_pemain']}, "
            f"p_setan_pemain={k['p_setan_pemain']}, flag_setan={k['flag_setan']}"
        )
    print(f"\noutput: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
