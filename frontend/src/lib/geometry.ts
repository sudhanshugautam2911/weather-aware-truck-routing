import type { RoutePlan } from '../types'

/** Where a truck on this route is `offsetS` seconds after departure. */
export function positionAt(route: RoutePlan, offsetS: number): [number, number] {
  const { coords, times } = route.geometry
  if (offsetS <= 0) return coords[0]
  if (offsetS >= times[times.length - 1]) return coords[coords.length - 1]
  let lo = 0
  let hi = times.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (times[mid] <= offsetS) lo = mid
    else hi = mid
  }
  const span = times[hi] - times[lo]
  const f = span > 0 ? (offsetS - times[lo]) / span : 0
  return [
    coords[lo][0] + f * (coords[hi][0] - coords[lo][0]),
    coords[lo][1] + f * (coords[hi][1] - coords[lo][1]),
  ]
}

export function boundsOf(routes: RoutePlan[]): [[number, number], [number, number]] {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const r of routes) {
    for (const [x, y] of r.geometry.coords) {
      if (x < minX) minX = x
      if (y < minY) minY = y
      if (x > maxX) maxX = x
      if (y > maxY) maxY = y
    }
  }
  return [
    [minX, minY],
    [maxX, maxY],
  ]
}

/**
 * A label spot for each route: the point (between 20% and 80% of the way) that is
 * furthest from every other route, so shields never sit on shared road.
 */
export function labelPoints(routes: RoutePlan[]): Record<string, [number, number]> {
  const sample = (r: RoutePlan, n: number) => {
    const c = r.geometry.coords
    return Array.from({ length: n }, (_, i) => c[Math.floor((c.length - 1) * (i / (n - 1)))])
  }
  const others = routes.map((r) => sample(r, 300))
  const out: Record<string, [number, number]> = {}
  routes.forEach((r, ri) => {
    const coords = r.geometry.coords
    let best: [number, number] = coords[Math.floor(coords.length / 2)]
    let bestD = -1
    for (let k = 20; k <= 80; k += 2) {
      const p = coords[Math.floor((coords.length - 1) * (k / 100))]
      let d = Infinity
      others.forEach((pts, oi) => {
        if (oi === ri) return
        for (const q of pts) {
          const dx = (p[0] - q[0]) * Math.cos((p[1] * Math.PI) / 180)
          const dy = p[1] - q[1]
          d = Math.min(d, dx * dx + dy * dy)
        }
      })
      if (d > bestD) {
        bestD = d
        best = p
      }
    }
    out[r.id] = best
  })
  return out
}
