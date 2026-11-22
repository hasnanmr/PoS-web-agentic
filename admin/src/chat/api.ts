// Endpoints of the customer web chat (screen-endpoint map → C1–C15). Every call carries
// `X-Chat-Session`; creating calls carry an `Idempotency-Key` and the access key the page made
// itself (`X-Order-Key` / `X-Booking-Key`): the server stores only its hash.
import type { Api } from '../lib/api'
import type {
  Availability, Booking, BookingCreated, CartLine, ChatMenuItem, ChatPage, ChatQuote, ChatSession, OrderCreated,
  OrderOverview, OrderStatus, RecommendationCard, Scope,
} from './types'

interface RawPage {
  outlet: ChatPage['outlet']
  table?: { name: string; area: string | null }
  reservations_enabled?: boolean
  web_ordering: boolean
  delivery_fee?: number
  agent_enabled: boolean
  privacy_notice: ChatPage['privacy_notice']
}

export interface OrderBody {
  items: CartLine[]
  note?: string | null
  expected_total?: number
  privacy_notice_version: string
  fulfillment?: 'pickup' | 'delivery' | 'dine_in' | 'takeaway'
  customer?: { name: string; phone: string; address?: string | null }
  customer_name?: string
}

export interface CreateKeys {
  idempotencyKey: string
  accessKey: string
}

export function scopeKey(scope: Scope): string {
  return scope.kind === 'o' ? `o:${scope.slug}` : `t:${scope.token}`
}

export function chatApi(api: Api, scope: Scope, session: string) {
  const base = scope.kind === 'o' ? `/public/o/${encodeURIComponent(scope.slug)}` : `/public/t/${encodeURIComponent(scope.token)}`
  const h = { 'X-Chat-Session': session }
  const orderKey = (key: string) => ({ ...h, 'X-Order-Key': key })
  const bookingKey = (key: string) => ({ ...h, 'X-Booking-Key': key })

  return {
    base,
    session,
    async page(): Promise<ChatPage> {
      const raw = await api.get<RawPage>(base, h)
      return {
        outlet: raw.outlet,
        table: raw.table ?? null,
        reservations_enabled: scope.kind === 'o' && Boolean(raw.reservations_enabled),
        web_ordering: raw.web_ordering,
        delivery_fee: raw.delivery_fee ?? 0,
        agent_enabled: raw.agent_enabled,
        privacy_notice: raw.privacy_notice,
      }
    },
    menu: () => api.get<ChatMenuItem[]>(`${base}/menu`, h),
    recommendations: () => api.get<RecommendationCard[]>(`${base}/recommendations`, h),
    getSession: () => api.get<ChatSession>(`${base}/chat-session`, h),
    putSession: (body: { step: string; cart: { lines: CartLine[] }; fulfillment: 'pickup' | 'delivery' | null }) =>
      api.put<ChatSession>(`${base}/chat-session`, body, h),
    quote: (items: CartLine[], fulfillment: 'pickup' | 'delivery' | null) =>
      api.post<ChatQuote>(`${base}/quote`, scope.kind === 'o' ? { items, fulfillment } : { items }, h),
    placeOrder: (body: OrderBody, keys: CreateKeys) =>
      api.post<OrderCreated>(`${base}/orders`, body, { ...orderKey(keys.accessKey), 'Idempotency-Key': keys.idempotencyKey }),
    order: (id: string, key: string) => api.get<OrderStatus>(`${base}/orders/${id}`, orderKey(key)),
    qris: (id: string, key: string) => api.blob(`${base}/orders/${id}/qris`, 'image/*', orderKey(key)),
    claim: (id: string, key: string) =>
      api.post<OrderStatus>(`${base}/orders/${id}/payment-claim`, {}, orderKey(key)),
    cancelOrder: (id: string, key: string) => api.post<OrderStatus>(`${base}/orders/${id}/cancel`, {}, orderKey(key)),
    ordersStatus: (orders: { order_id: string; key: string }[]) =>
      api.post<OrderOverview[]>(`${base}/orders/status`, { orders }, h),

    // C10–C12: outlet link only.
    availability: (partySize: number, date: string) =>
      api.get<Availability>(`${base}/availability?party_size=${partySize}&date=${date}`, h),
    book: (body: {
      party_size: number; start_at: string; customer: { name: string; phone: string }; privacy_notice_version: string
    }, keys: CreateKeys, source: 'buttons' | 'agent' = 'buttons') =>
      api.post<BookingCreated>(`${base}/reservations`, { ...body, source },
        { ...bookingKey(keys.accessKey), 'Idempotency-Key': keys.idempotencyKey }),
    booking: (id: string, key: string) => api.get<Booking>(`${base}/reservations/${id}`, bookingKey(key)),
    bookingsStatus: (reservations: { id: string; key: string }[]) =>
      api.post<Booking[]>(`${base}/reservations/status`, { reservations }, h),
    lookup: (bookingCode: string, phone: string) =>
      api.post<{ reservation_id: string; access_key: string }>(`${base}/reservations/lookup`,
        { booking_code: bookingCode, phone }, h),
    cancelBooking: (id: string, key: string, idempotencyKey: string) =>
      api.post<Booking>(`${base}/reservations/${id}/cancel`, {}, { ...bookingKey(key), 'Idempotency-Key': idempotencyKey }),
    reschedule: (id: string, key: string, startAt: string, idempotencyKey: string) =>
      api.post<Booking>(`${base}/reservations/${id}/reschedule`, { start_at: startAt },
        { ...bookingKey(key), 'Idempotency-Key': idempotencyKey }),
    calendarUrl: (apiRoot: string, id: string, key: string) =>
      `${apiRoot.replace(/\/+$/, '')}/api/v1${base}/reservations/${id}/calendar.ics?key=${encodeURIComponent(key)}`,
  }
}

export type ChatApi = ReturnType<typeof chatApi>
