"""Vonis per laga NBA: HIJAU / MENENGAH_HIJAU / KUNING / TUNGGU_LINEUP.

Latar: tiket nyata user 23 Nov 2026 kalah karena DEN@CHI (total akhir
296, OT, 42 tripoin; median pra-laga 233, garis bandar 236,5). Yang
JUJUR tidak terprediksi adalah banjirnya sendiri — yang TERDETEKSI
adalah RAPUHNYA. Keputusan user 2026-11-23 12:38 WIB: mesin menghitung
vonis per laga dari indikator-indikator pelajaran Denver. v18 MEROMBAK
sistem vonis (audit Gemini §2.2/§2.7 + jawaban user atas 4 keputusan
v18, DECISIONS.md 2026-11-23 13:57 WIB): demerit dirampingkan, HIJAU
menuntut bukti positif (rem alami), veto menjadi AND, OT menjadi
empiris, dan bintang Questionable menahan laga (TUNGGU_LINEUP).

GARIS ASURANSI (garis rujukan — semua indikator per garis dibaca di
sini, bukan di garis artefak sembarang): garis yang akan dimainkan
mesin untuk Asuransi, prioritas:
  (a) garis equilibrium Asuransi (bila ada);
  (b) garis tahan-banjir TIDAK-TIPIS terendah (bila ada — tahan =
      P banjir 3P >= tickets.insurance.flood_3p_min DAN P banjir FT
      >= tickets.insurance.flood_ft_min, gate v18; tidak-tipis =
      flag thin False — vonis TIDAK membaca min_volume, lihat
      "VOLUME" di bawah);
  (c) garis kaki Asuransi artefak (bila bergaris + berharga);
  (d) garis equilibrium Utama (bila ada);
  (e) garis kaki Utama artefak (bila bergaris + berharga);
  (f) garis acuan (garis tangga termurah dengan P normal >= target
      Asuransi).
Bila tidak satu pun ada -> vonis KUNING data_tidak_cukup.

DEMERIT v18 (6 — tiap indikator lemah = 1 demerit):
  (a) tail_fragility — kerapuhan ekor GABUNGAN (1 poin, bukan 2):
      P(Under) di banjir 3P pada garis Asuransi <
      vonis.tail_fragility.p_flood_3p_below (0,72) ATAU di banjir FT
      < vonis.tail_fragility.p_flood_ft_below (0,67). Banjir + setan
      mengukur hal yang sama (menggeser CDF yang sama) — v17
      menghitung ganda. Setan (umum maupun per pemain) TIDAK lagi
      memberi demerit: ia flag diagnostik (P setan tetap dicatat di
      indikator sebagai info).
  (b) total_tinggi — garis bandar >= vonis.total_tinggi_points
      (235,0, tetap). Sekunder (butuh main_total_line).
  (c) gap_besar — gap model-vs-pasar (p_model - p_market) pada garis
      Asuransi > anomaly.model_vs_market_points (8,0 poin, dipakai
      ulang) HANYA bila TANPA cedera baru terverifikasi. "Cedera baru
      terverifikasi" disederhanakan (keputusan desain v18, menunggu
      keberatan): ada entri OUT terkonfirmasi (>= 2 sumber) yang
      melibatkan pemain berdampak (BPM >= +2,0 atau USG >= 24% —
      ambang dipakai ulang dari vonis.tunggu_lineup; jalur USG
      dikualifikasi seperti timing gate — rotasi + tidak
      net-negatif). Bila ada ->
      flag investigasi saja (indikator.investigasi), BUKAN demerit.
      PENYEDERHANAAN JUJUR: artefak tidak mencatat apakah pasar
      sudah menyerap kabar cedera itu ("baru" vs "lama") — vonis
      menganggap cedera berdampak yang tercatat di artefak sebagai
      penjelasan yang sah atas gap besar.
  (d) ekor_gemuk — DIPERKETAT (v17: >= 10 poin DAN <= 85¢): jarak
      garis Asuransi ke total pasar >=
      vonis.ekor_gemuk.min_offset_points (16,0) DAN harga venue <=
      vonis.ekor_gemuk.max_price_cents (80). Sekunder (butuh
      main_total_line).
  (e) foul_tinggi — lingkungan foul tinggi: FTr GABUNGAN >=
      vonis.foul.ftr_p80 (0,308111, FIT). DEFINISI "GABUNGAN":
      rata-rata aritmetik FTr musim kedua tim (FTr = FTA/FGA per
      tim, dari inputs.{home,away}.stats_season.ftr). Rata-rata
      dipakai karena kedua tim sama-sama menyumbang lemparan bebas
      ke total laga; maks menghukum satu tim pelanggar, jumlah
      menggandakan skala. Bila FTr salah satu tim hilang -> tidak
      dinilai (rata-rata tidak terdefinisi).
  (f) spread_tipis — |spread| <= vonis.spread_tipis_max (3,0).
      Spread = |median margin sim| (engine/ot_empiris.baca_spread).
YANG DIHAPUS dari v17 (alasan di REFERENSI-AUDIT-GEMINI-V18.md):
  - edge_kecil (edge datar menghukum kaki harga tinggi secara
    aljabar) + pemicu keras edge_tidak_positif: nilai kini dinilai
    lewat EV di gate per kaki (tickets.*.max_negative_ev_pct),
    bukan di vonis laga. Edge terbaik tetap DICATAT sebagai info.
  - setan_lemah (digabung ke kerapuhan ekor), gap_kecil (menghukum
    kesepakatan dengan pasar justru membuang laga paling bersih),
    volume_tipis / volume_tidak_diketahui (volume pindah ke gate
    eksekusi — lihat "VOLUME").

VOLUME (v18): vonis TIDAK LAGI memakai volume sebagai masukan
vonis dan TIDAK membaca polymarket_ladder.min_volume_usd. Volume
adalah sifat orderbook, bukan cacat laga. Satu-satunya pemakaian
"tipis" yang tersisa adalah pemilihan garis rujukan (b): flag
thin APA ADANYA dari tangga (dihitung penarik tangga di
ingest/polymarket.py) — garis dengan flag thin True tidak dipilih
sebagai garis tahan-banjir rujukan. Vonis tidak menghitung ulang
tipis dari angka volume.

REM ALAMI (5 — bukti positif keamanan; HIJAU butuh >= 1):
  (1) pertahanan_top10 — salah satu tim punya DRtg musim <=
      vonis.rem_alami.drtg_top10_cutoff (112,9, FIT).
  (2) pace_lambat — salah satu tim punya pace musim <=
      vonis.rem_alami.pace_bottom12_cutoff (98,91, FIT). CATATAN
      ARAH: pace lambat = angka pace KECIL — Bottom-12 berarti 12
      tim paling lambat, jadi pace <= cutoff (bukan >=).
  (3) pencetak_utama_out — KEDUA tim kehilangan minimal satu
      pencetak utama OUT terkonfirmasi (status OUT, >= 2 sumber)
      dengan USG >= vonis.rem_alami.usg_scorer_out (0,25). USG dari
      ingest/pemain_usg.py (cache satu-proses); bila USG tidak
      tersedia, rem ini tidak_dievaluasi (BPM TIDAK dipakai sebagai
      pengganti — USG dan BPM mengukur hal berbeda). Jalur USG
      dikualifikasi (_lolos_jalur_usg): pemain harus rotasi
      (mp >= 10,0) dan tidak net-negatif (BPM >= 0,0 bila
      diketahui) — definisi "pemain berdampak via USG" yang sama
      dengan timing gate + aturan gap besar.
  (4) paint_utuh_blowout_atau_ftr_rendah — (tidak ada rim protector
      OUT di kedua tim DAN |spread| >=
      vonis.rem_alami.blowout_spread (8,5)) ATAU (FTr kedua tim <
      vonis.foul.ftr_p50 (0,274398, FIT)). "Rim protector OUT" di
      sini memakai status OUT APA PUN jumlah sumbernya (klaim
      positif "paint utuh" harus terbukti — OUT 1 sumber saja sudah
      meragukannya; berbeda dengan veto yang menuntut 2 sumber
      karena veto adalah klaim keras). Bila data cedera tidak ada,
      cabang blowout tidak_dievaluasi; bila FTr hilang, cabang FTr
      tidak_dievaluasi; rem tidak_dievaluasi hanya bila KEDUA
      cabang tidak_dievaluasi.
  (5) selaras_pasar — |median model - total pasar| <=
      vonis.rem_alami.market_align_max_gap (5,0) DAN total pasar <=
      vonis.rem_alami.market_align_max_total (228,0).
  Tiap rem dicatat (terpenuhi / gagal / tidak_dievaluasi) di
  indikator.rem_alami. Bila data rem tidak tersedia (artefak lama),
  rem itu "tidak_dievaluasi" (bukan gagal).

KOMBINASI:
  - pemicu keras -> KUNING: veto_rim_protector, ot_tinggi (OT
    EMPIRIS >= ot_seleksi.hard_skip_ot_prob — dengan rumus v18
    tidak pernah menyala, lihat engine/ot_empiris.py),
    data_tidak_cukup.
  - 0 veto + <= vonis.hijau_max_demerits (1) demerit + >= 1 rem
    alami terpenuhi -> HIJAU.
  - <= vonis.menengah_max_demerits (3) demerit (termasuk 0–1
    demerit TANPA rem alami) -> MENENGAH_HIJAU.
  - >= 4 demerit -> KUNING.
  Prinsip user (keputusan #3): mesin mencari kaki yang MASUK AKAL,
  bukan yang paling ketat — KUNING = tidak masuk akal (seperti
  Denver), bukan "tidak sempurna".

TIMING GATE (TUNGGU_LINEUP): bila ada bintang Questionable (status
QUESTIONABLE dengan USG >= vonis.tunggu_lineup.usg_bintang (0,24)
ATAU BPM >= vonis.tunggu_lineup.bpm_bintang (+2,0)), vonis adalah
"tunggu_lineup" — laga ditahan sampai injury report final ~30
menit sebelum tip-off (bukan HIJAU/KUNING). Jalur USG
dikualifikasi (_lolos_jalur_usg): pemain harus rotasi (mp >=
mp_min_rotasi 10,0) dan tidak net-negatif (BPM >=
bpm_min_jalur_usg 0,0 bila diketahui) — tanpa kualifikasi ini,
pemain garbage-time (RayJ Dennis USG 26,7% BPM -3,2) memblokir
laga. Precedence di
nilai_vonis: veto (KUNING) > tunggu_lineup > demerit — veto yang
sudah menyala tidak bisa diselamatkan kabar lineup. Komposer
(worker B) menangani nilai vonis "tunggu_lineup". USG dari
ingest/pemain_usg.py (cache satu-proses); bila fetch USG gagal ->
fallback BPM saja + dicatat. Cek hanya memakai data cedera +
pemain artefak (tanpa CDF/tangga) — laga TUNGGU_LINEUP tidak butuh
tangga untuk diputuskan.

VETO RIM PROTECTOR v18 (logika AND — keputusan user #4, 2026-11-23
13:59 WIB): rim protector OUT terkonfirmasi + garis pasar >=
vonis.veto.total_tinggi_points (232,0) DAN pace tercepat >=
vonis.veto.pace_tinggi (100,5). Kedua ambang INITIAL (dipasang
dari 2 titik data — DEN 236,5/103,22 vs OKC 231,5/102,19).
vonis.veto.logic "AND" (nilai "OR" didukung kode untuk
reversibilitas satu baris config bila user membatalkan). Bila
HANYA satu kondisi lingkungan menyala, veto TIDAK menyala tapi
hasil veto mencatat "peringatan_parsial": true + kondisi mana yang
menyala (worker B memakai ini untuk +3 bantalan). Veto menyala ->
blokir KEDUA tiket (vonis KUNING). Definisi rim protector v18:
filter posisi C/PF/F-C/C-F (dari BBRef — stats.nba.com tidak
menyediakan posisi), min 18 menit, BLK >= 1,0, maks 2/tim
(config/rim_protector_2026-27.json, diturunkan
scripts/fetch_rim_protector.py).

DATA WAJIB vs SEKUNDER (fail-closed):
  - WAJIB (hilang -> KUNING data_tidak_cukup): CDF total
    (simulation.markets), tangga Under (market.totals), jangkar pasar
    (kaki artefak bergaris + p_market — sama seperti equilibrium),
    spread (|median margin sim| — memberi makan OT empiris, demerit
    spread tipis, DAN rem blowout; tanpa spread, vonis tidak lengkap
    secara material), dan satu garis Asuransi yang bisa dipilih +
    harganya. ot_probability SIM bukan lagi wajib — hanya info.
    PENGECUALIAN KOMPOSER (didokumentasikan, menunggu keberatan):
    komposer hanya mengeluarkan laga KUNING yang DIEVALUASI
    (indikator.dievaluasi True); laga KUNING-karena-data tetap
    lewat ke gate per kaki (yang sudah fail-closed sendiri).
  - SEKUNDER (hilang -> tidak dinilai, dicatat, TANPA demerit):
    main_total_line (total_tinggi, ekor_gemuk, selaras_pasar);
    FTr tim (foul_tinggi, cabang FTr rem 4); DRtg/pace tim (rem 1/2);
    data cedera (rem 3, gap_besar-bersyarat, veto); USG (rem 3,
    gap_besar-bersyarat — fallback BPM).
  - Laga bola (format soccer_analysis) -> KUNING "bukan NBA"
    (dievaluasi False) — vonis hanya untuk total Under NBA.

HASIL_STRESS (argumen opsional): bila diberikan dan memuat entri kaki
pada garis Asuransi (dicocokkan per GARIS saja), P banjir 3P/FT +
P setan diambil dari sana supaya angkanya persis sama dengan gate
komposer; bila tidak ada entri yang cocok atau argumen None,
dihitung langsung dari CDF (engine/stress.p_under_digeser).
Tidak pernah raise karena hasil_stress berbentuk aneh.

Modul ini MURNI HITUNG kecuali SATU pengecualian v18: USG pemain
diambil dari ingest/pemain_usg.py (cache satu-proses + cache disk
10 menit; HANYA bila ada pemain Questionable/OUT yang perlu
diperiksa USG-nya — laga tanpa pemain seperti itu tidak pernah
fetch). Tanpa Odds API. Satu-satunya I/O lain adalah baca config
bila argumen cfg None + baca file data rim protector CHECK-IN
(bila file hilang/rusak, veto tidak dievaluasi — bukan crash).
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

import config as config_mod
from engine import equilibrium as equilibrium_mod
from engine import ot_empiris as ot_empiris_mod
from engine import stress as stress_mod
from ingest import pemain_usg as pemain_usg_mod

# Nilai vonis (kontrak API — dipakai worker lain, jangan diubah).
VONIS_HIJAU = "hijau"
VONIS_MENENGAH_HIJAU = "menengah_hijau"
VONIS_KUNING = "kuning"
VONIS_TUNGGU_LINEUP = "tunggu_lineup"

# Token demerit v18 (stabil untuk laporan + JSON ukur).
DEMERIT_TAIL_FRAGILITY = "tail_fragility"
DEMERIT_TOTAL_TINGGI = "total_tinggi"
DEMERIT_GAP_BESAR = "gap_besar"
DEMERIT_EKOR_GEMUK = "ekor_gemuk"
DEMERIT_FOUL_TINGGI = "foul_tinggi"
DEMERIT_SPREAD_TIPIS = "spread_tipis"

# Token rem alami (stabil untuk laporan + JSON ukur).
REM_PERTAHANAN_TOP10 = "pertahanan_top10"
REM_PACE_LAMBAT = "pace_lambat"
REM_PENCETAK_UTAMA_OUT = "pencetak_utama_out"
REM_PAINT_UTUH_BLOWOUT_ATAU_FTR_RENDAH = "paint_utuh_blowout_atau_ftr_rendah"
REM_SELARAS_PASAR = "selaras_pasar"
REM_SEMUA = (
    REM_PERTAHANAN_TOP10,
    REM_PACE_LAMBAT,
    REM_PENCETAK_UTAMA_OUT,
    REM_PAINT_UTUH_BLOWOUT_ATAU_FTR_RENDAH,
    REM_SELARAS_PASAR,
)

# Token pemicu keras (stabil untuk laporan + JSON ukur).
PICU_DATA_TIDAK_CUKUP = "data_tidak_cukup"
PICU_OT_TINGGI = "ot_tinggi"
PICU_VETO_RIM_PROTECTOR = "veto_rim_protector"
PICU_BUKAN_NBA = "bukan_nba"

# Pemetaan rim protector (CHECK-IN di repo; ditulis ulang oleh
# scripts/fetch_rim_protector.py). Jalur relatif terhadap root repo.
PEMETAAN_RIM_PROTECTOR = "config/rim_protector_2026-27.json"

# Musim default bila game_date artefak tidak bisa dibaca (dipakai
# tarikan USG; rim protector juga terpaku musim ini).
MUSIM_DEFAULT = "2026-27"


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


def _tipis_flag(entri: dict | None) -> bool | None:
    """Flag thin satu garis tangga/kaki, apa adanya (True/False/None).

    v18: vonis TIDAK menghitung ulang tipis dari angka volume
    (tidak membaca polymarket_ladder.min_volume_usd) — flag thin
    dihitung penarik tangga (ingest/polymarket.py) dan hanya dipakai
    di sini untuk PEMILIHAN garis rujukan, bukan vonis.
    """
    if not isinstance(entri, dict):
        return None
    flag = entri.get("thin")
    return flag if isinstance(flag, bool) else None


def _entri_tangga(tangga: list[dict], garis: float) -> dict | None:
    """Entri tangga Under pada satu garis (toleransi 1e-9), atau None."""
    for entri in tangga:
        garis_entri = _angka(entri.get("line"))
        if garis_entri is not None and abs(garis_entri - garis) < 1e-9:
            return entri
    return None


def _garis_tahan_banjir_nonthin(
    ktx: dict, flood_3p_min: float, flood_ft_min: float
) -> dict:
    """Garis tahan-banjir (gate v18) tidak-tipis terendah + hitungan.

    Tahan = P banjir 3P >= flood_3p_min DAN P banjir FT >=
    flood_ft_min (gate v18, tickets.insurance). Tidak-tipis = flag
    thin False (flag None TIDAK dihitung tidak-tipis — garis tahan
    yang tidak terbukti bisa dibeli bukan garis yang bisa
    menyelamatkan Asuransi). Mengembalikan {"entri", "garis",
    "harga_venue_cents", "thin", "volume_usd", "n_tahan_banjir",
    "n_tahan_banjir_nonthin"} — "entri" None bila tidak ada garis
    tidak-tipis yang tahan banjir.
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
    geser_3p = ktx["geser_banjir_3p"]
    geser_ft = ktx["geser_banjir_ft"]
    for entri in ktx["tangga"]:
        garis = float(entri["line"])
        p_3p = stress_mod.p_under_digeser(ktx["cdf"], garis, geser_3p)
        p_ft = stress_mod.p_under_digeser(ktx["cdf"], garis, geser_ft)
        if p_3p < flood_3p_min or p_ft < flood_ft_min:
            continue
        hasil["n_tahan_banjir"] += 1
        if _tipis_flag(entri) is not False:
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
) -> tuple[float | None, float | None, float | None, str | None]:
    """(P banjir 3P, P banjir FT, P setan, nama banjir terburuk) dari hasil_stress.

    Dicocokkan per GARIS saja (P Under per skenario hanya bergantung
    pada garis, bukan tiket). (None, None, None, None) bila tidak ada
    entri yang cocok / tidak bisa dibaca — pemanggil menghitung
    langsung dari CDF. Tidak pernah raise.
    """
    if not isinstance(hasil_stress, dict):
        return None, None, None, None
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
                return None, None, None, None
            return (
                _angka(p_under.get("banjir_3p")),
                _angka(p_under.get("banjir_ft")),
                _angka(p_under.get("setan")),
                banjir_terburuk if isinstance(banjir_terburuk, str) else None,
            )
    except (AttributeError, TypeError, ValueError):
        return None, None, None, None
    return None, None, None, None


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


def _stats_tim(analysis: dict) -> dict[str, dict]:
    """stats_season per sisi ({"away": {...}, "home": {...}}; {} bila hilang)."""
    inputs = analysis.get("inputs") if isinstance(analysis.get("inputs"), dict) else {}
    hasil: dict[str, dict] = {}
    for sisi in ("away", "home"):
        blok = inputs.get(sisi) if isinstance(inputs.get(sisi), dict) else {}
        musim = blok.get("stats_season")
        hasil[sisi] = dict(musim) if isinstance(musim, dict) else {}
    return hasil


def _pace_tercepat(analysis: dict) -> tuple[float | None, dict]:
    """Pace musim tertinggi kedua tim + rincian per tim.

    (None, rincian) bila pace kedua tim sama-sama tidak ada.
    """
    rincian: dict[str, float | None] = {}
    for sisi, musim in _stats_tim(analysis).items():
        rincian[sisi] = _angka(musim.get("pace"))
    nilai = [p for p in rincian.values() if p is not None]
    return (max(nilai) if nilai else None), rincian


def _entri_cedera(analysis: dict) -> list[dict] | None:
    """Daftar entri cedera artefak (None bila injuries.entries tidak ada)."""
    cedera = analysis.get("injuries")
    if not isinstance(cedera, dict) or not isinstance(cedera.get("entries"), list):
        return None
    return [e for e in cedera["entries"] if isinstance(e, dict)]


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


def _peta_mp(analysis: dict) -> dict[str, float]:
    """Menit per laga pemain artefak ({nama_ternormalisasi: mp}).

    Dari inputs.away/home.players (field "mp_per_game"). Pemain
    tanpa menit valid tidak masuk peta.
    """
    inputs = analysis.get("inputs") if isinstance(analysis.get("inputs"), dict) else {}
    peta: dict[str, float] = {}
    for sisi in ("away", "home"):
        blok = inputs.get(sisi) if isinstance(inputs.get(sisi), dict) else {}
        pemain = blok.get("players") if isinstance(blok.get("players"), list) else []
        for entri in pemain:
            if not isinstance(entri, dict):
                continue
            nama = _normalisasi_nama(entri.get("player"))
            mp = _angka(entri.get("mp_per_game"))
            if nama and mp is not None:
                peta[nama] = mp
    return peta


def _ambang_dampak_usg(cfg: dict) -> tuple[float, float]:
    """Kualifikasi jalur USG -> (mp_min_rotasi, bpm_min_jalur_usg).

    Dibaca dari vonis.tunggu_lineup (satu definisi "pemain
    berdampak via USG" untuk timing gate + rem alami (3) + aturan
    gap besar). ConfigError bila kunci hilang/tidak valid.
    """
    mp_min = _ambang(cfg, "vonis", "tunggu_lineup", "mp_min_rotasi")
    bpm_min = _ambang(cfg, "vonis", "tunggu_lineup", "bpm_min_jalur_usg")
    if mp_min < 0:
        raise config_mod.ConfigError(
            "playstyle.yaml vonis.tunggu_lineup.mp_min_rotasi harus >= 0: "
            f"{mp_min!r}"
        )
    return mp_min, bpm_min


def _lolos_jalur_usg(
    usg: float | None,
    bpm: float | None,
    mp: float | None,
    ambang_usg: float,
    mp_min: float,
    bpm_min: float,
) -> tuple[bool, str | None]:
    """Apakah pemain lolos sebagai "berdampak" lewat jalur USG?

    Mengembalikan (lolos, alasan_tolak). USG di bawah ambang /
    tidak ada -> (False, None) — bukan kandidat USG sama sekali.
    mp tidak ada -> (False, "mp_tidak_ada"): USG tanpa menit tidak
    bisa ditafsirkan (garbage-time vs rotasi tidak bisa dibedakan).
    mp < mp_min -> (False, "bukan_rotasi"). BPM diketahui dan di
    bawah bpm_min -> (False, "bpm_negatif"): pemain net-negatif
    bukan "pencetak utama"/"bintang" walau USG-nya tinggi. BPM
    tidak diketahui -> lantai dilewati (tidak ada bukti negatif).

    KEPUTUSAN DESAIN (menunggu keberatan — bukti slate 22 Nov):
    USG mentah menangkap pemain pinggiran (RayJ Dennis ATL USG
    26,7% BPM -3,2; Felix Okpara WAS USG 25,0% BPM -6,7 / 1,7
    mnt) — tanpa kualifikasi ini, timing gate memblokir 2 laga
    tambahan karena pemain yang main/tidaknya hampir tidak
    mengubah proyeksi. Tanpa kualifikasi: 6/10 baris
    tunggu_lineup; dengan kualifikasi: 4/10.
    """
    if usg is None or usg < ambang_usg:
        return False, None
    if mp is None:
        return False, "mp_tidak_ada"
    if mp < mp_min:
        return False, "bukan_rotasi"
    if bpm is not None and bpm < bpm_min:
        return False, "bpm_negatif"
    return True, None


def _peta_bpm(analysis: dict) -> dict[str, float]:
    """BPM pemain artefak ({nama_ternormalisasi: bpm}).

    Dari inputs.away/home.players (field "bpm" pasca-shrinkage).
    Pemain tanpa BPM valid tidak masuk peta.
    """
    inputs = analysis.get("inputs") if isinstance(analysis.get("inputs"), dict) else {}
    peta: dict[str, float] = {}
    for sisi in ("away", "home"):
        blok = inputs.get(sisi) if isinstance(inputs.get(sisi), dict) else {}
        pemain = blok.get("players") if isinstance(blok.get("players"), list) else []
        for entri in pemain:
            if not isinstance(entri, dict):
                continue
            nama = _normalisasi_nama(entri.get("player"))
            bpm = _angka(entri.get("bpm"))
            if nama and bpm is not None:
                peta[nama] = bpm
    return peta


def _musim_dari_tanggal(analysis: dict) -> str:
    """Musim NBA ("2026-27") dari game_date artefak (fallback MUSIM_DEFAULT).

    Musim NBA berjalan Oktober–Juni: bulan >= 10 -> musim dimulai
    tahun itu; bulan < 10 -> musim dimulai tahun sebelumnya.
    game_date hilang / tidak bisa diparsing -> MUSIM_DEFAULT.
    """
    tanggal = analysis.get("game_date")
    if isinstance(tanggal, str):
        cocok = re.match(r"^(\d{4})-(\d{2})", tanggal)
        if cocok:
            tahun, bulan = int(cocok.group(1)), int(cocok.group(2))
            if 1 <= bulan <= 12:
                awal = tahun if bulan >= 10 else tahun - 1
                return f"{awal}-{str(awal + 1)[-2:]}"
    return MUSIM_DEFAULT


def _muat_peta_usg(
    analysis: dict, usg_pemain=None
) -> tuple[dict[str, float] | None, str, str | None]:
    """Peta USG ({nama_ternormalisasi: usg_pct pecahan}, sumber, catatan).

    ``usg_pemain`` (suntikan — untuk tes/wiring): dict
    {nama: usg} ATAU list entri {"player", "usg_pct"} — sumber
    "suntik". Bila None: tarik sekali-per-proses via
    ingest/pemain_usg.fetch_pemain_usg_cached (musim dari
    game_date artefak); gagal -> (None, "tidak_tersedia", alasan).
    Fungsi ini SATU-SATUNYA titik fetch USG di modul ini — pemanggil
    lain (rem alami, gap besar) memakai fungsi ini supaya tarikan
    terjadi sekali per proses (cache pemain_usg).
    """
    if usg_pemain is not None:
        peta: dict[str, float] = {}
        if isinstance(usg_pemain, dict):
            for nama, nilai in usg_pemain.items():
                kunci = _normalisasi_nama(nama)
                usg = _angka(nilai)
                if kunci and usg is not None:
                    peta[kunci] = usg
        elif isinstance(usg_pemain, list):
            for entri in usg_pemain:
                if not isinstance(entri, dict):
                    continue
                kunci = _normalisasi_nama(entri.get("player"))
                usg = _angka(entri.get("usg_pct"))
                if kunci and usg is not None:
                    peta[kunci] = usg
        return peta, "suntik", None
    musim = _musim_dari_tanggal(analysis)
    try:
        hasil = pemain_usg_mod.fetch_pemain_usg_cached(season=musim)
    except Exception as exc:  # noqa: BLE001 - fetch gagal -> fallback BPM
        return None, "tidak_tersedia", f"fetch USG gagal: {exc}"
    if not hasil.ok:
        return None, "tidak_tersedia", f"fetch USG gagal: {hasil.error or 'gagal'}"
    peta = {}
    for nama, usg in pemain_usg_mod.peta_usg(hasil.data).items():
        kunci = _normalisasi_nama(nama)
        if kunci:
            peta[kunci] = usg
    sumber = "stats.nba.com"
    if isinstance(hasil.extra, dict) and hasil.extra.get("source_used"):
        sumber = str(hasil.extra["source_used"])
    return peta, sumber, None


def cek_tunggu_lineup(analysis: dict, cfg: dict | None = None, usg_pemain=None) -> dict:
    """Timing gate: apakah laga ini harus TUNGGU_LINEUP?

    ``analysis``: dict nba_analysis (atau entri match — dibuka dulu).
    ``cfg``: dict playstyle (default: dibaca dari file).
    ``usg_pemain`` (opsional): peta USG suntikan {nama: usg} atau
    list entri {"player", "usg_pct"} — untuk tes/wiring; bila None,
    USG ditarik sekali-per-proses (ingest/pemain_usg) HANYA bila ada
    pemain Questionable yang belum lolos lewat BPM.

    Bintang = pemain berstatus QUESTIONABLE dengan USG >=
    vonis.tunggu_lineup.usg_bintang (0,24) ATAU BPM >=
    vonis.tunggu_lineup.bpm_bintang (+2,0). BPM dari inputs pemain
    artefak; USG dari ingest/pemain_usg (bila fetch gagal ->
    fallback BPM saja + dicatat di "usg_catatan"). JALUR USG
    DIKUALIFIKASI (lihat _lolos_jalur_usg): USG tinggi saja tidak
    cukup — pemain harus rotasi (mp >= mp_min_rotasi) dan tidak
    net-negatif (BPM >= bpm_min_jalur_usg bila diketahui), supaya
    pemain garbage-time tidak memblokir laga.

    Mengembalikan {"tunggu", "bintang", "alasan", "dievaluasi",
    "diperiksa", "usg_sumber", "usg_catatan", "ambang"} — "bintang"
    list {"player", "team", "status", "usg", "bpm"} (usg/bpm None
    bila tidak diketahui); "alasan" daftar kalimat Bahasa
    Indonesia; "dievaluasi" False bila data cedera tidak ada
    (tunggu False — bukan bukti aman, dicatat). Tidak pernah raise
    karena data (hanya ConfigError bila ambang config rusak).
    """
    analysis = _buka_analysis(analysis)
    cfg = _muat_cfg(cfg)
    usg_bintang = _ambang(cfg, "vonis", "tunggu_lineup", "usg_bintang")
    bpm_bintang = _ambang(cfg, "vonis", "tunggu_lineup", "bpm_bintang")
    hasil: dict = {
        "tunggu": False,
        "bintang": [],
        "alasan": [],
        "dievaluasi": False,
        "diperiksa": [],
        "usg_sumber": None,
        "usg_catatan": None,
        "ambang": {"usg_bintang": usg_bintang, "bpm_bintang": bpm_bintang},
    }
    entri = _entri_cedera(analysis)
    if entri is None:
        hasil["alasan"] = [
            "timing gate tidak dievaluasi: data ketersediaan "
            "(injuries.entries) tidak ada di artefak"
        ]
        return hasil
    hasil["dievaluasi"] = True
    dipertanyakan = [
        e
        for e in entri
        if isinstance(e.get("status"), str) and e["status"].upper() == "QUESTIONABLE"
    ]
    if not dipertanyakan:
        hasil["alasan"] = ["tidak ada pemain berstatus Questionable"]
        return hasil
    peta_bpm = _peta_bpm(analysis)
    peta_mp = _peta_mp(analysis)
    mp_min, bpm_min_usg = _ambang_dampak_usg(cfg)
    # Tahap 1: BPM saja (tanpa fetch) — pemain yang sudah lolos
    # lewat BPM tidak butuh USG.
    butuh_usg: list[dict] = []
    for e in dipertanyakan:
        nama = e.get("player")
        kunci = _normalisasi_nama(nama)
        bpm = peta_bpm.get(kunci)
        lolos_bpm = bpm is not None and bpm >= bpm_bintang
        item = {
            "player": nama,
            "team": e.get("team_tricode"),
            "status": e.get("status"),
            "usg": None,
            "bpm": bpm,
            "mp_per_game": peta_mp.get(kunci),
            "bintang": bool(lolos_bpm),
            "lewat": "bpm" if lolos_bpm else None,
            "usg_ditolak": None,
        }
        hasil["diperiksa"].append(item)
        if lolos_bpm:
            hasil["bintang"].append(
                {
                    "player": nama,
                    "team": e.get("team_tricode"),
                    "status": e.get("status"),
                    "usg": None,
                    "bpm": bpm,
                }
            )
        else:
            butuh_usg.append(item)
    # Tahap 2: USG — hanya bila ada pemain yang belum lolos.
    if butuh_usg:
        peta_usg, sumber, catatan = _muat_peta_usg(analysis, usg_pemain)
        hasil["usg_sumber"] = sumber
        hasil["usg_catatan"] = catatan
        if peta_usg is None:
            hasil["alasan"].append(
                "USG tidak tersedia (fetch gagal — fallback BPM saja): "
                f"{catatan or 'tanpa alasan'}"
            )
        else:
            for item in butuh_usg:
                usg = peta_usg.get(_normalisasi_nama(item["player"]))
                item["usg"] = usg
                lolos, ditolak = _lolos_jalur_usg(
                    usg,
                    item["bpm"],
                    item["mp_per_game"],
                    usg_bintang,
                    mp_min,
                    bpm_min_usg,
                )
                item["usg_ditolak"] = ditolak
                if lolos:
                    item["bintang"] = True
                    item["lewat"] = "usg"
                    hasil["bintang"].append(
                        {
                            "player": item["player"],
                            "team": item["team"],
                            "status": item["status"],
                            "usg": usg,
                            "bpm": item["bpm"],
                        }
                    )
    hasil["tunggu"] = bool(hasil["bintang"])
    if hasil["tunggu"]:
        for bintang in hasil["bintang"]:
            bukti = []
            if bintang["bpm"] is not None and bintang["bpm"] >= bpm_bintang:
                bukti.append(f"BPM +{bintang['bpm']:.1f}")
            if bintang["usg"] is not None and bintang["usg"] >= usg_bintang:
                bukti.append(f"USG {bintang['usg'] * 100:.0f}%")
            hasil["alasan"].append(
                f"TUNGGU_LINEUP: {bintang['player']} ({bintang['team']}) "
                f"masih Questionable — bintang ({', '.join(bukti) or 'tanpa angka'}) "
                "yang main/tidaknya mengubah proyeksi; tunggu injury "
                "report final ~30 menit sebelum tip-off"
            )
    else:
        hasil["alasan"].append(
            "tidak ada bintang Questionable "
            f"(USG >= {usg_bintang * 100:.0f}% atau BPM >= +{bpm_bintang:.1f})"
        )
    return hasil


def evaluasi_veto(
    analysis: dict, cfg: dict | None = None, pemetaan: dict | None = None
) -> dict:
    """Evaluasi veto rim protector satu laga (tidak pernah raise data).

    ``analysis``: dict nba_analysis (atau entri match — dibuka dulu).
    ``cfg``: dict playstyle (default: dibaca dari file). ``pemetaan``:
    override pemetaan teams {tricode: [pelindung]} untuk tes; None
    berarti muat dari file CHECK-IN.

    v18: logika AND (vonis.veto.logic) — veto menyala HANYA bila rim
    protector OUT terkonfirmasi + garis pasar >=
    vonis.veto.total_tinggi_points + pace tercepat >=
    vonis.veto.pace_tinggi. Logic "OR" didukung (reversibilitas satu
    baris config). Bila HANYA satu kondisi lingkungan menyala,
    veto TIDAK menyala tapi "peringatan_parsial" True + "kondisi_
    menyala" mencatat kondisi mana (worker B: +3 bantalan).

    Mengembalikan dict veto: dievaluasi, menyala, alasan,
    pelindung_out, pelindung_diperiksa, tim, garis_pasar,
    pace_tercepat, ambang, kondisi, kondisi_menyala,
    peringatan_parsial, logic, provenance pemetaan,
    alasan_tidak_dievaluasi. Config rusak (ambang veto hilang/bukan
    angka, logic tidak dikenal) -> ConfigError, sama seperti ambang
    lain; semua masalah DATA -> dievaluasi False dengan alasan
    tercatat.
    """
    analysis = _buka_analysis(analysis)
    cfg = _muat_cfg(cfg)
    ambang_garis = _ambang(cfg, "vonis", "veto", "total_tinggi_points")
    ambang_pace = _ambang(cfg, "vonis", "veto", "pace_tinggi")
    logic = config_mod.get_value(cfg, "vonis", "veto", "logic")
    if logic not in ("AND", "OR"):
        raise config_mod.ConfigError(
            "playstyle.yaml vonis.veto.logic harus 'AND' atau 'OR': " f"{logic!r}"
        )
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
        "kondisi_menyala": [],
        "peringatan_parsial": False,
        "logic": logic,
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
        entri_cedera = _entri_cedera(analysis)
        if entri_cedera is None:
            hasil["alasan_tidak_dievaluasi"] = (
                "data ketersediaan (injuries.entries) tidak ada di artefak"
            )
            return hasil
        # Peta nama ternormalisasi -> entri cedera (OUT saja yang
        # relevan, tapi status lain tetap dicatat bila cocok).
        peta_cedera: dict[str, dict] = {}
        for entri in entri_cedera:
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
        if hasil["kondisi_garis"] is True:
            hasil["kondisi_menyala"].append("garis")
        if hasil["kondisi_pace"] is True:
            hasil["kondisi_menyala"].append("pace")
        if not hasil["pelindung_out"]:
            return hasil
        if logic == "AND":
            menyala = hasil["kondisi_garis"] is True and hasil["kondisi_pace"] is True
        else:  # OR (reversibilitas)
            menyala = hasil["kondisi_garis"] is True or hasil["kondisi_pace"] is True
        if menyala:
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
        elif len(hasil["kondisi_menyala"]) == 1:
            # HANYA satu kondisi menyala: veto tidak menyala, tapi
            # peringatan parsial dicatat (worker B: +3 bantalan).
            hasil["peringatan_parsial"] = True
        return hasil
    except (AttributeError, TypeError, ValueError):
        # Data berbentuk aneh -> veto tidak dievaluasi (bukan crash).
        hasil["dievaluasi"] = False
        hasil["menyala"] = False
        hasil["alasan"] = []
        hasil["kondisi_menyala"] = []
        hasil["peringatan_parsial"] = False
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


def _pemain_berdampak_out(
    analysis: dict,
    cfg: dict,
    muat_usg,
) -> tuple[bool, list[str], str | None]:
    """Apakah ada pemain berdampak OUT terkonfirmasi? -> (ada, nama, catatan).

    Pemain berdampak = BPM >= vonis.tunggu_lineup.bpm_bintang ATAU
    USG >= vonis.tunggu_lineup.usg_bintang (ambang dipakai ulang
    dari timing gate — satu definisi "pemain berdampak" di mesin).
    Jalur USG dikualifikasi (_lolos_jalur_usg): pemain harus rotasi
    dan tidak net-negatif.
    BPM dari inputs pemain artefak; USG lewat ``muat_usg`` (callable
    -> (peta_usg | None, sumber, catatan), dipanggil HANYA bila ada
    entri OUT terkonfirmasi yang belum lolos lewat BPM). Bila USG
    tidak tersedia, pemeriksaan hanya BPM + catatan (arah fail:
    pemain USG-tinggi/BPM-rendah bisa terlewat -> gap besar tetap
    jadi demerit — konservatif).
    """
    usg_bintang = _ambang(cfg, "vonis", "tunggu_lineup", "usg_bintang")
    bpm_bintang = _ambang(cfg, "vonis", "tunggu_lineup", "bpm_bintang")
    entri = _entri_cedera(analysis)
    if entri is None:
        return False, [], "data cedera tidak ada"
    out_terkonfirmasi = [e for e in entri if _out_terkonfirmasi(e)]
    if not out_terkonfirmasi:
        return False, [], None
    peta_bpm = _peta_bpm(analysis)
    peta_mp = _peta_mp(analysis)
    mp_min, bpm_min_usg = _ambang_dampak_usg(cfg)
    nama_berdampak: list[str] = []
    butuh_usg: list[dict] = []
    for e in out_terkonfirmasi:
        bpm = peta_bpm.get(_normalisasi_nama(e.get("player")))
        if bpm is not None and bpm >= bpm_bintang:
            nama_berdampak.append(e.get("player"))
        else:
            butuh_usg.append(e)
    catatan = None
    if butuh_usg:
        peta_usg, _sumber, catatan_usg = muat_usg()
        if peta_usg is None:
            catatan = "USG tidak tersedia (fallback BPM saja)" + (
                f": {catatan_usg}" if catatan_usg else ""
            )
        else:
            for e in butuh_usg:
                kunci = _normalisasi_nama(e.get("player"))
                usg = peta_usg.get(kunci)
                lolos, _ditolak = _lolos_jalur_usg(
                    usg,
                    peta_bpm.get(kunci),
                    peta_mp.get(kunci),
                    usg_bintang,
                    mp_min,
                    bpm_min_usg,
                )
                if lolos:
                    nama_berdampak.append(e.get("player"))
    return bool(nama_berdampak), nama_berdampak, catatan


def _evaluasi_rem_alami(
    analysis: dict,
    cfg: dict,
    ctx: dict,
    muat_usg,
) -> dict:
    """Evaluasi kelima rem alami (lihat docstring modul).

    ``ctx``: {"spread" (float|None), "garis_market" (float|None),
    "median_total" (float|None), "veto" (dict hasil evaluasi_veto)}.
    ``muat_usg``: callable -> (peta_usg | None, sumber, catatan),
    dipanggil HANYA bila rem (3) perlu USG (kedua tim punya pemain
    OUT terkonfirmasi).

    Mengembalikan {"terpenuhi": [token], "tidak_dievaluasi": [token],
    "gagal": [token], "rincian": {token: {...}}} — tiap rem tepat
    satu dari tiga status.
    """
    drtg_cutoff = _ambang(cfg, "vonis", "rem_alami", "drtg_top10_cutoff")
    pace_cutoff = _ambang(cfg, "vonis", "rem_alami", "pace_bottom12_cutoff")
    usg_scorer = _ambang(cfg, "vonis", "rem_alami", "usg_scorer_out")
    blowout = _ambang(cfg, "vonis", "rem_alami", "blowout_spread")
    align_gap = _ambang(cfg, "vonis", "rem_alami", "market_align_max_gap")
    align_total = _ambang(cfg, "vonis", "rem_alami", "market_align_max_total")
    ftr_p50 = _ambang(cfg, "vonis", "foul", "ftr_p50")
    stats = _stats_tim(analysis)
    terpenuhi: list[str] = []
    tidak_dinilai: list[str] = []
    gagal: list[str] = []
    rincian: dict = {}

    def catat(token: str, status: str, detail: dict) -> None:
        rincian[token] = {"status": status, **detail}
        if status == "terpenuhi":
            terpenuhi.append(token)
        elif status == "tidak_dievaluasi":
            tidak_dinilai.append(token)
        else:
            gagal.append(token)

    # (1) Pertahanan Top-10: salah satu tim DRtg <= cutoff.
    drtg_per_tim = {sisi: _angka(musim.get("def_rtg")) for sisi, musim in stats.items()}
    tim_top10 = [
        sisi
        for sisi, nilai in drtg_per_tim.items()
        if nilai is not None and nilai <= drtg_cutoff
    ]
    if tim_top10:
        catat(
            REM_PERTAHANAN_TOP10,
            "terpenuhi",
            {"drtg_per_tim": drtg_per_tim, "tim": tim_top10, "cutoff": drtg_cutoff},
        )
    elif any(nilai is not None for nilai in drtg_per_tim.values()):
        catat(
            REM_PERTAHANAN_TOP10,
            "gagal",
            {"drtg_per_tim": drtg_per_tim, "cutoff": drtg_cutoff},
        )
    else:
        catat(
            REM_PERTAHANAN_TOP10,
            "tidak_dievaluasi",
            {"alasan": "DRtg kedua tim tidak ada di artefak"},
        )
    # (2) Pace lambat (Bottom-12): salah satu tim pace <= cutoff.
    # ARAH: pace lambat = angka KECIL (lihat docstring modul).
    pace_per_tim = {sisi: _angka(musim.get("pace")) for sisi, musim in stats.items()}
    tim_lambat = [
        sisi
        for sisi, nilai in pace_per_tim.items()
        if nilai is not None and nilai <= pace_cutoff
    ]
    if tim_lambat:
        catat(
            REM_PACE_LAMBAT,
            "terpenuhi",
            {"pace_per_tim": pace_per_tim, "tim": tim_lambat, "cutoff": pace_cutoff},
        )
    elif any(nilai is not None for nilai in pace_per_tim.values()):
        catat(
            REM_PACE_LAMBAT,
            "gagal",
            {"pace_per_tim": pace_per_tim, "cutoff": pace_cutoff},
        )
    else:
        catat(
            REM_PACE_LAMBAT,
            "tidak_dievaluasi",
            {"alasan": "pace kedua tim tidak ada di artefak"},
        )
    # (3) Pencetak utama OUT di KEDUA tim (USG >= ambang, OUT terkonfirmasi).
    entri = _entri_cedera(analysis)
    if entri is None:
        catat(
            REM_PENCETAK_UTAMA_OUT,
            "tidak_dievaluasi",
            {"alasan": "data cedera tidak ada di artefak"},
        )
    else:
        out_per_tim: dict[str, list[str]] = {"away": [], "home": []}
        tricode_tandang, tricode_kandang = _tricode_tim(analysis)
        tricode_ke_sisi = {
            tricode_tandang: "away",
            tricode_kandang: "home",
        }
        for e in entri:
            if not _out_terkonfirmasi(e):
                continue
            sisi = tricode_ke_sisi.get(e.get("team_tricode"))
            if sisi is not None:
                out_per_tim[sisi].append(e.get("player"))
        if not out_per_tim["away"] or not out_per_tim["home"]:
            catat(
                REM_PENCETAK_UTAMA_OUT,
                "gagal",
                {
                    "out_terkonfirmasi_per_tim": out_per_tim,
                    "alasan": "salah satu tim tidak punya pemain OUT terkonfirmasi",
                },
            )
        else:
            peta_usg, sumber_usg, catatan_usg = muat_usg()
            if peta_usg is None:
                catat(
                    REM_PENCETAK_UTAMA_OUT,
                    "tidak_dievaluasi",
                    {
                        "out_terkonfirmasi_per_tim": out_per_tim,
                        "alasan": (
                            "USG tidak tersedia (fetch gagal — BPM tidak "
                            "dipakai sebagai pengganti)"
                            + (f": {catatan_usg}" if catatan_usg else "")
                        ),
                    },
                )
            else:
                peta_bpm = _peta_bpm(analysis)
                peta_mp = _peta_mp(analysis)
                mp_min, bpm_min_usg = _ambang_dampak_usg(cfg)
                pencetak_per_tim: dict[str, list[str]] = {"away": [], "home": []}
                usg_per_pemain: dict[str, float | None] = {}
                usg_ditolak: dict[str, str] = {}
                for sisi, daftar in out_per_tim.items():
                    for nama in daftar:
                        kunci = _normalisasi_nama(nama)
                        usg = peta_usg.get(kunci)
                        usg_per_pemain[nama] = usg
                        lolos, ditolak = _lolos_jalur_usg(
                            usg,
                            peta_bpm.get(kunci),
                            peta_mp.get(kunci),
                            usg_scorer,
                            mp_min,
                            bpm_min_usg,
                        )
                        if ditolak is not None:
                            usg_ditolak[nama] = ditolak
                        if lolos:
                            pencetak_per_tim[sisi].append(nama)
                if pencetak_per_tim["away"] and pencetak_per_tim["home"]:
                    catat(
                        REM_PENCETAK_UTAMA_OUT,
                        "terpenuhi",
                        {
                            "pencetak_out_per_tim": pencetak_per_tim,
                            "usg_per_pemain": usg_per_pemain,
                            "usg_ditolak": usg_ditolak,
                            "usg_sumber": sumber_usg,
                            "ambang_usg": usg_scorer,
                        },
                    )
                else:
                    catat(
                        REM_PENCETAK_UTAMA_OUT,
                        "gagal",
                        {
                            "pencetak_out_per_tim": pencetak_per_tim,
                            "out_terkonfirmasi_per_tim": out_per_tim,
                            "usg_per_pemain": usg_per_pemain,
                            "usg_ditolak": usg_ditolak,
                            "ambang_usg": usg_scorer,
                        },
                    )
    # (4) Paint utuh + blowout ATAU kedua tim FTr rendah.
    veto = ctx.get("veto") or {}
    spread = ctx.get("spread")
    cabang_blowout: str | None = None  # True/False/None (tidak dievaluasi)
    alasan_blowout = ""
    if not veto.get("dievaluasi"):
        alasan_blowout = "veto tidak dievaluasi (paint tidak bisa dinilai)"
    else:
        pelindung_out_status = [
            p["status"]
            for p in veto.get("pelindung_diperiksa") or []
            if isinstance(p, dict)
        ]
        paint_utuh = not any(
            isinstance(s, str) and s.startswith("OUT") for s in pelindung_out_status
        )
        if spread is None:
            alasan_blowout = "spread tidak ada (blowout tidak bisa dinilai)"
        elif paint_utuh and spread >= blowout:
            cabang_blowout = True
            alasan_blowout = (
                f"paint utuh (tidak ada rim protector OUT) + |spread| "
                f"{spread:g} >= {blowout:g}"
            )
        else:
            cabang_blowout = False
            alasan_blowout = (
                f"paint_utuh={paint_utuh}, |spread| "
                f"{spread:g} vs blowout {blowout:g}"
            )
    ftr_per_tim = {sisi: _angka(musim.get("ftr")) for sisi, musim in stats.items()}
    if all(nilai is not None for nilai in ftr_per_tim.values()):
        cabang_ftr = all(nilai < ftr_p50 for nilai in ftr_per_tim.values())
    else:
        cabang_ftr = None
    if cabang_blowout is True or cabang_ftr is True:
        catat(
            REM_PAINT_UTUH_BLOWOUT_ATAU_FTR_RENDAH,
            "terpenuhi",
            {
                "cabang_blowout": cabang_blowout,
                "cabang_ftr_rendah": cabang_ftr,
                "alasan_blowout": alasan_blowout,
                "ftr_per_tim": ftr_per_tim,
                "ftr_p50": ftr_p50,
                "spread": spread,
                "blowout_spread": blowout,
            },
        )
    elif cabang_blowout is None and cabang_ftr is None:
        catat(
            REM_PAINT_UTUH_BLOWOUT_ATAU_FTR_RENDAH,
            "tidak_dievaluasi",
            {
                "alasan_blowout": alasan_blowout,
                "ftr_per_tim": ftr_per_tim,
                "alasan": "kedua cabang tidak bisa dinilai",
            },
        )
    else:
        catat(
            REM_PAINT_UTUH_BLOWOUT_ATAU_FTR_RENDAH,
            "gagal",
            {
                "cabang_blowout": cabang_blowout,
                "cabang_ftr_rendah": cabang_ftr,
                "alasan_blowout": alasan_blowout,
                "ftr_per_tim": ftr_per_tim,
                "ftr_p50": ftr_p50,
                "spread": spread,
                "blowout_spread": blowout,
            },
        )
    # (5) Selaras pasar: |median - pasar| <= gap DAN pasar <= total.
    median_total = ctx.get("median_total")
    garis_market = ctx.get("garis_market")
    if median_total is None or garis_market is None:
        catat(
            REM_SELARAS_PASAR,
            "tidak_dievaluasi",
            {
                "median_total": median_total,
                "total_pasar": garis_market,
                "alasan": "median sim atau total pasar tidak ada",
            },
        )
    else:
        selisih = abs(median_total - garis_market)
        if selisih <= align_gap and garis_market <= align_total:
            catat(
                REM_SELARAS_PASAR,
                "terpenuhi",
                {
                    "median_total": median_total,
                    "total_pasar": garis_market,
                    "selisih": round(selisih, 4),
                    "gap_maks": align_gap,
                    "total_maks": align_total,
                },
            )
        else:
            catat(
                REM_SELARAS_PASAR,
                "gagal",
                {
                    "median_total": median_total,
                    "total_pasar": garis_market,
                    "selisih": round(selisih, 4),
                    "gap_maks": align_gap,
                    "total_maks": align_total,
                },
            )
    return {
        "terpenuhi": terpenuhi,
        "tidak_dievaluasi": tidak_dinilai,
        "gagal": gagal,
        "rincian": rincian,
    }


def nilai_vonis(
    analysis: dict, hasil_stress: dict | None = None, cfg: dict | None = None
) -> dict:
    """Vonis satu laga NBA dari data (HIJAU / MENENGAH_HIJAU / KUNING /
    TUNGGU_LINEUP).

    ``analysis``: dict nba_analysis, atau satu entri match artefak
    slate (dibuka otomatis bila membawa kunci ``nba_analysis``).
    ``hasil_stress``: hasil ``engine.stress.skenario_panas`` laga itu
    (opsional — bila diberikan dan memuat garis Asuransi, P banjir
    3P/FT + P setan diambil dari sana; bila None / tidak memuat
    garis itu, dihitung langsung dari CDF). ``cfg``: dict playstyle
    (default: dibaca dari config/playstyle.yaml).

    Mengembalikan ``{"vonis", "alasan", "indikator"}`` — "vonis" salah
    satu dari "hijau" / "menengah_hijau" / "kuning" /
    "tunggu_lineup"; "alasan" daftar kalimat Bahasa Indonesia (satu
    per demerit/pemicu/rem, plus catatan indikator yang tidak
    dinilai); "indikator" dict angka mentah + ambang + demerit +
    rem alami + veto + timing gate + ``dievaluasi`` (False bila
    vonis KUNING-karena-data — komposer hanya mengeluarkan laga
    KUNING yang dievaluasi, lihat docstring modul). Aturan persis +
    ambang: lihat docstring modul dan section ``vonis:`` di
    playstyle.yaml. Config rusak -> ConfigError. analysis bukan
    dict -> ValueError.
    """
    analysis = _buka_analysis(analysis)
    cfg = _muat_cfg(cfg)
    match_id = analysis.get("match_id")

    # Ambang v18 (baru dari section vonis; sisanya dipakai ulang —
    # satu sumber kebenaran per angka).
    p_flood_3p = _ambang(cfg, "vonis", "tail_fragility", "p_flood_3p_below")
    p_flood_ft = _ambang(cfg, "vonis", "tail_fragility", "p_flood_ft_below")
    total_tinggi = _ambang(cfg, "vonis", "total_tinggi_points")
    ekor_jauh = _ambang(cfg, "vonis", "ekor_gemuk", "min_offset_points")
    ekor_harga_rendah = _ambang(cfg, "vonis", "ekor_gemuk", "max_price_cents")
    ftr_p80 = _ambang(cfg, "vonis", "foul", "ftr_p80")
    ftr_p50 = _ambang(cfg, "vonis", "foul", "ftr_p50")
    spread_tipis = _ambang(cfg, "vonis", "spread_tipis_max")
    hijau_max = _ambang(cfg, "vonis", "hijau_max_demerits")
    menengah_max = _ambang(cfg, "vonis", "menengah_max_demerits")
    flood_3p_min = _ambang(cfg, "tickets", "insurance", "flood_3p_min")
    flood_ft_min = _ambang(cfg, "tickets", "insurance", "flood_ft_min")
    gap_besar = _ambang(cfg, "anomaly", "model_vs_market_points") / 100.0
    geser_3p = _ambang(cfg, "stress", "banjir_3p_points")
    geser_ft = _ambang(cfg, "stress", "banjir_ft_points")
    if not 0.0 <= p_flood_3p <= 1.0 or not 0.0 <= p_flood_ft <= 1.0:
        raise config_mod.ConfigError(
            "playstyle.yaml vonis.tail_fragility di luar 0-1: "
            f"{p_flood_3p}/{p_flood_ft}"
        )
    for nama, nilai in (
        ("hijau_max_demerits", hijau_max),
        ("menengah_max_demerits", menengah_max),
    ):
        if nilai < 0 or nilai != int(nilai):
            raise config_mod.ConfigError(
                f"playstyle.yaml vonis.{nama} harus bilangan bulat >= 0: {nilai}"
            )
    hijau_max = int(hijau_max)
    menengah_max = int(menengah_max)
    ambang = {
        "p_flood_3p_below": round(p_flood_3p, 4),
        "p_flood_ft_below": round(p_flood_ft, 4),
        "total_tinggi_points": total_tinggi,
        "ekor_min_offset_points": ekor_jauh,
        "ekor_max_price_cents": ekor_harga_rendah,
        "ftr_p80": round(ftr_p80, 6),
        "ftr_p50": round(ftr_p50, 6),
        "spread_tipis_max": spread_tipis,
        "gap_besar_pct": round(gap_besar * 100.0, 4),
        "hijau_max_demerits": hijau_max,
        "menengah_max_demerits": menengah_max,
        "flood_3p_min": round(flood_3p_min, 4),
        "flood_ft_min": round(flood_ft_min, 4),
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
    # alasannya ikut bila menyala. Precedence: veto > tunggu_lineup
    # > demerit — veto yang menyala tidak bisa diselamatkan kabar
    # lineup, dan cek timing gate dilewati bila veto menyala supaya
    # tidak fetch USG sia-sia.) ---
    veto = evaluasi_veto(analysis, cfg)
    veto_alasan = list(veto["alasan"]) if veto["menyala"] else []

    # --- Timing gate (hanya bila veto tidak menyala). ---
    timing_gate: dict | None = None
    if not veto["menyala"]:
        timing_gate = cek_tunggu_lineup(analysis, cfg)
        if timing_gate["tunggu"]:
            return {
                "vonis": VONIS_TUNGGU_LINEUP,
                "alasan": list(timing_gate["alasan"]),
                "indikator": {
                    "match_id": match_id,
                    "dievaluasi": True,
                    "pemicu_keras": None,
                    "demerit": [],
                    "n_demerit": 0,
                    "tidak_dinilai": [],
                    "timing_gate": timing_gate,
                    "veto": veto,
                    "ambang": ambang,
                },
            }

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
            {"ambang": ambang, "veto": veto, "timing_gate": timing_gate},
        )
    # Geser banjir per skenario (konteks hanya membawa yang terburuk).
    ktx["geser_banjir_3p"] = geser_3p
    ktx["geser_banjir_ft"] = geser_ft
    # --- Data wajib: spread (|median margin sim|). ---
    spread = ot_empiris_mod.baca_spread(analysis)
    if spread is None:
        return _kuning_data(
            match_id,
            PICU_DATA_TIDAK_CUKUP,
            [
                "data_tidak_cukup: spread tidak bisa dibaca "
                "(median/mean margin sim tidak ada di artefak)",
                *veto_alasan,
            ],
            {"ambang": ambang, "veto": veto, "timing_gate": timing_gate},
        )
    # --- OT empiris (spread -> p_ot; sim OT hanya info). ---
    pace_tercepat, _pace_rincian = _pace_tercepat(analysis)
    ot = ot_empiris_mod.evaluasi_ot(analysis, cfg, pace_tercepat=pace_tercepat)
    p_ot_empiris = ot["p_ot_empiris"]
    p_ot_sim = ot["p_ot_sim"]

    # --- Equilibrium kedua tiket + garis acuan + tahan-banjir. ---
    eq_ins = equilibrium_mod.cari_equilibrium(analysis, "insurance", cfg, ktx=ktx)
    eq_main = equilibrium_mod.cari_equilibrium(analysis, "main", cfg)
    acuan = equilibrium_mod.cari_garis_acuan(analysis, cfg, ktx=ktx)
    tahan = _garis_tahan_banjir_nonthin(ktx, flood_3p_min, flood_ft_min)
    ada_tahan_nonthin = tahan["entri"] is not None

    # --- Kaki artefak bergaris + berharga (sumber edge info + garis). ---
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
            {"ambang": ambang, "veto": veto, "timing_gate": timing_gate},
        )

    # Harga + volume di garis Asuransi: tangga dulu (paling otoritatif
    # untuk flag thin), kaki artefak sebagai cadangan. Volume hanya
    # INFO (bukan vonis) — lihat docstring modul, bagian VOLUME.
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
            {"ambang": ambang, "veto": veto, "timing_gate": timing_gate},
        )
    thin_asuransi = _tipis_flag(entri_tangga)
    volume_asuransi = _angka(entri_tangga.get("volume_usd")) if entri_tangga else None
    if thin_asuransi is None and leg_pada_garis is not None:
        thin_asuransi = _tipis_flag(leg_pada_garis)
        if volume_asuransi is None:
            volume_asuransi = _angka(leg_pada_garis.get("volume_usd"))

    # --- Peluang di garis Asuransi (CDF + jangkar pasar). ---
    p_model, p_market, p_final = equilibrium_mod.peluang_pada_garis(ktx, garis_asuransi)
    p_normal = stress_mod.p_under_digeser(ktx["cdf"], garis_asuransi, 0.0)
    p_banjir_3p, p_banjir_ft, p_setan, nama_banjir = _p_dari_stress(
        hasil_stress, garis_asuransi
    )
    stress_dipakai = (
        p_banjir_3p is not None or p_banjir_ft is not None or p_setan is not None
    )
    if p_banjir_3p is None:
        p_banjir_3p = stress_mod.p_under_digeser(ktx["cdf"], garis_asuransi, geser_3p)
    if p_banjir_ft is None:
        p_banjir_ft = stress_mod.p_under_digeser(ktx["cdf"], garis_asuransi, geser_ft)
    if p_setan is None:
        p_setan = stress_mod.p_under_digeser(
            ktx["cdf"], garis_asuransi, ktx["geser_setan"]
        )
    if not isinstance(nama_banjir, str):
        nama_banjir = ktx["banjir_terburuk"]
    p_banjir_terburuk = min(p_banjir_3p, p_banjir_ft)
    edge_garis = p_final - harga_asuransi / 100.0
    edge_kandidat.append((edge_garis, f"garis Asuransi U{garis_asuransi:g}"))
    edge_terbaik, edge_sumber = max(edge_kandidat, key=lambda pas: pas[0])
    gap = p_model - p_market if p_market is not None else None

    # --- Data sekunder: garis bandar + median total + FTr. ---
    market = (
        analysis.get("market") if isinstance(analysis.get("market"), dict) else None
    )
    garis_market = _angka(market.get("main_total_line")) if market else None
    median_total = None
    sim = analysis.get("simulation")
    if isinstance(sim, dict) and isinstance(sim.get("score_distribution"), dict):
        total = sim["score_distribution"].get("total")
        if isinstance(total, dict):
            median_total = _angka(total.get("median"))
    stats = _stats_tim(analysis)
    ftr_per_tim = {sisi: _angka(musim.get("ftr")) for sisi, musim in stats.items()}
    ftr_gabungan = None
    if all(nilai is not None for nilai in ftr_per_tim.values()):
        ftr_gabungan = sum(ftr_per_tim.values()) / len(ftr_per_tim)
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
    if ftr_gabungan is None:
        tidak_dinilai.append("foul_tinggi")
    if not veto["dievaluasi"]:
        tidak_dinilai.append("veto_rim_protector")

    # --- Loader USG malas (sekali per panggilan nilai_vonis; di
    # dalamnya cache satu-proses pemain_usg — tarikan jaringan
    # maksimal sekali per proses). Dipakai demerit gap besar +
    # rem alami (3). ---
    _cache_usg: dict = {}

    def muat_usg():
        if "hasil" not in _cache_usg:
            _cache_usg["hasil"] = _muat_peta_usg(analysis)
        return _cache_usg["hasil"]

    # --- Demerit + pemicu keras + investigasi (urutan tetap a–f). ---
    demerit: list[str] = []
    alasan: list[str] = []
    investigasi: list[str] = []
    pemicu_keras: str | None = None
    if veto["menyala"]:
        pemicu_keras = PICU_VETO_RIM_PROTECTOR
        alasan.extend(veto_alasan)
    if ot["hard_skip"] is True:
        if pemicu_keras is None:
            pemicu_keras = PICU_OT_TINGGI
        alasan.append(
            f"potensi overtime ekstrem: peluang OT empiris "
            f"{p_ot_empiris * 100:.2f}% >= ambang "
            f"{ot['ambang_hard_skip'] * 100:.1f}% (spread {spread:g} poin) — "
            "laga praktis imbang, babak tambahan menambah ~20 poin dan "
            "membunuh kaki Under"
        )
    # (a) Kerapuhan ekor gabungan (1 demerit).
    if p_banjir_3p < p_flood_3p or p_banjir_ft < p_flood_ft:
        demerit.append(DEMERIT_TAIL_FRAGILITY)
        bagian = []
        if p_banjir_3p < p_flood_3p:
            bagian.append(
                f"banjir 3P {p_banjir_3p * 100:.1f}% < {p_flood_3p * 100:.0f}%"
            )
        if p_banjir_ft < p_flood_ft:
            bagian.append(
                f"banjir FT {p_banjir_ft * 100:.1f}% < {p_flood_ft * 100:.0f}%"
            )
        alasan.append(
            "rapuh banjir: peluang Under di garis "
            f"U{garis_asuransi:g} — {' dan '.join(bagian)}"
        )
    # (b) Total tinggi.
    if total_tinggi_kena is True:
        demerit.append(DEMERIT_TOTAL_TINGGI)
        alasan.append(
            f"total tinggi: garis bandar {garis_market:g} "
            f"(ambang {total_tinggi:g}) — laga skor besar, variasinya "
            "lebih besar"
        )
    # (c) Gap besar — HANYA bila tanpa cedera berdampak terverifikasi.
    if gap is not None and gap > gap_besar:
        ada_berdampak, nama_berdampak, catatan_usg = _pemain_berdampak_out(
            analysis, cfg, muat_usg
        )
        if ada_berdampak:
            investigasi.append(
                "gap besar ada penjelasan: model jauh dari pasar "
                f"({gap * 100:+.1f} poin) tapi ada cedera berdampak "
                f"terkonfirmasi ({', '.join(nama_berdampak)}) yang belum "
                "tentu terserap pasar — investigasi, bukan demerit"
            )
        else:
            demerit.append(DEMERIT_GAP_BESAR)
            alasan.append(
                "model jauh dari pasar tanpa penjelasan cedera: gap "
                f"model-vs-pasar {gap * 100:+.1f} poin di garis "
                f"U{garis_asuransi:g} (ambang {gap_besar * 100:.1f}) "
                "dan tidak ada pemain berdampak OUT terkonfirmasi"
                + (f" ({catatan_usg})" if catatan_usg else "")
            )
    # (d) Ekor gemuk (diperketat).
    if ekor_gemuk is True:
        demerit.append(DEMERIT_EKOR_GEMUK)
        alasan.append(
            "ekor gemuk: garis U"
            f"{garis_asuransi:g} jauh {jarak:.1f} poin di atas total "
            f"pasar {garis_market:g} tapi harganya cuma "
            f"{harga_asuransi:g}¢ — pasar sendiri bilang total bisa "
            "meledak jauh"
        )
    # (e) Lingkungan foul tinggi (FTr gabungan >= p80).
    if ftr_gabungan is not None and ftr_gabungan >= ftr_p80:
        demerit.append(DEMERIT_FOUL_TINGGI)
        alasan.append(
            "lingkungan foul tinggi: FTr gabungan "
            f"{ftr_gabungan:.3f} (rata-rata kedua tim) >= p80 "
            f"{ftr_p80:.3f} — banyak lemparan bebas di Q4 membunuh "
            "kaki Under"
        )
    # (f) Spread tipis.
    if spread <= spread_tipis:
        demerit.append(DEMERIT_SPREAD_TIPIS)
        alasan.append(
            f"spread tipis: |spread| {spread:g} poin <= {spread_tipis:g} "
            "— laga ketat, risiko clutch + overtime tinggi"
        )

    # --- Rem alami (5). ---
    rem_alami = _evaluasi_rem_alami(
        analysis,
        cfg,
        {
            "spread": spread,
            "garis_market": garis_market,
            "median_total": median_total,
            "veto": veto,
        },
        muat_usg,
    )
    for token in rem_alami["tidak_dievaluasi"]:
        tidak_dinilai.append(f"rem_{token}")

    # --- Vonis. ---
    if pemicu_keras is not None:
        vonis = VONIS_KUNING
    elif len(demerit) <= hijau_max and rem_alami["terpenuhi"]:
        vonis = VONIS_HIJAU
    elif len(demerit) <= menengah_max:
        vonis = VONIS_MENENGAH_HIJAU
    else:
        vonis = VONIS_KUNING

    nama_rem = {
        REM_PERTAHANAN_TOP10: "pertahanan Top-10",
        REM_PACE_LAMBAT: "pace lambat (Bottom-12)",
        REM_PENCETAK_UTAMA_OUT: "pencetak utama OUT di kedua tim",
        REM_PAINT_UTUH_BLOWOUT_ATAU_FTR_RENDAH: (
            "paint utuh + blowout / kedua tim FTr rendah"
        ),
        REM_SELARAS_PASAR: "selaras pasar",
    }
    if vonis == VONIS_HIJAU:
        rem_teks = ", ".join(nama_rem[t] for t in rem_alami["terpenuhi"])
        alasan = [
            "semua indikator sehat: "
            f"{len(demerit)} demerit (maks {hijau_max}), rem alami: "
            f"{rem_teks}; peluang Under di banjir 3P "
            f"{p_banjir_3p * 100:.1f}% dan banjir FT "
            f"{p_banjir_ft * 100:.1f}% di garis U{garis_asuransi:g}, "
            f"peluang OT empiris {p_ot_empiris * 100:.2f}%"
            + (", veto rim protector tidak menyala" if veto["dievaluasi"] else "")
        ]
    elif rem_alami["terpenuhi"]:
        alasan.append(
            "rem alami terpenuhi: "
            + ", ".join(nama_rem[t] for t in rem_alami["terpenuhi"])
        )
    if investigasi:
        alasan.extend(investigasi)
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
        "investigasi": investigasi,
        "rem_alami": rem_alami,
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
        "p_banjir_3p": round(p_banjir_3p, 6),
        "p_banjir_ft": round(p_banjir_ft, 6),
        "p_banjir_terburuk": round(p_banjir_terburuk, 6),
        "banjir_terburuk": nama_banjir,
        "p_setan": round(p_setan, 6),
        "hasil_stress_dipakai": stress_dipakai,
        "p_model": round(p_model, 6),
        "p_market": round(p_market, 6) if p_market is not None else None,
        "p_final": round(p_final, 6),
        "gap_model_pasar": round(gap, 6) if gap is not None else None,
        "ekor_gemuk": ekor_gemuk,
        "jarak_garis_market_points": (round(jarak, 4) if jarak is not None else None),
        "ftr_per_tim": {
            sisi: (round(nilai, 6) if nilai is not None else None)
            for sisi, nilai in ftr_per_tim.items()
        },
        "ftr_gabungan": (round(ftr_gabungan, 6) if ftr_gabungan is not None else None),
        "spread_points": round(spread, 4),
        "ot": ot,
        "ot_probability": round(p_ot_sim, 6) if p_ot_sim is not None else None,
        "p_ot_empiris": round(p_ot_empiris, 6),
        "total_market": garis_market,
        "median_total": median_total,
        "veto": veto,
        "timing_gate": timing_gate,
        "ambang": ambang,
    }
    return {"vonis": vonis, "alasan": alasan, "indikator": indikator}
