"""Trip planning: routes -> checkpoints -> ETA weather -> risk -> recommendation."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise

from core.errors import AppError
from core.forecast import HOUR, ForecastRangeError, MissingWeatherError, floor_hour, sample_at
from core.geo import (
    METERS_PER_MILE,
    RouteLine,
    haversine_m,
    overlap_fraction,
    place_checkpoints,
    simplify,
)
from core.risk import RANKING_RULES, Risk, assess, deciding_rule, rank_routes, ranking_values, summarize
from providers.routing import ProviderRoute, get_router
from providers.weather import SOURCE_LABELS, fetch_hourly, forecast_window_end

log = logging.getLogger(__name__)

MAX_ROUTES = 3
MAX_DEPARTURE_AHEAD = timedelta(days=7)
PAST_GRACE = timedelta(minutes=15)
# A generated alternative must not share more than this with an existing route.
DUPLICATE_OVERLAP = 0.85
# ...and must not take more than this multiple of the fastest route's time.
MAX_DETOUR_FACTOR = 1.6
ROUTE_LETTERS = "ABCDEF"
HEATMAP_HOURS = 48


@dataclass(frozen=True)
class Place:
    lat: float
    lon: float
    label: str


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_trip(origin: Place, destination: Place, departure: datetime) -> datetime:
    now = datetime.now(UTC)
    departure = departure.astimezone(UTC)
    if departure < now - PAST_GRACE:
        raise AppError(
            "DEPARTURE_IN_PAST",
            "This departure time has already passed. Pick a time from now onward.",
            field="departure",
        )
    if departure > now + MAX_DEPARTURE_AHEAD:
        raise AppError(
            "DEPARTURE_TOO_FAR",
            "Pick a departure within the next 7 days. "
            "Forecasts further out are not reliable enough to judge road risk.",
            field="departure",
        )
    if haversine_m(origin.lat, origin.lon, destination.lat, destination.lon) < METERS_PER_MILE:
        raise AppError(
            "SAME_PLACE",
            "Origin and destination are less than a mile apart. Pick two different places.",
            field="destination",
        )
    return max(departure, now.replace(second=0, microsecond=0))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _is_new(candidate: ProviderRoute, existing: list[ProviderRoute]) -> bool:
    for r in existing:
        if overlap_fraction(candidate.line, r.line) >= DUPLICATE_OVERLAP:
            return False
        if overlap_fraction(r.line, candidate.line) >= DUPLICATE_OVERLAP:
            return False
    return True


def _via_candidates(line: RouteLine, straight_m: float):
    """Points beside the main route, used to ask for a genuinely different road."""
    offset = min(max(straight_m * 0.15, 15_000), 120_000)
    for frac, side in ((0.5, 1), (0.5, -1), (0.35, 1), (0.65, -1)):
        lat1, lon1, _ = line.at_distance(line.length_m * (frac - 0.03))
        lat2, lon2, _ = line.at_distance(line.length_m * (frac + 0.03))
        lat, lon, _ = line.at_distance(line.length_m * frac)
        # Unit vector perpendicular to the local direction of travel (in metres).
        kx = math.cos(math.radians(lat)) * 111_320
        dx, dy = (lon2 - lon1) * kx, (lat2 - lat1) * 110_574
        norm = math.hypot(dx, dy) or 1.0
        px, py = -dy / norm * side, dx / norm * side
        yield lat + py * offset / 110_574, lon + px * offset / kx


def find_routes(origin: Place, destination: Place, depart: datetime, load_lb: float):
    router = get_router()
    stops = [(origin.lat, origin.lon), (destination.lat, destination.lon)]
    found = router.routes(stops, depart, load_lb, max_alternatives=MAX_ROUTES - 1)
    if not found:
        raise AppError("NO_ROUTE", "No road route connects these two places.", status=422)

    routes: list[ProviderRoute] = []
    for r in found:
        if len(routes) < MAX_ROUTES and _is_new(r, routes):
            routes.append(r)

    # Providers do not promise alternatives. Ask for routes through points beside
    # the main road until we have three genuinely different options.
    if len(routes) < MAX_ROUTES:
        straight = haversine_m(origin.lat, origin.lon, destination.lat, destination.lon)
        fastest = min(r.line.duration_s for r in routes)
        for via in _via_candidates(routes[0].line, straight):
            if len(routes) >= MAX_ROUTES:
                break
            try:
                extra = router.routes([stops[0], via, stops[1]], depart, load_lb, max_alternatives=0)
            except AppError as exc:
                log.info("via route skipped: %s", exc.code)
                continue
            for r in extra:
                if r.line.duration_s <= fastest * MAX_DETOUR_FACTOR and _is_new(r, routes):
                    routes.append(r)
                    break
    return router, routes


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _geometry(line: RouteLine) -> dict:
    keep = simplify(line.lats, line.lons, tolerance_m=20)
    return {
        "coords": [[round(line.lons[i], 5), round(line.lats[i], 5)] for i in keep],
        "times": [round(line.cum_s[i]) for i in keep],
        "miles": [round(line.cum_m[i] / METERS_PER_MILE, 2) for i in keep],
    }


def plan_trip(origin: Place, destination: Place, departure: datetime, load_lb: float, interval_mi: int) -> dict:
    t0 = time.perf_counter()
    depart = validate_trip(origin, destination, departure)
    router, routes = find_routes(origin, destination, depart, load_lb)
    t_route = time.perf_counter()

    interval_m = interval_mi * METERS_PER_MILE
    spots_by_route = [place_checkpoints(r.line, interval_m) for r in routes]
    latest = depart + timedelta(seconds=max(r.line.duration_s for r in routes))
    if (latest + HOUR).date() > forecast_window_end():
        raise AppError(
            "FORECAST_OUT_OF_RANGE",
            "This trip ends beyond the available forecast. Pick an earlier departure.",
            field="departure",
        )

    all_points = [(s.lat, s.lon) for spots in spots_by_route for s in spots]
    series, sources = fetch_hourly(all_points, depart, latest, with_sources=True)
    t_weather = time.perf_counter()

    out_routes, summaries = [], []
    k = 0
    for idx, (route, spots) in enumerate(zip(routes, spots_by_route, strict=True)):
        route_id = ROUTE_LETTERS[idx]
        checkpoints, segments = [], []
        for s in spots:
            eta = depart + timedelta(seconds=s.offset_s)
            try:
                w = sample_at(series[k], eta)
            except (ForecastRangeError, MissingWeatherError) as exc:
                log.warning("weather gap at %s: %s", route_id, exc)
                raise AppError(
                    "WEATHER_INCOMPLETE",
                    "Weather data is missing for part of this trip. Try again in a few minutes.",
                    status=503,
                ) from exc
            k += 1
            a = assess(w.wind_mph, w.rain_in_hr, w.snow_in_hr, load_lb)
            segments.append((s.owned_m / METERS_PER_MILE, a.level))
            checkpoints.append(
                {
                    "index": s.index,
                    "mile": round(s.distance_m / METERS_PER_MILE, 1),
                    "lat": round(s.lat, 5),
                    "lon": round(s.lon, 5),
                    "eta": _iso(eta),
                    "owned_mi": round(s.owned_m / METERS_PER_MILE, 2),
                    "weather": {
                        "wind_mph": w.wind_mph,
                        "gust_mph": w.gust_mph,
                        "rain_in_hr": w.rain_in_hr,
                        "snow_in_hr": w.snow_in_hr,
                        "wind_hour": _iso(w.wind_hour),
                        "precip_hour_end": _iso(w.precip_hour_end),
                    },
                    "risk": {
                        "level": a.level.key,
                        "wind": a.wind.key,
                        "rain": a.rain.key,
                        "snow": a.snow.key,
                        "load_raised": a.load_raised,
                        "causes": list(a.causes),
                    },
                }
            )
        summary = summarize(route_id, segments, route.line.duration_s)
        summaries.append(summary)
        out_routes.append(
            {
                "id": route_id,
                "distance_mi": round(route.line.length_m / METERS_PER_MILE, 1),
                "duration_s": round(route.line.duration_s),
                "traffic_delay_s": round(route.traffic_delay_s),
                "arrival": _iso(depart + timedelta(seconds=route.line.duration_s)),
                "miles_by_level": {lvl.key: round(summary.miles(lvl), 1) for lvl in Risk},
                "avg_risk": round(summary.avg_risk, 3),
                "worst_level": max((c[1] for c in segments), default=Risk.LOW).key,
                "geometry": _geometry(route.line),
                "checkpoints": checkpoints,
            }
        )

    ranked = rank_routes(summaries)
    best = ranked[0]
    for rank, s in enumerate(ranked, start=1):
        r = next(x for x in out_routes if x["id"] == s.route_id)
        r["rank"] = rank
        r["recommended"] = rank == 1
    out_routes.sort(key=lambda r: r["rank"])

    rules = []
    for i, (key, label) in enumerate(RANKING_RULES):
        rules.append({"key": key, "label": label, "values": {s.route_id: ranking_values(s)[i] for s in summaries}})

    warnings = []
    if not router.truck_aware:
        warnings.append(
            {
                "code": "DEMO_ROUTING",
                "message": "Demo routing: drive times are for a car and ignore traffic and truck limits.",
            }
        )
    if len(routes) < MAX_ROUTES:
        warnings.append(
            {
                "code": "FEWER_ROUTES",
                "message": f"Only {len(routes)} different route{'' if len(routes) == 1 else 's'} "
                "exist between these places.",
            }
        )
    if all(s.miles(Risk.NO_TRAVEL) > 0 for s in summaries):
        warnings.append(
            {
                "code": "ALL_NO_TRAVEL",
                "message": "Every route crosses No Travel weather. Delay the trip until conditions improve.",
            }
        )

    t_end = time.perf_counter()
    return {
        "routes": out_routes,
        "recommendation": {
            "route_id": best.route_id,
            "decided_by": deciding_rule(best, ranked[1]) if len(ranked) > 1 else None,
            # For every other route: the first rule on which the recommended route beat it.
            "beats": {other.route_id: deciding_rule(best, other) for other in ranked[1:]},
            "rules": rules,
        },
        "warnings": warnings,
        "meta": {
            "departure": _iso(depart),
            "load_lb": load_lb,
            "interval_mi": interval_mi,
            "routing_provider": router.name,
            "truck_aware": router.truck_aware,
            "weather_sources": [SOURCE_LABELS.get(s, s) for s in sources],
            "generated_at": _iso(datetime.now(UTC)),
            "timings_ms": {
                "routing": round((t_route - t0) * 1000),
                "weather": round((t_weather - t_route) * 1000),
                "total": round((t_end - t0) * 1000),
            },
        },
    }


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------

LATTICE_STEPS = (0.1, 0.125, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0)
MAX_CELLS = 160
CORRIDOR_KM = 40.0


def _corridor_cells(lines: list[list[tuple[float, float]]], step: float) -> set[tuple[int, int]]:
    """Lattice cells (snapped to multiples of `step` degrees) near any route."""
    step_km = step * 111.0
    buffer_km = max(CORRIDOR_KM, step_km * 0.75)
    cells: set[tuple[int, int]] = set()
    for pts in lines:
        for (lon1, lat1), (lon2, lat2) in pairwise(pts):
            seg_km = haversine_m(lat1, lon1, lat2, lon2) / 1000
            n = max(1, int(seg_km / (step_km / 2)))
            for j in range(n + 1):
                lat = lat1 + (lat2 - lat1) * j / n
                lon = lon1 + (lon2 - lon1) * j / n
                ci, cj = round(lat / step), round(lon / step)
                r_lat = int(math.ceil(buffer_km / step_km)) + 1
                r_lon = int(math.ceil(buffer_km / (step_km * max(0.2, math.cos(math.radians(lat)))))) + 1
                for di in range(-r_lat, r_lat + 1):
                    for dj in range(-r_lon, r_lon + 1):
                        key = (ci + di, cj + dj)
                        if key in cells:
                            continue
                        if haversine_m(lat, lon, key[0] * step, key[1] * step) / 1000 <= buffer_km:
                            cells.add(key)
    return cells


def build_heatmap(lines: list[list[tuple[float, float]]], departure: datetime, load_lb: float) -> dict:
    if not lines or any(len(pts) < 2 for pts in lines):
        raise AppError("BAD_ROUTES", "Route shapes are missing. Plan the trip again.")
    # Coarse copies of the lines are enough to find the corridor.
    coarse = []
    for pts in lines:
        keep = simplify([p[1] for p in pts], [p[0] for p in pts], tolerance_m=2_000)
        coarse.append([pts[i] for i in keep])

    step, cells = LATTICE_STEPS[-1], set()
    for s in LATTICE_STEPS:
        cells = _corridor_cells(coarse, s)
        step = s
        if len(cells) <= MAX_CELLS:
            break
    cells_sorted = sorted(cells)
    points = [(i * step, j * step) for i, j in cells_sorted]

    start = floor_hour(departure)
    end = start + timedelta(hours=HEATMAP_HOURS)
    series, sources = fetch_hourly(points, start, end, with_sources=True)

    hours = [start + h * HOUR for h in range(HEATMAP_HOURS + 1)]
    out_cells = []
    fields = ("risk", "wind", "rain", "snow", "wind_risk", "rain_risk", "snow_risk")
    for (lat, lon), s in zip(points, series, strict=True):
        cell = {name: [] for name in fields}
        for t in hours:
            try:
                w = sample_at(s, t)
                a = assess(w.wind_mph, w.rain_in_hr, w.snow_in_hr, load_lb)
            except (ForecastRangeError, MissingWeatherError):
                for name in fields:
                    cell[name].append(None)
                continue
            cell["risk"].append(int(a.level))
            cell["wind"].append(w.wind_mph)
            cell["rain"].append(w.rain_in_hr)
            cell["snow"].append(w.snow_in_hr)
            cell["wind_risk"].append(int(a.wind))
            cell["rain_risk"].append(int(a.rain))
            cell["snow_risk"].append(int(a.snow))
        out_cells.append({"lat": round(lat, 4), "lon": round(lon, 4), **cell})
    return {
        "step": step,
        "hours": [_iso(t) for t in hours],
        "cells": out_cells,
        "weather_sources": [SOURCE_LABELS.get(s, s) for s in sources],
    }
