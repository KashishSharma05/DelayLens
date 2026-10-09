"""Collect departures of the followed airports from the AeroDataBox API.

Run with:  python -m src.collect_flights --days 3     (the last 3 days; the default)
           python -m src.collect_flights --check      (free call, to test the key)

Each call asks for one airport and one 12-hour window and costs 2 units of
the free plan's 400 a month. So the script:
  - skips every window already listed in the ledger,
  - adds up the units used in the last 30 days and stops before the budget,
  - saves the complete answer as a compressed JSON file, so nothing is ever
    fetched twice and the data can be re-read in a new way without a call.

The API key is read from RAPIDAPI_KEY (the .env file locally, a secret in
the scheduled job).
"""

import gzip
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from dotenv import load_dotenv

from src.config import AIRPORTS, API_CALLS_DIR, LEDGER_FILE, MONTHLY_UNIT_BUDGET, UNITS_PER_CALL

load_dotenv()

HOST = "aerodatabox.p.rapidapi.com"
URL = "https://" + HOST + "/flights/airports/iata/{airport}/{start}/{end}"
PARAMS = {
    "direction": "Departure",
    "withLeg": "true",          # also return the arrival end of each flight
    "withCancelled": "true",
    "withCodeshared": "false",  # one row per real flight, not one per marketing flight number
    "withCargo": "false",
    "withPrivate": "false",
}
LEDGER_COLUMNS = ["airport", "window_start", "window_end", "fetched_at", "units_used", "flights", "file"]
INDIA = ZoneInfo("Asia/Kolkata")


def read_ledger():
    if not os.path.exists(LEDGER_FILE):
        return pd.DataFrame(columns=LEDGER_COLUMNS)
    return pd.read_csv(LEDGER_FILE, parse_dates=["window_start", "window_end", "fetched_at"])


def windows_for(day):
    """The two 12-hour windows of one local day."""
    morning = datetime.combine(day, datetime.min.time())
    return [(morning, morning + timedelta(hours=11, minutes=59)),
            (morning + timedelta(hours=12), morning + timedelta(hours=23, minutes=59))]


def fetch(airport, start, end, api_key):
    """One API call. Returns the parsed JSON answer."""
    response = requests.get(
        URL.format(airport=airport, start=start.strftime("%Y-%m-%dT%H:%M"), end=end.strftime("%Y-%m-%dT%H:%M")),
        headers={"X-RapidAPI-Key": api_key, "X-RapidAPI-Host": HOST},
        params=PARAMS,
        timeout=60,
    )
    if response.status_code == 204:  # no flights in this window
        return {"departures": []}
    response.raise_for_status()
    return response.json()


def save_answer(airport, start, end, answer, ledger):
    """Write the answer to a compressed file and add a line to the ledger."""
    file_name = f"{airport}/{start:%Y-%m-%d_%H}.json.gz"
    path = os.path.join(API_CALLS_DIR, file_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as json_file:
        json.dump(answer, json_file)

    line = {"airport": airport, "window_start": start, "window_end": end,
            "fetched_at": datetime.now(INDIA).replace(tzinfo=None, microsecond=0),
            "units_used": UNITS_PER_CALL, "flights": len(answer.get("departures", [])), "file": file_name}
    ledger = pd.concat([ledger, pd.DataFrame([line])], ignore_index=True)
    ledger.sort_values(["window_start", "airport"]).to_csv(LEDGER_FILE, index=False)
    return ledger


def main():
    api_key = os.getenv("RAPIDAPI_KEY")
    if not api_key:
        sys.exit("RAPIDAPI_KEY is missing.")

    if "--check" in sys.argv:  # a free endpoint that only reports whether the service is up
        response = requests.get(f"https://{HOST}/health/services/feeds/FlightSchedules",
                                headers={"X-RapidAPI-Key": api_key, "X-RapidAPI-Host": HOST}, timeout=40)
        print("Key works." if response.ok else f"Problem: HTTP {response.status_code}",
              "| units left this month:", response.headers.get("X-RateLimit-API-Units-Remaining"))
        return

    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 3
    today = datetime.now(INDIA).date()
    # Complete days only (up to yesterday), newest first.
    wanted = [(airport, window)
              for offset in range(1, days + 1)
              for airport in AIRPORTS
              for window in windows_for(today - timedelta(days=offset))]

    ledger = read_ledger()
    stored = set(zip(ledger["airport"], ledger["window_start"]))
    todo = [(airport, window) for airport, window in wanted if (airport, pd.Timestamp(window[0])) not in stored]
    print(f"{len(wanted)} windows wanted, {len(wanted) - len(todo)} already stored, {len(todo)} to fetch.")

    for airport, (start, end) in todo:
        recent = ledger[ledger["fetched_at"] >= pd.Timestamp(datetime.now(INDIA).replace(tzinfo=None)) - pd.Timedelta(days=30)]
        used = int(recent["units_used"].sum())
        if used + UNITS_PER_CALL > MONTHLY_UNIT_BUDGET:
            print(f"Stopped: {used} of {MONTHLY_UNIT_BUDGET} budgeted units used in the last 30 days.")
            break

        answer = fetch(airport, start, end, api_key)
        ledger = save_answer(airport, start, end, answer, ledger)
        print(f"{airport}  {start:%Y-%m-%d %H:%M}  {len(answer.get('departures', [])):>4} departures   "
              f"(units in the last 30 days: {used + UNITS_PER_CALL})", flush=True)
        time.sleep(1.2)  # the free plan allows one request per second

    print(f"\nStored so far: {int(ledger['flights'].sum()):,} departures from {len(ledger)} calls.")


if __name__ == "__main__":
    main()
