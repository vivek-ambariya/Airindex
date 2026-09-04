-- Idempotent: the WHERE clause means a second click on the same link
-- affects zero rows instead of moving verified_at forward.
UPDATE subscriptions
SET verified_at = %(verified_at)s
WHERE verify_token = %(token)s
  AND verified_at IS NULL;
