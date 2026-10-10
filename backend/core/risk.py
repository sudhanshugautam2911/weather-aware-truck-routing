"""Weather risk rules from the assessment brief.

Pure Python, no Django: every function here is deterministic and unit-tested.

Boundary convention (the brief's ranges overlap at the edges, e.g. rain 0.25 sits
in both Moderate and High): each level's lower bound is inclusive. The only
exception is the top of the rain/snow tables, where the brief says "> 1.00" and
"> 3.0" for No Travel, so exactly 1.00 in/hr rain is still Severe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum


class Risk(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return _LABELS[self]

    @property
    def key(self) -> str:
        return self.name.lower()


_LABELS = {
    Risk.LOW: "Low",
    Risk.MODERATE: "Moderate",
    Risk.HIGH: "High",
    Risk.SEVERE: "Severe",
    Risk.NO_TRAVEL: "No Travel",
}

# Load thresholds in pounds.
HEAVY_LOAD_LB = 30_000
VERY_HEAVY_LOAD_LB = 40_000


def _check(value: float, name: str) -> float:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, got {value!r}")
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    if value < 0:
        raise ValueError(f"{name} cannot be negative, got {value!r}")
    return float(value)


def classify_wind(mph: float) -> Risk:
    mph = _check(mph, "wind")
    if mph < 25:
        return Risk.LOW
    if mph < 35:
        return Risk.MODERATE
    if mph < 45:
        return Risk.HIGH
    if mph < 55:
        return Risk.SEVERE
    return Risk.NO_TRAVEL


def classify_rain(in_per_hr: float) -> Risk:
    rate = _check(in_per_hr, "rain")
    if rate < 0.10:
        return Risk.LOW
    if rate < 0.25:
        return Risk.MODERATE
    if rate < 0.50:
        return Risk.HIGH
    if rate <= 1.00:
        return Risk.SEVERE
    return Risk.NO_TRAVEL


def classify_snow(in_per_hr: float) -> Risk:
    rate = _check(in_per_hr, "snow")
    if rate < 0.5:
        return Risk.LOW
    if rate < 1.0:
        return Risk.MODERATE
    if rate < 2.0:
        return Risk.HIGH
    if rate <= 3.0:
        return Risk.SEVERE
    return Risk.NO_TRAVEL


def wind_risk_for_load(mph: float, load_lb: float) -> Risk:
    """Wind risk after the brief's load rules. Load rules only ever raise risk."""
    mph = _check(mph, "wind")
    load_lb = _check(load_lb, "load")
    base = classify_wind(mph)
    if mph >= 55:
        return Risk.NO_TRAVEL
    if 45 <= mph < 55 and load_lb > HEAVY_LOAD_LB:
        return Risk.NO_TRAVEL
    if 35 <= mph < 45 and load_lb > VERY_HEAVY_LOAD_LB:
        return Risk.SEVERE
    return base


@dataclass(frozen=True)
class Assessment:
    level: Risk
    wind: Risk
    rain: Risk
    snow: Risk
    # True when a load rule raised the wind level above the plain table value.
    load_raised: bool
    # Which conditions set the final level ("wind", "rain", "snow"); empty when Low.
    causes: tuple[str, ...]


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Assessment:
    """Checkpoint risk = the worst of wind (after load rules), rain and snow."""
    wind = wind_risk_for_load(wind_mph, load_lb)
    rain = classify_rain(rain_in_hr)
    snow = classify_snow(snow_in_hr)
    level = max(wind, rain, snow)
    causes = ()
    if level > Risk.LOW:
        causes = tuple(name for name, value in (("wind", wind), ("rain", rain), ("snow", snow)) if value == level)
    return Assessment(
        level=level,
        wind=wind,
        rain=rain,
        snow=snow,
        load_raised=wind > classify_wind(wind_mph),
        causes=causes,
    )


# ---------------------------------------------------------------------------
# Route ranking
# ---------------------------------------------------------------------------

# Comparison tolerances so floating-point noise never decides a ranking.
MILES_PRECISION = 1  # 0.1 mile
AVG_PRECISION = 3


@dataclass(frozen=True)
class RouteRisk:
    route_id: str
    miles_by_level: dict[Risk, float]
    total_miles: float
    avg_risk: float  # mile-weighted, Low=0 ... No Travel=4
    duration_s: float

    def miles(self, level: Risk) -> float:
        return self.miles_by_level.get(level, 0.0)


def summarize(route_id: str, segments: list[tuple[float, Risk]], duration_s: float) -> RouteRisk:
    """segments: (miles, risk) for each checkpoint's stretch of road."""
    miles_by_level = {level: 0.0 for level in Risk}
    total = 0.0
    weighted = 0.0
    for miles, level in segments:
        if miles < 0:
            raise ValueError("segment miles cannot be negative")
        miles_by_level[level] += miles
        total += miles
        weighted += miles * int(level)
    avg = weighted / total if total > 0 else 0.0
    return RouteRisk(route_id, miles_by_level, total, avg, float(duration_s))


# Ranking rules, in order. Rule 0 (No Travel) is our addition: the brief does not
# mention No Travel in the ranking, but a route you must not drive can never beat
# one you can.
RANKING_RULES: tuple[tuple[str, str], ...] = (
    ("no_travel_miles", "Fewest No Travel miles"),
    ("severe_miles", "Fewest Severe miles"),
    ("high_miles", "Fewest High miles"),
    ("avg_risk", "Lowest average risk"),
    ("duration", "Shortest travel time"),
)


def ranking_values(r: RouteRisk) -> tuple[float, float, float, float, float]:
    return (
        round(r.miles(Risk.NO_TRAVEL), MILES_PRECISION),
        round(r.miles(Risk.SEVERE), MILES_PRECISION),
        round(r.miles(Risk.HIGH), MILES_PRECISION),
        round(r.avg_risk, AVG_PRECISION),
        round(r.duration_s),
    )


def rank_routes(routes: list[RouteRisk]) -> list[RouteRisk]:
    """Best first. Route id is the final, stable tie-breaker."""
    return sorted(routes, key=lambda r: (ranking_values(r), r.route_id))


def deciding_rule(best: RouteRisk, runner_up: RouteRisk) -> str | None:
    """Key of the first rule where the best route beat the runner-up (None = full tie)."""
    for (key, _), a, b in zip(RANKING_RULES, ranking_values(best), ranking_values(runner_up), strict=True):
        if a != b:
            return key
    return None
