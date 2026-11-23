"""Ukur 5 target acceptance test v18 (Gemini §4) di slate uji 10 baris.

    python3 scripts/ukur_v18.py [--out out/ukur_v18.json]

Membaca artefak analisis (22 Nov live 7 laga + verif tahap 4 3 laga),
menjalankan engine/vonis.py (nilai_vonis + evaluasi_veto +
cek_tunggu_lineup), engine/equilibrium.py (cari_equilibrium kedua
tiket), dan engine/ticket_composer.py (compose_tickets) per baris,
lalu menulis JSON + mencetak tabel ringkasan.

TARGET (Gemini REFERENSI-AUDIT-GEMINI-V18.md §4, dengan penyesuaian
keputusan user DECISIONS.md "Jawaban user atas 4 keputusan v18"):
  (1) DEN@CHI (kedua artefak) WAJIB KUNING via veto AND + demerit.
  (2) EQ Asuransi: minimal 2–3 kandidat HIJAU (BOS@GSW, OKC@MIA,
      dan/atau ORL@WAS) membentuk Tiket Asuransi valid tanpa kembar,
      target x2 TETAP.
  (3) False positive: dari 5 laga pemenang tiket nyata (OKC, DAL,
      ORL, IND, BOS — final di bawah garis artefak), yang divonis
      KUNING target 0–1 (dari 4/5 di v17). Definisi v17 (dipertahankan
      agar sebanding): per LAGA, KUNING bila ADA barisnya yang KUNING.
      DET@ATL (final 204, juga menang tapi bukan laga tiket)
      dilaporkan terpisah sebagai konteks, bukan penyebut target.
      Vonis "tunggu_lineup" BUKAN KUNING — tapi juga memblokir
      tiket, jadi dihitung terpisah sebagai "ditahan timing gate".
  (4) IND@NYK: cek_tunggu_lineup pada artefak tersimpan — target
      tunggu=True (KAT/Siakam Questionable di snapshot 22 Nov sore).
      Artefak verif TIDAK memuat IND@NYK (hanya OKC/DEN/BOS) —
      dicatat apa adanya.
  (5) Efisiensi: waktu short-circuit dari pengukuran
      out/ukur_short_circuit.json (bila ada) + catatan arsitektur
      (scan jup.ag slate-level, tidak terpangkas — lihat
      LAPORAN-DEMON-V18.md).

Script ini TIDAK PERNAH memalsukan angka: target yang GAGAL tetap
dicatat gagal dan script tetap exit 0. Exit 2 hanya bila file input
tidak ditemukan. Tanpa fetch live kecuali yang sudah di-cache
worker A (cek_tunggu_lineup menarik USG live HANYA bila ada pemain
Questionable yang belum lolos lewat BPM — gratis + cache
satu-proses; 0 kredit Odds API).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as config_mod
from engine import equilibrium as equilibrium_mod
from engine import ticket_composer as composer_mod
from engine import vonis as vonis_mod

ROOT = Path(__file__).resolve().parent.parent

ARTEFAK = [
    ("live 22 Nov", "out/analysis_live_2026-11-22.json"),
    ("verif tahap 4", "out/analysis_verif_tahap4_2026-11-22.json"),
]

# Total akhir nyata (settled) per laga, dari MEMORY.md / LAPORAN-VONIS.md.
# DEN kalah (296); 5 laga tiket + DET menang (final di bawah garis).
FINAL_TOTAL = {
    "DET@ATL_2026-11-22": 204,
    "OKC@MIA_2026-11-22": 236,
    "ORL@WAS_2026-11-22": 212,
    "DEN@CHI_2026-11-22": 296,
    "DAL@UTA_2026-11-22": 230,
    "IND@NYK_2026-11-22": 219,
    "BOS@GSW_2026-11-22": 175,
}

# 5 laga pemenang TIKET NYATA 23 Nov (penyebut target 3 — definisi v17).
LAGA_PEMENANG_TIKET = [
    "OKC@MIA_2026-11-22",
    "DAL@UTA_2026-11-22",
    "ORL@WAS_2026-11-22",
    "IND@NYK_2026-11-22",
    "BOS@GSW_2026-11-22",
]

# Modal total kedua tiket ($15 + $15 tiket nyata 23 Nov) untuk komposer.
STAKE_TOTAL = 30.0


def _baca_json(relatif: str) -> dict:
    return json.loads((ROOT / relatif).read_text(encoding="utf-8"))


def _vonis_baris(analysis: dict, cfg: dict) -> dict:
    """Vonis + veto + timing gate satu baris (error dicatat, bukan raise)."""
    hasil: dict = {}
    try:
        nilai = vonis_mod.nilai_vonis(analysis, None, cfg)
        ind = nilai.get("indikator") or {}
        hasil["vonis"] = nilai.get("vonis")
        hasil["vonis_error"] = None
        hasil["demerit"] = list(ind.get("demerit") or [])
        hasil["n_demerit"] = ind.get("n_demerit")
        hasil["pemicu_keras"] = ind.get("pemicu_keras")
        hasil["alasan_vonis"] = list(nilai.get("alasan") or [])
        hasil["veto"] = ind.get("veto")
        hasil["rem_alami"] = ind.get("rem_alami")
    except Exception as exc:  # noqa: BLE001 - dicatat per baris
        hasil["vonis"] = None
        hasil["vonis_error"] = f"{type(exc).__name__}: {exc}"
        hasil["demerit"] = None
        hasil["n_demerit"] = None
        hasil["pemicu_keras"] = None
        hasil["alasan_vonis"] = []
        hasil["veto"] = None
        hasil["rem_alami"] = None
    if hasil.get("veto") is None:
        try:
            hasil["veto"] = vonis_mod.evaluasi_veto(analysis, cfg)
            hasil["veto_error"] = None
        except Exception as exc:  # noqa: BLE001 - dicatat per baris
            hasil["veto_error"] = f"{type(exc).__name__}: {exc}"
    fungsi_tunggu = getattr(vonis_mod, "cek_tunggu_lineup", None)
    if not callable(fungsi_tunggu):
        hasil["tunggu_lineup"] = None
        hasil["tunggu_error"] = "cek_tunggu_lineup belum tersedia (worker A)"
    else:
        try:
            tunggu = fungsi_tunggu(analysis, cfg)
            hasil["tunggu_lineup"] = {
                "tunggu": bool(tunggu.get("tunggu")),
                "bintang": [
                    b.get("player") if isinstance(b, dict) else str(b)
                    for b in (tunggu.get("bintang") or [])
                ],
                "dievaluasi": bool(tunggu.get("dievaluasi")),
                "alasan": list(tunggu.get("alasan") or []),
            }
            hasil["tunggu_error"] = None
        except Exception as exc:  # noqa: BLE001 - dicatat per baris
            hasil["tunggu_lineup"] = None
            hasil["tunggu_error"] = f"{type(exc).__name__}: {exc}"
    return hasil


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
                "thin": eq.get("thin"),
                "volume_usd": eq.get("volume_usd"),
                "n_kandidat_lolos": eq.get("n_kandidat_lolos"),
                "n_garis_dinilai": eq.get("n_garis_dinilai"),
                "alasan_tidak_ada": eq.get("alasan_tidak_ada"),
                "alasan_tidak_dihitung": eq.get("alasan_tidak_dihitung"),
                "diagnosis_gate": eq.get("diagnosis_gate"),
            }
        except Exception as exc:  # noqa: BLE001 - dicatat per baris
            hasil[tiket] = {"ada": None, "error": f"{type(exc).__name__}: {exc}"}
    return hasil


def _under_menang(analysis: dict, final: int | None) -> bool | None:
    """Apakah Under MENANG di garis artefak? (final < semua garis kaki).

    None bila final tidak diketahui / tidak ada kaki bergaris.
    """
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


def _ukur_target5() -> dict:
    """Efisiensi short-circuit dari file pengukuran (bila ada)."""
    jalur = ROOT / "out/ukur_short_circuit.json"
    if not jalur.exists():
        return {
            "status": "tidak_diukur",
            "catatan": (
                "out/ukur_short_circuit.json tidak ada — jalankan "
                "pengukuran Tahap 3+5+5b+5c (lihat LAPORAN-DEMON-V18.md "
                "§Short-circuit) sebelum menilai target ini."
            ),
        }
    try:
        data = json.loads(jalur.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"status": "tidak_diukur", "catatan": f"file pengukuran rusak: {exc}"}
    hemat = data.get("hemat_per_laga_kena_veto_detik") or {}
    return {
        "status": "terukur",
        "hemat_per_laga_kena_veto_detik": hemat,
        "tahap3_simulasi_detik": data.get("tahap3_simulasi_detik"),
        "tahap5_kalshi_detik": data.get("tahap5_kalshi_detik"),
        "tahap5b_news_detik": data.get("tahap5b_news_detik"),
        "tahap5c_pemain_3p_detik": data.get("tahap5c_pemain_3p_detik"),
        "wall_clock_build_mock_detik": data.get("wall_clock_build_mock_detik"),
        "metode": data.get("metode"),
        "klaim_gemini_scan_jup": {
            "status": "tidak_berlaku_arsitektur",
            "penjelasan": (
                "Gemini §4 target 5 meminta laga kena veto melompati "
                "pemindaian orderbook jup.ag — TIDAK MUNGKIN di "
                "arsitektur ini: pemindaian jup.ag adalah SLATE-LEVEL "
                "(SlateBuilder.fetch_all, sekali per slate sebelum "
                "analisis per laga), bukan per laga. Short-circuit "
                "per laga hanya memangkas Tahap 3+5+5b+5c (angka di "
                "atas). Pemangkasan scan jup.ag butuh restrukturisasi "
                "slate-level (di luar lingkup v18)."
            ),
        },
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
                    "equilibrium": info_eq,
                }
            )
            if label_artefak.startswith("live"):
                live_analyses.append(analysis)

    # --- Target 1: DEN@CHI kedua artefak KUNING via veto AND. ---
    den_baris = [b for b in baris if b["match_id"] == "DEN@CHI_2026-11-22"]
    den_detail = []
    for b in den_baris:
        veto = b.get("veto") or {}
        den_detail.append(
            {
                "artefak": b["artefak"],
                "vonis": b["vonis"],
                "pemicu_keras": b["pemicu_keras"],
                "demerit": b["demerit"],
                "veto_menyala": veto.get("menyala"),
                "veto_dievaluasi": veto.get("dievaluasi"),
                "veto_logic": veto.get("logic"),
                "kondisi_menyala": veto.get("kondisi_menyala"),
                "peringatan_parsial": veto.get("peringatan_parsial"),
                "tunggu_lineup": (b.get("tunggu_lineup") or {}).get("tunggu"),
                "vonis_error": b.get("vonis_error"),
            }
        )
    target1_lolos = bool(den_baris) and all(
        b["vonis"] == "kuning"
        and b["pemicu_keras"] == "veto_rim_protector"
        and isinstance(b.get("veto"), dict)
        and b["veto"].get("menyala") is True
        for b in den_baris
    )
    den_diblokir = bool(den_baris) and all(
        b["vonis"] in ("kuning", "tunggu_lineup") for b in den_baris
    )
    target1 = {
        "target": ("DEN@CHI kedua artefak WAJIB KUNING via veto AND + demerit"),
        "lolos": target1_lolos,
        # KEPUTUSAN KOORDINATOR v18: tunggu_lineup DIHITUNG sebagai
        # "terblokir" untuk maksud target ini — DEN tidak masuk
        # tiket mana pun di kedua baris. Kriteria literal (semua
        # KUNING) tetap dicatat di "lolos" agar tidak ada angka
        # yang disembunyikan.
        "lolos_fungsional": den_diblokir,
        "n_baris_den": len(den_baris),
        "detail": den_detail,
        "catatan": (
            "Kedua baris terblokir dari tiket (KUNING atau " "tunggu_lineup)."
            if den_diblokir
            else "Ada baris DEN yang TIDAK terblokir — periksa detail."
        ),
    }
    if not target1_lolos and den_diblokir:
        target1["catatan"] += (
            " Target LITERAL gagal (bukan semua KUNING) tapi secara "
            "fungsional AMAN: baris live ditahan timing gate "
            "(Questionable bintang — snapshot pagi sebelum kabar "
            "Claxton OUT), baris verif KUNING via veto."
        )

    # --- Target 2: EQ Asuransi 2-3 kandidat HIJAU -> tiket valid. ---
    hijau_eq = [
        b
        for b in baris
        if b["vonis"] == "hijau"
        and isinstance(b.get("equilibrium", {}).get("insurance"), dict)
        and b["equilibrium"]["insurance"].get("ada") is True
    ]
    hijau_semua = [b for b in baris if b["vonis"] == "hijau"]
    try:
        hasil_racik = composer_mod.compose_tickets(
            live_analyses, None, cfg, stake_total=STAKE_TOTAL
        )
        tiket_ins = hasil_racik.get("insurance")
        ins_valid = isinstance(tiket_ins, dict) and bool(tiket_ins.get("legs"))
        ins_pengali = tiket_ins.get("multiplier") if ins_valid else None
        ins_match = []
        if ins_valid:
            for kaki in tiket_ins.get("legs") or []:
                leg_id = str(kaki.get("leg_id") or "")
                ins_match.append(leg_id.split(":")[0])
        composer = {
            "error": None,
            "insurance_terbentuk": ins_valid,
            "insurance_multiplier": ins_pengali,
            "insurance_legs": ins_match,
            "insurance_tanpa_kembar": len(ins_match) == len(set(ins_match)),
            "insurance_reason": hasil_racik.get("insurance_reason"),
            "main_terbentuk": isinstance(hasil_racik.get("main"), dict),
            "main_multiplier": (hasil_racik.get("main") or {}).get("multiplier"),
            "warnings": hasil_racik.get("warnings"),
            "skipped_matches": hasil_racik.get("skipped_matches"),
        }
    except Exception as exc:  # noqa: BLE001 - komposer rusak = target tak terukur
        composer = {
            "error": f"{type(exc).__name__}: {exc}",
            "insurance_terbentuk": None,
            "insurance_multiplier": None,
            "insurance_legs": [],
            "insurance_tanpa_kembar": None,
            "insurance_reason": None,
        }
    target2_lolos = (
        len({b["match_id"] for b in hijau_eq}) >= 2
        and composer.get("insurance_terbentuk") is True
        and composer.get("insurance_tanpa_kembar") is True
        and isinstance(composer.get("insurance_multiplier"), (int, float))
        and composer["insurance_multiplier"] >= 2.0
    )
    target2 = {
        "target": (
            "EQ Asuransi: minimal 2-3 kandidat HIJAU membentuk Tiket "
            "Asuransi valid tanpa kembar (target x2 TETAP)"
        ),
        "lolos": target2_lolos,
        "n_baris_hijau": len(hijau_semua),
        "match_hijau": sorted({b["match_id"] for b in hijau_semua}),
        "n_kandidat_hijau_dengan_eq_asuransi": len(hijau_eq),
        "kandidat": [
            {
                "match_id": b["match_id"],
                "artefak": b["artefak"],
                "garis_eq_asuransi": b["equilibrium"]["insurance"].get("garis"),
                "harga_venue_cents": b["equilibrium"]["insurance"].get(
                    "harga_venue_cents"
                ),
                "p_final": b["equilibrium"]["insurance"].get("p_final"),
                "ev_pct": b["equilibrium"]["insurance"].get("ev_pct"),
                "edge": b["equilibrium"]["insurance"].get("edge"),
            }
            for b in hijau_eq
        ],
        "komposer_live_7_laga": composer,
        "catatan": (
            "Komposer dijalankan atas 7 laga live (satu baris per "
            f"laga; stake_total ${STAKE_TOTAL:g} = tiket nyata 23 Nov). "
            "Baris verif adalah analisis ulang laga yang sama, bukan "
            "laga tambahan — tidak ikut diracik."
        ),
    }

    # --- Target 3: false positive 0-1 dari 4/5 (v17). ---
    fp_detail = []
    n_kuning = 0
    n_ditahan = 0
    for laga in LAGA_PEMENANG_TIKET:
        baris_laga = [b for b in baris if b["match_id"] == laga]
        vonis_laga = [b["vonis"] for b in baris_laga]
        kuning = "kuning" in vonis_laga
        ditahan = "tunggu_lineup" in vonis_laga
        if kuning:
            n_kuning += 1
        if ditahan:
            n_ditahan += 1
        fp_detail.append(
            {
                "match_id": laga,
                "final_total": FINAL_TOTAL[laga],
                "vonis_per_baris": [
                    {"artefak": b["artefak"], "vonis": b["vonis"]} for b in baris_laga
                ],
                "kuning_di_salah_satu_baris": kuning,
                "ditahan_timing_gate": ditahan,
            }
        )
    det_baris = [b for b in baris if b["match_id"] == "DET@ATL_2026-11-22"]
    target3 = {
        "target": (
            "False positive: laga pemenang yang divonis KUNING "
            "turun dari 4/5 (v17) menjadi 0-1"
        ),
        "lolos": n_kuning <= 1,
        "n_kuning_dari_5": n_kuning,
        "n_ditahan_timing_gate_dari_5": n_ditahan,
        "detail_5_laga_pemenang": fp_detail,
        "det_atl_konteks": {
            "final_total": FINAL_TOTAL["DET@ATL_2026-11-22"],
            "vonis_per_baris": [
                {"artefak": b["artefak"], "vonis": b["vonis"]} for b in det_baris
            ],
            "catatan": (
                "DET juga menang (final 204) tapi BUKAN laga tiket "
                "nyata — di luar penyebut 5 target ini (definisi v17)."
            ),
        },
        "catatan": (
            "Definisi v17 dipertahankan: per laga, KUNING bila ADA "
            "barisnya KUNING. Vonis tunggu_lineup dihitung terpisah "
            "(bukan KUNING, tapi juga memblokir tiket)."
        ),
    }

    # --- Target 4: IND@NYK tunggu_lineup. ---
    ind_baris = [b for b in baris if b["match_id"] == "IND@NYK_2026-11-22"]
    ind_detail = []
    for b in ind_baris:
        tunggu = b.get("tunggu_lineup") or {}
        ind_detail.append(
            {
                "artefak": b["artefak"],
                "vonis": b["vonis"],
                "tunggu": tunggu.get("tunggu"),
                "bintang": tunggu.get("bintang"),
                "dievaluasi": tunggu.get("dievaluasi"),
                "tunggu_error": b.get("tunggu_error"),
            }
        )
    target4_lolos = bool(ind_baris) and all(
        (b.get("tunggu_lineup") or {}).get("tunggu") is True for b in ind_baris
    )
    target4 = {
        "target": "IND@NYK masuk status TUNGGU_LINEUP (bintang Questionable)",
        "lolos": target4_lolos,
        "n_baris_ind": len(ind_baris),
        "detail": ind_detail,
        "catatan": (
            "Artefak verif tidak memuat IND@NYK (hanya OKC/DEN/BOS) — "
            "hanya baris live yang dinilai."
        ),
    }

    # --- Target 5: efisiensi. ---
    info5 = _ukur_target5()
    target5 = {
        "target": (
            "Efisiensi: laga kena veto melompati pemindaian jup.ag "
            "sehingga waktu analisis slate turun signifikan"
        ),
        "lolos": False,
        # KEPUTUSAN KOORDINATOR v18: target literal Gemini
        # dirumuskan ulang — yang terukur adalah penghematan
        # Tahap 3+5+5b+5c per laga kena veto (scan jup.ag adalah
        # slate-level, tidak bisa dipangkas per laga). Kriteria
        # literal tetap dicatat di "lolos" (False).
        "lolos_reformulasi": info5.get("status") == "terukur",
        "pengukuran": info5,
        "catatan": (
            "Target LITERAL Gemini tidak lolos karena tidak berlaku "
            "di arsitektur ini (scan jup.ag slate-level — lihat "
            "klaim_gemini_scan_jup). Yang terukur adalah penghematan "
            "Tahap 3+5+5b+5c per laga kena veto (angka di atas)."
        ),
    }
    if info5.get("status") == "terukur":
        target5["lolos_literal_gemini"] = False
        target5["penghematan_terukur"] = True

    target = {
        "target1_den_kuning_veto": target1,
        "target2_eq_asuransi": target2,
        "target3_false_positive": target3,
        "target4_tunggu_lineup": target4,
        "target5_efisiensi": target5,
    }
    n_lolos = sum(1 for t in target.values() if t.get("lolos") is True)
    return {
        "format": "ukur_v18",
        "format_version": 1,
        "config_version": cfg["meta"]["version"],
        "artefak_dipakai": [relatif for _label, relatif in ARTEFAK],
        "stake_total_usd": STAKE_TOTAL,
        "catatan_metodologi": (
            "DEN@CHI muncul dua kali (dua snapshot berbeda atas laga "
            "yang sama: live pagi + verif sore — keduanya dilaporkan, "
            "bukan digabung diam-diam). OKC/BOS juga muncul dua kali. "
            "Vonis dihitung dari config + kode SAAT script dijalankan "
            "(hasil berubah bila worker A/B masih mendaratkan "
            "perubahan). Target gagal TETAP dicatat gagal — script "
            "exit 0 dan tidak memalsukan angka."
        ),
        "ringkasan": {
            "n_baris": len(baris),
            "target_lolos": n_lolos,
            "target_total": 5,
            "target1": target1["lolos"],
            "target2": target2["lolos"],
            "target3": target3["lolos"],
            "target4": target4["lolos"],
            "target5": target5["lolos"],
        },
        "target": target,
        "baris": baris,
    }


def cetak_tabel(hasil: dict) -> None:
    """Cetak tabel ringkasan ke stdout."""
    print("ACCEPTANCE TEST v18 (Gemini §4, slate uji 10 baris)")
    print("=" * 110)
    print(
        f"{'Laga':<24}{'Artk':<6}{'Vonis':<15}{'Veto':<6}"
        f"{'EQ-Ins':<9}{'EQ-Utm':<9}{'Tunggu':<8}{'Final':<7}{'Under':<6}"
    )
    for b in hasil["baris"]:
        veto = b.get("veto") or {}
        eq_ins = (b.get("equilibrium") or {}).get("insurance") or {}
        eq_main = (b.get("equilibrium") or {}).get("main") or {}
        tunggu = (b.get("tunggu_lineup") or {}).get("tunggu")
        print(
            f"{b['match_id']:<24}{b['artefak'][:4]:<6}"
            f"{str(b['vonis']):<15}"
            f"{('YA' if veto.get('menyala') else '-'):>6}"
            f"{(str(eq_ins.get('garis')) if eq_ins.get('ada') else '-'):>9}"
            f"{(str(eq_main.get('garis')) if eq_main.get('ada') else '-'):>9}"
            f"{('YA' if tunggu else '-'):>8}"
            f"{str(b['final_total']):>7}"
            f"{('MENANG' if b['under_menang_di_garis_artefak'] else '-'):>6}"
        )
    print("=" * 110)
    for kunci, label in (
        ("target1_den_kuning_veto", "T1 DEN KUNING via veto"),
        ("target2_eq_asuransi", "T2 EQ Asuransi 2-3 HIJAU"),
        ("target3_false_positive", "T3 False positive 0-1"),
        ("target4_tunggu_lineup", "T4 IND TUNGGU_LINEUP"),
        ("target5_efisiensi", "T5 Efisiensi short-circuit"),
    ):
        target = hasil["target"][kunci]
        status = "LOLOS" if target["lolos"] else "GAGAL"
        tambahan = ""
        if target.get("lolos_fungsional") is True and not target["lolos"]:
            tambahan = " (fungsional: LOLOS — kedua baris terblokir)"
        if target.get("lolos_reformulasi") is True and not target["lolos"]:
            tambahan = " (reformulasi: LOLOS — penghematan terukur)"
        print(f"{label:<32} {status}{tambahan}")
    print("=" * 110)
    ringkasan = hasil["ringkasan"]
    print(
        f"Target lolos: {ringkasan['target_lolos']}/{ringkasan['target_total']} "
        f"(literal; config {hasil['config_version']})."
    )


def main(argv: list[str] | None = None) -> int:
    """Jalankan pengukuran. 0 sukses (termasuk target gagal), 2 input hilang."""
    parser = argparse.ArgumentParser(
        description="Ukur 5 target acceptance test v18 di slate uji."
    )
    parser.add_argument(
        "--out",
        default="out/ukur_v18.json",
        help="file output JSON (default: out/ukur_v18.json)",
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
