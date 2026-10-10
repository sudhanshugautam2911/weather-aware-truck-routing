# Weather-Aware Truck Routing

A React + Django web app that helps a truck driver pick the safest route. It finds three routes, checks the
forecast **for the hour the truck will actually reach each checkpoint**, scores weather risk with the load
weight in mind, and recommends the route with the least risk, using travel time as the tie-breaker.

**Live app:** _add Vercel URL here_ · **Walkthrough:** _add Loom URL here_

---

## What it does

1. You enter origin, destination, departure time and load weight, and pick how often to check weather (every 10, 25 or 50 miles).
2. The backend gets **3 route options** from a truck routing API.
3. It places **checkpoints** along each route and works out the **ETA** at each one.
4. It fetches the **hourly forecast at each checkpoint for that ETA** and applies the risk table and load rules.
5. It ranks the routes and **explains the recommendation** in plain words ("Route A has 12 mi of Severe weather").
6. The map shows all routes, colour-coded checkpoints with ETAs and weather, and a **weather heatmap over the trip
   corridor with a 0–48 h slider**. A marker on each route shows where that truck would be at the chosen hour.

## How a trip is computed

```
origin, destination, departure, load
        │
        ▼
TomTom truck routing ──► 3 routes (polyline + distance and drive time along it)
        │                 fewer than 3? ask again through a point beside the main road
        ▼
checkpoints every N miles + destination ──► ETA = departure + drive time to that point
        │
        ▼
Open-Meteo hourly forecast (NBM model) at each checkpoint, for the hour of its ETA
        │
        ▼
risk = worst of wind (after load rules), rain, snow
        │
        ▼
rank routes: No Travel mi → Severe mi → High mi → average risk → travel time
```

## Risk rules (from the brief)

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind | < 25 mph | 25–34 | 35–44 | 45–54 | ≥ 55 |
| Rain | < 0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow | < 0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

Load rules: ≥ 55 mph is No Travel for any load. 45–54 mph with more than 30,000 lb is No Travel. 35–44 mph with more than 40,000 lb is Severe.

All of this lives in one small pure-Python module, [`backend/core/risk.py`](backend/core/risk.py), with no Django or network code in it.

### Decisions where the brief is open

| Question | Decision | Why |
|---|---|---|
| Edges overlap (rain 0.25 is in Moderate *and* High) | Lower bound is inclusive: 0.25 → High. The top of rain/snow follows the brief's "> 1.00" / "> 3.0", so 1.00 is still Severe | One clear rule, applied the same way everywhere |
| No Travel isn't in the ranking rules | Ranked first: fewest **No Travel** miles, then the brief's four rules | A route you must not drive can never beat one you can |
| "Average risk" | Low 0 … No Travel 4, averaged **by miles** | Long stretches count more than short ones |
| Miles at each level | Each checkpoint covers the road halfway to its neighbours | Miles add up exactly to the route length |
| Which forecast hour for an ETA | Wind: the nearest hour. Rain/snow: the hour that contains the ETA | Open-Meteo stores rain/snow at the **end** of each hour (14:00 = 13:00–14:00), so 13:40 uses 14:00 |
| Rain | `rain + showers` | Open-Meteo's `rain` alone leaves out shower rain and would under-count risk |
| Wind | Sustained 10 m wind for the rules; gusts shown as extra info | The table says "wind"; sustained is the standard measure |
| Checkpoint spacing | User picks 10 / 25 / 50 mi (default 25) | The brief lists all three |
| Heatmap hour 0 | The departure hour | The slider follows the trip, not the clock |
| Departure window | From now up to 7 days ahead | Forecasts further out aren't reliable enough to judge risk |
| Truck weight for routing | Load + 35,000 lb typical empty tractor-trailer, sent to TomTom | TomTom needs gross weight to avoid weight-limited roads |
| Truck speed | Capped at 65 mph (`TRUCK_MAX_SPEED_MPH`) | Tested: without a cap, TomTom's truck mode gave exactly the car times (73 mph average Chicago → Denver). Fleet trucks are usually governed near 65 mph; with the cap, trips average 63–64 mph |

## Accuracy

Accuracy has two parts, so it is reported in two parts.

### 1. Our logic: proven by tests

| Check | Result |
|---|---|
| Every cell and edge of the risk table and load rules (incl. exactly 30,000 / 40,000 lb) | All pass |
| Random-input rules (Hypothesis, 15,000+ cases): more wind or a heavier load never lowers risk; final risk = worst condition | All pass |
| Route ranking against hand-worked examples, ties at every rule, floating-point noise | All pass |
| Checkpoints: exact spacing, on the route, ETA at constant speed, **miles add up exactly** for random route lengths | All pass |
| ETA → forecast-hour matching, time zones, gaps in data | All pass |
| API: validation messages, upstream failures, end-to-end plan with fake providers | All pass |
| **Total** | **121 backend tests, 100% branch coverage of the risk engine** (`core/` overall 95%) |

### 2. Outside data: measured

**Forecast backtest** ([`backend/accuracy/backtest.py`](backend/accuracy/backtest.py)): what the model predicted 1 day
earlier vs. what 24 airport weather stations actually observed, hour by hour, over 30 days (16,655 hours, Sep 9 – Oct 8 2026).
The same backtest picked the forecast model:

| 1 day ahead | Default (GFS/HRRR) | **NBM (used)** |
|---|---|---|
| Wind: average error | 3.01 mph | **2.73 mph** |
| Wind: within ±5 mph | 82.4% | **85.9%** |
| Wind: hours that really were Moderate, forecast as Moderate | 17.8% | **44.6%** |
| Rain: hours with rain that the forecast caught | 36% | **72%** |
| Rain: forecast rain hours that stayed dry (false alarms) | 53% | 69% |

NBM catches twice as many rainy hours at the cost of more false alarms. For a safety tool, a missed storm is worse than a
cautious warning, so the app uses NBM, with the global model filling any gaps (points outside the lower 48 states).

Honest limits of the backtest:
- Most hours were calm, so "overall match" (~99%) is easy. The per-level numbers above are the meaningful ones.
- Rain at an exact place and hour is hard to forecast. Showers are often a little early or late, or a few miles off.
- No snow fell in this 30-day window, and stations don't measure snowfall per hour, so snow was not tested in inches.

**Live checks** ([`backend/accuracy/checks.py`](backend/accuracy/checks.py), 4 long US trips, TomTom truck routing):

| Check | Result |
|---|---|
| Our checkpoint ETA vs. TomTom's own time for a trip ending at that checkpoint | **0.31 min average difference (0.08%)** over 10 checkpoints 200–770 miles in. Two more were skipped because TomTom's direct trip used a different road, so the times weren't comparable |
| Our wind vs. the US National Weather Service forecast at the same checkpoint and hour | **1.2 mph average difference, same risk level at 99.8%** of 409 checkpoints (NBM is the NWS's own blend, so this mainly confirms we read the right place, hour and units) |
| Same recommendation at 10, 25 and 50 mi checkpoint spacing | 4 of 4 trips on this run. On an earlier run with scattered showers (Dallas → Atlanta), coarse spacing changed the pick, so **10 mi is the safest choice when weather is patchy** |

Results are saved in [`backend/accuracy/results/`](backend/accuracy/results/).

### Safeguards in the code
- **Units are checked** on every weather response (mph and inch); anything else is rejected rather than silently mixed in.
- **All time maths is in UTC**; times are converted to the viewer's zone only for display.
- **Missing forecast data never becomes "Low risk"**: the user gets a clear error instead.

## Tech stack

| Part | Choice |
|---|---|
| Backend | Python 3.12+, Django 6.1, Django REST Framework, httpx |
| Frontend | React 19, TypeScript, Vite 8, MapLibre GL (WebGL map) via react-map-gl |
| Routing + place search | TomTom (truck profile with weight). Without a key, a free demo router (OSRM) and geocoder (Photon) are used so the app still runs |
| Weather | Open-Meteo, NBM model (no key) |
| Map tiles | OpenFreeMap (no key) |
| Database | None. Nothing is stored. Forecasts are cached for 1 hour (in memory, or Redis if `REDIS_URL` is set) |
| Hosting | Vercel: static frontend + Django as a Python function, one domain |

### Why the slider is smooth
The heatmap loads once: about 200 corridor cells × 49 hours. Every hour's value is stored on each cell, so moving the
slider only changes **which value the map reads** (a GPU paint update). There is no network call and no data re-upload.
Cells snap to a fixed grid, so nearby trips share cached forecasts.

## Project layout

```
backend/
  core/        risk rules, route geometry, ETA→forecast matching   (pure Python, fully tested)
  providers/   TomTom / OSRM routing, place search, Open-Meteo client (chunking, retries, cache, unit checks)
  api/         Django REST endpoints + trip planning service
  accuracy/    backtest and live checks; results/ holds the numbers above
  tests/       121 tests
frontend/
  src/components/   form, place search, results, ranking table, map, time slider
  src/lib/          formatting, plain-language explanations, geometry
api/index.py   Vercel entry point for Django
vercel.json    build + routing for one-domain deploy
```

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Status and which providers are active |
| `GET /api/geocode?q=dallas` | Place suggestions |
| `POST /api/plan` | `{origin, destination, departure, load_lb, interval_mi}` → routes, checkpoints, risk, recommendation |
| `POST /api/heatmap` | `{lines, departure, load_lb}` → corridor cells × 49 hourly values |

Errors always look like `{"error": {"code", "message", "field?"}}`. The message is written for the driver, and `field`
tells the form which input to highlight.

## Run locally

```bash
# backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env            # add TOMTOM_API_KEY (optional; demo routing is used without it)
.venv/bin/python manage.py runserver 8000

# frontend (second terminal)
cd frontend
npm install
npm run dev                     # http://localhost:5173, proxies /api to :8000
```

Tests:

```bash
cd backend && .venv/bin/python -m pytest tests --cov=core --cov-branch
cd frontend && npm test
```

Accuracy scripts (they call real services and take a few minutes):

```bash
cd backend && .venv/bin/python -m accuracy.backtest --days 30 --model ncep_nbm_conus
cd backend && .venv/bin/python -m accuracy.checks
```

## Deploy (Vercel)

1. Import the GitHub repo in Vercel (framework preset: **Other**; `vercel.json` sets the build).
2. Environment variables: `TOMTOM_API_KEY`, `DJANGO_SECRET_KEY` (any long random string), `DJANGO_DEBUG=0`,
   optional `REDIS_URL` (Upstash, free) so all function instances share the forecast cache.
3. Deploy. The frontend is served from `frontend/dist`, and `/api/*` goes to the Django function.

## Known limits

- Forecasts are forecasts: see the backtest for how often they are right at an exact place and hour.
- "Average risk" is averaged over miles, so on a much longer route the same bad stretch counts for less.
  This follows the brief's wording, and it only matters when Severe and High miles are already tied.
- Driver rest breaks (hours-of-service rules) are not modelled, so ETAs assume continuous driving.
