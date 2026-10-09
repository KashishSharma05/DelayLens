"""Fetch hourly weather for every followed airport from the Open-Meteo API.

Run with:  python -m src.load_weather

One request per airport returns the last 92 days plus the next 3 days,
hour by hour, in the airport's local time (so the hours line up with the
flight times). The result is merged into data/weather/weather_hourly.csv:
hours already in the file are replaced by the fresh values (a forecast is
replaced by what really happened), and older hours are kept.

Weather data: Open-Meteo (https://open-meteo.com), free, no API key.
"""

import os
import time

import pandas as pd
import requests

from src.config import WEATHER_FILE, followed_airports

API_URL = "https://api.open-meteo.com/v1/forecast"

# API variable name -> column name
VARIABLES = {
    "temperature_2m": "temperature_c",
    "relative_humidity_2m": "humidity_pct",
    "precipitation": "precipitation_mm",
    "wind_speed_10m": "wind_speed_kmh",
    "wind_gusts_10m": "wind_gusts_kmh",
    "visibility": "visibility_m",
    "cloud_cover": "cloud_cover_pct",
    "weather_code": "weather_code",
}


def fetch_airport_weather(airport):
    """One API call: recent and coming hourly weather for one airport."""
    response = requests.get(
        API_URL,
        params={
            "latitude": airport.latitude,
            "longitude": airport.longitude,
            "hourly": ",".join(VARIABLES),
            "past_days": 92,
            "forecast_days": 3,
            "timezone": airport.timezone,
        },
        timeout=120,
    )
    response.raise_for_status()
    hourly = pd.DataFrame(response.json()["hourly"]).rename(columns=VARIABLES)
    hourly["weather_time"] = pd.to_datetime(hourly.pop("time"))
    hourly.insert(0, "airport", airport.airport)
    # The oldest hours come back empty; keep only hours that have data.
    return hourly.dropna(subset=["temperature_c"])


def main():
    fresh = []
    for airport in followed_airports().itertuples():
        hourly = fetch_airport_weather(airport)
        fresh.append(hourly)
        print(f"{airport.airport}  {len(hourly):>5,} hours  ({hourly['weather_time'].min()} to {hourly['weather_time'].max()})", flush=True)
        time.sleep(2)  # be polite to the free API
    fresh = pd.concat(fresh, ignore_index=True)

    if os.path.exists(WEATHER_FILE):
        old = pd.read_csv(WEATHER_FILE, parse_dates=["weather_time"])
        fresh = pd.concat([old, fresh], ignore_index=True)
    # for an airport-hour seen twice, the later (fresher) row wins
    merged = fresh.drop_duplicates(subset=["airport", "weather_time"], keep="last").sort_values(["airport", "weather_time"])

    os.makedirs(os.path.dirname(WEATHER_FILE), exist_ok=True)
    merged.to_csv(WEATHER_FILE, index=False)
    print(f"{WEATHER_FILE}: {len(merged):,} hourly rows.")


if __name__ == "__main__":
    main()
