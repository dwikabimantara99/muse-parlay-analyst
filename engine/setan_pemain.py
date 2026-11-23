"""Setan per pemain: uji stress deviasi tripoin berbasis data pemain.

Menggantikan setan UMUM (+18,07 poin untuk semua laga — lihat
engine/stress.py) sebagai demon UTAMA bila data pemain tersedia; setan
umum tetap ada sebagai fallback (config stress.setan_points) bila data
pemain tidak tersedia.

RUMUS (disetujui user 2026-11-23 12:38 WIB, DECISIONS.md "Jawaban 4
pertanyaan" poin 2-3): demon per pemain = percobaan 3 poin per
laganya x % 3 poin TERBAIK liga musim ini (fakta dari data — % terbaik
di antara pemain yang memenuhi ambang percobaan minimum di config).
Dijumlah ke semua pemain tim — dengan percobaan yang DIHARAPKAN,
yaitu memperhitungkan siapa yang benar-benar main (BUKAN jumlah naif
seluruh roster):

- Pemain OUT (data cedera artefak analisis) -> percobaan 0.
- Pemain di luar rotasi (menit/laga < ambang_menit_rotasi di config)
  -> tidak dihitung (proksi ketersediaan bila data cedera tidak ada).
- Pemain rotasi yang main -> percobaan = fg3a per laga musim ini
  (per laga yang DIMAINKAN pemain — basis kekuatan penuh; lihat
  "BASIS KEKUATAN PENUH" di bawah).

Total setan tim = (total normal - poin 3P normal) + poin 3P setan,
di mana total normal = median sim, poin 3P normal = jumlah per pemain
(percobaan yang diharapkan x % 3P pemain itu x 3), dan poin 3P setan
= jumlah per pemain (percobaan yang diharapkan x % terbaik liga x 3).
Total setan LAGA = median_total - poin_3P_normal_kedua_tim +
poin_3P_setan_kedua_tim (dihitung per tim lalu digabung — pengurangan
dan penambahan memakai total yang sama sehingga konsisten).

P setan per kaki dihitung di engine/stress.py (bukan di sini): CDF sim
digeser sebesar total_setan_laga - median (geser_setan_pemain di
hasil ini) — cara yang sama seperti skenario banjir/setan umum.

STATUS EPISTEMIK (PENTING — jangan salah baca modul ini sebagai
prediksi): regresi ekor 3P (LAPORAN-EKOR-3P.md, n=2.466) menemukan
laju 3PA TIDAK memengaruhi ekor total (slope -0,3364, t=-0,17).
Setan per pemain TIDAK bertentangan dengan hasil itu karena ia
BUKAN prediksi — ia UJI STRESS (batas atas): "kalau SEMUA pemain
rotasi kedua tim menembak sebaik penembak terbaik liga dalam satu
laga yang sama, totalnya bisa sampai berapa?" Nilai itu dipakai
sebagai DETEKSI kerapuhan (total setan > garis kaki -> kaki rapuh),
bukan sebagai peluang terjadinya. Tidak ada klaim bahwa skenario
itu mungkin atau akan terjadi.

BASIS KEKUATAN PENUH: fg3a per laga di kedua sumber (stats.nba.com
dan BBRef) adalah per laga yang DIMAINKAN pemain, bukan per laga
tim. Pemain yang absen di sebagian laga musim ini (tapi main malam
ini) menyumbang rata-rata per laganya secara penuh — benar untuk
ekspektasi malam ini bila ia main, dan jumlahnya berjalan DI ATAS
rata-rata 3PA tim per laga musim ini (yang meratakan laga-laga saat
pemain itu absen). Di DEN@CHI: percobaan yang diharapkan 67,30 vs
rata-rata tim pra-laga 71,59 — LEBIH RENDAH karena dua penembak
terbesar CHI (Caleb Wilson 7,1 + Norman Powell 6,8 percobaan/laga)
OUT dan dikeluarkan; tanpa pengeluaran itu basis kekuatan penuh
berjalan ~10 percobaan di atas rata-rata tim. Perbandingan ini
tercatat di LAPORAN-SETAN-PEMAIN.md §5 — bukan kesalahan, melainkan
konsekuensi definisi "percobaan yang diharapkan".

Modul ini MURNI HITUNG: tanpa fetch, tanpa simulasi ulang, tanpa
Odds API. Satu-satunya I/O adalah baca config bila argumen cfg None
(pola yang sama dengan engine/stress.py).
"""

from __future__ import annotations

import math

import config as config_mod

FORMAT = "nba_setan_pemain"
FORMAT_VERSION = 1

# Jumlah kontributor terbesar yang dilaporkan per tim (detail laporan,
# bukan ambang — bukan angka strategi, jadi konstanta modul).
TOP_KONTRIBUTOR = 5

# Status cedera yang berarti "tidak main" (artefak nba_analysis
# memakai huruf besar; daftar cedera tingkat slate memakai kapitalisasi
# judul — keduanya diterima, perbandingan tanpa memperhatikan huruf).
_STATUS_ABSEN = {"out", "inactive", "dnp", "did not play"}


def _angka(nilai: object) -> float | None:
    """Ubah nilai jadi float; None bila bukan angka hingga (bool bukan angka)."""
    if isinstance(nilai, bool) or not isinstance(nilai, (int, float)):
        return None
    hasil = float(nilai)
    if not math.isfinite(hasil):
        return None
    return hasil


def pemain_absen_dari_artefak(analysis: dict) -> set[str]:
    """Kumpulkan nama pemain OUT dari artefak analisis NBA.

    Membaca dua bentuk yang ada di artefak: nba_analysis
    ["injuries"]["entries"] (status "OUT" + team_tricode) dan daftar
    cedera tingkat slate ["injuries"] (status "Out"). Nama dikembalikan
    apa adanya (pencocokan nama persis dengan data pemain; nama yang
    tidak cocok dengan pemain mana pun diabaikan hening oleh
    hitung_setan_pemain — dicatat di catatan hasil). Bila analysis
    bukan dict atau tidak ada blok cedera -> himpunan kosong.
    """
    absen: set[str] = set()
    if not isinstance(analysis, dict):
        return absen
    blok = analysis.get("injuries")
    entri: list = []
    if isinstance(blok, dict):
        entri = blok.get("entries") or []
    elif isinstance(blok, list):
        entri = blok
    for item in entri:
        if not isinstance(item, dict):
            continue
        status = (item.get("status") or "").strip().lower()
        nama = (item.get("player") or "").strip()
        if status in _STATUS_ABSEN and nama:
            absen.add(nama)
    return absen


def pct_terbaik_liga(pemain: list[dict], min_total_3pa: float) -> dict | None:
    """% 3P terbaik liga di antara pemain yang memenuhi ambang percobaan.

    pemain: list pemain skema ingest/pemain_3p.py (seluruh liga).
    min_total_3pa: percobaan 3P TOTAL minimum musim ini (fg3a_total;
    bila None, dihitung fg3a_per_game x games_played) — dari config
    setan_pemain.pct_terbaik_min_total_3pa. Kandidat butuh fg3_pct
    numerik 0-1 dan total percobaan >= ambang. Mengembalikan dict
    {pct, player, team, total_3pa, fg3a_per_game, games_played,
    source} atau None bila tidak ada kandidat. Seri % -> pemain
    dengan total percobaan lebih besar yang dipilih (sampel lebih
    besar = klaim "terbaik" lebih kuat); seri penuh -> nama pertama
    menurut abjad (deterministik).
    """
    if _angka(min_total_3pa) is None or float(min_total_3pa) < 0:
        raise ValueError(f"min_total_3pa harus angka >= 0: {min_total_3pa!r}")
    ambang = float(min_total_3pa)
    terbaik: dict | None = None
    for entri in pemain:
        if not isinstance(entri, dict):
            continue
        pct = _angka(entri.get("fg3_pct"))
        if pct is None or not 0.0 <= pct <= 1.0:
            continue
        total = _angka(entri.get("fg3a_total"))
        if total is None:
            fg3a = _angka(entri.get("fg3a_per_game"))
            games = _angka(entri.get("games_played"))
            if fg3a is not None and games is not None:
                total = fg3a * games
        if total is None or total < ambang:
            continue
        kandidat = {
            "pct": pct,
            "player": entri.get("player"),
            "team": entri.get("team"),
            "total_3pa": round(total, 2),
            "fg3a_per_game": _angka(entri.get("fg3a_per_game")),
            "games_played": entri.get("games_played"),
            "source": entri.get("source"),
        }
        if terbaik is None:
            terbaik = kandidat
            continue
        if (
            pct > terbaik["pct"]
            or (pct == terbaik["pct"] and total > terbaik["total_3pa"])
            or (
                pct == terbaik["pct"]
                and total == terbaik["total_3pa"]
                and str(kandidat["player"] or "") < str(terbaik["player"] or "")
            )
        ):
            terbaik = kandidat
    return terbaik


def _hitung_tim(
    pemain_tim: list[dict],
    tricode: str,
    pct_terbaik: float,
    ambang_menit_rotasi: float,
    pemain_absen: set[str],
    catatan: list[str],
) -> dict:
    """Hitung poin 3P normal + setan satu tim (lihat docstring modul).

    Mengembalikan dict rincian tim: tricode, jumlah pemain (rotasi
    main / absen dikeluarkan / di luar rotasi / dilewati tanpa data),
    percobaan yang diharapkan, poin 3P normal, poin 3P setan, dan
    top 5 kontributor (urut selisih poin setan vs normal menurun).
    """
    rotasi_main: list[dict] = []
    absen_dikeluarkan: list[str] = []
    n_di_luar_rotasi = 0
    n_tanpa_data = 0
    for entri in pemain_tim:
        if not isinstance(entri, dict):
            continue
        nama = entri.get("player") or "pemain_tidak_dikenal"
        if nama in pemain_absen:
            absen_dikeluarkan.append(nama)
            continue
        menit = _angka(entri.get("mp_per_game"))
        fg3a = _angka(entri.get("fg3a_per_game"))
        pct = _angka(entri.get("fg3_pct"))
        if menit is None or fg3a is None:
            # Tanpa menit tidak bisa dipastikan rotasi; tanpa percobaan
            # tidak bisa dihitung — dilewati + dicatat (bukan ditebak).
            n_tanpa_data += 1
            catatan.append(
                f"{tricode}: {nama} dilewati (data tidak lengkap: "
                f"menit={entri.get('mp_per_game')!r}, "
                f"fg3a={entri.get('fg3a_per_game')!r})"
            )
            continue
        if menit < ambang_menit_rotasi:
            n_di_luar_rotasi += 1
            continue
        if fg3a > 0 and (pct is None or not 0.0 <= pct <= 1.0):
            # Punya percobaan tapi % tidak valid — poin normalnya tidak
            # bisa dihitung; dilewati + dicatat (bukan ditebak 0%).
            n_tanpa_data += 1
            catatan.append(
                f"{tricode}: {nama} dilewati (% 3P tidak valid: "
                f"{entri.get('fg3_pct')!r} pada {fg3a} percobaan/laga)"
            )
            continue
        pct_efektif = pct if pct is not None else 0.0
        rotasi_main.append(
            {
                "player": nama,
                "fg3a_per_game": fg3a,
                "fg3_pct": pct_efektif,
                "mp_per_game": menit,
                "poin_3p_normal": fg3a * pct_efektif * 3.0,
                "poin_3p_setan": fg3a * pct_terbaik * 3.0,
            }
        )
    percobaan = sum(p["fg3a_per_game"] for p in rotasi_main)
    poin_normal = sum(p["poin_3p_normal"] for p in rotasi_main)
    poin_setan = sum(p["poin_3p_setan"] for p in rotasi_main)
    kontributor = sorted(
        rotasi_main,
        key=lambda p: (p["poin_3p_setan"] - p["poin_3p_normal"]),
        reverse=True,
    )[:TOP_KONTRIBUTOR]
    # Nilai TAK TERBULAT dikembalikan apa adanya — pembulatan hanya di
    # output hitung_setan_pemain (aturan repo: hitung dari nilai tak
    # terbulat, bulatkan hanya di output).
    return {
        "tricode": tricode,
        "n_pemain_rotasi_main": len(rotasi_main),
        "n_pemain_absen_dikeluarkan": len(absen_dikeluarkan),
        "pemain_absen_dikeluarkan": sorted(absen_dikeluarkan),
        "n_pemain_di_luar_rotasi": n_di_luar_rotasi,
        "n_pemain_dilewati_tanpa_data": n_tanpa_data,
        "percobaan_3p_diharapkan": percobaan,
        "poin_3p_normal": poin_normal,
        "poin_3p_setan": poin_setan,
        "selisih_poin_setan_vs_normal": poin_setan - poin_normal,
        "top_kontributor": [
            {
                "player": p["player"],
                "fg3a_per_game": p["fg3a_per_game"],
                "fg3_pct": p["fg3_pct"],
                "poin_3p_setan": p["poin_3p_setan"],
                "selisih_vs_normal": p["poin_3p_setan"] - p["poin_3p_normal"],
            }
            for p in kontributor
        ],
    }


def hitung_setan_pemain(
    pemain: list[dict],
    tricode_kandang: str,
    tricode_tandang: str,
    median_total: float,
    garis_bandar: float | None = None,
    pemain_absen: set[str] | None = None,
    cfg: dict | None = None,
) -> dict:
    """Hitung total setan per pemain satu laga (lihat docstring modul).

    pemain: list pemain SELURUH liga skema ingest/pemain_3p.py.
    tricode_kandang/tandang: tricode kedua tim (konvensi
    stats.nba.com). median_total: median total sim (total normal).
    garis_bandar: garis total market utama (None -> deviasi None).
    pemain_absen: nama pemain OUT (lihat pemain_absen_dari_artefak);
    None = tidak ada info cedera (hanya ambang rotasi yang memfilter).
    cfg: dict playstyle (default: dibaca dari config/playstyle.yaml);
    memakai setan_pemain.pct_terbaik_min_total_3pa dan
    setan_pemain.ambang_menit_rotasi (ConfigError bila kunci hilang —
    fail-closed, tanpa default dari kode).

    Mengembalikan dict format "nba_setan_pemain" v1: total setan laga,
    geser vs median (untuk engine/stress.py), deviasi vs garis bandar,
    % terbaik liga yang dipakai (+ pemainnya + sumbernya), rincian per
    tim + top 5 kontributor, dan catatan.
    Raise ValueError bila daftar pemain kosong, tidak ada kandidat %
    terbaik liga, atau median/garis tidak valid.
    """
    cfg = cfg if cfg is not None else config_mod.load_playstyle()
    min_total_3pa = float(
        config_mod.get_value(cfg, "setan_pemain", "pct_terbaik_min_total_3pa")
    )
    ambang_menit = float(
        config_mod.get_value(cfg, "setan_pemain", "ambang_menit_rotasi")
    )
    if min_total_3pa < 0:
        raise config_mod.ConfigError(
            "setan_pemain.pct_terbaik_min_total_3pa harus >= 0"
        )
    if ambang_menit < 0:
        raise config_mod.ConfigError("setan_pemain.ambang_menit_rotasi harus >= 0")
    median = _angka(median_total)
    if median is None:
        raise ValueError(f"median_total harus angka: {median_total!r}")
    garis = _angka(garis_bandar) if garis_bandar is not None else None
    if garis_bandar is not None and garis is None:
        raise ValueError(f"garis_bandar harus angka atau None: {garis_bandar!r}")
    if not isinstance(pemain, list) or not pemain:
        raise ValueError("daftar pemain kosong — setan per pemain tidak bisa dihitung")

    catatan: list[str] = []
    info_pct = pct_terbaik_liga(pemain, min_total_3pa)
    if info_pct is None:
        raise ValueError(
            "tidak ada pemain memenuhi ambang percobaan minimum "
            f"({min_total_3pa}) untuk % 3P terbaik liga"
        )
    pct_terbaik = float(info_pct["pct"])
    absen = set(pemain_absen or [])
    if pemain_absen is None:
        catatan.append(
            "tidak ada info cedera — ketersediaan hanya diproksi menit "
            "(ambang rotasi); pemain OUT yang tidak tercatat ikut terhitung"
        )

    kandang = _hitung_tim(
        [p for p in pemain if p.get("team") == tricode_kandang],
        tricode_kandang,
        pct_terbaik,
        ambang_menit,
        absen,
        catatan,
    )
    tandang = _hitung_tim(
        [p for p in pemain if p.get("team") == tricode_tandang],
        tricode_tandang,
        pct_terbaik,
        ambang_menit,
        absen,
        catatan,
    )
    if kandang["n_pemain_rotasi_main"] == 0:
        catatan.append(
            f"{tricode_kandang}: tidak ada pemain rotasi yang main — "
            "tim ini menyumbang 0 percobaan ke setan"
        )
    if tandang["n_pemain_rotasi_main"] == 0:
        catatan.append(
            f"{tricode_tandang}: tidak ada pemain rotasi yang main — "
            "tim ini menyumbang 0 percobaan ke setan"
        )
    # Nama absen yang tidak cocok dengan pemain mana pun di kedua tim
    # dicatat (kemungkinan salah eja / pemain pindah tim) — bukan
    # kesalahan fatal, tapi pemanggil harus tahu filternya tidak jalan.
    nama_dikenal = {p.get("player") for p in pemain if isinstance(p, dict)}
    for nama in sorted(absen - nama_dikenal):
        catatan.append(
            f"pemain absen {nama!r} tidak ditemukan di data pemain — "
            "filter absen tidak berpengaruh untuk nama itu"
        )

    # Total laga dihitung dari nilai TAK TERBULAT per tim, dibulatkan
    # hanya di output (aturan repo).
    poin_normal = kandang["poin_3p_normal"] + tandang["poin_3p_normal"]
    poin_setan = kandang["poin_3p_setan"] + tandang["poin_3p_setan"]
    percobaan = kandang["percobaan_3p_diharapkan"] + tandang["percobaan_3p_diharapkan"]
    total_setan = median - poin_normal + poin_setan

    def _bulatkan_tim(rincian: dict) -> dict:
        """Bulatkan angka rincian tim untuk output (2 desimal; % 3 desimal)."""
        hasil = dict(rincian)
        for kunci in (
            "percobaan_3p_diharapkan",
            "poin_3p_normal",
            "poin_3p_setan",
            "selisih_poin_setan_vs_normal",
        ):
            hasil[kunci] = round(rincian[kunci], 2)
        hasil["top_kontributor"] = [
            {
                "player": k["player"],
                "fg3a_per_game": round(k["fg3a_per_game"], 2),
                "fg3_pct": round(k["fg3_pct"], 3),
                "poin_3p_setan": round(k["poin_3p_setan"], 2),
                "selisih_vs_normal": round(k["selisih_vs_normal"], 2),
            }
            for k in rincian["top_kontributor"]
        ]
        return hasil

    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "median_total": median,
        "garis_bandar": garis,
        "total_setan_pemain": round(total_setan, 2),
        "geser_setan_pemain": round(total_setan - median, 2),
        "deviasi_setan_pemain_dari_garis_bandar": (
            round(total_setan - garis, 2) if garis is not None else None
        ),
        "percobaan_3p_diharapkan_gabungan": round(percobaan, 2),
        "poin_3p_normal_gabungan": round(poin_normal, 2),
        "poin_3p_setan_gabungan": round(poin_setan, 2),
        "pct_terbaik_liga": info_pct,
        "ambang_pct_terbaik_min_total_3pa": min_total_3pa,
        "ambang_menit_rotasi": ambang_menit,
        "tim": {
            "kandang": _bulatkan_tim(kandang),
            "tandang": _bulatkan_tim(tandang),
        },
        "catatan": catatan,
    }
