-- Features for the flight-delay prediction model.
-- Question: 30 minutes before a flight's scheduled departure, can we
-- tell whether it will take off 30 or more minutes late?
--
-- One row per departure that has an actual take-off time (status
-- 'on time' or 'late'). Cancelled flights and flights with no actual
-- time are left out: for them "late" cannot be measured.
--
-- RULE FOR EVERY COLUMN: it must be known 30 minutes before scheduled
-- departure. Nothing about this flight's own take-off is used.
--
--   history columns   built from PREVIOUS DAYS only
--   airport_now_*     flights of the same airport scheduled between 4 hours
--                     and 1 hour before this one. A flight scheduled an hour
--                     earlier is known to be late by the time it is 30 minutes
--                     overdue, which is 30 minutes before this departure.
--   prev_leg_*        the same aircraft's previous flight, already flown
--
-- The table lives in its own schema (ml), away from the tables the website reads.
-- Run this after sql/04_mart.sql.

CREATE SCHEMA IF NOT EXISTS ml;
DROP TABLE IF EXISTS ml.flight_features;

CREATE TABLE ml.flight_features AS
WITH tracked AS (
    SELECT f.*, (f.status = 'late')::int AS late
    FROM mart.fact_flights AS f
    WHERE f.status IN ('on time', 'late')
),

-- Late counts per day for each key, then a running total over the days BEFORE each day.
flight_number_history AS (
    SELECT origin, flight_number, flight_date,
           SUM(COUNT(*))  OVER before_today AS past_flights,
           SUM(SUM(late)) OVER before_today AS past_late
    FROM tracked
    GROUP BY origin, flight_number, flight_date
    WINDOW before_today AS (PARTITION BY origin, flight_number ORDER BY flight_date
                            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
),
airline_history AS (
    SELECT origin, airline_name, flight_date,
           SUM(COUNT(*))  OVER before_today AS past_flights,
           SUM(SUM(late)) OVER before_today AS past_late
    FROM tracked
    GROUP BY origin, airline_name, flight_date
    WINDOW before_today AS (PARTITION BY origin, airline_name ORDER BY flight_date
                            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
),
hour_history AS (
    SELECT origin, dep_hour, flight_date,
           SUM(COUNT(*))  OVER before_today AS past_flights,
           SUM(SUM(late)) OVER before_today AS past_late
    FROM tracked
    GROUP BY origin, dep_hour, flight_date
    WINDOW before_today AS (PARTITION BY origin, dep_hour ORDER BY flight_date
                            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
),

-- How the airport has been running in the hours just before this flight.
airport_now AS (
    SELECT flight_id,
           COUNT(*)  OVER earlier_today AS airport_now_flights,
           SUM(late) OVER earlier_today AS airport_now_late
    FROM tracked
    WINDOW earlier_today AS (PARTITION BY origin ORDER BY sched_dep
                             RANGE BETWEEN INTERVAL '4 hours' PRECEDING AND INTERVAL '1 hour' PRECEDING)
)

SELECT
    t.flight_id,
    t.flight_date,
    t.late AS is_late,

    -- the flight itself
    t.origin,
    t.airline_name,
    t.dest,
    t.is_international::int                      AS is_international,
    t.dep_hour,
    EXTRACT(ISODOW FROM t.flight_date)::int      AS weekday,

    -- forecast weather for the scheduled hour
    t.precipitation_mm,
    t.wind_gusts_kmh,
    t.visibility_m,
    t.temperature_c,
    COALESCE(t.weather_condition, 'unknown')     AS weather_condition,

    -- the same aircraft's previous flight
    (t.prev_flight_number IS NOT NULL)::int      AS has_prev_leg,
    t.prev_leg_late::int                         AS prev_leg_late,
    t.prev_arrival_delay_min,

    -- the airport in the hours before
    COALESCE(a.airport_now_flights, 0)           AS airport_now_flights,
    ROUND(a.airport_now_late::numeric / NULLIF(a.airport_now_flights, 0), 4) AS airport_now_late_rate,

    -- track record from previous days
    COALESCE(fh.past_flights, 0)                 AS flight_past_flights,
    ROUND(fh.past_late / NULLIF(fh.past_flights, 0), 4) AS flight_past_late_rate,
    ROUND(ah.past_late / NULLIF(ah.past_flights, 0), 4) AS airline_past_late_rate,
    ROUND(hh.past_late / NULLIF(hh.past_flights, 0), 4) AS hour_past_late_rate
FROM tracked AS t
JOIN airport_now AS a ON a.flight_id = t.flight_id
LEFT JOIN flight_number_history AS fh
       ON fh.origin = t.origin AND fh.flight_number = t.flight_number AND fh.flight_date = t.flight_date
LEFT JOIN airline_history AS ah
       ON ah.origin = t.origin AND ah.airline_name = t.airline_name AND ah.flight_date = t.flight_date
LEFT JOIN hour_history AS hh
       ON hh.origin = t.origin AND hh.dep_hour = t.dep_hour AND hh.flight_date = t.flight_date
-- only days for which the whole day was collected
WHERE EXISTS (SELECT 1 FROM mart.airport_daily AS d WHERE d.airport = t.origin AND d.flight_date = t.flight_date);

ALTER TABLE ml.flight_features ADD PRIMARY KEY (flight_id);
