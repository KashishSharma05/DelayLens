"""When delays happen: by hour of day, and the knock-on effect of a late aircraft."""

import plotly.express as px
import streamlit as st

from common import DELAY_SCALE, GREEN, ROSE, airport_filter, chart_layout, load, page_header, tile_title

page_header("When delays happen", "Delay risk by hour of day, and what a late incoming aircraft does to the next flight")

chosen = airport_filter()
hourly = load("hourly_pattern")
knock = load("knock_on")
if chosen:
    hourly, knock = hourly[hourly["airport"].isin(chosen)], knock[knock["airport"].isin(chosen)]

by_hour = hourly.groupby("dep_hour")[["tracked_flights", "late_flights"]].sum()
by_hour = by_hour[by_hour["tracked_flights"] >= 30]
by_hour["late_rate"] = 100 * by_hour["late_flights"] / by_hour["tracked_flights"]
best, worst = by_hour["late_rate"].idxmin(), by_hour["late_rate"].idxmax()

c1, c2, c3 = st.columns(3)
c1.metric("Most punctual hour to depart", f"{best:02d}:00", f"{by_hour.loc[best, 'late_rate']:.0f}% late", delta_color="off")
c2.metric("Least punctual hour to depart", f"{worst:02d}:00", f"{by_hour.loc[worst, 'late_rate']:.0f}% late", delta_color="off")
c3.metric("Difference", f"{by_hour.loc[worst, 'late_rate'] / max(by_hour.loc[best, 'late_rate'], 1):.1f}x")

left, right = st.columns([3, 2])
with left.container(border=True):
    tile_title("Share of departures that were late, by scheduled hour")
    figure = px.bar(by_hour.reset_index(), x="dep_hour", y="late_rate", color="late_rate", color_continuous_scale=DELAY_SCALE,
                    labels={"dep_hour": "Scheduled departure hour (India time)", "late_rate": "Late %"})
    figure.update_coloraxes(showscale=False)
    figure.update_xaxes(dtick=1)
    st.plotly_chart(chart_layout(figure, 340), width="stretch")
    st.caption("Hours with at least 30 tracked departures.")

with right.container(border=True):
    tile_title("The knock-on effect")
    by_leg = knock.groupby("previous_leg")[["tracked_flights", "late_flights"]].sum().reindex(["aircraft arrived on time", "aircraft arrived late"])
    by_leg["late_rate"] = 100 * by_leg["late_flights"] / by_leg["tracked_flights"]
    figure = px.bar(by_leg.reset_index(), x="previous_leg", y="late_rate", text=by_leg["late_rate"].map("{:.0f}%".format).values,
                    color="previous_leg", color_discrete_map={"aircraft arrived on time": GREEN, "aircraft arrived late": ROSE},
                    labels={"previous_leg": "", "late_rate": "Late %"})
    figure.update_layout(showlegend=False)
    st.plotly_chart(chart_layout(figure, 340), width="stretch")
    st.caption(
        f"Based on {by_leg['tracked_flights'].sum():.0f} flights whose aircraft could be followed from its previous flight "
        f"({by_leg.loc['aircraft arrived late', 'tracked_flights']:.0f} of them arrived late). A small sample for now; "
        "it grows every day."
    )
