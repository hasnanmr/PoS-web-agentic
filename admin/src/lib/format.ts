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
