import { describe, expect, it } from 'vitest'
import type { TripInput } from '../types'
import { toLocalInput } from './format'
import { validate } from './validate'

const ok = (): TripInput => ({
  origin: { label: 'Chicago, IL', lat: 41.88, lon: -87.63 },
  destination: { label: 'Denver, CO', lat: 39.74, lon: -104.99 },
  departure: toLocalInput(new Date(Date.now() + 60 * 60_000)),
  load_lb: '38,000',
  interval_mi: 25,
})

describe('validate', () => {
  it('accepts a complete trip (commas allowed in the load)', () => {
    expect(validate(ok())).toEqual({})
  })

  it('asks for places picked from the suggestions', () => {
    const e = validate({ ...ok(), origin: null, destination: null })
    expect(e.origin).toMatch(/starting point/)
    expect(e.destination).toMatch(/destination/)
  })

  it('rejects the same place twice', () => {
    const t = ok()
    expect(validate({ ...t, destination: t.origin }).destination).toMatch(/different/)
  })

  it('checks the departure window', () => {
    expect(validate({ ...ok(), departure: toLocalInput(new Date(Date.now() - 3 * 3_600_000)) }).departure).toMatch(
      /already passed/,
    )
    expect(validate({ ...ok(), departure: toLocalInput(new Date(Date.now() + 9 * 86_400_000)) }).departure).toMatch(
      /7 days/,
    )
  })

  it('checks the load weight', () => {
    expect(validate({ ...ok(), load_lb: '' }).load_lb).toMatch(/Enter/)
    expect(validate({ ...ok(), load_lb: 'heavy' }).load_lb).toMatch(/number/)
    expect(validate({ ...ok(), load_lb: '-5' }).load_lb).toMatch(/negative/)
    expect(validate({ ...ok(), load_lb: '90000' }).load_lb).toMatch(/80,000/)
    expect(validate({ ...ok(), load_lb: '0' })).toEqual({})
  })
})
