"""Open-Meteo ERA5 daily weather -> parquet, for the Phase 6 analysis.

    python analysis/fetch_weather.py --city Delhi

Open-Meteo's archive endpoint is free and needs no API key. It serves
ERA5 reanalysis, which is a physical model constrained by observations
rather than a station feed -- so it has no gaps, and it is NOT an
independent measurement at the monitor's location. That distinction
matters for the analysis and is stated in docs/methodology.md.

Variables, and why each one:
  temperature_2m_mean      seasonal cycle, and a proxy for heating demand
  temperature_2m_min       cold nights -> strong surface inversions, the
                           mechanism that traps emissions near the ground
  wind_speed_10m_mean      horizontal ventilation, the main dispersal term
  wind_speed_10m_max       gusts, which mix the layer even on calm days
  wind_direction_10m_dominant  north-westerlies carry crop-residue smoke
                           into Delhi; direction is not a magnitude, so it
                           enters as sin/cos components
  precipitation_sum        wet deposition scavenges particulate out
  shortwave_radiation_sum  drives daytime mixing depth

NOT available: boundary_layer_height. It is the single most physically
direct control for accumulation, and the archive endpoint returns nulls
for it at this location. temperature_2m_min stands in as an inversion
proxy, which is weaker, and the write-up says so.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import requests

ANALYSIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ANALYSIS_DIR.parent / "backend"))

from jobs.stations_fixture import STATIONS  # noqa: E402

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY_VARS = [
    "temperature_2m_mean",
    "temperature_2m_min",
    "wind_speed_10m_mean",
    "wind_speed_10m_max",
    "wind_direction_10m_dominant",
    "precipitation_sum",
    "shortwave_radiation_sum",
]


def city_centroid(city: str) -> tuple[float, float]:
    """Mean position of the city's stations.

    One weather series per CITY, not per station. ERA5's grid is ~25 km,
    so neighbouring monitors in the same city would receive identical
    values anyway -- pretending otherwise would imply spatial resolution
    the data does not have.
    """
    matches = [(lat, lon) for _, c, _, lat, lon in STATIONS
               if c.lower() == city.lower()]
    if not matches:
        sys.exit(f"No stations known for city {city!r}. "
                 f"Options include: Delhi, Kolkata, Mumbai, Chennai, Bengaluru.")
    lats, lons = zip(*matches)
    return sum(lats) / len(lats), sum(lons) / len(lons)


def fetch(city: str, start: str, end: str) -> pd.DataFrame:
    lat, lon = city_centroid(city)
    print(f"  {city}: centroid {lat:.4f}, {lon:.4f}")
    resp = requests.get(ARCHIVE_URL, params={
        "latitude": lat, "longitude": lon,
        "start_date": start, "end_date": end,
        "daily": ",".join(DAILY_VARS),
        "timezone": "UTC",
    }, timeout=90)
    if resp.status_code != 200:
        sys.exit(f"Open-Meteo returned HTTP {resp.status_code}: {resp.text[:300]}")
    payload = resp.json()
    frame = pd.DataFrame(payload["daily"])
    frame = frame.rename(columns={"time": "reading_date"})
    frame["reading_date"] = pd.to_datetime(frame["reading_date"])
    frame["city"] = city
    frame["grid_lat"] = payload["latitude"]
    frame["grid_lon"] = payload["longitude"]
    print(f"  {len(frame)} days, {frame['reading_date'].min().date()} .. "
          f"{frame['reading_date'].max().date()}")
    nulls = frame[DAILY_VARS].isna().sum()
    for var, n in nulls.items():
        if n:
            print(f"    {var}: {n} nulls")
    return frame


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch ERA5 daily weather.")
    ap.add_argument("--city", default="Delhi")
    ap.add_argument("--start", default="2021-08-31")
    ap.add_argument("--end", default="2026-08-31")
    args = ap.parse_args()

    print(f"fetch_weather.py  {args.city}  {args.start} .. {args.end}")
    frame = fetch(args.city, args.start, args.end)
    out = ANALYSIS_DIR / "output" / f"weather_{args.city.lower()}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out, index=False)
    print(f"\n  -> {out}")
    print(f"  next: python analysis/winter_rise.py --city {args.city}")


if __name__ == "__main__":
    main()
