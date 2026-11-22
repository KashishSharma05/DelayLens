"""Fetch hourly weather for every followed airport from the Open-Meteo API.

Run with:  python -m src.load_weather

One request per airport returns the last 14 days plus the next 3 days,
hour by hour, in the airport's local time (so the hours line up with the
flight times). The result is merged into data/weather/weather_hourly.csv:
hours already in the file are replaced by the fresh values (a forecast is
replaced by what really happened), and older hours are kept.

A slow or failed request is retried. If an airport still fails, the run
keeps its stored weather and continues, and a later run fills the gap.

Weather data: Open-Meteo (https://open-meteo.com), free, no API key.
"""

import os
import time

import pandas as pd
import requests

from src.config import WEATHER_FILE, followed_airports

API_URL = "https://api.open-meteo.com/v1/forecast"
PAST_DAYS = 14
REQUEST_TIMEOUT = 45   # seconds
MAX_ATTEMPTS = 4

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
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                API_URL,
                params={
                    "latitude": airport.latitude,
                    "longitude": airport.longitude,
                    "hourly": ",".join(VARIABLES),
                    "past_days": PAST_DAYS,
                    "forecast_days": 3,
                    "timezone": airport.timezone,
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            break
        except requests.RequestException as error:
            if attempt == MAX_ATTEMPTS:
                raise
            wait = 10 * attempt
            print(f"{airport.airport}  attempt {attempt} failed ({type(error).__name__}), retrying in {wait}s", flush=True)
            time.sleep(wait)

    hourly = pd.DataFrame(response.json()["hourly"]).rename(columns=VARIABLES)
    hourly["weather_time"] = pd.to_datetime(hourly.pop("time"))
    hourly.insert(0, "airport", airport.airport)
    # The oldest hours come back empty; keep only hours that have data.
    return hourly.dropna(subset=["temperature_c"])


def main():
    fresh = []
    for airport in followed_airports().itertuples():
        try:
            hourly = fetch_airport_weather(airport)
        except requests.RequestException as error:
            print(f"{airport.airport}  skipped after {MAX_ATTEMPTS} attempts ({type(error).__name__}); keeping stored weather", flush=True)
            continue
        fresh.append(hourly)
        print(f"{airport.airport}  {len(hourly):>5,} hours  ({hourly['weather_time'].min()} to {hourly['weather_time'].max()})", flush=True)
        time.sleep(2)  # be polite to the free API

    if not fresh:
        if os.path.exists(WEATHER_FILE):
            print("No new weather this run; keeping the stored file.")
            return
        raise RuntimeError("No weather could be fetched and no stored weather file exists.")
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
