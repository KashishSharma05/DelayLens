"""Home: the latest day at each airport, and where to go next."""

import pandas as pd
import streamlit as st

from common import SITE_NAME, TAGLINE, WEATHER_ICONS, last_updated, load

flights = load("flights")
daily = load("airport_daily")
airports = load("airports")
weather = load("weather_hourly")
latest_day = daily["flight_date"].max()

st.markdown(
    f"""
<div class="hero">
  <div class="tag">{SITE_NAME.upper()} · {TAGLINE.upper()}</div>
  <h1>Why was the flight late?</h1>
  <p>Every departure from Mumbai, Bengaluru and Hyderabad, tracked against its schedule and matched with the
  weather at that hour, the aircraft's previous flight and the day's news. {len(flights):,} flights so far,
  updated {last_updated()}.</p>
</div>
""",
    unsafe_allow_html=True,
)

st.subheader(f"Latest day on record: {latest_day:%A, %d %B %Y}")
for column, airport in zip(st.columns(len(airports)), airports.itertuples()):
    day = daily[(daily["airport"] == airport.airport) & (daily["flight_date"] == latest_day)]
    usual = daily[daily["airport"] == airport.airport]
    usual_rate = 100 * usual["late_flights"].sum() / usual["tracked_flights"].sum()
    with column.container(border=True):
        band = {"BOM": "linear-gradient(120deg,#4f46e5,#7c3aed)", "BLR": "linear-gradient(120deg,#0891b2,#22d3ee)",
                "HYD": "linear-gradient(120deg,#f59e0b,#f97316)"}.get(airport.airport, "#1e1b4b")
        st.markdown(f'<div class="airport-band" style="background:{band}">{airport.city}<span>{airport.airport}</span></div>',
                    unsafe_allow_html=True)
        if day.empty:
            st.caption("No complete data for this day yet.")
            continue
        day = day.iloc[0]
        st.metric("Departures late (30+ min after schedule)", f"{day['late_rate_pct']:.0f}%",
                  f"{day['late_rate_pct'] - usual_rate:+.0f} points vs its average", delta_color="inverse")
        afternoon = weather[(weather["airport"] == airport.airport) & (weather["weather_time"].dt.date == latest_day.date())]
        worst = afternoon["weather_condition"].map(lambda c: list(WEATHER_ICONS).index(c)).max()
        condition = list(WEATHER_ICONS)[int(worst)]
        st.write(f"{day['flights']:.0f} departures · {day['cancelled_flights']:.0f} cancelled · "
                 f"average {day['avg_minutes_when_late']:.0f} min when late")
        st.caption(f"Worst weather that day: {WEATHER_ICONS[condition]} {condition} · "
                   f"{afternoon['temperature_c'].min():.0f} to {afternoon['temperature_c'].max():.0f}°C")

st.subheader("Explore")
# Each card is one link: clicking anywhere on it opens the page.
cards = [
    ("chat", "💬", "violet", "Ask DelayLens", "Ask in plain English. The AI assistant queries the flight data, the weather and the news, and shows its working."),
    ("search", "🔎", "indigo", "Search a flight", "Type a flight number, a city or an airline. See how often that flight runs late and what happened each day."),
    ("board", "🛫", "cyan", "Departure board", "Pick an airport and a day: every departure with its scheduled and actual take-off time."),
    ("stats", "📊", "amber", "Airlines & airports", "Which airlines and routes are the most punctual, and how the airports compare."),
    ("patterns", "🕒", "rose", "When delays happen", "Delay risk by hour of day, and what a late incoming aircraft does to the next flight."),
    ("daily", "🗞️", "green", "Daily log & news", "Each day's numbers next to the weather and the disruption news, sorted by an AI model."),
]
for column, (page, icon, colour, title, description) in zip(st.columns(3) + st.columns(3), cards):
    column.markdown(
        f'''<a class="feature-link" href="{page}" target="_self">
                <div class="feature {colour}"><div class="icon">{icon}</div>
                <div class="name">{title}</div><div class="text">{description}</div><div class="arrow">→</div></div></a>''',
        unsafe_allow_html=True,
    )

st.write("")
st.caption(
    "A flight is counted as late when it takes off 30 or more minutes after its scheduled departure (a normal flight "
    "takes off 15 to 20 minutes after schedule because of push-back and taxi). Flight data: AeroDataBox. Weather: "
    "Open-Meteo. News headlines: Google News. Delhi is not covered because actual departure times are not available for it."
)
