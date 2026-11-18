// Response shapes from docs/api/openapi.json (screen-endpoint-map.md). Keep in sync with the API.

export type Timezone = 'Asia/Jakarta' | 'Asia/Makassar' | 'Asia/Jayapura'
export type PaymentMode = 'pay_first' | 'open_bill'

export interface MeOutlet {
  id: string
  name: string
  timezone: Timezone
  order_prefix: string
  payment_mode: PaymentMode
}

export interface Me {
  user: { id: string; email: string | null; display_name: string | null }
  role: 'owner' | 'staff' | 'owner_pending'
  onboarding_required: boolean
  tenant: { id: string; name: string; type: 'cafe' | 'restaurant' } | null
  outlets: MeOutlet[]
}

export interface OutletSummary {
  id: string
  name: string
  timezone: Timezone
  order_prefix: string
  is_active: boolean
}

export interface OpeningHours {
  weekday: number
  opens_at: string
  closes_at: string
}

export interface OutletDetail {
  id: string
  name: string
  address: string | null
  timezone: Timezone
  whatsapp_phone: string | null
  whatsapp_status: 'not_started' | 'pending_verification' | 'connected' | 'error'
  catalog_synced_at: string | null
  order_prefix: string
  payment_mode: PaymentMode
  pb1_enabled: boolean
  pb1_rate_bps: number | null
  delivery_fee: number
  unpaid_timeout_minutes: number
  attendance_grace_minutes: number
  is_active: boolean
  opening_hours: OpeningHours[]
}

export interface Drawer {
  id: string
  name: string
  has_open_shift: boolean
}

export interface StaffMember {
  id: string
  display_name: string
  email: string
  outlets: { id: string; name: string }[]
  status: 'active' | 'inactive' | 'invited'
}

export const TIMEZONE_LABEL: Record<Timezone, string> = {
  'Asia/Jakarta': 'WIB (Asia/Jakarta)',
  'Asia/Makassar': 'WITA (Asia/Makassar)',
  'Asia/Jayapura': 'WIT (Asia/Jayapura)',
}

// Catalog & stock (O5, O6, S7) -------------------------------------------------------

export type Unit = 'g' | 'ml' | 'pcs'
export type DisplayUnit = 'g' | 'kg' | 'ml' | 'L' | 'pcs'
export type ProductStatus = 'active' | 'sold_out' | 'inactive'

export interface ProductRow {
  id: string
  name: string
  category: string | null
  is_owner_pick: boolean
  is_sample: boolean
  has_photo: boolean
  addon_group_count: number
  ingredient_count: number
  price: number | null
  status: ProductStatus
}

export interface RecipeLine {
  stock_item_id: string
  stock_item: string
  unit: Unit
  quantity: string
}

export interface AddonOption {
  id: string
  name: string
  sort_order: number
  prices: { outlet_id: string; price: number }[]
  recipe: RecipeLine[]
}

export interface AddonGroup {
  id: string
  name: string
  selection: 'single' | 'multiple'
  is_required: boolean
  sort_order: number
  options: AddonOption[]
}

export interface ProductDetail {
  id: string
  name: string
  category: string | null
  description: string | null
  is_owner_pick: boolean
  is_active: boolean
  is_sample: boolean
  has_photo: boolean
  tags: string[]
  prices: { outlet_id: string; outlet_name: string; price: number | null }[]
  addon_groups: AddonGroup[]
  catalog_sync: string
}

export interface StockItem {
  id: string
  name: string
  unit: Unit
  display_unit: DisplayUnit | null
  thresholds: { outlet_id: string; low_threshold: string }[]
}

export interface Availability {
  outlet_id: string
  outlet_name: string
  portions_available: number
  sold_out: boolean
  limiting_stock_item: string | null
}

export interface StockRow {
  stock_item_id: string
  name: string
  unit: Unit
  display_unit: DisplayUnit | null
  on_hand: string
  low_threshold: string
  status: 'ok' | 'low' | 'out'
  affected_products: { name: string; kind: 'product' | 'addon'; sold_out: boolean }[]
}

export interface StockResponse {
  counts: { low: number; out: number }
  items: StockRow[]
}

export interface Movement {
  id: number
  at: string
  type: 'sale' | 'sale_reversal' | 'restock' | 'waste' | 'adjustment'
  quantity: string
  unit: Unit
  display_unit: DisplayUnit | null
  stock_item: string
  order_no: string | null
  note: string | null
  actor_type: string
  actor: string
}
