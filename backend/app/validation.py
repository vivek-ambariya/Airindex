"""Request validation.

Every route parses its input through these helpers, so a bad query string
becomes a 400 with a reason a caller can act on, never a 500 from a
type error deeper in the stack.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from .bands import SUPPORTED_PARAMETERS

# Caps on /api/compare. Both exist to keep one URL from asking for a
# scan of the whole table.
MAX_COMPARE_CITIES = 5
MIN_COMPARE_CITIES = 2
MAX_COMPARE_DAYS = 1830          # five years and a bit
MAX_SERIES_DAYS = 1830

# Nearest-station search radius.
DEFAULT_MAX_KM = 50.0
MAX_ALLOWED_KM = 200.0

# Deliberately permissive but structural. Address validity is proven by
# the verification email arriving, not by a regex -- the regex only
# rejects input that cannot be an address at all.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


class ValidationError(ValueError):
    """Raised with a message intended to be shown to the caller."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


def require_float(raw: str | None, field: str,
                  lo: float | None = None, hi: float | None = None) -> float:
    if raw is None or str(raw).strip() == "":
        raise ValidationError(f"{field} is required", field)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number, got {raw!r}", field) from None
    # NaN and the infinities parse as floats but are not coordinates.
    if value != value or value in (float("inf"), float("-inf")):
        raise ValidationError(f"{field} must be a finite number", field)
    if lo is not None and value < lo:
        raise ValidationError(f"{field} must be >= {lo}", field)
    if hi is not None and value > hi:
        raise ValidationError(f"{field} must be <= {hi}", field)
    return value


def require_lat_lon(args) -> tuple[float, float]:
    lat = require_float(args.get("lat"), "lat", -90, 90)
    lon = require_float(args.get("lon"), "lon", -180, 180)
    return lat, lon


def parameter(args, default: str = "pm25") -> str:
    raw = (args.get("parameter") or default).strip().lower()
    if raw not in SUPPORTED_PARAMETERS:
        raise ValidationError(
            f"parameter must be one of {', '.join(SUPPORTED_PARAMETERS)}, got {raw!r}",
            "parameter",
        )
    return raw


def _one_date(raw: str, field: str) -> date:
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be an ISO date (YYYY-MM-DD), got {raw!r}",
                              field) from None


def date_range(args, fallback_days: int, max_days: int,
               latest: date | None = None) -> tuple[date, date]:
    """Parse ?from=&to=, defaulting to the last `fallback_days`.

    `latest` anchors the default window to the newest date in the dataset
    rather than to today, so a snapshot collected last month still opens
    on data instead of on an empty range.
    """
    anchor = latest or date.today()
    raw_to, raw_from = args.get("to"), args.get("from")

    date_to = _one_date(raw_to, "to") if raw_to else anchor
    date_from = _one_date(raw_from, "from") if raw_from else date_to - timedelta(days=fallback_days - 1)

    if date_from > date_to:
        raise ValidationError(f"from ({date_from}) is after to ({date_to})", "from")
    span = (date_to - date_from).days + 1
    if span > max_days:
        raise ValidationError(
            f"date range is {span} days; the maximum is {max_days}. "
            "Narrow the range or request fewer cities.",
            "from",
        )
    return date_from, date_to


def city_list(args) -> list[str]:
    raw = (args.get("cities") or "").strip()
    if not raw:
        raise ValidationError("cities is required, as a comma-separated list", "cities")
    # dict.fromkeys de-duplicates while keeping the caller's order, so
    # ?cities=Delhi,Delhi,Mumbai is two cities, not a duplicated column.
    cities = list(dict.fromkeys(c.strip() for c in raw.split(",") if c.strip()))
    if len(cities) < MIN_COMPARE_CITIES:
        raise ValidationError(
            f"give at least {MIN_COMPARE_CITIES} distinct cities to compare, got {len(cities)}",
            "cities",
        )
    if len(cities) > MAX_COMPARE_CITIES:
        raise ValidationError(
            f"at most {MAX_COMPARE_CITIES} cities, got {len(cities)}", "cities"
        )
    return cities


def require_email(raw: str | None) -> str:
    if not raw or not str(raw).strip():
        raise ValidationError("email is required", "email")
    email = str(raw).strip().lower()
    if len(email) > 255:
        raise ValidationError("email is too long (max 255 characters)", "email")
    if not _EMAIL_RE.match(email):
        raise ValidationError(f"that does not look like an email address: {raw!r}", "email")
    return email


def require_int(raw, field: str, lo: int | None = None, hi: int | None = None) -> int:
    if raw is None or str(raw).strip() == "":
        raise ValidationError(f"{field} is required", field)
    try:
        # int(str) rejects "3.5" and "1e3", which is what we want for an id.
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be an integer, got {raw!r}", field) from None
    if lo is not None and value < lo:
        raise ValidationError(f"{field} must be >= {lo}", field)
    if hi is not None and value > hi:
        raise ValidationError(f"{field} must be <= {hi}", field)
    return value
