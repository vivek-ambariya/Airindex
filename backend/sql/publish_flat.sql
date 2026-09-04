-- The flat export Power BI reads. One row per station, date and
-- parameter, denormalised so the .pbix needs no relationships to be
-- useful on first open.
SELECT s.name          AS station,
       s.city,
       s.state,
       s.country_code,
       CAST(s.lat AS DOUBLE) AS lat,
       CAST(s.lon AS DOUBLE) AS lon,
       rd.reading_date,
       YEAR(rd.reading_date)  AS year,
       MONTH(rd.reading_date) AS month,
       rd.parameter,
       CAST(rd.value AS DOUBLE)        AS value,
       rd.n_hours,
       CAST(rd.completeness AS DOUBLE) AS completeness
FROM readings_daily rd
JOIN stations s ON s.id = rd.station_id
WHERE s.country_code = %(country)s
ORDER BY s.city, s.name, rd.parameter, rd.reading_date;
