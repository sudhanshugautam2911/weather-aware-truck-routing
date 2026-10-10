"""Route geometry: checkpoint placement, ETA interpolation, polyline helpers.

Distances and times along a route come from the routing provider (it knows the
real road length and speed of every stretch). We only interpolate *within* one
short polyline segment, where a straight line is accurate to well under a metre.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from itertools import pairwise

EARTH_RADIUS_M = 6_371_008.8  # mean Earth radius (IUGG)
METERS_PER_MILE = 1609.344


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


@dataclass
class RouteLine:
    """A route polyline with cumulative road distance and drive time at each vertex."""

    lats: list[float]
    lons: list[float]
    cum_m: list[float]  # metres from the start, non-decreasing, cum_m[0] == 0
    cum_s: list[float]  # seconds from the start, non-decreasing, cum_s[0] == 0

    def __post_init__(self) -> None:
        n = len(self.lats)
        if n < 2 or not (len(self.lons) == len(self.cum_m) == len(self.cum_s) == n):
            raise ValueError("route line needs >= 2 points and equal-length arrays")

    @property
    def length_m(self) -> float:
        return self.cum_m[-1]

    @property
    def duration_s(self) -> float:
        return self.cum_s[-1]

    def at_distance(self, d_m: float) -> tuple[float, float, float]:
        """(lat, lon, seconds from start) at road distance d_m."""
        d_m = min(max(d_m, 0.0), self.length_m)
        i = bisect.bisect_right(self.cum_m, d_m) - 1
        i = min(max(i, 0), len(self.cum_m) - 2)
        span = self.cum_m[i + 1] - self.cum_m[i]
        f = 0.0 if span <= 0 else (d_m - self.cum_m[i]) / span
        return (
            self.lats[i] + f * (self.lats[i + 1] - self.lats[i]),
            self.lons[i] + f * (self.lons[i + 1] - self.lons[i]),
            self.cum_s[i] + f * (self.cum_s[i + 1] - self.cum_s[i]),
        )


def fill_between_anchors(
    lats: list[float],
    lons: list[float],
    anchors: list[tuple[int, float, float]],
) -> tuple[list[float], list[float]]:
    """Cumulative distance/time for every vertex from sparse provider anchors.

    anchors: (point_index, metres_from_start, seconds_from_start), as returned by
    TomTom's `progress` array. Between two anchors we spread the provider's
    distance and time in proportion to the straight-line length of each vertex
    segment, so the anchor values are reproduced exactly.
    """
    n = len(lats)
    anchors = sorted(anchors)
    if not anchors or anchors[0][0] != 0:
        anchors.insert(0, (0, 0.0, 0.0))
    seg = [0.0] + [haversine_m(lats[i - 1], lons[i - 1], lats[i], lons[i]) for i in range(1, n)]
    cum_m = [0.0] * n
    cum_s = [0.0] * n
    for (i0, m0, s0), (i1, m1, s1) in pairwise(anchors):
        geo_total = sum(seg[i0 + 1 : i1 + 1])
        acc = 0.0
        for j in range(i0, i1 + 1):
            if j > i0:
                acc += seg[j]
            f = (acc / geo_total) if geo_total > 0 else (0.0 if j == i0 else 1.0)
            cum_m[j] = m0 + f * (m1 - m0)
            cum_s[j] = s0 + f * (s1 - s0)
    last_i, last_m, last_s = anchors[-1]
    # Vertices after the final anchor (should not happen with TomTom, but be safe).
    for j in range(last_i + 1, n):
        cum_m[j] = cum_m[j - 1] + seg[j]
        cum_s[j] = cum_s[j - 1]
    return cum_m, cum_s


@dataclass(frozen=True)
class CheckpointSpot:
    index: int
    distance_m: float  # road distance from the start
    lat: float
    lon: float
    offset_s: float  # drive time from departure
    owned_m: float  # length of road this checkpoint represents


def place_checkpoints(line: RouteLine, interval_m: float) -> list[CheckpointSpot]:
    """Checkpoints at 0, interval, 2*interval, ... and at the destination.

    Each checkpoint "owns" the road halfway to its neighbours, so the owned
    lengths add up exactly to the route length (no mile counted twice or lost).
    """
    if interval_m <= 0:
        raise ValueError("interval must be positive")
    total = line.length_m
    distances = []
    k = 0
    while k * interval_m < total:
        distances.append(k * interval_m)
        k += 1
    # Destination. Drop a regular checkpoint that falls within 1% of an interval
    # of the end, so we never sample the same spot twice.
    if distances and total - distances[-1] < 0.01 * interval_m and len(distances) > 1:
        distances.pop()
    distances.append(total)

    spots = []
    for i, d in enumerate(distances):
        left = 0.0 if i == 0 else (d - distances[i - 1]) / 2
        right = 0.0 if i == len(distances) - 1 else (distances[i + 1] - d) / 2
        lat, lon, t = line.at_distance(d)
        spots.append(CheckpointSpot(i, d, lat, lon, t, left + right))
    return spots


def simplify(lats: list[float], lons: list[float], tolerance_m: float) -> list[int]:
    """Douglas-Peucker. Returns indices of the vertices to keep (always first and last)."""
    n = len(lats)
    if n <= 2:
        return list(range(n))
    # Local equirectangular projection in metres; fine for perpendicular distances.
    lat0 = math.radians(sum(lats) / n)
    kx = math.cos(lat0) * math.pi / 180 * EARTH_RADIUS_M
    ky = math.pi / 180 * EARTH_RADIUS_M
    xs = [lon * kx for lon in lons]
    ys = [lat * ky for lat in lats]
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    tol2 = tolerance_m * tolerance_m
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ax, ay, bx, by = xs[a], ys[a], xs[b], ys[b]
        dx, dy = bx - ax, by - ay
        len2 = dx * dx + dy * dy
        worst, worst_i = -1.0, -1
        for i in range(a + 1, b):
            px, py = xs[i] - ax, ys[i] - ay
            if len2 == 0:
                d2 = px * px + py * py
            else:
                t = max(0.0, min(1.0, (px * dx + py * dy) / len2))
                ex, ey = px - t * dx, py - t * dy
                d2 = ex * ex + ey * ey
            if d2 > worst:
                worst, worst_i = d2, i
        if worst > tol2:
            keep[worst_i] = True
            stack.append((a, worst_i))
            stack.append((worst_i, b))
    return [i for i in range(n) if keep[i]]


def point_to_polyline_m(lat: float, lon: float, lats: list[float], lons: list[float]) -> float:
    """Approximate shortest distance (metres) from a point to a polyline."""
    kx = math.cos(math.radians(lat)) * math.pi / 180 * EARTH_RADIUS_M
    ky = math.pi / 180 * EARTH_RADIUS_M
    best = float("inf")
    for i in range(len(lats) - 1):
        ax, ay = (lons[i] - lon) * kx, (lats[i] - lat) * ky
        bx, by = (lons[i + 1] - lon) * kx, (lats[i + 1] - lat) * ky
        dx, dy = bx - ax, by - ay
        len2 = dx * dx + dy * dy
        t = 0.0 if len2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / len2))
        ex, ey = ax + t * dx, ay + t * dy
        d2 = ex * ex + ey * ey
        if d2 < best:
            best = d2
    return math.sqrt(best)


def overlap_fraction(a: RouteLine, b: RouteLine, sample_every_m: float = 5_000, near_m: float = 1_000) -> float:
    """Share of route `a` (sampled) that runs within `near_m` of route `b`."""
    idx = simplify(b.lats, b.lons, 50)
    blats = [b.lats[i] for i in idx]
    blons = [b.lons[i] for i in idx]
    samples = max(2, int(a.length_m // sample_every_m))
    near = 0
    for k in range(samples + 1):
        lat, lon, _ = a.at_distance(a.length_m * k / samples)
        if point_to_polyline_m(lat, lon, blats, blons) <= near_m:
            near += 1
    return near / (samples + 1)
