-- Idempotent daily load. The primary key is
-- (station_id, reading_date, parameter), so re-running a month replaces
-- those rows rather than duplicating or erroring.
INSERT INTO readings_daily
    (station_id, reading_date, parameter, value, n_hours, completeness)
VALUES
    (%(station_id)s, %(reading_date)s, %(parameter)s, %(value)s,
     %(n_hours)s, %(completeness)s)
ON DUPLICATE KEY UPDATE
    value        = VALUES(value),
    n_hours      = VALUES(n_hours),
    completeness = VALUES(completeness);
