"""Live accuracy checks on real trips.

B1  ETA check: our interpolated checkpoint ETA vs. the routing provider's own
    time for a trip that ends at that checkpoint.
B2  Cross-source wind: our forecast at each checkpoint's ETA vs. the US National
    Weather Service gridded forecast for the same place and hour.
B4  Sampling sensitivity: risk miles found with 10 / 25 / 50 mile checkpoints.

Run:  cd backend && .venv/bin/python -m accuracy.checks
Writes accuracy/results/checks.json.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import httpx  # noqa: E402

from api.services import Place, plan_trip  # noqa: E402
from core.risk import classify_wind  # noqa: E402
from providers.routing import get_router  # noqa: E402

TRIPS = [
    (Place(41.8781, -87.6298, "Chicago, IL"), Place(39.7392, -104.9903, "Denver, CO")),
    (Place(32.7767, -96.7970, "Dallas, TX"), Place(33.7490, -84.3880, "Atlanta, GA")),
    (Place(47.6062, -122.3321, "Seattle, WA"), Place(40.7608, -111.8910, "Salt Lake City, UT")),
    (Place(35.4676, -97.5164, "Oklahoma City, OK"), Place(44.9778, -93.2650, "Minneapolis, MN")),
]
LOAD_LB = 38_000
OUT = Path(__file__).parent / "results"
nws = httpx.Client(timeout=30, headers={"User-Agent": "weather-aware-truck-routing accuracy check", "Accept": "application/geo+json"})


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _duration(iso: str) -> timedelta:
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", iso)
    d, h, mi = (int(x) if x else 0 for x in m.groups())
    return timedelta(days=d, hours=h, minutes=mi)


def eta_check(plan: dict, origin: Place, depart: datetime) -> list[dict]:
    router = get_router()
    route = next(r for r in plan["routes"] if r["recommended"])
    cps = route["checkpoints"]
    rows = []
    for frac in (0.25, 0.5, 0.75):
        cp = cps[int(len(cps) * frac)]
        ours = (_dt(cp["eta"]) - depart).total_seconds()
        direct = router.routes([(origin.lat, origin.lon), (cp["lat"], cp["lon"])], depart, LOAD_LB, 0)[0].line
        # Only compare when the direct trip uses the same road (length within 2%).
        same_road = abs(direct.length_m / 1609.344 - cp["mile"]) <= 0.02 * cp["mile"]
        rows.append(
            {
                "mile": cp["mile"],
                "our_eta_min": round(ours / 60, 1),
                "provider_min": round(direct.duration_s / 60, 1),
                "error_min": round((ours - direct.duration_s) / 60, 1),
                "same_road": same_road,
            }
        )
        time.sleep(1)  # be gentle with the public demo router
    return rows


def nws_wind_at(lat: float, lon: float, when: datetime, cache: dict) -> float | None:
    key = (round(lat, 2), round(lon, 2))
    if key not in cache:
        p = nws.get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")
        if p.status_code != 200:
            cache[key] = None
        else:
            g = nws.get(p.json()["properties"]["forecastGridData"])
            cache[key] = g.json()["properties"]["windSpeed"] if g.status_code == 200 else None
        time.sleep(0.3)
    data = cache[key]
    if not data:
        return None
    for v in data["values"]:
        start_s, dur_s = v["validTime"].split("/")
        start = _dt(start_s)
        if start <= when < start + _duration(dur_s) and v["value"] is not None:
            return v["value"] * 0.621371  # km/h -> mph
    return None


def cross_check(plan: dict, cache: dict) -> list[dict]:
    rows = []
    for route in plan["routes"]:
        for cp in route["checkpoints"][::3]:
            when = _dt(cp["weather"]["wind_hour"])
            theirs = nws_wind_at(cp["lat"], cp["lon"], when, cache)
            if theirs is None:
                continue
            ours = cp["weather"]["wind_mph"]
            rows.append({"ours_mph": ours, "nws_mph": round(theirs, 1), "same_level": classify_wind(ours) == classify_wind(theirs)})
    return rows


def main() -> None:
    depart = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "departure": depart.isoformat(), "trips": []}
    nws_cache: dict = {}
    eta_rows, wind_rows = [], []
    for origin, dest in TRIPS:
        trip = {"trip": f"{origin.label} to {dest.label}", "sampling": {}}
        plans = {}
        for interval in (10, 25, 50):
            plans[interval] = plan_trip(origin, dest, depart, LOAD_LB, interval)
            trip["sampling"][interval] = {
                r["id"]: {
                    "checkpoints": len(r["checkpoints"]),
                    "miles_by_level": r["miles_by_level"],
                    "max_wind_mph": max(c["weather"]["wind_mph"] for c in r["checkpoints"]),
                    "max_rain_in_hr": max(c["weather"]["rain_in_hr"] for c in r["checkpoints"]),
                }
                for r in plans[interval]["routes"]
            }
            trip["sampling"][interval]["recommended"] = plans[interval]["recommendation"]["route_id"]
            time.sleep(1)
        trip["eta_check"] = eta_check(plans[10], origin, _dt(plans[10]["meta"]["departure"]))
        trip["wind_cross_check"] = cross_check(plans[10], nws_cache)
        eta_rows += [r for r in trip["eta_check"] if r["same_road"]]
        wind_rows += trip["wind_cross_check"]
        out["trips"].append(trip)
        print("done:", trip["trip"])

    out["summary"] = {
        "routing_provider": get_router().name,
        "eta_points_compared": len(eta_rows),
        "eta_mean_abs_error_min": round(sum(abs(r["error_min"]) for r in eta_rows) / len(eta_rows), 2) if eta_rows else None,
        "eta_mean_abs_error_pct": round(
            100 * sum(abs(r["error_min"]) / r["provider_min"] for r in eta_rows) / len(eta_rows), 2
        ) if eta_rows else None,
        "wind_points_compared": len(wind_rows),
        "wind_mae_vs_nws_mph": round(sum(abs(r["ours_mph"] - r["nws_mph"]) for r in wind_rows) / len(wind_rows), 2) if wind_rows else None,
        "wind_same_level_pct": round(100 * sum(r["same_level"] for r in wind_rows) / len(wind_rows), 1) if wind_rows else None,
        "recommendation_same_at_all_intervals": sum(
            len({t["sampling"][i]["recommended"] for i in (10, 25, 50)}) == 1 for t in out["trips"]
        ),
        "trips": len(out["trips"]),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "checks.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out["summary"], indent=2))


if __name__ == "__main__":
    main()
