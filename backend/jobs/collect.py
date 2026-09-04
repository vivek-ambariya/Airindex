"""OpenAQ -> raw parquet.

Run manually. Two modes, one output shape:

    # Phase 1 -- one city, one month, real API
    python -m jobs.collect --city Delhi --months 1

    # Phase 2 -- the whole country, five years
    python -m jobs.collect --all --years 5

    # No API key yet -- generate a fixture with the same schema
    python -m jobs.collect --synthetic --years 5

    # Phase 8 check: show every place a country is referenced
    python -m jobs.collect --verify-country-agnostic

Writes:
    data/raw/stations.parquet
    data/raw/sensors.parquet
    data/raw/measurements/year=YYYY/part-*.parquet
    data/raw/provenance.json     <- says which mode produced this data

HOURLY, not daily. The API can hand back daily means directly, but the
cleaning rules need the hours: a flatline is defined over consecutive
hours, and n_hours/completeness cannot be recovered from an average
somebody else already took.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone

import pandas as pd
from dotenv import load_dotenv

from . import openaq
from .paths import (PROVENANCE_JSON, RAW_MEASUREMENTS, SENSORS_PARQUET,
                    STATIONS_PARQUET, SYNTHETIC_BANNER, BACKEND_DIR, ensure_dirs)
from .regions import state_for_city

load_dotenv(BACKEND_DIR / ".env", override=False)

# Parameters this project stores. OpenAQ carries more; these are the ones
# with CPCB bands defined in app/bands.py.
WANTED_PARAMETERS = {"pm25", "pm10", "no2", "so2", "o3", "co"}


def _write_measurements(frame: pd.DataFrame) -> int:
    """Partition by year, as the spec's data/clean layout implies for the
    lake: a five-year backfill is otherwise one unwieldy file, and
    clean.py can then process a year at a time."""
    if frame.empty:
        return 0
    frame = frame.copy()
    frame["year"] = frame["datetime_utc"].dt.year
    written = 0
    for year, chunk in frame.groupby("year", sort=True):
        out_dir = RAW_MEASUREMENTS / f"year={year}"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "part-0.parquet"
        chunk.drop(columns=["year"]).to_parquet(path, index=False,
                                                compression="snappy")
        written += len(chunk)
        print(f"    {path.relative_to(RAW_MEASUREMENTS.parent.parent)}: "
              f"{len(chunk):,} rows")
    return written


def _clear_measurements() -> None:
    if not RAW_MEASUREMENTS.exists():
        return
    for path in sorted(RAW_MEASUREMENTS.rglob("*.parquet")):
        path.unlink()


def _provenance(mode: str, extra: dict) -> None:
    payload = {
        "mode": mode,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "synthetic": mode == "synthetic",
        **extra,
    }
    if mode == "synthetic":
        payload["WARNING"] = SYNTHETIC_BANNER
    PROVENANCE_JSON.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\n  provenance -> {PROVENANCE_JSON}")


# ---------------------------------------------------------------------
# Real API path
# ---------------------------------------------------------------------
def collect_from_api(country: str, date_from: date, date_to: date,
                     city: str | None, max_stations: int | None) -> None:
    client = openaq.Client.from_env()
    print(f"  OpenAQ v3 {client.base_url}  country={country}")

    print(f"\n  [1/2] locations for {country} ...")
    raw_locations = client.locations(country)
    print(f"        {len(raw_locations)} returned")

    parsed, no_coords = [], 0
    for raw in raw_locations:
        loc = openaq.parse_location(raw)
        if loc is None:
            no_coords += 1
            continue
        # The API's own country code is authoritative; the iso filter is
        # trusted but verified.
        if loc["country_code"] and loc["country_code"] != country.upper():
            continue
        loc["country_code"] = country.upper()
        loc["state"] = state_for_city(loc["city"], country)
        parsed.append(loc)
    if no_coords:
        print(f"        {no_coords} dropped: no usable coordinates")

    if city:
        needle = city.strip().lower()
        parsed = [p for p in parsed
                  if (p["city"] or "").lower() == needle
                  or needle in (p["name"] or "").lower()]
        print(f"        {len(parsed)} match city={city!r}")
    if max_stations:
        parsed = parsed[:max_stations]
        print(f"        capped at {len(parsed)} stations")

    if not parsed:
        sys.exit(f"No stations found for country={country} city={city!r}. "
                 f"Nothing written.")

    station_rows, sensor_rows = [], []
    for loc in parsed:
        station_rows.append({k: loc[k] for k in
                             ("openaq_id", "name", "city", "state",
                              "country_code", "lat", "lon",
                              "first_seen", "last_seen")})
        for sensor in loc["sensors"]:
            if sensor["parameter"] in WANTED_PARAMETERS:
                sensor_rows.append({
                    "sensor_id": sensor["sensor_id"],
                    "openaq_id": loc["openaq_id"],
                    "parameter": sensor["parameter"],
                    "units": sensor["units"],
                })

    stations = pd.DataFrame(station_rows)
    sensors = pd.DataFrame(sensor_rows)
    if sensors.empty:
        sys.exit("No sensors for the wanted parameters. Nothing written.")

    print(f"\n  [2/2] hourly measurements for {len(sensors)} sensors, "
          f"{date_from} .. {date_to}")
    print(f"        this is {len(sensors)} x paginated GETs at "
          f"~{openaq.MIN_SECONDS_BETWEEN_REQUESTS}s each -- be patient")

    _clear_measurements()
    collected, failures, total_rows = 0, [], 0
    buffer: list[pd.DataFrame] = []

    for i, sensor in enumerate(sensors.itertuples(index=False), start=1):
        try:
            raw_hours = client.sensor_hours(sensor.sensor_id, date_from, date_to)
        except openaq.OpenAQError as exc:
            # One dead sensor must not lose the other 400. Recorded and
            # reported at the end.
            failures.append({"sensor_id": sensor.sensor_id, "error": str(exc)})
            print(f"    [{i}/{len(sensors)}] sensor {sensor.sensor_id}: FAILED {exc}")
            continue

        rows = [r for r in (openaq.parse_hour(h, sensor.sensor_id, sensor.parameter)
                            for h in raw_hours) if r is not None]
        collected += 1
        if rows:
            buffer.append(pd.DataFrame(rows))
            total_rows += len(rows)
        print(f"    [{i}/{len(sensors)}] sensor {sensor.sensor_id} "
              f"({sensor.parameter}): {len(rows):,} hours")

        # Flush periodically so a long backfill does not hold everything
        # in memory, and so an interrupted run leaves usable partitions.
        if len(buffer) >= 40:
            _write_measurements(pd.concat(buffer, ignore_index=True))
            buffer.clear()

    if buffer:
        _write_measurements(pd.concat(buffer, ignore_index=True))

    stations.to_parquet(STATIONS_PARQUET, index=False)
    sensors.to_parquet(SENSORS_PARQUET, index=False)
    print(f"\n  stations -> {STATIONS_PARQUET} ({len(stations)} rows)")
    print(f"  sensors  -> {SENSORS_PARQUET} ({len(sensors)} rows)")
    print(f"  measurements: {total_rows:,} hourly rows")
    if failures:
        print(f"  {len(failures)} sensors failed; see provenance.json")

    _provenance("api", {
        "country": country,
        "city_filter": city,
        "date_from": date_from,
        "date_to": date_to,
        "n_stations": len(stations),
        "n_sensors": len(sensors),
        "n_sensors_collected": collected,
        "n_hourly_rows": total_rows,
        "api_requests": client.request_count,
        "failures": failures,
    })


# ---------------------------------------------------------------------
# Synthetic path
# ---------------------------------------------------------------------
def collect_synthetic(date_from: date, date_to: date, country: str) -> None:
    from . import synth

    print("  " + "!" * 68)
    for line in ("SYNTHETIC MODE", "", SYNTHETIC_BANNER):
        print(f"  {line}")
    print("  " + "!" * 68)

    print(f"\n  generating {date_from} .. {date_to} ...")
    stations, sensors, measurements, dirt = synth.generate(
        pd.Timestamp(date_from), pd.Timestamp(date_to))

    stations["state"] = [state_for_city(c, country) or s
                         for c, s in zip(stations["city"], stations["state"])]

    _clear_measurements()
    stations.to_parquet(STATIONS_PARQUET, index=False)
    sensors.to_parquet(SENSORS_PARQUET, index=False)
    print(f"\n  stations -> {STATIONS_PARQUET} ({len(stations)} rows)")
    print(f"  sensors  -> {SENSORS_PARQUET} ({len(sensors)} rows)")
    written = _write_measurements(measurements)
    print(f"  measurements: {written:,} hourly rows")

    print("\n  deliberately seeded dirt (clean.py should find these):")
    for reason, count in dirt.items():
        print(f"    {reason:16s} {count:>8,}")

    _provenance("synthetic", {
        "country": country,
        "date_from": date_from,
        "date_to": date_to,
        "seed": synth.SEED,
        "n_stations": len(stations),
        "n_sensors": len(sensors),
        "n_hourly_rows": written,
        "seeded_dirt": dirt,
    })


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Collect air quality data from OpenAQ v3 into raw parquet.")
    ap.add_argument("--country", default=None,
                    help="ISO-3166 alpha-2. Defaults to COLLECT_COUNTRY in .env. "
                         "This flag IS the Phase 8 Asia expansion.")
    ap.add_argument("--city", default=None,
                    help="Restrict to one city (Phase 1 vertical slice).")
    ap.add_argument("--all", action="store_true",
                    help="Every station in the country.")
    ap.add_argument("--years", type=float, default=None, help="Years back to collect.")
    ap.add_argument("--months", type=float, default=None, help="Months back to collect.")
    ap.add_argument("--to", default=None, help="End date, YYYY-MM-DD. Default: today.")
    ap.add_argument("--max-stations", type=int, default=None,
                    help="Cap station count, for a cheap trial run.")
    ap.add_argument("--synthetic", action="store_true",
                    help="Generate a fixture instead of calling the API.")
    ap.add_argument("--verify-country-agnostic", action="store_true",
                    help="List every place a country is referenced, then exit.")
    args = ap.parse_args()

    if args.verify_country_agnostic:
        print("Places a country appears in the collector:\n")
        for i, place in enumerate(openaq.verify_country_agnostic(), 1):
            print(f"  {i}. {place}")
        print("\nNo parsing, no endpoint and no cleaning rule is India-specific.")
        print("Phase 8 (Asia) is: COLLECT_COUNTRY=TH, or --country TH.")
        print("\nThe one enrichment that IS country-specific is the optional")
        print("city -> state lookup in jobs/regions.py. It returns None for an")
        print("unknown country, leaving stations.state NULL -- a missing label,")
        print("not a broken collector.")
        return

    import os
    country = (args.country or os.environ.get("COLLECT_COUNTRY", "IN")).upper()

    date_to = (datetime.strptime(args.to, "%Y-%m-%d").date()
               if args.to else date.today())
    if args.years:
        date_from = date_to - timedelta(days=round(args.years * 365.25))
    elif args.months:
        date_from = date_to - timedelta(days=round(args.months * 30.44))
    else:
        date_from = date_to - timedelta(days=30)

    if not (args.all or args.city or args.synthetic):
        ap.error("give --city for a slice, --all for the country, or --synthetic")

    ensure_dirs()
    print(f"\ncollect.py  {date_from} .. {date_to}  country={country}")

    if args.synthetic:
        collect_synthetic(date_from, date_to, country)
    else:
        collect_from_api(country, date_from, date_to, args.city, args.max_stations)

    print("\n  next: python -m jobs.clean")


if __name__ == "__main__":
    main()
