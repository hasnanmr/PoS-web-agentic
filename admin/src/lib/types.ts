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

// Orders, bills, shifts (S1, S2, S3, S5, S8) ------------------------------------------

export interface MenuOption { id: string; name: string; price: number; available: boolean }
export interface MenuGroup {
  id: string
  name: string
  selection: 'single' | 'multiple'
  is_required: boolean
  options: MenuOption[]
}
export interface MenuItem {
  product_id: string
  name: string
  category: string | null
  is_owner_pick: boolean
  price: number
  photo_url: string | null
  sold_out: boolean
  sold_out_reason: string | null
  addon_groups: MenuGroup[]
}

export interface TableRow {
  id: string
  name: string
  area: string | null
  open_bill: { id: string; total: number } | null
}

export interface Quote {
  lines: { product_id: string; name: string; unit_price: number; quantity: number; line_total: number;
    addons: { id: string; name: string; price: number }[] }[]
  subtotal: number
  pb1_rate_bps: number | null
  pb1_amount: number
  total: number
}

export interface OrderCreated {
  id: string
  order_no: string
  status: string
  payment_status: string
  subtotal: number
  pb1_amount: number
  total: number
  change_due: number | null
  bill_id: string | null
}

export type OrderStatus =
  | 'pending_payment' | 'confirmed' | 'preparing' | 'ready' | 'out_for_delivery' | 'served' | 'completed' | 'cancelled'
export type PaymentStatus = 'unpaid' | 'proof_submitted' | 'paid' | 'refunded'

export interface OrderCard {
  id: string
  order_no: string
  channel: 'counter' | 'whatsapp_online' | 'whatsapp_table'
  type: 'dine_in' | 'takeaway' | 'delivery' | 'pickup'
  payment_mode: 'pay_first' | 'open_bill'
  status: OrderStatus
  payment_status: PaymentStatus
  payment_method: 'cash' | 'qris' | null
  table: string | null
  customer_name: string | null
  item_summary: string
  total: number
  bill_id: string | null
  created_at: string
  auto_cancel_at: string | null
  allowed_actions: string[]
}

export interface Board {
  awaiting_payment: OrderCard[]
  confirmed: OrderCard[]
  preparing: OrderCard[]
  ready: OrderCard[]
  done_today: OrderCard[]
}

export interface OrderEvent {
  at: string
  kind: string
  from: string | null
  to: string | null
  from_payment: string | null
  to_payment: string | null
  reason: string | null
  data: Record<string, unknown>
  actor: { type: string; name: string | null; role: string | null }
}

export interface OrderDetail extends OrderCard {
  items: { id: string; name: string; unit_price: number; quantity: number; line_total: number; note: string | null;
    addons: { name: string; price: number }[] }[]
  subtotal: number
  pb1_rate_bps: number | null
  pb1_amount: number
  delivery_fee: number
  timezone: string
  events: OrderEvent[]
  refund?: { amount: number; method: string } | null
}

export interface BillCard {
  id: string
  table_id: string | null
  table_name: string | null
  table_area: string | null
  guest_name: string | null
  running_total: number
  order_count: number
  opened_at: string
}

export interface BillDetail {
  id: string
  table_name: string | null
  table_area: string | null
  guest_name: string | null
  status: string
  opened_at: string
  orders: { id: string; order_no: string; channel: string; created_at: string; status: string; line_total: number;
    items: { name: string; quantity: number; addons: string }[] }[]
  subtotal: number
  pb1_rate_bps: number | null
  pb1_amount: number
  total: number
}

export interface ShiftRow {
  id: string
  drawer_id: string
  drawer_name: string
  drawer_number: number
  opened_at: string
  starting_cash: number
  /** Who opened the shift: the counter prefers the cashier's own shift when several are open. */
  opened_by: string | null
  opened_by_name: string | null
}

export interface DrawerCard {
  drawer: { id: string; name: string }
  shift: { id: string; opened_at: string; starting_cash: number; opened_by: string | null; cash_in: number;
    cash_in_count: number; cash_refunds: number } | null
}

// S8 close (blind count) ---------------------------------------------------------------
export interface ShiftClosed {
  id: string
  drawer: { id: string; name: string | null }
  opened_at: string
  closed_at: string
  timezone: string
  starting_cash: number
  cash_in: number
  cash_refunds: number
  expected_cash: number
  counted_cash: number
  difference: number
  kind: 'shortage' | 'surplus' | 'none'
  counted_by: string | null
}

// S4 Review Pembayaran QRIS -------------------------------------------------------------
export interface ProofQueueItem {
  proof_id: string
  order_id: string
  order_no: string
  channel: OrderCard['channel']
  order_type: OrderCard['type']
  table: string | null
  total: number
  received_at: string
  timezone: string
}

export interface ProofDetail {
  proof_id: string
  status: 'pending' | 'accepted' | 'rejected'
  image_url: string | null
  order_id: string
  order_no: string
  channel: OrderCard['channel']
  order_type: OrderCard['type']
  table: string | null
  total: number
  order_status: string
  payment_status: string
  customer_phone_masked: string | null
  received_at: string
  timezone: string
  timer_stopped: boolean
  reviewed_by: string | null
  reviewed_at: string | null
  rejection_reason: string | null
}

// O9 Laporan Cashflow & Pengeluaran ------------------------------------------------------
export interface Expense {
  id: number
  business_date: string
  outlet: { id: string; name: string }
  description: string
  amount: number
  recorded_by: string | null
  created_at: string
  reversed: boolean
  reversal_reason: string | null
}

export interface ExpensePage {
  items: Expense[]
  next_cursor: string | null
}

export interface Tile {
  amount: number
  change_pct: number | null
}

export type Granularity = 'daily' | 'weekly' | 'monthly'

export interface Cashflow {
  from: string
  to: string
  granularity: Granularity
  previous: { from: string; to: string }
  totals: { cash_in: Tile; cash_out: Tile; net: Tile; pb1_collected: Tile }
  series: { date: string; cash_in: number; cash_out: number }[]
  breakdown: {
    revenue_excl_pb1: number
    pb1: number
    delivery_fee: number
    cash: number
    qris: number
    refunds: number
    expenses: number
    cash_difference: number
  }
  expenses_by_outlet: { outlet_id: string; outlet: string; amount: number; count: number }[]
  expenses_total: number
  expenses_count: number
}

// O10 Laporan Cash Count ------------------------------------------------------------------
export interface CashCountRow {
  shift_id: string
  opened_at: string
  closed_at: string
  timezone: Timezone
  outlet: { id: string; name: string }
  drawer: { id: string; name: string; number: number }
  starting_cash: number
  expected_cash: number
  counted_cash: number
  difference: number
  kind: 'shortage' | 'surplus' | 'none'
  counted_by: string | null
}

export interface CashCount {
  from: string
  to: string
  summary: { shifts: number; shifts_with_difference: number; total_shortage: number; total_surplus: number }
  rows: CashCountRow[]
}
