// Wireframe O2b — Dashboard drawer detail Revenue / Order (drill-down from O2).
// Opened by the Revenue tile, the Order tile, a bar of "Order per jam", or a row of "Item
// terlaris". Endpoint: GET /owner/dashboard/orders (docs/architecture/screen-endpoint-map.md → O2b).
// Canvas notes: the tiles carry the header outlet, period, and hours; a bar sends `hour` with
// hours=all and an item sends `product_id` with its card's own period (both cards ignore the hours
// filter). The summary box equals the number that was clicked (paid orders, by the outlet-local
// time the order was created; revenue = subtotal excl. PB1 and delivery fee). The chips Semua /
// Cash / QRIS, "Semua kanal ▾", and "Cari no. order…" filter only the list. "Per outlet" only for
// Semua outlet with more than one outlet. Newest first, 30 per page, "Muat lagi". A row opens S3
// inside this drawer with "← Kembali". ✕, Esc, or a click on the dark area closes it.
import { useCallback, useEffect, useRef, useState } from 'react'
import { useSession } from '../../app/session'
import { errorMessage } from '../../lib/api'
import { formatNumber, formatRupiah, formatTime, todayIn, ZONE_LABEL } from '../../lib/format'
import type { DashboardOrderRow, DashboardOrders, DrillPeriod, HoursFilter } from '../../lib/types'
import { useKept, useLoad } from '../../lib/useLoad'
import { Alert, Button, Loading, Select, TextInput } from '../../ui/kit'
import { TYPE_LABEL } from '../orders/labels'
import { OrderDetailPanel } from '../orders/OrderDrawer'
import { datesText, periodDates, periodTitle, type DayRange } from './period'

export type DrillKind = 'revenue' | 'orders' | 'hour' | 'item'

export interface Drill {
  kind: DrillKind
  outletId: string
  period: DrillPeriod
  range?: DayRange
  hours: HoursFilter
  hour?: number
  item?: { product_id: string; name: string }
  /** The Revenue tile's comparison line ("▲ 8% vs kemarin"), shown again in the summary box. */
  change?: string
}

const PAGE_SIZE = 30
/** Matches --animate-drawer-out in index.css. */
const CLOSE_MS = 160
const HOURS_LABEL: Record<HoursFilter, string> = { all: 'Semua jam', busy: 'Jam ramai', quiet: 'Jam sepi' }
const CHANNELS: { key: DashboardOrderRow['channel']; label: string }[] = [
  { key: 'web_online', label: 'Web chat (link outlet)' },
  { key: 'web_table', label: 'Web meja (QR)' },
  { key: 'counter', label: 'Counter' },
  { key: 'whatsapp_online', label: 'WhatsApp online' },
  { key: 'whatsapp_table', label: 'WhatsApp meja (QR)' },
]
const CHANNEL_LABEL = Object.fromEntries(CHANNELS.map((c) => [c.key, c.label])) as Record<DashboardOrderRow['channel'], string>
const pad = (h: number) => String(h).padStart(2, '0')

function drillQuery(drill: Drill): URLSearchParams {
  const params = new URLSearchParams({ period: drill.period })
  if (drill.period === 'range' && drill.range) {
    params.set('from', drill.range.from)
    params.set('to', drill.range.to)
  }
  params.set('hours', drill.hours)
  if (drill.hour !== undefined) params.set('hour', String(drill.hour))
  if (drill.item) params.set('product_id', drill.item.product_id)
  if (drill.outletId) params.set('outlet_id', drill.outletId)
  return params
}

function title(drill: Drill): string {
  const when = periodTitle(drill.period, drill.range)
  if (drill.kind === 'revenue') return `Revenue · ${when}`
  if (drill.kind === 'hour') return `Order · jam ${pad(drill.hour ?? 0)}.00–${pad(drill.hour ?? 0)}.59 · ${when}`
  if (drill.kind === 'item') return `${drill.item?.name ?? ''} · ${when}`
  return `Order · ${when}`
}

function where(o: DashboardOrderRow): string {
  if (o.table) return o.customer_name ? `${o.table} · ${o.customer_name}` : o.table
  return o.customer_name ? `${TYPE_LABEL[o.type]} · ${o.customer_name}` : TYPE_LABEL[o.type]
}

export function OrdersDrawer({ drill, outletCount, onClose }: { drill: Drill; outletCount: number; onClose: () => void }) {
  const { api, me } = useSession()
  const [method, setMethod] = useState<'' | 'cash' | 'qris'>('')
  const [channel, setChannel] = useState('')
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [more, setMore] = useState<{ key: string; rows: DashboardOrderRow[]; cursor: string | null }>()
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState<string>()
  const [openId, setOpenId] = useState<string>()
  const [leaving, setLeaving] = useState(false)
  const closeTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const close = useCallback(() => {
    if (closeTimer.current) return
    setLeaving(true)
    closeTimer.current = setTimeout(onClose, CLOSE_MS)
  }, [onClose])
  useEffect(() => () => clearTimeout(closeTimer.current), [])

  useEffect(() => {
    const t = setTimeout(() => setQ(search.trim()), 300)
    return () => clearTimeout(t)
  }, [search])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close])

  const params = drillQuery(drill)
  if (method) params.set('method', method)
  if (channel) params.set('channel', channel)
  if (q) params.set('q', q)
  params.set('limit', String(PAGE_SIZE))
  const query = params.toString()
  const result = useLoad(() => api.get<DashboardOrders>(`/owner/dashboard/orders?${query}`), query)
  // Keep the last result on screen while a filter reloads, so the drawer does not flash to "Memuat…".
  const data = useKept(result.data, !result.error)
  const reloading = result.loading && data !== undefined
  const extra = more?.key === query ? more : undefined
  const rows = [...(data?.orders ?? []), ...(extra?.rows ?? [])]
  const cursor = extra ? extra.cursor : data?.next_cursor ?? null

  async function loadMore() {
    if (!cursor) return
    setLoadingMore(true)
    setMoreError(undefined)
    try {
      const page = await api.get<DashboardOrders>(`/owner/dashboard/orders?${query}&cursor=${encodeURIComponent(cursor)}`)
      setMore({ key: query, rows: [...(extra?.rows ?? []), ...page.orders], cursor: page.next_cursor })
    } catch (e) {
      setMoreError(errorMessage(e))
    } finally {
      setLoadingMore(false)
    }
  }

  const outlet = me.outlets.find((o) => o.id === drill.outletId)
  const zone = outlet?.timezone ?? me.outlets[0]?.timezone ?? 'Asia/Jakarta'
  const today = todayIn(zone)
  const subtitle = [
    outlet?.name ?? 'Semua outlet',
    datesText(periodDates(drill.period, today, drill.range)),
    drill.hour === undefined && drill.kind !== 'item' ? HOURS_LABEL[drill.hours] : null,
  ].filter(Boolean).join(' · ')
  const multiOutlet = !drill.outletId && outletCount > 1
  const s = data?.summary
  const filtered = channel !== '' || q !== ''
  const listTotal = filtered || !s ? undefined : method === 'cash' ? s.cash_count : method === 'qris' ? s.qris_count : s.orders

  return (
    <div className={`fixed inset-0 z-40 flex justify-end bg-text/30 ${leaving ? 'animate-fade-out' : 'animate-fade-in'}`}
      role="dialog" aria-modal="true" aria-label={title(drill)}>
      <button type="button" aria-label="Tutup drawer" className="flex-1 cursor-default" onClick={close} />
      <div className={`h-full w-full max-w-[460px] overflow-y-auto overscroll-contain bg-surface p-5 shadow-xl ${leaving ? 'animate-drawer-out' : 'animate-drawer-in'}`}>
        {openId ? (
          <OrderDetailPanel orderId={openId} onClose={close} onBack={() => setOpenId(undefined)}
            onChanged={() => void result.reload()} />
        ) : (
          <>
            <div className="flex items-start justify-between gap-2">
              <h2 className="text-[16px] font-bold text-text">{title(drill)}</h2>
              <button type="button" aria-label="Tutup" className="-m-1 rounded p-1 text-[16px] text-text-muted transition-colors hover:bg-page hover:text-text" onClick={close}>✕</button>
            </div>
            <p className="mt-1 text-[12px] text-text-muted">{subtitle}</p>

            {result.error && !data ? (
              <div className="mt-4"><Alert>Detail belum bisa dimuat: {errorMessage(result.error)}</Alert></div>
            ) : !data || !s ? <Loading /> : (
              <>
                <SummaryBox drill={drill} data={data} />

                {multiOutlet && data.by_outlet.length > 1 && <PerOutlet rows={data.by_outlet} />}

                <section aria-label="Daftar order" className="mt-4 border-t border-border pt-4">
                  <h3 className="text-[11px] font-semibold tracking-wide text-text-muted">DAFTAR ORDER</h3>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <div role="group" aria-label="Metode bayar" className="flex flex-wrap gap-2">
                      {([['', 'Semua', s.orders], ['cash', 'Cash', s.cash_count], ['qris', 'QRIS', s.qris_count]] as const).map(([key, label, n]) => (
                        <button key={key} type="button" aria-pressed={method === key} onClick={() => setMethod(key)}
                          className={`h-[26px] rounded-full border px-3 text-[12px] transition-colors ${method === key
                            ? 'border-primary bg-primary-soft font-semibold text-primary'
                            : 'border-border bg-surface text-[#444444] hover:border-primary hover:text-primary'}`}>
                          {label} {formatNumber(n)}
                        </button>
                      ))}
                    </div>
                    <Select aria-label="Kanal" className="ml-auto h-[26px] w-auto text-[12px]" value={channel} onChange={(e) => setChannel(e.target.value)}>
                      <option value="">Semua kanal</option>
                      {CHANNELS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                    </Select>
                  </div>
                  <TextInput aria-label="Cari no. order" placeholder="Cari no. order…" className="mt-2 h-8 w-full text-[12px]"
                    value={search} onChange={(e) => setSearch(e.target.value)} />

                  {result.error ? <div className="mt-2"><Alert>Daftar belum bisa dimuat: {errorMessage(result.error)}</Alert></div> : null}
                  <div aria-busy={reloading} className={`transition-opacity duration-150 ${reloading ? 'opacity-50' : ''}`}>
                  {rows.length === 0 ? (
                    <p className="py-8 text-center text-[13px] text-text-muted">Belum ada order di periode ini.</p>
                  ) : (
                    <ul className="mt-2 divide-y divide-border">
                      {rows.map((o) => <OrderRow key={o.id} order={o} multiOutlet={multiOutlet} onOpen={() => setOpenId(o.id)} />)}
                    </ul>
                  )}
                  {rows.length > 0 && (
                    <p className="mt-2 text-[11px] text-text-muted">
                      Menampilkan {formatNumber(rows.length)}{listTotal !== undefined ? ` dari ${formatNumber(listTotal)}` : ''}
                    </p>
                  )}
                  </div>
                  {moreError && <div className="mt-2"><Alert>{moreError}</Alert></div>}
                  {cursor && (
                    <Button variant="ghost" className="mt-2 h-8 w-full text-[12px]" disabled={loadingMore} onClick={() => void loadMore()}>
                      {loadingMore ? 'Memuat…' : 'Muat lagi'}
                    </Button>
                  )}
                </section>
                <p className="mt-4 text-[11px] text-text-muted">
                  Revenue per order = subtotal (excl. PB1 &amp; ongkir). Klik order untuk detail.
                </p>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function SummaryBox({ drill, data }: { drill: Drill; data: DashboardOrders }) {
  const s = data.summary
  const methods = `${formatNumber(s.cash_count)} cash · ${formatNumber(s.qris_count)} QRIS`
  let label: string, value: string, side: string[]
  if (drill.kind === 'item' && data.item) {
    label = 'Terjual'
    value = formatNumber(data.item.quantity)
    side = [`${formatRupiah(data.item.revenue)}`, `dari ${formatNumber(s.orders)} order`, methods]
  } else if (drill.kind === 'revenue') {
    label = 'Revenue (excl. PB1)'
    value = formatRupiah(s.revenue_excl_pb1)
    side = [`${formatNumber(s.orders)} order`, methods,
      s.orders ? `rata-rata ${formatRupiah(Math.round(s.revenue_excl_pb1 / s.orders))}` : '']
  } else {
    label = 'Order'
    value = formatNumber(s.orders)
    side = [formatRupiah(s.revenue_excl_pb1), methods, 'revenue excl. PB1']
  }
  return (
    <div className="mt-4 flex items-start justify-between gap-3 rounded-lg bg-primary-soft px-4 py-3">
      <div className="min-w-0">
        <p className="text-[12px] text-text-muted">{label}</p>
        <p className="mt-0.5 text-[20px] font-bold text-text">{value}</p>
        {drill.kind === 'revenue' && drill.change && (
          <p className={`mt-0.5 text-[11px] ${drill.change.startsWith('▲') ? 'text-success' : drill.change.startsWith('▼') ? 'text-danger' : 'text-text-muted'}`}>
            {drill.change}
          </p>
        )}
      </div>
      <div className="shrink-0 text-right">
        <p className="text-[13px] font-semibold text-text">{side[0]}</p>
        {side.slice(1).filter(Boolean).map((t) => <p key={t} className="text-[11px] text-text-muted">{t}</p>)}
      </div>
    </div>
  )
}

function PerOutlet({ rows }: { rows: DashboardOrders['by_outlet'] }) {
  const max = Math.max(1, ...rows.map((r) => r.revenue_excl_pb1))
  return (
    <section aria-label="Per outlet" className="mt-4">
      <h3 className="text-[11px] font-semibold tracking-wide text-text-muted">PER OUTLET</h3>
      <ul className="mt-2 space-y-2 text-[12px]">
        {rows.map((r) => (
          <li key={r.outlet_id} className="grid grid-cols-[1fr_96px_auto] items-center gap-3">
            <span className="truncate text-text">{r.name}</span>
            <span aria-hidden="true" className="h-2 rounded bg-primary-soft">
              <span className="block h-2 rounded bg-primary" style={{ width: `${(Math.max(0, r.revenue_excl_pb1) / max) * 100}%` }} />
            </span>
            <span className="text-right text-text">{formatRupiah(r.revenue_excl_pb1)} · {formatNumber(r.orders)} order</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function OrderRow({ order: o, multiOutlet, onOpen }: { order: DashboardOrderRow; multiOutlet: boolean; onOpen: () => void }) {
  const zone = ZONE_LABEL[o.timezone]
  const time = formatTime(o.created_at, o.timezone).replace(':', '.')
  const meta = [`${time}${zone && zone !== 'WIB' ? ` ${zone}` : ''}`, CHANNEL_LABEL[o.channel], multiOutlet ? o.outlet : null]
  return (
    <li>
      <button type="button" onClick={onOpen} className="-mx-2 w-[calc(100%+1rem)] rounded px-2 py-2.5 text-left transition-colors hover:bg-page">
        <span className="flex items-start justify-between gap-2">
          <span className="min-w-0 text-[13px] font-semibold text-text">{o.order_no} · {where(o)}</span>
          <span className="shrink-0 text-[13px] font-semibold text-text">{formatRupiah(o.revenue_excl_pb1)}</span>
        </span>
        <span className="mt-0.5 flex items-center justify-between gap-2">
          <span className="min-w-0 truncate text-[11px] text-text-muted">{meta.filter(Boolean).join(' · ')}</span>
          {o.payment_method && (
            <span className={`shrink-0 rounded-full px-2 text-[10px] font-semibold ${o.payment_method === 'qris'
              ? 'bg-primary-soft text-primary' : 'bg-[#F1F3F5] text-[#444444]'}`}>
              {o.payment_method === 'qris' ? 'QRIS' : 'Cash'}
            </span>
          )}
        </span>
        <span className="mt-0.5 block truncate text-[11px] text-text">{o.item_summary}</span>
      </button>
    </li>
  )
}
