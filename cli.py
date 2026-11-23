#!/usr/bin/env python3
"""Satu pintu masuk muse-parlay-analyst (Blueprint §10, SOP §5).

    python cli.py analyze --input slate.json [--out out.json]
        # Tahap 2b ✓ — tarik data (SOP langkah 2-3), tulis
        # out/analysis_<slate_id>.json. Simulasi/tiket Tahap 3+.
    python cli.py recheck --analysis out/analysis_<id>.json [--match DET@ATL_2026-11-22]
        # Tahap 3 Langkah 2 ✓ — cek ulang pra-submit satu laga NBA.
        # Exit 0 = GO, 1 = NO-GO (laporan ditulis), 2 = tidak bisa jalan.
    python cli.py laporan --analysis out/analysis_<id>.json [--match ...]
        [--recheck out/recheck_<id>.json] [--out laporan.txt] [--json]
        # Tahap 3 Langkah 3 ✓ — laporan lengkap satu laga NBA.
    python cli.py tanya --analysis out/analysis_<id>.json [--match ...]
        "<pertanyaan>"
        # Tahap 3 Langkah 3 ✓ — tanya-jawab soal satu laga NBA.
    python cli.py racik --analysis <file...> [--recheck <file...>]
        --stake-total <usd> [--out out/tickets_<tanggal>.json]
        # Tahap 3 Langkah 3 ✓ — racik Tiket Asuransi + Utama.
        # Exit 0 = minimal satu tiket terracik, 1 = tidak ada tiket,
        # 2 = tidak bisa jalan.
    python cli.py audit --ticket out/tickets_<tanggal>.json
        --analysis out/analysis_<id>.json [out/analysis_<id2>.json ...]
        [--output out/audit_<nama-tiket>_<tanggal>.json]
        # Tahap 4 — audit tiket sebelum pasang (insiden DEN 23 Nov 2026).
        # Exit 0 = semua tiket GO, 1 = ada tiket NO-GO (laporan tetap
        # ditulis), 2 = tidak bisa jalan.
    python cli.py pantau --ticket out/tickets_<tanggal>.json
        [--analysis out/analysis_<id>.json ...] [--match DET@ATL_2026-11-22]
        [--date YYYY-MM-DD] [--output out/pantau_<tanggal>.json]
        # Tahap 3 Langkah 4 — pantau tiket live + deteksi anomali.
        # Exit 0 = aman, 1 = ada kaki TERANCAM/KALAH/anomali atau kaki
        # yang tidak bisa dinilai (DATA_INCOMPLETE), 2 = tidak bisa jalan.
    python cli.py log --file ticket.json       # Tahap 1  ✓
    python cli.py log --settle <id> --result WIN|LOSS|PUSH|VOID|CASHOUT
        [--cashout-amount <usd>] [--leg-result <leg_id>=<hasil> ...]
    python cli.py recap [--json]
    python cli.py belajar [--db ledger.db] [--keluaran laporan.txt]
        [--contoh-sintetis]
        # Tahap 3 Langkah 6 — laporan belajar dari hasil tercatat:
        # ringkasan Brier per pasar, kalibrasi bobot w, dan usulan
        # yang menunggu persetujuan. Belum ada data -> laporan
        # "belum ada data", exit 0. --contoh-sintetis memakai fixture
        # sintetis (laporan berlabel SINTETIS).

Exit code: 0 sukses, 1 error (input tidak valid / ledger gagal) —
recheck: 0 = GO, 1 = NO-GO (laporan tetap ditulis), 2 = recheck tidak
bisa berjalan (tidak ada laporan). laporan/tanya: 0 sukses, 2 = tidak
bisa jalan. racik: 0 = minimal satu tiket terracik, 1 = tidak ada
tiket yang bisa diracik, 2 = tidak bisa jalan. audit: 0 = semua
tiket GO, 1 = ada tiket NO-GO (laporan tetap ditulis), 2 = tidak
bisa jalan. pantau: 0 = aman,
1 = ada kaki TERANCAM/KALAH/anomali atau DATA_INCOMPLETE,
2 = tidak bisa jalan. belajar: 0 sukses (termasuk belum ada data),
2 = tidak bisa jalan (modul belajar / fixture tidak tersedia).
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from ledger import recap as recap_mod  # noqa: E402
from ledger import store  # noqa: E402

RECHECK_ERROR = 2  # recheck tidak bisa berjalan (tidak ada laporan)


def _db_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--db",
        default=str(store.DEFAULT_DB_PATH),
        help="path file SQLite ledger (default: ledger.db di root repo)",
    )


def _validate_slate(slate: dict) -> str | None:
    """Validasi slate input terhadap schemas/slate.schema.json.

    Mengembalikan pesan error, atau None bila valid. Bila ``jsonschema``
    tidak tersedia, pakai validasi minimal (required-field) + peringatan
    ke stderr.
    """
    try:
        import jsonschema
    except ImportError:
        print(
            "peringatan: jsonschema tidak tersedia — validasi minimal "
            "(required-field) saja",
            file=sys.stderr,
        )
        for key in ("slate_id", "created_at_wib", "matches"):
            if key not in slate:
                return f"slate kehilangan kunci wajib: {key}"
        if not isinstance(slate.get("matches"), list) or not slate["matches"]:
            return "slate.matches harus list tidak kosong"
        for entry in slate["matches"]:
            for key in ("match_id", "sport", "league", "home", "away", "start_time"):
                if key not in entry:
                    return f"laga kehilangan kunci wajib: {key}"
        return None
    schema_path = REPO_ROOT / "schemas" / "slate.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"tidak bisa membaca skema slate: {exc}"
    try:
        jsonschema.validate(slate, schema)
    except jsonschema.ValidationError as exc:
        return f"slate tidak valid: {exc.message}"
    return None


def _slate_date(match: dict, sport: str | None = None) -> str | None:
    """Tanggal (YYYY-MM-DD) dari start_time satu laga; None bila tidak sah.

    NBA: tanggal US Eastern — stats.nba.com memakai tanggal Eastern, jadi
    start_time WIB yang jatuh dini hari (mis. 08:00 WIB) adalah laga malam
    sebelumnya di AS. Sport lain: tanggal apa adanya dari start_time
    (pencocokan fixture bola toleran ±1 hari).
    """
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    try:
        parsed = datetime.fromisoformat(match["start_time"])
    except (KeyError, TypeError, ValueError):
        return None
    if sport == "nba":
        if parsed.tzinfo is None:
            # Skema slate mewajibkan zona waktu; bila hilang, anggap UTC.
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    return parsed.date().isoformat()


def _league_code(league: str | None) -> str:
    """Kode liga fetcher dari nama liga slate ('Premier League' -> 'EPL')."""
    mapping = {
        "Premier League": "EPL",
        "EPL": "EPL",
        "LaLiga": "LaLiga",
        "La Liga": "LaLiga",
    }
    return mapping.get(str(league or ""), str(league or "EPL"))


def _lampirkan_nba_analysis(
    matches_2b: list[dict], entries_slate: list[dict], tanggal_eastern: str
) -> None:
    """Lampirkan artefak nba_analysis ke tiap laga NBA hasil build_slate.

    Tahap 3 Langkah 2: untuk tiap laga NBA, tricode diambil dari nama tim
    entri slate asal (dicocokkan lewat match_id), lalu
    engine.nba_analysis.build_nba_analysis dipanggil dan hasilnya
    dilampirkan sebagai kunci "nba_analysis" pada entri MatchData 2b.
    Bila builder gagal total / tricode tidak bisa dipetakan, dilampirkan
    artefak minimal DATA_INCOMPLETE — analyze TIDAK gagal hanya karena
    satu laga NBA. Laga tanpa entri slate asal (mis. slate hasil mock
    di tes) dilewati: timnya tidak diketahui, tidak bisa dianalisis.
    """
    from engine import nba_analysis as nba_analysis_mod
    from ingest.nba_brain import team_tricode

    per_match_id = {
        entry.get("match_id"): entry
        for entry in entries_slate
        if isinstance(entry, dict)
    }
    for match_2b in matches_2b:
        entri = per_match_id.get(match_2b.get("match_id"))
        if entri is None:
            continue
        start_time = entri.get("start_time")
        home = team_tricode(entri.get("home") or "")
        away = team_tricode(entri.get("away") or "")
        if home is None or away is None:
            match_2b["nba_analysis"] = nba_analysis_mod.minimal_nba_analysis(
                entri.get("match_id") or match_2b.get("match_id"),
                home or "UNK",
                away or "UNK",
                tanggal_eastern,
                [
                    "tricode_tidak_dikenal: "
                    f"{entri.get('home')!r} vs {entri.get('away')!r}"
                ],
                start_time=start_time,
            )
            continue
        try:
            match_2b["nba_analysis"] = nba_analysis_mod.build_nba_analysis(
                home,
                away,
                tanggal_eastern,
                slate_match=match_2b,
                start_time=start_time,
            )
        except Exception as exc:  # noqa: BLE001 - builder gagal != analyze gagal
            match_2b["nba_analysis"] = nba_analysis_mod.minimal_nba_analysis(
                f"{away}@{home}_{tanggal_eastern}",
                home,
                away,
                tanggal_eastern,
                [f"builder_gagal: {type(exc).__name__}: {exc}"],
                start_time=start_time,
            )


def _lampirkan_soccer_analysis(
    matches_2b: list[dict], entries_slate: list[dict], tanggal: str
) -> None:
    """Lampirkan artefak soccer_analysis ke tiap laga bola hasil build_slate.

    Tahap 3 Langkah 5: untuk tiap laga bola, nama tim diambil dari entri
    slate asal (dicocokkan lewat match_id), lalu
    engine.soccer_analysis.build_soccer_analysis dipanggil dan hasilnya
    dilampirkan sebagai kunci "soccer_analysis" pada entri MatchData 2b.
    Bila builder gagal total, dilampirkan artefak minimal
    DATA_INCOMPLETE — analyze TIDAK gagal hanya karena satu laga bola.
    Laga tanpa entri slate asal (mis. slate hasil mock di tes) dilewati:
    timnya tidak diketahui, tidak bisa dianalisis. Liga diambil dari
    entri slate (default EPL); liga yang tidak didukung soccer_brain
    menghasilkan artefak DATA_INCOMPLETE dari builder sendiri.
    """
    from engine import soccer_analysis as soccer_analysis_mod

    per_match_id = {
        entry.get("match_id"): entry
        for entry in entries_slate
        if isinstance(entry, dict)
    }
    for match_2b in matches_2b:
        entri = per_match_id.get(match_2b.get("match_id"))
        if entri is None:
            continue
        start_time = entri.get("start_time")
        home = entri.get("home") or ""
        away = entri.get("away") or ""
        liga = _league_code(entri.get("league"))
        if not str(home).strip() or not str(away).strip():
            match_2b["soccer_analysis"] = soccer_analysis_mod.minimal_soccer_analysis(
                entri.get("match_id") or match_2b.get("match_id"),
                str(home) or "UNK",
                str(away) or "UNK",
                tanggal,
                ["nama_tim_kosong: " f"{entri.get('home')!r} vs {entri.get('away')!r}"],
                league=liga,
                start_time=start_time,
            )
            continue
        try:
            match_2b["soccer_analysis"] = soccer_analysis_mod.build_soccer_analysis(
                str(home),
                str(away),
                tanggal,
                league=liga,
                slate_match=match_2b,
                start_time=start_time,
            )
        except Exception as exc:  # noqa: BLE001 - builder gagal != analyze gagal
            match_2b["soccer_analysis"] = soccer_analysis_mod.minimal_soccer_analysis(
                f"{away}@{home}_{tanggal}",
                str(home),
                str(away),
                tanggal,
                [f"builder_gagal: {type(exc).__name__}: {exc}"],
                league=liga,
                start_time=start_time,
            )


def cmd_analyze(args: argparse.Namespace) -> int:
    """Jalankan analisis slate Tahap 2b+3: tarik data + validasi (SOP langkah 2-3).

    Input slate divalidasi skema, ditolak bila ``confirmed_by_user`` bukan
    true (SOP langkah 1). Laga dikelompokkan per sport; tanggal per sport
    = tanggal start_time laga pertama sport itu — NBA dikonversi ke tanggal
    US Eastern (stats.nba.com memakai tanggal Eastern). Bila laga lintas
    tanggal, laga di tanggal lain tetap diproses — pencocokan berbasis tim,
    tapi pencarian jadwal memakai tanggal sport itu. Untuk laga NBA,
    setelah build_slate, dilampirkan artefak "nba_analysis" per laga
    (Tahap 3 Langkah 2; gagal total -> artefak minimal DATA_INCOMPLETE,
    slate tetap jalan). Untuk laga bola, dilampirkan artefak
    "soccer_analysis" per laga (Tahap 3 Langkah 5; gagal total ->
    artefak minimal DATA_INCOMPLETE). Satu file output JSON ditulis
    (default ``out/analysis_<slate_id>.json``) + ringkasan tercetak.
    """
    try:
        slate = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: tidak bisa membaca {args.input}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(slate, dict):
        print("error: slate harus berupa objek JSON", file=sys.stderr)
        return 1
    error = _validate_slate(slate)
    if error is not None:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if slate.get("confirmed_by_user") is not True:
        print(
            "error: slate belum dikonfirmasi user (confirmed_by_user bukan "
            "true) — analisis tidak jalan (SOP langkah 1: tampilkan tabel "
            "dulu, tunggu user balas 'ok')",
            file=sys.stderr,
        )
        return 1

    from ingest.slate import build_slate

    by_sport: dict[str, list[dict]] = {}
    for entry in slate["matches"]:
        by_sport.setdefault(entry["sport"], []).append(entry)

    all_matches: list[dict] = []
    summary = {
        "matches": 0,
        "ok": 0,
        "data_incomplete": 0,
        "hold": 0,
        "model_only": 0,
        "tanpa_xg": 0,
    }
    odds_api = {"calls": 0, "credits_used": 0}
    skip_odds_api = bool(getattr(args, "tanpa_odds_api", False))
    for sport, entries in sorted(by_sport.items()):
        date = _slate_date(entries[0], sport)
        if date is None:
            print(
                f"error: start_time laga pertama {sport} tidak bisa dibaca: "
                f"{entries[0].get('start_time')!r}",
                file=sys.stderr,
            )
            return 1
        league = _league_code(entries[0].get("league"))
        try:
            if sport == "football":
                result = build_slate(
                    sport,
                    date,
                    matches=entries,
                    league=league,
                    skip_odds_api=skip_odds_api,
                )
            else:
                result = build_slate(
                    sport, date, matches=entries, skip_odds_api=skip_odds_api
                )
        except (ValueError, RuntimeError) as exc:
            print(f"error: gagal merakit slate {sport}: {exc}", file=sys.stderr)
            return 1
        if sport == "nba":
            _lampirkan_nba_analysis(result["matches"], entries, date)
        if sport == "football":
            _lampirkan_soccer_analysis(result["matches"], entries, date)
        all_matches.extend(result["matches"])
        for key in summary:
            summary[key] += result["summary"][key]
        odds_api["calls"] += result["odds_api"]["calls"]
        odds_api["credits_used"] += result["odds_api"]["credits_used"]

    from datetime import UTC, datetime

    output = {
        "slate_id": slate["slate_id"],
        "generated_at": datetime.now(UTC).isoformat(),
        "matches": all_matches,
        "summary": summary,
        "odds_api": odds_api,
    }
    out_path = Path(
        args.out or (REPO_ROOT / "out" / f"analysis_{slate['slate_id']}.json")
    )
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"error: tidak bisa menulis {out_path}: {exc}", file=sys.stderr)
        return 1
    print(
        f"slate {slate['slate_id']}: {summary['matches']} laga "
        f"(OK {summary['ok']}, HOLD {summary['hold']}, "
        f"DATA_INCOMPLETE {summary['data_incomplete']})"
    )
    print(
        f"MODEL_ONLY: {summary['model_only']} laga | "
        f"TANPA_XG: {summary['tanpa_xg']} laga"
    )
    print(
        f"Odds API: {odds_api['calls']} panggilan, "
        f"{odds_api['credits_used']} kredit"
    )
    for entry in all_matches:
        labels = ",".join(entry.get("labels") or [])
        label_text = f" [{labels}]" if labels else ""
        nba = entry.get("nba_analysis")
        nba_text = (
            f" | nba_analysis: {nba['status']}"
            if isinstance(nba, dict) and isinstance(nba.get("status"), str)
            else ""
        )
        bola = entry.get("soccer_analysis")
        bola_text = (
            f" | soccer_analysis: {bola['status']}"
            if isinstance(bola, dict) and isinstance(bola.get("status"), str)
            else ""
        )
        print(
            f"  {entry['match_id']}: {entry['status']}{label_text}"
            f"{nba_text}{bola_text}"
        )
    print(f"output: {out_path}")
    return 0


def _ambil_nba_analysis(
    data: dict, match_id: str | None
) -> tuple[dict | None, str | None]:
    """Ambil artefak nba_analysis dari file input recheck.

    Menerima (a) artefak nba_analysis langsung (format ==
    "nba_analysis") atau (b) output cli.py analyze (ada kunci
    "matches"; artefak ada di kunci "nba_analysis" tiap entri laga).
    match_id: bila diisi, laga yang dicari; bila kosong dan hanya
    satu laga punya artefak, laga itu yang dipakai. Mengembalikan
    (artefak, None) atau (None, pesan error).
    """
    if not isinstance(data, dict):
        return None, "file analisis harus berupa objek JSON"
    if data.get("format") == "nba_analysis":
        if match_id is not None and data.get("match_id") != match_id:
            return None, (
                f"file berisi artefak {data.get('match_id')}, bukan {match_id}"
            )
        return data, None
    matches = data.get("matches")
    if not isinstance(matches, list):
        return None, (
            "file bukan artefak nba_analysis maupun output analyze "
            "(tidak ada kunci 'matches')"
        )
    punya = [
        m
        for m in matches
        if isinstance(m, dict) and isinstance(m.get("nba_analysis"), dict)
    ]
    if match_id is not None:
        for m in punya:
            if m.get("match_id") == match_id:
                return m["nba_analysis"], None
            # Terima juga match_id artefak ("DET@ATL_2026-11-22"),
            # bukan hanya match_id slate ("nba-2026-11-22-det-atl").
            inner = m.get("nba_analysis") or {}
            if inner.get("match_id") == match_id:
                return m["nba_analysis"], None
        return None, f"laga {match_id} tidak punya artefak nba_analysis di file ini"
    if len(punya) == 1:
        return punya[0]["nba_analysis"], None
    if not punya:
        return None, "tidak ada laga dengan artefak nba_analysis di file ini"
    daftar = ", ".join(m.get("match_id", "?") for m in punya)
    return (
        None,
        f"ada {len(punya)} laga dengan artefak nba_analysis ({daftar}) — "
        "sebutkan --match",
    )


def _kumpulkan_nba_analysis(
    data: dict,
) -> tuple[list[dict] | None, str | None]:
    """Kumpulkan SEMUA artefak nba_analysis dari file input (untuk racik).

    Menerima (a) artefak nba_analysis langsung (format ==
    "nba_analysis") atau (b) output cli.py analyze (ada kunci
    "matches"; artefak ada di kunci "nba_analysis" tiap entri laga).
    Mengembalikan (daftar artefak, None) atau (None, pesan error).
    """
    if not isinstance(data, dict):
        return None, "file analisis harus berupa objek JSON"
    if data.get("format") == "nba_analysis":
        return [data], None
    matches = data.get("matches")
    if not isinstance(matches, list):
        return None, (
            "file bukan artefak nba_analysis maupun output analyze "
            "(tidak ada kunci 'matches')"
        )
    punya = [
        m["nba_analysis"]
        for m in matches
        if isinstance(m, dict) and isinstance(m.get("nba_analysis"), dict)
    ]
    if not punya:
        return None, "tidak ada laga dengan artefak nba_analysis di file ini"
    return punya, None


def cmd_recheck(args: argparse.Namespace) -> int:
    """Cek ulang pra-submit satu laga NBA (Tahap 3 Langkah 2).

    Input: file JSON analisis (--analysis) — artefak nba_analysis
    langsung, atau output cli.py analyze (pilih laga dengan --match).
    Ambil data segar + putuskan GO / NO-GO via engine.recheck
    (0 kredit Odds API: recheck hanya memakai cedera + tangga
    Polymarket/jup.ag). Laporan ditulis ke --out (default
    out/recheck_<match_id>.json). Exit code: 0 = GO, 1 = NO-GO
    (laporan tetap ditulis), 2 = recheck tidak bisa berjalan
    (tidak ada laporan).
    """
    try:
        data = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: tidak bisa membaca {args.analysis}: {exc}", file=sys.stderr)
        return RECHECK_ERROR
    analysis, error = _ambil_nba_analysis(data, args.match)
    if error is not None:
        print(f"error: {error}", file=sys.stderr)
        return RECHECK_ERROR
    from config import ConfigError
    from engine import nba_analysis as nba_analysis_mod
    from engine import recheck as recheck_mod

    error = nba_analysis_mod.validate_nba_analysis(analysis)
    if error is not None:
        print(f"error: artefak nba_analysis tidak valid: {error}", file=sys.stderr)
        return RECHECK_ERROR
    try:
        fresh = recheck_mod.fetch_fresh(analysis)
        laporan = recheck_mod.decide(analysis, fresh)
    except (ValueError, OSError, ConfigError) as exc:
        print(f"error: recheck gagal: {exc}", file=sys.stderr)
        return RECHECK_ERROR
    match_id = analysis.get("match_id", "unknown")
    out_path = Path(args.out or (REPO_ROOT / "out" / f"recheck_{match_id}.json"))
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(laporan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"error: tidak bisa menulis {out_path}: {exc}", file=sys.stderr)
        return RECHECK_ERROR
    verdict = laporan.get("verdict", "?")
    resim = "ya" if laporan.get("resimulated") else "tidak"
    print(f"recheck {match_id}: {verdict} (resim: {resim})")
    for kaki in laporan.get("legs", []):
        tiket = kaki.get("ticket")
        if not tiket:
            # Laporan recheck belum membawa kunci "ticket" (kontrak
            # langkah 2); tiket diambil dari akhir leg_id
            # ("...:total_under_233.5:insurance" -> "insurance").
            leg_id = kaki.get("leg_id", "?")
            tiket = leg_id.rsplit(":", 1)[-1] if ":" in leg_id else leg_id
        garis = (
            kaki.get("new_line")
            if kaki.get("new_line") is not None
            else kaki.get("old_line")
        )
        garis_txt = f" U{garis:g}" if isinstance(garis, (int, float)) else ""
        alasan = kaki.get("reasons") or []
        alasan_txt = f" — {alasan[0]}" if alasan else ""
        print(f"  {tiket}{garis_txt}: {kaki.get('verdict')}{alasan_txt}")
    if laporan.get("action_required"):
        print(f"  yang harus diubah: {laporan['action_required']}")
    print(f"output: {out_path}")
    return 0 if verdict == "GO" else 1


def cmd_laporan(args: argparse.Namespace) -> int:
    """Laporan lengkap satu laga NBA (Tahap 3 Langkah 3).

    Input: file JSON analisis (--analysis) — artefak nba_analysis
    langsung, atau output cli.py analyze (pilih laga dengan --match).
    Laporan recheck opsional (--recheck) dilampirkan bila ada.
    Teks dicetak ke stdout atau ditulis ke --out; --json mengeluarkan
    bentuk JSON laporan. Exit code: 0 sukses, 2 = tidak bisa jalan.
    """
    try:
        data = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: tidak bisa membaca {args.analysis}: {exc}", file=sys.stderr)
        return 2
    analysis, error = _ambil_nba_analysis(data, args.match)
    if error is not None:
        print(f"error: {error}", file=sys.stderr)
        return 2
    recheck = None
    if args.recheck:
        try:
            recheck = json.loads(Path(args.recheck).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: tidak bisa membaca {args.recheck}: {exc}", file=sys.stderr)
            return 2
    from report import nba_report as nba_report_mod

    try:
        if args.json:
            hasil = nba_report_mod.render_nba_report_json(analysis, recheck)
            teks = json.dumps(hasil, ensure_ascii=False, indent=2)
        else:
            teks = nba_report_mod.render_nba_report(analysis, recheck)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    match_id = analysis.get("match_id", "unknown")
    if args.out:
        try:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(teks, encoding="utf-8")
        except OSError as exc:
            print(f"error: tidak bisa menulis {args.out}: {exc}", file=sys.stderr)
            return 2
        print(f"laporan {match_id} ditulis ke {args.out}")
        return 0
    print(teks)
    return 0


def cmd_tanya(args: argparse.Namespace) -> int:
    """Tanya-jawab soal satu laga NBA (Tahap 3 Langkah 3).

    Input: file JSON analisis (--analysis) + pertanyaan
    (Bahasa Indonesia). Jawaban berasal dari artefak analisis dan
    mesin sim — angka dari kode, bukan karangan; data tidak ada
    dijawab "tidak terverifikasi". Exit code: 0 sukses,
    2 = tidak bisa jalan.
    """
    try:
        data = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: tidak bisa membaca {args.analysis}: {exc}", file=sys.stderr)
        return 2
    analysis, error = _ambil_nba_analysis(data, args.match)
    if error is not None:
        print(f"error: {error}", file=sys.stderr)
        return 2
    from engine import qa as qa_mod

    hasil = qa_mod.answer(analysis, args.pertanyaan)
    print(hasil["answer"])
    if not hasil.get("verified", True):
        print(
            "[sebagian jawaban tidak terverifikasi — datanya tidak ada "
            "di analisis ini]",
            file=sys.stderr,
        )
    return 0


def cmd_racik(args: argparse.Namespace) -> int:
    """Racik Tiket Asuransi + Utama dari satu slate NBA (Tahap 3 Langkah 3).

    Input: file-file JSON analisis (--analysis, boleh banyak) —
    artefak nba_analysis langsung, atau output cli.py analyze.
    Laporan recheck (--recheck, boleh banyak) bersifat opsional;
    tanpa recheck, tiket mendapat peringatan jendela. Modal total
    (--stake-total, USD) wajib — peracik tidak mengarang modal.
    Hasil ditulis ke --out (default out/tickets_<tanggal>.json) +
    ringkasan tercetak. Exit code: 0 = minimal satu tiket terracik,
    1 = tidak ada tiket yang bisa diracik, 2 = tidak bisa jalan.
    """
    analyses: list[dict] = []
    for path in args.analysis:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: tidak bisa membaca {path}: {exc}", file=sys.stderr)
            return 2
        got, error = _kumpulkan_nba_analysis(data)
        if error is not None:
            print(f"error: {path}: {error}", file=sys.stderr)
            return 2
        analyses.extend(got)
    # Laga yang sama dari dua file dihitung sekali (kemunculan pertama).
    dilihat: set[str] = set()
    unik: list[dict] = []
    for art in analyses:
        mid = art.get("match_id")
        if isinstance(mid, str) and mid in dilihat:
            print(
                f"catatan: laga {mid} muncul dua kali — dipakai sekali",
                file=sys.stderr,
            )
            continue
        if isinstance(mid, str):
            dilihat.add(mid)
        unik.append(art)
    analyses = unik
    if not analyses:
        print("error: tidak ada artefak nba_analysis", file=sys.stderr)
        return 2
    rechecks: list[dict] | None = None
    if args.recheck:
        rechecks = []
        for path in args.recheck:
            try:
                lap = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"error: tidak bisa membaca {path}: {exc}", file=sys.stderr)
                return 2
            if not isinstance(lap, dict) or lap.get("format") != "nba_recheck":
                print(f"error: {path} bukan laporan nba_recheck", file=sys.stderr)
                return 2
            rechecks.append(lap)
    from config import ConfigError, load_playstyle
    from engine import nba_analysis as nba_analysis_mod
    from engine import ticket_composer as composer_mod

    for art in analyses:
        error = nba_analysis_mod.validate_nba_analysis(art)
        if error is not None:
            print(
                f"error: artefak {art.get('match_id', '?')} tidak valid: {error}",
                file=sys.stderr,
            )
            return 2
    try:
        cfg = load_playstyle()
        hasil = composer_mod.compose_tickets(
            analyses, rechecks, cfg, stake_total=args.stake_total
        )
    except (ValueError, ConfigError) as exc:
        print(f"error: peracik gagal: {exc}", file=sys.stderr)
        return 2
    tanggal = analyses[0].get("game_date") or datetime.date.today().isoformat()
    out_path = Path(args.out or (REPO_ROOT / "out" / f"tickets_{tanggal}.json"))
    payload = {
        "format": "tickets",
        "game_date": tanggal,
        "insurance": hasil.get("insurance"),
        "insurance_reason": hasil.get("insurance_reason"),
        # v18.1 Patch #2 fallback (b): opsi berlabel, BUKAN tiket —
        # dicatat di file racikan supaya tidak hilang (tidak pernah
        # dicatat ke ledger sebagai tiket: tanpa ticket_id/type).
        "insurance_fallback_option": hasil.get("insurance_fallback_option"),
        "main": hasil.get("main"),
        "main_reason": hasil.get("main_reason"),
        "warnings": hasil.get("warnings", []),
        "summary": hasil.get("summary", ""),
    }
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"error: tidak bisa menulis {out_path}: {exc}", file=sys.stderr)
        return 2
    print(hasil.get("summary", ""))
    for warn in hasil.get("warnings", []):
        print(f"PERINGATAN: {warn}")
    print(f"output: {out_path}")
    return 0 if (hasil.get("insurance") or hasil.get("main")) else 1


def cmd_audit(args: argparse.Namespace) -> int:
    """Audit tiket sebelum pasang (Tahap 4 — insiden DEN 23 Nov 2026).

    Input: file tiket (--ticket) — objek tiket tunggal, pasangan
    {"insurance","main"}, atau {"tickets": [...]} — plus 1+ file
    analisis (--analysis, boleh banyak; laga yang sama di dua file:
    artefak terbaru menang). P_model tiap kaki dihitung dari sim
    markets artefak analisis; angka p_model di file tiket (Gemini)
    diabaikan untuk verdict. File tiket TIDAK diubah; hasil audit
    ditulis ke --output (default
    out/audit_<nama-tiket>_<tanggal>.json) + teks tercetak.
    Exit code: 0 = semua tiket GO, 1 = ada tiket NO-GO (laporan
    tetap ditulis), 2 = audit tidak bisa berjalan.
    """
    try:
        dokumen_tiket = json.loads(Path(args.ticket).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: tidak bisa membaca {args.ticket}: {exc}", file=sys.stderr)
        return 2
    dokumen_analisis: list[dict] = []
    for path in args.analysis:
        try:
            dokumen_analisis.append(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            # Fail-closed: file analisis rusak -> audit batal, bukan
            # jalan dengan data sebagian (kaki bisa lolos diam-diam).
            print(f"error: tidak bisa membaca {path}: {exc}", file=sys.stderr)
            return 2
    from config import ConfigError, load_playstyle
    from engine import ticket_audit as audit_mod

    try:
        cfg = load_playstyle()
        hasil = audit_mod.audit_tickets(dokumen_tiket, dokumen_analisis, cfg)
    except ConfigError as exc:
        print(f"error: config tidak bisa dibaca: {exc}", file=sys.stderr)
        return 2
    if hasil.get("error"):
        print(f"error: {hasil['error']}", file=sys.stderr)
        return 2
    hasil["ticket_file"] = args.ticket
    hasil["analysis_files"] = list(args.analysis)
    tanggal = (
        dokumen_tiket.get("game_date") if isinstance(dokumen_tiket, dict) else None
    ) or datetime.date.today().isoformat()
    nama_tiket = Path(args.ticket).stem
    out_path = Path(
        args.output or (REPO_ROOT / "out" / f"audit_{nama_tiket}_{tanggal}.json")
    )
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(hasil, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"error: tidak bisa menulis {out_path}: {exc}", file=sys.stderr)
        return 2
    print(audit_mod.render_audit_text(hasil))
    print(f"output: {out_path}")
    return 0 if all(t.get("verdict") == "GO" for t in hasil["tickets"]) else 1


def _normalisasi_match_id(match_id: str) -> str:
    """Normalisasi match_id ke bentuk artefak "AWAY@HOME_YYYY-MM-DD".

    Menerima bentuk artefak (dipakai apa adanya, huruf besar) dan
    bentuk slate ("nba-2026-11-22-det-atl" -> "DET@ATL_2026-11-22",
    urutan away-home sama seperti perbaikan --match langkah 3).
    Bentuk lain dikembalikan apa adanya (huruf besar).
    """
    import re

    teks = str(match_id or "").strip()
    cocok = re.match(
        r"^[A-Za-z]+-(\d{4}-\d{2}-\d{2})-([A-Za-z]{3})-([A-Za-z]{3})$",
        teks,
    )
    if cocok:
        tanggal, away, home = cocok.groups()
        return f"{away.upper()}@{home.upper()}_{tanggal}"
    return teks.upper()


def _baca_tiket_pantau(data: object) -> tuple[list[dict] | None, str | None]:
    """Kumpulkan tiket dari file racik (3 bentuk yang didukung).

    (a) objek tiket tunggal (ada kunci "legs"); (b) output racik
    {"insurance": {...}|null, "main": {...}|null}; (c)
    {"tickets": [...]}. Mengembalikan (daftar tiket, None) atau
    (None, pesan error). Tiket tanpa "legs" list -> error.
    """
    if not isinstance(data, dict):
        return None, "file tiket harus berupa objek JSON"
    if isinstance(data.get("legs"), list):
        tiket = [data]
    elif isinstance(data.get("tickets"), list):
        tiket = data["tickets"]
    elif "insurance" in data or "main" in data:
        tiket = [t for t in (data.get("insurance"), data.get("main")) if t]
    else:
        return None, (
            "file tiket tidak dikenali: butuh objek tiket tunggal "
            "(kunci 'legs'), pasangan {'insurance','main'}, atau "
            "{'tickets': [...]}"
        )
    if not tiket:
        return None, "file tiket tidak berisi tiket apa pun"
    for t in tiket:
        if not isinstance(t, dict) or not isinstance(t.get("legs"), list):
            return None, "tiket tidak valid: tiap tiket butuh kunci 'legs'"
        if not t["legs"]:
            return None, "tiket tidak valid: ada tiket tanpa kaki"
    return tiket, None


def _tanggal_dari_match_id(match_id: str) -> str | None:
    """Tanggal (YYYY-MM-DD) dari akhir match_id artefak; None bila tidak ada."""
    import re

    cocok = re.search(r"_(\d{4}-\d{2}-\d{2})$", str(match_id or ""))
    if not cocok:
        return None
    try:
        datetime.date.fromisoformat(cocok.group(1))
    except ValueError:
        return None
    return cocok.group(1)


def _musim_bbref(tanggal: str) -> int:
    """Tahun musim-berakhir BBRef dari tanggal laga (YYYY-MM-DD).

    Musim NBA berjalan Okt–Jun: laga Jul–Des -> tahun+1 (misal
    2026-11-22 -> 2027), laga Jan–Jun -> tahun itu (2027-03-01 ->
    2027). Bulan Jul–Sep tidak ada laga; dipakai tahun+1 (musim
    berikutnya).
    """
    tahun = int(tanggal[:4])
    bulan = int(tanggal[5:7])
    return tahun + 1 if bulan >= 7 else tahun


def _muat_median_pra_laga(
    paths: list[str],
) -> tuple[dict[str, float], list[str]]:
    """Median total pra-laga per match_id dari 1+ file analisis.

    Median = simulation.score_distribution.total.median tiap artefak
    nba_analysis. Laga yang sama di dua file: artefak TERBARU menang
    (dedup di ``engine/ticket_audit.py`` — satu implementasi dengan
    audit tiket). File yang tidak bisa dibaca dilewati + dicatat
    (pantau tetap jalan dengan file yang bisa dibaca); artefak tanpa
    median dilewati + dicatat; tidak ditebak.
    """
    from engine import ticket_audit as audit_mod

    catatan: list[str] = []
    dokumen: list[dict] = []
    for path in paths:
        try:
            dokumen.append(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            catatan.append(f"file analisis {path} tidak bisa dibaca ({exc}) — dilewati")
    artefak, cat_kumpul = audit_mod.kumpulkan_analisis(dokumen)
    catatan.extend(cat_kumpul)
    median, cat_median = audit_mod.median_pra_laga(artefak)
    catatan.extend(cat_median)
    return median, catatan


def cmd_pantau(args: argparse.Namespace) -> int:
    """Pantau tiket yang sedang berjalan (Tahap 3 Langkah 4).

    Input: file tiket (--ticket) — objek tiket tunggal, pasangan
    {"insurance","main"} output racik, atau {"tickets": [...]}.
    File analisis (--analysis) opsional, boleh banyak: median total
    pra-laga dipakai sebagai pembanding laju skor (metode proyeksi
    "blend"); laga yang sama di dua file memakai artefak terbaru.
    Laga tanpa median di artefak mana pun tetap diproyeksi dengan
    laju live saja ("live_rate_only") + dicatat per laga.
    Alur: baca tiket -> tentukan tanggal dari match_id kaki (atau
    --date) -> fetch scoreboard per tanggal (ingest/live_nba.py,
    pekerja A) -> fetch stats per laga berjalan/selesai ->
    fetch baseline tembakan BBRef -> evaluasi tiap tiket
    (engine/live_status.py, pekerja B) + deteksi anomali per laga
    (engine/live_anomaly.py) -> cetak teks Indonesia ke stdout,
    tulis JSON lengkap bila --output diberi.
    Exit code: 0 = pantauan berhasil, tidak ada kaki TERANCAM/KALAH/
    DATA_INCOMPLETE dan tidak ada anomali; 1 = ada kaki TERANCAM/
    KALAH/DATA_INCOMPLETE atau anomali (laporan tetap tampil);
    2 = pantauan tidak bisa berjalan (file tiket tidak ada/tidak
    valid, semua feed gagal, atau modul pekerja A/B belum ada).
    DATA_INCOMPLETE ikut menaikkan exit code (keputusan koordinator
    langkah 4): kaki yang tidak bisa dinilai bukan berarti aman —
    fail-closed. WASPADA/PUSH tidak menaikkan exit code (WASPADA
    masih diproyeksikan menang; keduanya terlihat jelas di teks).

    KONTRAK INTEGRASI (terverifikasi dari modul pekerja A/B):
    - ingest.live_nba.fetch_live_games(tanggal) -> FetchResult,
      data = list LiveGame.
    - ingest.live_nba.fetch_game_stats(espn_game_id) -> FetchResult,
      data = {abbr: {fg3_made, fg3_attempted, ft_made, ft_attempted}}
      (ditulis ke game["stats"]).
    - engine.live_status.project_final_total(live_game,
      pregame_median_total, cfg) -> dict.
    - engine.live_status.evaluate_ticket(tiket, live_games_by_match,
      pregame_medians, cfg) -> dict {ticket_id, type, status, legs,
      notes}; kaki yang laganya tidak ada di scoreboard dinilai
      DATA_INCOMPLETE oleh modul itu (tiket penuh diteruskan).
    - engine.live_status.render_live_status(hasil_tiket,
      anomalies_by_match) -> str (per tiket; anomali ikut tampil).
    Status kaki yang memicu exit 1: TERANCAM, KALAH, atau
    DATA_INCOMPLETE (tidak diketahui ≠ aman — fail-closed).
    """
    try:
        data = json.loads(Path(args.ticket).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: tidak bisa membaca {args.ticket}: {exc}", file=sys.stderr)
        return 2
    tiket, error = _baca_tiket_pantau(data)
    if error is not None:
        print(f"error: {error}", file=sys.stderr)
        return 2
    assert tiket is not None

    # -- Filter --match (bentuk artefak maupun slate). --
    if args.match:
        target = _normalisasi_match_id(args.match)
        tiket_terfilter: list[dict] = []
        for t in tiket:
            kaki = [
                k
                for k in t["legs"]
                if _normalisasi_match_id(k.get("match_id", "")) == target
            ]
            if kaki:
                salinan = dict(t)
                salinan["legs"] = kaki
                tiket_terfilter.append(salinan)
        if not tiket_terfilter:
            print(
                f"error: laga {target} tidak ada di file tiket",
                file=sys.stderr,
            )
            return 2
        tiket = tiket_terfilter

    # -- Tanggal: --date menang; kalau tidak, dari match_id kaki. --
    catatan: list[str] = []
    if args.date:
        try:
            datetime.date.fromisoformat(args.date)
        except ValueError:
            print(
                f"error: --date harus YYYY-MM-DD: {args.date!r}",
                file=sys.stderr,
            )
            return 2
        tanggal_list = [args.date]
    else:
        tanggal_set: set[str] = set()
        for t in tiket:
            for k in t["legs"]:
                tgl = _tanggal_dari_match_id(k.get("match_id", ""))
                if tgl:
                    tanggal_set.add(tgl)
        if not tanggal_set:
            print(
                "error: tidak ada tanggal yang bisa diambil dari "
                "match_id kaki — pakai --date YYYY-MM-DD",
                file=sys.stderr,
            )
            return 2
        tanggal_list = sorted(tanggal_set)

    # -- Median pra-laga (opsional; boleh banyak file, artefak terbaru
    # menang; file rusak -> dilewati, lanjut dengan yang bisa dibaca).
    # args.analysis bisa berupa str (pemanggil langsung, satu file)
    # atau list (parser nargs="+"). --
    median: dict[str, float] = {}
    if args.analysis:
        paths = args.analysis if isinstance(args.analysis, list) else [args.analysis]
        median, cat_an = _muat_median_pra_laga(paths)
        catatan.extend(cat_an)
    else:
        catatan.append("tanpa file analisis — tanpa median pra-laga")

    # -- Modul pekerja A/B (lazy import; belum ada -> exit 2). --
    try:
        from ingest import live_nba as live_nba_mod
    except ImportError:
        print(
            "error: modul ingest/live_nba.py belum ada (pekerja A) — "
            "pantauan tidak bisa berjalan",
            file=sys.stderr,
        )
        return 2
    try:
        from engine import live_status as live_status_mod
    except ImportError:
        print(
            "error: modul engine/live_status.py belum ada (pekerja B) — "
            "pantauan tidak bisa berjalan",
            file=sys.stderr,
        )
        return 2
    from engine import live_anomaly as anomaly_mod
    from ingest import bbref as bbref_mod

    try:
        from config import ConfigError, load_playstyle

        cfg = load_playstyle()
    except ConfigError as exc:
        print(f"error: config tidak bisa dibaca: {exc}", file=sys.stderr)
        return 2
    if not isinstance(cfg.get("live"), dict):
        print(
            "error: section 'live:' belum ada di config/playstyle.yaml "
            "(pekerja B) — pantauan tidak bisa berjalan",
            file=sys.stderr,
        )
        return 2

    # -- Scoreboard per tanggal. --
    live: dict[str, dict] = {}
    feed_gagal = 0
    for tanggal in tanggal_list:
        try:
            hasil = live_nba_mod.fetch_live_games(tanggal)
        except Exception as exc:  # noqa: BLE001 - feed gagal != crash
            catatan.append(f"scoreboard {tanggal} gagal: {exc}")
            feed_gagal += 1
            continue
        if not hasil.ok:
            catatan.append(
                f"scoreboard {tanggal} gagal: {hasil.error or 'tanpa alasan'}"
            )
            feed_gagal += 1
            continue
        for game in hasil.data or []:
            if isinstance(game, dict) and isinstance(game.get("match_id"), str):
                live[game["match_id"]] = game
    if feed_gagal == len(tanggal_list):
        print(
            "error: semua feed scoreboard gagal — pantauan tidak bisa " "berjalan",
            file=sys.stderr,
        )
        return 2

    # -- Stats per laga berjalan/selesai (ditulis ke game["stats"]). --
    for mid, game in list(live.items()):
        if game.get("status") not in ("berjalan", "selesai"):
            continue
        espn_id = game.get("espn_game_id")
        if not espn_id:
            catatan.append(f"{mid}: tanpa espn_game_id — stats tidak diambil")
            continue
        try:
            ringkas = live_nba_mod.fetch_game_stats(espn_id)
        except Exception as exc:  # noqa: BLE001 - stats gagal != fatal
            catatan.append(f"{mid}: stats gagal ({exc}) — stats tidak ada")
            continue
        if not ringkas.ok or not isinstance(ringkas.data, dict):
            catatan.append(
                f"{mid}: stats gagal "
                f"({ringkas.error or 'tanpa alasan'}) — stats tidak ada"
            )
            continue
        game["stats"] = ringkas.data

    # -- Baseline tembakan BBRef (gagal -> anomali 3PT/FT dilewati). --
    baselines: dict = {}
    try:
        musim = _musim_bbref(min(tanggal_list))
        dasar = bbref_mod.fetch_team_shooting_baselines(season=musim)
        if dasar.ok:
            baselines = anomaly_mod.index_baselines(dasar.data)
        else:
            catatan.append(
                f"baseline BBRef gagal ({dasar.error or 'tanpa alasan'}) "
                "— anomali 3PT/FT dilewati"
            )
    except Exception as exc:  # noqa: BLE001 - baseline gagal != fatal
        catatan.append(f"baseline BBRef gagal ({exc}) — anomali dilewati")

    # -- Proyeksi + anomali per laga yang ada di tiket. --
    match_dipantau: list[str] = []
    for t in tiket:
        for k in t["legs"]:
            mid = k.get("match_id")
            if isinstance(mid, str) and mid not in match_dipantau:
                match_dipantau.append(mid)
    hilang: list[str] = [m for m in match_dipantau if m not in live]
    for m in hilang:
        catatan.append(f"{m}: tidak ada di scoreboard — kakinya DATA_INCOMPLETE")
    # Laga tanpa median pra-laga: proyeksinya tetap live-rate-only
    # (fail-closed, tidak ditebak) + dicatat eksplisit.
    for m in match_dipantau:
        if m not in median:
            catatan.append(
                f"{m}: tanpa median pra-laga — proyeksi hanya memakai "
                "laju skor live (live_rate_only)"
            )

    proyeksi: dict[str, dict] = {}
    anomali: dict[str, list[dict]] = {}
    dilewati: dict[str, list[dict]] = {}
    for mid in match_dipantau:
        game = live.get(mid)
        if game is None:
            continue
        try:
            proyeksi[mid] = live_status_mod.project_final_total(
                game, median.get(mid), cfg
            )
        except Exception as exc:  # noqa: BLE001 - proyeksi gagal != fatal
            catatan.append(f"{mid}: proyeksi gagal ({exc})")
            proyeksi[mid] = {}
        try:
            anoms, skip = anomaly_mod.detect_anomalies(
                game, baselines, proyeksi[mid], cfg
            )
        except ValueError as exc:
            catatan.append(f"{mid}: deteksi anomali gagal ({exc})")
            anoms, skip = [], []
        anomali[mid] = anoms
        dilewati[mid] = skip

    # -- Evaluasi tiap tiket (tiket penuh; kaki tanpa laga dinilai
    # DATA_INCOMPLETE oleh evaluate_ticket). --
    evaluasi: list[dict] = []
    for t in tiket:
        try:
            ev = live_status_mod.evaluate_ticket(t, live, median, cfg)
        except Exception as exc:  # noqa: BLE001 - evaluasi gagal
            print(
                f"error: evaluasi tiket {t.get('ticket_id')} gagal: {exc}",
                file=sys.stderr,
            )
            return 2
        if not isinstance(ev, dict):
            print(
                f"error: evaluate_ticket mengembalikan {type(ev).__name__}, "
                "bukan dict",
                file=sys.stderr,
            )
            return 2
        evaluasi.append(ev)

    ada_terancam = any(
        leg.get("status") in ("TERANCAM", "KALAH")
        for ev in evaluasi
        for leg in ev.get("legs", []) or []
    ) or any(ev.get("status") in ("TERANCAM", "KALAH") for ev in evaluasi)
    ada_tidak_dinilai = any(
        leg.get("status") == "DATA_INCOMPLETE"
        for ev in evaluasi
        for leg in ev.get("legs", []) or []
    )
    ada_anomali = any(anomali.get(m) for m in match_dipantau)

    # -- Teks ke stdout: render_live_status per tiket (anomali ikut
    # tampil di dalamnya) + pemeriksaan anomali yang dilewati. --
    for ev in evaluasi:
        print(live_status_mod.render_live_status(ev, anomali))
    for mid in match_dipantau:
        # Laga belum mulai: semua pemeriksaan trivially dilewati (0 menit
        # berjalan) — tidak usah dicetak; render sudah menulis
        # "belum mulai". Laga berjalan/selesai: yang dilewati dicetak
        # agar user tahu pemeriksaan apa yang tidak bisa dilakukan.
        if (
            mid in live
            and live[mid].get("status") in ("berjalan", "selesai")
            and dilewati.get(mid)
        ):
            print(anomaly_mod.format_anomalies([], dilewati.get(mid, []), mid))
    for cat in catatan:
        print(f"catatan: {cat}")
    if ada_terancam or ada_anomali or ada_tidak_dinilai:
        print(
            "PERINGATAN: ada kaki TERANCAM/KALAH, anomali, atau kaki "
            "yang tidak bisa dinilai — cek di atas"
        )

    # -- JSON lengkap bila --output diberi. --
    if args.output:
        laporan = {
            "format": "live_monitor",
            "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "ticket_file": args.ticket,
            "dates": tanggal_list,
            "match_filter": (_normalisasi_match_id(args.match) if args.match else None),
            "tickets": evaluasi,
            "matches": {
                mid: {
                    "status": live[mid].get("status"),
                    "home_abbr": live[mid].get("home_abbr"),
                    "away_abbr": live[mid].get("away_abbr"),
                    "home_score": live[mid].get("home_score"),
                    "away_score": live[mid].get("away_score"),
                    "period": live[mid].get("period"),
                    "clock_display": live[mid].get("clock_display"),
                    "projected_total": proyeksi.get(mid, {}).get("projected_total"),
                    "projection_method": proyeksi.get(mid, {}).get("method"),
                    "pregame_median_total": median.get(mid),
                }
                for mid in match_dipantau
                if mid in live
            },
            "anomalies": {mid: anomali.get(mid, []) for mid in match_dipantau},
            "skipped": {mid: dilewati.get(mid, []) for mid in match_dipantau},
            "missing_matches": hilang,
            "notes": catatan,
            "has_threatened_leg": ada_terancam,
            "has_anomaly": ada_anomali,
            "has_data_incomplete": ada_tidak_dinilai,
        }
        try:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(laporan, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            print(
                f"error: tidak bisa menulis {args.output}: {exc}",
                file=sys.stderr,
            )
            return 2
        print(f"output: {args.output}")
    return 1 if (ada_terancam or ada_anomali or ada_tidak_dinilai) else 0


def _parse_leg_results(raw: list[str] | None) -> dict[str, str]:
    """Ubah ['leg-01=WIN', ...] menjadi {leg_id: hasil}. Format salah -> error."""
    parsed: dict[str, str] = {}
    for item in raw or []:
        if "=" not in item:
            raise ValueError(f"format --leg-result salah: {item!r} (pakai ID=HASIL)")
        leg_id, result = item.split("=", 1)
        parsed[leg_id.strip()] = result.strip().upper()
    return parsed


def cmd_log(args: argparse.Namespace) -> int:
    """Catat tiket dari file JSON, atau selesaikan tiket PENDING."""
    conn = store.connect(args.db)
    if args.settle:
        try:
            leg_results = _parse_leg_results(args.leg_result)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        try:
            profit = store.settle_ticket(
                conn,
                args.settle,
                args.result,
                leg_results=leg_results,
                cashout_amount=args.cashout_amount,
            )
        except store.LedgerError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        saved = store.get_ticket(conn, args.settle)
        extra = ""
        if saved and saved.get("multiplier_original") is not None:
            extra = (
                f" (pengali dihitung ulang {saved['multiplier_original']}"
                f"x -> {saved['multiplier']:.4f}x karena kaki VOID/PUSH)"
            )
        print(
            f"tiket {args.settle} diselesaikan: {saved['result']}, "
            f"untung/rugi ${profit:+.2f}{extra}"
        )
        return 0

    if not args.file:
        print(
            "error: pakai --file ticket.json atau --settle <id> --result ...",
            file=sys.stderr,
        )
        return 1
    try:
        ticket = json.loads(Path(args.file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: tidak bisa membaca {args.file}: {exc}", file=sys.stderr)
        return 1
    try:
        ticket_id = store.log_ticket(conn, ticket)
    except store.LedgerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    saved = store.get_ticket(conn, ticket_id)
    profit = saved["profit_loss"] if saved else None
    profit_text = f"${profit:+.2f}" if profit is not None else "pending"
    extra = ""
    if saved and saved.get("multiplier_original") is not None:
        extra = (
            f", pengali awal {saved['multiplier_original']}x "
            f"(dihitung ulang karena kaki VOID/PUSH)"
        )
    print(
        f"tiket {ticket_id} dicatat ({saved['type']}, "
        f"modal ${saved['stake']:.2f}, pengali {saved['multiplier']}x, "
        f"hasil {saved['result']}, untung/rugi {profit_text}{extra})"
    )
    return 0


def cmd_recap(args: argparse.Namespace) -> int:
    """Tampilkan rekap untung/rugi ledger (teks atau JSON)."""
    conn = store.connect(args.db)
    data = recap_mod.compute_recap(conn)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(recap_mod.format_recap(data))
    return 0


# Fixture demo/tes perintah belajar (DATA SINTETIS — bukan hasil nyata).
FIXTURE_SINTETIS_BELAJAR = (
    REPO_ROOT / "tests" / "fixtures" / "sintetis_belajar_kaki.json"
)


def _modul_belajar():
    """Muat modul Langkah 6 (learning/calibration/proposals) defensif.

    Mengembalikan (learning, calibration, proposals, belum_tersedia):
    modul yang tidak ada di disk jadi None dan namanya dicatat di
    belum_tersedia. Pemeriksaan memakai find_spec — error DI DALAM
    modul yang ada (mis. ImportError dari dependensinya) tetap raise,
    supaya bug tidak tertutup diam-diam oleh jalur "belum ada".
    engine.learning wajib (tanpa itu ringkasan tidak bisa dibangun);
    calibration/proposals opsional (bagiannya ditandai belum tersedia
    di laporan).
    """
    belum_tersedia: list[str] = []

    def _coba(nama: str):
        if importlib.util.find_spec(nama) is None:
            belum_tersedia.append(nama)
            return None
        return importlib.import_module(nama)

    learning_mod = _coba("engine.learning")
    calibration_mod = _coba("engine.calibration")
    proposals_mod = _coba("engine.proposals")
    return learning_mod, calibration_mod, proposals_mod, belum_tersedia


def bangun_data_belajar(
    outcomes,
    sumber_data: str,
    *,
    modul=None,
    n_settled: int | None = None,
    n_pending: int = 0,
    n_dikeluarkan: int = 0,
    n_hasil_tidak_dikenal: int | None = None,
    n_tiket: int | None = None,
    pesan: str | None = None,
    catatan_sumber: str | None = None,
):
    """Rakit dict data laporan belajar dari daftar outcome record.

    outcomes: daftar dict kontrak OUTCOME RECORD (engine/learning.py).
    sumber_data: "ledger" | "replay" | "sintetis". modul: tuple dari
    _modul_belajar (None = muat sendiri). Hitungan n_* bila tidak
    diberikan dihitung dari outcomes (n_settled) atau 0.
    Dipakai cmd_belajar dan scripts/laporan_belajar_replay.py.
    Mengembalikan (data, error): error str bila engine.learning belum
    tersedia (data None); bila tidak, error None.
    """
    if modul is None:
        modul = _modul_belajar()
    learning_mod, calibration_mod, proposals_mod, hilang = modul
    if learning_mod is None:
        return None, "modul engine/learning.py belum tersedia"
    outcomes = [o for o in (outcomes or []) if isinstance(o, dict)]
    settled = [
        o
        for o in outcomes
        if o.get("settled") is True and o.get("result") in (True, False)
    ]
    ada_data = len(settled) > 0
    ringkasan = learning_mod.ringkasan_keseluruhan(outcomes) if ada_data else None
    per_pasar = learning_mod.ringkasan_per_pasar(outcomes) if ada_data else None
    kalibrasi_w = (
        calibration_mod.rekomendasi_w(outcomes) if calibration_mod is not None else None
    )
    usulan = (
        proposals_mod.hasilkan_usulan(per_pasar or {}, outcomes)
        if proposals_mod is not None
        else None
    )
    data = {
        "sumber_data": sumber_data,
        "ada_data": ada_data,
        "pesan": pesan,
        "ringkasan": ringkasan,
        "ringkasan_per_pasar": per_pasar,
        "kalibrasi_w": kalibrasi_w,
        "usulan": usulan,
        "n_settled": n_settled if n_settled is not None else len(settled),
        "n_pending": n_pending,
        "n_dikeluarkan": n_dikeluarkan,
        "n_hasil_tidak_dikenal": n_hasil_tidak_dikenal,
        "n_tiket": n_tiket,
        "dibuat_pada": datetime.datetime.now(datetime.UTC).isoformat(),
        "catatan_sumber": catatan_sumber,
        "modul_belum_tersedia": hilang,
    }
    return data, None


def _muat_fixture_sintetis():
    """Baca fixture kaki sintetis -> (outcomes, error)."""
    try:
        dokumen = json.loads(FIXTURE_SINTETIS_BELAJAR.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"tidak bisa membaca fixture sintetis: {exc}"
    kaki = dokumen.get("kaki") if isinstance(dokumen, dict) else None
    if not isinstance(kaki, list) or not kaki:
        return None, "fixture sintetis tidak berisi daftar kaki"
    return kaki, None


def cmd_belajar(args: argparse.Namespace) -> int:
    """Laporan belajar dari hasil tercatat (Tahap 3 Langkah 6).

    Default: baca ledger (--db), bangun ringkasan Brier per pasar +
    kalibrasi bobot w + usulan lewat modul Langkah 6, cetak laporan.
    Bila belum ada data -> laporan "belum ada data", exit 0.
    --contoh-sintetis memakai fixture sintetis (laporan berlabel
    SINTETIS). --keluaran menulis laporan ke file (dan mencetak
    pathnya). Exit code: 0 sukses (termasuk belum ada data),
    2 = tidak bisa jalan.
    """
    from report import learning_report as learning_report_mod

    modul = _modul_belajar()
    learning_mod = modul[0]
    if learning_mod is None:
        print(
            "error: modul engine/learning.py belum tersedia — laporan "
            "belajar belum bisa dibuat",
            file=sys.stderr,
        )
        return 2
    if args.contoh_sintetis:
        outcomes, error = _muat_fixture_sintetis()
        if error is not None:
            print(f"error: {error}", file=sys.stderr)
            return 2
        data, error = bangun_data_belajar(outcomes, "sintetis", modul=modul)
    else:
        hasil = learning_mod.muat_hasil_ledger(args.db)
        data, error = bangun_data_belajar(
            hasil.get("outcomes") or [],
            "ledger",
            modul=modul,
            n_settled=hasil.get("n_settled"),
            n_pending=hasil.get("n_pending") or 0,
            n_dikeluarkan=hasil.get("n_dikeluarkan") or 0,
            n_hasil_tidak_dikenal=hasil.get("n_hasil_tidak_dikenal"),
            n_tiket=hasil.get("n_tiket"),
            pesan=hasil.get("pesan"),
        )
    if error is not None:
        print(f"error: {error}", file=sys.stderr)
        return 2
    teks = learning_report_mod.render_laporan_belajar(data)
    if args.keluaran:
        try:
            out_path = Path(args.keluaran)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(teks, encoding="utf-8")
        except OSError as exc:
            print(f"error: tidak bisa menulis {args.keluaran}: {exc}", file=sys.stderr)
            return 2
        print(f"laporan belajar ditulis ke {args.keluaran}")
        return 0
    print(teks)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Bangun parser argumen CLI (analyze / recheck / laporan / tanya / racik / audit / pantau / log / recap / belajar)."""
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="muse-parlay-analyst — satu pintu masuk (Blueprint §10).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="analisis slate (Tahap 2b: tarik data)")
    p_analyze.add_argument("--input", required=True, help="file slate.json")
    p_analyze.add_argument(
        "--out",
        default=None,
        help="file output JSON (default: out/analysis_<slate_id>.json)",
    )
    p_analyze.add_argument(
        "--tanpa-odds-api",
        action="store_true",
        help="jangan panggil The Odds API sama sekali (0 kredit; pembanding "
        "sportsbook dilewati, Kalshi tetap dicoba)",
    )
    p_analyze.set_defaults(func=cmd_analyze)

    p_recheck = sub.add_parser(
        "recheck",
        help="cek ulang pra-submit satu laga NBA (Tahap 3 Langkah 2)",
    )
    p_recheck.add_argument(
        "--analysis",
        required=True,
        help="file JSON analisis: artefak nba_analysis langsung, atau "
        "output cli.py analyze",
    )
    p_recheck.add_argument(
        "--match",
        default=None,
        help="match_id laga yang dicek (wajib bila file berisi lebih "
        "dari satu laga dengan artefak nba_analysis)",
    )
    p_recheck.add_argument(
        "--out",
        default=None,
        help="file output JSON (default: out/recheck_<match_id>.json)",
    )
    p_recheck.set_defaults(func=cmd_recheck)

    p_laporan = sub.add_parser(
        "laporan",
        help="laporan lengkap satu laga NBA (Tahap 3 Langkah 3)",
    )
    p_laporan.add_argument(
        "--analysis",
        required=True,
        help="file JSON analisis: artefak nba_analysis langsung, atau "
        "output cli.py analyze",
    )
    p_laporan.add_argument(
        "--match",
        default=None,
        help="match_id laga yang dilaporkan (wajib bila file berisi lebih "
        "dari satu laga dengan artefak nba_analysis)",
    )
    p_laporan.add_argument(
        "--recheck",
        default=None,
        help="file laporan nba_recheck untuk dilampirkan (opsional)",
    )
    p_laporan.add_argument(
        "--out",
        default=None,
        help="file output (default: cetak ke stdout)",
    )
    p_laporan.add_argument(
        "--json", action="store_true", help="keluarkan JSON, bukan teks"
    )
    p_laporan.set_defaults(func=cmd_laporan)

    p_tanya = sub.add_parser(
        "tanya",
        help="tanya-jawab soal satu laga NBA (Tahap 3 Langkah 3)",
    )
    p_tanya.add_argument(
        "--analysis",
        required=True,
        help="file JSON analisis: artefak nba_analysis langsung, atau "
        "output cli.py analyze",
    )
    p_tanya.add_argument(
        "--match",
        default=None,
        help="match_id laga yang ditanya (wajib bila file berisi lebih "
        "dari satu laga dengan artefak nba_analysis)",
    )
    p_tanya.add_argument("pertanyaan", help="pertanyaan dalam Bahasa Indonesia")
    p_tanya.set_defaults(func=cmd_tanya)

    p_racik = sub.add_parser(
        "racik",
        help="racik Tiket Asuransi + Utama dari satu slate NBA " "(Tahap 3 Langkah 3)",
    )
    p_racik.add_argument(
        "--analysis",
        required=True,
        nargs="+",
        help="file JSON analisis (artefak nba_analysis atau output "
        "analyze), boleh banyak",
    )
    p_racik.add_argument(
        "--recheck",
        default=None,
        nargs="+",
        help="file laporan nba_recheck, boleh banyak (opsional)",
    )
    p_racik.add_argument(
        "--stake-total",
        required=True,
        type=float,
        help="total modal kedua tiket (USD) — wajib",
    )
    p_racik.add_argument(
        "--out",
        default=None,
        help="file output JSON (default: out/tickets_<tanggal>.json)",
    )
    p_racik.set_defaults(func=cmd_racik)

    p_audit = sub.add_parser(
        "audit",
        help="audit tiket sebelum pasang (Tahap 4 — insiden DEN 23 Nov 2026)",
    )
    p_audit.add_argument(
        "--ticket",
        required=True,
        help="file tiket: objek tiket tunggal, pasangan "
        "{'insurance','main'}, atau {'tickets': [...]}",
    )
    p_audit.add_argument(
        "--analysis",
        required=True,
        nargs="+",
        help="file JSON analisis (artefak nba_analysis atau output "
        "analyze), boleh banyak; laga yang sama memakai artefak terbaru",
    )
    p_audit.add_argument(
        "--output",
        default=None,
        help="file output JSON (default: " "out/audit_<nama-tiket>_<tanggal>.json)",
    )
    p_audit.set_defaults(func=cmd_audit)

    p_pantau = sub.add_parser(
        "pantau",
        help="pantau tiket yang sedang berjalan (Tahap 3 Langkah 4)",
    )
    p_pantau.add_argument(
        "--ticket",
        required=True,
        help="file tiket: objek tiket tunggal, pasangan "
        "{'insurance','main'} output racik, atau {'tickets': [...]}",
    )
    p_pantau.add_argument(
        "--analysis",
        default=None,
        nargs="+",
        help="file JSON analisis (artefak nba_analysis atau output "
        "analyze) untuk median total pra-laga, boleh banyak "
        "(laga yang sama memakai artefak terbaru; opsional)",
    )
    p_pantau.add_argument(
        "--match",
        default=None,
        help="hanya pantau satu laga (match_id artefak "
        "'DET@ATL_2026-11-22' atau slate 'nba-2026-11-22-det-atl')",
    )
    p_pantau.add_argument(
        "--date",
        default=None,
        help="tanggal scoreboard YYYY-MM-DD (default: dari match_id kaki)",
    )
    p_pantau.add_argument(
        "--output",
        default=None,
        help="file output JSON laporan lengkap (opsional)",
    )
    p_pantau.set_defaults(func=cmd_pantau)

    p_log = sub.add_parser("log", help="catat / selesaikan tiket (Tahap 1)")
    p_log.add_argument("--file", help="file ticket.json (sesuai skema)")
    p_log.add_argument("--settle", metavar="TICKET_ID", help="selesaikan tiket PENDING")
    p_log.add_argument(
        "--result",
        choices=["WIN", "LOSS", "PUSH", "VOID", "CASHOUT"],
        help="hasil untuk --settle",
    )
    p_log.add_argument(
        "--cashout-amount",
        type=float,
        default=None,
        help="jumlah cashout USD (wajib bila --result CASHOUT)",
    )
    p_log.add_argument(
        "--leg-result",
        action="append",
        default=None,
        metavar="LEG_ID=HASIL",
        help="hasil per kaki, boleh diulang: --leg-result leg-01=WIN",
    )
    _db_arg(p_log)
    p_log.set_defaults(func=cmd_log)

    p_recap = sub.add_parser("recap", help="rekap untung/rugi (Tahap 1)")
    p_recap.add_argument(
        "--json", action="store_true", help="keluarkan JSON, bukan teks"
    )
    _db_arg(p_recap)
    p_recap.set_defaults(func=cmd_recap)

    p_belajar = sub.add_parser(
        "belajar",
        help="laporan belajar dari hasil tercatat (Tahap 3 Langkah 6)",
    )
    p_belajar.add_argument(
        "--keluaran",
        default=None,
        help="file output laporan (default: cetak ke stdout)",
    )
    p_belajar.add_argument(
        "--contoh-sintetis",
        action="store_true",
        help="demo dengan fixture kaki sintetis (laporan berlabel "
        "SINTETIS — bukan hasil nyata)",
    )
    _db_arg(p_belajar)
    p_belajar.set_defaults(func=cmd_belajar)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Titik masuk CLI; mengembalikan exit code (0 sukses, 1 error, 2 belum tersedia)."""
    args = build_parser().parse_args(argv)
    if args.command == "log" and args.settle and not args.result:
        print(
            "error: --settle butuh --result WIN|LOSS|PUSH|VOID|CASHOUT", file=sys.stderr
        )
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
