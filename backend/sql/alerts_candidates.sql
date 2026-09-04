-- Days that should trigger an alert but have not yet.
--
-- Three gates, each corresponding to a promise made in the UI:
--
--  1. sub.verified_at IS NOT NULL -- an unverified subscription receives
--     nothing, ever. This is the double opt-in, enforced in the query
--     rather than in Python, so no caller can forget it.
--  2. rd.completeness >= min -- "silence when data stops". A day built
--     from three hours is not evidence of a threshold breach, and a
--     sparse day that happens to average high must not fire.
--  3. a.subscription_id IS NULL -- nothing sent for this subscription on
--     this date. The PRIMARY KEY on alerts_sent makes the guarantee
--     structural; this clause is what stops us from trying.
SELECT sub.id                          AS subscription_id,
       sub.email,
       sub.parameter,
       CAST(sub.threshold AS DOUBLE)   AS threshold,
       sub.unsubscribe_token,
       s.id                            AS station_id,
       s.name                          AS station_name,
       s.city,
       rd.reading_date,
       CAST(rd.value AS DOUBLE)        AS value,
       CAST(rd.completeness AS DOUBLE) AS completeness
FROM subscriptions sub
JOIN stations s        ON s.id = sub.station_id
JOIN readings_daily rd ON rd.station_id = sub.station_id
                      AND rd.parameter  = sub.parameter
LEFT JOIN alerts_sent a ON a.subscription_id = sub.id
                       AND a.reading_date    = rd.reading_date
WHERE sub.verified_at IS NOT NULL
  AND rd.reading_date >= %(since_date)s
  AND rd.value >= sub.threshold
  AND rd.completeness >= %(min_completeness)s
  AND a.subscription_id IS NULL
ORDER BY sub.id, rd.reading_date;
