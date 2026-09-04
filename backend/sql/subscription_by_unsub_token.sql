SELECT id, email, station_id, parameter
FROM subscriptions
WHERE unsubscribe_token = %(token)s;
