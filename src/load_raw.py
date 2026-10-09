"""Rebuild the raw schema of the database from the files kept in data/.

Run with:  python -m src.load_raw

Reads the airport list, the ledger and saved API answers, the weather file
and the news files, and loads them into PostgreSQL. Nothing is fetched from
the internet here, so this gives the same database on any machine.
"""

import gzip
import json
import os

import pandas as pd
from sqlalchemy import text

from src.config import AIRPORTS_FILE, API_CALLS_DIR, LEDGER_FILE, NEWS_FILE, NEWS_TAGS_FILE, WEATHER_FILE
from src.db import get_engine, run_sql_file


def main():
    run_sql_file("sql/01_raw_schema.sql")
    engine = get_engine()

    airports = pd.read_csv(AIRPORTS_FILE)
    airports.to_sql("airports", engine, schema="raw", if_exists="append", index=False)

    # API answers: one row per ledger line, with the JSON read from its file.
    ledger = pd.read_csv(LEDGER_FILE, parse_dates=["window_start", "window_end", "fetched_at"])
    with engine.begin() as connection:
        for call in ledger.itertuples():
            with gzip.open(os.path.join(API_CALLS_DIR, call.file), "rt", encoding="utf-8") as json_file:
                payload = json_file.read()
            connection.execute(
                text("""INSERT INTO raw.api_calls (airport, window_start, window_end, fetched_at, units_used, flights, payload)
                        VALUES (:airport, :start, :end, :fetched, :units, :flights, CAST(:payload AS JSONB))"""),
                {"airport": call.airport, "start": call.window_start, "end": call.window_end, "fetched": call.fetched_at,
                 "units": call.units_used, "flights": call.flights, "payload": payload},
            )

    weather = pd.read_csv(WEATHER_FILE, parse_dates=["weather_time"])
    weather.to_sql("weather_hourly", engine, schema="raw", if_exists="append", index=False, chunksize=2000, method="multi")

    # News with its tags side by side (untagged headlines keep empty tag columns).
    news = pd.read_csv(NEWS_FILE, parse_dates=["published_at"])
    if os.path.exists(NEWS_TAGS_FILE):
        tags = pd.read_csv(NEWS_TAGS_FILE, keep_default_na=False)
        tags["is_relevant"] = tags["is_relevant"].astype(str).str.lower() == "true"
        tags["airports"] = tags["airports"].map(lambda value: [a for a in value.split("|") if a])
        news = news.merge(tags, on="news_id", how="left")
        news["airports"] = news["airports"].map(lambda value: value if isinstance(value, list) else None)
        news["is_relevant"] = news["is_relevant"].astype(object).where(news["is_relevant"].notna(), None)
    news.to_sql("news", engine, schema="raw", if_exists="append", index=False, chunksize=1000, method="multi")

    print(f"raw schema rebuilt: {len(airports)} airports, {len(ledger)} API answers ({int(ledger['flights'].sum()):,} departures), "
          f"{len(weather):,} weather hours, {len(news)} headlines.")


if __name__ == "__main__":
    main()
