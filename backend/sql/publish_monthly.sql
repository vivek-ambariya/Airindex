-- Seasonal profile for every station at once. Pooled across all years,
-- sparse days excluded from the mean rather than down-weighted.
SELECT station_id,
       MONTH(reading_date)         AS month,
       ROUND(AVG(value), 2)        AS value,
       COUNT(*)                    AS n_days
FROM readings_daily
WHERE parameter = %(parameter)s
  AND completeness >= %(min_completeness)s
GROUP BY station_id, MONTH(reading_date)
ORDER BY station_id, month;
