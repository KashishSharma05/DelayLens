"""Settings and file locations shared by the scripts."""

import pandas as pd

AIRPORTS_FILE = "data/reference/airports.csv"

# Collected data is kept as plain files in the repository, so the whole
# database can be rebuilt anywhere (a laptop or the daily scheduled job).
API_CALLS_DIR = "data/api_calls"                 # one compressed JSON file per API answer
LEDGER_FILE = "data/api_calls/ledger.csv"        # one line per API call: what was fetched and what it cost
WEATHER_FILE = "data/weather/weather_hourly.csv"
NEWS_FILE = "data/news/news.csv"
NEWS_TAGS_FILE = "data/news/news_tags.csv"

# The free plan of the flight API gives 400 units a month and one airport-departures
# call costs 2 units. The collector stops before this many units are used in 30 days.
MONTHLY_UNIT_BUDGET = 380
UNITS_PER_CALL = 2


def followed_airports():
    """Airports whose flights are collected and analysed, as a DataFrame."""
    airports = pd.read_csv(AIRPORTS_FILE)
    return airports[airports["is_followed"]]


AIRPORTS = list(followed_airports()["airport"])
