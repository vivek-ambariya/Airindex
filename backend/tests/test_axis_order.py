"""The axis-order guard.

This is the test the whole spatial design hangs on, and it is written
before anything depends on it -- because the failure it catches is
silent. Swap the two coordinates and MariaDB still returns a number, and
that number is still plausible. Delhi to Mumbai becomes 560 km instead of
1148 km: wrong by a factor of two, with nothing to indicate it.

What is actually being asserted, on this server (MariaDB 10.4.28):

  MariaDB 10.4 has no SRID-aware geometry. Its POINT is plain cartesian
  (x, y), and ST_Distance_Sphere reads x as LONGITUDE. So the correct
  construction is POINT(lon, lat) -- LONGITUDE FIRST.

  This contradicts the usual advice for MySQL 8, where a geometry with
  SRID 4326 follows the EPSG axis definition and is LATITUDE FIRST. Both
  statements are true; they are about different servers. The spec for
  this project asserted latitude-first, which would have been a bug here.
  If this project is ever moved to MySQL 8+, this test is the thing that
  will fail, and schema.sql's two triggers are the only code to change.

Reference distances are great-circle on a sphere of radius 6371 km,
which is what ST_Distance_Sphere uses. Tolerance is 1% as specified.
"""
from __future__ import annotations

import math

import pytest

# (name, lat, lon)
DELHI_CP = ("Delhi Connaught Place", 28.6139, 77.2090)
MUMBAI = ("Mumbai", 19.0760, 72.8777)
ANAND_VIHAR = ("Anand Vihar, Delhi", 28.6469, 77.3152)
BENGALURU = ("Bengaluru", 12.9716, 77.5946)
KOLKATA = ("Kolkata", 22.5726, 88.3639)

TOLERANCE = 0.01  # 1%


def haversine_km(lat1, lon1, lat2, lon2, radius_km=6371.0):
    """Independent reference implementation.

    Deliberately not using any database function, so the test proves the
    database agrees with an outside source rather than with itself.
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))


PAIRS = [
    (DELHI_CP, MUMBAI),
    (DELHI_CP, ANAND_VIHAR),
    (DELHI_CP, BENGALURU),
    (MUMBAI, KOLKATA),
    (BENGALURU, KOLKATA),
]


def _db_km(conn, a, b, order):
    """Distance from the database, constructing points in `order`."""
    (_, lat1, lon1), (_, lat2, lon2) = a, b
    if order == "lon_first":
        p1, p2 = (lon1, lat1), (lon2, lat2)
    else:
        p1, p2 = (lat1, lon1), (lat2, lon2)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ST_Distance_Sphere(POINT(%s, %s), POINT(%s, %s)) / 1000 AS km",
            (p1[0], p1[1], p2[0], p2[1]),
        )
        return float(cur.fetchone()["km"])


@pytest.mark.parametrize("a,b", PAIRS, ids=lambda p: p[0] if isinstance(p, tuple) else str(p))
def test_lon_first_matches_haversine_within_1pct(db_conn, a, b):
    """POINT(lon, lat) is the correct construction on this server."""
    expected = haversine_km(a[1], a[2], b[1], b[2])
    actual = _db_km(db_conn, a, b, "lon_first")
    error = abs(actual - expected) / expected
    assert error <= TOLERANCE, (
        f"{a[0]} -> {b[0]}: database says {actual:.3f} km, "
        f"haversine says {expected:.3f} km ({error:.2%} off, limit {TOLERANCE:.0%})"
    )


def test_lat_first_is_wrong_on_this_server(db_conn):
    """The mistake this suite exists to catch actually is a mistake here.

    Without this, a future change to lat-first could make the test above
    pass for a symmetric pair and nobody would notice. Delhi and Mumbai
    are far apart in both axes, so swapping them is unambiguous.
    """
    expected = haversine_km(DELHI_CP[1], DELHI_CP[2], MUMBAI[1], MUMBAI[2])
    swapped = _db_km(db_conn, DELHI_CP, MUMBAI, "lat_first")
    assert abs(swapped - expected) / expected > 0.10, (
        "Latitude-first gave the right answer, which means this server IS "
        "SRID-aware (MySQL 8+?). schema.sql's triggers must be inverted to "
        "POINT(lat, lon) and this test updated."
    )


def test_schema_trigger_stores_lon_first(db_conn):
    """The trigger in schema.sql -- the one place axis order is decided --
    produces the ordering the queries assume.

    Uses a temporary table with the same trigger body rather than
    touching the real stations table.
    """
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS _axis_probe")
        cur.execute("""
            CREATE TABLE _axis_probe (
                lat DECIMAL(9,6) NOT NULL,
                lon DECIMAL(9,6) NOT NULL,
                geom POINT NOT NULL,
                SPATIAL INDEX (geom)
            ) ENGINE=InnoDB
        """)
        cur.execute("DROP TRIGGER IF EXISTS _axis_probe_bi")
        # Same body as stations_geom_bi in schema.sql.
        cur.execute("""
            CREATE TRIGGER _axis_probe_bi BEFORE INSERT ON _axis_probe
            FOR EACH ROW SET NEW.geom = POINT(NEW.lon, NEW.lat)
        """)
        cur.execute("INSERT INTO _axis_probe (lat, lon) VALUES (%s, %s)",
                    (ANAND_VIHAR[1], ANAND_VIHAR[2]))

        # X must be longitude.
        cur.execute("SELECT ST_X(geom) AS x, ST_Y(geom) AS y FROM _axis_probe")
        row = cur.fetchone()
        assert abs(float(row["x"]) - ANAND_VIHAR[2]) < 1e-5, "ST_X is not longitude"
        assert abs(float(row["y"]) - ANAND_VIHAR[1]) < 1e-5, "ST_Y is not latitude"

        # And a distance through the stored geometry must be right.
        cur.execute(
            "SELECT ST_Distance_Sphere(geom, POINT(%s, %s)) / 1000 AS km FROM _axis_probe",
            (DELHI_CP[2], DELHI_CP[1]),
        )
        actual = float(cur.fetchone()["km"])
        expected = haversine_km(ANAND_VIHAR[1], ANAND_VIHAR[2], DELHI_CP[1], DELHI_CP[2])
        assert abs(actual - expected) / expected <= TOLERANCE, (
            f"through stored geom: {actual:.3f} km vs {expected:.3f} km expected"
        )

        cur.execute("DROP TABLE IF EXISTS _axis_probe")
    db_conn.commit()
