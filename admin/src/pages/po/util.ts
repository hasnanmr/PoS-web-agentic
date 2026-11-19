// Shared helpers for the purchase-order screens: Dashboard tab "PO & Supplier" (O15–O17), Buka PO
// (O16, staff S12) and the staff screens S10/S11. Labels are the wireframe's Bahasa Indonesia copy.
import { MONTHS, formatDay } from '../../lib/format'
import type { PaymentTerm, PoChip, PoRow } from '../../lib/types'

export const TERM_LABEL: Record<PaymentTerm, string> = {
  pay_later: 'Bayar mundur',
  pay_in_advance: 'Bayar di muka',
}

/** O15 list chips (FR3.10): Semua + the status filters. */
export const CHIPS: { key: PoChip | null; label: string; danger?: boolean }[] = [
  { key: null, label: 'Semua' },
  { key: 'open', label: 'Terbuka' },
  { key: 'difference_found', label: 'Ada selisih' },
  { key: 'awaiting_payment', label: 'Menunggu bayar' },
  { key: 'overdue', label: 'Overdue', danger: true },
  { key: 'closed', label: 'Ditutup' },
]

export function newKey(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `k-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/** "2026-11" → "Nov 2026". */
export function monthLabel(month: string): string {
  const [y, m] = month.split('-').map(Number)
  return `${MONTHS[m - 1]} ${y}`
}

/** The last 12 months, newest first, for the tab's month filter. */
export function recentMonths(current: string, count = 12): string[] {
  let [y, m] = current.split('-').map(Number)
  const out: string[] = []
  for (let i = 0; i < count; i++) {
    out.push(`${y}-${String(m).padStart(2, '0')}`)
    m -= 1
    if (m === 0) {
      m = 12
      y -= 1
    }
  }
  return out
}

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000)
}

/** One status badge per row, most urgent first (O15 list, S10). */
export type Tone = 'primary' | 'success' | 'warning' | 'danger' | 'teal' | 'muted'

export function rowBadge(row: PoRow, today: string): { tone: Tone; label: string } {
  if (row.status === 'cancelled') return { tone: 'muted', label: 'Dibatalkan' }
  if (row.overdue && row.due_date) return { tone: 'danger', label: `Overdue ${daysBetween(row.due_date, today)} hari` }
  if (row.status === 'difference_found') return { tone: 'warning', label: 'Ada selisih qty' }
  const paid = row.payment_status === 'paid'
  if (row.status === 'closed') return paid ? { tone: 'success', label: 'Ditutup · lunas' } : { tone: 'warning', label: 'Menunggu bayar' }
  if (row.payment_term === 'pay_in_advance') {
    return paid ? { tone: 'teal', label: 'Menunggu barang' } : { tone: 'warning', label: 'Perlu dibayar' }
  }
  return { tone: 'primary', label: 'Terbuka' }
}

/** Second line of the TERMIN column: "JT 30 Nov", "Tiba ± 24 Nov", "Lunas". */
export function termDetail(row: PoRow): string {
  if (row.status === 'closed' && row.payment_status === 'paid') return 'Lunas'
  if (row.payment_term === 'pay_later') return row.due_date ? `JT ${formatDay(row.due_date)}` : ''
  return row.expected_date ? `Tiba ± ${formatDay(row.expected_date)}` : ''
}

/** Line subtotal in whole rupiah, half up — same rule as the server. */
export function lineSubtotal(quantity: string, unitPrice: number): number {
  const qty = Number(quantity.replace(',', '.'))
  if (!Number.isFinite(qty) || qty <= 0 || !Number.isFinite(unitPrice)) return 0
  return Math.floor(qty * unitPrice + 0.5)
}
