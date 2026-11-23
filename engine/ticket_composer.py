"""Peracik tiket Asuransi + Utama dari artefak analisis NBA (Tahap 3 Langkah 3).

Fungsi utama: ``compose_tickets(analyses, rechecks, config, stake_total=...)``.

Masukan:
- ``analyses``: daftar artefak ``nba_analysis`` (format_version 1, satu
  per laga — satu slate). Tiap artefak membawa dua kaki Alt Under
  (``ticket`` "insurance" / "main").
- ``rechecks``: daftar laporan ``nba_recheck`` (format_version 1), satu
  per laga, atau None bila belum ada recheck. Putusan recheck TIDAK
  pernah dilonggarkan: kaki JANGAN_PASANG / DATA_INCOMPLETE tidak masuk
  tiket apapun alasannya.
- ``config``: dict playstyle.yaml (``config.load_playstyle()``); None
  berarti muat default.
- ``stake_total`` (wajib): total modal kedua tiket dalam USD. Dibagi
  menurut ``tickets.stake_split_default`` (default 50/50). Modal TIDAK
  pernah dikarang — tanpa ``stake_total``, fungsi menolak jalan.

Keluaran: ``{"insurance": tiket|None, "insurance_reason": str|None,
"main": tiket|None, "main_reason": str|None, "warnings": [...],
"summary": "..."}``. Tiket valid terhadap ``schemas/ticket.schema.json``
(divalidasi di sini; tiket yang gagal validasi menjadi None + alasan).
``summary`` ringkasan Bahasa Indonesia sehari-hari.

Aturan yang ditegakkan (lihat DECISIONS.md + laporan Langkah 2 §11):
- Garis berbeda untuk laga yang sama: bila suatu laga masuk kedua tiket,
  garis Asuransi HARUS lebih tinggi (lebih aman) dari garis Utama. Bila
  garisnya sama — atau garis Asuransi lebih rendah — laga itu hanya masuk
  SATU tiket, diprioritaskan Asuransi.
- TANPA_XG (B4, Tahap 3 Langkah 5): kaki dari analisis bola TANPA_XG
  (``no_xg``/``banned_from_insurance``) DILARANG masuk Tiket Asuransi,
  dan ambang peluang minimumnya naik ``no_xg.threshold_penalty_points``
  (+5 poin) untuk tiket mana pun. Penegakan memakai FLAG kaki, bukan
  format artefaknya — kaki TANPA_XG tidak pernah masuk Asuransi
  sekalipun artefaknya salah memberi tiket "insurance".
- Aturan condong-ke-market (keputusan user 20:36 WIB 2026-11-22): bila
  |median model - garis market| > ``market_line_check.total_gap_points``
  dan tidak ada alasan konkret ("Kenapa beda?"), probabilitas kaki
  Asuransi memakai harga market; harga market < ambang Asuransi (0,74)
  berarti kaki tidak lolos Asuransi. Bila ada recheck, putusan recheck
  yang dipakai (recheck sudah menerapkan aturan ini). Bila belum ada
  recheck, peracik menerapkannya sendiri dari artefak analisis.
- Hanya kaki TETAP_OK yang masuk tiket; PERHATIAN masuk hanya bila
  alasannya tercatat, dan ditandai di kaki (flag) + ringkasan.
- MAHAL tidak masuk Asuransi; boleh masuk Utama dengan label MAHAL.
- Target pengali dari config: Asuransi 2,0–2,5; Utama 3,0–5,0
  (maks 5,0 profil user 2026-11-22) dengan target lunak ≤ 3,5
  (fondasi harga & pengali, keputusan user 2026-11-23). Bila
  target tidak tercapai dengan kaki yang lolos, tiket menjadi None +
  alasan jujur — kaki yang tidak lolos TIDAK PERNAH dipaksakan masuk.
- Gate edge minimum Asuransi (insiden DEN@CHI 2026-11-23): kaki
  Asuransi dengan edge (p_final − harga venue/100 — definisi edge
  yang sama dengan yang dipakai ``_rakit_tiket``) di bawah
  ``tickets.insurance.min_edge_pct`` DITOLAK dari Asuransi (hard
  gate, seperti thin), alasan tercatat ("edge_kecil" + nilainya).
  Utama TIDAK kena gate ini. Nilai ambang adalah PROPOSAL (pola
  D12) — menunggu persetujuan user; lihat komentar di config.
- Gate skenario banjir Asuransi (insiden DEN@CHI 2026-11-23,
  keputusan user R1 + koreksi 09:52 WIB): kaki Asuransi (NBA
  total_under) lolos hanya bila P(Under) di skenario banjir
  TERBURUK (worst of banjir_3p/banjir_ft p90, engine/stress.py)
  >= ``tickets.insurance.min_leg_prob`` (0,74). Skenario dibaca
  dari ``tickets.insurance.stress_gate_scenario``
  ("banjir_terburuk"; "setan" didukung kode tapi BUKAN kriteria
  produksi — setan hanya deteksi kerapuhan). Garis yang gagal
  NAIK ke garis tahan skenario itu dari tangga (climb tercatat,
  alasan "banjir"); bila tidak ada garis tangga yang tahan, laga
  di-SKIP untuk Asuransi (alasan "tidak_ada_garis_tahan_banjir").
  Garis tahan yang thin TIDAK dipakai (aturan thin Asuransi yang
  sudah ada: thin = hard gate) -> SKIP — keputusan ini menunggu
  keberatan user/reviewer. Skenario yang tidak bisa dihitung (CDF
  tidak ada dsb.) -> kaki ditolak (fail-closed), bukan lolos
  diam-diam. Utama TIDAK kena gate ini. Kaki yang naik garis
  memakai p_final/EV garis lama (konservatif: peluang sebenarnya
  di garis baru lebih tinggi; peracik tidak menghitung ulang
  blend di garis baru — menunggu keputusan reviewer). Kaki bola
  dan total_over tidak kena gate ini (tidak ada model stress
  untuk keduanya).
- Lantai harga (filosofi user 2026-11-23): kaki NBA dengan harga
  venue (jup_estimated_cents, fallback price_cents) di bawah
  analis.harga_min_utama_cents (Utama) / analis.harga_min_asuransi_cents
  (Asuransi) — keduanya 75¢ — dicoret, alasan tercatat. Seleksi
  seharusnya sudah menjamin ini; peracik menegakkan sebagai pertahanan
  lapis kedua. Kaki BOLA tidak kena lantai harga (harga moneyline bola
  bukan proksi bantalan; pengecualian ini menunggu keberatan
  user/reviewer).
- Volume tipis = PENGHALANG KERAS Asuransi: kaki dengan thin=True
  dicoret dari Asuransi. Untuk Utama, kaki tipis BOLEH masuk tapi
  ditandai flag VOLUME_TIPIS + peringatan di warnings[] + ringkasan.
- Kriteria "yakin" Utama di atas target lunak (USULAN — menunggu
  keberatan user/reviewer): pengali Utama boleh melewati target lunak
  (≤ 3,5) sampai maks 5,0 HANYA bila SEMUA kaki p_final ≥ ambang yakin
  (tickets.main.yakin_min_leg_prob: 0,75) DAN semua kaki TETAP_OK
  (tanpa recheck = tidak yakin) DAN tidak ada anomali di laga
  kaki-kakinya. Subset yakin di atas lunak DIUTAMAKAN atas subset
  lunak (keputusan koordinator integrasi Tahap 4 — tanpa ini x5
  tidak pernah terjadi; menunggu keberatan). Di mode agresif
  (perintah eksplisit user per malam), kriteria ini tidak berlaku
  dan preferensi lunak dipertahankan.
- Utama tak terlindungi: bila Tiket Utama terracik tanpa Tiket
  Asuransi, warnings[] + ringkasan WAJIB memuat peringatan eksplisit
  "Tiket Utama tidak terlindungi" + alasan Asuransi tidak terbentuk +
  artinya (kalau Utama kalah, tidak ada pengembalian dari Asuransi).
- Peringatan jendela recheck: recheck lebih tua dari
  ``data.recheck_window_minutes`` (batas atas 60 menit) atau belum ada
  recheck sama sekali -> peringatan di ``warnings`` + ringkasan
  (peringatan saja, bukan larangan).

Batasan (dicatat, bukan disembunyikan):
- Peracik memakai kaki Alt Under dari artefak nba_analysis DAN kaki
  1X2/O-U gol/BTTS dari artefak soccer_analysis (Langkah 5). Moneyline
  NBA TIDAK diracik (profil user: hindari moneyline kecuali fakta
  sangat membuktikan pemenang; mesin belum punya kriteria itu) —
  moneyline 1X2 BOLA diracik karena itu pasar utama bola.
- Kaki bola (TANPA_XG) hanya masuk Tiket Utama, tidak pernah Asuransi
  (B4), dengan ambang peluang minimum +5 poin.
- EV tiket dari simulasi gabungan: kaki dari laga berbeda dianggap
  independen (P menang = Π p_final/keputusan); kaki dari laga yang sama
  (garis berbeda) berkorelasi — P(keduanya menang) = P(total ≤ garis
  terendah) dari distribusi sim laga itu. Peracik sendiri tidak pernah
  menumpuk dua kaki dari satu laga dalam satu tiket (tiap laga menyumbang
  paling banyak satu kaki per tiket), jadi korelasi tidak muncul dari
  racikan peracik; rumusnya tetap diimplementasikan di
  ``ticket_win_probability`` untuk pemakaian umum + tes.
- ``p_total_loss`` (P kedua tiket kalah) TIDAK dihitung — butuh sebaran
  gabungan antar-tiket yang berkorelasi lewat laga yang sama; field
  metrics-nya dibiarkan null.

SPESIFIKASI WIRING UNTUK KOORDINATOR (subcommand ``cli.py racik``):
    analyses = [json.loads(Path(f).read_text()) for f in args.analysis]
    rechecks = [json.loads(Path(f).read_text()) for f in args.recheck] \\
        if args.recheck else None
    hasil = compose_tickets(
        analyses,
        rechecks,
        config.load_playstyle(),
        stake_total=args.stake_total,
    )
    # hasil["insurance"] / hasil["main"]: dict tiket (siap dicatat
    # lewat `cli.py log --file`) atau None; alasan di
    # hasil["insurance_reason"] / hasil["main_reason"].
    # Tampilkan hasil["summary"]; bila hasil["warnings"] tidak kosong,
    # tampilkan juga + minta konfirmasi user sebelum mencatat.
    # Exit code yang disarankan: 0 bila minimal satu tiket terracik,
    # 1 bila keduanya None.
Contoh pemanggilan:
    python cli.py racik --analysis out/analisis_DET_ATL.json \\
        out/analisis_BOS_NYK.json --recheck out/recheck_DET_ATL.json \\
        --stake-total 20
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import config as config_mod
from engine import stress as stress_mod

REPO_ROOT = Path(__file__).resolve().parent.parent
_SKEMA_TIKET = REPO_ROOT / "schemas" / "ticket.schema.json"

# Pencarian subset kaki bersifat eksponensial; di atas batas ini hanya
# kaki teraman yang dipertimbangkan (slate NBA maksimal 15 laga/malam,
# jadi batas ini praktis tidak pernah terpicu).
_MAKS_KAKI_PENCARIAN = 18
_EPS = 1e-9

# Default lantai harga kaki (sen) + ambang "yakin" — nilai kontrak
# bersama filosofi user 2026-11-23, dipakai hanya bila kuncinya belum
# ada di config (sumber "default" dicatat di ringkasan). JANGAN ubah
# angka ini tanpa persetujuan user.
_DEFAULT_HARGA_MIN_CENTS = 75.0
_DEFAULT_YAKIN_MIN_LEG_PROB = 0.75

# Default gate edge minimum Asuransi (persen) — NILAI PROPOSAL yang
# sama dengan tickets.insurance.min_edge_pct di config (insiden DEN
# 2026-11-23; lihat komentar config). Dipakai hanya bila kuncinya
# belum ada di config (sumber "default" dicatat di ringkasan).
_DEFAULT_MIN_EDGE_INS_PCT = 3.5

# Kunci wajib minimal tiket (dipakai bila jsonschema tidak tersedia).
_KUNCI_WAJIB_TIKET = ("ticket_id", "type", "stake", "multiplier", "legs")
_KUNCI_WAJIB_KAKI = (
    "leg_id",
    "match_id",
    "sport",
    "market",
    "selection",
    "p_model",
    "p_market",
    "p_final",
    "jup_price_cents",
    "edge",
    "ev_pct",
    "status",
)


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


def _angka_config_atau_default(
    cfg: dict,
    kunci: tuple[str, ...],
    default: float,
    batas_bawah: float,
    batas_atas: float,
) -> tuple[float, str]:
    """Baca angka dari config; kunci hilang -> (default, "default").

    Kunci ADA tapi bukan angka / di luar batas -> ConfigError (config
    rusak, bukan data hilang). Dipakai untuk kunci baru Tahap 4 yang
    mungkin belum ada di config saat integrasi paralel (lantai harga,
    ambang yakin) — nilai defaultnya adalah keputusan user, bukan
    karangan, dan sumbernya dicatat di ringkasan.
    """
    try:
        nilai = config_mod.get_value(cfg, *kunci)
    except config_mod.ConfigError:
        return default, "default"
    hasil = _angka(nilai)
    if hasil is None or not (batas_bawah <= hasil <= batas_atas):
        raise config_mod.ConfigError(
            f"playstyle.yaml kunci {'.'.join(kunci)} tidak valid: {nilai!r} "
            f"(harus angka {batas_bawah:g}–{batas_atas:g})"
        )
    return hasil, "config"


def _lantai_harga(cfg: dict) -> tuple[dict[str, float], dict[str, str]]:
    """Lantai harga kaki (sen) per tiket + sumbernya ("config"/"default")."""
    lantai: dict[str, float] = {}
    sumber: dict[str, str] = {}
    for tiket, kunci in (
        ("insurance", "harga_min_asuransi_cents"),
        ("main", "harga_min_utama_cents"),
    ):
        nilai, asal = _angka_config_atau_default(
            cfg, ("analis", kunci), _DEFAULT_HARGA_MIN_CENTS, 0.0, 100.0
        )
        lantai[tiket] = nilai
        sumber[tiket] = asal
    return lantai, sumber


def _ambang_yakin(cfg: dict) -> tuple[float, str]:
    """Ambang p_final minimum kriteria "yakin" Utama + sumbernya."""
    return _angka_config_atau_default(
        cfg,
        ("tickets", "main", "yakin_min_leg_prob"),
        _DEFAULT_YAKIN_MIN_LEG_PROB,
        0.0,
        1.0,
    )


def _ambang_edge_asuransi(cfg: dict) -> tuple[float, str]:
    """Edge minimum kaki Asuransi (desimal) + sumbernya ("config"/"default").

    Dibaca dari ``tickets.insurance.min_edge_pct`` (persen; 3,5 berarti
    edge minimum +3,5 poin). Kunci hilang -> nilai proposal default
    (pola yang sama dengan lantai harga / ambang yakin).
    """
    nilai_pct, sumber = _angka_config_atau_default(
        cfg,
        ("tickets", "insurance", "min_edge_pct"),
        _DEFAULT_MIN_EDGE_INS_PCT,
        0.0,
        100.0,
    )
    return nilai_pct / 100.0, sumber


def _skenario_gate_asuransi(cfg: dict) -> str:
    """Nama skenario gate Asuransi dari config (fail-closed).

    Dibaca dari ``tickets.insurance.stress_gate_scenario``. Kunci
    hilang / bukan "banjir_terburuk" atau "setan" -> ConfigError
    (tanpa default dari kode). Nilai produksi: "banjir_terburuk"
    (koreksi user 09:52 WIB 2026-11-23: gate keras Asuransi adalah
    banjir p90; "setan" hanya deteksi kerapuhan, bukan kriteria
    produksi — jangan ubah nilai ini tanpa persetujuan user).
    """
    try:
        nilai = config_mod.get_value(
            cfg, "tickets", "insurance", "stress_gate_scenario"
        )
    except config_mod.ConfigError as exc:
        raise config_mod.ConfigError(
            "playstyle.yaml kehilangan kunci: "
            "tickets.insurance.stress_gate_scenario (gate banjir Asuransi)"
        ) from exc
    if nilai not in ("banjir_terburuk", "setan"):
        raise config_mod.ConfigError(
            "playstyle.yaml tickets.insurance.stress_gate_scenario harus "
            f"'banjir_terburuk' atau 'setan', dapat: {nilai!r}"
        )
    return nilai


def _kunci_skenario(hasil_stress: dict, skenario: str) -> tuple[str, str, str]:
    """Kunci output stress untuk satu skenario gate.

    Mengembalikan (kunci P di p_under, kunci garis tahan, kunci
    alasan tidak tahan): "banjir_terburuk" -> P dari
    hasil["banjir_terburuk"] ("banjir_3p"/"banjir_ft", mana yang
    gesernya terbesar) + "garis_tahan_banjir";
    "setan" -> p_under["setan"] + "garis_tahan_setan".
    Raise ValueError bila skenario tak dikenal atau hasil stress
    tidak menyebut skenario banjir terburuknya.
    """
    if skenario == "banjir_terburuk":
        terburuk = hasil_stress.get("banjir_terburuk")
        if terburuk not in ("banjir_3p", "banjir_ft"):
            raise ValueError(
                f"hasil skenario panas tanpa banjir_terburuk yang dikenal: {terburuk!r}"
            )
        return terburuk, "garis_tahan_banjir", "alasan_tidak_tahan_banjir"
    if skenario == "setan":
        return "setan", "garis_tahan_setan", "alasan_tidak_tahan_setan"
    raise ValueError(f"skenario gate tidak dikenal: {skenario!r}")


def _label_skenario(hasil_stress: dict, skenario: str) -> str:
    """Label skenario untuk pesan coret ("banjir terburuk (banjir_ft)")."""
    if skenario == "banjir_terburuk":
        terburuk = hasil_stress.get("banjir_terburuk")
        return (
            f"banjir terburuk ({terburuk})"
            if isinstance(terburuk, str) and terburuk
            else "banjir terburuk"
        )
    return skenario


def _stress_laga(
    analisis: dict, cfg: dict, cache: dict[str, tuple[dict | None, str | None]]
) -> tuple[dict | None, str | None]:
    """Hasil skenario_panas satu laga (cache per match_id).

    Mengembalikan (hasil, galat): hasil None + galat berisi pesan bila
    skenario tidak bisa dihitung (CDF tidak bisa dibangun, kunci
    config hilang, dsb.) — gate memakai ini untuk fail-closed, bukan
    crash. Kaki yang dihitung: kaki total_under bergaris dari artefak
    (tiket dikenali lewat ``_tiket_kaki``, termasuk turunan leg_id) —
    kaki tanpa tiket/garis tidak ikut, supaya satu kaki aneh tidak
    menggagalkan seluruh laga.
    """
    match_id = analisis.get("match_id")
    if isinstance(match_id, str) and match_id in cache:
        return cache[match_id]
    kaki: list[dict] = []
    for leg in analisis.get("legs") or []:
        if not isinstance(leg, dict):
            continue
        if leg.get("market_type") != "total_under":
            continue
        tiket = _tiket_kaki(leg)
        garis = _angka(leg.get("line"))
        if tiket is None or garis is None:
            continue
        kaki.append({"line": garis, "ticket": tiket})
    try:
        hasil = stress_mod.skenario_panas(analisis, kaki=kaki, cfg=cfg)
        pasangan: tuple[dict | None, str | None] = (hasil, None)
    except (ValueError, TypeError, config_mod.ConfigError) as exc:
        # TypeError: artefak/config bentuk tak terduga (mis. nilai
        # config None) — tetap fail-closed per laga, bukan crash
        # seluruh slate.
        pasangan = (None, str(exc))
    if isinstance(match_id, str):
        cache[match_id] = pasangan
    return pasangan


def _entri_stress_kaki(hasil_stress: dict, garis: float, tiket: str) -> dict | None:
    """Entri kaki (garis, tiket) di hasil skenario_panas, atau None."""
    for entri in hasil_stress.get("kaki") or []:
        if not isinstance(entri, dict):
            continue
        if entri.get("ticket") != tiket:
            continue
        garis_entri = _angka(entri.get("line"))
        if garis_entri is not None and abs(garis_entri - garis) < 1e-9:
            return entri
    return None


def _gate_skenario(
    hasil_stress: dict, entri_kaki: dict, skenario: str, ambang: float
) -> tuple[str, float | None, dict | None, str | None]:
    """Nilai satu kaki Asuransi di satu skenario stress (gate banjir/setan).

    Mengembalikan (putusan, p_skenario, garis_tahan, alasan):
    - ("lolos", p, None, None): P(Under) di skenario >= ambang.
    - ("naik", p, garis_tahan, None): P < ambang tapi ada garis tangga
      yang tahan skenario itu (garis_tahan = ringkasan entri tangga
      dari stress: line/price/thin/volume).
    - ("tolak", p, None, alasan): P tidak tersedia di skenario itu
      (p None), atau tidak ada garis tangga yang tahan.
    ``skenario``: "banjir_terburuk" atau "setan" (lihat
    ``_kunci_skenario``). Kunci skenario yang belum ada di output
    stress -> "tolak" (fail-closed), bukan lolos diam-diam.
    """
    kunci_p, kunci_garis, kunci_alasan = _kunci_skenario(hasil_stress, skenario)
    p_under = entri_kaki.get("p_under")
    p = _angka(p_under.get(kunci_p)) if isinstance(p_under, dict) else None
    if p is None:
        return (
            "tolak",
            None,
            None,
            f"P(Under) skenario {kunci_p} tidak tersedia di hasil skenario panas",
        )
    if p >= ambang:
        return "lolos", p, None, None
    garis_tahan = entri_kaki.get(kunci_garis)
    if not isinstance(garis_tahan, dict) or _angka(garis_tahan.get("line")) is None:
        alasan = entri_kaki.get(kunci_alasan)
        if not isinstance(alasan, str) or not alasan:
            alasan = (
                f"tidak ada garis tangga yang tahan skenario {kunci_p} "
                f"(P(Under) < {ambang:.0%} di semua garis)"
            )
        return "tolak", p, None, alasan
    return "naik", p, garis_tahan, None


def _kaki_naik_garis(kaki: dict, garis_tahan: dict, tangga: list[dict]) -> dict | None:
    """Salinan kaki yang garisnya naik ke garis tahan + climb tercatat.

    ``garis_tahan``: ringkasan entri tangga dari stress (line, harga,
    volume, thin). ``tangga``: entri Under terurut
    (``stress.tangga_under``) untuk hitung rungs. Mengembalikan None
    bila garis tahan tidak lebih tinggi dari garis kaki (tidak boleh
    "naik" ke bawah). Climb lama (dari cushion) dirangkai: from_line
    asal dipertahankan, rungs dijumlah, alasan digabung "+" (gaya
    cushion); alasan climb gate ini: "banjir".
    p_final/EV/cushion kaki TIDAK dihitung ulang di garis baru —
    nilainya masih garis lama (konservatif: peluang sebenarnya di
    garis baru lebih tinggi; edge/EV sebenarnya lebih baik).
    """
    dari = _angka(kaki.get("line"))
    ke = _angka(garis_tahan.get("line"))
    if dari is None or ke is None or ke <= dari:
        return None
    urut = [float(entri["line"]) for entri in tangga]

    def _indeks(garis_cari: float) -> int | None:
        for i, garis_tangga in enumerate(urut):
            if abs(garis_tangga - garis_cari) < 1e-9:
                return i
        return None

    indeks_dari = _indeks(dari)
    indeks_ke = _indeks(ke)
    rungs_baru = (
        indeks_ke - indeks_dari
        if indeks_dari is not None and indeks_ke is not None
        else None
    )
    climb_lama = kaki.get("climb") if isinstance(kaki.get("climb"), dict) else None
    if climb_lama is not None:
        dari_awal = _angka(climb_lama.get("from_line")) or dari
        rungs_lama = climb_lama.get("rungs")
        if (
            isinstance(rungs_lama, int)
            and not isinstance(rungs_lama, bool)
            and rungs_baru is not None
        ):
            rungs = rungs_baru + rungs_lama
        else:
            rungs = rungs_baru
        alasan_lama = climb_lama.get("reason")
        alasan = (
            f"{alasan_lama}+banjir"
            if isinstance(alasan_lama, str) and alasan_lama
            else "banjir"
        )
    else:
        dari_awal = dari
        rungs = rungs_baru
        alasan = "banjir"
    baru = dict(kaki)
    baru.update(
        {
            "line": ke,
            "price_cents": _angka(garis_tahan.get("price_cents")),
            "jup_estimated_cents": _angka(garis_tahan.get("jup_estimated_cents")),
            "volume_usd": _angka(garis_tahan.get("volume_usd")),
            "thin": garis_tahan.get("thin"),
            "climb": {
                "from_line": dari_awal,
                "to_line": ke,
                "rungs": rungs,
                "reason": alasan,
            },
        }
    )
    return baru


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


def _tiket_kaki(kaki: dict) -> str | None:
    """Tiket yang dituju satu kaki artefak ("insurance"/"main").

    Utamakan kunci ``ticket`` artefak; bila tidak ada, turunkan dari
    akhir ``leg_id`` seperti yang dilakukan CLI (laporan Langkah 2 §3b:
    kaki recheck belum membawa kunci ``ticket``).
    """
    tiket = kaki.get("ticket")
    if tiket in ("insurance", "main"):
        return tiket
    leg_id = kaki.get("leg_id", "")
    if isinstance(leg_id, str) and ":" in leg_id:
        akhir = leg_id.rsplit(":", 1)[-1]
        if akhir in ("insurance", "main"):
            return akhir
    return None


def _penalti_no_xg(kaki: dict, cfg: dict) -> float:
    """Penalti ambang TANPA_XG satu kaki, sebagai fraksi (0,05 = 5 poin).

    Diambil dari kaki itu sendiri (``threshold_penalty_points`` yang
    ditulis builder dari config), lalu dari config
    ``no_xg.threshold_penalty_points``. Bila keduanya tidak ada,
    0,05 — nilai B4/D-T1 yang didokumentasikan (arah fail-closed:
    ambang lebih ketat, bukan lebih longgar).
    """
    nilai = _angka(kaki.get("threshold_penalty_points"))
    if nilai is not None and nilai >= 0:
        return nilai / 100.0
    try:
        return _ambang(cfg, "no_xg", "threshold_penalty_points") / 100.0
    except config_mod.ConfigError:
        return 0.05


def _seleksi_kaki(kaki: dict, analisis: dict) -> str:
    """Teks seleksi kaki untuk tiket + ringkasan (Bahasa Indonesia).

    Bola: "Liverpool menang" / "Seri" / "Over 2,5 gol" / "Kedua tim
    mencetak gol". NBA: "Under 233,5" (tanpa kata "gol").
    """
    market_type = kaki.get("market_type")
    if analisis.get("format") == "soccer_analysis":
        home = analisis.get("home_team") or "kandang"
        away = analisis.get("away_team") or "tandang"
        if market_type == "moneyline_home":
            return f"{home} menang"
        if market_type == "moneyline_draw":
            return "Seri"
        if market_type == "moneyline_away":
            return f"{away} menang"
        if market_type in ("total_over", "total_under"):
            garis = _angka(kaki.get("line"))
            arah = "Over" if market_type == "total_over" else "Under"
            if garis is not None:
                teks_garis = (
                    f"{garis:g}".replace(".", ",")
                    if garis != int(garis)
                    else f"{int(garis)}"
                )
                return f"{arah} {teks_garis} gol"
            return arah
        if market_type == "btts_yes":
            return "Kedua tim mencetak gol"
        return str(market_type or "kaki")
    garis = _angka(kaki.get("line"))
    if garis is not None:
        return f"Under {garis:g}"
    return str(market_type or "kaki")


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


def _pasar_sim(analisis: dict) -> dict:
    """Dict markets simulasi artefak (kunci 'total_under_<garis>')."""
    simulasi = analisis.get("simulation")
    if not isinstance(simulasi, dict):
        return {}
    pasar = simulasi.get("markets")
    return pasar if isinstance(pasar, dict) else {}


def _harga_kaki(kaki: dict) -> tuple[float | None, float | None]:
    """Harga kaki: (harga venue jup.ag untuk pengali, harga market mentah).

    Harga venue = ``jup_estimated_cents`` bila ada, else ``price_cents``.
    Harga market mentah (untuk probabilitas market aturan condong-ke-
    market) = ``price_cents`` Polymarket bila ada — sengaja BUKAN estimasi
    jup.ag (keputusan user: pakai harga market mentah; recheck.py
    ``_probabilitas_market``) — fallback ke ``jup_estimated_cents`` bila
    ``price_cents`` tidak ada.
    """
    harga_poly = _angka(kaki.get("price_cents"))
    harga_jup = _angka(kaki.get("jup_estimated_cents"))
    venue = harga_jup if harga_jup is not None else harga_poly
    mentah = harga_poly if harga_poly is not None else harga_jup
    return venue, mentah


def combo_multiplier(harga_cents: list[float], spread_cut_pct: float) -> float:
    """Pengali kombo (DECISIONS.md D8): Π(100/harga¢) × (1 − potongan).

    ``harga_cents``: harga tiap kaki dalam sen (0 < harga < 100).
    ``spread_cut_pct``: potongan spread kombo dalam persen (config
    ``combo.spread_cut_pct``, 5,5).
    """
    if not harga_cents:
        raise ValueError("combo_multiplier butuh minimal satu harga kaki")
    pengali = 1.0
    for harga in harga_cents:
        if harga is None or not 0.0 < harga < 100.0:
            raise ValueError(f"harga kaki tidak valid untuk kombo: {harga!r}")
        pengali *= 100.0 / harga
    return pengali * (1.0 - spread_cut_pct / 100.0)


def ticket_win_probability(kaki_tiket: list[dict]) -> tuple[float, list[str]]:
    """Peluang menang tiket dari kaki-kakinya (simulasi gabungan).

    Tiap kaki adalah dict kandidat peracik (lihat ``_kumpulkan_kandidat``)
    dengan kunci ``match_id``, ``line``, ``decision_prob``, dan
    ``sim_markets`` (dict markets simulasi laganya). Kaki dari laga
    berbeda dianggap independen (P = Π decision_prob). Kaki dari laga
    yang SAMA berkorelasi: P(keduanya Under) = P(total ≤ garis terendah)
    dari distribusi sim laga itu (``sim_markets["total_under_<garis>"]``);
    bila persentil sim tidak tersedia, fallback ke Π decision_prob dengan
    catatan bahwa korelasi tidak dihitung.

    Mengembalikan (p_menang, catatan) — catatan kosong bila tidak ada
    fallback korelasi.
    """
    catatan: list[str] = []
    per_laga: dict[str, list[dict]] = {}
    for kandidat in kaki_tiket:
        per_laga.setdefault(kandidat["match_id"], []).append(kandidat)
    peluang = 1.0
    for match_id, grup in per_laga.items():
        if len(grup) == 1:
            peluang *= grup[0]["decision_prob"]
            continue
        garis_grup = [k.get("line") for k in grup]
        # Kaki tanpa kunci "leg" (bentuk lama, NBA sebelum Langkah 5)
        # dianggap total_under — semua kandidat lama adalah kaki
        # total_under; hanya market_type yang JELAS bukan total_under
        # yang memicu fallback.
        semua_total_under = all(
            k.get("leg", {}).get("market_type") in (None, "total_under") for k in grup
        )
        if not semua_total_under or any(g is None for g in garis_grup):
            # Korelasi hanya terdefinisi untuk dua kaki total_under dari
            # laga yang sama (P = P(total <= garis terendah)). Kaki 1X2/
            # BTTS/Over tidak punya rumus korelasi di sini -> produk
            # dengan catatan (peracik sendiri tidak pernah menumpuk dua
            # kaki dari satu laga dalam satu tiket).
            for kandidat in grup:
                peluang *= kandidat["decision_prob"]
            catatan.append(
                f"korelasi laga {match_id} tidak dihitung (kaki bukan "
                "total_under semua) — peluang menang dihitung seolah "
                "kaki-kakinya independen"
            )
            continue
        garis_terendah = min(k["line"] for k in grup)
        pasar = grup[0].get("sim_markets") or {}
        p_sim = _angka(pasar.get(f"total_under_{garis_terendah:g}"))
        if p_sim is not None and 0.0 <= p_sim <= 1.0:
            peluang *= p_sim
        else:
            for kandidat in grup:
                peluang *= kandidat["decision_prob"]
            catatan.append(
                f"korelasi laga {match_id} tidak dihitung (persentil sim "
                f"garis {garis_terendah:g} tidak ada di artefak) — peluang "
                "menang dihitung seolah kaki-kakinya independen"
            )
    return peluang, catatan


def validate_ticket(tiket: dict) -> str | None:
    """Validasi satu tiket terhadap schemas/ticket.schema.json.

    Mengembalikan None bila valid, else pesan galat singkat. Bila
    ``jsonschema`` tidak tersedia, pakai validasi minimal (kunci wajib +
    pengali > 1 + modal > 0 + minimal satu kaki) — pola yang sama dengan
    ``engine/nba_analysis.py``.
    """
    try:
        import jsonschema
    except ImportError:
        jsonschema = None  # type: ignore[assignment]
    if jsonschema is not None:
        try:
            skema = json.loads(_SKEMA_TIKET.read_text(encoding="utf-8"))
            jsonschema.validate(instance=tiket, schema=skema)
        except jsonschema.ValidationError as exc:
            return f"skema tiket: {exc.message}"
        except (OSError, ValueError) as exc:
            return f"skema tiket tidak bisa dibaca: {exc}"
        return None
    for kunci in _KUNCI_WAJIB_TIKET:
        if kunci not in tiket:
            return f"skema tiket: kunci wajib hilang: {kunci}"
    if not isinstance(tiket.get("legs"), list) or not tiket["legs"]:
        return "skema tiket: legs kosong"
    if _angka(tiket.get("multiplier")) is None or tiket["multiplier"] <= 1:
        return "skema tiket: multiplier harus > 1"
    if _angka(tiket.get("stake")) is None or tiket["stake"] <= 0:
        return "skema tiket: stake harus > 0"
    for kaki in tiket["legs"]:
        if not isinstance(kaki, dict):
            return "skema tiket: kaki bukan dict"
        for kunci in _KUNCI_WAJIB_KAKI:
            if kunci not in kaki:
                return f"skema tiket: kaki kehilangan kunci: {kunci}"
    return None


def _terbaru_per_laga(dokumen: list[dict], kunci_waktu: str) -> dict[str, dict]:
    """Deduplikasi dokumen per match_id — yang terbaru (kunci_waktu) menang."""
    hasil: dict[str, dict] = {}
    for dokumen_satu in dokumen:
        if not isinstance(dokumen_satu, dict):
            continue
        match_id = dokumen_satu.get("match_id")
        if not isinstance(match_id, str) or not match_id:
            continue
        lama = hasil.get(match_id)
        if lama is None:
            hasil[match_id] = dokumen_satu
            continue
        baru_waktu = _parse_iso(dokumen_satu.get(kunci_waktu))
        lama_waktu = _parse_iso(lama.get(kunci_waktu))
        if baru_waktu is not None and (lama_waktu is None or baru_waktu > lama_waktu):
            hasil[match_id] = dokumen_satu
    return hasil


def _kumpulkan_kandidat(
    analisis_per_laga: dict[str, dict],
    recheck_per_laga: dict[str, dict],
    cfg: dict,
    lantai: dict[str, float] | None = None,
    edge_min_ins: float | None = None,
) -> tuple[dict[str, list[dict]], dict[str, list[str]]]:
    """Saring kaki-kaki artefak menjadi kandidat per tiket.

    Mengembalikan (kandidat, coret):
    - kandidat: {"insurance": [...], "main": [...]} — dict kandidat
      (lihat ``ticket_win_probability`` untuk bentuknya) yang lolos
      semua filter.
    - coret: {"insurance": [...], "main": [...]} — alasan pencoretan
      per kaki, untuk alasan jujur bila tiket tidak terracik dan
      untuk transparansi di ringkasan.

    ``lantai``: lantai harga per tiket (None = baca dari config di
    sini via ``_lantai_harga``). ``edge_min_ins``: edge minimum kaki
    Asuransi dalam desimal (None = baca dari config di sini via
    ``_ambang_edge_asuransi``).
    """
    ambang_gap = _ambang(cfg, "market_line_check", "total_gap_points")
    min_prob = {
        "insurance": _ambang(cfg, "tickets", "insurance", "min_leg_prob"),
        "main": _ambang(cfg, "tickets", "main", "min_leg_prob"),
    }
    if lantai is None:
        lantai, _sumber_lantai = _lantai_harga(cfg)
    if edge_min_ins is None:
        edge_min_ins, _sumber_edge = _ambang_edge_asuransi(cfg)
    # Skenario gate Asuransi (fail-closed bila kunci hilang) + cache
    # skenario panas per laga (dihitung sekali per match_id, bukan
    # per kaki — lihat _stress_laga).
    skenario_gate = _skenario_gate_asuransi(cfg)
    stress_per_laga: dict[str, tuple[dict | None, str | None]] = {}
    tolak_mahal_ins = bool(
        config_mod.get_value(cfg, "optimizer", "exclude_mahal_from_insurance")
    )
    kandidat: dict[str, list[dict]] = {"insurance": [], "main": []}
    coret: dict[str, list[str]] = {"insurance": [], "main": []}

    for match_id, analisis in sorted(analisis_per_laga.items()):
        status = analisis.get("status")
        if status != "OK":
            for tiket in ("insurance", "main"):
                coret[tiket].append(
                    f"{match_id}: analisis berstatus {status or 'tidak diketahui'}"
                )
            continue
        recheck = recheck_per_laga.get(match_id)
        putusan_recheck: dict[str, dict] = {}
        recheck_at = None
        ada_anomali = bool(analisis.get("anomalies"))
        if recheck is not None:
            if recheck.get("anomalies"):
                ada_anomali = True
            recheck_at = _parse_iso(recheck.get("recheck_at"))
            for kaki_recheck in recheck.get("legs") or []:
                if isinstance(kaki_recheck, dict) and kaki_recheck.get("leg_id"):
                    putusan_recheck[kaki_recheck["leg_id"]] = kaki_recheck
        median = _median_total(analisis)
        garis_market = _garis_market(analisis)
        pasar_sim = _pasar_sim(analisis)
        for kaki in analisis.get("legs") or []:
            if not isinstance(kaki, dict):
                continue
            tiket = _tiket_kaki(kaki)
            if tiket not in ("insurance", "main"):
                continue
            leg_id = kaki.get("leg_id") or "?"
            garis = _angka(kaki.get("line"))
            label_kaki = _seleksi_kaki(kaki, analisis)
            if not kaki.get("meets"):
                alasan = kaki.get("reason") or "tidak memenuhi syarat"
                coret[tiket].append(f"{match_id} ({label_kaki}): {alasan}")
                continue
            market_type = kaki.get("market_type")
            if market_type in ("total_over", "total_under") and garis is None:
                # Kaki total tanpa garis tidak bisa dinilai; kaki 1X2/
                # BTTS memang tidak punya garis (line null itu sah).
                coret[tiket].append(f"{match_id} ({label_kaki}): garis total tidak ada")
                continue
            # --- Gate skenario banjir Asuransi (R1, insiden DEN
            # 2026-11-23). Hanya kaki NBA total_under Asuransi: bola
            # tidak punya model stress, total_over bukan Under.
            # Berjalan SEBELUM gate lain yang memakai garis/harga,
            # supaya kaki yang naik garis dinilai di garis barunya
            # (lantai harga, thin, edge). p_final/EV tetap garis lama
            # (konservatif — lihat _kaki_naik_garis).
            if (
                tiket == "insurance"
                and analisis.get("format") != "soccer_analysis"
                and market_type == "total_under"
            ):
                hasil_stress, galat_stress = _stress_laga(
                    analisis, cfg, stress_per_laga
                )
                if hasil_stress is None:
                    nama_skenario = "setan" if skenario_gate == "setan" else "banjir"
                    coret[tiket].append(
                        f"{match_id} ({label_kaki}): skenario {nama_skenario} "
                        f"tidak bisa dihitung ({galat_stress}) — kaki "
                        "Asuransi ditolak (fail-closed)"
                    )
                    continue
                entri_stress = _entri_stress_kaki(hasil_stress, garis, tiket)
                if entri_stress is None:
                    coret[tiket].append(
                        f"{match_id} ({label_kaki}): kaki tidak ada di hasil "
                        "skenario panas — kaki Asuransi ditolak (fail-closed)"
                    )
                    continue
                label_skenario = _label_skenario(hasil_stress, skenario_gate)
                putusan, p_skenario, garis_tahan, alasan_gate = _gate_skenario(
                    hasil_stress, entri_stress, skenario_gate, min_prob["insurance"]
                )
                if putusan == "tolak":
                    if p_skenario is None:
                        coret[tiket].append(
                            f"{match_id} ({label_kaki}): {alasan_gate} — kaki "
                            "Asuransi ditolak (fail-closed)"
                        )
                    else:
                        token_tidak_tahan = (
                            "tidak_ada_garis_tahan_banjir"
                            if skenario_gate == "banjir_terburuk"
                            else "tidak_ada_garis_tahan_setan"
                        )
                        coret[tiket].append(
                            f"{match_id} ({label_kaki}): {token_tidak_tahan} — "
                            f"P(Under) di skenario {label_skenario} "
                            f"{p_skenario * 100:.1f}% < "
                            f"{min_prob['insurance'] * 100:.0f}% dan {alasan_gate}"
                        )
                    continue
                if putusan == "naik":
                    garis_tahan_line = (
                        _angka(garis_tahan.get("line"))
                        if isinstance(garis_tahan, dict)
                        else None
                    )
                    if garis_tahan_line is None:
                        coret[tiket].append(
                            f"{match_id} ({label_kaki}): garis tahan "
                            f"{label_skenario} tidak valid — kaki Asuransi ditolak"
                        )
                        continue
                    if (
                        isinstance(garis_tahan, dict)
                        and garis_tahan.get("thin") is True
                    ):
                        # Garis tahan yang thin TIDAK dipakai (aturan
                        # thin Asuransi yang sudah ada: thin = hard
                        # gate) -> SKIP. Keputusan ini menunggu
                        # keberatan user/reviewer.
                        nama_garis_tahan = (
                            "garis tahan-setan"
                            if skenario_gate == "setan"
                            else "garis tahan-banjir"
                        )
                        coret[tiket].append(
                            f"{match_id} ({label_kaki}): {nama_garis_tahan} "
                            f"Under {garis_tahan_line:g} volume tipis — "
                            "tidak dipakai (aturan thin Asuransi); P(Under) "
                            f"di skenario {label_skenario} "
                            f"{p_skenario * 100:.1f}% < "
                            f"{min_prob['insurance'] * 100:.0f}% di garis awal"
                        )
                        continue
                    kaki_baru = _kaki_naik_garis(
                        kaki,
                        garis_tahan,
                        stress_mod.tangga_under(analisis.get("market")),
                    )
                    if kaki_baru is None:
                        coret[tiket].append(
                            f"{match_id} ({label_kaki}): garis tahan "
                            f"{label_skenario} tidak lebih tinggi dari garis "
                            "kaki — kaki Asuransi ditolak"
                        )
                        continue
                    kaki = kaki_baru
                    garis = _angka(kaki.get("line"))
                    label_kaki = _seleksi_kaki(kaki, analisis)
            p_final = _angka(kaki.get("p_final"))
            p_model = _angka(kaki.get("p_model"))
            p_market = _angka(kaki.get("p_market"))
            ev_pct = _angka(kaki.get("ev_pct"))
            harga_venue, harga_mentah = _harga_kaki(kaki)
            if p_final is None or p_model is None or ev_pct is None:
                coret[tiket].append(
                    f"{match_id} ({label_kaki}): peluang/EV tidak lengkap"
                )
                continue
            if p_market is None:
                # MODEL_ONLY: skema tiket mewajibkan p_market (angka,
                # bukan null), jadi kaki ini tidak bisa masuk tiket
                # yang valid — dicoret dengan alasan, bukan dikarang.
                coret[tiket].append(
                    f"{match_id} ({label_kaki}): tanpa pembanding pasar "
                    "(MODEL_ONLY) — tidak bisa masuk tiket"
                )
                continue
            if harga_venue is None or not 0.0 < harga_venue < 100.0:
                coret[tiket].append(f"{match_id} ({label_kaki}): harga venue tidak ada")
                continue
            # --- Lantai harga (filosofi 2026-11-23, pertahanan lapis
            # kedua — seleksi seharusnya sudah menjamin). Hanya kaki
            # NBA: harga moneyline bola bukan proksi bantalan.
            if (
                analisis.get("format") != "soccer_analysis"
                and harga_venue < lantai[tiket]
            ):
                coret[tiket].append(
                    f"{match_id} ({label_kaki}): harga {harga_venue:g}¢ di "
                    f"bawah lantai {lantai[tiket]:g}¢ untuk "
                    f"{'Asuransi' if tiket == 'insurance' else 'Utama'}"
                )
                continue
            # --- Volume tipis = PENGHALANG KERAS Asuransi. ---
            if tiket == "insurance" and kaki.get("thin") is True:
                coret[tiket].append(
                    f"{match_id} ({label_kaki}): volume tipis — garis "
                    "yang tidak bisa dibeli bukan asuransi"
                )
                continue
            label = kaki.get("price_label")
            if label == "MAHAL" and tiket == "insurance" and tolak_mahal_ins:
                coret[tiket].append(
                    f"{match_id} ({label_kaki}): label MAHAL — tidak "
                    "boleh masuk Asuransi"
                )
                continue
            # --- TANPA_XG (B4): dilarang Asuransi + ambang +5 poin. ---
            # Penegakan memakai FLAG kaki (no_xg/banned_from_insurance),
            # bukan format artefak — kaki TANPA_XG tidak pernah masuk
            # Asuransi sekalipun artefaknya salah memberi tiket
            # "insurance".
            no_xg = (
                kaki.get("no_xg") is True or kaki.get("banned_from_insurance") is True
            )
            penalti = _penalti_no_xg(kaki, cfg) if no_xg else 0.0
            if no_xg and tiket == "insurance":
                coret[tiket].append(
                    f"{match_id} ({label_kaki}): TANPA_XG — kaki bola "
                    "tanpa xG dilarang masuk Asuransi (B4)"
                )
                continue
            # --- Putusan recheck (tidak pernah dilonggarkan) ---
            putusan = None
            alasan_perhatian: list[str] = []
            prob_keputusan = p_final
            alasan_prob: str | None = None
            if recheck is not None:
                putusan = putusan_recheck.get(leg_id)
                if putusan is None:
                    # Laporan recheck wajib membawa satu entri per kaki
                    # analisis awal; bila hilang -> fail-closed.
                    coret[tiket].append(
                        f"{match_id} ({label_kaki}): kaki tidak ada di "
                        "laporan recheck"
                    )
                    continue
                verdict = putusan.get("verdict")
                if verdict in ("JANGAN_PASANG", "DATA_INCOMPLETE"):
                    alasan = "; ".join(putusan.get("reasons") or []) or verdict
                    coret[tiket].append(
                        f"{match_id} ({label_kaki}): recheck {verdict} — {alasan}"
                    )
                    continue
                if verdict == "PERHATIAN":
                    alasan_perhatian = list(putusan.get("reasons") or [])
                    if not alasan_perhatian:
                        coret[tiket].append(
                            f"{match_id} ({label_kaki}): PERHATIAN tanpa "
                            "alasan tercatat"
                        )
                        continue
                elif verdict != "TETAP_OK":
                    coret[tiket].append(
                        f"{match_id} ({label_kaki}): putusan recheck "
                        f"tidak dikenal: {verdict!r}"
                    )
                    continue
                # Recheck sudah menerapkan condong-ke-market; pakai
                # probabilitas yang dipakainya untuk keputusan kaki ini.
                if putusan.get("probability_used") == "market":
                    nilai_market = _angka(putusan.get("probability_value"))
                    if nilai_market is not None:
                        prob_keputusan = nilai_market
                        alasan_prob = (
                            "probabilitas market (aturan condong-ke-market "
                            "dari recheck)"
                        )
            else:
                # --- Tanpa recheck: peracik menerapkan condong-ke-market
                # sendiri (hanya untuk Asuransi; Utama selalu model). ---
                if (
                    tiket == "insurance"
                    and median is not None
                    and garis_market is not None
                ):
                    gap = abs(median - garis_market)
                    if gap > ambang_gap:
                        prob_market = (
                            harga_mentah / 100.0 if harga_mentah is not None else None
                        )
                        if prob_market is None:
                            coret[tiket].append(
                                f"{match_id} ({label_kaki}): selisih median "
                                f"vs garis market {gap:g} poin tapi harga "
                                "market tidak tersedia"
                            )
                            continue
                        if prob_market < min_prob["insurance"]:
                            coret[tiket].append(
                                f"{match_id} ({label_kaki}): condong-ke-market "
                                f"(selisih {gap:g} poin, tanpa alasan konkret) "
                                f"— harga market {prob_market * 100:.0f}% < "
                                f"{min_prob['insurance'] * 100:.0f}%"
                            )
                            continue
                        prob_keputusan = prob_market
                        alasan_prob = (
                            "probabilitas market (aturan condong-ke-market: "
                            f"selisih {gap:g} poin, tanpa recheck/alasan konkret)"
                        )
            # Ambang efektif: min_leg_prob + penalti TANPA_XG (bila ada).
            ambang_efektif = min_prob[tiket] + penalti
            if prob_keputusan < ambang_efektif:
                pesan = (
                    f"{match_id} ({label_kaki}): peluang keputusan "
                    f"{prob_keputusan * 100:.0f}% < minimum "
                    f"{ambang_efektif * 100:.0f}% untuk "
                    f"{'Asuransi' if tiket == 'insurance' else 'Utama'}"
                )
                if penalti > 0:
                    pesan += (
                        f" (ambang dasar {min_prob[tiket] * 100:.0f}% + "
                        f"{penalti * 100:.0f} poin TANPA_XG)"
                    )
                coret[tiket].append(pesan)
                continue
            # --- Gate edge minimum Asuransi (insiden DEN 2026-11-23).
            # Hard gate, hanya Asuransi — Utama tidak kena. Edge memakai
            # definisi yang sama dengan _rakit_tiket: p_final dikurangi
            # harga venue (jup.ag), BUKAN probabilitas keputusan
            # (condong-ke-market tidak mengubah edge).
            if tiket == "insurance":
                edge = p_final - harga_venue / 100.0
                if edge < edge_min_ins:
                    coret[tiket].append(
                        f"{match_id} ({label_kaki}): edge_kecil — edge "
                        f"{edge * 100:+.1f}% di bawah minimum "
                        f"{edge_min_ins * 100:.1f}% untuk Asuransi "
                        f"(p_final {p_final * 100:.1f}% − harga "
                        f"{harga_venue:g}¢)"
                    )
                    continue
            kandidat[tiket].append(
                {
                    "leg": kaki,
                    "analysis": analisis,
                    "match_id": match_id,
                    "ticket": tiket,
                    "line": garis,
                    "selection": label_kaki,
                    "sport": (
                        "football"
                        if analisis.get("format") == "soccer_analysis"
                        else "nba"
                    ),
                    "no_xg": no_xg,
                    "harga_jup": harga_venue,
                    "p_final": p_final,
                    "p_model": p_model,
                    "p_market": p_market,
                    "ev_pct": ev_pct,
                    "price_label": label,
                    "decision_prob": prob_keputusan,
                    "decision_alasan": alasan_prob,
                    "recheck_verdict": (
                        putusan.get("verdict") if putusan is not None else None
                    ),
                    "recheck_alasan": alasan_perhatian,
                    "recheck_at": recheck_at,
                    "thin": kaki.get("thin") is True,
                    "ada_anomali": ada_anomali,
                    "sim_markets": pasar_sim,
                }
            )
    # Satu laga menyumbang paling banyak satu kaki per tiket (bila artefak
    # membawa dua kaki untuk tiket yang sama, ambil yang peluangnya
    # tertinggi — penjaga agar hitungan Π peluang menang tetap sah).
    for tiket in ("insurance", "main"):
        terbaik: dict[str, dict] = {}
        for kand in kandidat[tiket]:
            lama = terbaik.get(kand["match_id"])
            if lama is None or kand["decision_prob"] > lama["decision_prob"]:
                terbaik[kand["match_id"]] = kand
        kandidat[tiket] = sorted(
            terbaik.values(),
            key=lambda k: (-k["decision_prob"], k["leg"].get("leg_id") or ""),
        )
    return kandidat, coret


def _yakin_utama(subset: list[dict], ambang_p: float) -> bool:
    """Kriteria "yakin" Utama di atas target lunak (USULAN — menunggu
    keberatan user/reviewer).

    True hanya bila subset tidak kosong DAN SEMUA kakinya: p_final >=
    ambang_p DAN putusan recheck TETAP_OK (tanpa recheck -> verdict
    None -> tidak yakin) DAN tidak ada anomali di laganya (artefak
    analisis maupun laporan recheck). PERHATIAN gagal lewat syarat
    TETAP_OK. Syarat ini monoton: menambah kaki tidak pernah mengubah
    subset yang tidak yakin menjadi yakin (dipakai pemangkasan di
    ``_pilih_subset``).
    """
    if not subset:
        return False
    for kand in subset:
        if kand["p_final"] < ambang_p:
            return False
        if kand.get("recheck_verdict") != "TETAP_OK":
            return False
        if kand.get("ada_anomali"):
            return False
    return True


def _salin_climb(climb) -> dict | None:
    """Salinan climb {from_line, to_line, rungs, reason} atau None.

    Hanya dict yang disalin (kunci yang dikenal, jenis divalidasi);
    bentuk lain dibuang — skema tiket hanya mengenal bentuk dict.
    """
    if not isinstance(climb, dict):
        return None
    rungs = climb.get("rungs")
    if isinstance(rungs, bool) or not isinstance(rungs, int):
        rungs = None
    alasan = climb.get("reason")
    return {
        "from_line": _angka(climb.get("from_line")),
        "to_line": _angka(climb.get("to_line")),
        "rungs": rungs,
        "reason": alasan if isinstance(alasan, str) else None,
    }


def _pilih_subset(
    kandidat: list[dict],
    mult_min: float,
    mult_max: float | None,
    soft_max: float,
    potongan_pct: float,
    yakin_fn=None,
) -> tuple[list[dict] | None, float, bool, bool]:
    """Pilih subset kaki terbaik untuk satu tiket (pencarian menyeluruh).

    Mengembalikan (subset | None, pengali_maks_yang_bisa_dicapai,
    dipangkas, terblokir_yakin). ``dipangkas`` True bila daftar
    kandidat dipotong ke ``_MAKS_KAKI_PENCARIAN`` kaki teraman.
    ``terblokir_yakin`` True bila ada subset dalam target yang
    ditolak HANYA karena kriteria "yakin" (``yakin_fn``) — untuk
    alasan jujur di ``compose_tickets``.

    ``yakin_fn`` (opsional): callable(subset) -> bool. Bila diberikan,
    subset dengan pengali di atas ``soft_max`` hanya boleh dicatat
    bila ``yakin_fn(subset)`` True; subset yang gagal dipangkas
    (menambah kaki tidak bisa membuatnya yakin — syarat "semua kaki"
    monoton). Subset pada/di bawah ``soft_max`` tidak kena syarat ini.

    Kriteria pilih (berurutan): (1) minimal 2 kaki bila ada subset
    ≥2 kaki yang masuk target — 1 kaki hanya bila tidak ada pilihan
    lain; (2) subset YAKIN di atas target lunak diutamakan (keputusan
    koordinator integrasi Tahap 4 — filosofi user 2026-11-23: x5 boleh
    bila mesin beneran yakin; tanpa preferensi ini gate yakin tidak
    pernah mengubah hasil karena subset lunak selalu ada — temuan
    struktural pekerja B; menunggu keberatan user/reviewer); lalu
    pengali dalam target lunak (≤ ``soft_max``); (3) peluang menang
    (Π peluang keputusan) terbesar; (4) pengali paling dekat ke tengah
    jendela target — kecuali di kelas yakin, di mana pengali lebih
    besar lebih baik (mesin yakin -> ambil bayaran); (5) kaki lebih
    banyak; (6) urutan leg_id (deterministik).
    """
    dipangkas = False
    if len(kandidat) > _MAKS_KAKI_PENCARIAN:
        kandidat = kandidat[:_MAKS_KAKI_PENCARIAN]
        dipangkas = True
    if not kandidat:
        return None, 0.0, dipangkas, False
    potongan = 1.0 - potongan_pct / 100.0
    # Urutkan berdasarkan kontribusi pengali (harga termurah dulu) agar
    # pemangkasan cabang pencarian efektif.
    urutan = sorted(
        kandidat,
        key=lambda k: (-(100.0 / k["harga_jup"]), k["leg"].get("leg_id") or ""),
    )
    faktor = [100.0 / k["harga_jup"] for k in urutan]
    n = len(urutan)
    # sufiks[i] = Π faktor dari i sampai akhir (untuk pemangkasan).
    sufiks = [1.0] * (n + 1)
    for i in range(n - 1, -1, -1):
        sufiks[i] = sufiks[i + 1] * faktor[i]
    pengali_maks = sufiks[0] * potongan
    tengah = (mult_min + soft_max) / 2.0

    def _kunci(subset: list[dict], mult: float, p_menang: float) -> tuple:
        di_atas_lunak = mult > soft_max + _EPS
        # Yakin hanya bermakna bila ada gate (yakin_fn); tanpa gate
        # (mode agresif) perilaku lama dipertahankan: lunak diutamakan.
        yakin = bool(yakin_fn) and di_atas_lunak and yakin_fn(subset)
        if yakin:
            kelas = 0
            jarak = -mult  # yakin -> ambil bayaran terbesar
        elif di_atas_lunak:
            kelas = 2  # di atas lunak tapi tidak yakin: tidak pernah
            # dicatat (dipangkas di _telusuri); pertahanan saja.
            jarak = abs(mult - tengah)
        else:
            kelas = 1
            jarak = abs(mult - tengah)
        return (
            kelas,
            -p_menang,
            jarak,
            -len(subset),
            tuple(sorted(k["leg"].get("leg_id") or "" for k in subset)),
        )

    terbaik: dict[str, tuple[tuple, list[dict]] | None] = {
        "banyak": None,
        "tunggal": None,
    }
    terblokir_yakin = False
    subset: list[dict] = []

    def _telusuri(indeks: int, produk: float, p_menang: float) -> None:
        nonlocal terblokir_yakin
        # Cabang tidak bisa mencapai target minimum -> pangkas.
        if produk * sufiks[indeks] * potongan < mult_min - _EPS:
            return
        if subset:
            mult = produk * potongan
            if mult_max is not None and mult > mult_max + _EPS:
                return  # menambah kaki hanya menaikkan pengali
            if mult >= mult_min - _EPS:
                if (
                    mult > soft_max + _EPS
                    and yakin_fn is not None
                    and not yakin_fn(subset)
                ):
                    # Di atas target lunak tapi tidak yakin -> tidak
                    # boleh dicatat; superset tidak bisa lolos yakin
                    # (syarat "semua kaki" monoton) -> pangkas.
                    terblokir_yakin = True
                    return
                kunci = _kunci(subset, mult, p_menang)
                slot = "banyak" if len(subset) >= 2 else "tunggal"
                lama = terbaik[slot]
                if lama is None or kunci < lama[0]:
                    terbaik[slot] = (kunci, list(subset))
        for i in range(indeks, n):
            # Cabang dari i tidak bisa mencapai minimum -> pangkas.
            if produk * sufiks[i] * potongan < mult_min - _EPS:
                break
            subset.append(urutan[i])
            _telusuri(i + 1, produk * faktor[i], p_menang * urutan[i]["decision_prob"])
            subset.pop()

    _telusuri(0, 1.0, 1.0)
    pilihan = terbaik["banyak"] or terbaik["tunggal"]
    if pilihan is None:
        return None, pengali_maks, dipangkas, terblokir_yakin
    return pilihan[1], pengali_maks, dipangkas, terblokir_yakin


def _tanggal_tiket(subset: list[dict]) -> str:
    """Tanggal tiket: game_date/match_date paling umum di kaki-kakinya (else hari ini UTC)."""
    tanggal = Counter()
    for kand in subset:
        game_date = kand["analysis"].get("game_date") or kand["analysis"].get(
            "match_date"
        )
        if isinstance(game_date, str) and game_date:
            tanggal[game_date] += 1
    if tanggal:
        terbanyak = max(tanggal.values())
        return sorted(d for d, c in tanggal.items() if c == terbanyak)[0]
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _rakit_tiket(
    tipe: str,
    subset: list[dict],
    stake: float,
    potongan_pct: float,
    catatan_tiket: list[str],
) -> tuple[dict, float, float, list[str]]:
    """Rakit satu dict tiket (sesuai ticket.schema.json) dari subset kaki.

    Mengembalikan (tiket, p_menang, ev_pct, catatan_korelasi).
    """
    harga = [k["harga_jup"] for k in subset]
    pengali = combo_multiplier(harga, potongan_pct)
    p_menang, catatan_korelasi = ticket_win_probability(subset)
    ev = p_menang * pengali - 1.0
    tanggal = _tanggal_tiket(subset)
    akhiran = "ins" if tipe == "Asuransi" else "utm"
    kaki_tiket = []
    for kand in subset:
        kaki = kand["leg"]
        match_id = kand["match_id"]
        tim = match_id.rsplit("_", 1)[0] if "_" in match_id else match_id
        flags: list[str] = []
        if kand["price_label"] == "MAHAL":
            flags.append("MAHAL")
        if kand.get("no_xg"):
            flags.append("TANPA_XG")
        if kand["recheck_verdict"] == "PERHATIAN":
            flags.append("PERHATIAN")
        if kand.get("thin"):
            flags.append("VOLUME_TIPIS")
        seleksi = kand.get("selection")
        if seleksi is None:
            # Kandidat dari pemanggil lama (tanpa "selection"): turunkan
            # dari garis bila ada, else nama market.
            garis = kand.get("line")
            seleksi = (
                f"Under {garis:g}"
                if garis is not None
                else str(kaki.get("market_type") or "kaki")
            )
        elif kand.get("sport", "nba") == "nba":
            # Format lama NBA dipertahankan: "Under 233.5 (DET@ATL)".
            seleksi = f"{seleksi} ({tim})"
        kaki_tiket.append(
            {
                "leg_id": kaki.get("leg_id"),
                "match_id": match_id,
                "sport": kand.get("sport", "nba"),
                "market": kaki.get("market_type") or "total_under",
                "selection": seleksi,
                "p_model": kand["p_model"],
                "p_market": kand["p_market"],
                "p_final": kand["p_final"],
                "jup_price_cents": kand["harga_jup"],
                "edge": round(kand["p_final"] - kand["harga_jup"] / 100.0, 4),
                "ev_pct": kand["ev_pct"],
                "cushion_points": _angka(kaki.get("cushion_points")),
                "cushion_reason": (
                    kaki.get("cushion_reason")
                    if isinstance(kaki.get("cushion_reason"), str)
                    else None
                ),
                "volume_usd": _angka(kaki.get("volume_usd")),
                "thin": (
                    kaki.get("thin") if isinstance(kaki.get("thin"), bool) else None
                ),
                "climb": _salin_climb(kaki.get("climb")),
                "status": "OK",
                "flags": flags,
                "jup_provider": "polymarket",
                "critic_light": None,
                "critic_notes": [],
                "anomaly_reason": None,
                "filter_reason": None,
                "result": None,
                "price_close_cents": None,
            }
        )
    catatan = list(catatan_tiket) + catatan_korelasi
    tiket = {
        "ticket_id": f"tkt-{tanggal}-{akhiran}",
        "type": tipe,
        "stake": stake,
        "multiplier": round(pengali, 4),
        "combo_spread_pct": potongan_pct,
        "legs": kaki_tiket,
        "metrics": {
            "p_win": round(p_menang, 4),
            "combined_ev_pct": round(ev * 100.0, 2),
            "combined_ev_usd": round(ev * stake, 2),
            "p_min_breakeven": round(1.0 / pengali, 4),
            "p_total_loss": None,
        },
        "notes": "; ".join(catatan) if catatan else None,
        "option_label": None,
        "slate_id": None,
        "placed_at": None,
        "result": "PENDING",
        "cashout_amount": None,
    }
    return tiket, p_menang, ev * 100.0, catatan_korelasi


def _usia_menit(recheck_at: datetime | None, sekarang: datetime) -> int | None:
    """Usia recheck dalam menit (dibulatkan ke bawah; None bila tak ada)."""
    if recheck_at is None:
        return None
    selisih = (sekarang - recheck_at).total_seconds() / 60.0
    return max(0, int(selisih))


def _peringatan_jendela(
    subset: list[dict],
    sekarang: datetime,
    basi_menit: float,
) -> tuple[list[str], bool]:
    """Peringatan jendela recheck untuk satu tiket.

    Mengembalikan (peringatan, ada_yang_belum_dicek). Recheck lebih tua
    dari ``basi_menit`` (batas atas jendela, 60 menit) atau belum ada
    recheck -> peringatan; bukan larangan.
    """
    peringatan: list[str] = []
    belum_dicek = False
    for kand in subset:
        usia = _usia_menit(kand["recheck_at"], sekarang)
        if usia is None:
            belum_dicek = True
            peringatan.append(
                f"Laga {kand['match_id']} belum dicek ulang — sebaiknya "
                "cek ulang sebelum pasang."
            )
        elif usia > basi_menit:
            peringatan.append(
                f"Recheck laga {kand['match_id']} sudah {usia} menit lalu — "
                "sebaiknya cek ulang sebelum pasang."
            )
    return peringatan, belum_dicek


def _fmt_uang(nilai: float) -> str:
    """Format USD singkat untuk ringkasan ($10 / $10,50)."""
    if abs(nilai - round(nilai)) < 0.005:
        return f"${nilai:.0f}"
    return f"${nilai:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ringkasan_tiket(
    nama: str,
    tiket: dict | None,
    alasan: str | None,
    subset: list[dict] | None,
    p_menang: float | None,
    ev_pct: float | None,
    belum_dicek: bool,
) -> list[str]:
    """Blok ringkasan satu tiket (Bahasa Indonesia sehari-hari)."""
    baris = [f"{nama.upper()}"]
    if tiket is None:
        baris.append(f"  Tidak diracik. Alasan: {alasan or 'tidak diketahui'}")
        return baris
    baris.append(
        f"  Modal {_fmt_uang(tiket['stake'])} — pengali x{tiket['multiplier']:.2f}"
    )
    for kand in subset or []:
        seleksi = kand.get("selection")
        if seleksi is None:
            garis = kand.get("line")
            seleksi = f"Under {garis:g}" if garis is not None else "kaki"
        info = (
            f"  • {seleksi} ({kand['match_id']}) — "
            f"harga {kand['harga_jup']:g}¢, peluang "
            f"{kand['decision_prob'] * 100:.0f}%"
        )
        if kand["price_label"]:
            info += f", {kand['price_label']}"
        if kand.get("no_xg"):
            info += ", TANPA_XG"
        if kand.get("thin"):
            info += ", volume tipis"
        if kand["recheck_verdict"] == "PERHATIAN":
            info += " [PERHATIAN: " + "; ".join(kand["recheck_alasan"]) + "]"
        if kand["decision_alasan"]:
            info += f" [{kand['decision_alasan']}]"
        baris.append(info)
    if p_menang is not None and ev_pct is not None:
        kembali = tiket["stake"] * tiket["multiplier"]
        baris.append(
            f"  Peluang menang tiket: {p_menang * 100:.0f}% • "
            f"EV: {ev_pct:+.0f}% • Bila menang, kembali {_fmt_uang(kembali)}"
        )
    if subset is not None and len(subset) == 1:
        baris.append("  Hanya berisi 1 kaki (tidak ada pilihan lain).")
    if belum_dicek:
        baris.append("  Status: belum dicek ulang.")
    return baris


def compose_tickets(
    analyses: list[dict],
    rechecks: list[dict] | None = None,
    config: dict | None = None,
    stake_total: float | None = None,
    now: datetime | str | None = None,
) -> dict:
    """Racik pasangan Tiket Asuransi + Tiket Utama dari satu slate.

    ``analyses``: daftar artefak ``nba_analysis`` dan/atau
    ``soccer_analysis`` (satu per laga). Kaki bola (TANPA_XG) hanya
    masuk Tiket Utama, tidak pernah Asuransi, dengan ambang peluang
    minimum +5 poin (B4).
    ``rechecks``: daftar laporan ``nba_recheck`` (satu per laga) atau
    None bila belum ada recheck — kaki tetap boleh dipakai, tapi tiket
    mendapat peringatan jendela + status "belum dicek ulang".
    ``config``: dict playstyle.yaml (None = muat default).
    ``stake_total``: total modal kedua tiket (USD) — WAJIB; tanpa ini
    fungsi menolak jalan (modal tidak pernah dikarang).
    ``now``: jam "sekarang" untuk peringatan jendela (datetime/str ISO;
    None = jam UTC saat ini). Parameter ini ada untuk tes.

    Mengembalikan ``{"insurance", "insurance_reason", "main",
    "main_reason", "warnings", "summary"}`` — lihat docstring modul.
    """
    if stake_total is None:
        raise ValueError(
            "stake_total wajib diisi (total modal kedua tiket, USD) — "
            "peracik tidak mengarang modal"
        )
    total_modal = _angka(stake_total)
    if total_modal is None or total_modal <= 0:
        raise ValueError(f"stake_total harus angka > 0, dapat: {stake_total!r}")
    cfg = _muat_cfg(config)
    sekarang = _parse_iso(now) if isinstance(now, str) else now
    if sekarang is None:
        sekarang = datetime.now(UTC)
    if sekarang.tzinfo is None:
        sekarang = sekarang.replace(tzinfo=UTC)

    potongan_pct = _ambang(cfg, "combo", "spread_cut_pct")
    jendela = config_mod.get_value(cfg, "data", "recheck_window_minutes")
    if not isinstance(jendela, list) or not jendela:
        raise config_mod.ConfigError(
            "playstyle.yaml data.recheck_window_minutes harus daftar angka"
        )
    nilai_jendela = [_angka(v) for v in jendela]
    if any(v is None for v in nilai_jendela):
        raise config_mod.ConfigError(
            "playstyle.yaml data.recheck_window_minutes berisi bukan-angka"
        )
    basi_menit = max(nilai_jendela)  # batas atas jendela = "basi" (60 menit)
    bagi_modal = config_mod.get_value(cfg, "tickets", "stake_split_default")
    try:
        porsi_ins = float(bagi_modal["insurance"])
        porsi_main = float(bagi_modal["main"])
    except (TypeError, KeyError, ValueError) as exc:
        raise config_mod.ConfigError(
            "playstyle.yaml tickets.stake_split_default harus " "{insurance, main}"
        ) from exc
    if abs((porsi_ins + porsi_main) - 1.0) > 1e-6:
        raise config_mod.ConfigError(
            "playstyle.yaml tickets.stake_split_default harus berjumlah 1"
        )
    mode_agresif = str(config_mod.get_value(cfg, "tickets", "mode")).lower() == (
        "aggressive"
    )
    try:
        target_main_soft = _angka(
            config_mod.get_value(cfg, "tickets", "main", "target_multiplier_max")
        )
    except config_mod.ConfigError:
        target_main_soft = None
    target = {
        "insurance": {
            "min": _ambang(cfg, "tickets", "insurance", "multiplier_min"),
            "max": _ambang(cfg, "tickets", "insurance", "multiplier_max"),
            "soft": _ambang(cfg, "tickets", "insurance", "multiplier_max"),
        },
        "main": {
            "min": _ambang(cfg, "tickets", "main", "multiplier_min"),
            "max": (
                None
                if mode_agresif
                else _ambang(cfg, "tickets", "main", "multiplier_max")
            ),
            # Target lunak (≤ 3,5 fondasi 2026-11-23); bila kunci belum
            # ada di config lama, fallback ke multiplier_max (bukan
            # angka baru).
            "soft": target_main_soft
            or _ambang(cfg, "tickets", "main", "multiplier_max"),
        },
    }
    must_cover = bool(
        config_mod.get_value(cfg, "tickets", "insurance", "must_cover_total_stake")
    )

    stake_ins = round(total_modal * porsi_ins, 2)
    stake_main = round(total_modal - stake_ins, 2)

    if not analyses:
        alasan = "Tidak ada analisis untuk diracik."
        return {
            "insurance": None,
            "insurance_reason": alasan,
            "main": None,
            "main_reason": alasan,
            "warnings": [],
            "summary": (
                "RACIKAN TIKET\nTidak ada analisis untuk diracik — "
                "jalankan analyze dulu untuk slate malam ini."
            ),
        }

    analisis_per_laga = _terbaru_per_laga(analyses, "generated_at")
    recheck_per_laga = _terbaru_per_laga(rechecks or [], "recheck_at")
    lantai, sumber_lantai = _lantai_harga(cfg)
    ambang_yakin, sumber_yakin = _ambang_yakin(cfg)
    ambang_edge, sumber_edge = _ambang_edge_asuransi(cfg)
    kandidat, coret = _kumpulkan_kandidat(
        analisis_per_laga,
        recheck_per_laga,
        cfg,
        lantai=lantai,
        edge_min_ins=ambang_edge,
    )

    warnings: list[str] = []
    hasil: dict = {}
    subset_terpilih: dict[str, list[dict] | None] = {}
    info_tiket: dict[str, tuple[float, float]] = {}
    belum_dicek: dict[str, bool] = {}

    # Asuransi dulu (prioritas bila ada konflik garis laga yang sama).
    subset_ins, maks_ins, pangkas_ins, _blokir_ins = _pilih_subset(
        kandidat["insurance"],
        target["insurance"]["min"],
        target["insurance"]["max"],
        target["insurance"]["soft"],
        potongan_pct,
    )
    if pangkas_ins:
        warnings.append(
            "Kaki Asuransi yang lolos lebih dari "
            f"{_MAKS_KAKI_PENCARIAN} — hanya "
            f"{_MAKS_KAKI_PENCARIAN} kaki teraman yang dipertimbangkan."
        )
    garis_ins_terpilih: dict[str, float] = {}
    if subset_ins is None:
        if not kandidat["insurance"]:
            alasan_ins = "Tidak ada kaki Asuransi yang lolos."
            if coret["insurance"]:
                alasan_ins += " " + "; ".join(coret["insurance"]) + "."
        elif maks_ins < target["insurance"]["min"] - _EPS:
            alasan_ins = (
                "Kaki Asuransi yang lolos hanya mencapai pengali "
                f"x{maks_ins:.2f} — target "
                f"x{target['insurance']['min']:.2f}–"
                f"x{target['insurance']['max']:.2f} tidak tercapai."
            )
        else:
            alasan_ins = (
                "Kombinasi kaki Asuransi yang lolos tidak ada yang masuk "
                f"target x{target['insurance']['min']:.2f}–"
                f"x{target['insurance']['max']:.2f} (pengali maksimum "
                f"yang bisa dicapai x{maks_ins:.2f})."
            )
        hasil["insurance"] = None
        hasil["insurance_reason"] = alasan_ins
        subset_terpilih["insurance"] = None
        belum_dicek["insurance"] = False
    else:
        garis_ins_terpilih = {k["match_id"]: k["line"] for k in subset_ins}
        catatan_ins: list[str] = []
        if len(subset_ins) == 1:
            catatan_ins.append("Tiket Asuransi hanya berisi 1 kaki.")
            warnings.append("Tiket Asuransi hanya berisi 1 kaki.")
        peringatan_ins, belum_ins = _peringatan_jendela(
            subset_ins, sekarang, basi_menit
        )
        warnings.extend(peringatan_ins)
        tiket_ins, p_ins, ev_ins, _ = _rakit_tiket(
            "Asuransi", subset_ins, stake_ins, potongan_pct, catatan_ins
        )
        galat = validate_ticket(tiket_ins)
        if galat is not None:
            hasil["insurance"] = None
            hasil["insurance_reason"] = f"Tiket Asuransi gagal validasi skema: {galat}"
            subset_terpilih["insurance"] = None
            belum_dicek["insurance"] = False
            warnings.append(f"Tiket Asuransi dibatalkan: {galat}")
        else:
            hasil["insurance"] = tiket_ins
            hasil["insurance_reason"] = None
            subset_terpilih["insurance"] = subset_ins
            info_tiket["insurance"] = (p_ins, ev_ins)
            belum_dicek["insurance"] = belum_ins
            if ev_ins < 0:
                warnings.append(
                    f"EV tiket Asuransi negatif ({ev_ins:+.0f}%) — secara "
                    "hitungan, tiket ini merugi dalam jangka panjang."
                )

    # Utama: buang kaki dari laga yang sudah masuk Asuransi bila garisnya
    # tidak lebih rendah dari garis Asuransi (kendala garis berbeda).
    kandidat_main = kandidat["main"]
    catatan_garis: list[str] = []
    if subset_terpilih["insurance"]:
        tersaring = []
        for kand in kandidat_main:
            garis_ins = garis_ins_terpilih.get(kand["match_id"])
            garis_main = kand.get("line")
            # Aturan garis berbeda hanya berlaku bila kedua kaki punya
            # garis (total); kaki 1X2/BTTS tidak punya garis dan tidak
            # pernah masuk Asuransi (TANPA_XG) sehingga tidak berkonflik.
            if (
                garis_ins is not None
                and garis_main is not None
                and garis_ins <= garis_main
            ):
                if garis_ins == garis_main:
                    catatan_garis.append(
                        f"Laga {kand['match_id']} hanya masuk Asuransi "
                        f"karena garisnya sama ({garis_ins:g})."
                    )
                else:
                    catatan_garis.append(
                        f"Laga {kand['match_id']} hanya masuk Asuransi "
                        f"karena garis Asuransi ({garis_ins:g}) tidak lebih "
                        f"aman dari garis Utama ({garis_main:g})."
                    )
                continue
            tersaring.append(kand)
        kandidat_main = tersaring
    # Utama: kriteria "yakin" membatasi pengali di atas target lunak —
    # kecuali mode agresif (perintah eksplisit user per malam).
    yakin_fn_main = (
        None if mode_agresif else (lambda subset: _yakin_utama(subset, ambang_yakin))
    )
    subset_main, maks_main, pangkas_main, blokir_yakin = _pilih_subset(
        kandidat_main,
        target["main"]["min"],
        target["main"]["max"],
        target["main"]["soft"],
        potongan_pct,
        yakin_fn=yakin_fn_main,
    )
    if pangkas_main:
        warnings.append(
            "Kaki Utama yang lolos lebih dari "
            f"{_MAKS_KAKI_PENCARIAN} — hanya "
            f"{_MAKS_KAKI_PENCARIAN} kaki teraman yang dipertimbangkan."
        )
    maks_main_teks = (
        f"x{target['main']['max']:.2f}"
        if target["main"]["max"] is not None
        else "tanpa batas (mode agresif)"
    )
    if subset_main is None:
        if not kandidat_main:
            alasan_main = "Tidak ada kaki Utama yang lolos."
            rincian = list(coret["main"]) + catatan_garis
            if rincian:
                alasan_main += " " + "; ".join(rincian) + "."
        elif maks_main < target["main"]["min"] - _EPS:
            alasan_main = (
                "Kaki Utama yang lolos hanya mencapai pengali "
                f"x{maks_main:.2f} — target "
                f"x{target['main']['min']:.2f}–{maks_main_teks} tidak tercapai."
            )
        else:
            alasan_main = (
                "Kombinasi kaki Utama yang lolos tidak ada yang masuk "
                f"target x{target['main']['min']:.2f}–{maks_main_teks} "
                f"(pengali maksimum yang bisa dicapai x{maks_main:.2f})."
            )
        if blokir_yakin:
            alasan_main += (
                " Kombinasi di atas target lunak "
                f"x{target['main']['soft']:.2f} ditolak karena kriteria "
                "'yakin' tidak terpenuhi (butuh tiap kaki p_final "
                f">= {ambang_yakin * 100:.0f}%, semua TETAP_OK, tanpa "
                "anomali)."
            )
        hasil["main"] = None
        hasil["main_reason"] = alasan_main
        subset_terpilih["main"] = None
        belum_dicek["main"] = False
    else:
        catatan_main: list[str] = list(catatan_garis)
        if len(subset_main) == 1:
            catatan_main.append("Tiket Utama hanya berisi 1 kaki.")
            warnings.append("Tiket Utama hanya berisi 1 kaki.")
        peringatan_main, belum_main = _peringatan_jendela(
            subset_main, sekarang, basi_menit
        )
        warnings.extend(peringatan_main)
        tiket_main, p_main, ev_main, _ = _rakit_tiket(
            "Utama", subset_main, stake_main, potongan_pct, catatan_main
        )
        galat = validate_ticket(tiket_main)
        if galat is not None:
            hasil["main"] = None
            hasil["main_reason"] = f"Tiket Utama gagal validasi skema: {galat}"
            subset_terpilih["main"] = None
            belum_dicek["main"] = False
            warnings.append(f"Tiket Utama dibatalkan: {galat}")
        else:
            hasil["main"] = tiket_main
            hasil["main_reason"] = None
            subset_terpilih["main"] = subset_main
            info_tiket["main"] = (p_main, ev_main)
            belum_dicek["main"] = belum_main
            for kand in subset_main:
                if kand.get("thin"):
                    seleksi = kand.get("selection") or "kaki"
                    warnings.append(
                        f"Kaki Utama {kand['match_id']} ({seleksi}) "
                        "bervolume tipis — harganya bisa bergerak saat "
                        "pasang, sebaiknya cek lagi sebelum submit."
                    )
            if ev_main < 0:
                warnings.append(
                    f"EV tiket Utama negatif ({ev_main:+.0f}%) — secara "
                    "hitungan, tiket ini merugi dalam jangka panjang."
                )

    # Syarat §6a: pengali Asuransi × modal Asuransi ≥ total modal.
    if (
        must_cover
        and hasil.get("insurance") is not None
        and hasil.get("main") is not None
    ):
        tiket_ins = hasil["insurance"]
        assert isinstance(tiket_ins, dict)
        if tiket_ins["multiplier"] * tiket_ins["stake"] < total_modal - _EPS:
            warnings.append(
                "Pengali Asuransi tidak cukup menutup total modal bila "
                "tiket Utama kalah."
            )

    # Utama terracik tanpa Asuransi -> WAJIB diperingatkan jelas
    # (filosofi 2026-11-23; 22 Nov warnings kosong = bug).
    if hasil.get("main") is not None and hasil.get("insurance") is None:
        warnings.append(
            "Tiket Utama tidak terlindungi — Tiket Asuransi tidak "
            f"terbentuk ({hasil.get('insurance_reason') or 'tanpa alasan'}). "
            "Kalau Tiket Utama kalah, tidak ada uang yang kembali dari "
            "Asuransi."
        )

    # Dedup (satu laga bisa muncul di kedua tiket -> peringatan sama).
    warnings = list(dict.fromkeys(warnings))

    # --- Ringkasan ---
    tanggal = _tanggal_tiket(
        (subset_terpilih["insurance"] or []) + (subset_terpilih["main"] or [])
    )
    baris = [
        f"RACIKAN TIKET — {tanggal}",
        f"Modal total {_fmt_uang(total_modal)} "
        f"(Asuransi {_fmt_uang(stake_ins)} + Utama {_fmt_uang(stake_main)})",
        "",
    ]
    p_ins, ev_ins = info_tiket.get("insurance", (None, None))
    baris += _ringkasan_tiket(
        "Asuransi",
        hasil.get("insurance"),
        hasil.get("insurance_reason"),
        subset_terpilih["insurance"],
        p_ins,
        ev_ins,
        belum_dicek["insurance"],
    )
    baris.append("")
    p_main, ev_main = info_tiket.get("main", (None, None))
    baris += _ringkasan_tiket(
        "Utama",
        hasil.get("main"),
        hasil.get("main_reason"),
        subset_terpilih["main"],
        p_main,
        ev_main,
        belum_dicek["main"],
    )
    perhatian = []
    for nama, subset in (
        ("Asuransi", subset_terpilih["insurance"]),
        ("Utama", subset_terpilih["main"]),
    ):
        for kand in subset or []:
            if kand["recheck_verdict"] == "PERHATIAN":
                seleksi = kand.get("selection") or "kaki"
                perhatian.append(
                    f"{nama} — {kand['match_id']} ({seleksi}): "
                    + "; ".join(kand["recheck_alasan"])
                )
    if perhatian:
        baris += ["", "PERHATIAN (baca sebelum pasang):"] + [
            f"  • {p}" for p in perhatian
        ]
    if warnings:
        baris += ["", "PERINGATAN:"] + [f"  • {w}" for w in warnings]
    tidak_lolos = [f"Asuransi — {c}" for c in coret["insurance"]] + [
        f"Utama — {c}" for c in coret["main"]
    ]
    if tidak_lolos:
        baris += ["", "KAKI YANG TIDAK LOLOS:"] + [f"  • {c}" for c in tidak_lolos]
    catatan_ringkas = list(catatan_garis)
    if sumber_lantai["insurance"] == "default" or sumber_lantai["main"] == "default":
        catatan_ringkas.append(
            f"Lantai harga kaki {_DEFAULT_HARGA_MIN_CENTS:g}¢ (nilai "
            "default — kunci analis.harga_min_utama_cents / "
            "analis.harga_min_asuransi_cents belum ada di config)."
        )
    if sumber_yakin == "default":
        catatan_ringkas.append(
            "Ambang 'yakin' Utama di atas "
            f"x{target['main']['soft']:.2f}: tiap kaki p_final "
            f">= {_DEFAULT_YAKIN_MIN_LEG_PROB * 100:.0f}% (nilai default "
            "— kunci tickets.main.yakin_min_leg_prob belum ada di config)."
        )
    if sumber_edge == "default":
        catatan_ringkas.append(
            "Gate edge minimum Asuransi "
            f"{_DEFAULT_MIN_EDGE_INS_PCT:g}% (nilai default — kunci "
            "tickets.insurance.min_edge_pct belum ada di config)."
        )
    catatan_ringkas.append(
        "Hanya kaki Alt Under (NBA) dan kaki 1X2/O-U gol/BTTS (bola) "
        "yang diracik; moneyline NBA tidak dipakai."
    )
    ada_bola = any(
        kand.get("sport") == "football"
        for subset in (subset_terpilih["insurance"], subset_terpilih["main"])
        for kand in (subset or [])
    )
    if ada_bola:
        catatan_ringkas.append(
            "Kaki bola (TANPA_XG) hanya masuk Tiket Utama, tidak pernah "
            "Asuransi, dengan ambang peluang +5 poin (B4)."
        )
    if mode_agresif:
        catatan_ringkas.append(
            "Mode agresif: pengali maksimum Utama bebas; kriteria "
            "'yakin' tidak berlaku (perintah eksplisit user)."
        )
    baris += ["", "CATATAN:"] + [f"  • {c}" for c in catatan_ringkas]
    hasil["warnings"] = warnings
    hasil["summary"] = "\n".join(baris)
    return hasil
