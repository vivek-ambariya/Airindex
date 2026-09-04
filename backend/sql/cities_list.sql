-- Cities that have at least one station with data, for the compare
-- picker and the dashboard league table.
SELECT s.city,
       s.state,
       COUNT(DISTINCT s.id)                AS n_stations,
       ROUND(AVG(rd.value), 2)             AS mean_value,
       ROUND(SUM(rd.n_hours) / (COUNT(DISTINCT rd.reading_date) * 24) * 100, 2) AS mean_completeness,
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
