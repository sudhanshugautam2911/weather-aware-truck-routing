"""A4: checkpoint placement, ETA interpolation and mileage bookkeeping."""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.geo import METERS_PER_MILE, RouteLine, fill_between_anchors, haversine_m, place_checkpoints, simplify


def straight_line(miles=100.0, mph=50.0, n=200):
    """A route due north along a meridian at constant speed."""
    total_m = miles * METERS_PER_MILE
    deg = total_m / 111_195.0
    lats = [40 + deg * i / (n - 1) for i in range(n)]
    lons = [-100.0] * n
    cum_m = [total_m * i / (n - 1) for i in range(n)]
    cum_s = [m / (mph * METERS_PER_MILE / 3600) for m in cum_m]
    return RouteLine(lats, lons, cum_m, cum_s)


def test_haversine_known_distance():
    # One degree of latitude is ~111.2 km on the mean sphere.
    assert abs(haversine_m(0, 0, 1, 0) - 111_195) < 5


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_spacing_and_endpoints(interval):
    line = straight_line(miles=123.0)
    spots = place_checkpoints(line, interval * METERS_PER_MILE)
    assert spots[0].distance_m == 0
    assert spots[-1].distance_m == pytest.approx(line.length_m)
    gaps = [b.distance_m - a.distance_m for a, b in zip(spots, spots[1:])]
    assert all(g == pytest.approx(interval * METERS_PER_MILE) for g in gaps[:-1])
    assert 0 < gaps[-1] <= interval * METERS_PER_MILE + 1e-6


@settings(max_examples=300, deadline=None)
@given(
    miles=st.floats(min_value=1.5, max_value=2500),
    interval=st.sampled_from([10, 25, 50]),
)
def test_owned_miles_add_up_exactly(miles, interval):
    line = straight_line(miles=miles, n=50)
    spots = place_checkpoints(line, interval * METERS_PER_MILE)
    assert sum(s.owned_m for s in spots) == pytest.approx(line.length_m, rel=1e-9)
    assert all(s.owned_m >= 0 for s in spots)


def test_short_route_still_has_start_and_end():
    line = straight_line(miles=5)
    spots = place_checkpoints(line, 25 * METERS_PER_MILE)
    assert [round(s.distance_m / METERS_PER_MILE, 3) for s in spots] == [0, 5]


def test_eta_at_checkpoint_matches_constant_speed():
    line = straight_line(miles=200, mph=50)
    spots = place_checkpoints(line, 25 * METERS_PER_MILE)
    for s in spots:
        assert s.offset_s == pytest.approx(s.distance_m / METERS_PER_MILE / 50 * 3600, rel=1e-9)


def test_checkpoints_lie_on_the_line():
    line = straight_line(miles=80)
    for s in place_checkpoints(line, 10 * METERS_PER_MILE):
        assert s.lon == pytest.approx(-100.0)
        assert haversine_m(40, -100, s.lat, s.lon) == pytest.approx(s.distance_m, rel=2e-3)


def test_fill_between_anchors_reproduces_provider_values():
    lats = [0.0, 0.0, 0.0, 0.0, 0.0]
    lons = [0.0, 0.01, 0.02, 0.03, 0.05]
    cum_m, cum_s = fill_between_anchors(lats, lons, [(0, 0, 0), (2, 2_500, 100), (4, 6_000, 400)])
    assert cum_m[0] == 0 and cum_m[2] == pytest.approx(2_500) and cum_m[4] == pytest.approx(6_000)
    assert cum_s[2] == pytest.approx(100) and cum_s[4] == pytest.approx(400)
    # Between anchors, distance is spread by geometry: point 3 is 1/3 of the way from 2 to 4.
    assert cum_m[3] == pytest.approx(2_500 + 3_500 / 3, rel=1e-6)
    assert all(b >= a for a, b in zip(cum_m, cum_m[1:]))


def test_simplify_keeps_corners_and_ends():
    lats = [0, 0, 0, 0.5, 1.0]
    lons = [0, 0.5, 1.0, 1.0, 1.0]
    assert simplify(lats, lons, 10) == [0, 2, 4]


def test_route_line_rejects_bad_shapes():
    with pytest.raises(ValueError):
        RouteLine([0], [0], [0], [0])
