import type { HeatmapResponse, PlanResponse, Place } from './types'

export class ApiError extends Error {
  code: string
  field?: string
  status: number

  constructor(code: string, message: string, status: number, field?: string) {
    super(message)
    this.code = code
    this.field = field
    this.status = status
  }
}

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  let resp: Response
  try {
    resp = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    })
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err
    throw new ApiError(
      'NETWORK',
      'Could not reach the server. Check your internet connection and try again.',
      0,
    )
  }
  let body: unknown = null
  try {
    body = await resp.json()
  } catch {
    // Non-JSON answer (e.g. a proxy error page).
  }
  if (!resp.ok) {
    const e = (body as { error?: { code: string; message: string; field?: string } } | null)?.error
    if (e) throw new ApiError(e.code, e.message, resp.status, e.field)
    if (resp.status === 504) {
      throw new ApiError('TIMEOUT', 'The server took too long to answer. Try again in a moment.', 504)
    }
    throw new ApiError('SERVER', 'Something went wrong on our side. Try again in a moment.', resp.status)
  }
  return body as T
}

export function searchPlaces(q: string, signal: AbortSignal) {
  return call<{ results: Place[] }>(`/api/geocode?q=${encodeURIComponent(q)}`, { signal })
}

export function planTrip(
  body: { origin: Place; destination: Place; departure: string; load_lb: number; interval_mi: number },
  signal?: AbortSignal,
) {
  return call<PlanResponse>('/api/plan', { method: 'POST', body: JSON.stringify(body), signal })
}

export function fetchHeatmap(
  body: { lines: [number, number][][]; departure: string; load_lb: number },
  signal?: AbortSignal,
) {
  return call<HeatmapResponse>('/api/heatmap', { method: 'POST', body: JSON.stringify(body), signal })
}

export function warmUp() {
  // Wake the serverless backend while the user fills in the form.
  fetch(`${BASE}/api/health`).catch(() => undefined)
}
