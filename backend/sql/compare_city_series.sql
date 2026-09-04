-- One city's daily series for the comparison view.
--
-- Run once per city rather than with an IN list over a joined set. Two
-- reasons: `city = %(city)s` uses ix_city where FIND_IN_SET could not,
-- and it keeps the promise that no SQL is ever assembled by string
-- concatenation -- a variable-length IN list cannot be parameterized in
-- one statement without building placeholders. The city count is capped
-- at 5 by the route, so this is at most five indexed queries.
--
-- A city value is the unweighted mean of its stations' daily values.
-- Stations below the completeness floor are excluded outright rather
-- than down-weighted, and n_stations is returned so a day backed by one
-- station is distinguishable from a day backed by twelve.
SELECT rd.reading_date,
       ROUND(AVG(rd.value), 3)          AS value,
       COUNT(DISTINCT rd.station_id)    AS n_stations,
       ROUND(AVG(rd.completeness), 2)   AS mean_completeness
FROM readings_daily rd
JOIN stations s ON s.id = rd.station_id
WHERE s.city        = %(city)s
  AND s.country_code = %(country)s
  AND rd.parameter  = %(parameter)s
  AND rd.completeness >= %(min_completeness)s
  AND rd.reading_date BETWEEN %(date_from)s AND %(date_to)s
GROUP BY rd.reading_date
ORDER BY rd.reading_date;
