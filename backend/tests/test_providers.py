"""Parsing of provider responses, including the unit guard and TomTom progress anchors."""

from datetime import UTC, date

import pytest

from core.errors import UpstreamError
from providers.routing import OsrmRouter, TomTomRouter
from providers.weather import _to_series


def om_block(**unit_overrides):
    units = {
        "time": "iso8601",
        "wind_speed_10m": "mp/h",
        "wind_gusts_10m": "mp/h",
        "rain": "inch",
        "showers": "inch",
        "snowfall": "inch",
    }
    units.update(unit_overrides)
    return {
        "hourly_units": units,
        "hourly": {
            "time": ["2026-10-11T00:00", "2026-10-11T01:00"],
            "wind_speed_10m": [7.9, 30.2],
            "wind_gusts_10m": [15.7, 41.0],
            "rain": [0.01, 0.2],
            "showers": [0.02, 0.1],
            "snowfall": [0.0, 0.0],
        },
    }


def test_open_meteo_rain_includes_showers():
    s = _to_series(om_block(), date(2026, 10, 11))
    assert s.rain_in == [0.03, 0.3]
    assert s.wind_mph == [7.9, 30.2]
    assert s.start.isoformat() == "2026-10-11T00:00:00+00:00"


@pytest.mark.parametrize("override", [{"wind_speed_10m": "km/h"}, {"rain": "mm"}, {"snowfall": "cm"}])
def test_open_meteo_wrong_units_are_rejected(override):
    with pytest.raises(UpstreamError) as e:
        _to_series(om_block(**override), date(2026, 10, 11))
    assert e.value.code == "WEATHER_BAD_DATA"


def test_open_meteo_wrong_start_hour_is_rejected():
    with pytest.raises(UpstreamError):
        _to_series(om_block(), date(2026, 10, 12))


def test_tomtom_progress_anchors_and_leg_join():
    route = {
        "summary": {"lengthInMeters": 3000, "travelTimeInSeconds": 200, "trafficDelayInSeconds": 30},
        "legs": [
            {"points": [{"latitude": 0.0, "longitude": 0.0}, {"latitude": 0.0, "longitude": 0.01}]},
            # Second leg starts at the joining point; it must not be duplicated.
            {"points": [{"latitude": 0.0, "longitude": 0.01}, {"latitude": 0.0, "longitude": 0.02}]},
        ],
        "progress": [
            {"pointIndex": 0, "distanceInMeters": 0, "travelTimeInSeconds": 0},
            {"pointIndex": 1, "distanceInMeters": 1200, "travelTimeInSeconds": 120},
        ],
    }
    r = TomTomRouter._parse(route)
    assert r.line.lats == [0.0, 0.0, 0.0]
    assert r.line.cum_m == pytest.approx([0, 1200, 3000])
    assert r.line.cum_s == pytest.approx([0, 120, 200])
    assert r.traffic_delay_s == 30


def test_osrm_annotations_build_cumulative_values():
    route = {
        "distance": 300.0,
        "duration": 30.0,
        "geometry": {"coordinates": [[0, 0], [0.001, 0], [0.002, 0]]},
        "legs": [{"annotation": {"distance": [100.0, 200.0], "duration": [10.0, 20.0]}}],
    }
    r = OsrmRouter._parse(route)
    assert r.line.cum_m == [0, 100, 300]
    assert r.line.cum_s == [0, 10, 30]


def test_backup_model_fills_only_missing_hours(monkeypatch, settings):
    from datetime import datetime

    from core.forecast import HourlySeries
    from providers import weather

    settings.WEATHER_MODELS = "primary,backup"
    start = datetime(2026, 10, 11, tzinfo=UTC)

    def fake(points, s, e, model):
        val = 5.0 if model == "primary" else 9.0
        out = {}
        for p in points:
            wind = [val, None, val] if model == "primary" else [val] * 3
            out[p] = HourlySeries(start, wind, [val] * 3, [0.0] * 3, [0.0] * 3)
        return out

    monkeypatch.setattr(weather, "_fetch_model", fake)
    (s,) = weather.fetch_hourly([(40.0, -100.0)], start, start)
    assert s.wind_mph == [5.0, 9.0, 5.0]


def test_point_outside_primary_model_uses_backup(monkeypatch, settings):
    """NBM returns an empty block outside the lower 48; the backup model must take over."""
    from datetime import datetime

    from core.forecast import HourlySeries
    from providers import weather

    settings.WEATHER_MODELS = "primary,backup"
    start = datetime(2026, 10, 11, tzinfo=UTC)

    def fake(points, s, e, model):
        if model == "primary":
            return {p: None for p in points}
        return {p: HourlySeries(start, [7.0] * 3, [9.0] * 3, [0.0] * 3, [0.0] * 3) for p in points}

    monkeypatch.setattr(weather, "_fetch_model", fake)
    (s,) = weather.fetch_hourly([(19.43, -99.13)], start, start)
    assert s.wind_mph == [7.0, 7.0, 7.0]


def test_empty_open_meteo_block_means_no_data():
    from datetime import date

    from providers.weather import _to_series

    assert _to_series({"latitude": None}, date(2026, 10, 11)) is None


def test_no_model_covers_point_gives_clear_error(monkeypatch, settings):
    from datetime import datetime

    from core.errors import AppError
    from providers import weather

    settings.WEATHER_MODELS = "primary,backup"
    monkeypatch.setattr(weather, "_fetch_model", lambda points, s, e, m: {p: None for p in points})
    start = datetime(2026, 10, 11, tzinfo=UTC)
    with pytest.raises(AppError) as e:
        weather.fetch_hourly([(0.0, 0.0)], start, start)
    assert e.value.code == "NO_WEATHER_COVERAGE"


class FakeResp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text

    def json(self):
        import json

        return json.loads(self.text)


def test_parse_json_turns_stray_nan_into_missing_values():
    from providers.weather import _parse_json

    assert _parse_json('{"latitude":nan,"v":[1.0,-nan,NaN,inf]}') == {"latitude": None, "v": [1.0, None, None, None]}
    assert _parse_json("<html>busy</html>") is None


def test_lone_point_without_data_is_a_gap_not_an_error(monkeypatch):
    from datetime import date

    from providers import weather

    monkeypatch.setattr(
        weather,
        "request",
        lambda *a, **k: FakeResp(400, '{"error":true,"reason":"No data is available for this location"}'),
    )
    assert weather._fetch_chunk([(19.43, -99.13)], date(2026, 10, 11), date(2026, 10, 12), "ncep_nbm_conus") == [None]


def test_unreadable_body_is_retried_then_reported_cleanly(monkeypatch):
    from datetime import date

    from providers import weather

    calls = []

    def fake(*a, **k):
        calls.append(1)
        return FakeResp(200, "<html>oops</html>")

    monkeypatch.setattr(weather, "request", fake)
    with pytest.raises(UpstreamError) as e:
        weather._fetch_chunk([(40.0, -100.0)], date(2026, 10, 11), date(2026, 10, 12), "best_match")
    assert e.value.code == "WEATHER_BAD_DATA" and len(calls) == 2
