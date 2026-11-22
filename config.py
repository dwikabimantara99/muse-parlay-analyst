"""Loader config muse-parlay-analyst.

Satu-satunya cara kode membaca ambang & default strategi: dari
``config/playstyle.yaml`` (Blueprint §6, §7) dan daftar sumber dari
``config/sources.yaml`` (Blueprint §4).

Aturan kerja 4: semua ambang & default strategi hanya ada di playstyle.yaml.
Kode TIDAK BOLEH menulis angka ambang sendiri — baca dari sini.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_PLAYSTYLE_PATH = REPO_ROOT / "config" / "playstyle.yaml"
DEFAULT_SOURCES_PATH = REPO_ROOT / "config" / "sources.yaml"

# Bagian wajib di playstyle.yaml (Tahap 1). Kalau ada yang hilang, config
# dianggap rusak dan analisis tidak boleh jalan.
REQUIRED_PLAYSTYLE_SECTIONS = (
    "meta",
    "tickets",
    "optimizer",
    "combo",
    "blend",
    "comparison",
    "price_labels",
    "model_only",
    "no_xg",
    "anomaly",
    "market_line_check",
    "polymarket_ladder",
    "filters",
    "formulas",
    "currency",
    "simulation",
    "fees",
    "data",
    "recheck",
    "live",
    "calibration",
)

REQUIRED_SOURCES_KEYS = ("meta", "sources", "rules")


class ConfigError(Exception):
    """Config hilang, tidak bisa di-parse, atau tidak lengkap."""


def load_yaml(path: str | Path) -> dict:
    """Baca satu file YAML menjadi dict. Raise ConfigError bila gagal."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"file config tidak ditemukan: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"file config tidak valid: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"file config harus berisi mapping: {path}")
    return data


def load_playstyle(path: str | Path | None = None) -> dict:
    """Baca + validasi playstyle.yaml. Raise ConfigError bila tidak lengkap."""
    cfg = load_yaml(path or DEFAULT_PLAYSTYLE_PATH)
    missing = [s for s in REQUIRED_PLAYSTYLE_SECTIONS if s not in cfg]
    if missing:
        raise ConfigError(f"playstyle.yaml kehilangan bagian: {', '.join(missing)}")
    return cfg


def load_sources(path: str | Path | None = None) -> dict:
    """Baca + validasi sources.yaml. Raise ConfigError bila tidak lengkap."""
    cfg = load_yaml(path or DEFAULT_SOURCES_PATH)
    missing = [k for k in REQUIRED_SOURCES_KEYS if k not in cfg]
    if missing:
        raise ConfigError(f"sources.yaml kehilangan bagian: {', '.join(missing)}")
    return cfg


def get_value(cfg: dict, *keys: str):
    """Ambil nilai bersarang, misal get_value(cfg, 'tickets', 'insurance',
    'multiplier_min'). Raise ConfigError bila kunci tidak ada — jangan
    diam-diam memakai default dari kode."""
    node: object = cfg
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            raise ConfigError("kunci config tidak ditemukan: " + ".".join(keys))
        node = node[key]
    return node
