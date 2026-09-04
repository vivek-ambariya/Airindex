"""CPCB air quality bands.

The National Air Quality Index sub-index breakpoints published by the
Central Pollution Control Board, for the 24-hour averaging period. These
are concentration bands, NOT the 0-500 AQI number -- this project reports
concentrations in their measured units and colours them by band, because
converting to an index and back loses the quantity people can check
against a standard.

The frontend has the same table in src/lib/bands.js. They must agree; the
values are asserted identical by tests/test_bands.py.
"""
from __future__ import annotations

# Upper bound (inclusive) of bands 0..4. Anything above the last entry is
# band 5. Units: ug/m3, except CO which is mg/m3.
THRESHOLDS: dict[str, list[float]] = {
    "pm25": [30, 60, 90, 120, 250],
    "pm10": [50, 100, 250, 350, 430],
    "no2": [40, 80, 180, 280, 400],
    "so2": [40, 80, 380, 800, 1600],
    "o3": [50, 100, 168, 208, 748],
    "co": [1, 2, 10, 17, 34],
}

BAND_NAMES = ["Good", "Satisfactory", "Moderate", "Poor", "Very poor", "Severe"]

UNITS: dict[str, str] = {
    "pm25": "ug/m3",
    "pm10": "ug/m3",
    "no2": "ug/m3",
    "so2": "ug/m3",
    "o3": "ug/m3",
    "co": "mg/m3",
}

SUPPORTED_PARAMETERS = tuple(THRESHOLDS)

# Below this, a daily value is shown grey and given no band. A colour
# implies a claim about the day that 12 hours of data cannot support.
MIN_COMPLETENESS_FOR_BAND = 50.0


def band_index(parameter: str, value: float) -> int:
    """0..5, or raises for an unknown parameter."""
    try:
        cuts = THRESHOLDS[parameter]
    except KeyError:
        raise ValueError(f"Unknown parameter: {parameter}") from None
    for i, cut in enumerate(cuts):
        if value <= cut:
            return i
    return 5


def band_name(parameter: str, value: float, completeness: float | None = None) -> str | None:
    """The band label, or None when completeness is too low to assign one."""
    if completeness is not None and completeness < MIN_COMPLETENESS_FOR_BAND:
        return None
    return BAND_NAMES[band_index(parameter, value)]


def band_with_reason(
    parameter: str,
    value: float | None,
    day_completeness: float | None = None,
    window_completeness: float | None = None,
) -> tuple[str | None, str | None]:
    """(band, reason_it_was_withheld). Exactly one of the two is None.

    A colour on a map is a claim about the air. There are three separate
    ways that claim can be unsupportable, and all three have to be
    checked or the map lies in a way nobody notices:

      1. No reading at all for this parameter.
      2. The station has barely reported over the window -- so the one
         value we have is not representative of anything. A station that
         stopped transmitting six weeks ago still has a "latest" value,
         and rendering it green means the map shows clean air where it
         actually has no instrument. This is the failure mode the whole
         completeness column exists to prevent.
      3. The latest day itself is too sparse -- a mean of three hours is
         not a measurement of a day.

    Callers pass whichever completeness figures they have; a None is
    simply not checked.
    """
    if value is None:
        return None, "no readings for this parameter"
    if window_completeness is not None and window_completeness < MIN_COMPLETENESS_FOR_BAND:
        if window_completeness == 0:
            return None, "station has stopped reporting"
        return None, (f"station reported only {window_completeness:.0f}% of the "
                      f"window, under the {MIN_COMPLETENESS_FOR_BAND:.0f}% floor")
    if day_completeness is not None and day_completeness < MIN_COMPLETENESS_FOR_BAND:
        return None, (f"latest day is {day_completeness:.0f}% complete, under the "
                      f"{MIN_COMPLETENESS_FOR_BAND:.0f}% floor")
    return BAND_NAMES[band_index(parameter, value)], None
