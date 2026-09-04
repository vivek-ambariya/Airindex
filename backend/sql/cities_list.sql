-- Cities that have at least one station with data, for the compare
-- picker and the dashboard league table.
SELECT s.city,
       s.state,
       COUNT(DISTINCT s.id)                AS n_stations,
       ROUND(AVG(rd.value), 2)             AS mean_value,
       -- Denominator is stations x days x 24, NOT days x 24.
       --
       -- Summing n_hours across a city's stations while dividing by
       -- distinct DATES made this scale with station count: Delhi's
       -- seven stations reported 659% complete and two-station cities
       -- reported 188%. It is not only a wrong label -- this figure
       -- gates whether the city gets a colour band at all, so an
       -- inflated value could grant a band to a city whose monitors
       -- barely reported.
       --
       -- The date span (rather than COUNT(*)) keeps days on which a
       -- station reported nothing at all in the denominator, so going
       -- quiet lowers the score instead of being invisible.
       ROUND(SUM(rd.n_hours) /
             (COUNT(DISTINCT rd.station_id)
              * (DATEDIFF(MAX(rd.reading_date), MIN(rd.reading_date)) + 1)
              * 24) * 100, 2) AS mean_completeness,
       MIN(rd.reading_date)                AS first_date,
       MAX(rd.reading_date)                AS last_date,
       COUNT(*)                            AS n_rows
FROM stations s
JOIN readings_daily rd ON rd.station_id = s.id
WHERE s.country_code = %(country)s
  AND s.city IS NOT NULL
  AND rd.parameter = %(parameter)s
GROUP BY s.city, s.state
ORDER BY mean_value DESC;
