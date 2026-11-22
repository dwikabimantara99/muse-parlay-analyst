"""Status live tiket NBA + proyeksi total akhir (Tahap 3 Langkah 4).

Fungsi utama: ``evaluate_ticket(tiket, live_games, pregame_medians, cfg)``
lalu ``render_live_status(hasil)`` untuk teks Bahasa Indonesia sehari-hari.

Masukan:
- ``tiket``: dict tiket (``schemas/ticket.schema.json``) dari peracik
  (``engine/ticket_composer.py``). Kaki tiket TIDAK punya kunci ``line`` —
  garis diurai dari ``selection`` ("Under 237.5 (DET@ATL)").
- ``live_games_by_match``: dict match_id -> LiveGame (kontrak pekerja A:
  ``match_id``, ``espn_game_id``, ``home_abbr``, ``away_abbr``,
  ``home_team``, ``away_team``, ``status`` ("belum_mulai"|"berjalan"|
  "selesai"), ``period``, ``clock_display``, ``seconds_remaining`` (total
  detik tersisa sampai akhir regulasi), ``home_score``, ``away_score``,
  ``line_scores``, ``stats``, ``fetched_at``, ``source``).
- ``pregame_medians``: dict match_id -> median total pra-laga (dari
  artefak ``nba_analysis``; None berarti proyeksi hanya memakai laju live).

METODE PROYEKSI (pace-based; didokumentasikan jujur, lihat "Keterbatasan"):
- menit_lalu = 48 - menit_sisa (dari ``seconds_remaining``). Bila
  ``period`` > 4 (OT): menit_lalu = 48 + 5*(period-4) - sisa di OT
  berjalan, dan menit_sisa = sisa di OT berjalan. Sisa OT dibaca dari
  ``clock_display`` ("M:SS") karena ``seconds_remaining`` kontraknya
  "sampai akhir regulasi" (sudah lewat saat OT); bila jam tidak terurai,
  fallback ke ``seconds_remaining`` bila 0 < nilai <= 300 detik.
  Bila ``seconds_remaining`` tidak tersedia di regulasi, fallback ke
  ``clock_display`` + sisa kuarter penuh ((4-period)*12 menit).
- live_rate = total_skor_berjalan / menit_lalu (poin/menit); butuh
  menit_lalu >= 1 menit, bila kurang belum ada proyeksi.
- pregame_rate = median_total_pra_laga / 48 (bila median tersedia).
- w_live = menit_lalu / 48, dijepit [0, 1] (di OT = 1,0).
- projected = total_berjalan + (w_live*live_rate + (1-w_live)*pregame_rate)
  * menit_sisa. Tanpa median pra-laga: projected memakai live_rate saja
  (metode "live_rate_only", kurang andal di awal laga). Laga selesai:
  projected = total_akhir (metode "final"). Laga belum mulai: tidak ada
  proyeksi (metode None).
- OT RISK: True bila |selisih skor| <= ``live.ot_risk_margin_points`` DAN
  menit_sisa <= ``live.ot_risk_minutes_remaining`` — laga bisa masuk OT
  dan total bertambah (penting untuk kaki Under). Di OT yang sedang
  berjalan, flag yang sama berarti risiko OT berikutnya.

STATUS KAKI (Under): margin = garis - projected_total. margin >=
``live.status_margin_aman_points`` -> AMAN; >=
``live.status_margin_waspada_points`` -> WASPADA; sisanya TERANCAM.
Laga selesai: total akhir < garis -> MENANG; > garis -> KALAH; == garis
-> PUSH (keputusan modul ini: total sama dengan garis adalah seri —
modal kaki biasanya kembali, tergantung aturan venue; garis .5 praktis
tidak pernah push). Laga belum mulai -> BELUM_MULAI. Pasar bukan
``total_under``, garis tak terurai, laga tak ditemukan, atau proyeksi
tidak bisa dihitung -> DATA_INCOMPLETE + alasan (tidak ditebak).

STATUS TIKET = kaki terburuk, urutan: KALAH > TERANCAM > WASPADA >
DATA_INCOMPLETE > AMAN > BELUM_MULAI. Kaki selesai (MENANG/PUSH) tidak
menarik status ke bawah: campuran selesai/belum mengikuti kaki terburuk
yang belum selesai, dengan catatan. Semua kaki MENANG -> MENANG; semua
kaki PUSH -> PUSH; campuran MENANG+PUSH -> MENANG + catatan (kaki yang
push biasanya keluar dari tiket).

KETERBATASAN (jujur, bukan disembunyikan):
- Proyeksi pace-based mengasumsikan laju skor berjalan berlanjut.
  Ia MENGABAIKAN: perubahan tempo kuarter akhir, foul di akhir laga
  (yang menaikkan total), pergantian pemain/cedera di tengah laga, dan
  OT itu sendiri kecuali flag risiko — proyeksi hanya sampai akhir
  periode berjalan, tidak menambah menit OT yang mungkin terjadi.
- Ambang status (6,0 / 2,0 poin) dan ambang OT adalah NILAI AWAL di
  config/playstyle.yaml — BELUM DIKALIBRASI atas data PAPER.
- Metode ini proyeksi kasar untuk pantauan, BUKAN pengganti simulasi
  pra-laga (100.000 iterasi) — jangan dipakai menilai ulang peluang
  menang tiket.

SPESIFIKASI WIRING UNTUK KOORDINATOR (subcommand ``cli.py pantau``):
    live_games = {g["match_id"]: g for g in ambil_live(...)}  # pekerja A
    medians = {a["match_id"]: median_total(a) for a in analyses}  # opsional
    hasil = evaluate_ticket(tiket, live_games, medians, config.load_playstyle())
    print(render_live_status(hasil, anomalies_by_match))  # pekerja C, opsional
    # Exit code (keputusan koordinator langkah 4): 0 bila tidak ada kaki
    # TERANCAM/KALAH/DATA_INCOMPLETE dan tidak ada anomali; 1 bila ada
    # kaki TERANCAM/KALAH/DATA_INCOMPLETE atau anomali; 2 bila pantauan
    # tidak bisa berjalan. WASPADA/PUSH tidak menaikkan exit code
    # (terlihat jelas di teks; WASPADA masih diproyeksikan menang).
"""

from __future__ import annotations

import math
import re
from collections import Counter

import config as config_mod

_REGULASI_MENIT = 48.0
_REGULASI_DETIK = 2880
_KUARTER_DETIK = 720
_OT_MENIT = 5.0
_OT_DETIK = 300
# Proyeksi butuh minimal 1 menit laga berjalan (live_rate dari < 1 menit
# terlalu liar: pembagian total skor oleh pecahan menit yang kecil).
_MENIT_MINIMAL_PROYEKSI = 1.0

_POLA_GARIS = re.compile(r"Under\s+([0-9]+(?:\.[0-9]+)?)")
_POLA_JAM = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")
_POLA_MATCH_ID = re.compile(r"^([A-Z]{3}@[A-Z]{3})_\d{4}-\d{2}-\d{2}$")

_KATA_STATUS = {
    "AMAN": "aman",
    "WASPADA": "waspada",
    "TERANCAM": "terancam",
    "MENANG": "menang",
    "KALAH": "kalah",
    "PUSH": "seri (push)",
    "BELUM_MULAI": "belum mulai",
    "DATA_INCOMPLETE": "belum bisa dinilai",
}


def _angka(nilai) -> float | None:
    """Ubah nilai menjadi float berhingga, atau None bila tidak valid."""
    if isinstance(nilai, bool) or nilai is None:
        return None
    try:
        hasil = float(nilai)
    except (TypeError, ValueError):
        return None
    return hasil if math.isfinite(hasil) else None


def _muat_cfg(cfg: dict | None) -> dict:
    """Pakai cfg yang diberikan, atau muat playstyle.yaml bila None."""
    if cfg is not None:
        return cfg
    return config_mod.load_playstyle()


def _ambang(cfg: dict, *kunci: str) -> float:
    """Ambil ambang numerik dari config; hilang/tidak valid -> ConfigError."""
    try:
        nilai = config_mod.get_value(cfg, *kunci)
    except (KeyError, TypeError, AttributeError) as exc:
        raise config_mod.ConfigError(
            f"playstyle.yaml kehilangan kunci: {'.'.join(kunci)}"
        ) from exc
    hasil = _angka(nilai)
    if hasil is None:
        raise config_mod.ConfigError(
            f"playstyle.yaml kunci {'.'.join(kunci)} bukan angka: {nilai!r}"
        )
    return hasil


def _parse_jam(teks) -> int | None:
    """Urai clock_display 'M:SS' menjadi detik tersisa di periode berjalan."""
    if not isinstance(teks, str):
        return None
    cocok = _POLA_JAM.match(teks)
    if cocok is None:
        return None
    menit, detik = int(cocok.group(1)), int(cocok.group(2))
    if detik >= 60 or menit > 12:
        return None
    return menit * 60 + detik


def _sisa_detik(live_game: dict) -> tuple[int | None, str | None]:
    """Sisa waktu laga dalam detik (ke akhir regulasi, atau ke akhir OT).

    Mengembalikan (detik | None, catatan_gagal | None). Di OT, sumber
    utama adalah ``clock_display`` (``seconds_remaining`` kontraknya
    "sampai akhir regulasi" — sudah lewat saat OT); fallback ke
    ``seconds_remaining`` bila 0 < nilai <= 300 detik. Di regulasi,
    sumber utama ``seconds_remaining``; fallback ke ``clock_display`` +
    sisa kuarter penuh.
    """
    period = _angka(live_game.get("period"))
    periode = int(period) if period is not None else None
    sr = _angka(live_game.get("seconds_remaining"))
    if periode is not None and periode > 4:
        jam = _parse_jam(live_game.get("clock_display"))
        if jam is not None and jam <= _OT_DETIK:
            return jam, None
        if sr is not None and 0 < sr <= _OT_DETIK:
            return int(sr), None
        return None, "Sisa waktu OT tidak bisa dibaca (jam tidak terurai)."
    if sr is not None and 0 <= sr <= _REGULASI_DETIK:
        return int(sr), None
    jam = _parse_jam(live_game.get("clock_display"))
    if jam is not None and periode is not None and 1 <= periode <= 4:
        return (4 - periode) * _KUARTER_DETIK + jam, None
    return None, "Sisa waktu laga tidak tersedia — proyeksi tidak bisa dihitung."


def _urai_garis(selection) -> float | None:
    """Urai garis total dari selection kaki ('Under 237.5 (DET@ATL)')."""
    if not isinstance(selection, str):
        return None
    cocok = _POLA_GARIS.search(selection)
    if cocok is None:
        return None
    return _angka(cocok.group(1))


def _skor_total(live_game: dict) -> float | None:
    """Total skor berjalan (home + away), atau None bila skor tak lengkap."""
    home = _angka(live_game.get("home_score"))
    away = _angka(live_game.get("away_score"))
    if home is None or away is None:
        return None
    return home + away


def project_final_total(
    live_game: dict,
    pregame_median_total: float | None = None,
    cfg: dict | None = None,
) -> dict:
    """Proyeksi total akhir satu laga NBA (pace-based, lihat docstring modul).

    Mengembalikan dict: ``projected_total`` (float | None),
    ``method`` ("blend"|"live_rate_only"|"final"|None), ``live_rate_ppm``
    dan ``pregame_rate_ppm`` (poin/menit, atau None),
    ``minutes_elapsed`` / ``minutes_remaining`` (float | None), ``ot_risk``
    (bool), ``notes`` (list[str]). ``projected_total`` None berarti tidak
    ada proyeksi — alasannya di ``notes`` (bukan ditebak).
    """
    hasil: dict = {
        "projected_total": None,
        "method": None,
        "live_rate_ppm": None,
        "pregame_rate_ppm": None,
        "minutes_elapsed": None,
        "minutes_remaining": None,
        "ot_risk": False,
        "notes": [],
    }
    if not isinstance(live_game, dict):
        hasil["notes"].append("Data live laga tidak tersedia.")
        return hasil
    median = _angka(pregame_median_total)
    if pregame_median_total is not None and (median is None or median <= 0):
        hasil["notes"].append("Median total pra-laga tidak valid — diabaikan.")
        median = None
    if median is not None:
        hasil["pregame_rate_ppm"] = median / _REGULASI_MENIT

    status = live_game.get("status")
    current_total = _skor_total(live_game)

    if status == "belum_mulai":
        hasil["minutes_elapsed"] = 0.0
        hasil["minutes_remaining"] = _REGULASI_MENIT
        hasil["notes"].append("Laga belum mulai — belum ada proyeksi total akhir.")
        return hasil

    if status == "selesai":
        hasil["minutes_remaining"] = 0.0
        period = _angka(live_game.get("period"))
        if period is not None and period > 4:
            hasil["minutes_elapsed"] = _REGULASI_MENIT + _OT_MENIT * (period - 4)
        else:
            hasil["minutes_elapsed"] = _REGULASI_MENIT
        if current_total is None:
            hasil["notes"].append("Laga selesai tapi skor akhir tidak tersedia.")
            return hasil
        hasil["projected_total"] = current_total
        hasil["method"] = "final"
        hasil["live_rate_ppm"] = current_total / hasil["minutes_elapsed"]
        return hasil

    if status != "berjalan":
        hasil["notes"].append(f"Status laga tidak dikenal: {status!r}.")
        return hasil

    # --- Laga berjalan ---
    if current_total is None:
        hasil["notes"].append(
            "Skor berjalan tidak tersedia — proyeksi tidak bisa dihitung."
        )
        return hasil
    sisa_detik, catatan_waktu = _sisa_detik(live_game)
    if sisa_detik is None:
        hasil["notes"].append(catatan_waktu or "Sisa waktu laga tidak tersedia.")
        return hasil
    period = _angka(live_game.get("period"))
    menit_sisa = sisa_detik / 60.0
    if period is not None and period > 4:
        menit_lalu = _REGULASI_MENIT + _OT_MENIT * (period - 4) - menit_sisa
        hasil["notes"].append(
            f"Laga masuk babak tambahan (OT ke-{int(period - 4)}) — proyeksi "
            "hanya sampai akhir OT berjalan; OT berikutnya tidak terhitung."
        )
    else:
        menit_lalu = _REGULASI_MENIT - menit_sisa
    hasil["minutes_elapsed"] = menit_lalu
    hasil["minutes_remaining"] = menit_sisa
    if menit_lalu < _MENIT_MINIMAL_PROYEKSI:
        hasil["notes"].append(
            "Laga baru berjalan kurang dari 1 menit — proyeksi belum bisa " "dihitung."
        )
        return hasil
    live_rate = current_total / menit_lalu
    hasil["live_rate_ppm"] = live_rate
    w_live = min(1.0, max(0.0, menit_lalu / _REGULASI_MENIT))
    if median is not None:
        campuran = w_live * live_rate + (1.0 - w_live) * hasil["pregame_rate_ppm"]
        hasil["projected_total"] = current_total + campuran * menit_sisa
        hasil["method"] = "blend"
    else:
        hasil["projected_total"] = current_total + live_rate * menit_sisa
        hasil["method"] = "live_rate_only"
        hasil["notes"].append(
            "Tanpa median total pra-laga, proyeksi hanya memakai laju skor "
            "live — kurang andal di awal laga."
        )
    # Risiko OT (ambang dari config; hanya dibaca bila laga berjalan).
    cfg_penuh = _muat_cfg(cfg)
    margin_ot = _ambang(cfg_penuh, "live", "ot_risk_margin_points")
    menit_ot = _ambang(cfg_penuh, "live", "ot_risk_minutes_remaining")
    home = _angka(live_game.get("home_score"))
    away = _angka(live_game.get("away_score"))
    assert home is not None and away is not None  # sudah dicek di atas
    if abs(home - away) <= margin_ot and menit_sisa <= menit_ot:
        hasil["ot_risk"] = True
        hasil["notes"].append(
            "Hati-hati: selisih skor tipis di akhir laga — laga bisa masuk "
            "babak tambahan (OT) dan total bertambah."
        )
    return hasil


def evaluate_leg(
    leg: dict,
    live_game: dict | None,
    pregame_median_total: float | None = None,
    cfg: dict | None = None,
) -> dict:
    """Nilai satu kaki tiket terhadap data live laganya.

    Mengembalikan dict: ``leg_id``, ``match_id``, ``line`` (float | None),
    ``current_total``, ``projected_total``, ``status`` (AMAN|WASPADA|
    TERANCAM|MENANG|KALAH|PUSH|BELUM_MULAI|DATA_INCOMPLETE),
    ``margin_points`` (garis - proyeksi/total akhir, atau None),
    ``ot_risk`` (bool), ``notes`` (list[str]).
    """
    hasil: dict = {
        "leg_id": leg.get("leg_id") if isinstance(leg, dict) else None,
        "match_id": leg.get("match_id") if isinstance(leg, dict) else None,
        "line": None,
        "current_total": None,
        "projected_total": None,
        "status": "DATA_INCOMPLETE",
        "margin_points": None,
        "ot_risk": False,
        "notes": [],
    }
    if not isinstance(leg, dict):
        hasil["notes"].append("Kaki tiket bukan dict.")
        return hasil
    if leg.get("market") != "total_under":
        hasil["notes"].append(
            f"Pasar {leg.get('market')!r} belum didukung pantauan live "
            "(hanya total_under)."
        )
        return hasil
    garis = _urai_garis(leg.get("selection"))
    if garis is None:
        hasil["notes"].append(
            f"Garis tidak bisa diurai dari selection: {leg.get('selection')!r}."
        )
        return hasil
    hasil["line"] = garis
    if not isinstance(live_game, dict):
        hasil["notes"].append("Laga tidak ditemukan di data live.")
        return hasil
    hasil["current_total"] = _skor_total(live_game)
    status_laga = live_game.get("status")
    if status_laga == "belum_mulai":
        hasil["notes"].append("Laga belum mulai — belum ada proyeksi total akhir.")
        hasil["status"] = "BELUM_MULAI"
        return hasil
    if status_laga == "selesai":
        proyeksi = project_final_total(live_game, pregame_median_total, cfg)
        hasil["notes"].extend(proyeksi["notes"])
        if proyeksi["projected_total"] is None:
            return hasil
        hasil["projected_total"] = proyeksi["projected_total"]
        hasil["margin_points"] = garis - proyeksi["projected_total"]
        if proyeksi["projected_total"] < garis:
            hasil["status"] = "MENANG"
        elif proyeksi["projected_total"] > garis:
            hasil["status"] = "KALAH"
        else:
            hasil["status"] = "PUSH"
            hasil["notes"].append(
                "Total akhir sama dengan garis (push) — modal kaki ini "
                "biasanya kembali, tergantung aturan venue."
            )
        return hasil
    if status_laga != "berjalan":
        hasil["notes"].append(f"Status laga tidak dikenal: {status_laga!r}.")
        return hasil
    proyeksi = project_final_total(live_game, pregame_median_total, cfg)
    hasil["notes"].extend(proyeksi["notes"])
    hasil["ot_risk"] = proyeksi["ot_risk"]
    if proyeksi["projected_total"] is None:
        return hasil
    hasil["projected_total"] = proyeksi["projected_total"]
    margin = garis - proyeksi["projected_total"]
    hasil["margin_points"] = margin
    cfg_penuh = _muat_cfg(cfg)
    aman = _ambang(cfg_penuh, "live", "status_margin_aman_points")
    waspada = _ambang(cfg_penuh, "live", "status_margin_waspada_points")
    if margin >= aman:
        hasil["status"] = "AMAN"
    elif margin >= waspada:
        hasil["status"] = "WASPADA"
    else:
        hasil["status"] = "TERANCAM"
    return hasil


def _status_tiket(hasil_kaki: list[dict], notes: list[str]) -> str:
    """Status tiket = kaki terburuk (urutan di docstring modul)."""
    if not hasil_kaki:
        notes.append("Tiket tidak punya kaki.")
        return "DATA_INCOMPLETE"
    status_set = {kaki["status"] for kaki in hasil_kaki}
    selesai = [
        kaki for kaki in hasil_kaki if kaki["status"] in ("MENANG", "KALAH", "PUSH")
    ]
    belum = [
        kaki for kaki in hasil_kaki if kaki["status"] not in ("MENANG", "KALAH", "PUSH")
    ]
    if selesai and belum:
        notes.append(
            f"{len(selesai)} kaki sudah selesai, {len(belum)} kaki masih "
            "berjalan/belum mulai — status tiket mengikuti kaki terburuk "
            "yang belum selesai."
        )
    if "KALAH" in status_set:
        kalah = [kaki["match_id"] for kaki in hasil_kaki if kaki["status"] == "KALAH"]
        notes.append(f"Kaki yang kalah: {', '.join(str(m) for m in kalah)}.")
        return "KALAH"
    if "TERANCAM" in status_set:
        return "TERANCAM"
    if "WASPADA" in status_set:
        return "WASPADA"
    if "DATA_INCOMPLETE" in status_set:
        tak_dinilai = [
            kaki["match_id"]
            for kaki in hasil_kaki
            if kaki["status"] == "DATA_INCOMPLETE"
        ]
        notes.append(
            "Kaki yang belum bisa dinilai: "
            + ", ".join(str(m) for m in tak_dinilai)
            + "."
        )
        return "DATA_INCOMPLETE"
    if "AMAN" in status_set:
        return "AMAN"
    if "BELUM_MULAI" in status_set:
        return "BELUM_MULAI"
    if "PUSH" in status_set:
        if all(kaki["status"] == "PUSH" for kaki in hasil_kaki):
            notes.append("Semua kaki seri (push).")
            return "PUSH"
        notes.append("Satu kaki seri (push) — biasanya kaki itu keluar dari tiket.")
        return "MENANG"
    return "MENANG"


def evaluate_ticket(
    ticket: dict,
    live_games_by_match: dict | None,
    pregame_medians: dict | None = None,
    cfg: dict | None = None,
) -> dict:
    """Nilai seluruh kaki satu tiket terhadap data live.

    ``live_games_by_match``: dict match_id -> LiveGame. ``pregame_medians``:
    dict match_id -> median total pra-laga (opsional; tanpa median,
    proyeksi memakai laju live saja). Mengembalikan dict: ``ticket_id``,
    ``type``, ``status`` (kaki terburuk, lihat ``_status_tiket``),
    ``legs`` (daftar hasil ``evaluate_leg``), ``notes``.
    """
    cfg_penuh = _muat_cfg(cfg)
    if not isinstance(ticket, dict):
        return {
            "ticket_id": None,
            "type": None,
            "status": "DATA_INCOMPLETE",
            "legs": [],
            "notes": ["Tiket bukan dict."],
        }
    games = live_games_by_match or {}
    medians = pregame_medians or {}
    hasil_kaki = []
    for leg in ticket.get("legs") or []:
        match_id = leg.get("match_id") if isinstance(leg, dict) else None
        live_game = games.get(match_id) if match_id else None
        median = medians.get(match_id) if match_id else None
        hasil_kaki.append(evaluate_leg(leg, live_game, median, cfg_penuh))
    notes: list[str] = []
    status = _status_tiket(hasil_kaki, notes)
    return {
        "ticket_id": ticket.get("ticket_id"),
        "type": ticket.get("type"),
        "status": status,
        "legs": hasil_kaki,
        "notes": notes,
    }


def _fmt(nilai) -> str:
    """Format angka gaya Indonesia: 237,5; bilangan bulat tanpa koma."""
    if nilai is None:
        return "—"
    angka = float(nilai)
    if abs(angka - round(angka)) < 0.05:
        return str(int(round(angka)))
    return f"{angka:.1f}".replace(".", ",")


def _singkat_match(match_id) -> str:
    """'DET@ATL_2026-11-22' -> 'DET@ATL'; format lain dipakai apa adanya."""
    if not isinstance(match_id, str):
        return "?"
    cocok = _POLA_MATCH_ID.match(match_id)
    return cocok.group(1) if cocok else match_id


def _baris_kaki(leg: dict) -> str:
    """Satu baris teks untuk satu kaki (Bahasa Indonesia sehari-hari)."""
    singkat = _singkat_match(leg.get("match_id"))
    status = leg.get("status")
    garis = _fmt(leg.get("line"))
    current = _fmt(leg.get("current_total"))
    proyeksi = _fmt(leg.get("projected_total"))
    if status in ("AMAN", "WASPADA", "TERANCAM"):
        kata = _KATA_STATUS[status]
        teks = (
            f"Kaki {singkat} {kata} — proyeksi total {proyeksi} "
            f"vs garis {garis} (total berjalan {current})"
        )
        margin = leg.get("margin_points")
        if margin is not None:
            teks += f", selisih {_fmt(margin)} poin"
        teks += "."
        if leg.get("ot_risk"):
            teks += " Hati-hati: laga bisa masuk babak tambahan (OT)."
        return teks
    if status == "MENANG":
        return f"Kaki {singkat} menang — total akhir {current} di bawah garis {garis}."
    if status == "KALAH":
        return f"Kaki {singkat} kalah — total akhir {current} di atas garis {garis}."
    if status == "PUSH":
        return (
            f"Kaki {singkat} seri (push) — total akhir {current} "
            f"sama dengan garis {garis}."
        )
    if status == "BELUM_MULAI":
        return f"Kaki {singkat} belum mulai — laga belum berjalan."
    alasan = "; ".join(leg.get("notes") or []) or "data live tidak lengkap"
    return f"Kaki {singkat} belum bisa dinilai — {alasan}"


def _anomali_laga(anomalies_by_match, match_id) -> list[str]:
    """Urai anomali satu laga menjadi daftar teks (dari pekerja C).

    Menerima daftar string, atau daftar dict dengan kunci 'pesan' /
    'message' / 'ringkasan' / 'description' / 'text'. None -> [].
    """
    if not isinstance(anomalies_by_match, dict) or match_id is None:
        return []
    daftar = anomalies_by_match.get(match_id)
    if not daftar:
        return []
    if isinstance(daftar, str):
        return [daftar]
    hasil = []
    for item in daftar:
        if isinstance(item, str):
            hasil.append(item)
        elif isinstance(item, dict):
            for kunci in ("pesan", "message", "ringkasan", "description", "text"):
                if item.get(kunci):
                    hasil.append(str(item[kunci]))
                    break
            else:
                hasil.append(str(item))
        else:
            hasil.append(str(item))
    return hasil


def render_live_status(ticket_result: dict, anomalies_by_match=None) -> str:
    """Rangkai teks status live satu tiket (Bahasa Indonesia sehari-hari).

    ``ticket_result``: hasil ``evaluate_ticket``. ``anomalies_by_match``
    (opsional, dari pekerja C): dict match_id -> daftar anomali (string
    atau dict); bila None, anomali diabaikan.
    """
    if not isinstance(ticket_result, dict):
        return "Status tiket tidak bisa ditampilkan — hasil evaluasi tidak tersedia."
    tipe = ticket_result.get("type")
    sapaan = f"Tiket {tipe}mu" if tipe in ("Asuransi", "Utama") else "Tiketmu"
    kaki = ticket_result.get("legs") or []
    status = ticket_result.get("status")
    hitung = Counter(leg.get("status") for leg in kaki)
    if status == "MENANG":
        baris = [f"{sapaan} menang — semua kaki menang."]
    elif status == "KALAH":
        baris = [f"{sapaan} kalah — ada kaki yang kalah."]
    elif status == "TERANCAM":
        baris = [f"{sapaan} terancam — {hitung['TERANCAM']} kaki terancam."]
    elif status == "WASPADA":
        baris = [f"{sapaan} perlu diawasi — {hitung['WASPADA']} kaki waspada."]
    elif status == "AMAN":
        baris = [f"{sapaan} masih hijau — {hitung['AMAN']} kaki aman."]
    elif status == "BELUM_MULAI":
        baris = [f"{sapaan} belum mulai — semua laga belum berjalan."]
    elif status == "DATA_INCOMPLETE":
        baris = [f"{sapaan} belum bisa dinilai — data live belum lengkap."]
    elif status == "PUSH":
        baris = [f"{sapaan} seri (push) — semua kaki seri."]
    else:
        baris = [f"{sapaan} belum bisa dinilai."]
    for leg in kaki:
        baris.append(_baris_kaki(leg))
        for teks in _anomali_laga(anomalies_by_match, leg.get("match_id")):
            baris.append(f"  Anomali: {teks}")
    for catatan in ticket_result.get("notes") or []:
        baris.append(f"Catatan: {catatan}")
    return "\n".join(baris)
