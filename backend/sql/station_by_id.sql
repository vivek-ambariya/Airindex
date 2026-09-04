SELECT id, openaq_id, name, city, state, country_code,
       CAST(lat AS DOUBLE) AS lat, CAST(lon AS DOUBLE) AS lon,
       first_seen, last_seen
FROM stations
WHERE id = %(station_id)s;
