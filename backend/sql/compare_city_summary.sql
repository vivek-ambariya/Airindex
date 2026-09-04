-- Headline figures for one city over the compared range.
SELECT ROUND(AVG(daily.value), 2) AS mean_value,
       ROUND(MIN(daily.value), 2) AS min_value,
       ROUND(MAX(daily.value), 2) AS max_value,
       COUNT(*)                   AS n_days,
       ROUND(AVG(daily.mean_completeness), 2) AS mean_completeness,
       MAX(daily.n_stations)      AS max_stations
FROM (
    SELECT rd.reading_date,
           AVG(rd.value)        AS value,
           AVG(rd.completeness) AS mean_completeness,
           COUNT(DISTINCT rd.station_id) AS n_stations
    FROM readings_daily rd
    JOIN stations s ON s.id = rd.station_id
    WHERE s.city         = %(city)s
      AND s.country_code = %(country)s
      AND rd.parameter   = %(parameter)s
      AND rd.completeness >= %(min_completeness)s
      AND rd.reading_date BETWEEN %(date_from)s AND %(date_to)s
    GROUP BY rd.reading_date
) daily;
