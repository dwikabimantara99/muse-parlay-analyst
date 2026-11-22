"""Rekomendasi bobot blend w dari kalibrasi Brier (Blueprint §9).

p_final = w * p_model + (1 - w) * p_market, dengan w dari
playstyle.yaml -> blend.w_model (nilai awal 0,3; engine/devig.py::blend).
Keputusan user 2026-11-21: w diatur DATA lewat kalibrasi Brier tiap
50 kaki; kenaikan w HANYA dengan persetujuan user.

PRINSIP KEAMANAN: modul ini hanya MENGHITUNG rekomendasi. Ia TIDAK
PERNAH menerapkan perubahan — tidak menulis config/playstyle.yaml,
tidak mengubah ambang apa pun, tidak menyentuh file. Setiap hasil
keluar dengan "diterapkan": False dan "butuh_persetujuan_user": True.

Cara kerja ``rekomendasi_w``: atas kaki settled yang punya p_model DAN
p_market (keduanya), grid search w = 0,00-1,00 langkah 0,05; untuk
tiap w hitung Brier dari blend w*p_model + (1-w)*p_market; pilih w
dengan Brier terkecil. Brier dihitung ulang dari engine/validation.py
(brier_score) — bukan dari p_final yang tersimpan, supaya rekomendasi
tidak bergantung pada w lama.

Syarat cukup data: n >= calibration.min_legs_w (playstyle.yaml §9,
default 50, sama dengan report_every_legs). Di bawah ambang itu,
w_rekomendasi None — mesin tidak mengusulkan apa-apa dari sampel kecil.

Tie-break grid search: bila beberapa w berbagi Brier terkecil, yang
dipilih w TERKECIL (pemindaian 0,00 -> 1,00, minimum pertama menang).
Ini deterministik dan didokumentasikan di sini; bukan pilihan strategi.

Kaki yang dipakai: settled True, result True/False (bukan None), dan
p_model + p_market keduanya ada. Kaki tanpa p_market (MODEL_ONLY, D2)
diabaikan — tanpa pembanding pasar, w tidak bisa dikalibrasi dari kaki
itu. Kaki belum settled / result None juga diabaikan.
"""

from __future__ import annotations

import config
from engine.validation import brier_score

# Grid w untuk pencarian: 0,00-1,00 langkah 0,05 (21 titik). Parameter
# komputasi dari brief Langkah 6, bukan ambang strategi — jadi konstanta
# modul, bukan angka di playstyle.yaml.
_GRID_W = [round(i * 0.05, 2) for i in range(21)]


def _kaki_terpakai(outcomes) -> list[tuple[float, float, bool]]:
    """Saring kaki yang bisa dipakai kalibrasi w.

    Syarat: dict, settled True, result True/False (bukan None), p_model
    dan p_market keduanya ada. Mengembalikan daftar
    (p_model, p_market, result). Validasi nilai peluang (0-1) dilakukan
    brier_score saat dipakai — di sini hanya penyaringan.
    """
    terpakai: list[tuple[float, float, bool]] = []
    for kaki in outcomes or []:
        if not isinstance(kaki, dict):
            continue
        if not kaki.get("settled"):
            continue
        result = kaki.get("result")
        if result is None:
            continue
        p_model = kaki.get("p_model")
        p_market = kaki.get("p_market")
        if p_model is None or p_market is None:
            continue
        terpakai.append((p_model, p_market, result))
    return terpakai


def rekomendasi_w(outcomes, cfg: dict | None = None) -> dict:
    """Rekomendasikan w optimal dari Brier blend atas kaki settled.

    outcomes: daftar dict record hasil (bentuk dari engine/learning.py
    pekerja A: leg_id, ticket_id, sport, market, selection, p_model,
    p_market, p_final, price_buy_cents, price_close_cents, ev_pct,
    result, settled, sumber). Hanya settled, result, p_model, p_market
    yang dibaca di sini.
    cfg: dict playstyle (None = baca config/playstyle.yaml, hanya baca).

    Mengembalikan dict:
      w_saat_ini, w_rekomendasi (None bila data tidak cukup),
      brier_model, brier_market, brier_blend_w_saat_ini,
      brier_blend_w_rekomendasi (None bila data tidak cukup / n=0),
      n, cukup_data (bool), alasan, diterapkan (selalu False),
      butuh_persetujuan_user (selalu True).
    Bila n = 0, semua Brier None (tidak ada yang bisa dihitung).
    Fungsi ini tidak menulis apa pun ke mana pun.
    """
    cfg = cfg if cfg is not None else config.load_playstyle()
    w_saat_ini = config.get_value(cfg, "blend", "w_model")
    min_legs = config.get_value(cfg, "calibration", "min_legs_w")
    terpakai = _kaki_terpakai(outcomes)
    n = len(terpakai)
    hasil = {
        "w_saat_ini": w_saat_ini,
        "w_rekomendasi": None,
        "brier_model": None,
        "brier_market": None,
        "brier_blend_w_saat_ini": None,
        "brier_blend_w_rekomendasi": None,
        "n": n,
        "cukup_data": False,
        "alasan": f"sampel belum cukup (n={n}, butuh >={min_legs})",
        "diterapkan": False,
        "butuh_persetujuan_user": True,
    }
    if n == 0:
        return hasil
    pairs_model = [(p_model, result) for p_model, _, result in terpakai]
    pairs_market = [(p_market, result) for _, p_market, result in terpakai]
    hasil["brier_model"] = brier_score(pairs_model)
    hasil["brier_market"] = brier_score(pairs_market)

    def _brier_blend(w: float) -> float:
        return brier_score(
            [
                (w * p_model + (1.0 - w) * p_market, result)
                for p_model, p_market, result in terpakai
            ]
        )

    hasil["brier_blend_w_saat_ini"] = _brier_blend(w_saat_ini)
    if n < min_legs:
        return hasil
    w_terbaik = _GRID_W[0]
    brier_terbaik = _brier_blend(w_terbaik)
    for w in _GRID_W[1:]:
        brier_w = _brier_blend(w)
        if brier_w < brier_terbaik:
            w_terbaik, brier_terbaik = w, brier_w
    hasil["cukup_data"] = True
    hasil["w_rekomendasi"] = w_terbaik
    hasil["brier_blend_w_rekomendasi"] = brier_terbaik
    if w_terbaik == w_saat_ini:
        hasil["alasan"] = (
            "tidak ada perubahan yang diusulkan "
            f"(w optimal {w_terbaik} sama dengan w saat ini; "
            f"Brier blend {brier_terbaik:.4f}, n={n})"
        )
    else:
        hasil["alasan"] = (
            f"w optimal {w_terbaik} (Brier {brier_terbaik:.4f}) vs "
            f"w saat ini {w_saat_ini} "
            f"(Brier {hasil['brier_blend_w_saat_ini']:.4f}); n={n}"
        )
    return hasil
