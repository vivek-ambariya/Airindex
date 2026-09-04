-- alerts_sent has a FK to subscriptions, so its rows go first.
-- "Deleted on unsubscribe" means the whole trail, not just the row that
-- holds the address.
DELETE FROM alerts_sent WHERE subscription_id = %(subscription_id)s;
