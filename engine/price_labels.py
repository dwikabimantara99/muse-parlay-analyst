"""Label harga kaki dari EV (keputusan user 2026-11-21, berlaku Tahap 3).

DISKON / WAJAR / MAHAL — dari EV terhadap harga ¢ jup.ag. Ambang dibaca
dari playstyle.yaml -> price_labels; modul ini tidak menulis angka ambang
sendiri (aturan kerja 4).
"""

from __future__ import annotations

import math

import config

DISKON = "DISKON"
WAJAR = "WAJAR"
MAHAL = "MAHAL"


def label_for_ev(ev_pct: float, cfg: dict | None = None) -> str:
    """Label harga dari EV dalam persen (2.0 berarti +2%).

    DISKON bila EV >= diskon_min_ev_pct; MAHAL bila EV < mahal_max_ev_pct;
    WAJAR di antaranya. Ambang dari config (cfg opsional, untuk tes).
    Melempar ValueError bila EV bukan angka hingga, ConfigError bila
    ambang config terbalik (diskon <= mahal).
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
        return DISKON
    if ev_pct < mahal_max:
        return MAHAL
    return WAJAR
