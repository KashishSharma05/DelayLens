"""Departure board: every departure from one airport on one day."""

import pandas as pd
import streamlit as st

from common import STATUS_COLOURS, airport_labels, board_html, load, page_header

page_header("Departure board", "Every departure with its scheduled and actual take-off time")

flights = load("flights")
labels = airport_labels()

c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
airport = c1.selectbox("Airport", list(labels), format_func=labels.get)
days = sorted(flights.loc[flights["origin"] == airport, "flight_date"].unique(), reverse=True)
day = c2.selectbox("Date", days, format_func=lambda d: pd.Timestamp(d).strftime("%a, %d %b %Y"))
status_choice = c3.multiselect("Status", list(STATUS_COLOURS), placeholder="All statuses")
text = c4.text_input("Filter", placeholder="Flight, airline or destination").strip().lower()

board = flights[(flights["origin"] == airport) & (flights["flight_date"] == day)].sort_values("sched_dep")
shown = board[board["status"].isin(status_choice)] if status_choice else board
if text:
    haystack = (shown["flight_number"] + " " + shown["airline_name"] + " " + shown["dest"] + " " + shown["dest_name"].fillna("")).str.lower()
    shown = shown[haystack.str.contains(text, regex=False)]

tracked = board["minutes_after_schedule"].notna().sum()
late = (board["status"] == "late").sum()
k1, k2, k3, k4 = st.columns(4)
k1.metric("Departures", f"{len(board):,}")
k2.metric("Late (30+ min after schedule)", f"{100 * late / tracked:.0f}%" if tracked else "-")
k3.metric("Cancelled", f"{(board['status'] == 'canceled').sum():,}")
k4.metric("Longest wait", f"{board['minutes_after_schedule'].max():.0f} min" if tracked else "-")

st.markdown(board_html(shown), unsafe_allow_html=True)
st.caption(f"{len(shown):,} of {len(board):,} departures. Times are India time. 'After schedule' is the gap between scheduled "
           "departure and actual take-off; 'no actual time' means the take-off was not recorded by the data provider.")
