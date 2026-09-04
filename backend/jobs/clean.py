"""Raw hourly parquet -> clean daily parquet, plus the quality report.

Six rules, applied in order, every drop counted and attributed. The
report at docs/data_quality_report.md is a deliverable: it is the
document that says what this dataset cannot be used for.

    python -m jobs.clean

Reads : data/raw/measurements/year=*/  + data/raw/{stations,sensors}.parquet
Writes: data/clean/month=YYYY-MM/part-0.parquet   (daily aggregates)
        data/clean/stations.parquet
        data/clean/drops.parquet                  (every dropped hour, with reason)
        docs/data_quality_report.md

THE RULES (spec order):
  1. Negative values                          -> drop
  2. Zero values, PM2.5 and PM10 only         -> drop
  3. Sentinels 999 / 9999 / -999              -> drop
  4. Implausible: PM2.5 > 1000, PM10 > 2000   -> drop
  5. Flatlines: same value >= 6 hours running -> drop the whole run
  6. Days built from < 6 hours                -> KEEP, mark completeness low

Rule 6 is the one that does not drop. A sparse day is still information --
it just cannot carry a colour. The frontend greys anything under 50%
completeness, and app/bands.py refuses to assign a band.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .paths import (CLEAN_DIR, DOCS_DIR, PROVENANCE_JSON, RAW_MEASUREMENTS,
                    SENSORS_PARQUET, STATIONS_PARQUET, SYNTHETIC_BANNER,
                    ensure_dirs)

SENTINELS = (999.0, 9999.0, -999.0)
IMPLAUSIBLE_CEILING = {"pm25": 1000.0, "pm10": 2000.0}
ZERO_INVALID_FOR = {"pm25", "pm10"}
FLATLINE_MIN_RUN = 6
SPARSE_DAY_HOURS = 6
LOW_COMPLETENESS_PCT = 50.0

# Order matters for attribution: an hour that is both negative and a
# sentinel (-999) is counted once, under the first rule that matched.
RULES = [
    ("negative",     "Rule 1 - negative concentration"),
    ("zero_pm",      "Rule 2 - zero PM2.5/PM10"),
    ("sentinel",     "Rule 3 - sentinel value (999/9999/-999)"),
    ("implausible",  "Rule 4 - physically implausible magnitude"),
    ("flatline",     "Rule 5 - flatlined >= 6 consecutive hours"),
]


def _read_raw() -> pd.DataFrame:
    parts = sorted(RAW_MEASUREMENTS.rglob("*.parquet"))
    if not parts:
        raise SystemExit(
            "No raw measurements found. Run one of:\n"
            "  python -m jobs.collect --synthetic --years 5\n"
            "  python -m jobs.collect --all --years 5")
    frames = [pd.read_parquet(p) for p in parts]
    frame = pd.concat(frames, ignore_index=True)
    return frame.sort_values(["sensor_id", "datetime_utc"], ignore_index=True)


def _flag_flatlines(frame: pd.DataFrame) -> pd.Series:
    """True for every hour inside a run of >= 6 identical consecutive values.

    Grouped by sensor and computed on the value column: a new run starts
    wherever the value changes OR the sensor changes. Runs are measured
    in ROWS, not clock hours -- a gap in the middle of a stuck spell
    still leaves the instrument stuck, and treating the two sides as
    separate short runs would let a 20-hour flatline through as two
    5-hour ones.
    """
    sensor = frame["sensor_id"].to_numpy()
    value = frame["value"].to_numpy()
    new_run = np.empty(len(frame), dtype=bool)
    new_run[0] = True
    new_run[1:] = (value[1:] != value[:-1]) | (sensor[1:] != sensor[:-1])
    run_id = np.cumsum(new_run)
    run_length = pd.Series(run_id).groupby(run_id).transform("size").to_numpy()
    return pd.Series(run_length >= FLATLINE_MIN_RUN, index=frame.index)


def clean() -> dict:
    ensure_dirs()
    print("clean.py\n")

    provenance = {}
    if PROVENANCE_JSON.exists():
        provenance = json.loads(PROVENANCE_JSON.read_text())
    is_synthetic = bool(provenance.get("synthetic"))

    stations = pd.read_parquet(STATIONS_PARQUET)
    sensors = pd.read_parquet(SENSORS_PARQUET)
    raw = _read_raw()
    rows_in = len(raw)
    print(f"  rows in: {rows_in:,} hourly measurements")
    print(f"  {len(stations)} stations, {len(sensors)} sensors\n")

    # ---- rules 1-5: attribute every hour to at most one reason -------
    reason = pd.Series(pd.NA, index=raw.index, dtype="object")

    def mark(mask: pd.Series, label: str) -> None:
        # Only rows not already attributed, so counts sum to the total
        # dropped instead of double-counting overlaps.
        newly = mask & reason.isna()
        reason[newly] = label
        print(f"    {label:12s} {int(newly.sum()):>9,}")

    print("  applying rules:")
    mark(raw["value"] < 0, "negative")
    mark((raw["value"] == 0) & raw["parameter"].isin(ZERO_INVALID_FOR), "zero_pm")
    mark(raw["value"].isin(SENTINELS), "sentinel")

    implausible = pd.Series(False, index=raw.index)
    for param, ceiling in IMPLAUSIBLE_CEILING.items():
        implausible |= (raw["parameter"] == param) & (raw["value"] > ceiling)
    mark(implausible, "implausible")

    # Flatlines are detected on the values that survived rules 1-4:
    # a run of repeated -999s is a sentinel problem, not a stuck sensor,
    # and should be reported as the former.
    surviving = raw[reason.isna()]
    flat = _flag_flatlines(surviving)
    mark(flat.reindex(raw.index, fill_value=False), "flatline")

    drops = raw[reason.notna()].copy()
    drops["reason"] = reason[reason.notna()]
    clean_hours = raw[reason.isna()].copy()
    print(f"\n  rows out (hourly): {len(clean_hours):,} "
          f"({len(drops):,} dropped, {len(drops) / max(rows_in, 1):.2%})")

    # ---- daily aggregation, and rule 6 -------------------------------
    clean_hours["reading_date"] = clean_hours["datetime_utc"].dt.date
    daily = (clean_hours
             .groupby(["sensor_id", "parameter", "reading_date"], as_index=False)
             .agg(value=("value", "mean"), n_hours=("value", "size")))
    daily["value"] = daily["value"].round(3)
    # A day has 24 hours whether or not the instrument was on. Dividing
    # by hours observed instead would make every day 100% complete.
    daily["completeness"] = (daily["n_hours"] / 24 * 100).round(2)

    sparse = daily["n_hours"] < SPARSE_DAY_HOURS
    low = daily["completeness"] < LOW_COMPLETENESS_PCT
    print(f"\n  daily rows: {len(daily):,}")
    print(f"    rule 6 -- under {SPARSE_DAY_HOURS} hours: {int(sparse.sum()):,} "
          f"KEPT, flagged (not dropped)")
    print(f"    under {LOW_COMPLETENESS_PCT:g}% completeness: {int(low.sum()):,} "
          f"-- no band will be assigned")

    # Attach station identity.
    daily = (daily
             .merge(sensors[["sensor_id", "openaq_id"]], on="sensor_id", how="left")
             .merge(stations[["openaq_id", "name", "city", "state"]],
                    on="openaq_id", how="left"))

    # ---- write the clean lake, partitioned by month ------------------
    for path in sorted(CLEAN_DIR.rglob("*.parquet")):
        path.unlink()
    daily["reading_date"] = pd.to_datetime(daily["reading_date"])
    daily["month"] = daily["reading_date"].dt.strftime("%Y-%m")
    n_parts = 0
    for month, chunk in daily.groupby("month", sort=True):
        out_dir = CLEAN_DIR / f"month={month}"
        out_dir.mkdir(parents=True, exist_ok=True)
        chunk.drop(columns=["month"]).to_parquet(
            out_dir / "part-0.parquet", index=False, compression="snappy")
        n_parts += 1
    stations.to_parquet(CLEAN_DIR / "stations.parquet", index=False)
    if not drops.empty:
        drops.to_parquet(CLEAN_DIR / "drops.parquet", index=False)
    print(f"\n  wrote {n_parts} monthly partitions -> {CLEAN_DIR}")

    # ---- the report --------------------------------------------------
    summary = _report(raw, drops, daily, stations, sensors, reason,
                      rows_in, is_synthetic, provenance)
    print(f"  wrote {DOCS_DIR / 'data_quality_report.md'}")
    print("\n  next: python -m jobs.load")
    return summary


def _report(raw, drops, daily, stations, sensors, reason,
            rows_in, is_synthetic, provenance) -> dict:
    counts = {key: int((reason == key).sum()) for key, _ in RULES}
    rows_out = rows_in - len(drops)

    # Grouped by station AND parameter. Grouping by station alone mixes
    # units: a station carrying PM2.5, PM10 and NO2 has three rows per
    # calendar day, so a distinct-date count and a row count are not
    # comparable and "days under 50%" could exceed "days".
    per_station = (daily
                   .groupby(["name", "city", "state", "parameter"], dropna=False)
                   .agg(n_days=("reading_date", "size"),
                        mean_completeness=("completeness", "mean"),
                        days_under_50=("completeness", lambda s: int((s < 50).sum())),
                        first=("reading_date", "min"),
                        last=("reading_date", "max"))
                   .reset_index()
                   .sort_values(["mean_completeness", "name"]))

    lines: list[str] = []
    add = lines.append

    add("# Data quality report")
    add("")
    add(f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by "
        "`backend/jobs/clean.py`.")
    add("")
    if is_synthetic:
        add("> ## ⚠ SYNTHETIC DATA")
        add(">")
        add(f"> {SYNTHETIC_BANNER}")
        add(">")
        add("> The row counts, drop counts and completeness figures below are"
            " real measurements **of the generated dataset**. The cleaning"
            " rules genuinely ran and genuinely found these problems --"
            " they were seeded to make sure the rules are exercised rather"
            " than merely present. What you cannot do is draw a conclusion"
            " about Indian air quality from them.")
        add("")
    else:
        add(f"Source: OpenAQ v3, country `{provenance.get('country', '?')}`, "
            f"{provenance.get('date_from')} to {provenance.get('date_to')}.")
        add("")

    add("## Rows in, rows out")
    add("")
    add("| | Rows | Share of input |")
    add("|---|---:|---:|")
    add(f"| Hourly measurements read | {rows_in:,} | 100.00% |")
    for key, label in RULES:
        n = counts[key]
        add(f"| Dropped — {label} | {n:,} | {n / max(rows_in, 1):.2%} |")
    add(f"| **Dropped, total** | **{len(drops):,}** | "
        f"**{len(drops) / max(rows_in, 1):.2%}** |")
    add(f"| **Hourly rows surviving** | **{rows_out:,}** | "
        f"**{rows_out / max(rows_in, 1):.2%}** |")
    add(f"| Daily aggregates produced | {len(daily):,} | — |")
    add("")
    add("Each hour is attributed to at most one rule, in the order listed, so"
        " the drop counts sum exactly to the total. An hour reading `-999` is"
        " counted as negative rather than as a sentinel — the first rule that"
        " matched wins.")
    add("")

    add("## What each rule is for")
    add("")
    add("| Rule | Test | Action | Reasoning |")
    add("|---|---|---|---|")
    add("| 1 | `value < 0` | drop | A concentration cannot be negative. "
        "Usually a zero-drift or calibration artefact. |")
    add("| 2 | `value == 0` for PM2.5/PM10 | drop | An exact zero is an "
        "instrument reporting nothing, not air containing nothing. Gases can "
        "legitimately read zero, so the rule is restricted to PM. |")
    add("| 3 | `value in (999, 9999, -999)` | drop | Legacy no-data sentinels "
        "that pass through as if they were measurements. 999 µg/m³ of PM2.5 is "
        "not physically impossible, which is exactly why this rule has to be "
        "explicit rather than left to rule 4. |")
    add("| 4 | PM2.5 > 1000, PM10 > 2000 µg/m³ | drop | Above any credible "
        "ambient reading, including during a severe episode. |")
    add("| 5 | identical value ≥ 6 consecutive hours | drop the run | A stuck "
        "sensor. This is the most dangerous category because it looks like "
        "data: it has a plausible magnitude and it fills the gap that would "
        "otherwise be visible. |")
    add(f"| 6 | day built from < {SPARSE_DAY_HOURS} hours | **keep, flag** | A "
        "sparse day is still information. It is kept with a low `completeness` "
        "value, and the frontend greys it out rather than colouring it. |")
    add("")

    add("## Rule 6 in effect")
    add("")
    sparse_n = int((daily["n_hours"] < SPARSE_DAY_HOURS).sum())
    low_n = int((daily["completeness"] < LOW_COMPLETENESS_PCT).sum())
    add(f"- {sparse_n:,} daily values ({sparse_n / max(len(daily), 1):.2%}) rest "
        f"on fewer than {SPARSE_DAY_HOURS} hours. **Kept.**")
    add(f"- {low_n:,} daily values ({low_n / max(len(daily), 1):.2%}) fall below "
        f"{LOW_COMPLETENESS_PCT:g}% completeness and are shown grey with no band "
        "assigned.")
    add(f"- Mean completeness across all daily rows: "
        f"{daily['completeness'].mean():.1f}%.")
    add("")
    add("`completeness` is `n_hours / 24 × 100`. The denominator is the day, not"
        " the hours the instrument happened to report — otherwise every day is"
        " 100% complete by construction and the column says nothing.")
    add("")

    add("## Per-station completeness")
    add("")
    add(f"One row per station and parameter ({len(per_station)} series across"
        f" {daily['name'].nunique()} stations), worst first. `Days < 50%` is the"
        " count of daily values that will render grey and carry no band.")
    add("")
    add("| Station | City | State | Parameter | Days | Mean completeness | Days < 50% | First | Last |")
    add("|---|---|---|---|---:|---:|---:|---|---|")
    for row in per_station.itertuples(index=False):
        state = row.state if isinstance(row.state, str) else "—"
        city = row.city if isinstance(row.city, str) else "—"
        add(f"| {row.name} | {city} | {state} | {row.parameter} | "
            f"{row.n_days:,} | {row.mean_completeness:.1f}% | "
            f"{row.days_under_50:,} | "
            f"{row.first:%Y-%m-%d} | {row.last:%Y-%m-%d} |")
    add("")

    add("## Known gaps in the metadata")
    add("")
    no_state = int(stations["state"].isna().sum()) if "state" in stations else 0
    no_city = int(stations["city"].isna().sum()) if "city" in stations else 0
    add(f"- **State is not source data.** OpenAQ v3 gives a country and a "
        f"`locality`; it does not give a state or province. The `state` column "
        f"is filled from a city→state lookup in `backend/jobs/regions.py`. "
        f"{no_state} of {len(stations)} stations have no state as a result.")
    add(f"- {no_city} of {len(stations)} stations have no city label.")
    add("- **Station siting is not recorded.** A roadside monitor and a "
        "background monitor a kilometre apart measure genuinely different air, "
        "and nothing in this dataset distinguishes them. City averages mix the "
        "two.")
    add("- **A station's absence is not information about air.** The map draws "
        "a station that has stopped reporting in grey, never in a colour. "
        "Distinguishing 'clean' from 'not measured' is the single most "
        "important thing this dataset has to get right, and completeness is "
        "how it does it.")
    add("")

    add("## Reproducing this")
    add("")
    add("```bash")
    add("cd backend")
    if is_synthetic:
        add(f"python -m jobs.collect --synthetic --to "
            f"{provenance.get('date_to')} --years 5   # seed="
            f"{provenance.get('seed')}, deterministic")
    else:
        add("python -m jobs.collect --all --years 5")
    add("python -m jobs.clean")
    add("```")
    add("")
    add("The generator is seeded, so the synthetic path reproduces byte for"
        " byte. The API path will not: OpenAQ backfills and revises, so a"
        " collection run a month from now legitimately returns different"
        " numbers for the same dates. `data/raw/provenance.json` records"
        " which mode and which window produced any given lake.")
    add("")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "data_quality_report.md").write_text("\n".join(lines), encoding="utf-8")

    return {
        "rows_in": rows_in,
        "rows_out": rows_out,
        "dropped": len(drops),
        "drop_counts": counts,
        "daily_rows": len(daily),
        "sparse_days": sparse_n,
        "low_completeness_days": low_n,
        "synthetic": is_synthetic,
    }


if __name__ == "__main__":
    clean()
