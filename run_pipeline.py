"""Run the whole DelayLens pipeline with one command.

Run with:  python run_pipeline.py              (collect new data, then rebuild everything)
           python run_pipeline.py --no-collect  (rebuild from the files already in data/)

Steps:
  1. collect yesterday's departures (and any of the last 3 days still missing)
  2. refresh the hourly weather
  3. collect news headlines and tag the new ones with the LLM
  4. rebuild the database from the files in data/
  5. clean, model and summarise with SQL
  6. write the files the website reads

This is the script the daily scheduled job runs. Steps 1 to 3 are skipped
one by one if their API key is not set, so the rest still works.
"""

import os
import sys
import time

from dotenv import load_dotenv

from src import collect_flights, collect_news, export, load_raw, load_weather
from src.ai import news_tags
from src.db import run_sql_file

load_dotenv()


def step(title):
    print(f"\n===== {title} =====", flush=True)


def main():
    start = time.time()
    collect = "--no-collect" not in sys.argv

    if collect:
        step("1. Flights")
        if os.getenv("RAPIDAPI_KEY"):
            sys.argv = [sys.argv[0], "--days", "3"]
            collect_flights.main()
        else:
            print("Skipped: RAPIDAPI_KEY is not set.")

        step("2. Weather")
        load_weather.main()

        step("3. News")
        collect_news.main()
        if os.getenv("GEMINI_API_KEY"):
            news_tags.main()
        else:
            print("Tagging skipped: GEMINI_API_KEY is not set.")

    step("4. Rebuild the database from files")
    load_raw.main()

    step("5. Clean, model and summarise")
    for sql_file in ("sql/03_clean.sql", "sql/04_mart.sql", "sql/05_analysis.sql"):
        run_sql_file(sql_file)
        print("ran", sql_file)

    step("6. Website files")
    export.main()

    print(f"\nPipeline finished in {time.time() - start:.0f} seconds.")


if __name__ == "__main__":
    main()
