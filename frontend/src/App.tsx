import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, fetchHeatmap, planTrip, warmUp } from './api'
import { CheckpointList } from './components/CheckpointList'
import { MapView, type HeatMetric } from './components/MapView'
import { Notice } from './components/Notice'
import { RankingTable } from './components/RankingTable'
import { RouteList } from './components/RouteList'
import { TimeBar } from './components/TimeBar'
import { TripForm } from './components/TripForm'
import { Verdict } from './components/Verdict'
import { verdict } from './lib/explain'
import { formatDayTime, formatNumber, toLocalInput } from './lib/format'
import { validate, type FieldErrors } from './lib/validate'
import type { HeatmapResponse, PlanResponse, TripInput } from './types'

const EXAMPLE: Pick<TripInput, 'origin' | 'destination' | 'load_lb'> = {
  origin: { label: 'Chicago, IL, USA', lat: 41.8781, lon: -87.6298 },
  destination: { label: 'Denver, CO, USA', lat: 39.7392, lon: -104.9903 },
  load_lb: '38000',
}

const defaultTrip = (): TripInput => ({
  origin: null,
  destination: null,
  departure: toLocalInput(new Date(Date.now() + 60 * 60_000)),
  load_lb: '',
  interval_mi: 25,
})

type HeatState = { status: 'idle' | 'loading' | 'ready' | 'error'; data: HeatmapResponse | null; error?: string }

export default function App() {
  const [trip, setTrip] = useState<TripInput>(defaultTrip)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [loading, setLoading] = useState(false)
  const [planError, setPlanError] = useState<ApiError | null>(null)
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [planned, setPlanned] = useState<TripInput | null>(null)
  const [editing, setEditing] = useState(true)
  const [selected, setSelected] = useState('')
  const [focusedCp, setFocusedCp] = useState<number | null>(null)
  const [heat, setHeat] = useState<HeatState>({ status: 'idle', data: null })
  const [hour, setHour] = useState(0)
  const [metric, setMetric] = useState<HeatMetric>('risk')
  const planCtrl = useRef<AbortController | null>(null)
  const heatCtrl = useRef<AbortController | null>(null)
  const formTop = useRef<HTMLDivElement>(null)

  useEffect(warmUp, [])

  const loadHeat = useCallback((p: PlanResponse) => {
    heatCtrl.current?.abort()
    const ctrl = new AbortController()
    heatCtrl.current = ctrl
    setHeat({ status: 'loading', data: null })
    fetchHeatmap(
      { lines: p.routes.map((r) => r.geometry.coords), departure: p.meta.departure, load_lb: p.meta.load_lb },
      ctrl.signal,
    )
      .then((data) => setHeat({ status: 'ready', data }))
      .catch((err) => {
        if ((err as Error).name === 'AbortError') return
        setHeat({
          status: 'error',
          data: null,
          error: err instanceof ApiError ? err.message : 'The weather layer could not load.',
        })
      })
  }, [])

  const submit = useCallback(async () => {
    const found = validate(trip)
    setErrors(found)
    if (Object.keys(found).length) {
      const first = Object.keys(found)[0]
      const el = document.querySelector<HTMLElement>(
        first === 'origin' || first === 'destination' ? `input[name="${first}"]` : first === 'load_lb' ? '#load' : `#${first}`,
      )
      el?.focus()
      return
    }
    planCtrl.current?.abort()
    const ctrl = new AbortController()
    planCtrl.current = ctrl
    setLoading(true)
    setPlanError(null)
    try {
      const result = await planTrip(
        {
          origin: trip.origin!,
          destination: trip.destination!,
          departure: new Date(trip.departure).toISOString(),
          load_lb: Number(trip.load_lb.replace(/,/g, '')),
          interval_mi: trip.interval_mi,
        },
        ctrl.signal,
      )
      setPlan(result)
      setPlanned(trip)
      setSelected(result.recommendation.route_id)
      setFocusedCp(null)
      setHour(0)
      setEditing(false)
      loadHeat(result)
      // On phones the map sits above the panel: bring it into view.
      if (window.matchMedia('(max-width: 899px)').matches) window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) {
      if ((err as Error).name === 'AbortError') return
      const e = err instanceof ApiError ? err : new ApiError('UNKNOWN', 'Something went wrong. Try again.', 0)
      const fieldMap: Record<string, keyof FieldErrors> = {
        origin: 'origin',
        destination: 'destination',
        departure: 'departure',
        load_lb: 'load_lb',
        interval_mi: 'interval_mi',
      }
      if (e.field && fieldMap[e.field]) {
        setErrors({ [fieldMap[e.field]]: e.message })
        setEditing(true)
      } else {
        setPlanError(e)
      }
    } finally {
      if (planCtrl.current === ctrl) setLoading(false)
    }
  }, [trip, loadHeat])

  const selectRoute = (id: string) => {
    setSelected(id)
    setFocusedCp(null)
  }

  // After a failed attempt, keep the old results out of view until the user goes back to them.
  const shown = planError ? null : plan
  const selectedRoute = plan?.routes.find((r) => r.id === selected) ?? null
  const best = plan?.routes.find((r) => r.recommended) ?? null

  return (
    <div className="app">
      <aside className="panel" aria-label="Trip planner">
        <header className="brand">
          <svg width="30" height="32" viewBox="0 0 30 32" aria-hidden="true">
            <path d="M2 2h26v13.5c0 8.2-6.2 12.8-13 15.4C8.2 28.3 2 23.7 2 15.5z" fill="#fff" />
            <path d="M9 23l6-14 6 14" fill="none" stroke="#0f5e3f" strokeWidth="2.8" strokeLinejoin="round" />
          </svg>
          <div>
            <h1>Weather-Aware Truck Routing</h1>
            <p>Three routes, checked against the forecast for when you will drive them</p>
          </div>
        </header>

        <div className="section" ref={formTop}>
          {editing || !plan ? (
            <>
              <TripForm value={trip} onChange={setTrip} errors={errors} onSubmit={submit} loading={loading} />
              {plan && !loading && (
                <button
                  type="button"
                  className="linklike"
                  style={{ marginTop: 10 }}
                  onClick={() => {
                    setPlanError(null)
                    setEditing(false)
                  }}
                >
                  Back to current results
                </button>
              )}
            </>
          ) : (
            <div className="trip-summary">
              <div className="route-line">
                {planned?.origin?.label} to {planned?.destination?.label}
              </div>
              <button type="button" className="btn btn-quiet" onClick={() => setEditing(true)}>
                Edit trip
              </button>
              <div className="details num">
                Leaving {formatDayTime(plan.meta.departure)}, {formatNumber(plan.meta.load_lb)} lb load, weather every{' '}
                {plan.meta.interval_mi} mi
              </div>
            </div>
          )}
          {!plan && !loading && editing && (
            <p className="hint" style={{ marginTop: 12 }}>
              New here?{' '}
              <button
                type="button"
                className="linklike"
                onClick={() => setTrip((t) => ({ ...t, ...EXAMPLE }))}
              >
                Fill in an example trip
              </button>{' '}
              from Chicago to Denver.
            </p>
          )}
        </div>

        {(planError || (plan && plan.warnings.length > 0)) && (
          <div className="section notices">
            {planError && (
              <Notice
                tone="error"
                title="Could not plan this trip"
                action={planError.status === 0 || planError.status >= 500 ? { label: 'Try again', onClick: submit } : undefined}
              >
                {planError.message}
              </Notice>
            )}
            {!planError &&
              plan?.warnings.map((w) => (
                <Notice key={w.code} tone={w.code === 'ALL_NO_TRAVEL' ? 'error' : w.code === 'DEMO_ROUTING' ? 'info' : 'warn'}>
                  {w.message}
                </Notice>
              ))}
          </div>
        )}

        {plan && best && !planError && (
          <>
            <Verdict plan={plan} best={best} />
            <RouteList routes={plan.routes} selected={selected} onSelect={selectRoute} />
            <RankingTable plan={plan} />
            {selectedRoute && (
              <CheckpointList
                route={selectedRoute}
                loadLb={plan.meta.load_lb}
                focused={focusedCp}
                onFocus={setFocusedCp}
              />
            )}
          </>
        )}

        <footer className="footer">
          <p>
            Weather: <a href="https://www.weatherapi.com/">WeatherAPI.com</a> and{' '}
            <a href="https://open-meteo.com/">Open-Meteo</a> (CC BY 4.0). Map:{' '}
            <a href="https://openfreemap.org/">OpenFreeMap</a>, <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>.
          </p>
          {plan && (
            <p>
              Routing: {plan.meta.truck_aware ? 'TomTom truck routing' : 'OSRM demo (car)'}. Forecast:{' '}
              {plan.meta.weather_sources.join(', then ')}.
              Checked {formatDayTime(plan.meta.generated_at)}.
            </p>
          )}
        </footer>
      </aside>

      <p className="visually-hidden" aria-live="polite">
        {loading ? 'Checking routes and weather.' : best && plan && !planError ? verdict(plan, best).headline : ''}
      </p>

      <main className="map-area" aria-label="Map">
        <div className="map-canvas">
        <MapView
          plan={shown}
          selected={selected}
          onSelect={selectRoute}
          focusedCp={focusedCp}
          onFocusCp={setFocusedCp}
          heat={shown ? heat.data : null}
          hour={hour}
          metric={metric}
        />
        {!shown && (
          <div className="map-empty">
            <div>{loading ? 'Finding routes and checking the forecast…' : 'Enter a trip to see three routes and the weather along them.'}</div>
          </div>
        )}
        </div>
        {shown && plan && heat.status !== 'idle' && (
          <TimeBar
            hours={heat.data?.hours ?? []}
            hour={hour}
            onHour={setHour}
            metric={metric}
            onMetric={setMetric}
            status={heat.status === 'ready' ? 'ready' : heat.status === 'error' ? 'error' : 'loading'}
            error={heat.error}
            onRetry={() => loadHeat(plan)}
          />
        )}
      </main>
    </div>
  )
}
