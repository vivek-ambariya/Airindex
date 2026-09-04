"""Database -> bundled frontend snapshot + Power BI CSV.

    python -m jobs.publish

Writes:
    frontend/public/snapshot.json      the map's entire data source
    powerbi/airindex_daily.csv         flat export for Power BI Desktop

WHY THE SNAPSHOT EXISTS: the map has to render with Flask stopped. The
API is for nearest-station lookup, comparison and alerts -- the things
that genuinely need a query. Drawing 65 markers and a station's history
does not, and making the map depend on a live backend means a dead
backend shows an empty country rather than the data it already had.

SIZE DISCIPLINE: values are rounded to one decimal (the instruments do
not justify more), and completeness is NOT shipped as a parallel array.
Only ~2% of days fall below the band floor, so the snapshot carries the
indices of those days instead. The frontend needs exactly one thing from
completeness -- which points to grey -- and that is what it gets.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv

from .paths import (BACKEND_DIR, FRONTEND_PUBLIC, POWERBI_DIR, PROVENANCE_JSON,
                    SYNTHETIC_BANNER, ensure_dirs)

load_dotenv(BACKEND_DIR / ".env", override=False)

import sys  # noqa: E402
sys.path.insert(0, str(BACKEND_DIR))

from app.bands import (BAND_NAMES, MIN_COMPLETENESS_FOR_BAND, THRESHOLDS,  # noqa: E402
                       UNITS, band_with_reason)
from app.db import connect, load_sql  # noqa: E402

# Fixed colour bands, shared with the frontend. Same six as the design
# mockups; CPCB NAQI categories.
BAND_COLOURS = ["#157F73", "#4FA79A", "#E6C351", "#E08A3C", "#C9497C", "#7E3A9E"]
NO_BAND_COLOUR = "#4A4A4A"

# How much history the snapshot carries. Five years of daily values for
# every station is the whole point of the series chart, and it compresses
# well over the wire.
SNAPSHOT_YEARS = 5


def _rows(conn, sql_name: str, params: dict) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(load_sql(sql_name), params)
        return cur.fetchall()


def build_snapshot(conn, parameter: str, country: str) -> dict:
    provenance = json.loads(PROVENANCE_JSON.read_text()) if PROVENANCE_JSON.exists() else {}

    latest = _rows(conn, "latest_date.sql", {"parameter": parameter})
    date_to: date | None = latest[0]["latest_date"] if latest else None
    if date_to is None:
        raise SystemExit(f"No readings for parameter={parameter}. "
                         f"Run jobs.load first.")
    date_from = date_to - timedelta(days=round(SNAPSHOT_YEARS * 365.25))

    print(f"  parameter={parameter}  {date_from} .. {date_to}")

    station_rows = _rows(conn, "stations_list.sql",
                         {"parameter": parameter, "country": country})
    series_rows = _rows(conn, "publish_series.sql",
                        {"parameter": parameter,
                         "date_from": date_from, "date_to": date_to})
    monthly_rows = _rows(conn, "publish_monthly.sql",
                         {"parameter": parameter,
                          "min_completeness": MIN_COMPLETENESS_FOR_BAND})
    city_rows = _rows(conn, "cities_list.sql",
                      {"parameter": parameter, "country": country})
    national_rows = _rows(conn, "national_monthly.sql",
                          {"parameter": parameter,
                           "min_completeness": MIN_COMPLETENESS_FOR_BAND})

    n_days = (date_to - date_from).days + 1

    # ---- pivot the series into per-station parallel arrays ----------
    by_station: dict[int, dict[date, dict]] = defaultdict(dict)
    for row in series_rows:
        by_station[row["station_id"]][row["reading_date"]] = row

    monthly_by_station: dict[int, dict[int, dict]] = defaultdict(dict)
    for row in monthly_rows:
        monthly_by_station[row["station_id"]][int(row["month"])] = row

    stations, total_points = [], 0
    for row in station_rows:
        sid = row["id"]
        days = by_station.get(sid, {})

        values: list[float | None] = []
        low_idx: list[int] = []
        for offset in range(n_days):
            day = days.get(date_from + timedelta(days=offset))
            if day is None:
                values.append(None)
                continue
            values.append(round(float(day["value"]), 1))
            if float(day["completeness"]) < MIN_COMPLETENESS_FOR_BAND:
                low_idx.append(offset)
        total_points += sum(1 for v in values if v is not None)

        months = [None] * 12
        month_days = [0] * 12
        for month, m in monthly_by_station.get(sid, {}).items():
            months[month - 1] = round(float(m["value"]), 1)
            month_days[month - 1] = int(m["n_days"])

        completeness_30d = float(row["completeness_30d"] or 0)
        latest_value = row["latest_value"]
        band, band_withheld = band_with_reason(
            parameter,
            float(latest_value) if latest_value is not None else None,
            day_completeness=float(row["latest_completeness"]) if row["latest_completeness"] is not None else None,
            window_completeness=completeness_30d,
        )

        stations.append({
            "id": sid,
            "name": row["name"],
            "city": row["city"],
            "state": row["state"],
            "lat": round(float(row["lat"]), 5),
            "lon": round(float(row["lon"]), 5),
            "first_seen": row["first_seen"].isoformat() if row["first_seen"] else None,
            "last_seen": row["last_seen"].isoformat() if row["last_seen"] else None,
            "latest_value": round(float(latest_value), 1) if latest_value is not None else None,
            "latest_date": row["latest_date"].isoformat() if row["latest_date"] else None,
            "completeness_30d": round(completeness_30d, 1),
            "band": band,
            "band_withheld": band_withheld,
            "silent": completeness_30d == 0.0,
            "values": values,
            # Indices into `values` that must render grey and carry no
            # band. Cheaper than a parallel completeness array, and it
            # encodes the only decision the frontend actually makes.
            "low_completeness": low_idx,
            "monthly": months,
            "monthly_n_days": month_days,
        })

    cities = []
    for row in city_rows:
        mean_value = float(row["mean_value"]) if row["mean_value"] is not None else None
        completeness = float(row["mean_completeness"] or 0)
        c_band, c_withheld = band_with_reason(parameter, mean_value,
                                              window_completeness=completeness)
        cities.append({
            "city": row["city"],
            "state": row["state"],
            "n_stations": int(row["n_stations"]),
            "mean_value": round(mean_value, 1) if mean_value is not None else None,
            "mean_completeness": round(completeness, 1),
            "band": c_band,
            "band_withheld": c_withheld,
        })

    snapshot = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "parameter": parameter,
            "unit": UNITS[parameter],
            "country": country,
            "start": date_from.isoformat(),
            "end": date_to.isoformat(),
            "step": "P1D",
            "n_days": n_days,
            "n_stations": len(stations),
            "n_cities": len(cities),
            "n_points": total_points,
            "completeness_floor": MIN_COMPLETENESS_FOR_BAND,
            "bands": {
                "names": BAND_NAMES,
                "colours": BAND_COLOURS,
                "no_band_colour": NO_BAND_COLOUR,
                "thresholds": THRESHOLDS[parameter],
                "source": "CPCB National Air Quality Index, 24-hour breakpoints",
            },
            "provenance": {
                "mode": provenance.get("mode"),
                "synthetic": bool(provenance.get("synthetic")),
                "collected_at_utc": provenance.get("generated_at_utc"),
                "warning": SYNTHETIC_BANNER if provenance.get("synthetic") else None,
            },
        },
        "stations": stations,
        "cities": cities,
        "national_monthly": [
            {"month": r["month"],
             "value": round(float(r["value"]), 1),
             "n_stations": int(r["n_stations"])}
            for r in national_rows
        ],
    }
    return snapshot


def write_powerbi_csv(conn, country: str) -> int:
    """Flat CSV for Power BI Desktop.

    Denormalised on purpose: the .pbix should be useful the moment it
    opens, without the reader having to define relationships first. Band
    and completeness_flag are precomputed so the report's colour rules do
    not have to re-implement the thresholds and drift from the app.
    """
    path = POWERBI_DIR / "airindex_daily.csv"
    written = 0
    with conn.cursor() as cur:
        cur.execute(load_sql("publish_flat.sql"), {"country": country})
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "station", "city", "state", "country_code", "lat", "lon",
                "reading_date", "year", "month", "parameter", "value",
                "n_hours", "completeness", "band", "band_index",
                "completeness_flag",
            ])
            while True:
                batch = cur.fetchmany(20000)
                if not batch:
                    break
                for r in batch:
                    band, _ = band_with_reason(
                        r["parameter"], float(r["value"]),
                        day_completeness=float(r["completeness"]))
                    writer.writerow([
                        r["station"], r["city"], r["state"], r["country_code"],
                        r["lat"], r["lon"], r["reading_date"].isoformat(),
                        r["year"], r["month"], r["parameter"], r["value"],
                        r["n_hours"], r["completeness"],
                        band or "No band",
                        BAND_NAMES.index(band) if band else -1,
                        "usable" if float(r["completeness"]) >= MIN_COMPLETENESS_FOR_BAND
                        else "low",
                    ])
                    written += 1
    print(f"  powerbi  -> {path} ({written:,} rows, "
          f"{path.stat().st_size / 1e6:.1f} MB)")
    return written


def main() -> None:
    import os
    ap = argparse.ArgumentParser(description="Publish frontend snapshot and BI CSV.")
    ap.add_argument("--parameter", default="pm25")
    ap.add_argument("--skip-csv", action="store_true",
                    help="Snapshot only, skip the Power BI export.")
    args = ap.parse_args()

    country = os.environ.get("COLLECT_COUNTRY", "IN").upper()
    ensure_dirs()
    conn = connect()
    print("publish.py")

    snapshot = build_snapshot(conn, args.parameter, country)
    out = FRONTEND_PUBLIC / "snapshot.json"
    # separators without spaces: this file is parsed, not read.
    out.write_text(json.dumps(snapshot, separators=(",", ":")), encoding="utf-8")
    meta = snapshot["meta"]
    print(f"  snapshot -> {out}")
    print(f"             {meta['n_stations']} stations, {meta['n_cities']} cities, "
          f"{meta['n_points']:,} daily values, "
          f"{out.stat().st_size / 1e6:.2f} MB")
    if meta["provenance"]["synthetic"]:
        print(f"             SYNTHETIC -- the frontend will show the banner")

    if not args.skip_csv:
        write_powerbi_csv(conn, country)

    conn.close()
    print("\n  the map now works with Flask stopped.")


if __name__ == "__main__":
    main()
