"""Titik equilibrium per kaki NBA (keputusan user 2026-11-23 10:31 + 10:41 WIB).

DEFINISI (disepakati user: "cari titik paling manis per kaki; tumpuk
kaki-kaki yang benar-benar kuat hingga Asuransi x2 dan Utama x3+").
Untuk satu laga + satu tiket, dari distribusi sim 100.000x (CDF total
di ``simulation.markets``) + tangga Polymarket (``market.totals``):
di antara garis Under yang lolos SEMUA gate tiket itu, equilibrium
adalah garis yang dipilih MODE tiket itu (config ``equilibrium.
mode_insurance`` / ``equilibrium.mode_main``):

- "max_er" (Utama): garis yang memaksimalkan expected return
  ER(garis) = p_final(garis) x (100 / harga_venue(garis)), yaitu
  ekspektasi pengembalian per $1 bila kaki itu dipasang sendiri
  (ER = 1 + EV). Seri (selisih ER < 1e-9): p_final lebih besar, lalu
  garis lebih kecil (deterministik).
- "safety_first" (Asuransi, keputusan user 2026-11-23 12:20 + 12:33
  WIB): garis dengan p_final TERTINGGI (paling aman) di antara garis
  yang lolos semua gate. Seri p_final (< 1e-9): ER lebih tinggi, lalu
  garis lebih kecil. Alasan: Asuransi adalah permainan yang
  "benar-benar bisa menyelamatkan dari kegagalan Utama" — titik
  manisnya adalah yang paling aman, bukan yang nilai harapannya
  tertinggi. KONSEKUENSI: garis paling aman adalah garis termahal,
  jadi pengali per kaki kecil dan Asuransi butuh LEBIH BANYAK kaki
  untuk mencapai target x2 — kendala pengali tiket tetap ditegakkan
  peracik (``ticket_composer._pilih_subset``), bukan di sini.

KENAPA MAX-ER (alasan definisi, untuk Utama): aturan lama memilih
yang lolos ambang — garis itu lolos saringan, tapi belum tentu titik
manisnya: garis yang sedikit lebih mahal bisa jauh lebih mungkin
menang sehingga nilai harapannya lebih tinggi, atau sebaliknya garis
lebih murah bisa memberi nilai lebih baik dengan peluang yang masih
di atas ambang. Max-ER adalah titik di mana "distribusi normal bilang
kaki itu paling oke" (kata user): di situlah harga dan peluang
bertemu paling menguntungkan. Kendala target pengali TIKET (x2/x3+)
bukan urusan per kaki — itu diurus pemilihan subset peracik
(``ticket_composer._pilih_subset``), yang menumpuk kaki-kaki
equilibrium hingga target tercapai. TIDAK ADA floor ER > 1: max-ER
adalah yang terbaik yang tersedia; bila titik manisnya pun ber-EV
negatif, itu dilaporkan transparan (bukan disembunyikan) dan kelayakan
tiket dinilai di tingkat tiket.

GATE PER GARIS v18 (keputusan user 2026-11-23 13:57 WIB, atas
proposal audit Gemini v18 — MENGGANTIKAN gate v17: edge datar 3,5%
DIHAPUS, banjir tunggal 74% DIGANTI dua ambang terpisah, thin $100
DIGANTI gate eksekusi berbasis stake):
- Asuransi: p_final >= tickets.insurance.min_leg_prob (0,82);
  p_market >= tickets.insurance.min_p_market (0,80) — bila p_market
  tidak ada (MODEL_ONLY, tanpa jangkar), gate ini TIDAK dievaluasi
  (bukan fail-closed buta: garis tetap boleh lolos bila p_final +
  banjir + EV lolos, dengan catatan "p_market tidak dievaluasi");
  EV >= tickets.insurance.max_negative_ev_pct (-1%) — EV
  MENGGANTIKAN edge datar (edge datar mustahil di ekor 85-94¢:
  audit Gemini §1.2); P banjir 3P >= flood_3p_min (0,70) DAN
  P banjir FT >= flood_ft_min (0,65) — DUA ambang terpisah dari CDF
  yang digeser, seperti sebelumnya; harga venue >= lantai Asuransi
  (75¢); EKSEKUSI: gate eksekusi (lihat di bawah).
- Utama: p_final >= tickets.main.min_leg_prob (0,74); EV >=
  tickets.main.max_negative_ev_pct (-2%, tolak bila sangat MAHAL);
  harga venue >= lantai Utama (75¢); EKSEKUSI: gate eksekusi (sama
  seperti Asuransi). Banjir WARNING-ONLY untuk Utama: P banjir
  dicatat (p_banjir_3p / p_banjir_ft + flag banjir_warning), tidak
  memblokir.
- EKSEKUSI -> GATE LIKUIDITAS + SPREAD (v18, revisi koordinator
  saat integrasi — MENGGANTIKAN gate volume_usd worker B):
  garis lolos hanya bila likuiditas Gamma (`liquidity`, USD) >=
  max(execution.min_liquidity_multiplier x
  execution.stake_default_usd, execution.liquidity_hard_min_usd)
  = max(2 x $15, $25) = $30 DAN spread bid/ask (ask_cents -
  bid_cents, kuotasi CLOB Gamma) <= execution.max_spread_cents
  (5,0¢) DAN ask nyata (< 99¢). Alasan revisi: volume_usd adalah
  volume KUMULATIF yang sudah diperdagangkan — ukuran sejarah,
  bukan kemampuan beli sekarang; garis dengan kuotasi hidup
  spread 2¢ gagal gate volume karena volume kumulatifnya $5,
  padahal order $15 di ask pasti terisi (bukti: artefak 22 Nov,
  DET U239,5 bid 79/ask 82, likuiditas $36.580, volume $5).
  Data hilang (likuiditas/bid/ask tidak tercatat) -> TIDAK lolos
  (fail-closed) + dicatat. Volume kumulatif < $100 (ambang lama
  polymarket_ladder.min_volume_usd) dicatat sebagai info
  (info_volume_dibawah_100), BUKAN blokir. Flag "thin" TIDAK LAGI
  menjadi gate di modul ini (thin tetap dilaporkan apa adanya).
- BAND HARGA + PEMILIHAN (v18): Asuransi safety-first memilih
  p_final TERTINGGI di antara garis lolos DALAM band
  tickets.insurance.preferred_price_band (80-89¢); bila tidak ada
  garis lolos dalam band, fallback ke p_final tertinggi di antara
  SEMUA garis lolos (fallback_band=True dicatat). Utama max-ER
  memilih ER tertinggi dalam band tickets.main.preferred_price_band
  (76-84¢) dengan tie-break: bila selisih ER < tiebreak_er_tolerance
  (0,015), pilih garis yang LEBIH AMAN (p_final lebih tinggi);
  fallback band yang sama bila tidak ada garis lolos dalam band.

P_FINAL PER GARIS (jangkar pasar): artefak hanya membawa p_market
untuk dua kaki artefak (dari Kalshi, garis yang sama persis) — tangga
Kalshi tidak disimpan di artefak, jadi p_market per garis tangga
TIDAK BISA dibaca langsung. Yang dilakukan modul ini: hitung GESER
PASAR δ dari kaki jangkar (kaki artefak mana pun yang bergaris +
ber-p_market; utamakan tiket yang sama):
δ = garis_jangkar − CDF⁻¹(p_market_jangkar), lalu
p_market(garis) = CDF(garis − δ) dan p_final = blend w=0,3.
ASUMSI (didokumentasikan, bukan disembunyikan): pasar dan model
berbeda hanya oleh GESERAN LOKASI — asumsi yang SAMA dengan yang
dipakai engine/stress.py untuk banjir (geser lokasi, sigma tetap).
P2 DIHORMATI: sumber pembanding tetap Kalshi (jangkar); harga
Polymarket hanya dipakai sebagai HARGA (biaya), bukan sebagai
p_market. Tanpa jangkar pasar -> equilibrium TIDAK DIHITUNG (bukan
"tidak ada") — lihat ``butuh_anchor_pasar`` di config.

MENGGANTIKAN ATURAN LAMA: komposer memakai garis equilibrium bila
terhitung (``ticket_composer``). Gate banjir komposer tetap berjalan
sebagai pertahanan lapis kedua (lolos by construction pada kaki
equilibrium). Konsekuensi yang disengaja: equilibrium BOLEH melompati
garis tahan-banjir yang thin ke garis tebal di atasnya — keputusan
lama "gate TIDAK melompat" (LAPORAN-ATURAN-KERAS.md §7.1) digantikan,
karena keputusan itu hanya bermakna di dalam mekanisme climb
("naik ke garis tahan ITU"); equilibrium tidak memanjat — ia menilai
SEMUA garis dan memilih yang terbaik di antara yang lolos.
Kaki equilibrium dibangun ulang (``rakit_kaki_equilibrium``):
p_model/p_market/p_final/EV/label dihitung di garis baru — ini
MEMPERBAIKI interaksi gate banjir × gate edge (§5 laporan aturan
keras): kaki yang naik garis tidak lagi memakai p_final garis lama.

TIDAK DIHITUNG vs TIDAK ADA: tanpa CDF / tanpa tangga / tanpa jangkar
pasar -> ``dihitung=False`` -> komposer memakai kaki artefak apa
adanya (fallback). Equilibrium adalah peningkatan seleksi, bukan gate
ketersediaan data — artefak tanpa tangga (mis. ladder fetch gagal)
tidak boleh membuat semua kaki hilang. ``dihitung=True`` + ``ada=
False`` berarti dihitung sungguh-sungguh dan TIDAK ADA garis yang
lolos semua gate -> kaki itu ditolak (alasan diagnostik tercatat).

KETERBATASAN (dicatat jujur):
- p_final di garis baru memakai asumsi geser-lokasi (di atas); bila
  pasar dan model berbeda bentuk (bukan hanya lokasi), p_final di
  garis jauh dari jangkar bisa meleset.
- Recheck menilai garis LAMA (leg_id tidak berubah — pola yang sama
  dengan climb banjir): putusan recheck bisa basi untuk garis baru.
- CDF dijepit di ujung (tanpa ekstrapolasi, seperti stress.py):
  P di garis di luar jangkauan CDF bisa terlalu rendah (garis atas)
  atau terlalu tinggi (garis bawah) — konservatif untuk garis atas.
- Harga venue = jup_estimated_cents (fallback price_cents), sama
  seperti komposer.

Modul ini MURNI HITUNG: tanpa fetch, tanpa simulasi ulang, tanpa
Odds API. Satu-satunya I/O adalah baca config bila argumen cfg None.
"""

from __future__ import annotations

import math

import config as config_mod
from engine import price_labels as price_labels_mod
from engine import stress as stress_mod

FORMAT = "nba_equilibrium"
FORMAT_VERSION = 1

# Toleransi seri expected return / p_final (lihat docstring modul).
_EPS_ER = 1e-9

_TIKET = ("insurance", "main")

# Mode pemilihan equilibrium per tiket (config equilibrium.
# mode_insurance / mode_main). "max_er": ER tertinggi; "safety_first":
# p_final tertinggi. Nilai lain -> ConfigError (fail-closed).
_MODE = ("max_er", "safety_first")

# Default kunci v18 (dipakai HANYA bila kunci belum ada di cfg dict
# — mis. dict cfg di tes — mengikuti pola _angka_config_atau_default
# di ticket_composer untuk integrasi paralel). Nilai-nilai ini BUKAN
# tebakan: SAMA PERSIS dengan config v18 yang ditulis worker A
# (keputusan user 2026-11-23 13:57 WIB + proposal audit Gemini v18
# §3, DECISIONS.md "Jawaban user atas 4 keputusan v18"). Bila
# config v18 sudah mendarat, nilai config yang dipakai (default
# tidak pernah menimpa config).
_DEFAULT_MIN_P_MARKET_INS = 0.80
_DEFAULT_MAX_NEG_EV_INS_PCT = -1.0
_DEFAULT_MAX_NEG_EV_MAIN_PCT = -2.0
_DEFAULT_FLOOD_3P_MIN = 0.70
_DEFAULT_FLOOD_FT_MIN = 0.65
_DEFAULT_BAND_INS = (80.0, 89.0)
_DEFAULT_BAND_MAIN = (76.0, 84.0)
_DEFAULT_TIEBREAK_ER = 0.015
_DEFAULT_LIQ_MULTIPLIER = 2.0
_DEFAULT_LIQ_HARD_MIN_USD = 25.0
_DEFAULT_STAKE_USD = 15.0
_DEFAULT_MAX_SPREAD_CENTS = 5.0
_DEFAULT_MIN_VOLUME_INFO_USD = 100.0


def _angka(nilai) -> float | None:
    """Ubah nilai menjadi float berhingga, atau None bila tidak valid."""
    if isinstance(nilai, bool) or nilai is None:
        return None
    try:
        hasil = float(nilai)
    except (TypeError, ValueError):
        return None
    return hasil if math.isfinite(hasil) else None


def _ambang(cfg: dict, *kunci: str) -> float:
    """Ambil ambang numerik dari config; hilang/tidak valid -> ConfigError."""
    nilai = config_mod.get_value(cfg, *kunci)
    hasil = _angka(nilai)
    if hasil is None:
        raise config_mod.ConfigError(
            f"playstyle.yaml kunci {'.'.join(kunci)} bukan angka: {nilai!r}"
        )
    return hasil


def _cfg_angka_atau_default(cfg: dict, kunci: tuple[str, ...], default: float) -> float:
    """Baca angka dari config; kunci hilang -> default (v18).

    Kunci ADA tapi bukan angka -> ConfigError (config rusak, bukan
    data hilang). Dipakai untuk kunci BARU v18 (min_p_market,
    max_negative_ev_pct, flood_3p_min, flood_ft_min,
    tiebreak_er_tolerance, execution.*) supaya modul tetap jalan
    dengan dict cfg yang belum membawa kunci itu (tes / integrasi
    paralel) — defaultnya adalah nilai v18 yang disetujui user
    (lihat konstanta _DEFAULT_* di atas), bukan karangan.
    """
    try:
        nilai = config_mod.get_value(cfg, *kunci)
    except config_mod.ConfigError:
        return default
    hasil = _angka(nilai)
    if hasil is None:
        raise config_mod.ConfigError(
            f"playstyle.yaml kunci {'.'.join(kunci)} bukan angka: {nilai!r}"
        )
    return hasil


def _cfg_band(cfg: dict, tiket: str) -> tuple[float, float]:
    """Band harga pilihan satu tiket (sen) dari config v18.

    Kunci: tickets.<tiket>.preferred_price_band [lo, hi]. Hilang ->
    default v18 (Asuransi 80-89, Utama 76-84). Bentuk salah / bukan
    angka / lo > hi -> ConfigError.
    """
    default = _DEFAULT_BAND_INS if tiket == "insurance" else _DEFAULT_BAND_MAIN
    try:
        nilai = config_mod.get_value(cfg, "tickets", tiket, "preferred_price_band")
    except config_mod.ConfigError:
        return default
    if not isinstance(nilai, (list, tuple)) or len(nilai) != 2:
        raise config_mod.ConfigError(
            "playstyle.yaml tickets."
            f"{tiket}.preferred_price_band harus [bawah, atas], dapat: "
            f"{nilai!r}"
        )
    bawah = _angka(nilai[0])
    atas = _angka(nilai[1])
    if bawah is None or atas is None or bawah > atas:
        raise config_mod.ConfigError(
            "playstyle.yaml tickets."
            f"{tiket}.preferred_price_band tidak valid: {nilai!r}"
        )
    return bawah, atas


def likuiditas_min_eksekusi(cfg: dict | None = None) -> float:
    """Likuiditas minimum gate eksekusi v18 (USD).

    max(min_liquidity_multiplier x stake_default_usd,
    liquidity_hard_min_usd) = max(2 x $15, $25) = $30 (config v18).
    Dipakai equilibrium + komposer (satu rumus, dua pemakai).
    Berlaku untuk field `liquidity` Gamma (likuiditas pasar saat
    ini), BUKAN volume_usd kumulatif (revisi koordinator v18).
    """
    cfg = _muat_cfg(cfg)
    pengali = _cfg_angka_atau_default(
        cfg, ("execution", "min_liquidity_multiplier"), _DEFAULT_LIQ_MULTIPLIER
    )
    modal = _cfg_angka_atau_default(
        cfg, ("execution", "stake_default_usd"), _DEFAULT_STAKE_USD
    )
    batas_bawah = _cfg_angka_atau_default(
        cfg, ("execution", "liquidity_hard_min_usd"), _DEFAULT_LIQ_HARD_MIN_USD
    )
    if pengali < 0 or modal < 0 or batas_bawah < 0:
        raise config_mod.ConfigError(
            "playstyle.yaml execution.* harus >= 0 "
            f"(pengali {pengali}, stake {modal}, batas bawah {batas_bawah})"
        )
    return max(pengali * modal, batas_bawah)


def cek_eksekusi(entri: dict, cfg: dict | None = None) -> dict:
    """Gate eksekusi v18 untuk satu entri tangga (SATU implementasi).

    Dipakai equilibrium._nilai_garis + komposer (garis tahan banjir
    + cek kaki via tangga) — satu definisi "garis bisa dibeli".
    Lolos bila SEMUA terpenuhi: likuiditas Gamma >=
    likuiditas_min_eksekusi ($30) DAN bid/ask tercatat DAN ask nyata
    (< 99¢, sentinel "tidak ada ask") DAN spread (ask - bid) <=
    execution.max_spread_cents (5,0¢). Data hilang -> tidak lolos
    (fail-closed). Mengembalikan dict lolos/alasan/nilai-nilai
    (alasan None bila lolos; bila gagal salah satu dari:
    "likuiditas_tidak_tercatat", "likuiditas_di_bawah_minimum",
    "tanpa_kuotasi", "tanpa_ask_nyata", "spread_terlalu_lebar").
    """
    cfg = _muat_cfg(cfg)
    likuiditas_min = likuiditas_min_eksekusi(cfg)
    spread_max = _cfg_angka_atau_default(
        cfg, ("execution", "max_spread_cents"), _DEFAULT_MAX_SPREAD_CENTS
    )
    likuiditas = _angka(entri.get("liquidity"))
    bid = _angka(entri.get("bid_cents"))
    ask = _angka(entri.get("ask_cents"))
    spread = (ask - bid) if (bid is not None and ask is not None) else None
    if likuiditas is None:
        alasan = "likuiditas_tidak_tercatat"
    elif likuiditas < likuiditas_min:
        alasan = "likuiditas_di_bawah_minimum"
    elif bid is None or ask is None:
        alasan = "tanpa_kuotasi"
    elif ask >= 99.0:
        alasan = "tanpa_ask_nyata"
    elif spread is not None and spread > spread_max:
        alasan = "spread_terlalu_lebar"
    else:
        alasan = None
    return {
        "lolos": alasan is None,
        "alasan": alasan,
        "likuiditas_usd": likuiditas,
        "likuiditas_min_usd": likuiditas_min,
        "bid_cents": bid,
        "ask_cents": ask,
        "spread_cents": spread,
        "spread_max_cents": spread_max,
        "volume_usd": _angka(entri.get("volume_usd")),
    }


def _harga_venue(entri: dict) -> float | None:
    """Harga venue jup.ag satu entri tangga (jup, fallback Polymarket)."""
    harga = _angka(entri.get("jup_estimated_cents"))
    if harga is not None:
        return harga
    return _angka(entri.get("price_cents"))


def _muat_cfg(cfg: dict | None) -> dict:
    if cfg is not None:
        return cfg
    return config_mod.load_playstyle()


def _mode_equilibrium(cfg: dict, tiket: str) -> str:
    """Mode pemilihan equilibrium satu tiket dari config.

    Kunci: ``equilibrium.mode_insurance`` / ``equilibrium.
    mode_main``. Hilang / bukan string / tidak dikenal ->
    ConfigError (fail-closed: mode yang salah diam-diam lebih buruk
    daripada error keras).
    """
    kunci = f"mode_{tiket}"
    mode = config_mod.get_value(cfg, "equilibrium", kunci)
    if not isinstance(mode, str) or mode not in _MODE:
        raise config_mod.ConfigError(
            f"playstyle.yaml equilibrium.{kunci} harus salah satu dari "
            f"{list(_MODE)}, dapat: {mode!r}"
        )
    return mode


def inversi_cdf(cdf: list[tuple[float, float]], p_target: float) -> float:
    """Garis x dengan CDF(x) = p_target (interpolasi linear).

    Di luar jangkauan CDF, dijepit ke ujung (tidak ada ekstrapolasi —
    konsisten dengan ``stress.p_under_digeser``).
    """
    if not cdf:
        raise ValueError("cdf tidak boleh kosong")
    if p_target <= cdf[0][1]:
        return cdf[0][0]
    if p_target >= cdf[-1][1]:
        return cdf[-1][0]
    for (g0, p0), (g1, p1) in zip(cdf, cdf[1:], strict=True):
        if p0 <= p_target <= p1:
            if p1 == p0:
                return g0
            return g0 + (p_target - p0) * (g1 - g0) / (p1 - p0)
    raise ValueError(f"inversi CDF gagal untuk p={p_target}")


def _jangkar_pasar(analysis: dict, tiket: str) -> dict | None:
    """Kaki jangkar: kaki artefak bergaris + ber-p_market.

    Utamakan tiket yang diminta; bila tidak ada, pakai tiket lain
    (geser pasar adalah sifat LAGA, bukan sifat tiket — pasar dan
    model bergeser sama untuk kedua kaki laga itu, sampai orde
    pertama). None bila tidak ada kaki artefak yang bisa jadi jangkar.
    """
    kaki_list = [
        leg
        for leg in (analysis.get("legs") or [])
        if isinstance(leg, dict)
        and _angka(leg.get("line")) is not None
        and _angka(leg.get("p_market")) is not None
    ]
    if not kaki_list:
        return None
    for leg in kaki_list:
        if leg.get("ticket") == tiket:
            return leg
    return kaki_list[0]


def siapkan_konteks(analysis: dict, tiket: str, cfg: dict | None = None) -> dict:
    """Konteks hitung bersama equilibrium + skip_awal satu laga.

    Mengembalikan dict {"ok", "alasan", "cdf", "tangga", "delta",
    "anchor", "w", "geser_banjir_terburuk", "banjir_terburuk",
    "geser_banjir_3p", "geser_banjir_ft", "geser_setan", "median",
    "garis_market"}. "ok" False (bukan raise) bila data artefak
    tidak lengkap (tanpa CDF / tanpa tangga / tanpa jangkar pasar)
    — itu keadaan operasional yang sah, bukan bug. Config rusak ->
    ConfigError (fail-closed, seperti stress.py). Geser banjir
    3P/FT terpisah (v18: gate banjir dua ambang); geser terburuk
    dipertahankan untuk kompatibilitas (skip_awal / vonis).
    """
    if tiket not in _TIKET:
        raise ValueError(f"tiket tidak dikenal: {tiket!r}")
    cfg = _muat_cfg(cfg)
    geser_3p = _ambang(cfg, "stress", "banjir_3p_points")
    geser_ft = _ambang(cfg, "stress", "banjir_ft_points")
    geser_setan = _ambang(cfg, "stress", "setan_points")
    if geser_3p < 0 or geser_ft < 0 or geser_setan < 0:
        raise config_mod.ConfigError("geser banjir/setan harus >= 0")
    if geser_ft >= geser_3p:
        banjir_terburuk, geser_terburuk = "banjir_ft", geser_ft
    else:
        banjir_terburuk, geser_terburuk = "banjir_3p", geser_3p
    dasar = {
        "ok": False,
        "alasan": None,
        "cdf": None,
        "tangga": None,
        "delta": None,
        "anchor": None,
        "w": None,
        "geser_banjir_terburuk": geser_terburuk,
        "banjir_terburuk": banjir_terburuk,
        "geser_banjir_3p": geser_3p,
        "geser_banjir_ft": geser_ft,
        "geser_setan": geser_setan,
        "median": None,
        "garis_market": None,
    }
    sim = analysis.get("simulation")
    if not isinstance(sim, dict):
        dasar["alasan"] = "artefak tanpa blok simulation"
        return dasar
    try:
        cdf = stress_mod.cdf_total_dari_markets(sim.get("markets"))
    except ValueError as exc:
        dasar["alasan"] = f"CDF total tidak bisa dibangun: {exc}"
        return dasar
    market = (
        analysis.get("market") if isinstance(analysis.get("market"), dict) else None
    )
    tangga = stress_mod.tangga_under(market)
    if not tangga:
        dasar["alasan"] = "tangga total Under tidak ada di artefak"
        return dasar
    butuh_anchor = config_mod.get_value(cfg, "equilibrium", "butuh_anchor_pasar")
    anchor = _jangkar_pasar(analysis, tiket)
    delta = None
    if anchor is None:
        if butuh_anchor is True:
            dasar["alasan"] = (
                "tanpa jangkar pasar: tidak ada kaki artefak bergaris + "
                "p_market, jadi p_final per garis tidak bisa dihitung"
            )
            return dasar
    else:
        garis_anchor = float(anchor["line"])
        p_market_anchor = float(anchor["p_market"])
        delta = garis_anchor - inversi_cdf(cdf, p_market_anchor)
    try:
        w = _ambang(cfg, "blend", "w_model")
    except config_mod.ConfigError:
        raise
    if not 0.0 <= w <= 1.0:
        raise config_mod.ConfigError(f"blend.w_model di luar 0-1: {w}")
    dist = sim.get("score_distribution") or {}
    total = dist.get("total") if isinstance(dist, dict) else None
    median = _angka(total.get("median")) if isinstance(total, dict) else None
    garis_market = _angka(market.get("main_total_line")) if market else None
    dasar.update(
        {
            "ok": True,
            "cdf": cdf,
            "tangga": tangga,
            "delta": delta,
            "anchor": (
                {
                    "line": _angka(anchor.get("line")),
                    "ticket": anchor.get("ticket"),
                    "p_market": _angka(anchor.get("p_market")),
                    "comparison_source": anchor.get("comparison_source"),
                }
                if anchor is not None
                else None
            ),
            "w": w,
            "median": median,
            "garis_market": garis_market,
        }
    )
    return dasar


def peluang_pada_garis(ktx: dict, garis: float) -> tuple[float, float | None, float]:
    """(p_model, p_market, p_final) di satu garis dari konteks.

    p_market None bila konteks tanpa jangkar (delta None) — dalam hal
    itu p_final = p_model (MODEL_ONLY per garis; hanya terjadi bila
    config butuh_anchor_pasar false — BUKAN nilai produksi).
    """
    cdf = ktx["cdf"]
    p_model = stress_mod.p_under_digeser(cdf, garis, 0.0)
    delta = ktx["delta"]
    if delta is None:
        return p_model, None, p_model
    p_market = stress_mod.p_under_digeser(cdf, garis, delta)
    w = ktx["w"]
    p_final = w * p_model + (1.0 - w) * p_market
    return p_model, p_market, p_final


def _label_ev(ev_pct: float, cfg: dict) -> str | None:
    """Label harga dari EV (None bila tidak bisa dihitung)."""
    try:
        return price_labels_mod.label_for_ev(ev_pct, cfg)
    except (ValueError, config_mod.ConfigError):
        return None


def _nilai_garis(
    ktx: dict, entri: dict, tiket: str, ambang: float, cfg: dict
) -> dict | None:
    """Nilai satu garis tangga: peluang + harga + hasil tiap gate (v18).

    None bila garis tidak punya harga venue yang valid (tidak bisa
    dibeli — tidak dinilai sama sekali). "lolos_semua" True bila
    semua gate tiket itu lolos. Gate v18 (lihat docstring modul):
    Asuransi = peluang + p_market + banjir_3p + banjir_ft + ev +
    lantai_harga + eksekusi; Utama = peluang + lantai_harga + ev +
    eksekusi (banjir warning-only, dicatat di "banjir_warning").
    "edge" tetap dihitung (informatif — dipakai vonis + laporan),
    tapi BUKAN gate lagi (edge datar 3,5% DIHAPUS v18, diganti EV).
    "thin" tetap dilaporkan apa adanya, tapi BUKAN gate lagi
    (diganti gate eksekusi likuiditas + spread — cek_eksekusi).
    """
    garis = float(entri["line"])
    harga = _harga_venue(entri)
    if harga is None or not 0.0 < harga < 100.0:
        return None
    p_model, p_market, p_final = peluang_pada_garis(ktx, garis)
    p_banjir_3p = stress_mod.p_under_digeser(ktx["cdf"], garis, ktx["geser_banjir_3p"])
    p_banjir_ft = stress_mod.p_under_digeser(ktx["cdf"], garis, ktx["geser_banjir_ft"])
    p_banjir = stress_mod.p_under_digeser(
        ktx["cdf"], garis, ktx["geser_banjir_terburuk"]
    )
    p_setan = stress_mod.p_under_digeser(ktx["cdf"], garis, ktx["geser_setan"])
    edge = p_final - harga / 100.0
    ev_pct = (p_final * (100.0 / harga) - 1.0) * 100.0
    expected_return = p_final * (100.0 / harga)
    label = _label_ev(ev_pct, cfg)
    volume = _angka(entri.get("volume_usd"))
    # Gate eksekusi v18 (revisi koordinator — cek_eksekusi):
    # likuiditas Gamma >= lantai + spread <= maks + ask nyata.
    # Volume kumulatif BUKAN lagi bagian gate (lihat docstring modul).
    hasil_eksekusi = cek_eksekusi(entri, cfg)
    gate_eksekusi = hasil_eksekusi["lolos"]
    likuiditas_min = hasil_eksekusi["likuiditas_min_usd"]
    volume_info = _cfg_angka_atau_default(
        cfg,
        ("polymarket_ladder", "min_volume_usd"),
        _DEFAULT_MIN_VOLUME_INFO_USD,
    )
    # Info (bukan blokir): volume lolos gate eksekusi tapi di bawah
    # ambang lama $100 — garisnya bisa dibeli, tapi pasarnya tipis.
    info_volume_dibawah_100 = bool(
        gate_eksekusi and volume is not None and volume < volume_info
    )
    if tiket == "insurance":
        lantai = _ambang(cfg, "analis", "harga_min_asuransi_cents")
        p_market_min = _cfg_angka_atau_default(
            cfg,
            ("tickets", "insurance", "min_p_market"),
            _DEFAULT_MIN_P_MARKET_INS,
        )
        ev_min = _cfg_angka_atau_default(
            cfg,
            ("tickets", "insurance", "max_negative_ev_pct"),
            _DEFAULT_MAX_NEG_EV_INS_PCT,
        )
        banjir_3p_min = _cfg_angka_atau_default(
            cfg,
            ("tickets", "insurance", "flood_3p_min"),
            _DEFAULT_FLOOD_3P_MIN,
        )
        banjir_ft_min = _cfg_angka_atau_default(
            cfg,
            ("tickets", "insurance", "flood_ft_min"),
            _DEFAULT_FLOOD_FT_MIN,
        )
        # Gate p_market: bila p_market tidak ada (MODEL_ONLY, tanpa
        # jangkar pasar — hanya bila butuh_anchor_pasar false),
        # gate ini TIDAK dievaluasi (lolos dengan catatan, bukan
        # fail-closed buta): garis tetap boleh lolos bila p_final +
        # banjir + EV lolos. "p_market_gate_dievaluasi" mencatatnya.
        p_market_dievaluasi = p_market is not None
        gate = {
            "peluang": p_final >= ambang,
            "p_market": (p_market >= p_market_min if p_market_dievaluasi else True),
            "lantai_harga": harga >= lantai,
            "banjir_3p": p_banjir_3p >= banjir_3p_min,
            "banjir_ft": p_banjir_ft >= banjir_ft_min,
            "ev": ev_pct >= ev_min,
            "eksekusi": gate_eksekusi,
        }
        banjir_warning = False
    else:
        lantai = _ambang(cfg, "analis", "harga_min_utama_cents")
        ev_min = _cfg_angka_atau_default(
            cfg,
            ("tickets", "main", "max_negative_ev_pct"),
            _DEFAULT_MAX_NEG_EV_MAIN_PCT,
        )
        gate = {
            "peluang": p_final >= ambang,
            "lantai_harga": harga >= lantai,
            "ev": ev_pct >= ev_min,
            "eksekusi": gate_eksekusi,
        }
        p_market_dievaluasi = p_market is not None
        # Banjir Utama WARNING-ONLY: dicatat (tidak memblokir).
        # Ambang peringatannya memakai ambang banjir Asuransi
        # (0,70/0,65) — satu definisi "rapuh banjir" untuk kedua
        # tiket; komposer memakai flag ini untuk peringatan.
        banjir_3p_min = _cfg_angka_atau_default(
            cfg,
            ("tickets", "insurance", "flood_3p_min"),
            _DEFAULT_FLOOD_3P_MIN,
        )
        banjir_ft_min = _cfg_angka_atau_default(
            cfg,
            ("tickets", "insurance", "flood_ft_min"),
            _DEFAULT_FLOOD_FT_MIN,
        )
        banjir_warning = bool(
            p_banjir_3p < banjir_3p_min or p_banjir_ft < banjir_ft_min
        )
    return {
        "line": garis,
        "entri": entri,
        "harga_venue_cents": harga,
        "price_cents": _angka(entri.get("price_cents")),
        "jup_estimated_cents": _angka(entri.get("jup_estimated_cents")),
        "volume_usd": volume,
        "thin": entri.get("thin"),
        "likuiditas_usd": hasil_eksekusi["likuiditas_usd"],
        "bid_cents": hasil_eksekusi["bid_cents"],
        "ask_cents": hasil_eksekusi["ask_cents"],
        "spread_cents": hasil_eksekusi["spread_cents"],
        "eksekusi_alasan": hasil_eksekusi["alasan"],
        "p_model": p_model,
        "p_market": p_market,
        "p_final": p_final,
        "p_banjir_terburuk": p_banjir,
        "p_banjir_3p": p_banjir_3p,
        "p_banjir_ft": p_banjir_ft,
        "p_setan": p_setan,
        "edge": edge,
        "ev_pct": ev_pct,
        "expected_return": expected_return,
        "price_label": label,
        "p_market_gate_dievaluasi": p_market_dievaluasi,
        "info_volume_dibawah_100": info_volume_dibawah_100,
        "banjir_warning": banjir_warning,
        "likuiditas_min_eksekusi_usd": likuiditas_min,
        "gate": gate,
        "lolos_semua": all(gate.values()),
    }


# Urutan diagnosis gate v18: gate yang pertama kali menghabiskan
# himpunan kandidat adalah yang "mengikat" — alasan
# tidak-ada-equilibrium menamai gate itu + detailnya.
_URUTAN_GATE_INS = (
    "peluang",
    "p_market",
    "lantai_harga",
    "banjir_3p",
    "banjir_ft",
    "ev",
    "eksekusi",
)
_URUTAN_GATE_MAIN = ("peluang", "lantai_harga", "ev", "eksekusi")


def _alasan_tidak_ada(
    ktx: dict,
    nilai: list[dict],
    tiket: str,
    ambang: float,
    cfg: dict,
    analysis: dict,
) -> str:
    """Alasan diagnostik bila tidak ada garis yang lolos semua gate (v18).

    Menamai gate yang mengikat (yang pertama menghabiskan kandidat
    dalam urutan diagnosis) + detail yang bisa dicek. Token alasan
    lama dipakai ulang di mana relevan ("tidak_ada_garis_tahan_banjir")
    supaya jejak audit tetap nyambung. Token v17 "edge_kecil" TIDAK
    dipakai lagi (gate edge DIHAPUS v18, diganti EV).
    """
    urutan = _URUTAN_GATE_INS if tiket == "insurance" else _URUTAN_GATE_MAIN
    sisa = list(nilai)
    mengikat = None
    for nama in urutan:
        sisa = [n for n in sisa if n["gate"][nama]]
        if not sisa:
            mengikat = nama
            break
    nama_tiket = "Asuransi" if tiket == "insurance" else "Utama"
    pembuka = (
        f"tidak ada equilibrium {nama_tiket}: tidak ada garis tangga "
        f"yang lolos semua gate ({len(nilai)} garis dinilai)"
    )
    if mengikat is None:
        return pembuka + "."
    detail = ""
    if mengikat in ("banjir_3p", "banjir_ft"):
        kunci_p = "p_banjir_3p" if mengikat == "banjir_3p" else "p_banjir_ft"
        kunci_ambang = "flood_3p_min" if mengikat == "banjir_3p" else "flood_ft_min"
        kunci_geser = (
            "geser_banjir_3p" if mengikat == "banjir_3p" else "geser_banjir_ft"
        )
        nama_skenario = "banjir_3p" if mengikat == "banjir_3p" else "banjir_ft"
        ambang_banjir = _cfg_angka_atau_default(
            cfg,
            ("tickets", "insurance", kunci_ambang),
            (
                _DEFAULT_FLOOD_3P_MIN
                if mengikat == "banjir_3p"
                else _DEFAULT_FLOOD_FT_MIN
            ),
        )
        tertahan = max(nilai, key=lambda n: n[kunci_p])
        detail = (
            f"tidak_ada_garis_tahan_banjir — tidak ada garis tangga yang "
            f"P(Under) >= {ambang_banjir:.0%} di skenario {nama_skenario} "
            f"(geser {ktx[kunci_geser]:.2f} poin); garis terbaik "
            f"U{tertahan['line']:g} hanya "
            f"{tertahan[kunci_p] * 100:.1f}% "
            f"(P banjir 3P {tertahan['p_banjir_3p'] * 100:.1f}%, "
            f"P banjir FT {tertahan['p_banjir_ft'] * 100:.1f}%)"
        )
    elif mengikat == "eksekusi":
        likuiditas_min = likuiditas_min_eksekusi(cfg)
        spread_max = _cfg_angka_atau_default(
            cfg, ("execution", "max_spread_cents"), _DEFAULT_MAX_SPREAD_CENTS
        )
        # Garis yang lolos semua gate LAIN tapi gagal eksekusi.
        lolos_lain = [
            n for n in nilai if all(n["gate"][g] for g in urutan if g != "eksekusi")
        ]
        if lolos_lain:
            # Garis "terbaik" = spread tersempit yang tercatat
            # (paling dekat lolos); tanpa spread -> garis pertama.
            def _kunci_eksekusi(n):
                spread = n.get("spread_cents")
                return spread if spread is not None else 999.0

            terbaik = min(lolos_lain, key=_kunci_eksekusi)
            alasan = terbaik.get("eksekusi_alasan") or "tidak_diketahui"
            if alasan == "likuiditas_di_bawah_minimum":
                liq = terbaik.get("likuiditas_usd")
                teks_alasan = (
                    f"likuiditas ${liq:,.2f} di bawah minimum "
                    f"${likuiditas_min:,.0f}"
                )
            elif alasan == "likuiditas_tidak_tercatat":
                teks_alasan = "likuiditas tidak tercatat"
            elif alasan == "tanpa_kuotasi":
                teks_alasan = "bid/ask tidak tercatat"
            elif alasan == "tanpa_ask_nyata":
                teks_alasan = "ask 99¢ (tidak ada ask nyata)"
            elif alasan == "spread_terlalu_lebar":
                spread = terbaik.get("spread_cents")
                teks_alasan = f"spread {spread:g}¢ di atas maksimum {spread_max:g}¢"
            else:
                teks_alasan = alasan
            detail = (
                f"eksekusi_tidak_lolos — garis terbaik yang lolos semua gate "
                f"lain U{terbaik['line']:g} gagal gate eksekusi "
                f"({teks_alasan}); semua {len(lolos_lain)} "
                f"garis yang lolos gate lain gagal gate eksekusi"
            )
        else:
            detail = (
                f"eksekusi_tidak_lolos — tidak ada garis yang lolos gate "
                f"eksekusi (likuiditas >= ${likuiditas_min:,.0f} + "
                f"spread <= {spread_max:g}¢ + ask nyata)"
            )
    elif mengikat == "ev":
        default_ev = (
            _DEFAULT_MAX_NEG_EV_INS_PCT
            if tiket == "insurance"
            else _DEFAULT_MAX_NEG_EV_MAIN_PCT
        )
        ev_min = _cfg_angka_atau_default(
            cfg, ("tickets", tiket, "max_negative_ev_pct"), default_ev
        )
        lolos_sebelum = [
            n for n in nilai if all(n["gate"][g] for g in urutan[: urutan.index("ev")])
        ]
        terbaik = (
            max(lolos_sebelum, key=lambda n: n["ev_pct"]) if lolos_sebelum else None
        )
        if terbaik is not None:
            detail = (
                f"ev_di_bawah_minimum — garis terbaik yang lolos gate lain "
                f"U{terbaik['line']:g} @{terbaik['harga_venue_cents']:g}¢ "
                f"EV {terbaik['ev_pct']:+.1f}% di bawah minimum "
                f"{ev_min:+.1f}% (p_final "
                f"{terbaik['p_final'] * 100:.1f}% — harga "
                f"{terbaik['harga_venue_cents']:g}¢ terlalu mahal untuk "
                f"peluangnya)"
            )
        else:
            detail = (
                f"ev_di_bawah_minimum — tidak ada garis dengan EV >= {ev_min:+.1f}%"
            )
    elif mengikat == "peluang":
        terbaik = max(nilai, key=lambda n: n["p_final"])
        detail = (
            f"tidak ada garis dengan p_final >= {ambang:.0%} (terbaik "
            f"U{terbaik['line']:g}: p_final "
            f"{terbaik['p_final'] * 100:.1f}%)"
        )
    elif mengikat == "p_market":
        p_market_min = _cfg_angka_atau_default(
            cfg,
            ("tickets", "insurance", "min_p_market"),
            _DEFAULT_MIN_P_MARKET_INS,
        )
        dengan_pasar = [n for n in nilai if n["p_market"] is not None]
        if dengan_pasar:
            terbaik = max(dengan_pasar, key=lambda n: n["p_market"])
            detail = (
                f"tidak ada garis dengan p_market >= {p_market_min:.0%} "
                f"(terbaik U{terbaik['line']:g}: p_market "
                f"{terbaik['p_market'] * 100:.1f}% — pasar tidak cukup "
                f"yakin di garis mana pun)"
            )
        else:
            detail = (
                "p_market tidak tersedia di garis mana pun (tanpa jangkar "
                "pasar) — gate p_market tidak bisa dievaluasi"
            )
    elif mengikat == "lantai_harga":
        kunci = (
            "harga_min_asuransi_cents"
            if tiket == "insurance"
            else "harga_min_utama_cents"
        )
        lantai = _ambang(cfg, "analis", kunci)
        detail = (
            f"tidak ada garis yang lolos peluang dengan harga >= lantai " f"{lantai:g}¢"
        )
    return f"{pembuka}; gate yang mengikat: {mengikat} — {detail}."


def nilai_semua_garis(
    analysis: dict, tiket: str, cfg: dict | None = None, ktx: dict | None = None
) -> list[dict] | None:
    """Nilai SEMUA garis tangga satu laga + satu tiket (gate per garis).

    Mengembalikan daftar dict hasil ``_nilai_garis`` (tanpa kunci
    "entri" — entri tangga mentah tidak perlu keluar modul), atau
    None bila konteks tidak bisa disiapkan (tanpa CDF / tangga /
    jangkar pasar — sama seperti ``cari_equilibrium`` mengembalikan
    dihitung=False). Dipakai pengukuran (mis. menghitung garis yang
    gagal HANYA karena eksekusi) tanpa menduplikasi logika gate.
    Config rusak -> ConfigError. Artefak bukan dict / tiket tidak
    dikenal -> ValueError.
    """
    if not isinstance(analysis, dict):
        raise ValueError("analysis harus dict")
    if tiket not in _TIKET:
        raise ValueError(f"tiket tidak dikenal: {tiket!r}")
    cfg = _muat_cfg(cfg)
    if ktx is None:
        ktx = siapkan_konteks(analysis, tiket, cfg)
    if not ktx.get("ok"):
        return None
    ambang = _ambang(cfg, "tickets", tiket, "min_leg_prob")
    nilai: list[dict] = []
    for entri in ktx["tangga"]:
        dinilai = _nilai_garis(ktx, entri, tiket, ambang, cfg)
        if dinilai is not None:
            nilai.append({k: v for k, v in dinilai.items() if k != "entri"})
    return nilai


def cari_equilibrium(
    analysis: dict, tiket: str, cfg: dict | None = None, ktx: dict | None = None
) -> dict:
    """Cari titik equilibrium satu laga + satu tiket (v18).

    Mengembalikan dict hasil (lihat docstring modul untuk definisi):
    {"dihitung", "ada", "mode", "garis", "harga_venue_cents",
    "p_model", "p_market", "p_final", "p_banjir_terburuk",
    "p_banjir_3p", "p_banjir_ft", "p_setan", "edge", "ev_pct",
    "expected_return", "thin", "volume_usd", "geser_pasar", "anchor",
    "n_kandidat_lolos", "n_garis_dinilai", "diagnosis_gate",
    "band_harga", "dalam_band", "fallback_band",
    "p_market_gate_dievaluasi", "info_volume_dibawah_100",
    "banjir_warning", "likuiditas_min_eksekusi_usd",
    "alasan_tidak_dihitung", "alasan_tidak_ada"}.
    ``mode`` adalah mode pemilihan yang dipakai ("max_er" /
    "safety_first" dari config). Pemilihan v18: di antara garis
    yang lolos SEMUA gate, pilih DALAM band harga tiket itu dulu
    (Asuransi 80-89¢, Utama 76-84¢); bila tidak ada garis lolos
    dalam band, fallback ke semua garis lolos ("fallback_band"
    True). Max-ER memakai tie-break toleransi ER (selisih ER <
    0,015 -> garis yang lebih aman). ``ktx`` opsional: konteks
    dari ``siapkan_konteks`` (dipakai pemanggil yang sudah
    menghitungnya — mis. skip_awal — supaya CDF + tangga tidak
    dihitung ulang). Config rusak -> ConfigError. Artefak bukan
    dict -> ValueError.
    """
    if not isinstance(analysis, dict):
        raise ValueError("analysis harus dict")
    if tiket not in _TIKET:
        raise ValueError(f"tiket tidak dikenal: {tiket!r}")
    cfg = _muat_cfg(cfg)
    ambang = _ambang(cfg, "tickets", tiket, "min_leg_prob")
    mode = _mode_equilibrium(cfg, tiket)
    hasil = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "match_id": analysis.get("match_id"),
        "ticket": tiket,
        "mode": mode,
        "dihitung": False,
        "alasan_tidak_dihitung": None,
        "ada": False,
        "alasan_tidak_ada": None,
        "garis": None,
        "harga_venue_cents": None,
        "price_cents": None,
        "jup_estimated_cents": None,
        "thin": None,
        "volume_usd": None,
        "p_model": None,
        "p_market": None,
        "p_final": None,
        "p_banjir_terburuk": None,
        "banjir_terburuk": None,
        "p_banjir_3p": None,
        "p_banjir_ft": None,
        "p_setan": None,
        "edge": None,
        "ev_pct": None,
        "expected_return": None,
        "price_label": None,
        "geser_pasar": None,
        "anchor": None,
        "n_kandidat_lolos": 0,
        "n_garis_dinilai": 0,
        "diagnosis_gate": {},
        "band_harga": None,
        "dalam_band": None,
        "fallback_band": False,
        "p_market_gate_dievaluasi": None,
        "info_volume_dibawah_100": None,
        "banjir_warning": None,
        "likuiditas_min_eksekusi_usd": None,
    }
    if ktx is None:
        ktx = siapkan_konteks(analysis, tiket, cfg)
    if not ktx.get("ok"):
        hasil["alasan_tidak_dihitung"] = ktx.get("alasan") or "konteks tidak siap"
        return hasil
    hasil["banjir_terburuk"] = ktx["banjir_terburuk"]
    hasil["geser_pasar"] = round(ktx["delta"], 4) if ktx["delta"] is not None else None
    hasil["anchor"] = ktx["anchor"]
    nilai = nilai_semua_garis(analysis, tiket, cfg, ktx=ktx) or []
    hasil["dihitung"] = True
    hasil["n_garis_dinilai"] = len(nilai)
    urutan = _URUTAN_GATE_INS if tiket == "insurance" else _URUTAN_GATE_MAIN
    hasil["diagnosis_gate"] = {
        nama: sum(1 for n in nilai if n["gate"][nama]) for nama in urutan
    }
    lolos = [n for n in nilai if n["lolos_semua"]]
    hasil["n_kandidat_lolos"] = len(lolos)
    band_bawah, band_atas = _cfg_band(cfg, tiket)
    hasil["band_harga"] = [band_bawah, band_atas]
    hasil["likuiditas_min_eksekusi_usd"] = likuiditas_min_eksekusi(cfg)
    if not lolos:
        hasil["alasan_tidak_ada"] = _alasan_tidak_ada(
            ktx, nilai, tiket, ambang, cfg, analysis
        )
        return hasil
    # BAND HARGA (v18): pilih di antara garis lolos DALAM band dulu;
    # bila tidak ada garis lolos dalam band, fallback ke semua garis
    # lolos (dicatat — band adalah preferensi pemilihan, bukan gate:
    # garis di luar band tetap boleh dipilih bila tidak ada pilihan
    # lain, supaya satu band yang kosong tidak mematikan tiket).
    dalam_band = [n for n in lolos if band_bawah <= n["harga_venue_cents"] <= band_atas]
    fallback_band = not dalam_band
    kolam = lolos if fallback_band else dalam_band
    hasil["fallback_band"] = fallback_band
    if mode == "safety_first":
        # p_final tertinggi (paling aman); seri (< 1e-9) -> ER lebih
        # tinggi -> garis lebih kecil.
        p_maks = max(n["p_final"] for n in kolam)
        seri = [n for n in kolam if p_maks - n["p_final"] < _EPS_ER]
        er_maks = max(n["expected_return"] for n in seri)
        seri = [n for n in seri if er_maks - n["expected_return"] < _EPS_ER]
        pilihan = min(seri, key=lambda n: n["line"])
    else:
        # Max-ER dengan TIE-BREAK v18: bila selisih ER < toleransi
        # config (0,015), pilih garis yang LEBIH AMAN (p_final lebih
        # tinggi) — ER yang hampir sama tidak sebanding dengan
        # risiko kalah yang lebih besar. Seri p_final (< 1e-9) ->
        # garis lebih kecil.
        toleransi = _cfg_angka_atau_default(
            cfg,
            ("tickets", tiket, "tiebreak_er_tolerance"),
            _DEFAULT_TIEBREAK_ER,
        )
        if toleransi < 0:
            raise config_mod.ConfigError(
                "playstyle.yaml tickets."
                f"{tiket}.tiebreak_er_tolerance harus >= 0: {toleransi}"
            )
        er_maks = max(n["expected_return"] for n in kolam)
        seri = [n for n in kolam if er_maks - n["expected_return"] < toleransi]
        p_maks = max(n["p_final"] for n in seri)
        seri = [n for n in seri if p_maks - n["p_final"] < _EPS_ER]
        pilihan = min(seri, key=lambda n: n["line"])
    hasil.update(
        {
            "ada": True,
            "garis": pilihan["line"],
            "harga_venue_cents": pilihan["harga_venue_cents"],
            "price_cents": pilihan["price_cents"],
            "jup_estimated_cents": pilihan["jup_estimated_cents"],
            "thin": pilihan["thin"],
            "volume_usd": pilihan["volume_usd"],
            "p_model": round(pilihan["p_model"], 6),
            "p_market": (
                round(pilihan["p_market"], 6)
                if pilihan["p_market"] is not None
                else None
            ),
            "p_final": round(pilihan["p_final"], 6),
            "p_banjir_terburuk": round(pilihan["p_banjir_terburuk"], 6),
            "p_banjir_3p": round(pilihan["p_banjir_3p"], 6),
            "p_banjir_ft": round(pilihan["p_banjir_ft"], 6),
            "p_setan": round(pilihan["p_setan"], 6),
            "edge": round(pilihan["edge"], 6),
            "ev_pct": round(pilihan["ev_pct"], 4),
            "expected_return": round(pilihan["expected_return"], 6),
            "price_label": pilihan["price_label"],
            "dalam_band": bool(band_bawah <= pilihan["harga_venue_cents"] <= band_atas),
            "p_market_gate_dievaluasi": pilihan["p_market_gate_dievaluasi"],
            "info_volume_dibawah_100": pilihan["info_volume_dibawah_100"],
            "banjir_warning": pilihan["banjir_warning"],
        }
    )
    return hasil


def cari_garis_acuan(
    analysis: dict, cfg: dict | None = None, ktx: dict | None = None
) -> dict:
    """Garis acuan Asuransi satu laga (untuk pola Denver, skip_awal).

    Garis tangga Under TERENDAH dengan P normal >= target Asuransi
    (0,74) — garis wajar pertama laga itu: di bawahnya, model sendiri
    belum cukup yakin; di sinilah kerapuhan laga dibaca. Pada tangga
    monoton naik (harga naik dengan garis, seperti tangga nyata),
    garis terendah ini sekaligus yang termurah. Di samping garisnya,
    kembalikan flag_setan, edge implied, dan info garis tahan-banjir
    (ada/tidak, thin/tidak) — bahan mentah keempat syarat pola
    Denver. Tanpa konteks (tanpa CDF/tangga) ->
    {"dihitung": False, "alasan": ...}. Tanpa jangkar pasar, p_final/
    edge None (syarat edge tidak bisa dinilai — pemanggil yang
    memutuskan).
    """
    if not isinstance(analysis, dict):
        raise ValueError("analysis harus dict")
    cfg = _muat_cfg(cfg)
    ambang = _ambang(cfg, "tickets", "insurance", "min_leg_prob")
    hasil = {
        "dihitung": False,
        "alasan": None,
        "garis": None,
        "harga_venue_cents": None,
        "thin": None,
        "volume_usd": None,
        "p_normal": None,
        "p_setan": None,
        "flag_setan": None,
        "p_final": None,
        "edge": None,
        "garis_tahan_banjir": None,
        "n_tahan_banjir": 0,
        "n_tahan_banjir_nonthin": 0,
        "ada_tahan_banjir_nonthin": False,
    }
    if ktx is None:
        ktx = siapkan_konteks(analysis, "insurance", cfg)
    if not ktx.get("ok"):
        hasil["alasan"] = ktx.get("alasan") or "konteks tidak siap"
        return hasil
    acuan = None
    for entri in ktx["tangga"]:
        garis = float(entri["line"])
        if stress_mod.p_under_digeser(ktx["cdf"], garis, 0.0) >= ambang:
            acuan = entri
            break
    tahan = [
        entri
        for entri in ktx["tangga"]
        if stress_mod.p_under_digeser(
            ktx["cdf"], float(entri["line"]), ktx["geser_banjir_terburuk"]
        )
        >= ambang
    ]
    tahan_nonthin = [e for e in tahan if e.get("thin") is not True]
    hasil["n_tahan_banjir"] = len(tahan)
    hasil["n_tahan_banjir_nonthin"] = len(tahan_nonthin)
    hasil["ada_tahan_banjir_nonthin"] = bool(tahan_nonthin)
    if tahan:
        pertama = tahan[0]
        hasil["garis_tahan_banjir"] = {
            "line": float(pertama["line"]),
            "harga_venue_cents": _harga_venue(pertama),
            "thin": pertama.get("thin"),
        }
    if acuan is None:
        hasil["alasan"] = (
            f"tidak ada garis tangga dengan P normal >= {ambang:.0%} "
            "(model tidak cukup yakin di garis mana pun)"
        )
        return hasil
    garis = float(acuan["line"])
    p_normal = stress_mod.p_under_digeser(ktx["cdf"], garis, 0.0)
    p_setan = stress_mod.p_under_digeser(ktx["cdf"], garis, ktx["geser_setan"])
    _p_model, _p_market, p_final = peluang_pada_garis(ktx, garis)
    harga = _harga_venue(acuan)
    hasil.update(
        {
            "dihitung": True,
            "garis": garis,
            "harga_venue_cents": harga,
            "thin": acuan.get("thin"),
            "volume_usd": _angka(acuan.get("volume_usd")),
            "p_normal": round(p_normal, 6),
            "p_setan": round(p_setan, 6),
            "flag_setan": bool(p_normal >= ambang and p_setan < ambang),
            "p_final": (round(p_final, 6) if ktx["delta"] is not None else None),
            "edge": (
                round(p_final - harga / 100.0, 6)
                if ktx["delta"] is not None and harga is not None
                else None
            ),
        }
    )
    return hasil


def rakit_kaki_equilibrium(
    kaki_lama: dict,
    hasil_eq: dict,
    analysis: dict,
    cfg: dict | None = None,
) -> dict | None:
    """Bangun ulang kaki artefak di garis equilibrium (atau None).

    None bila: hasil equilibrium tidak ada (``ada`` False), atau
    garis equilibrium SAMA dengan garis kaki lama (tidak ada yang
    diubah — kaki artefak dipakai apa adanya, termasuk p_final dan
    label aslinya, supaya tidak ada selisih pembulatan).
    Kaki baru: p_model/p_market/p_final/EV/label dihitung di garis
    baru (MEMPERBAIKI pemakaian p_final garis lama); leg_id TIDAK
    berubah (recheck matching — pola yang sama dengan climb banjir);
    cushion_points/reason dipertahankan (per laga, bukan per garis);
    cushion_vs_median/market dihitung ulang dari median/garis market;
    climb dicatat alasan "equilibrium" (dirangkai dengan climb lama
    bila ada, seperti climb banjir); meets=True, reason=None.
    """
    if not hasil_eq.get("ada"):
        return None
    garis_baru = _angka(hasil_eq.get("garis"))
    if garis_baru is None:
        return None
    garis_lama = _angka(kaki_lama.get("line"))
    if garis_lama is not None and abs(garis_baru - garis_lama) < 1e-9:
        return None
    cfg = _muat_cfg(cfg)
    ktx = siapkan_konteks(
        analysis, kaki_lama.get("ticket") or hasil_eq.get("ticket"), cfg
    )
    median = ktx.get("median")
    garis_market = ktx.get("garis_market")
    tangga = ktx.get("tangga") or []
    urut = [float(entri["line"]) for entri in tangga]

    def _indeks(garis_cari: float) -> int | None:
        for i, garis_tangga in enumerate(urut):
            if abs(garis_tangga - garis_cari) < 1e-9:
                return i
        return None

    rungs_baru = None
    if garis_lama is not None:
        indeks_dari = _indeks(garis_lama)
        indeks_ke = _indeks(garis_baru)
        if indeks_dari is not None and indeks_ke is not None:
            rungs_baru = abs(indeks_ke - indeks_dari)
    climb_lama = (
        kaki_lama.get("climb") if isinstance(kaki_lama.get("climb"), dict) else None
    )
    if climb_lama is not None:
        dari_awal = _angka(climb_lama.get("from_line"))
        if dari_awal is None:
            dari_awal = garis_lama
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
            f"{alasan_lama}+equilibrium"
            if isinstance(alasan_lama, str) and alasan_lama
            else "equilibrium"
        )
    else:
        dari_awal = garis_lama
        rungs = rungs_baru
        alasan = "equilibrium"
    baru = dict(kaki_lama)
    anchor = hasil_eq.get("anchor") or {}
    baru.update(
        {
            "line": garis_baru,
            "p_model": hasil_eq.get("p_model"),
            "p_market": hasil_eq.get("p_market"),
            "comparison_source": anchor.get("comparison_source")
            or kaki_lama.get("comparison_source"),
            "p_final": hasil_eq.get("p_final"),
            "price_cents": hasil_eq.get("price_cents"),
            "jup_estimated_cents": hasil_eq.get("jup_estimated_cents"),
            "ev_pct": hasil_eq.get("ev_pct"),
            "price_label": hasil_eq.get("price_label"),
            "cushion_vs_median_points": (
                round(garis_baru - median, 4) if median is not None else None
            ),
            "cushion_vs_market_points": (
                round(garis_baru - garis_market, 4)
                if garis_market is not None
                else None
            ),
            "volume_usd": hasil_eq.get("volume_usd"),
            "thin": hasil_eq.get("thin"),
            "climb": {
                "from_line": dari_awal,
                "to_line": garis_baru,
                "rungs": rungs,
                "reason": alasan,
            },
            "meets": True,
            "reason": None,
        }
    )
    return baru
