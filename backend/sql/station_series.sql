-- Daily values for one station and parameter over a date range.
--
-- Returned as parallel arrays by the route, so the response carries one
-- copy of the field names rather than one per day. Gaps are preserved as
-- nulls by the route walking the calendar -- this query returns only the
-- days that exist, and deliberately does not invent the missing ones.
SELECT reading_date,
       CAST(value AS DOUBLE)        AS value,
       n_hours,
       CAST(completeness AS DOUBLE) AS completeness
FROM readings_daily
WHERE station_id = %(station_id)s
  AND parameter  = %(parameter)s
  AND reading_date BETWEEN %(date_from)s AND %(date_to)s
ORDER BY reading_date;
