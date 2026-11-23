"""Audit tiket sebelum pasang (insiden DEN 23 Nov 2026).

Fungsi utama: ``audit_tickets(dokumen_tiket, dokumen_analisis, cfg)``
lalu ``render_audit_text(hasil)`` untuk teks Bahasa Indonesia
sehari-hari.

MASALAH YANG DISELESAIKAN: tiket nyata 23 Nov 2026 diracik Gemini,
bukan mesin. Kaki DEN@CHI jebol karena banjir 3 poin (halftime total
142, proyeksi live 284). Pra-laga, mesin sudah menandai DEN sebagai
kaki terlemah Asuransi (P_model 84,5%, edge +2,5% terkecil), tapi
tidak ada modul yang memeriksa tiket SEBELUM dipasang — kaki itu
lolos semua gate yang ada. Modul ini adalah pemeriksa itu: ia
menilai tiap kaki tiket terhadap simulasi mesin + tangga Polymarket
dan memberi verdict GO / NO-GO sebelum uang keluar.

PERINGATAN PENTING: ``p_model``/``p_final`` di file tiket nyata
adalah angka GEMINI (lihat notes file itu), BUKAN angka mesin.
Modul ini MENGHITUNG P_model dari sim markets artefak analisis
(``simulation.markets["total_under_<garis>"]``) dan MENGABAIKAN
angka file tiket untuk verdict. Angka file tiket hanya ditampilkan
sebagai perbandingan dengan label jelas "angka Gemini, bukan mesin".

Masukan:
- ``dokumen_tiket``: dict tiket — objek tiket tunggal (kunci
  "legs"), pasangan {"insurance","main"} output racik / tiket
  nyata, atau {"tickets": [...]}. Tiap kaki: ``leg_id``,
  ``match_id``, ``market`` ("total_under"), ``selection``
  ("Under 242.5 (OKC@MIA)"), ``jup_price_cents``, plus
  ``multiplier`` dan ``stake`` di level tiket.
- ``dokumen_analisis``: daftar dict JSON analisis — artefak
  ``nba_analysis`` langsung (format == "nba_analysis") atau output
  ``cli.py analyze`` (kunci "matches", artefak di
  ``matches[].nba_analysis``). Laga yang sama di dua file: yang
  TERBARU (``generated_at``) menang (sama seperti
  ``ticket_composer._terbaru_per_laga``); tanpa stempel waktu yang
  bisa diurai, kemunculan pertama menang.
- ``cfg``: dict playstyle.yaml (None = muat default).

Keluaran per kaki: P_model (dari sim, cocok garis persis — bila
tidak ada, kaki DATA_INCOMPLETE, tidak ditebak), harga, edge =
P_model − harga/100, EV + label harga (dari P_model, selaras
``engine/price_labels.py``), volume tangga + thin?, evaluasi
condong-ke-market (|median − garis market| vs ambang config dan
apakah probabilitas pasar < target), hasil tiap gate, verdict
LOLOS / PERHATIAN / JANGAN_PASANG / DATA_INCOMPLETE + alasan
Bahasa Indonesia sederhana.

GATE (selaras ``engine/ticket_composer.py``):
- peluang minimum: P_model >= tickets.<tipe>.min_leg_prob
  (Asuransi 0,74 / Utama 0,65) — gagal = JANGAN_PASANG.
- lantai harga: harga >= analis.harga_min_<tipe>_cents (75¢) —
  gagal = JANGAN_PASANG.
- volume tipis (thin=True di tangga): PENGHALANG KERAS Asuransi
  (JANGAN_PASANG); Utama boleh tapi PERHATIAN + flag VOLUME_TIPIS.
  Tangga tidak ditemukan untuk garis itu: Asuransi JANGAN_PASANG
  (volume tidak terverifikasi — fail-closed), Utama PERHATIAN.
- condong-ke-market (aturan 2026-11-22): bila |median − garis
  market| > market_line_check.total_gap_points dan probabilitas
  pasar < ambang Asuransi, kaki Asuransi JANGAN_PASANG. Utama
  hanya dicatat (peracik: Utama selalu memakai model); bila
  probabilitas pasar juga < ambang Utama, kaki Utama PERHATIAN.
- label MAHAL (EV < −2%): Asuransi JANGAN_PASANG (selaras
  optimizer.exclude_mahal_from_insurance); Utama PERHATIAN.
- OVERPAY (edge < 0): flag di kaki mana pun; kaki Utama (atau
  Asuransi yang bukan MAHAL) menjadi PERHATIAN.
- edge tipis (0 <= edge < 5 poin, NILAI AWAL): PERHATIAN — pelajaran
  DEN 23 Nov (edge +2,5% adalah kaki terlemah yang akhirnya jebol);
  menunggu kalibrasi + persetujuan user.

Per tiket: kaki terlemah (P_model terendah), peluang gabungan
(produk P_model — asumsi kaki independen, sama seperti peracik),
EV = P_gabungan × pengali riil tiket − 1, verdict GO / NO-GO.
NO-GO bila ada kaki JANGAN_PASANG atau DATA_INCOMPLETE; bila
tidak, GO — kaki PERHATIAN dicatat sebagai peringatan eksplisit
(bukan alasan NO-GO, selaras peracik yang membolehkan kaki
PERHATIAN/volume tipis di Utama dengan flag).

Modul ini juga menyediakan dua pembantu artefak analisis yang
dipakai ``cli.py pantau`` (Item 5): ``kumpulkan_analisis`` (kumpul
+ dedup terbaru per laga dari banyak file) dan ``median_pra_laga``
(median total pra-laga per match_id) — satu implementasi dedup
untuk audit dan pantau.

Batasan (dicatat, bukan disembunyikan):
- Hanya pasar ``total_under`` NBA yang dinilai; pasar lain
  DATA_INCOMPLETE (belum didukung).
- Peluang gabungan mengasumsikan kaki independen. Dua kaki dari
  laga yang sama dalam satu tiket berkorelasi (peracik tidak
  pernah menumpuknya; bila tiket luar menumpuk, produk tetap
  dipakai + dicatat di asumsi).
- Label harga dihitung dari P_model mesin, BUKAN p_final
  (audit tidak punya p_market blend) — labelnya berarti "harga
  dinilai dari model mesin saja".
- Aturan condong-ke-market di sini tidak mengenal "alasan
  konkret" / "Kenapa beda?" (audit tidak menerima input recheck)
  — gap besar selalu memakai probabilitas pasar untuk Asuransi.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime

import config as config_mod
from engine import price_labels as price_labels_mod

_TIPE_TIKET = {
    "insurance": "insurance",
    "asuransi": "insurance",
    "main": "main",
    "utama": "main",
}
_NAMA_TIPE = {"insurance": "Asuransi", "main": "Utama"}

_POLA_GARIS = re.compile(r"Under\s+([0-9]+(?:\.[0-9]+)?)")

# Default ambang edge tipis bila kunci audit.edge_tipis_pct belum ada
# di config (pola yang sama seperti fallback di ticket_composer).
# Nilai config-lah yang berlaku bila ada; lihat playstyle.yaml.
_EDGE_TIPIS_DEFAULT = 0.05
# Perbandingan memakai toleransi epsilon agar batasnya tidak goyang
# oleh galat floating point (0,85 - 0,80 != tepat 0,05).
_EPS = 1e-9


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


def _ambang_edge_tipis(cfg: dict) -> tuple[float, str]:
    """Ambang edge tipis audit dari config (persen -> desimal).

    Kunci ``audit.edge_tipis_pct``; hilang/tidak valid -> default 0,05
    dengan sumber dicatat (bukan diam-diam). Ambang ini PERHATIAN,
    bukan gate keras.
    """
    try:
        nilai = config_mod.get_value(cfg, "audit", "edge_tipis_pct")
    except (config_mod.ConfigError, KeyError, TypeError, AttributeError):
        nilai = None
    hasil = _angka(nilai)
    if hasil is None:
        return (
            _EDGE_TIPIS_DEFAULT,
            "default 5,0% (kunci audit.edge_tipis_pct belum ada di config)",
        )
    return hasil / 100.0, "config audit.edge_tipis_pct"


def _parse_iso(teks) -> datetime | None:
    """Parse ISO 8601 menjadi datetime aware (UTC bila tanpa zona)."""
    if not isinstance(teks, str) or not teks.strip():
        return None
    try:
        hasil = datetime.fromisoformat(teks.replace("Z", "+00:00"))
    except ValueError:
        return None
    if hasil.tzinfo is None:
        hasil = hasil.replace(tzinfo=UTC)
    return hasil


def _urai_garis(selection) -> float | None:
    """Urai garis total dari selection kaki ('Under 237.5 (DET@ATL)')."""
    if not isinstance(selection, str):
        return None
    cocok = _POLA_GARIS.search(selection)
    if cocok is None:
        return None
    return _angka(cocok.group(1))


def _fmt_persen(nilai: float | None, desimal: int = 1) -> str:
    """Format peluang desimal sebagai persen ('84,5%'); None -> '—'."""
    if nilai is None:
        return "—"
    return f"{nilai * 100:.{desimal}f}%".replace(".", ",")


def _fmt_poin(nilai: float | None, desimal: int = 1) -> str:
    """Format angka poin gaya Indonesia ('8,5'); None -> '—'."""
    if nilai is None:
        return "—"
    return f"{nilai:.{desimal}f}".replace(".", ",")


def _fmt_uang(nilai: float | None) -> str:
    """Format USD singkat ('$15' / '$10,50'); None -> '—'."""
    if nilai is None:
        return "—"
    if abs(nilai - round(nilai)) < 0.005:
        return f"${nilai:.0f}"
    return f"${nilai:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------------------
# Pembantu artefak analisis (dipakai audit + cli.py pantau)
# ---------------------------------------------------------------------------


def _artefak_dari_dokumen(dokumen: dict) -> list[dict]:
    """Kumpulkan artefak nba_analysis dari satu dokumen JSON.

    Menerima (a) artefak nba_analysis langsung (format ==
    "nba_analysis") atau (b) output cli.py analyze (kunci "matches",
    artefak di "nba_analysis" tiap entri laga). Dokumen yang bukan
    keduanya -> daftar kosong.
    """
    if not isinstance(dokumen, dict):
        return []
    if dokumen.get("format") == "nba_analysis":
        return [dokumen]
    matches = dokumen.get("matches")
    if not isinstance(matches, list):
        return []
    return [
        m["nba_analysis"]
        for m in matches
        if isinstance(m, dict) and isinstance(m.get("nba_analysis"), dict)
    ]


def terbaru_per_laga(artefak: list[dict]) -> tuple[dict[str, dict], list[str]]:
    """Dedup artefak per match_id — yang TERBARU (generated_at) menang.

    Artefak tanpa match_id dilewati + dicatat. Tanpa stempel waktu
    yang bisa diurai di kedua belah pihak, kemunculan pertama menang
    (stabil, tidak ditebak). Mengembalikan (dict match_id -> artefak,
    catatan).
    """
    hasil: dict[str, dict] = {}
    catatan: list[str] = []
    for art in artefak:
        if not isinstance(art, dict):
            continue
        match_id = art.get("match_id")
        if not isinstance(match_id, str) or not match_id:
            catatan.append("artefak tanpa match_id dilewati")
            continue
        lama = hasil.get(match_id)
        if lama is None:
            hasil[match_id] = art
            continue
        baru_waktu = _parse_iso(art.get("generated_at"))
        lama_waktu = _parse_iso(lama.get("generated_at"))
        if baru_waktu is not None and (lama_waktu is None or baru_waktu > lama_waktu):
            hasil[match_id] = art
            catatan.append(
                f"{match_id}: muncul di dua artefak — dipakai yang "
                f"terbaru ({art.get('generated_at')}); yang lain "
                f"({lama.get('generated_at')}) lebih lama"
            )
        else:
            catatan.append(
                f"{match_id}: muncul di dua artefak — dipakai yang "
                f"terbaru ({lama.get('generated_at')}); yang lain "
                f"({art.get('generated_at')}) lebih lama atau tanpa "
                "stempel waktu"
            )
    return hasil, catatan


def kumpulkan_analisis(
    dokumen_list: list[dict],
) -> tuple[dict[str, dict], list[str]]:
    """Kumpulkan artefak nba_analysis dari banyak dokumen JSON.

    Tiap dokumen boleh berupa artefak langsung atau output analyze
    (lihat ``_artefak_dari_dokumen``). Laga yang sama di dua dokumen:
    yang terbaru menang (lihat ``terbaru_per_laga``). Mengembalikan
    (dict match_id -> artefak, catatan).
    """
    semua: list[dict] = []
    catatan: list[str] = []
    for dokumen in dokumen_list:
        got = _artefak_dari_dokumen(dokumen)
        if not got:
            catatan.append(
                "dokumen analisis tidak berisi artefak nba_analysis "
                "(bukan artefak langsung maupun output analyze)"
            )
        semua.extend(got)
    per_laga, cat_dedup = terbaru_per_laga(semua)
    catatan.extend(cat_dedup)
    return per_laga, catatan


def median_pra_laga(
    artefak_per_laga: dict[str, dict],
) -> tuple[dict[str, float], list[str]]:
    """Median total pra-laga per match_id dari artefak yang terkumpul.

    Median = simulation.score_distribution.total.median. Artefak
    tanpa median dilewati + dicatat; tidak ditebak.
    """
    median: dict[str, float] = {}
    catatan: list[str] = []
    for match_id, art in sorted(artefak_per_laga.items()):
        sim = art.get("simulation") if isinstance(art, dict) else None
        total = (sim.get("score_distribution") or {}).get("total") or {}
        nilai = _angka(total.get("median")) if isinstance(total, dict) else None
        if nilai is not None:
            median[match_id] = nilai
        else:
            catatan.append(f"{match_id}: median pra-laga tidak ada di analisis")
    return median, catatan


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def _ekstrak_tiket(
    dokumen: dict,
) -> tuple[list[tuple[dict, str | None]], str | None]:
    """Kumpulkan tiket dari dokumen file tiket (3 bentuk yang didukung).

    (a) objek tiket tunggal (ada kunci "legs"); (b) pasangan
    {"insurance": {...}|null, "main": {...}|null} (tipe fallback dari
    nama kunci); (c) {"tickets": [...]}. Mengembalikan (daftar
    (tiket, tipe_fallback), None) atau ([], pesan error).
    """
    if not isinstance(dokumen, dict):
        return [], "file tiket harus berupa objek JSON"
    if isinstance(dokumen.get("legs"), list):
        pasangan = [(dokumen, None)]
    elif isinstance(dokumen.get("tickets"), list):
        pasangan = [(t, None) for t in dokumen["tickets"]]
    elif "insurance" in dokumen or "main" in dokumen:
        pasangan = [
            (dokumen["insurance"], "insurance"),
            (dokumen["main"], "main"),
        ]
        pasangan = [(t, fb) for t, fb in pasangan if t is not None]
    else:
        return [], (
            "file tiket tidak dikenali: butuh objek tiket tunggal "
            "(kunci 'legs'), pasangan {'insurance','main'}, atau "
            "{'tickets': [...]}"
        )
    if not pasangan:
        return [], "file tiket tidak berisi tiket apa pun"
    for tiket, _ in pasangan:
        if not isinstance(tiket, dict) or not isinstance(tiket.get("legs"), list):
            return [], "tiket tidak valid: tiap tiket butuh kunci 'legs'"
    return pasangan, None


def _tipe_tiket(tiket: dict, fallback: str | None) -> str | None:
    """Normalisasi jenis tiket ke 'insurance'/'main' (None bila tak dikenal).

    Menerima "insurance"/"Asuransi" dan "main"/"Utama" (huruf bebas).
    Bila kunci 'type' tidak dikenal, pakai fallback dari nama kunci
    pasangan {"insurance","main"}.
    """
    tipe = tiket.get("type")
    if isinstance(tipe, str):
        normal = _TIPE_TIKET.get(tipe.strip().lower())
        if normal is not None:
            return normal
    if fallback in ("insurance", "main"):
        return fallback
    return None


def _pasar_sim(analisis: dict) -> dict:
    """Dict markets simulasi artefak (kunci 'total_under_<garis>')."""
    simulasi = analisis.get("simulation")
    if not isinstance(simulasi, dict):
        return {}
    pasar = simulasi.get("markets")
    return pasar if isinstance(pasar, dict) else {}


def _median_total(analisis: dict) -> float | None:
    """Median total dari simulasi artefak (score_distribution.total)."""
    simulasi = analisis.get("simulation")
    if not isinstance(simulasi, dict):
        return None
    total = (simulasi.get("score_distribution") or {}).get("total")
    if not isinstance(total, dict):
        return None
    return _angka(total.get("median"))


def _garis_market(analisis: dict) -> float | None:
    """Garis total utama market dari artefak (market.main_total_line)."""
    market = analisis.get("market")
    if not isinstance(market, dict):
        return None
    return _angka(market.get("main_total_line"))


def _entri_tangga(analisis: dict, garis: float) -> dict | None:
    """Entri tangga Polymarket untuk garis Under itu (side 'under').

    None bila tangga tidak punya garis itu — volume tidak bisa
    diverifikasi (fail-closed di gate volume).
    """
    market = analisis.get("market")
    if not isinstance(market, dict):
        return None
    totals = market.get("totals")
    if not isinstance(totals, list):
        return None
    for entri in totals:
        if not isinstance(entri, dict) or entri.get("side") != "under":
            continue
        garis_entri = _angka(entri.get("line"))
        if garis_entri is not None and abs(garis_entri - garis) < 1e-9:
            return entri
    return None


def _audit_kaki(
    kaki: dict,
    tipe: str,
    artefak_per_laga: dict[str, dict],
    cfg: dict,
    min_prob: float,
    lantai_harga: float,
    ambang_gap: float,
    edge_tipis: float,
) -> dict:
    """Audit satu kaki tiket terhadap artefak analisis laganya."""
    nama_tiket = _NAMA_TIPE[tipe]
    hasil: dict = {
        "leg_id": kaki.get("leg_id") if isinstance(kaki, dict) else None,
        "match_id": kaki.get("match_id") if isinstance(kaki, dict) else None,
        "line": None,
        "selection": kaki.get("selection") if isinstance(kaki, dict) else None,
        "p_model": None,
        "p_model_sumber": None,
        # Angka file tiket (Gemini) — HANYA perbandingan, tidak dipakai
        # untuk verdict. Labelnya eksplisit di teks + JSON.
        "p_model_file_tiket": None,
        "p_model_file_tiket_catatan": (
            "angka dari file tiket (Gemini), BUKAN dari mesin — "
            "tidak dipakai untuk verdict"
        ),
        "harga_cents": None,
        "edge": None,
        "ev_pct": None,
        "price_label": None,
        "overpay": False,
        "volume_usd": None,
        "thin": None,
        "lean": {
            "median": None,
            "garis_market": None,
            "gap_points": None,
            "ambang_gap_points": ambang_gap,
            "berlaku": False,
            "probabilitas_pasar": None,
            "probabilitas_pasar_sumber": None,
            "di_bawah_target": None,
        },
        "gates": [],
        "verdict": "DATA_INCOMPLETE",
        "alasan": [],
        "flags": [],
    }
    if not isinstance(kaki, dict):
        hasil["alasan"].append("Kaki tiket bukan dict.")
        return hasil
    hasil["p_model_file_tiket"] = _angka(kaki.get("p_model"))

    def _gagal(alasan: str) -> dict:
        hasil["alasan"].append(alasan)
        return hasil

    if kaki.get("market") != "total_under":
        return _gagal(
            f"Pasar {kaki.get('market')!r} belum didukung audit " "(hanya total_under)."
        )
    garis = _urai_garis(kaki.get("selection"))
    if garis is None:
        return _gagal(
            f"Garis tidak bisa diurai dari selection: {kaki.get('selection')!r}."
        )
    hasil["line"] = garis
    harga = _angka(kaki.get("jup_price_cents"))
    if harga is None or not 0.0 < harga < 100.0:
        return _gagal(
            "Harga kaki (jup_price_cents) tidak ada atau tidak valid — "
            "edge tidak bisa dihitung."
        )
    hasil["harga_cents"] = harga
    match_id = kaki.get("match_id")
    analisis = artefak_per_laga.get(match_id) if isinstance(match_id, str) else None
    if analisis is None:
        return _gagal(
            f"Tidak ada artefak analisis untuk laga {match_id} — "
            "P_model mesin tidak bisa dihitung."
        )
    pasar_sim = _pasar_sim(analisis)
    kunci_sim = f"total_under_{garis:g}"
    p_model = _angka(pasar_sim.get(kunci_sim))
    if p_model is None or not 0.0 <= p_model <= 1.0:
        return _gagal(
            f"Simulasi tidak punya P_model untuk garis Under {garis:g} "
            f"(kunci {kunci_sim} tidak ada di artefak) — tidak ditebak."
        )
    hasil["p_model"] = p_model
    hasil["p_model_sumber"] = (
        f"sim markets {kunci_sim} artefak {match_id} "
        f"({analisis.get('generated_at') or 'tanpa stempel waktu'})"
    )

    # --- Edge, EV, label harga (dari P_model mesin). ---
    edge = p_model - harga / 100.0
    hasil["edge"] = edge
    ev_pct = (p_model * (100.0 / harga) - 1.0) * 100.0
    hasil["ev_pct"] = ev_pct
    try:
        label = price_labels_mod.label_for_ev(ev_pct, cfg)
    except (ValueError, config_mod.ConfigError) as exc:
        return _gagal(f"Label harga tidak bisa dihitung: {exc}")
    hasil["price_label"] = label
    overpay = edge < 0
    hasil["overpay"] = overpay
    if overpay:
        hasil["flags"].append("OVERPAY")

    # --- Volume tangga. ---
    entri = _entri_tangga(analisis, garis)
    thin = None
    volume = None
    if entri is not None:
        volume = _angka(entri.get("volume_usd"))
        thin = entri.get("thin") if isinstance(entri.get("thin"), bool) else None
    hasil["volume_usd"] = volume
    hasil["thin"] = thin
    if thin is True:
        hasil["flags"].append("VOLUME_TIPIS")

    # --- Condong-ke-market. ---
    median = _median_total(analisis)
    garis_market = _garis_market(analisis)
    lean = hasil["lean"]
    lean["median"] = median
    lean["garis_market"] = garis_market
    prob_pasar = None
    sumber_prob = None
    if entri is not None:
        harga_tangga = _angka(entri.get("price_cents"))
        if harga_tangga is not None:
            prob_pasar = harga_tangga / 100.0
            sumber_prob = "harga tangga Polymarket (price_cents)"
    if prob_pasar is None:
        # Fallback: harga tiket (jup.ag, sudah termasuk markup tipikal
        # ~0,5¢) — dicatat sumbernya.
        prob_pasar = harga / 100.0
        sumber_prob = "harga tiket (jup.ag)"
    lean["probabilitas_pasar"] = prob_pasar
    lean["probabilitas_pasar_sumber"] = sumber_prob
    if median is not None and garis_market is not None:
        gap = abs(median - garis_market)
        lean["gap_points"] = gap
        if gap > ambang_gap:
            lean["berlaku"] = True
            lean["di_bawah_target"] = prob_pasar < min_prob

    # --- Gate. ---
    keras_gagal: list[str] = []  # -> JANGAN_PASANG
    lunak_gagal: list[str] = []  # -> PERHATIAN
    gates = hasil["gates"]

    lolos_prob = p_model >= min_prob
    gates.append(
        {
            "gate": "peluang_minimum",
            "lolos": lolos_prob,
            "detail": (
                f"P_model {_fmt_persen(p_model)} vs minimum "
                f"{_fmt_persen(min_prob)} untuk {nama_tiket}"
            ),
        }
    )
    if not lolos_prob:
        keras_gagal.append(
            f"peluang model {_fmt_persen(p_model)} di bawah minimum "
            f"{_fmt_persen(min_prob)} untuk {nama_tiket}"
        )

    lolos_harga = harga >= lantai_harga
    gates.append(
        {
            "gate": "lantai_harga",
            "lolos": lolos_harga,
            "detail": f"harga {harga:g}¢ vs lantai {lantai_harga:g}¢",
        }
    )
    if not lolos_harga:
        keras_gagal.append(
            f"harga {harga:g}¢ di bawah lantai {lantai_harga:g}¢ " f"untuk {nama_tiket}"
        )

    if entri is None:
        detail_volume = "tangga tidak punya garis ini — volume tidak terverifikasi"
        gates.append({"gate": "volume", "lolos": False, "detail": detail_volume})
        if tipe == "insurance":
            keras_gagal.append(
                "volume garis tidak ditemukan di tangga — garis yang "
                "tidak bisa dipastikan dibeli bukan asuransi"
            )
        else:
            lunak_gagal.append(
                "volume garis tidak ditemukan di tangga — belum tentu "
                "bisa dibeli dengan harga itu"
            )
    elif thin is True:
        detail_volume = (
            "volume tipis (thin=True"
            + (
                f", volume ${volume:,.2f}"
                if volume is not None
                else ", volume tidak tercatat"
            )
            + ")"
        )
        gates.append({"gate": "volume", "lolos": False, "detail": detail_volume})
        if tipe == "insurance":
            keras_gagal.append(
                "volume tipis — garis yang tidak bisa dibeli bukan asuransi"
            )
        else:
            lunak_gagal.append("volume tipis — harga bisa bergerak saat dibeli")
    else:
        detail_volume = "volume tidak tipis" + (
            f" (${volume:,.2f})" if volume is not None else ""
        )
        gates.append({"gate": "volume", "lolos": True, "detail": detail_volume})

    if lean["berlaku"]:
        di_bawah = lean["di_bawah_target"]
        detail_lean = (
            f"selisih median vs garis market {_fmt_poin(lean['gap_points'])} "
            f"poin (> {_fmt_poin(ambang_gap)}); probabilitas pasar "
            f"{_fmt_persen(prob_pasar)}"
        )
        if tipe == "insurance":
            lolos_lean = not di_bawah
            gates.append(
                {
                    "gate": "condong_ke_market",
                    "lolos": lolos_lean,
                    "detail": detail_lean,
                }
            )
            if not lolos_lean:
                keras_gagal.append(
                    "model dan market beda jauh (condong-ke-market) dan "
                    f"probabilitas pasar {_fmt_persen(prob_pasar)} di bawah "
                    f"ambang {_fmt_persen(min_prob)}"
                )
        else:
            gates.append(
                {
                    "gate": "condong_ke_market",
                    "lolos": True,
                    "detail": detail_lean + " (Utama memakai model; hanya dicatat)",
                }
            )
            if di_bawah:
                lunak_gagal.append(
                    "model dan market beda jauh, dan probabilitas pasar "
                    f"{_fmt_persen(prob_pasar)} di bawah ambang "
                    f"{_fmt_persen(min_prob)}"
                )
    else:
        detail_lean = (
            "selisih median vs garis market "
            f"{_fmt_poin(lean['gap_points'])} poin "
            f"(≤ {_fmt_poin(ambang_gap)} — aturan tidak berlaku)"
            if lean["gap_points"] is not None
            else "median/garis market tidak ada — aturan tidak bisa dinilai"
        )
        gates.append(
            {"gate": "condong_ke_market", "lolos": True, "detail": detail_lean}
        )

    if label == price_labels_mod.MAHAL:
        gates.append(
            {
                "gate": "label_harga",
                "lolos": tipe != "insurance",
                "detail": f"label MAHAL (EV {ev_pct:+.1f}%)".replace(".", ","),
            }
        )
        if tipe == "insurance":
            keras_gagal.append(
                f"label MAHAL (EV {ev_pct:+.1f}%) — tidak boleh Asuransi".replace(
                    ".", ","
                )
            )
        else:
            lunak_gagal.append(f"label MAHAL (EV {ev_pct:+.1f}%)".replace(".", ","))
    else:
        gates.append(
            {
                "gate": "label_harga",
                "lolos": True,
                "detail": f"label {label} (EV {ev_pct:+.1f}%)".replace(".", ","),
            }
        )

    if overpay:
        lunak_gagal.append(
            f"OVERPAY: harga {harga:g}¢ di atas peluang model "
            f"{_fmt_persen(p_model)} (edge {_fmt_persen(edge)})"
        )
    elif edge < edge_tipis - _EPS:
        # Edge positif tapi tipis (di bawah ambang config) — bukan gate
        # keras, tapi layak dicatat sebagai perhatian (pelajaran DEN:
        # edge +2,5% adalah kaki terlemah yang akhirnya jebol).
        lunak_gagal.append(
            f"edge tipis: hanya {_fmt_persen(edge)} di atas harga "
            f"{harga:g}¢ — sedikit salah hitung model, kaki ini rugi"
        )

    if keras_gagal:
        hasil["verdict"] = "JANGAN_PASANG"
        hasil["alasan"].extend(keras_gagal)
        hasil["alasan"].extend(lunak_gagal)
    elif lunak_gagal:
        hasil["verdict"] = "PERHATIAN"
        hasil["alasan"].extend(lunak_gagal)
    else:
        hasil["verdict"] = "LOLOS"
    return hasil


def _audit_satu_tiket(
    tiket: dict,
    tipe: str | None,
    artefak_per_laga: dict[str, dict],
    cfg: dict,
    edge_tipis: float,
) -> dict:
    """Audit satu tiket (semua kakinya + agregat)."""
    hasil: dict = {
        "ticket_id": tiket.get("ticket_id"),
        "type": tipe,
        "type_nama": _NAMA_TIPE.get(tipe) if tipe else None,
        "stake": _angka(tiket.get("stake")),
        "multiplier": _angka(tiket.get("multiplier")),
        "verdict": "NO-GO",
        "p_gabungan": None,
        "ev": None,
        "kaki_terlemah": None,
        "legs": [],
        "alasan": [],
        "peringatan": [],
    }
    kaki_list = tiket.get("legs") or []
    if tipe is None:
        hasil["alasan"].append(
            "Jenis tiket tidak dikenal (bukan Asuransi/Utama) — "
            "ambang tidak bisa ditentukan."
        )
        for kaki in kaki_list:
            hasil["legs"].append(
                {
                    "leg_id": kaki.get("leg_id") if isinstance(kaki, dict) else None,
                    "match_id": (
                        kaki.get("match_id") if isinstance(kaki, dict) else None
                    ),
                    "verdict": "DATA_INCOMPLETE",
                    "alasan": ["Jenis tiket tidak dikenal — kaki tidak bisa dinilai."],
                }
            )
        return hasil
    if not kaki_list:
        hasil["alasan"].append("Tiket tidak punya kaki.")
        return hasil
    min_prob = _ambang(cfg, "tickets", tipe, "min_leg_prob")
    kunci_lantai = (
        "harga_min_asuransi_cents" if tipe == "insurance" else "harga_min_utama_cents"
    )
    lantai_harga = _ambang(cfg, "analis", kunci_lantai)
    ambang_gap = _ambang(cfg, "market_line_check", "total_gap_points")
    for kaki in kaki_list:
        hasil["legs"].append(
            _audit_kaki(
                kaki,
                tipe,
                artefak_per_laga,
                cfg,
                min_prob,
                lantai_harga,
                ambang_gap,
                edge_tipis,
            )
        )
    # --- Agregat. ---
    dengan_p = [k for k in hasil["legs"] if k.get("p_model") is not None]
    if dengan_p:
        terlemah = min(dengan_p, key=lambda k: k["p_model"])
        hasil["kaki_terlemah"] = {
            "leg_id": terlemah.get("leg_id"),
            "match_id": terlemah.get("match_id"),
            "line": terlemah.get("line"),
            "p_model": terlemah.get("p_model"),
        }
    if len(dengan_p) == len(hasil["legs"]):
        peluang = 1.0
        for kaki in hasil["legs"]:
            peluang *= kaki["p_model"]
        hasil["p_gabungan"] = peluang
        pengali = hasil["multiplier"]
        if pengali is not None and pengali > 0:
            hasil["ev"] = peluang * pengali - 1.0
        else:
            hasil["alasan"].append(
                "Pengali tiket tidak ada/tidak valid — EV tidak bisa dihitung."
            )
    else:
        hasil["alasan"].append(
            "Ada kaki tanpa P_model mesin — peluang gabungan + EV "
            "tidak bisa dihitung."
        )
    # --- Verdict tiket. ---
    ada_jangan = [k for k in hasil["legs"] if k["verdict"] == "JANGAN_PASANG"]
    ada_incomplete = [k for k in hasil["legs"] if k["verdict"] == "DATA_INCOMPLETE"]
    ada_perhatian = [k for k in hasil["legs"] if k["verdict"] == "PERHATIAN"]
    for kaki in ada_jangan:
        alasan = "; ".join(kaki["alasan"])
        hasil["alasan"].append(
            f"Kaki {kaki.get('match_id')} Under {kaki.get('line')}: "
            f"JANGAN_PASANG — {alasan}"
        )
    for kaki in ada_incomplete:
        alasan = "; ".join(kaki["alasan"])
        hasil["alasan"].append(
            f"Kaki {kaki.get('match_id')}: tidak bisa dinilai — {alasan}"
        )
    for kaki in ada_perhatian:
        alasan = "; ".join(kaki["alasan"])
        hasil["peringatan"].append(
            f"Kaki {kaki.get('match_id')} Under {kaki.get('line')}: "
            f"PERHATIAN — {alasan}"
        )
    if ada_jangan or ada_incomplete:
        hasil["verdict"] = "NO-GO"
    else:
        hasil["verdict"] = "GO"
    return hasil


def audit_tickets(
    dokumen_tiket: dict,
    dokumen_analisis: list[dict],
    cfg: dict | None = None,
) -> dict:
    """Audit seluruh tiket dalam satu dokumen file tiket.

    ``dokumen_tiket``: objek tiket tunggal, pasangan
    {"insurance","main"}, atau {"tickets": [...]}.
    ``dokumen_analisis``: daftar dokumen JSON analisis (artefak
    langsung atau output analyze, boleh banyak file). Mengembalikan
    dict audit (format "ticket_audit") — TIDAK mengubah file tiket.
    """
    cfg_penuh = _muat_cfg(cfg)
    edge_tipis, sumber_edge_tipis = _ambang_edge_tipis(cfg_penuh)
    artefak, catatan = kumpulkan_analisis(dokumen_analisis)
    tiket_list, error = _ekstrak_tiket(dokumen_tiket)
    hasil: dict = {
        "format": "ticket_audit",
        "generated_at": datetime.now(UTC).isoformat(),
        "config_version": (cfg_penuh.get("meta") or {}).get("version"),
        "ambang_edge_tipis_pct": round(edge_tipis * 100.0, 4),
        "ambang_edge_tipis_sumber": sumber_edge_tipis,
        "tickets": [],
        "notes": list(catatan),
        "asumsi": [
            "P_model tiap kaki dari sim markets artefak analisis "
            "(bukan dari angka p_model di file tiket — angka itu "
            "milik Gemini, bukan mesin).",
            "Kaki dianggap independen: peluang gabungan = produk "
            "P_model (sama seperti peracik).",
            "Label harga dihitung dari P_model mesin, bukan p_final.",
        ],
    }
    if error is not None:
        hasil["notes"].append(error)
        hasil["error"] = error
        return hasil
    for tiket, fallback in tiket_list:
        tipe = _tipe_tiket(tiket, fallback)
        hasil["tickets"].append(
            _audit_satu_tiket(tiket, tipe, artefak, cfg_penuh, edge_tipis)
        )
    return hasil


# ---------------------------------------------------------------------------
# Teks (Bahasa Indonesia sehari-hari)
# ---------------------------------------------------------------------------


def _baris_kaki(kaki: dict) -> list[str]:
    """Baris-baris teks untuk satu kaki hasil audit."""
    match_id = kaki.get("match_id") or "?"
    garis = kaki.get("line")
    teks_garis = f"Under {garis:g}" if garis is not None else "Under ?"
    verdict = kaki.get("verdict")
    p_model = kaki.get("p_model")
    harga = kaki.get("harga_cents")
    edge = kaki.get("edge")
    info = f"  • {match_id} {teks_garis} — {verdict}"
    if p_model is not None and harga is not None:
        info += (
            f" (peluang model {_fmt_persen(p_model)}, harga {harga:g}¢, "
            f"edge {_fmt_persen(edge)})"
        )
    if kaki.get("overpay"):
        info += " [OVERPAY]"
    if kaki.get("thin") is True:
        info += " [volume tipis]"
    baris = [info]
    for alasan in kaki.get("alasan") or []:
        baris.append(f"      Alasan: {alasan}")
    return baris


def render_audit_text(hasil: dict) -> str:
    """Rangkai teks hasil audit (Bahasa Indonesia sehari-hari)."""
    if not isinstance(hasil, dict):
        return "Hasil audit tidak tersedia."
    if hasil.get("error"):
        return f"Audit tidak bisa berjalan: {hasil['error']}"
    baris = [
        "AUDIT TIKET SEBELUM PASANG",
        "Peluang di bawah ini dari simulasi mesin (100.000x), bukan "
        "dari angka di file tiket.",
    ]
    for tiket in hasil.get("tickets") or []:
        nama = tiket.get("type_nama") or tiket.get("type") or "?"
        baris.append("")
        baris.append(f"TIKET {str(nama).upper()} ({tiket.get('ticket_id') or '?'})")
        baris.append(f"Verdict: {tiket.get('verdict')}")
        if tiket.get("p_gabungan") is not None:
            teks = f"Peluang menang tiket: {_fmt_persen(tiket['p_gabungan'])}"
            if tiket.get("ev") is not None:
                teks += f" • EV: {tiket['ev'] * 100:+.1f}%".replace(".", ",")
            if tiket.get("multiplier") is not None:
                teks += f" • Pengali x{tiket['multiplier']:.2f}".replace(".", ",")
            if tiket.get("stake") is not None:
                teks += f" • Modal {_fmt_uang(tiket['stake'])}"
            baris.append(teks)
        terlemah = tiket.get("kaki_terlemah") or {}
        if terlemah.get("p_model") is not None:
            baris.append(
                f"Kaki terlemah: {terlemah.get('match_id')} "
                f"Under {terlemah.get('line')} "
                f"({_fmt_persen(terlemah.get('p_model'))})"
            )
        for kaki in tiket.get("legs") or []:
            baris.extend(_baris_kaki(kaki))
        for alasan in tiket.get("alasan") or []:
            baris.append(f"  Alasan: {alasan}")
        for peringatan in tiket.get("peringatan") or []:
            baris.append(f"  Peringatan: {peringatan}")
    for catatan in hasil.get("notes") or []:
        baris.append(f"Catatan: {catatan}")
    return "\n".join(baris)
