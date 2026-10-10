import { causeLine, weatherLine } from '../lib/explain'
import { formatDayTime, formatNumber } from '../lib/format'
import type { RoutePlan } from '../types'
import { RiskChip } from './RiskChip'

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
