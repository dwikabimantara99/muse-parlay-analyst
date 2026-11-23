"""Deteksi anomali pasar + snapshot harga + EV/label per kaki (Tahap 3).

Modul ini TIDAK menolak kaki — ia hanya melaporkan apa adanya (keputusan
user 2026-11-21: selisih dengan pasar = alasan untuk MENYELIDIKI, bukan
otomatis menolak). Ambang dibaca dari playstyle.yaml -> anomaly; koefisien
fee taker Kalshi dari playstyle.yaml -> fees.kalshi_taker_fee_coeff.

Anomali yang dideteksi (Blueprint §5d, DECISIONS.md D9):
  - sharp_move: harga bergerak >= 3¢ sejak pengambilan pertama.
  - jup_vs_market: |harga jup.ag - p_pasar| > 4 poin.
  - model_vs_market: |p_model - p_pasar| > 8 poin (memicu bagian wajib
    "Kenapa beda?" di laporan, keputusan user 2026-11-21).

Cek garis market (prinsip user 22 Nov 2026 — bursa dibaca sebagai
psikologi market/bandar, bukan sekadar pembanding harga): rasa "aman"
model untuk kaki Under wajib di-cross-check ke garis total market
sebelum kaki dipakai, supaya model tidak menolak bantalan (cushion)
Alt Under padahal garis market menunjukkan batas bawah yang lebih
tinggi. Anomali tambahan:
  - total_line_vs_model: |garis total market - median model| > ambang.
  - cushion_tidak_dikonfirmasi_market: bantalan lolos D10 menurut
    model tapi tidak menurut garis market.
  - model_optimis_harga_melawan: model optimis Under tapi harga Under
    turun sebesar ambang sharp move.

NILAI AWAL (BELUM DIKALIBRASI, menunggu validasi/persetujuan user):
  market_line_check.total_gap_points = 5.0 (pertimbangan: kira-kira
  setengah bantalan minimum D10 — bukan hasil fit);
  market_line_check.min_model_under_prob = 0.70 (pertimbangan:
  optimisme Under setinggi ini patut dicurigai bila harga melawan —
  bukan hasil fit).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import config
from engine import devig, price_labels

# Snapshot harga adalah runtime state (out/ gitignored).
DEFAULT_SNAPSHOTS_PATH = config.REPO_ROOT / "out" / "price_snapshots.json"
DEFAULT_MARKET_LINE_SNAPSHOTS_PATH = (
    config.REPO_ROOT / "out" / "market_line_snapshots.json"
)

# Venue yang dikenal evaluate_leg.
VENUES = ("jup", "kalshi")


def _validasi_peluang(nilai, nama: str) -> float:
    """Pastikan nilai adalah peluang desimal 0–1 yang hingga."""
    if (
        isinstance(nilai, bool)
        or not isinstance(nilai, (int, float))
        or not math.isfinite(nilai)
        or not 0.0 <= nilai <= 1.0
    ):
        raise ValueError(f"{nama} tidak valid: {nilai!r} (harus peluang 0–1)")
    return float(nilai)


def _validasi_harga_cents(nilai, nama: str) -> float:
    """Pastikan nilai adalah harga dalam sen, 0 < harga < 100."""
    if (
        isinstance(nilai, bool)
        or not isinstance(nilai, (int, float))
        or not math.isfinite(nilai)
        or not 0.0 < nilai < 100.0
    ):
        raise ValueError(f"{nama} tidak valid: {nilai!r} (harus 0 < harga < 100¢)")
    return float(nilai)


def _validasi_garis_total(nilai, nama: str) -> float:
    """Pastikan nilai adalah garis total (poin), angka hingga > 0."""
    if (
        isinstance(nilai, bool)
        or not isinstance(nilai, (int, float))
        or not math.isfinite(nilai)
        or not nilai > 0
    ):
        raise ValueError(f"{nama} tidak valid: {nilai!r} (harus angka hingga > 0)")
    return float(nilai)


def _validasi_ambang(nilai, nama: str) -> float:
    """Pastikan ambang config adalah angka hingga >= 0."""
    if (
        isinstance(nilai, bool)
        or not isinstance(nilai, (int, float))
        or not math.isfinite(nilai)
        or nilai < 0
    ):
        raise ValueError(f"{nama} tidak valid: {nilai!r} (harus angka hingga >= 0)")
    return float(nilai)


def kalshi_effective_price_cents(price_cents, cfg: dict | None = None) -> float:
    """Harga efektif Kalshi (¢) setelah fee taker.

    Fee Schedule resmi Kalshi (berlaku 7 Juli 2026): fee taker per
    kontrak = 0,07 × P × (1 − P) dolar, P = harga dalam dolar (0–1).
    Harga efektif = harga + fee (dalam sen).

    APROKSIMASI: Fee Schedule membulatkan fee ke atas (roundup) per
    order; di sini pembulatan itu diabaikan — fee dihitung persis
    per kontrak — karena matematika harga bekerja per kontrak, bukan
    per order. Selisihnya kurang dari 1¢ per kontrak. Koefisien 0,07
    dibaca dari playstyle.yaml -> fees.kalshi_taker_fee_coeff.

    Contoh acuan: 80¢ -> 81,12¢; 50¢ -> 51,75¢.
    Melempar ValueError bila harga di luar (0, 100) atau koefisien
    config tidak valid.
    """
    harga = _validasi_harga_cents(price_cents, "price_cents")
    cfg = cfg if cfg is not None else config.load_playstyle()
    coeff = config.get_value(cfg, "fees", "kalshi_taker_fee_coeff")
    if (
        isinstance(coeff, bool)
        or not isinstance(coeff, (int, float))
        or not math.isfinite(coeff)
        or not 0.0 <= coeff < 1.0
    ):
        raise ValueError(
            f"fees.kalshi_taker_fee_coeff tidak valid: {coeff!r} (harus 0–1)"
        )
    p = harga / 100.0
    fee_cents = 100.0 * coeff * p * (1.0 - p)
    return harga + fee_cents


class PriceSnapshots:
    """Snapshot harga PERTAMA per kunci pasar, untuk deteksi sharp move (D9).

    Format kunci yang disarankan: f"{match_id}:{market_key}", misal
    "nba_2026-11-22_okc_lal:total_under_227.5". Hanya snapshot pertama
    yang disimpan — record() berikutnya untuk kunci yang sama diabaikan,
    supaya pergerakan selalu diukur dari harga pengambilan pertama.
    State disimpan sebagai JSON di out/price_snapshots.json (runtime
    state, gitignored) dan dimuat lagi saat objek dibuat.
    """

    def __init__(self, path: str | Path | None = None):
        """Buat/muat snapshot. path None -> out/price_snapshots.json.

        Melempar ValueError bila file yang ada rusak (JSON tidak valid
        atau isinya bukan mapping snapshot) — sejarah harga tidak boleh
        diam-diam dihapus.
        """
        self.path = Path(path) if path is not None else DEFAULT_SNAPSHOTS_PATH
        self._snapshots: dict[str, dict] = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"file snapshot rusak: {self.path}: {exc}") from exc
            if not isinstance(data, dict):
                raise ValueError(f"file snapshot rusak: {self.path} bukan mapping")
            for key, entry in data.items():
                if (
                    not isinstance(entry, dict)
                    or not isinstance(entry.get("price_cents"), (int, float))
                    or not isinstance(entry.get("first_at"), str)
                ):
                    raise ValueError(
                        f"file snapshot rusak: entri {key!r} tidak lengkap"
                    )
            self._snapshots = data

    def _simpan(self) -> None:
        """Tulis state ke file JSON."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._snapshots, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def record(self, key: str, price_cents, now_iso: str) -> bool:
        """Simpan snapshot pertama untuk kunci; kunci yang sudah ada diabaikan.

        Mengembalikan True bila snapshot baru disimpan, False bila kunci
        sudah punya snapshot (harga pertama dipertahankan). Melempar
        ValueError bila kunci/jam kosong atau harga tidak valid.
        """
        if not isinstance(key, str) or not key:
            raise ValueError(f"kunci snapshot tidak valid: {key!r}")
        harga = _validasi_harga_cents(price_cents, "price_cents")
        if not isinstance(now_iso, str) or not now_iso:
            raise ValueError(f"jam snapshot tidak valid: {now_iso!r}")
        if key in self._snapshots:
            return False
        self._snapshots[key] = {"price_cents": harga, "first_at": now_iso}
        self._simpan()
        return True

    def get(self, key: str) -> dict | None:
        """Snapshot untuk kunci, atau None bila belum ada.

        Mengembalikan salinan {"price_cents": ..., "first_at": ...}.
        """
        snapshot = self._snapshots.get(key)
        return dict(snapshot) if snapshot is not None else None

    def sharp_move(self, key: str, price_cents, cfg: dict | None = None) -> dict | None:
        """Anomali bila harga kini bergerak >= sharp_move_cents (D9: 3¢).

        Membandingkan harga kini dengan snapshot pertama untuk kunci itu.
        Mengembalikan {"type": "sharp_move", "key", "first_cents",
        "now_cents", "delta_cents", "first_at"} bila gerak mencapai ambang,
        else None (termasuk bila belum ada snapshot untuk kunci itu).
        delta_cents bertanda: negatif berarti harga turun.
        """
        harga = _validasi_harga_cents(price_cents, "price_cents")
        snapshot = self._snapshots.get(key)
        if snapshot is None:
            return None
        cfg = cfg if cfg is not None else config.load_playstyle()
        ambang = config.get_value(cfg, "anomaly", "sharp_move_cents")
        delta = round(harga - snapshot["price_cents"], 9)
        if abs(delta) >= ambang:
            return {
                "type": "sharp_move",
                "key": key,
                "first_cents": snapshot["price_cents"],
                "now_cents": harga,
                "delta_cents": delta,
                "first_at": snapshot["first_at"],
            }
        return None


class MarketLineSnapshots:
    """Snapshot garis market PERTAMA per kunci pasar.

    Seperti PriceSnapshots, tapi menyimpan garis (line) + harga saat
    pertama kali pasar itu dilihat — dipakai untuk membaca DI MANA
    market memasang garis (psikologi market/bandar, prinsip user
    22 Nov 2026) dan membandingkannya dengan proyeksi model.

    Format kunci yang disarankan sama seperti PriceSnapshots:
    f"{match_id}:{market_key}". Hanya snapshot pertama yang disimpan.
    State disimpan sebagai JSON di out/market_line_snapshots.json
    (runtime state, gitignored).
    """

    def __init__(self, path: str | Path | None = None):
        """Buat/muat snapshot. path None -> out/market_line_snapshots.json.

        Melempar ValueError bila file yang ada rusak (JSON tidak valid
        atau isinya bukan mapping snapshot) — sejarah garis tidak boleh
        diam-diam dihapus.
        """
        self.path = (
            Path(path) if path is not None else DEFAULT_MARKET_LINE_SNAPSHOTS_PATH
        )
        self._snapshots: dict[str, dict] = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"file snapshot rusak: {self.path}: {exc}") from exc
            if not isinstance(data, dict):
                raise ValueError(f"file snapshot rusak: {self.path} bukan mapping")
            for key, entry in data.items():
                if (
                    not isinstance(entry, dict)
                    or not isinstance(entry.get("line"), (int, float))
                    or not isinstance(entry.get("price_cents"), (int, float))
                    or not isinstance(entry.get("first_at"), str)
                ):
                    raise ValueError(
                        f"file snapshot rusak: entri {key!r} tidak lengkap"
                    )
            self._snapshots = data

    def _simpan(self) -> None:
        """Tulis state ke file JSON."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._snapshots, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def record(self, key: str, line, price_cents, now_iso: str) -> bool:
        """Simpan snapshot pertama untuk kunci; kunci yang sudah ada diabaikan.

        Mengembalikan True bila snapshot baru disimpan, False bila kunci
        sudah punya snapshot (garis pertama dipertahankan). Melempar
        ValueError bila kunci/jam kosong atau garis/harga tidak valid.
        """
        if not isinstance(key, str) or not key:
            raise ValueError(f"kunci snapshot tidak valid: {key!r}")
        garis = _validasi_garis_total(line, "line")
        harga = _validasi_harga_cents(price_cents, "price_cents")
        if not isinstance(now_iso, str) or not now_iso:
            raise ValueError(f"jam snapshot tidak valid: {now_iso!r}")
        if key in self._snapshots:
            return False
        self._snapshots[key] = {
            "line": garis,
            "price_cents": harga,
            "first_at": now_iso,
        }
        self._simpan()
        return True

    def get(self, key: str) -> dict | None:
        """Snapshot untuk kunci, atau None bila belum ada.

        Mengembalikan salinan {"line", "price_cents", "first_at"}.
        """
        snapshot = self._snapshots.get(key)
        return dict(snapshot) if snapshot is not None else None


def check_jup_vs_market(
    jup_price_cents, p_market, cfg: dict | None = None
) -> dict | None:
    """Anomali bila |harga jup.ag - p_pasar| > anomaly.jup_vs_market_points.

    Ambang 4 poin, aturan "lebih dari": tepat di ambang BUKAN anomali.
    Mengembalikan {"type": "jup_vs_market", "jup_cents", "p_market",
    "diff_points"} atau None (termasuk bila p_market None — tidak ada
    pembanding, tidak ada anomali). Melempar ValueError bila input
    tidak valid.
    """
    if p_market is None:
        return None
    jup = _validasi_harga_cents(jup_price_cents, "jup_price_cents")
    p_market = _validasi_peluang(p_market, "p_market")
    cfg = cfg if cfg is not None else config.load_playstyle()
    ambang = config.get_value(cfg, "anomaly", "jup_vs_market_points")
    # Hitung dalam satuan sen lalu bulatkan: selisih float mentah
    # (mis. 0.75 - 0.71 = 0.040000000000000036) bisa salah melewati ambang.
    diff_points = round(abs(jup - p_market * 100.0), 9)
    if diff_points > ambang:
        return {
            "type": "jup_vs_market",
            "jup_cents": jup,
            "p_market": p_market,
            "diff_points": diff_points,
        }
    return None


def check_model_vs_market(p_model, p_market, cfg: dict | None = None) -> dict | None:
    """Anomali bila |p_model - p_pasar| > anomaly.model_vs_market_points.

    Ambang 8 poin, aturan "lebih dari": tepat di ambang BUKAN anomali.
    Anomali ini memicu bagian wajib "Kenapa beda?" di laporan (keputusan
    user 2026-11-21). Mengembalikan {"type": "model_vs_market",
    "p_model", "p_market", "diff_points", "kenapa_beda_required": True}
    atau None (termasuk bila p_market None). Melempar ValueError bila
    input tidak valid.
    """
    if p_market is None:
        return None
    p_model = _validasi_peluang(p_model, "p_model")
    p_market = _validasi_peluang(p_market, "p_market")
    cfg = cfg if cfg is not None else config.load_playstyle()
    ambang = config.get_value(cfg, "anomaly", "model_vs_market_points")
    # Dibulatkan supaya tepat di ambang tidak salah terpicu oleh float.
    diff_points = round(abs(p_model - p_market) * 100.0, 9)
    if diff_points > ambang:
        return {
            "type": "model_vs_market",
            "p_model": p_model,
            "p_market": p_market,
            "diff_points": diff_points,
            "kenapa_beda_required": True,
        }
    return None


def check_total_line_vs_model(
    model_median_total, market_total_line, cfg: dict | None = None
) -> dict | None:
    """Anomali bila |garis total market - median model| > ambang.

    gap = market_total_line - model_median_total. Ambang dari cfg
    "market_line_check.total_gap_points" (NILAI AWAL yang diusulkan
    5.0 — BELUM DIKALIBRASI, menunggu validasi/persetujuan user).
    Aturan "lebih dari": tepat di ambang BUKAN anomali.

    gap > 0 adalah arah berbahaya untuk kaki Under: market mengharap
    total LEBIH TINGGI dari model, jadi optimisme Under model patut
    dicurigai. Mengembalikan {"type": "total_line_vs_model",
    "model_median_total", "market_total_line", "gap_points",
    "direction", "kenapa_beda_required": True} atau None (termasuk
    bila salah satu input None — tidak bisa dicek berarti tidak ada
    anomali dari cek ini). Melempar ValueError bila input tidak valid.
    """
    if model_median_total is None or market_total_line is None:
        return None
    median = _validasi_garis_total(model_median_total, "model_median_total")
    garis = _validasi_garis_total(market_total_line, "market_total_line")
    cfg = cfg if cfg is not None else config.load_playstyle()
    ambang = _validasi_ambang(
        config.get_value(cfg, "market_line_check", "total_gap_points"),
        "market_line_check.total_gap_points",
    )
    # Dibulatkan supaya tepat di ambang tidak salah terpicu oleh float.
    gap = round(garis - median, 9)
    if abs(gap) > ambang:
        return {
            "type": "total_line_vs_model",
            "model_median_total": median,
            "market_total_line": garis,
            "gap_points": gap,
            "direction": "market_lebih_tinggi" if gap > 0 else "model_lebih_tinggi",
            "kenapa_beda_required": True,
        }
    return None


def check_cushion_vs_market(
    alt_line, model_median_total, market_total_line, cushion_points
) -> dict | None:
    """Anomali bila bantalan adaptif lolos menurut model tapi tidak menurut market.

    model_cushion = alt_line - model_median_total; market_cushion =
    alt_line - market_total_line. required = cushion_points, yaitu
    bantalan adaptif dari engine/analis.py yang TERCATAT pada kaki
    (mis. hasil cushion.utama_line["cushion_points"]) — BUKAN lagi
    aturan kaku 8/12 berbasis spread (kunci config
    min_cushion_points[_close_spread] + close_spread_threshold
    DIHAPUS di playstyle.yaml versi 13).

    Hanya peduli kasus model_cushion >= required TAPI market_cushion <
    required — model bilang bantalan cukup, market bilang tidak.
    Bila model_cushion sendiri < required, itu urusan pemilihan garis
    (bukan fungsi ini) -> None. Bila salah satu garis None ATAU
    cushion_points None -> None (tidak bisa dicek). Melempar
    ValueError bila input tidak valid.
    """
    if (
        alt_line is None
        or model_median_total is None
        or market_total_line is None
        or cushion_points is None
    ):
        return None
    alt = _validasi_garis_total(alt_line, "alt_line")
    median = _validasi_garis_total(model_median_total, "model_median_total")
    garis = _validasi_garis_total(market_total_line, "market_total_line")
    if (
        isinstance(cushion_points, bool)
        or not isinstance(cushion_points, (int, float))
        or not math.isfinite(cushion_points)
        or cushion_points < 0
    ):
        raise ValueError(
            f"cushion_points tidak valid: {cushion_points!r} (harus angka hingga >= 0)"
        )
    required = float(cushion_points)
    model_cushion = round(alt - median, 9)
    market_cushion = round(alt - garis, 9)
    if model_cushion >= required and market_cushion < required:
        return {
            "type": "cushion_tidak_dikonfirmasi_market",
            "alt_line": alt,
            "model_median_total": median,
            "market_total_line": garis,
            "model_cushion_points": model_cushion,
            "market_cushion_points": market_cushion,
            "required_cushion_points": required,
            "kenapa_beda_required": True,
        }
    return None


def evaluate_leg(
    p_model,
    p_market,
    jup_price_cents,
    comparison_source,
    cfg: dict | None = None,
    venue: str = "jup",
    snapshots: PriceSnapshots | None = None,
    snapshot_key: str | None = None,
) -> dict:
    """Nilai SATU kaki: blend, EV%, label harga, dan semua anomali.

    Langkah: (a) harga efektif = harga + fee taker bila venue "kalshi",
    else harga apa adanya; (b) blend -> p_final (+ model_only bila
    p_market None); (c) EV% = (p_final × (100/harga_efektif) − 1) × 100
    (D7); (d) anomali sharp_move dulu (bila snapshots + snapshot_key
    diberikan) karena label bergantung padanya: bila sharp move
    terdeteksi, label DISKON ditekan jadi DISKON_DITEKAN (sharp move
    BUKAN diskon — kasus Thunder); (e) label via
    price_labels.label_for_ev; (f) anomali jup_vs_market dan
    model_vs_market (bila p_market ada).

    jup_price_cents adalah harga venue dalam sen (harga jup.ag bila
    venue "jup", harga Kalshi bila venue "kalshi"). comparison_source
    adalah sumber p_market (mis. "odds_api_devig"), None bila MODEL_ONLY.
    Fungsi ini TIDAK menolak kaki — laporkan apa adanya.
    Melempar ValueError bila venue tidak dikenal atau input tidak valid.
    """
    if venue not in VENUES:
        raise ValueError(f"venue tidak dikenal: {venue!r} (harus 'jup'/'kalshi')")
    harga = _validasi_harga_cents(jup_price_cents, "jup_price_cents")
    cfg = cfg if cfg is not None else config.load_playstyle()
    if venue == "kalshi":
        harga_efektif = kalshi_effective_price_cents(harga, cfg)
    else:
        harga_efektif = harga
    hasil_blend = devig.blend(p_model, p_market, cfg)
    p_final = hasil_blend["p_final"]
    ev_pct = (p_final * (100.0 / harga_efektif) - 1.0) * 100.0
    anomalies: list[dict] = []
    sharp_move_terdeteksi = False
    if snapshots is not None and snapshot_key is not None:
        gerak = snapshots.sharp_move(snapshot_key, harga, cfg)
        if gerak is not None:
            anomalies.append(gerak)
            sharp_move_terdeteksi = True
    # Sharp move BUKAN diskon (kasus Thunder): bila harga baru bergerak
    # tajam, label DISKON ditekan jadi DISKON_DITEKAN — jangan pernah
    # mengembalikan DISKON polos bersamaan dengan anomali sharp_move.
    label = price_labels.label_for_ev(ev_pct, cfg, sharp_move=sharp_move_terdeteksi)
    if p_market is not None:
        jup_anomali = check_jup_vs_market(harga, p_market, cfg)
        if jup_anomali is not None:
            anomalies.append(jup_anomali)
        model_anomali = check_model_vs_market(p_model, p_market, cfg)
        if model_anomali is not None:
            anomalies.append(model_anomali)
    return {
        "p_model": hasil_blend["p_model"],
        "p_market": hasil_blend["p_market"],
        "comparison_source": comparison_source,
        "p_final": p_final,
        "w_model": hasil_blend["w_model"],
        "model_only": hasil_blend["model_only"],
        "price_cents": harga,
        "effective_price_cents": harga_efektif,
        "venue": venue,
        "ev_pct": ev_pct,
        "price_label": label,
        "anomalies": anomalies,
    }


def check_under_safety(
    p_model_under,
    model_median_total,
    market_total_line,
    alt_line,
    cushion_points,
    price_delta_cents,
    cfg: dict | None = None,
) -> dict:
    """Verdict gabungan untuk satu kaki Under: aman menurut model + market?

    Mengumpulkan anomali dari check_total_line_vs_model dan
    check_cushion_vs_market (cushion_points = bantalan adaptif
    TERCATAT pada kaki, dari engine/analis.py — bukan lagi spread),
    DITAMBAH cek harga-melawan: bila
    p_model_under >= market_line_check.min_model_under_prob (NILAI
    AWAL yang diusulkan 0,70 — BELUM DIKALIBRASI, menunggu
    validasi/persetujuan user) DAN harga Under TURUN melawan posisi
    sebesar ambang sharp move (price_delta_cents <=
    -anomaly.sharp_move_cents) -> anomali "model_optimis_harga_melawan".
    Mengembalikan {"safe_confirmed": True bila tidak ada anomali,
    "anomalies": [...]}.

    p_model_under None -> cek harga-melawan dilewati saja (cek garis
    tetap jalan bila datanya ada). price_delta_cents None -> tidak ada
    cek harga-melawan. Fungsi ini TIDAK menolak kaki — hanya
    melaporkan, seperti anomali lain di modul ini.
    """
    cfg = cfg if cfg is not None else config.load_playstyle()
    anomalies: list[dict] = []
    garis_anomali = check_total_line_vs_model(
        model_median_total, market_total_line, cfg
    )
    if garis_anomali is not None:
        anomalies.append(garis_anomali)
    bantalan_anomali = check_cushion_vs_market(
        alt_line, model_median_total, market_total_line, cushion_points
    )
    if bantalan_anomali is not None:
        anomalies.append(bantalan_anomali)
    p_under = (
        _validasi_peluang(p_model_under, "p_model_under")
        if p_model_under is not None
        else None
    )
    delta = None
    if price_delta_cents is not None:
        if (
            isinstance(price_delta_cents, bool)
            or not isinstance(price_delta_cents, (int, float))
            or not math.isfinite(price_delta_cents)
        ):
            raise ValueError(
                f"price_delta_cents tidak valid: {price_delta_cents!r} "
                "(harus angka hingga)"
            )
        delta = float(price_delta_cents)
    if p_under is not None and delta is not None:
        ambang_optimis = _validasi_peluang(
            config.get_value(cfg, "market_line_check", "min_model_under_prob"),
            "market_line_check.min_model_under_prob",
        )
        sharp = _validasi_ambang(
            config.get_value(cfg, "anomaly", "sharp_move_cents"),
            "anomaly.sharp_move_cents",
        )
        if p_under >= ambang_optimis and delta <= -sharp:
            anomalies.append(
                {
                    "type": "model_optimis_harga_melawan",
                    "p_model_under": p_under,
                    "price_delta_cents": delta,
                    "kenapa_beda_required": True,
                }
            )
    return {"safe_confirmed": len(anomalies) == 0, "anomalies": anomalies}
