"""Ask DelayLens: answer a question about the flight data in plain English.

How one question is answered:
  1. PLAN     The LLM reads the question and the table descriptions and writes
              up to three SQL queries (for example: the flights of that day,
              the weather of that day, the news of that day).
  2. GUARD    Each query is parsed and must be a single read-only SELECT on
              the known tables. Anything else is refused.
  3. RUN      The queries run on an in-memory SQLite copy of the site's data
              files, opened in query-only mode.
  4. ANSWER   The LLM writes the answer from the result rows only.
  5. CHECK    Every number in the answer is looked up in the result rows; the
              page shows how many could be verified.

The LLM never calculates or remembers a number: it writes queries and words
the answer. The site works without a database server, so this also runs on
the hosted version.
"""

import json
import os
import re
import sqlite3
import time

import pandas as pd
import sqlglot
import streamlit as st
from google import genai
from google.genai import errors, types
from sqlglot import exp

from common import load

MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]  # second one is used if the first is busy
TABLES = ["flights", "airport_daily", "flight_punctuality", "weather_hourly", "news", "airports"]
MAX_ROWS = 60
MAX_QUERIES = 3

SCHEMA_NOTES = """
Tables (SQLite). Dates are text 'YYYY-MM-DD'; date-times are text 'YYYY-MM-DD HH:MM:SS' in India time.

flights: one row per departure.
  flight_date, origin (BOM Mumbai, BLR Bengaluru, HYD Hyderabad), flight_number (e.g. '6E 5237'), airline (code),
  airline_name, dest (airport code), dest_name, is_international (0/1), aircraft_reg, sched_dep, took_off,
  minutes_after_schedule (minutes between scheduled departure and actual take-off; NULL when not recorded),
  status ('on time', 'late', 'canceled', 'no actual time'), dep_hour (0-23),
  prev_flight_number, prev_origin, prev_arrival_delay_min (the same aircraft's previous flight; often NULL),
  temperature_c, precipitation_mm, wind_gusts_kmh, visibility_m, weather_condition (weather at origin in the departure hour)

airport_daily: one row per airport and day.
  airport, flight_date, flights, tracked_flights, late_flights, cancelled_flights, late_rate_pct, avg_minutes_when_late

flight_punctuality: one row per origin and flight number (its track record over all days).
  origin, flight_number, airline_name, dest, dest_name, usual_departure, days_seen, days_tracked, days_late, late_pct,
  avg_minutes_after_schedule, worst_minutes_after_schedule

weather_hourly: one row per airport and hour.
  airport, weather_time, temperature_c, humidity_pct, precipitation_mm, wind_gusts_kmh, visibility_m,
  weather_condition ('dry and calm', 'light rain', 'rain', 'strong wind', 'low visibility', 'thunderstorm')

news: recent headlines about flight disruption in India, tagged by an AI model.
  published_at, title, source, cause, summary

airports: airport, airport_name, city

Rules:
- A flight is LATE when status = 'late' (took off 30 or more minutes after schedule).
- A late RATE is 100.0 * late flights / flights with minutes_after_schedule IS NOT NULL. Never divide by all flights.
- Data covers {first_day} to {last_day}. Only Mumbai (BOM), Bengaluru (BLR) and Hyderabad (HYD) departures exist. Delhi departures are NOT in the data (Delhi appears only as a destination).
- For "why" questions, also query weather_hourly for that airport and day, and news for those dates.
- Use LIKE with wildcards for names (e.g. airline_name LIKE '%Akasa%').
- When ranking airlines, routes or destinations, include only those with at least 40 tracked flights, so a carrier
  with a handful of flights does not top the list. For single flight numbers require at least 3 tracked days.
- Always return the counts behind a rate (tracked flights, late flights) next to the rate.
"""

PLAN_PROMPT = """You are the data analyst behind a flight-delay website. Today is {today}.
{schema}
Question: {question}

Write up to {max_queries} SQLite SELECT queries that together give the evidence needed to answer.
Each query must return at most {max_rows} rows (aggregate, or use LIMIT). Use only the tables and columns above.
If the question cannot be answered from this data, return an empty list and say why.

Reply as JSON: {{"queries": [{{"purpose": "<a few words>", "sql": "<query>"}}], "note": "<empty, or why it cannot be answered>"}}
"""

ANSWER_PROMPT = """A user of a flight-delay website asked: "{question}"

These queries were run on the data:
{evidence}

Write the answer in 2 to 5 sentences for a traveller, in plain English.
- Use ONLY numbers and facts that appear in the results above. Do not add outside knowledge or guesses.
- A late rate is counted over TRACKED flights. Say "X late out of Y tracked flights", never out of all flights.
- For a "why" question, say what the evidence shows (weather, the aircraft's previous flight, how the whole airport
  did that day, news) and say clearly when the evidence does not show a cause. India publishes no official cause per flight.
- If the results are empty, say that no matching data was found and what period the data covers.
"""


def get_api_key():
    """The Gemini key from the environment, or from Streamlit secrets on the hosted site."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        try:
            key = st.secrets["GEMINI_API_KEY"]
        except Exception:
            key = None
    return key


@st.cache_resource
def get_database():
    """In-memory SQLite copy of the site's data files, switched to read-only after loading."""
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    for name in TABLES:
        frame = load(name).copy()
        for column in frame.columns:
            if pd.api.types.is_datetime64_any_dtype(frame[column]):
                # dates without a time become 'YYYY-MM-DD', others keep the time
                only_dates = (frame[column].dropna().dt.normalize() == frame[column].dropna()).all()
                frame[column] = frame[column].dt.strftime("%Y-%m-%d" if only_dates else "%Y-%m-%d %H:%M:%S")
        frame.to_sql(name, connection, index=False)
    connection.execute("PRAGMA query_only = ON")  # the database itself now refuses any write
    return connection


def check_sql(sql):
    """Return the query with a row limit if it is a safe read-only SELECT; otherwise raise ValueError."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except sqlglot.errors.ParseError as error:
        raise ValueError(f"could not be parsed: {error}") from error
    if len(statements) != 1:
        raise ValueError("only one statement is allowed")
    statement = statements[0]
    if not isinstance(statement, (exp.Select, exp.Union)):
        raise ValueError("only SELECT is allowed")
    blocked = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command, exp.Pragma, exp.Attach)
    if any(isinstance(node, blocked) for node in statement.walk()):
        raise ValueError("the query tries to change something")
    cte_names = {cte.alias_or_name for cte in statement.find_all(exp.CTE)}
    for table in statement.find_all(exp.Table):
        if table.name not in TABLES and table.name not in cte_names:
            raise ValueError(f"unknown table: {table.name}")
    if statement.args.get("limit") is None:
        statement = statement.limit(MAX_ROWS)
    return statement.sql(dialect="sqlite")


@st.cache_data(show_spinner=False)
def ask_llm(prompt, as_json):
    """One LLM call, with a retry on the second model when the first is busy. Cached by prompt."""
    client = genai.Client(api_key=get_api_key())
    config = types.GenerateContentConfig(temperature=0, response_mime_type="application/json" if as_json else "text/plain")
    last_error = None
    for attempt in range(3):
        for model in MODELS:
            try:
                response = client.models.generate_content(model=model, contents=prompt, config=config)
                if response.text:
                    return response.text
            except errors.APIError as error:
                last_error = error
                if error.code not in (429, 500, 503):
                    raise
        time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"The AI model is busy right now. Please try again in a minute. ({last_error})")


def verify_numbers(answer, evidence_text):
    """How many of the numbers in the answer can be found in the result rows."""
    numbers = re.findall(r"\d+(?:\.\d+)?", answer.replace(",", ""))
    numbers = [n for n in numbers if len(n) > 1 or "." in n]  # single digits are too common to be meaningful
    haystack = evidence_text.replace(",", "")
    found = 0
    for number in numbers:
        value = float(number)
        variants = {number, f"{value:.0f}", f"{value:.1f}", f"{value:.2f}"}
        found += any(variant in haystack for variant in variants)
    return found, len(numbers)


def answer_question(question):
    """Run the whole flow. Returns a dictionary with the answer and every step taken."""
    database = get_database()
    days = load("airport_daily")["flight_date"]
    schema = SCHEMA_NOTES.format(first_day=f"{days.min():%Y-%m-%d}", last_day=f"{days.max():%Y-%m-%d}")
    result = {"question": question, "steps": [], "answer": None, "note": None, "verified": None}

    plan = json.loads(ask_llm(
        PLAN_PROMPT.format(today=f"{pd.Timestamp.now():%Y-%m-%d}", schema=schema, question=question,
                           max_queries=MAX_QUERIES, max_rows=MAX_ROWS),
        as_json=True,
    ))
    result["note"] = plan.get("note") or None

    for item in (plan.get("queries") or [])[:MAX_QUERIES]:
        step = {"purpose": item.get("purpose", ""), "sql": item.get("sql", ""), "rows": None, "error": None}
        try:
            step["sql"] = check_sql(step["sql"])
            step["rows"] = pd.read_sql_query(step["sql"], database)
        except Exception as error:
            step["error"] = str(error).splitlines()[0]
        result["steps"].append(step)

    usable = [step for step in result["steps"] if step["rows"] is not None]
    if not usable:
        result["answer"] = result["note"] or "I could not find a way to answer that from the flight data."
        return result

    evidence = "\n\n".join(f"-- {step['purpose']}\n{step['sql']}\nResult:\n{step['rows'].to_csv(index=False)}" for step in usable)
    result["answer"] = ask_llm(ANSWER_PROMPT.format(question=question, evidence=evidence), as_json=False).strip()
    result["verified"] = verify_numbers(result["answer"], evidence)
    return result
