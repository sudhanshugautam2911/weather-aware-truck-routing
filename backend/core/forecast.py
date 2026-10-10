"""Matching a truck's ETA to the right forecast hour.

Open-Meteo hourly data (times in UTC):
- wind / gusts at time T are the value *at* T (an instant), so we use the hour
  nearest the ETA;
- rain / showers / snowfall at time T are the total of the *preceding* hour
  (T-1h .. T), i.e. already a per-hour rate. A truck at the checkpoint at 13:40
  is inside the 13:00-14:00 window, which is stored at 14:00.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

HOUR = timedelta(hours=1)


class ForecastRangeError(Exception):
    """The ETA falls outside the hours we have forecast data for."""


class MissingWeatherError(Exception):
    """The provider returned an empty value for a needed hour."""


@dataclass(frozen=True)
class HourlySeries:
    start: datetime  # UTC time of index 0, on the hour
    wind_mph: list[float | None]
    gust_mph: list[float | None]
    rain_in: list[float | None]  # rain + showers (liquid), inches per hour
    snow_in: list[float | None]  # snowfall depth, inches per hour

    def __len__(self) -> int:
        return len(self.wind_mph)


@dataclass(frozen=True)
class WeatherSample:
    wind_mph: float
    gust_mph: float | None
    rain_in_hr: float
    snow_in_hr: float
    wind_hour: datetime
    precip_hour_end: datetime


def floor_hour(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("datetimes must be timezone-aware")
    dt = dt.astimezone(UTC)
    return dt.replace(minute=0, second=0, microsecond=0)


def _value(arr: list[float | None], i: int, what: str) -> float:
    v = arr[i]
    if v is None or (isinstance(v, float) and math.isnan(v)):
        raise MissingWeatherError(f"no {what} value for hour index {i}")
    return float(v)


def sample_at(series: HourlySeries, eta: datetime) -> WeatherSample:
    eta = eta.astimezone(UTC)
    hours = (eta - series.start) / HOUR
    wind_i = int(math.floor(hours + 0.5))
    precip_i = int(math.floor(hours)) + 1
    if hours < 0 or wind_i >= len(series) or precip_i >= len(series):
        raise ForecastRangeError(f"ETA {eta.isoformat()} is outside the forecast window")
    gust = series.gust_mph[wind_i]
    return WeatherSample(
        wind_mph=_value(series.wind_mph, wind_i, "wind"),
        gust_mph=None if gust is None else float(gust),
        rain_in_hr=_value(series.rain_in, precip_i, "rain"),
        snow_in_hr=_value(series.snow_in, precip_i, "snow"),
        wind_hour=series.start + wind_i * HOUR,
        precip_hour_end=series.start + precip_i * HOUR,
    )
