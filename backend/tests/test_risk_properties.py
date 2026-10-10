"""A2: rules that must hold for any input (random testing with Hypothesis)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from core.risk import Risk, assess, classify_rain, classify_snow, classify_wind, wind_risk_for_load

wind = st.floats(min_value=0, max_value=120, allow_nan=False)
rate = st.floats(min_value=0, max_value=6, allow_nan=False)
load = st.floats(min_value=0, max_value=80_000, allow_nan=False)


@settings(max_examples=3000)
@given(wind, wind, load)
def test_more_wind_never_lowers_risk(a, b, w):
    lo, hi = sorted((a, b))
    assert wind_risk_for_load(lo, w) <= wind_risk_for_load(hi, w)


@settings(max_examples=3000)
@given(wind, load, load)
def test_heavier_load_never_lowers_risk(mph, a, b):
    lo, hi = sorted((a, b))
    assert wind_risk_for_load(mph, lo) <= wind_risk_for_load(mph, hi)


@settings(max_examples=3000)
@given(wind, load)
def test_load_rules_only_raise(mph, w):
    assert wind_risk_for_load(mph, w) >= classify_wind(mph)


@settings(max_examples=3000)
@given(rate, rate)
def test_more_rain_or_snow_never_lowers_risk(a, b):
    lo, hi = sorted((a, b))
    assert classify_rain(lo) <= classify_rain(hi)
    assert classify_snow(lo) <= classify_snow(hi)


@settings(max_examples=3000)
@given(wind, rate, rate, load)
def test_overall_is_max_of_parts(mph, rain, snow, w):
    a = assess(mph, rain, snow, w)
    assert a.level == max(a.wind, a.rain, a.snow)
    assert a.level >= classify_rain(rain) and a.level >= classify_snow(snow)
    assert isinstance(a.level, Risk)
