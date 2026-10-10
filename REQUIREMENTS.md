# Weather-Aware Truck Routing — Requirements

Source: [docs/fs-assessment-spotter.pdf](docs/fs-assessment-spotter.pdf) (Full Stack Developer take-home assessment, 2 pages).

> **Status (2026-10-10):** built end to end; see [README.md](README.md) for how it works and the measured accuracy.
> Decisions D1–D10 below were applied as proposed (D10 settled by the backtest). The app runs on free demo routing
> until a TomTom key is added.

## 1. The idea

A truck driver wants to go from A to B. Bad weather (strong wind, heavy rain, heavy snow) is dangerous,
and it is **more** dangerous when the truck is carrying a heavy load.

The app finds 3 possible routes, checks the weather along each route **at the time the truck will
actually be there**, scores each route for risk, and recommends the safest one. Everything is shown on a map.

**Stack (fixed by the brief):** React frontend + Django backend.
Third-party APIs are allowed for routing, geocoding (turning an address into lat/lng), and weather.
You do **not** build your own routing engine.

## 2. Inputs (what the user types)

| Input | Notes |
|---|---|
| Origin | Address / city → geocoded to lat/lng |
| Destination | Same |
| Departure date & time | Can be in the future; must fall inside the weather API's forecast window |
| Load weight | In pounds (the load rules use lb) |

## 3. What the app must do

1. **Get 3 route options** from a routing API.
2. **Place checkpoints** along each route every **10 / 25 / 50 miles**.
3. **Work out the ETA** (estimated arrival time) at each checkpoint = departure time + driving time to that point.
4. **Fetch the weather forecast for that place at that ETA** (not "weather right now").
5. **Classify risk** at each checkpoint using the risk table + load rules (section 4).
6. **Recommend the best route** using the ranking rules (section 5).
7. **Map view** showing: all 3 routes, checkpoints, risk level per checkpoint, ETAs, and a summary per route.
8. **Weather heatmap** along the trip corridor (the band of land around the routes), with a **slider for 0–48 hours** of forecast.

## 4. Risk rules

### 4.1 Weather table (per checkpoint)

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind | < 25 mph | 25–34 | 35–44 | 45–54 | ≥ 55 mph |
| Rain | < 0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow | < 0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

### 4.2 Load rules (make wind risk worse for heavy trucks)

- Wind ≥ 55 mph → **No Travel**, any load.
- Wind 45–54 mph **and** load > 30,000 lb → **No Travel** (instead of Severe).
- Wind 35–44 mph **and** load > 40,000 lb → **Severe** (instead of High).

### 4.3 Checkpoint risk = the worst of wind, rain, snow (after load rules)

Example: wind 47 mph, rain 0.05 in/hr, no snow, load 35,000 lb
→ wind table says Severe → load rule bumps it to **No Travel** → checkpoint = **No Travel**.

Example: wind 38 mph, load 42,000 lb → table says High → load rule bumps to **Severe**.

## 5. Route recommendation

Compare routes in this strict order; move to the next rule only when there is a tie:

1. Fewest **Severe** miles
2. Fewest **High** miles
3. Lowest **average risk**
4. Shortest **travel time**

"Severe miles" = total length of route segments whose checkpoint is Severe.

Example: Route A has 0 Severe mi, 50 High mi, 6 h. Route B has 0 Severe mi, 25 High mi, 6.5 h.
→ **B wins** (fewer High miles), even though it is slower. Time only decides when risk is tied.

## 6. Deliverables

- GitHub repository
- Hosted (live) application
- 5–10 minute Loom video walkthrough

## 7. How it is graded

| Weight | Area | What this means for us |
|---|---|---|
| **40%** | Routes, weather, risk & recommendation logic | The core. Must be correct and unit-tested. |
| **35%** | UI, map & heatmap smoothness and performance | Slider must feel instant; map must not lag. |
| 10% | Code quality | Clean structure, clear names. |
| 5% | Documentation & walkthrough | README + Loom. |

> "Prioritize correctness and clarity over extra features."

(The weights add to 90% — the PDF does not say what the last 10% is. Worth asking.)

## 8. Gaps & ambiguities in the brief (with our default choice)

| # | Unclear point | Our default |
|---|---|---|
| 1 | "Every 10 / 25 / 50 miles" — pick one, or let the user choose? | User picks the interval (dropdown, default 25 mi). |
| 2 | Boundary values overlap (e.g. rain 0.25 is in both Moderate and High). | Lower bound inclusive: 0.10 ≤ x < 0.25 = Moderate, 0.25 ≤ x < 0.50 = High, 0.50 ≤ x ≤ 1.00 = Severe, > 1.00 = No Travel. Same for snow. Wind: fractional values like 34.6 count as < 35. |
| 3 | Recommendation rules do not mention **No Travel**. | Any route with No Travel miles ranks below every route without them (fewest No Travel miles becomes rule 0). If all routes have No Travel, show a clear "do not travel / delay departure" warning. |
| 4 | How to compute "average risk". | Score Low=0, Moderate=1, High=2, Severe=3, No Travel=4; average weighted by miles. |
| 5 | Wind = sustained speed or gusts? | Sustained wind for the rule; show gusts as extra info. |
| 6 | Heatmap 0–48 h — from **now** or from **departure**? And heatmap of what? | Hours from departure time; colour = combined risk level (same scale as checkpoints). |
| 7 | Routing APIs may return fewer than 3 alternatives on some trips. | Show what is returned and say so; optionally force alternates via via-points. |
| 8 | Car vs truck speeds. | Use a truck (HGV) routing profile if the API has one, so ETAs are realistic. |
| 9 | Driver rest breaks (legal driving-hour limits) for long trips. | Not required — ignore; mention in README as a possible extension. |
| 10 | Departure date beyond the forecast range. | Validate on input and show an error. |

## 9. External services (checked against official docs + real API calls on 2026-10-10)

### 9.1 What we will use

| Need | Service | Key / account | Free limit | Why this one |
|---|---|---|---|---|
| **Routing (3 routes)** | **TomTom Routing API** | Free key, **no card** | 20,000 req/month | Real truck mode with `vehicleWeight`; up to 5 alternatives with no distance limit; returns **travel time at points along the line** (`extendedRouteRepresentation=travelTime`) → exact ETA per checkpoint |
| Routing fallback | HERE Routing v8 | Key, card needed | ~5K truck req/month | Strongest truck support; per-segment durations. Only if TomTom fails us |
| **Geocoding + autocomplete** | **TomTom** (same key) | — | Geocoding 20K/mo, Suggest 10K/mo | One key for everything; debounce typing |
| **Weather forecast** | **Open-Meteo** | None | 10,000 calls/day, 600/min, **non-commercial** (fine for an assessment), must show attribution | Hourly to 16 days; returns mph + inches; many points in one request |
| Weather cross-check (B2) | NWS `api.weather.gov` | None (needs `User-Agent` header) | Not published | Official US forecast; second opinion on wind/precip |
| Backtest forecasts (B3) | Open-Meteo **Previous Runs API** | None | Same as above | Gives what the model forecast 1–7 days before a past hour |
| Backtest truth (B3) | **IEM ASOS** (airport weather stations) | None | — | Real observed hourly wind + rain at airports, years of history |
| Basemap tiles | **OpenFreeMap** (Positron style) | None | No limits | No key → graders can never hit a quota block |

### 9.2 Rejected (and why)

| Service | Reason |
|---|---|
| OpenRouteService | **Alternative routes only work for trips < 100 km** — useless for truck trips of 300+ miles |
| GraphHopper (free) | No truck profile on free plan; non-commercial only |
| Google Routes | Truck mode needs Google's approval; billing must be on; must use Google Maps for display |
| Mapbox Directions | No real truck profile; at most 3 routes, not guaranteed |
| OSM's own tile server | Best-effort only, can block apps without notice |

### 9.3 Facts we confirmed with real calls (these shape the code)

- **Open-Meteo units:** with `wind_speed_unit=mph&precipitation_unit=inch`, wind comes back as `"mp/h"` and rain/snow as `"inch"`. Snowfall is **snow depth** in inches (not water) — matches the brief's "in/hr" of snow.
- **Hourly value = total of the *preceding* hour.** The 14:00 value covers 13:00–14:00. So a truck at a checkpoint at 13:40 uses the **14:00** value (the hour that contains the ETA).
- **Rain = `rain` + `showers`.** Open-Meteo's `rain` alone leaves out shower rain → would under-count risk.
- **Default US model:** `best_match` = HRRR (3 km, very accurate, first ~18–48 h) then GFS. Option: NBM (`ncep_nbm_conus`, NWS blend, ~11 days but switches to 3–6 h steps after ~1 day). **Pick the model with the backtest (B3), not by guess.**
- **Open-Meteo was slow and flaky in testing:** 25 points ≈ 14 s, 100 points ≈ 30–44 s, and some calls got `503 overloaded`. A 500-point request costs ~500 "calls" against the daily limit. → Biggest performance risk; see 9.4.
- **NWS:** wind in km/h, rain/snow in mm and only as **6-hour totals**, time blocks of uneven length → good for wind cross-check, coarse for precip.
- **IEM ASOS:** has hourly wind and rain, but **no snow amount** (only "is it snowing: yes/no"). So snow accuracy can only be checked as yes/no.
- **Alternatives are "not guaranteed" by every provider.** If fewer than 3 come back, re-ask with a forced via-point to create a different route.

### 9.4 How we keep weather fast and within limits

- **Snap heatmap grid points to a fixed lattice** (e.g. every 0.25°). Nearby trips reuse the same points → cache hits.
- **Send POST requests in chunks of ~50 points, in parallel**, retry on 503 with backoff.
- **Cache weather by (lattice point, model run hour)** on the backend — forecasts only change once per hour.
- **Load checkpoints first** (small, fast), heatmap after (bigger), so the map is useful in seconds.
- Keep the heatmap grid modest (~100–200 points per trip); measure before going bigger.
- If the free tier is still too slow, Open-Meteo has a paid API plan — decide after measuring.

## 10. Key technical points (where marks are won or lost)

- **ETA-based weather**: each checkpoint uses the forecast hour matching its ETA — this is the heart of the 40%.
- **Batch weather calls**: fetch all checkpoints (and heatmap grid points) in as few requests as possible; cache on the backend.
- **Smooth slider**: load all 49 hours of heatmap data once; moving the slider only re-colours the layer — no new network call.
- **Keep API keys on the Django side**; the frontend only talks to our backend.
- **Unit tests** for the risk table edges, load rules, and route ranking.

## 11. Accuracy plan (top priority)

"Accuracy" has two different parts. We never quote one single "the app is X% accurate" number.

| Part | Who controls it | How we show it |
|---|---|---|
| **Our logic** — risk rules, checkpoints, ranking | Us | **Prove** it: tests → 100% correct |
| **Outside data** — forecasts, drive times | APIs | **Measure** it: real percentages |

### 11.1 Prove our logic is correct

| # | Check | What we can claim |
|---|---|---|
| A1 | **Table tests** — one test per cell of the risk table, every boundary (24.9 / 25 / 34.9 / 35 …), every load rule incl. exactly 30,000 and 40,000 lb | "All N rule tests pass; 100% branch coverage of the risk engine" |
| A2 | **Property tests** (Hypothesis library, random inputs): more wind never lowers risk; heavier load never lowers risk; final risk ≥ each single condition's risk | "Rules hold for 10,000+ random inputs" |
| A3 | **Ranking tests** — hand-worked fake routes with a known winner, incl. ties at every rule level | "Recommendation matches the spec in every case" |
| A4 | **Checkpoint geometry** — spacing between checkpoints = chosen interval (± small error); every checkpoint lies on the route line; risk miles add up to the route length | "Max spacing error X m; mileage sums exactly" |

### 11.2 Measure the outside data

| # | Check | Example output (real numbers come after we build it) |
|---|---|---|
| B1 | **ETA check** — ask the routing API for origin → checkpoint directly, compare with our interpolated ETA | "Checkpoint ETAs within ~N min on average (N%)" |
| B2 | **Cross-source weather** — compare primary forecast with a second source at the same places/hours | "Same risk level at N% of checkpoints" |
| B3 | **Backtest** — past forecasts vs what actually happened, by lead time (0–12 h, 12–24 h, 24–48 h) | "24 h ahead: risk level matched reality N% of the time" |
| B4 | **Sampling sensitivity** — same trip at 10 vs 50 mi spacing | "50 mi spacing missed N% of high-risk miles found at 10 mi" |

**Trap:** most weather is Low risk, so "matches" look easy. Report results **per risk level** (especially High and above), not just one overall %.

### 11.3 Silent accuracy killers (rules for the code)

- **Time zones:** all time maths in UTC; convert only for display. Trucks cross time zones.
- **Units:** request mph and inches explicitly; assert the units in the API response.
- **Between forecast hours:** truck arrives 10:40 but data is hourly → pick one rule (nearest hour vs blend 10:00/11:00) and document it.
- **Truck vs car speed:** use a truck routing profile so ETAs are realistic.

### 11.4 How we present it

- README "Accuracy" section: test results + measured percentages + method.
- In the app: a **"Why this route?"** table showing each ranking rule's values per route.
- ~1 minute of the Loom on accuracy (it's worth 40% of the grade).

## 12. Tech stack (versions checked 2026-10-10)

### 12.1 Backend — Django

| Piece | Choice | Version | Why |
|---|---|---|---|
| Language | Python | 3.14 (installed locally) | Django 6.1 supports 3.12–3.14. **Not 3.15** (just released, not yet supported by Django) |
| Framework | Django + Django REST Framework | 6.1.2 / 3.18.3 | Required by the brief; DRF for clean JSON APIs |
| CORS | django-cors-headers | 4.9.0 | Frontend and backend live on different domains |
| HTTP client | httpx | latest | Parallel calls (async) + timeouts + retries for Open-Meteo/TomTom |
| Distance maths | geographiclib | latest | Exact distance on the Earth's real shape (WGS84), not the rougher "perfect sphere" formula → accurate checkpoint spacing |
| Cache | Django locmem cache | built-in | Enough on one always-on server. Switch to Upstash Redis (free) only if we go serverless |
| Tests | pytest + pytest-django + Hypothesis + coverage | latest | A1–A4 accuracy proofs |
| Server | gunicorn | 26.2.0 | 1 worker + threads (so all requests share one cache) |
| Database | **None** | — | Nothing needs to be saved. Keeps it simple |

Code layout idea — the **risk engine is plain Python with no Django inside**, so it is easy to test and read:

```
backend/
  risk/       # risk table, load rules, route ranking  (pure functions, 100% tested)
  routing/    # TomTom client, checkpoint placement, ETA per checkpoint
  weather/    # Open-Meteo client, chunking, cache, ETA→forecast-hour matching
  api/        # DRF views: /api/plan, /api/heatmap, /api/geocode, /api/health
  accuracy/   # backtest + cross-check scripts (B1–B4), output goes to README
```

### 12.2 Frontend — React

| Piece | Choice | Version | Why |
|---|---|---|---|
| Framework | React + Vite + TypeScript | 19.3 / 8.3 / (as Vite template pins) | Required (React); Vite = fast builds; TS catches mistakes. TS 7 is brand new — if tooling breaks, pin the older line |
| Map | **MapLibre GL JS** via react-map-gl | 6.13.0 / 8.1.3 | GPU (WebGL) map: routes, checkpoints, heatmap all on one map |
| Basemap | OpenFreeMap Positron | — | Light, plain style → risk colours stand out |
| Tests | Vitest | latest | Small UI logic tests |

**Heatmap approach (important for both accuracy and smoothness):**
- MapLibre's built-in "heatmap" layer **adds up** overlapping points (more points = hotter). That would show *point density*, not *weather risk* → misleading.
- Instead: draw the corridor as **coloured grid cells**, colour = risk level at that hour. All 49 hours are stored on each cell (`r0 … r48`); the slider only changes which property is read (`setPaintProperty`). **No network call, no data re-upload** → instant slider.

## 13. Deployment

> **Decided (2026-10-10): everything on Vercel ($0).** Frontend as a static site, Django as Vercel Python functions.
> Defaults in section 15.1 accepted. TomTom key comes later; build key-free parts first.
> To verify when we deploy: Vercel function time limit vs slow Open-Meteo calls, and whether we need Upstash Redis (free) for a shared cache.

| Part | Where | Cost | Notes |
|---|---|---|---|
| Frontend | **Vercel** | $0 | Add a rewrite to `index.html` for SPA routes. Only `VITE_*` vars reach the browser → **no secrets in the frontend** |
| Backend | **Fly.io**, 512 MB, always on | **~$3.69/month**, card needed | Never sleeps → graders never wait. Needs a Dockerfile (Docker is installed) |
| Backend (easier, pricier) | Render Starter | $7/month | No Docker needed |
| Backend ($0 option) | Vercel Python functions + Upstash Redis | $0 | First request after idle loads Django (slower); needs Redis for cache |
| Avoid | Render free (≈1 min wake-up), Koyeb free (sleeps after 1 h), PythonAnywhere free (blocks outside APIs), Netlify free (each deploy uses 15 of 300 credits) | | |

Extra: the frontend pings `/api/health` when the page opens, so the backend is warm by the time the user submits the form.

## 14. Accounts & keys you need to create (I can't create accounts for you)

| # | Account | Needed for | Card? |
|---|---|---|---|
| 1 | **TomTom Developer** → API key | Routing + geocoding | No |
| 2 | **Fly.io** (or Render) | Backend hosting | Yes (Fly) |
| 3 | **Vercel** (sign in with GitHub) | Frontend hosting | No |
| 4 | GitHub repo | Deliverable | Already logged in (`gh`) |
| 5 | Loom | Walkthrough video | No |
| — | Open-Meteo, NWS, IEM, OpenFreeMap | Weather, tiles | **No account needed** |
| opt | HERE Developer | Only if TomTom fails | Yes |

Keys live in a `.env` file on the backend only (never committed; a `.env.example` is committed instead).

## 15. Pre-code checklist — decisions & risks

### 15.1 Decisions to confirm

| # | Decision | Proposal |
|---|---|---|
| D1 | Checkpoint interval | User picks 10 / 25 / 50 mi (default 25) |
| D2 | Boundary values | Lower bound inclusive (section 8 #2) |
| D3 | No Travel in ranking | Rule 0: fewest No Travel miles; warn if every route has some |
| D4 | Average risk | Low 0 … No Travel 4, weighted by miles |
| D5 | Miles per checkpoint | Each checkpoint "owns" the stretch halfway to its neighbours, so miles add up exactly to the route length |
| D6 | Forecast hour at ETA | Use the hour **containing** the ETA (13:40 → 14:00 value) — matches how Open-Meteo stores data |
| D7 | Wind | Sustained 10 m wind for rules; gusts shown as info |
| D8 | Heatmap time | Hours 0–48 counted from departure |
| D9 | Departure window | Now → +7 days; reject if any checkpoint ETA falls outside forecast data |
| D10 | Weather model | **Decided: NBM** (`ncep_nbm_conus`), with `best_match` filling gaps. 30-day backtest: wind error 2.73 vs 3.01 mph, rain detection 72% vs 36% (see README) |

### 15.2 Risks

| Risk | Impact | Plan |
|---|---|---|
| Open-Meteo slow / 503 | Hurts the 35% performance grade | Section 9.4 (lattice + chunks + cache + retry); measure early |
| TomTom alternatives on long truck trips — docs say OK, **not yet tested with a real call** | Core requirement | **First task once you have the key:** one real 1,000-mile truck request with alternatives + travel-time points |
| Fewer than 3 routes returned | Core requirement | Via-point retry, then show what we have with a clear note |
| Snow can't be backtested in inches | Accuracy report gap | Report snow as yes/no accuracy and say so honestly |
| PDF grading weights add to 90% | Unknown 10% | Ask the recruiter if possible |
| TomTom terms on storing results not confirmed | Cache legality | Cache routes only briefly (minutes); re-check terms |

### 15.3 Build order (once the above is confirmed)

1. TomTom smoke test (risk #2) → confirms the whole plan works.
2. Risk engine + its tests (pure Python, A1–A3) — 40% of the grade, no API needed.
3. Routing → checkpoints → ETA (A4, B1).
4. Weather fetch + cache → checkpoint risk → recommendation → `/api/plan`.
5. Frontend: form, map, routes, checkpoints, summaries, "Why this route?" table.
6. Heatmap + slider (measure smoothness).
7. Accuracy scripts (B2–B4), README, deploy, Loom.
