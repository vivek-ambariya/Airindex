-- Nearest station to an arbitrary point.
--
-- Two-step by design. The bounding box on lat/lon runs first against the
-- ix_lat_lon B-tree and throws away almost every row cheaply;
-- ST_Distance_Sphere then produces an exact great-circle distance over
-- the handful that survive. Distance functions are not sargable, so
-- ordering by km alone would scan the whole table -- the box is what
-- makes this an index lookup rather than a full scan.
--
-- The box half-widths are computed by the caller from max_km rather than
-- hardcoded at 0.5 degrees: a degree of longitude is ~111 km at the
-- equator but ~96 km at Srinagar, so a fixed 0.5 would quietly clip
-- candidates in the north and over-scan in the south. See
-- routes/stations.py:_bounding_box.
--
-- AXIS ORDER: POINT(lon, lat) -- x is longitude on MariaDB 10.4. This
-- matches the trigger in schema.sql. See tests/test_axis_order.py.
SELECT
    id,
    openaq_id,
    name,
    city,
    state,
    CAST(lat AS DOUBLE) AS lat,
    CAST(lon AS DOUBLE) AS lon,
    ROUND(ST_Distance_Sphere(geom, POINT(%(lon)s, %(lat)s)) / 1000, 3) AS distance_km
FROM stations
WHERE country_code = %(country)s
  AND lat BETWEEN %(lat)s - %(lat_delta)s AND %(lat)s + %(lat_delta)s
  AND lon BETWEEN %(lon)s - %(lon_delta)s AND %(lon)s + %(lon_delta)s
HAVING distance_km <= %(max_km)s
ORDER BY distance_km
LIMIT 1;
