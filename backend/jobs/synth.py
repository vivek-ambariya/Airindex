"""Synthetic measurement generator.

WHY THIS EXISTS: OpenAQ v3 requires an API key, and the pipeline needs to
be demonstrably working end to end before one is in place. This module
produces the SAME raw shape collect.py writes from the API, so clean.py,
load.py, publish.py and the whole frontend run on it unchanged. Swapping
in real data is `collect.py` without --synthetic; nothing downstream
knows the difference.

WHAT IS REAL AND WHAT IS NOT:
  Real      -- station names, cities, states, coordinates (CPCB sites).
  Generated -- every concentration value.
  Every output file and document carries a banner saying so.

The generator is not trying to be a model of atmospheric chemistry. It is
trying to produce data with the STRUCTURE the application must handle:
a strong Indo-Gangetic winter peak, monsoon washout, a twin-peaked
diurnal cycle, autocorrelated weather, and -- importantly -- realistic
dirt, so the cleaning rules in clean.py have genuine work to do and
data_quality_report.md reports real counts rather than zeros.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .stations_fixture import NORTH_PLAIN_CITIES, STATIONS

SEED = 20260904  # fixed, so the fixture is reproducible

# Annual-mean PM2.5 by city, ug/m3. Anchored on published CPCB/WHO
# city averages so the league table ranks the way the real one does.
CITY_BASE_PM25: dict[str, float] = {
    "Delhi": 104, "Ghaziabad": 110, "Noida": 98, "Gurugram": 89, "Faridabad": 94,
    "Kanpur": 88, "Lucknow": 86, "Bulandshahr": 92, "Varanasi": 78,
    "Patna": 84, "Muzaffarpur": 82, "Gaya": 76,
    "Kolkata": 64, "Howrah": 70, "Guwahati": 58,
    "Mumbai": 46, "Navi Mumbai": 44, "Pune": 42, "Nagpur": 52,
    "Ahmedabad": 58, "Surat": 50, "Vadodara": 48,
    "Jaipur": 66, "Jodhpur": 56,
    "Bhopal": 50, "Indore": 48, "Bhilai": 60,
    "Chandigarh": 62, "Ludhiana": 72, "Amritsar": 68,
    "Dehradun": 64, "Srinagar": 54,
    "Hyderabad": 40, "Bengaluru": 30, "Chennai": 32, "Vellore": 34,
    "Kochi": 24, "Thiruvananthapuram": 22, "Visakhapatnam": 38, "Amaravati": 36,
}

# Monthly multipliers. Winter inversion traps emissions over the northern
# plain; the monsoon scavenges particulate out of the column. The southern
# coast sees a far flatter year, applied via the `north` weight below.
MONTHLY_SHAPE = np.array([1.34, 1.06, 0.79, 0.74, 0.68, 0.56,
                          0.38, 0.34, 0.42, 0.86, 1.38, 1.28])

# Twin-peaked day: morning traffic plus a shallow boundary layer, an
# afternoon minimum as the layer lifts, then a deeper evening peak from
# traffic and biomass burning under a collapsing layer.
HOURLY_SHAPE = np.array([
    1.18, 1.14, 1.08, 1.04, 1.06, 1.16, 1.30, 1.38, 1.34, 1.18, 0.98, 0.84,
    0.74, 0.68, 0.66, 0.70, 0.80, 0.96, 1.16, 1.34, 1.44, 1.42, 1.34, 1.26,
])

# Ratio to PM2.5 for the other parameters. Coarse dust lifts PM10 well
# above the fine fraction in the dry north-west.
PARAM_RATIO = {"pm25": 1.0, "pm10": 2.15, "no2": 0.44}
PARAM_UNITS = {"pm25": "ug/m3", "pm10": "ug/m3", "no2": "ug/m3"}

# How many stations carry each parameter. PM2.5 everywhere; the others on
# a subset, which is also true of the real network.
PARAM_COVERAGE = {"pm25": 65, "pm10": 40, "no2": 20}


def build_station_frame() -> pd.DataFrame:
    """stations.parquet -- the same columns collect.py writes."""
    rows = []
    for i, (name, city, state, lat, lon) in enumerate(STATIONS):
        rows.append({
            # Negative ids can never collide with a real OpenAQ id.
            "openaq_id": -(i + 1),
            "name": name,
            "city": city,
            "state": state,
            "country_code": "IN",
            "lat": lat,
            "lon": lon,
        })
    return pd.DataFrame(rows)


def build_sensor_frame(stations: pd.DataFrame) -> pd.DataFrame:
    rows = []
    sensor_id = -1
    for param, n_stations in PARAM_COVERAGE.items():
        for _, st in stations.head(n_stations).iterrows():
            rows.append({
                "sensor_id": sensor_id,
                "openaq_id": int(st["openaq_id"]),
                "parameter": param,
                "units": PARAM_UNITS[param],
            })
            sensor_id -= 1
    return pd.DataFrame(rows)


def _ar1_weather(n: int, rng: np.random.Generator, rho: float = 0.93) -> np.ndarray:
    """Autocorrelated multiplicative noise.

    Air quality is persistent -- a still, polluted day is usually
    followed by another. White noise would let the cleaning rules and the
    Phase 6 regression see a much easier problem than the real one.
    """
    shocks = rng.normal(0, 1, n)
    out = np.empty(n)
    out[0] = shocks[0]
    for i in range(1, n):
        out[i] = rho * out[i - 1] + np.sqrt(1 - rho ** 2) * shocks[i]
    return out


def generate(date_from: pd.Timestamp, date_to: pd.Timestamp,
             seed: int = SEED) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Return (stations, sensors, measurements, seeded_dirt_counts)."""
    rng = np.random.default_rng(seed)
    stations = build_station_frame()
    sensors = build_sensor_frame(stations)
    by_openaq = stations.set_index("openaq_id")

    hours = pd.date_range(date_from, date_to + pd.Timedelta(days=1),
                          freq="h", inclusive="left")
    n = len(hours)
    month_idx = hours.month.to_numpy() - 1
    hour_idx = hours.hour.to_numpy()
    doy = hours.dayofyear.to_numpy()

    # Counts of dirt deliberately injected, for cross-checking against
    # what clean.py actually catches. Sparse days are NOT listed: they
    # emerge from the absence model rather than being injected, and
    # clean.py is what discovers them.
    dirt = {k: 0 for k in ("negative", "zero_pm", "sentinel",
                           "implausible", "flatline_hours")}
    frames = []

    for _, sensor in sensors.iterrows():
        st = by_openaq.loc[int(sensor["openaq_id"])]
        param = sensor["parameter"]
        city = st["city"]

        base = CITY_BASE_PM25.get(city, 45.0) * PARAM_RATIO[param]
        # 1.0 = full northern-plain seasonality, 0.42 = coastal south.
        north = 1.0 if city in NORTH_PLAIN_CITIES else 0.42

        seasonal = 1 + (MONTHLY_SHAPE[month_idx] - 1) * north
        diurnal = HOURLY_SHAPE[hour_idx]
        # A slow multi-year drift, so the five-year trend is not flat.
        trend = 1 + 0.02 * np.sin(2 * np.pi * (doy / 365.25)) - \
            0.012 * ((hours.year.to_numpy() - hours.year.min()))
        weather = np.exp(0.34 * _ar1_weather(n, rng))

        values = base * seasonal * diurnal * trend * weather
        values *= rng.lognormal(0, 0.10, n)          # instrument scatter
        values = np.clip(values, 0.5, None)

        coverage = np.full(n, 100.0)
        n_raw = np.full(n, 4)                         # 15-minute samples
        keep = np.ones(n, dtype=bool)

        # ---- realistic absence -------------------------------------
        # Routine downtime: calibration, power, telemetry.
        keep &= rng.random(n) > 0.035
        # Occasional multi-day outages.
        for _ in range(rng.integers(2, 7)):
            start = rng.integers(0, max(n - 200, 1))
            keep[start:start + int(rng.integers(24, 200))] = False

        # ---- station-specific behaviour the UI must handle ----------
        if st["name"] == "Dampier Park":
            # Muzaffarpur: chronically sparse. Lands near 45%
            # completeness so the "no band assigned" path is real.
            keep &= rng.random(n) > 0.52
        if st["name"] == "Sector 62":
            # Noida: goes silent for the final 45 days. This is the
            # "silent, not clean" case -- a station that stops reporting
            # must never read as good air.
            keep[-45 * 24:] = False

        # ---- seeded dirt, so the cleaning rules have real work ------
        idx = np.arange(n)

        neg = rng.choice(idx, size=int(n * 0.0016), replace=False)
        values[neg] = -np.abs(values[neg]) * rng.uniform(0.1, 1.0, len(neg))
        dirt["negative"] += int(keep[neg].sum())

        if param in ("pm25", "pm10"):
            zeros = rng.choice(idx, size=int(n * 0.0011), replace=False)
            values[zeros] = 0.0
            dirt["zero_pm"] += int(keep[zeros].sum())

        sent = rng.choice(idx, size=int(n * 0.0009), replace=False)
        values[sent] = rng.choice([999.0, 9999.0, -999.0], size=len(sent))
        dirt["sentinel"] += int(keep[sent].sum())

        imp = rng.choice(idx, size=int(n * 0.0004), replace=False)
        ceiling = 2000.0 if param == "pm10" else 1000.0
        values[imp] = ceiling * rng.uniform(1.05, 3.0, len(imp))
        dirt["implausible"] += int(keep[imp].sum())

        # Stuck sensor: one value held for 6-30 hours. The classic
        # failure that looks like data.
        #
        # Episode count scales with the series length -- roughly one
        # stuck spell per two months. A fixed count would make a
        # one-month slice look catastrophically broken and a five-year
        # backfill look pristine.
        n_flatlines = max(1, int(n / 1400))
        for _ in range(n_flatlines):
            start = int(rng.integers(0, max(n - 40, 1)))
            run = int(rng.integers(6, 30))
            values[start:start + run] = round(float(values[start]), 1)
            dirt["flatline_hours"] += int(keep[start:start + run].sum())

        frame = pd.DataFrame({
            "sensor_id": np.int64(sensor["sensor_id"]),
            "parameter": param,
            "datetime_utc": hours,
            "value": np.round(values, 3),
            "coverage_pct": coverage,
            "n_raw": n_raw,
        })[keep]
        frames.append(frame)

    measurements = pd.concat(frames, ignore_index=True)

    # first_seen / last_seen per station, from what was actually kept.
    span = (measurements.merge(sensors[["sensor_id", "openaq_id"]], on="sensor_id")
            .groupby("openaq_id")["datetime_utc"].agg(["min", "max"]))
    stations = stations.merge(
        span.rename(columns={"min": "first_seen", "max": "last_seen"}),
        left_on="openaq_id", right_index=True, how="left")
    stations["first_seen"] = stations["first_seen"].dt.date
    stations["last_seen"] = stations["last_seen"].dt.date

    return stations, sensors, measurements, dirt
