import { formatDuration, formatNumber } from '../lib/format'
import type { PlanResponse, RuleKey } from '../types'

const fmt = (key: RuleKey, v: number) =>
  key === 'duration' ? formatDuration(v) : key === 'avg_risk' ? formatNumber(v, 2) : `${formatNumber(v, 1)} mi`

/** The brief's ranking rules, in order, with each route's value. */
export function RankingTable({ plan }: { plan: PlanResponse }) {
  const ids = plan.routes.map((r) => r.id)
  const rec = plan.recommendation
  return (
    <details className="disclosure section">
      <summary>Why this route?</summary>
      <div>
        {rec.decided_by === 'duration' && (
          <p className="tie-note">All routes have the same weather risk, so the fastest one is recommended.</p>
        )}
        {rec.decided_by === null && ids.length > 1 && (
          <p className="tie-note">The routes tie on every rule, so any of them is equally good.</p>
        )}
        <p className="hint" style={{ marginBottom: 10 }}>
          Routes are compared rule by rule, top to bottom. The first rule that separates two routes decides between
          them. Average risk scores Low as 0 and No Travel as 4, weighted by miles.
        </p>
        <div className="table-wrap">
          <table className="num">
            <thead>
              <tr>
                <th scope="col">Rule</th>
                {ids.map((id) => (
                  <th scope="col" key={id}>
                    {id}
                    {id === rec.route_id ? ' ✓' : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rec.rules.map((rule) => {
                const values = ids.map((id) => rule.values[id])
                const min = Math.min(...values)
                // A row where every route has the same value has no winner: show it plain.
                const tied = values.every((v) => v === min)
                const isDecider = rec.decided_by === rule.key
                return (
                  <tr key={rule.key} className={isDecider ? 'decider' : tied ? 'tied' : undefined}>
                    <td>
                      {rule.label}
                      {tied && ids.length > 1 && <span className="tie-tag"> (tie)</span>}
                    </td>
                    {ids.map((id) => (
                      <td key={id} className={!tied && rule.values[id] === min ? 'best' : undefined}>
                        {fmt(rule.key, rule.values[id])}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="hint" style={{ marginTop: 10 }}>
          “Fewest No Travel miles” is checked first: a stretch you must not drive rules a route out before anything else.
        </p>
      </div>
    </details>
  )
}
