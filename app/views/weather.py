"""Weather impact: how the weather at departure changes the late rate."""

import plotly.express as px
import streamlit as st

from common import AMBER, WEATHER_ICONS, WEATHER_ORDER, airport_filter, chart_layout, load, page_header, tile_title

page_header("Weather impact", "Each flight is matched to the weather at its airport in its scheduled departure hour")

chosen = airport_filter()
impact = load("weather_impact")
if chosen:
    impact = impact[impact["airport"].isin(chosen)]

by_weather = impact.groupby("weather_condition")[["flights", "tracked_flights", "late_flights", "cancelled_flights"]].sum()
by_weather = by_weather.reindex([w for w in WEATHER_ORDER if w in by_weather.index])
by_weather["late_rate"] = 100 * by_weather["late_flights"] / by_weather["tracked_flights"]
by_weather["label"] = [f"{WEATHER_ICONS[w]} {w}" for w in by_weather.index]

calm = by_weather.loc["dry and calm"]
other = by_weather.drop(index="dry and calm")
c1, c2, c3 = st.columns(3)
c1.metric("Late in dry, calm weather", f"{calm['late_rate']:.1f}%")
c2.metric("Late in any other weather", f"{100 * other['late_flights'].sum() / other['tracked_flights'].sum():.1f}%" if other["tracked_flights"].sum() else "-")
c3.metric("Departures in other than calm weather", f"{100 * other['flights'].sum() / by_weather['flights'].sum():.0f}%")

left, right = st.columns([3, 2])
with left.container(border=True):
    tile_title("Share of departures that were late, by weather at departure")
    enough = by_weather[by_weather["tracked_flights"] >= 20]
    figure = px.bar(enough, x="label", y="late_rate", text=enough["late_rate"].map("{:.0f}%".format).values,
                    color_discrete_sequence=[AMBER], labels={"label": "", "late_rate": "Late %"})
    st.plotly_chart(chart_layout(figure, 340), width="stretch")
    st.caption("Weather types with at least 20 tracked departures.")
with right.container(border=True):
    tile_title("The numbers")
    table = by_weather[["label", "tracked_flights", "late_rate", "cancelled_flights"]].copy()
    table.columns = ["Weather", "Tracked departures", "Late %", "Cancelled"]
    st.dataframe(table.round(1), hide_index=True, width="stretch")

st.caption(
    "Light rain is under 2.5 mm in the hour; low visibility is under 1.5 km; strong wind is gusts of 45 km/h or more. "
    "So far the data covers a few mostly dry October days, so the bad-weather groups are small and the comparison "
    "will only become meaningful as monsoon, fog and storm days are collected."
)
