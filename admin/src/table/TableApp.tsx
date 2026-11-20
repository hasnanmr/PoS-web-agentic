// Customer table web page, wireframes Q0–Q5 + Q2a (page 06 · QR Meja Pelanggan; T-135, issue #44).
// A separate public app on route /t/<token>: no sidebar and no sign-in. Endpoints (all under
// /public/t/{token}): GET / (Q1), GET /menu (Q2/Q2a), POST /quote + POST /orders (Q3),
// GET /orders/{id}/qris + POST /orders/{id}/payment-claim | cancel (Q4), GET /orders/{id} (Q5).
// Behaviour notes (canvas):
// - Q1 only for "Web + WhatsApp" with WhatsApp connected; "web" goes straight to Q2; "whatsapp"
//   redirects to the outlet's chat. An unknown or replaced token shows Q0.
// - Web orders are always paid first with the outlet's static QRIS; no screenshot upload: the
//   customer taps "Saya sudah bayar" and staff confirm. Unpaid past the deadline → cancelled.
// - The page shows only orders placed from this phone (kept with their access key); no table bill.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError, createApi, errorMessage, type Api } from '../lib/api'
import { formatRupiah, formatTime } from '../lib/format'
import type { MenuItem, Quote } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { usePolling } from '../lib/usePolling'
import { PRODUCT_NAME } from '../ui/Brand'
import { Photo } from '../ui/Photo'
import { forgetOrder, loadOrders, rememberOrder, type SavedOrder } from './storage'

interface TablePage {
  outlet: { name: string; timezone: string }
  table: { name: string; area: string | null }
  target: 'web_whatsapp' | 'web' | 'whatsapp'
  web_ordering: boolean
  whatsapp_url: string | null
}

interface OrderCreated {
  order_id: string
  access_key: string
  order_no: string
  total: number
  pay_by: string
}

export interface WebOrderStatus {
  id: string
  order_no: string
  created_at: string
  customer_name: string | null
  note: string | null
  status: string
  payment_status: string
  claimed_at: string | null
  pay_by: string
  items: { name: string; quantity: number; addons: string[]; line_total: number }[]
  subtotal: number
  pb1_amount: number
  total: number
  reject_reason: string | null
  cancel_reason: string | null
  events: { status: string; at: string }[]
  timezone: string
}

interface CartLine {
  key: string
  product_id: string
  name: string
  unit_price: number
  addon_option_ids: string[]
  addon_names: string[]
  quantity: number
}

type View =
  | { name: 'loading' }
  | { name: 'invalid' }
  | { name: 'error'; message: string }
  | { name: 'choose' }
  | { name: 'menu' }
  | { name: 'addon'; item: MenuItem }
  | { name: 'cart' }
  | { name: 'order'; saved: SavedOrder }

const POLL_MS = 5000

export function TableApp({ apiBaseUrl, token }: { apiBaseUrl: string; token: string }) {
  const [api] = useState(() => createApi(apiBaseUrl, async () => null))
  return <TableScreens api={api} token={token} redirect={(url) => window.location.replace(url)} />
}

export function TableScreens({ api, token, redirect }: { api: Api; token: string; redirect: (url: string) => void }) {
  const base = `/public/t/${encodeURIComponent(token)}`
  const [page, setPage] = useState<TablePage>()
  const [menu, setMenu] = useState<MenuItem[]>()
  const [view, setView] = useState<View>({ name: 'loading' })
  const [cart, setCart] = useState<CartLine[]>([])
  const [saved, setSaved] = useState<SavedOrder[]>(() => loadOrders(token))

  const loadMenu = useCallback(async () => {
    setMenu(await api.get<MenuItem[]>(`${base}/menu`))
  }, [api, base])

  useEffect(() => {
    let cancelled = false
    api.get<TablePage>(base).then(async (p) => {
      if (cancelled) return
      setPage(p)
      if (p.target === 'whatsapp' && p.whatsapp_url) {
        redirect(p.whatsapp_url)
        return
      }
      await loadMenu()
      if (!cancelled) setView(p.target === 'web_whatsapp' ? { name: 'choose' } : { name: 'menu' })
    }).catch((e: unknown) => {
      if (cancelled) return
      if (e instanceof ApiError && e.code === 'table_qr_invalid') setView({ name: 'invalid' })
      else setView({ name: 'error', message: errorMessage(e) })
    })
    return () => { cancelled = true }
  }, [api, base, loadMenu, redirect])

  function addToCart(item: MenuItem, optionIds: string[], quantity: number) {
    const options = item.addon_groups.flatMap((g) => g.options).filter((o) => optionIds.includes(o.id))
    const key = `${item.product_id}:${[...optionIds].sort().join(',')}`
    setCart((lines) => {
      const found = lines.find((l) => l.key === key)
      if (found) return lines.map((l) => (l.key === key ? { ...l, quantity: l.quantity + quantity } : l))
      return [...lines, {
        key, product_id: item.product_id, name: item.name, quantity,
        unit_price: item.price + options.reduce((sum, o) => sum + o.price, 0),
        addon_option_ids: optionIds, addon_names: options.map((o) => o.name),
      }]
    })
  }

  function setQuantity(key: string, quantity: number) {
    setCart((lines) => (quantity <= 0 ? lines.filter((l) => l.key !== key) : lines.map((l) => (l.key === key ? { ...l, quantity } : l))))
  }

  function openOrder(order: SavedOrder) {
    setView({ name: 'order', saved: order })
  }

  if (view.name === 'loading') return <Shell><p className="p-6 text-center text-[13px] text-text-muted">Memuat…</p></Shell>
  if (view.name === 'invalid') return <InvalidQr />
  if (view.name === 'error') return <Shell><div className="p-6"><Notice tone="danger">{view.message}</Notice></div></Shell>
  if (!page || !menu) return null

  const myOrders = saved.length > 0 && (view.name === 'choose' || view.name === 'menu') && (
    <MyOrders orders={saved} onOpen={openOrder} />
  )

  switch (view.name) {
    case 'choose':
      return <ChooseScreen page={page} myOrders={myOrders} onWeb={() => setView({ name: 'menu' })} />
    case 'menu':
      return (
        <MenuScreen page={page} menu={menu} cart={cart} myOrders={myOrders}
          onAdd={(item) => (item.addon_groups.length ? setView({ name: 'addon', item }) : addToCart(item, [], 1))}
          onQuantity={setQuantity} onCart={() => setView({ name: 'cart' })} />
      )
    case 'addon':
      return (
        <AddonScreen item={view.item} table={page.table.name} onBack={() => setView({ name: 'menu' })}
          onAdd={(ids, qty) => { addToCart(view.item, ids, qty); setView({ name: 'menu' }) }} />
      )
    case 'cart':
      return (
        <CartScreen api={api} base={base} page={page} cart={cart} onQuantity={setQuantity}
          onBack={() => setView({ name: 'menu' })}
          onStale={() => void loadMenu()}
          onPlaced={(created) => {
            const order: SavedOrder = { order_id: created.order_id, access_key: created.access_key,
              order_no: created.order_no, saved_at: new Date().toISOString() }
            setSaved(rememberOrder(token, order))
            setCart([])
            openOrder(order)
          }} />
      )
    case 'order':
      return (
        <OrderScreen api={api} base={base} page={page} saved={view.saved}
          onGone={() => { setSaved(forgetOrder(token, view.saved.order_id)); setView({ name: 'menu' }) }}
          onMore={() => { void loadMenu(); setView({ name: 'menu' }) }} />
      )
  }
}

// Layout ------------------------------------------------------------------------------------------

function Shell({ children }: { children: ReactNode }) {
  return <div className="mx-auto flex min-h-dvh max-w-[480px] flex-col bg-page text-text">{children}</div>
}

function Header({ title, subtitle, onBack, children }: {
  title: string; subtitle?: string; onBack?: () => void; children?: ReactNode
}) {
  return (
    <header className="bg-surface px-4 pb-3 pt-4">
      <div className="flex items-center gap-3">
        {onBack && <button type="button" aria-label="Kembali" className="text-[18px] font-bold" onClick={onBack}>←</button>}
        <h1 className="text-[17px] font-bold">{title}</h1>
      </div>
      {subtitle && <p className="mt-1 text-[11px] text-text-muted">{subtitle}</p>}
      {children}
    </header>
  )
}

function BottomBar({ children, onClick, disabled }: { children: ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled}
      className="sticky bottom-0 mt-auto flex w-full items-center justify-between gap-2 bg-action px-[18px] py-[18px] text-[14px] font-bold text-white disabled:opacity-60">
      {children}
    </button>
  )
}

function Notice({ tone, children }: { tone: 'danger' | 'warning' | 'info' | 'success'; children: ReactNode }) {
  const tones = {
    danger: 'bg-danger-soft text-danger', warning: 'bg-warning-soft text-warning',
    info: 'bg-primary-soft text-primary', success: 'bg-success-soft text-success',
  }
  return <div role={tone === 'danger' ? 'alert' : 'status'} className={`rounded-lg px-3 py-2.5 text-[12px] leading-[18px] ${tones[tone]}`}>{children}</div>
}

function time(iso: string, timeZone: string): string {
  return formatTime(iso, timeZone)
}

function MyOrders({ orders, onOpen }: { orders: SavedOrder[]; onOpen: (o: SavedOrder) => void }) {
  return (
    <div className="mx-3 mt-3 rounded-lg border border-border bg-surface px-3 py-2 text-[12px]">
      <span className="font-semibold">Pesanan dari HP ini: </span>
      {orders.map((o, i) => (
        <span key={o.order_id}>
          {i > 0 && ', '}
          <button type="button" className="font-semibold text-primary hover:underline" onClick={() => onOpen(o)}>{o.order_no} →</button>
        </span>
      ))}
    </div>
  )
}

// Q0 · QR tidak berlaku ----------------------------------------------------------------------------

function InvalidQr() {
  return (
    <Shell>
      <div className="flex flex-1 flex-col items-center px-5 pt-32 text-center">
        <div className="w-full rounded-xl border border-border bg-surface p-5">
          <span className="inline-block rounded-full bg-danger-soft px-2.5 py-0.5 text-[11px] font-semibold text-danger">QR tidak berlaku</span>
          <h1 className="mt-3 text-[18px] font-bold">QR ini sudah tidak berlaku.</h1>
          <p className="mt-1 text-[13px] text-text-muted">Minta QR baru ke staf.</p>
        </div>
        <p className="mt-4 text-[11px] text-text-muted">Tidak ada menu atau tombol pesan di halaman ini.</p>
        <p className="mt-3 text-[11px] text-text-muted">Didukung {PRODUCT_NAME}</p>
      </div>
    </Shell>
  )
}

// Q1 · Pilih cara pesan -----------------------------------------------------------------------------

function ChooseScreen({ page, myOrders, onWeb }: { page: TablePage; myOrders: ReactNode; onWeb: () => void }) {
  return (
    <Shell>
      <div className="flex flex-1 flex-col items-center gap-4 px-5 pt-12">
        <h1 className="text-[20px] font-bold">{page.outlet.name}</h1>
        <span className="rounded-full bg-primary-soft px-3.5 py-1.5 text-[13px] font-semibold text-primary">
          Meja {page.table.name}{page.table.area ? ` · ${page.table.area}` : ''}
        </span>
        <div className="w-full rounded-xl border border-border bg-surface p-4">
          <h2 className="text-[16px] font-semibold">Mau pesan lewat mana?</h2>
          {page.web_ordering ? (
            <button type="button" onClick={onWeb} className="mt-3 w-full rounded-lg bg-action px-3.5 py-3 text-left text-white">
              <span className="block text-[15px] font-bold">Pesan di sini →</span>
              <span className="block text-[12px] opacity-90">Lihat menu & pesan langsung dari HP ini</span>
            </button>
          ) : (
            <button type="button" onClick={onWeb} className="mt-3 w-full rounded-lg border border-border px-3.5 py-3 text-left">
              <span className="block text-[15px] font-bold">Lihat menu →</span>
              <span className="block text-[12px] text-text-muted">Pesan di kasir</span>
            </button>
          )}
          {page.whatsapp_url && (
            <a href={page.whatsapp_url} className="mt-3 block w-full rounded-lg border border-success px-3.5 py-3">
              <span className="block text-[15px] font-bold text-success">✆  Pesan via WhatsApp</span>
              <span className="block text-[12px] text-text-muted">Buka chat {page.outlet.name}, kode meja sudah terisi</span>
            </a>
          )}
        </div>
        {myOrders}
        <p className="max-w-[300px] text-center text-[11px] leading-4 text-text-muted">
          Pesan di sini: bayar dulu dengan QRIS outlet, pesanan diproses setelah staf mengecek pembayaran. Via WhatsApp:
          mengikuti aturan bayar outlet.
        </p>
        <p className="text-[11px] text-text-muted">Didukung {PRODUCT_NAME}</p>
      </div>
    </Shell>
  )
}

// Q2 · Menu -------------------------------------------------------------------------------------------

function MenuScreen({ page, menu, cart, myOrders, onAdd, onQuantity, onCart }: {
  page: TablePage
  menu: MenuItem[]
  cart: CartLine[]
  myOrders: ReactNode
  onAdd: (item: MenuItem) => void
  onQuantity: (key: string, quantity: number) => void
  onCart: () => void
}) {
  const [chip, setChip] = useState<string>('')
  const categories = useMemo(() => [...new Set(menu.map((m) => m.category).filter((c): c is string => !!c))], [menu])
  const hasPicks = menu.some((m) => m.is_owner_pick)
  const shown = menu.filter((m) => (chip === '' ? true : chip === '★' ? m.is_owner_pick : m.category === chip))
  const count = cart.reduce((n, l) => n + l.quantity, 0)
  const subtotal = cart.reduce((n, l) => n + l.unit_price * l.quantity, 0)
  const chips = [{ value: '', label: 'Semua' }, ...categories.map((c) => ({ value: c, label: c })),
    ...(hasPicks ? [{ value: '★', label: 'Rekomendasi ★' }] : [])]
  return (
    <Shell>
      <Header title={`Meja ${page.table.name} · ${page.outlet.name}`}
        subtitle={page.web_ordering ? 'Dine-in · bayar dulu via QRIS' : 'Dine-in · pesan & bayar di kasir'}>
        <div className="mt-2 flex gap-2 overflow-x-auto text-[11px] font-semibold" role="tablist" aria-label="Kategori">
          {chips.map((c) => (
            <button key={c.value} type="button" role="tab" aria-selected={chip === c.value} onClick={() => setChip(c.value)}
              className={`shrink-0 rounded-full px-2.5 py-1 ${chip === c.value ? 'bg-primary-soft text-primary' : 'text-primary'}`}>
              {c.label}
            </button>
          ))}
        </div>
      </Header>
      {myOrders}
      <ul className="flex-1 space-y-2 p-3">
        {!page.web_ordering && (
          <li><Notice tone="warning"><b>Pesan di kasir.</b> Pesan dari HP belum tersedia di outlet ini.</Notice></li>
        )}
        {shown.map((item) => {
          const inCart = cart.filter((l) => l.product_id === item.product_id)
          const qty = inCart.reduce((n, l) => n + l.quantity, 0)
          const simple = item.addon_groups.length === 0 && inCart.length === 1
          return (
            <li key={item.product_id} className={`flex items-center gap-3 rounded-lg border border-border bg-surface p-2.5 ${item.sold_out ? 'opacity-60' : ''}`}>
              <Photo src={item.photo_url} alt={item.name} className="h-14 w-14 shrink-0 rounded-md" />
              <div className="min-w-0 flex-1 text-[13px] leading-5">
                <div className={item.sold_out ? 'text-text-muted' : ''}>{item.name}</div>
                <div className={item.sold_out ? 'text-text-muted' : ''}>
                  {formatRupiah(item.price)}{item.addon_groups.length ? ' · pilih add-on' : ''}
                </div>
              </div>
              {item.sold_out ? (
                <span className="rounded-full bg-danger-soft px-2 py-0.5 text-[11px] font-semibold text-danger">Habis</span>
              ) : !page.web_ordering ? null : simple ? (
                <Stepper label={item.name} value={qty} onChange={(v) => onQuantity(inCart[0].key, v)} />
              ) : (
                <button type="button" aria-label={`Tambah ${item.name}`} onClick={() => onAdd(item)}
                  className="rounded-md border border-primary px-2.5 py-1 text-[14px] font-bold text-primary">
                  {qty > 0 ? `${qty} +` : '+'}
                </button>
              )}
            </li>
          )
        })}
      </ul>
      {count > 0 && (
        <BottomBar onClick={onCart}>
          <span>{count} item · {formatRupiah(subtotal)}</span>
          <span>Lihat pesanan →</span>
        </BottomBar>
      )}
    </Shell>
  )
}

function Stepper({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <span className="flex items-center gap-2 text-[14px] font-bold text-primary">
      <button type="button" aria-label={`Kurangi ${label}`} className="px-1" onClick={() => onChange(value - 1)}>−</button>
      <span aria-label={`Jumlah ${label}`}>{value}</span>
      <button type="button" aria-label={`Tambah ${label}`} className="px-1" disabled={value >= 99} onClick={() => onChange(value + 1)}>+</button>
    </span>
  )
}

// Q2a · Pilih add-on -----------------------------------------------------------------------------------

function AddonScreen({ item, table, onBack, onAdd }: {
  item: MenuItem; table: string; onBack: () => void; onAdd: (optionIds: string[], quantity: number) => void
}) {
  const [picked, setPicked] = useState<Record<string, string[]>>({})
  const [qty, setQty] = useState(1)
  const missing = item.addon_groups.filter((g) => g.is_required && !(picked[g.id]?.length))
  const ids = Object.values(picked).flat()
  const options = item.addon_groups.flatMap((g) => g.options)
  const unit = item.price + options.filter((o) => ids.includes(o.id)).reduce((n, o) => n + o.price, 0)

  function toggle(groupId: string, optionId: string, single: boolean) {
    setPicked((p) => {
      const current = p[groupId] ?? []
      if (single) return { ...p, [groupId]: [optionId] }
      return { ...p, [groupId]: current.includes(optionId) ? current.filter((x) => x !== optionId) : [...current, optionId] }
    })
  }

  return (
    <Shell>
      <Header title={item.name} subtitle={`${formatRupiah(item.price)} · Meja ${table}`} onBack={onBack} />
      <div className="flex-1 space-y-2.5 p-3">
        {item.addon_groups.map((g) => {
          const single = g.selection === 'single'
          return (
            <fieldset key={g.id} className="rounded-lg border border-border bg-surface p-3">
              <legend className="sr-only">{g.name}</legend>
              <div className="mb-2 flex items-center justify-between text-[13px] font-semibold">
                <span>{g.name}{single ? ' · pilih 1' : ''}</span>
                {g.is_required
                  ? <span className={`rounded-full px-2 py-0.5 text-[11px] ${missing.includes(g) ? 'bg-danger-soft text-danger' : 'bg-page text-text-muted'}`}>Wajib</span>
                  : <span className="text-[11px] font-normal text-text-muted">Opsional</span>}
              </div>
              {g.options.map((o) => {
                const checked = picked[g.id]?.includes(o.id) ?? false
                return (
                  <label key={o.id} className={`flex items-center gap-2 py-1 text-[13px] ${!o.available ? 'text-text-muted' : checked ? 'font-semibold text-primary' : ''}`}>
                    <input type={single ? 'radio' : 'checkbox'} name={g.id} checked={checked} disabled={!o.available}
                      onChange={() => toggle(g.id, o.id, single)} />
                    <span className="flex-1">{o.name}{!o.available ? ' (habis)' : ''}</span>
                    <span>+ {formatRupiah(o.price)}</span>
                  </label>
                )
              })}
            </fieldset>
          )
        })}
        <div className="flex items-center justify-between rounded-lg border border-border bg-surface p-3 text-[13px] font-semibold">
          Jumlah
          <Stepper label={item.name} value={qty} onChange={(v) => setQty(Math.max(1, v))} />
        </div>
        {missing.length > 0 && (
          <p className="text-[11px] leading-4 text-text-muted">
            Selama grup “Wajib” belum dipilih, tombol di bawah nonaktif ({missing.map((g) => g.name).join(', ')}: pilih salah satu).
          </p>
        )}
      </div>
      <BottomBar disabled={missing.length > 0} onClick={() => onAdd(ids, qty)}>
        <span className="w-full text-center">Tambah ke pesanan · {formatRupiah(unit * qty)}</span>
      </BottomBar>
    </Shell>
  )
}

// Q3 · Pesanan kamu ------------------------------------------------------------------------------------

function CartScreen({ api, base, page, cart, onQuantity, onBack, onStale, onPlaced }: {
  api: Api
  base: string
  page: TablePage
  cart: CartLine[]
  onQuantity: (key: string, quantity: number) => void
  onBack: () => void
  onStale: () => void
  onPlaced: (created: OrderCreated) => void
}) {
  const [note, setNote] = useState('')
  const [name, setName] = useState('')
  const [quote, setQuote] = useState<Quote>()
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  // One key per cart: a retry after a lost connection returns the same order, not a second one.
  const idempotencyKey = useRef(crypto.randomUUID())
  const items = useMemo(() => cart.map((l) => ({ product_id: l.product_id, quantity: l.quantity, addon_option_ids: l.addon_option_ids })), [cart])

  useEffect(() => {
    idempotencyKey.current = crypto.randomUUID()
    if (items.length === 0) return
    let cancelled = false
    api.post<Quote>(`${base}/quote`, { items }).then((q) => { if (!cancelled) { setQuote(q); setError(undefined) } })
      .catch((e: unknown) => { if (!cancelled) setError(errorMessage(e)) })
    return () => { cancelled = true }
  }, [api, base, items])

  async function submit() {
    if (!quote) return
    setBusy(true)
    setError(undefined)
    try {
      const created = await api.post<OrderCreated>(`${base}/orders`, {
        items, note: note.trim() || null, customer_name: name.trim() || null, expected_total: quote.total,
      }, { 'Idempotency-Key': idempotencyKey.current })
      onPlaced(created)
    } catch (e) {
      if (e instanceof ApiError && (e.code === 'price_changed' || e.code === 'item_sold_out')) onStale()
      if (e instanceof ApiError && e.code === 'price_changed') {
        setQuote(await api.post<Quote>(`${base}/quote`, { items }).catch(() => quote))
      }
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  if (cart.length === 0) {
    return (
      <Shell>
        <Header title="Pesanan kamu" subtitle={`Meja ${page.table.name} · ${page.outlet.name}`} onBack={onBack} />
        <p className="p-6 text-center text-[13px] text-text-muted">Belum ada item. <button type="button" className="text-primary" onClick={onBack}>Lihat menu</button></p>
      </Shell>
    )
  }
  return (
    <Shell>
      <Header title="Pesanan kamu" subtitle={`Meja ${page.table.name} · ${page.outlet.name} · bayar dulu`} onBack={onBack} />
      <div className="flex-1 space-y-2.5 p-3">
        <section className="rounded-lg border border-border bg-surface p-3 text-[13px]">
          <ul className="space-y-2">
            {cart.map((l) => (
              <li key={l.key} className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <div>{l.quantity}× {l.name}</div>
                  {l.addon_names.length > 0 && <div className="pl-4 text-[12px] text-text-muted">+ {l.addon_names.join(', ')}</div>}
                </div>
                <Stepper label={l.name} value={l.quantity} onChange={(v) => onQuantity(l.key, v)} />
                <span className="w-20 text-right">{formatRupiah(l.unit_price * l.quantity)}</span>
              </li>
            ))}
          </ul>
          <button type="button" className="mt-2 font-semibold text-primary" onClick={onBack}>+ Tambah item</button>
        </section>
        <section className="space-y-2 rounded-lg border border-border bg-surface p-3">
          <label className="block text-[13px] font-semibold">Catatan untuk dapur (opsional)
            <input className="mt-1 h-9 w-full rounded-md border border-border px-2.5 text-[12px] font-normal" maxLength={200}
              placeholder="mis. kopi kurang manis" value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <label className="block text-[13px] font-semibold">Nama pemesan (opsional)
            <input className="mt-1 h-9 w-full rounded-md border border-border px-2.5 text-[12px] font-normal" maxLength={40}
              placeholder="mis. Rina — biar pelayan tahu pesanan siapa" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
        </section>
        <dl className="space-y-1 rounded-lg border border-border bg-surface p-3 text-[13px]">
          <div className="flex justify-between"><dt>Subtotal</dt><dd>{quote ? formatRupiah(quote.subtotal) : '…'}</dd></div>
          {quote?.pb1_rate_bps != null && (
            <div className="flex justify-between"><dt>PB1 {(quote.pb1_rate_bps / 100).toLocaleString('id-ID')}%</dt><dd>{formatRupiah(quote.pb1_amount)}</dd></div>
          )}
          <div className="flex justify-between font-semibold"><dt>Total pesanan ini</dt><dd>{quote ? formatRupiah(quote.total) : '…'}</dd></div>
        </dl>
        <Notice tone="info">ⓘ Bayar dulu dengan QRIS outlet. Pesanan masuk dapur setelah staf mengecek pembayaranmu. Isi nama biar staf mudah mencocokkan.</Notice>
        {error && <Notice tone="danger">{error}</Notice>}
      </div>
      <BottomBar disabled={!quote || busy} onClick={() => void submit()}>
        <span className="w-full text-center">{busy ? 'Mengirim…' : `Pesan & bayar · ${quote ? formatRupiah(quote.total) : '…'}`}</span>
      </BottomBar>
    </Shell>
  )
}

// Q4 · Bayar QRIS  /  Q5 · Status pesanan ----------------------------------------------------------------

function OrderScreen({ api, base, page, saved, onGone, onMore }: {
  api: Api; base: string; page: TablePage; saved: SavedOrder; onGone: () => void; onMore: () => void
}) {
  const headers = useMemo(() => ({ 'X-Order-Key': saved.access_key }), [saved.access_key])
  const url = `${base}/orders/${saved.order_id}`
  const loaded = useLoad(() => api.get<WebOrderStatus>(url, headers), url)
  usePolling(loaded, POLL_MS)
  const status = loaded.data
  const gone = loaded.error instanceof ApiError && loaded.error.status === 404
  const error = loaded.error && !gone ? errorMessage(loaded.error) : undefined

  if (gone) {
    return (
      <Shell>
        <div className="space-y-3 p-6 text-center text-[13px]">
          <p>Pesanan {saved.order_no} sudah tidak bisa dibuka dari HP ini.</p>
          <button type="button" className="font-semibold text-primary" onClick={onGone}>Kembali ke menu</button>
        </div>
      </Shell>
    )
  }
  if (!status) {
    return <Shell>{error ? <div className="p-6"><Notice tone="danger">{error}</Notice></div> : <p className="p-6 text-center text-[13px] text-text-muted">Memuat…</p>}</Shell>
  }
  if (status.status === 'pending_payment' && status.payment_status === 'unpaid') {
    return <PayScreen api={api} url={url} headers={headers} page={page} status={status} onChanged={() => loaded.reload()} />
  }
  return <StatusScreen status={status} error={error} onMore={onMore} />
}

function PayScreen({ api, url, headers, page, status, onChanged }: {
  api: Api; url: string; headers: Record<string, string>; page: TablePage; status: WebOrderStatus
  onChanged: () => Promise<void>
}) {
  const [qris, setQris] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const [confirmCancel, setConfirmCancel] = useState(false)

  useEffect(() => {
    let objectUrl: string | undefined
    let cancelled = false
    api.blob(`${url}/qris`, 'image/*', headers).then((blob) => {
      if (cancelled || !(blob instanceof Blob)) return
      objectUrl = URL.createObjectURL(blob)
      setQris(objectUrl)
    }).catch(() => undefined)
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [api, url, headers])

  async function run(path: string) {
    setBusy(true)
    setError(undefined)
    try {
      await api.post<WebOrderStatus>(`${url}/${path}`, {}, headers)
      await onChanged()
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  return (
    <Shell>
      <Header title={`Bayar pesanan ${status.order_no}`}
        subtitle={`Meja ${page.table.name} · ${page.outlet.name}${status.customer_name ? ` · ${status.customer_name}` : ''}`} />
      <div className="flex-1 space-y-2.5 p-3">
        <section className="flex flex-col items-center gap-2.5 rounded-lg border border-border bg-surface p-4">
          <span className="text-[12px] text-text-muted">Total bayar</span>
          <span className="text-[26px] font-bold">{formatRupiah(status.total)}</span>
          {qris
            ? <img src={qris} alt={`QRIS ${page.outlet.name}`} className="h-[200px] w-[200px] rounded object-contain" />
            : <span className="flex h-[200px] w-[200px] items-center justify-center rounded border border-text text-[11px] text-text-muted">Memuat QRIS…</span>}
          {qris && <a href={qris} download={`qris-${status.order_no.replace('#', '')}.png`} className="text-[12px] font-semibold text-primary">⭳ Simpan gambar QRIS</a>}
        </section>
        <ol className="list-inside list-decimal text-[13px] leading-[22px]">
          <li>Scan QRIS dengan e-wallet / m-banking.</li>
          <li>Bayar tepat {formatRupiah(status.total)}.</li>
          <li>Tekan “Saya sudah bayar”.</li>
        </ol>
        <Notice tone="warning">◷ Bayar sebelum {time(status.pay_by, status.timezone)}. Lewat dari itu pesanan batal otomatis.</Notice>
        {error && <Notice tone="danger">{error}</Notice>}
        {confirmCancel ? (
          <div className="flex items-center gap-3 text-[13px]">
            Batalkan pesanan ini?
            <button type="button" className="font-semibold text-danger" disabled={busy} onClick={() => void run('cancel')}>Ya, batalkan</button>
            <button type="button" className="text-text-muted" onClick={() => setConfirmCancel(false)}>Tidak</button>
          </div>
        ) : (
          <button type="button" className="text-[13px] font-semibold text-danger" onClick={() => setConfirmCancel(true)}>Batalkan pesanan</button>
        )}
      </div>
      <BottomBar disabled={busy} onClick={() => void run('payment-claim')}>
        <span className="w-full text-center">Saya sudah bayar</span>
      </BottomBar>
    </Shell>
  )
}

const STEPS: { status: string[]; label: string }[] = [
  { status: ['confirmed'], label: 'Pembayaran dikonfirmasi' },
  { status: ['preparing'], label: 'Disiapkan' },
  { status: ['ready', 'served', 'completed'], label: 'Siap diantar ke meja' },
]

function StatusScreen({ status, error, onMore }: { status: WebOrderStatus; error?: string; onMore: () => void }) {
  const tz = status.timezone
  const at = (s: string[]) => status.events.find((e) => s.includes(e.status))?.at
  const reached = (i: number) => STEPS.slice(i).some((step) => at(step.status))
  const cancelled = status.status === 'cancelled'
  const waiting = status.payment_status === 'proof_submitted'
  const banner = cancelled
    ? <Notice tone="danger"><b>{status.reject_reason ? '✕ Pembayaran ditolak' : '✕ Pesanan dibatalkan'}</b><br />{status.reject_reason ?? status.cancel_reason ?? 'Hubungi staf.'}</Notice>
    : waiting
      ? <Notice tone="warning"><b className="text-[15px]">◷ Menunggu konfirmasi staf</b><br />Kamu bilang sudah bayar {status.claimed_at ? time(status.claimed_at, tz) : ''}. Staf sedang mengecek pembayaran QRIS-mu.</Notice>
      : status.status === 'ready' || status.status === 'completed'
        ? <Notice tone="success"><b className="text-[15px]">✓ Pesanan siap</b><br />Pesananmu diantar ke meja.</Notice>
        : <Notice tone="success"><b className="text-[15px]">✓ Pembayaran diterima</b><br />Pesananmu sedang diproses dapur.</Notice>
  return (
    <Shell>
      <Header title={`Pesanan ${status.order_no}`}
        subtitle={`dipesan ${time(status.created_at, tz)}${status.customer_name ? ` · ${status.customer_name}` : ''}`} />
      <div className="flex-1 space-y-2.5 p-3">
        {banner}
        {!cancelled && (
          <section className="rounded-lg border border-border bg-surface p-3 text-[13px]">
            <h2 className="mb-1 font-semibold">Status</h2>
            <ul className="space-y-1 leading-6">
              <li>✓  Pesanan dibuat <span className="float-right">{time(status.created_at, tz)}</span></li>
              {status.claimed_at && <li>✓  Kamu bilang sudah bayar <span className="float-right">{time(status.claimed_at, tz)}</span></li>}
              {waiting && <li>●  Staf cek pembayaran</li>}
              {STEPS.map((step, i) => {
                const when = at(step.status)
                const current = !waiting && reached(i) && !reached(i + 1)
                return (
                  <li key={step.label} className={reached(i) ? '' : 'text-text-muted'}>
                    {reached(i) ? (current ? '●' : '✓') : '○'}  {step.label}
                    {when && <span className="float-right">{time(when, tz)}</span>}
                  </li>
                )
              })}
            </ul>
          </section>
        )}
        <section className="rounded-lg border border-border bg-surface p-3 text-[13px]">
          <ul className="space-y-1">
            {status.items.map((i, n) => (
              <li key={n} className="flex justify-between gap-2">
                <span>{i.quantity}× {i.name}{i.addons.length ? ` + ${i.addons.join(', ')}` : ''}</span>
                <span>{formatRupiah(i.line_total)}</span>
              </li>
            ))}
            <li className="flex justify-between font-semibold"><span>Total (incl. PB1)</span><span>{formatRupiah(status.total)}</span></li>
          </ul>
        </section>
        {error && <Notice tone="danger">{error}</Notice>}
        <button type="button" onClick={onMore}
          className="w-full rounded-lg border border-primary bg-surface py-2.5 text-[13px] font-semibold text-primary">
          + Pesan lagi
        </button>
        <p className="text-[11px] leading-4 text-text-muted">
          Halaman ini memperbarui status sendiri. Kalau staf menolak (mis. pembayaran tidak ditemukan) atau membatalkan
          pesanan, alasannya tampil di sini. Pesanan dari HP ini tetap bisa dibuka lagi lewat QR meja.
        </p>
      </div>
    </Shell>
  )
}
