-- Idempotent station load, keyed on the OpenAQ id.
--
-- Re-running load.py must not duplicate stations or renumber them: the
-- readings_daily foreign key and any existing subscriptions both point
-- at stations.id, so that surrogate key has to survive a reload.
--
-- The BEFORE UPDATE trigger recomputes geom whenever lat/lon change, so
-- a station that OpenAQ has repositioned moves on the map without any
-- geometry handling here.
INSERT INTO stations
    (openaq_id, name, city, state, country_code, lat, lon, first_seen, last_seen)
VALUES
    (%(openaq_id)s, %(name)s, %(city)s, %(state)s, %(country_code)s,
     %(lat)s, %(lon)s, %(first_seen)s, %(last_seen)s)
ON DUPLICATE KEY UPDATE
    name         = VALUES(name),
    city         = VALUES(city),
    state        = VALUES(state),
    country_code = VALUES(country_code),
    lat          = VALUES(lat),
    lon          = VALUES(lon),
    -- first_seen only ever moves earlier, last_seen only later, so a
    -- partial reload of one month cannot shrink a station's known span.
    first_seen   = LEAST(COALESCE(first_seen, VALUES(first_seen)), VALUES(first_seen)),
    last_seen    = GREATEST(COALESCE(last_seen, VALUES(last_seen)), VALUES(last_seen));
