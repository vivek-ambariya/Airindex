"""Threshold alert subscriptions, with double opt-in.

Nothing here sends mail directly -- it all goes through
app.emailer.send_email, which currently writes to logs/emails.log.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from .. import db, validation as v
from ..bands import SUPPORTED_PARAMETERS, UNITS
from ..emailer import public_url, send_email

bp = Blueprint("subscriptions", __name__, url_prefix="/api/subscriptions")

# A threshold has to be a plausible concentration. Zero would fire every
# day and be useless; the ceiling is above any reading ever recorded.
MIN_THRESHOLD = 1.0
MAX_THRESHOLD = 2000.0


def _utcnow() -> datetime:
    # Naive UTC: the columns are DATETIME, not TIMESTAMP, so the value
    # stored is exactly what is written with no session-timezone
    # conversion applied on the way in or out.
    return datetime.now(timezone.utc).replace(tzinfo=None)


@bp.post("")
@bp.post("/")
def create_subscription():
    """Create an UNVERIFIED subscription and send a verification link.

    Returns 202, not 201: nothing is active yet. check_alerts.py will
    not look at this row until verified_at is set.
    """
    payload = request.get_json(silent=True) or {}

    email = v.require_email(payload.get("email"))
    station_id = v.require_int(payload.get("station_id"), "station_id", lo=1)
    parameter = v.parameter(payload, default="pm25")
    threshold = v.require_float(payload.get("threshold"), "threshold",
                                MIN_THRESHOLD, MAX_THRESHOLD)

    station = db.query_one("station_by_id.sql", {"station_id": station_id})
    if station is None:
        return jsonify({"error": "not_found",
                        "message": f"No station with id {station_id}."}), 404

    existing = db.query_one("subscription_find.sql", {
        "email": email, "station_id": station_id, "parameter": parameter,
    })
    if existing is not None:
        # Deliberately does NOT send a second email and does NOT reset
        # the token. Re-posting the same form is not a reason to mail
        # somebody again.
        return jsonify({
            "status": "already_exists",
            "verified": existing["verified_at"] is not None,
            "message": (
                "You already have this alert. "
                + ("It is active." if existing["verified_at"]
                   else "It is still waiting for the confirmation link in your inbox.")
            ),
        }), 200

    verify_token = str(uuid.uuid4())
    unsubscribe_token = str(uuid.uuid4())
    db.execute("subscription_insert.sql", {
        "email": email,
        "station_id": station_id,
        "parameter": parameter,
        "threshold": threshold,
        "verify_token": verify_token,
        "unsubscribe_token": unsubscribe_token,
        "created_at": _utcnow(),
    })
    db.get_db().commit()

    where = station["name"] + (f", {station['city']}" if station.get("city") else "")
    send_email(
        to=email,
        subject=f"Confirm your {parameter.upper()} alert for {where}",
        body=(
            f"You asked to be told when {parameter.upper()} at {where} reaches "
            f"{threshold:g} {UNITS[parameter]} as a daily average.\n\n"
            f"This alert is NOT active yet. Confirm it here:\n"
            f"  {public_url('/alerts/verify?token=' + verify_token)}\n\n"
            f"If you did not ask for this, ignore this message -- nothing was\n"
            f"activated and no further mail will be sent.\n\n"
            f"To remove it later:\n"
            f"  {public_url('/alerts/unsubscribe?token=' + unsubscribe_token)}\n"
        ),
    )

    return jsonify({
        "status": "pending_verification",
        "message": ("Check your inbox to switch it on. Nothing is sent until "
                    "you confirm."),
        "station": {"id": station_id, "name": station["name"], "city": station.get("city")},
        "parameter": parameter,
        "threshold": threshold,
        "unit": UNITS[parameter],
    }), 202


@bp.get("/verify")
def verify_subscription():
    token = (request.args.get("token") or "").strip()
    if not token:
        raise v.ValidationError("token is required", "token")

    row = db.query_one("subscription_by_verify_token.sql", {"token": token})
    if row is None:
        return jsonify({
            "error": "not_found",
            "message": ("That confirmation link is not valid. It may already have "
                        "been used to unsubscribe."),
        }), 404

    if row["verified_at"] is not None:
        return jsonify({
            "status": "already_verified",
            "message": "This alert was already switched on.",
            "station": {"id": row["station_id"], "name": row["station_name"],
                        "city": row.get("city")},
            "parameter": row["parameter"],
            "threshold": row["threshold"],
        }), 200

    db.execute("subscription_verify.sql", {"token": token, "verified_at": _utcnow()})
    db.get_db().commit()

    return jsonify({
        "status": "verified",
        "message": ("Alert is on. You will get at most one message per day, and "
                    "nothing at all on days the station does not report."),
        "station": {"id": row["station_id"], "name": row["station_name"],
                    "city": row.get("city")},
        "parameter": row["parameter"],
        "threshold": row["threshold"],
        "unsubscribe_token": row["unsubscribe_token"],
    }), 200


@bp.delete("/<unsubscribe_token>")
def delete_subscription(unsubscribe_token: str):
    """Remove a subscription and its whole alert history."""
    token = (unsubscribe_token or "").strip()
    row = db.query_one("subscription_by_unsub_token.sql", {"token": token})
    if row is None:
        # Idempotent by design: a second click on the unsubscribe link
        # should read as "you are unsubscribed", not as an error.
        return jsonify({
            "status": "not_found",
            "message": "Nothing to remove -- that link has already been used.",
        }), 404

    db.execute("subscription_delete_alerts.sql", {"subscription_id": row["id"]})
    db.execute("subscription_delete.sql", {"token": token})
    db.get_db().commit()

    return jsonify({
        "status": "deleted",
        "message": "Alert removed, along with the record of what was sent.",
    }), 200
