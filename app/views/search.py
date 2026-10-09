"""Search: find a flight by number, city or airline, then see its track record and each day's story."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import (AMBER, GREEN, GREY, STATUS_COLOURS, WEATHER_ICONS, airport_labels, board_html, chart_layout, clock, load,
                    page_header, tile_title)

page_header("Search a flight", "Flight number, destination city or airline: see how reliable it is and why it was late")

flights = load("flights")
record = load("flight_punctuality")
daily = load("airport_daily")
labels = airport_labels()

query = st.text_input("Search", placeholder="Try  6E 5237   or   Delhi   or   Akasa   or   BOM DEL", key="search_text").strip()

matches = record.copy()
if query:
    # every word must be found somewhere in the flight's number, airline, airports or destination name
    searchable = (record["flight_number"] + " " + record["flight_number"].str.replace(" ", "") + " " + record["airline_name"] + " "
                  + record["origin"] + " " + record["dest"] + " " + record["dest_name"].fillna("")
                  + " " + record["origin"].map(labels)).str.lower()
    for word in query.lower().split():
        matches = matches[searchable.loc[matches.index].str.contains(word, regex=False)]

matches = matches[matches["days_tracked"] > 0].sort_values(["days_seen", "late_pct"], ascending=False)
st.caption(f"{len(matches):,} flights match." if query else f"{len(matches):,} flights on record. Type to narrow down.")
if matches.empty:
    st.info("No flight matches. Try a flight number such as 6E 5237, or a city.")
    st.stop()

table = matches.head(200)[["flight_number", "airline_name", "origin", "dest", "dest_name", "usual_departure", "days_tracked",
                           "late_pct", "avg_minutes_after_schedule", "days_cancelled"]].copy()
table.columns = ["Flight", "Airline", "From", "To", "Destination", "Usual departure", "Days tracked", "Late %",
                 "Avg min after schedule", "Days cancelled"]
st.dataframe(table, hide_index=True, width="stretch", height=250)

# ------------------------------------------------------------ one flight in detail
st.subheader("Flight details")
options = matches.head(200)
option_labels = {i: f"{row.flight_number} · {row.airline_name} · {row.origin} → {row.dest} {row.dest_name} · {row.usual_departure}"
                 for i, row in options.iterrows()}
chosen = options.loc[st.selectbox("Flight", list(option_labels), format_func=option_labels.get)]
history = flights[(flights["flight_number"] == chosen["flight_number"]) & (flights["origin"] == chosen["origin"])].sort_values("sched_dep")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Days tracked", f"{chosen['days_tracked']:.0f}")
k2.metric("Late (30+ min after schedule)", f"{chosen['late_pct']:.0f}%", f"{chosen['days_late']:.0f} of {chosen['days_tracked']:.0f} days", delta_color="off")
k3.metric("Average after schedule", f"{chosen['avg_minutes_after_schedule']:.0f} min")
k4.metric("Worst day", f"{chosen['worst_minutes_after_schedule']:.0f} min")

left, right = st.columns([3, 2])
with left.container(border=True):
    tile_title("Minutes after schedule, day by day")
    tracked = history[history["minutes_after_schedule"].notna()]
    figure = go.Figure(go.Bar(
        x=tracked["flight_date"].dt.strftime("%d %b"), y=tracked["minutes_after_schedule"],
        marker_color=[STATUS_COLOURS[s] for s in tracked["status"]], text=tracked["minutes_after_schedule"].map("{:.0f}".format),
    ))
    figure.add_hline(y=30, line_dash="dash", line_color=GREY, annotation_text="late from 30 min")
    st.plotly_chart(chart_layout(figure, 300), width="stretch")
with right.container(border=True):
    tile_title("How this flight compares")
    airport_rate = 100 * daily.loc[daily["airport"] == chosen["origin"], "late_flights"].sum() / daily.loc[daily["airport"] == chosen["origin"], "tracked_flights"].sum()
    figure = go.Figure(go.Bar(x=[f"This flight", f"All flights from {chosen['origin']}"], y=[chosen["late_pct"], airport_rate],
                              marker_color=[AMBER, GREEN], text=[f"{chosen['late_pct']:.0f}%", f"{airport_rate:.0f}%"]))
    figure.update_layout(yaxis_title="Late %")
    st.plotly_chart(chart_layout(figure, 300), width="stretch")

st.markdown(board_html(history), unsafe_allow_html=True)
st.caption("With only a few days of data so far, a flight's percentage can swing a lot. It becomes more reliable as days are added.")

# ---------------------------------------------------------------- why, for one day
late_days = history[history["status"] == "late"]
if not late_days.empty:
    st.subheader("Why was it late?")
    day_labels = {row.flight_id: f"{row.flight_date:%d %b %Y} · took off {row.minutes_after_schedule:.0f} min after schedule" for row in late_days.itertuples()}
    flight = late_days.set_index("flight_id").loc[st.selectbox("Day", list(day_labels), format_func=day_labels.get)]

    evidence = [
        f"<b>The flight.</b> {chosen['airline_name']} {chosen['flight_number']} to {flight['dest_name']} was scheduled for "
        f"{clock(flight['sched_dep'])} and took off at {clock(flight['took_off'])}, {flight['minutes_after_schedule']:.0f} minutes after schedule."
    ]
    if pd.notna(flight["prev_arrival_delay_min"]):
        if flight["prev_arrival_delay_min"] >= 15:
            evidence.append(f"<b>The aircraft.</b> {flight['aircraft_reg']} had just arrived from {flight['prev_origin']} as "
                            f"{flight['prev_flight_number']}, landing {flight['prev_arrival_delay_min']:.0f} minutes late. "
                            "The delay was already on the aircraft before this flight boarded.")
        else:
            evidence.append(f"<b>The aircraft.</b> {flight['aircraft_reg']} arrived from {flight['prev_origin']} on time "
                            f"({flight['prev_arrival_delay_min']:+.0f} min), so the delay started at this airport.")
    else:
        evidence.append("<b>The aircraft.</b> Its previous flight is not in the data, so a knock-on delay can neither be confirmed nor ruled out.")

    condition = flight["weather_condition"]
    evidence.append(
        f"<b>Weather at {flight['origin']} at {pd.Timestamp(flight['sched_dep']):%H}:00.</b> {WEATHER_ICONS.get(condition, '')} {condition}: "
        f"{flight['temperature_c']:.0f}°C, rain {flight['precipitation_mm']:.1f} mm, gusts {flight['wind_gusts_kmh']:.0f} km/h, "
        f"visibility {flight['visibility_m'] / 1000:.1f} km."
    )
    that_day = daily[(daily["airport"] == flight["origin"]) & (daily["flight_date"] == flight["flight_date"])].iloc[0]
    typical = 100 * daily.loc[daily["airport"] == flight["origin"], "late_flights"].sum() / daily.loc[daily["airport"] == flight["origin"], "tracked_flights"].sum()
    evidence.append(f"<b>The airport that day.</b> {that_day['late_rate_pct']:.0f}% of departures from {flight['origin']} were late, "
                    f"against its average of {typical:.0f}%.")
    for item in evidence:
        st.markdown(f'<div class="evidence">{item}</div>', unsafe_allow_html=True)
    st.caption("India does not publish an official cause for each delay. This is the evidence available for that flight, not a confirmed cause.")
