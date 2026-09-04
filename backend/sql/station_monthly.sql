-- Twelve monthly averages -- the seasonal profile, pooled across every
-- year the station has data for.
--
-- Days under 50% completeness are excluded from the mean rather than
-- weighted down: a half-empty day is not a measurement of that day.
-- n_days is returned so the frontend can say how much each month rests
-- on instead of drawing twelve equally confident bars.
SELECT MONTH(reading_date)              AS month,
       ROUND(AVG(value), 2)             AS value,
       COUNT(*)                         AS n_days,
       ROUND(AVG(completeness), 2)      AS mean_completeness
FROM readings_daily
WHERE station_id = %(station_id)s
  AND parameter  = %(parameter)s
  AND completeness >= %(min_completeness)s
GROUP BY MONTH(reading_date)
ORDER BY month;
