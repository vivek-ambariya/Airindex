INSERT INTO subscriptions
    (email, station_id, parameter, threshold,
     verify_token, unsubscribe_token, verified_at, created_at)
VALUES
    (%(email)s, %(station_id)s, %(parameter)s, %(threshold)s,
     %(verify_token)s, %(unsubscribe_token)s, NULL, %(created_at)s);
