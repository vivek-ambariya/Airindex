"""Threshold check. Run manually.

    python -m jobs.check_alerts                 # the latest day only
    python -m jobs.check_alerts --lookback 7    # catch up a week
    python -m jobs.check_alerts --dry-run       # report, send nothing

Writes a row to alerts_sent for every alert it sends, and sends nothing
it has already sent for that subscription and date.

THREE GUARANTEES, and where each is enforced:

  1. An unverified subscription receives nothing.
     sql/alerts_candidates.sql, `sub.verified_at IS NOT NULL`. In the
     query, not in Python, so no code path here can bypass it.

  2. Never twice for the same subscription and day.
     alerts_sent has PRIMARY KEY (subscription_id, reading_date), and
     the insert is INSERT IGNORE. The row goes in BEFORE the mail goes
     out, and a rowcount of 0 means somebody already claimed that day
     and we send nothing. Ordering it the other way round would mean a
     crash between send and insert produces a duplicate on the next run.

  3. Silence when the data stops.
     The candidate query requires completeness >= 50%. A day averaged
     from three hours is not evidence of a breach, and a station that
     has gone quiet must never generate mail -- nor a false all-clear.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv

from .paths import BACKEND_DIR

load_dotenv(BACKEND_DIR / ".env", override=False)
sys.path.insert(0, str(BACKEND_DIR))

from app.bands import MIN_COMPLETENESS_FOR_BAND, UNITS, band_with_reason  # noqa: E402
from app.db import connect, load_sql  # noqa: E402
from app.emailer import public_url, send_email  # noqa: E402


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def check(lookback_days: int, dry_run: bool) -> dict:
    conn = connect()
    print("check_alerts.py" + ("  [DRY RUN -- nothing will be sent]" if dry_run else ""))

    with conn.cursor() as cur:
        cur.execute(load_sql("latest_date.sql"), {"parameter": "pm25"})
        row = cur.fetchone()
    anchor: date = (row or {}).get("latest_date") or date.today()
    since = anchor - timedelta(days=lookback_days - 1)
    print(f"  window: {since} .. {anchor}  (lookback {lookback_days}d)")

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n, "
                    "SUM(verified_at IS NOT NULL) AS verified FROM subscriptions")
        counts = cur.fetchone()
    n_subs = int(counts["n"] or 0)
    n_verified = int(counts["verified"] or 0)
    print(f"  subscriptions: {n_subs} total, {n_verified} verified, "
          f"{n_subs - n_verified} awaiting confirmation (these get nothing)")

    with conn.cursor() as cur:
        cur.execute(load_sql("alerts_candidates.sql"), {
            "since_date": since,
            "min_completeness": MIN_COMPLETENESS_FOR_BAND,
        })
        candidates = cur.fetchall()

    print(f"  candidate breaches: {len(candidates)}")
    sent, skipped = 0, 0

    for c in candidates:
        where = c["station_name"] + (f", {c['city']}" if c["city"] else "")
        unit = UNITS.get(c["parameter"], "ug/m3")
        band, _ = band_with_reason(c["parameter"], float(c["value"]),
                                   day_completeness=float(c["completeness"]))

        if dry_run:
            print(f"    WOULD SEND  {c['email']}  {where}  "
                  f"{c['reading_date']}  {c['value']:g} >= {c['threshold']:g} {unit}")
            sent += 1
            continue

        # Claim the day FIRST. If this returns 0 rows another run has it.
        with conn.cursor() as cur:
            cur.execute(load_sql("alert_insert.sql"), {
                "subscription_id": c["subscription_id"],
                "reading_date": c["reading_date"],
                "value": c["value"],
                "sent_at": _utcnow(),
            })
            claimed = cur.rowcount
        conn.commit()

        if not claimed:
            skipped += 1
            print(f"    already sent  sub={c['subscription_id']} "
                  f"{c['reading_date']} -- skipping")
            continue

        send_email(
            to=c["email"],
            subject=(f"{c['parameter'].upper()} {c['value']:g} {unit} at {where} "
                     f"on {c['reading_date']:%d %b %Y}"),
            body=(
                f"{where}\n"
                f"{c['reading_date']:%A %d %B %Y}\n\n"
                f"  {c['parameter'].upper()}   {c['value']:g} {unit}"
                f"   ({band or 'no band'})\n"
                f"  your threshold   {c['threshold']:g} {unit}\n"
                f"  day completeness {c['completeness']:g}%\n\n"
                f"This is a DAILY AVERAGE, not a live reading. It is the mean of\n"
                f"the hours the station reported on that date.\n\n"
                f"One message per station per day at most. On days the station\n"
                f"does not report enough hours you will hear nothing -- silence\n"
                f"means no usable data, not clean air.\n\n"
                f"Stop these:\n"
                f"  {public_url('/alerts/unsubscribe?token=' + c['unsubscribe_token'])}\n"
            ),
        )
        sent += 1

    print(f"\n  sent: {sent}   already-sent and skipped: {skipped}")
    if not dry_run and sent:
        print(f"  mail written to logs/emails.log")
    conn.close()
    return {"candidates": len(candidates), "sent": sent, "skipped": skipped,
            "subscriptions": n_subs, "verified": n_verified}


def main() -> None:
    ap = argparse.ArgumentParser(description="Check thresholds and send alerts.")
    ap.add_argument("--lookback", type=int, default=1,
                    help="Days back from the newest reading to consider. "
                         "Default 1 -- the latest day only.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would be sent, write nothing.")
    args = ap.parse_args()
    if args.lookback < 1:
        ap.error("--lookback must be at least 1")
    check(args.lookback, args.dry_run)


if __name__ == "__main__":
    main()
