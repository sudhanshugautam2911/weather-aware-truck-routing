const timeFmt = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' })
const dayTimeFmt = new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })
const dayHourFmt = new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })
const tzFmt = new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' })

export function formatTime(iso: string) {
  return timeFmt.format(new Date(iso))
}

export function formatDayTime(iso: string) {
  return dayTimeFmt.format(new Date(iso))
}

export function formatDayHour(iso: string) {
  return dayHourFmt.format(new Date(iso))
}

export function timeZoneName() {
  const part = tzFmt.formatToParts(new Date()).find((p) => p.type === 'timeZoneName')
  return part?.value ?? 'local time'
}

export function formatDuration(seconds: number) {
  const mins = Math.round(seconds / 60)
  const h = Math.floor(mins / 60)
  const m = mins % 60
  if (h === 0) return `${m} min`
  return m === 0 ? `${h} h` : `${h} h ${m} min`
}

export function formatMiles(mi: number, digits = 0) {
  return `${mi.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits })} mi`
}

export function formatNumber(n: number, digits = 0) {
  return n.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

/** datetime-local value (browser time zone) for `date`, rounded up to 15 minutes. */
export function toLocalInput(date: Date) {
  const d = new Date(date)
  d.setSeconds(0, 0)
  d.setMinutes(Math.ceil(d.getMinutes() / 15) * 15)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
