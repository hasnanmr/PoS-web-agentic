// O2 / O2b period words and dates: "Hari ini", "Minggu ini", "1–17 Nov", "Jum, 20 Nov 2026".
import { formatRange, MONTHS, WEEKDAYS } from '../../lib/format'
import type { DashboardSummary, DrillPeriod } from '../../lib/types'

export interface DayRange { from: string; to: string }

/** Longest custom range the server accepts (screen-endpoint-map O2, `period=range`). */
export const MAX_RANGE_DAYS = 92

function toDate(day: string): Date {
  const [y, m, d] = day.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d))
}

function toDay(date: Date): string {
  return date.toISOString().slice(0, 10)
}

/** The days a period covers, up to and including `today` (week from Monday, like the server). */
export function periodDates(period: DrillPeriod, today: string, range?: DayRange): DayRange {
  if (period === 'range' && range) return range
  const t = toDate(today)
  if (period === 'week') {
    const monday = new Date(t)
    monday.setUTCDate(t.getUTCDate() - ((t.getUTCDay() + 6) % 7))
    return { from: toDay(monday), to: today }
  }
  if (period === 'month') return { from: `${today.slice(0, 7)}-01`, to: today }
  if (period === 'year') return { from: `${today.slice(0, 4)}-01-01`, to: today }
  return { from: today, to: today }
}

/** Drawer title word: "Hari ini", "Minggu ini", …, or "1–17 Nov" for a custom range. */
export function periodTitle(period: DrillPeriod, range?: DayRange): string {
  if (period === 'range' && range) return formatRange(range.from, range.to, false)
  return { today: 'Hari ini', week: 'Minggu ini', month: 'Bulan ini', year: 'Tahun ini', range: 'Rentang' }[period]
}

/** "Jum, 20 Nov 2026" for one day, else "16–20 Nov 2026". */
export function datesText({ from, to }: DayRange): string {
  if (from !== to) return formatRange(from, to)
  const d = toDate(from)
  return `${WEEKDAYS[(d.getUTCDay() + 6) % 7]}, ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

const PERIOD_WORD = { today: 'hari ini', week: 'minggu ini', month: 'bulan ini' } as const
const PREVIOUS = { today: 'kemarin', week: 'minggu lalu', month: 'bulan lalu', range: 'periode sebelumnya' } as const

/** O2 labels: "Revenue hari ini", "Order per jam · minggu ini", "Revenue 1–17 Nov". */
export function periodWord(data: Pick<DashboardSummary, 'period' | 'from' | 'to'>): string {
  return data.period === 'range' ? formatRange(data.from, data.to, false) : PERIOD_WORD[data.period]
}

/** The Revenue tile's comparison line: "▲ 8% vs kemarin", "Belum ada data periode sebelumnya". */
export function revenueChange(data: Pick<DashboardSummary, 'period' | 'kpis'>): string {
  const change = data.kpis.change_pct
  const previous = PREVIOUS[data.period]
  return change === null ? `Belum ada data ${previous}` : `${change < 0 ? '▼' : '▲'} ${Math.abs(change)}% vs ${previous}`
}
