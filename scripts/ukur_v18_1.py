"""Ukur 5 kriteria acceptance test v18.1 (Gemini §4) di slate uji 10 baris.

    python3 scripts/ukur_v18_1.py [--out out/ukur_v18_1.json]

Tiruan scripts/ukur_v18.py untuk patch v18.1. Membaca artefak
analisis (22 Nov live 7 laga + verif tahap 4 3 laga), menjalankan
engine/skip_awal.py (evaluasi_skip_awal), engine/vonis.py
(nilai_vonis + evaluasi_veto), engine/equilibrium.py
(cari_equilibrium kedua tiket), engine/ticket_composer.py
(compose_tickets), dan engine/nba_analysis.py (_sebab_cedera_baru
sintetis) per baris, lalu menulis JSON + mencetak tabel ringkasan.

KRITERIA (REFERENSI-PATCH-V18-1-GEMINI.md §4):
  (1) skip_awal baru: DEN@CHI wajib tetap di-skip (dan/atau
      diblokir veto); OKC@MIA, ORL@WAS, IND@NYK TIDAK lagi kena
      skip pola Denver.
  (2) Pemulihan T2: komposer Asuransi memilih kombinasi dari
      valid_lines (80-89c) mencapai pengali bersih >= 2,00x TANPA
      melanggar gate maupun tanpa-kembar; bila tidak mencapai
      2,00x, opsi fallback [1,80x, 1,99x] TERLAPORKAN dengan joint
      P_final + alasan (bukan tiket). Hasil literal dicatat apa
      adanya.
  (3) Peta rim protector 30/30 (0 tim buta pada 10 laga slate
      24 Nov, khususnya OKC@IND, PHX@NOP, LAC@HOU).
  (4) Kesegaran cedera: pemain absen jangka panjang (GP == 0,
      contoh Haliburton) TIDAK lagi memicu _sebab_cedera_baru
      (kontrol: GP >= 3 tetap memicu).
  (5) Regresi nol: dicatat dari hasil full suite (koordinator yang
      menjalankan). Script membaca out/full_suite_v18_1.json bila
      ada — format {"total": N, "gagal": n, "error": n} — bila
      tidak ada, kriteria ini berstatus "menunggu_koordinator"
      (bukan gagal, bukan lolos).

Script ini TIDAK PERNAH memalsukan angka: kriteria yang GAGAL tetap
dicatat gagal dan script tetap exit 0. Exit 2 hanya bila file input
tidak ditemukan. Kunci/antarmuka baru Worker A/B (skip_awal baru,
insurance_fallback_option) dibaca secara DEFENSIF: bila kunci
absen, dicatat "tidak_dievaluasi" (bukan crash) — koordinator
menyesuaikan antarmuka bila perlu saat integrasi. 0 kredit Odds API.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine import equilibrium as equilibrium_mod
from engine import skip_awal as skip_awal_mod
from engine import ticket_composer as composer_mod
from engine import vonis as vonis_mod

ROOT = Path(__file__).resolve().parent.parent

ARTEFAK = [
    ("live 22 Nov", "out/analysis_live_2026-11-22.json"),
    ("verif tahap 4", "out/analysis_verif_tahap4_2026-11-22.json"),
]

# Total akhir nyata (settled) per laga (sama dengan ukur_v18.py).
FINAL_TOTAL = {
    "DET@ATL_2026-11-22": 204,
    "OKC@MIA_2026-11-22": 236,
    "ORL@WAS_2026-11-22": 212,
    "DEN@CHI_2026-11-22": 296,
    "DAL@UTA_2026-11-22": 230,
    "IND@NYK_2026-11-22": 219,
    "BOS@GSW_2026-11-22": 175,
}

# Modal total kedua tiket ($15 + $15 tiket nyata 23 Nov) untuk komposer.
STAKE_TOTAL = 30.0

# Kriteria 1: DEN wajib tetap di-skip; tiga laga ini bebas pola Denver.
LAGA_WAJIB_SKIP = "DEN@CHI_2026-11-22"
LAGA_BEBAS_POLA_DENVER = [
    "OKC@MIA_2026-11-22",
    "ORL@WAS_2026-11-22",
    "IND@NYK_2026-11-22",
]

# Kriteria 3: 20 tim slate 24 Nov + 3 laga yang disebut eksplisit.
TIM_SLATE_24_NOV = {
    "MEM",
    "CHA",
    "POR",
    "PHI",
    "OKC",
    "IND",
    "MIL",
    "TOR",
    "BKN",
    "MIN",
    "CLE",
    "CHI",
    "PHX",
    "NOP",
    "LAC",
    "HOU",
    "UTA",
    "LAL",
    "SAS",
    "SAC",
}
LAGA_SOROTAN_24_NOV = [
    ("OKC", "IND"),
    ("PHX", "NOP"),
    ("LAC", "HOU"),
]

# Kriteria 2: band harga valid_lines Asuransi (Patch #2).
BAND_VALID_LINES_CENTS = (80.0, 89.0)
TARGET_PENGALI_ASURANSI = 2.00
FALLBACK_PENGALI_MIN = 1.80
FALLBACK_PENGALI_MAKS = 1.99


def _baca_json(relatif: str) -> dict:
    return json.loads((ROOT / relatif).read_text(encoding="utf-8"))


def _vonis_baris(analysis: dict, cfg: dict) -> dict:
    """Vonis + veto satu baris (error dicatat, bukan raise)."""
    hasil: dict = {}
    try:
        nilai = vonis_mod.nilai_vonis(analysis, None, cfg)
        ind = nilai.get("indikator") or {}
        hasil["vonis"] = nilai.get("vonis")
        hasil["vonis_error"] = None
        hasil["demerit"] = list(ind.get("demerit") or [])
        hasil["pemicu_keras"] = ind.get("pemicu_keras")
        hasil["veto"] = ind.get("veto")
    except Exception as exc:  # noqa: BLE001 - dicatat per baris
        hasil["vonis"] = None
        hasil["vonis_error"] = f"{type(exc).__name__}: {exc}"
        hasil["demerit"] = None
        hasil["pemicu_keras"] = None
        hasil["veto"] = None
    if hasil.get("veto") is None:
        try:
            hasil["veto"] = vonis_mod.evaluasi_veto(analysis, cfg)
            hasil["veto_error"] = None
        except Exception as exc:  # noqa: BLE001 - dicatat per baris
            hasil["veto_error"] = f"{type(exc).__name__}: {exc}"
    return hasil


def _skip_baris(analysis: dict, cfg: dict) -> dict:
    """skip_awal satu baris (defensif: kunci baru boleh absen)."""
    fungsi = getattr(skip_awal_mod, "evaluasi_skip_awal", None)
    if not callable(fungsi):
        return {
            "dievaluasi": None,
            "skip": None,
            "pemicu": None,
            "pola_denver": None,
            "error": "evaluasi_skip_awal belum tersedia",
        }
    try:
        hasil_skip = fungsi(analysis, cfg)
    except Exception as exc:  # noqa: BLE001 - dicatat per baris
        return {
            "dievaluasi": None,
            "skip": None,
            "pemicu": None,
            "pola_denver": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
    pola = hasil_skip.get("pola_denver")
    return {
        "dievaluasi": hasil_skip.get("dievaluasi"),
        "skip": hasil_skip.get("skip"),
        "pemicu": list(hasil_skip.get("pemicu") or []),
        "alasan": hasil_skip.get("alasan"),
        "alasan_tidak_dievaluasi": hasil_skip.get("alasan_tidak_dievaluasi"),
        "pola_denver": (
            {
                "dievaluasi": pola.get("dievaluasi"),
                "cocok": pola.get("cocok"),
                "alasan": pola.get("alasan"),
                "syarat": pola.get("syarat"),
            }
            if isinstance(pola, dict)
            else None
        ),
        "error": None,
    }


def _eq_baris(analysis: dict, cfg: dict) -> dict:
    """Equilibrium kedua tiket satu baris (error dicatat, bukan raise)."""
    hasil: dict = {}
    for tiket in ("insurance", "main"):
        try:
            eq = equilibrium_mod.cari_equilibrium(analysis, tiket, cfg)
            hasil[tiket] = {
                "ada": bool(eq.get("ada")),
                "dihitung": bool(eq.get("dihitung")),
                "garis": eq.get("garis"),
                "harga_venue_cents": eq.get("harga_venue_cents"),
                "p_final": eq.get("p_final"),
                "edge": eq.get("edge"),
                "ev_pct": eq.get("ev_pct"),
                "n_valid_lines": (
                    len(eq.get("valid_lines"))
                    if isinstance(eq.get("valid_lines"), list)
                    else None
                ),
                "alasan_tidak_ada": eq.get("alasan_tidak_ada"),
                "alasan_tidak_dihitung": eq.get("alasan_tidak_dihitung"),
            }
        except Exception as exc:  # noqa: BLE001 - dicatat per baris
            hasil[tiket] = {"ada": None, "error": f"{type(exc).__name__}: {exc}"}
    return hasil


def _under_menang(analysis: dict, final: int | None) -> bool | None:
    """Apakah Under MENANG di garis artefak? (final < semua garis kaki)."""
    if final is None:
        return None
    garis_kaki = [
        leg.get("line")
        for leg in (analysis.get("legs") or [])
        if isinstance(leg, dict) and isinstance(leg.get("line"), (int, float))
    ]
    if not garis_kaki:
        return None
    return all(final < garis for garis in garis_kaki)


def _artefak_sintetis_cedera(nama: str, bpm: float, games_played: int) -> dict:
    """Artefak minimal untuk _sebab_cedera_baru (OUT 2 sumber)."""
    return {
        "match_id": "SINTETIS@SINTETIS_2026-11-22",
        "inputs": {
            "away": {
                "players": [
                    {
                        "player": nama,
                        "bpm": bpm,
                        "games_played": games_played,
                        "team_tricode": "IND",
                    }
                ]
            },
            "home": {"players": []},
        },
        "injuries": {
            "entries": [
                {
                    "player": nama,
                    "status": "OUT",
                    "team_tricode": "IND",
                    "sources": ["Official NBA Injury Report", "ESPN"],
                    "availability_n_sources": 2,
                }
            ]
        },
    }


def _ukur_kriteria4(cfg: dict, baris: list[dict]) -> dict:
    """Kesegaran cedera: GP==0 tidak memicu; GP>=3 tetap memicu."""
    detail: dict = {"kasus": {}, "konteks_artefak_nyata": None}
    try:
        from engine import nba_analysis as nba_analysis_mod
    except ImportError as exc:
        detail["status"] = "tidak_dievaluasi"
        detail["catatan"] = f"engine.nba_analysis tidak bisa diimpor: {exc}"
        return {"lolos": None, **detail}
    fungsi = getattr(nba_analysis_mod, "_sebab_cedera_baru", None)
    if not callable(fungsi):
        detail["status"] = "tidak_dievaluasi"
        detail["catatan"] = "_sebab_cedera_baru tidak ditemukan di nba_analysis"
        return {"lolos": None, **detail}
    for kunci, gp, harap_memicu in (
        ("gp_0_haliburton", 0, False),
        ("gp_10_kontrol", 10, True),
    ):
        try:
            artefak = _artefak_sintetis_cedera("Tyrese Haliburton", 2.5, gp)
            ada, pemain, dievaluasi, dikecualikan = fungsi(artefak, cfg)
            detail["kasus"][kunci] = {
                "games_played": gp,
                "ada_sebab": bool(ada),
                "pemain_sebab": list(pemain),
                "dievaluasi": bool(dievaluasi),
                "dikecualikan_gp": list(dikecualikan or []),
                "harap_memicu": harap_memicu,
                "sesuai_harapan": bool(ada) is harap_memicu and bool(dievaluasi),
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001 - dicatat per kasus
            detail["kasus"][kunci] = {
                "games_played": gp,
                "ada_sebab": None,
                "pemain_sebab": None,
                "dievaluasi": None,
                "harap_memicu": harap_memicu,
                "sesuai_harapan": None,
                "error": f"{type(exc).__name__}: {exc}",
            }
    # Konteks artefak nyata: Haliburton di IND@NYK live (GP=4 di
    # artefak — di bawah aturan GP>=3 ia TETAP terhitung "segar";
    # ini konteks, BUKAN bagian dari lolos/gagal kriteria 4 yang
    # memakai kasus sintetis GP==0).
    try:
        ind_live = next(
            b
            for b in baris
            if b["match_id"] == "IND@NYK_2026-11-22" and b["artefak"].startswith("live")
        )
        analysis = ind_live.get("_analysis") or {}
        ada, pemain, dievaluasi, dikecualikan = fungsi(analysis, cfg)
        detail["konteks_artefak_nyata"] = {
            "match_id": "IND@NYK_2026-11-22",
            "ada_sebab": bool(ada),
            "pemain_sebab": list(pemain),
            "dievaluasi": bool(dievaluasi),
            "dikecualikan_gp": list(dikecualikan or []),
            "catatan": (
                "Haliburton di artefak live ini GP=4 (bukan 0) — "
                "aturan GP>=3 Patch #4 membuatnya tetap terhitung; "
                "hanya konteks, bukan penentu kriteria."
            ),
        }
    except Exception as exc:  # noqa: BLE001 - konteks boleh gagal
        detail["konteks_artefak_nyata"] = {"error": f"{type(exc).__name__}: {exc}"}
    kasus = detail["kasus"]
    semua_sesuai = (
        all(k.get("sesuai_harapan") is True for k in kasus.values()) and len(kasus) == 2
    )
    detail["status"] = "dievaluasi"
    return {"lolos": semua_sesuai, **detail}


def _ukur_kriteria5() -> dict:
    """Regresi nol — dari hasil full suite yang dijalankan koordinator."""
    jalur = ROOT / "out" / "full_suite_v18_1.json"
    if not jalur.exists():
        return {
            "lolos": None,
            "status": "menunggu_koordinator",
            "catatan": (
                "out/full_suite_v18_1.json tidak ada — koordinator "
                "menjalankan full suite (python3 -m unittest discover "
                "-s tests) di akhir integrasi dan menulis file "
                'berformat {"total": N, "gagal": n, "error": n, '
                '"perintah": "..."}, lalu menjalankan ulang script '
                "ini. Kriteria ini TIDAK dinilai gagal sebelum itu."
            ),
        }
    try:
        data = json.loads(jalur.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {
            "lolos": None,
            "status": "tidak_dievaluasi",
            "catatan": f"file hasil full suite rusak: {exc}",
        }
    total = data.get("total")
    gagal = data.get("gagal")
    error = data.get("error")
    terukur = (
        isinstance(total, int)
        and total > 0
        and isinstance(gagal, int)
        and isinstance(error, int)
    )
    return {
        "lolos": bool(terukur and gagal == 0 and error == 0),
        "status": "dievaluasi" if terukur else "tidak_dievaluasi",
        "total": total,
        "gagal": gagal,
        "error": error,
        "perintah": data.get("perintah"),
        "catatan": (
            "Regresi nol = 0 gagal + 0 error dari full suite."
            if terukur
            else "File hasil tidak memuat total/gagal/error yang valid."
        ),
    }


def ukur() -> dict:
    """Jalankan pengukuran; kembalikan dict hasil lengkap."""
    cfg = config_mod.load_playstyle()
    baris: list[dict] = []
    live_analyses: list[dict] = []
    for label_artefak, relatif in ARTEFAK:
        data = _baca_json(relatif)
        for match in data.get("matches") or []:
            analysis = match.get("nba_analysis") or {}
            match_id = str(match.get("match_id") or analysis.get("match_id"))
            nba_id = str(analysis.get("match_id") or match_id)
            info_vonis = _vonis_baris(analysis, cfg)
            info_skip = _skip_baris(analysis, cfg)
            info_eq = _eq_baris(analysis, cfg)
            final = FINAL_TOTAL.get(nba_id)
            baris.append(
                {
                    "match_id": nba_id,
                    "slate_match_id": match_id,
                    "artefak": label_artefak,
                    "status_analisis": analysis.get("status"),
                    "final_total": final,
                    "under_menang_di_garis_artefak": _under_menang(analysis, final),
                    **info_vonis,
                    "skip_awal": info_skip,
                    "equilibrium": info_eq,
                    "_analysis": analysis,
                }
            )
            if label_artefak.startswith("live"):
                live_analyses.append(analysis)

    # --- Kriteria 1: skip_awal baru. ---
    def _pola_cocok(b: dict) -> bool | None:
        pola = (b.get("skip_awal") or {}).get("pola_denver")
        if not isinstance(pola, dict):
            return None
        return pola.get("cocok") is True

    def _terblokir(b: dict) -> bool:
        veto = b.get("veto") or {}
        return (
            b.get("skip_awal", {}).get("skip") is True
            or b.get("vonis") in ("kuning", "tunggu_lineup")
            or veto.get("menyala") is True
        )

    den_baris = [b for b in baris if b["match_id"] == LAGA_WAJIB_SKIP]
    den_detail = [
        {
            "artefak": b["artefak"],
            "vonis": b["vonis"],
            "skip": b.get("skip_awal", {}).get("skip"),
            "pemicu_skip": b.get("skip_awal", {}).get("pemicu"),
            "pola_denver_cocok": _pola_cocok(b),
            "pola_denver_dievaluasi": (
                (b.get("skip_awal", {}).get("pola_denver") or {}).get("dievaluasi")
            ),
            "veto_menyala": (b.get("veto") or {}).get("menyala"),
            "terblokir": _terblokir(b),
            "skip_error": b.get("skip_awal", {}).get("error"),
        }
        for b in den_baris
    ]
    den_lolos = bool(den_baris) and all(_terblokir(b) for b in den_baris)
    bebas_detail = []
    for laga in LAGA_BEBAS_POLA_DENVER:
        for b in [x for x in baris if x["match_id"] == laga]:
            bebas_detail.append(
                {
                    "match_id": laga,
                    "artefak": b["artefak"],
                    "vonis": b["vonis"],
                    "skip": b.get("skip_awal", {}).get("skip"),
                    "pemicu_skip": b.get("skip_awal", {}).get("pemicu"),
                    "pola_denver_cocok": _pola_cocok(b),
                    "pola_denver_dievaluasi": (
                        (b.get("skip_awal", {}).get("pola_denver") or {}).get(
                            "dievaluasi"
                        )
                    ),
                    "skip_error": b.get("skip_awal", {}).get("error"),
                }
            )
    pola_dinilai = [d for d in bebas_detail if d["pola_denver_cocok"] is not None]
    bebas_lolos = bool(pola_dinilai) and all(
        d["pola_denver_cocok"] is False for d in pola_dinilai
    )
    kriteria1 = {
        "kriteria": (
            "skip_awal baru: DEN@CHI tetap di-skip/diblokir; OKC@MIA, "
            "ORL@WAS, IND@NYK bebas pola Denver"
        ),
        "lolos": bool(den_lolos and bebas_lolos),
        "den_wajib_skip": {
            "lolos": den_lolos,
            "n_baris_den": len(den_baris),
            "detail": den_detail,
        },
        "bebas_pola_denver": {
            "lolos": bebas_lolos,
            "n_baris_dinilai": len(pola_dinilai),
            "detail": bebas_detail,
        },
        "catatan": (
            "DEN 'terblokir' = skip_awal menyala ATAU vonis "
            "kuning/tunggu_lineup ATAU veto menyala. 'Bebas pola "
            "Denver' dinilai dari pola_denver.cocok (bukan skip "
            "keseluruhan — laga boleh di-skip pemicu lain, mis. OT)."
        ),
    }

    # --- Kriteria 2: pemulihan T2 (komposer Asuransi). ---
    try:
        hasil_racik = composer_mod.compose_tickets(
            live_analyses, None, cfg, stake_total=STAKE_TOTAL
        )
        tiket_ins = hasil_racik.get("insurance")
        ins_valid = isinstance(tiket_ins, dict) and bool(tiket_ins.get("legs"))
        kaki_ins = []
        if ins_valid:
            for kaki in tiket_ins.get("legs") or []:
                leg_id = str(kaki.get("leg_id") or "")
                kaki_ins.append(
                    {
                        "match_id": leg_id.split(":")[0],
                        "leg_id": leg_id,
                        "line": kaki.get("line"),
                        "price_cents": kaki.get("price_cents"),
                        "p_final": kaki.get("p_final"),
                    }
                )
        harga_ins = [
            k["price_cents"]
            for k in kaki_ins
            if isinstance(k["price_cents"], (int, float))
        ]
        p_ins = [
            k["p_final"] for k in kaki_ins if isinstance(k["p_final"], (int, float))
        ]
        joint_p = math.prod(p_ins) if p_ins and len(p_ins) == len(kaki_ins) else None
        ins_pengali = tiket_ins.get("multiplier") if ins_valid else None
        tanpa_kembar = len({k["match_id"] for k in kaki_ins}) == len(kaki_ins)
        dalam_band = bool(harga_ins) and all(
            BAND_VALID_LINES_CENTS[0] <= h <= BAND_VALID_LINES_CENTS[1]
            for h in harga_ins
        )
        opsi_fallback = hasil_racik.get("insurance_fallback_option")
        if opsi_fallback is None:
            fallback_info: dict = {
                "status": "tidak_dievaluasi",
                "catatan": (
                    "Kunci insurance_fallback_option tidak ada di "
                    "hasil komposer (Worker B belum mendarat / "
                    "antarmuka berbeda) — koordinator menyesuaikan."
                ),
            }
            fallback_terlaporkan = None
        elif not isinstance(opsi_fallback, dict):
            fallback_info = {
                "status": "tidak_dievaluasi",
                "catatan": (
                    "insurance_fallback_option bukan dict: "
                    f"{type(opsi_fallback).__name__}"
                ),
            }
            fallback_terlaporkan = None
        else:
            fb_pengali = opsi_fallback.get("multiplier")
            fallback_terlaporkan = (
                isinstance(fb_pengali, (int, float))
                and FALLBACK_PENGALI_MIN <= fb_pengali <= FALLBACK_PENGALI_MAKS
            )
            fallback_info = {
                "status": (
                    "terlaporkan" if fallback_terlaporkan else "di_luar_rentang"
                ),
                "multiplier": fb_pengali,
                "joint_p_final": opsi_fallback.get("joint_p_final"),
                "alasan": opsi_fallback.get("alasan") or opsi_fallback.get("reason"),
                "legs": opsi_fallback.get("legs"),
            }
        composer = {
            "error": None,
            "insurance_terbentuk": ins_valid,
            "insurance_multiplier": ins_pengali,
            "insurance_legs": kaki_ins,
            "insurance_joint_p_final": joint_p,
            "insurance_tanpa_kembar": tanpa_kembar if ins_valid else None,
            "insurance_semua_dalam_band_80_89c": dalam_band if ins_valid else None,
            "insurance_reason": hasil_racik.get("insurance_reason"),
            "insurance_fallback_option": fallback_info,
            "main_terbentuk": isinstance(hasil_racik.get("main"), dict),
            "main_multiplier": (hasil_racik.get("main") or {}).get("multiplier"),
            "warnings": hasil_racik.get("warnings"),
            "skipped_matches": hasil_racik.get("skipped_matches"),
        }
    except Exception as exc:  # noqa: BLE001 - komposer rusak = kriteria tak terukur
        composer = {
            "error": f"{type(exc).__name__}: {exc}",
            "insurance_terbentuk": None,
            "insurance_multiplier": None,
            "insurance_legs": [],
            "insurance_joint_p_final": None,
            "insurance_tanpa_kembar": None,
            "insurance_semua_dalam_band_80_89c": None,
            "insurance_reason": None,
            "insurance_fallback_option": {
                "status": "tidak_dievaluasi",
                "catatan": "komposer gagal — opsi fallback tidak bisa dinilai",
            },
        }
        ins_valid = False
        ins_pengali = None
        tanpa_kembar = None
        dalam_band = None
        fallback_terlaporkan = None
    kriteria2_lolos = bool(
        ins_valid
        and isinstance(ins_pengali, (int, float))
        and ins_pengali >= TARGET_PENGALI_ASURANSI
        and tanpa_kembar is True
        and dalam_band is True
    )
    kriteria2 = {
        "kriteria": (
            "Pemulihan T2: Asuransi dari valid_lines (80-89c) mencapai "
            "pengali bersih >= 2,00x tanpa melanggar gate/tanpa-kembar"
        ),
        "lolos": kriteria2_lolos,
        "lolos_fallback_terlaporkan": bool(
            not kriteria2_lolos and fallback_terlaporkan is True
        ),
        "komposer_live_7_laga": composer,
        "catatan": (
            "'Tanpa melanggar gate' dinilai dari keluaran komposer: "
            "kaki dalam band 80-89c (band valid_lines Asuransi) + "
            "tanpa kembar + komposer sendiri menegakkan gate "
            "Asuransi. Bila pengali < 2,00x, kriteria ini GAGAL "
            "secara literal; opsi fallback [1,80x, 1,99x] yang "
            "terlaporkan dicatat terpisah (bukan tiket) di "
            "lolos_fallback_terlaporkan."
        ),
    }

    # --- Kriteria 3: peta rim protector 30/30. ---
    try:
        dokumen_peta = _baca_json("config/rim_protector_2026-27.json")
        tim_peta = dokumen_peta.get("teams") or {}
        n_tim = len(tim_peta)
        hilang_slate = sorted(TIM_SLATE_24_NOV - set(tim_peta))
        sorotan = [
            {
                "laga": f"{tandang}@{kandang}",
                "tandang_terpetakan": tandang in tim_peta,
                "kandang_terpetakan": kandang in tim_peta,
            }
            for tandang, kandang in LAGA_SOROTAN_24_NOV
        ]
        tim_fallback = sorted(
            t
            for t, daftar in tim_peta.items()
            if isinstance(daftar, list)
            and any(e.get("tier") == "fallback" for e in daftar if isinstance(e, dict))
        )
        n_entri_fallback = sum(
            1
            for daftar in tim_peta.values()
            if isinstance(daftar, list)
            for e in daftar
            if isinstance(e, dict) and e.get("tier") == "fallback"
        )
        kriteria3_lolos = n_tim == 30 and not hilang_slate
        kriteria3 = {
            "kriteria": (
                "Peta rim protector 30/30; 0 tim buta pada slate 24 Nov "
                "(khususnya OKC@IND, PHX@NOP, LAC@HOU)"
            ),
            "lolos": kriteria3_lolos,
            "n_tim_terpetakan": n_tim,
            "n_tim_target": 30,
            "tim_buta_slate_24_nov": hilang_slate,
            "laga_sorotan": sorotan,
            "tim_fallback": tim_fallback,
            "n_entri_fallback": n_entri_fallback,
            "fetched_at": dokumen_peta.get("fetched_at"),
            "sumber": dokumen_peta.get("source"),
        }
    except (OSError, ValueError) as exc:
        kriteria3 = {
            "kriteria": "Peta rim protector 30/30",
            "lolos": None,
            "status": "tidak_dievaluasi",
            "catatan": f"peta tidak bisa dibaca: {exc}",
        }

    # --- Kriteria 4: kesegaran cedera. ---
    info4 = _ukur_kriteria4(cfg, baris)
    kriteria4 = {
        "kriteria": (
            "Kesegaran cedera: pemain absen jangka panjang (GP == 0) "
            "tidak memicu _sebab_cedera_baru"
        ),
        **info4,
    }

    # --- Kriteria 5: regresi nol. ---
    info5 = _ukur_kriteria5()
    kriteria5 = {
        "kriteria": "Regresi nol: full suite 0 gagal + 0 error",
        **info5,
    }

    kriteria = {
        "kriteria1_skip_awal_baru": kriteria1,
        "kriteria2_pemulihan_t2": kriteria2,
        "kriteria3_peta_rim_protector": kriteria3,
        "kriteria4_kesegaran_cedera": kriteria4,
        "kriteria5_regresi_nol": kriteria5,
    }
    n_lolos = sum(1 for k in kriteria.values() if k.get("lolos") is True)
    n_menunggu = sum(1 for k in kriteria.values() if k.get("lolos") is None)
    # _analysis hanya untuk kebutuhan internal (kriteria 4); jangan
    # ditulis ke JSON output (artefak sudah ada di file asalnya).
    for b in baris:
        b.pop("_analysis", None)
    return {
        "format": "ukur_v18_1",
        "format_version": 1,
        "config_version": cfg["meta"]["version"],
        "artefak_dipakai": [relatif for _label, relatif in ARTEFAK],
        "stake_total_usd": STAKE_TOTAL,
        "catatan_metodologi": (
            "DEN@CHI muncul dua kali (dua snapshot berbeda atas laga "
            "yang sama: live pagi + verif sore — keduanya dilaporkan, "
            "bukan digabung diam-diam). OKC/BOS juga muncul dua kali. "
            "Vonis/skip/equilibrium dihitung dari config + kode SAAT "
            "script dijalankan (hasil berubah bila Worker A/B/D masih "
            "mendaratkan perubahan). Kriteria gagal TETAP dicatat "
            "gagal; kriteria yang antarmukanya belum mendarat dicatat "
            "'tidak_dievaluasi' — script exit 0 dan tidak memalsukan "
            "angka."
        ),
        "ringkasan": {
            "n_baris": len(baris),
            "kriteria_lolos": n_lolos,
            "kriteria_total": 5,
            "kriteria_menunggu_tidak_dievaluasi": n_menunggu,
            "kriteria1": kriteria1["lolos"],
            "kriteria2": kriteria2["lolos"],
            "kriteria3": kriteria3["lolos"],
            "kriteria4": kriteria4["lolos"],
            "kriteria5": kriteria5["lolos"],
        },
        "kriteria": kriteria,
        "baris": baris,
    }


def cetak_tabel(hasil: dict) -> None:
    """Cetak tabel ringkasan ke stdout."""
    print("ACCEPTANCE TEST v18.1 (Gemini §4, slate uji 10 baris)")
    print("=" * 112)
    print(
        f"{'Laga':<24}{'Artk':<6}{'Vonis':<15}{'Veto':<6}"
        f"{'Skip':<6}{'PolaDen':<9}{'EQ-Ins':<9}{'EQ-Utm':<9}{'Final':<7}"
    )
    for b in hasil["baris"]:
        veto = b.get("veto") or {}
        skip = b.get("skip_awal") or {}
        pola = skip.get("pola_denver") or {}
        eq_ins = (b.get("equilibrium") or {}).get("insurance") or {}
        eq_main = (b.get("equilibrium") or {}).get("main") or {}
        print(
            f"{b['match_id']:<24}{b['artefak'][:4]:<6}"
            f"{str(b['vonis']):<15}"
            f"{('YA' if veto.get('menyala') else '-'):>6}"
            f"{('YA' if skip.get('skip') else '-'):>6}"
            f"{('YA' if pola.get('cocok') else ('?' if pola.get('cocok') is None else '-')):>9}"
            f"{(str(eq_ins.get('garis')) if eq_ins.get('ada') else '-'):>9}"
            f"{(str(eq_main.get('garis')) if eq_main.get('ada') else '-'):>9}"
            f"{str(b['final_total']):>7}"
        )
    print("=" * 112)
    for kunci, label in (
        ("kriteria1_skip_awal_baru", "K1 skip_awal baru"),
        ("kriteria2_pemulihan_t2", "K2 Pemulihan T2 (>= 2,00x)"),
        ("kriteria3_peta_rim_protector", "K3 Peta rim protector 30/30"),
        ("kriteria4_kesegaran_cedera", "K4 Kesegaran cedera (GP==0)"),
        ("kriteria5_regresi_nol", "K5 Regresi nol"),
    ):
        kr = hasil["kriteria"][kunci]
        if kr["lolos"] is True:
            status = "LOLOS"
        elif kr["lolos"] is None:
            status = "MENUNGGU/TIDAK DIEVALUASI"
        else:
            status = "GAGAL"
        tambahan = ""
        if kr.get("lolos_fallback_terlaporkan") is True:
            tambahan = " (fallback [1,80x, 1,99x] TERLAPORKAN)"
        print(f"{label:<32} {status}{tambahan}")
    print("=" * 112)
    ringkasan = hasil["ringkasan"]
    print(
        f"Kriteria lolos: {ringkasan['kriteria_lolos']}/"
        f"{ringkasan['kriteria_total']} "
        f"({ringkasan['kriteria_menunggu_tidak_dievaluasi']} menunggu; "
        f"config {hasil['config_version']})."
    )


def main(argv: list[str] | None = None) -> int:
    """Jalankan pengukuran. 0 sukses (termasuk kriteria gagal), 2 input hilang."""
    parser = argparse.ArgumentParser(
        description="Ukur 5 kriteria acceptance test v18.1 di slate uji."
    )
    parser.add_argument(
        "--out",
        default="out/ukur_v18_1.json",
        help="file output JSON (default: out/ukur_v18_1.json)",
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
