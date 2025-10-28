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

ddef get_schedule(d: date, tz_name: str = DEFAULT_TZ) -> List[Game]:
    """Hakee päivän ottelut Flashscoresta; jos tyhjää, käyttää NHL-schedule fallbackia."""
    # 1) JSON-feed
    try:
        games = try_json_feed(d, tz_name)
        if games:
            return games
    except Exception:
        pass
    # 2) HTML-scrape
    try:
        games = fallback_html_scrape(d, tz_name)
        if games:
            return games
    except Exception:
        pass
    # 3) NHL virallinen aikataulu (fallback, erityisesti iltaisin huomiselle)
    try:
        return nhl_schedule_fallback(d, tz_name)
    except Exception:
        return []

def nhl_schedule_fallback(d: date, tz_name: str) -> List[Game]:
    """
    Hakee päivän ottelut NHL:n virallisesta schedule-APIsta:
    https://api-web.nhle.com/v1/schedule/YYYY-MM-DD
    Palauttaa listan Game-olioita. Käytetään vain, jos Flashscore ei anna dataa.
    """
    import pytz
    from datetime import datetime

    url = f"https://api-web.nhle.com/v1/schedule/{d.isoformat()}"
    resp = _get(url)  # käyttää samaa _get():iä (User-Agent + timeout)
    data = resp.json()

    games = []
    hel = pytz.timezone("Europe/Helsinki")
    # Rakenne: {"gameWeek": [{"games":[ ... ]}, ...]}
    for week in data.get("gameWeek", []):
        for g in week.get("games", []):
            try:
                home_name = (
                    g.get("homeTeam", {}).get("name", {}).get("default")
                    or g.get("homeTeam", {}).get("commonName", {}).get("default")
                    or g.get("homeTeam", {}).get("abbrev")
                    or "HOME"
                )
                away_name = (
                    g.get("awayTeam", {}).get("name", {}).get("default")
                    or g.get("awayTeam", {}).get("commonName", {}).get("default")
                    or g.get("awayTeam", {}).get("abbrev")
                    or "AWAY"
                )
                # startTimeUTC esim. "2025-10-29T23:00:00Z"
                start_utc = g.get("startTimeUTC") or g.get("startTimeUTCUnix")
                if isinstance(start_utc, (int, float)):
                    dt_utc = datetime.utcfromtimestamp(int(start_utc))
                else:
                    dt_utc = datetime.fromisoformat(start_utc.replace("Z", "+00:00"))
                time_local = dt_utc.astimezone(hel).strftime("%H:%M")
                games.append(Game(home=home_name, away=away_name, time_local=time_local))
            except Exception:
                continue
    return games
# -------------------------------------------------------------------------------

