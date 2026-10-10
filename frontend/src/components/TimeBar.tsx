import { useEffect, useState } from 'react'
import { formatDayHour } from '../lib/format'
import { RISK_LEVELS } from '../lib/risk'
import { PauseIcon, PlayIcon } from './Icons'
import type { HeatMetric } from './MapView'

const METRICS: { key: HeatMetric; label: string }[] = [
  { key: 'risk', label: 'All' },
  { key: 'wind_risk', label: 'Wind' },
  { key: 'rain_risk', label: 'Rain' },
  { key: 'snow_risk', label: 'Snow' },
]

const METRIC_HINT: Record<HeatMetric, string> = {
  risk: 'Colour shows the overall risk. Dots show where each truck is at this hour',
  wind_risk: 'Colour shows wind risk. Darker squares are windier',
  rain_risk: 'Colour shows rain risk. Darker squares are wetter',
  snow_risk: 'Colour shows snow risk. Darker squares have more snow',
}

export function TimeBar({
  hours,
  hour,
  onHour,
  metric,
  onMetric,
  status,
  error,
  onRetry,
}: {
  hours: string[]
  hour: number
  onHour: (h: number) => void
  metric: HeatMetric
  onMetric: (m: HeatMetric) => void
  status: 'loading' | 'ready' | 'error'
  error?: string
  onRetry: () => void
}) {
  const [playing, setPlaying] = useState(false)
  const last = Math.max(0, hours.length - 1)

  useEffect(() => {
    if (!playing) return
    const t = setInterval(() => {
      onHour(hour >= last ? last : hour + 1)
      if (hour >= last) setPlaying(false)
    }, 450)
    return () => clearInterval(t)
  }, [playing, hour, last, onHour])

  const ready = status === 'ready' && hours.length > 0

  return (
    <div className="time-bar" role="group" aria-label="Weather forecast over the next 48 hours">
      <button
        type="button"
        className="play"
        disabled={!ready}
        onClick={() => {
          if (!playing && hour >= last) onHour(0)
          setPlaying((p) => !p)
        }}
        aria-label={playing ? 'Pause forecast animation' : 'Play forecast animation'}
      >
        {playing ? <PauseIcon /> : <PlayIcon />}
      </button>
      <div>
        <div className="top">
          <span className="when num" aria-live="polite">
            {ready ? formatDayHour(hours[hour]) : 'Weather along the trip'}
            {ready && <small>{hour === 0 ? 'departure hour' : `+${hour} h after departure`}</small>}
          </span>
          <div className="layer-switch" role="group" aria-label="Weather layer">
            {METRICS.map((m) => (
              <button
                key={m.key}
                type="button"
                aria-pressed={metric === m.key}
                onClick={() => onMetric(m.key)}
                disabled={!ready}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>
        <label className="visually-hidden" htmlFor="hour-slider">
          Forecast hour
        </label>
        <input
          id="hour-slider"
          type="range"
          min={0}
          max={last || 48}
          step={1}
          value={hour}
          disabled={!ready}
          onChange={(e) => {
            setPlaying(false)
            onHour(Number(e.target.value))
          }}
          aria-valuetext={ready ? `${formatDayHour(hours[hour])}, ${hour} hours after departure` : undefined}
        />
      </div>
      {status === 'loading' && (
        <div className="status">
          <span className="spinner" style={{ borderColor: 'rgb(27 32 38 / 0.2)', borderTopColor: 'var(--ink)' }} />
          Loading the 48-hour weather layer…
        </div>
      )}
      {status === 'error' && (
        <div className="status error" role="alert">
          {error ?? 'The weather layer could not load.'}
          <button type="button" className="btn btn-quiet" onClick={onRetry}>
            Retry
          </button>
        </div>
      )}
      {ready && (
        <div className="bottom">
          <div className="legend" aria-label="Risk colours">
            {RISK_LEVELS.map((l) => (
              <span key={l.key}>
                <i className="swatch" style={{ background: l.color }} />
                {l.label}
              </span>
            ))}
          </div>
          <span className="hint">{METRIC_HINT[metric]}</span>
        </div>
      )}
    </div>
  )
}
