-- All stations with their most recent daily value and a 30-day
-- completeness figure. Powers GET /api/stations and publish.py.
--
-- completeness_30d is SUM(n_hours) / (30 * 24), NOT the average of the
-- daily completeness column. The difference matters: a station that
-- reported three perfect days and then went silent would score ~100% by
-- the averaging definition and ~10% by this one. The second is the truth
-- a reader needs, and it is what makes the "silent station" case visible
-- instead of flattering.
--
-- The window is anchored to the newest reading_date in the dataset, not
-- to CURDATE(), so a static snapshot reads the same tomorrow.
SELECT
    s.id,
    s.openaq_id,
    s.name,
    s.city,
    s.state,
    s.country_code,
    CAST(s.lat AS DOUBLE)          AS lat,
    CAST(s.lon AS DOUBLE)          AS lon,
    s.first_seen,
    s.last_seen,
    CAST(latest.value AS DOUBLE)   AS latest_value,
    latest.reading_date            AS latest_date,
    CAST(latest.completeness AS DOUBLE) AS latest_completeness,
    CAST(COALESCE(win.completeness_30d, 0) AS DOUBLE) AS completeness_30d,
    CAST(COALESCE(win.days_reported, 0) AS UNSIGNED)  AS days_reported_30d
FROM stations s
LEFT JOIN (
    SELECT rd.station_id, rd.value, rd.reading_date, rd.completeness
    FROM readings_daily rd
    JOIN (
        SELECT station_id, MAX(reading_date) AS max_date
        FROM readings_daily
        WHERE parameter = %(parameter)s
        GROUP BY station_id
    ) mx ON mx.station_id = rd.station_id AND mx.max_date = rd.reading_date
    WHERE rd.parameter = %(parameter)s
) latest ON latest.station_id = s.id
LEFT JOIN (
    SELECT
        station_id,
        ROUND(SUM(n_hours) / (30 * 24) * 100, 2) AS completeness_30d,
        COUNT(*)                                 AS days_reported
    FROM readings_daily
    WHERE parameter = %(parameter)s
      AND reading_date > DATE_SUB(
            (SELECT MAX(reading_date) FROM readings_daily WHERE parameter = %(parameter)s),
            INTERVAL 30 DAY)
    GROUP BY station_id
) win ON win.station_id = s.id
WHERE s.country_code = %(country)s
ORDER BY s.city IS NULL, s.city, s.name;
