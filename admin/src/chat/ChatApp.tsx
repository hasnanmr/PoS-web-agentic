// Customer web chat — page 07 · Web Chat Pelanggan, screens C1–C15 (T-145; the agent parts of
// C9/C14/C15 are T-115, T-087, T-088: AgentReply.tsx, agent.ts). One public app on two routes, no
// sign-in: the outlet link /o/<slug> (C1: Pesan, Rekomendasi, Reservasi, Reservasi Saya) and
// the table QR /t/<token> (C8: Pesan, Rekomendasi). Endpoints: screen-endpoint map → C1–C15.
// Behaviour notes (canvas):
// - Every step works with buttons; the text box takes "menu", the kitchen note, and free text
//   for the agent (when the outlet has it: `agent_enabled`). The agent only reads; it never
//   creates a cart, order, or booking — the customer's tap does, through the same endpoints. "☰ Menu utama" / "menu" returns to the main menu without creating anything;
//   the cart stays.
// - The server keeps the step and cart for this phone's chat session; a cart idle for 2 hours
//   comes back empty (C13 card 4). Name, phone, and address stay on the phone only.
// - Web chat orders are always paid first (C6); "Saya sudah bayar" stops the auto-cancel. The
//   status refreshes by itself every 5 s (≤ 10 s); nothing is sent outside the chat.
// - Create calls carry an Idempotency-Key and an access key made here; a retry after a lost
//   connection reuses both, so a double tap or retry never creates a second order or booking.
// - Customer-facing errors are everyday Bahasa, never codes, paths, or tokens (copy.ts).
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { ApiError, createApi, type Api } from '../lib/api'
import { formatRupiah } from '../lib/format'
import { Photo } from '../ui/Photo'
import { sendToAgent, type AgentBookingDraft, type AgentContext, type AgentOrderDraft } from './agent'
import { AgentReply, type AgentTurn } from './AgentReply'
import { chatApi, scopeKey, type ChatApi, type OrderBody } from './api'
import { BookedCard, BookingFlow, MyBookings, type BookingPreset, type Person } from './Booking'
import { friendly, isRetryable } from './copy'
import { cartTotal, describeLine, lineUnitPrice } from './cart'
import {
  AddonPicker, CartCard, DetailsForm, FulfillmentChoice, MenuCards, NotePrompt, SummaryCard, type Details,
} from './OrderSteps'
import { MyOrders, PayCard, StatusCard } from './PayStatus'
import { isActive, useObjectUrl } from './status'
import {
  bookingFragment, clearDetails, forgetOrder, loadBookings, loadDetails, loadOrders, orderFragment, randomKey,
  readFragment, rememberBooking, rememberOrder, saveDetails, sessionId, type SavedBooking, type SavedOrder,
} from './storage'
import type {
  Booking, CartLine, ChatMenuItem, ChatPage, ChatQuote, OrderOverview, OrderStatus, RecommendationCard, Scope,
} from './types'
import { Action, ActionBar, Bubble, BottomBar, ChatHeader, Choice, Mine, TextLink } from './ui'

type Step =
  | { name: 'main' }
  | { name: 'menu' }
  | { name: 'addons'; item: ChatMenuItem }
  | { name: 'note'; item: ChatMenuItem; optionIds: string[] }
  | { name: 'cart' }
  | { name: 'details' }
  | { name: 'summary' }
  | { name: 'order'; saved: SavedOrder }
  | { name: 'myOrders' }
  | { name: 'recs' }
  | { name: 'book'; preset?: BookingPreset }
  | { name: 'reschedule'; booking: Booking; key: string }
  | { name: 'booked'; booking: Booking; saved: SavedBooking }
  | { name: 'myBookings' }

type Msg =
  | { id: number; kind: 'me' | 'ok' | 'info' | 'warn' | 'expired'; text: string }
  | { id: number; kind: 'ai'; turn: AgentTurn }

export interface HashLocation {
  read: () => string
  write: (hash: string) => void
  href: (hash: string) => string
}

const windowHash: HashLocation = {
  read: () => window.location.hash,
  write: (hash) => window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${hash}`),
  href: (hash) => `${window.location.origin}${window.location.pathname}${hash}`,
}

const POLL_MS = 5000
const RESUME_STEPS = new Set(['menu', 'addons', 'note', 'cart', 'details', 'summary'])

const SHORT_STATUS: Record<string, string> = {
  pending_payment: 'menunggu bayar', confirmed: 'dikonfirmasi', preparing: 'disiapkan', ready: 'siap',
  out_for_delivery: 'diantar', served: 'diantar',
}

export function ChatApp({ apiBaseUrl, scope }: { apiBaseUrl: string; scope: Scope }) {
  const [api] = useState(() => createApi(apiBaseUrl, async () => null))
  return <ChatScreens api={api} apiBaseUrl={apiBaseUrl} scope={scope} />
}

export function ChatScreens({ api, apiBaseUrl, scope, location = windowHash }: {
  api: Api; apiBaseUrl: string; scope: Scope; location?: HashLocation
}) {
  const key = scopeKey(scope)
  const chat = useMemo(() => chatApi(api, scope, sessionId(key)), [api, scope, key])
  const [page, setPage] = useState<ChatPage>()
  const [menu, setMenu] = useState<ChatMenuItem[]>([])
  const [load, setLoad] = useState<'loading' | 'ready' | 'invalid' | 'error'>('loading')
  const [step, setStep] = useState<Step>({ name: 'main' })
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [cart, setCart] = useState<CartLine[]>([])
  const [fulfillment, setFulfillment] = useState<'pickup' | 'delivery' | null>(null)
  const saved = loadDetails()
  const [details, setDetails] = useState<Details>({ name: saved?.name ?? '', phone: saved?.phone ?? '', address: saved?.address ?? '' })
  const [prefilled, setPrefilled] = useState(Boolean(saved))
  const [remember, setRemember] = useState(Boolean(saved))
  const [orders, setOrders] = useState<SavedOrder[]>(() => loadOrders(key))
  const [overview, setOverview] = useState<OrderOverview[]>([])
  const nextId = useRef(1)
  // The action bar of the current step renders here (between the chat and the bottom bar).
  const [footerSlot, setFooterSlot] = useState<HTMLDivElement | null>(null)
  const restored = useRef(false)

  const byId = useMemo(() => new Map(menu.map((m) => [m.product_id, m])), [menu])
  const say = useCallback((kind: Exclude<Msg['kind'], 'ai'>, text: string) => {
    setMsgs((m) => [...m.slice(-20), { id: nextId.current++, kind, text }])
  }, [])

  // Load: page (C1/C8), menu, chat session; then a link fragment or the saved step.
  const start = useCallback(async () => {
    try {
      const p = await chat.page()
      setPage(p)
      const [m, session] = await Promise.all([chat.menu(), chat.getSession()])
      setMenu(m)
      setCart(session.cart.lines)
      setFulfillment(session.fulfillment)
      const fragment = readFragment(location.read())
      if (fragment?.kind === 'order') {
        setOrders(rememberOrder(key, fragment.order))
        setStep({ name: 'order', saved: fragment.order })
      } else if (fragment?.kind === 'booking' && scope.kind === 'o') {
        try {
          const b = await chat.booking(fragment.booking.reservation_id, fragment.booking.access_key)
          const sb = { ...fragment.booking, booking_code: b.booking_code }
          rememberBooking(scope.slug, sb)
          setStep({ name: 'booked', booking: b, saved: sb })
        } catch {
          location.write('')
          setStep({ name: 'main' })
        }
      } else if (session.cart_expired) {
        setMsgs([{ id: nextId.current++, kind: 'expired', text: '' }])
        setStep({ name: 'main' })
      } else if (session.cart.lines.length > 0 && RESUME_STEPS.has(session.step)) {
        setStep(session.step === 'menu' || session.step.startsWith('addons') || session.step === 'note' ? { name: 'menu' } : { name: 'cart' })
      }
      restored.current = true
      setLoad('ready')
    } catch (e) {
      if (e instanceof ApiError && (e.code === 'outlet_link_invalid' || e.code === 'table_qr_invalid')) setLoad('invalid')
      else setLoad('error')
    }
  }, [chat, key, location, scope])

  useEffect(() => {
    const timer = window.setTimeout(() => void start(), 0)
    return () => window.clearTimeout(timer)
  }, [start])

  // Keep the server's chat session (step + cart, no personal data) in step with the screen.
  const stepName = step.name === 'addons' ? `addons:${step.item.product_id}` : step.name.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`)
  useEffect(() => {
    if (!restored.current) return
    const timer = window.setTimeout(() => {
      chat.putSession({ step: stepName.slice(0, 60), cart: { lines: cart }, fulfillment: scope.kind === 'o' ? fulfillment : null })
        .catch(() => undefined)
    }, 400)
    return () => window.clearTimeout(timer)
  }, [chat, cart, fulfillment, stepName, scope.kind])

  // Pesanan Saya (C1 button, C7 list): the orders this phone kept keys for.
  const refreshOverview = useCallback(async () => {
    if (orders.length === 0) return
    try {
      setOverview(await chat.ordersStatus(orders.map((o) => ({ order_id: o.order_id, key: o.access_key }))))
    } catch {
      // keep the last list
    }
  }, [chat, orders])
  useEffect(() => {
    if (load !== 'ready') return
    const timer = window.setTimeout(() => void refreshOverview(), 0)
    return () => window.clearTimeout(timer)
  }, [load, refreshOverview, step.name])
  const myOrders = orders.length > 0 ? overview : []

  function mainMenu() {
    setMsgs([])
    location.write('')
    setStep({ name: 'main' })
  }

  function go(label: string, next: Step) {
    say('me', label)
    setStep(next)
  }

  // C2 → C3 → note → cart ----------------------------------------------------------------------------
  function startAdd(item: ChatMenuItem) {
    if (item.sold_out) return
    if (item.addon_groups.length > 0) go(`+ Tambah · ${item.name}`, { name: 'addons', item })
    else go(`+ Tambah · ${item.name}`, { name: 'note', item, optionIds: [] })
  }

  function addLine(item: ChatMenuItem, optionIds: string[], note: string | null) {
    const sorted = [...optionIds].sort()
    setCart((c) => {
      const same = c.findIndex((l) => l.product_id === item.product_id && l.note === note
        && [...l.addon_option_ids].sort().join() === sorted.join())
      if (same >= 0) return c.map((l, i) => (i === same ? { ...l, quantity: l.quantity + 1 } : l))
      return [...c, { product_id: item.product_id, quantity: 1, addon_option_ids: sorted, note }]
    })
    const line = { product_id: item.product_id, quantity: 1, addon_option_ids: sorted, note }
    say('ok', `✓ Masuk keranjang: ${describeLine(item, line)} — ${formatRupiah(lineUnitPrice(item, sorted))}`)
    setStep({ name: 'menu' })
  }

  function setQuantity(index: number, quantity: number) {
    setCart((c) => (quantity <= 0 ? c.filter((_, i) => i !== index) : c.map((l, i) => (i === index ? { ...l, quantity: Math.min(99, quantity) } : l))))
  }

  // Text box ---------------------------------------------------------------------------------------------
  function onText(text: string) {
    if (text.trim().toLowerCase() === 'menu') { mainMenu(); return }
    if (step.name === 'note') {
      say('me', text)
      addLine(step.item, step.optionIds, text.slice(0, 200))
      return
    }
    if (page?.agent_enabled) { void askAgent(text.trim().slice(0, 500)); return }
    say('me', text)
    say('info', 'Untuk sekarang pakai tombol di atas ya. Ketik "menu" kapan saja untuk kembali ke menu utama.')
  }

  // C9 AI / C14 / C15: one message to the agent, the reply streamed into its bubble.
  const agentBusy = useRef(false)
  function updateTurn(id: number, change: (t: AgentTurn) => AgentTurn) {
    setMsgs((all) => all.map((m) => (m.id === id && m.kind === 'ai' ? { ...m, turn: change(m.turn) } : m)))
  }
  async function askAgent(text: string) {
    if (!text) return
    if (agentBusy.current) {
      say('me', text)
      say('info', 'Tunggu sebentar ya, asistennya masih menjawab pesan sebelumnya.')
      return
    }
    agentBusy.current = true
    const context: AgentContext = step.name === 'recs' ? 'recommend' : step.name === 'book' ? 'book'
      : ['menu', 'addons', 'cart', 'details', 'summary'].includes(step.name) ? 'order' : 'auto'
    say('me', text)
    const id = nextId.current++
    setMsgs((m) => [...m.slice(-20), { id, kind: 'ai', turn: { context, text: '', result: null } }])
    try {
      const result = await sendToAgent({
        apiBaseUrl, base: chat.base, session: chat.session, text, context,
        onDelta: (d) => updateTurn(id, (t) => ({ ...t, text: t.text + d })),
      })
      updateTurn(id, (t) => ({ ...t, result }))
    } finally {
      agentBusy.current = false
    }
  }

  function applyOrderDraft(draft: AgentOrderDraft, edit: boolean) {
    setCart(draft.lines.map((l) => ({
      product_id: l.product_id, quantity: l.quantity, addon_option_ids: [...l.addon_option_ids].sort(), note: l.note,
    })))
    const chosen = scope.kind === 'o' ? draft.fulfillment ?? fulfillment : null
    if (scope.kind === 'o' && draft.fulfillment) setFulfillment(draft.fulfillment)
    if (edit || (scope.kind === 'o' && !chosen)) { go(edit ? 'Ubah' : 'Pesan & bayar', { name: 'cart' }); return }
    const missing = !details.name.trim() || (scope.kind === 'o' && (!details.phone.trim() || (chosen === 'delivery' && !details.address.trim())))
    go('Pesan & bayar', { name: missing ? 'details' : 'summary' })
  }

  function applyBookingDraft(draft: AgentBookingDraft) {
    go('Lanjut isi nama & no HP', { name: 'book', preset: { party_size: draft.party_size, start_at: draft.start_at, label: draft.label } })
  }

  if (load === 'loading') {
    return <Shell header={<ChatHeader initials="…" title="Memuat…" subtitle="" />}><Bubble>Sebentar ya…</Bubble></Shell>
  }
  if (load === 'invalid' || load === 'error' || !page) {
    return (
      <Shell header={<ChatHeader initials="T" title="Thinker" subtitle="Pemesanan lewat chat" />}>
        {load === 'invalid' && scope.kind === 'o' && (
          <Bubble>
            <p className="font-semibold">Waduh, halamannya tidak ketemu 🙏</p>
            <p className="mt-1">Sepertinya link-nya sudah diganti oleh outlet. Coba cek link terbaru di Instagram atau Google Maps mereka ya.</p>
          </Bubble>
        )}
        {load === 'invalid' && scope.kind === 't' && (
          <Bubble>
            <p className="font-semibold">QR ini sudah tidak bisa dipakai</p>
            <p className="mt-1">Minta QR yang baru ke kakak staf ya, nanti langsung bisa pesan lagi.</p>
          </Bubble>
        )}
        {load === 'error' && (
          <Bubble>
            <p>Sinyalnya lagi putus-putus. Coba lagi sebentar ya.</p>
            <TextLink className="mt-1" onClick={() => { setLoad('loading'); void start() }}>Coba lagi</TextLink>
          </Bubble>
        )}
      </Shell>
    )
  }

  const outletName = page.outlet.name
  const mode: 'pickup' | 'delivery' | 'table' = scope.kind === 't' ? 'table' : fulfillment ?? 'pickup'
  const totals = cartTotal(cart, byId)
  const active = myOrders.filter(isActive)
  const header = (
    <ChatHeader initials={page.outlet.short_name} title={outletName}
      subtitle={page.table ? `${tableLabel(page.table.name)} · ${page.table.area ? `${page.table.area} · ` : ''}dine-in` : outletSubtitle(page)} />
  )
  const placeholder = step.name === 'note' ? 'Tulis catatan…'
    : page.agent_enabled && step.name === 'recs' ? 'Ceritakan seleramu…'
      : page.agent_enabled && step.name === 'menu' ? 'Tulis pesananmu…'
        : step.name === 'main' || step.name === 'menu' ? 'Ketik pesanan atau "menu"…' : 'Ketik "menu"…'

  let footer: ReactNode = null
  if (step.name === 'menu' && cart.length > 0) {
    footer = (
      <ActionBar onClick={() => go('Lihat keranjang', { name: 'cart' })}>
        <span>🛒 {totals.count} item · {formatRupiah(totals.amount)}</span><span>Lihat keranjang →</span>
      </ActionBar>
    )
  }

  return (
    <Shell header={header} footer={<>{footer}<div ref={setFooterSlot} /></>}
      bottom={<BottomBar placeholder={placeholder} onMainMenu={mainMenu} onSend={onText} />}>
      {msgs.map((m) => (
        m.kind === 'ai' ? (
          <AgentReply key={m.id} turn={m.turn} byId={byId} webOrdering={page.web_ordering}
            canBook={scope.kind === 'o' && page.reservations_enabled}
            onAdd={startAdd} onQuick={(q) => void askAgent(q)} onOrder={applyOrderDraft} onBook={applyBookingDraft}
            onPick={(target) => go(target === 'menu' ? 'Pesan' : target === 'recs' ? 'Rekomendasi' : 'Reservasi meja', { name: target })} />
        )
          : m.kind === 'me' ? <Mine key={m.id}>{m.text}</Mine>
          : m.kind === 'expired' ? (
            <Bubble key={m.id}>
              <p className="font-semibold">Keranjangmu sudah kosong lagi</p>
              <p className="mt-1">Karena 2 jam tidak ada aktivitas, keranjangnya kami kosongkan. Tenang, belum ada yang dipesan kok.</p>
              <TextLink className="mt-1" onClick={() => go('Mulai pesan lagi', { name: 'menu' })}>Mulai pesan lagi</TextLink>
            </Bubble>
          )
            : <Bubble key={m.id} tone={m.kind === 'ok' ? 'success' : m.kind === 'warn' ? 'warning' : 'plain'}>{m.text}</Bubble>
      ))}

      {step.name === 'main' && (
        <MainMenu page={page} scope={scope} active={active[0] ?? null}
          onPick={(label, next) => go(label, next)} />
      )}
      {step.name === 'menu' && (
        <MenuCards outletName={outletName} menu={menu} cart={cart} webOrdering={page.web_ordering} onAdd={startAdd} />
      )}
      {step.name === 'addons' && (
        <AddonPicker item={step.item} onDone={(ids) => setStep({ name: 'note', item: step.item, optionIds: ids })} />
      )}
      {step.name === 'note' && (
        <NotePrompt onSkip={() => { say('me', 'Tanpa catatan'); addLine(step.item, step.optionIds, null) }} />
      )}
      {step.name === 'recs' && (
        <Recommendations chat={chat} byId={byId} webOrdering={page.web_ordering} agent={page.agent_enabled} onAdd={startAdd} />
      )}
      {(step.name === 'cart' || step.name === 'details' || step.name === 'summary') && (
        <Checkout footerSlot={footerSlot} chat={chat} page={page} scope={scope} step={step.name} mode={mode} cart={cart} byId={byId}
          fulfillment={fulfillment} details={details} prefilled={prefilled} remember={remember}
          onQuantity={setQuantity} onAddMore={() => go('+ Tambah menu', { name: 'menu' })}
          onEmpty={() => { setCart([]); say('info', 'Keranjang sudah dikosongkan.') }}
          onFulfillment={(f) => {
            setFulfillment(f)
            go(f === 'delivery' ? '🛵 Diantar' : '🛍 Ambil di outlet', { name: 'details' })
          }}
          onTableNext={() => setStep({ name: 'details' })}
          onRemember={(on) => { setRemember(on); if (!on) { clearDetails(); setPrefilled(false) } }}
          onClearSaved={() => { clearDetails(); setPrefilled(false); setRemember(false); setDetails({ name: '', phone: '', address: '' }) }}
          onDetails={(d) => {
            setDetails(d)
            if (remember) saveDetails({ ...loadDetails(), ...d, address: d.address || loadDetails()?.address || '' })
            setStep({ name: 'summary' })
          }}
          onEditDetails={() => setStep({ name: 'details' })}
          onCart={(lines) => setCart(lines)}
          onMenu={() => setStep({ name: 'menu' })}
          onPlaced={(o) => {
            const s: SavedOrder = { order_id: o.order_id, access_key: o.access_key, order_no: o.order_no, saved_at: new Date().toISOString() }
            setOrders(rememberOrder(key, s))
            setCart([])
            setMsgs([])
            location.write(orderFragment(s))
            setStep({ name: 'order', saved: s })
          }} />
      )}
      {step.name === 'order' && (
        <OrderView chat={chat} saved={step.saved} link={location.href(orderFragment(step.saved))}
          others={myOrders.filter((o) => o.order_id !== step.saved.order_id)} timezone={page.outlet.timezone}
          onGone={() => {
            setOrders(forgetOrder(key, step.saved.order_id))
            mainMenu()
            say('info', 'Pesanan itu sudah tidak bisa dibuka lagi dari sini.')
          }}
          onOpen={(id) => {
            const s = orders.find((o) => o.order_id === id)
            if (s) { location.write(orderFragment(s)); setStep({ name: 'order', saved: s }) }
          }} />
      )}
      {step.name === 'myOrders' && (
        <MyOrders orders={myOrders} timezone={page.outlet.timezone} onOpen={(id) => {
          const s = orders.find((o) => o.order_id === id)
          if (s) { location.write(orderFragment(s)); setStep({ name: 'order', saved: s }) }
        }} />
      )}
      {scope.kind === 'o' && (step.name === 'book' || step.name === 'reschedule') && (
        <BookingFlow key={step.name === 'book' && step.preset ? step.preset.start_at : step.name} api={chat} outletName={outletName} timezone={page.outlet.timezone} privacyUrl={page.privacy_notice.url}
          privacyVersion={page.privacy_notice.version}
          reschedule={step.name === 'reschedule' ? { booking: step.booking, key: step.key } : null}
          preset={step.name === 'book' ? step.preset ?? null : null}
          person={{ name: details.name, phone: details.phone }} prefilled={prefilled} remember={remember}
          onRemember={(on) => { setRemember(on); if (!on) { clearDetails(); setPrefilled(false) } }}
          onBooked={(created, person: Person) => {
            if (remember) saveDetails({ name: person.name, phone: person.phone, address: details.address })
            const sb: SavedBooking = { reservation_id: created.reservation_id, access_key: created.access_key,
              booking_code: created.booking_code, saved_at: new Date().toISOString() }
            rememberBooking(scope.slug, sb)
            location.write(bookingFragment(sb))
            setMsgs([])
            setStep({ name: 'booked', booking: created, saved: sb })
          }}
          onRescheduled={(b) => {
            if (step.name !== 'reschedule') return
            const sb: SavedBooking = { reservation_id: b.reservation_id, access_key: step.key, booking_code: b.booking_code,
              saved_at: new Date().toISOString() }
            location.write(bookingFragment(sb))
            setMsgs([])
            setStep({ name: 'booked', booking: b, saved: sb })
          }} />
      )}
      {scope.kind === 'o' && step.name === 'booked' && (
        <BookedCard booking={step.booking}
          calendarUrl={chat.calendarUrl(apiBaseUrl, step.saved.reservation_id, step.saved.access_key)}
          link={location.href(bookingFragment(step.saved))}
          onMyBookings={() => go('Reservasi Saya', { name: 'myBookings' })}
          onMenu={() => go('Lihat menu', { name: 'menu' })} />
      )}
      {scope.kind === 'o' && step.name === 'myBookings' && (
        <BookingsView chat={chat} slug={scope.slug} apiBaseUrl={apiBaseUrl}
          onReschedule={(b, k) => go('↻ Jadwal ulang', { name: 'reschedule', booking: b, key: k })} />
      )}
    </Shell>
  )
}

// Shell ----------------------------------------------------------------------------------------------

function Shell({ header, children, footer, bottom }: { header: ReactNode; children: ReactNode; footer?: ReactNode; bottom?: ReactNode }) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { end.current?.scrollIntoView?.({ block: 'end' }) })
  return (
    // Full-height column: the conversation scrolls inside, the action bar and the bottom bar
    // stay on screen (C2 "Lihat keranjang", C4 "Pesan & bayar", "☰ Menu utama").
    <div className="mx-auto flex h-dvh max-w-[480px] flex-col bg-page font-sans text-text">
      {header}
      <main className="min-h-0 flex-1 space-y-2 overflow-y-auto overflow-x-hidden px-3 py-3">
        {children}
        <div ref={end} />
      </main>
      <div className="shrink-0">
        {footer}
        {bottom}
      </div>
    </div>
  )
}

function tableLabel(name: string): string {
  return /^\d+$/.test(name) || /^M\d+$/i.test(name) ? `Meja ${name.replace(/^M/i, '')}` : name
}

const ISO_WEEKDAY: Record<string, number> = { Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 7 }

/** C1 header: "Buka · 08.00–22.00 · biasanya balas instan" (today's hours in the outlet zone). */
function outletSubtitle(page: ChatPage, now: Date = new Date()): string {
  const name = new Intl.DateTimeFormat('en-US', { weekday: 'short', timeZone: page.outlet.timezone }).format(now)
  const weekday = ISO_WEEKDAY[name] ?? 0
  const today = page.outlet.opening_hours.find((h) => h.weekday === weekday)
  const hours = today ? `${today.opens_at.replace(':', '.')}–${today.closes_at.replace(':', '.')}` : null
  const state = page.outlet.is_open_now === null ? null : page.outlet.is_open_now ? 'Buka' : 'Tutup'
  return [state, hours, 'biasanya balas instan'].filter(Boolean).join(' · ')
}

// C1 / C8 ---------------------------------------------------------------------------------------------

function MainMenu({ page, scope, active, onPick }: {
  page: ChatPage; scope: Scope; active: OrderOverview | null; onPick: (label: string, next: Step) => void
}) {
  return (
    <div className="max-w-[92%] space-y-2">
      <Bubble>
        {page.table ? (
          <p>Halo! 👋 Kamu di {tableLabel(page.table.name)} {page.outlet.name}. Pesan dari sini, bayar dulu via QRIS, pesanan diantar ke meja.</p>
        ) : (
          <p>Halo! 👋 Selamat datang di {page.outlet.name}. Mau ngapain hari ini?</p>
        )}
      </Bubble>
      <Choice onClick={() => onPick('Pesan', { name: 'menu' })}>🛒  Pesan</Choice>
      <Choice onClick={() => onPick('Rekomendasi', { name: 'recs' })}>⭐  Rekomendasi</Choice>
      {scope.kind === 'o' && page.reservations_enabled && (
        <>
          <Choice onClick={() => onPick('Reservasi meja', { name: 'book' })}>📅  Reservasi meja</Choice>
          <Choice onClick={() => onPick('Reservasi Saya', { name: 'myBookings' })}>🗂  Reservasi Saya</Choice>
        </>
      )}
      {active && (
        <button type="button" onClick={() => onPick('Pesanan Saya', { name: 'myOrders' })}
          className="w-full rounded-lg bg-primary-soft px-3 py-2.5 text-left text-[13px] font-semibold text-primary">
          🧾  Pesanan Saya · {active.order_no}{' '}
          {active.status === 'pending_payment' && active.payment_status === 'proof_submitted' ? 'dicek staf' : SHORT_STATUS[active.status] ?? ''}
        </button>
      )}
    </div>
  )
}

// C9 (cards; the AI answers render in AgentReply) ---------------------------------------------------------

function Recommendations({ chat, byId, webOrdering, agent, onAdd }: {
  chat: ChatApi; byId: Map<string, ChatMenuItem>; webOrdering: boolean; agent: boolean; onAdd: (item: ChatMenuItem) => void
}) {
  const [cards, setCards] = useState<RecommendationCard[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    chat.recommendations().then((c) => { if (!cancelled) setCards(c) }).catch((e: unknown) => { if (!cancelled) setError(friendly(e)) })
    return () => { cancelled = true }
  }, [chat])
  return (
    <div className="space-y-2">
      <Bubble>
        <p>Pilihan owner &amp; terlaris di outlet ini{agent ? ' — atau ceritakan seleramu di kotak teks ↓' : '.'}</p>
      </Bubble>
      {error && <Bubble tone="danger">{error}</Bubble>}
      {cards && cards.length === 0 && <Bubble>Belum ada rekomendasi di outlet ini. Coba lihat menunya ya.</Bubble>}
      {cards && cards.length > 0 && (
        <ul className="flex gap-2 overflow-x-auto pb-1" aria-label="Rekomendasi">
          {cards.map((c) => {
            const item = byId.get(c.product_id)
            return (
              <li key={c.product_id} className="w-36 shrink-0 rounded-xl border border-border bg-surface p-2 text-[12px]">
                {c.photo_url
                  ? <Photo src={c.photo_url} className="mb-1 h-20 w-full rounded-lg" />
                  : <span aria-hidden="true" className="mb-1 flex h-20 w-full items-center justify-center rounded-lg bg-page text-[20px]">☕</span>}
                <p className="text-[11px] text-text-muted">{c.badge === 'owner_pick' ? '★ Pilihan owner' : '🔥 Terlaris'}</p>
                <p className="font-semibold">{c.name}</p>
                <p>{formatRupiah(c.price)}</p>
                {webOrdering && item && !item.sold_out && (
                  <TextLink onClick={() => onAdd(item)} aria-label={`Tambah ${c.name}`}>+ Tambah</TextLink>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

// C4 / C5 / C8 → Pesan & bayar ---------------------------------------------------------------------------

function Checkout(props: {
  footerSlot: HTMLDivElement | null
  chat: ChatApi; page: ChatPage; scope: Scope; step: 'cart' | 'details' | 'summary'; mode: 'pickup' | 'delivery' | 'table'
  cart: CartLine[]; byId: Map<string, ChatMenuItem>; fulfillment: 'pickup' | 'delivery' | null; details: Details
  prefilled: boolean; remember: boolean
  onQuantity: (i: number, q: number) => void; onAddMore: () => void; onEmpty: () => void
  onFulfillment: (f: 'pickup' | 'delivery') => void; onTableNext: () => void
  onRemember: (on: boolean) => void; onClearSaved: () => void; onDetails: (d: Details) => void; onEditDetails: () => void
  onCart: (lines: CartLine[]) => void; onMenu: () => void
  onPlaced: (o: { order_id: string; access_key: string; order_no: string }) => void
}) {
  const { chat, page, step, mode, cart, byId, details } = props
  const [quoted, setQuoted] = useState<{ key: string; quote: ChatQuote } | null>(null)
  const [error, setError] = useState<{ text: string; retry: boolean } | null>(null)
  const [soldOut, setSoldOut] = useState<{ productId: string | null; name: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const pending = useRef<{ body: string; idempotencyKey: string; accessKey: string } | null>(null)
  const fulfillmentForQuote = mode === 'table' ? null : mode
  const quoteKey = JSON.stringify([cart, fulfillmentForQuote])
  const quote = quoted && quoted.key === quoteKey ? quoted.quote : null

  useEffect(() => {
    if (step !== 'summary' || cart.length === 0) return
    let cancelled = false
    chat.quote(cart, fulfillmentForQuote).then((q) => { if (!cancelled) setQuoted({ key: quoteKey, quote: q }) })
      .catch((e: unknown) => { if (!cancelled) setError({ text: friendly(e), retry: false }) })
    return () => { cancelled = true }
  }, [chat, cart, fulfillmentForQuote, step, quoteKey])

  async function place() {
    if (!quote) return
    const body: OrderBody = mode === 'table'
      ? { items: cart, customer_name: details.name.trim(), privacy_notice_version: page.privacy_notice.version, expected_total: quote.total }
      : {
        items: cart, fulfillment: mode, privacy_notice_version: page.privacy_notice.version, expected_total: quote.total,
        customer: { name: details.name.trim(), phone: details.phone.trim(), ...(mode === 'delivery' ? { address: details.address.trim() } : {}) },
      }
    const text = JSON.stringify(body)
    // The same request after a lost connection keeps its keys, so it can't create a second order.
    if (pending.current?.body !== text) pending.current = { body: text, idempotencyKey: randomKey(), accessKey: randomKey() }
    setBusy(true)
    setError(null)
    setSoldOut(null)
    try {
      const created = await chat.placeOrder(body, pending.current)
      pending.current = null
      props.onPlaced(created)
    } catch (e) {
      if (e instanceof ApiError && e.code === 'item_sold_out') {
        const name = typeof e.details.name === 'string' ? e.details.name : 'Salah satu menu'
        setSoldOut({ productId: typeof e.details.product_id === 'string' ? e.details.product_id : null, name })
      } else if (e instanceof ApiError && e.code === 'price_changed') {
        setError({ text: friendly(e), retry: false })
        chat.quote(cart, fulfillmentForQuote).then((q) => setQuoted({ key: quoteKey, quote: q })).catch(() => undefined)
      } else {
        setError({ text: friendly(e), retry: isRetryable(e) })
      }
    } finally {
      setBusy(false)
    }
  }

  function dropSoldOut(thenMenu: boolean) {
    if (!soldOut) return
    const name = soldOut.name
    const left = cart.filter((l) => (soldOut.productId ? l.product_id !== soldOut.productId : byId.get(l.product_id)?.name !== name))
    setSoldOut(null)
    props.onCart(left)
    if (thenMenu || left.length === 0) props.onMenu()
  }

  const items = cart.map((l) => describeLine(byId.get(l.product_id), l))
  return (
    <div className="space-y-2">
      {step === 'cart' && (
        <>
          <CartCard cart={cart} byId={byId} onQuantity={props.onQuantity} onAddMore={props.onAddMore} onEmpty={props.onEmpty} />
          {cart.length > 0 && (mode === 'table' ? (
            <div className="max-w-[92%]"><Action onClick={props.onTableNext}>Lanjut</Action></div>
          ) : (
            <FulfillmentChoice value={props.fulfillment} deliveryFee={page.delivery_fee} onPick={props.onFulfillment} />
          ))}
        </>
      )}
      {step === 'details' && (
        <DetailsForm mode={mode} initial={details} prefilled={props.prefilled} remember={props.remember}
          privacyUrl={page.privacy_notice.url} error={null} onRemember={props.onRemember}
          onClearSaved={props.onClearSaved} onSubmit={props.onDetails} />
      )}
      {step === 'summary' && cart.length > 0 && (
        <>
          <SummaryCard quote={quote} mode={mode} details={details} tableName={page.table ? tableLabel(page.table.name) : null}
            items={items} onEdit={props.onEditDetails} />
          {soldOut && (
            <Bubble tone="danger">
              <p>
                Yah, {soldOut.name} baru saja habis 😔 Pesananmu belum dibuat, jadi tenang saja. Mau dihapus dari keranjang atau
                ganti menu lain?
              </p>
              <p className="mt-1">
                <TextLink onClick={() => dropSoldOut(false)}>Hapus item &amp; lanjut</TextLink>
                <span className="text-text-muted">  ·  </span>
                <TextLink onClick={() => dropSoldOut(true)}>Pilih pengganti</TextLink>
              </p>
            </Bubble>
          )}
          {error && (
            <Bubble tone="danger">
              <p>{error.text}</p>
              {error.retry && <TextLink className="mt-1" disabled={busy} onClick={() => void place()}>Coba lagi</TextLink>}
            </Bubble>
          )}
          {props.footerSlot && createPortal(
            <ActionBar onClick={() => void place()} disabled={busy || !quote || !page.web_ordering}>
              <span className="w-full text-center">{busy ? 'Mengirim…' : `Pesan & bayar · ${quote ? formatRupiah(quote.total) : '…'}`}</span>
            </ActionBar>,
            props.footerSlot,
          )}
        </>
      )}
      {step === 'summary' && cart.length === 0 && <Bubble>Keranjangmu masih kosong. Pilih menu dulu ya.</Bubble>}
    </div>
  )
}

// C6 / C7 -------------------------------------------------------------------------------------------------

function OrderView({ chat, saved, link, others, timezone, onGone, onOpen }: {
  chat: ChatApi; saved: SavedOrder; link: string; others: OrderOverview[]; timezone: string
  onGone: () => void; onOpen: (id: string) => void
}) {
  const [order, setOrder] = useState<OrderStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [claimed, setClaimed] = useState(false)
  const loading = useRef(false)

  const refresh = useCallback(async () => {
    if (loading.current) return
    loading.current = true
    try {
      setOrder(await chat.order(saved.order_id, saved.access_key))
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) onGone()
    } finally {
      loading.current = false
    }
  }, [chat, saved, onGone])

  useEffect(() => {
    const first = window.setTimeout(() => void refresh(), 0)
    const timer = window.setInterval(() => void refresh(), POLL_MS)
    return () => { window.clearTimeout(first); window.clearInterval(timer) }
  }, [refresh])

  const payable = order?.status === 'pending_payment' && order.payment_status === 'unpaid'
  const loadQris = useMemo(() => (payable ? () => chat.qris(saved.order_id, saved.access_key) : null), [payable, chat, saved])
  const qrisUrl = useObjectUrl(loadQris)

  async function act(kind: 'claim' | 'cancel') {
    setBusy(true)
    setError(null)
    try {
      setOrder(kind === 'claim' ? await chat.claim(saved.order_id, saved.access_key) : await chat.cancelOrder(saved.order_id, saved.access_key))
      if (kind === 'claim') setClaimed(true)
    } catch (e) {
      setError(friendly(e))
      void refresh()
    } finally {
      setBusy(false)
    }
  }

  if (!order) return <Bubble>Sebentar ya, cek pesananmu…</Bubble>
  return (
    <div className="space-y-2">
      {payable ? (
        <PayCard order={order} qrisUrl={qrisUrl} busy={busy} error={error} onClaim={() => void act('claim')} onCancel={() => void act('cancel')} />
      ) : (
        <>
          {(claimed || order.claimed_at) && <Mine>Saya sudah bayar</Mine>}
          <div className="max-w-[92%] space-y-2">
            <StatusCard order={order} link={link} />
            {error && <Bubble tone="danger">{error}</Bubble>}
            {others.length > 0 && <MyOrders orders={others} timezone={timezone} onOpen={onOpen} />}
          </div>
        </>
      )}
    </div>
  )
}

// C12 -----------------------------------------------------------------------------------------------------

function BookingsView({ chat, slug, apiBaseUrl, onReschedule }: {
  chat: ChatApi; slug: string; apiBaseUrl: string; onReschedule: (b: Booking, key: string) => void
}) {
  const [list, setList] = useState<Booking[] | null>(() => (loadBookings(slug).length ? null : []))
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const keyOf = (id: string) => loadBookings(slug).find((b) => b.reservation_id === id)?.access_key ?? ''

  const reload = useCallback(async () => {
    const saved = loadBookings(slug)
    if (saved.length === 0) return
    try {
      setList(await chat.bookingsStatus(saved.map((b) => ({ id: b.reservation_id, key: b.access_key }))))
    } catch (e) {
      setError(friendly(e))
      setList([])
    }
  }, [chat, slug])
  useEffect(() => {
    const timer = window.setTimeout(() => void reload(), 0)
    return () => window.clearTimeout(timer)
  }, [reload])

  async function cancel(b: Booking) {
    if (!b.can_change) {
      setError('Reservasi ini sudah terlalu dekat dengan waktunya, jadi tidak bisa diubah lewat chat. Hubungi outlet ya.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await chat.cancelBooking(b.reservation_id, keyOf(b.reservation_id), randomKey())
      await reload()
    } catch (e) {
      setError(friendly(e))
    } finally {
      setBusy(false)
    }
  }

  async function lookup(code: string, phone: string) {
    setBusy(true)
    setError(null)
    try {
      const found = await chat.lookup(code, phone)
      rememberBooking(slug, { reservation_id: found.reservation_id, access_key: found.access_key, booking_code: code,
        saved_at: new Date().toISOString() })
      await reload()
    } catch (e) {
      setError(e instanceof ApiError && e.code === 'too_many_requests' ? 'Coba lagi beberapa menit lagi ya.' : friendly(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <MyBookings bookings={list} busy={busy} error={error}
      calendarUrl={(b) => chat.calendarUrl(apiBaseUrl, b.reservation_id, keyOf(b.reservation_id))}
      onReschedule={(b) => {
        if (!b.can_change) {
          setError('Reservasi ini sudah terlalu dekat dengan waktunya, jadi tidak bisa diubah lewat chat. Hubungi outlet ya.')
          return
        }
        onReschedule(b, keyOf(b.reservation_id))
      }}
      onCancel={(b) => void cancel(b)} onLookup={(c, p) => void lookup(c, p)} />
  )
}

