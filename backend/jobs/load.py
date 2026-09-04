"""Clean daily parquet -> MariaDB.

    python -m jobs.load                 # everything in data/clean
    python -m jobs.load --month 2026-08 # one partition
    python -m jobs.load --truncate      # start from empty

Idempotent. Both writes are upserts keyed on the natural key, so running
this twice leaves the same rows and does not renumber stations -- which
matters because subscriptions and readings both reference stations.id.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import pymysql
from dotenv import load_dotenv

from .paths import BACKEND_DIR, CLEAN_DIR

load_dotenv(BACKEND_DIR / ".env", override=False)
sys.path.insert(0, str(BACKEND_DIR))

from app.bands import SUPPORTED_PARAMETERS  # noqa: E402
from app.db import connect, load_sql  # noqa: E402

BATCH = 5000


def _die(message: str) -> None:
    sys.exit(f"\nload.py: {message}")


def _connect():
    try:
        return connect()
    except pymysql.err.OperationalError as exc:
        _die(f"cannot reach the database ({exc}).\n"
             f"  Start XAMPP's MySQL, then check DB_* in backend/.env.")
    except pymysql.err.InternalError as exc:
        _die(f"{exc}\n  Has schema.sql been applied? Run:\n"
             f"    mysql -u root < backend/schema.sql")


def load_stations(conn) -> dict[int, int]:
    path = CLEAN_DIR / "stations.parquet"
    if not path.exists():
        _die(f"{path} not found. Run: python -m jobs.clean")
    stations = pd.read_parquet(path)

    # NaN is not NULL as far as the driver is concerned; it arrives as
    # the float nan and MariaDB stores the string 'nan' in a VARCHAR.
    stations = stations.astype(object).where(pd.notna(stations), None)

    sql = load_sql("station_upsert.sql")
    rows = [{
        "openaq_id": int(r["openaq_id"]),
        "name": r["name"],
        "city": r["city"],
        "state": r["state"],
        "country_code": r["country_code"] or "IN",
        "lat": float(r["lat"]),
        "lon": float(r["lon"]),
        "first_seen": r["first_seen"],
        "last_seen": r["last_seen"],
    } for _, r in stations.iterrows()]

    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    print(f"  stations: {len(rows)} upserted")

    with conn.cursor() as cur:
        cur.execute(load_sql("station_id_map.sql"))
        return {int(r["openaq_id"]): int(r["id"]) for r in cur.fetchall()}


def load_readings(conn, id_map: dict[int, int], month: str | None) -> int:
    pattern = f"month={month}" if month else "month=*"
    parts = sorted(CLEAN_DIR.glob(f"{pattern}/*.parquet"))
    if not parts:
        _die(f"no clean partitions matching {pattern} in {CLEAN_DIR}. "
             f"Run: python -m jobs.clean")

    sql = load_sql("reading_upsert.sql")
    total, skipped_param, skipped_station = 0, 0, 0

    for part in parts:
        frame = pd.read_parquet(part)
        rows = []
        for r in frame.itertuples(index=False):
            if r.parameter not in SUPPORTED_PARAMETERS:
                skipped_param += 1
                continue
            station_id = id_map.get(int(r.openaq_id))
            if station_id is None:
                # A reading whose station is not loaded would violate the
                # foreign key. Counted, not silently dropped.
                skipped_station += 1
                continue
            rows.append({
                "station_id": station_id,
                "reading_date": pd.Timestamp(r.reading_date).date(),
                "parameter": r.parameter,
                "value": float(r.value),
                "n_hours": int(r.n_hours),
                "completeness": float(r.completeness),
            })

        for start in range(0, len(rows), BATCH):
            with conn.cursor() as cur:
                cur.executemany(sql, rows[start:start + BATCH])
            conn.commit()
        total += len(rows)
        print(f"    {part.parent.name}: {len(rows):,} rows")

    if skipped_param:
        print(f"  skipped {skipped_param:,} rows: parameter not in "
              f"{sorted(SUPPORTED_PARAMETERS)}")
    if skipped_station:
        print(f"  skipped {skipped_station:,} rows: station not in the "
              f"stations table")
    return total


def main() -> None:
    ap = argparse.ArgumentParser(description="Load clean daily parquet into MariaDB.")
    ap.add_argument("--month", default=None, help="Load one month=YYYY-MM partition.")
    ap.add_argument("--truncate", action="store_true",
                    help="Empty readings_daily and stations first. "
                         "Refuses if any subscription exists.")
    args = ap.parse_args()

    conn = _connect()
    print("load.py")

    if args.truncate:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM subscriptions")
            n_subs = int(cur.fetchone()["n"])
        if n_subs:
            _die(f"refusing to truncate: {n_subs} subscription(s) reference "
                 f"stations.id.\n  Delete them first, or reload without "
                 f"--truncate (the upserts are idempotent).")
        with conn.cursor() as cur:
            # Order matters: the FK points from readings to stations.
            cur.execute("DELETE FROM readings_daily")
            cur.execute("DELETE FROM stations")
            cur.execute("ALTER TABLE stations AUTO_INCREMENT = 1")
        conn.commit()
        print("  truncated readings_daily and stations")

    id_map = load_stations(conn)
    print("  readings:")
    total = load_readings(conn, id_map, args.month)
    print(f"  readings: {total:,} upserted")

    with conn.cursor() as cur:
        cur.execute(load_sql("health.sql"))
        row = cur.fetchone()
    print(f"\n  in database now: {row['n_stations']} stations, "
          f"{row['n_readings']:,} readings, latest {row['latest_date']}")
    print(f"  spatial check (Delhi->Mumbai): {row['delhi_mumbai_km']} km "
          f"(expected ~1148)")
    conn.close()
    print("\n  next: python -m jobs.publish")


if __name__ == "__main__":
    main()
