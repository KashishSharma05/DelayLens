"""DelayLens: the website.

Run with:  streamlit run app/site.py

Every page reads small CSV files in app/data/ (written by src/export.py),
so the site needs no database. Fresh data arrives whenever the pipeline
runs and the files are updated.
"""

import streamlit as st
from dotenv import load_dotenv

from common import SITE_NAME, apply_style, last_updated

load_dotenv()  # locally the AI key comes from .env; on the hosted site it comes from the site's secrets

st.set_page_config(page_title=f"{SITE_NAME} · Indian flight delays", page_icon="✈️", layout="wide")
apply_style()

pages = {
    "": [
        st.Page("views/home.py", title="Home", icon="🏠", default=True),
        st.Page("views/chat.py", title=f"Ask {SITE_NAME}", icon="💬"),
    ],
    "Flights": [
        st.Page("views/search.py", title="Search a flight", icon="🔎"),
        st.Page("views/board.py", title="Departure board", icon="🛫"),
    ],
    "Statistics": [
        st.Page("views/stats.py", title="Airlines & airports", icon="📊"),
        st.Page("views/patterns.py", title="When delays happen", icon="🕒"),
        st.Page("views/weather.py", title="Weather impact", icon="🌧️"),
    ],
    "Daily": [st.Page("views/daily.py", title="Daily log & news", icon="🗞️")],
}

st.sidebar.caption(f"Data last updated\n\n**{last_updated()}**")
st.navigation(pages).run()
