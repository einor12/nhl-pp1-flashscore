# NHL PP1 Flashscore Analyzer (kausi 2025/2026)

Tämä projekti hakee päivittäin:
- Päivän NHL-ottelut Flashscoresta (JSON-feed tai HTML-scrape)
- NHL API:sta top-5 eniten alivoimalle joutuvat joukkueet (timesShorthanded)
- Ottelut, joissa nämä joukkueet pelaavat
- Vastustajien PP1-pelaajat (top-5 powerPlayTimeOnIcePerGame)
- Tallentaa tulokset `data/`-kansioon (.csv ja .xlsx)
- Lähettää Telegram-viestin päivittäin klo 07:05

## Päivittäinen ajo (GitHub Actions)
Workflow löytyy tiedostosta `.github/workflows/daily.yml`  
Ajo käynnistyy automaattisesti joka aamu klo 07:05 (Europe/Helsinki).  

Telegram-ilmoitukset konfiguroidaan GitHub Secrets -asetuksissa:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Streamlit-sovellus (Render)
Appi lukee uusimman CSV:n suoraan GitHub Raw -URLista:
