"""Skenario panas (stress) NBA: banjir 3 poin, banjir FT, konservatif.

Latar: tiket nyata 23 Nov 2026 — kaki DEN@CHI (Asuransi U252,5 @82¢,
Utama U250,5 @79¢) jebol karena banjir 3 poin (halftime total 142,
tripoin 21-41 = 51%, proyeksi live 284), padahal median simulasi
pra-laga 233. Simulasi normal tidak punya skenario ekor seperti itu.
Modul ini menjawab, SEBELUM pasang, per kaki Under: "kalau panas,
garis ini tembus nggak? garis berapa yang tahan banjir, dan berapa
harganya?"

CARA KERJA (pergeseran distribusi, BUKAN simulasi ulang): peluang
Under di tiap skenario dihitung dari CDF total yang SUDAH tersimpan di
artefak (``simulation.markets``: ``total_under_<garis>`` di semua garis
tangga) dengan menggesernya: P_skenario(Under L) = CDF_normal(L - geser).
Sigma TIDAK berubah — banjir hanya menggeser lokasi distribusi, bukan
menyebarkannya. Di antara dua garis CDF yang tersimpan dipakai
interpolasi linear; di luar jangkauan, nilai dijepit ke ujung CDF
(tidak ada ekstrapolasi). Pilihan desain ini sengaja: murah (tanpa
simulasi 100.000x ulang per skenario), deterministik, dan bisa diuji
dengan fixture — dengan mengorbankan satu hal: banjir di dunia nyata
mungkin JUGA melebarkan sebaran (varians naik saat tembakan panas),
yang di sini TIDAK dimodelkan. Lihat "KETERBATASAN" di bawah.

SKENARIO (geser dalam poin, ditambahkan ke total):
- "normal": geser 0 (CDF apa adanya).
- "banjir_3p": geser ``stress.banjir_3p_points`` dari config.
- "banjir_ft": geser ``stress.banjir_ft_points`` dari config.
- "konservatif": distribusi dipusatkan ke garis market — geser =
  ``market.main_total_line`` - median sim (``score_distribution.total.
  median``), sigma sama. Bila garis market atau median tidak ada di
  artefak, skenario ini tidak terdefinisi (dicatat, bukan ditebak).

DASAR DATA PARAMETER BANJIR (bukan tebakan — diturunkan dari game log
stats.nba.com, musim 2026-27, n=247 laga, 20 Okt–22 Nov 2026,
leaguegamefinder; 0 kredit Odds API):
- 3PM gabungan/laga: rata-rata 26,62, p90 33,00 (lebih 6,38 tembakan).
  Kemiringan regresi OLS total poin terhadap 3PM gabungan: 2,12 poin
  per tembakan masuk (bukan 3,0 — tembakan tiga tambahan sebagian
  menggantikan tembakan dua angka). Geser = 6,38 x 2,12 = 13,54 poin.
- FTM gabungan/laga: rata-rata 37,79, p90 52,00 (lebih 14,22).
  Kemiringan OLS total terhadap FTM gabungan: 1,23 poin per lemparan
  masuk. Geser = 14,22 x 1,23 = 17,54 poin.
- Persentil p90 ("1 dari 10 laga") adalah PILIHAN DESAIN — menunggu
  keberatan reviewer. Jangkar insiden DEN@CHI: 21 tripoin masuk di
  halftime (laju 42/laga) berada DI ATAS maks musim (40; z +2,89,
  di atas p99) — banjir p90 TIDAK mencakup insiden separah itu.
  Garis tahan-banjir p90 menjawab "tahan banjir 1-dari-10", BUKAN
  "tahan banjir separah DEN@CHI". Bandingkan selalu dengan proyeksi
  insiden bila ada.
- KALIBRASI ULANG: tarik lagi game log musim berjalan (leaguegamefinder,
  keyless), hitung ulang rata-rata + p90 + kemiringan OLS, ganti kedua
  kunci config, dan minta persetujuan user (seperti D12 untuk parameter
  fit). Kemiringan OLS bersifat asosiatif, bukan kausal — ia ikut
  menangkap efek pace/OT di laga-laga tersebut.

GARIS TAHAN-BANJIR per kaki: garis Under tangga TERKECIL yang
P(Under) >= target DI SKENARIO BANJIR TERBURUK (geser terbesar dari
banjir_3p/banjir_ft). Target dibaca dari config: Asuransi =
``tickets.insurance.min_leg_prob`` (0,74), Utama =
``tickets.main.min_leg_prob`` (0,65). Bila tidak ada garis tangga yang
lolos, hasilnya None + alasan — kaki dinyatakan TIDAK tahan banjir,
bukan dipaksakan. Garis tipis (thin) TIDAK dikeluarkan dari pencarian
(pertanyaannya adalah soal garisnya, bukan soal eksekusi), TAPI flag
thin + volume selalu dilaporkan bersama harganya.

KETERBATASAN (dicatat jujur, bukan disembunyikan):
- Banjir hanya menggeser rata-rata; varians dianggap tetap.
- Geser banjir adalah angka LIGA (bukan per matchup) — dipakai sebagai
  kelebihan di atas ekspektasi matchup itu sendiri. Alasan: simpangan
  baku 3PM per tim nyaris sama di semua tim (binomial dengan ~35
  percobaan; DEN 10,5/laga vs rata-rata liga 13,3/laga mengubah
  simpangan baku kurang dari 2%), jadi kelebihan p90 liga berlaku
  untuk semua matchup sampai orde pertama. Per-matchup butuh rata-rata
  3PM/FTM per tim di artefak inputs — belum ada.
- Kemiringan OLS asosiatif (lihat "DASAR DATA" di atas).
- CDF tersimpan dibulatkan ke 6 desimal oleh sim; interpolasi di
  antara garis tangga 2 poin menambah galat kecil (di bawah ~0,5 poin
  peluang untuk garis di tengah interval).

Modul ini MURNI HITUNG: tanpa fetch, tanpa simulasi ulang, tanpa
Odds API. Satu-satunya I/O adalah baca config bila argumen cfg None
(pola yang sama dengan engine/anomaly.py).
"""

from __future__ import annotations

import math

import config as config_mod

FORMAT = "nba_stress"
FORMAT_VERSION = 1

# Nama skenario banjir (yang dipakai untuk "banjir terburuk").
SKENARIO_BANJIR = ("banjir_3p", "banjir_ft")

# Tiket yang dikenal + kunci targetnya di config (target dibaca dari
# config, bukan ditulis di sini — aturan kerja 4).
_TARGET_TIKET = {
    "insurance": ("tickets", "insurance", "min_leg_prob"),
    "main": ("tickets", "main", "min_leg_prob"),
}

# Penjelasan dasar parameter (ditulis ke output agar artefak stress
# bisa diaudit sendiri tanpa membuka file ini).
_DASAR_BANJIR_3P = (
    "p90-rerata 3PM gabungan/laga (33,00-26,62) x kemiringan total/3PM "
    "(2,12) = 13,54 poin; game log stats.nba.com 2026-27, n=247 laga, "
    "20 Okt-22 Nov 2026"
)
_DASAR_BANJIR_FT = (
    "p90-rerata FTM gabungan/laga (52,00-37,79) x kemiringan total/FTM "
    "(1,23) = 17,54 poin; game log stats.nba.com 2026-27, n=247 laga, "
    "20 Okt-22 Nov 2026"
)


def _angka(nilai: object) -> float | None:
    """Ubah nilai jadi float; None bila bukan angka (bool bukan angka)."""
    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        return None
    if not math.isfinite(float(nilai)):
        return None
    return float(nilai)


def cdf_total_dari_markets(markets: dict) -> list[tuple[float, float]]:
    """Ekstrak CDF total (garis, P(Under)) dari dict markets simulasi.

    Memakai semua kunci ``total_under_<garis>``; hasilnya terurut naik
    berdasarkan garis. Raise ValueError bila markets bukan dict, tidak
    ada kunci total_under, atau ada peluang di luar 0-1.
    """
    if not isinstance(markets, dict):
        raise ValueError("markets harus dict")
    cdf: list[tuple[float, float]] = []
    for kunci, nilai in markets.items():
        if not isinstance(kunci, str) or not kunci.startswith("total_under_"):
            continue
        try:
            garis = float(kunci[len("total_under_") :])
        except ValueError:
            garis = None
        peluang = _angka(nilai)
        if garis is None or not math.isfinite(garis):
            raise ValueError(f"garis CDF tidak valid di kunci markets: {kunci!r}")
        if peluang is None or not 0.0 <= peluang <= 1.0:
            raise ValueError(
                f"peluang CDF tidak valid di kunci markets {kunci!r}: {nilai!r}"
            )
        cdf.append((garis, peluang))
    if not cdf:
        raise ValueError(
            "markets tidak membawa kunci total_under_* — CDF total "
            "tidak bisa dibangun"
        )
    cdf.sort()
    return cdf


def p_under_digeser(
    cdf: list[tuple[float, float]], garis: float, geser: float
) -> float:
    """P(Under garis) bila distribusi total digeser naik sebesar geser.

    = CDF(garis - geser), interpolasi linear di antara dua titik CDF
    yang tersimpan; di luar jangkauan dijepit ke ujung CDF (tidak ada
    ekstrapolasi). cdf: daftar (garis, peluang) terurut naik.
    """
    if not cdf:
        raise ValueError("cdf tidak boleh kosong")
    if _angka(garis) is None or _angka(geser) is None:
        raise ValueError(f"garis/geser harus angka: {garis!r}, {geser!r}")
    x = float(garis) - float(geser)
    if x <= cdf[0][0]:
        return cdf[0][1]
    if x >= cdf[-1][0]:
        return cdf[-1][1]
    for (g0, p0), (g1, p1) in zip(cdf, cdf[1:], strict=True):
        if g0 <= x <= g1:
            if g1 == g0:
                return p0
            return p0 + (p1 - p0) * (x - g0) / (g1 - g0)
    # Tidak tercapai: x sudah dipastikan berada di dalam jangkauan.
    raise ValueError(f"interpolasi CDF gagal untuk x={x}")


def tangga_under(market: dict | None) -> list[dict]:
    """Daftar entri tangga sisi Under, terurut naik berdasarkan garis.

    Entri tanpa garis numerik dibuang; harga boleh None (dilaporkan apa
    adanya). market None / tanpa daftar totals -> daftar kosong.
    """
    if not isinstance(market, dict):
        return []
    totals = market.get("totals")
    if not isinstance(totals, list):
        return []
    hasil: list[dict] = []
    for entri in totals:
        if not isinstance(entri, dict) or entri.get("side") != "under":
            continue
        garis = _angka(entri.get("line"))
        if garis is None:
            continue
        hasil.append(entri)
    hasil.sort(key=lambda e: float(e["line"]))
    return hasil


def garis_tahan_banjir(
    tangga: list[dict],
    cdf: list[tuple[float, float]],
    geser_banjir: float,
    target: float,
) -> dict | None:
    """Garis Under tangga terkecil dengan P(Under) >= target di banjir.

    tangga: hasil tangga_under (terurut naik). Mengembalikan entri tangga
    itu (apa adanya), atau None bila tidak ada garis yang lolos.
    """
    for entri in tangga:
        garis = float(entri["line"])
        if p_under_digeser(cdf, garis, geser_banjir) >= target:
            return entri
    return None


def garis_untuk_harga(tangga: list[dict], harga_cents: float) -> dict | None:
    """Entri tangga Under yang harganya paling dekat dengan target.

    Harga yang dipakai: price_cents (bila ada), kalau tidak
    jup_estimated_cents. Bila seri (selisih sama), garis yang lebih
    kecil yang dipilih. None bila tidak ada entri berharga.
    """
    if _angka(harga_cents) is None:
        raise ValueError(f"harga_cents harus angka: {harga_cents!r}")
    target = float(harga_cents)
    terbaik: dict | None = None
    selisih_terbaik: float | None = None
    for entri in tangga:
        harga = _angka(entri.get("price_cents"))
        if harga is None:
            harga = _angka(entri.get("jup_estimated_cents"))
        if harga is None:
            continue
        selisih = abs(harga - target)
        if selisih_terbaik is None or selisih < selisih_terbaik - 1e-9:
            terbaik = entri
            selisih_terbaik = selisih
    return terbaik


def _ringkas_entri_tangga(entri: dict | None) -> dict | None:
    """Ringkasan satu entri tangga untuk output (garis + harga + volume)."""
    if entri is None:
        return None
    return {
        "line": _angka(entri.get("line")),
        "price_cents": _angka(entri.get("price_cents")),
        "jup_estimated_cents": _angka(entri.get("jup_estimated_cents")),
        "volume_usd": _angka(entri.get("volume_usd")),
        "thin": entri.get("thin"),
    }


def _kaki_dari_artefak(analysis: dict, catatan: list[str]) -> list[dict]:
    """Bangun daftar kaki dari analysis['legs'] (garis numerik saja)."""
    kaki: list[dict] = []
    for leg in analysis.get("legs") or []:
        if not isinstance(leg, dict):
            continue
        garis = _angka(leg.get("line"))
        tiket = leg.get("ticket")
        if garis is None:
            catatan.append(
                f"kaki {tiket or '?'} tanpa garis di artefak — "
                "skenario panas tidak dihitung untuk kaki itu"
            )
            continue
        if tiket not in _TARGET_TIKET:
            raise ValueError(f"tiket kaki tidak dikenal: {tiket!r}")
        kaki.append(
            {
                "line": garis,
                "ticket": tiket,
                "price_cents": _angka(leg.get("price_cents")),
                "jup_estimated_cents": _angka(leg.get("jup_estimated_cents")),
            }
        )
    return kaki


def _validasi_kaki_eksplisit(kaki: list[dict]) -> list[dict]:
    """Validasi daftar kaki eksplisit (argumen kaki=...)."""
    hasil: list[dict] = []
    for entri in kaki:
        if not isinstance(entri, dict):
            raise ValueError(f"kaki harus dict: {entri!r}")
        garis = _angka(entri.get("line"))
        tiket = entri.get("ticket")
        if garis is None:
            raise ValueError(f"kaki tanpa garis numerik: {entri!r}")
        if tiket not in _TARGET_TIKET:
            raise ValueError(f"tiket kaki tidak dikenal: {tiket!r}")
        hasil.append(
            {
                "line": garis,
                "ticket": tiket,
                "price_cents": _angka(entri.get("price_cents")),
                "jup_estimated_cents": _angka(entri.get("jup_estimated_cents")),
            }
        )
    return hasil


def skenario_panas(
    analysis: dict,
    kaki: list[dict] | None = None,
    harga_cek: list[float] | None = None,
    cfg: dict | None = None,
) -> dict:
    """Hitung skenario panas satu laga NBA dari artefak nba_analysis.

    analysis: dict artefak ``nba_analysis`` v1 (butuh
      ``simulation.markets`` + ``simulation.score_distribution.total.
      median`` + ``market.main_total_line`` + ``market.totals``).
    kaki: daftar kaki eksplisit {"line", "ticket", "price_cents"?} —
      bila None, diambil dari analysis["legs"] (kaki tanpa garis
      dilewati + dicatat). ticket harus "insurance"/"main".
    harga_cek: daftar harga (sen) yang mau dicek ("di 82¢ tembus
      nggak kalau panas?") — untuk tiap harga dicari garis tangga
      Under terdekat harganya + P(Under) per skenario di garis itu.
    cfg: dict playstyle (default: dibaca dari config/playstyle.yaml).

    Mengembalikan dict format "nba_stress" v1: geser per skenario,
    P(Under) per kaki per skenario, garis tahan-banjir per kaki
    (atau None + alasan bila tidak ada), dan hasil cek harga.
    Raise ValueError bila CDF tidak bisa dibangun; ConfigError bila
    kunci config hilang (fail-closed, tanpa default dari kode).
    """
    if not isinstance(analysis, dict):
        raise ValueError("analysis harus dict")
    cfg = cfg if cfg is not None else config_mod.load_playstyle()
    geser_3p = float(config_mod.get_value(cfg, "stress", "banjir_3p_points"))
    geser_ft = float(config_mod.get_value(cfg, "stress", "banjir_ft_points"))
    if geser_3p < 0 or geser_ft < 0:
        raise config_mod.ConfigError("geser banjir harus >= 0")

    sim = analysis.get("simulation")
    if not isinstance(sim, dict):
        raise ValueError("analysis tanpa blok simulation")
    cdf = cdf_total_dari_markets(sim.get("markets"))
    dist = sim.get("score_distribution") or {}
    total = dist.get("total") if isinstance(dist, dict) else None
    median_sim = _angka(total.get("median")) if isinstance(total, dict) else None

    market = (
        analysis.get("market") if isinstance(analysis.get("market"), dict) else None
    )
    garis_market = _angka(market.get("main_total_line")) if market else None
    tangga = tangga_under(market)

    catatan: list[str] = []
    if median_sim is None:
        catatan.append(
            "median total simulasi tidak ada di artefak — skenario "
            "konservatif tidak terdefinisi"
        )
    if garis_market is None:
        catatan.append(
            "garis market utama (main_total_line) tidak ada di artefak — "
            "skenario konservatif tidak terdefinisi"
        )
    geser_konservatif: float | None = None
    if median_sim is not None and garis_market is not None:
        geser_konservatif = garis_market - median_sim
    if not tangga:
        catatan.append(
            "tangga total Under tidak ada di artefak — garis tahan-banjir "
            "tidak bisa dicari"
        )

    if geser_ft >= geser_3p:
        banjir_terburuk, geser_terburuk = "banjir_ft", geser_ft
    else:
        banjir_terburuk, geser_terburuk = "banjir_3p", geser_3p

    daftar_kaki = (
        _validasi_kaki_eksplisit(kaki)
        if kaki is not None
        else _kaki_dari_artefak(analysis, catatan)
    )
    if not daftar_kaki:
        catatan.append("tidak ada kaki Under bergaris — hanya geser dilaporkan")

    geser_skenario: dict[str, float | None] = {
        "normal": 0.0,
        "banjir_3p": geser_3p,
        "banjir_ft": geser_ft,
        "konservatif": geser_konservatif,
    }
    hasil_kaki: list[dict] = []
    for entri_kaki in daftar_kaki:
        garis = entri_kaki["line"]
        tiket = entri_kaki["ticket"]
        target = float(config_mod.get_value(cfg, *_TARGET_TIKET[tiket]))
        p_under: dict[str, float | None] = {}
        for nama, geser in geser_skenario.items():
            p_under[nama] = (
                round(p_under_digeser(cdf, garis, geser), 6)
                if geser is not None
                else None
            )
        p_banjir = p_under[banjir_terburuk]
        tahan = p_banjir is not None and p_banjir >= target
        entri_tahan = (
            garis_tahan_banjir(tangga, cdf, geser_terburuk, target) if tangga else None
        )
        alasan_tidak_tahan: str | None = None
        if not tangga:
            alasan_tidak_tahan = "tangga tidak ada di artefak"
        elif entri_tahan is None:
            alasan_tidak_tahan = (
                "tidak ada garis tangga yang P(Under) >= target "
                f"({target:.0%}) di skenario {banjir_terburuk}"
            )
        hasil_kaki.append(
            {
                "line": garis,
                "ticket": tiket,
                "price_cents": entri_kaki["price_cents"],
                "jup_estimated_cents": entri_kaki["jup_estimated_cents"],
                "target_probability": target,
                "p_under": p_under,
                "tahan_banjir": tahan,
                "garis_tahan_banjir": _ringkas_entri_tangga(entri_tahan),
                "alasan_tidak_tahan_banjir": alasan_tidak_tahan,
            }
        )

    hasil_cek_harga: list[dict] = []
    for harga in harga_cek or []:
        entri = garis_untuk_harga(tangga, harga)
        if entri is None:
            hasil_cek_harga.append(
                {
                    "harga_cents": float(harga),
                    "line": None,
                    "p_under": None,
                    "alasan": "tidak ada garis tangga berharga",
                }
            )
            continue
        garis_harga = float(entri["line"])
        hasil_cek_harga.append(
            {
                "harga_cents": float(harga),
                "line": garis_harga,
                "price_cents": _angka(entri.get("price_cents")),
                "jup_estimated_cents": _angka(entri.get("jup_estimated_cents")),
                "thin": entri.get("thin"),
                "p_under": {
                    nama: (
                        round(p_under_digeser(cdf, garis_harga, geser), 6)
                        if geser is not None
                        else None
                    )
                    for nama, geser in geser_skenario.items()
                },
            }
        )

    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "match_id": analysis.get("match_id"),
        "skenario": {
            "normal": {
                "geser_points": 0.0,
                "penjelasan": "Distribusi simulasi apa adanya (tanpa banjir).",
            },
            "banjir_3p": {
                "geser_points": round(geser_3p, 2),
                "penjelasan": (
                    "Banjir tripoin p90 (1 dari 10 laga tembakan tiga "
                    "panas). Dasar: " + _DASAR_BANJIR_3P + "."
                ),
            },
            "banjir_ft": {
                "geser_points": round(geser_ft, 2),
                "penjelasan": (
                    "Banjir lemparan bebas p90 (1 dari 10 laga banyak "
                    "pelanggaran/lemparan bebas). Dasar: " + _DASAR_BANJIR_FT + "."
                ),
            },
            "konservatif": {
                "geser_points": (
                    round(geser_konservatif, 2)
                    if geser_konservatif is not None
                    else None
                ),
                "garis_market": garis_market,
                "median_sim": median_sim,
                "penjelasan": (
                    "Distribusi dipusatkan ke garis market "
                    f"({garis_market}) dari median sim ({median_sim}); "
                    "sigma sama."
                    if geser_konservatif is not None
                    else "Tidak terdefinisi: garis market/median sim "
                    "tidak ada di artefak."
                ),
            },
        },
        "banjir_terburuk": banjir_terburuk,
        "geser_banjir_terburuk_points": round(geser_terburuk, 2),
        "kaki": hasil_kaki,
        "cek_harga": hasil_cek_harga,
        "catatan": catatan,
    }
