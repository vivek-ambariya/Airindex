-- The newest day in the dataset for a parameter. Used to anchor default
-- date windows to the data rather than to today's date, so a snapshot
-- collected weeks ago still opens on readings instead of on a gap.
SELECT MAX(reading_date) AS latest_date
FROM readings_daily
WHERE parameter = %(parameter)s;
