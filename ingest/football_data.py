"""Loader CSV hasil liga sepak bola dari football-data.co.uk.

Sumber disetujui user (DECISIONS.md 2026-11-20): unduhan satu kali
per file musim, disimpan lokal di data/ (gitignored), TIDAK di-commit.
Loader ini HANYA membaca file lokal — tidak ada unduhan otomatis,
agar syarat "satu kali unduh per file" tidak dilanggar diam-diam.

HANYA kolom HASIL yang dipakai (Date, HomeTeam, AwayTeam, FTHG,
FTAG). Kolom odds Pinnacle TIDAK dibaca: situs memperingatkan odds
Pinnacle "systematically out of date" sejak 23/07/2025, jadi tidak
boleh dipakai untuk keputusan fit/validasi.

Format tanggal football-data.co.uk: DD/MM/YYYY (musim 2022/23 ke
atas); parser juga menerima DD/MM/YY secara defensif. File memakai
BOM UTF-8 — dibuka dengan encoding utf-8-sig.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

# Kode file football-data.co.uk per liga.
KODE_LIGA = {
    "EPL": "E0",
    "LaLiga": "SP1",
}

# Label musim "2223" -> "2022/23" (untuk laporan).
LABEL_MUSIM = {
    "2223": "2022/23",
    "2324": "2023/24",
    "2425": "2024/25",
    "2526": "2025/26",
    "2627": "2026/27",
}


def label_musim(musim: str) -> str:
    """Ubah kode musim "2223" -> label "2022/23" (atau apa adanya)."""
    return LABEL_MUSIM.get(musim, musim)


def parse_tanggal_fd(teks: str) -> date | None:
    """Parse tanggal football-data.co.uk DD/MM/YYYY (atau DD/MM/YY).

    Mengembalikan date, atau None bila tidak bisa di-parse.
    """
    if not isinstance(teks, str):
        return None
    teks = teks.strip()
    if not teks:
        return None
    bagian = teks.split("/")
    if len(bagian) != 3:
        return None
    try:
        hari = int(bagian[0])
        bulan = int(bagian[1])
        tahun = int(bagian[2])
    except ValueError:
        return None
    if tahun < 100:  # format DD/MM/YY -> 20YY
        tahun += 2000
    try:
        return date(tahun, bulan, hari)
    except ValueError:
        return None


def _skor(nilai) -> int | None:
    """Parse satu kolom skor (FTHG/FTAG); None bila kosong/bukan angka."""
    if nilai is None:
        return None
    teks = str(nilai).strip()
    if teks == "":
        return None
    try:
        skor = int(teks)
    except ValueError:
        return None
    return skor if skor >= 0 else None


def muat_csv_hasil(path: str | Path, liga: str, musim: str) -> tuple[list[dict], dict]:
    """Muat satu file CSV hasil jadi daftar laga.

    path: file CSV football-data.co.uk. liga: nama liga ("EPL",
    "LaLiga"). musim: kode musim ("2223", ...).
    Mengembalikan (laga, info). Tiap laga: {"date" (YYYY-MM-DD),
    "season" (kode, mis. "2223"), "season_label" ("2022/23"),
    "league", "home_team", "away_team", "home_goals", "away_goals"}.
    Baris tanpa skor valid (laga belum dimainkan / baris rusak)
    dilewati + dihitung di info (bukan dikarang).
    Raise FileNotFoundError bila file tidak ada, ValueError bila
    kolom wajib tidak ada.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"file CSV hasil tidak ditemukan: {path}")
    laga: list[dict] = []
    info = {
        "file": str(path),
        "league": liga,
        "season": musim,
        "season_label": label_musim(musim),
        "n_baris": 0,
        "n_laga": 0,
        "n_tanpa_skor": 0,
        "n_tanpa_tanggal": 0,
        "tanggal_awal": None,
        "tanggal_akhir": None,
    }
    with path.open(encoding="utf-8-sig", newline="") as fh:
        pembaca = csv.DictReader(fh)
        kolom = pembaca.fieldnames or []
        for wajib in ("Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"):
            if wajib not in kolom:
                raise ValueError(f"kolom {wajib} tidak ada di {path}")
        for baris in pembaca:
            info["n_baris"] += 1
            tanggal = parse_tanggal_fd(baris.get("Date") or "")
            gol_kandang = _skor(baris.get("FTHG"))
            gol_tandang = _skor(baris.get("FTAG"))
            tim_kandang = (baris.get("HomeTeam") or "").strip()
            tim_tandang = (baris.get("AwayTeam") or "").strip()
            if gol_kandang is None or gol_tandang is None:
                info["n_tanpa_skor"] += 1
                continue
            if tanggal is None or not tim_kandang or not tim_tandang:
                info["n_tanpa_tanggal"] += 1
                continue
            laga.append(
                {
                    "date": tanggal.isoformat(),
                    "season": musim,
                    "season_label": label_musim(musim),
                    "league": liga,
                    "home_team": tim_kandang,
                    "away_team": tim_tandang,
                    "home_goals": gol_kandang,
                    "away_goals": gol_tandang,
                }
            )
    info["n_laga"] = len(laga)
    if laga:
        tanggal_list = sorted(m["date"] for m in laga)
        info["tanggal_awal"] = tanggal_list[0]
        info["tanggal_akhir"] = tanggal_list[-1]
    return laga, info


def muat_musim(
    data_dir: str | Path, liga: str, musim_list: list[str]
) -> tuple[list[dict], list[dict]]:
    """Muat beberapa file musim satu liga (data/{KODE}_{musim}.csv).

    Mengembalikan (semua_laga, info_per_file). Raise ValueError bila
    liga tidak dikenal; FileNotFoundError diteruskan dari muat_csv_hasil.
    """
    kode = KODE_LIGA.get(liga)
    if kode is None:
        raise ValueError(f"liga tidak dikenal: {liga!r} (pilih: {sorted(KODE_LIGA)})")
    data_dir = Path(data_dir)
    semua: list[dict] = []
    info_semua: list[dict] = []
    for musim in musim_list:
        path = data_dir / f"{kode}_{musim}.csv"
        laga, info = muat_csv_hasil(path, liga, musim)
        semua.extend(laga)
        info_semua.append(info)
    return semua, info_semua
