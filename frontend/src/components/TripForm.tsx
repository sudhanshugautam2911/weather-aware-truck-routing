import { useState } from 'react'
import { timeZoneName, toLocalInput } from '../lib/format'
import type { FieldErrors } from '../lib/validate'
import type { Place, TripInput } from '../types'
import { PlaceInput } from './PlaceInput'

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
  // Allowed departure range, fixed when the form first appears.
  const [limits] = useState(() => {
    const now = Date.now()
    return { min: toLocalInput(new Date(now - 15 * 60_000)), max: toLocalInput(new Date(now + 7 * 86_400_000 - 15 * 60_000)) }
  })
  const [tz] = useState(timeZoneName)

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
          name="departure"
          autoComplete="off"
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
              name="load_lb"
              autoComplete="off"
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
