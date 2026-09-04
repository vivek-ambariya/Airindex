-- Phase 6 analysis dataset: one row per city-day.
--
-- Runs in DuckDB directly over the Parquet lake -- no database needed,
-- which is the point of keeping data/clean/ as files as well as loading
-- it into MariaDB. The API serves the app; this serves the analysis.
--
-- Aggregated to CITY-day rather than station-day, deliberately:
--   * ERA5's grid is ~25 km, so every Delhi station would be joined to
--     an identical weather row. Station-day rows would inflate n roughly
--     sevenfold while adding no independent weather information, and the
--     standard errors would be badly understated.
--   * The question is about a city's winter, not a monitor's.
--
-- Days below the completeness floor are excluded, not down-weighted: a
-- day averaged from four hours is not a measurement of that day, and
-- including it would put measurement error in the dependent variable
-- exactly when the weather is calmest.
WITH daily AS (
    SELECT
        CAST(reading_date AS DATE) AS reading_date,
        AVG(value)                 AS pm25,
        COUNT(DISTINCT name)       AS n_stations,
        AVG(completeness)          AS mean_completeness
    FROM read_parquet($clean_glob)
    WHERE city = $city
      AND parameter = 'pm25'
      AND completeness >= $min_completeness
    GROUP BY 1
),
weather AS (
    SELECT
        CAST(reading_date AS DATE)  AS reading_date,
        temperature_2m_mean,
        temperature_2m_min,
        wind_speed_10m_mean,
        wind_speed_10m_max,
        wind_direction_10m_dominant,
        precipitation_sum,
        shortwave_radiation_sum
    FROM read_parquet($weather_path)
)
SELECT
    d.reading_date,
    EXTRACT(year  FROM d.reading_date)  AS year,
    EXTRACT(month FROM d.reading_date)  AS month,
    EXTRACT(doy   FROM d.reading_date)  AS doy,
    -- Day of week, to absorb the weekly emissions cycle (freight,
    -- construction and commuting are all lower on Sundays).
    EXTRACT(dow   FROM d.reading_date)  AS dow,
    d.pm25,
    d.n_stations,
    d.mean_completeness,
    w.temperature_2m_mean,
    w.temperature_2m_min,
    w.wind_speed_10m_mean,
    w.wind_speed_10m_max,
    w.wind_direction_10m_dominant,
    w.precipitation_sum,
    w.shortwave_radiation_sum,
    -- Winter as the analysis defines it: November, December, January.
    -- The months when the Indo-Gangetic inversion is established.
    CASE WHEN EXTRACT(month FROM d.reading_date) IN (11, 12, 1)
         THEN 1 ELSE 0 END AS winter,
    -- Monsoon, kept separate. Lumping it into "not winter" would make
    -- the baseline a mixture of the wettest and driest months.
    CASE WHEN EXTRACT(month FROM d.reading_date) IN (6, 7, 8, 9)
         THEN 1 ELSE 0 END AS monsoon
FROM daily d
JOIN weather w USING (reading_date)
ORDER BY d.reading_date;
