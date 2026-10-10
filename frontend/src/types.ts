export type RiskKey = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel'

export interface Place {
  label: string
  lat: number
  lon: number
}

export interface Checkpoint {
  index: number
  mile: number
  lat: number
  lon: number
  eta: string
  owned_mi: number
  weather: {
    wind_mph: number
    gust_mph: number | null
    rain_in_hr: number
    snow_in_hr: number
    wind_hour: string
    precip_hour_end: string
  }
  risk: {
    level: RiskKey
    wind: RiskKey
    rain: RiskKey
    snow: RiskKey
    load_raised: boolean
    causes: ('wind' | 'rain' | 'snow')[]
  }
}

export interface RoutePlan {
  id: string
  rank: number
  recommended: boolean
  distance_mi: number
  duration_s: number
  traffic_delay_s: number
  arrival: string
  miles_by_level: Record<RiskKey, number>
  avg_risk: number
  worst_level: RiskKey
  geometry: { coords: [number, number][]; times: number[]; miles: number[] }
  checkpoints: Checkpoint[]
}

export type RuleKey = 'no_travel_miles' | 'severe_miles' | 'high_miles' | 'avg_risk' | 'duration'

export interface PlanResponse {
  routes: RoutePlan[]
  recommendation: {
    route_id: string
    decided_by: RuleKey | null
    beats: Record<string, RuleKey | null>
    rules: { key: RuleKey; label: string; values: Record<string, number> }[]
  }
  warnings: { code: string; message: string }[]
  meta: {
    departure: string
    load_lb: number
    interval_mi: number
    routing_provider: string
    truck_aware: boolean
    weather_sources: string[]
    generated_at: string
    timings_ms: Record<string, number>
  }
}

export interface HeatmapCell {
  lat: number
  lon: number
  risk: (number | null)[]
  wind: (number | null)[]
  rain: (number | null)[]
  snow: (number | null)[]
  wind_risk: (number | null)[]
  rain_risk: (number | null)[]
  snow_risk: (number | null)[]
}

export interface HeatmapResponse {
  step: number
  hours: string[]
  cells: HeatmapCell[]
  weather_sources: string[]
}

export interface TripInput {
  origin: Place | null
  destination: Place | null
  departure: string // datetime-local value, in the browser's time zone
  load_lb: string
  interval_mi: 10 | 25 | 50
}
