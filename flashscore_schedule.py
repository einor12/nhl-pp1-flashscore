import requests, json
from datetime import date
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List

DEFAULT_TZ = "Europe/Helsinki"

@dataclass
class Game:
    home: str
    away: str
    time_local: str

def _get(url: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp

def _fmt_fs_date(d: date) -> List[str]:
    """Palauttaa Flashscoren hyväksymät päivämäärämuodot"""
    return [d.strftime("%Y-%m-%d"), d.strftime("%Y%m%d")]

def try_json_feed(d: date, tz_name: str) -> List[Game]:
    d_variants = _fmt_fs_date(d)
    urls = [
        f"https://d.flashscore.com/x/feed/f_1_hockey_usa_nhl?d={d}"
        for d in d_variants
    ] + [
        f"https://d.flashscore.com/x/feed/f_1_hockey_usa_nhl_{d}"
        for d in d_variants
    ]
    for url in urls:
        try:
            resp = _get(url)
            text = resp.text.strip()
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                start = text.find("{"); end = text.rfind("}")
                if start != -1 and end != -1:
                    data = json.loads(text[start:end + 1])
                else:
                    continue
            break
        except Exception:
            data = None
            continue

    if not data:
        return []

    games = []
    for g in data.get("events", []):
        try:
            games.append(
                Game(
                    home=g["home"]["name"],
                    away=g["away"]["name"],
                    time_local=g.get("startTime", "??:??"),
                )
            )
        except Exception:
            continue
    return games

def fallback_html_scrape(d: date, tz_name: str) -> List[Game]:
    d_variants = _fmt_fs_date(d)
    urls = [
        f"https://www.flashscore.com/hockey/usa/nhl/?d={d}"
        for d in d_variants
    ]
    for url in urls:
        try:
            page = _get(url)
            if page.text:
                break
        except Exception:
            page = None
            continue

    if not page:
        return []

    soup = BeautifulSoup(page.text, "lxml")
    games = []
    for match in soup.select(".event__match"):
        home = match.select_one(".event__participant--home")
        away = match.select_one(".event__participant--away")
        time = match.select_one(".event__time")
        if home and away:
            games.append(Game(home.text.strip(), away.text.strip(), time.text.strip() if time else "?"))
    return games

def get_schedule(d: date, tz_name: str = DEFAULT_TZ) -> List[Game]:
    """Hakee päivän ottelut Flashscoresta"""
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
