-- Every station's daily values for one parameter over a window, in one
-- pass. publish.py pivots this into per-station parallel arrays.
--
-- One query rather than one per station: 65 round trips to build a
-- static file is 65 chances for the snapshot to be internally
-- inconsistent if a load runs halfway through.
SELECT station_id,
       reading_date,
       CAST(value AS DOUBLE)        AS value,
       CAST(completeness AS DOUBLE) AS completeness
FROM readings_daily
WHERE parameter = %(parameter)s
  AND reading_date BETWEEN %(date_from)s AND %(date_to)s
ORDER BY station_id, reading_date;
