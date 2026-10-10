import type { FeatureCollection } from 'geojson'
import { useEffect, useMemo, useRef, useState } from 'react'
import MapGL, {
  Layer,
  Marker,
  NavigationControl,
  Popup,
  Source,
  type MapLayerMouseEvent,
  type MapRef,
} from 'react-map-gl/maplibre'
import { causeLine, riskSummary } from '../lib/explain'
import { formatDayHour, formatDayTime, formatDuration, formatMiles, formatNumber } from '../lib/format'
import { boundsOf, labelPoints, positionAt } from '../lib/geometry'
import { RISK_LEVELS } from '../lib/risk'
import type { HeatmapResponse, PlanResponse, RiskKey } from '../types'
import { RiskChip } from './RiskChip'
import { Shield } from './Shield'

export type HeatMetric = 'risk' | 'wind_risk' | 'rain_risk' | 'snow_risk'

const STYLE = 'https://tiles.openfreemap.org/styles/positron'
const INK = '#1b2026'
const ROUTE_IDLE = '#7d8790'
const RISK_KEYS = RISK_LEVELS.map((r) => r.key)

const reduceMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

const levelColor = (prop: unknown) => [
  'match',
  prop,
  ...RISK_LEVELS.flatMap((r, i) => [i, r.color]),
  'rgba(0,0,0,0)',
]

export function MapView({
  plan,
  selected,
  onSelect,
  focusedCp,
  onFocusCp,
  heat,
  hour,
  metric,
}: {
  plan: PlanResponse | null
  selected: string
  onSelect: (id: string) => void
  focusedCp: number | null
  onFocusCp: (i: number | null) => void
  heat: HeatmapResponse | null
  hour: number
  metric: HeatMetric
}) {
  const mapRef = useRef<MapRef>(null)
  const [hover, setHover] = useState<{ cell: number; lng: number; lat: number } | null>(null)
  const [hoverCp, setHoverCp] = useState<{ route: string; index: number } | null>(null)
  const selectedRoute = plan?.routes.find((r) => r.id === selected) ?? null

  // Fit the map to the routes whenever a new plan arrives.
  useEffect(() => {
    if (!plan || !mapRef.current) return
    const narrow = window.innerWidth < 900
    mapRef.current.fitBounds(boundsOf(plan.routes), {
      padding: { top: 50, left: 50, right: 50, bottom: narrow ? 150 : 190 },
      duration: reduceMotion() ? 0 : 900,
    })
  }, [plan])

  // Bring a checkpoint chosen from the list into view.
  useEffect(() => {
    if (focusedCp === null || !selectedRoute || !mapRef.current) return
    const cp = selectedRoute.checkpoints[focusedCp]
    if (cp) mapRef.current.easeTo({ center: [cp.lon, cp.lat], zoom: Math.max(mapRef.current.getZoom(), 7), duration: reduceMotion() ? 0 : 600 })
  }, [focusedCp, selectedRoute])

  const shieldAt = useMemo(() => (plan ? labelPoints(plan.routes) : {}), [plan])

  const routesGeo = useMemo<FeatureCollection | null>(() => {
    if (!plan) return null
    return {
      type: 'FeatureCollection',
      features: plan.routes.map((r) => ({
        type: 'Feature',
        properties: { id: r.id, selected: r.id === selected ? 1 : 0 },
        geometry: { type: 'LineString', coordinates: r.geometry.coords },
      })),
    }
  }, [plan, selected])

  // Checkpoints of every route; the selected route's are drawn larger and on top.
  const checkpointsGeo = useMemo<FeatureCollection | null>(() => {
    if (!plan) return null
    let id = 0
    return {
      type: 'FeatureCollection',
      features: plan.routes.flatMap((r) =>
        r.checkpoints.map((c) => ({
          type: 'Feature' as const,
          id: id++,
          properties: {
            route: r.id,
            index: c.index,
            selected: r.id === selected ? 1 : 0,
            level: RISK_KEYS.indexOf(c.risk.level),
          },
          geometry: { type: 'Point' as const, coordinates: [c.lon, c.lat] },
        })),
      ),
    }
  }, [plan, selected])

  // All 49 hours are baked into each cell's properties once. Moving the slider
  // only swaps which property the paint expression reads: no new data, no fetch.
  const heatGeo = useMemo<FeatureCollection | null>(() => {
    if (!heat) return null
    const half = heat.step / 2
    return {
      type: 'FeatureCollection',
      features: heat.cells.map((c, i) => {
        const props: Record<string, number | null> = {}
        for (let h = 0; h < heat.hours.length; h++) {
          props[`risk${h}`] = c.risk[h]
          props[`wind_risk${h}`] = c.wind_risk[h]
          props[`rain_risk${h}`] = c.rain_risk[h]
          props[`snow_risk${h}`] = c.snow_risk[h]
          props[`wind${h}`] = c.wind[h]
          props[`rain${h}`] = c.rain[h]
          props[`snow${h}`] = c.snow[h]
        }
        return {
          type: 'Feature',
          id: i,
          properties: props,
          geometry: {
            type: 'Polygon',
            coordinates: [
              [
                [c.lon - half, c.lat - half],
                [c.lon + half, c.lat - half],
                [c.lon + half, c.lat + half],
                [c.lon - half, c.lat + half],
                [c.lon - half, c.lat - half],
              ],
            ],
          },
        }
      }),
    }
  }, [heat])

  const heatProp = ['get', `${metric}${hour}`]
  const heatPaint = useMemo(() => {
    // "All": colour = overall risk; calm cells stay faint so risky areas stand out.
    // Wind / Rain / Snow: colour = that condition's risk level, and the square gets
    // darker the stronger the weather, so the views differ even when all is Low.
    const raw = (name: string) => ['coalesce', ['get', `${name}${hour}`], 0]
    const strength: Record<HeatMetric, unknown> = {
      risk: ['match', heatProp, 0, 0.16, 1, 0.42, 2, 0.5, 3, 0.55, 4, 0.6, 0],
      wind_risk: ['interpolate', ['linear'], raw('wind'), 0, 0.04, 10, 0.16, 25, 0.42, 45, 0.55, 60, 0.65],
      rain_risk: ['interpolate', ['linear'], raw('rain'), 0, 0, 0.005, 0.12, 0.1, 0.42, 0.5, 0.55, 1, 0.65],
      snow_risk: ['interpolate', ['linear'], raw('snow'), 0, 0, 0.05, 0.14, 0.5, 0.42, 2, 0.55, 3, 0.65],
    }
    return {
      'fill-color': levelColor(heatProp),
      'fill-opacity': ['case', ['==', heatProp, null], 0, strength[metric]],
      'fill-outline-color': 'rgba(255,255,255,0.35)',
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metric, hour])

  const onMove = (e: MapLayerMouseEvent) => {
    const cp = e.features?.find((x) => x.layer.id === 'checkpoints')
    if (cp) {
      setHover(null)
      setHoverCp({ route: String(cp.properties?.route), index: Number(cp.properties?.index) })
      return
    }
    setHoverCp(null)
    const f = e.features?.find((x) => x.layer.id === 'heat')
    if (f && typeof f.id === 'number') setHover({ cell: f.id, lng: e.lngLat.lng, lat: e.lngLat.lat })
    else setHover(null)
  }

  const onClick = (e: MapLayerMouseEvent) => {
    const f = e.features?.find((x) => x.layer.id === 'checkpoints' || x.layer.id === 'route-hit')
    if (!f) return
    if (f.layer.id === 'checkpoints') {
      const route = String(f.properties?.route)
      if (route !== selected) onSelect(route)
      onFocusCp(Number(f.properties?.index))
    } else {
      onSelect(String(f.properties?.id))
    }
  }

  const departure = plan ? new Date(plan.meta.departure).getTime() : 0
  const hourTime = heat ? new Date(heat.hours[hour]).getTime() : departure
  const offsetS = (hourTime - departure) / 1000
  const focused = focusedCp !== null && selectedRoute ? selectedRoute.checkpoints[focusedCp] : null
  const hoverCell = hover && heat ? heat.cells[hover.cell] : null

  return (
    <MapGL
      ref={mapRef}
      initialViewState={{ longitude: -96, latitude: 38.5, zoom: 3.6 }}
      mapStyle={STYLE}
      style={{ position: 'absolute', inset: 0 }}
      interactiveLayerIds={plan ? ['checkpoints', 'route-hit', 'heat'] : []}
      onMouseMove={onMove}
      onMouseLeave={() => {
        setHover(null)
        setHoverCp(null)
      }}
      onClick={onClick}
      cursor={hoverCp ? 'pointer' : hover ? 'crosshair' : 'auto'}
      attributionControl={{ compact: true }}
      dragRotate={false}
      touchPitch={false}
    >
      <NavigationControl position="top-right" showCompass={false} />

      {heatGeo && (
        <Source id="heat-src" type="geojson" data={heatGeo}>
          <Layer id="heat" type="fill" paint={heatPaint as never} />
        </Source>
      )}

      {routesGeo && (
        <Source id="routes-src" type="geojson" data={routesGeo}>
          <Layer
            id="route-casing"
            type="line"
            layout={{ 'line-join': 'round', 'line-cap': 'round', 'line-sort-key': ['get', 'selected'] }}
            paint={{ 'line-color': '#ffffff', 'line-width': ['case', ['==', ['get', 'selected'], 1], 9, 6] }}
          />
          <Layer
            id="route-line"
            type="line"
            layout={{ 'line-join': 'round', 'line-cap': 'round', 'line-sort-key': ['get', 'selected'] }}
            paint={{
              'line-color': ['case', ['==', ['get', 'selected'], 1], INK, ROUTE_IDLE],
              'line-width': ['case', ['==', ['get', 'selected'], 1], 5, 3],
            }}
          />
          {/* Wide invisible line so routes are easy to click. */}
          <Layer id="route-hit" type="line" paint={{ 'line-color': '#000', 'line-opacity': 0, 'line-width': 18 }} />
        </Source>
      )}

      {checkpointsGeo && (
        <Source id="cp-src" type="geojson" data={checkpointsGeo}>
          <Layer
            id="checkpoints"
            type="circle"
            layout={{ 'circle-sort-key': ['get', 'selected'] }}
            paint={{
              // Zoom must be the outer expression; the selected route's dots are larger.
              'circle-radius': [
                'interpolate',
                ['linear'],
                ['zoom'],
                4,
                ['case', ['==', ['get', 'selected'], 1], 4.5, 3],
                8,
                ['case', ['==', ['get', 'selected'], 1], 7, 5],
              ] as never,
              'circle-color': levelColor(['get', 'level']) as never,
              'circle-stroke-color': '#ffffff',
              'circle-stroke-width': ['case', ['==', ['get', 'selected'], 1], 2, 1.25] as never,
            }}
          />
        </Source>
      )}

      {plan && (
        <>
          <Marker longitude={plan.routes[0].geometry.coords[0][0]} latitude={plan.routes[0].geometry.coords[0][1]}>
            <span className="start-dot" title="Start" />
          </Marker>
          <Marker
            longitude={plan.routes[0].geometry.coords[plan.routes[0].geometry.coords.length - 1][0]}
            latitude={plan.routes[0].geometry.coords[plan.routes[0].geometry.coords.length - 1][1]}
          >
            <span className="end-dot" title="Destination" />
          </Marker>
          {plan.routes.map((r) => {
            const mid = shieldAt[r.id]
            return (
              <Marker key={`shield-${r.id}`} longitude={mid[0]} latitude={mid[1]} anchor="bottom">
                <button
                  type="button"
                  onClick={() => onSelect(r.id)}
                  aria-label={`Select route ${r.id}`}
                  style={{ border: 0, padding: 0, background: 'none', cursor: 'pointer', opacity: r.id === selected ? 1 : 0.85 }}
                >
                  <span className="route-tag">
                    <Shield id={r.id} recommended={r.recommended} size={r.id === selected ? 30 : 24} />
                    <span className="route-tag-text num">
                      <b>
                        {formatDuration(r.duration_s)}, {formatMiles(r.distance_mi)}
                      </b>
                      <span>
                        <i className="swatch" style={{ background: RISK_LEVELS[RISK_KEYS.indexOf(riskSummary(r).level)].color }} />
                        {r.recommended ? 'Recommended, ' : ''}
                        {riskSummary(r).text}
                      </span>
                    </span>
                  </span>
                </button>
              </Marker>
            )
          })}
          {heat &&
            plan.routes.map((r) => {
              const [lng, lat] = positionAt(r, offsetS)
              return (
                <Marker key={`truck-${r.id}`} longitude={lng} latitude={lat}>
                  <span
                    className={`truck-dot${r.id === selected ? ' selected' : ''}`}
                    title={`Truck on route ${r.id}`}
                  />
                </Marker>
              )
            })}
        </>
      )}

      {focused && selectedRoute && plan && (
        <Popup
          longitude={focused.lon}
          latitude={focused.lat}
          anchor="bottom"
          offset={12}
          onClose={() => onFocusCp(null)}
          closeOnClick={false}
          maxWidth="300px"
        >
          <div className="popup">
            <h3 className="num">
              Route {selectedRoute.id}, mile {formatNumber(focused.mile)}
            </h3>
            <RiskChip level={focused.risk.level} />
            <dl className="num">
              <dt>Truck arrives</dt>
              <dd>{formatDayTime(focused.eta)}</dd>
              <dt>Wind</dt>
              <dd>
                {formatNumber(focused.weather.wind_mph)} mph
                {focused.weather.gust_mph != null && `, gusts ${formatNumber(focused.weather.gust_mph)}`}
              </dd>
              <dt>Rain</dt>
              <dd>{formatNumber(focused.weather.rain_in_hr, 2)} in/hr</dd>
              <dt>Snow</dt>
              <dd>{formatNumber(focused.weather.snow_in_hr, 2)} in/hr</dd>
            </dl>
            {causeLine(focused, plan.meta.load_lb) && <p className="note">{causeLine(focused, plan.meta.load_lb)}</p>}
          </div>
        </Popup>
      )}


      {hoverCp && plan && !focused && (() => {
        const r = plan.routes.find((x) => x.id === hoverCp.route)
        const c = r?.checkpoints[hoverCp.index]
        if (!r || !c) return null
        return (
          <Popup longitude={c.lon} latitude={c.lat} closeButton={false} anchor="bottom" offset={10} maxWidth="260px">
            <div className="popup">
              <h3 className="num">
                Route {r.id}, mile {formatNumber(c.mile)}
              </h3>
              <RiskChip level={c.risk.level} />
              <p className="note num">Truck arrives {formatDayTime(c.eta)}</p>
            </div>
          </Popup>
        )
      })()}
      {hover && hoverCell && heat && !focused && !hoverCp && (
        <Popup longitude={hover.lng} latitude={hover.lat} closeButton={false} anchor="bottom" offset={14} maxWidth="260px">
          <div className="popup">
            <h3>{formatDayHour(heat.hours[hour])}</h3>
            {hoverCell.risk[hour] == null ? (
              <p className="note">No forecast for this hour.</p>
            ) : (
              <>
                <RiskChip level={RISK_KEYS[hoverCell[metric][hour] as number] as RiskKey} />
                <dl className="num">
                  <dt>Wind</dt>
                  <dd>{formatNumber(hoverCell.wind[hour] ?? 0)} mph</dd>
                  <dt>Rain</dt>
                  <dd>{formatNumber(hoverCell.rain[hour] ?? 0, 2)} in/hr</dd>
                  <dt>Snow</dt>
                  <dd>{formatNumber(hoverCell.snow[hour] ?? 0, 2)} in/hr</dd>
                </dl>
              </>
            )}
          </div>
        </Popup>
      )}
    </MapGL>
  )
}
