"""Daily log: each day's numbers beside the weather, plus disruption news sorted by an AI model."""

import pandas as pd
import streamlit as st

from common import CAUSE_LABELS, WEATHER_ICONS, airport_labels, load, page_header, tile_title

page_header("Daily log & news", "What each day looked like, and what the news said about flight disruption")

daily = load("airport_daily")
weather = load("weather_hourly")
news = load("news")
labels = airport_labels()

with st.container(border=True):
    tile_title("Day by day")
    worst = (weather.assign(day=weather["weather_time"].dt.normalize(), rank=weather["weather_condition"].map(list(WEATHER_ICONS).index))
             .groupby(["airport", "day"])["rank"].max().map(lambda r: f"{list(WEATHER_ICONS.values())[r]} {list(WEATHER_ICONS)[r]}"))
    log = daily.sort_values(["flight_date", "airport"], ascending=[False, True]).copy()
    log["worst_weather"] = [worst.get((a, d), "") for a, d in zip(log["airport"], log["flight_date"])]
    log["airport"] = log["airport"].map(labels)
    log["flight_date"] = log["flight_date"].dt.strftime("%a %d %b")
    table = log[["flight_date", "airport", "flights", "late_rate_pct", "avg_minutes_when_late", "cancelled_flights", "worst_weather"]]
    table.columns = ["Day", "Airport", "Departures", "Late %", "Avg min after schedule when late", "Cancelled", "Worst weather"]
    st.dataframe(table, hide_index=True, width="stretch", height=330)

st.subheader("Disruption news")
st.caption(
    f"{len(news)} recent headlines that report flights being delayed, cancelled or diverted. A news search returns many "
    "unrelated aviation stories; an AI model reads each headline, keeps the relevant ones, and tags the cause."
)
c1, c2 = st.columns(2)
causes = c1.multiselect("Cause", sorted(news["cause"].unique()), format_func=lambda c: CAUSE_LABELS.get(c, c), placeholder="All causes")
shown = news[news["cause"].isin(causes)] if causes else news
counts = news["cause"].map(lambda c: CAUSE_LABELS.get(c, c)).value_counts()
c2.markdown("**This week:** " + " · ".join(f"{name} ({count})" for name, count in counts.items()))

for item in shown.head(30).itertuples():
    st.markdown(
        f'<div class="evidence"><b>{CAUSE_LABELS.get(item.cause, item.cause)}</b> · {item.published_at:%d %b, %H:%M} · {item.source}<br>'
        f'{item.summary}<br><a href="{item.link}" target="_blank">{item.title}</a></div>',
        unsafe_allow_html=True,
    )
