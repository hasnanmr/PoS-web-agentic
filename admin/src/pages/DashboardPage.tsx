// Wireframe O2 — Dashboard (T-071), owner only, with header tabs **Ringkasan** and **PO & Supplier**
// (PRD v0.15, issue #16).
// - Tab Ringkasan (O2, T-071/T-124): header outlet filter + period (Hari ini / Minggu / Bulan) +
//   jam (Semua jam / Jam ramai / Jam sepi); KPI tiles, peta keramaian, keramaian outlet sekarang,
//   order per jam, stok rendah & sold out, komposisi per kanal + metode bayar (./dashboard/Summary,
//   GET /owner/dashboard?outlet_id=&period=&hours=), and "Item terlaris"
//   (GET /owner/dashboard/top-items?outlet_id=&period=day|month|year).
//   Canvas notes (Item terlaris): the card has its own period toggle (Hari ini / Bulan ini / Tahun
//   ini, default Hari ini) and follows only the header outlet filter; top 5 by quantity sold (ties:
//   higher revenue); paid orders only; revenue excl. PB1 and delivery fee; empty → "Belum ada item
//   terjual di periode ini."
//   Header "Rentang ▾" (period=range&from=&to=): a custom range of at most 92 days up to today.
//   "Link pesan online" strip above the KPI tiles (page 07 note "Bagikan link outlet",
//   ./shared/OutletShareLink, GET /owner/outlets/{id}/public-link): follows the header outlet.
// - O2b drawer (./dashboard/OrdersDrawer, GET /owner/dashboard/orders): opened by the Revenue and
//   Order tiles, a bar of "Order per jam", or a row of "Item terlaris".
// - Tab PO & Supplier (O17 cards + O15 list/detail, ./po/PoTab): its own outlet + month filter,
//   Daftar supplier, + Buka PO (O16, ./po/PoForm, breadcrumb "Dashboard › PO & Supplier").
// The tab and the O16 view live in the URL (?tab=po, ?tab=po&view=new) so they can be linked.
import { useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { formatNumber, formatRupiah, todayIn } from '../lib/format'
import type { DashboardPeriod, DashboardSummary, DrillPeriod, HoursFilter, TopItem, TopItems, TopItemsPeriod } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Loading, Select } from '../ui/kit'
import { RangePicker } from '../ui/RangePicker'
import { OrdersDrawer, type Drill } from './dashboard/OrdersDrawer'
import { MAX_RANGE_DAYS, revenueChange, type DayRange } from './dashboard/period'
import { BusynessMap, ChannelsAndMethods, CurrentCrowd, KpiTiles, LowStock, OrdersPerHour } from './dashboard/Summary'
import { SupplierDialog } from './po/dialogs'
import { OutletLinkStrip } from './shared/OutletShareLink'
import { PoForm } from './po/PoForm'
import { PoTab } from './po/PoTab'
import { monthLabel, recentMonths } from './po/util'

const PERIODS: { key: TopItemsPeriod; label: string }[] = [
  { key: 'day', label: 'Hari ini' },
  { key: 'month', label: 'Bulan ini' },
  { key: 'year', label: 'Tahun ini' },
]

const ITEM_PERIOD: Record<TopItemsPeriod, DrillPeriod> = { day: 'today', month: 'month', year: 'year' }

const HEADER_PERIODS: { key: DashboardPeriod; label: string }[] = [
  { key: 'today', label: 'Hari ini' },
  { key: 'week', label: 'Minggu' },
  { key: 'month', label: 'Bulan' },
]
const HOURS: { key: HoursFilter; label: string }[] = [
  { key: 'all', label: 'Semua jam' },
  { key: 'busy', label: 'Jam ramai' },
  { key: 'quiet', label: 'Jam sepi' },
]

/** Header toggle (O2 "Hari ini | Minggu | Bulan", "Semua jam | Jam ramai | Jam sepi"). */
const segment = (on: boolean) =>
  `h-full rounded px-2.5 ${on ? 'border border-primary bg-surface font-semibold text-primary' : 'text-[#444444]'}`

/** Header toggle (O2 "Hari ini | Minggu | Bulan | Rentang ▾", "Semua jam | Jam ramai | Jam sepi"). */
function Segmented<T extends string>({ label, options, value, onChange, children }: {
  label: string
  options: { key: T; label: string }[]
  value: T
  onChange: (v: T) => void
  children?: ReactNode
}) {
  return (
    <div role="group" aria-label={label} className="flex h-8 rounded-md border border-border bg-[#EEF2F8] p-0.5 text-[12px]">
      {options.map((o) => (
        <button key={o.key} type="button" aria-pressed={value === o.key} onClick={() => onChange(o.key)} className={segment(value === o.key)}>
          {o.label}
        </button>
      ))}
      {children}
    </div>
  )
}

export default function DashboardPage() {
  const { me } = useSession()
  const [search, setSearch] = useSearchParams()
  const tab = search.get('tab') === 'po' ? 'po' : 'summary'
  const creating = tab === 'po' && search.get('view') === 'new'
  const [outletId, setOutletId] = useState('')
  const [period, setPeriod] = useState<DashboardPeriod>('today')
  const [range, setRange] = useState<DayRange>()
  const [hours, setHours] = useState<HoursFilter>('all')
  const [drill, setDrill] = useState<Drill>()
  const [poOutletId, setPoOutletId] = useState('')
  const tz = me.outlets.find((o) => o.id === poOutletId)?.timezone ?? 'Asia/Jakarta'
  const currentMonth = todayIn(tz).slice(0, 7)
  const [month, setMonth] = useState<string>()
  const [suppliers, setSuppliers] = useState(false)
  const [focusId, setFocusId] = useState<string | undefined>(search.get('po') ?? undefined) // ?po=<id>: O9b "Lihat PO →"

  const go = (next: Record<string, string>) => setSearch(next)

  if (creating) {
    return (
      <>
        <PageHeader title="Buka Purchase Order"
          tabs={<p className="text-[12px] text-text-muted">Dashboard › PO & Supplier</p>} />
        <div className="p-4 md:p-6">
          <PoForm defaultOutletId={poOutletId} onCancel={() => go({ tab: 'po' })}
            onOpened={(po) => {
              setFocusId(po.id)
              go({ tab: 'po' })
            }} />
        </div>
      </>
    )
  }

  const tabs = (
    <div role="tablist" aria-label="Tab dashboard" className="flex gap-5 text-[13px]">
      {([['summary', 'Ringkasan'], ['po', 'PO & Supplier']] as const).map(([key, label]) => (
        <button key={key} type="button" role="tab" aria-selected={tab === key}
          onClick={() => {
            setFocusId(undefined)
            go(key === 'po' ? { tab: 'po' } : {})
          }}
          className={`-mb-3 border-b-[3px] pb-2.5 md:-mb-4 md:pb-3.5 ${tab === key
            ? 'border-primary font-semibold text-primary'
            : 'border-transparent text-text-muted'}`}>
          {label}
        </button>
      ))}
    </div>
  )

  const outletSelect = (value: string, onChange: (v: string) => void) => (
    <Select aria-label="Outlet" className="h-8 w-full text-[12px] sm:w-[150px]" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Semua outlet</option>
      {me.outlets.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
    </Select>
  )

  if (tab === 'po') {
    const shown = month ?? currentMonth
    return (
      <>
        <PageHeader title="Dashboard" tabs={tabs} actions={
          <div className="flex flex-wrap items-center gap-2">
            {outletSelect(poOutletId, (v) => {
              setFocusId(undefined)
              setPoOutletId(v)
            })}
            <Select aria-label="Periode" className="h-8 w-auto text-[12px]" value={shown} onChange={(e) => setMonth(e.target.value)}>
              {recentMonths(currentMonth).map((m) => <option key={m} value={m}>Periode: {monthLabel(m)}</option>)}
            </Select>
            <Button variant="ghost" className="h-8 text-[12px]" onClick={() => setSuppliers(true)}>☰ Daftar supplier</Button>
            <Button variant="action" className="h-8" onClick={() => go({ tab: 'po', view: 'new' })}>+ Buka PO</Button>
          </div>
        } />
        <div className="p-4 md:p-6">
          <PoTab key={poOutletId} outletId={poOutletId} month={shown} focusId={focusId} />
        </div>
        {suppliers && <SupplierDialog onClose={() => setSuppliers(false)} />}
      </>
    )
  }

  return (
    <>
      <PageHeader title="Dashboard" tabs={tabs} actions={
        <div className="flex flex-wrap items-center gap-2">
          {outletSelect(outletId, setOutletId)}
          <Segmented label="Periode" options={HEADER_PERIODS} value={period} onChange={setPeriod}>
            <RangePicker label="Rentang" withYear={false} align="right" pressed={period === 'range'}
              value={period === 'range' ? range : undefined} buttonClassName={segment(period === 'range')}
              max={todayIn(me.outlets.find((o) => o.id === outletId)?.timezone ?? 'Asia/Jakarta')} maxDays={MAX_RANGE_DAYS}
              onChange={(r) => {
                setRange(r)
                setPeriod('range')
              }} />
          </Segmented>
          <Segmented label="Jam" options={HOURS} value={hours} onChange={setHours} />
        </div>
      } />
      <div className="space-y-4 p-4 md:p-6">
        <OutletLinkStrip headerOutletId={outletId} />
        <SummaryCards outletId={outletId} period={period} range={range} hours={hours}
          outletCount={outletId ? 1 : me.outlets.length} onDrill={setDrill} />
        <TopItemsCard outletId={outletId}
          onItem={(item, p) => setDrill({ kind: 'item', outletId, period: ITEM_PERIOD[p], hours: 'all', item })} />
      </div>
      {drill && <OrdersDrawer drill={drill} outletCount={me.outlets.length} onClose={() => setDrill(undefined)} />}
    </>
  )
}

function SummaryCards({ outletId, period, range, hours, outletCount, onDrill }: {
  outletId: string
  period: DashboardPeriod
  range: DayRange | undefined
  hours: HoursFilter
  outletCount: number
  onDrill: (drill: Drill) => void
}) {
  const { api } = useSession()
  const params = new URLSearchParams({ period })
  if (period === 'range' && range) {
    params.set('from', range.from)
    params.set('to', range.to)
  }
  params.set('hours', hours)
  if (outletId) params.set('outlet_id', outletId)
  const query = params.toString()
  const result = useLoad(() => api.get<DashboardSummary>(`/owner/dashboard?${query}`), query)
  const data = result.data
  if (result.error && !data) return <Alert>Ringkasan belum bisa dimuat: {errorMessage(result.error)}</Alert>
  if (!data) return <Loading />
  return (
    <>
      {result.error ? <Alert>Ringkasan belum bisa dimuat: {errorMessage(result.error)}</Alert> : null}
      <KpiTiles data={data} onOpen={(kind) => onDrill({ kind, outletId, period, range, hours, change: revenueChange(data) })} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[640fr_356fr]">
        <BusynessMap data={data} />
        <CurrentCrowd data={data} />
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <OrdersPerHour data={data} onHour={(hour) => onDrill({ kind: 'hour', outletId, period, range, hours: 'all', hour })} />
        <LowStock data={data} outletCount={outletCount} />
        <ChannelsAndMethods data={data} />
      </div>
    </>
  )
}

function TopItemsCard({ outletId, onItem }: { outletId: string; onItem: (item: TopItem, period: TopItemsPeriod) => void }) {
  const { api } = useSession()
  const [period, setPeriod] = useState<TopItemsPeriod>('day')
  const params = new URLSearchParams({ period })
  if (outletId) params.set('outlet_id', outletId)
  const query = params.toString()
  const result = useLoad(() => api.get<TopItems>(`/owner/dashboard/top-items?${query}`), query)
  const items = result.data?.top_items
  const maxQty = Math.max(1, ...(items ?? []).map((i) => i.quantity_sold))

  return (
    <section aria-labelledby="top-items-title" className="rounded-lg border border-border bg-surface p-4 lg:max-w-[676px]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="top-items-title" className="text-[14px] font-bold text-text">Item terlaris</h2>
          <p className="mt-0.5 text-[11px] text-text-muted">Top 5 menurut jumlah terjual · ikut filter outlet · klik item untuk daftar order</p>
        </div>
        <div role="group" aria-label="Periode item terlaris" className="flex rounded-md bg-[#EEF2F8] p-0.5 text-[12px]">
          {PERIODS.map((p) => (
            <button key={p.key} type="button" aria-pressed={period === p.key} onClick={() => setPeriod(p.key)}
              className={`h-6 min-w-[68px] rounded px-2 ${period === p.key
                ? 'border border-[#CFD4DA] bg-surface font-semibold text-primary'
                : 'text-[#444444]'}`}>
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {result.error ? (
        <div className="mt-3"><Alert>Item terlaris belum bisa dimuat: {errorMessage(result.error)}</Alert></div>
      ) : null}
      {!items ? (result.loading ? <Loading /> : null) : items.length === 0 ? (
        <p className="py-8 text-center text-[13px] text-text-muted">Belum ada item terjual di periode ini.</p>
      ) : (
        <table className="mt-3 w-full text-[13px]">
          <thead>
            <tr className="border-b border-border text-left text-[11px] text-text-muted">
              <th className="w-6 pb-2 font-semibold">#</th>
              <th className="pb-2 font-semibold">ITEM</th>
              <th className="hidden pb-2 sm:table-cell" aria-hidden="true" />
              <th className="pb-2 text-right font-semibold">TERJUAL</th>
              <th className="pb-2 text-right font-semibold">PENDAPATAN</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={`${i}-${item.product_id}`} onClick={() => onItem(item, period)}
                className="cursor-pointer border-b border-border last:border-0 hover:bg-page">
                <td className="py-2 font-semibold text-text-muted">{i + 1}</td>
                <td className="py-2 font-semibold text-text">
                  <button type="button" className="text-left hover:text-primary hover:underline"
                    onClick={(e) => { e.stopPropagation(); onItem(item, period) }}>{item.name}</button>
                </td>
                <td className="hidden w-[180px] py-2 sm:table-cell">
                  <div className="h-2 rounded bg-primary-soft">
                    <div className="h-2 rounded bg-primary" style={{ width: `${(item.quantity_sold / maxQty) * 100}%` }} />
                  </div>
                </td>
                <td className="py-2 pl-3 text-right font-semibold text-text">{formatNumber(item.quantity_sold)}</td>
                <td className="py-2 pl-3 text-right text-text">{formatRupiah(item.revenue)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="mt-3 text-[11px] text-text-muted">
        Pendapatan = total baris item (harga + add-on) excl. PB1, hanya order lunas.
      </p>
    </section>
  )
}
