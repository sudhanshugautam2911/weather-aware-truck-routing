import { useMemo } from 'react'
import { timeZoneName, toLocalInput } from '../lib/format'
import type { Place, TripInput } from '../types'
import { PlaceInput } from './PlaceInput'

export type FieldErrors = Partial<Record<'origin' | 'destination' | 'departure' | 'load_lb' | 'interval_mi', string>>

const MAX_LOAD = 80_000

export function validate(t: TripInput): FieldErrors {
  const e: FieldErrors = {}
  if (!t.origin) e.origin = 'Choose a starting point from the suggestions.'
  if (!t.destination) e.destination = 'Choose a destination from the suggestions.'
  if (t.origin && t.destination && t.origin.label === t.destination.label) {
    e.destination = 'Destination must be different from the starting point.'
  }
  if (!t.departure) {
    e.departure = 'Pick a departure date and time.'
  } else {
    const dep = new Date(t.departure).getTime()
    const now = Date.now()
    if (Number.isNaN(dep)) e.departure = 'Enter a valid date and time.'
    else if (dep < now - 15 * 60_000) e.departure = 'This time has already passed. Pick a time from now onward.'
    else if (dep > now + 7 * 86_400_000) e.departure = 'Pick a departure within the next 7 days.'
  }
  const load = t.load_lb.trim() === '' ? NaN : Number(t.load_lb.replace(/,/g, ''))
  if (t.load_lb.trim() === '') e.load_lb = 'Enter the load weight in pounds.'
  else if (Number.isNaN(load)) e.load_lb = 'Load weight must be a number of pounds.'
  else if (load < 0) e.load_lb = 'Load weight cannot be negative.'
  else if (load > MAX_LOAD) e.load_lb = 'Load weight must be 80,000 lb or less.'
  return e
}

export function TripForm({
  value,
  onChange,
  errors,
  onSubmit,
  loading,
}: {
  value: TripInput
  onChange: (v: TripInput) => void
  errors: FieldErrors
  onSubmit: () => void
  loading: boolean
}) {
  const set = <K extends keyof TripInput>(k: K, v: TripInput[K]) => onChange({ ...value, [k]: v })
  const limits = useMemo(() => {
    const now = new Date()
    return { min: toLocalInput(new Date(now.getTime() - 15 * 60_000)), max: toLocalInput(new Date(now.getTime() + 7 * 86_400_000 - 15 * 60_000)) }
  }, [])
  const tz = useMemo(timeZoneName, [])

  return (
    <form
      className="form"
      noValidate
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit()
      }}
    >
      <div className="places">
        <div className="places-rail" aria-hidden="true">
          <i />
          <b />
          <i />
        </div>
        <PlaceInput
          name="origin"
          label="From"
          placeholder="City or street address"
          value={value.origin}
          onChange={(p: Place | null) => set('origin', p)}
          error={errors.origin}
        />
        <PlaceInput
          name="destination"
          label="To"
          placeholder="City or street address"
          value={value.destination}
          onChange={(p: Place | null) => set('destination', p)}
          error={errors.destination}
        />
      </div>

      <div className="field">
        <label htmlFor="departure">Departure ({tz})</label>
        <input
          id="departure"
          className="input"
          type="datetime-local"
          value={value.departure}
          min={limits.min}
          max={limits.max}
          step={900}
          aria-invalid={errors.departure ? true : undefined}
          aria-describedby={errors.departure ? 'departure-err' : undefined}
          onChange={(e) => set('departure', e.target.value)}
        />
        {errors.departure && (
          <p className="field-error" id="departure-err">
            {errors.departure}
          </p>
        )}
      </div>

      <div className="field-row">
        <div className="field">
          <label htmlFor="load">Load weight</label>
          <div className="input-suffix">
            <input
              id="load"
              className="input num"
              inputMode="numeric"
              placeholder="e.g. 38000"
              value={value.load_lb}
              aria-invalid={errors.load_lb ? true : undefined}
              aria-describedby={errors.load_lb ? 'load-err' : 'load-hint'}
              onChange={(e) => set('load_lb', e.target.value)}
            />
            <span>lb</span>
          </div>
          {errors.load_lb ? (
            <p className="field-error" id="load-err">
              {errors.load_lb}
            </p>
          ) : (
            <p className="hint" id="load-hint">
              Over 30,000 lb raises wind risk
            </p>
          )}
        </div>

        <fieldset className="fieldset">
          <legend>Check weather every</legend>
          <div className="segmented">
            {([10, 25, 50] as const).map((mi) => (
              <label key={mi}>
                <input
                  type="radio"
                  name="interval"
                  value={mi}
                  checked={value.interval_mi === mi}
                  onChange={() => set('interval_mi', mi)}
                />
                {mi} mi
              </label>
            ))}
          </div>
        </fieldset>
      </div>

      <button className="btn btn-primary btn-block" type="submit" disabled={loading}>
        {loading ? (
          <>
            <span className="spinner" aria-hidden="true" /> Checking routes and weather…
          </>
        ) : (
          'Compare routes'
        )}
      </button>
    </form>
  )
}
