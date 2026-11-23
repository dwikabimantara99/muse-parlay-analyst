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

GATE PER GARIS (ambang dari config yang SUDAH ADA — tidak diduplikasi):
- Asuransi: p_final >= tickets.insurance.min_leg_prob (0,74);
  P banjir terburuk >= 0,74 (gate banjir R1, skenario dari
  tickets.insurance.stress_gate_scenario); edge (p_final - harga
  venue) >= tickets.insurance.min_edge_pct (3,5%); tidak thin;
  harga venue >= analis.harga_min_asuransi_cents (75¢); label
  bukan MAHAL (aturan optimizer).
- Utama: p_final >= tickets.main.min_leg_prob (0,65); harga venue
  >= analis.harga_min_utama_cents (75¢). Thin BOLEH (sesuai aturan
  komposer: thin Utama hanya flag + peringatan); banjir/edge TIDAK
  di-gate untuk Utama (sesuai aturan yang ada).

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
    "geser_setan", "median", "garis_market"}. "ok" False (bukan raise)
    bila data artefak tidak lengkap (tanpa CDF / tanpa tangga / tanpa
    jangkar pasar) — itu keadaan operasional yang sah, bukan bug.
    Config rusak -> ConfigError (fail-closed, seperti stress.py).
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
    """Nilai satu garis tangga: peluang + harga + hasil tiap gate.

    None bila garis tidak punya harga venue yang valid (tidak bisa
    dibeli — tidak dinilai sama sekali). "lolos_semua" True bila
    semua gate tiket itu lolos.
    """
    garis = float(entri["line"])
    harga = _harga_venue(entri)
    if harga is None or not 0.0 < harga < 100.0:
        return None
    p_model, p_market, p_final = peluang_pada_garis(ktx, garis)
    p_banjir = stress_mod.p_under_digeser(
        ktx["cdf"], garis, ktx["geser_banjir_terburuk"]
    )
    p_setan = stress_mod.p_under_digeser(ktx["cdf"], garis, ktx["geser_setan"])
    edge = p_final - harga / 100.0
    ev_pct = (p_final * (100.0 / harga) - 1.0) * 100.0
    expected_return = p_final * (100.0 / harga)
    label = _label_ev(ev_pct, cfg)
    thin = entri.get("thin") is True
    if tiket == "insurance":
        lantai = _ambang(cfg, "analis", "harga_min_asuransi_cents")
        edge_min = _ambang(cfg, "tickets", "insurance", "min_edge_pct") / 100.0
        gate = {
            "peluang": p_final >= ambang,
            "lantai_harga": harga >= lantai,
            "banjir": p_banjir >= ambang,
            "volume": not thin,
            "edge": edge >= edge_min,
            "label": label != "MAHAL",
        }
    else:
        lantai = _ambang(cfg, "analis", "harga_min_utama_cents")
        gate = {
            "peluang": p_final >= ambang,
            "lantai_harga": harga >= lantai,
        }
    return {
        "line": garis,
        "entri": entri,
        "harga_venue_cents": harga,
        "price_cents": _angka(entri.get("price_cents")),
        "jup_estimated_cents": _angka(entri.get("jup_estimated_cents")),
        "volume_usd": _angka(entri.get("volume_usd")),
        "thin": entri.get("thin"),
        "p_model": p_model,
        "p_market": p_market,
        "p_final": p_final,
        "p_banjir_terburuk": p_banjir,
        "p_setan": p_setan,
        "edge": edge,
        "ev_pct": ev_pct,
        "expected_return": expected_return,
        "price_label": label,
        "gate": gate,
        "lolos_semua": all(gate.values()),
    }


# Urutan diagnosis gate (Asuransi): gate yang pertama kali
# menghabiskan himpunan kandidat adalah yang "mengikat" — alasan
# tidak-ada-equilibrium menamai gate itu + detailnya.
_URUTAN_GATE_INS = ("peluang", "lantai_harga", "banjir", "volume", "edge", "label")
_URUTAN_GATE_MAIN = ("peluang", "lantai_harga")


def _alasan_tidak_ada(
    ktx: dict,
    nilai: list[dict],
    tiket: str,
    ambang: float,
    cfg: dict,
    analysis: dict,
) -> str:
    """Alasan diagnostik bila tidak ada garis yang lolos semua gate.

    Menamai gate yang mengikat (yang pertama menghabiskan kandidat
    dalam urutan diagnosis) + detail yang bisa dicek. Token alasan
    lama dipakai ulang di mana relevan ("tidak_ada_garis_tahan_banjir",
    "volume tipis", "edge_kecil") supaya jejak audit tetap nyambung.
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
    if mengikat == "banjir":
        tertahan = max(nilai, key=lambda n: n["p_banjir_terburuk"])
        detail = (
            f"tidak_ada_garis_tahan_banjir — tidak ada garis tangga yang "
            f"P(Under) >= {ambang:.0%} di skenario "
            f"{ktx['banjir_terburuk']} (geser "
            f"{ktx['geser_banjir_terburuk']:.2f} poin); garis terbaik "
            f"U{tertahan['line']:g} hanya "
            f"{tertahan['p_banjir_terburuk'] * 100:.1f}%"
        )
    elif mengikat == "volume":
        lolos_banjir = [n for n in nilai if n["gate"]["banjir"]]
        tahan = min(lolos_banjir, key=lambda n: n["line"]) if lolos_banjir else None
        kaki_artifak = None
        for leg in analysis.get("legs") or []:
            if isinstance(leg, dict) and leg.get("ticket") == tiket:
                kaki_artifak = leg
                break
        teks_awal = ""
        if kaki_artifak is not None and _angka(kaki_artifak.get("line")) is not None:
            p_awal = stress_mod.p_under_digeser(
                ktx["cdf"],
                float(kaki_artifak["line"]),
                ktx["geser_banjir_terburuk"],
            )
            teks_awal = (
                f"; P(Under) di skenario {ktx['banjir_terburuk']} "
                f"{p_awal * 100:.1f}% < {ambang:.0%} di garis awal "
                f"U{float(kaki_artifak['line']):g}"
            )
        if tahan is not None:
            detail = (
                f"garis tahan-banjir Under {tahan['line']:g} volume tipis "
                f"— tidak dipakai (aturan thin Asuransi); semua "
                f"{len(lolos_banjir)} garis yang tahan banjir tipis"
                f"{teks_awal}"
            )
        else:
            detail = "semua garis yang tahan banjir volume tipis"
    elif mengikat == "edge":
        lolos_volume = [
            n
            for n in nilai
            if n["gate"]["peluang"]
            and n["gate"]["lantai_harga"]
            and n["gate"]["banjir"]
            and n["gate"]["volume"]
        ]
        terbaik = max(lolos_volume, key=lambda n: n["edge"]) if lolos_volume else None
        edge_min = _ambang(cfg, "tickets", "insurance", "min_edge_pct")
        if terbaik is not None:
            detail = (
                f"edge_kecil — garis terbaik yang lolos banjir + volume "
                f"U{terbaik['line']:g} @{terbaik['harga_venue_cents']:g}¢ "
                f"edge {terbaik['edge'] * 100:+.1f}% di bawah minimum "
                f"{edge_min:.1f}% (p_final "
                f"{terbaik['p_final'] * 100:.1f}% − harga "
                f"{terbaik['harga_venue_cents']:g}¢)"
            )
        else:
            detail = f"edge_kecil — tidak ada garis dengan edge >= {edge_min:.1f}%"
    elif mengikat == "peluang":
        terbaik = max(nilai, key=lambda n: n["p_final"])
        detail = (
            f"tidak ada garis dengan p_final >= {ambang:.0%} (terbaik "
            f"U{terbaik['line']:g}: p_final "
            f"{terbaik['p_final'] * 100:.1f}%)"
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
    elif mengikat == "label":
        detail = (
            "semua garis yang lolos gate lain berlabel MAHAL (EV < -2%) "
            "— MAHAL tidak boleh masuk Asuransi"
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
    gagal HANYA karena volume) tanpa menduplikasi logika gate.
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
    """Cari titik equilibrium satu laga + satu tiket.

    Mengembalikan dict hasil (lihat docstring modul untuk definisi):
    {"dihitung", "ada", "mode", "garis", "harga_venue_cents",
    "p_model", "p_market", "p_final", "p_banjir_terburuk", "p_setan",
    "edge", "ev_pct", "expected_return", "thin", "volume_usd",
    "geser_pasar", "anchor", "n_kandidat_lolos", "n_garis_dinilai",
    "diagnosis_gate", "alasan_tidak_dihitung", "alasan_tidak_ada"}.
    ``mode`` adalah mode pemilihan yang dipakai ("max_er" /
    "safety_first" dari config). ``ktx`` opsional: konteks dari
    ``siapkan_konteks`` (dipakai pemanggil yang sudah menghitungnya
    — mis. skip_awal — supaya CDF + tangga tidak dihitung ulang).
    Config rusak -> ConfigError. Artefak bukan dict -> ValueError.
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
    if not lolos:
        hasil["alasan_tidak_ada"] = _alasan_tidak_ada(
            ktx, nilai, tiket, ambang, cfg, analysis
        )
        return hasil
    if mode == "safety_first":
        # p_final tertinggi (paling aman); seri (< 1e-9) -> ER lebih
        # tinggi -> garis lebih kecil.
        p_maks = max(n["p_final"] for n in lolos)
        seri = [n for n in lolos if p_maks - n["p_final"] < _EPS_ER]
        er_maks = max(n["expected_return"] for n in seri)
        seri = [n for n in seri if er_maks - n["expected_return"] < _EPS_ER]
        pilihan = min(seri, key=lambda n: n["line"])
    else:
        # Max-ER; seri (< 1e-9) -> p_final lebih besar -> garis lebih kecil.
        er_maks = max(n["expected_return"] for n in lolos)
        seri = [n for n in lolos if er_maks - n["expected_return"] < _EPS_ER]
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
            "p_setan": round(pilihan["p_setan"], 6),
            "edge": round(pilihan["edge"], 6),
            "ev_pct": round(pilihan["ev_pct"], 4),
            "expected_return": round(pilihan["expected_return"], 6),
            "price_label": pilihan["price_label"],
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
