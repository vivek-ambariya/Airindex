from __future__ import annotations

from flask import Blueprint, jsonify

from .. import db

bp = Blueprint("health", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    """Liveness, plus enough to tell a healthy empty database from a
    broken one. The Delhi-Mumbai distance is a live check that geometry
    works -- see sql/health.sql."""
    try:
        row = db.query_one("health.sql") or {}
    except Exception as exc:  # noqa: BLE001 - the point is to report it
        return jsonify({
            "status": "degraded",
            "database": "unreachable",
            "message": str(exc),
        }), 503

    # The known answer. If geometry silently changes axis order, this
    # number moves to ~560 and the endpoint says so.
    spatial_ok = row.get("delhi_mumbai_km") is not None and \
        abs(float(row["delhi_mumbai_km"]) - 1148) <= 12

    return jsonify({
        "status": "ok",
        "database": "ok",
        "db_version": row.get("db_version"),
        "spatial_ok": spatial_ok,
        "delhi_mumbai_km": row.get("delhi_mumbai_km"),
        "n_stations": row.get("n_stations"),
        "n_readings": row.get("n_readings"),
        "latest_date": row["latest_date"].isoformat() if row.get("latest_date") else None,
    })
