// Order labels shared by S2 (Order Board), S3 (order detail), and O2b (dashboard drawer).
import type { OrderCard } from '../../lib/types'

export const TYPE_LABEL: Record<OrderCard['type'], string> = {
  dine_in: 'Dine-in', takeaway: 'Takeaway', delivery: 'Delivery', pickup: 'Pickup',
}

// S2 web_online card (page 07): "🛵 Delivery · Rina · 0812-3456-7221", "🛍 Pickup · Dimas · …".
const WEB_ONLINE_ICON: Partial<Record<OrderCard['type'], string>> = { delivery: '🛵', pickup: '🛍' }

export function where(o: OrderCard): string {
  const base = TYPE_LABEL[o.type]
  if (o.channel === 'web_online') {
    return [`${WEB_ONLINE_ICON[o.type] ?? ''} ${base}`.trim(), o.customer_name, o.customer_phone].filter(Boolean).join(' · ')
  }
  if (o.channel === 'web_table') return `${base} · ${o.table}${o.customer_name ? ` · ${o.customer_name}` : ''}`
  if (o.table) return `${base} · ${o.table}${o.channel === 'whatsapp_table' ? ` · ${o.payment_mode === 'open_bill' ? 'open bill' : 'pay-first'}` : ''}`
  if (o.customer_name) return `${base} · ${o.customer_name}`
  return base
}

export function paymentText(o: OrderCard): string {
  if (o.bill_id && o.payment_status !== 'paid' && o.payment_status !== 'refunded') return 'di bill'
  if (o.payment_status === 'paid') return `paid (${o.payment_method === 'qris' ? `QRIS${o.qris_checked ? ' ✓ dicek' : ''}` : 'cash'})`
  return o.payment_status
}
