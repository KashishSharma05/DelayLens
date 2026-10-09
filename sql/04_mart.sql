-- Mart layer: flights with weather and the aircraft's previous leg attached,
-- plus the tables the website reads. Re-running this file rebuilds the schema.

DROP SCHEMA IF EXISTS mart CASCADE;
CREATE SCHEMA mart;

-- Only the airports that are being followed (see data/reference/airports.csv).
CREATE TABLE mart.dim_airport AS
SELECT airport, icao, airport_name, city, latitude, longitude, timezone
FROM raw.airports
WHERE is_followed;
ALTER TABLE mart.dim_airport ADD PRIMARY KEY (airport);

CREATE TABLE mart.weather_hourly AS
SELECT w.*,
       -- one readable label for the weather in that hour, worst condition first
       CASE
           WHEN w.weather_code >= 95        THEN 'thunderstorm'
           WHEN w.visibility_m < 1500       THEN 'low visibility'
           WHEN w.precipitation_mm >= 2.5   THEN 'rain'
           WHEN w.precipitation_mm > 0      THEN 'light rain'
           WHEN w.wind_gusts_kmh >= 45      THEN 'strong wind'
           ELSE 'dry and calm'
       END AS weather_condition
FROM raw.weather_hourly AS w
WHERE w.airport IN (SELECT airport FROM mart.dim_airport);
ALTER TABLE mart.weather_hourly ADD PRIMARY KEY (airport, weather_time);


-- =====================================================================
-- fact_flights: one row per departure, with the weather at the airport
-- in the scheduled departure hour and the aircraft's previous leg.
-- DATE_TRUNC('hour', ...) rounds the time down to the hour, which is how
-- the weather table is keyed.
-- =====================================================================
CREATE TABLE mart.fact_flights AS
SELECT
    f.*,
    EXTRACT(HOUR FROM f.sched_dep)::int        AS dep_hour,
    (f.status = 'late')                        AS is_late,
    (f.took_off IS NOT NULL)                   AS has_actual_time,
    p.prev_flight_number,
    p.prev_origin,
    p.prev_arrival_delay_min,
    (p.prev_arrival_delay_min >= 15)           AS prev_leg_late,
    w.temperature_c,
    w.precipitation_mm,
    w.wind_gusts_kmh,
    w.visibility_m,
    w.weather_code,
    w.weather_condition
FROM clean.flights AS f
LEFT JOIN clean.previous_leg AS p ON p.flight_id = f.flight_id
LEFT JOIN mart.weather_hourly AS w
       ON w.airport = f.origin AND w.weather_time = DATE_TRUNC('hour', f.sched_dep);

ALTER TABLE mart.fact_flights ADD PRIMARY KEY (flight_id);
CREATE INDEX idx_fact_origin_date ON mart.fact_flights (origin, flight_date);
CREATE INDEX idx_fact_number      ON mart.fact_flights (flight_number);
ANALYZE mart.fact_flights;


-- =====================================================================
-- airport_daily: one row per airport and day.
-- The late rate is counted over flights whose take-off time is known.
-- =====================================================================
CREATE TABLE mart.airport_daily AS
SELECT
    origin                                              AS airport,
    flight_date,
    COUNT(*)                                            AS flights,
    COUNT(*) FILTER (WHERE has_actual_time)             AS tracked_flights,
    COUNT(*) FILTER (WHERE is_late)                     AS late_flights,
    COUNT(*) FILTER (WHERE is_cancelled)                AS cancelled_flights,
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_late) / NULLIF(COUNT(*) FILTER (WHERE has_actual_time), 0), 1) AS late_rate_pct,
    ROUND(AVG(minutes_after_schedule) FILTER (WHERE is_late))   AS avg_minutes_when_late,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY minutes_after_schedule) AS median_minutes_after_schedule,
    COALESCE(SUM(precipitation_mm) / NULLIF(COUNT(precipitation_mm), 0), 0) AS avg_precipitation_mm,
    COUNT(*) FILTER (WHERE weather_condition = 'thunderstorm')  AS flights_in_thunderstorm,
    MIN(visibility_m)                                   AS min_visibility_m,
    MAX(wind_gusts_kmh)                                 AS max_wind_gusts_kmh
FROM mart.fact_flights AS f
-- only days for which both 12-hour windows were collected, so no half days
WHERE EXISTS (
    SELECT 1 FROM raw.api_calls AS c
    WHERE c.airport = f.origin AND c.window_start::date = f.flight_date
    GROUP BY c.airport HAVING COUNT(*) = 2
)
GROUP BY origin, flight_date;

ALTER TABLE mart.airport_daily ADD PRIMARY KEY (airport, flight_date);


-- =====================================================================
-- flight_punctuality: the track record of each flight number.
-- Business question: how reliable is this particular flight?
-- =====================================================================
CREATE TABLE mart.flight_punctuality AS
SELECT
    origin,
    flight_number,
    MAX(airline_name)                                   AS airline_name,
    MAX(dest)                                           AS dest,
    MAX(dest_name)                                      AS dest_name,
    TO_CHAR(MIN(sched_dep::time), 'HH24:MI')            AS usual_departure,
    COUNT(*)                                            AS days_seen,
    COUNT(*) FILTER (WHERE has_actual_time)             AS days_tracked,
    COUNT(*) FILTER (WHERE is_late)                     AS days_late,
    COUNT(*) FILTER (WHERE is_cancelled)                AS days_cancelled,
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_late) / NULLIF(COUNT(*) FILTER (WHERE has_actual_time), 0)) AS late_pct,
    ROUND(AVG(minutes_after_schedule))                  AS avg_minutes_after_schedule,
    MAX(minutes_after_schedule)                         AS worst_minutes_after_schedule
FROM mart.fact_flights
GROUP BY origin, flight_number;

ALTER TABLE mart.flight_punctuality ADD PRIMARY KEY (origin, flight_number);
