"""Airlines and airports: who is punctual, and which routes are reliable."""

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from common import AMBER, DELAY_SCALE, INK, PRIMARY, airport_filter, chart_layout, late_rate, load, page_header, tile_title

page_header("Airlines & airports", "Punctuality of departures from Mumbai, Bengaluru and Hyderabad")

chosen = airport_filter()
summary = load("daily_summary")
if chosen:
    summary = summary[summary["airport"].isin(chosen)]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Departures", f"{summary['flights'].sum():,.0f}")
c2.metric("Late (30+ min after schedule)", f"{late_rate(summary):.1f}%")
c3.metric("Average wait when late", f"{summary['late_minutes'].sum() / summary['late_flights'].sum():.0f} min")
c4.metric("Cancelled", f"{summary['cancelled_flights'].sum():,.0f}")

left, right = st.columns(2)
with left.container(border=True):
    tile_title("Airlines: share of departures that were late")
    airlines = summary.groupby("airline_name")[["flights", "tracked_flights", "late_flights"]].sum()
    airlines = airlines[airlines["tracked_flights"] >= 40]
    airlines["late_rate"] = 100 * airlines["late_flights"] / airlines["tracked_flights"]
    airlines = airlines.sort_values("late_rate", ascending=False)
    figure = px.bar(airlines.reset_index(), x="late_rate", y="airline_name", orientation="h", color="late_rate",
                    color_continuous_scale=DELAY_SCALE, text=airlines["late_rate"].map("{:.0f}%".format).values,
                    hover_data=["tracked_flights"], labels={"late_rate": "", "airline_name": ""})
    figure.update_coloraxes(showscale=False)
    figure.update_xaxes(showticklabels=False)
    st.plotly_chart(chart_layout(figure, max(300, 34 * len(airlines))), width="stretch")
    st.caption("Airlines with at least 40 tracked departures in the selection.")

with right.container(border=True):
    tile_title("Airports")
    airports = load("airports")
    by_airport = load("daily_summary").groupby("airport")[["flights", "tracked_flights", "late_flights"]].sum().reset_index()
    by_airport["late_rate"] = 100 * by_airport["late_flights"] / by_airport["tracked_flights"]
    by_airport = by_airport.merge(airports, on="airport")
    figure = px.scatter_geo(by_airport, lat="latitude", lon="longitude", size="flights", color="late_rate", text="airport",
                            hover_name="airport_name", hover_data={"late_rate": ":.1f", "flights": ":,", "latitude": False, "longitude": False},
                            color_continuous_scale=DELAY_SCALE, size_max=34, labels={"late_rate": "Late %"})
    figure.update_traces(textposition="top center", textfont=dict(color=INK, size=13))
    figure.update_geos(bgcolor="rgba(0,0,0,0)", landcolor="#eef0fb", countrycolor="#c7d2fe", showcountries=True,
                       lataxis_range=[6, 36], lonaxis_range=[66, 94], projection_type="mercator")
    st.plotly_chart(chart_layout(figure, 380), width="stretch")

with st.container(border=True):
    tile_title("Late rate by day")
    by_day = summary.groupby(["flight_date", "airport"])[["tracked_flights", "late_flights"]].sum().reset_index()
    by_day["late_rate"] = 100 * by_day["late_flights"] / by_day["tracked_flights"]
    figure = px.line(by_day, x="flight_date", y="late_rate", color="airport", markers=True,
                     labels={"flight_date": "", "late_rate": "Late %", "airport": ""})
    figure.update_xaxes(dtick="D1", tickformat="%d %b")
    st.plotly_chart(chart_layout(figure, 300), width="stretch")

with st.container(border=True):
    tile_title("Routes")
    routes = load("route_summary")
    if chosen:
        routes = routes[routes["origin"].isin(chosen)]
    routes = routes.assign(route=routes["origin"] + " → " + routes["dest"] + "  " + routes["dest_name"],
                           late_rate=100 * routes["late_flights"] / routes["tracked_flights"])
    table = routes[["route", "tracked_flights", "late_rate", "avg_minutes_when_late", "cancelled_flights"]]
    table.columns = ["Route", "Tracked departures", "Late %", "Avg min after schedule when late", "Cancelled"]
    left, right = st.columns(2)
    left.markdown("**Most punctual**")
    left.dataframe(table.nsmallest(10, "Late %").round(0), hide_index=True, width="stretch")
    right.markdown("**Least punctual**")
    right.dataframe(table.nlargest(10, "Late %").round(0), hide_index=True, width="stretch")
    st.caption("Routes with at least 15 tracked departures.")
