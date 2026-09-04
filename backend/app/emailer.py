"""Outbound email.

Stubbed on purpose: send_email() appends to logs/emails.log and prints.
It is one function with a real signature, so swapping in SMTP or a
provider later is a change to this file and nowhere else. Nothing
upstream knows how mail is delivered.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_LOG = Path(__file__).resolve().parent.parent.parent / "logs" / "emails.log"


def _log_path() -> Path:
    raw = os.environ.get("EMAIL_LOG_PATH")
    if not raw:
        return _DEFAULT_LOG
    path = Path(raw)
    if not path.is_absolute():
        # Relative paths in .env are relative to backend/, which is where
        # both the Flask app and the jobs are run from.
        path = (Path(__file__).resolve().parent.parent / path).resolve()
    return path


def send_email(to: str, subject: str, body: str) -> None:
    """Pretend to send. Records the full message so it can be inspected."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    record = (
        f"{'=' * 72}\n"
        f"SENT-AT: {stamp}\n"
        f"TO:      {to}\n"
        f"SUBJECT: {subject}\n"
        f"{'-' * 72}\n"
        f"{body.rstrip()}\n"
    )
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(record)
    print(f"[email] -> {to}: {subject}  (logged to {path})")


def public_url(path: str) -> str:
    base = os.environ.get("PUBLIC_APP_URL", "http://localhost:5173").rstrip("/")
    return f"{base}/{path.lstrip('/')}"
