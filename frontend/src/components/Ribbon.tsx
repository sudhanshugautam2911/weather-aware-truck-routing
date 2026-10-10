import { RISK_LEVELS, riskColor } from '../lib/risk'
import { formatNumber } from '../lib/format'
import type { RoutePlan } from '../types'

/** The route's length, left to right, painted by the risk at each checkpoint's stretch. */
export function Ribbon({ route }: { route: RoutePlan }) {
  const total = route.distance_mi || 1
  // Merge neighbouring checkpoints with the same level into one block.
  const blocks: { level: (typeof route.checkpoints)[number]['risk']['level']; miles: number }[] = []
  for (const cp of route.checkpoints) {
    const last = blocks[blocks.length - 1]
    if (last && last.level === cp.risk.level) last.miles += cp.owned_mi
    else blocks.push({ level: cp.risk.level, miles: cp.owned_mi })
  }
  const counts = RISK_LEVELS.filter((l) => route.miles_by_level[l.key] > 0)
  const summary = counts.map((l) => `${formatNumber(route.miles_by_level[l.key])} miles ${l.label}`).join(', ')
  return (
    <div>
      <div className="ribbon" role="img" aria-label={`Risk along route ${route.id}: ${summary}`}>
        {blocks.map((b, i) => (
          <i key={i} style={{ flexGrow: b.miles / total, background: riskColor(b.level) }} />
        ))}
      </div>
      <div className="ribbon-counts">
        {counts.map((l) => (
          <span key={l.key} className="num">
            <i className="swatch" style={{ background: l.color }} />
            {l.label} {formatNumber(route.miles_by_level[l.key])} mi
          </span>
        ))}
      </div>
    </div>
  )
}
