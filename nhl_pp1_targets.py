# nhl_pp1_targets.py
# -*- coding: utf-8 -*-
"""
NHL PP1 -targets päiväkohtaisesti kaudelle 2025/2026 (oletus).
- Hakee Flashscoresta päivän NHL-otteluohjelman (JSON feed -> fallback HTML-scrape).
- Hakee NHL stats API:sta top-5 timesShorthanded (TSH) joukkueet kyseiselle kaudelle.
- Etsii otteluista vastustajat, jotka kohtaavat TSH top-5 -joukkueen.
- Arvioi vastustajan PP1-kokoonpanon pelaajien PP TOI/GP (powerPlayTimeOnIcePerGame) perusteella.
- Tallentaa CSV ja XLSX: data/nhl_pp1_targets_{YYYY-MM-DD}.*
- Tulostaa lyhyen yhteenvedon konsoliin.

HUOM. Flashscore-sisältö on Flashscoren omaa aineistoa. Tämä skripti on tarkoitettu
henkilökohtaiseen analyysiin / oppimiseen. Noudata Flashscoren ehtoja.
"""

from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime, date
from typing import Dict, List, Tuple, Optional

import pandas as pd
import pytz
import requests
from dateutil import tz
from tenacity import retry, stop_after_attempt, wait_exponential

from flashscore_schedule import get_schedule, Game, seconds_to_mmss
# HTTP asetukset
HEADERS = {"User-Agent": "NHL-PP1/1.0 (+github.com/einor12/nhl-pp1-flashscore)"}
TIMEOUT = 20

from tenacity import retry, stop_after_attempt, wait_exponential
import requests, sys, os

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=6))
def http_get_json(url: str):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


# -------------------------------
# Vakioita (muokkaa turvallisesti)
# -------------------------------
DEFAULT_TZ = "Europe/Helsinki"
DEFAULT_SEASON = "20252026"  # <-- Kausi 2025/2026
NHL_API_BASE = "https://api.nhl.com"
OUTPUT_DIR = "data"

# Joitain yleisiä nimikorjauksia, jos Flashscore vs. NHL API eivät täsmää 1:1
TEAM_NAME_ALIASES = {
    # Flashscore -> NHL virallinen nimi
    "Tampa Bay Lightning": "Tampa Bay Lightning",
    "New York Rangers": "New York Rangers",
    "NY Rangers": "New York Rangers",
    "New Jersey Devils": "New Jersey Devils",
    "NJ Devils": "New Jersey Devils",
    "Vegas Golden Knights": "Vegas Golden Knights",
    "Washington Capitals": "Washington Capitals",
    "St. Louis Blues": "St Louis Blues",
    "St Louis Blues": "St Louis Blues",
    "Los Angeles Kings": "Los Angeles Kings",
    "LA Kings": "Los Angeles Kings",
    "Arizona Coyotes": "Utah Hockey Club",  # jos FS käyttää vanhaa nimeä
    "Utah HC": "Utah Hockey Club",
    "Montréal Canadiens": "Montreal Canadiens",  # aksenttivariantti
    "Montréal": "Montreal Canadiens",
}

# -------------------------------
# Pienet apurit
# -------------------------------

def normalize_team_name(name: str) -> str:
    """Yritetään mapata Flashscore-nimi NHL:n viralliseen nimeen."""
    name = name.strip()
    return TEAM_NAME_ALIASES.get(name, name)


def ensure_output_dir() -> None:
    if not os.path.isdir(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR, exist_ok=True)


def local_today(tz_name: str) -> date:
    tzinfo = pytz.timezone(tz_name)
    return datetime.now(tzinfo).date()


# -------------------------------
# HTTP apurit
# -------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PP1-Targets/1.0; +https://example.com)"
}

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
def http_get_json(url: str, params: Optional[dict] = None) -> dict:
    r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


# -------------------------------
# NHL API -kutsut
# -------------------------------

def get_all_teams_meta() -> List[dict]:
    """Palauttaa kaikki NHL-joukkueet nimineen ja teamId:ineen."""
    url = f"{NHL_API_BASE}/api/v1/teams"
    data = http_get_json(url)
    return data.get("teams", [])


def build_team_name_to_id(teams_meta: List[dict]) -> Tuple[Dict[str, int], Dict[int, str]]:
    name_to_id: Dict[str, int] = {}
    id_to_name: Dict[int, str] = {}
    for t in teams_meta:
        tid = t.get("id")
        name = t.get("name")
        if tid and name:
            name_to_id[name] = int(tid)
            id_to_name[int(tid)] = name
    return name_to_id, id_to_name


def get_top5_tsh(season: str) -> List[dict]:
    """
    Hakee kauden top-5 timesShorthanded (TSH) joukkueet.
    Endpoint:
    https://api.nhl.com/stats/rest/en/team?isAggregate=false&reportType=basic&isGame=false&reportName=teamsummary&cayenneExp=seasonId=SEASONID
    """
    url = (
        f"{NHL_API_BASE}/stats/rest/en/team?"
        "isAggregate=false&reportType=basic&isGame=false&"
        "reportName=teamsummary&cayenneExp=" + f"seasonId={season}"
    )
    data = http_get_json(url)
    rows = data.get("data", [])
    # Poimi vain relevantit kentät
    out = []
    for r in rows:
        out.append({
            "teamId": int(r.get("teamId")),
            "teamFullName": r.get("teamFullName"),
            "timesShorthanded": int(r.get("timesShorthanded", 0)),
        })
    # Lajittele TSH desc ja ota top-5
    out.sort(key=lambda x: x["timesShorthanded"], reverse=True)
    return out[:5]


def mmss_to_seconds(mmss: str) -> int:
    if not mmss or mmss == "0:00":
        return 0
    parts = mmss.split(":")
    if len(parts) != 2:
        return 0
    m, s = parts
    return int(m) * 60 + int(s)


def get_team_roster(team_id: int, season: str) -> List[dict]:
    """
    Hakee joukkueen rosterin kaudelle (kaikki rosterissa olevat).
    /api/v1/teams/{id}/roster?season=SEASONID
    """
    url = f"{NHL_API_BASE}/api/v1/teams/{team_id}/roster"
    params = {"season": season}
    data = http_get_json(url, params=params)
    return data.get("roster", [])


def get_player_pp_toi_per_game(player_id: int, season: str) -> Optional[str]:
    """
    Hakee pelaajan statsit SingleSeason -raportista ja palauttaa powerPlayTimeOnIcePerGame "MM:SS".
    /api/v1/people/{id}/stats?stats=statsSingleSeason&season=SEASONID
    """
    url = f"{NHL_API_BASE}/api/v1/people/{player_id}/stats"
    params = {"stats": "statsSingleSeason", "season": season}
    data = http_get_json(url, params=params)
    splits = (
        data.get("stats", [{}])[0]
        .get("splits", [])
    )
    if not splits:
        return None
    stat = splits[0].get("stat", {})
    return stat.get("powerPlayTimeOnIcePerGame")


def compute_pp1_candidates(team_id: int, season: str) -> List[Tuple[str, str, int, str]]:
    """
    Palauttaa listan pelaajista muodossa:
    [(name, primaryPosition, pp_toi_seconds, pp_toi_mmss), ...] lajittelun mukaan desc.
    Valitsee top-5 ilman pakotettua 3F+2D -rakennetta.
    """
    roster = get_team_roster(team_id, season)
    players_stats: List[Tuple[str, str, int, str]] = []

    for p in roster:
        person = p.get("person", {})
        pos = p.get("position", {}).get("abbreviation", "")
        pid = person.get("id")
        name = person.get("fullName")
        if not pid or not name:
            continue
        mmss = get_player_pp_toi_per_game(int(pid), season) or "0:00"
        secs = mmss_to_seconds(mmss)
        players_stats.append((name, pos, secs, mmss))

    # Järjestä PP TOI/GP desc ja ota top-5
    players_stats.sort(key=lambda x: x[2], reverse=True)
    return players_stats[:5]


# -------------------------------
# Ydinlogiikka
# -------------------------------

def build_targets(run_date: date, season: str, tz_name: str = DEFAULT_TZ) -> pd.DataFrame:
    """
    Rakentaa päivän PP1-targetit:
    - Hakee Flashscore-ottelut
    - Hakee TSH top-5
    - Etsii otteluista vastustajat ja muodostaa PP1-arvion
    Palauttaa DataFramen pyydetyillä sarakkeilla.
    """
    # 1) Otteluohjelma
    schedule: List[Game] = get_schedule(run_date, tz_name)

    # 2) TSH top-5
    tsh_top5 = get_top5_tsh(season)

    # Myös kaikki joukkueet ja name->id map
    teams_meta = get_all_teams_meta()
    name_to_id, id_to_name = build_team_name_to_id(teams_meta)

    # Rakennetaan helpoksi setti TSH-joukkueiden nimiä (NHL viralliset)
    tsh_team_ids = {t["teamId"] for t in tsh_top5}
    tsh_names = {id_to_name[tid] for tid in tsh_team_ids if tid in id_to_name}

    # 3) Käy läpi päivän ottelut ja löydä vastustajat
    #    - Jos ottelussa on mukana TSH-top5 -joukkue, kerätään vastustaja (de-dupe).
    opponents: Dict[str, Dict[str, str]] = {}  # opponent_name -> dict(plays_against, game_time_local, source)
    for g in schedule:
        home = normalize_team_name(g["home_name"])
        away = normalize_team_name(g["away_name"])
        home_is_tsh = home in tsh_names
        away_is_tsh = away in tsh_names

        if home_is_tsh and not away_is_tsh:
            opponents[away] = {
                "plays_against": home,
                "game_time_local": g["start_local"],
                "source": g["source"],
            }
        elif away_is_tsh and not home_is_tsh:
            opponents[home] = {
                "plays_against": away,
                "game_time_local": g["start_local"],
                "source": g["source"],
            }
        # Jos molemmat TSH-top5 (harvinainen): ohitetaan lisäys, koska "vastustaja" on myös tsh.
        # Jos kumpikaan ei ole TSH-top5: ei lisätä.

    # 4) Kullekin vastustajalle muodosta PP1-ehdokaslista
    rows = []
    helsinki = tz.gettz(tz_name)
    run_date_str = run_date.isoformat()
    for opponent_name, meta in opponents.items():
        # Mäpätään opponent NHL teamId:hen
        opponent_official_name = normalize_team_name(opponent_name)
        team_id = name_to_id.get(opponent_official_name)
        if not team_id:
            # Yritetään löysällä haulla: exact casefold match keys
            for k in name_to_id.keys():
                if k.casefold() == opponent_official_name.casefold():
                    team_id = name_to_id[k]
                    break
        if not team_id:
            # Ei löydy teamId, skipataan rivi, mutta kerrotaan konsolissa
            print(f"[WARN] Ei teamId:tä vastustajalle: '{opponent_name}' -> '{opponent_official_name}'")
            continue

        top5 = compute_pp1_candidates(team_id, season)
        # Muotoillaan "Nimi (POS) – PP TOI/GP mm:ss"
        pp1_str = ", ".join([f"{n} ({p}) – PP TOI/GP {mm}" for (n, p, _, mm) in top5])

        rows.append({
            "date": run_date_str,
            "opponent_team": opponent_official_name,
            "plays_against": meta["plays_against"],
            "game_time_local": meta["game_time_local"],
            "pp1_players": pp1_str,
            "source": meta["source"],
        })

    df = pd.DataFrame(rows, columns=[
        "date", "opponent_team", "plays_against", "game_time_local", "pp1_players", "source"
    ])
    return df, tsh_top5, schedule


def save_outputs(df: pd.DataFrame, run_date: date) -> Tuple[str, str]:
    ensure_output_dir()
    csv_path = os.path.join(OUTPUT_DIR, f"nhl_pp1_targets_{run_date.isoformat()}.csv")
    xlsx_path = os.path.join(OUTPUT_DIR, f"nhl_pp1_targets_{run_date.isoformat()}.xlsx")
    df.to_csv(csv_path, index=False, quoting=csv.QUOTE_MINIMAL, encoding="utf-8")
    df.to_excel(xlsx_path, index=False, engine="openpyxl")
    return csv_path, xlsx_path


def print_summary(tsh_top5: List[dict], schedule: List[Game], df: pd.DataFrame) -> None:
    print("\n=== TSH top-5 (kausi 2025/2026) ===")
    for r in tsh_top5:
        print(f"{r['teamFullName']}: TSH {r['timesShorthanded']}")
    print("\n=== Päivän ottelut (Flashscore) ===")
    for g in schedule:
        print(f"{g['start_local']}  {g['home_name']} vs {g['away_name']}  [{g['source']}]")
    print("\n=== Tulokset (PP1-targets) ===")
    if df.empty:
        print("(Ei rivejä tälle päivälle.)")
    else:
        for _, row in df.iterrows():
            print(f"{row['date']}  {row['opponent_team']} vs {row['plays_against']} @ {row['game_time_local']}")
            print(f"  PP1: {row['pp1_players']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NHL PP1 targets päivälle D")
    parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DD (oletus: tänään Europe/Helsinki)")
    parser.add_argument("--season", type=str, default=DEFAULT_SEASON, help="seasonId, esim. 20252026")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.date:
        run_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        run_date = local_today(DEFAULT_TZ)

    df, tsh_top5, schedule = build_targets(run_date, args.season, DEFAULT_TZ)
    csv_path, xlsx_path = save_outputs(df, run_date)
    print_summary(tsh_top5, schedule, df)
    print(f"\nTallennettu: {csv_path}")
    print(f"Tallennettu: {xlsx_path}")


if __name__ == "__main__":
    main()
