"""Collect recent news headlines about flight delays in India.

Run with:  python -m src.collect_news

Uses the public Google News RSS feed: one search per followed airport plus
one for India as a whole, limited to the last 7 days. Only the headline,
source, time and link are kept (never the article text), in
data/news/news.csv. A headline already in the file is skipped.
"""

import hashlib
import os
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from src.config import NEWS_FILE, followed_airports

FEED_URL = "https://news.google.com/rss/search"
WORDS = "(delayed OR delay OR cancelled OR diverted OR fog OR storm OR disruption)"
INDIA = ZoneInfo("Asia/Kolkata")
COLUMNS = ["news_id", "published_at", "title", "source", "link", "search_query"]


def searches():
    """One search per followed airport (by city name), plus one for India overall."""
    airports = followed_airports()
    queries = {f'"{city} airport" flights {WORDS} when:7d': code for code, city in zip(airports["airport"], airports["city"])}
    queries[f"India flights {WORDS} airport when:7d"] = "India"
    return queries


def fetch(query, label):
    """Return the headlines of one search as a list of dictionaries."""
    response = requests.get(FEED_URL, params={"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
                            headers={"User-Agent": "Mozilla/5.0"}, timeout=40)
    response.raise_for_status()

    rows = []
    for item in ET.fromstring(response.content).findall(".//item"):
        link, title, source = item.findtext("link"), item.findtext("title"), item.findtext("source")
        if source and title.endswith(f" - {source}"):
            title = title[: -len(f" - {source}")]  # the feed repeats the source at the end of the title
        rows.append({
            "news_id": hashlib.sha256(link.encode()).hexdigest()[:16],  # short id, so a headline is stored once
            "published_at": parsedate_to_datetime(item.findtext("pubDate")).astimezone(INDIA).replace(tzinfo=None),
            "title": title.strip(), "source": source, "link": link, "search_query": label,
        })
    return rows


def main():
    old = pd.read_csv(NEWS_FILE, parse_dates=["published_at"]) if os.path.exists(NEWS_FILE) else pd.DataFrame(columns=COLUMNS)

    found = []
    for query, label in searches().items():
        rows = fetch(query, label)
        found.extend(rows)
        print(f"{label:6s} {len(rows):>3} headlines found")
        time.sleep(2)

    merged = pd.concat([old, pd.DataFrame(found, columns=COLUMNS)], ignore_index=True)
    merged = merged.drop_duplicates(subset="news_id", keep="first").sort_values("published_at")
    os.makedirs(os.path.dirname(NEWS_FILE), exist_ok=True)
    merged.to_csv(NEWS_FILE, index=False)
    print(f"\n{len(merged) - len(old)} new headlines; {len(merged)} in {NEWS_FILE}.")


if __name__ == "__main__":
    main()
