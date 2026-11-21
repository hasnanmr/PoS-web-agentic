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

// O3 · Tablet absensi (T-121) ------------------------------------------------------------
export interface AttendanceDevice {
  id: string
  name: string
  paired_at: string
  last_seen_at: string | null
  revoked_at: string | null
}

export interface PairingCode {
  code: string
  expires_at: string
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
  /** Signed, short-lived URL of the menu photo (T-132); null without a photo. */
  photo_url: string | null
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
  photo_url: string | null
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
  channel: 'counter' | 'whatsapp_online' | 'whatsapp_table' | 'web_table' | 'web_online'
  type: 'dine_in' | 'takeaway' | 'delivery' | 'pickup'
  payment_mode: 'pay_first' | 'open_bill'
  status: OrderStatus
  payment_status: PaymentStatus
  payment_method: 'cash' | 'qris' | null
  payment_id: string | null
  /** QRIS only: found in the receiving account (S2 "Cek →"); null otherwise. */
  qris_checked: boolean | null
  table: string | null
  customer_name: string | null
  /** web_online: number to call; cleared once the order is finished. */
  customer_phone?: string | null
  /** web_online delivery: where to deliver; cleared once the order is finished. */
  delivery_address?: string | null
  /** Web orders: "Catatan untuk dapur". */
  note: string | null
  /** Pending payment proof to review in S4. */
  proof_id: string | null
  /** Web orders: "Pelanggan bilang sudah bayar · 12:44" (no screenshot). */
  payment_claimed_at: string | null
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
export type ProofKind = 'screenshot' | 'customer_claim'

export interface ProofQueueItem {
  proof_id: string
  /** customer_claim = "Saya sudah bayar" on the table web page, no screenshot. */
  kind: ProofKind
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
  kind: ProofKind
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

// O9 Laporan Cashflow & Pengeluaran, O9b Pengeluaran ------------------------------------------------------
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
  /** O9b: "po" = a supplier payment on a purchase order, "direct" = logged by the owner. */
  source: 'po' | 'direct'
  payment_method: 'cash' | 'transfer' | null
  purchase_order: {
    id: string
    number: string
    supplier: { id: string; name: string }
    created_by: string | null
    created_by_role: 'owner' | 'staff' | null
    payment_term: 'pay_later' | 'pay_in_advance'
    /** Right after this payment, not today's PO state. */
    payment_status: 'unpaid' | 'partially_paid' | 'paid'
  } | null
}

export interface ExpenseSummary {
  from: string
  to: string
  total: { amount: number; count: number }
  /** `count` = payments (list rows); `po_count` = distinct POs paid. */
  po: { amount: number; count: number; po_count: number }
  direct: { amount: number; count: number }
  by_supplier: { supplier: { id: string; name: string }; amount: number; count: number }[]
  po_owed: { amount: number; count: number; overdue_count: number }
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

/** O3 "QRIS statis outlet" (PoC demo). */
export interface QrisStatus {
  image: { filename: string; content_type: string; size: number; uploaded_at: string } | null
}

// O2 Dashboard · Item terlaris (GET /owner/dashboard/top-items)
export type TopItemsPeriod = 'day' | 'month' | 'year'

export interface TopItem {
  product_id: string
  name: string
  quantity_sold: number
  revenue: number
}

export interface TopItems {
  period: TopItemsPeriod
  top_items: TopItem[]
}

// O11 Audit Log — GET /owner/audit-log (T-101) -------------------------------------------
export type AuditKind = 'reversal' | 'status' | 'payment'

export interface AuditRow {
  id: number
  created_at: string
  timezone: string
  outlet_id: string
  order_id: string
  order_no: string
  kind: AuditKind
  change: string
  actor: { type: 'user' | 'system' | 'agent' | 'device'; id: string | null; name: string | null; role: string | null }
  reason: string | null
}

export interface AuditPage {
  date_from: string
  date_to: string
  items: AuditRow[]
  next_cursor: string | null
}

// O2 tab Ringkasan — GET /owner/dashboard (T-071, T-123) ---------------------------------
export type DashboardPeriod = 'today' | 'week' | 'month' | 'range'
export type HoursFilter = 'all' | 'busy' | 'quiet'
export type CrowdLevel = 'ramai' | 'normal' | 'sepi'

export interface DashboardKpis {
  revenue_excl_pb1: number
  change_pct: number | null
  orders: number
  cash_count: number
  qris_count: number
  pb1_collected: number
  delivery_fee: number
  delivery_orders: number
}

export interface HourSummary {
  hours: number[]
  orders: number
  share_pct: number
}

export interface DashboardSummary {
  period: DashboardPeriod
  /** The days used (first selected outlet's zone), "YYYY-MM-DD". */
  from: string
  to: string
  hours: HoursFilter
  as_of: string
  kpis: DashboardKpis
  busyness_map: { weekday: number; hour: number; avg_orders: number }[]
  current_crowd: {
    outlet_id: string
    name: string
    timezone: string
    occupied_tables: number
    total_tables: number
    active_orders: number
    level: CrowdLevel
  }[]
  orders_per_hour: { hour: number; orders: number; mark: 'busy' | 'quiet' | null }[]
  busy_summary: HourSummary
  quiet_summary: HourSummary
  low_stock: {
    stock_item: string
    outlet_id: string
    outlet: string
    on_hand: string
    low_threshold: string
    unit: string
    display_unit: string | null
    status: 'low' | 'out'
  }[]
  channel_mix: { channel: 'web_online' | 'web_table' | 'counter' | 'whatsapp_online' | 'whatsapp_table'; orders: number; share_pct: number }[]
  payment_methods: { method: 'cash' | 'qris'; amount: number; transactions: number }[]
}

// O2b drawer detail Revenue / Order — GET /owner/dashboard/orders ------------------------
export type DrillPeriod = DashboardPeriod | 'year'

export interface DashboardOrderRow {
  id: string
  order_no: string
  outlet_id: string
  outlet: string
  timezone: string
  created_at: string
  channel: OrderCard['channel']
  type: OrderCard['type']
  table: string | null
  customer_name: string | null
  payment_method: 'cash' | 'qris' | null
  item_summary: string
  revenue_excl_pb1: number
  total: number
}

export interface DashboardOrders {
  period: DrillPeriod
  summary: { orders: number; revenue_excl_pb1: number; cash_count: number; qris_count: number }
  item: { product_id: string; name: string; quantity: number; revenue: number } | null
  by_outlet: { outlet_id: string; name: string; orders: number; revenue_excl_pb1: number }[]
  orders: DashboardOrderRow[]
  next_cursor: string | null
}

// Purchase orders — Dashboard tab "PO & Supplier" (O15–O17), O16/S12, S10, S11 -----------
export type PaymentTerm = 'pay_later' | 'pay_in_advance'
export type PoStatus = 'open' | 'difference_found' | 'closed' | 'cancelled'
export type GoodsStatus = 'not_arrived' | 'partly_arrived' | 'arrived'
export type PoPaymentStatus = 'unpaid' | 'partially_paid' | 'paid'
export type PoAction = 'receive' | 'close' | 'close_with_note' | 'record_payment' | 'cancel'
export type PoChip = 'open' | 'difference_found' | 'awaiting_payment' | 'overdue' | 'closed'

export interface Ref { id: string; name: string }

export interface PoRow {
  id: string
  number: string
  supplier: Ref
  outlet: Ref
  payment_term: PaymentTerm
  ordered_on: string
  due_date: string | null
  expected_date: string | null
  status: PoStatus
  goods_status: GoodsStatus
  payment_status: PoPaymentStatus
  overdue: boolean
  total: number
  created_at: string
  created_by: string | null
  /** Owner only (null for staff). */
  amount_paid: number | null
  amount_owed: number | null
}

export interface PoPage { items: PoRow[]; next_cursor: string | null }

/** S10 chips: Terbuka / Menunggu barang / Ditutup. */
export type OutletChip = 'active' | 'waiting_goods' | 'closed'
export interface OutletPoPage extends PoPage { counts: { active: number; waiting_goods: number } }

export interface PoLine {
  id: string
  item: string
  stock_item_id: string | null
  quantity: string
  unit: string
  unit_price: number
  subtotal: number
  received_quantity: string
  remaining_quantity: string
  check: 'match' | 'short'
}

export interface PoEvent {
  at: string
  kind: 'opened' | 'received' | 'paid' | 'closed' | 'cancelled'
  actor: { name: string | null; role: string | null }
  data: Record<string, unknown>
}

export interface PoDetail extends PoRow {
  note: string | null
  close_note: string | null
  cancel_reason: string | null
  lines: PoLine[]
  events: PoEvent[]
  allowed_actions: PoAction[]
}

export interface Supplier { id: string; name: string; phone: string | null; note: string | null; is_active: boolean }

export interface Bucket { count: number; amount: number }

export interface PoSummary {
  month: string
  total: Bucket
  status: { open: Bucket; closed: Bucket }
  goods: Record<GoodsStatus, Bucket>
  payment: Record<PoPaymentStatus, Bucket>
  by_term: Record<PaymentTerm, Bucket>
}

export interface PaymentItem {
  po_id: string
  number: string
  supplier: Ref
  outlet: Ref
  payment_term: PaymentTerm
  reason: 'overdue' | 'due' | 'pay_in_advance'
  status: 'open' | 'difference_found' | 'closed'
  due_date: string | null
  expected_date: string | null
  days_overdue: number | null
  total: number
  amount_paid: number
  amount_owed: number
  created_by: string | null
  /** Bayar only with record_payment. */
  allowed_actions: PoAction[]
}

export interface SupplierPayments {
  debt_total: number
  overdue_count: number
  due_7d_amount: number
  due_7d_count: number
  prepaid_not_received: number
  prepaid_not_received_count: number
  items: PaymentItem[]
}

export interface PoDifference {
  po_id: string
  number: string
  supplier: Ref
  outlet: Ref
  payment_term: PaymentTerm
  short_lines: { item: string; ordered: string; received: string; short: string; unit: string }[]
  last_received_on: string | null
  last_received_at: string | null
  days_since_last_received: number | null
  /** Tutup dengan catatan only with close_with_note. */
  allowed_actions: PoAction[]
}

export interface PoDashboard {
  po_summary: PoSummary
  supplier_payments: SupplierPayments
  po_differences: PoDifference[]
}

// O8 · Meja & Aturan Reservasi (T-057)
export interface OwnerTable {
  id: string
  name: string
  capacity: number
  area: string | null
  is_bookable: boolean
}

export interface ReservationSettings {
  is_enabled: boolean
  bookable_from: string
  bookable_until: string
  default_duration_minutes: number
  booking_window_days: number
  max_party_size: number
  reminder_offset_minutes: number
  cancellation_cutoff_minutes: number
  hold_minutes: number
}

// S6 / M4 · Reservasi & Meja (T-062, T-063, T-064)
export type ReservationStatus = 'booked' | 'seated' | 'completed' | 'cancelled' | 'no_show'
export type ReservationAction = 'seat' | 'move' | 'cancel' | 'no_show' | 'complete'

export interface ReservationRow {
  id: string
  table_id: string
  table_name: string
  guest_name: string | null
  party_size: number
  starts_at: string
  ends_at: string
  status: ReservationStatus
  source: 'whatsapp' | 'phone' | 'in_person' | 'walk_in'
  hold_until: string | null
  no_show_at: string | null
  allowed_actions: ReservationAction[]
}

export interface ReservationBoard {
  date: string
  timezone: string
  settings: {
    bookable_from: string
    bookable_until: string
    default_duration_minutes: number
    max_party_size: number
    booking_window_days: number
    hold_minutes: number
  }
  tables: { id: string; name: string; capacity: number; area: string | null; is_bookable: boolean }[]
  reservations: ReservationRow[]
}

export interface ReservationDetail extends ReservationRow {
  phone_masked: string | null
  timezone: string
  events: {
    event: string
    from_status: ReservationStatus | null
    to_status: ReservationStatus | null
    from_table: string | null
    to_table: string | null
    reason: string | null
    actor_type: 'user' | 'system' | 'agent' | 'device'
    actor_name: string | null
    created_at: string
  }[]
}

// O14 · Kehadiran Staf / S9 · Absensi Saya (T-118, T-119, T-122) -----------------------------
export type AttendanceStatus = 'open' | 'closed' | 'needs_correction' | 'corrected'

export interface AttendanceRecord {
  id: string
  date: string
  user: { id: string; name: string }
  outlet: { id: string; name: string }
  timezone: string
  clock_in_at: string
  clock_out_at: string | null
  duration_minutes: number | null
  has_selfie_in: boolean
  has_selfie_out: boolean
  status: AttendanceStatus
}

export interface AttendanceReport {
  from: string
  to: string
  summary: { user: { id: string; name: string }; outlets: string[]; worked_minutes: number; days: number }[]
  needs_correction_count: number
  records: AttendanceRecord[]
}

export interface AttendanceTimes {
  clock_in_at: string | null
  clock_out_at: string | null
}

export interface AttendanceDetail extends AttendanceRecord {
  devices: { clock_in: string | null; clock_out: string | null }
  original: AttendanceTimes
  flag: { at: string; closes_at: string | null; grace_minutes: number | null } | null
  corrections: { at: string; by: string; from: AttendanceTimes; to: AttendanceTimes; reason: string | null }[]
}

export interface MyAttendanceToday {
  status: 'working' | 'not_clocked_in'
  clock_in_at: string | null
  device_name: string | null
  outlet: { name: string; timezone: string | null } | null
  flagged_records: { id: string; date: string; outlet: { name: string } }[]
}

export interface MyAttendanceHistory {
  from: string
  to: string
  records: AttendanceRecord[]
  total_minutes: number
}

// O8 · QR meja (T-136) ----------------------------------------------------------------------------
export type TableQrTarget = 'web_whatsapp' | 'web' | 'whatsapp'

export interface TableQrSettings {
  target: TableQrTarget
  whatsapp_connected: boolean
}

// O7 · Rekomendasi (T-073) -----------------------------------------------------------------------
export interface OwnerPick {
  product_id: string
  name: string
  category: string | null
  is_active: boolean
  tags: string[]
}

export interface PreviewItem {
  product_id: string
  name: string
  /** Place in the customer's list (picks and best sellers share one count); null when skipped. */
  position: number | null
  skipped_reason: 'sold_out' | 'duplicate' | 'unavailable' | null
}

export interface RecommendationPreview {
  picks: PreviewItem[]
  best_sellers: (PreviewItem & { units_30d: number })[]
  listed_count: number
  max_items: number
}
