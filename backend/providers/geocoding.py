"""Place search (address -> coordinates) with type-ahead suggestions."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from django.conf import settings

from core.errors import UpstreamError

from . import cache
from .http import request


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float

    def as_dict(self) -> dict:
        return {"label": self.label, "lat": self.lat, "lon": self.lon}


def _dedupe(places: list[Place], limit: int) -> list[Place]:
    seen, out = set(), []
    for p in places:
        if p.label.lower() in seen:
            continue
        seen.add(p.label.lower())
        out.append(p)
    return out[:limit]


def _tomtom(query: str, limit: int) -> list[Place]:
    # The search endpoint (unlike /geocode) understands half-typed words ("Memph").
    # Cities, addresses and streets only: business names make noisy suggestions.
    url = f"https://api.tomtom.com/search/2/search/{quote(query, safe='')}.json"
    resp = request(
        "GET",
        url,
        service="place search",
        params={
            "key": settings.TOMTOM_API_KEY,
            "typeahead": "true",
            "limit": str(limit + 2),
            "language": "en-US",
            "idxSet": "Geo,PAD,Addr,Str",
        },
        retries=1,
    )
    if resp.status_code != 200:
        raise UpstreamError("GEOCODER_UNAVAILABLE", "Place search is unavailable right now. Try again in a moment.")
    places = []
    for r in resp.json().get("results", []):
        label = r.get("address", {}).get("freeformAddress")
        pos = r.get("position") or {}
        if label and "lat" in pos and "lon" in pos:
            places.append(Place(label, float(pos["lat"]), float(pos["lon"])))
    return places


def _photon(query: str, limit: int) -> list[Place]:
    resp = request(
        "GET",
        "https://photon.komoot.io/api/",
        service="place search",
        params={"q": query, "limit": str(limit + 4), "lang": "en"},
        retries=1,
    )
    if resp.status_code != 200:
        raise UpstreamError("GEOCODER_UNAVAILABLE", "Place search is unavailable right now. Try again in a moment.")
    places = []
    for f in resp.json().get("features", []):
        props = f.get("properties", {})
        lon, lat = f.get("geometry", {}).get("coordinates", [None, None])
        if lat is None:
            continue
        parts = [props.get("name")]
        for key in ("city", "state"):
            value = props.get(key)
            if value and value not in parts:
                parts.append(value)
        parts.append(props.get("countrycode", "").upper() or props.get("country"))
        label = ", ".join(p for p in parts if p)
        if label:
            places.append(Place(label, float(lat), float(lon)))
    return places


def search_places(query: str, limit: int = 6) -> list[Place]:
    use_tomtom = bool(getattr(settings, "TOMTOM_API_KEY", ""))
    key = f"geo:{'tt' if use_tomtom else 'ph'}:{limit}:{query.strip().lower()}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    places = _dedupe(_tomtom(query, limit) if use_tomtom else _photon(query, limit), limit)
    cache.set(key, places, timeout=24 * 3600)  # place names don't change; saves free-tier quota
    return places
