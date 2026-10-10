import { reasonAgainst, verdict } from '../lib/explain'
import { formatDayTime, formatDuration, formatMiles } from '../lib/format'
import type { PlanResponse, RoutePlan } from '../types'
import { Shield } from './Shield'

export function Verdict({ plan, best }: { plan: PlanResponse; best: RoutePlan }) {
  const v = verdict(plan, best)
  const others = plan.routes.filter((r) => r.id !== best.id)
  return (
    <section className="verdict" data-tone={v.tone} aria-labelledby="verdict-title">
      <Shield id={best.id} recommended size={40} />
      <div>
        <h2 id="verdict-title">{v.headline}</h2>
        {others.length > 0 && (
          <ul>
            {others.map((o) => (
              <li key={o.id}>{reasonAgainst(best, o, plan.recommendation.beats[o.id] ?? null)}</li>
            ))}
          </ul>
        )}
        <div className="facts num">
          <span>
            <b>{formatMiles(best.distance_mi)}</b>
          </span>
          <span>
            <b>{formatDuration(best.duration_s)}</b> driving
          </span>
          <span>
            Arrive <b>{formatDayTime(best.arrival)}</b>
          </span>
        </div>
      </div>
    </section>
  )
}
