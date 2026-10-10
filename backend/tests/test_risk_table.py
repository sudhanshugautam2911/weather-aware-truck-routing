"""A1: every cell and every boundary of the brief's risk table and load rules."""

import math

import pytest

from core.risk import Risk, assess, classify_rain, classify_snow, classify_wind, wind_risk_for_load

L, M, H, S, N = Risk.LOW, Risk.MODERATE, Risk.HIGH, Risk.SEVERE, Risk.NO_TRAVEL


@pytest.mark.parametrize(
    "mph, expected",
    [
        (0, L),
        (24.9, L),
        (25, M),
        (30, M),
        (34.9, M),
        (35, H),
        (40, H),
        (44.9, H),
        (45, S),
        (50, S),
        (54.9, S),
        (55, N),
        (80, N),
    ],
)
def test_wind_table(mph, expected):
    assert classify_wind(mph) == expected


@pytest.mark.parametrize(
    "rate, expected",
    [
        (0, L),
        (0.09, L),
        (0.10, M),
        (0.2, M),
        (0.249, M),
        (0.25, H),
        (0.4, H),
        (0.499, H),
        (0.50, S),
        (0.75, S),
        (1.00, S),
        (1.001, N),
        (2.0, N),
    ],
)
def test_rain_table(rate, expected):
    assert classify_rain(rate) == expected


@pytest.mark.parametrize(
    "rate, expected",
    [
        (0, L),
        (0.49, L),
        (0.5, M),
        (0.99, M),
        (1.0, H),
        (1.99, H),
        (2.0, S),
        (3.0, S),
        (3.01, N),
        (5, N),
    ],
)
def test_snow_table(rate, expected):
    assert classify_snow(rate) == expected


@pytest.mark.parametrize(
    "mph, load, expected",
    [
        # >= 55 mph is No Travel for any load, including empty.
        (55, 0, N),
        (60, 80_000, N),
        # 45-54 mph: > 30,000 lb -> No Travel; exactly 30,000 stays Severe.
        (45, 30_000, S),
        (45, 30_001, N),
        (54.9, 30_001, N),
        (50, 10_000, S),
        # 35-44 mph: > 40,000 lb -> Severe; exactly 40,000 stays High.
        (35, 40_000, H),
        (35, 40_001, S),
        (44.9, 45_000, S),
        (40, 30_001, H),
        # Below 35 mph the load never matters.
        (34.9, 80_000, M),
        (10, 80_000, L),
    ],
)
def test_load_rules(mph, load, expected):
    assert wind_risk_for_load(mph, load) == expected


def test_overall_is_worst_condition():
    a = assess(wind_mph=30, rain_in_hr=0.3, snow_in_hr=0.0, load_lb=0)
    assert (a.level, a.wind, a.rain, a.snow) == (H, M, H, L)
    assert a.causes == ("rain",)


def test_brief_example_heavy_load_in_strong_wind():
    a = assess(wind_mph=47, rain_in_hr=0.05, snow_in_hr=0, load_lb=35_000)
    assert a.level == N and a.load_raised and a.causes == ("wind",)


def test_ties_list_every_cause():
    a = assess(wind_mph=36, rain_in_hr=0.3, snow_in_hr=1.5, load_lb=0)
    assert a.level == H and a.causes == ("wind", "rain", "snow")


def test_low_has_no_causes():
    assert assess(5, 0, 0, 20_000).causes == ()


@pytest.mark.parametrize("bad", [-1, math.nan, math.inf, None, "10", True])
def test_rejects_bad_numbers(bad):
    with pytest.raises(ValueError):
        classify_wind(bad)


def test_labels_and_keys():
    assert [r.label for r in Risk] == ["Low", "Moderate", "High", "Severe", "No Travel"]
    assert Risk.NO_TRAVEL.key == "no_travel"


def test_negative_segment_miles_rejected():
    from core.risk import summarize

    with pytest.raises(ValueError):
        summarize("A", [(-1, L)], 0)


def test_empty_route_has_zero_average():
    from core.risk import summarize

    assert summarize("A", [], 0).avg_risk == 0.0
