"""Endpoint contracts and validation.

Runs against the configured database, so it needs XAMPP up and
jobs.load to have run. Skips rather than fails when there is no data --
a green suite on an empty database would be a lie either way.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def loaded(client):
    """Skip a test that needs data when the database is empty.

    Function-scoped because `client` is: a module-scoped fixture cannot
    depend on a function-scoped one.
    """
    health = client.get("/api/health").get_json()
    if not health or health.get("n_stations", 0) == 0:
        pytest.skip("No stations loaded. Run jobs.collect/clean/load first.")
    return health


class TestHealth:
    def test_reports_ok_and_proves_geometry(self, client, loaded):
        body = client.get("/api/health").get_json()
        assert body["status"] == "ok"
        assert body["database"] == "ok"
        # The health endpoint carries a known-answer spatial check so a
        # broken geometry path cannot hide until somebody clicks the map.
        assert body["spatial_ok"] is True, (
            f"Delhi-Mumbai came back as {body['delhi_mumbai_km']} km, "
            f"expected ~1148. Axis order or SRID handling has changed.")


class TestStationsList:
    def test_shape(self, client, loaded):
        body = client.get("/api/stations").get_json()
        assert body["count"] == len(body["stations"])
        assert body["unit"] == "ug/m3"
        station = body["stations"][0]
        for key in ("id", "name", "city", "state", "lat", "lon",
                    "latest_value", "latest_date", "completeness_30d",
                    "band", "band_withheld", "silent"):
            assert key in station, f"missing {key}"

    def test_coordinates_are_inside_india(self, client, loaded):
        """A latitude/longitude swap anywhere in the stack would put
        stations in the Arabian desert or the South Atlantic."""
        for s in client.get("/api/stations").get_json()["stations"]:
            assert 6 <= s["lat"] <= 37, f"{s['name']} lat {s['lat']} outside India"
            assert 68 <= s["lon"] <= 98, f"{s['name']} lon {s['lon']} outside India"

    def test_band_is_withheld_exactly_when_reason_given(self, client, loaded):
        for s in client.get("/api/stations").get_json()["stations"]:
            assert (s["band"] is None) == (s["band_withheld"] is not None), (
                f"{s['name']}: band={s['band']} withheld={s['band_withheld']}")

    def test_silent_station_never_carries_a_band(self, client, loaded):
        for s in client.get("/api/stations").get_json()["stations"]:
            if s["silent"]:
                assert s["band"] is None, (
                    f"{s['name']} has stopped reporting but shows "
                    f"band={s['band']} -- the map would draw clean air where "
                    f"there is no instrument")

    def test_rejects_unknown_parameter(self, client):
        resp = client.get("/api/stations?parameter=xenon")
        assert resp.status_code == 400
        assert resp.get_json()["field"] == "parameter"


class TestNearest:
    def test_finds_a_station_and_the_distance_is_sane(self, client, loaded):
        # Connaught Place, Delhi. Several stations within a few km.
        body = client.get("/api/stations/nearest?lat=28.6139&lon=77.2090").get_json()
        station = body["station"]
        assert station["city"] == "Delhi"
        assert 0 < station["distance_km"] < 15, station["distance_km"]

    def test_refuses_beyond_max_km_with_a_reason(self, client, loaded):
        """Phase 3's acceptance check. Middle of the Bay of Bengal."""
        resp = client.get("/api/stations/nearest?lat=15.0&lon=88.0&max_km=50")
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["error"] == "no_station_in_range"
        # The message has to distinguish a network gap from clean air.
        assert "not a reading of clean air" in body["message"]

    def test_widening_the_radius_finds_what_a_narrow_one_missed(self, client, loaded):
        """Guards the bounding-box maths: a fixed 0.5-degree box would
        clip candidates well before 200 km."""
        near = client.get("/api/stations/nearest?lat=15.0&lon=88.0&max_km=50")
        far = client.get("/api/stations/nearest?lat=15.0&lon=88.0&max_km=200")
        assert near.status_code == 404
        if far.status_code == 200:
            assert far.get_json()["station"]["distance_km"] > 50

    @pytest.mark.parametrize("query,field", [
        ("", "lat"),
        ("lat=28.6", "lon"),
        ("lon=77.2", "lat"),
        ("lat=abc&lon=77.2", "lat"),
        ("lat=28.6&lon=xyz", "lon"),
        ("lat=&lon=77.2", "lat"),
        ("lat=91&lon=77.2", "lat"),
        ("lat=28.6&lon=181", "lon"),
        ("lat=nan&lon=77.2", "lat"),
        ("lat=inf&lon=77.2", "lat"),
    ])
    def test_rejects_bad_coordinates_with_400(self, client, query, field):
        resp = client.get(f"/api/stations/nearest?{query}")
        assert resp.status_code == 400, f"?{query} should be a 400"
        assert resp.get_json()["field"] == field

    def test_rejects_absurd_radius(self, client):
        assert client.get(
            "/api/stations/nearest?lat=28.6&lon=77.2&max_km=99999"
        ).status_code == 400


class TestSeries:
    def test_parallel_arrays_are_equal_length_and_dense(self, client, loaded):
        body = client.get("/api/stations/1/series"
                          "?from=2026-01-01&to=2026-01-31").get_json()
        assert body["n_days"] == 31
        # The contract is { start, values[] } -- parallel arrays walked
        # over the calendar, so a gap is a null at a known index.
        assert len(body["values"]) == 31
        assert len(body["completeness"]) == 31
        assert len(body["n_hours"]) == 31
        assert body["start"] == "2026-01-01"
        assert body["step"] == "P1D"

    def test_gaps_are_null_not_absent(self, client, loaded):
        body = client.get("/api/stations/1/series"
                          "?from=2015-01-01&to=2015-01-10").get_json()
        # Long before the dataset starts: every day present as a null.
        assert body["values"] == [None] * 10
        assert body["n_present"] == 0

    def test_unknown_station_404s(self, client, loaded):
        assert client.get("/api/stations/999999/series").status_code == 404

    def test_rejects_reversed_range(self, client, loaded):
        resp = client.get("/api/stations/1/series?from=2026-08-01&to=2026-01-01")
        assert resp.status_code == 400
        assert "after" in resp.get_json()["message"]

    def test_caps_the_range(self, client, loaded):
        resp = client.get("/api/stations/1/series?from=1990-01-01&to=2026-08-31")
        assert resp.status_code == 400


class TestMonthly:
    def test_always_twelve_months(self, client, loaded):
        body = client.get("/api/stations/1/monthly").get_json()
        assert len(body["months"]) == 12
        assert [m["month"] for m in body["months"]] == list(range(1, 13))

    def test_northern_station_peaks_in_winter(self, client, loaded):
        """Sanity check on the seasonal profile: the Indo-Gangetic winter
        inversion means Nov-Jan must exceed the monsoon months."""
        body = client.get("/api/stations/1/monthly").get_json()
        values = {m["month"]: m["value"] for m in body["months"] if m["value"]}
        if len(values) < 12:
            pytest.skip("station does not have all twelve months")
        winter = max(values[11], values[12], values[1])
        monsoon = min(values[7], values[8])
        assert winter > monsoon * 1.5, (
            f"winter peak {winter} vs monsoon {monsoon} -- seasonality is absent")


class TestCompare:
    def test_shared_date_axis_across_cities(self, client, loaded):
        body = client.get("/api/compare?cities=Delhi,Mumbai"
                          "&from=2026-01-01&to=2026-03-31").get_json()
        assert body["n_days"] == 90
        assert len(body["cities"]) == 2
        for city in body["cities"]:
            assert len(city["values"]) == 90, "cities are not on one axis"

    def test_unknown_city_does_not_fail_the_others(self, client, loaded):
        body = client.get("/api/compare?cities=Delhi,Nowhereville").get_json()
        found = {c["city"]: c["found"] for c in body["cities"]}
        assert found["Delhi"] is True
        assert found["Nowhereville"] is False

    def test_duplicate_cities_are_collapsed(self, client, loaded):
        resp = client.get("/api/compare?cities=Delhi,Delhi,Mumbai")
        assert resp.status_code == 200
        assert [c["city"] for c in resp.get_json()["cities"]] == ["Delhi", "Mumbai"]

    def test_duplicates_can_drop_below_the_minimum(self, client):
        resp = client.get("/api/compare?cities=Delhi,Delhi")
        assert resp.status_code == 400

    @pytest.mark.parametrize("query", [
        "cities=Delhi",
        "cities=",
        "cities=A,B,C,D,E,F",
        "cities=Delhi,Mumbai&from=1990-01-01&to=2026-08-31",
        "cities=Delhi,Mumbai&from=notadate",
    ])
    def test_rejects_bad_input(self, client, query):
        assert client.get(f"/api/compare?{query}").status_code == 400


class TestCORS:
    def test_allows_only_the_vite_origin(self, client, loaded):
        allowed = client.get("/api/stations",
                             headers={"Origin": "http://localhost:5173"})
        assert allowed.headers.get("Access-Control-Allow-Origin") == \
            "http://localhost:5173"

    def test_does_not_allow_another_origin(self, client, loaded):
        other = client.get("/api/stations",
                           headers={"Origin": "http://evil.example.com"})
        assert other.headers.get("Access-Control-Allow-Origin") != \
            "http://evil.example.com"
        assert other.headers.get("Access-Control-Allow-Origin") != "*"


class TestErrorsAreJSON:
    def test_404_is_json_not_html(self, client):
        resp = client.get("/api/nope")
        assert resp.status_code == 404
        assert resp.is_json, "an HTML error page turns a clear 404 into a " \
                             "parse failure in the browser"
        assert resp.get_json()["error"] == "not_found"

    def test_405_is_json(self, client):
        resp = client.post("/api/stations")
        assert resp.status_code == 405
        assert resp.is_json
