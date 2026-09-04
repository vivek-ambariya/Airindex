"""City comparison."""
from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request

from .. import db, validation as v
from ..bands import MIN_COMPLETENESS_FOR_BAND, UNITS, band_with_reason

bp = Blueprint("compare", __name__, url_prefix="/api")


@bp.get("/cities")
def list_cities():
    """Cities with data, ranked by mean value. Feeds the compare picker
    and the dashboard league table."""
    parameter = v.parameter(request.args)
    rows = db.query_all("cities_list.sql", {
        "parameter": parameter,
        "country": current_app.config["COUNTRY"],
    })
    cities = []
    for r in rows:
        mean_value = float(r["mean_value"]) if r.get("mean_value") is not None else None
        completeness = float(r["mean_completeness"] or 0)
        # Same gate and same wording as /api/stations and the published
        # snapshot, so a city is never coloured on one screen and grey
        # on another.
        band, band_withheld = band_with_reason(
            parameter, mean_value, window_completeness=completeness)
        cities.append({
            "city": r["city"],
            "state": r.get("state"),
            "n_stations": int(r["n_stations"]),
            "mean_value": mean_value,
            "mean_completeness": completeness,
            "band": band,
            "band_withheld": band_withheld,
            "first_date": r["first_date"].isoformat() if r.get("first_date") else None,
            "last_date": r["last_date"].isoformat() if r.get("last_date") else None,
            "n_rows": int(r["n_rows"]),
        })
    return jsonify({
        "parameter": parameter,
        "unit": UNITS[parameter],
        "count": len(cities),
        "cities": cities,
    })


@bp.get("/compare")
def compare_cities():
    """2-5 cities over a shared date axis.

    Both the city count and the date span are capped in validation --
    without that, one URL could ask for every city over five years and
    hold a connection open while MariaDB scans the table.

    Each city is queried separately (see sql/compare_city_series.sql for
    why) and then aligned onto one date axis here, so the response has a
    single `start` and equal-length arrays: the frontend can index across
    cities on the same day without doing date arithmetic.
    """
    cities = v.city_list(request.args)
    parameter = v.parameter(request.args)
    date_from, date_to = v.date_range(
        request.args, fallback_days=365, max_days=v.MAX_COMPARE_DAYS,
        latest=_latest_for(parameter),
    )
    country = current_app.config["COUNTRY"]
    n_days = (date_to - date_from).days + 1

    params_common = {
        "parameter": parameter,
        "country": country,
        "min_completeness": MIN_COMPLETENESS_FOR_BAND,
        "date_from": date_from,
        "date_to": date_to,
    }

    series = []
    for city in cities:
        rows = db.query_all("compare_city_series.sql", {**params_common, "city": city})
        summary = db.query_one("compare_city_summary.sql", {**params_common, "city": city}) or {}

        by_date = {r["reading_date"]: r for r in rows}
        values: list[float | None] = []
        n_stations: list[int | None] = []
        for offset in range(n_days):
            row = by_date.get(date_from + timedelta(days=offset))
            values.append(float(row["value"]) if row else None)
            n_stations.append(int(row["n_stations"]) if row else None)

        mean_value = float(summary["mean_value"]) if summary.get("mean_value") is not None else None
        mean_completeness = float(summary["mean_completeness"]) if summary.get("mean_completeness") is not None else None

        series.append({
            "city": city,
            # An unknown city name is not an error -- it comes back with
            # a null series and found=false, so a typo in one of five
            # cities does not fail the other four.
            "found": mean_value is not None,
            "values": values,
            "n_stations": n_stations,
            "summary": {
                "mean_value": mean_value,
                "min_value": float(summary["min_value"]) if summary.get("min_value") is not None else None,
                "max_value": float(summary["max_value"]) if summary.get("max_value") is not None else None,
                "n_days_present": int(summary["n_days"] or 0),
                "n_days_requested": n_days,
                "coverage_pct": round((int(summary["n_days"] or 0) / n_days) * 100, 2),
                "mean_completeness": mean_completeness,
                "max_stations": int(summary["max_stations"]) if summary.get("max_stations") is not None else 0,
                "band": band_with_reason(
                    parameter, mean_value,
                    window_completeness=mean_completeness)[0],
            },
        })

    return jsonify({
        "parameter": parameter,
        "unit": UNITS[parameter],
        "start": date_from.isoformat(),
        "end": date_to.isoformat(),
        "step": "P1D",
        "n_days": n_days,
        "completeness_floor": MIN_COMPLETENESS_FOR_BAND,
        "cities": series,
    })


def _latest_for(parameter: str):
    row = db.query_one("latest_date.sql", {"parameter": parameter})
    return row["latest_date"] if row and row.get("latest_date") else None
