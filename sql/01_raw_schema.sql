-- Raw layer. Filled by src/load_raw.py from the files kept in data/
-- (API answers, weather, news), so the database can be rebuilt anywhere.
-- Re-running this file empties and recreates the raw schema.

DROP SCHEMA IF EXISTS raw CASCADE;
CREATE SCHEMA raw;

-- Airports, with position (for the weather API) and time zone.
-- is_followed is FALSE for airports that were only tested: their API calls
-- stay in the ledger so the unit count is right, but they are not analysed.
CREATE TABLE raw.airports (
    airport      CHAR(3) PRIMARY KEY,      -- IATA code, e.g. BOM
    icao         CHAR(4) NOT NULL,
    airport_name TEXT NOT NULL,
    city         TEXT NOT NULL,
    latitude     NUMERIC(8, 4) NOT NULL,
    longitude    NUMERIC(8, 4) NOT NULL,
    timezone     TEXT NOT NULL,
    is_followed  BOOLEAN NOT NULL
);

-- One row per API call: which airport and 12-hour window, and the full JSON answer.
-- Keeping the whole answer means it can be read in a new way later without another call.
CREATE TABLE raw.api_calls (
    airport      CHAR(3)   NOT NULL REFERENCES raw.airports (airport),
    window_start TIMESTAMP NOT NULL,       -- local time
    window_end   TIMESTAMP NOT NULL,
    fetched_at   TIMESTAMP NOT NULL,
    units_used   INTEGER   NOT NULL,
    flights      INTEGER   NOT NULL,       -- departures in the answer
    payload      JSONB     NOT NULL,
    PRIMARY KEY (airport, window_start)
);

-- One row per airport and hour, in local time.
CREATE TABLE raw.weather_hourly (
    airport          CHAR(3)   NOT NULL REFERENCES raw.airports (airport),
    weather_time     TIMESTAMP NOT NULL,   -- local time, start of the hour
    temperature_c    NUMERIC(5, 1),
    humidity_pct     NUMERIC(5, 1),
    precipitation_mm NUMERIC(6, 2),
    wind_speed_kmh   NUMERIC(6, 1),
    wind_gusts_kmh   NUMERIC(6, 1),
    visibility_m     NUMERIC(8, 1),        -- low visibility = fog, haze or heavy rain
    cloud_cover_pct  NUMERIC(5, 1),
    weather_code     INTEGER,              -- WMO code: 0 clear, 45/48 fog, 51-67 rain, 95-99 thunderstorm
    PRIMARY KEY (airport, weather_time)
);

-- News headlines about flight disruption, with the tags an LLM gave them.
-- Only the headline, source, time and link are stored, never the article text.
CREATE TABLE raw.news (
    news_id      CHAR(16)  PRIMARY KEY,
    published_at TIMESTAMP NOT NULL,       -- India time
    title        TEXT      NOT NULL,
    source       TEXT,
    link         TEXT      NOT NULL,
    search_query TEXT      NOT NULL,
    is_relevant  BOOLEAN,                  -- NULL until the headline has been tagged
    airports     TEXT[],
    cause        TEXT,
    summary      TEXT
);
