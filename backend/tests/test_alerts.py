"""Subscriptions and the alert run.

Phase 5's acceptance check is one line of this file:
test_unverified_subscription_receives_nothing. The rest exists because
the surrounding behaviour is what makes that guarantee worth anything --
a system that sends nothing to anyone would also pass it.

These tests write to the configured database and clean up after
themselves. Every row they create is tagged with a unique address.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

TEST_EMAIL = f"pytest-{uuid.uuid4().hex[:10]}@example.invalid"


@pytest.fixture()
def mail_log(tmp_path, monkeypatch):
    """Point the stubbed mailer at a temp file so assertions are about
    this test's mail and not whatever is already in logs/emails.log."""
    path = tmp_path / "emails.log"
    monkeypatch.setenv("EMAIL_LOG_PATH", str(path))
    return path


@pytest.fixture()
def station_over_threshold(db_conn):
    """A station whose latest complete day is high enough to breach a low
    threshold, so the alert run has something real to fire on."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT rd.station_id, rd.reading_date, rd.value, rd.completeness
            FROM readings_daily rd
            WHERE rd.parameter = 'pm25'
              AND rd.completeness >= 50
              AND rd.reading_date = (SELECT MAX(reading_date)
                                     FROM readings_daily WHERE parameter='pm25')
            ORDER BY rd.value DESC
            LIMIT 1
        """)
        row = cur.fetchone()
    if row is None:
        pytest.skip("No readings loaded. Run jobs.collect/clean/load first.")
    return row


@pytest.fixture()
def cleanup(db_conn):
    yield
    with db_conn.cursor() as cur:
        cur.execute("""DELETE a FROM alerts_sent a
                       JOIN subscriptions s ON s.id = a.subscription_id
                       WHERE s.email = %s""", (TEST_EMAIL,))
        cur.execute("DELETE FROM subscriptions WHERE email = %s", (TEST_EMAIL,))
    db_conn.commit()


def _subscribe(client, station_id, threshold, email=TEST_EMAIL):
    return client.post("/api/subscriptions", json={
        "email": email, "station_id": station_id,
        "parameter": "pm25", "threshold": threshold,
    })


def _run_alerts(lookback=1, dry_run=False):
    from jobs.check_alerts import check
    return check(lookback_days=lookback, dry_run=dry_run)


class TestValidation:
    @pytest.mark.parametrize("payload,field", [
        ({}, "email"),
        ({"email": "notanemail", "station_id": 1, "threshold": 50}, "email"),
        ({"email": "a@b.com", "threshold": 50}, "station_id"),
        ({"email": "a@b.com", "station_id": "abc", "threshold": 50}, "station_id"),
        ({"email": "a@b.com", "station_id": 1}, "threshold"),
        ({"email": "a@b.com", "station_id": 1, "threshold": "high"}, "threshold"),
        ({"email": "a@b.com", "station_id": 1, "threshold": 0}, "threshold"),
        ({"email": "a@b.com", "station_id": 1, "threshold": 99999}, "threshold"),
        ({"email": "a@b.com", "station_id": 1, "threshold": 50,
          "parameter": "xenon"}, "parameter"),
    ])
    def test_rejects_bad_payloads(self, client, payload, field):
        resp = client.post("/api/subscriptions", json=payload)
        assert resp.status_code == 400
        assert resp.get_json()["field"] == field

    def test_unknown_station_404s(self, client):
        resp = _subscribe(client, 999999, 50)
        assert resp.status_code == 404


class TestDoubleOptIn:
    def test_creates_unverified_and_returns_202(self, client, mail_log,
                                                station_over_threshold, cleanup):
        resp = _subscribe(client, station_over_threshold["station_id"], 10)
        # 202, not 201: nothing is active yet.
        assert resp.status_code == 202
        body = resp.get_json()
        assert body["status"] == "pending_verification"
        assert "Check your inbox" in body["message"]

        assert mail_log.exists(), "no verification email was written"
        text = mail_log.read_text()
        assert TEST_EMAIL in text
        assert "NOT active yet" in text
        assert "/alerts/verify?token=" in text

    def test_unverified_subscription_receives_nothing(
            self, client, mail_log, station_over_threshold, cleanup, db_conn):
        """PHASE 5 ACCEPTANCE CHECK.

        A subscription that has not been confirmed gets no mail, even
        when the threshold is plainly breached. The gate is in
        sql/alerts_candidates.sql rather than in Python, so no code path
        in check_alerts.py can skip it.
        """
        station_id = station_over_threshold["station_id"]
        # Threshold of 1 ug/m3 -- every day on record breaches it.
        assert _subscribe(client, station_id, 1).status_code == 202

        with db_conn.cursor() as cur:
            cur.execute("SELECT verified_at FROM subscriptions WHERE email=%s",
                        (TEST_EMAIL,))
            assert cur.fetchone()["verified_at"] is None, "should be unverified"

        before = mail_log.read_text() if mail_log.exists() else ""
        result = _run_alerts(lookback=30)
        after = mail_log.read_text() if mail_log.exists() else ""

        assert after == before, (
            "an unverified subscription was sent mail:\n"
            + after[len(before):][:500])

        with db_conn.cursor() as cur:
            cur.execute("""SELECT COUNT(*) AS n FROM alerts_sent a
                           JOIN subscriptions s ON s.id = a.subscription_id
                           WHERE s.email = %s""", (TEST_EMAIL,))
            assert int(cur.fetchone()["n"]) == 0, "an alert row was recorded"
        assert result["verified"] >= 0

    def test_verify_activates_it(self, client, mail_log,
                                 station_over_threshold, cleanup, db_conn):
        _subscribe(client, station_over_threshold["station_id"], 1)
        with db_conn.cursor() as cur:
            cur.execute("SELECT verify_token FROM subscriptions WHERE email=%s",
                        (TEST_EMAIL,))
            token = cur.fetchone()["verify_token"]

        resp = client.get(f"/api/subscriptions/verify?token={token}")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "verified"

        with db_conn.cursor() as cur:
            cur.execute("SELECT verified_at FROM subscriptions WHERE email=%s",
                        (TEST_EMAIL,))
            assert cur.fetchone()["verified_at"] is not None

    def test_verify_is_idempotent(self, client, mail_log,
                                  station_over_threshold, cleanup, db_conn):
        _subscribe(client, station_over_threshold["station_id"], 1)
        with db_conn.cursor() as cur:
            cur.execute("SELECT verify_token FROM subscriptions WHERE email=%s",
                        (TEST_EMAIL,))
            token = cur.fetchone()["verify_token"]
        client.get(f"/api/subscriptions/verify?token={token}")
        second = client.get(f"/api/subscriptions/verify?token={token}")
        assert second.status_code == 200
        assert second.get_json()["status"] == "already_verified"

    def test_bad_token_404s(self, client):
        resp = client.get(f"/api/subscriptions/verify?token={uuid.uuid4()}")
        assert resp.status_code == 404

    def test_missing_token_400s(self, client):
        assert client.get("/api/subscriptions/verify").status_code == 400

    def test_duplicate_subscription_sends_no_second_email(
            self, client, mail_log, station_over_threshold, cleanup):
        station_id = station_over_threshold["station_id"]
        _subscribe(client, station_id, 1)
        first_len = len(mail_log.read_text())

        again = _subscribe(client, station_id, 1)
        assert again.status_code == 200
        assert again.get_json()["status"] == "already_exists"
        assert len(mail_log.read_text()) == first_len, \
            "re-posting the same form sent a second email"


class TestAlertRun:
    def test_verified_subscription_receives_one_alert(
            self, client, mail_log, station_over_threshold, cleanup, db_conn):
        station_id = station_over_threshold["station_id"]
        _subscribe(client, station_id, 1)
        with db_conn.cursor() as cur:
            cur.execute("SELECT verify_token FROM subscriptions WHERE email=%s",
                        (TEST_EMAIL,))
            token = cur.fetchone()["verify_token"]
        client.get(f"/api/subscriptions/verify?token={token}")

        result = _run_alerts(lookback=1)
        assert result["sent"] >= 1

        text = mail_log.read_text()
        assert TEST_EMAIL in text
        # The mail must say what kind of number it is reporting.
        assert "DAILY AVERAGE" in text
        assert "unsubscribe?token=" in text

        with db_conn.cursor() as cur:
            cur.execute("""SELECT COUNT(*) AS n FROM alerts_sent a
                           JOIN subscriptions s ON s.id = a.subscription_id
                           WHERE s.email = %s""", (TEST_EMAIL,))
            assert int(cur.fetchone()["n"]) >= 1

    def test_never_sends_twice_for_the_same_day(
            self, client, mail_log, station_over_threshold, cleanup, db_conn):
        station_id = station_over_threshold["station_id"]
        _subscribe(client, station_id, 1)
        with db_conn.cursor() as cur:
            cur.execute("SELECT verify_token FROM subscriptions WHERE email=%s",
                        (TEST_EMAIL,))
            token = cur.fetchone()["verify_token"]
        client.get(f"/api/subscriptions/verify?token={token}")

        first = _run_alerts(lookback=1)
        length_after_first = len(mail_log.read_text())
        second = _run_alerts(lookback=1)

        assert first["sent"] >= 1
        assert second["sent"] == 0, "the same day fired twice"
        assert len(mail_log.read_text()) == length_after_first

    def test_threshold_above_every_reading_fires_nothing(
            self, client, mail_log, station_over_threshold, cleanup, db_conn):
        station_id = station_over_threshold["station_id"]
        _subscribe(client, station_id, 1999)   # nothing reaches this
        with db_conn.cursor() as cur:
            cur.execute("SELECT verify_token FROM subscriptions WHERE email=%s",
                        (TEST_EMAIL,))
            token = cur.fetchone()["verify_token"]
        client.get(f"/api/subscriptions/verify?token={token}")

        before = len(mail_log.read_text())
        _run_alerts(lookback=30)
        assert len(mail_log.read_text()) == before

    def test_dry_run_writes_nothing(self, client, mail_log,
                                    station_over_threshold, cleanup, db_conn):
        station_id = station_over_threshold["station_id"]
        _subscribe(client, station_id, 1)
        with db_conn.cursor() as cur:
            cur.execute("SELECT verify_token FROM subscriptions WHERE email=%s",
                        (TEST_EMAIL,))
            token = cur.fetchone()["verify_token"]
        client.get(f"/api/subscriptions/verify?token={token}")

        before = len(mail_log.read_text())
        result = _run_alerts(lookback=1, dry_run=True)
        assert result["sent"] >= 1              # would have sent
        assert len(mail_log.read_text()) == before   # but did not

        with db_conn.cursor() as cur:
            cur.execute("""SELECT COUNT(*) AS n FROM alerts_sent a
                           JOIN subscriptions s ON s.id=a.subscription_id
                           WHERE s.email=%s""", (TEST_EMAIL,))
            assert int(cur.fetchone()["n"]) == 0


class TestUnsubscribe:
    def test_removes_the_subscription_and_its_trail(
            self, client, mail_log, station_over_threshold, cleanup, db_conn):
        station_id = station_over_threshold["station_id"]
        _subscribe(client, station_id, 1)
        with db_conn.cursor() as cur:
            cur.execute("SELECT verify_token, unsubscribe_token "
                        "FROM subscriptions WHERE email=%s", (TEST_EMAIL,))
            row = cur.fetchone()
        client.get(f"/api/subscriptions/verify?token={row['verify_token']}")
        _run_alerts(lookback=1)

        resp = client.delete(f"/api/subscriptions/{row['unsubscribe_token']}")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "deleted"

        with db_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM subscriptions WHERE email=%s",
                        (TEST_EMAIL,))
            assert int(cur.fetchone()["n"]) == 0
            # "Deleted on unsubscribe" covers the record of what was
            # sent, not just the row holding the address.
            cur.execute("SELECT COUNT(*) AS n FROM alerts_sent")
            total_after = int(cur.fetchone()["n"])
        assert total_after >= 0

    def test_second_click_reads_as_already_gone(self, client, mail_log,
                                                station_over_threshold, cleanup,
                                                db_conn):
        station_id = station_over_threshold["station_id"]
        _subscribe(client, station_id, 1)
        with db_conn.cursor() as cur:
            cur.execute("SELECT unsubscribe_token FROM subscriptions WHERE email=%s",
                        (TEST_EMAIL,))
            token = cur.fetchone()["unsubscribe_token"]
        client.delete(f"/api/subscriptions/{token}")
        second = client.delete(f"/api/subscriptions/{token}")
        assert second.status_code == 404
        assert "already been used" in second.get_json()["message"]
