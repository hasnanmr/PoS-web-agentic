// What the web chat keeps on this phone only (FR2.15, FR6.2, FR9.5, FR12.3):
// - the chat session id (the server keeps step + cart under it);
// - the orders and bookings placed from this phone, with their access keys (the server stores
//   only hashes, so a key lost here can't be recovered; the saveable link carries it too);
// - optionally the customer's own name, phone, and address ("Ingat data di HP ini");
// - the chat transcript of the current session, so a refresh shows the same bubbles; it is
//   dropped after 2 hours with no activity, like the cart (FR6.2).
// Nothing here is sent anywhere except the matching API calls.

export interface SavedOrder {
  order_id: string
  access_key: string
  order_no: string
  saved_at: string
}

export interface SavedBooking {
  reservation_id: string
  access_key: string
  booking_code: string
  saved_at: string
}

export interface SavedDetails {
  name: string
  phone: string
  address: string
}

const SESSIONS = 'thinker.chat.sessions.v1'
const ORDERS = 'thinker.chat.orders.v1'
const BOOKINGS = 'thinker.chat.bookings.v1'
const DETAILS = 'thinker.chat.details.v1'
const MAX_ORDERS = 10
const MAX_BOOKINGS = 10
const ORDER_MAX_AGE_MS = 2 * 24 * 60 * 60 * 1000

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function write(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // private mode / storage blocked: the chat still works in this tab
  }
}

/** A random URL-safe secret (256 bits): chat session ids, access keys, idempotency keys. */
export function randomKey(): string {
  const bytes = new Uint8Array(32)
  crypto.getRandomValues(bytes)
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

export function sessionId(scopeKey: string): string {
  const all = read<Record<string, string>>(SESSIONS, {})
  if (!all[scopeKey]) {
    all[scopeKey] = randomKey()
    write(SESSIONS, all)
  }
  return all[scopeKey]
}

export function loadOrders(scopeKey: string, now = Date.now()): SavedOrder[] {
  return (read<Record<string, SavedOrder[]>>(ORDERS, {})[scopeKey] ?? [])
    .filter((o) => now - new Date(o.saved_at).getTime() < ORDER_MAX_AGE_MS)
}

export function rememberOrder(scopeKey: string, order: SavedOrder): SavedOrder[] {
  const all = read<Record<string, SavedOrder[]>>(ORDERS, {})
  const list = [order, ...(all[scopeKey] ?? []).filter((o) => o.order_id !== order.order_id)].slice(0, MAX_ORDERS)
  write(ORDERS, { ...all, [scopeKey]: list })
  return list
}

export function forgetOrder(scopeKey: string, orderId: string): SavedOrder[] {
  const all = read<Record<string, SavedOrder[]>>(ORDERS, {})
  const list = (all[scopeKey] ?? []).filter((o) => o.order_id !== orderId)
  write(ORDERS, { ...all, [scopeKey]: list })
  return list
}

export function loadBookings(slug: string): SavedBooking[] {
  return read<Record<string, SavedBooking[]>>(BOOKINGS, {})[slug] ?? []
}

export function rememberBooking(slug: string, booking: SavedBooking): SavedBooking[] {
  const all = read<Record<string, SavedBooking[]>>(BOOKINGS, {})
  const list = [booking, ...(all[slug] ?? []).filter((b) => b.reservation_id !== booking.reservation_id)]
    .slice(0, MAX_BOOKINGS)
  write(BOOKINGS, { ...all, [slug]: list })
  return list
}

// Chat transcript ------------------------------------------------------------------------------
// Kept on this phone only (never on the server), per scope and chat session. Generic over the
// message type so storage does not depend on the chat components.

const TRANSCRIPT = 'thinker.chat.transcript.v1'
export const TRANSCRIPT_IDLE_MS = 2 * 60 * 60 * 1000

interface SavedTranscript<T> {
  session: string
  saved_at: string
  messages: T[]
}

/** All saved transcripts with the ones idle for 2 hours or more removed from the phone (every
 * scope, not only the one being opened, so an outlet or table never visited again is cleaned too). */
function liveTranscripts<T>(now: number): Record<string, SavedTranscript<T>> {
  const all = read<Record<string, SavedTranscript<T>>>(TRANSCRIPT, {})
  const live = Object.fromEntries(Object.entries(all).filter(([, t]) =>
    t && Array.isArray(t.messages) && now - new Date(t.saved_at).getTime() < TRANSCRIPT_IDLE_MS))
  if (Object.keys(live).length !== Object.keys(all).length) {
    if (Object.keys(live).length === 0) {
      try { localStorage.removeItem(TRANSCRIPT) } catch { /* ignore */ }
    } else write(TRANSCRIPT, live)
  }
  return live
}

export function loadTranscript<T>(scopeKey: string, session: string, now = Date.now()): T[] {
  const saved = liveTranscripts<T>(now)[scopeKey]
  return saved && saved.session === session ? saved.messages : []
}

export function saveTranscript<T>(scopeKey: string, session: string, messages: T[], now = Date.now()): void {
  const all = liveTranscripts<T>(now)
  write(TRANSCRIPT, { ...all, [scopeKey]: { session, saved_at: new Date(now).toISOString(), messages } })
}

export function clearTranscript(scopeKey: string): void {
  const all = read<Record<string, unknown>>(TRANSCRIPT, {})
  if (!(scopeKey in all)) return
  delete all[scopeKey]
  write(TRANSCRIPT, all)
}

export function loadDetails(): SavedDetails | null {
  return read<SavedDetails | null>(DETAILS, null)
}

export function saveDetails(details: SavedDetails): void {
  write(DETAILS, details)
}

export function clearDetails(): void {
  try {
    localStorage.removeItem(DETAILS)
  } catch {
    // ignore
  }
}

// The open order or booking is also kept in the URL fragment (#order=…&key=… or
// #booking=…&key=…): a refresh comes back to it, and the "Simpan link" copy carries it. The
// fragment never reaches the server.
export type Fragment =
  | { kind: 'order'; order: SavedOrder }
  | { kind: 'booking'; booking: SavedBooking }

export function readFragment(hash: string): Fragment | null {
  const p = new URLSearchParams(hash.replace(/^#/, ''))
  const key = p.get('key')
  if (!key) return null
  const now = new Date().toISOString()
  const order = p.get('order')
  if (order) return { kind: 'order', order: { order_id: order, access_key: key, order_no: p.get('no') ?? '', saved_at: now } }
  const booking = p.get('booking')
  if (booking) {
    return { kind: 'booking', booking: { reservation_id: booking, access_key: key, booking_code: p.get('code') ?? '', saved_at: now } }
  }
  return null
}

export function orderFragment(o: SavedOrder): string {
  return `#${new URLSearchParams({ order: o.order_id, key: o.access_key, no: o.order_no }).toString()}`
}

export function bookingFragment(b: SavedBooking): string {
  return `#${new URLSearchParams({ booking: b.reservation_id, key: b.access_key, code: b.booking_code }).toString()}`
}
