-- The national monthly trend on the dashboard: one mean per calendar
-- month across the whole network.
--
-- Averaged over STATIONS, unweighted. This is stated rather than hidden
-- because it is a real choice: Delhi has seven stations in this dataset
-- and Kochi has one, so the "national" figure leans towards wherever the
-- network is dense -- which is the polluted north. It is a mean of
-- monitors, not a mean of people or of land area.
SELECT DATE_FORMAT(reading_date, '%%Y-%%m') AS month,
       ROUND(AVG(value), 2)                AS value,
       COUNT(DISTINCT station_id)          AS n_stations,
       COUNT(*)                            AS n_rows
FROM readings_daily
WHERE parameter = %(parameter)s
  AND completeness >= %(min_completeness)s
GROUP BY DATE_FORMAT(reading_date, '%%Y-%%m')
ORDER BY month;
