"""Open-Meteo hourly forecast client: chunked, parallel, cached, unit-checked."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from django.conf import settings
from django.core.cache import cache

from core.errors import AppError, UpstreamError
from core.forecast import HourlySeries

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
COORD_DECIMALS = 3  # ~100 m; far finer than any weather model's grid


def _round(lat: float, lon: float) -> tuple[float, float]:
    return round(lat, COORD_DECIMALS), round(lon, COORD_DECIMALS)


def _cache_key(lat: float, lon: float, start: date, end: date, model: str) -> str:
    # Forecasts refresh at most hourly, so the current UTC hour is part of the key.
    run = datetime.now(timezone.utc).strftime("%Y%m%d%H")
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
    first = datetime.fromisoformat(h["time"][0]).replace(tzinfo=timezone.utc)
    expected_first = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    if first != expected_first:
        raise UpstreamError("WEATHER_BAD_DATA", "The weather service sent data for the wrong hours. Try again later.")
    rain = [
        None if r is None or s is None else round(r + s, 3) for r, s in zip(h["rain"], h["showers"])
    ]
    return HourlySeries(
        start=first,
        wind_mph=h["wind_speed_10m"],
        gust_mph=h["wind_gusts_10m"],
        rain_in=rain,
        snow_in=h["snowfall"],
    )


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
    resp = request("POST", base, service="weather", data=data, retries=3, backoff_s=1.0)
    if resp.status_code != 200:
        reason = ""
        try:
            reason = resp.json().get("reason", "")
        except ValueError:
            pass
        log.warning("open-meteo %s: %s", resp.status_code, reason)
        raise UpstreamError("WEATHER_UNAVAILABLE", "The weather service could not answer this request. Try again in a minute.")
    body = resp.json()
    blocks = body if isinstance(body, list) else [body]
    if len(blocks) != len(points):
        raise UpstreamError("WEATHER_BAD_DATA", "The weather service sent incomplete data. Try again later.")
    return [_to_series(b, start) for b in blocks]


def forecast_window_end() -> date:
    return datetime.now(timezone.utc).date() + timedelta(days=MAX_FORECAST_DAY)


def _fetch_model(points: list[tuple[float, float]], start: date, end: date, model: str) -> dict:
    """{point: HourlySeries} for one model, served from cache where possible."""
    keys = {p: _cache_key(p[0], p[1], start, end, model) for p in points}
    cached = cache.get_many(list(keys.values()))
    found = {p: cached[keys[p]] for p in points if keys[p] in cached}
    missing = [p for p in points if p not in found]
    if missing:
        chunks = [missing[i : i + CHUNK_SIZE] for i in range(0, len(missing), CHUNK_SIZE)]
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(chunks))) as pool:
            results = list(pool.map(lambda c: _fetch_chunk(c, start, end, model), chunks))
        fresh = {}
        for chunk, series_list in zip(chunks, results):
            for p, s in zip(chunk, series_list):
                found[p] = s
                if s is not None:
                    fresh[keys[p]] = s
        cache.set_many(fresh, timeout=3600)
    log.info("weather %s: %d points, %d cached, %d fetched", model, len(points), len(points) - len(missing), len(missing))
    return found


def _has_gaps(s: HourlySeries | None) -> bool:
    if s is None:
        return True
    return any(v is None for arr in (s.wind_mph, s.rain_in, s.snow_in) for v in arr)


def _fill(primary: HourlySeries | None, backup: HourlySeries | None) -> HourlySeries | None:
    if primary is None or backup is None:
        return primary or backup

    def merge(a, b):
        return [x if x is not None else y for x, y in zip(a, b)]

    return HourlySeries(
        start=primary.start,
        wind_mph=merge(primary.wind_mph, backup.wind_mph),
        gust_mph=merge(primary.gust_mph, backup.gust_mph),
        rain_in=merge(primary.rain_in, backup.rain_in),
        snow_in=merge(primary.snow_in, backup.snow_in),
    )


def fetch_hourly(points: list[tuple[float, float]], start_utc: datetime, end_utc: datetime) -> list[HourlySeries]:
    """Hourly series for each point, covering at least start_utc .. end_utc (+1 h).

    Uses the primary model (NBM by default: it scored best in our backtest) and
    fills any hours it lacks, such as points outside the lower 48 states, from
    the next model in WEATHER_MODELS. Results come back in the order of `points`.
    """
    models = [m.strip() for m in getattr(settings, "WEATHER_MODELS", "best_match").split(",") if m.strip()]
    start = start_utc.astimezone(timezone.utc).date()
    # +1 h: the precipitation for an ETA late in an hour is stored at the next hour.
    end = (end_utc.astimezone(timezone.utc) + timedelta(hours=1)).date()
    if end > forecast_window_end():
        end = forecast_window_end()

    rounded = [_round(lat, lon) for lat, lon in points]
    unique = list(dict.fromkeys(rounded))
    series = _fetch_model(unique, start, end, models[0])
    for backup_model in models[1:]:
        gappy = [p for p in unique if _has_gaps(series[p])]
        if not gappy:
            break
        backup = _fetch_model(gappy, start, end, backup_model)
        for p in gappy:
            series[p] = _fill(series[p], backup[p])
    if any(series[p] is None for p in unique):
        raise AppError(
            "NO_WEATHER_COVERAGE",
            "Forecasts aren't available for part of this trip. Try places on land within North America.",
            status=422,
        )
    return [series[p] for p in rounded]
