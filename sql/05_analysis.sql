-- Summary tables for the website. Each holds COUNTS (not ready-made rates),
-- so the site can combine any airports or airlines and still calculate
-- exact rates. Only flights with a known take-off time count as "tracked".
-- Run after 04_mart.sql.

-- Business question: how do airports and airlines perform day by day?
DROP TABLE IF EXISTS mart.daily_summary;
CREATE TABLE mart.daily_summary AS
SELECT
    flight_date,
    origin                                   AS airport,
    airline_name,
    COUNT(*)                                 AS flights,
    COUNT(*) FILTER (WHERE has_actual_time)  AS tracked_flights,
    COUNT(*) FILTER (WHERE is_late)          AS late_flights,
    COUNT(*) FILTER (WHERE is_cancelled)     AS cancelled_flights,
    COALESCE(SUM(minutes_after_schedule) FILTER (WHERE is_late), 0) AS late_minutes
FROM mart.fact_flights
WHERE flight_date IN (SELECT flight_date FROM mart.airport_daily)
GROUP BY 1, 2, 3;

-- Business question: at what hour is a late departure most likely?
DROP TABLE IF EXISTS mart.hourly_pattern;
CREATE TABLE mart.hourly_pattern AS
SELECT
    origin                                   AS airport,
    dep_hour,
    COUNT(*)                                 AS flights,
    COUNT(*) FILTER (WHERE has_actual_time)  AS tracked_flights,
    COUNT(*) FILTER (WHERE is_late)          AS late_flights
FROM mart.fact_flights
GROUP BY 1, 2;

-- Business question: how much does the weather at departure change the late rate?
DROP TABLE IF EXISTS mart.weather_impact;
CREATE TABLE mart.weather_impact AS
SELECT
    origin                                   AS airport,
    weather_condition,
    COUNT(*)                                 AS flights,
    COUNT(*) FILTER (WHERE has_actual_time)  AS tracked_flights,
    COUNT(*) FILTER (WHERE is_late)          AS late_flights,
    COUNT(*) FILTER (WHERE is_cancelled)     AS cancelled_flights,
    COALESCE(SUM(minutes_after_schedule) FILTER (WHERE is_late), 0) AS late_minutes
FROM mart.fact_flights
WHERE weather_condition IS NOT NULL
GROUP BY 1, 2;

-- Business question: does a late incoming aircraft make the next flight late?
DROP TABLE IF EXISTS mart.knock_on;
CREATE TABLE mart.knock_on AS
SELECT
    origin AS airport,
    CASE WHEN prev_leg_late THEN 'aircraft arrived late' ELSE 'aircraft arrived on time' END AS previous_leg,
    COUNT(*) FILTER (WHERE has_actual_time)  AS tracked_flights,
    COUNT(*) FILTER (WHERE is_late)          AS late_flights
FROM mart.fact_flights
WHERE prev_leg_late IS NOT NULL
GROUP BY 1, 2;

-- Business question: which routes are the most and least reliable?
DROP TABLE IF EXISTS mart.route_summary;
CREATE TABLE mart.route_summary AS
SELECT
    origin,
    dest,
    MAX(dest_name)                           AS dest_name,
    BOOL_OR(is_international)                AS is_international,
    COUNT(*)                                 AS flights,
    COUNT(*) FILTER (WHERE has_actual_time)  AS tracked_flights,
    COUNT(*) FILTER (WHERE is_late)          AS late_flights,
    COUNT(*) FILTER (WHERE is_cancelled)     AS cancelled_flights,
    ROUND(AVG(minutes_after_schedule) FILTER (WHERE is_late)) AS avg_minutes_when_late
FROM mart.fact_flights
GROUP BY 1, 2
HAVING COUNT(*) FILTER (WHERE has_actual_time) >= 15;
