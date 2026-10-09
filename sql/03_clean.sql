-- Clean layer: turn the stored API answers (JSON) into one row per flight.
-- Re-running this file rebuilds the clean schema; it never calls the API.

DROP SCHEMA IF EXISTS clean CASCADE;
CREATE SCHEMA clean;


-- ---------------------------------------------------------------------
-- airlines: display names. The API's names are wrong or missing for a
-- few Indian carriers, so those are corrected here by airline code.
-- ---------------------------------------------------------------------
CREATE TABLE clean.airline_names (
    airline      VARCHAR(3) PRIMARY KEY,
    airline_name TEXT NOT NULL
);
INSERT INTO clean.airline_names VALUES
    ('6E', 'IndiGo'), ('AI', 'Air India'), ('IX', 'Air India Express'),
    ('QP', 'Akasa Air'), ('SG', 'SpiceJet'), ('9I', 'Alliance Air'), ('S5', 'Star Air');


-- ---------------------------------------------------------------------
-- flights: one row per departure.
--
-- jsonb_array_elements() turns the "departures" array of each stored API
-- answer into rows; ->  and ->> pick fields out of the JSON.
--
-- A delayed flight can appear in two time windows, so DISTINCT ON keeps
-- one row per (airport, flight number, scheduled time): the most recently
-- fetched one.
--
-- Times are local (India time for departures). The first 16 characters of
-- the API's local time, e.g. '2026-10-08 00:12', are the clock time.
--
-- took_off: the runway time when the API has it; otherwise the revised
-- time, but only if it differs from the schedule (an unchanged revised
-- time is just a copy of the schedule, not a real observation).
-- ---------------------------------------------------------------------
CREATE TABLE clean.flights AS
WITH unpacked AS (
    SELECT DISTINCT ON (c.airport, j ->> 'number', j -> 'departure' -> 'scheduledTime' ->> 'utc')
        c.airport                                                         AS origin,
        j ->> 'number'                                                    AS flight_number,
        NULLIF(j -> 'airline' ->> 'iata', '')                             AS airline,
        j -> 'airline' ->> 'name'                                         AS api_airline_name,
        j -> 'arrival' -> 'airport' ->> 'iata'                            AS dest,
        j -> 'arrival' -> 'airport' ->> 'name'                            AS dest_name,
        UPPER(j -> 'arrival' -> 'airport' ->> 'countryCode')              AS dest_country,
        NULLIF(j -> 'aircraft' ->> 'reg', '')                             AS aircraft_reg,
        j -> 'aircraft' ->> 'model'                                       AS aircraft_model,
        j ->> 'status'                                                    AS api_status,
        LEFT(j -> 'departure' -> 'scheduledTime' ->> 'local', 16)::timestamp AS sched_dep,
        LEFT(j -> 'departure' -> 'revisedTime'   ->> 'local', 16)::timestamp AS revised_dep,
        LEFT(j -> 'departure' -> 'runwayTime'    ->> 'local', 16)::timestamp AS runway_dep,
        LEFT(j -> 'arrival'   -> 'scheduledTime' ->> 'local', 16)::timestamp AS sched_arr,
        LEFT(j -> 'arrival'   -> 'runwayTime'    ->> 'local', 16)::timestamp AS landed,
        j -> 'departure' ->> 'terminal'                                   AS terminal
    FROM raw.api_calls AS c
    CROSS JOIN LATERAL jsonb_array_elements(c.payload -> 'departures') AS j
    ORDER BY c.airport, j ->> 'number', j -> 'departure' -> 'scheduledTime' ->> 'utc', c.fetched_at DESC
),
timed AS (
    SELECT
        u.*,
        COALESCE(u.runway_dep, CASE WHEN u.revised_dep <> u.sched_dep THEN u.revised_dep END) AS took_off
    FROM unpacked AS u
    WHERE u.airline IS NOT NULL      -- rows without an airline code are radar-only duplicates or private flights
      AND u.dest IS NOT NULL
)
SELECT
    ROW_NUMBER() OVER (ORDER BY sched_dep, origin, flight_number)     AS flight_id,
    sched_dep::date                                                   AS flight_date,
    origin,
    flight_number,
    t.airline,
    COALESCE(n.airline_name, t.api_airline_name)                      AS airline_name,
    dest,
    dest_name,
    (dest_country <> 'IN')                                            AS is_international,
    aircraft_reg,
    aircraft_model,
    terminal,
    sched_dep,
    took_off,
    sched_arr,
    landed,
    ROUND(EXTRACT(EPOCH FROM took_off - sched_dep) / 60)::int         AS minutes_after_schedule,
    ROUND(EXTRACT(EPOCH FROM landed - sched_arr) / 60)::int           AS arrival_delay_min,
    (api_status = 'Canceled')                                         AS is_cancelled,
    -- One readable status per flight. A flight normally takes off 15 to 20
    -- minutes after its scheduled departure (push-back and taxi), so it is
    -- called late only when take-off is 30 or more minutes after schedule.
    CASE
        WHEN api_status = 'Canceled'                                  THEN 'canceled'
        WHEN took_off IS NULL                                         THEN 'no actual time'
        WHEN took_off - sched_dep >= INTERVAL '30 minutes'            THEN 'late'
        ELSE 'on time'
    END                                                               AS status
FROM timed AS t
LEFT JOIN clean.airline_names AS n ON n.airline = t.airline
WHERE t.origin IN (SELECT airport FROM raw.airports WHERE is_followed);

ALTER TABLE clean.flights ADD PRIMARY KEY (flight_id);
CREATE INDEX idx_flights_reg_dep     ON clean.flights (aircraft_reg, sched_dep);
CREATE INDEX idx_flights_origin_date ON clean.flights (origin, flight_date);


-- ---------------------------------------------------------------------
-- previous_leg: the flight the same aircraft flew just before this one.
--
-- LAG() looks one row back among the flights of the same aircraft
-- registration, ordered by time. It only counts as the previous leg when
-- that flight landed at the airport this one leaves from, within 12 hours.
-- Only flights that left one of the followed airports are in the data, so
-- many aircraft have no known previous leg.
-- ---------------------------------------------------------------------
CREATE TABLE clean.previous_leg AS
WITH ordered AS (
    SELECT
        flight_id,
        origin,
        sched_dep,
        LAG(flight_number)     OVER aircraft AS prev_flight_number,
        LAG(origin)            OVER aircraft AS prev_origin,
        LAG(dest)              OVER aircraft AS prev_dest,
        LAG(sched_dep)         OVER aircraft AS prev_sched_dep,
        LAG(minutes_after_schedule) OVER aircraft AS prev_minutes_after_schedule,
        LAG(arrival_delay_min) OVER aircraft AS prev_arrival_delay_min,
        LAG(is_cancelled)      OVER aircraft AS prev_is_cancelled
    FROM clean.flights
    WHERE aircraft_reg IS NOT NULL
    WINDOW aircraft AS (PARTITION BY aircraft_reg ORDER BY sched_dep, flight_id)
)
SELECT flight_id, prev_flight_number, prev_origin, prev_minutes_after_schedule, prev_arrival_delay_min
FROM ordered
WHERE prev_dest = origin
  AND NOT prev_is_cancelled
  AND sched_dep - prev_sched_dep <= INTERVAL '12 hours';

ALTER TABLE clean.previous_leg ADD PRIMARY KEY (flight_id);

ANALYZE clean.flights;
