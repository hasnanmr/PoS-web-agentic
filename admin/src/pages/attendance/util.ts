// Shared helpers for O14 (Kehadiran Staf) and S9/M6 (Absensi Saya).
import { useEffect, useState } from 'react'
import { formatMinutes, formatTime, offsetAt, ZONE_LABEL } from '../../lib/format'
import type { AttendanceRecord } from '../../lib/types'

/** "09:00" (WIB) or "09:00 WITA" for outlets in other zones. */
export function timeIn(r: { timezone: string }, iso: string | null, withZone = true): string {
  if (!iso) return '—'
  const zone = r.timezone !== 'Asia/Jakarta' && withZone ? ` ${ZONE_LABEL[r.timezone]}` : ''
  return `${formatTime(iso, r.timezone)}${zone}`
}

export function durationCell(r: AttendanceRecord): string {
  if (r.status === 'open') return 'berjalan'
  return r.duration_minutes === null ? '—' : formatMinutes(r.duration_minutes)
}

export function selfieIcons(r: AttendanceRecord): string {
  return [r.has_selfie_in, r.has_selfie_out].filter(Boolean).map(() => '▣').join(' ') || '—'
}

export function nextDate(day: string): string {
  const d = new Date(`${day}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + 1)
  return d.toISOString().slice(0, 10)
}

/** "HH:MM" on the record's local day, or the next day for a clock-out at or before the clock-in. */
export function toInstant(day: string, time: string, tz: string, after?: string): string {
  const date = after && time <= after ? nextDate(day) : day
  return `${date}T${time}:00${offsetAt(tz, date, time)}`
}

/** Current time, refreshed every 30 seconds ("3 j 12 mnt" since clock in). */
export function useNow(): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(id)
  }, [])
  return now
}
