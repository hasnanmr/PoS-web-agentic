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
