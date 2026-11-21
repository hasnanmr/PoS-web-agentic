// Dates and times in the outlet's zone for the booking screens (C10-C12).
import { ZONE_LABEL } from '../lib/format'

export const zone = (tz: string) => ZONE_LABEL[tz] ?? ''

export function addDays(day: string, n: number): string {
  const d = new Date(`${day}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

/** "Sab 21", "Min 22 Nov" (outlet calendar date, Indonesian). */
export function dayLabel(day: string, withMonth: boolean): string {
  const d = new Date(`${day}T12:00:00Z`)
  const fmt = new Intl.DateTimeFormat('id-ID', { weekday: 'short', day: 'numeric', ...(withMonth ? { month: 'short' } : {}), timeZone: 'UTC' })
  return fmt.format(d).replace(/\./g, '').replace(',', '')
}

/** "Minggu, 22 Nov 2026" in the outlet's zone. */
export function longDate(iso: string, tz: string): string {
  return new Intl.DateTimeFormat('id-ID', { weekday: 'long', day: 'numeric', month: 'short', year: 'numeric', timeZone: tz })
    .format(new Date(iso)).replace(/\./g, '')
}

export function shortDate(iso: string, tz: string): string {
  return new Intl.DateTimeFormat('id-ID', { weekday: 'short', day: 'numeric', month: 'short', timeZone: tz })
    .format(new Date(iso)).replace(/\./g, '').replace(',', '')
}
