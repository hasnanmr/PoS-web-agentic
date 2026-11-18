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
