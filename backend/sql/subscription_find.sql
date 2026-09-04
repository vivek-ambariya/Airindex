-- Does this exact subscription already exist? Drives the "you already
-- have this alert, no second email" path rather than letting the UNIQUE
-- constraint surface as a 500.
SELECT id, email, station_id, parameter,
       CAST(threshold AS DOUBLE) AS threshold,
       verified_at, created_at
FROM subscriptions
WHERE email = %(email)s
  AND station_id = %(station_id)s
  AND parameter = %(parameter)s;
