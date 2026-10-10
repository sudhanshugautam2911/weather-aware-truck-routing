import { formatDayTime, formatNumber } from '../lib/format'
import { riskLabel } from '../lib/risk'
import type { Checkpoint, RoutePlan } from '../types'
import { RiskChip } from './RiskChip'

export function weatherLine(cp: Checkpoint) {
  const w = cp.weather
  const gust = w.gust_mph != null ? ` (gusts ${formatNumber(w.gust_mph)})` : ''
  return `Wind ${formatNumber(w.wind_mph)} mph${gust}, rain ${formatNumber(w.rain_in_hr, 2)} in/hr, snow ${formatNumber(w.snow_in_hr, 2)} in/hr`
}

export function causeLine(cp: Checkpoint, loadLb: number) {
  if (cp.risk.level === 'low') return ''
  const parts = cp.risk.causes.map((c) => c[0].toUpperCase() + c.slice(1))
  let s = `${riskLabel(cp.risk.level)} because of ${parts.join(' and ').toLowerCase()}`
  if (cp.risk.load_raised) s += `, raised by the ${formatNumber(loadLb)} lb load`
  return s + '.'
}

export function CheckpointList({
  route,
  loadLb,
  focused,
  onFocus,
}: {
  route: RoutePlan
  loadLb: number
  focused: number | null
  onFocus: (index: number) => void
}) {
  const risky = route.checkpoints.filter((c) => c.risk.level !== 'low').length
  return (
    <section aria-labelledby="cp-title">
      <div className="cp-head">
        <h2 id="cp-title">Route {route.id} checkpoints</h2>
        <span className="hint num">
          {route.checkpoints.length} stops, {risky} above Low
        </span>
      </div>
      <ol className="cp-list">
        {route.checkpoints.map((cp) => {
          const why = causeLine(cp, loadLb)
          return (
            <li key={cp.index}>
              <button
                type="button"
                className="cp"
                aria-current={focused === cp.index ? 'true' : undefined}
                onClick={() => onFocus(cp.index)}
              >
                <span className="mile num">{formatNumber(cp.mile)} mi</span>
                <span className="eta num">{formatDayTime(cp.eta)}</span>
                <RiskChip level={cp.risk.level} />
                <span className="wx num">{weatherLine(cp)}</span>
                {why && <span className="why">{why}</span>}
              </button>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
