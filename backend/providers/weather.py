"""Hourly weather at many points, from a chain of sources.

Sources are tried in order (WEATHER_MODELS). Each later source only fills the
points and hours the earlier ones could not provide, and a source that fails
entirely is skipped. Default chain: WeatherAPI.com (fast, no per-minute limit)
-> Open-Meteo NBM -> Open-Meteo global. Every source is normalised to the same
HourlySeries: UTC hours, wind in mph, rain and snow in inches per hour, with
precipitation stored at the END of its hour.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta

from django.conf import settings

from core.errors import AppError, UpstreamError
from core.forecast import HourlySeries

from . import cache
from .http import request

log = logging.getLogger(__name__)

HOURLY_VARS = "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall"
EXPECTED_UNITS = {
    "wind_speed_10m": "mp/h",
    "wind_gusts_10m": "mp/h",
    "rain": "inch",
    "showers": "inch",
    "snowfall": "inch",
}
CHUNK_SIZE = 50
MAX_WORKERS = 4
# Open-Meteo's free forecast reaches 16 days ahead (today + 15).
MAX_FORECAST_DAY = 15
# Weather lookups snap to a 0.02° grid (~2 km), finer than NBM's own 2.5 km grid,
# so the forecast is unchanged (Open-Meteo returns the nearest model cell anyway).
# Overlapping checkpoints of different routes then share one lookup, which keeps
# each trip well inside Open-Meteo's free 600 locations per minute.
SNAP_DEG = 0.02


def _round(lat: float, lon: float) -> tuple[float, float]:
    return round(round(lat / SNAP_DEG) * SNAP_DEG, 3), round(round(lon / SNAP_DEG) * SNAP_DEG, 3)


def _cache_key(lat: float, lon: float, start: date, end: date, model: str) -> str:
    # Forecasts refresh at most hourly, so the current UTC hour is part of the key.
    run = datetime.now(UTC).strftime("%Y%m%d%H")
    return f"om:{model}:{lat:.3f}:{lon:.3f}:{start.isoformat()}:{end.isoformat()}:{run}"


def _to_series(block: dict, start: date) -> HourlySeries | None:
    """None when the model has no data for this point (e.g. NBM outside the lower 48)."""
    if not (block.get("hourly") or {}).get("time"):
        return None
    units = block.get("hourly_units", {})
    for var, unit in EXPECTED_UNITS.items():
        if units.get(var) != unit:
            # Guard against silently mixing km/h or mm into mph/inch rules.
            log.error("open-meteo units %s for %s (expected %s)", units.get(var), var, unit)
            raise UpstreamError(
                "WEATHER_BAD_DATA",
                "The weather service sent data in unexpected units. Try again later.",
            )
    h = block["hourly"]
    first = datetime.fromisoformat(h["time"][0]).replace(tzinfo=UTC)
    expected_first = datetime(start.year, start.month, start.day, tzinfo=UTC)
    if first != expected_first:
        raise UpstreamError("WEATHER_BAD_DATA", "The weather service sent data for the wrong hours. Try again later.")
    rain = [None if r is None or s is None else round(r + s, 3) for r, s in zip(h["rain"], h["showers"], strict=True)]
    return HourlySeries(
        start=first,
        wind_mph=h["wind_speed_10m"],
        gust_mph=h["wind_gusts_10m"],
        rain_in=rain,
        snow_in=h["snowfall"],
    )


_BAD_NUMBER = re.compile(r"(?<=[:\[,])\s*-?(?:nan|inf(?:inity)?)\b", re.IGNORECASE)


def _parse_json(text: str):
    """Parse a response, treating stray nan/inf tokens (not valid JSON) as missing values."""
    try:
        return json.loads(text, parse_constant=lambda _: None)
    except ValueError:
        pass
    try:
        return json.loads(_BAD_NUMBER.sub("null", text), parse_constant=lambda _: None)
    except ValueError:
        return None


def _fetch_chunk(points: list[tuple[float, float]], start: date, end: date, model: str) -> list[HourlySeries | None]:
    data = {
        "latitude": ",".join(f"{lat:.3f}" for lat, _ in points),
        "longitude": ",".join(f"{lon:.3f}" for _, lon in points),
        "hourly": HOURLY_VARS,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "GMT",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    if model and model != "best_match":
        data["models"] = model
    base = getattr(settings, "OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
    for attempt in range(2):
        resp = request("POST", base, service="weather", data=data, retries=3, backoff_s=1.0)
        if resp.status_code != 200:
            reason = ""
            with contextlib.suppress(ValueError):
                reason = resp.json().get("reason", "")
            if "no data is available" in reason.lower():
                # A lone point outside this model's area: no data, the backup model fills it.
                return [None] * len(points)
            log.warning("open-meteo %s: %s", resp.status_code, reason)
            raise UpstreamError(
                "WEATHER_UNAVAILABLE", "The weather service could not answer this request. Try again in a minute."
            )
        body = _parse_json(resp.text)
        if body is not None:
            break
        log.warning("open-meteo sent unreadable JSON (attempt %d): %r", attempt + 1, resp.text[:120])
    else:
        raise UpstreamError("WEATHER_BAD_DATA", "The weather service sent unreadable data. Try again in a minute.")
    blocks = body if isinstance(body, list) else [body]
    if len(blocks) != len(points):
        raise UpstreamError("WEATHER_BAD_DATA", "The weather service sent incomplete data. Try again later.")
    return [_to_series(b, start) for b in blocks]


def forecast_window_end() -> date:
    return datetime.now(UTC).date() + timedelta(days=MAX_FORECAST_DAY)


# --------------------------------------------------------------------------
# WeatherAPI.com
# --------------------------------------------------------------------------

WEATHERAPI_URL = "https://api.weatherapi.com/v1/forecast.json"
WEATHERAPI_BULK = 50  # locations per bulk request
WEATHERAPI_WORKERS = 12
CM_PER_INCH = 2.54
SNOW_TO_WATER = 10  # 10 in of snow ~ 1 in of water (standard ratio)


def _weatherapi_series(query: dict, start: date, n_hours: int) -> HourlySeries | None:
    """One location's forecast -> HourlySeries aligned to `start` 00:00 UTC.

    WeatherAPI's hourly precipitation lines up with Open-Meteo's at the same
    timestamp (checked against NBM on the wettest US points: best correlation at
    zero shift), so it is stored at the same index. `precip_in` is rain plus
    melted snow; the rain part is what is left after the snow's water.
    """
    if "error" in query or "forecast" not in query:
        return None
    origin = datetime(start.year, start.month, start.day, tzinfo=UTC)
    wind = [None] * n_hours
    gust = [None] * n_hours
    rain = [None] * n_hours
    snow = [None] * n_hours
    for day in query["forecast"].get("forecastday", []):
        for h in day.get("hour", []):
            t = datetime.fromtimestamp(h["time_epoch"], UTC)
            i = int((t - origin) / timedelta(hours=1))
            if not 0 <= i < n_hours:
                continue
            snow_in = (h.get("snow_cm") or 0.0) / CM_PER_INCH
            wind[i] = float(h["wind_mph"])
            gust[i] = float(h["gust_mph"]) if h.get("gust_mph") is not None else None
            snow[i] = round(snow_in, 3)
            rain[i] = round(max(0.0, (h.get("precip_in") or 0.0) - snow_in / SNOW_TO_WATER), 3)
    if all(v is None for v in wind):
        return None
    return HourlySeries(start=origin, wind_mph=wind, gust_mph=gust, rain_in=rain, snow_in=snow)


_bulk_supported = True


def _weatherapi_days(end: date) -> int:
    # Days counted in the location's own calendar from today; +2 covers time zones.
    return max(1, min(14, (end - datetime.now(UTC).date()).days + 2))


def _weatherapi_check(resp) -> dict:
    if resp.status_code in (401, 403):
        raise UpstreamError("WEATHER_NOT_CONFIGURED", "The backup weather key was rejected.")
    try:
        return resp.json()
    except ValueError:
        raise UpstreamError("WEATHER_BAD_DATA", "The weather service sent unreadable data.") from None


def _fetch_weatherapi(points: list[tuple[float, float]], start: date, end: date) -> list[HourlySeries | None]:
    global _bulk_supported
    key = settings.WEATHERAPI_KEY
    n_hours = ((end - start).days + 1) * 24
    params = {"key": key, "days": _weatherapi_days(end), "aqi": "no", "alerts": "no"}

    if _bulk_supported:

        def bulk(chunk_start: int) -> list[HourlySeries | None]:
            chunk = points[chunk_start : chunk_start + WEATHERAPI_BULK]
            body = {
                "locations": [{"q": f"{lat:.4f},{lon:.4f}", "custom_id": str(i)} for i, (lat, lon) in enumerate(chunk)]
            }
            resp = request(
                "POST", WEATHERAPI_URL, service="weather", params={**params, "q": "bulk"}, json=body, retries=2
            )
            data = _weatherapi_check(resp)
            if resp.status_code != 200 or "bulk" not in data:
                raise LookupError("bulk not available")
            out: list[HourlySeries | None] = [None] * len(chunk)
            for item in data["bulk"]:
                q = item.get("query", {})
                i = int(q.get("custom_id", -1))
                if 0 <= i < len(chunk):
                    out[i] = _weatherapi_series(q, start, n_hours)
            return out

        try:
            starts = list(range(0, len(points), WEATHERAPI_BULK))
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(starts))) as pool:
                parts = list(pool.map(bulk, starts))
            return [s for part in parts for s in part]
        except LookupError:
            log.info("weatherapi bulk requests unavailable on this plan; using single requests")
            _bulk_supported = False

    def single(point: tuple[float, float]) -> HourlySeries | None:
        lat, lon = point
        resp = request(
            "GET", WEATHERAPI_URL, service="weather", params={**params, "q": f"{lat:.4f},{lon:.4f}"}, retries=2
        )
        data = _weatherapi_check(resp)
        if resp.status_code != 200:
            return None  # e.g. location not found: leave it to the next source
        return _weatherapi_series(data, start, n_hours)

    with ThreadPoolExecutor(max_workers=WEATHERAPI_WORKERS) as pool:
        return list(pool.map(single, points))


# --------------------------------------------------------------------------
# Source chain
# --------------------------------------------------------------------------

SOURCE_LABELS = {
    "weatherapi": "WeatherAPI.com",
    "ncep_nbm_conus": "Open-Meteo (NWS National Blend of Models)",
    "best_match": "Open-Meteo",
}


def _fetch_model(points: list[tuple[float, float]], start: date, end: date, model: str) -> dict:
    """{point: HourlySeries | None} from one source, served from cache where possible."""
    keys = {p: _cache_key(p[0], p[1], start, end, model) for p in points}
    cached = cache.get_many(list(keys.values()))
    found = {p: cached[keys[p]] for p in points if keys[p] in cached}
    missing = [p for p in points if p not in found]
    if missing:
        if model == "weatherapi":
            fetched = _fetch_weatherapi(missing, start, end)
        else:
            chunks = [missing[i : i + CHUNK_SIZE] for i in range(0, len(missing), CHUNK_SIZE)]
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(chunks))) as pool:
                results = list(pool.map(lambda c: _fetch_chunk(c, start, end, model), chunks))
            fetched = [s for part in results for s in part]
        fresh = {}
        for p, s in zip(missing, fetched, strict=True):
            found[p] = s
            if s is not None:
                fresh[keys[p]] = s
        cache.set_many(fresh, timeout=3600)
    log.info(
        "weather %s: %d points, %d cached, %d fetched", model, len(points), len(points) - len(missing), len(missing)
    )
    return found


def _has_gaps(s: HourlySeries | None, lo: int = 0, hi: int | None = None) -> bool:
    """Missing values between hour indices lo..hi (inclusive): the hours the trip needs."""
    if s is None:
        return True
    hi = len(s) - 1 if hi is None else min(hi, len(s) - 1)
    return any(arr[i] is None for arr in (s.wind_mph, s.rain_in, s.snow_in) for i in range(lo, hi + 1))


def _fill(primary: HourlySeries | None, backup: HourlySeries | None) -> HourlySeries | None:
    if primary is None or backup is None:
        return primary or backup

    def merge(a, b):
        return [x if x is not None else y for x, y in zip(a, b, strict=True)]

    return HourlySeries(
        start=primary.start,
        wind_mph=merge(primary.wind_mph, backup.wind_mph),
        gust_mph=merge(primary.gust_mph, backup.gust_mph),
        rain_in=merge(primary.rain_in, backup.rain_in),
        snow_in=merge(primary.snow_in, backup.snow_in),
    )


def weather_sources() -> list[str]:
    return [m.strip() for m in getattr(settings, "WEATHER_MODELS", "best_match").split(",") if m.strip()]


def fetch_hourly(
    points: list[tuple[float, float]], start_utc: datetime, end_utc: datetime, *, with_sources: bool = False
):
    """Hourly series for each point, covering at least start_utc .. end_utc (+1 h).

    Results come back in the order of `points`. With `with_sources=True`, also
    returns the list of sources that actually supplied data.
    """
    start_utc = start_utc.astimezone(UTC)
    end_utc = end_utc.astimezone(UTC)
    start = start_utc.date()
    # +1 h: the precipitation for an ETA late in an hour is stored at the next hour.
    end = (end_utc + timedelta(hours=1)).date()
    if end > forecast_window_end():
        end = forecast_window_end()
    origin = datetime(start.year, start.month, start.day, tzinfo=UTC)
    lo = int((start_utc - origin) // timedelta(hours=1))
    hi = int((end_utc - origin) // timedelta(hours=1)) + 2

    rounded = [_round(lat, lon) for lat, lon in points]
    unique = list(dict.fromkeys(rounded))
    series: dict = {p: None for p in unique}
    used: list[str] = []
    last_error: UpstreamError | None = None
    for source in weather_sources():
        need = [p for p in unique if _has_gaps(series[p], lo, hi)]
        if not need:
            break
        try:
            got = _fetch_model(need, start, end, source)
        except UpstreamError as exc:
            log.warning("weather source %s failed (%s); trying the next one", source, exc.code)
            last_error = exc
            continue
        if any(got[p] is not None for p in need):
            used.append(source)
        for p in need:
            series[p] = _fill(series[p], got[p])

    if any(_has_gaps(series[p], lo, hi) for p in unique):
        if all(series[p] is None for p in unique) and last_error is not None:
            raise last_error
        raise AppError(
            "NO_WEATHER_COVERAGE",
            "Forecasts aren't available for part of this trip. Try places on land, or an earlier departure.",
            status=422,
        )
    result = [series[p] for p in rounded]
    return (result, used) if with_sources else result
