-- Cheap liveness probe that also proves the spatial path works, because
-- a broken geometry function is the failure most likely to go unnoticed
-- until somebody clicks the map. 1148 km is Delhi -> Mumbai.
SELECT
    (SELECT COUNT(*) FROM stations)       AS n_stations,
    (SELECT COUNT(*) FROM readings_daily) AS n_readings,
    (SELECT MAX(reading_date) FROM readings_daily) AS latest_date,
    ROUND(ST_Distance_Sphere(POINT(77.2090, 28.6139),
                             POINT(72.8777, 19.0760)) / 1000) AS delhi_mumbai_km,
    VERSION() AS db_version;
