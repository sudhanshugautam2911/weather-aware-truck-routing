import { describe, expect, it } from 'vitest'
import type { RoutePlan } from '../types'
import { reasonAgainst } from './explain'
import { formatDuration, toLocalInput } from './format'
import { positionAt } from './geometry'

const route = (id: string, over: Partial<RoutePlan> = {}): RoutePlan => ({
  id,
  rank: 1,
  recommended: false,
  distance_mi: 100,
  duration_s: 7200,
  traffic_delay_s: 0,
  arrival: '2026-10-10T12:00:00Z',
  miles_by_level: { low: 100, moderate: 0, high: 0, severe: 0, no_travel: 0 },
  avg_risk: 0,
  worst_level: 'low',
  geometry: { coords: [[0, 0], [1, 0], [3, 0]], times: [0, 100, 300], miles: [0, 1, 3] },
  checkpoints: [],
  ...over,
})

describe('positionAt', () => {
  it('clamps to the ends and interpolates by time', () => {
    const r = route('A')
    expect(positionAt(r, -5)).toEqual([0, 0])
    expect(positionAt(r, 999)).toEqual([3, 0])
    expect(positionAt(r, 50)).toEqual([0.5, 0])
    expect(positionAt(r, 200)).toEqual([2, 0])
  })
})

describe('formatDuration', () => {
  it('formats hours and minutes', () => {
    expect(formatDuration(59 * 60)).toBe('59 min')
    expect(formatDuration(3600)).toBe('1 h')
    expect(formatDuration(3600 * 19 + 60 * 54)).toBe('19 h 54 min')
  })
})

describe('toLocalInput', () => {
  it('rounds up to the next quarter hour', () => {
    expect(toLocalInput(new Date(2026, 9, 10, 9, 1))).toBe('2026-10-10T09:15')
    expect(toLocalInput(new Date(2026, 9, 10, 9, 45))).toBe('2026-10-10T09:45')
  })
})

describe('reasonAgainst', () => {
  it('names the deciding rule in plain words', () => {
    const best = route('B')
    const other = route('A', { miles_by_level: { low: 50, moderate: 0, high: 0, severe: 12, no_travel: 0 } })
    expect(reasonAgainst(best, other, 'severe_miles')).toBe('Route A has 12 mi of Severe weather.')
    expect(reasonAgainst(best, route('C', { duration_s: 7200 + 1800 }), 'duration')).toBe(
      'Route C has the same weather risk but takes 30 min longer.',
    )
    expect(reasonAgainst(best, route('C'), null)).toMatch(/ties on every rule/)
  })
})
