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
"insurance_fallback_option": opsi|None, "main": tiket|None,
"main_reason": str|None, "warnings": [...],
"skipped_matches": [{"match_id", "pemicu", "alasan"}],
"menunggu_lineup": [{"match_id", "bintang", "alasan"}],
"summary": "..."}``. Tiket valid terhadap ``schemas/ticket.schema.json``
(divalidasi di sini; tiket yang gagal validasi menjadi None + alasan).
``insurance_fallback_option`` adalah OPSI BERLABEL (v18.1 Patch #2,
keputusan user fallback (b) 2026-11-23 15:52 WIB) — BUKAN tiket:
tanpa ticket_id/type/stake, tidak pernah masuk ledger sebagai tiket.
``summary`` ringkasan Bahasa Indonesia sehari-hari.

Aturan yang ditegakkan (lihat DECISIONS.md + laporan Langkah 2 §11):
- TANPA KAKI KEMBAR (keputusan user 2026-11-23 12:20 WIB — insiden
  DEN@CHI 23 Nov: kaki Denver ada di KEDUA tiket sehingga keduanya
  mati bersamaan): satu laga (match_id) TIDAK BOLEH muncul di kedua
  tiket. MENGGANTIKAN aturan lama "garis berbeda" (laga boleh masuk
  kedua tiket asal garis Asuransi lebih tinggi — aturan itu yang
  membiarkan Denver membunuh kedua tiket). Alokasi vonis
  (``_alokasikan_laga``): laga HIJAU -> Asuransi dulu, laga
  menengah-hijau -> Utama, laga KUNING -> skip dari kedua tiket,
  laga tanpa vonis -> tanpa preferensi (disjoint ditegakkan di
  tingkat subset: Asuransi dipilih dulu, Utama membuang laga yang
  sudah masuk Asuransi). Bila satu tiket tidak mencapai target
  pengali karena pembagian ini -> tiket tidak terbentuk
  (fail-closed, jangan paksa).
- TANPA_XG (B4, Tahap 3 Langkah 5): kaki dari analisis bola TANPA_XG
  (``no_xg``/``banned_from_insurance``) DILARANG masuk Tiket Asuransi,
  dan ambang peluang minimumnya naik ``no_xg.threshold_penalty_points``
  (+5 poin) untuk tiket mana pun. Penegakan memakai FLAG kaki, bukan
  format artefaknya — kaki TANPA_XG tidak pernah masuk Asuransi
  sekalipun artefaknya salah memberi tiket "insurance".
- Aturan condong-ke-market (keputusan user 20:36 WIB 2026-11-22;
  ambang v18 dibaca dari ``calibration.lean_to_market_gap`` 5,0 —
  kunci lama ``market_line_check.total_gap_points`` DIHAPUS di
  config v18): bila |median model - garis market| > ambang dan
  tidak ada alasan konkret ("Kenapa beda?"), probabilitas kaki
  Asuransi memakai harga market; harga market < ambang Asuransi
  berarti kaki tidak lolos Asuransi. Bila ada recheck, putusan
  recheck yang dipakai (recheck sudah menerapkan aturan ini). Bila
  belum ada recheck, peracik menerapkannya sendiri dari artefak
  analisis. (Di v18, engine/vegas.py juga menyusutkan median ke
  arah pasar SEBELUM vonis — pertahanan berlapis, bukan pengganti:
  peracik tetap menegakkan aturan ini pada kaki fallback.)
- Hanya kaki TETAP_OK yang masuk tiket; PERHATIAN masuk hanya bila
  alasannya tercatat, dan ditandai di kaki (flag) + ringkasan.
- MAHAL tidak masuk Asuransi; boleh masuk Utama dengan label MAHAL.
- Target pengali dari config: Asuransi 2,0–2,5; Utama 3,0–5,0
  (maks 5,0 profil user 2026-11-22) dengan target lunak ≤ 3,5
  (fondasi harga & pengali, keputusan user 2026-11-23). Bila
  target tidak tercapai dengan kaki yang lolos, tiket menjadi None +
  alasan jujur — kaki yang tidak lolos TIDAK PERNAH dipaksakan masuk.
- Gate EV Asuransi + Utama (v18, MENGGANTIKAN gate edge minimum
  Asuransi 3,5% — keputusan user 2026-11-23 13:57 WIB atas
  proposal audit Gemini v18 §1.2: edge datar mustahil di ekor
  85-94¢): kaki Asuransi dengan EV < tickets.insurance.
  max_negative_ev_pct (-1%) DITOLAK dari Asuransi; kaki Utama
  dengan EV < tickets.main.max_negative_ev_pct (-2%) DITOLAK dari
  Utama. EV = p_final x (100/harga) - 1 (dari p_final kaki,
  definisi yang sama dengan ``_rakit_tiket``). Kunci v17
  tickets.insurance.min_edge_pct DIHAPUS — tidak ada lagi
  pembacanya di repo ini.
- Gate banjir Asuransi v18 (DUA ambang terpisah, menggantikan
  skenario tunggal banjir_terburuk >= 0,74): kaki Asuransi (NBA
  total_under) lolos hanya bila P(Under) di banjir 3P >=
  tickets.insurance.flood_3p_min (0,70) DAN di banjir FT >=
  tickets.insurance.flood_ft_min (0,65), keduanya dari CDF yang
  digeser (engine/stress.py, seperti sebelumnya). Garis yang gagal
  NAIK ke garis tahan terendah yang lolos KEDUA ambang + gate
  eksekusi (climb tercatat, alasan "banjir"); bila tidak ada garis
  tangga yang tahan, laga di-SKIP untuk Asuransi (alasan
  "tidak_ada_garis_tahan_banjir"). Skenario yang tidak bisa
  dihitung (CDF tidak ada dsb.) -> kaki ditolak (fail-closed),
  bukan lolos diam-diam. Utama TIDAK kena gate banjir (warning
  saja: P banjir kaki equilibrium dicatat + diperingatkan bila
  rapuh). Kaki yang naik garis memakai p_final/EV garis lama
  (konservatif: peluang sebenarnya di garis baru lebih tinggi;
  peracik tidak menghitung ulang blend di garis baru — menunggu
  keputusan reviewer). Kaki bola dan total_over tidak kena gate
  ini (tidak ada model stress untuk keduanya).
- Gate p_market Asuransi (v18): kaki Asuransi dengan p_market <
  tickets.insurance.min_p_market (0,80) DITOLAK (tidak boleh
  bertaruh ekstrem melawan pasar). Utama tidak kena gate ini.
- Gate eksekusi likuiditas + spread (v18, MENGGANTIKAN thin $100
  sebagai penghalang keras; revisi koordinator — gate volume_usd
  worker B diganti, lihat engine/equilibrium.cek_eksekusi): kaki
  NBA lolos hanya bila bukti eksekusinya lolos cek_eksekusi —
  likuiditas Gamma >= max(2 x stake_default, $25) = $30 (config
  execution; rumus engine/equilibrium.likuiditas_min_eksekusi)
  DAN spread bid/ask <= execution.max_spread_cents (5,0¢) DAN ask
  nyata (< 99¢). Bukti dibaca dari field kaki (liquidity_usd /
  bid_cents / ask_cents, disalin builder dari tangga) atau — bila
  kaki artefak lama tidak membawanya — dari entri tangga di garis
  kaki. Data tidak tercatat -> TIDAK lolos (fail-closed) + dicatat.
  Volume kumulatif < $100 dicatat sebagai info (bukan blokir):
  flag VOLUME_TIPIS + peringatan dipertahankan sebagai INFO di
  kedua tiket. Kaki BOLA tidak kena gate ini (kaki bola tidak
  membawa data volume — fail-closed di sana akan mematikan semua
  kaki bola; keputusan ini menunggu keberatan).
- TUNGGU_LINEUP (v18, timing gate Gemini §2 Q8): laga berstatus
  "tunggu_lineup" (atau bervonis "tunggu_lineup" dari
  engine/vonis.py — bintang Questionable) DIKELUARKAN dari
  kandidat final + dicatat terpisah di hasil["menunggu_lineup"]
  (match_id + bintang + alasan) — bukan KUNING, bukan kandidat.
- VETO PARSIAL +3 (v18, Gemini §2 Q3): bila evaluasi veto
  mencatat peringatan_parsial (hanya satu kondisi veto menyala —
  rim protector OUT + garis tinggi ATAU pace tinggi, bukan
  keduanya), kaki laga itu wajib +3 poin tambahan bantalan:
  garis yang dipilih (equilibrium atau kaki artefak) harus >=
  garis_acuan_normal (garis kaki artefak sebelum equilibrium)
  + 3,0. Bila tidak ada garis yang memenuhi, kaki dicoret dengan
  alasan tercatat. Tambahan 3,0 dibaca dari
  vonis.veto_parsial_bantalan_points (default 3,0 bila kunci
  belum ada di config — kunci ini belum ditulis worker A;
  lihat LAPORAN-GATE-V18.md).
- Titik equilibrium per kaki (keputusan user 2026-11-23 10:31 +
  10:41 WIB; engine/equilibrium.py): garis kaki NBA total_under
  DIPILIH ULANG dari tangga + CDF sim — garis yang dipilih MODE
  tiket itu di antara garis yang lolos SEMUA gate tiket itu:
  Asuransi "safety_first" (p_final tertinggi — keputusan user
  12:20 + 12:33 WIB), Utama "max_er" (expected return p_final x
  (100/harga) tertinggi). MENGGANTIKAN aturan lama "garis termurah
  yang lolos" (seleksi cushion + climb banjir): kaki equilibrium
  dibangun ulang dengan p_model/p_market/p_final/EV/label dihitung
  di garis baru (leg_id tidak berubah — recheck matching), climb
  dicatat alasan "equilibrium" bila garis berubah. Bila equilibrium
  TIDAK ADA (dihitung, tidak ada garis lolos) -> kaki ditolak dengan
  alasan diagnostik. Bila equilibrium TIDAK DIHITUNG (tanpa CDF /
  tanpa tangga / tanpa jangkar pasar) -> kaki artefak dipakai apa
  adanya (fallback, bukan penolakan). Gate banjir di bawah tetap
  berjalan sebagai pertahanan lapis kedua (lolos by construction
  pada kaki equilibrium). Equilibrium BOLEH melompati garis
  tahan-banjir yang thin ke garis tebal di atasnya (keputusan lama
  "tidak melompat" digantikan). Kaki BOLA tidak kena equilibrium
  (tidak ada model CDF/tangga yang sama).
- Optimasi gabungan Asuransi (v18.1 Patch #2 "Perangkap Plafon
  88,5¢", REFERENSI-PATCH-V18-1-GEMINI.md §1): safety-first dalam
  band 80–89¢ SELALU memetik plafon (P_final monoton naik terhadap
  harga) — di T2 v18 ketiga kaki Asuransi terkunci di 88,5¢
  (pengali maks x1,36). Karena itu komposer Asuransi TIDAK lagi
  memakai satu garis plafon per laga: dari SEMUA garis valid
  (``equilibrium.garis_valid_asuransi`` — garis dalam band yang
  lolos 100% gate Asuransi), komposer memilih kombinasi (1 garis
  per laga, 2–6 kaki; 1 kaki hanya sebagai jalan terakhir seperti
  ``_pilih_subset``) yang MEMAKSIMALKAN peluang cair gabungan
  (max Π P_final, dihitung dalam log: max Σ log P_final — dalam
  praktik Π decision_prob, yang sama dengan Π P_final kecuali
  condong-ke-market / recheck-market berlaku) dengan pengali bersih
  di [2,00x, 2,50x]. Pencarian memakai DP atas bucket log-pengali
  (langkah 0,001 log) melintasi laga — BUKAN brute force. Setiap
  garis kombinasi divalidasi keanggotaannya di valid_lines
  (fail-closed). Laga TANPA garis valid (tanpa equilibrium / garis
  valid kosong) menyumbang satu varian: kandidat v18-nya (garis
  yang lolos semua gate komposer). Flag config
  ``tickets.insurance.expose_all_valid_lines_to_composer`` (false)
  mengembalikan jalur ``_pilih_subset`` v18 persis (rollback).
- Fallback Asuransi (b) (v18.1, KEPUTUSAN USER 2026-11-23 15:52
  WIB — DECISIONS.md "Pilihan fallback Asuransi (b) + filosofi
  pasti menang"): bila tidak ada kombinasi >= 2,00x tanpa
  melanggar gate, komposer MELAPORKAN opsi terbaik di [1,80x,
  1,99x] (batas bawah dari
  ``tickets.insurance.target_multiplier_fallback_min`` 1,80; batas
  atas = target_min − 0,01) sebagai OPSI BERLABEL
  (``insurance_fallback_option``: label OPSI_DI_BAWAH_TARGET,
  pengali, peluang cair gabungan joint_p_final, detail per kaki,
  alasan tidak mencapai x2) — BUKAN tiket: tanpa ticket_id/type/
  stake, tidak masuk insurance_reason sebagai tiket, dan tidak
  bisa masuk ledger (gagal validasi skema tiket). Bila tidak ada
  juga kombinasi di [1,80x, 1,99x], opsi None + alasan menyebut
  pengali maksimum yang tercapai. Opsi TIDAK memesan laga dari
  Utama (bukan tiket — Utama diracik seolah Asuransi tidak
  terbentuk); bila opsi berbagi laga dengan Tiket Utama, warnings
  memuat peringatan tumpang-tindih (pelajaran DEN: satu laga bisa
  membunuh kedua tiket bila user memasang keduanya).
- Skip dari awal (keputusan user 2026-11-23 10:22 + 10:41 WIB;
  engine/skip_awal.py): laga NBA yang (a) tidak punya equilibrium di
  KEDUA tiket, atau (b) cocok pola Denver (flag setan + tidak ada
  garis tidak-tipis yang tahan banjir + garis acuan thin + edge
  kecil), atau (c) potensi OT tinggi -> di-SKIP dari KEDUA tiket
  sebelum kaki apa pun dinilai; alasan tercatat per tiket + daftar
  laga yang di-skip ada di hasil["skipped_matches"] + ringkasan.
  Tanpa data yang cukup -> tidak dievaluasi, BUKAN skip (skip adalah
  klaim positif). Flag config equilibrium.enabled / skip_awal.enabled
  (false) mengembalikan perilaku lama persis (untuk pengukuran A/B +
  rollback).
- Lantai harga (filosofi user 2026-11-23): kaki NBA dengan harga
  venue (jup_estimated_cents, fallback price_cents) di bawah
  analis.harga_min_utama_cents (Utama) / analis.harga_min_asuransi_cents
  (Asuransi) — keduanya 75¢ — dicoret, alasan tercatat. Seleksi
  seharusnya sudah menjamin ini; peracik menegakkan sebagai pertahanan
  lapis kedua. Kaki BOLA tidak kena lantai harga (harga moneyline bola
  bukan proksi bantalan; pengecualian ini menunggu keberatan
  user/reviewer).
- Volume tipis (v18): BUKAN lagi penghalang keras — gate eksekusi
  ($30, di atas) yang menentukan bisa-tidaknya garis dibeli.
  Kaki dengan thin=True yang lolos gate eksekusi BOLEH masuk
  kedua tiket, ditandai flag VOLUME_TIPIS + peringatan di
  warnings[] + ringkasan (INFO, bukan blokir).
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
from engine import equilibrium as equilibrium_mod
from engine import skip_awal as skip_awal_mod
from engine import stress as stress_mod
from engine import vonis as vonis_mod

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

# Default kunci v18 (dipakai HANYA bila kunci belum ada di cfg dict —
# pola yang sama dengan lantai harga / ambang yakin di atas; sumber
# "default" dicatat di ringkasan). Nilai-nilai ini BUKAN tebakan:
# SAMA PERSIS dengan config v18 yang ditulis worker A (keputusan
# user 2026-11-23 13:57 WIB + proposal audit Gemini v18 §3).
_DEFAULT_MAX_NEG_EV_INS_PCT = -1.0
_DEFAULT_MAX_NEG_EV_MAIN_PCT = -2.0
_DEFAULT_FLOOD_3P_MIN = 0.70
_DEFAULT_FLOOD_FT_MIN = 0.65
_DEFAULT_MIN_P_MARKET_INS = 0.80
_DEFAULT_LEAN_GAP_POINTS = 5.0
_DEFAULT_TIEBREAK_ER = 0.015
# Tambahan bantalan veto parsial (Gemini §2 Q3: hanya satu kondisi
# veto menyala -> wajib +3 poin). Kunci config
# vonis.veto_parsial_bantalan_points BELUM ditulis worker A saat
# modul ini ditulis — default 3,0 dipakai sampai kuncinya ada
# (lihat LAPORAN-GATE-V18.md).
_DEFAULT_BANTALAN_VETO_PARSIAL = 3.0

# --- Optimasi gabungan Asuransi, v18.1 Patch #2 ---
# Tujuan komposer Asuransi (satu-satunya yang didukung v18.1):
# maksimalkan peluang cair gabungan (max Π P_final) dalam jendela
# pengali target. Nilai lain di config -> ConfigError (fail-closed).
_TUJUAN_KOMPOSER_INS = "max_joint_p_final_within_target_multiplier"
# Batas bawah pengali opsi fallback (b) bila kunci belum ada di cfg
# dict (pola default v18 — SAMA PERSIS dengan config v18.1 yang
# ditulis worker B: keputusan user 2026-11-23 15:52 WIB).
_DEFAULT_FALLBACK_MIN = 1.80
# Label opsi fallback (b) — BUKAN tiket (tanpa ticket_id/type).
_LABEL_OPSI_FALLBACK = "OPSI_DI_BAWAH_TARGET"
# Langkah diskretisasi bucket log-pengali DP (0,001 log ≈ 0,1%
# pengali — halus; pemilihan akhir selalu dicek dengan pengali
# EKSAK dari harga, jadi pembulatan bucket tidak pernah meloloskan
# kombinasi di luar jendela).
_DP_LANGKAH_LOG = 0.001
# Jumlah kaki per kombinasi Asuransi (spesifikasi Patch #2): 2–6.
# 1 kaki hanya sebagai jalan terakhir (perilaku _pilih_subset —
# di config live tidak mungkin: 1 kaki maks x1,26 di lantai 75¢).
_DP_MAKS_KAKI = 6
_DP_MIN_KAKI_OPSI = 2
# Jarak batas atas fallback dari target minimum (presisi sen):
# fallback_max = multiplier_min - 0,01 (1,99 dengan target 2,00).
_FALLBACK_JARAK_ATAS = 0.01

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


def _ambang_ev(cfg: dict, tiket: str) -> tuple[float, str]:
    """EV minimum satu tiket (persen) + sumbernya ("config"/"default").

    Dibaca dari ``tickets.<tiket>.max_negative_ev_pct`` (v18,
    MENGGANTIKAN gate edge Asuransi): Asuransi -1,0%, Utama -2,0%.
    Kunci hilang -> default v18 (pola yang sama dengan lantai
    harga / ambang yakin).
    """
    default = (
        _DEFAULT_MAX_NEG_EV_INS_PCT
        if tiket == "insurance"
        else _DEFAULT_MAX_NEG_EV_MAIN_PCT
    )
    return _angka_config_atau_default(
        cfg,
        ("tickets", tiket, "max_negative_ev_pct"),
        default,
        -100.0,
        100.0,
    )


def _ambang_banjir(cfg: dict) -> tuple[float, float]:
    """Ambang banjir Asuransi v18: (P banjir 3P min, P banjir FT min).

    Dibaca dari tickets.insurance.flood_3p_min (0,70) /
    flood_ft_min (0,65). Kunci hilang -> default v18. Nilai di
    luar 0-1 -> ConfigError.
    """
    ambang_3p, _ = _angka_config_atau_default(
        cfg,
        ("tickets", "insurance", "flood_3p_min"),
        _DEFAULT_FLOOD_3P_MIN,
        0.0,
        1.0,
    )
    ambang_ft, _ = _angka_config_atau_default(
        cfg,
        ("tickets", "insurance", "flood_ft_min"),
        _DEFAULT_FLOOD_FT_MIN,
        0.0,
        1.0,
    )
    return ambang_3p, ambang_ft


def _ambang_p_market_ins(cfg: dict) -> float:
    """p_market minimum kaki Asuransi (v18, default 0,80)."""
    nilai, _ = _angka_config_atau_default(
        cfg,
        ("tickets", "insurance", "min_p_market"),
        _DEFAULT_MIN_P_MARKET_INS,
        0.0,
        1.0,
    )
    return nilai


def _optimasi_asuransi_aktif(cfg: dict) -> bool:
    """Flag optimasi gabungan Asuransi v18.1 Patch #2 + validasi tujuan.

    True bila ``tickets.insurance.expose_all_valid_lines_to_composer``
    true (default True bila kunci belum ada di cfg dict — nilai
    produksi v18.1) DAN ``composer_objective`` adalah tujuan yang
    didukung (``max_joint_p_final_within_target_multiplier``;
    default nilai itu bila kunci belum ada). Tujuan tidak dikenal
    -> ConfigError (fail-closed: tujuan yang salah diam-diam lebih
    buruk daripada error keras — pola _mode_equilibrium). Nilai
    flag bukan bool -> ConfigError.
    """
    try:
        nilai = config_mod.get_value(
            cfg, "tickets", "insurance", "expose_all_valid_lines_to_composer"
        )
    except config_mod.ConfigError:
        nilai = True
    if not isinstance(nilai, bool):
        raise config_mod.ConfigError(
            "playstyle.yaml tickets.insurance."
            "expose_all_valid_lines_to_composer harus bool, dapat: "
            f"{nilai!r}"
        )
    try:
        tujuan = config_mod.get_value(cfg, "tickets", "insurance", "composer_objective")
    except config_mod.ConfigError:
        tujuan = _TUJUAN_KOMPOSER_INS
    if tujuan != _TUJUAN_KOMPOSER_INS:
        raise config_mod.ConfigError(
            "playstyle.yaml tickets.insurance.composer_objective harus "
            f"{_TUJUAN_KOMPOSER_INS!r}, dapat: {tujuan!r}"
        )
    return nilai


def _ambang_fallback_ins(cfg: dict, mult_min: float) -> float:
    """Batas bawah pengali opsi fallback (b) Asuransi (v18.1).

    Dibaca dari ``tickets.insurance.target_multiplier_fallback_min``
    (1,80; keputusan user 2026-11-23 15:52 WIB). Kunci hilang ->
    default 1,80. Harus 1,0 < fallback_min < mult_min (bila tidak,
    config tidak konsisten -> ConfigError, bukan diam-diam dipakai).
    """
    nilai, _ = _angka_config_atau_default(
        cfg,
        ("tickets", "insurance", "target_multiplier_fallback_min"),
        _DEFAULT_FALLBACK_MIN,
        1.0,
        10.0,
    )
    if not (1.0 < nilai < mult_min):
        raise config_mod.ConfigError(
            "playstyle.yaml tickets.insurance."
            "target_multiplier_fallback_min harus di antara 1,0 dan "
            f"multiplier_min ({mult_min:g}), dapat: {nilai}"
        )
    return nilai


def _ambang_gap_market(cfg: dict) -> float:
    """Ambang selisih median-vs-pasar aturan condong-ke-market (poin).

    Dibaca dari calibration.lean_to_market_gap (v18, 5,0 poin);
    kunci lama market_line_check.total_gap_points DIHAPUS di
    config v18. Kunci hilang -> default 5,0.
    """
    nilai, _ = _angka_config_atau_default(
        cfg,
        ("calibration", "lean_to_market_gap"),
        _DEFAULT_LEAN_GAP_POINTS,
        0.0,
        100.0,
    )
    return nilai


def _bantalan_veto_parsial(cfg: dict) -> tuple[float, str]:
    """Tambahan bantalan veto parsial (poin) + sumbernya.

    Dibaca dari vonis.veto_parsial_bantalan_points (v18, +3 poin —
    Gemini §2 Q3; kunci ditulis koordinator saat integrasi v18).
    Kunci hilang -> default 3,0.
    """
    return _angka_config_atau_default(
        cfg,
        ("vonis", "veto_parsial_bantalan_points"),
        _DEFAULT_BANTALAN_VETO_PARSIAL,
        0.0,
        20.0,
    )


def _flag_enabled(cfg: dict, section: str) -> bool:
    """Baca flag ``<section>.enabled`` dari config (default True).

    Kunci/section hilang -> True (nilai produksi; config yang dikirim
    selalu membawa kunci ini — REQUIRED di config.py). Nilai bukan
    bool -> ConfigError (config rusak, bukan default).
    """
    try:
        nilai = config_mod.get_value(cfg, section, "enabled")
    except config_mod.ConfigError:
        return True
    if not isinstance(nilai, bool):
        raise config_mod.ConfigError(
            f"playstyle.yaml {section}.enabled harus bool, dapat: {nilai!r}"
        )
    return nilai


def _gate_banjir(
    p_3p: float | None, p_ft: float | None, ambang_3p: float, ambang_ft: float
) -> tuple[str, str | None]:
    """Nilai satu kaki Asuransi di DUA skenario banjir (gate v18).

    Mengembalikan (putusan, alasan):
    - ("lolos", None): P banjir 3P >= ambang_3p DAN P banjir FT >=
      ambang_ft (DUA ambang terpisah — menggantikan skenario
      tunggal banjir_terburuk v17).
    - ("tolak", alasan): salah satu / kedua P di bawah ambangnya,
      atau P tidak tersedia (None — fail-closed, bukan lolos
      diam-diam). Pemanggil yang memutuskan naik-garis (lihat
      ``_garis_tahan_banjir_ganda``).
    """
    if p_3p is None or p_ft is None:
        hilang = []
        if p_3p is None:
            hilang.append("banjir 3P")
        if p_ft is None:
            hilang.append("banjir FT")
        return (
            "tolak",
            f"P(Under) skenario {', '.join(hilang)} tidak tersedia",
        )
    if p_3p >= ambang_3p and p_ft >= ambang_ft:
        return "lolos", None
    gagal = []
    if p_3p < ambang_3p:
        gagal.append(f"banjir 3P {p_3p * 100:.1f}% < {ambang_3p * 100:.0f}%")
    if p_ft < ambang_ft:
        gagal.append(f"banjir FT {p_ft * 100:.1f}% < {ambang_ft * 100:.0f}%")
    return "tolak", "; ".join(gagal)


def _garis_tahan_banjir_ganda(
    tangga: list[dict],
    cdf: list[tuple[float, float]],
    geser_3p: float,
    geser_ft: float,
    ambang_3p: float,
    ambang_ft: float,
    cfg: dict | None = None,
) -> dict | None:
    """Garis tangga Under terendah yang tahan KEDUA banjir (v18).

    Garis lolos bila P(Under) di banjir 3P >= ambang_3p DAN di
    banjir FT >= ambang_ft (CDF digeser, seperti stress.py). Bila
    ``cfg`` diberikan, garis juga harus lolos gate eksekusi
    (equilibrium.cek_eksekusi: likuiditas + spread + ask nyata) —
    garis tahan yang tidak bisa dibeli bukan garis tahan.
    Mengembalikan entri tangga itu (apa adanya), atau None bila
    tidak ada garis yang lolos. Dipakai climb gate banjir komposer
    (pertahanan lapis kedua di atas equilibrium).
    """
    for entri in tangga:
        garis = _angka(entri.get("line"))
        if garis is None:
            continue
        if cfg is not None and not equilibrium_mod.cek_eksekusi(entri, cfg)["lolos"]:
            continue
        p_3p = stress_mod.p_under_digeser(cdf, garis, geser_3p)
        p_ft = stress_mod.p_under_digeser(cdf, garis, geser_ft)
        if (
            p_3p is not None
            and p_ft is not None
            and p_3p >= ambang_3p
            and p_ft >= ambang_ft
        ):
            return entri
    return None


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


def _pilih_garis_veto_parsial(
    analysis: dict, tiket: str, garis_min: float, cfg: dict, ktx: dict | None = None
) -> dict | None:
    """Garis lolos semua gate >= garis_min untuk veto parsial (v18).

    Mengembalikan dict hasil-equilibrium sintetis (bentuk yang
    diterima ``equilibrium.rakit_kaki_equilibrium``: ada/garis/
    p_model/p_market/p_final/ev_pct/price_label/harga/volume/thin/
    anchor), atau None bila tidak ada garis yang memenuhi (tidak ada
    konteks / tidak ada garis lolos di atas garis_min). Pemilihan
    mengikuti MODE tiket itu (safety_first -> p_final tertinggi;
    max_er -> ER tertinggi dengan tie-break toleransi -> lebih aman)
    tapi MENGABAIKAN band harga: keselamatan veto di atas preferensi
    harga. Dipakai penegakan veto parsial di ``_kumpulkan_kandidat``.
    """
    if ktx is None:
        ktx = equilibrium_mod.siapkan_konteks(analysis, tiket, cfg)
    nilai = equilibrium_mod.nilai_semua_garis(analysis, tiket, cfg, ktx=ktx)
    if not nilai:
        return None
    lolos = [n for n in nilai if n["lolos_semua"] and n["line"] >= garis_min - 1e-9]
    if not lolos:
        return None
    try:
        mode = config_mod.get_value(cfg, "equilibrium", f"mode_{tiket}")
    except config_mod.ConfigError:
        mode = "max_er" if tiket == "main" else "safety_first"
    if mode not in ("max_er", "safety_first"):
        raise config_mod.ConfigError(
            f"playstyle.yaml equilibrium.mode_{tiket} harus 'max_er' atau "
            f"'safety_first', dapat: {mode!r}"
        )
    if mode == "safety_first":
        p_maks = max(n["p_final"] for n in lolos)
        seri = [n for n in lolos if p_maks - n["p_final"] < _EPS]
        er_maks = max(n["expected_return"] for n in seri)
        seri = [n for n in seri if er_maks - n["expected_return"] < _EPS]
        pilihan = min(seri, key=lambda n: n["line"])
    else:
        toleransi, _ = _angka_config_atau_default(
            cfg,
            ("tickets", tiket, "tiebreak_er_tolerance"),
            _DEFAULT_TIEBREAK_ER,
            0.0,
            1.0,
        )
        er_maks = max(n["expected_return"] for n in lolos)
        seri = [n for n in lolos if er_maks - n["expected_return"] < toleransi]
        p_maks = max(n["p_final"] for n in seri)
        seri = [n for n in seri if p_maks - n["p_final"] < _EPS]
        pilihan = min(seri, key=lambda n: n["line"])
    return {
        "ada": True,
        "ticket": tiket,
        "garis": pilihan["line"],
        "harga_venue_cents": pilihan["harga_venue_cents"],
        "price_cents": pilihan["price_cents"],
        "jup_estimated_cents": pilihan["jup_estimated_cents"],
        "thin": pilihan["thin"],
        "volume_usd": pilihan["volume_usd"],
        "p_model": round(pilihan["p_model"], 6),
        "p_market": (
            round(pilihan["p_market"], 6) if pilihan["p_market"] is not None else None
        ),
        "p_final": round(pilihan["p_final"], 6),
        "ev_pct": round(pilihan["ev_pct"], 4),
        "price_label": pilihan["price_label"],
        "anchor": ktx.get("anchor") or {},
    }


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


def _bintang_tunggu_lineup(info_vonis: dict | None, analisis: dict) -> list[str]:
    """Nama bintang Questionable untuk entri TUNGGU_LINEUP.

    Dibaca dari indikator vonis v18 worker A
    (``indikator["timing_gate"]["bintang"]`` — list {"player", ...})
    atau, defensif, dari kunci lain ("bintang_questionable" /
    "pemain_questionable" / "questionable"), atau dari artefak
    (injuries.entries berstatus QUESTIONABLE/DOUBTFUL bila ada).
    [] bila tidak ada nama yang bisa disebut — alasan tetap
    tercatat, nama tidak dikarang.
    """
    if isinstance(info_vonis, dict):
        ind = info_vonis.get("indikator")
        if isinstance(ind, dict):
            timing_gate = ind.get("timing_gate")
            if isinstance(timing_gate, dict):
                bintang = timing_gate.get("bintang")
                if isinstance(bintang, list):
                    nama = [
                        str(v.get("player"))
                        for v in bintang
                        if isinstance(v, dict)
                        and isinstance(v.get("player"), str)
                        and v.get("player")
                    ]
                    if nama:
                        return nama
            for kunci in (
                "bintang_questionable",
                "pemain_questionable",
                "questionable",
            ):
                nilai = ind.get(kunci)
                if isinstance(nilai, list):
                    nama = []
                    for v in nilai:
                        if isinstance(v, dict):
                            pemain = v.get("player")
                        elif isinstance(v, str):
                            pemain = v
                        else:
                            continue
                        if isinstance(pemain, str) and pemain:
                            nama.append(pemain)
                    if nama:
                        return nama
    cedera = analisis.get("injuries")
    if isinstance(cedera, dict) and isinstance(cedera.get("entries"), list):
        nama = []
        for entri in cedera["entries"]:
            if not isinstance(entri, dict):
                continue
            status = entri.get("status")
            pemain = entri.get("player")
            if (
                isinstance(status, str)
                and status.upper() in ("QUESTIONABLE", "DOUBTFUL")
                and isinstance(pemain, str)
                and pemain
            ):
                nama.append(pemain)
        return nama
    return []


def _cek_eksekusi_kaki(analysis: dict, kaki: dict, cfg: dict) -> dict:
    """Gate eksekusi satu kaki NBA (v18, revisi koordinator).

    Sumber bukti, berurutan: (1) field kaki itu sendiri
    (liquidity_usd/bid_cents/ask_cents — disalin builder dari entri
    tangga saat kaki dirakit, seperti volume_usd/thin); (2) bila
    kaki tidak membawa ketiganya (artefak lama pra-v18), entri
    tangga di garis kaki (``stress.tangga_under``). Bila ada >1
    entri di garis itu (duplikat market_id), kaki lolos bila SALAH
    SATU entrinya lolos cek_eksekusi (user membeli di kuotasi
    terbaik). Bila kaki membawa SEBAGIAN field (mis. likuiditas
    ada, bid/ask tidak) -> fail-closed pada field kaki (tidak
    mencampur sumber). Bila tidak ada bukti sama sekali -> gagal
    ("garis_tidak_ada_di_tangga" / alasan cek_eksekusi).
    """
    liq_kaki = _angka(kaki.get("liquidity_usd"))
    bid_kaki = _angka(kaki.get("bid_cents"))
    ask_kaki = _angka(kaki.get("ask_cents"))
    if liq_kaki is not None or bid_kaki is not None or ask_kaki is not None:
        return equilibrium_mod.cek_eksekusi(
            {
                "liquidity": liq_kaki,
                "bid_cents": bid_kaki,
                "ask_cents": ask_kaki,
                "volume_usd": _angka(kaki.get("volume_usd")),
            },
            cfg,
        )
    garis_kaki = _angka(kaki.get("line"))
    if garis_kaki is None:
        return {"lolos": False, "alasan": "garis_tidak_ada_di_tangga"}
    tangga = stress_mod.tangga_under(analysis.get("market"))
    entri_garis = [
        e
        for e in tangga
        if _angka(e.get("line")) is not None
        and abs(_angka(e.get("line")) - garis_kaki) < 1e-9
    ]
    if not entri_garis:
        return {"lolos": False, "alasan": "garis_tidak_ada_di_tangga"}
    hasil = [equilibrium_mod.cek_eksekusi(e, cfg) for e in entri_garis]
    lolos = [h for h in hasil if h["lolos"]]
    if lolos:
        return lolos[0]

    # Gagal semua: laporkan yang spread-nya tersempit (paling dekat).
    def _kunci(h):
        spread = h.get("spread_cents")
        return spread if spread is not None else 999.0

    return min(hasil, key=_kunci)


def _teks_alasan_eksekusi(hasil: dict) -> str:
    """Alasan gate eksekusi gagal dalam Bahasa Indonesia (+ angka)."""
    alasan = hasil.get("alasan")
    if alasan == "garis_tidak_ada_di_tangga":
        return "garis kaki tidak ada di tangga Polymarket"
    if alasan == "likuiditas_tidak_tercatat":
        return "likuiditas tidak tercatat"
    if alasan == "likuiditas_di_bawah_minimum":
        liq = hasil.get("likuiditas_usd")
        minimum = hasil.get("likuiditas_min_usd")
        return (
            f"likuiditas ${liq:,.2f} di bawah minimum ${minimum:,.2f} "
            "(max(2 x stake, $25))"
        )
    if alasan == "tanpa_kuotasi":
        return "bid/ask tidak tercatat"
    if alasan == "tanpa_ask_nyata":
        return "ask 99¢ (tidak ada ask nyata)"
    if alasan == "spread_terlalu_lebar":
        spread = hasil.get("spread_cents")
        maksimum = hasil.get("spread_max_cents")
        return f"spread {spread:g}¢ di atas maksimum {maksimum:g}¢"
    return str(alasan) if alasan else "tidak diketahui"


def _kumpulkan_kandidat(
    analisis_per_laga: dict[str, dict],
    recheck_per_laga: dict[str, dict],
    cfg: dict,
    lantai: dict[str, float] | None = None,
    ambang_ev: dict[str, float] | None = None,
    skipped: list | None = None,
    menunggu_lineup: list | None = None,
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
    sini via ``_lantai_harga``). ``ambang_ev``: EV minimum per tiket
    dalam persen (None = baca dari config di sini via ``_ambang_ev``;
    v18 MENGGANTIKAN parameter lama ``edge_min_ins`` — gate edge
    DIHAPUS). ``skipped``: bila list diberikan, diisi dict laga yang
    di-skip dari awal ({"match_id", "pemicu", "alasan"}) — dipakai
    ``compose_tickets`` untuk hasil ["skipped_matches"].
    ``menunggu_lineup``: bila list diberikan, diisi dict laga
    TUNGGU_LINEUP ({"match_id", "bintang", "alasan"}) — dipakai
    ``compose_tickets`` untuk hasil ["menunggu_lineup"]; pemanggil
    lama tanpa argumen ini tidak terpengaruh.

    Vonis per laga (engine/vonis.py, NBA saja): laga KUNING yang
    DIEVALUASI dikeluarkan dari kedua tiket (alasan di ``coret``);
    laga TUNGGU_LINEUP dikeluarkan dari kedua tiket + dicatat di
    ``menunggu_lineup`` (bukan KUNING, bukan kandidat); tiap
    kandidat membawa ``vonis`` ("hijau" / "menengah_hijau" / None
    bila tidak dievaluasi / tidak dihitung) + ``vonis_alasan``
    (daftar alasan) — dibaca ``_alokasikan_laga`` untuk aturan
    tanpa kaki kembar. Laga KUNING-karena-data (tidak dievaluasi)
    TIDAK dikeluarkan di sini (gate per kaki tetap fail-closed
    sendiri). Veto parsial (peringatan_parsial di indikator veto):
    kaki laga itu wajib +3 poin bantalan di atas garis acuan normal
    (lihat docstring modul).
    """
    ambang_gap = _ambang_gap_market(cfg)
    min_prob = {
        "insurance": _ambang(cfg, "tickets", "insurance", "min_leg_prob"),
        "main": _ambang(cfg, "tickets", "main", "min_leg_prob"),
    }
    if lantai is None:
        lantai, _sumber_lantai = _lantai_harga(cfg)
    if ambang_ev is None:
        ambang_ev = {}
        for tiket_ev in ("insurance", "main"):
            ambang_ev[tiket_ev], _ = _ambang_ev(cfg, tiket_ev)
    ambang_banjir_3p, ambang_banjir_ft = _ambang_banjir(cfg)
    ambang_p_market = _ambang_p_market_ins(cfg)
    bantalan_parsial, _sumber_parsial = _bantalan_veto_parsial(cfg)
    equilibrium_aktif = _flag_enabled(cfg, "equilibrium")
    skip_aktif = _flag_enabled(cfg, "skip_awal")
    vonis_aktif = _flag_enabled(cfg, "vonis")
    tolak_mahal_ins = bool(
        config_mod.get_value(cfg, "optimizer", "exclude_mahal_from_insurance")
    )
    kandidat: dict[str, list[dict]] = {"insurance": [], "main": []}
    coret: dict[str, list[str]] = {"insurance": [], "main": []}

    for match_id, analisis in sorted(analisis_per_laga.items()):
        status = analisis.get("status")
        # --- TUNGGU_LINEUP (v18, timing gate): laga berstatus
        # "tunggu_lineup" (atau vonis "tunggu_lineup" di artefak)
        # DIKELUARKAN dari kandidat final + dicatat terpisah —
        # bukan KUNING, bukan kandidat. Dicek SEBELUM status OK
        # (status tunggu_lineup bukan OK, tapi juga bukan HOLD).
        vonis_artifak = _vonis_dari_nilai(analisis.get("vonis"))
        if status == "tunggu_lineup" or vonis_artifak == "tunggu_lineup":
            bintang = _bintang_tunggu_lineup(None, analisis)
            alasan_tunggu = (
                "bintang masih Questionable — lineup belum final, "
                "tunggu injury report 30 menit sebelum tip-off"
            )
            if bintang:
                alasan_tunggu += f" ({', '.join(bintang)})"
            for tiket in ("insurance", "main"):
                coret[tiket].append(f"{match_id}: TUNGGU_LINEUP — {alasan_tunggu}")
            if menunggu_lineup is not None:
                menunggu_lineup.append(
                    {
                        "match_id": match_id,
                        "bintang": bintang,
                        "alasan": alasan_tunggu,
                    }
                )
            continue
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
        # --- Equilibrium + skip dari awal (NBA saja; bola tidak punya
        # model CDF/tangga/stress yang sama). Dihitung sekali per laga,
        # SEBELUM kaki apa pun dinilai: laga yang di-skip tidak
        # menyumbang kaki ke tiket mana pun; kaki yang tidak di-skip
        # diganti garisnya ke titik equilibrium (bila terhitung).
        eq_per_tiket: dict[str, dict | None] = {
            "insurance": None,
            "main": None,
        }
        ktx_ins: dict | None = None
        ktx_main: dict | None = None
        # Garis valid Asuransi v18.1 Patch #2 (seluruh garis dalam
        # band yang lolos 100% gate — bahan optimasi gabungan
        # komposer). None bila equilibrium nonaktif / konteks tidak
        # siap (tanpa CDF / tangga / jangkar pasar).
        valid_lines_ins: list[dict] | None = None
        # Konteks fallback gate banjir (dibangun sekali per laga bila
        # equilibrium + skip_awal nonaktif sehingga ktx di atas None).
        ktx_banjir_jatuh: dict | None = None
        if analisis.get("format") != "soccer_analysis" and (
            equilibrium_aktif or skip_aktif
        ):
            ktx_ins = equilibrium_mod.siapkan_konteks(analisis, "insurance", cfg)
            ktx_main = equilibrium_mod.siapkan_konteks(analisis, "main", cfg)
            if equilibrium_aktif:
                for tiket_eq, ktx_eq in (
                    ("insurance", ktx_ins),
                    ("main", ktx_main),
                ):
                    hasil_eq = equilibrium_mod.cari_equilibrium(
                        analisis, tiket_eq, cfg, ktx=ktx_eq
                    )
                    eq_per_tiket[tiket_eq] = hasil_eq
                # Dihitung sekali per laga dari ktx_ins yang sama
                # (tanpa hitung ulang CDF/tangga).
                valid_lines_ins = equilibrium_mod.garis_valid_asuransi(
                    analisis, cfg, ktx=ktx_ins
                )
            if skip_aktif:
                # Equilibrium nonaktif -> stub "tidak dihitung" supaya
                # pemicu (a) tidak bisa terpicu (tanpa equilibrium,
                # tidak ada klaim "tidak ada equilibrium").
                eq_ins_skip = eq_per_tiket["insurance"] or {
                    "dihitung": False,
                    "ada": False,
                    "alasan_tidak_dihitung": "equilibrium nonaktif di config",
                }
                eq_main_skip = eq_per_tiket["main"] or {
                    "dihitung": False,
                    "ada": False,
                    "alasan_tidak_dihitung": "equilibrium nonaktif di config",
                }
                info_skip = skip_awal_mod.evaluasi_skip_awal(
                    analisis,
                    cfg,
                    eq_ins=eq_ins_skip,
                    eq_main=eq_main_skip,
                    ktx=ktx_ins,
                )
                if info_skip.get("skip"):
                    for tiket_skip in ("insurance", "main"):
                        coret[tiket_skip].append(
                            f"{match_id}: SKIP dari awal — "
                            f"{info_skip.get('alasan') or 'tanpa alasan'}"
                        )
                    if skipped is not None:
                        skipped.append(
                            {
                                "match_id": match_id,
                                "pemicu": list(info_skip.get("pemicu") or []),
                                "alasan": info_skip.get("alasan"),
                            }
                        )
                    continue
        # --- Vonis per laga (NBA saja; bola tidak punya model
        # CDF/tangga/stress yang sama). Dihitung sekali per laga,
        # SETELAH skip dari awal (laga yang di-skip tidak mencapai
        # vonis) dan SEBELUM kaki apa pun dinilai: laga KUNING yang
        # DIEVALUASI dikeluarkan dari kedua tiket; vonis + alasan
        # disimpan pada tiap kandidat (dipakai alokasi tiket untuk
        # aturan tanpa kaki kembar). Laga KUNING-karena-data
        # (dievaluasi False) TIDAK dikeluarkan di sini — gate per
        # kaki yang sudah fail-closed tetap berlaku — dan
        # kandidatnya membawa vonis None (tanpa preferensi alokasi)
        # supaya satu ladder fetch yang gagal tidak mematikan
        # seluruh slate termasuk Utama (lihat engine/vonis.py;
        # menunggu keberatan). Vonis menghitung konteksnya sendiri
        # (tidak memakai ktx/equilibrium di atas) supaya tetap jalan
        # bila equilibrium nonaktif.
        info_vonis: dict | None = None
        vonis_kandidat: str | None = None
        vonis_alasan: list[str] = []
        veto_parsial = False
        veto_parsial_alasan: list[str] = []
        if vonis_aktif and analisis.get("format") != "soccer_analysis":
            info_vonis = vonis_mod.nilai_vonis(analisis, None, cfg)
            vonis_alasan = list(info_vonis.get("alasan") or [])
            # --- TUNGGU_LINEUP dari vonis (v18): bintang
            # Questionable -> laga ditahan dari kedua tiket +
            # dicatat terpisah (bukan KUNING, bukan kandidat).
            vonis_mentah = _normalisasi_vonis(info_vonis.get("vonis"))
            if vonis_mentah == "tunggu_lineup":
                bintang = _bintang_tunggu_lineup(info_vonis, analisis)
                alasan_tunggu = "; ".join(vonis_alasan) or (
                    "bintang masih Questionable — lineup belum final"
                )
                # Alasan vonis v18 sudah diawali "TUNGGU_LINEUP:" —
                # jangan duplikasi prefix di pesan coret.
                teks_coret = (
                    alasan_tunggu
                    if alasan_tunggu.startswith("TUNGGU_LINEUP:")
                    else f"TUNGGU_LINEUP — {alasan_tunggu}"
                )
                for tiket_vonis in ("insurance", "main"):
                    coret[tiket_vonis].append(f"{match_id}: {teks_coret}")
                if menunggu_lineup is not None:
                    menunggu_lineup.append(
                        {
                            "match_id": match_id,
                            "bintang": bintang,
                            "alasan": alasan_tunggu,
                        }
                    )
                continue
            # --- VETO PARSIAL (v18): hanya satu kondisi veto menyala
            # (rim protector OUT + garis tinggi ATAU pace tinggi) ->
            # kaki laga ini wajib +3 poin bantalan (ditegakkan per
            # kaki di bawah). Dibaca defensif: vonis v17 tidak punya
            # kunci ini (False = tidak ada peringatan parsial).
            indikator_vonis = info_vonis.get("indikator")
            veto_info = (
                indikator_vonis.get("veto")
                if isinstance(indikator_vonis, dict)
                else None
            )
            if isinstance(veto_info, dict) and veto_info.get("peringatan_parsial"):
                veto_parsial = True
                veto_parsial_alasan = list(veto_info.get("alasan") or [])
            if (info_vonis.get("indikator") or {}).get("dievaluasi"):
                vonis_kandidat = info_vonis.get("vonis")
                if vonis_kandidat == "kuning":
                    alasan_vonis = "; ".join(vonis_alasan) or "tanpa alasan"
                    for tiket_vonis in ("insurance", "main"):
                        coret[tiket_vonis].append(
                            f"{match_id}: vonis KUNING — {alasan_vonis}"
                        )
                    continue
        for kaki in analisis.get("legs") or []:
            if not isinstance(kaki, dict):
                continue
            tiket = _tiket_kaki(kaki)
            if tiket not in ("insurance", "main"):
                continue
            leg_id = kaki.get("leg_id") or "?"
            garis = _angka(kaki.get("line"))
            # Garis acuan normal = garis kaki artefak SEBELUM
            # equilibrium (dipakai veto parsial +3 di bawah).
            garis_acuan_normal = garis
            kaki_awal = kaki
            label_kaki = _seleksi_kaki(kaki, analisis)
            market_type = kaki.get("market_type")
            # P banjir kaki equilibrium (bila ada) — dipakai
            # peringatan banjir Utama (warning-only, v18).
            p_banjir_eq: dict | None = None
            # Garis valid laga ini untuk kandidat Asuransi (v18.1
            # Patch #2) — disaring veto parsial di bawah bila ada.
            # Salinan daftar (filter tidak mengubah daftar per laga).
            valid_lines_kandidat = (
                list(valid_lines_ins)
                if tiket == "insurance" and valid_lines_ins
                else None
            )
            # --- Titik equilibrium (MENGGANTIKAN seleksi garis lama).
            # Berjalan SEBELUM cek meets: equilibrium memilih ulang
            # dari tangga + CDF, jadi kaki meets=false karena seleksi
            # garis lama (mis. tidak ada garis lolos di cushion) bisa
            # hidup kembali bila equilibrium menemukan garis yang
            # lolos semua gate komposer. Bila equilibrium TIDAK ADA
            # (dihitung, tidak ada garis lolos) -> kaki ditolak dengan
            # alasan diagnostiknya. Bila TIDAK DIHITUNG (tanpa CDF /
            # tangga / jangkar) -> kaki artefak dipakai apa adanya
            # (fallback, lanjut ke logika lama di bawah). Gate v18
            # TETAP diterapkan ulang pada kaki artefak fallback di
            # bawah (bukan dipakai mentah-mentah).
            if (
                equilibrium_aktif
                and analisis.get("format") != "soccer_analysis"
                and market_type == "total_under"
                and eq_per_tiket.get(tiket) is not None
            ):
                hasil_eq = eq_per_tiket[tiket]
                if hasil_eq.get("dihitung"):
                    if not hasil_eq.get("ada"):
                        coret[tiket].append(
                            f"{match_id} ({label_kaki}): "
                            f"{hasil_eq.get('alasan_tidak_ada') or 'tidak ada equilibrium'}"
                        )
                        continue
                    p_banjir_eq = {
                        "p_banjir_3p": hasil_eq.get("p_banjir_3p"),
                        "p_banjir_ft": hasil_eq.get("p_banjir_ft"),
                        "banjir_warning": hasil_eq.get("banjir_warning"),
                    }
                    kaki_baru = equilibrium_mod.rakit_kaki_equilibrium(
                        kaki, hasil_eq, analisis, cfg
                    )
                    if kaki_baru is not None:
                        kaki = kaki_baru
                        garis = _angka(kaki.get("line"))
                        label_kaki = _seleksi_kaki(kaki, analisis)
            # --- VETO PARSIAL +3 (v18): garis yang dipilih harus >=
            # garis acuan normal + 3,0. Bila garis equilibrium /
            # artefak kurang, cari garis lolos semua gate di atas
            # batas itu (band harga diabaikan — keselamatan veto di
            # atas preferensi harga); bila tidak ada, kaki dicoret.
            # Hanya kaki NBA total_under (veto adalah konsep NBA).
            if (
                veto_parsial
                and analisis.get("format") != "soccer_analysis"
                and market_type == "total_under"
                and garis_acuan_normal is not None
            ):
                garis_min_veto = garis_acuan_normal + bantalan_parsial
                if garis is None or garis < garis_min_veto - 1e-9:
                    ktx_veto = ktx_ins if tiket == "insurance" else ktx_main
                    hasil_veto = _pilih_garis_veto_parsial(
                        analisis, tiket, garis_min_veto, cfg, ktx=ktx_veto
                    )
                    if hasil_veto is None:
                        alasan_parsial = (
                            "; ".join(veto_parsial_alasan)
                            if veto_parsial_alasan
                            else "peringatan parsial veto rim protector"
                        )
                        coret[tiket].append(
                            f"{match_id} ({label_kaki}): veto parsial — "
                            f"garis harus >= U{garis_min_veto:g} "
                            f"(garis acuan U{garis_acuan_normal:g} + "
                            f"{bantalan_parsial:g} poin bantalan) tapi tidak "
                            f"ada garis lolos semua gate di atas batas itu "
                            f"({alasan_parsial})"
                        )
                        continue
                    kaki_veto = equilibrium_mod.rakit_kaki_equilibrium(
                        kaki_awal, hasil_veto, analisis, cfg
                    )
                    if kaki_veto is not None:
                        climb_veto = kaki_veto.get("climb")
                        if isinstance(climb_veto, dict) and isinstance(
                            climb_veto.get("reason"), str
                        ):
                            climb_veto["reason"] += "+veto_parsial"
                        kaki = kaki_veto
                        garis = _angka(kaki.get("line"))
                        label_kaki = _seleksi_kaki(kaki, analisis)
            # --- VETO PARSIAL +3 pada garis valid (v18.1 Patch #2):
            # garis valid di bawah batas veto (garis acuan + 3,0)
            # BUKAN pilihan komposer — disaring dari varian, apa pun
            # garis equilibriumnya (blok di atas hanya berjalan bila
            # garis equilibrium kurang; saringan ini berlaku selalu
            # bila veto parsial menyala untuk laga ini).
            if (
                veto_parsial
                and tiket == "insurance"
                and analisis.get("format") != "soccer_analysis"
                and market_type == "total_under"
                and garis_acuan_normal is not None
                and valid_lines_kandidat
            ):
                batas_veto = garis_acuan_normal + bantalan_parsial
                valid_lines_kandidat = [
                    entri
                    for entri in valid_lines_kandidat
                    if _angka(entri.get("garis")) is not None
                    and _angka(entri.get("garis")) >= batas_veto - 1e-9
                ]
            if not kaki.get("meets"):
                alasan = kaki.get("reason") or "tidak memenuhi syarat"
                coret[tiket].append(f"{match_id} ({label_kaki}): {alasan}")
                continue
            if market_type in ("total_over", "total_under") and garis is None:
                # Kaki total tanpa garis tidak bisa dinilai; kaki 1X2/
                # BTTS memang tidak punya garis (line null itu sah).
                coret[tiket].append(f"{match_id} ({label_kaki}): garis total tidak ada")
                continue
            # --- Gate banjir Asuransi v18 (DUA ambang terpisah:
            # P banjir 3P >= 0,70 DAN P banjir FT >= 0,65 — keputusan
            # user 2026-11-23 13:57 WIB, menggantikan skenario
            # tunggal banjir_terburuk >= 74% v17). Hanya kaki NBA
            # total_under Asuransi: bola tidak punya model stress,
            # total_over bukan Under. P banjir dihitung LANGSUNG
            # dari CDF (CDF yang sama dengan equilibrium), bukan
            # dari entri skenario_panas — supaya gate menilai garis
            # APAPUN yang dipilih (equilibrium / veto parsial /
            # naik-garis), bukan hanya garis kaki artefak.
            # Berjalan SEBELUM gate lain yang memakai garis/harga,
            # supaya kaki yang naik garis dinilai di garis barunya
            # (lantai harga, volume eksekusi, EV). Pada kaki
            # equilibrium, gate ini lolos by construction
            # (equilibrium sudah memakai gate banjir yang sama) —
            # ia tetap berjalan sebagai pertahanan lapis kedua +
            # untuk kaki fallback (tanpa equilibrium). p_final/EV
            # kaki yang naik garis di sini tetap garis lama
            # (konservatif — lihat _kaki_naik_garis); kaki
            # equilibrium TIDAK kena konservatisme itu karena
            # p_finalnya sudah dihitung ulang di garis baru oleh
            # engine/equilibrium.py.
            if (
                tiket == "insurance"
                and analisis.get("format") != "soccer_analysis"
                and market_type == "total_under"
            ):
                ktx_banjir = ktx_ins or ktx_main
                if ktx_banjir is None:
                    if ktx_banjir_jatuh is None:
                        ktx_banjir_jatuh = equilibrium_mod.siapkan_konteks(
                            analisis, tiket, cfg
                        )
                    ktx_banjir = ktx_banjir_jatuh
                cdf_banjir = ktx_banjir.get("cdf")
                geser_3p = _angka(ktx_banjir.get("geser_banjir_3p"))
                geser_ft = _angka(ktx_banjir.get("geser_banjir_ft"))
                if cdf_banjir is None:
                    # Konteks equilibrium tanpa CDF (artefak tanpa
                    # tangga / tanpa jangkar): bangun CDF langsung
                    # dari markets simulasi — P banjir hanya butuh
                    # CDF, bukan tangga (perilaku yang sama dengan
                    # gate stress v17; tanpa ini kaki artefak tanpa
                    # tangga selalu ditolak fail-closed).
                    sim = analisis.get("simulation")
                    markets = sim.get("markets") if isinstance(sim, dict) else None
                    try:
                        cdf_banjir = stress_mod.cdf_total_dari_markets(markets)
                    except (ValueError, TypeError):
                        cdf_banjir = None
                if cdf_banjir is None or geser_3p is None or geser_ft is None:
                    coret[tiket].append(
                        f"{match_id} ({label_kaki}): CDF total tidak "
                        "bisa dibangun — skenario banjir tidak bisa "
                        "dihitung, kaki Asuransi ditolak (fail-closed)"
                    )
                    continue
                p_3p = stress_mod.p_under_digeser(cdf_banjir, garis, geser_3p)
                p_ft = stress_mod.p_under_digeser(cdf_banjir, garis, geser_ft)
                putusan_banjir, alasan_banjir = _gate_banjir(
                    p_3p, p_ft, ambang_banjir_3p, ambang_banjir_ft
                )
                if putusan_banjir == "tolak":
                    # Coba naik ke garis tangga terendah yang tahan
                    # KEDUA banjir + lolos gate eksekusi (garis
                    # tahan yang tidak bisa dibeli bukan garis tahan).
                    tangga_banjir = stress_mod.tangga_under(analisis.get("market"))
                    entri_tahan = _garis_tahan_banjir_ganda(
                        tangga_banjir,
                        cdf_banjir,
                        geser_3p,
                        geser_ft,
                        ambang_banjir_3p,
                        ambang_banjir_ft,
                        cfg=cfg,
                    )
                    if entri_tahan is None:
                        coret[tiket].append(
                            f"{match_id} ({label_kaki}): "
                            "tidak_ada_garis_tahan_banjir — "
                            f"{alasan_banjir} dan tidak ada garis "
                            "tangga yang tahan kedua banjir + lolos "
                            "gate eksekusi"
                        )
                        continue
                    kaki_baru = _kaki_naik_garis(kaki, entri_tahan, tangga_banjir)
                    if kaki_baru is None:
                        coret[tiket].append(
                            f"{match_id} ({label_kaki}): garis tahan "
                            "banjir tidak lebih tinggi dari garis "
                            "kaki — kaki Asuransi ditolak"
                        )
                        continue
                    kaki = kaki_baru
                    garis = _angka(kaki.get("line"))
                    label_kaki = _seleksi_kaki(kaki, analisis)
                # Catat P banjir di garis FINAL (setelah naik-garis
                # bila naik) untuk kandidat + peringatan.
                p_banjir_eq = {
                    "p_banjir_3p": stress_mod.p_under_digeser(
                        cdf_banjir, garis, geser_3p
                    ),
                    "p_banjir_ft": stress_mod.p_under_digeser(
                        cdf_banjir, garis, geser_ft
                    ),
                    "banjir_warning": False,
                }
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
            # --- Gate eksekusi v18 (MENGGANTIKAN thin sebagai
            # penghalang keras Asuransi; revisi koordinator —
            # likuiditas + spread, bukan volume kumulatif):
            # bukti eksekusi kaki (field kaki, fallback tangga di
            # garis kaki) harus lolos equilibrium.cek_eksekusi.
            # Hanya kaki NBA total_under (kaki bola dan moneyline
            # tidak membawa data tangga di artefak; fail-closed di
            # sana akan membunuh semua kaki itu — keputusan ini
            # menunggu keberatan). thin=True yang lolos gate
            # eksekusi BOLEH masuk kedua tiket (flag VOLUME_TIPIS +
            # peringatan di compose).
            if (
                analisis.get("format") != "soccer_analysis"
                and market_type == "total_under"
            ):
                hasil_eksekusi = _cek_eksekusi_kaki(analisis, kaki, cfg)
                if not hasil_eksekusi["lolos"]:
                    coret[tiket].append(
                        f"{match_id} ({label_kaki}): gate eksekusi "
                        f"tidak lolos "
                        f"({_teks_alasan_eksekusi(hasil_eksekusi)})"
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
            # Sumber probabilitas keputusan (v18.1 Patch #2 — dipakai
            # varian garis valid: "p_final" (biasa), "market_recheck"
            # (probabilitas market dari recheck, per leg_id — sama
            # untuk semua varian), "market_condong" (harga market
            # mentah di garis itu — dihitung ulang per varian).
            sumber_prob = "p_final"
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
                        sumber_prob = "market_recheck"
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
                        sumber_prob = "market_condong"
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
            # --- Gate p_market Asuransi v18 (hanya Asuransi): harga
            # pasar (p_market) harus >= 0,80 — kaki yang pasarnya
            # sendiri ragu bukan asuransi. MODEL_ONLY sudah dicoret
            # di atas (p_market None), jadi di sini p_market selalu
            # angka. (Di equilibrium, MODEL_ONLY lolos gate ini
            # dengan catatan — komposer lebih ketat karena skema
            # tiket mewajibkan p_market.)
            if tiket == "insurance" and p_market < ambang_p_market:
                coret[tiket].append(
                    f"{match_id} ({label_kaki}): p_market "
                    f"{p_market * 100:.1f}% di bawah minimum "
                    f"{ambang_p_market * 100:.0f}% untuk Asuransi"
                )
                continue
            # --- Gate EV v18 (MENGGANTIKAN gate edge datar 3,5%
            # Asuransi — keputusan user 2026-11-23 13:57 WIB):
            # Asuransi EV >= -1%, Utama EV >= -2%. EV memakai
            # ev_pct kaki (p_final x 100/harga - 1), BUKAN
            # probabilitas keputusan (condong-ke-market tidak
            # mengubah EV).
            if ev_pct < ambang_ev[tiket]:
                coret[tiket].append(
                    f"{match_id} ({label_kaki}): ev_di_bawah_minimum "
                    f"— EV {ev_pct:+.1f}% di bawah minimum "
                    f"{ambang_ev[tiket]:+.1f}% untuk "
                    f"{'Asuransi' if tiket == 'insurance' else 'Utama'}"
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
                    # Sumber probabilitas keputusan (v18.1 Patch #2 —
                    # lihat sumber_prob di atas).
                    "decision_prob_sumber": sumber_prob,
                    # Garis valid Asuransi laga ini (v18.1 Patch #2;
                    # None untuk Utama / tanpa equilibrium / tanpa
                    # garis valid) — bahan optimasi gabungan.
                    "valid_lines": valid_lines_kandidat,
                    # Kaki artefak SEBELUM equilibrium (v18.1 Patch
                    # #2): varian garis valid dibangun ulang DARI
                    # kaki ini (bukan dari kaki equilibrium) supaya
                    # climb-nya benar (dari garis artefak ke garis
                    # varian — bukan dirangkai dari climb equilibrium
                    # yang sudah ada).
                    "leg_awal": kaki_awal,
                    "recheck_verdict": (
                        putusan.get("verdict") if putusan is not None else None
                    ),
                    "recheck_alasan": alasan_perhatian,
                    "recheck_at": recheck_at,
                    "thin": kaki.get("thin") is True,
                    "ada_anomali": ada_anomali,
                    "sim_markets": pasar_sim,
                    "vonis": vonis_kandidat,
                    "vonis_alasan": list(vonis_alasan),
                    # P banjir v18 (None bila tidak dihitung —
                    # kaki bola / tanpa equilibrium / tanpa CDF):
                    # Utama warning-only, Asuransi sudah lolos gate.
                    "p_banjir_3p": (
                        p_banjir_eq.get("p_banjir_3p")
                        if p_banjir_eq is not None
                        else None
                    ),
                    "p_banjir_ft": (
                        p_banjir_eq.get("p_banjir_ft")
                        if p_banjir_eq is not None
                        else None
                    ),
                    "banjir_warning": bool(
                        p_banjir_eq is not None and p_banjir_eq.get("banjir_warning")
                    ),
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


# ======================================================================
# Optimasi gabungan Asuransi v18.1 Patch #2 ("Perangkap Plafon 88,5¢")
# ======================================================================


def _varian_dalam_valid_lines(varian: dict, valid_lines: list[dict] | None) -> bool:
    """Validasi fail-closed: garis varian ada di valid_lines laganya.

    Varian lolos hanya bila ada entri valid_lines dengan garis yang
    SAMA (toleransi 1e-9) DAN harga venue yang SAMA (toleransi
    1e-9). Tanpa valid_lines (None/kosong) -> False (tidak ada yang
    bisa divalidasi — pemanggil memakai jalur kandidat v18, bukan
    validasi ini).
    """
    if not valid_lines:
        return False
    garis = _angka(varian.get("line"))
    harga = _angka(varian.get("harga_jup"))
    if garis is None or harga is None:
        return False
    for entri in valid_lines:
        garis_entri = _angka(entri.get("garis"))
        if garis_entri is None:
            garis_entri = _angka(entri.get("line"))
        harga_entri = _angka(entri.get("harga_venue_cents"))
        if (
            garis_entri is not None
            and harga_entri is not None
            and abs(garis_entri - garis) < 1e-9
            and abs(harga_entri - harga) < 1e-9
        ):
            return True
    return False


def _varian_dari_garis_valid(kand: dict, entri: dict, cfg: dict) -> dict | None:
    """Satu varian kandidat Asuransi dari satu entri garis valid.

    Kaki dibangun ulang di garis entri (via
    ``equilibrium.rakit_kaki_equilibrium`` dengan hasil-equilibrium
    sintetis — pola yang sama dengan ``_pilih_garis_veto_parsial``)
    DARI kaki artefak (``leg_awal`` kandidat — bukan dari kaki
    equilibrium) supaya climb-nya benar: dari garis artefak ke
    garis varian, bukan dirangkai dari climb equilibrium yang
    sudah ada. Bila garis entri SAMA dengan garis artefak, kaki
    artefak dipakai apa adanya (rakit mengembalikan None untuk
    garis yang sama).
    Bukti eksekusi (likuiditas/bid/ask) disalin dari entri tangga
    supaya varian mandiri (kuotasi adalah sifat GARIS, bukan sifat
    kaki — kaki lama membawa kuotasi garis lama).
    decision_prob dihitung ulang sesuai sumbernya (lihat
    ``decision_prob_sumber`` di ``_kumpulkan_kandidat``): p_final
    varian (biasa), probabilitas recheck (per leg_id — sama untuk
    semua varian), atau harga market mentah di garis varian
    (condong-ke-market — varian yang jatuh di bawah ambang peluang
    DIBUANG, bukan diloloskan).
    None bila entri tidak valid / kaki tidak bisa dibangun ulang /
    varian gagal ambang peluang condong (fail-closed per varian —
    varian lain tidak terpengaruh).
    """
    garis_entri = _angka(entri.get("garis"))
    if garis_entri is None:
        garis_entri = _angka(entri.get("line"))
    harga_entri = _angka(entri.get("harga_venue_cents"))
    p_final_entri = _angka(entri.get("p_final"))
    p_model_entri = _angka(entri.get("p_model"))
    p_market_entri = _angka(entri.get("p_market"))
    ev_entri = _angka(entri.get("ev_pct"))
    if (
        garis_entri is None
        or harga_entri is None
        or not 0.0 < harga_entri < 100.0
        or p_final_entri is None
        or not 0.0 < p_final_entri <= 1.0
        or p_model_entri is None
        or p_market_entri is None
        or ev_entri is None
    ):
        return None
    kaki_lama = kand.get("leg_awal") or kand["leg"]
    analisis = kand["analysis"]
    garis_lama = _angka(kaki_lama.get("line"))
    if garis_lama is not None and abs(garis_entri - garis_lama) < 1e-9:
        kaki_baru = dict(kaki_lama)
    else:
        hasil_eq = {
            "ada": True,
            "ticket": "insurance",
            "garis": garis_entri,
            "harga_venue_cents": harga_entri,
            "price_cents": _angka(entri.get("price_cents")),
            "jup_estimated_cents": _angka(entri.get("jup_estimated_cents")),
            "thin": entri.get("thin"),
            "volume_usd": _angka(entri.get("volume_usd")),
            "p_model": p_model_entri,
            "p_market": p_market_entri,
            "p_final": p_final_entri,
            "ev_pct": ev_entri,
            "price_label": entri.get("price_label"),
            "anchor": {},
        }
        kaki_baru = equilibrium_mod.rakit_kaki_equilibrium(
            kaki_lama, hasil_eq, analisis, cfg
        )
        if kaki_baru is None:
            return None
    # Bukti eksekusi dari entri tangga (bukan dari kaki lama).
    likuiditas = _angka(entri.get("likuiditas_usd"))
    bid = _angka(entri.get("bid_cents"))
    ask = _angka(entri.get("ask_cents"))
    if likuiditas is not None:
        kaki_baru["liquidity_usd"] = likuiditas
    if bid is not None:
        kaki_baru["bid_cents"] = bid
    if ask is not None:
        kaki_baru["ask_cents"] = ask
    # Probabilitas keputusan per varian (lihat decision_prob_sumber).
    sumber = kand.get("decision_prob_sumber") or "p_final"
    if sumber == "market_recheck":
        prob_keputusan = kand["decision_prob"]
    elif sumber == "market_condong":
        harga_mentah = _angka(entri.get("price_cents"))
        if harga_mentah is None:
            harga_mentah = harga_entri
        prob_keputusan = harga_mentah / 100.0
        ambang_prob = _ambang(cfg, "tickets", "insurance", "min_leg_prob")
        if prob_keputusan < ambang_prob:
            return None
    else:
        prob_keputusan = p_final_entri
    varian = dict(kand)
    varian.update(
        {
            "leg": kaki_baru,
            "line": garis_entri,
            "selection": _seleksi_kaki(kaki_baru, analisis),
            "harga_jup": harga_entri,
            "p_final": p_final_entri,
            "p_model": p_model_entri,
            "p_market": p_market_entri,
            "ev_pct": ev_entri,
            "price_label": entri.get("price_label"),
            "decision_prob": prob_keputusan,
            "thin": entri.get("thin") is True,
            "p_banjir_3p": _angka(entri.get("p_banjir_3p")),
            "p_banjir_ft": _angka(entri.get("p_banjir_ft")),
            "banjir_warning": False,
        }
    )
    return varian


def _varian_kandidat_asuransi(kand: dict, cfg: dict) -> list[dict]:
    """Varian kandidat Asuransi satu laga (v18.1 Patch #2).

    Bila kandidat membawa valid_lines (garis Asuransi yang lolos
    100% gate dalam band 80–89¢), satu varian per garis valid
    (kaki dibangun ulang di garis itu + divalidasi keanggotaannya
    di valid_lines — fail-closed: varian yang gagal dibangun atau
    gagal validasi DIBUANG). Bila tidak ada garis valid (tanpa
    equilibrium / garis valid kosong), satu varian = kandidat itu
    sendiri (jalur v18 — garis yang lolos semua gate komposer).
    Bila SEMUA garis valid gagal dibangun (tidak seharusnya
    terjadi), kandidat v18 dipakai sebagai satu-satunya varian
    supaya laga tidak hilang diam-diam (garisnya lolos semua gate
    komposer — pertahanan terakhir, bukan pelonggaran).
    """
    valid = kand.get("valid_lines")
    if not valid:
        return [kand]
    varian: list[dict] = []
    for entri in valid:
        dibuat = _varian_dari_garis_valid(kand, entri, cfg)
        if dibuat is None:
            continue
        if not _varian_dalam_valid_lines(dibuat, valid):
            continue
        varian.append(dibuat)
    return varian or [kand]


def _kunci_dp(
    log_p: float,
    mult_net: float,
    n_kaki: int,
    sidik: tuple,
    tengah: float,
    utamakan_pengali: bool,
) -> tuple:
    """Kunci urut satu kombinasi DP (lebih kecil = lebih baik).

    (1) peluang cair gabungan tertinggi (log_p terbesar — sama
    dengan Π P_final terbesar); (2) tiket: pengali paling dekat ke
    tengah jendela (perilaku ``_pilih_subset``); opsi fallback:
    pengali TERBESAR (paling dekat menutup modal —
    ``utamakan_pengali`` True); (3) kaki lebih banyak; (4) sidik
    deterministik (pasangan (match_id, garis) terurut) — supaya
    pilihan tidak bergantung urutan penelusuran (leg_id tidak
    membedakan varian: leg_id tidak memuat garis).
    """
    jarak = -mult_net if utamakan_pengali else abs(mult_net - tengah)
    return (-log_p, jarak, -n_kaki, sidik)


def _pengali_maks_asuransi(
    varian_per_laga: list[list[dict]], potongan_pct: float
) -> tuple[float, int]:
    """Pengali maksimum Asuransi (2–6 kaki) + jumlah kakinya.

    Eksak tanpa DP: faktor tiap kaki (100/harga) > 1, jadi pengali
    maksimum memakai garis TERMURAH tiap laga dan mengambil
    _DP_MAKS_KAKI (6) faktor terbesar lintas laga. Dipakai alasan
    jujur bila tiket tidak terbentuk (bukan perkiraan DP).
    """
    termurah = []
    for varian in varian_per_laga:
        if varian:
            termurah.append(min(v["harga_jup"] for v in varian))
    termurah.sort()
    ambil = termurah[:_DP_MAKS_KAKI]
    if not ambil:
        return 0.0, 0
    return combo_multiplier(ambil, potongan_pct), len(ambil)


def _optimasi_asuransi(
    kandidat_ins: list[dict],
    cfg: dict,
    target: dict,
    potongan_pct: float,
) -> dict:
    """Pilih kombinasi Asuransi optimal lintas garis valid (v18.1 #2).

    DP atas bucket log-pengali (langkah ``_DP_LANGKAH_LOG``) yang
    melintasi laga: tiap laga menyumbang 0 atau 1 varian (1 garis
    per laga), total 1–6 kaki (2–6 untuk tiket yang diutamakan;
    1 kaki hanya jalan terakhir seperti ``_pilih_subset``).
    Tujuan: maksimalkan peluang cair gabungan (Σ log decision_prob
    — sama dengan Σ log P_final kecuali condong/recheck-market)
    dengan pengali bersih di [mult_min, mult_max]. Pemilihan akhir
    selalu dicek dengan pengali EKSAK dari harga (pembulatan bucket
    tidak pernah meloloskan kombinasi di luar jendela).
    Bila tidak ada tiket, cari opsi fallback (b) terbaik di
    [fallback_min, mult_min − 0,01] (>= 2 kaki) dari tabel DP yang
    sama (satu kali jalan, dua jendela).

    Mengembalikan {"subset", "pengali", "joint_p", "fallback_option",
    "pengali_maks", "pengali_maks_kaki", "harga_termurah_cents",
    "n_laga_valid"}:
    - subset: list varian tiket (atau None bila tidak ada).
    - pengali / joint_p: pengali bersih + Π decision_prob subset.
    - fallback_option: dict opsi (b) (atau None).
    - pengali_maks (+ kaki): pengali maksimum 1–6 kaki (eksak —
      lihat ``_pengali_maks_asuransi``).
    - harga_termurah_cents: harga termurah di antara semua varian
      (untuk alasan konkret); n_laga_valid: laga yang membawa
      valid_lines.
    """
    mult_min = target["min"]
    mult_max = target["max"]
    fallback_min = _ambang_fallback_ins(cfg, mult_min)
    fallback_max = mult_min - _FALLBACK_JARAK_ATAS
    potongan = 1.0 - potongan_pct / 100.0
    log_potongan = math.log(potongan)
    # Jendela dalam log-pengali KOTOR (sebelum potongan spread):
    # log_net = log_kotor + log_potongan.
    lo_tiket = math.log(mult_min) - log_potongan
    hi_tiket = math.log(mult_max) - log_potongan
    lo_opsi = math.log(fallback_min) - log_potongan
    hi_opsi = math.log(fallback_max) - log_potongan
    tengah_tiket = (mult_min + mult_max) / 2.0

    varian_per_laga = [_varian_kandidat_asuransi(k, cfg) for k in kandidat_ins]
    n_laga_valid = sum(1 for k in kandidat_ins if k.get("valid_lines"))
    harga_termurah = None
    for varian in varian_per_laga:
        for v in varian:
            if harga_termurah is None or v["harga_jup"] < harga_termurah:
                harga_termurah = v["harga_jup"]
    pengali_maks, pengali_maks_kaki = _pengali_maks_asuransi(
        varian_per_laga, potongan_pct
    )
    dasar = {
        "subset": None,
        "pengali": None,
        "joint_p": None,
        "fallback_option": None,
        "pengali_maks": pengali_maks,
        "pengali_maks_kaki": pengali_maks_kaki,
        "harga_termurah_cents": harga_termurah,
        "n_laga_valid": n_laga_valid,
    }
    if not varian_per_laga:
        return dasar

    # Sufiks pengali kotor maksimum per laga (pemangkasan): cabang
    # yang bahkan dengan garis termurah sisa laga tidak mencapai
    # jendela opsi tidak perlu ditelusuri — TAPI hanya dipangkas
    # bila cabang itu juga tidak bisa mencapai jendela tiket
    # (pemangkasan memakai batas bawah opsi karena opsi adalah
    # jendela terendah yang masih berguna).
    maks_per_laga = [
        max(math.log(100.0 / v["harga_jup"]) for v in varian)
        for varian in varian_per_laga
    ]
    n = len(varian_per_laga)
    sufiks = [0.0] * (n + 1)
    for i in range(n - 1, -1, -1):
        sufiks[i] = sufiks[i + 1] + maks_per_laga[i]

    # Status DP: (bucket_log_kotor, jumlah_kaki) ->
    # (log_p_sum, log_kotor_eksak, tuple_varian). Satu entri
    # terbaik per kunci (tie-break kunci DP dengan tengah tiket —
    # pemilihan akhir diulang lintas bucket dengan kunci penuh).
    def _bucket(log_kotor: float) -> int:
        return int(math.floor(log_kotor / _DP_LANGKAH_LOG))

    def _sidik(pilihan: tuple) -> tuple:
        return tuple(sorted((v["match_id"], v["line"]) for v in pilihan))

    status: dict[tuple[int, int], tuple[float, float, tuple]] = {(0, 0): (0.0, 0.0, ())}
    for i, varian in enumerate(varian_per_laga):
        baru = dict(status)
        for (_bk, jumlah), (log_p, log_kotor, pilihan) in status.items():
            if jumlah >= _DP_MAKS_KAKI:
                continue
            # Cabang ini + semua sisa laga tidak mencapai jendela
            # opsi -> tidak ada gunanya (tiket maupun opsi).
            if log_kotor + sufiks[i] < lo_opsi - _EPS:
                continue
            for v in varian:
                log_kotor_baru = log_kotor + math.log(100.0 / v["harga_jup"])
                # Di atas jendela tiket: menambah kaki hanya
                # menaikkan pengali — tidak bisa kembali.
                if log_kotor_baru > hi_tiket + _EPS:
                    continue
                pilihan_baru = pilihan + (v,)
                kunci_baru = (_bucket(log_kotor_baru), jumlah + 1)
                log_p_baru = log_p + math.log(v["decision_prob"])
                lama = baru.get(kunci_baru)
                if lama is None:
                    baru[kunci_baru] = (log_p_baru, log_kotor_baru, pilihan_baru)
                    continue
                # Tie-break dalam bucket: peluang gabungan lebih
                # besar menang; seri -> sidik deterministik.
                if log_p_baru > lama[0] + _EPS or (
                    abs(log_p_baru - lama[0]) <= _EPS
                    and _sidik(pilihan_baru) < _sidik(lama[2])
                ):
                    baru[kunci_baru] = (log_p_baru, log_kotor_baru, pilihan_baru)
        status = baru

    # Pemilihan akhir dari SEMUA status (bukan hanya satu bucket):
    # pengali EKSAK dari harga, jendela tiket dulu (>= 2 kaki;
    # 1 kaki hanya bila tidak ada pilihan lain — perilaku
    # _pilih_subset), lalu jendela opsi (>= 2 kaki).
    def _pilih_dalam_jendela(
        lo: float, hi: float, min_kaki: int, utamakan_pengali: bool, tengah: float
    ):
        terbaik = None
        for (_bucket_k, jumlah), (log_p, log_kotor, pilihan) in status.items():
            if jumlah < min_kaki:
                continue
            if not (lo - _EPS <= log_kotor <= hi + _EPS):
                continue
            mult_net = math.exp(log_kotor + log_potongan)
            # Cek eksak kedua dari harga (bukan dari log yang
            # terakumulasi) — pengali yang dilaporkan & dirakit
            # harus SAMA dengan combo_multiplier.
            mult_eksak = combo_multiplier(
                [v["harga_jup"] for v in pilihan], potongan_pct
            )
            if abs(mult_eksak - mult_net) > 1e-6:
                mult_net = mult_eksak
            kunci = _kunci_dp(
                log_p, mult_net, jumlah, _sidik(pilihan), tengah, utamakan_pengali
            )
            if terbaik is None or kunci < terbaik[0]:
                terbaik = (kunci, pilihan, mult_net, math.exp(log_p))
        return terbaik

    pilihan_tiket = _pilih_dalam_jendela(lo_tiket, hi_tiket, 2, False, tengah_tiket)
    if pilihan_tiket is None:
        pilihan_tiket = _pilih_dalam_jendela(lo_tiket, hi_tiket, 1, False, tengah_tiket)
    if pilihan_tiket is not None:
        _kunci, pilihan, mult_net, joint_p = pilihan_tiket
        dasar["subset"] = list(pilihan)
        dasar["pengali"] = mult_net
        dasar["joint_p"] = joint_p
        return dasar

    # Tidak ada tiket -> opsi fallback (b) terbaik di jendela opsi.
    pilihan_opsi = _pilih_dalam_jendela(
        lo_opsi, hi_opsi, _DP_MIN_KAKI_OPSI, True, (fallback_min + fallback_max) / 2.0
    )
    if pilihan_opsi is not None:
        _kunci, pilihan, mult_net, joint_p = pilihan_opsi
        dasar["fallback_option"] = _rakit_opsi_fallback(
            list(pilihan),
            mult_net,
            joint_p,
            mult_min,
            pengali_maks,
            pengali_maks_kaki,
            len(varian_per_laga),
            harga_termurah,
        )
    return dasar


def _rakit_opsi_fallback(
    pilihan: list[dict],
    mult_net: float,
    joint_p: float,
    mult_min: float,
    pengali_maks: float,
    pengali_maks_kaki: int,
    n_laga: int,
    harga_termurah: float | None,
) -> dict:
    """Rakit dict opsi fallback (b) — BUKAN tiket.

    Tanpa ticket_id/type/stake (gagal validasi skema tiket +
    ditolak ledger). Memuat label OPSI_DI_BAWAH_TARGET, pengali,
    peluang cair gabungan (joint_p_final = Π decision_prob),
    detail per kaki, dan alasan konkret tidak mencapai x2
    (pengali maksimum yang bisa dicapai + jumlah kaki + harga
    termurah yang lolos gate).
    """
    kaki_opsi = []
    for v in pilihan:
        kaki_opsi.append(
            {
                "match_id": v["match_id"],
                "selection": v.get("selection"),
                "line": v["line"],
                "harga_venue_cents": v["harga_jup"],
                "p_final": v["p_final"],
                "p_market": v["p_market"],
                "ev_pct": v["ev_pct"],
                "p_banjir_3p": v.get("p_banjir_3p"),
                "p_banjir_ft": v.get("p_banjir_ft"),
            }
        )
    harga_teks = (
        f"harga termurah yang lolos gate {harga_termurah:g}¢"
        if harga_termurah is not None
        else "tidak ada harga termurah yang tercatat"
    )
    alasan = (
        f"tidak ada kombinasi >= x{mult_min:.2f} tanpa melanggar gate "
        f"(pengali maksimum yang bisa dicapai x{pengali_maks:.2f} "
        f"dengan {pengali_maks_kaki} kaki dari {n_laga} laga yang "
        f"lolos; {harga_teks}) — opsi terbaik di bawah target "
        f"adalah x{mult_net:.2f} dengan peluang cair gabungan "
        f"{joint_p * 100:.0f}%"
    )
    return {
        "label": _LABEL_OPSI_FALLBACK,
        "multiplier": round(mult_net, 4),
        "joint_p_final": round(joint_p, 4),
        "n_legs": len(pilihan),
        "legs": kaki_opsi,
        "alasan": alasan,
    }


def _peringatan_tumpang_tindih_opsi(
    opsi: dict | None, subset_main: list[dict] | None
) -> str | None:
    """Peringatan bila opsi fallback berbagi laga dengan Tiket Utama.

    Opsi BUKAN tiket sehingga tidak memesan laga (Utama diracik
    seolah Asuransi tidak terbentuk) — tapi bila user memasang
    opsi itu DAN Utama, satu laga bisa membunuh keduanya
    (pelajaran DEN 23 Nov). None bila tidak ada opsi / tidak ada
    Utama / tidak ada laga yang sama.
    """
    if opsi is None or not subset_main:
        return None
    laga_opsi = {k.get("match_id") for k in opsi.get("legs") or []}
    laga_main = {k.get("match_id") for k in subset_main}
    bentrok = sorted(laga_opsi & laga_main)
    if not bentrok:
        return None
    return (
        "Opsi Asuransi di bawah target berbagi laga "
        f"{', '.join(bentrok)} dengan Tiket Utama — bila Anda "
        "memasang opsi itu DAN Tiket Utama, satu laga bisa "
        "membunuh keduanya (aturan tanpa kaki kembar hanya "
        "berlaku untuk tiket yang diracik mesin)."
    )


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


def _ringkasan_opsi_fallback(opsi: dict) -> list[str]:
    """Blok ringkasan opsi fallback (b) — eksplisit BUKAN tiket."""
    n_kaki = opsi.get("n_legs")
    if n_kaki is None:
        n_kaki = len(opsi.get("legs") or [])
    baris = [
        "OPSI ASURANSI DI BAWAH TARGET (BUKAN TIKET — keputusan pasang di tangan Anda)",
        f"  Pengali x{opsi['multiplier']:.2f} — peluang cair gabungan "
        f"{opsi['joint_p_final'] * 100:.0f}% — {n_kaki} kaki",
    ]
    for kaki in opsi.get("legs") or []:
        seleksi = kaki.get("selection") or "kaki"
        harga = kaki.get("harga_venue_cents")
        p_final = kaki.get("p_final")
        info = f"  • {seleksi} ({kaki.get('match_id')})"
        if harga is not None:
            info += f" — harga {harga:g}¢"
        if p_final is not None:
            info += f", peluang {p_final * 100:.0f}%"
        baris.append(info)
    baris.append(f"  Alasan: {opsi.get('alasan') or 'tanpa alasan'}")
    return baris


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


def _normalisasi_vonis(nilai) -> str | None:
    """Normalisasi vonis per laga ke token kanonik.

    Menerima ejaan apa pun yang masuk akal ("HIJAU",
    "menengah_hijau", "menengah-cukup-hijau", "KUNING",
    "TUNGGU_LINEUP", spasi / kapital apa pun) -> "hijau" /
    "menengah_hijau" / "kuning" / "tunggu_lineup". Nilai tidak
    dikenal / bukan string -> None (tanpa preferensi alokasi —
    lihat ``_alokasikan_laga``).
    """
    if not isinstance(nilai, str):
        return None
    token = nilai.strip().lower().replace("-", "_").replace(" ", "_")
    if token == "hijau":
        return "hijau"
    if token in ("menengah_hijau", "menengah_cukup_hijau"):
        return "menengah_hijau"
    if token == "kuning":
        return "kuning"
    if token == "tunggu_lineup":
        return "tunggu_lineup"
    return None


def _vonis_dari_nilai(nilai) -> str | None:
    """Ekstrak token vonis dari satu nilai field "vonis".

    Bentuk yang diterima: string ("HIJAU" / "menengah_hijau" /
    "KUNING", ejaan apa pun) atau dict hasil
    ``engine.vonis.nilai_vonis`` ({"vonis": ..., "indikator":
    {"dievaluasi": ...}}). KUNING yang TIDAK dievaluasi
    (dievaluasi False — KUNING-karena-data atau bukan NBA) -> None:
    bukan vonis yang dievaluasi, jadi tidak mengalokasikan (preseden
    skip_awal: tanpa data -> tidak dievaluasi, BUKAN skip; gate per
    kaki yang sudah fail-closed tetap berjalan). Nilai lain -> None.
    """
    if isinstance(nilai, str):
        return _normalisasi_vonis(nilai)
    if isinstance(nilai, dict):
        token = _normalisasi_vonis(nilai.get("vonis"))
        if token is None:
            return None
        if token == "kuning":
            indikator = nilai.get("indikator")
            dievaluasi = (
                indikator.get("dievaluasi") if isinstance(indikator, dict) else None
            )
            if dievaluasi is False:
                return None
        return token
    return None


def _vonis_kandidat(kand: dict) -> str | None:
    """Vonis satu kandidat: field "vonis" kandidat, lalu artefaknya.

    Vonis adalah sifat LAGA (dihitung worker sistem vonis dari
    indikator per laga — DECISIONS.md 2026-11-23 12:33 WIB); dibaca
    dari kandidat bila ada, bila tidak dari artefak analisis yang
    dibawa kandidat. Kedua sumber boleh membawa string vonis atau
    dict hasil ``engine.vonis.nilai_vonis`` (lihat
    ``_vonis_dari_nilai``). None bila tidak ada di keduanya.
    """
    nilai = _vonis_dari_nilai(kand.get("vonis"))
    if nilai is not None:
        return nilai
    analisis = kand.get("analysis")
    if isinstance(analisis, dict):
        return _vonis_dari_nilai(analisis.get("vonis"))
    return None


def _alokasikan_laga(
    kandidat: dict[str, list[dict]], coret: dict[str, list[str]]
) -> dict[str, list[dict]]:
    """Alokasikan laga ke tiket berdasarkan vonis (tanpa kaki kembar).

    ATURAN ALOKASI (keputusan user 2026-11-23 12:20 + 12:33 WIB;
    vonis dari angka, bukan perasaan):
    - Laga HIJAU (sehat) -> ASURANSI DULU: kandidat Asuransinya
      dipertahankan dan kandidat Utamanya JUGA dipertahankan sebagai
      SISA (leftover) — Asuransi memilih dulu di tingkat subset dan
      Utama hanya memakai laga HIJAU yang TIDAK masuk Asuransi
      (filter tanpa-kaki-kembar di ``compose_tickets``). REVISI
      KOORDINATOR v18: sebelumnya kandidat Utama laga HIJAU dibuang
      di sini — pada slate uji v18 (HIJAU 3, MENENGAH 0) aturan itu
      membuat Utama 0 kandidat dan kedua tiket gagal terbentuk
      padahal kaki HIJAU yang tidak terpakai Asuransi terbuang
      percuma. "DULU" dalam keputusan user dibaca sebagai prioritas
      pilih (bukan kepemilikan eksklusif); bila user keberatan,
      yang berubah hanya cabang ini.
    - Laga MENENGAH-HIJAU (cukup hijau) -> UTAMA: kandidat
      Asuransinya dibuang, kandidat Utamanya dipertahankan.
    - Laga KUNING (lempar koin) -> SKIP dari kedua tiket: kedua
      kandidatnya dibuang. KUNING yang TIDAK dievaluasi
      (KUNING-karena-data, indikator.dievaluasi False) BUKAN skip —
      diperlakukan seperti tanpa vonis (lihat ``_vonis_dari_nilai``).
      Catatan: komposer juga mengeluarkan laga KUNING yang
      dievaluasi lebih awal di ``_kumpulkan_kandidat`` (wiring
      worker sistem vonis) — cabang ini adalah pertahanan kedua
      bila kandidat KUNING mencapai alokasi lewat jalur lain.
    - Laga TUNGGU_LINEUP (v18, bintang Questionable) -> SKIP dari
      kedua tiket, sama seperti KUNING (pertahanan kedua — cabang
      utama ada di ``_kumpulkan_kandidat``; laga yang sampai sini
      tidak masuk daftar "menunggu_lineup" hasil compose).
    - Laga TANPA VONIS (artefak lama / sistem vonis belum jalan) ->
      TIDAK ADA preferensi alokasi: kedua kandidat dipertahankan,
      dan disjoint ditegakkan di tingkat subset (Asuransi dipilih
      dulu, Utama membuang laga yang sudah masuk Asuransi — lihat
      ``compose_tickets``). PENYIMPANGAN YANG DIDOKUMENTASIKAN dari
      perintah kerja ("tanpa vonis = menengah_hijau"): menandai
      semua laga tanpa vonis sebagai menengah-hijau akan membuang
      SEMUA kandidat Asuransi dan membuat Asuransi tidak pernah
      terbentuk — termasuk di slate uji yang belum punya vonis.
      Perilaku ini menunggu keberatan koordinator; bila koordinator
      memutuskan lain, yang berubah hanya cabang ini.
    - Laga dengan dua vonis BERBEDA di kedua kandidatnya (data tidak
      konsisten — tidak seharusnya terjadi) -> tanpa preferensi +
      catatan di coret kedua tiket, supaya terlihat di ringkasan.

    Bila satu tiket tidak mencapai target pengali karena pembagian
    ini -> tiket TIDAK TERBENTUK (fail-closed, jangan paksa — lihat
    ``_pilih_subset``: tidak ada subset dalam target -> None).
    Penghapusan dicatat di ``coret`` (alasan jujur di ringkasan +
    alasan tiket yang tidak terracik). Mengembalikan dict kandidat
    baru (dict lama tidak diubah); ``coret`` dimutasi (ditambah).
    """
    vonis_per_laga: dict[str, str] = {}
    bentrok: dict[str, set[str]] = {}
    for tiket in ("insurance", "main"):
        for kand in kandidat[tiket]:
            vonis = _vonis_kandidat(kand)
            if vonis is None:
                continue
            match_id = kand["match_id"]
            lama = vonis_per_laga.get(match_id)
            if lama is None:
                vonis_per_laga[match_id] = vonis
            elif lama != vonis:
                bentrok.setdefault(match_id, set()).add(lama)
                bentrok[match_id].add(vonis)
    for match_id, nilai_set in bentrok.items():
        # Vonis bentrok -> tanpa preferensi (disjoint tetap ditegakkan
        # di tingkat subset) + catatan supaya terlihat.
        del vonis_per_laga[match_id]
        daftar = ", ".join(sorted(nilai_set))
        for tiket in ("insurance", "main"):
            coret[tiket].append(
                f"{match_id}: vonis bentrok ({daftar}) — alokasi "
                "dibatalkan, laga berebut kedua tiket (disjoint "
                "tetap ditegakkan di tingkat subset)"
            )
    baru: dict[str, list[dict]] = {"insurance": [], "main": []}
    for tiket in ("insurance", "main"):
        for kand in kandidat[tiket]:
            match_id = kand["match_id"]
            vonis = vonis_per_laga.get(match_id)
            # REVISI KOORDINATOR v18: laga HIJAU TIDAK lagi membuang
            # kandidat Utamanya di sini — kandidat itu dipertahankan
            # sebagai sisa; Asuransi memilih dulu di tingkat subset
            # dan filter tanpa-kaki-kembar di compose_tickets yang
            # membuang laga yang sudah masuk Asuransi. (Sebelumnya
            # cabang ini membuang kandidat Utama HIJAU sehingga
            # Utama 0 kandidat pada slate uji v18.)
            if vonis == "menengah_hijau" and tiket == "insurance":
                coret["insurance"].append(
                    f"{match_id}: dialokasikan ke Utama (vonis "
                    "menengah-hijau) — tidak masuk Asuransi (aturan "
                    "tanpa kaki kembar)"
                )
                continue
            if vonis == "kuning":
                coret[tiket].append(
                    f"{match_id}: vonis KUNING (lempar koin) — di-skip "
                    "dari kedua tiket"
                )
                continue
            if vonis == "tunggu_lineup":
                coret[tiket].append(
                    f"{match_id}: TUNGGU_LINEUP — bintang masih "
                    "Questionable, di-skip dari kedua tiket"
                )
                continue
            baru[tiket].append(kand)
    return baru


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

    Mengembalikan ``{"insurance", "insurance_reason",
    "insurance_fallback_option", "main", "main_reason", "warnings",
    "skipped_matches", "menunggu_lineup", "summary"}`` — lihat
    docstring modul. ``insurance_fallback_option``: opsi berlabel
    (b) v18.1 (atau None bila tidak ada opsi) — BUKAN tiket.
    ``skipped_matches``: daftar laga yang di-skip dari awal
    ({"match_id", "pemicu", "alasan"}); kosong bila tidak ada laga
    yang di-skip. ``menunggu_lineup``: daftar laga TUNGGU_LINEUP
    ({"match_id", "bintang", "alasan"}); kosong bila tidak ada laga
    yang menunggu lineup.
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
            "insurance_fallback_option": None,
            "main": None,
            "main_reason": alasan,
            "warnings": [],
            "skipped_matches": [],
            "menunggu_lineup": [],
            "summary": (
                "RACIKAN TIKET\nTidak ada analisis untuk diracik — "
                "jalankan analyze dulu untuk slate malam ini."
            ),
        }

    analisis_per_laga = _terbaru_per_laga(analyses, "generated_at")
    recheck_per_laga = _terbaru_per_laga(rechecks or [], "recheck_at")
    lantai, sumber_lantai = _lantai_harga(cfg)
    ambang_yakin, sumber_yakin = _ambang_yakin(cfg)
    ambang_ev: dict[str, float] = {}
    sumber_ev: dict[str, str] = {}
    for tiket_ev in ("insurance", "main"):
        ambang_ev[tiket_ev], sumber_ev[tiket_ev] = _ambang_ev(cfg, tiket_ev)
    skipped_matches: list[dict] = []
    menunggu_lineup: list[dict] = []
    kandidat, coret = _kumpulkan_kandidat(
        analisis_per_laga,
        recheck_per_laga,
        cfg,
        lantai=lantai,
        ambang_ev=ambang_ev,
        skipped=skipped_matches,
        menunggu_lineup=menunggu_lineup,
    )
    # Alokasi laga ke tiket berdasarkan vonis (aturan tanpa kaki
    # kembar — lihat _alokasikan_laga). Berjalan SETELAH kandidat
    # dikumpulkan (vonis dibaca dari kandidat/artefak) dan SEBELUM
    # subset dipilih, supaya pembagian memengaruhi kedua tiket.
    kandidat = _alokasikan_laga(kandidat, coret)

    warnings: list[str] = []
    hasil: dict = {}
    subset_terpilih: dict[str, list[dict] | None] = {}
    info_tiket: dict[str, tuple[float, float]] = {}
    belum_dicek: dict[str, bool] = {}

    # Asuransi dulu (prioritas: laga HIJAU dialokasikan ke Asuransi
    # dulu di _alokasikan_laga; di sini Asuransi memilih subsetnya
    # dulu dan Utama mendapat sisanya — aturan tanpa kaki kembar).
    # v18.1 Patch #2: bila flag optimasi aktif, pilih kombinasi
    # optimal lintas garis valid (DP max joint P_final) + opsi
    # fallback (b); bila flag mati, jalur _pilih_subset v18 persis
    # (rollback — termasuk tanpa opsi fallback).
    opsi_fallback_ins = None
    if _optimasi_asuransi_aktif(cfg):
        hasil_dp = _optimasi_asuransi(
            kandidat["insurance"],
            cfg,
            target["insurance"],
            potongan_pct,
        )
        subset_ins = hasil_dp["subset"]
        maks_ins = hasil_dp["pengali_maks"]
        pangkas_ins = False
        opsi_fallback_ins = hasil_dp["fallback_option"]
    else:
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
    laga_ins_terpilih: set[str] = set()
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
        # v18.1 Patch #2: opsi fallback (b) — alasan tiket tetap
        # menjelaskan x2 tidak terbentuk; opsi disebut sebagai
        # rujukan (bukan tiket).
        if opsi_fallback_ins is not None:
            alasan_ins += (
                " Opsi di bawah target tersedia (pengali "
                f"x{opsi_fallback_ins['multiplier']:.2f}, peluang cair "
                f"{opsi_fallback_ins['joint_p_final'] * 100:.0f}%) — "
                "lihat kunci insurance_fallback_option (bukan tiket, "
                "keputusan pasang di tangan Anda)."
            )
            warnings.append(
                "Tiket Asuransi x"
                f"{target['insurance']['min']:.2f} tidak terbentuk — "
                "ada opsi di bawah target "
                f"(pengali x{opsi_fallback_ins['multiplier']:.2f}, "
                "peluang cair "
                f"{opsi_fallback_ins['joint_p_final'] * 100:.0f}%) di "
                "kunci insurance_fallback_option; itu BUKAN tiket."
            )
        hasil["insurance"] = None
        hasil["insurance_reason"] = alasan_ins
        subset_terpilih["insurance"] = None
        belum_dicek["insurance"] = False
    else:
        laga_ins_terpilih = {k["match_id"] for k in subset_ins}
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
            # v18: kaki thin BOLEH masuk Asuransi bila lolos gate
            # eksekusi ($30) — tapi tetap diperingatkan (INFO).
            for kand in subset_ins:
                if kand.get("thin"):
                    seleksi = kand.get("selection") or "kaki"
                    warnings.append(
                        f"Kaki Asuransi {kand['match_id']} ({seleksi}) "
                        "bervolume tipis — harganya bisa bergerak saat "
                        "pasang, sebaiknya cek lagi sebelum submit."
                    )
            if ev_ins < 0:
                warnings.append(
                    f"EV tiket Asuransi negatif ({ev_ins:+.0f}%) — secara "
                    "hitungan, tiket ini merugi dalam jangka panjang."
                )

    # Opsi fallback (b) v18.1 — kuncinya selalu ada (None bila
    # tidak ada opsi), supaya bentuk hasil stabil.
    hasil["insurance_fallback_option"] = opsi_fallback_ins

    # Utama: TANPA KAKI KEMBAR (keputusan user 2026-11-23 12:20 WIB —
    # MENGGANTIKAN aturan lama "garis berbeda"): kaki Utama dari laga
    # yang sudah masuk Asuransi DIBUANG seluruhnya, apa pun garisnya.
    # Alokasi vonis di _alokasikan_laga sudah memisahkan laga
    # HIJAU/menengah-hijau di tingkat kandidat; filter ini adalah
    # pertahanan kedua untuk laga tanpa vonis (kedua tiket masih
    # berebut laga yang sama) + menjamin himpunan laga kedua tiket
    # disjoint apa pun yang terjadi di atas. Bila Asuransi tidak
    # terbentuk, tidak ada yang difilter (tidak ada kembar yang bisa
    # terjadi).
    kandidat_main = kandidat["main"]
    catatan_kembar: list[str] = []
    if subset_terpilih["insurance"]:
        tersaring = []
        for kand in kandidat_main:
            if kand["match_id"] in laga_ins_terpilih:
                catatan_kembar.append(
                    f"Laga {kand['match_id']} hanya masuk Asuransi "
                    "(aturan tanpa kaki kembar — satu laga tidak boleh "
                    "ada di kedua tiket)."
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
            rincian = list(coret["main"]) + catatan_kembar
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
        catatan_main: list[str] = list(catatan_kembar)
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
            # v18: banjir Utama warning-only (tidak memblokir) —
            # kaki yang rapuh banjir tetap diperingatkan.
            for kand in subset_main:
                if kand.get("banjir_warning"):
                    seleksi = kand.get("selection") or "kaki"
                    p_3p_w = kand.get("p_banjir_3p")
                    p_ft_w = kand.get("p_banjir_ft")
                    detail = ""
                    if p_3p_w is not None and p_ft_w is not None:
                        detail = (
                            f" (peluang lolos banjir 3P "
                            f"{p_3p_w * 100:.0f}%, banjir FT "
                            f"{p_ft_w * 100:.0f}%)"
                        )
                    warnings.append(
                        f"Kaki Utama {kand['match_id']} ({seleksi}) "
                        "rapuh bila laga banjir poin" + detail + " — "
                        "kaki ini tidak lolos standar banjir Asuransi."
                    )
            if ev_main < 0:
                warnings.append(
                    f"EV tiket Utama negatif ({ev_main:+.0f}%) — secara "
                    "hitungan, tiket ini merugi dalam jangka panjang."
                )

    # v18.1 Patch #2: opsi fallback (b) bukan tiket sehingga tidak
    # memesan laga dari Utama — tapi bila berbagi laga dengan
    # Utama, peringatkan (pelajaran DEN: satu laga bisa membunuh
    # kedua tiket bila user memasang keduanya).
    peringatan_opsi = _peringatan_tumpang_tindih_opsi(
        opsi_fallback_ins, subset_terpilih["main"]
    )
    if peringatan_opsi is not None:
        warnings.append(peringatan_opsi)

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
    if opsi_fallback_ins is not None:
        baris += _ringkasan_opsi_fallback(opsi_fallback_ins)
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
    if skipped_matches:
        # Semua laga dilaporkan, termasuk yang di-skip, beserta
        # alasannya (keputusan user 2026-11-23 10:41 WIB).
        baris += ["", "LAGA YANG DI-SKIP DARI AWAL (tidak masuk tiket mana pun):"]
        for item in skipped_matches:
            pemicu = ", ".join(item.get("pemicu") or [])
            baris.append(
                f"  • {item.get('match_id')}"
                + (f" [{pemicu}]" if pemicu else "")
                + f": {item.get('alasan') or 'tanpa alasan'}"
            )
    if menunggu_lineup:
        baris += [
            "",
            "LAGA YANG MENUNGGU LINEUP (tidak masuk tiket — cek lagi "
            "setelah injury report final):",
        ]
        for item in menunggu_lineup:
            bintang = item.get("bintang") or []
            baris.append(
                f"  • {item.get('match_id')}"
                + (f" ({', '.join(bintang)})" if bintang else "")
                + f": {item.get('alasan') or 'tanpa alasan'}"
            )
    catatan_ringkas = list(catatan_kembar)
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
    if sumber_ev.get("insurance") == "default":
        catatan_ringkas.append(
            "Gate EV minimum Asuransi "
            f"{_DEFAULT_MAX_NEG_EV_INS_PCT:g}% (nilai default — kunci "
            "tickets.insurance.max_negative_ev_pct belum ada di config)."
        )
    if sumber_ev.get("main") == "default":
        catatan_ringkas.append(
            "Gate EV minimum Utama "
            f"{_DEFAULT_MAX_NEG_EV_MAIN_PCT:g}% (nilai default — kunci "
            "tickets.main.max_negative_ev_pct belum ada di config)."
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
    hasil["skipped_matches"] = skipped_matches
    hasil["menunggu_lineup"] = menunggu_lineup
    hasil["summary"] = "\n".join(baris)
    return hasil
