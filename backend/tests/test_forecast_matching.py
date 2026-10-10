"""ETA -> forecast hour matching (precipitation is stored at the END of its hour)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from core.forecast import ForecastRangeError, HourlySeries, MissingWeatherError, sample_at

START = datetime(2026, 10, 11, tzinfo=UTC)


def series(n=6):
    return HourlySeries(
        start=START,
        wind_mph=[float(10 * i) for i in range(n)],  # value at hour i = 10*i
        gust_mph=[float(10 * i + 5) for i in range(n)],
        rain_in=[float(i) / 100 for i in range(n)],  # value stored at hour i = i/100
        snow_in=[0.0] * n,
    )


def test_13_40_uses_wind_at_14_and_precip_window_ending_14():
    s = series()
    w = sample_at(s, START + timedelta(hours=1, minutes=40))
    assert w.wind_mph == 20.0  # nearest hour (02:00)
    assert w.rain_in_hr == 0.02  # window 01:00-02:00 is stored at 02:00
    assert w.precip_hour_end == START + timedelta(hours=2)


def test_13_10_uses_wind_at_13_and_precip_window_ending_14():
    w = sample_at(series(), START + timedelta(hours=1, minutes=10))
    assert w.wind_mph == 10.0
    assert w.rain_in_hr == 0.02


def test_exactly_on_the_hour_uses_the_hour_ahead_for_precip():
    w = sample_at(series(), START + timedelta(hours=3))
    assert w.wind_mph == 30.0 and w.rain_in_hr == 0.04


def test_timezone_aware_inputs_are_converted_to_utc():
    ist = timezone(timedelta(hours=5, minutes=30))
    eta = (START + timedelta(hours=2)).astimezone(ist)
    assert sample_at(series(), eta).wind_mph == 20.0


def test_outside_window_raises():
    with pytest.raises(ForecastRangeError):
        sample_at(series(), START - timedelta(minutes=1))
    with pytest.raises(ForecastRangeError):
        sample_at(series(n=3), START + timedelta(hours=2, minutes=1))


def test_missing_value_raises():
    s = series()
    s.rain_in[2] = None
    with pytest.raises(MissingWeatherError):
        sample_at(s, START + timedelta(hours=1, minutes=30))
