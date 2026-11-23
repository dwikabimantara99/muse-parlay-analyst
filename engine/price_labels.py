"""Label harga kaki dari EV (keputusan user 2026-11-21, berlaku Tahap 3).

DISKON / WAJAR / MAHAL — dari EV terhadap harga ¢ jup.ag. Ambang dibaca
dari playstyle.yaml -> price_labels; modul ini tidak menulis angka ambang
sendiri (aturan kerja 4).

SHARP MOVE BUKAN DISKON (keputusan user 2026-11-23 09:47 WIB, kasus
Thunder): pergerakan harga tajam (>= anomaly.sharp_move_cents, 3¢)
menjelang tip-off adalah PERINGATAN (pasar kemungkinan tahu sesuatu),
bukan peluang diskon. Karena itu label_for_ev menerima parameter
``sharp_move``: bila True dan EV-nya akan berlabel DISKON, yang
dikembalikan adalah DISKON_DITEKAN — DISKON polos DILARANG dalam
kondisi ini sampai pergerakannya dijelaskan ("Kenapa beda?"). WAJAR
dan MAHAL tidak berubah oleh sharp move (penekanan hanya menahan
klaim diskon, bukan mengubah definisi EV atau ambang label).
"""

from __future__ import annotations

import math

import config

DISKON = "DISKON"
WAJAR = "WAJAR"
MAHAL = "MAHAL"
# DISKON yang ditekan karena harga baru bergerak tajam (sharp move):
# EV-nya memenuhi ambang DISKON, tapi label DISKON polos dilarang
# sampai pergerakannya dijelaskan ("Kenapa beda?").
DISKON_DITEKAN = "DISKON_DITEKAN"


def label_for_ev(
    ev_pct: float, cfg: dict | None = None, sharp_move: bool = False
) -> str:
    """Label harga dari EV dalam persen (2.0 berarti +2%).

    DISKON bila EV >= diskon_min_ev_pct; MAHAL bila EV < mahal_max_ev_pct;
    WAJAR di antaranya. Ambang dari config (cfg opsional, untuk tes).
    Melempar ValueError bila EV bukan angka hingga, ConfigError bila
    ambang config terbalik (diskon <= mahal).

    sharp_move: True bila harga kaki ini baru bergerak tajam (>= ambang
    anomaly.sharp_move_cents) menjelang tip-off — dalam kondisi itu
    DISKON polos dilarang: EV yang akan berlabel DISKON dikembalikan
    sebagai DISKON_DITEKAN. WAJAR/MAHAL tidak berubah. Default False
    sehingga pemanggil lama tanpa parameter tidak berubah perilakunya.
    """
    if (
        isinstance(ev_pct, bool)
        or not isinstance(ev_pct, (int, float))
        or not math.isfinite(ev_pct)
    ):
        raise ValueError(f"EV tidak valid: {ev_pct!r} (harus angka hingga)")
    cfg = cfg if cfg is not None else config.load_playstyle()
    diskon_min = config.get_value(cfg, "price_labels", "diskon_min_ev_pct")
    mahal_max = config.get_value(cfg, "price_labels", "mahal_max_ev_pct")
    if not diskon_min > mahal_max:
        raise config.ConfigError(
            "price_labels rusak: diskon_min_ev_pct harus > mahal_max_ev_pct"
        )
    if ev_pct >= diskon_min:
        # Sharp move BUKAN diskon: harga yang baru bergerak tajam tidak
        # boleh berlabel DISKON polos sampai pergerakannya dijelaskan.
        return DISKON_DITEKAN if sharp_move else DISKON
    if ev_pct < mahal_max:
        return MAHAL
    return WAJAR
