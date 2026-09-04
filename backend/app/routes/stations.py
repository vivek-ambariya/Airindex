"""Station endpoints: listing, series, monthly profile, nearest."""
from __future__ import annotations

import math
from datetime import date, timedelta

from flask import Blueprint, current_app, jsonify, request

from .. import db, validation as v
from ..bands import MIN_COMPLETENESS_FOR_BAND, UNITS, band_with_reason

bp = Blueprint("stations", __name__, url_prefix="/api/stations")


def _latest_date(parameter: str) -> date | None:
    row = db.query_one("latest_date.sql", {"parameter": parameter})
    return row["latest_date"] if row and row.get("latest_date") else None


def _bounding_box(lat: float, max_km: float) -> tuple[float, float]:
    """Half-widths in degrees for a box that is guaranteed to contain
    every point within max_km.

    A degree of latitude is ~110.57 km everywhere. A degree of longitude
    is that times cos(latitude): ~111 km at the equator, ~96 km at
    Srinagar, 0 at the pole. Using one fixed number for both -- the 0.5
    the original sketch suggested -- either clips real candidates in the
    north or scans far more rows than needed in the south.

    The 1.02 factor is slack for the earth not being a sphere; the exact
    ST_Distance_Sphere filter downstream is what actually enforces
    max_km, so over-selecting here is cheap and under-selecting is a bug.
    """
    km_per_deg_lat = 110.574
    lat_delta = (max_km / km_per_deg_lat) * 1.02
    # cos() collapses towards the poles; floor it so we never divide by
    # something near zero and ask for a box wider than the planet.
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    lon_delta = min((max_km / (111.320 * cos_lat)) * 1.02, 180.0)
    return round(lat_delta, 6), round(lon_delta, 6)


def _shape_station(row: dict, parameter: str) -> dict:
    """One station as the API and the bundled snapshot both present it."""
    latest_value = row.get("latest_value")
    latest_completeness = row.get("latest_completeness")
    completeness_30d = float(row.get("completeness_30d") or 0.0)

    # A band is a claim about the air. Gated on BOTH the latest day and
    # the 30-day window -- see bands.band_with_reason. Gating on the day
    # alone would give a station that went silent six weeks ago a green
    # marker, because its last recorded day was itself complete.
    band, band_withheld = band_with_reason(
        parameter,
        float(latest_value) if latest_value is not None else None,
        day_completeness=float(latest_completeness) if latest_completeness is not None else None,
        window_completeness=completeness_30d,
    )

    return {
        "id": row["id"],
        "openaq_id": row.get("openaq_id"),
        "name": row["name"],
        "city": row.get("city"),
        "state": row.get("state"),
        "lat": float(row["lat"]),
        "lon": float(row["lon"]),
        "first_seen": row["first_seen"].isoformat() if row.get("first_seen") else None,
        "last_seen": row["last_seen"].isoformat() if row.get("last_seen") else None,
        "latest_value": float(latest_value) if latest_value is not None else None,
        "latest_date": row["latest_date"].isoformat() if row.get("latest_date") else None,
        "latest_completeness": float(latest_completeness) if latest_completeness is not None else None,
        "completeness_30d": completeness_30d,
        "days_reported_30d": int(row.get("days_reported_30d") or 0),
        "band": band,
        # Why there is no band, in words the UI can show verbatim.
        "band_withheld": band_withheld,
        # Distinguishes "clean air" from "no instrument reporting". The
        # map draws these differently, and the distinction is the whole
        # point of showing completeness at all.
        "silent": completeness_30d == 0.0,
    }


@bp.get("")
@bp.get("/")
def list_stations():
    parameter = v.parameter(request.args)
    rows = db.query_all("stations_list.sql", {
        "parameter": parameter,
        "country": current_app.config["COUNTRY"],
    })
    stations = [_shape_station(r, parameter) for r in rows]
    return jsonify({
        "parameter": parameter,
        "unit": UNITS[parameter],
        "country": current_app.config["COUNTRY"],
        "completeness_floor": MIN_COMPLETENESS_FOR_BAND,
        "count": len(stations),
        "stations": stations,
    })


@bp.get("/nearest")
def nearest_station():
    """Nearest station to a point, or 404 with a reason.

    Declared before the /<int:station_id> routes is unnecessary here --
    "nearest" cannot match the int converter -- but the ordering is kept
    deliberate anyway.
    """
    lat, lon = v.require_lat_lon(request.args)
    max_km = v.require_float(
        request.args.get("max_km", v.DEFAULT_MAX_KM),
        "max_km", 0.1, v.MAX_ALLOWED_KM,
    )
    parameter = v.parameter(request.args)
    lat_delta, lon_delta = _bounding_box(lat, max_km)

    row = db.query_one("nearest.sql", {
        "lat": lat, "lon": lon,
        "lat_delta": lat_delta, "lon_delta": lon_delta,
        "max_km": max_km,
        "country": current_app.config["COUNTRY"],
    })

    if row is None:
        # A 404 that says why, and says what would work -- the frontend
        # shows this text verbatim rather than inventing its own.
        return jsonify({
            "error": "no_station_in_range",
            "message": (
                f"No monitoring station within {max_km:g} km of "
                f"{lat:.4f}, {lon:.4f}. This is a gap in the network, "
                f"not a reading of clean air."
            ),
            "query": {"lat": lat, "lon": lon, "max_km": max_km},
        }), 404

    latest = db.query_one("station_latest.sql", {
        "station_id": row["id"], "parameter": parameter,
    }) or {}

    band, band_withheld = _nearest_band(parameter, latest)
    return jsonify({
        "parameter": parameter,
        "unit": UNITS[parameter],
        "query": {"lat": lat, "lon": lon, "max_km": max_km},
        "station": {
            "id": row["id"],
            "openaq_id": row.get("openaq_id"),
            "name": row["name"],
            "city": row.get("city"),
            "state": row.get("state"),
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "distance_km": float(row["distance_km"]),
            "latest_value": float(latest["value"]) if latest.get("value") is not None else None,
            "latest_date": latest["reading_date"].isoformat() if latest.get("reading_date") else None,
            "latest_completeness": float(latest["completeness"]) if latest.get("completeness") is not None else None,
            "band": band,
            "band_withheld": band_withheld,
        },
    })


def _nearest_band(parameter: str, latest: dict):
    """Band for the nearest-station panel.

    Only the latest day's completeness is available here without a
    second aggregate query, so that is what gates it. The listing
    endpoint applies the stricter window test as well.
    """
    if latest.get("value") is None:
        return None, "no readings for this parameter"
    return band_with_reason(
        parameter, float(latest["value"]),
        day_completeness=float(latest["completeness"]) if latest.get("completeness") is not None else None,
    )


@bp.get("/<int:station_id>/series")
def station_series(station_id: int):
    """Daily values as parallel arrays.

    Shape is { start, values[] } rather than a list of objects: one date
    anchor plus dense arrays, with the calendar walked day by day so a
    missing day is a null at a known index. An array of objects would
    repeat the field names ~1800 times and would let a gap disappear
    silently by simply not being there.
    """
    parameter = v.parameter(request.args)
    station = db.query_one("station_by_id.sql", {"station_id": station_id})
    if station is None:
        return jsonify({"error": "not_found",
                        "message": f"No station with id {station_id}."}), 404

    date_from, date_to = v.date_range(
        request.args, fallback_days=365, max_days=v.MAX_SERIES_DAYS,
        latest=_latest_date(parameter),
    )
    rows = db.query_all("station_series.sql", {
        "station_id": station_id, "parameter": parameter,
        "date_from": date_from, "date_to": date_to,
    })

    by_date = {r["reading_date"]: r for r in rows}
    n_days = (date_to - date_from).days + 1
    values: list[float | None] = []
    completeness: list[float | None] = []
    n_hours: list[int | None] = []
    for offset in range(n_days):
        row = by_date.get(date_from + timedelta(days=offset))
        if row is None:
            values.append(None)
            completeness.append(None)
            n_hours.append(None)
        else:
            values.append(float(row["value"]))
            completeness.append(float(row["completeness"]))
            n_hours.append(int(row["n_hours"]))

    present = [x for x in values if x is not None]
    return jsonify({
        "station_id": station_id,
        "station_name": station["name"],
        "city": station.get("city"),
        "parameter": parameter,
        "unit": UNITS[parameter],
        "start": date_from.isoformat(),
        "end": date_to.isoformat(),
        "step": "P1D",
        "completeness_floor": MIN_COMPLETENESS_FOR_BAND,
        "n_days": n_days,
        "n_present": len(present),
        "values": values,
        "completeness": completeness,
        "n_hours": n_hours,
    })


@bp.get("/<int:station_id>/monthly")
def station_monthly(station_id: int):
    """Twelve monthly means -- the seasonal profile."""
    parameter = v.parameter(request.args)
    station = db.query_one("station_by_id.sql", {"station_id": station_id})
    if station is None:
        return jsonify({"error": "not_found",
                        "message": f"No station with id {station_id}."}), 404

    rows = db.query_all("station_monthly.sql", {
        "station_id": station_id, "parameter": parameter,
        "min_completeness": MIN_COMPLETENESS_FOR_BAND,
    })
    by_month = {int(r["month"]): r for r in rows}

    # Always twelve slots. A month with no qualifying data is a null,
    # not an absent key -- the chart needs to draw the hole.
    months = []
    for month in range(1, 13):
        row = by_month.get(month)
        months.append({
            "month": month,
            "value": float(row["value"]) if row else None,
            "n_days": int(row["n_days"]) if row else 0,
            "mean_completeness": float(row["mean_completeness"]) if row else None,
        })

    return jsonify({
        "station_id": station_id,
        "station_name": station["name"],
        "city": station.get("city"),
        "parameter": parameter,
        "unit": UNITS[parameter],
        "min_completeness": MIN_COMPLETENESS_FOR_BAND,
        "months": months,
    })
