import type { PlanResponse, RoutePlan, RuleKey } from '../types'
import { formatDuration, formatMiles } from './format'

const RULE_FIELD: Record<RuleKey, (r: RoutePlan) => number> = {
  no_travel_miles: (r) => r.miles_by_level.no_travel,
  severe_miles: (r) => r.miles_by_level.severe,
  high_miles: (r) => r.miles_by_level.high,
  avg_risk: (r) => r.avg_risk,
  duration: (r) => r.duration_s,
}

/** One plain sentence per other route: why the recommended route beat it. */
export function reasonAgainst(best: RoutePlan, other: RoutePlan, rule: RuleKey | null): string {
  if (rule === null) return `Route ${other.id} ties on every rule, so either works.`
  const a = RULE_FIELD[rule](best)
  const b = RULE_FIELD[rule](other)
  switch (rule) {
    case 'no_travel_miles':
      return a === 0
        ? `Route ${other.id} crosses ${formatMiles(b)} of No Travel weather.`
        : `Route ${other.id} has ${formatMiles(b - a)} more No Travel weather.`
    case 'severe_miles':
      return a === 0
        ? `Route ${other.id} has ${formatMiles(b)} of Severe weather.`
        : `Route ${other.id} has ${formatMiles(b - a)} more Severe weather.`
    case 'high_miles':
      return a === 0
        ? `Route ${other.id} has ${formatMiles(b)} of High-risk weather.`
        : `Route ${other.id} has ${formatMiles(b - a)} more High-risk weather.`
    case 'avg_risk':
      return `Route ${other.id} has the same Severe and High miles but more Moderate weather overall.`
    case 'duration':
      return `Route ${other.id} has the same weather risk but takes ${formatDuration(b - a)} longer.`
  }
}

export type Verdict = { tone: 'clear' | 'caution' | 'danger'; headline: string }

export function verdict(plan: PlanResponse, best: RoutePlan): Verdict {
  const m = best.miles_by_level
  if (plan.warnings.some((w) => w.code === 'ALL_NO_TRAVEL')) {
    return { tone: 'danger', headline: 'Do not travel at this time' }
  }
  if (m.severe > 0) {
    return { tone: 'danger', headline: `Take route ${best.id}, but expect ${formatMiles(m.severe)} of Severe weather` }
  }
  if (m.high > 0) {
    return { tone: 'caution', headline: `Take route ${best.id}, with ${formatMiles(m.high)} of High-risk weather` }
  }
  if (m.moderate > 0) {
    return { tone: 'caution', headline: `Take route ${best.id}, with some Moderate weather` }
  }
  return { tone: 'clear', headline: `Take route ${best.id}, with Low risk all the way` }
}

/** Short risk line for a route label: its worst weather and how many miles of it. */
export function riskSummary(r: RoutePlan): { level: RoutePlan['worst_level']; text: string } {
  const m = r.miles_by_level
  if (m.no_travel > 0) return { level: 'no_travel', text: `${formatMiles(m.no_travel)} No Travel` }
  if (m.severe > 0) return { level: 'severe', text: `${formatMiles(m.severe)} Severe` }
  if (m.high > 0) return { level: 'high', text: `${formatMiles(m.high)} High` }
  if (m.moderate > 0) return { level: 'moderate', text: `${formatMiles(m.moderate)} Moderate` }
  return { level: 'low', text: 'Low risk all the way' }
}
