// Display helpers matching the wireframe copy (Rp 92.400, Sen–Min 08:00 – 22:00, "2 menit lalu").

const rupiah = new Intl.NumberFormat('id-ID', { maximumFractionDigits: 0 })

export function formatRupiah(amount: number): string {
  return `${amount < 0 ? '− ' : ''}Rp ${rupiah.format(Math.abs(amount))}`
}

export const WEEKDAYS = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min'] as const

export function hhmm(value: string): string {
  return value.slice(0, 5)
}

export function summarizeHours(hours: { weekday: number; opens_at: string; closes_at: string }[]): string {
  if (hours.length === 0) return 'Tutup setiap hari'
  const sorted = [...hours].sort((a, b) => a.weekday - b.weekday)
  const same = sorted.every((h) => h.opens_at === sorted[0].opens_at && h.closes_at === sorted[0].closes_at)
  const consecutive = sorted.every((h, i) => h.weekday === sorted[0].weekday + i)
  if (same && consecutive) {
    const first = WEEKDAYS[sorted[0].weekday - 1]
    const last = WEEKDAYS[sorted[sorted.length - 1].weekday - 1]
    const days = sorted.length === 1 ? first : `${first}–${last}`
    return `${days}  ${hhmm(sorted[0].opens_at)} – ${hhmm(sorted[0].closes_at)}`
  }
  return sorted.map((h) => `${WEEKDAYS[h.weekday - 1]} ${hhmm(h.opens_at)}–${hhmm(h.closes_at)}`).join(', ')
}

export function timeAgo(iso: string, now: Date = new Date()): string {
  const minutes = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 60000))
  if (minutes < 1) return 'baru saja'
  if (minutes < 60) return `${minutes} menit lalu`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} jam lalu`
  return `${Math.round(hours / 24)} hari lalu`
}

const LARGE: Record<string, { unit: string; factor: number }> = {
  kg: { unit: 'kg', factor: 1000 },
  L: { unit: 'L', factor: 1000 },
}

function idNumber(value: number, maxFraction = 3): string {
  return new Intl.NumberFormat('id-ID', { maximumFractionDigits: maxFraction }).format(value)
}

/** Base-unit quantity in the item's display unit, like S7: "2,4 kg", "180 g", "140 pcs". */
export function formatQty(qty: string | number, unit: string, displayUnit?: string | null): string {
  const value = Number(qty)
  const large = displayUnit ? LARGE[displayUnit] : undefined
  if (large) return `${idNumber(value / large.factor)} ${large.unit}`
  if (!displayUnit && unit !== 'pcs' && Math.abs(value) >= 1000) {
    return `${idNumber(value / 1000)} ${unit === 'g' ? 'kg' : 'L'}`
  }
  return `${idNumber(value)} ${unit}`
}

/** Signed delta for recipes and movements: "+ 6 g", "− 150 ml". */
export function formatDelta(qty: string | number, unit: string, displayUnit?: string | null): string {
  const value = Number(qty)
  return `${value < 0 ? '−' : '+'} ${formatQty(Math.abs(value), unit, displayUnit)}`
}

/** Factor from the display unit the user types in to the base unit stored. */
export function displayFactor(displayUnit?: string | null): number {
  return displayUnit && LARGE[displayUnit] ? LARGE[displayUnit].factor : 1
}

export function formatTime(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat('id-ID', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone })
    .format(new Date(iso))
    .replace('.', ':')
}

/** A decimal string from the API (e.g. "125.000", "0.500") as editable id-ID text ("125", "0,5"), without rounding through Number. */
export function plainQuantity(value: string | number): string {
  const text = String(value)
  if (!text.includes('.')) return text
  return text.replace(/\.?0+$/, '').replace('.', ',')
}

export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'] as const

/** Plain thousands, as in the O10 table: "1.678.400". */
export function formatNumber(amount: number): string {
  return rupiah.format(amount)
}

/** Signed amount with a space, as in O9/O10: "+ Rp 82.000", "− Rp 50.000", "Rp 0". */
export function formatSignedRupiah(amount: number): string {
  if (amount === 0) return 'Rp 0'
  return `${amount < 0 ? '−' : '+'} Rp ${rupiah.format(Math.abs(amount))}`
}

function parts(day: string): [number, number, number] {
  const [y, m, d] = day.split('-').map(Number)
  return [y, m, d]
}

/** "2026-11-17" → "17 Nov". */
export function formatDay(day: string): string {
  const [, m, d] = parts(day)
  return `${d} ${MONTHS[m - 1]}`
}

/** "1–17 Nov 2026", "28 Okt – 3 Nov 2026", "17 Nov 2026" (O9/O10 date pickers). */
export function formatRange(from: string, to: string, withYear = true): string {
  const [fy, fm, fd] = parts(from)
  const [ty, tm, td] = parts(to)
  const year = withYear ? ` ${ty}` : ''
  if (from === to) return `${td} ${MONTHS[tm - 1]}${year}`
  if (fy === ty && fm === tm) return `${fd}–${td} ${MONTHS[tm - 1]}${year}`
  if (fy === ty) return `${fd} ${MONTHS[fm - 1]} – ${td} ${MONTHS[tm - 1]}${year}`
  return `${fd} ${MONTHS[fm - 1]} ${fy} – ${td} ${MONTHS[tm - 1]}${year}`
}

/** The outlet-local calendar date of an instant, as "YYYY-MM-DD". */
export function localDay(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' })
    .format(new Date(iso))
}

/** Today in a zone, as "YYYY-MM-DD". */
export function todayIn(timeZone: string, now: Date = new Date()): string {
  return localDay(now.toISOString(), timeZone)
}

/** "Bandung – Dago" → "Dago" (short outlet labels in O9/O10 rows). */
export function shortOutlet(name: string): string {
  const cut = name.lastIndexOf('– ')
  return cut >= 0 ? name.slice(cut + 2) : name
}

export const ZONE_LABEL: Record<string, string> = {
  'Asia/Jakarta': 'WIB',
  'Asia/Makassar': 'WITA',
  'Asia/Jayapura': 'WIT',
}

/** UTC offset ("+08:00") of `tz` at a local date and time, so `starts_at` is sent in the outlet zone. */
export function offsetAt(tz: string, date: string, time: string): string {
  const name = new Intl.DateTimeFormat('en-US', { timeZone: tz, timeZoneName: 'longOffset' })
    .formatToParts(new Date(`${date}T${time}:00Z`)).find((p) => p.type === 'timeZoneName')?.value ?? 'GMT'
  const m = /GMT([+-])(\d{2}):?(\d{2})?/.exec(name)
  return m ? `${m[1]}${m[2]}:${m[3] ?? '00'}` : '+00:00'
}
