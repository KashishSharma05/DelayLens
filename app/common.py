"""Shared helpers for the website: data loading, styling and KPI maths."""

import os

import pandas as pd
import streamlit as st

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(APP_DIR)
DATA_DIR = os.path.join(APP_DIR, "data")

# One palette for the whole site.
INK = "#1e1b4b"       # deep indigo: headers, dark surfaces
PRIMARY = "#4f46e5"   # indigo: main bars and links
CYAN = "#06b6d4"      # accent
AMBER = "#f59e0b"     # delays
ROSE = "#f43f5e"      # cancellations, bad weather
GREEN = "#10b981"     # on time
VIOLET = "#8b5cf6"
GREY = "#94a3b8"
PALETTE = [PRIMARY, CYAN, AMBER, ROSE, GREEN, VIOLET]

# Low to high delay: calm blue, through amber, to rose.
DELAY_SCALE = ["#e0e7ff", "#a5b4fc", "#fcd34d", "#fb923c", "#f43f5e"]

SITE_NAME = "DelayLens"
TAGLINE = "See why flights run late"

# Colour of each flight status, used everywhere.
STATUS_COLOURS = {"on time": GREEN, "late": AMBER, "canceled": ROSE, "no actual time": GREY}
WEATHER_ORDER = ["dry and calm", "light rain", "rain", "strong wind", "low visibility", "thunderstorm"]
WEATHER_ICONS = {"dry and calm": "☀️", "light rain": "🌦️", "rain": "🌧️", "strong wind": "💨",
                 "low visibility": "🌫️", "thunderstorm": "⛈️"}
CAUSE_LABELS = {
    "fog_or_low_visibility": "Fog / low visibility", "rain_or_storm": "Rain or storm",
    "technical_fault": "Technical fault", "airline_operations": "Airline operations",
    "airport_or_air_traffic": "Airport / air traffic", "security_or_conflict": "Security or conflict",
    "strike": "Strike", "other": "Other",
}

DATE_COLUMNS = {
    "flights": ["flight_date", "sched_dep", "took_off", "sched_arr", "landed"],
    "airport_daily": ["flight_date"],
    "daily_summary": ["flight_date"],
    "weather_hourly": ["weather_time"],
    "news": ["published_at"],
}

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
/* set on the page root only, so icon fonts inside buttons and expanders keep working */
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] { font-family: 'Inter', -apple-system, sans-serif; }

.block-container { padding-top: 3.4rem; max-width: 1320px; }
h2, h3 { color: #1e1b4b; letter-spacing: -0.01em; }

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] { background: linear-gradient(180deg, #1e1b4b 0%, #312e81 100%); }
[data-testid="stSidebar"] * { color: #e0e7ff; }
[data-testid="stSidebarNavLink"] { border-radius: 10px; margin: 2px 6px; }
[data-testid="stSidebarNavLink"]:hover { background: rgba(255, 255, 255, 0.10); }
[data-testid="stSidebarNavLink"][aria-current="page"] { background: rgba(255, 255, 255, 0.18); }
[data-testid="stSidebarNavLink"][aria-current="page"] span { color: #ffffff; font-weight: 600; }
[data-testid="stSidebar"] [data-baseweb="select"] > div { background: rgba(255, 255, 255, 0.10); border-color: rgba(255, 255, 255, 0.25); }

/* ---------- KPI tiles: white card with a coloured top edge ---------- */
[data-testid="stMetric"] {
    background: #ffffff; border: 1px solid #e7e9f3; border-top: 4px solid #4f46e5; border-radius: 14px;
    padding: 14px 18px 12px 18px; box-shadow: 0 4px 14px rgba(30, 27, 75, 0.06);
}
[data-testid="stColumn"]:nth-of-type(2) [data-testid="stMetric"] { border-top-color: #f59e0b; }
[data-testid="stColumn"]:nth-of-type(3) [data-testid="stMetric"] { border-top-color: #06b6d4; }
[data-testid="stColumn"]:nth-of-type(4) [data-testid="stMetric"] { border-top-color: #f43f5e; }
[data-testid="stColumn"]:nth-of-type(5) [data-testid="stMetric"] { border-top-color: #10b981; }
[data-testid="stMetricLabel"] { color: #6b7280; font-weight: 500; }
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * { font-size: 1.65rem !important; font-weight: 700; color: #1e1b4b; }

/* ---------- chart and content cards ---------- */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: #ffffff; border-radius: 16px; border-color: #e7e9f3 !important;
    box-shadow: 0 4px 14px rgba(30, 27, 75, 0.06);
}
.tile-title { font-weight: 600; color: #1e1b4b; font-size: 0.98rem; margin-bottom: -2px; }

/* ---------- hero and page headers ---------- */
.hero {
    background: radial-gradient(900px 300px at 85% -20%, rgba(6, 182, 212, 0.55), transparent 60%),
                linear-gradient(120deg, #1e1b4b 0%, #4338ca 60%, #6366f1 100%);
    color: #ffffff; padding: 38px 40px; border-radius: 22px; margin-bottom: 20px;
    box-shadow: 0 14px 34px rgba(67, 56, 202, 0.28); position: relative; overflow: hidden;
}
.hero::after { content: "✈"; position: absolute; right: 44px; top: 18px; font-size: 7rem; opacity: 0.14; transform: rotate(-12deg); }
.hero h1 { color: #ffffff; font-size: 2.5rem; font-weight: 800; margin: 0 0 8px 0; padding: 0; letter-spacing: -0.02em; }
.hero p { color: #e0e7ff; font-size: 1.05rem; margin: 0; max-width: 780px; line-height: 1.55; }
.hero .tag { display: inline-block; background: rgba(255, 255, 255, 0.16); border: 1px solid rgba(255, 255, 255, 0.25);
             border-radius: 999px; padding: 4px 14px; font-size: 0.74rem; font-weight: 600; margin-bottom: 14px; letter-spacing: 0.08em; }
.page-header {
    background: linear-gradient(120deg, #1e1b4b 0%, #4338ca 100%); color: #ffffff; padding: 18px 24px;
    border-radius: 16px; margin-bottom: 16px; box-shadow: 0 8px 22px rgba(67, 56, 202, 0.20);
}
.page-header .title { font-size: 1.45rem; font-weight: 700; letter-spacing: -0.01em; }
.page-header .subtitle { font-size: 0.9rem; color: #c7d2fe; margin-top: 2px; }

/* ---------- feature cards on the home page: the whole card is a link ---------- */
a.feature-link, a.feature-link:hover, a.feature-link:visited { text-decoration: none !important; display: block; }
.feature {
    position: relative; height: 175px; padding: 20px 20px 16px 20px; border-radius: 20px; color: #ffffff; cursor: pointer;
    margin-bottom: 14px;
    box-shadow: 0 8px 20px rgba(30, 27, 75, 0.14); transition: transform 0.18s ease, box-shadow 0.18s ease; overflow: hidden;
}
.feature::before {  /* soft glow in the corner */
    content: ""; position: absolute; right: -40px; top: -40px; width: 140px; height: 140px; border-radius: 50%;
    background: rgba(255, 255, 255, 0.16);
}
.feature:hover { transform: translateY(-7px); box-shadow: 0 18px 36px rgba(30, 27, 75, 0.28); }
.feature .icon { width: 46px; height: 46px; border-radius: 14px; display: flex; align-items: center; justify-content: center;
                 font-size: 1.4rem; margin-bottom: 14px; background: rgba(255, 255, 255, 0.22); }
.feature .name { font-weight: 700; color: #ffffff; font-size: 1.08rem; margin-bottom: 6px; }
.feature .text { color: rgba(255, 255, 255, 0.88); font-size: 0.86rem; line-height: 1.5; }
.feature .arrow { position: absolute; right: 18px; bottom: 14px; font-size: 1.25rem; color: #ffffff; opacity: 0.6;
                  transition: transform 0.18s ease, opacity 0.18s ease; }
.feature:hover .arrow { transform: translateX(6px); opacity: 1; }
.feature.violet { background: linear-gradient(140deg, #1e1b4b 0%, #6d28d9 70%, #a855f7 100%); }
.feature.indigo { background: linear-gradient(140deg, #4338ca 0%, #6366f1 100%); }
.feature.cyan   { background: linear-gradient(140deg, #0891b2 0%, #06b6d4 60%, #22d3ee 100%); }
.feature.amber  { background: linear-gradient(140deg, #f59e0b 0%, #f97316 100%); }
.feature.rose   { background: linear-gradient(140deg, #e11d48 0%, #f43f5e 55%, #fb7185 100%); }
.feature.green  { background: linear-gradient(140deg, #059669 0%, #10b981 60%, #34d399 100%); }

/* ---------- airport cards on the home page ---------- */
.airport-band { margin: -4px 0 10px 0; padding: 12px 16px; border-radius: 12px; color: #ffffff; font-weight: 700; font-size: 1.15rem; }
.airport-band span { font-weight: 500; opacity: 0.85; font-size: 0.85rem; margin-left: 6px; }

/* ---------- departure board ---------- */
.board-wrap { max-height: 540px; overflow-y: auto; border-radius: 16px; box-shadow: 0 10px 28px rgba(30, 27, 75, 0.22); }
table.board { width: 100%; border-collapse: collapse; font-size: 0.86rem; background: #14122e; color: #e0e7ff; }
table.board th { position: sticky; top: 0; background: #1e1b4b; color: #a5b4fc; text-align: left; padding: 11px 14px;
                 font-weight: 600; font-size: 0.74rem; letter-spacing: 0.07em; text-transform: uppercase; }
table.board td { padding: 9px 14px; border-top: 1px solid rgba(165, 180, 252, 0.10); white-space: nowrap; }
table.board tr:nth-child(even) td { background: rgba(255, 255, 255, 0.025); }
table.board tr:hover td { background: rgba(99, 102, 241, 0.18); }
table.board .mono { font-variant-numeric: tabular-nums; }
table.board .late { color: #fbbf24; font-weight: 700; }
table.board .muted { color: #8b8fb5; }
.pill { display: inline-block; padding: 3px 11px; border-radius: 999px; font-size: 0.74rem; font-weight: 700; color: #14122e; }

/* ---------- evidence cards ---------- */
.evidence { background: #ffffff; border: 1px solid #e7e9f3; border-left: 5px solid #4f46e5; padding: 12px 16px;
            border-radius: 12px; margin-bottom: 10px; box-shadow: 0 2px 8px rgba(30, 27, 75, 0.05); line-height: 1.55; }
.evidence b { color: #4338ca; }
</style>
"""


def apply_style():
    st.markdown(STYLE, unsafe_allow_html=True)


def page_header(title, subtitle):
    st.markdown(
        f'<div class="page-header"><div class="title">{title}</div><div class="subtitle">{subtitle}</div></div>',
        unsafe_allow_html=True,
    )


def tile_title(text):
    st.markdown(f'<div class="tile-title">{text}</div>', unsafe_allow_html=True)


def chart_layout(figure, height=320):
    """Same compact look for every chart."""
    figure.update_layout(
        height=height, margin=dict(l=8, r=8, t=10, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.12, x=0), font=dict(size=12), colorway=PALETTE,
    )
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(gridcolor="#eceef6", zeroline=False)
    return figure


@st.cache_data
def load(name):
    """Read one summary file from app/data (cached)."""
    return pd.read_csv(os.path.join(DATA_DIR, f"{name}.csv"), parse_dates=DATE_COLUMNS.get(name, []))


def rate(part, whole):
    """Percentage, or None when there is nothing to divide by."""
    return 100 * part / whole if whole else None


def last_updated():
    """When the data files were last refreshed."""
    path = os.path.join(DATA_DIR, "last_updated.txt")
    return open(path, encoding="utf-8").read().strip() if os.path.exists(path) else "unknown"


def airport_labels():
    airports = load("airports")
    return dict(zip(airports["airport"], airports["city"] + " (" + airports["airport"] + ")"))


def airport_filter(where=None):
    """Multiselect of followed airports. Empty means all. Kept when moving between pages."""
    where = where or st.sidebar
    labels = airport_labels()
    chosen = where.multiselect("Airport", list(labels), default=st.session_state.get("saved_airports", []),
                               format_func=labels.get, key="airports_widget", placeholder="All airports")
    st.session_state["saved_airports"] = chosen
    return chosen


def clock(value):
    """HH:MM of a timestamp, or an empty string."""
    return "" if pd.isna(value) else pd.Timestamp(value).strftime("%H:%M")


def board_html(flights):
    """A departure-board style table for a set of flights."""
    rows = []
    for flight in flights.itertuples():
        minutes = "" if pd.isna(flight.minutes_after_schedule) else f"{flight.minutes_after_schedule:+.0f} min"
        took_off = '<span class="muted">-</span>' if pd.isna(flight.took_off) else clock(flight.took_off)
        rows.append(
            f"<tr><td><b>{flight.flight_number}</b></td><td>{flight.airline_name}</td>"
            f"<td><b>{flight.dest}</b> <span class='muted'>{flight.dest_name}</span></td>"
            f'<td class="mono">{flight.flight_date:%d %b}</td>'
            f'<td class="mono">{clock(flight.sched_dep)}</td><td class="mono">{took_off}</td>'
            f'<td class="mono {"late" if flight.status == "late" else ""}">{minutes}</td>'
            f'<td><span class="pill" style="background:{STATUS_COLOURS[flight.status]}">{flight.status}</span></td>'
            f"<td class='muted'>{WEATHER_ICONS.get(flight.weather_condition, '')} {flight.weather_condition if isinstance(flight.weather_condition, str) else ''}</td></tr>"
        )
    return (
        '<div class="board-wrap"><table class="board"><tr><th>Flight</th><th>Airline</th><th>To</th><th>Date</th>'
        "<th>Scheduled</th><th>Took off</th><th>After schedule</th><th>Status</th><th>Weather at departure</th></tr>"
        + "".join(rows) + "</table></div>"
    )


def late_rate(df):
    """Share of tracked flights that took off 30+ minutes after schedule, in percent."""
    tracked = df["tracked_flights"].sum()
    return 100 * df["late_flights"].sum() / tracked if tracked else float("nan")
