# flashscore_schedule.py
# -*- coding: utf-8 -*-
"""
Flashscore-otteluohjelma NHL:lle päiväkohtaisesti.
- Ensin yritetään kevyt JSON/feeds (A); jos epäonnistuu, fallback HTML-scrape (B).
- Palauttaa listan Game-dictejä: {home_name, away_name, start_utc, start_local, source}
- Aikavyöhykkeet normalisoidaan: start_utc ISO, start_local ISO (Europe/Helsinki).
- Robustit retryt (tenacity).

HUOM. Flashscore-sisältö on Flashscoren omaa aineistoa. Tämä koodi on henkilökohtaiseen analyysiin.
Noudata aina Flashscoren ehtoja; vältä liiallista kuormitusta.
"""

from __future__ import annotations

from typing import List, TypedDict
from datetime import datetime, date
import json
import pytz
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

DEFAULT_TZ = "Europe/Helsinki"
# --- TIME HELPERS: MM:SS <-> seconds -----------------------------------------
def mmss_to_seconds(s: str) -> int:
    """
    Muuntaa merkkijonon 'MM:SS' kokonaissekunneiksi.
    Palauttaa 0 jos arvo puuttuu tai formaatti on väärä.
    """
    try:
        if not s or s in ("", "0", "00:00", "--"):
            return 0
        parts = str(s).strip().split(":")
        if len(parts) != 2:
            return 0
        m, sec = int(parts[0]), int(parts[1])
        return max(0, m * 60 + sec)
    except Exception:
        return 0


def seconds_to_mmss(n: int) -> str:
    """
    Muuntaa sekunnit 'MM:SS' -muotoon.
    """
    try:
        n = int(n)
        if n < 0:
            n = 0
        m, s = divmod(n, 60)
        return f"{m:02d}:{s:02d}"
    except Exception:
        return "00:00"
# -----------------------------------------------------------------------------


def mmss_to_seconds(s: str) -> int:
    """
    Muuntaa merkkijonon 'MM:SS' kokonaissekunneiksi.
    Palauttaa 0 jos arvo puuttuu tai formaatti on väärä.
    """
    try:
        if not s or s in ("", "0", "00:00", "--"):
            return 0
        parts = str(s).strip().split(":")
        if len(parts) != 2:
            return 0
        m, sec = int(parts[0]), int(parts[1])
        return max(0, m * 60 + sec)
    except Exception:
        return 0


def seconds_to_mmss(n: int) -> str:
    """
    Muuntaa sekunnit 'MM:SS' -muotoon.
    """
    try:
        n = int(n)
        if n < 0:
            n = 0
        m, s = divmod(n, 60)
        return f"{m:02d}:{s:02d}"
    except Exception:
        return "00:00"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PP1-Targets/1.0; +https://example.com)"
}

class Game(TypedDict):
    home_name: str
    away_name: str
    start_utc: str   # ISO 8601
    start_local: str # ISO 8601 Europe/Helsinki
    source: str      # "flashscore-json" / "flashscore-html"


def to_local_iso(utc_dt: datetime, tz_name: str) -> str:
    hel = pytz.timezone(tz_name)
    return utc_dt.astimezone(hel).replace(microsecond=0).isoformat()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
def _get(url: str, params=None) -> requests.Response:
    r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r


def try_json_feed(d: date, tz_name: str) -> List[Game]:
    url = "https://d.flashscore.com/x/feed/f_1_hockey_usa_nhl"
    resp = _get(url)
    text = resp.text.strip()
    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            data = json.loads(text[start:end+1])
        else:
            raise

    games: List[Game] = []
    candidates = []
    for key in ("events", "matches", "data", "E"):
        if isinstance(data, dict) and key in data and isinstance(data[key], list):
            candidates = data[key]
            break
    if not candidates:
        if isinstance(data, list):
            candidates = data

    target_day = d.isoformat()

    for ev in candidates:
        home = (ev.get("homeTeam", {}) or {}).get("name") or ev.get("home") or ev.get("homeName")
        away = (ev.get("awayTeam", {}) or {}).get("name") or ev.get("away") or ev.get("awayName")
        if not home or not away:
            continue

        ts = ev.get("startTimestamp") or ev.get("startTime") or ev.get("time")
        utc_dt = None
        if isinstance(ts, (int, float)):
            utc_dt = datetime.utcfromtimestamp(int(ts)).replace(tzinfo=pytz.UTC)
        elif isinstance(ts, str) and ts.isdigit():
            utc_dt = datetime.utcfromtimestamp(int(ts)).replace(tzinfo=pytz.UTC)
        elif isinstance(ts, str):
            try:
                utc_dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(pytz.UTC)
            except Exception:
                pass
        if utc_dt is None:
            continue

        local_iso = to_local_iso(utc_dt, tz_name)
        local_day = local_iso[:10]
        if local_day != target_day:
            continue

        games.append(Game(
            home_name=home,
            away_name=away,
            start_utc=utc_dt.replace(microsecond=0).isoformat(),
            start_local=local_iso,
            source="flashscore-json"
        ))

    return games


def fallback_html_scrape(d: date, tz_name: str) -> List[Game]:
    url = "https://www.flashscore.com/hockey/usa/nhl/"
    r = _get(url)
    soup = BeautifulSoup(r.text, "lxml")
    games: List[Game] = []
    hel = pytz.timezone(tz_name)
    target_day = d.isoformat()

    rows = soup.select(".event__match, .event__match--scheduled, .event__match--live")
    for row in rows:
        home_el = row.select_one(".event__participant--home")
        away_el = row.select_one(".event__participant--away")
        if not home_el or not away_el:
            continue
        home = home_el.get_text(strip=True)
        away = away_el.get_text(strip=True)
        if not home or not away:
            continue

        ts_attr = row.get("data-start-time") or row.get("data-time-ts") or row.get("data-timestamp")
        utc_dt = None
        if ts_attr and str(ts_attr).isdigit():
            utc_dt = datetime.utcfromtimestamp(int(ts_attr)).replace(tzinfo=pytz.UTC)
        if utc_dt is None:
            continue

        local_iso = hel.normalize(utc_dt.astimezone(hel)).replace(microsecond=0).isoformat()
        if local_iso[:10] != target_day:
            continue

        games.append(Game(
            home_name=home,
            away_name=away,
            start_utc=utc_dt.replace(microsecond=0).isoformat(),
            start_local=local_iso,
            source="flashscore-html"
        ))

    return games


def get_schedule(d: date, tz_name: str = DEFAULT_TZ) -> List[Game]:
    try:
        games = try_json_feed(d, tz_name)
        if games:
            return games
    except Exception:
        pass
    try:
        return fallback_html_scrape(d, tz_name)
    except Exception:
        return []
