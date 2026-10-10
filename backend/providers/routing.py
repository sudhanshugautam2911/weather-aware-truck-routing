"""Routing providers.

TomTom (truck profile, uses load weight and departure time) is the real
provider. OSRM's public demo server is a key-free stand-in for local
development only: car speeds, no traffic, and no weight limits.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime

from django.conf import settings

from core.errors import AppError, UpstreamError
from core.geo import RouteLine, fill_between_anchors

from .http import request

LB_TO_KG = 0.45359237
# Typical empty tractor-trailer. TomTom needs gross vehicle weight to avoid
# roads and bridges with weight limits; the brief gives us only the load.
TRUCK_TARE_LB = 35_000
MPH_TO_KMH = 1.609344


@dataclass
class ProviderRoute:
    line: RouteLine
    traffic_delay_s: float = 0.0


class Router:
    name = "base"
    truck_aware = False

    def routes(
        self,
        stops: list[tuple[float, float]],
        depart_utc: datetime,
        load_lb: float,
        max_alternatives: int,
    ) -> list[ProviderRoute]:
        raise NotImplementedError


class TomTomRouter(Router):
    name = "tomtom"
    truck_aware = True
    BASE = "https://api.tomtom.com/routing/1/calculateRoute"

    def __init__(self, key: str):
        self.key = key

    def routes(self, stops, depart_utc, load_lb, max_alternatives):
        locations = ":".join(f"{lat:.6f},{lon:.6f}" for lat, lon in stops)
        gross_kg = round((load_lb + TRUCK_TARE_LB) * LB_TO_KG)
        params = [
            ("key", self.key),
            ("travelMode", "truck"),
            ("vehicleCommercial", "true"),
            ("vehicleWeight", str(gross_kg)),
            # Without a cap TomTom's truck mode drives at car speeds (checked:
            # identical times). Fleet trucks are usually governed near 65 mph.
            ("vehicleMaxSpeed", str(round(settings.TRUCK_MAX_SPEED_MPH * MPH_TO_KMH))),
            ("traffic", "true"),
            ("routeRepresentation", "polyline"),
            ("extendedRouteRepresentation", "distance"),
            ("extendedRouteRepresentation", "travelTime"),
            ("maxAlternatives", str(max_alternatives if len(stops) == 2 else 0)),
        ]
        if depart_utc > datetime.now(UTC):
            params.append(("departAt", depart_utc.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")))
        resp = request("GET", f"{self.BASE}/{locations}/json", service="routing", params=params)
        if resp.status_code in (401, 403):
            raise UpstreamError(
                "ROUTING_NOT_CONFIGURED",
                "The route service rejected our API key. The app owner needs to check the TomTom key.",
            )
        if resp.status_code == 400:
            detail = ""
            with contextlib.suppress(ValueError):
                detail = resp.json().get("detailedError", {}).get("message", "")
            if "NO_ROUTE" in detail.upper() or "not connected" in detail.lower() or "near a road" in detail.lower():
                raise AppError(
                    "NO_ROUTE",
                    "No truck route connects these two places. Check that both are reachable by road.",
                    status=422,
                )
            raise UpstreamError(
                "ROUTING_BAD_REQUEST", "The route service could not process this trip. Try different places."
            )
        if resp.status_code != 200:
            raise UpstreamError(
                "ROUTING_UNAVAILABLE", "The route service is unavailable right now. Try again in a minute."
            )
        return [self._parse(r) for r in resp.json().get("routes", [])]

    @staticmethod
    def _parse(route: dict) -> ProviderRoute:
        lats, lons = [], []
        for leg in route["legs"]:
            for p in leg["points"]:
                if lats and lats[-1] == p["latitude"] and lons[-1] == p["longitude"]:
                    continue  # legs share their joining point
                lats.append(p["latitude"])
                lons.append(p["longitude"])
        summary = route["summary"]
        progress = route.get("progress") or []
        anchors = [
            (p["pointIndex"], float(p.get("distanceInMeters", 0)), float(p.get("travelTimeInSeconds", 0)))
            for p in progress
            if "pointIndex" in p and p["pointIndex"] < len(lats)
        ]
        # Always pin the end to the summary totals.
        anchors = [a for a in anchors if a[0] != len(lats) - 1]
        anchors.append((len(lats) - 1, float(summary["lengthInMeters"]), float(summary["travelTimeInSeconds"])))
        cum_m, cum_s = fill_between_anchors(lats, lons, anchors)
        return ProviderRoute(
            line=RouteLine(lats, lons, cum_m, cum_s),
            traffic_delay_s=float(summary.get("trafficDelayInSeconds", 0)),
        )


class OsrmRouter(Router):
    name = "osrm-demo"
    truck_aware = False
    BASE = "https://router.project-osrm.org/route/v1/driving"

    def routes(self, stops, depart_utc, load_lb, max_alternatives):
        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in stops)
        params = {
            "overview": "full",
            "geometries": "geojson",
            "annotations": "distance,duration",
            # The demo server allows at most 3; ask for all of them since some may be near-duplicates.
            "alternatives": "3" if len(stops) == 2 and max_alternatives else "false",
            "steps": "false",
        }
        resp = request("GET", f"{self.BASE}/{coords}", service="routing", params=params)
        body = {}
        with contextlib.suppress(ValueError):
            body = resp.json()
        if body.get("code") in ("NoRoute", "NoSegment"):
            raise AppError(
                "NO_ROUTE",
                "No road route connects these two places. Check that both are reachable by road.",
                status=422,
            )
        if resp.status_code != 200 or body.get("code") != "Ok":
            raise UpstreamError(
                "ROUTING_UNAVAILABLE", "The route service is unavailable right now. Try again in a minute."
            )
        return [self._parse(r) for r in body["routes"]]

    @staticmethod
    def _parse(route: dict) -> ProviderRoute:
        coords = route["geometry"]["coordinates"]
        lats = [c[1] for c in coords]
        lons = [c[0] for c in coords]
        dist, dur = [], []
        for leg in route["legs"]:
            ann = leg.get("annotation") or {}
            dist.extend(ann.get("distance", []))
            dur.extend(ann.get("duration", []))
        if len(dist) == len(lats) - 1 == len(dur):
            cum_m, cum_s = [0.0], [0.0]
            for d, t in zip(dist, dur, strict=True):
                cum_m.append(cum_m[-1] + d)
                cum_s.append(cum_s[-1] + t)
        else:
            cum_m, cum_s = fill_between_anchors(
                lats, lons, [(len(lats) - 1, float(route["distance"]), float(route["duration"]))]
            )
        return ProviderRoute(line=RouteLine(lats, lons, cum_m, cum_s))


def get_router() -> Router:
    key = getattr(settings, "TOMTOM_API_KEY", "")
    return TomTomRouter(key) if key else OsrmRouter()
