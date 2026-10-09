"""Use an LLM to turn news headlines into structured data.

Run with:  python -m src.ai.news_tags

A search for "flights delayed" also returns headlines about airports
opening, ticket prices or events abroad. For every headline the LLM decides:
  is_relevant  does it report flights being delayed, cancelled or diverted in India?
  airports     which followed airports it concerns (DEL, BOM, BLR), or none
  cause        one value from a fixed list
  summary      what happened, in at most 15 words

Tags are saved in data/news/news_tags.csv (airports joined with "|").
Headlines already tagged are skipped, so each headline costs one LLM call share only once.
"""

import os

import pandas as pd

from src.ai.llm import ask
from src.config import AIRPORTS, NEWS_FILE, NEWS_TAGS_FILE

CAUSES = [
    "fog_or_low_visibility",
    "rain_or_storm",
    "technical_fault",       # aircraft or system fault
    "airline_operations",    # crew, schedule, airline-side problems
    "airport_or_air_traffic",  # runway closure, congestion, air traffic control
    "security_or_conflict",  # security alert, threat, airspace closure
    "strike",
    "other",
]
BATCH_SIZE = 30

PROMPT = """You are sorting news headlines for a flight-delay tracker covering three Indian airports:
DEL (Delhi), BOM (Mumbai), BLR (Bengaluru).

For EACH headline return one JSON object with:
  "id": the id exactly as given
  "is_relevant": true only if the headline reports flights being delayed, cancelled, diverted or
                 suspended that affect flights to or from India. Airport construction, renaming,
                 fares, awards and general aviation business news are NOT relevant.
  "airports": a list with any of {airports} that the headline clearly concerns; [] if none or unclear
  "cause": exactly one of {causes} (use "other" if not relevant or not stated)
  "summary": what happened, in at most 15 words, using only what the headline says

Return a JSON array with exactly {count} objects and nothing else.

Headlines:
{headlines}
"""


def tag_batch(batch):
    lines = "\n".join(f"[id: {row.news_id}] ({row.published_at:%d %b %Y}) {row.title}" for row in batch.itertuples())
    # use_cache=False: this step runs before the database exists in the scheduled job
    answers = ask(PROMPT.format(airports=AIRPORTS, causes=CAUSES, count=len(batch), headlines=lines), as_json=True, use_cache=False)

    # Keep only ids that were sent, and force every field back into its allowed values.
    sent = set(batch["news_id"])
    rows = []
    for answer in answers:
        if not isinstance(answer, dict) or answer.get("id") not in sent:
            continue
        airports = [a for a in answer.get("airports") or [] if a in AIRPORTS]
        rows.append(
            {
                "news_id": answer["id"],
                "is_relevant": bool(answer.get("is_relevant")),
                "airports": "|".join(airports),
                "cause": answer.get("cause") if answer.get("cause") in CAUSES else "other",
                "summary": str(answer.get("summary", ""))[:200],
            }
        )
    return rows


def main():
    news = pd.read_csv(NEWS_FILE, parse_dates=["published_at"])
    columns = ["news_id", "is_relevant", "airports", "cause", "summary"]
    tags = pd.read_csv(NEWS_TAGS_FILE, keep_default_na=False) if os.path.exists(NEWS_TAGS_FILE) else pd.DataFrame(columns=columns)

    todo = news[~news["news_id"].isin(tags["news_id"])].sort_values("published_at")
    print(f"{len(todo)} headlines to tag.")

    for start in range(0, len(todo), BATCH_SIZE):
        rows = tag_batch(todo.iloc[start : start + BATCH_SIZE])
        tags = pd.concat([tags, pd.DataFrame(rows, columns=columns)], ignore_index=True)
        tags.to_csv(NEWS_TAGS_FILE, index=False)  # saved after every batch, so an interrupted run loses nothing
        print(f"  batch {start // BATCH_SIZE + 1}: saved {len(rows)}", flush=True)

    relevant = tags[tags["is_relevant"].astype(str).str.lower() == "true"]
    print(f"\n{len(tags)} headlines tagged; {len(relevant)} relevant.")
    print(relevant["cause"].value_counts().to_string())


if __name__ == "__main__":
    main()
