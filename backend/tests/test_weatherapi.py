"""WeatherAPI.com source: parsing, bulk fallback, and the source chain."""

from datetime import UTC, date, datetime, timedelta

import pytest

from core.errors import UpstreamError
from core.forecast import HourlySeries
from providers import weather

START = date(2026, 10, 11)
T0 = datetime(2026, 10, 11, tzinfo=UTC)


def wa_query(hours=3, precip=0.2, snow_cm=0.0, wind=12.0):
    return {
        "location": {},
        "forecast": {
            "forecastday": [
                {
                    "hour": [
                        {
                            "time_epoch": int((T0 + timedelta(hours=i)).timestamp()),
                            "wind_mph": wind + i,
                            "gust_mph": wind + 10,
                            "precip_in": precip,
                            "snow_cm": snow_cm,
                        }
                        for i in range(hours)
                    ]
                }
            ]
        },
    }


def test_series_aligned_to_utc_hours_with_mph_and_inches():
    s = weather._weatherapi_series(wa_query(), START, 48)
    assert s.start == T0 and len(s) == 48
    assert s.wind_mph[:3] == [12.0, 13.0, 14.0] and s.wind_mph[3] is None
    assert s.rain_in[0] == 0.2 and s.snow_in[0] == 0.0


def test_rain_excludes_the_water_in_snow():
    # 2.54 cm of snow = 1 in; its water (1/10 in) is taken out of total precipitation.
    s = weather._weatherapi_series(wa_query(precip=0.15, snow_cm=2.54), START, 24)
    assert s.snow_in[0] == 1.0
    assert s.rain_in[0] == pytest.approx(0.05)


def test_error_or_empty_location_is_no_data():
    assert weather._weatherapi_series({"error": {"code": 1006}}, START, 24) is None
    assert weather._weatherapi_series({"forecast": {"forecastday": []}}, START, 24) is None


class Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


def test_bulk_unavailable_falls_back_to_single_requests(monkeypatch, settings):
    settings.WEATHERAPI_KEY = "k"
    monkeypatch.setattr(weather, "_bulk_supported", True)
    calls = []

    def fake(method, url, **kw):
        calls.append(kw["params"]["q"])
        if kw["params"]["q"] == "bulk":
            return Resp(400, {"error": {"code": 2009, "message": "no bulk on this plan"}})
        return Resp(200, wa_query())

    monkeypatch.setattr(weather, "request", fake)
    out = weather._fetch_weatherapi([(40.0, -100.0), (41.0, -101.0)], START, START)
    assert all(isinstance(s, HourlySeries) for s in out)
    assert calls[0] == "bulk" and len(calls) == 3 and weather._bulk_supported is False


def test_rejected_key_raises_so_the_chain_moves_on(monkeypatch, settings):
    settings.WEATHERAPI_KEY = "bad"
    monkeypatch.setattr(weather, "_bulk_supported", False)
    monkeypatch.setattr(weather, "request", lambda *a, **k: Resp(401, {"error": {"code": 2006}}))
    with pytest.raises(UpstreamError):
        weather._fetch_weatherapi([(40.0, -100.0)], START, START)


def test_chain_skips_a_failing_source_and_reports_what_was_used(monkeypatch, settings):
    settings.WEATHER_MODELS = "weatherapi,ncep_nbm_conus"

    def fake(points, s, e, model):
        if model == "weatherapi":
            raise UpstreamError("WEATHER_RATE_LIMITED", "busy")
        return {p: HourlySeries(T0, [5.0] * 48, [9.0] * 48, [0.0] * 48, [0.0] * 48) for p in points}

    monkeypatch.setattr(weather, "_fetch_model", fake)
    series, used = weather.fetch_hourly([(40.0, -100.0)], T0, T0 + timedelta(hours=3), with_sources=True)
    assert used == ["ncep_nbm_conus"] and series[0].wind_mph[0] == 5.0


def test_gaps_outside_the_trip_hours_do_not_trigger_the_next_source(monkeypatch, settings):
    settings.WEATHER_MODELS = "weatherapi,ncep_nbm_conus"
    asked = []

    def fake(points, s, e, model):
        asked.append(model)
        # Data for the first 10 hours only, like a short forecast horizon.
        wind = [5.0] * 10 + [None] * 38
        return {p: HourlySeries(T0, wind, wind, wind, wind) for p in points}

    monkeypatch.setattr(weather, "_fetch_model", fake)
    weather.fetch_hourly([(40.0, -100.0)], T0 + timedelta(hours=1), T0 + timedelta(hours=5))
    assert asked == ["weatherapi"]


def test_all_sources_failing_reports_the_upstream_error(monkeypatch, settings):
    settings.WEATHER_MODELS = "weatherapi,ncep_nbm_conus"

    def fail(points, s, e, model):
        raise UpstreamError("WEATHER_UNAVAILABLE", "down")

    monkeypatch.setattr(weather, "_fetch_model", fail)
    with pytest.raises(UpstreamError) as e:
        weather.fetch_hourly([(40.0, -100.0)], T0, T0)
    assert e.value.code == "WEATHER_UNAVAILABLE"
