import { formatDayTime, formatDuration, formatMiles } from '../lib/format'
import type { RoutePlan } from '../types'
import { Ribbon } from './Ribbon'
import { Shield } from './Shield'

export function RouteList({
  routes,
  selected,
  onSelect,
}: {
  routes: RoutePlan[]
  selected: string
  onSelect: (id: string) => void
}) {
  return (
    <section aria-labelledby="routes-title">
      <h2 id="routes-title" className="visually-hidden">
        Route options
      </h2>
      <div className="routes">
        {routes.map((r) => (
          <button
            key={r.id}
            type="button"
            className="route-row"
            aria-pressed={r.id === selected}
            onClick={() => onSelect(r.id)}
          >
            <Shield id={r.id} recommended={r.recommended} />
            <div>
              <div className="title">
                Route {r.id}
                {r.recommended && <span className="tag">Recommended</span>}
              </div>
              <div className="meta num">
                {formatMiles(r.distance_mi)}, arrive {formatDayTime(r.arrival)}
              </div>
            </div>
            <div className="time num">
              {formatDuration(r.duration_s)}
              {r.traffic_delay_s >= 300 && <small>incl. {formatDuration(r.traffic_delay_s)} traffic</small>}
            </div>
            <div className="ribbon-wrap">
              <Ribbon route={r} />
            </div>
          </button>
        ))}
      </div>
    </section>
  )
}
