"""Write the files the website reads, into app/data/.

Run with:  python -m src.export

The hosted website has no database, so everything it shows comes from
these CSV files. The summary tables hold counts (not ready-made rates), so
any filter on the site still gives exact rates.
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from src.db import get_engine

APP_DATA_DIR = "app/data"

EXPORTS = {
    "airports": "SELECT * FROM mart.dim_airport ORDER BY airport",
    "flights": """
        SELECT flight_id, flight_date, origin, flight_number, airline, airline_name, dest, dest_name, is_international,
               aircraft_reg, aircraft_model, terminal, sched_dep, took_off, sched_arr, landed,
               minutes_after_schedule, arrival_delay_min, status, dep_hour,
               prev_flight_number, prev_origin, prev_arrival_delay_min,
               temperature_c, precipitation_mm, wind_gusts_kmh, visibility_m, weather_condition
        FROM mart.fact_flights
        WHERE flight_date IN (SELECT flight_date FROM mart.airport_daily)
        ORDER BY sched_dep, origin, flight_number""",
    "airport_daily": "SELECT * FROM mart.airport_daily ORDER BY airport, flight_date",
    "daily_summary": "SELECT * FROM mart.daily_summary ORDER BY flight_date, airport, airline_name",
    "hourly_pattern": "SELECT * FROM mart.hourly_pattern ORDER BY airport, dep_hour",
    "weather_impact": "SELECT * FROM mart.weather_impact ORDER BY airport, weather_condition",
    "knock_on": "SELECT * FROM mart.knock_on ORDER BY airport, previous_leg",
    "route_summary": "SELECT * FROM mart.route_summary ORDER BY origin, dest",
    "flight_punctuality": "SELECT * FROM mart.flight_punctuality ORDER BY origin, flight_number",
    "weather_hourly": """
        SELECT * FROM mart.weather_hourly
        WHERE weather_time::date >= (SELECT MIN(flight_date) FROM mart.airport_daily)
        ORDER BY airport, weather_time""",
    "news": """
        SELECT published_at, title, source, link, ARRAY_TO_STRING(airports, '|') AS airports, cause, summary
        FROM raw.news
        WHERE is_relevant
        ORDER BY published_at DESC""",
}


def main():
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    connection = get_engine().raw_connection()
    try:
        with connection.cursor() as cursor:
            for name, query in EXPORTS.items():
                path = f"{APP_DATA_DIR}/{name}.csv"
                with open(path, "w", encoding="utf-8", newline="") as csv_file:
                    cursor.copy_expert(f"COPY ({query}) TO STDOUT WITH (FORMAT csv, HEADER true)", csv_file)
                print(f"  {name:20s} {cursor.rowcount:>7,} rows  ->  {path}")
    finally:
        connection.close()

    # The site shows this as "Last updated".
    with open(f"{APP_DATA_DIR}/last_updated.txt", "w", encoding="utf-8") as stamp:
        stamp.write(datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y, %H:%M IST"))


if __name__ == "__main__":
    main()
