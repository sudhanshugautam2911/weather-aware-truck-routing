"""B3 backtest: how often did the forecast's risk level match what really happened?

Forecasts: Open-Meteo Previous Runs API, i.e. what the model predicted 1 and 2
days before each hour (the same model family the app uses).
Truth: hourly airport observations (ASOS) from the Iowa Environmental Mesonet.

Run:  cd backend && .venv/bin/python -m accuracy.backtest --days 30
Writes accuracy/results/backtest.json and prints a summary table.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

from core.risk import Risk, classify_rain, classify_wind

# Airports along major US truck corridors, mixing windy plains, wet coasts,
# mountain passes and snowy northern routes.
STATIONS = [
    "ORD",
    "DEN",
    "DFW",
    "ATL",
    "SEA",
    "SLC",
    "OKC",
    "AMA",
    "CYS",
    "BIS",
    "MSP",
    "STL",
    "MEM",
    "PHX",
    "ABQ",
    "BOS",
    "PIT",
    "BUF",
    "MCI",
    "OMA",
    "ICT",
    "LBB",
    "RAP",
    "GTF",
]
KNOTS_TO_MPH = 1.150779
RAIN_YES = 0.01  # in/hr: "measurable rain"
OUT = Path(__file__).parent / "results"
client = httpx.Client(timeout=60, headers={"User-Agent": "weather-aware-truck-routing backtest"})


def observations(station: str, start: date, end: date):
    """{utc_hour: (wind_mph, rain_in, snowing)} from hourly routine METARs."""
    params = [
        ("station", station),
        ("data", "sknt"),
        ("data", "p01i"),
        ("data", "wxcodes"),
        ("year1", start.year),
        ("month1", start.month),
        ("day1", start.day),
        ("year2", end.year),
        ("month2", end.month),
        ("day2", end.day),
        ("tz", "Etc/UTC"),
        ("format", "onlycomma"),
        ("latlon", "yes"),
        ("missing", "M"),
        ("trace", "0.0001"),
        ("report_type", "3"),
    ]
    r = client.get("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py", params=params)
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    obs, lat, lon = {}, None, None
    for row in rows:
        if row["sknt"] in ("M", "") or row["p01i"] in ("M", ""):
            continue
        t = datetime.strptime(row["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
        # A report at 13:51 describes the hour ending 13:51: match it to 14:00.
        hour = (t + timedelta(minutes=30)).replace(minute=0)
        wx = row.get("wxcodes", "") or ""
        obs[hour] = (float(row["sknt"]) * KNOTS_TO_MPH, float(row["p01i"]), "SN" in wx)
        lat, lon = float(row["lat"]), float(row["lon"])
    return obs, lat, lon


def forecasts(lat: float, lon: float, start: date, end: date, lead: int, model: str):
    """{utc_hour: (wind_mph, rain_in, snow_in)} as forecast `lead` days earlier."""
    v = f"_previous_day{lead}"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join(f"{x}{v}" for x in ("wind_speed_10m", "rain", "showers", "snowfall")),
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "GMT",
    }
    if model != "best_match":
        params["models"] = model
    for attempt in range(4):
        r = client.get("https://previous-runs-api.open-meteo.com/v1/forecast", params=params)
        if r.status_code == 200:
            break
        time.sleep(2 * (attempt + 1))
    r.raise_for_status()
    h = r.json()["hourly"]
    out = {}
    for i, ts in enumerate(h["time"]):
        w, ra, sh, sn = (h[f"{x}{v}"][i] for x in ("wind_speed_10m", "rain", "showers", "snowfall"))
        if None in (w, ra, sh, sn):
            continue
        out[datetime.fromisoformat(ts).replace(tzinfo=UTC)] = (w, ra + sh, sn)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--model", default="best_match", help="Open-Meteo model id, e.g. ncep_nbm_conus")
    args = ap.parse_args()
    end = datetime.now(UTC).date() - timedelta(days=2)
    start = end - timedelta(days=args.days - 1)

    observed = {st: observations(st, start, end) for st in STATIONS}
    results = {}
    for lead in (1, 2):
        pairs = []  # (obs_wind, fc_wind, obs_rain, fc_rain, obs_snow, fc_snow)
        for st in STATIONS:
            obs, lat, lon = observed[st]
            if not obs:
                continue
            fc = forecasts(lat, lon, start, end, lead, args.model)
            for hour, (ow, orain, osnow) in obs.items():
                if hour in fc:
                    fw, frain, fsnow = fc[hour]
                    pairs.append((ow, fw, orain, frain, osnow, fsnow > 0))
        n = len(pairs)
        wind_match = Counter()
        wind_total = Counter()
        rain_match = Counter()
        rain_total = Counter()
        for ow, fw, orain, frain, *_ in pairs:
            lo, lf = classify_wind(ow), classify_wind(fw)
            wind_total[lo] += 1
            wind_match[lo] += lo == lf
            ro, rf = classify_rain(orain), classify_rain(frain)
            rain_total[ro] += 1
            rain_match[ro] += ro == rf
        within5 = sum(abs(ow - fw) <= 5 for ow, fw, *_ in pairs)
        mae = sum(abs(ow - fw) for ow, fw, *_ in pairs) / n
        rain_yes = [(orain >= RAIN_YES, frain >= RAIN_YES) for _, _, orain, frain, _, _ in pairs]
        snow_yes = [(os_, fs) for *_, os_, fs in pairs]
        hits = sum(o and f for o, f in rain_yes)
        misses = sum(o and not f for o, f in rain_yes)
        false_alarms = sum(f and not o for o, f in rain_yes)
        results[f"lead_{lead}_day"] = {
            "hours_compared": n,
            "stations": len(STATIONS),
            "model": args.model,
            "period": f"{start} to {end}",
            "wind_mae_mph": round(mae, 2),
            "wind_within_5mph_pct": round(100 * within5 / n, 1),
            "wind_level_match_pct": round(100 * sum(wind_match.values()) / n, 1),
            "wind_level_match_by_observed": {
                Risk(k).label: {"hours": wind_total[k], "match_pct": round(100 * wind_match[k] / wind_total[k], 1)}
                for k in sorted(wind_total)
            },
            "rain_level_match_pct": round(100 * sum(rain_match.values()) / n, 1),
            "rain_level_match_by_observed": {
                Risk(k).label: {"hours": rain_total[k], "match_pct": round(100 * rain_match[k] / rain_total[k], 1)}
                for k in sorted(rain_total)
            },
            "rain_yes_no_accuracy_pct": round(100 * sum(o == f for o, f in rain_yes) / n, 1),
            "rain_detection_pct": round(100 * hits / (hits + misses), 1) if hits + misses else None,
            "rain_false_alarm_pct": round(100 * false_alarms / (hits + false_alarms), 1)
            if hits + false_alarms
            else None,
            "snow_yes_no_accuracy_pct": round(100 * sum(o == f for o, f in snow_yes) / n, 1),
            "snow_hours_observed": sum(o for o, _ in snow_yes),
        }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"backtest_{args.model}.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
