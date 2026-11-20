"""Pencocokan nama tim antar sumber (murni, tanpa network).

Kalshi memakai nama KOTA untuk NBA ("Charlotte") dan nama SINGKAT untuk
bola ("Newcastle"), sementara jup.ag memakai nama JULUKAN ("Hornets") dan
nama RESMI ("Newcastle United FC"). Modul ini menormalisasi nama tim agar
pasar dari sumber berbeda bisa dicocokkan.

Di-port dari probes/kalshi_sports.py (probe 2a lanjutan) dengan satu
perbedaan: pemetaan julukan/alias dipilih lewat parameter `sport`
("nba"/"football"), bukan lewat fungsi terpisah per olahraga.
"""

from __future__ import annotations

import re

# Kata pengisi nama klub yang dibuang saat normalisasi (sebagai kata utuh,
# di posisi mana pun): FC/CF/SC/AFC/RC/RCD = bentuk badan klub; "club";
# "united" (Kalshi menulis "Newcastle", bukan "Newcastle United");
# "de" (preposisi Spanyol/Portugal: "Celta de Vigo" = "Celta Vigo");
# "and" ("Brighton and Hove Albion" di Odds API = "Brighton & Hove
# Albion" di ESPN — "&" hilang sebagai tanda baca, "and" harus hilang
# juga agar keduanya sama).
_FILLER_WORDS = {"fc", "cf", "sc", "afc", "rc", "rcd", "club", "united", "de", "and"}

# Julukan NBA -> nama kota versi Kalshi (30 tim; Kalshi membedakan dua tim
# Los Angeles dengan "Los Angeles L" / "Los Angeles C"). Dipakai HANYA
# untuk pencocokan NBA (tidak untuk bola — "Spurs" juga nama Tottenham).
NBA_NICKNAME_TO_CITY = {
    "hawks": "atlanta",
    "celtics": "boston",
    "nets": "brooklyn",
    "hornets": "charlotte",
    "bulls": "chicago",
    "cavaliers": "cleveland",
    "mavericks": "dallas",
    "nuggets": "denver",
    "pistons": "detroit",
    "warriors": "golden state",
    "rockets": "houston",
    "pacers": "indiana",
    "clippers": "los angeles c",
    "lakers": "los angeles l",
    "grizzlies": "memphis",
    "heat": "miami",
    "bucks": "milwaukee",
    "timberwolves": "minnesota",
    "pelicans": "new orleans",
    "knicks": "new york",
    "thunder": "oklahoma city",
    "magic": "orlando",
    "76ers": "philadelphia",
    "suns": "phoenix",
    "trail blazers": "portland",
    "kings": "sacramento",
    "spurs": "san antonio",
    "raptors": "toronto",
    "jazz": "utah",
    "wizards": "washington",
}

# Tricode NBA -> kota versi Kalshi (30 tim; tricode terverifikasi di
# ingest/stats_nba.py TEAM_TRICODES dari LineScore live). Dipakai untuk
# sumber yang menulis singkatan tim, mis. Rotowire ("LAL").
NBA_TRICODE_TO_CITY = {
    "atl": "atlanta",
    "bos": "boston",
    "bkn": "brooklyn",
    "cha": "charlotte",
    "chi": "chicago",
    "cle": "cleveland",
    "dal": "dallas",
    "den": "denver",
    "det": "detroit",
    "gsw": "golden state",
    "hou": "houston",
    "ind": "indiana",
    "lac": "los angeles c",
    "lal": "los angeles l",
    "mem": "memphis",
    "mia": "miami",
    "mil": "milwaukee",
    "min": "minnesota",
    "nop": "new orleans",
    "nyk": "new york",
    "okc": "oklahoma city",
    "orl": "orlando",
    "phi": "philadelphia",
    "phx": "phoenix",
    "por": "portland",
    "sac": "sacramento",
    "sas": "san antonio",
    "tor": "toronto",
    "uta": "utah",
    "was": "washington",
}

# Julukan NBA terurut dari yang terpanjang (untuk pencocokan sufiks nama
# lengkap: "trail blazers" harus dicek sebelum kata tunggal).
_NBA_NICKNAMES_BY_LENGTH = tuple(sorted(NBA_NICKNAME_TO_CITY, key=len, reverse=True))

# Alias bola (nama ternormalisasi -> bentuk kanonik nama lengkap).
# "athletic"/"espanyol": judul event Kalshi yang teramati di slate probe.
# Sisanya: bentuk pendek FPL (fantasy.premierleague.com, daftar 20 tim
# terverifikasi live 2026-11-20) -> nama lengkap fixtures/ESPN/Jupiter.
# Tanpa alias ini, cedera FPL untuk tim-tim itu tidak pernah masuk ke
# laganya (mis. "Man City" vs "Manchester City").
FOOTBALL_ALIASES = {
    "athletic": "bilbao",
    "espanyol barcelona": "espanyol",
    "brighton": "brighton hove albion",
    "man city": "manchester city",
    "man utd": "manchester",
    "nott m forest": "nottingham forest",
    "spurs": "tottenham hotspur",
    "tottenham": "tottenham hotspur",
}


def normalize_team(name: str, sport: str) -> str:
    """Normalisasi nama tim ke bentuk kanonik versi Kalshi.

    Huruf kecil, buang tanda baca + kata pengisi ("FC", "United", "de",
    ...). Untuk NBA, tiga bentuk diterima dan dipetakan ke kota yang
    sama: julukan ("Hornets" -> "charlotte"), tricode ("LAL" ->
    "los angeles l", sumber: Rotowire), dan nama lengkap
    ("Los Angeles Lakers" / "LA Clippers" / "Golden State Warriors" ->
    kota via julukan di akhir nama; sumber: stats.nba.com, ESPN,
    PDF cedera, Basketball-Reference). Untuk bola, alias yang teramati
    diterapkan ("Athletic" -> "bilbao"). "City" TIDAK dibuang agar
    Manchester City tetap berbeda dari Manchester United ("manchester").
    Sport lain: normalisasi dasar saja.
    """
    if not isinstance(name, str):
        return ""
    text = name.lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    tokens = [t for t in text.split() if t not in _FILLER_WORDS]
    normalized = " ".join(tokens)
    if sport == "nba":
        if normalized in NBA_NICKNAME_TO_CITY:
            return NBA_NICKNAME_TO_CITY[normalized]
        if normalized in NBA_TRICODE_TO_CITY:
            return NBA_TRICODE_TO_CITY[normalized]
        # Nama lengkap: julukan adalah akhir nama ("Los Angeles Lakers"
        # -> "lakers"; "Portland Trail Blazers" -> "trail blazers").
        # Sufiks terpanjang dicek dulu agar julukan dua kata menang.
        for nickname in _NBA_NICKNAMES_BY_LENGTH:
            if normalized.endswith(" " + nickname):
                return NBA_NICKNAME_TO_CITY[nickname]
        return normalized
    if sport == "football":
        return FOOTBALL_ALIASES.get(normalized, normalized)
    return normalized


def teams_match(a: str, b: str, sport: str) -> bool:
    """Apakah dua nama tim merujuk ke tim yang sama (untuk sport itu)?

    Membandingkan hasil normalize_team; nama kosong tidak pernah cocok.
    """
    normalized_a = normalize_team(a, sport)
    normalized_b = normalize_team(b, sport)
    return bool(normalized_a) and normalized_a == normalized_b


def parse_vs_title(title: str) -> tuple[str, str] | None:
    """Pecah judul "Tim A vs. Tim B" jadi (tim_a, tim_b) mentah.

    Mengembalikan None bila judul bukan format lawan-vs-lawan.
    Urutan tim TIDAK diartikan di sini — konvensi kandang/tandang
    berbeda per olahraga (NBA: tandang dulu; bola: kandang dulu) dan
    ditangani pemanggil.
    """
    if not isinstance(title, str):
        return None
    for sep in (" vs. ", " vs ", " v "):
        if sep in title:
            left, right = title.split(sep, 1)
            return (left.strip(), right.strip())
    return None
