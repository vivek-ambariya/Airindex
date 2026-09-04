SELECT sub.id, sub.email, sub.station_id, sub.parameter,
       CAST(sub.threshold AS DOUBLE) AS threshold,
       sub.verified_at, sub.unsubscribe_token,
       s.name AS station_name, s.city
FROM subscriptions sub
JOIN stations s ON s.id = sub.station_id
WHERE sub.verify_token = %(token)s;
