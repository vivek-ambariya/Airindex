"""Band table and the completeness gate."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.bands import (BAND_NAMES, MIN_COMPLETENESS_FOR_BAND, SUPPORTED_PARAMETERS,
                       THRESHOLDS, band_index, band_with_reason)

FRONTEND_BANDS = Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "lib" / "bands.js"


def test_every_parameter_has_five_cuts():
    """Five cuts make six bands. A short list would silently collapse
    two categories into one."""
    for param, cuts in THRESHOLDS.items():
        assert len(cuts) == 5, f"{param} has {len(cuts)} cuts, expected 5"
        assert cuts == sorted(cuts), f"{param} cuts are not ascending: {cuts}"
        assert len(set(cuts)) == 5, f"{param} has duplicate cuts: {cuts}"


def test_band_names_are_six():
    assert len(BAND_NAMES) == 6


@pytest.mark.parametrize("param,value,expected", [
    # CPCB PM2.5 24-hour breakpoints, checked on both sides of each edge.
    ("pm25", 0, 0), ("pm25", 30, 0), ("pm25", 30.1, 1),
    ("pm25", 60, 1), ("pm25", 60.1, 2),
    ("pm25", 90, 2), ("pm25", 90.1, 3),
    ("pm25", 120, 3), ("pm25", 120.1, 4),
    ("pm25", 250, 4), ("pm25", 250.1, 5), ("pm25", 9999, 5),
    ("pm10", 50, 0), ("pm10", 430, 4), ("pm10", 431, 5),
    ("co", 1, 0), ("co", 34, 4), ("co", 35, 5),
])
def test_band_index_boundaries(param, value, expected):
    assert band_index(param, value) == expected


def test_unknown_parameter_raises():
    with pytest.raises(ValueError, match="Unknown parameter"):
        band_index("xenon", 10)


class TestCompletenessGate:
    """band_with_reason is what stops the map claiming clean air where
    there is no working instrument."""

    def test_good_data_gets_a_band(self):
        band, reason = band_with_reason("pm25", 25, 100.0, 95.0)
        assert band == "Good" and reason is None

    def test_no_value_has_no_band(self):
        band, reason = band_with_reason("pm25", None, 100.0, 95.0)
        assert band is None and "no readings" in reason

    def test_silent_station_has_no_band(self):
        """The important one. A station that stopped transmitting has a
        complete final day, so a day-only gate would colour it."""
        band, reason = band_with_reason("pm25", 20, day_completeness=100.0,
                                        window_completeness=0.0)
        assert band is None
        assert "stopped reporting" in reason

    def test_sparse_window_has_no_band(self):
        band, reason = band_with_reason("pm25", 20, day_completeness=100.0,
                                        window_completeness=47.0)
        assert band is None
        assert "47%" in reason

    def test_sparse_day_has_no_band(self):
        band, reason = band_with_reason("pm25", 20, day_completeness=12.5,
                                        window_completeness=95.0)
        assert band is None
        assert "12%" in reason or "13%" in reason

    def test_exactly_at_the_floor_is_allowed(self):
        band, _ = band_with_reason("pm25", 20,
                                   day_completeness=MIN_COMPLETENESS_FOR_BAND,
                                   window_completeness=MIN_COMPLETENESS_FOR_BAND)
        assert band == "Good"

    def test_missing_completeness_is_not_checked(self):
        band, reason = band_with_reason("pm25", 500)
        assert band == "Severe" and reason is None


@pytest.mark.skipif(not FRONTEND_BANDS.exists(),
                    reason="frontend bands.js not written yet")
def test_frontend_band_table_matches_backend():
    """The frontend has its own copy so the map works with Flask stopped.
    Two copies of a threshold table is two chances to disagree, so the
    agreement is asserted rather than hoped for."""
    source = FRONTEND_BANDS.read_text()

    match = re.search(r"export const THRESHOLDS\s*=\s*(\{.*?\n\})", source, re.S)
    assert match, "could not find THRESHOLDS in frontend/src/lib/bands.js"
    # JS object literal with unquoted-safe keys -> JSON.
    literal = re.sub(r"//.*", "", match.group(1))
    literal = re.sub(r"(\w+):", r'"\1":', literal)
    literal = re.sub(r",(\s*[}\]])", r"\1", literal)
    frontend = json.loads(literal)

    assert set(frontend) == set(SUPPORTED_PARAMETERS), (
        f"parameter sets differ: frontend={sorted(frontend)} "
        f"backend={sorted(SUPPORTED_PARAMETERS)}")
    for param, cuts in THRESHOLDS.items():
        assert frontend[param] == cuts, (
            f"{param}: frontend {frontend[param]} != backend {cuts}")

    names = re.search(r"export const BAND_NAMES\s*=\s*(\[.*?\])", source, re.S)
    assert names, "could not find BAND_NAMES in frontend bands.js"
    assert json.loads(names.group(1).replace("'", '"')) == BAND_NAMES
