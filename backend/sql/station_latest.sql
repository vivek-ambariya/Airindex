-- The most recent daily reading for one station and parameter.
SELECT reading_date,
       CAST(value AS DOUBLE)        AS value,
       n_hours,
       CAST(completeness AS DOUBLE) AS completeness
FROM readings_daily
WHERE station_id = %(station_id)s
  AND parameter  = %(parameter)s
ORDER BY reading_date DESC
LIMIT 1;
