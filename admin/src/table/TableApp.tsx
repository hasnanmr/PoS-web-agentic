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
// - "Catatan untuk dapur" is per item (Q2a, or "✎ + Catatan" on each Q3 line), not per order: the
//   same item with a different note is a separate line, and the note follows the item to S2/S3.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError, createApi, errorMessage, type Api } from '../lib/api'
import { formatRupiah, formatTime } from '../lib/format'
import type { MenuItem, Quote } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { usePolling } from '../lib/usePolling'
import { PRODUCT_NAME } from '../ui/Brand'
import { Photo } from '../ui/Photo'
import { forgetOrder, loadOrders, orderFromHash, orderHash, rememberOrder, type SavedOrder } from './storage'

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
  items: { name: string; quantity: number; addons: string[]; note: string | null; line_total: number }[]
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
  note: string
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

export interface HashLocation {
  read: () => string
  write: (hash: string) => void
}

const windowHash: HashLocation = {
  read: () => window.location.hash,
  write: (hash) => window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${hash}`),
}

export function TableApp({ apiBaseUrl, token }: { apiBaseUrl: string; token: string }) {
  const [api] = useState(() => createApi(apiBaseUrl, async () => null))
  return <TableScreens api={api} token={token} redirect={(url) => window.location.replace(url)} />
}

export function TableScreens({ api, token, redirect, location = windowHash }: {
  api: Api; token: string; redirect: (url: string) => void; location?: HashLocation
}) {
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
      if (cancelled) return
      // A refresh on Q4/Q5 comes back to the same order (fragment), not to the menu.
      const fromUrl = orderFromHash(location.read())
      if (fromUrl) {
        const known = loadOrders(token).find((o) => o.order_id === fromUrl.order_id)
        if (!known) setSaved(rememberOrder(token, fromUrl))
        setView({ name: 'order', saved: known ?? fromUrl })
        return
      }
      setView(p.target === 'web_whatsapp' ? { name: 'choose' } : { name: 'menu' })
    }).catch((e: unknown) => {
      if (cancelled) return
      if (e instanceof ApiError && e.code === 'table_qr_invalid') setView({ name: 'invalid' })
      else setView({ name: 'error', message: errorMessage(e) })
    })
    return () => { cancelled = true }
  }, [api, base, loadMenu, redirect, location, token])

  function addToCart(item: MenuItem, optionIds: string[], quantity: number, note = '') {
    const options = item.addon_groups.flatMap((g) => g.options).filter((o) => optionIds.includes(o.id))
    const key = lineKey(item.product_id, optionIds, note)
    setCart((lines) => {
      const found = lines.find((l) => l.key === key)
      if (found) return lines.map((l) => (l.key === key ? { ...l, quantity: l.quantity + quantity } : l))
      return [...lines, {
        key, product_id: item.product_id, name: item.name, quantity,
        unit_price: item.price + options.reduce((sum, o) => sum + o.price, 0),
        addon_option_ids: optionIds, addon_names: options.map((o) => o.name), note: note.trim(),
      }]
    })
  }

  function setNote(key: string, note: string) {
    setCart((lines) => {
      const line = lines.find((l) => l.key === key)
      if (!line) return lines
      const next = { ...line, note: note.trim(), key: lineKey(line.product_id, line.addon_option_ids, note) }
      const same = lines.find((l) => l.key === next.key && l.key !== key)
      if (same) return lines.filter((l) => l.key !== key).map((l) => (l === same ? { ...l, quantity: l.quantity + line.quantity } : l))
      return lines.map((l) => (l.key === key ? next : l))
    })
  }

  function setQuantity(key: string, quantity: number) {
    setCart((lines) => (quantity <= 0 ? lines.filter((l) => l.key !== key) : lines.map((l) => (l.key === key ? { ...l, quantity } : l))))
  }

  function closeOrder() {
    location.write('')
    setView({ name: 'menu' })
  }

  function openOrder(order: SavedOrder) {
    location.write(orderHash(order))
    setView({ name: 'order', saved: order })
  }

  if (view.name === 'loading') return <Shell><p className="p-6 text-center text-[13px] text-text-muted">Memuat…</p></Shell>
  if (view.name === 'invalid') return <InvalidQr />
  if (view.name === 'error') return <Shell><div className="p-6"><Notice tone="danger">{view.message}</Notice></div></Shell>
  if (!page || !menu) return null

  const myOrders = saved.length > 0 && view.name === 'choose' && <MyOrders orders={saved} onOpen={openOrder} />
  // "Menu | Pesanan saya": always reachable once this phone has an order (menu and order screens).
  const tabs = saved.length > 0 && (view.name === 'menu' || view.name === 'order') && (
    <OrderTabs orders={saved} active={view.name === 'order' ? view.saved.order_id : null}
      onMenu={closeOrder} onOrder={openOrder} />
  )

  switch (view.name) {
    case 'choose':
      return <ChooseScreen page={page} myOrders={myOrders} onWeb={() => setView({ name: 'menu' })} />
    case 'menu':
      return (
        <MenuScreen page={page} menu={menu} cart={cart} myOrders={tabs}
          onAdd={(item) => (item.addon_groups.length ? setView({ name: 'addon', item }) : addToCart(item, [], 1))}
          onQuantity={setQuantity} onCart={() => setView({ name: 'cart' })} />
      )
    case 'addon':
      return (
        <AddonScreen item={view.item} table={page.table.name} onBack={() => setView({ name: 'menu' })}
          onAdd={(ids, qty, note) => { addToCart(view.item, ids, qty, note); setView({ name: 'menu' }) }} />
      )
    case 'cart':
      return (
        <CartScreen api={api} base={base} page={page} cart={cart} onQuantity={setQuantity} onNote={setNote}
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
        <OrderScreen key={view.saved.order_id} api={api} base={base} page={page} saved={view.saved} tabs={tabs}
          onGone={() => { setSaved(forgetOrder(token, view.saved.order_id)); closeOrder() }}
          onMore={() => { void loadMenu(); closeOrder() }} />
      )
  }
}

function lineKey(productId: string, optionIds: string[], note: string): string {
  return `${productId}:${[...optionIds].sort().join(',')}:${note.trim().toLowerCase()}`
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

function OrderTabs({ orders, active, onMenu, onOrder }: {
  orders: SavedOrder[]
  active: string | null
  onMenu: () => void
  onOrder: (o: SavedOrder) => void
}) {
  const tab = (selected: boolean) =>
    `flex-1 border-b-2 py-3 text-center text-[13px] font-semibold ${selected ? 'border-primary text-primary' : 'border-transparent text-text-muted'}`
  return (
    <nav aria-label="Navigasi pesanan" className="sticky top-0 z-10 bg-surface shadow-[0_1px_0_var(--color-border)]">
      <div role="tablist" className="flex">
        <button type="button" role="tab" aria-selected={active === null} className={tab(active === null)} onClick={onMenu}>
          Menu
        </button>
        <button type="button" role="tab" aria-selected={active !== null} className={tab(active !== null)}
          onClick={() => onOrder(orders.find((o) => o.order_id === active) ?? orders[0])}>
          Pesanan saya <span className="ml-1 rounded-full bg-primary-soft px-1.5 text-[11px] text-primary">{orders.length}</span>
        </button>
      </div>
      {active !== null && orders.length > 1 && (
        <div className="flex gap-2 overflow-x-auto px-3 pb-2 text-[12px]" aria-label="Pilih pesanan">
          {orders.map((o) => (
            <button key={o.order_id} type="button" aria-pressed={o.order_id === active} onClick={() => onOrder(o)}
              className={`shrink-0 rounded-full border px-2.5 py-1 font-semibold ${o.order_id === active ? 'border-primary bg-primary-soft text-primary' : 'border-border text-text-muted'}`}>
              {o.order_no}
            </button>
          ))}
        </div>
      )}
    </nav>
  )
}

function MyOrders({ orders, onOpen }: { orders: SavedOrder[]; onOpen: (o: SavedOrder) => void }) {
  return (
    <div className="mx-3 mt-3 space-y-2">
      {orders.map((o) => (
        <button key={o.order_id} type="button" onClick={() => onOpen(o)}
          className="flex w-full items-center justify-between rounded-lg border border-primary bg-primary-soft px-3 py-2.5 text-left text-[13px] font-semibold text-primary">
          <span>Lihat status pesanan {o.order_no}</span>
          <span aria-hidden="true">→</span>
        </button>
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
      {myOrders}
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
  item: MenuItem; table: string; onBack: () => void; onAdd: (optionIds: string[], quantity: number, note: string) => void
}) {
  const [picked, setPicked] = useState<Record<string, string[]>>({})
  const [qty, setQty] = useState(1)
  const [note, setNote] = useState('')
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
        <label className="block rounded-lg border border-border bg-surface p-3 text-[13px] font-semibold">
          Catatan untuk dapur (opsional)
          <input className="mt-1 h-9 w-full rounded-md border border-border px-2.5 text-[12px] font-normal" maxLength={200}
            placeholder="mis. kurang manis" value={note} onChange={(e) => setNote(e.target.value)} />
          <span className="mt-1 block text-[11px] font-normal text-text-muted">Untuk item ini saja.</span>
        </label>
        {missing.length > 0 && (
          <p className="text-[11px] leading-4 text-text-muted">
            Selama grup “Wajib” belum dipilih, tombol di bawah nonaktif ({missing.map((g) => g.name).join(', ')}: pilih salah satu).
          </p>
        )}
      </div>
      <BottomBar disabled={missing.length > 0} onClick={() => onAdd(ids, qty, note)}>
        <span className="w-full text-center">Tambah ke pesanan · {formatRupiah(unit * qty)}</span>
      </BottomBar>
    </Shell>
  )
}

// Q3 · Pesanan kamu ------------------------------------------------------------------------------------

function CartScreen({ api, base, page, cart, onQuantity, onNote, onBack, onStale, onPlaced }: {
  api: Api
  base: string
  page: TablePage
  cart: CartLine[]
  onQuantity: (key: string, quantity: number) => void
  onNote: (key: string, note: string) => void
  onBack: () => void
  onStale: () => void
  onPlaced: (created: OrderCreated) => void
}) {
  const [name, setName] = useState('')
  const [editing, setEditing] = useState<{ key: string; text: string }>()
  const [quote, setQuote] = useState<Quote>()
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  // One key per cart: a retry after a lost connection returns the same order, not a second one.
  const idempotencyKey = useRef(crypto.randomUUID())
  const items = useMemo(() => cart.map((l) => ({
    product_id: l.product_id, quantity: l.quantity, addon_option_ids: l.addon_option_ids, note: l.note || null,
  })), [cart])

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
    // A note still being typed counts too: the customer may tap "Pesan & bayar" without "Simpan".
    const draft = editing
    const body = draft
      ? items.map((it, n) => (cart[n]?.key === draft.key ? { ...it, note: draft.text.trim() || null } : it))
      : items
    if (draft) {
      onNote(draft.key, draft.text)
      setEditing(undefined)
    }
    setBusy(true)
    setError(undefined)
    try {
      const created = await api.post<OrderCreated>(`${base}/orders`, {
        items: body, customer_name: name.trim() || null, expected_total: quote.total,
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
                  {editing?.key === l.key ? (
                    <div className="mt-1 flex gap-2 pl-4">
                      <input autoFocus aria-label={`Catatan ${l.name}`} maxLength={200} placeholder="mis. kurang manis"
                        className="h-8 min-w-0 flex-1 rounded-md border border-border px-2 text-[12px]" value={editing.text}
                        onChange={(e) => setEditing({ key: l.key, text: e.target.value })}
                        onBlur={(e) => { onNote(l.key, e.target.value); setEditing(undefined) }} />
                      <button type="button" className="text-[12px] font-semibold text-primary"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => { onNote(l.key, editing.text); setEditing(undefined) }}>Simpan</button>
                    </div>
                  ) : (
                    <button type="button" className="pl-4 text-left text-[12px] text-primary"
                      onClick={() => setEditing({ key: l.key, text: l.note })}>
                      {l.note ? `✎ ${l.note}` : '✎ + Catatan'}
                    </button>
                  )}
                </div>
                <Stepper label={l.name} value={l.quantity} onChange={(v) => onQuantity(l.key, v)} />
                <span className="w-20 text-right">{formatRupiah(l.unit_price * l.quantity)}</span>
              </li>
            ))}
          </ul>
          <button type="button" className="mt-2 font-semibold text-primary" onClick={onBack}>+ Tambah item</button>
        </section>
        <section className="space-y-2 rounded-lg border border-border bg-surface p-3">
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

function OrderScreen({ api, base, page, saved, tabs, onGone, onMore }: {
  api: Api; base: string; page: TablePage; saved: SavedOrder; tabs: ReactNode; onGone: () => void; onMore: () => void
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
    return <PayScreen api={api} url={url} headers={headers} page={page} status={status} tabs={tabs} onChanged={() => loaded.reload()} />
  }
  return <StatusScreen status={status} error={error} tabs={tabs} onMore={onMore} />
}

function PayScreen({ api, url, headers, page, status, tabs, onChanged }: {
  api: Api; url: string; headers: Record<string, string>; page: TablePage; status: WebOrderStatus; tabs: ReactNode
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
      {tabs}
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

type StepState = 'done' | 'current' | 'todo'

/** Q5 progress: one step per stage, each done / current / to do, with the time when known. */
function progress(status: WebOrderStatus): { label: string; state: StepState; at?: string }[] {
  const at = (names: string[]) => status.events.find((e) => names.includes(e.status))?.at
  const paidAt = at(['confirmed'])
  const preparingAt = at(['preparing'])
  const readyAt = at(['ready', 'served', 'completed'])
  const stages = [
    { label: 'Pesanan dibuat', at: status.created_at, done: true },
    { label: 'Pembayaran dikirim', at: status.claimed_at ?? undefined, done: !!status.claimed_at || !!paidAt },
    { label: 'Dikonfirmasi staf', at: paidAt, done: !!paidAt },
    { label: 'Disiapkan', at: preparingAt, done: !!preparingAt || !!readyAt },
    { label: 'Siap diantar ke meja', at: readyAt, done: !!readyAt },
  ]
  const firstTodo = stages.findIndex((st) => !st.done)
  return stages.map((st, n) => ({
    label: st.label,
    at: st.at,
    // The last finished stage is "current" until the next one starts; the final stage is done.
    state: st.done ? (n === firstTodo - 1 && firstTodo !== -1 ? 'current' : 'done') : 'todo',
  }))
}

function StepIcon({ state }: { state: StepState }) {
  if (state === 'todo') return <span className="block h-4 w-4 rounded-full border-2 border-border bg-surface" aria-hidden="true" />
  if (state === 'current') {
    return (
      <span className="flex h-4 w-4 items-center justify-center rounded-full border-2 border-primary bg-surface" aria-hidden="true">
        <span className="h-1.5 w-1.5 rounded-full bg-primary" />
      </span>
    )
  }
  return (
    <span className="flex h-4 w-4 items-center justify-center rounded-full bg-success text-[10px] font-bold leading-none text-white" aria-hidden="true">✓</span>
  )
}

function Progress({ status }: { status: WebOrderStatus }) {
  const steps = progress(status)
  const label = { done: 'selesai', current: 'sedang berjalan', todo: 'belum' }
  return (
    <ol className="mt-1">
      {steps.map((st, n) => (
        <li key={st.label} className="flex gap-3" aria-label={`${st.label}: ${label[st.state]}`}>
          <div className="flex flex-col items-center">
            <span className="pt-1"><StepIcon state={st.state} /></span>
            {n < steps.length - 1 && (
              <span className={`w-0.5 flex-1 ${st.state === 'todo' || steps[n + 1].state === 'todo' ? 'bg-border' : 'bg-success'}`} aria-hidden="true" />
            )}
          </div>
          <div className={`flex flex-1 justify-between pb-3 text-[13px] leading-6 ${st.state === 'todo' ? 'text-text-muted' : ''} ${st.state === 'current' ? 'font-semibold' : ''}`}>
            <span>{st.label}</span>
            {st.at && st.state !== 'todo' && <span className="font-normal text-text-muted">{time(st.at, status.timezone)}</span>}
          </div>
        </li>
      ))}
    </ol>
  )
}

function StatusScreen({ status, error, tabs, onMore }: {
  status: WebOrderStatus; error?: string; tabs: ReactNode; onMore: () => void
}) {
  const tz = status.timezone
  const cancelled = status.status === 'cancelled'
  const waiting = status.payment_status === 'proof_submitted'
  const banner = cancelled
    ? <Notice tone="danger"><b>{status.reject_reason ? '✕ Pembayaran ditolak' : '✕ Pesanan dibatalkan'}</b><br />{status.reject_reason ?? status.cancel_reason ?? 'Hubungi staf.'}</Notice>
    : waiting
      ? <Notice tone="warning"><b className="text-[15px]">◷ Menunggu konfirmasi staf</b><br />Terima kasih atas pembayarannya. Staf akan konfirmasi ke kamu setelah ini.</Notice>
      : status.status === 'ready' || status.status === 'completed'
        ? <Notice tone="success"><b className="text-[15px]">✓ Pesanan siap</b><br />Pesananmu diantar ke meja.</Notice>
        : <Notice tone="success"><b className="text-[15px]">✓ Pembayaran diterima</b><br />Pesananmu sedang diproses dapur.</Notice>
  return (
    <Shell>
      {tabs}
      <Header title={`Pesanan ${status.order_no}`}
        subtitle={`dipesan ${time(status.created_at, tz)}${status.customer_name ? ` · ${status.customer_name}` : ''}`} />
      <div className="flex-1 space-y-2.5 p-3">
        {banner}
        {!cancelled && (
          <section className="rounded-lg border border-border bg-surface p-3 text-[13px]">
            <h2 className="mb-1 font-semibold">Status</h2>
            <Progress status={status} />
          </section>
        )}
        <section className="rounded-lg border border-border bg-surface p-3 text-[13px]">
          <ul className="space-y-1">
            {status.items.map((i, n) => (
              <li key={n} className="flex justify-between gap-2">
                <span>
                  {i.quantity}× {i.name}{i.addons.length ? ` + ${i.addons.join(', ')}` : ''}
                  {i.note && <span className="block text-[12px] text-text-muted">✎ {i.note}</span>}
                </span>
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
