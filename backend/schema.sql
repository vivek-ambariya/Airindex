-- =====================================================================
-- India Air Quality Explorer — schema
--
-- TARGET: MariaDB 10.4 (the version XAMPP ships). Verified against
--         10.4.28. See docs/methodology.md § "Spatial on MariaDB 10.4"
--         for why this differs from the MySQL 8 form.
--
-- All datetimes are UTC, and DATETIME rather than TIMESTAMP so the
-- server's session time zone can never silently shift a stored value.
--
-- AXIS ORDER lives in exactly ONE place: the two triggers at the bottom
-- of this file. Nothing else in the codebase constructs a POINT.
-- MariaDB 10.4 has no SRID-aware geometry, so its POINT is plain
-- cartesian (x, y) = (longitude, latitude). Proven by
-- backend/tests/test_axis_order.py, which fails loudly if this changes.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS aqi_india
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE aqi_india;

-- ---------------------------------------------------------------------
-- stations
--
-- lat/lon are the source of truth. geom is derived from them by trigger
-- and exists only so the spatial index can serve nearest-station.
--
-- Deviation from the MySQL 8 spec, and why:
--   spec:  geom POINT SRID 4326 GENERATED ALWAYS AS (...) STORED
--   here:  geom POINT NOT NULL, maintained by trigger
-- MariaDB 10.4 rejects the SRID column attribute outright, and it will
-- not accept NOT NULL on a generated column -- while SPATIAL INDEX
-- requires every part to be NOT NULL. A generated geom column and a
-- spatial index are therefore mutually exclusive on this server. The
-- trigger keeps the "one place for axis order" property that the
-- generated column was there to provide.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stations (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  openaq_id     BIGINT NOT NULL UNIQUE,
  name          VARCHAR(255) NOT NULL,
  city          VARCHAR(128),
  state         VARCHAR(128),
  country_code  CHAR(2) NOT NULL DEFAULT 'IN',
  lat           DECIMAL(9,6) NOT NULL,
  lon           DECIMAL(9,6) NOT NULL,
  geom          POINT NOT NULL,
  first_seen    DATE,
  last_seen     DATE,
  SPATIAL INDEX sx_geom (geom),
  -- Serves the bounding-box prefilter in nearest.sql. The spatial index
  -- cannot be used for an ST_Distance_Sphere ORDER BY, so the cheap
  -- B-tree range scan on lat/lon is what actually bounds the work.
  INDEX ix_lat_lon (lat, lon),
  INDEX ix_city (city),
  INDEX ix_country (country_code)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- readings_daily — one row per station, per day, per parameter
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS readings_daily (
  station_id    INT NOT NULL,
  reading_date  DATE NOT NULL,
  parameter     VARCHAR(16) NOT NULL,
  value         DECIMAL(10,3) NOT NULL,
  n_hours       SMALLINT NOT NULL,      -- hours contributing to this average
  completeness  DECIMAL(5,2) NOT NULL,  -- n_hours / 24 * 100
  PRIMARY KEY (station_id, reading_date, parameter),
  FOREIGN KEY (station_id) REFERENCES stations(id),
  INDEX ix_param_date (parameter, reading_date)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- subscriptions — double opt-in. verified_at NULL means "send nothing".
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subscriptions (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  email             VARCHAR(255) NOT NULL,
  station_id        INT NOT NULL,
  parameter         VARCHAR(16) NOT NULL DEFAULT 'pm25',
  threshold         DECIMAL(10,3) NOT NULL,
  verify_token      CHAR(36) NOT NULL UNIQUE,
  unsubscribe_token CHAR(36) NOT NULL UNIQUE,
  verified_at       DATETIME NULL,
  created_at        DATETIME NOT NULL,
  FOREIGN KEY (station_id) REFERENCES stations(id),
  UNIQUE KEY uniq_sub (email, station_id, parameter)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- alerts_sent — the PK is what makes "never twice in a day" structural
-- rather than a thing check_alerts.py has to remember.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts_sent (
  subscription_id INT NOT NULL,
  reading_date    DATE NOT NULL,
  value           DECIMAL(10,3) NOT NULL,
  sent_at         DATETIME NOT NULL,
  PRIMARY KEY (subscription_id, reading_date),
  FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
) ENGINE=InnoDB;

-- =====================================================================
-- THE ONE PLACE AXIS ORDER IS DECIDED
--
-- MariaDB 10.4's POINT is cartesian: POINT(x, y) with x = longitude.
-- ST_Distance_Sphere then reads x as longitude and y as latitude.
-- Getting this backwards puts Delhi at 560 km from Mumbai instead of
-- 1148 km, silently. test_axis_order.py is the guard.
--
-- If this project is ever moved to MySQL 8+, geometries become
-- SRID-aware and SRID 4326 declares a LATITUDE-FIRST axis order, so
-- these two triggers -- and only these two -- invert to POINT(lat, lon).
-- =====================================================================
DROP TRIGGER IF EXISTS stations_geom_bi;
CREATE TRIGGER stations_geom_bi BEFORE INSERT ON stations
FOR EACH ROW SET NEW.geom = POINT(NEW.lon, NEW.lat);

DROP TRIGGER IF EXISTS stations_geom_bu;
CREATE TRIGGER stations_geom_bu BEFORE UPDATE ON stations
FOR EACH ROW SET NEW.geom = POINT(NEW.lon, NEW.lat);
