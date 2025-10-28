# app.py
# -*- coding: utf-8 -*-
"""
Streamlit UI (Renderiin).
Näyttää uusimman CSV-datan GitHub Raw -URLista.
"""

import os
from datetime import datetime, date
from urllib.parse import urljoin

import pandas as pd
import pytz
import requests
import streamlit as st

DEFAULT_TZ = "Europe/Helsinki"

st.set_page_config(page_title="NHL PP1 Targets", page_icon="🏒", layout="wide")
st.title("🏒 NHL PP1 -targets (Flashscore + NHL API)")
st.caption("Kausi 2025/2026 • Data päivittyy joka aamu klo 07:05 (Europe/Helsinki).")

RAW_BASE = os.getenv("GITHUB_RAW_BASE", "").rstrip("/")
if not RAW_BASE:
    st.error("Puuttuu ympäristömuuttuja GITHUB_RAW_BASE. Aseta se Renderissä (Environment).")
    st.stop()

hel = pytz.timezone(DEFAULT_TZ)
today_local = datetime.now(hel).date()

picked_date = st.date_input("Valitse päivä", value=today_local, max_value=today_local)
date_str = picked_date.isoformat()

csv_path = f"data/nhl_pp1_targets_{date_str}.csv"
xlsx_path = f"data/nhl_pp1_targets_{date_str}.xlsx"

csv_url = urljoin(RAW_BASE + "/", csv_path)
xlsx_url = urljoin(RAW_BASE + "/", xlsx_path)

def fetch_csv(url: str) -> pd.DataFrame | None:
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return None
        from io import StringIO
        return pd.read_csv(StringIO(r.text))
    except Exception:
        return None

df = fetch_csv(csv_url)

col1, col2 = st.columns([3, 2])
with col1:
    if df is None or df.empty:
        st.info("Ei dataa tälle päivälle. Ajo valmistuu yleensä klo 07 jälkeen.")
    else:
        st.subheader(f"Päivä: {date_str}")
        st.dataframe(df, use_container_width=True)

with col2:
    st.markdown("### Lataukset")
    st.markdown(f"- [CSV]({csv_url})")
    st.markdown(f"- [XLSX]({xlsx_url})")

st.caption("Huom: Flashscore-sisältö on heidän omaa aineistoaan. Käytä vain henkilökohtaiseen analyysiin.")
