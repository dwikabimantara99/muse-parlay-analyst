"""Vonis per laga NBA: HIJAU / MENENGAH_HIJAU / KUNING dari data.

Latar: tiket nyata user 23 Nov 2026 kalah karena DEN@CHI (total akhir
296, OT, 42 tripoin; median pra-laga 233, garis bandar 236,5). Yang
JUJUR tidak terprediksi adalah banjirnya sendiri (kedua tim penembak
tripoin di bawah rata-rata musim) — yang TERDETEKSI adalah RAPUHNYA.
Keputusan user 2026-11-23 12:38 WIB: mesin menghitung vonis per laga
dari indikator-indikator pelajaran Denver — HIJAU/sehat (kandidat
Asuransi), MENENGAH_HIJAU (kandidat Utama), KUNING/lempar koin (skip
dari kedua tiket). Definisi vonis "terserah mesin, asal data di
baliknya cukup" — aturan persis di bawah ini + ambang di section
``vonis:`` config/playstyle.yaml (semua INITIAL, FIT dari slate
10 baris 22 Nov 2026 — lihat komentar config + LAPORAN-VONIS.md).

GARIS ASURANSI (garis rujukan — semua indikator per garis dibaca di
sini, bukan di garis artefak sembarang): garis yang akan dimainkan
mesin untuk Asuransi, prioritas:
  (a) garis equilibrium Asuransi (bila ada);
  (b) garis tahan-banjir TIDAK-TIPIS terendah (bila ada);
  (c) garis kaki Asuransi artefak (bila bergaris + berharga);
  (d) garis equilibrium Utama (bila ada);
  (e) garis kaki Utama artefak (bila bergaris + berharga);
  (f) garis acuan (garis tangga termurah dengan P normal >= 0,74).
Bila tidak satu pun ada -> vonis KUNING data_tidak_cukup.

INDIKATOR (8, dari pelajaran Denver):
  (1) edge kaki terbaik: maks edge (p_final - harga venue) atas kaki
      artefak + garis equilibrium kedua tiket + garis Asuransi.
      Edge terbaik adalah sifat LAGA ("apakah laga ini menawarkan
      nilai di mana pun?"), bukan sifat satu kaki — gate edge per kaki
      tetap diurus komposer.
  (2) P Under di banjir terburuk pada garis Asuransi (geser terbesar
      banjir_3p/banjir_ft; dari hasil_stress bila diberikan dan memuat
      garis itu, kalau tidak dihitung langsung dari CDF — matematikanya
      sama, engine/stress.p_under_digeser).
  (3) P Under di skenario setan pada garis Asuransi (sumber sama).
      CATATAN: banjir dan setan berkorelasi (keduanya menggeser CDF
      yang sama) tapi geser + ambangnya berbeda — banjir terburuk
      memakai geser p90 data bersih (saat penulisan 12,52 poin),
      setan memakai deviasi maksimal (18,07 poin) — sehingga
      keduanya bisa berbeda putusan (mis. BOS@GSW live: P banjir
      67,3% tapi P setan 56,5%). Keduanya tetap dihitung terpisah
      karena user menamai keduanya sebagai indikator Denver yang
      berbeda.
  (4) volume per garis pada garis Asuransi: thin = flag thin True ATAU
      volume_usd < polymarket_ladder.min_volume_usd ($100 — ambang
      dipakai ulang, tidak diubah). Volume PER GARIS, bukan volume
      laga (jawaban user 12:38 WIB).
  (5) gap model-vs-pasar (p_model - p_market) pada garis Asuransi
      lewat jangkar pasar (engine/equilibrium.peluang_pada_garis).
  (6) sinyal garis-jauh + harga-rendah (pasar bilang ekor gemuk),
      RUMUS EKSPLISIT: jarak = garis Asuransi - main_total_line
      (poin); sinyal TRUE bila jarak >= vonis.ekor_jauh_points DAN
      harga venue garis Asuransi <= vonis.ekor_harga_rendah_cents.
  (7) risiko OT: ot_probability sim (engine/skip_awal).
  (8) level total: main_total_line (garis bandar).

KOMBINASI (sistem demerit — tiap indikator lemah = 1 demerit):
  - edge_kecil: edge terbaik < vonis.edge_hijau_pct.
  - banjir_lemah: P banjir < target Asuransi (0,74, dipakai ulang
    dari tickets.insurance.min_leg_prob) DAN tidak ada garis
    tidak-tipis yang tahan banjir.
  - setan_lemah: P setan < vonis.p_setan_hijau.
  - volume_tipis: garis Asuransi thin (lihat (4)).
  - volume_tidak_diketahui: thin dan volume sama-sama tidak tercatat
    (tidak bisa dibuktikan bisa dibeli — demerit, bukan pemicu keras).
  - gap_kecil: gap < vonis.gap_kecil_pct (model hampir setuju dengan
    bandar = tidak ada keunggulan).
  - gap_besar: gap > anomaly.model_vs_market_points (8,0 poin,
    dipakai ulang — model jauh dari pasar, "Kenapa beda?").
  - ekor_gemuk: sinyal (6) TRUE.
  - total_tinggi: garis bandar >= vonis.total_tinggi_points.
  PEMICU KERAS (langsung KUNING, berapa pun demeritnya):
  - data_tidak_cukup: data WAJIB hilang (lihat di bawah).
  - ot_tinggi: ot_probability >= ot_seleksi.skip_ot_prob (0,028,
    dipakai ulang — selaras dengan skip_awal).
  - edge_tidak_positif: edge terbaik <= 0 (tidak ada nilai di mana
    pun di laga ini).
  - veto_rim_protector: rim protector OUT terkonfirmasi + garis
    pasar tinggi ATAU pace tinggi (lihat VETO di bawah) — tidak
    bisa dikalahkan skor EV simulasi.

VETO RIM PROTECTOR (temua Gemini yang sudah DIVERIFIKASI main agent
dari data mesin; keputusan koordinator 2026-11-23 12:54 WIB):
Nic Claxton (center utama CHI, 1,0 blok/laga) OUT vs Jokic,
terkonfirmasi 2 sumber di artefak verif DEN@CHI (Official NBA Injury
Report + ESPN) — veto HARUS menyala di laga itu. Rasional: sim
menyesuaikan BPM pemain absen, tapi tidak memodelkan hilangnya
perlindungan ring secara eksplisit; di lingkungan skor-tinggi
(garis pasar tinggi ATAU pace tinggi) tim tanpa pelindung ring
kebobolan jauh lebih mudah dan kaki Under jadi berbahaya.
  - RIM PROTECTOR (definisi data, bukan perasaan): per tim maksimal
    2 pemain rotasi (GP >= 3, MP >= 15) dengan blok bermakna
    (BLK >= 0,8), urut BPG tertinggi — diturunkan dari stats.nba.com
    (fallback BBRef) oleh scripts/fetch_rim_protector.py ke file
    config/rim_protector_2026-27.json (CHECK-IN, segarkan mingguan).
    Ambang derivasi di config vonis.rim_protector. KENAPA TOP-2:
    perlindungan ring adalah pekerjaan rotasi; selisih BPG #1 vs #2
    sering di dalam noise (CHI: Jalen Smith 1,1 vs Claxton 1,0).
    KETERBATASAN JUJUR: aturan BPG murni bisa menamai guard di tim
    yang bloknya lemah (DET: Cade Cunningham 0,9); pemain dengan
    0–2 laga tidak bisa diidentifikasi (Jalen Duren DET, 2 laga);
    alasan veto selalu menyebut nama + angka bloknya supaya bisa
    diaudit. Klaim "Aday Mara OUT di OKC" TIDAK dipakai (tidak ada
    di data cedera mesin — Mara justru pemimpin blok OKC yang MAIN).
  - OUT TERKONFIRMASI: status OUT di data ketersediaan artefak
    (injuries.entries) dengan >= 2 sumber (availability_n_sources,
    fallback jumlah sources). OUT 1 sumber TIDAK memveto.
  - KONDISI LINGKUNGAN (salah satu cukup): main_total_line >=
    vonis.veto_total_tinggi_points (235,0) ATAU pace musim tertinggi
    kedua tim >= vonis.veto_pace_tinggi (102,0). Pace tim tercepat
    dipakai (bukan pace laga rata-rata sim) karena tim tercepat yang
    menentukan tempo menyerang melawan pertahanan tanpa pelindung
    ring.
  - Veto dievaluasi untuk SETIAP laga NBA (juga yang data wajibnya
    hilang — hasilnya tercatat di indikator.veto); bila veto tidak
    bisa dievaluasi (pemetaan hilang/rusak, data ketersediaan tidak
    ada, tidak ada tim yang terpetakan, atau garis+pace sama-sama
    tidak ada) veto TIDAK menyala dan alasannya dicatat — veto
    adalah klaim positif yang butuh data, bukan default; permainan
    tetap dinilai sistem demerit. Veto yang tidak dievaluasi dicatat
    di tidak_dinilai (seperti indikator sekunder lain).
  VONIS: pemicu keras -> KUNING; 0 demerit -> HIJAU; 1 s.d.
  vonis.max_demerit_menengah demerit -> MENENGAH_HIJAU; lebih dari
  itu -> KUNING.

DATA WAJIB vs SEKUNDER (fail-closed):
  - WAJIB (hilang -> KUNING data_tidak_cukup): CDF total
    (simulation.markets), tangga Under (market.totals), jangkar pasar
    (kaki artefak bergaris + p_market — sama seperti equilibrium),
    ot_probability, dan satu garis Asuransi yang bisa dipilih +
    harganya. Edge terbaik selalu bisa dihitung begitu garis Asuransi
    terpilih (p_final dari CDF + jangkar, harga dari tangga/kaki).
    Tanpa salah satunya, vonis tidak bisa dihitung jujur — defaultnya
    KUNING, bukan "tidak dievaluasi".
    PENGECUALIAN KOMPOSER (didokumentasikan, menunggu keberatan):
    komposer hanya mengeluarkan laga KUNING yang DIEVALUASI
    (indikator.dievaluasi True); laga KUNING-karena-data tetap
    lewat ke gate per kaki (yang sudah fail-closed sendiri) supaya
    satu ladder fetch yang gagal tidak mematikan seluruh slate
    termasuk Utama — preseden yang sama dengan skip_awal ("tanpa
    data -> tidak dievaluasi, BUKAN skip").
  - SEKUNDER (hilang -> tidak dinilai, dicatat, TANPA demerit):
    main_total_line — memberi makan (6) ekor gemuk dan (8) level
    total. Keduanya satu demerit sekunder; hilangnya tidak boleh
    sendirian membuat KUNING, dan 6 indikator lain tetap menilai.
  - Volume tidak diketahui (flag + angka sama-sama hilang) -> demerit
    volume_tidak_diketahui (tengah-tengah: tidak diabaikan, tidak
    juga pemicu keras).
  - Laga bola (format soccer_analysis) -> KUNING "bukan NBA"
    (dievaluasi False) — vonis hanya untuk total Under NBA, seperti
    skip_awal; komposer + laporan memanggilnya hanya untuk NBA.

HASIL_STRESS (argumen opsional): bila diberikan dan memuat entri kaki
pada garis Asuransi (dicocokkan per GARIS saja — P Under per skenario
hanya bergantung pada garis, bukan tiket), P banjir/setan diambil
dari sana supaya angkanya persis sama dengan gate komposer; bila
tidak ada entri yang cocok atau argumen None, dihitung langsung dari
CDF. Tidak pernah raise karena hasil_stress berbentuk aneh — entri
yang tidak bisa dibaca dilewati dan dihitung langsung.

Modul ini MURNI HITUNG: tanpa fetch, tanpa simulasi ulang, tanpa
Odds API. Satu-satunya I/O adalah baca config bila argumen cfg None
+ baca file data rim protector yang CHECK-IN di repo (dipakai veto;
bila file hilang/rusak, veto tidak dievaluasi — bukan crash).
Tidak membaca flag equilibrium.enabled / skip_awal.enabled — vonis
selalu menilai dari data; flag vonis.enabled hanya dipakai komposer.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

import config as config_mod
from engine import equilibrium as equilibrium_mod
from engine import skip_awal as skip_awal_mod
from engine import stress as stress_mod

# Nilai vonis (kontrak API — dipakai worker lain, jangan diubah).
VONIS_HIJAU = "hijau"
VONIS_MENENGAH_HIJAU = "menengah_hijau"
VONIS_KUNING = "kuning"

# Token demerit (stabil untuk laporan + JSON ukur).
DEMERIT_EDGE_KECIL = "edge_kecil"
DEMERIT_BANJIR_LEMAH = "banjir_lemah"
DEMERIT_SETAN_LEMAH = "setan_lemah"
DEMERIT_VOLUME_TIPIS = "volume_tipis"
DEMERIT_VOLUME_TIDAK_DIKETAHUI = "volume_tidak_diketahui"
DEMERIT_GAP_KECIL = "gap_kecil"
DEMERIT_GAP_BESAR = "gap_besar"
DEMERIT_EKOR_GEMUK = "ekor_gemuk"
DEMERIT_TOTAL_TINGGI = "total_tinggi"

# Token pemicu keras (stabil untuk laporan + JSON ukur).
PICU_DATA_TIDAK_CUKUP = "data_tidak_cukup"
PICU_OT_TINGGI = "ot_tinggi"
PICU_EDGE_TIDAK_POSITIF = "edge_tidak_positif"
PICU_VETO_RIM_PROTECTOR = "veto_rim_protector"
PICU_BUKAN_NBA = "bukan_nba"

# Pemetaan rim protector (CHECK-IN di repo; ditulis ulang oleh
# scripts/fetch_rim_protector.py). Jalur relatif terhadap root repo.
PEMETAAN_RIM_PROTECTOR = "config/rim_protector_2026-27.json"


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
    if cfg is not None:
        return cfg
    return config_mod.load_playstyle()


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
    """Harga venue jup.ag satu entri tangga/kaki (jup, fallback Polymarket)."""
    harga = _angka(entri.get("jup_estimated_cents"))
    if harga is not None:
        return harga
    return _angka(entri.get("price_cents"))


def _buka_analysis(analysis: dict) -> dict:
    """Satu entri match artefak -> dict nba_analysis.

    Menerima dict nba_analysis langsung, ATAU satu entri match dari
    artefak slate ({"match_id", "nba_analysis": {...}}) — dibungkus
    dibuka supaya pemanggil dari kedua sisi bisa memakai API yang
    sama. Bukan dict -> ValueError.
    """
    if not isinstance(analysis, dict):
        raise ValueError("analysis harus dict")
    dalam = analysis.get("nba_analysis")
    if isinstance(dalam, dict):
        return dalam
    return analysis


def _tipis(entri: dict | None, min_volume_usd: float) -> bool | None:
    """Apakah satu garis tangga/kaki tipis? None bila tidak bisa dinilai.

    Tipis = flag thin True ATAU volume_usd < ambang config ($100).
    Keduanya dibaca karena flag dan angka bisa tidak sepakat (data
    basi) — yang konservatif menang. None hanya bila flag bukan True
    DAN volume tidak tercatat.
    """
    if not isinstance(entri, dict):
        return None
    if entri.get("thin") is True:
        return True
    volume = _angka(entri.get("volume_usd"))
    if volume is not None:
        return volume < min_volume_usd
    if entri.get("thin") is False:
        return False
    return None


def _entri_tangga(tangga: list[dict], garis: float) -> dict | None:
    """Entri tangga Under pada satu garis (toleransi 1e-9), atau None."""
    for entri in tangga:
        garis_entri = _angka(entri.get("line"))
        if garis_entri is not None and abs(garis_entri - garis) < 1e-9:
            return entri
    return None


def _garis_tahan_banjir_nonthin(ktx: dict, target: float, min_volume: float) -> dict:
    """Garis tahan-banjir tidak-tipis terendah + hitungan (dari konteks).

    Mengembalikan {"entri", "garis", "harga_venue_cents", "thin",
    "volume_usd", "n_tahan_banjir", "n_tahan_banjir_nonthin"} —
    "entri" None bila tidak ada garis tidak-tipis yang tahan banjir.
    "Tidak-tipis" memakai definisi _tipis() modul ini (flag ATAU
    volume), bukan hanya flag seperti cari_garis_acuan — selisihnya
    hanya muncul bila flag dan angka volume tidak sepakat.
    """
    hasil = {
        "entri": None,
        "garis": None,
        "harga_venue_cents": None,
        "thin": None,
        "volume_usd": None,
        "n_tahan_banjir": 0,
        "n_tahan_banjir_nonthin": 0,
    }
    for entri in ktx["tangga"]:
        garis = float(entri["line"])
        p_banjir = stress_mod.p_under_digeser(
            ktx["cdf"], garis, ktx["geser_banjir_terburuk"]
        )
        if p_banjir < target:
            continue
        hasil["n_tahan_banjir"] += 1
        if _tipis(entri, min_volume) is True:
            continue
        # Thin yang tidak bisa dinilai (None) TIDAK dihitung sebagai
        # tidak-tipis — garis tahan yang tidak terbukti bisa dibeli
        # bukan garis yang bisa menyelamatkan Asuransi.
        if _tipis(entri, min_volume) is not False:
            continue
        hasil["n_tahan_banjir_nonthin"] += 1
        if hasil["entri"] is None:
            hasil["entri"] = entri
            hasil["garis"] = garis
            hasil["harga_venue_cents"] = _harga_venue(entri)
            hasil["thin"] = entri.get("thin")
            hasil["volume_usd"] = _angka(entri.get("volume_usd"))
    return hasil


def _p_dari_stress(
    hasil_stress: dict | None, garis: float
) -> tuple[float | None, float | None, str | None]:
    """(P banjir terburuk, P setan, nama skenario) dari hasil_stress.

    Dicocokkan per GARIS saja (P Under per skenario hanya bergantung
    pada garis, bukan tiket). (None, None, None) bila tidak ada entri
    yang cocok / tidak bisa dibaca — pemanggil menghitung langsung
    dari CDF. Tidak pernah raise.
    """
    if not isinstance(hasil_stress, dict):
        return None, None, None
    try:
        banjir_terburuk = hasil_stress.get("banjir_terburuk")
        for entri in hasil_stress.get("kaki") or []:
            if not isinstance(entri, dict):
                continue
            garis_entri = _angka(entri.get("line"))
            if garis_entri is None or abs(garis_entri - garis) >= 1e-9:
                continue
            p_under = entri.get("p_under")
            if not isinstance(p_under, dict):
                return None, None, None
            p_banjir = None
            if isinstance(banjir_terburuk, str):
                p_banjir = _angka(p_under.get(banjir_terburuk))
            if p_banjir is None:
                # Fallback: yang terburuk dari kedua skenario banjir.
                kandidat = [
                    _angka(p_under.get(nama)) for nama in stress_mod.SKENARIO_BANJIR
                ]
                kandidat = [p for p in kandidat if p is not None]
                p_banjir = min(kandidat) if kandidat else None
            p_setan = _angka(p_under.get("setan"))
            return p_banjir, p_setan, banjir_terburuk
    except (AttributeError, TypeError, ValueError):
        return None, None, None
    return None, None, None


def _normalisasi_nama(nama) -> str:
    """Normalisasi nama pemain untuk pencocokan antar-sumber.

    Huruf kecil, aksen dilipat ("Jokić" -> "jokic"), tanda baca
    .' - dibuang ("Day'Ron" -> "dayron"), spasi diringkas — sumber
    stats.nba.com dan laporan cedera tidak selalu menulis nama
    dengan persis sama.
    """
    if not isinstance(nama, str):
        return ""
    tanpa_aksen = unicodedata.normalize("NFKD", nama)
    tanpa_aksen = tanpa_aksen.encode("ascii", "ignore").decode("ascii")
    tanpa_aksen = re.sub(r"[.'\-]", "", tanpa_aksen.lower())
    return re.sub(r"\s+", " ", tanpa_aksen).strip()


def _muat_rim_protector() -> tuple[dict | None, dict | None, str | None]:
    """Muat pemetaan rim protector (teams, meta, galat).

    (None, None, alasan-galat) bila file hilang / bukan JSON /
    format salah — pemanggil memperlakukan veto sebagai tidak
    dievaluasi, bukan crash.
    """
    jalur = Path(__file__).resolve().parent.parent / PEMETAAN_RIM_PROTECTOR
    try:
        dokumen = json.loads(jalur.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, None, f"file pemetaan tidak ada: {PEMETAAN_RIM_PROTECTOR}"
    except (OSError, ValueError) as exc:
        return None, None, f"file pemetaan tidak bisa dibaca: {exc}"
    if not isinstance(dokumen, dict) or dokumen.get("format") != "rim_protector":
        return None, None, "file pemetaan format salah (bukan rim_protector)"
    tim = dokumen.get("teams")
    if not isinstance(tim, dict):
        return None, None, "file pemetaan tanpa kunci teams"
    meta = {
        "musim": dokumen.get("season"),
        "diambil": dokumen.get("fetched_at"),
        "sumber": dokumen.get("source"),
    }
    return tim, meta, None


def _tricode_tim(analysis: dict) -> tuple[str | None, str | None]:
    """Tricode (tandang, kandang) dari match_id, fallback data pemain.

    match_id artefak berbentuk "DEN@CHI_2026-11-22". Fallback:
    team_tricode pemain pertama tiap sisi (inputs.away/home.players).
    """
    match_id = analysis.get("match_id")
    if isinstance(match_id, str):
        cocok = re.match(r"^([A-Z]{3})@([A-Z]{3})_", match_id)
        if cocok:
            return cocok.group(1), cocok.group(2)
    inputs = analysis.get("inputs") if isinstance(analysis.get("inputs"), dict) else {}
    hasil: list[str | None] = []
    for sisi in ("away", "home"):
        tricode = None
        blok = inputs.get(sisi) if isinstance(inputs.get(sisi), dict) else {}
        pemain = blok.get("players") if isinstance(blok.get("players"), list) else []
        for entri in pemain:
            if isinstance(entri, dict) and isinstance(entri.get("team_tricode"), str):
                tricode = entri["team_tricode"]
                break
        hasil.append(tricode)
    return hasil[0], hasil[1]


def _pace_tercepat(analysis: dict) -> tuple[float | None, dict]:
    """Pace musim tertinggi kedua tim + rincian per tim.

    (None, rincian) bila pace kedua tim sama-sama tidak ada.
    """
    inputs = analysis.get("inputs") if isinstance(analysis.get("inputs"), dict) else {}
    rincian: dict[str, float | None] = {}
    for sisi in ("away", "home"):
        blok = inputs.get(sisi) if isinstance(inputs.get(sisi), dict) else {}
        musim = (
            blok.get("stats_season")
            if isinstance(blok.get("stats_season"), dict)
            else {}
        )
        rincian[sisi] = _angka(musim.get("pace"))
    nilai = [p for p in rincian.values() if p is not None]
    return (max(nilai) if nilai else None), rincian


def _out_terkonfirmasi(entri: dict) -> bool:
    """Apakah entri cedera menyatakan OUT terkonfirmasi (>= 2 sumber)?

    Status harus OUT (tepat, tidak peka huruf); konfirmasi dari
    availability_n_sources, fallback jumlah sources. OUT 1 sumber
    TIDAK terkonfirmasi (selaras aturan cedera B2 mesin: cedera
    perlu 2 sumber).
    """
    if not isinstance(entri, dict):
        return False
    status = entri.get("status")
    if not isinstance(status, str) or status.upper() != "OUT":
        return False
    n_sumber = _angka(entri.get("availability_n_sources"))
    if n_sumber is None:
        sumber = entri.get("sources")
        n_sumber = float(len(sumber)) if isinstance(sumber, list) else 0.0
    return n_sumber >= 2


def evaluasi_veto(
    analysis: dict, cfg: dict | None = None, pemetaan: dict | None = None
) -> dict:
    """Evaluasi veto rim protector satu laga (tidak pernah raise data).

    ``analysis``: dict nba_analysis (atau entri match — dibuka dulu).
    ``cfg``: dict playstyle (default: dibaca dari file). ``pemetaan``:
    override pemetaan teams {tricode: [pelindung]} untuk tes; None
    berarti muat dari file CHECK-IN.

    Mengembalikan dict veto (lihat docstring modul, bagian VETO):
    dievaluasi, menyala, alasan (kalimat), pelindung_out,
    pelindung_diperiksa, tim, garis_pasar, pace_tercepat, ambang,
    kondisi, provenance pemetaan, alasan_tidak_dievaluasi. Config
    rusak (ambang veto hilang/bukan angka) -> ConfigError, sama
    seperti ambang lain; semua masalah DATA -> dievaluasi False
    dengan alasan tercatat.
    """
    analysis = _buka_analysis(analysis)
    cfg = _muat_cfg(cfg)
    ambang_garis = _ambang(cfg, "vonis", "veto_total_tinggi_points")
    ambang_pace = _ambang(cfg, "vonis", "veto_pace_tinggi")
    hasil: dict = {
        "dievaluasi": False,
        "menyala": False,
        "alasan": [],
        "pelindung_out": [],
        "pelindung_diperiksa": [],
        "tim": {"away": None, "home": None},
        "tim_tidak_terpetakan": [],
        "garis_pasar": None,
        "pace_tercepat": None,
        "pace_per_tim": {},
        "ambang_garis": ambang_garis,
        "ambang_pace": ambang_pace,
        "kondisi_garis": None,
        "kondisi_pace": None,
        "pemetaan_musim": None,
        "pemetaan_diambil": None,
        "pemetaan_sumber": None,
        "alasan_tidak_dievaluasi": None,
    }
    try:
        if pemetaan is None:
            pemetaan, meta, galat = _muat_rim_protector()
            if pemetaan is None:
                hasil["alasan_tidak_dievaluasi"] = galat
                return hasil
            hasil["pemetaan_musim"] = meta.get("musim")
            hasil["pemetaan_diambil"] = meta.get("diambil")
            hasil["pemetaan_sumber"] = meta.get("sumber")
        tandang, kandang = _tricode_tim(analysis)
        hasil["tim"] = {"away": tandang, "home": kandang}
        if tandang is None and kandang is None:
            hasil["alasan_tidak_dievaluasi"] = (
                "tricode kedua tim tidak ditemukan (match_id / data pemain)"
            )
            return hasil
        cedera = analysis.get("injuries")
        if not isinstance(cedera, dict) or not isinstance(cedera.get("entries"), list):
            hasil["alasan_tidak_dievaluasi"] = (
                "data ketersediaan (injuries.entries) tidak ada di artefak"
            )
            return hasil
        entri_cedera = cedera["entries"]
        # Peta nama ternormalisasi -> entri cedera (OUT saja yang
        # relevan, tapi status lain tetap dicatat bila cocok).
        peta_cedera: dict[str, dict] = {}
        for entri in entri_cedera:
            if not isinstance(entri, dict):
                continue
            nama = _normalisasi_nama(entri.get("player"))
            if nama:
                peta_cedera.setdefault(nama, entri)
        ada_tim_terpetakan = False
        for tricode in (tandang, kandang):
            if tricode is None:
                continue
            pelindung = pemetaan.get(tricode)
            if not isinstance(pelindung, list) or not pelindung:
                hasil["tim_tidak_terpetakan"].append(tricode)
                continue
            ada_tim_terpetakan = True
            for orang in pelindung:
                if not isinstance(orang, dict):
                    continue
                nama = orang.get("player")
                blk = _angka(orang.get("blk_per_game"))
                entri = peta_cedera.get(_normalisasi_nama(nama))
                if entri is not None and _out_terkonfirmasi(entri):
                    status = "OUT_terkonfirmasi"
                    sumber = entri.get("sources")
                    hasil["pelindung_out"].append(
                        {
                            "player": nama,
                            "team": tricode,
                            "blk_per_game": blk,
                            "sumber": (
                                list(sumber) if isinstance(sumber, list) else None
                            ),
                        }
                    )
                elif (
                    entri is not None
                    and isinstance(entri.get("status"), str)
                    and entri["status"].upper() == "OUT"
                ):
                    status = "OUT_belum_terkonfirmasi"
                else:
                    status = "main"
                hasil["pelindung_diperiksa"].append(
                    {
                        "player": nama,
                        "team": tricode,
                        "blk_per_game": blk,
                        "status": status,
                    }
                )
        if not ada_tim_terpetakan:
            hasil["alasan_tidak_dievaluasi"] = (
                "tidak ada tim yang terpetakan di pemetaan rim protector"
            )
            return hasil
        market = (
            analysis.get("market") if isinstance(analysis.get("market"), dict) else None
        )
        garis_pasar = _angka(market.get("main_total_line")) if market else None
        pace, pace_per_tim = _pace_tercepat(analysis)
        hasil["garis_pasar"] = garis_pasar
        hasil["pace_tercepat"] = pace
        hasil["pace_per_tim"] = pace_per_tim
        if garis_pasar is None and pace is None:
            hasil["alasan_tidak_dievaluasi"] = (
                "garis pasar dan pace sama-sama tidak ada — kondisi "
                "lingkungan veto tidak bisa dinilai"
            )
            return hasil
        hasil["kondisi_garis"] = (
            garis_pasar >= ambang_garis if garis_pasar is not None else None
        )
        hasil["kondisi_pace"] = pace >= ambang_pace if pace is not None else None
        hasil["dievaluasi"] = True
        if hasil["pelindung_out"] and (
            hasil["kondisi_garis"] is True or hasil["kondisi_pace"] is True
        ):
            hasil["menyala"] = True
            kondisi: list[str] = []
            if hasil["kondisi_garis"] is True:
                kondisi.append(f"garis pasar {garis_pasar:g} >= {ambang_garis:g}")
            if hasil["kondisi_pace"] is True:
                kondisi.append(f"pace tercepat {pace:g} >= {ambang_pace:g}")
            for orang in hasil["pelindung_out"]:
                sumber = orang.get("sumber")
                teks_sumber = f" ({', '.join(sumber)})" if sumber else " (2 sumber)"
                hasil["alasan"].append(
                    "VETO rim protector: "
                    f"{orang['player']} ({orang['team']}, "
                    f"{orang['blk_per_game']} blok/laga) OUT terkonfirmasi"
                    f"{teks_sumber} + {' dan '.join(kondisi)} — "
                    "tim tanpa pelindung ring di laga skor-tinggi, "
                    "kaki Under berbahaya"
                )
        return hasil
    except (AttributeError, TypeError, ValueError):
        # Data berbentuk aneh -> veto tidak dievaluasi (bukan crash).
        hasil["dievaluasi"] = False
        hasil["menyala"] = False
        hasil["alasan"] = []
        hasil["alasan_tidak_dievaluasi"] = "data veto berbentuk tidak wajar"
        return hasil


def _kuning_data(
    match_id, pemicu: str, alasan: str | list[str], indikator: dict | None = None
) -> dict:
    """Hasil KUNING fail-closed (data tidak cukup / bukan NBA)."""
    hasil_indikator = {"match_id": match_id, "dievaluasi": False}
    if indikator:
        hasil_indikator.update(indikator)
    hasil_indikator["pemicu_keras"] = pemicu
    if isinstance(alasan, str):
        alasan = [alasan]
    return {
        "vonis": VONIS_KUNING,
        "alasan": list(alasan),
        "indikator": hasil_indikator,
    }


def nilai_vonis(
    analysis: dict, hasil_stress: dict | None = None, cfg: dict | None = None
) -> dict:
    """Vonis satu laga NBA dari data (HIJAU / MENENGAH_HIJAU / KUNING).

    ``analysis``: dict nba_analysis, atau satu entri match artefak
    slate (dibuka otomatis bila membawa kunci ``nba_analysis``).
    ``hasil_stress``: hasil ``engine.stress.skenario_panas`` laga itu
    (opsional — bila diberikan dan memuat garis Asuransi, P banjir /
    setan diambil dari sana; bila None / tidak memuat garis itu,
    dihitung langsung dari CDF). ``cfg``: dict playstyle (default:
    dibaca dari config/playstyle.yaml).

    Mengembalikan ``{"vonis", "alasan", "indikator"}`` — "vonis" salah
    satu dari "hijau" / "menengah_hijau" / "kuning"; "alasan" daftar
    kalimat Bahasa Indonesia (satu per demerit/pemicu, plus catatan
    indikator sekunder yang tidak dinilai); "indikator" dict angka
    mentah + ambang + demerit + ``dievaluasi`` (False bila vonis
    KUNING-karena-data — komposer hanya mengeluarkan laga KUNING yang
    dievaluasi, lihat docstring modul). Aturan persis + ambang: lihat
    docstring modul dan section ``vonis:`` di playstyle.yaml.
    Config rusak -> ConfigError. analysis bukan dict -> ValueError.
    """
    analysis = _buka_analysis(analysis)
    cfg = _muat_cfg(cfg)
    match_id = analysis.get("match_id")

    # Ambang: baru dari section vonis, sisanya dipakai ulang (tidak
    # diduplikasi — satu sumber kebenaran per angka).
    edge_hijau = _ambang(cfg, "vonis", "edge_hijau_pct") / 100.0
    p_setan_hijau = _ambang(cfg, "vonis", "p_setan_hijau")
    gap_kecil = _ambang(cfg, "vonis", "gap_kecil_pct") / 100.0
    ekor_jauh = _ambang(cfg, "vonis", "ekor_jauh_points")
    ekor_harga_rendah = _ambang(cfg, "vonis", "ekor_harga_rendah_cents")
    total_tinggi = _ambang(cfg, "vonis", "total_tinggi_points")
    max_demerit = _ambang(cfg, "vonis", "max_demerit_menengah")
    veto_garis = _ambang(cfg, "vonis", "veto_total_tinggi_points")
    veto_pace = _ambang(cfg, "vonis", "veto_pace_tinggi")
    target_ins = _ambang(cfg, "tickets", "insurance", "min_leg_prob")
    ambang_ot = _ambang(cfg, "ot_seleksi", "skip_ot_prob")
    gap_besar = _ambang(cfg, "anomaly", "model_vs_market_points") / 100.0
    min_volume = _ambang(cfg, "polymarket_ladder", "min_volume_usd")
    if not 0.0 <= p_setan_hijau <= 1.0:
        raise config_mod.ConfigError(
            f"playstyle.yaml vonis.p_setan_hijau di luar 0-1: {p_setan_hijau}"
        )
    if max_demerit < 0 or max_demerit != int(max_demerit):
        raise config_mod.ConfigError(
            "playstyle.yaml vonis.max_demerit_menengah harus bilangan "
            f"bulat >= 0: {max_demerit}"
        )
    max_demerit = int(max_demerit)
    ambang = {
        "edge_hijau_pct": round(edge_hijau * 100.0, 4),
        "p_banjir_target": round(target_ins, 4),
        "p_setan_hijau": round(p_setan_hijau, 4),
        "gap_kecil_pct": round(gap_kecil * 100.0, 4),
        "gap_besar_pct": round(gap_besar * 100.0, 4),
        "ekor_jauh_points": ekor_jauh,
        "ekor_harga_rendah_cents": ekor_harga_rendah,
        "total_tinggi_points": total_tinggi,
        "skip_ot_prob": round(ambang_ot, 4),
        "min_volume_usd": min_volume,
        "max_demerit_menengah": max_demerit,
        "veto_total_tinggi_points": veto_garis,
        "veto_pace_tinggi": veto_pace,
    }

    if analysis.get("format") == "soccer_analysis":
        return _kuning_data(
            match_id,
            PICU_BUKAN_NBA,
            "vonis hanya untuk laga NBA (total Under) — laga bola " "tidak dinilai",
            {"ambang": ambang},
        )

    # --- Veto rim protector (dievaluasi untuk SETIAP laga NBA, juga
    # yang data wajibnya hilang — hasilnya tercatat di indikator dan
    # alasannya ikut bila menyala, supaya laporan tetap menunjukkannya.
    # Bila veto tidak bisa dievaluasi, permainan tetap dinilai sistem
    # demerit — lihat docstring modul, bagian VETO.) ---
    veto = evaluasi_veto(analysis, cfg)
    veto_alasan = list(veto["alasan"]) if veto["menyala"] else []

    # --- Data wajib: CDF + tangga + jangkar (konteks equilibrium). ---
    ktx = equilibrium_mod.siapkan_konteks(analysis, "insurance", cfg)
    if not ktx.get("ok"):
        return _kuning_data(
            match_id,
            PICU_DATA_TIDAK_CUKUP,
            [
                f"data_tidak_cukup: {ktx.get('alasan') or 'konteks tidak siap'}",
                *veto_alasan,
            ],
            {"ambang": ambang, "veto": veto},
        )
    # --- Data wajib: ot_probability. ---
    ot_prob = skip_awal_mod.baca_ot_probability(analysis)
    if ot_prob is None:
        return _kuning_data(
            match_id,
            PICU_DATA_TIDAK_CUKUP,
            [
                "data_tidak_cukup: ot_probability tidak ada di artefak "
                "(risiko overtime tidak bisa dinilai)",
                *veto_alasan,
            ],
            {"ambang": ambang, "veto": veto},
        )

    # --- Equilibrium kedua tiket + garis acuan + tahan-banjir. ---
    eq_ins = equilibrium_mod.cari_equilibrium(analysis, "insurance", cfg, ktx=ktx)
    eq_main = equilibrium_mod.cari_equilibrium(analysis, "main", cfg)
    acuan = equilibrium_mod.cari_garis_acuan(analysis, cfg, ktx=ktx)
    tahan = _garis_tahan_banjir_nonthin(ktx, target_ins, min_volume)
    ada_tahan_nonthin = tahan["entri"] is not None

    # --- Kaki artefak bergaris + berharga (sumber edge + garis). ---
    kaki_artifak: dict[str, dict | None] = {"insurance": None, "main": None}
    edge_kandidat: list[tuple[float, str]] = []
    for leg in analysis.get("legs") or []:
        if not isinstance(leg, dict):
            continue
        tiket = leg.get("ticket")
        if tiket not in kaki_artifak:
            continue
        garis = _angka(leg.get("line"))
        harga = _harga_venue(leg)
        p_final = _angka(leg.get("p_final"))
        if garis is None or harga is None or not 0.0 < harga < 100.0:
            continue
        if kaki_artifak[tiket] is None:
            kaki_artifak[tiket] = {"line": garis, "harga": harga, "leg": leg}
        if p_final is not None:
            nama_tiket = "Asuransi" if tiket == "insurance" else "Utama"
            edge_kandidat.append(
                (p_final - harga / 100.0, f"kaki artefak {nama_tiket} U{garis:g}")
            )
    for eq, nama in ((eq_ins, "Asuransi"), (eq_main, "Utama")):
        if eq.get("ada") and _angka(eq.get("edge")) is not None:
            edge_kandidat.append(
                (float(eq["edge"]), f"equilibrium {nama} U{float(eq['garis']):g}")
            )

    # --- Pilih garis Asuransi (prioritas a–f, lihat docstring). ---
    garis_asuransi: float | None = None
    sumber_garis: str | None = None
    if eq_ins.get("ada"):
        garis_asuransi = float(eq_ins["garis"])
        sumber_garis = "equilibrium Asuransi"
    elif tahan["entri"] is not None:
        garis_asuransi = float(tahan["garis"])
        sumber_garis = "garis tahan-banjir tidak-tipis"
    elif kaki_artifak["insurance"] is not None:
        garis_asuransi = float(kaki_artifak["insurance"]["line"])
        sumber_garis = "kaki Asuransi artefak"
    elif eq_main.get("ada"):
        garis_asuransi = float(eq_main["garis"])
        sumber_garis = "equilibrium Utama"
    elif kaki_artifak["main"] is not None:
        garis_asuransi = float(kaki_artifak["main"]["line"])
        sumber_garis = "kaki Utama artefak"
    elif acuan.get("dihitung"):
        garis_asuransi = float(acuan["garis"])
        sumber_garis = "garis acuan"
    if garis_asuransi is None:
        return _kuning_data(
            match_id,
            PICU_DATA_TIDAK_CUKUP,
            [
                "data_tidak_cukup: tidak ada garis yang bisa dinilai "
                "(tanpa equilibrium, tanpa kaki bergaris, tanpa garis acuan)",
                *veto_alasan,
            ],
            {"ambang": ambang, "veto": veto},
        )

    # Harga + volume di garis Asuransi: tangga dulu (paling otoritatif
    # untuk volume/thin), kaki artefak sebagai cadangan.
    entri_tangga = _entri_tangga(ktx["tangga"], garis_asuransi)
    harga_asuransi = _harga_venue(entri_tangga) if entri_tangga else None
    leg_pada_garis = None
    for info in kaki_artifak.values():
        if info is not None and abs(info["line"] - garis_asuransi) < 1e-9:
            leg_pada_garis = info["leg"]
            break
    if harga_asuransi is None and leg_pada_garis is not None:
        harga_asuransi = _harga_venue(leg_pada_garis)
    if harga_asuransi is None or not 0.0 < harga_asuransi < 100.0:
        return _kuning_data(
            match_id,
            PICU_DATA_TIDAK_CUKUP,
            [
                f"data_tidak_cukup: garis Asuransi U{garis_asuransi:g} "
                "tidak punya harga venue yang valid",
                *veto_alasan,
            ],
            {"ambang": ambang, "veto": veto},
        )
    thin_asuransi = _tipis(entri_tangga, min_volume)
    volume_asuransi = _angka(entri_tangga.get("volume_usd")) if entri_tangga else None
    if thin_asuransi is None and leg_pada_garis is not None:
        thin_asuransi = _tipis(leg_pada_garis, min_volume)
        if volume_asuransi is None:
            volume_asuransi = _angka(leg_pada_garis.get("volume_usd"))

    # --- Peluang di garis Asuransi (CDF + jangkar pasar). ---
    p_model, p_market, p_final = equilibrium_mod.peluang_pada_garis(ktx, garis_asuransi)
    p_normal = stress_mod.p_under_digeser(ktx["cdf"], garis_asuransi, 0.0)
    p_banjir, p_setan, nama_banjir = _p_dari_stress(hasil_stress, garis_asuransi)
    stress_dipakai = p_banjir is not None or p_setan is not None
    if p_banjir is None:
        p_banjir = stress_mod.p_under_digeser(
            ktx["cdf"], garis_asuransi, ktx["geser_banjir_terburuk"]
        )
    if p_setan is None:
        p_setan = stress_mod.p_under_digeser(
            ktx["cdf"], garis_asuransi, ktx["geser_setan"]
        )
    if not isinstance(nama_banjir, str):
        nama_banjir = ktx["banjir_terburuk"]
    edge_garis = p_final - harga_asuransi / 100.0
    edge_kandidat.append((edge_garis, f"garis Asuransi U{garis_asuransi:g}"))
    # edge_kandidat tidak mungkin kosong di sini: edge garis Asuransi
    # selalu bisa dihitung (p_final dari CDF + jangkar, harga sudah
    # divalidasi di atas) — sumber edge wajib terpenuhi begitu garis
    # Asuransi terpilih.
    edge_terbaik, edge_sumber = max(edge_kandidat, key=lambda pas: pas[0])
    gap = p_model - p_market if p_market is not None else None

    # --- Data sekunder: garis bandar (ekor gemuk + level total). ---
    market = (
        analysis.get("market") if isinstance(analysis.get("market"), dict) else None
    )
    garis_market = _angka(market.get("main_total_line")) if market else None
    tidak_dinilai: list[str] = []
    if garis_market is None:
        tidak_dinilai.extend(["ekor_gemuk", "total_tinggi"])
        jarak = None
        ekor_gemuk = None
        total_tinggi_kena = None
    else:
        jarak = garis_asuransi - garis_market
        ekor_gemuk = jarak >= ekor_jauh and harga_asuransi <= ekor_harga_rendah
        total_tinggi_kena = garis_market >= total_tinggi
    if gap is None:
        tidak_dinilai.append("gap_model_pasar")
    if not veto["dievaluasi"]:
        tidak_dinilai.append("veto_rim_protector")

    # --- Demerit + pemicu keras (urutan tetap D1–D8). ---
    demerit: list[str] = []
    alasan: list[str] = []
    pemicu_keras: str | None = None
    if veto["menyala"]:
        pemicu_keras = PICU_VETO_RIM_PROTECTOR
        alasan.extend(veto_alasan)
    if ot_prob >= ambang_ot:
        pemicu_keras = PICU_OT_TINGGI
        alasan.append(
            f"potensi overtime tinggi: peluang OT sim {ot_prob * 100:.2f}% "
            f">= ambang {ambang_ot * 100:.1f}% — laga praktis imbang, "
            "babak tambahan menambah ~20 poin dan membunuh kaki Under"
        )
    if edge_terbaik <= 0.0:
        if pemicu_keras is None:
            pemicu_keras = PICU_EDGE_TIDAK_POSITIF
        alasan.append(
            "tidak ada nilai di laga ini: edge kaki terbaik "
            f"{edge_terbaik * 100:+.1f}% (tidak positif) — model tidak "
            "menemukan keunggulan atas harga di garis mana pun"
        )
    if edge_terbaik < edge_hijau:
        demerit.append(DEMERIT_EDGE_KECIL)
        alasan.append(
            f"edge kecil: kaki terbaik hanya {edge_terbaik * 100:+.1f}% "
            f"({edge_sumber}; ambang {edge_hijau * 100:.1f}%)"
        )
    if p_banjir < target_ins and not ada_tahan_nonthin:
        demerit.append(DEMERIT_BANJIR_LEMAH)
        alasan.append(
            "rapuh banjir: peluang Under di banjir terburuk "
            f"{p_banjir * 100:.1f}% di garis U{garis_asuransi:g} "
            f"(ambang {target_ins * 100:.0f}%) dan tidak ada garis "
            "tidak-tipis yang tahan banjir"
        )
    if p_setan < p_setan_hijau:
        demerit.append(DEMERIT_SETAN_LEMAH)
        alasan.append(
            "rapuh setan: peluang Under di deviasi maksimal "
            f"{p_setan * 100:.1f}% di garis U{garis_asuransi:g} "
            f"(ambang {p_setan_hijau * 100:.0f}%)"
        )
    if thin_asuransi is True:
        demerit.append(DEMERIT_VOLUME_TIPIS)
        teks_volume = (
            f"hanya ${volume_asuransi:,.2f}"
            if volume_asuransi is not None
            else "tidak tercatat angkanya"
        )
        alasan.append(
            f"volume tipis: garis U{garis_asuransi:g} {teks_volume} "
            f"(ambang ${min_volume:,.2f}) — garis yang tidak bisa "
            "dibeli harganya kurang bisa dipercaya"
        )
    elif thin_asuransi is None:
        demerit.append(DEMERIT_VOLUME_TIDAK_DIKETAHUI)
        alasan.append(
            f"volume tidak diketahui: garis U{garis_asuransi:g} tidak "
            "membawa flag thin maupun angka volume — tidak bisa "
            "dibuktikan bisa dibeli"
        )
    if gap is not None and gap < gap_kecil:
        demerit.append(DEMERIT_GAP_KECIL)
        alasan.append(
            "model hampir setuju dengan bandar: gap model-vs-pasar "
            f"hanya {gap * 100:+.1f} poin di garis U{garis_asuransi:g} "
            f"(ambang {gap_kecil * 100:.1f}) — tidak ada keunggulan "
            "yang jelas atas pasar"
        )
    elif gap is not None and gap > gap_besar:
        demerit.append(DEMERIT_GAP_BESAR)
        alasan.append(
            "model jauh dari pasar: gap model-vs-pasar "
            f"{gap * 100:+.1f} poin di garis U{garis_asuransi:g} "
            f"(ambang {gap_besar * 100:.1f}) — model dan pasar tidak "
            "sepakat, perlu dicek kenapa beda"
        )
    if ekor_gemuk is True:
        demerit.append(DEMERIT_EKOR_GEMUK)
        alasan.append(
            "ekor gemuk: garis U"
            f"{garis_asuransi:g} jauh {jarak:.1f} poin di atas total "
            f"pasar {garis_market:g} tapi harganya cuma "
            f"{harga_asuransi:g}¢ — pasar sendiri bilang total bisa "
            "meledak jauh"
        )
    if total_tinggi_kena is True:
        demerit.append(DEMERIT_TOTAL_TINGGI)
        alasan.append(
            f"total tinggi: garis bandar {garis_market:g} "
            f"(ambang {total_tinggi:g}) — laga skor besar, variasinya "
            "lebih besar"
        )

    # --- Vonis. ---
    if pemicu_keras is not None:
        vonis = VONIS_KUNING
    elif not demerit:
        vonis = VONIS_HIJAU
    elif len(demerit) <= max_demerit:
        vonis = VONIS_MENENGAH_HIJAU
    else:
        vonis = VONIS_KUNING

    if vonis == VONIS_HIJAU:
        teks_volume = (
            f"${volume_asuransi:,.2f}" if volume_asuransi is not None else "tidak tipis"
        )
        alasan = [
            "semua indikator sehat: edge kaki terbaik "
            f"{edge_terbaik * 100:+.1f}% ({edge_sumber}), peluang Under "
            f"di banjir terburuk {p_banjir * 100:.1f}% dan di deviasi "
            f"maksimal {p_setan * 100:.1f}% di garis U{garis_asuransi:g}, "
            f"volume {teks_volume}, gap model-vs-pasar "
            + (f"{gap * 100:+.1f} poin" if gap is not None else "tidak dinilai")
            + f", peluang OT {ot_prob * 100:.2f}%"
            + (", veto rim protector tidak menyala" if veto["dievaluasi"] else "")
        ]
    if tidak_dinilai:
        alasan.append(
            "tidak dinilai (data sekunder hilang): "
            + ", ".join(tidak_dinilai)
            + " — vonis dihitung dari indikator lain."
        )

    indikator = {
        "match_id": match_id,
        "dievaluasi": True,
        "pemicu_keras": pemicu_keras,
        "demerit": demerit,
        "n_demerit": len(demerit),
        "tidak_dinilai": tidak_dinilai,
        "garis_asuransi": {
            "line": garis_asuransi,
            "sumber": sumber_garis,
            "harga_venue_cents": harga_asuransi,
            "thin": thin_asuransi,
            "volume_usd": (
                round(volume_asuransi, 2) if volume_asuransi is not None else None
            ),
        },
        "garis_acuan": {
            "dihitung": bool(acuan.get("dihitung")),
            "alasan": acuan.get("alasan"),
            "garis": acuan.get("garis"),
            "harga_venue_cents": acuan.get("harga_venue_cents"),
            "thin": acuan.get("thin"),
            "volume_usd": acuan.get("volume_usd"),
            "p_normal": acuan.get("p_normal"),
            "p_setan": acuan.get("p_setan"),
            "flag_setan": acuan.get("flag_setan"),
            "p_final": acuan.get("p_final"),
            "edge": acuan.get("edge"),
        },
        "garis_tahan_banjir_nonthin": {
            "line": tahan["garis"],
            "harga_venue_cents": tahan["harga_venue_cents"],
            "thin": tahan["thin"],
            "volume_usd": tahan["volume_usd"],
            "n_tahan_banjir": tahan["n_tahan_banjir"],
            "n_tahan_banjir_nonthin": tahan["n_tahan_banjir_nonthin"],
            "ada": ada_tahan_nonthin,
        },
        "edge_terbaik": round(edge_terbaik, 6),
        "edge_terbaik_sumber": edge_sumber,
        "p_normal": round(p_normal, 6),
        "p_banjir_terburuk": round(p_banjir, 6),
        "banjir_terburuk": nama_banjir,
        "p_setan": round(p_setan, 6),
        "hasil_stress_dipakai": stress_dipakai,
        "p_model": round(p_model, 6),
        "p_market": round(p_market, 6) if p_market is not None else None,
        "p_final": round(p_final, 6),
        "gap_model_pasar": round(gap, 6) if gap is not None else None,
        "ekor_gemuk": ekor_gemuk,
        "jarak_garis_market_points": (round(jarak, 4) if jarak is not None else None),
        "ot_probability": round(ot_prob, 6),
        "total_market": garis_market,
        "veto": veto,
        "ambang": ambang,
    }
    return {"vonis": vonis, "alasan": alasan, "indikator": indikator}
