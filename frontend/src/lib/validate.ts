import type { TripInput } from '../types'

export type FieldErrors = Partial<Record<'origin' | 'destination' | 'departure' | 'load_lb' | 'interval_mi', string>>

const MAX_LOAD = 80_000

export function validate(t: TripInput): FieldErrors {
  const e: FieldErrors = {}
  if (!t.origin) e.origin = 'Choose a starting point from the suggestions.'
  if (!t.destination) e.destination = 'Choose a destination from the suggestions.'
  if (t.origin && t.destination && t.origin.label === t.destination.label) {
    e.destination = 'Destination must be different from the starting point.'
  }
  if (!t.departure) {
    e.departure = 'Pick a departure date and time.'
  } else {
    const dep = new Date(t.departure).getTime()
    const now = Date.now()
    if (Number.isNaN(dep)) e.departure = 'Enter a valid date and time.'
    else if (dep < now - 15 * 60_000) e.departure = 'This time has already passed. Pick a time from now onward.'
    else if (dep > now + 7 * 86_400_000) e.departure = 'Pick a departure within the next 7 days.'
  }
  const load = t.load_lb.trim() === '' ? NaN : Number(t.load_lb.replace(/,/g, ''))
  if (t.load_lb.trim() === '') e.load_lb = 'Enter the load weight in pounds.'
  else if (Number.isNaN(load)) e.load_lb = 'Load weight must be a number of pounds.'
  else if (load < 0) e.load_lb = 'Load weight cannot be negative.'
  else if (load > MAX_LOAD) e.load_lb = 'Load weight must be 80,000 lb or less.'
  return e
}
