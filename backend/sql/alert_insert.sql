-- INSERT IGNORE, so a concurrent run cannot produce a second email for
-- the same subscription and date. rowcount 0 means somebody beat us to
-- it and no mail should go out.
INSERT IGNORE INTO alerts_sent (subscription_id, reading_date, value, sent_at)
VALUES (%(subscription_id)s, %(reading_date)s, %(value)s, %(sent_at)s);
