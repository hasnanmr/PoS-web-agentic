// Orders placed from this phone on the table page (FR2.15): kept per table token with their
// access key, so the customer can reopen them from the QR. The server stops answering an hour
// after an order is completed or cancelled; such entries are dropped when they 404.
export interface SavedOrder {
  order_id: string
  access_key: string
  order_no: string
  saved_at: string
}

const KEY = 'thinker.table-orders.v1'
const MAX_PER_TABLE = 5
const MAX_AGE_MS = 24 * 60 * 60 * 1000

type Store = Record<string, SavedOrder[]>

function read(): Store {
  try {
    const raw = localStorage.getItem(KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : {}
    return parsed && typeof parsed === 'object' ? (parsed as Store) : {}
  } catch {
    return {}
  }
}

function write(store: Store): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(store))
  } catch {
    // private mode / storage blocked: the order still works in this tab
  }
}

export function loadOrders(token: string, now = Date.now()): SavedOrder[] {
  return (read()[token] ?? []).filter((o) => now - new Date(o.saved_at).getTime() < MAX_AGE_MS)
}

export function rememberOrder(token: string, order: SavedOrder): SavedOrder[] {
  const store = read()
  const orders = [order, ...(store[token] ?? []).filter((o) => o.order_id !== order.order_id)].slice(0, MAX_PER_TABLE)
  write({ ...store, [token]: orders })
  return orders
}

export function forgetOrder(token: string, orderId: string): SavedOrder[] {
  const store = read()
  const orders = (store[token] ?? []).filter((o) => o.order_id !== orderId)
  write({ ...store, [token]: orders })
  return orders
}

// The open order is also kept in the URL fragment (#order=…&key=…&no=…), so a refresh shows its
// status again even when the browser keeps no site data (private mode, in-app browsers). The
// fragment never reaches the server.
export function orderFromHash(hash: string): SavedOrder | null {
  const params = new URLSearchParams(hash.replace(/^#/, ''))
  const orderId = params.get('order')
  const key = params.get('key')
  if (!orderId || !key) return null
  return { order_id: orderId, access_key: key, order_no: params.get('no') ?? '', saved_at: new Date().toISOString() }
}

export function orderHash(order: SavedOrder): string {
  return `#${new URLSearchParams({ order: order.order_id, key: order.access_key, no: order.order_no }).toString()}`
}
