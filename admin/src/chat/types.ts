// Customer web chat (page 07, C1–C15): response shapes of /public/o/{slug} and /public/t/{token}.
// Contract: docs/architecture/screen-endpoint-map.md → "Customer web chat (C1–C15)".
import type { MenuItem } from '../lib/types'

export type Scope = { kind: 'o'; slug: string } | { kind: 't'; token: string }

export interface ChatOutlet {
  name: string
  short_name: string
  timezone: string
  opening_hours: { weekday: number; opens_at: string; closes_at: string }[]
  is_open_now: boolean | null
}

export interface PrivacyNotice {
  version: string
  url: string
}

/** C1 (outlet link) or C8 (table QR): what the main menu offers. */
export interface ChatPage {
  outlet: ChatOutlet
  table: { name: string; area: string | null } | null
  reservations_enabled: boolean
  web_ordering: boolean
  delivery_fee: number
  agent_enabled: boolean
  privacy_notice: PrivacyNotice
}

export interface CartLine {
  product_id: string
  quantity: number
  addon_option_ids: string[]
  note: string | null
}

export interface ChatSession {
  step: string
  cart: { lines: CartLine[] }
  fulfillment: 'pickup' | 'delivery' | null
  last_activity_at: string | null
  cart_expired: boolean
}

export interface ChatQuote {
  lines: { product_id: string; name: string; unit_price: number; quantity: number; line_total: number }[]
  subtotal: number
  pb1_rate_bps: number | null
  pb1_amount: number
  delivery_fee: number
  total: number
}

export interface OrderCreated {
  order_id: string
  access_key: string
  order_no: string
  status: string
  payment_status: string
  subtotal: number
  pb1_amount: number
  delivery_fee: number
  total: number
  pay_by: string
}

export interface OrderStatus {
  id: string
  order_no: string
  created_at: string
  fulfillment: 'dine_in' | 'pickup' | 'delivery'
  customer_name: string | null
  delivery_address: string | null
  note: string | null
  status: string
  payment_status: string
  claimed_at: string | null
  pay_by: string
  items: { name: string; quantity: number; addons: string[]; note: string | null; line_total: number }[]
  subtotal: number
  pb1_amount: number
  delivery_fee: number
  total: number
  reject_reason: string | null
  cancel_reason: string | null
  events: { status: string; at: string }[]
  timezone: string
}

export interface OrderOverview {
  order_id: string
  order_no: string
  fulfillment: 'dine_in' | 'pickup' | 'delivery'
  status: string
  payment_status: string
  total: number
  created_at: string
}

export interface RecommendationCard {
  product_id: string
  name: string
  description: string | null
  price: number
  photo_url: string | null
  badge: 'owner_pick' | 'best_seller'
}

export interface Availability {
  date: string
  timezone: string
  max_party_size: number
  last_date: string
  times: { start_at: string; label: string }[]
}

export interface Booking {
  reservation_id: string
  booking_code: string
  start_at: string
  label: string
  timezone: string
  party_size: number
  status: string
  guest_name: string | null
  hold_until: string | null
  change_until: string
  can_change: boolean
  reminder_at: string | null
  outlet_name: string
}

export interface BookingCreated extends Booking {
  access_key: string
}

export type ChatMenuItem = MenuItem & { description?: string | null }
