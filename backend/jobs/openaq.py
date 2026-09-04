"""A small OpenAQ v3 client.

Deliberately thin: paginate, throttle, retry, hand back dicts. It knows
nothing about India -- the country is a parameter. That is what makes the
Phase 8 (Asia) expansion a config change; see verify_country_agnostic().

Endpoints used (https://docs.openaq.org):
    GET /v3/locations                 ?iso=IN&limit=1000&page=N
    GET /v3/sensors/{id}/hours        ?datetime_from=&datetime_to=&limit=1000&page=N

Auth is the X-API-Key header. The free tier is rate limited; the
throttle below stays under it rather than relying on catching 429s.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterator

import requests

DEFAULT_BASE_URL = "https://api.openaq.org/v3"

# OpenAQ's free tier allows 60 requests/minute. One request per second
# with a little slack keeps us comfortably inside it without needing to
# be told off first.
MIN_SECONDS_BETWEEN_REQUESTS = 1.05
MAX_PAGE_SIZE = 1000
MAX_RETRIES = 5


class OpenAQError(RuntimeError):
    pass


class MissingAPIKey(OpenAQError):
    def __init__(self):
        super().__init__(
            "OPENAQ_API_KEY is not set.\n"
            "  1. Register (free) at https://explore.openaq.org/register\n"
            "  2. Put the key in backend/.env as OPENAQ_API_KEY=...\n"
            "Or run with --synthetic to build the pipeline on a generated\n"
            "fixture instead (clearly labelled as such in every output)."
        )


@dataclass
class Client:
    api_key: str | None = None
    base_url: str = DEFAULT_BASE_URL
    session: requests.Session = field(default_factory=requests.Session)
    _last_request_at: float = 0.0
    request_count: int = 0

    @classmethod
    def from_env(cls) -> "Client":
        key = (os.environ.get("OPENAQ_API_KEY") or "").strip()
        if not key:
            raise MissingAPIKey()
        return cls(
            api_key=key,
            base_url=os.environ.get("OPENAQ_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        )

    # ---- transport ------------------------------------------------------
    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
            time.sleep(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)
        self._last_request_at = time.monotonic()

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"X-API-Key": self.api_key or "", "Accept": "application/json"}

        for attempt in range(1, MAX_RETRIES + 1):
            self._throttle()
            self.request_count += 1
            try:
                resp = self.session.get(url, params=params, headers=headers, timeout=60)
            except requests.RequestException as exc:
                if attempt == MAX_RETRIES:
                    raise OpenAQError(f"GET {url} failed after {attempt} tries: {exc}") from exc
                time.sleep(2 ** attempt)
                continue

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 401:
                raise OpenAQError(
                    "OpenAQ rejected the API key (401). Check OPENAQ_API_KEY in .env."
                )
            if resp.status_code == 404:
                # A sensor with no data for the window is a legitimate
                # 404 on some paths -- the caller decides what that means.
                raise OpenAQError(f"404 for {url} (params={params})")

            if resp.status_code == 429:
                # Honour Retry-After when given; otherwise back off.
                wait = float(resp.headers.get("Retry-After") or (2 ** attempt))
                print(f"    rate limited, waiting {wait:.0f}s "
                      f"(attempt {attempt}/{MAX_RETRIES})")
                time.sleep(wait)
                continue

            if 500 <= resp.status_code < 600:
                if attempt == MAX_RETRIES:
                    raise OpenAQError(f"{resp.status_code} from {url} after {attempt} tries")
                time.sleep(2 ** attempt)
                continue

            raise OpenAQError(f"{resp.status_code} from {url}: {resp.text[:300]}")

        raise OpenAQError(f"exhausted retries for {url}")

    def paginate(self, path: str, params: dict[str, Any] | None = None,
                 max_pages: int | None = None) -> Iterator[dict]:
        """Yield every result across pages.

        Stops when a page comes back short, which is more reliable than
        trusting meta.found -- OpenAQ returns found as a string like
        '>1000' once the count is large.
        """
        params = dict(params or {})
        params.setdefault("limit", MAX_PAGE_SIZE)
        page = 1
        while True:
            params["page"] = page
            payload = self.get(path, params)
            results = payload.get("results") or []
            yield from results
            if len(results) < params["limit"]:
                return
            page += 1
            if max_pages is not None and page > max_pages:
                return
            # OpenAQ caps offset-based paging; beyond this the API errors
            # rather than returning empty, so stop cleanly first.
            if page * params["limit"] > 100_000:
                return

    # ---- endpoints ------------------------------------------------------
    def locations(self, country_iso: str, limit: int = MAX_PAGE_SIZE) -> list[dict]:
        """Every monitoring location in a country.

        `iso` is the only country-specific input in this whole module.
        """
        return list(self.paginate("locations", {
            "iso": country_iso.upper(),
            "limit": limit,
        }))

    def sensor_hours(self, sensor_id: int, date_from: date, date_to: date) -> list[dict]:
        """Hourly aggregates for one sensor over a date range.

        Hourly, not daily, on purpose: the cleaning rules in clean.py need
        the hours. Flatline detection ("same value 6 hours running") and
        the n_hours/completeness columns cannot be reconstructed from a
        daily mean that the API already computed.
        """
        return list(self.paginate(f"sensors/{sensor_id}/hours", {
            "datetime_from": date_from.isoformat(),
            "datetime_to": date_to.isoformat(),
            "limit": MAX_PAGE_SIZE,
        }))


# ---- parsing helpers ----------------------------------------------------
# Kept as functions rather than methods so the synthetic generator can
# produce the same shapes and be parsed by the same code.

def parse_location(raw: dict) -> dict | None:
    """An OpenAQ location -> the fields the stations table needs.

    Returns None for a location without usable coordinates; a station
    with no position cannot go on a map and cannot answer a nearest
    query, so it is dropped here and counted by the caller.
    """
    coords = raw.get("coordinates") or {}
    lat, lon = coords.get("latitude"), coords.get("longitude")
    if lat is None or lon is None:
        return None
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    # (0, 0) is the classic "coordinates missing" sentinel in station
    # metadata -- it is in the Gulf of Guinea, never a monitoring site.
    if lat == 0.0 and lon == 0.0:
        return None
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return None

    country = raw.get("country") or {}
    return {
        "openaq_id": int(raw["id"]),
        "name": (raw.get("name") or f"OpenAQ {raw['id']}").strip()[:255],
        "city": (raw.get("locality") or None),
        "country_code": (country.get("code") or "").upper()[:2] or None,
        "lat": lat,
        "lon": lon,
        "first_seen": _iso_date(raw.get("datetimeFirst")),
        "last_seen": _iso_date(raw.get("datetimeLast")),
        "sensors": [
            {
                "sensor_id": int(s["id"]),
                "parameter": (s.get("parameter") or {}).get("name", "").lower(),
                "units": (s.get("parameter") or {}).get("units"),
            }
            for s in (raw.get("sensors") or [])
            if s.get("id") is not None
        ],
    }


def parse_hour(raw: dict, sensor_id: int, parameter: str) -> dict | None:
    """An OpenAQ hourly aggregate -> one raw measurement row."""
    value = raw.get("value")
    if value is None:
        return None
    period = raw.get("period") or {}
    stamp = (period.get("datetimeFrom") or {}).get("utc")
    if not stamp:
        return None
    parsed = _iso_datetime(stamp)
    if parsed is None:
        return None
    coverage = raw.get("coverage") or {}
    return {
        "sensor_id": sensor_id,
        "parameter": parameter,
        "datetime_utc": parsed,
        "value": float(value),
        # How much of the hour the instrument actually observed, as
        # reported by OpenAQ. Carried through so clean.py can tell a
        # full hour from a single spot reading.
        "coverage_pct": _as_float(coverage.get("percentComplete")),
        "n_raw": _as_int(coverage.get("observedCount")),
    }


def _iso_date(node) -> date | None:
    if not node:
        return None
    raw = node.get("utc") if isinstance(node, dict) else node
    parsed = _iso_datetime(raw)
    return parsed.date() if parsed else None


def _iso_datetime(raw) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    # Normalise to naive UTC. Everything downstream and every DATETIME
    # column in this project is UTC; carrying tzinfo around invites a
    # local-time conversion nobody asked for.
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def verify_country_agnostic() -> list[str]:
    """Phase 1 asked for the Asia-expansion assumption to be checked.

    This returns the complete list of places in the collector where a
    country appears. If it ever grows beyond "a value read from the
    environment", the Phase 8 claim has stopped being true.
    """
    return [
        "COLLECT_COUNTRY env var (backend/.env) -- the only default",
        "Client.locations(country_iso=...) -> GET /v3/locations?iso=<code>",
        "stations.country_code column, written from the API's own response",
        "collect.py --country flag, which overrides the env var",
    ]
