-- Reference and weather tables.

CREATE SCHEMA IF NOT EXISTS raw;

-- The 10 hub airports with their position and time zone.
-- Position is what the weather API is asked for; time zone makes the
-- weather hours line up with the flight times, which are local.
DROP TABLE IF EXISTS raw.airports CASCADE;
CREATE TABLE raw.airports (
    airport      CHAR(3) PRIMARY KEY,
    airport_name TEXT NOT NULL,
    city         TEXT NOT NULL,
    state        CHAR(2) NOT NULL,
    latitude     NUMERIC(8, 4) NOT NULL,
    longitude    NUMERIC(8, 4) NOT NULL,
    timezone     TEXT NOT NULL
);

-- One row per airport and hour, in the airport's local time.
CREATE TABLE IF NOT EXISTS raw.weather_hourly (
    airport          CHAR(3)   NOT NULL,
    weather_time     TIMESTAMP NOT NULL,     -- local time, start of the hour
    temperature_c    NUMERIC(5, 1),
    precipitation_mm NUMERIC(6, 2),          -- rain + melted snow in that hour
    rain_mm          NUMERIC(6, 2),
    snowfall_cm      NUMERIC(6, 2),
    wind_speed_kmh   NUMERIC(6, 1),
    wind_gusts_kmh   NUMERIC(6, 1),
    cloud_cover_pct  NUMERIC(5, 1),
    weather_code     INTEGER,                -- WMO code: 0 clear ... 95-99 thunderstorm
    PRIMARY KEY (airport, weather_time)
);
