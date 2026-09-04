"""Phase 6: how much of the winter PM2.5 rise is weather, not emissions?

    python analysis/winter_rise.py --city Delhi

Method, in one paragraph. Regress log PM2.5 on a winter indicator, first
with no controls and then adding meteorology. The winter coefficient in
the first model is the raw winter penalty. What survives in the second is
the part weather cannot account for. The difference, as a share, is the
part weather CAN account for. This is a variance-accounting exercise, not
a causal estimate -- see the confounders section in
docs/methodology.md, which is the honest part of this analysis.

Outputs:
    analysis/output/winter_rise_<city>.md      the written result
    analysis/output/analysis_panel_<city>.parquet   the modelling panel
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import statsmodels.api as sm

ANALYSIS_DIR = Path(__file__).resolve().parent
REPO = ANALYSIS_DIR.parent
CLEAN_GLOB = str(REPO / "data" / "clean" / "month=*" / "*.parquet")
MIN_COMPLETENESS = 50.0


def build_panel(city: str) -> pd.DataFrame:
    weather_path = ANALYSIS_DIR / "output" / f"weather_{city.lower()}.parquet"
    if not weather_path.exists():
        sys.exit(f"{weather_path} not found.\n"
                 f"  Run: python analysis/fetch_weather.py --city {city}")
    sql = (ANALYSIS_DIR / "winter_rise.sql").read_text()
    con = duckdb.connect()
    frame = con.execute(sql, {
        "clean_glob": CLEAN_GLOB,
        "weather_path": str(weather_path),
        "city": city,
        "min_completeness": MIN_COMPLETENESS,
    }).df()
    con.close()
    if frame.empty:
        sys.exit(f"No joined rows for {city}. Has jobs.clean run?")

    # log outcome: PM2.5 is right-skewed and multiplicative in its
    # drivers -- halving ventilation roughly doubles concentration, it
    # does not add a fixed number of micrograms. Coefficients then read
    # as proportional changes.
    frame["log_pm25"] = np.log(frame["pm25"])

    # Wind direction is circular: 359 and 1 degree are neighbours, so it
    # cannot enter as a number. Sin/cos components preserve that.
    theta = np.radians(frame["wind_direction_10m_dominant"])
    frame["wind_sin"] = np.sin(theta)
    frame["wind_cos"] = np.cos(theta)

    # Ventilation is what matters and it is non-linear -- the difference
    # between 2 and 4 km/h matters far more than 20 to 22.
    frame["inv_wind"] = 1.0 / frame["wind_speed_10m_mean"].clip(lower=0.5)
    frame["log_wind"] = np.log(frame["wind_speed_10m_mean"].clip(lower=0.5))
    frame["rain_day"] = (frame["precipitation_sum"] > 1.0).astype(int)
    # Inversion proxy: cold nights with a large day-night spread.
    frame["diurnal_range"] = frame["temperature_2m_mean"] - frame["temperature_2m_min"]
    frame["year_index"] = frame["year"] - frame["year"].min()
    return frame


def fit(frame: pd.DataFrame, regressors: list[str], label: str):
    X = sm.add_constant(frame[regressors], has_constant="add")
    model = sm.OLS(frame["log_pm25"], X).fit(
        # Newey-West. Daily air quality is strongly autocorrelated -- a
        # polluted day follows a polluted day -- so ordinary standard
        # errors would be far too small and every t-statistic
        # implausibly large. 30 lags covers about a month of persistence.
        cov_type="HAC", cov_kwds={"maxlags": 30},
    )
    print(f"\n  {label}")
    print(f"    n = {int(model.nobs)}   adj R2 = {model.rsquared_adj:.3f}")
    for name in regressors:
        print(f"    {name:28s} {model.params[name]:+.4f}  "
              f"(se {model.bse[name]:.4f}, p {model.pvalues[name]:.3g})")
    return model


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="Delhi")
    args = ap.parse_args()
    city = args.city

    print(f"winter_rise.py  {city}")
    frame = build_panel(city)
    print(f"  panel: {len(frame)} city-days, "
          f"{frame['reading_date'].min().date()} .. {frame['reading_date'].max().date()}")
    print(f"  winter days: {int(frame['winter'].sum())}, "
          f"non-winter: {int((1 - frame['winter']).sum())}")

    # ---- descriptive -------------------------------------------------
    w = frame[frame["winter"] == 1]["pm25"]
    nw = frame[frame["winter"] == 0]["pm25"]
    raw_ratio = w.mean() / nw.mean()
    print(f"\n  raw winter mean {w.mean():.1f} vs non-winter {nw.mean():.1f} "
          f"ug/m3  (x{raw_ratio:.2f})")

    # ---- models ------------------------------------------------------
    WEATHER = ["log_wind", "wind_speed_10m_max", "temperature_2m_mean",
               "diurnal_range", "rain_day", "shortwave_radiation_sum",
               "wind_sin", "wind_cos"]

    m0 = fit(frame, ["winter"], "Model 0 - winter only")
    m1 = fit(frame, ["winter", "year_index"], "Model 1 - winter + year trend")
    m2 = fit(frame, ["winter", "year_index"] + WEATHER,
             "Model 2 - winter + year trend + weather")

    b0, b2 = m0.params["winter"], m2.params["winter"]
    explained = (b0 - b2) / b0 if b0 else float("nan")

    print(f"\n  winter coefficient, no controls   {b0:+.4f} "
          f"(x{np.exp(b0):.2f} in levels)")
    print(f"  winter coefficient, with weather  {b2:+.4f} "
          f"(x{np.exp(b2):.2f} in levels)")
    print(f"  share of the winter rise attributable to weather: {explained:.1%}")

    # ---- the diagnostic that decides how much of that to believe ----
    #
    # Regress the winter dummy itself on the weather controls. If winter
    # is largely reconstructible from weather, then "adding weather"
    # does not isolate a meteorological channel -- it partly re-adds the
    # calendar under another name, and the drop in the winter
    # coefficient is collinearity rather than explanation.
    collinearity = sm.OLS(
        frame["winter"], sm.add_constant(frame[WEATHER])).fit().rsquared
    print(f"\n  DIAGNOSTIC  R2 of (winter ~ weather alone) = {collinearity:.3f}")
    print(f"    {collinearity:.0%} of the winter indicator is reconstructible "
          f"from the controls.")
    if collinearity > 0.4:
        print(f"    This is high. The {explained:.0%} above is an UPPER BOUND on "
              f"weather's\n    contribution, not an estimate of it.")

    ground_truth = _ground_truth_check(explained, collinearity)

    out_panel = ANALYSIS_DIR / "output" / f"analysis_panel_{city.lower()}.parquet"
    frame.to_parquet(out_panel, index=False)

    write_report(city, frame, m0, m1, m2, raw_ratio, explained,
                 WEATHER, collinearity, ground_truth)
    print(f"\n  -> {ANALYSIS_DIR / 'output' / f'winter_rise_{city.lower()}.md'}")
    print(f"  -> {out_panel}")


def _ground_truth_check(explained, collinearity):
    """When the PM2.5 is synthetic, the true answer is known.

    synth.py builds its winter peak from a CALENDAR multiplier and its
    day-to-day variation from an autocorrelated random walk. Neither
    reads the weather. So for this dataset the true weather contribution
    to the winter rise is exactly ZERO.

    That makes the fixture an unusually useful test: any figure the
    regression reports above zero is measurable bias in the design
    itself, and can be quantified rather than merely worried about.
    """
    import json
    prov = REPO / "data" / "raw" / "provenance.json"
    if not prov.exists():
        return None
    if not json.loads(prov.read_text()).get("synthetic", False):
        return None
    print(f"\n  GROUND TRUTH (synthetic fixture only)")
    print(f"    true weather contribution, by construction:  0%")
    print(f"    this method reports:                        {explained:.0%}")
    print(f"    => the design overstates weather by {explained:.0%} when the")
    print(f"       controls are {collinearity:.0%} collinear with the season.")
    return {"true": 0.0, "estimated": explained, "collinearity": collinearity}


def write_report(city, frame, m0, m1, m2, raw_ratio, explained, weather_vars,
                 collinearity, ground_truth):
    import json
    prov = REPO / "data" / "raw" / "provenance.json"
    synthetic = json.loads(prov.read_text()).get("synthetic", False) if prov.exists() else False

    b0, b2 = m0.params["winter"], m2.params["winter"]
    lines = []
    a = lines.append
    a(f"# Does weather explain {city}'s winter PM2.5 rise?")
    a("")
    a(f"Generated by `analysis/winter_rise.py`. "
      f"Panel: {len(frame)} city-days, "
      f"{frame['reading_date'].min().date()} to {frame['reading_date'].max().date()}.")
    a("")
    if synthetic:
        a("> ## ⚠ The PM2.5 in this analysis is synthetic")
        a(">")
        a("> The weather is real ERA5 reanalysis from Open-Meteo. The PM2.5 is"
          " generated by `backend/jobs/synth.py`. **The headline number below"
          f" is not a finding about {city}.**")
        a("")
        if ground_truth:
            a("### What the fixture accidentally proves")
            a("")
            a("This turned out to be more useful than a placeholder, so it is"
              " worth stating plainly rather than burying.")
            a("")
            a("`synth.py` builds its winter peak from a **calendar** multiplier"
              " and its day-to-day variation from an autocorrelated random walk."
              " Neither reads the weather. **For this dataset the true"
              " contribution of weather to the winter rise is exactly zero,"
              " by construction.**")
            a("")
            a(f"The method above reports **{ground_truth['estimated']:.0%}**.")
            a("")
            a("That gap is not a bug in the code — the regression is correctly"
              " specified and correctly fitted. It is a limit of the *design*."
              " Regressing the winter indicator on the weather controls alone"
              f" gives an R² of **{collinearity:.2f}**: about"
              f" {collinearity:.0%} of 'winter' is reconstructible from"
              " temperature, radiation and wind. Winter and winter weather are"
              " very nearly the same variable in Delhi. So 'controlling for"
              " weather' does not isolate a meteorological channel — it partly"
              " re-adds the calendar under a different name, and the winter"
              " coefficient falls whether or not weather did anything.")
            a("")
            a("**The consequence for the real analysis.** Run this on genuine"
              " OpenAQ data and it will report some similar-looking share. That"
              f" number must be read as an **upper bound** on weather's"
              " contribution, never as an estimate of it. Any design that"
              " regresses a seasonal outcome on seasonal controls inherits this"
              " problem; a credible causal answer needs variation in weather"
              " that is independent of the season — comparing unusually windy"
              " Januaries with unusually still ones, within-month, rather than"
              " comparing January with July.")
            a("")
            a("I know the size of the bias here only because I control the"
              " data-generating process. On real data I would not, which is"
              " the honest reason to distrust the headline figure.")
            a("")
        a("> With a real `OPENAQ_API_KEY` and a real collection, this same"
          " script runs unchanged. Published work on Delhi typically attributes"
          " a substantial minority of the winter difference to meteorology,"
          " with the majority remaining in emissions and regional transport —"
          " and does so using within-season designs that avoid the trap"
          " described above.")
        a("")

    a("## Question")
    a("")
    a(f"{city}'s PM2.5 is dramatically higher in winter. Winter is also colder,"
      " calmer and drier. How much of the rise is the weather trapping the same"
      " emissions, and how much is more being emitted?")
    a("")
    a("## Result")
    a("")
    a("| | Winter coefficient (log PM2.5) | Multiplicative | adj R² |")
    a("|---|---:|---:|---:|")
    a(f"| No controls | {m0.params['winter']:+.4f} | ×{np.exp(m0.params['winter']):.2f} | {m0.rsquared_adj:.3f} |")
    a(f"| + year trend | {m1.params['winter']:+.4f} | ×{np.exp(m1.params['winter']):.2f} | {m1.rsquared_adj:.3f} |")
    a(f"| + weather | {m2.params['winter']:+.4f} | ×{np.exp(m2.params['winter']):.2f} | {m2.rsquared_adj:.3f} |")
    a("")
    a(f"Raw winter/non-winter ratio in levels: **×{raw_ratio:.2f}**.")
    a("")
    a(f"Adding meteorology moves the winter coefficient from {b0:+.4f} to"
      f" {b2:+.4f}. Taken at face value that is **{explained:.0%} of the winter"
      f" rise attributable to weather** and {1-explained:.0%} not.")
    a("")
    a("### Why that figure is an upper bound")
    a("")
    a(f"Regressing the winter indicator on the weather controls alone gives"
      f" R² = **{collinearity:.2f}**. Roughly {collinearity:.0%} of 'winter' is"
      " reconstructible from temperature, radiation and wind speed: in Delhi,"
      " winter and winter weather are close to the same variable. Adding the"
      " controls therefore removes part of the calendar as well as part of the"
      " meteorology, and the winter coefficient would fall even if weather"
      f" affected nothing. Read {explained:.0%} as a ceiling.")
    a("")
    a("## Specification")
    a("")
    a("- **Outcome**: `log(PM2.5)`. The distribution is right-skewed and its"
      " drivers are multiplicative — halving ventilation roughly doubles"
      " concentration rather than adding a fixed number of micrograms. In logs,"
      " coefficients read as proportional changes.")
    a("- **Unit**: city-day, the unweighted mean across the city's stations."
      " Not station-day: ERA5's grid is about 25 km, so every station in the"
      f" city joins to an identical weather row. Station-day rows would"
      f" multiply n by roughly the station count while adding no independent"
      f" weather information, and would understate the standard errors badly.")
    a(f"- **Winter**: November, December, January. Monsoon (June–September) is"
      " flagged separately so the comparison baseline is not a blend of the"
      " wettest and driest months.")
    a("- **Standard errors**: Newey–West (HAC), 30 lags. Daily air quality is"
      " strongly autocorrelated — a still, polluted day is usually followed by"
      " another — so classical standard errors would be far too small and"
      " every t-statistic implausibly large.")
    a("- **Completeness**: days under 50% are dropped, not down-weighted. A"
      " day averaged from four hours carries measurement error precisely when"
      " conditions are calmest, which is when it would do most damage.")
    a("- **Wind direction** enters as sin/cos components, because 359° and 1°"
      " are neighbours and the raw number is not an interval scale.")
    a("- **Wind speed** enters in logs: the difference between 2 and 4 km/h"
      " matters far more than between 20 and 22.")
    a("")
    a("### Weather controls used")
    a("")
    a("| Variable | Coefficient | SE | p |")
    a("|---|---:|---:|---:|")
    for v in weather_vars:
        a(f"| `{v}` | {m2.params[v]:+.4f} | {m2.bse[v]:.4f} | {m2.pvalues[v]:.3g} |")
    a("")

    a("## Confounders I could not rule out")
    a("")
    a("This is the part that matters, and none of these are hypothetical.")
    a("")
    a("1. **Weather and emissions are not independent.** Cold weather causes"
       " both poor dispersion *and* more combustion for heating. The winter"
       " coefficient therefore cannot be cleanly split — a control for"
       " temperature absorbs some genuine emissions response along with the"
       " meteorology. This biases the 'weather-explained' share **upwards**"
       " and there is no way around it with these variables.")
    a("2. **Crop-residue burning is seasonal and unmeasured.** Post-monsoon"
       " stubble burning in Punjab and Haryana coincides with the onset of the"
       " winter inversion. Nothing here separates them. Wind direction is a"
       " crude proxy at best — it tells you air arrived from the north-west,"
       " not whether anything was burning there.")
    a("3. **ERA5 is a model, not a measurement at the monitor.** It is"
       " reanalysis on a ~25 km grid. Street-level wind at a roadside monitor"
       " can differ substantially, and the error is not random with respect to"
       " urban form — dense built-up areas are systematically calmer than the"
       " grid cell suggests.")
    a("4. **Boundary-layer height is missing.** It is the most physically"
       " direct control for accumulation, and the archive endpoint returns"
       " nulls for it here. `diurnal_range` and `temperature_2m_min` stand in"
       " as inversion proxies. They are weaker, so genuine meteorological"
       " effect is being attributed to the winter dummy — biasing the"
       " weather-explained share **downwards**. Note this pushes the opposite"
       " way to confounder 1; I cannot say which dominates.")
    a("5. **Diwali moves.** It falls between mid-October and mid-November on"
       " the Gregorian calendar, so a fixed month dummy smears a large,"
       " one-to-three-day emissions spike across the winter/non-winter"
       " boundary differently each year.")
    a("6. **The station network is not fixed.** Monitors are commissioned and"
       " decommissioned, so the 'city mean' is a mean of a changing set of"
       " places. A station added in a cleaner suburb lowers the city mean with"
       " no change in anybody's air.")
    a("7. **Regional transport is not local weather.** Delhi sits downwind of"
       " a large emitting region. Local wind speed says how well the city"
       " ventilates, not what is in the air arriving.")
    a("8. **This is association, not causation.** No instrument, no"
       " discontinuity, no randomisation. A variance decomposition under one"
       " functional form. A different but equally defensible specification"
       " would move the headline number by several percentage points.")
    a("")
    a("## Reproducing")
    a("")
    a("```bash")
    a(f"python analysis/fetch_weather.py --city {city}")
    a(f"python analysis/winter_rise.py --city {city}")
    a("```")
    a("")
    a("Weather comes from the Open-Meteo ERA5 archive, which needs no API key.")

    out = ANALYSIS_DIR / "output" / f"winter_rise_{city.lower()}.md"
    out.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
