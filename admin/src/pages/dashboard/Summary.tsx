// Wireframe O2 — Dashboard tab Ringkasan (T-071, T-124): KPI tiles, Peta keramaian, Keramaian
// outlet sekarang, Order per jam, Stok rendah & sold out, Komposisi per kanal + Metode bayar.
// Endpoint: GET /owner/dashboard?outlet_id=&period=today|week|month&hours=all|busy|quiet
// (docs/architecture/screen-endpoint-map.md → O2). The map, current crowd, and low stock ignore
// the header period and hours; "Item terlaris" is its own card (DashboardPage).
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { formatNumber, formatQty, formatRupiah, formatTime, hourRanges, WEEKDAYS, ZONE_LABEL } from '../../lib/format'
import type { CrowdLevel, DashboardPeriod, DashboardSummary, HourSummary } from '../../lib/types'

const PERIOD_WORD: Record<DashboardPeriod, string> = { today: 'hari ini', week: 'minggu ini', month: 'bulan ini' }
const PREVIOUS: Record<DashboardPeriod, string> = { today: 'kemarin', week: 'minggu lalu', month: 'bulan lalu' }

// Wireframe colours: map scale light → peak, the channel/method bars, and the crowd badges.
const MAP_SCALE = ['bg-[#E8EFFB]', 'bg-[#B9CDF0]', 'bg-[#5F86CF]', 'bg-primary', 'bg-accent-orange']
const SERIES = ['bg-primary', 'bg-[#8FB0E8]', 'bg-[#CBD5E6]']
const CROWD: Record<CrowdLevel, { label: string; badge: string; bar: string }> = {
  ramai: { label: 'Ramai', badge: 'bg-[#FFF1E6] text-[#9A3412]', bar: 'bg-accent-orange' },
  normal: { label: 'Normal', badge: 'bg-primary-soft text-primary', bar: 'bg-primary' },
  sepi: { label: 'Sepi', badge: 'bg-[#F1F3F5] text-text-muted', bar: 'bg-[#8FB0E8]' },
}
const CHANNELS = { whatsapp_online: 'WhatsApp online', whatsapp_table: 'WhatsApp meja (QR)', counter: 'Counter' }
const METHODS = { cash: 'Cash', qris: 'QRIS' }

const pad = (h: number) => String(h % 24).padStart(2, '0')

function Panel({ title, subtitle, actions, children, className = '', id }: {
  title: string
  subtitle?: string
  actions?: ReactNode
  children: ReactNode
  className?: string
  id: string
}) {
  return (
    <section aria-labelledby={id} className={`min-w-0 rounded-lg border border-border bg-surface p-4 ${className}`}>
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 id={id} className="text-[14px] font-bold text-text">{title}</h2>
          {subtitle && <p className="mt-0.5 text-[11px] text-text-muted">{subtitle}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  )
}

export function KpiTiles({ data }: { data: DashboardSummary }) {
  const k = data.kpis
  const change = k.change_pct
  const tiles = [
    { label: 'Order', value: formatNumber(k.orders), note: `${formatNumber(k.cash_count)} cash · ${formatNumber(k.qris_count)} QRIS`, accent: 'bg-primary' },
    { label: 'PB1 terkumpul', value: formatRupiah(k.pb1_collected), note: 'Terpisah dari revenue', accent: 'bg-[#CFD4DA]' },
    { label: 'Delivery fee', value: formatRupiah(k.delivery_fee), note: `${formatNumber(k.delivery_orders)} order delivery`, accent: 'bg-[#CFD4DA]' },
  ]
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <div className="rounded-lg bg-primary px-4 py-3.5 text-white">
        <p className="text-[12px] text-[#DCE7FA]">Revenue {PERIOD_WORD[data.period]} (excl. PB1)</p>
        <p className="mt-1 text-[20px] font-bold">{formatRupiah(k.revenue_excl_pb1)}</p>
        <p className="mt-0.5 text-[11px] text-[#DCE7FA]">
          {change === null ? `Belum ada data ${PREVIOUS[data.period]}`
            : `${change < 0 ? '▼' : '▲'} ${Math.abs(change)}% vs ${PREVIOUS[data.period]}`}
        </p>
      </div>
      {tiles.map((t) => (
        <div key={t.label} className="flex items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3.5">
          <span aria-hidden="true" className={`h-14 w-1 shrink-0 rounded ${t.accent}`} />
          <div className="min-w-0">
            <p className="text-[12px] text-text-muted">{t.label}</p>
            <p className="mt-1 text-[20px] font-bold text-text">{t.value}</p>
            <p className="mt-0.5 text-[11px] text-text-muted">{t.note}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

export function BusynessMap({ data }: { data: DashboardSummary }) {
  const cells = data.busyness_map
  const hours = [...new Set(cells.map((c) => c.hour))].sort((a, b) => a - b)
  const value = new Map(cells.map((c) => [`${c.weekday}-${c.hour}`, c.avg_orders]))
  const max = Math.max(0, ...cells.map((c) => c.avg_orders))
  const level = (v: number) => (max === 0 || v === 0 ? 0 : Math.min(4, Math.floor((v / max) * 5)))
  return (
    <Panel id="o2-map" title="Peta keramaian · hari × jam"
      subtitle="Rata-rata order per jam · 4 minggu terakhir · zona waktu outlet"
      actions={
        <div aria-hidden="true" className="hidden items-center gap-1 text-[11px] text-text-muted sm:flex">
          Sepi {MAP_SCALE.map((c) => <span key={c} className={`h-3 w-[18px] rounded-sm ${c}`} />)} Puncak
        </div>
      }>
      {hours.length === 0 ? (
        <p className="py-8 text-center text-[13px] text-text-muted">Atur jam buka outlet untuk melihat peta keramaian.</p>
      ) : (
        <table className="w-full table-fixed border-separate border-spacing-[2px] text-[11px]">
          <thead>
            <tr>
              <th className="w-9" />
              {hours.map((h, i) => (
                <th key={h} scope="col" className="font-normal text-text-muted">
                  <span className={i % 2 ? 'hidden sm:inline' : ''}>{pad(h)}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {WEEKDAYS.map((day, d) => (
              <tr key={day}>
                <th scope="row" className="pr-1 text-left font-semibold text-text">{day}</th>
                {hours.map((h) => {
                  const v = value.get(`${d + 1}-${h}`)
                  return (
                    <td key={h} title={v === undefined ? `${day} ${pad(h)}: tutup` : `${day} ${pad(h)}: ${v.toLocaleString('id-ID')} order`}
                      className={`h-5 rounded-sm ${v === undefined ? 'bg-transparent' : MAP_SCALE[level(v)]}`} />
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  )
}

export function CurrentCrowd({ data }: { data: DashboardSummary }) {
  const tz = data.current_crowd[0]?.timezone ?? 'Asia/Jakarta'
  return (
    <Panel id="o2-crowd" title="Keramaian outlet sekarang"
      subtitle={`Pukul ${formatTime(data.as_of, tz).replace(':', '.')} · dari meja terisi dan order aktif`}>
      <ul className="space-y-3.5">
        {data.current_crowd.map((c) => {
          const style = CROWD[c.level]
          const zone = ZONE_LABEL[c.timezone]
          const pct = c.total_tables ? (c.occupied_tables / c.total_tables) * 100 : 0
          return (
            <li key={c.outlet_id}>
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-[13px] font-semibold text-text">
                  {c.name}{zone && zone !== 'WIB' ? ` (${zone})` : ''}
                </p>
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${style.badge}`}>{style.label}</span>
              </div>
              <div className="mt-1.5 flex items-center gap-3">
                <div className="h-2 flex-1 rounded bg-[#EEF2F8]">
                  <div className={`h-2 rounded ${style.bar}`} style={{ width: `${pct}%` }} />
                </div>
                <p className="shrink-0 text-[11px] text-text-muted">
                  {c.total_tables ? `${c.occupied_tables}/${c.total_tables} meja · ` : ''}{c.active_orders} order aktif
                </p>
              </div>
            </li>
          )
        })}
      </ul>
    </Panel>
  )
}

function summaryLine(label: string, s: HourSummary): string {
  return s.hours.length ? `${label} ${hourRanges(s.hours)} · ${s.orders} order (${s.share_pct}%)` : `Belum ada ${label.toLowerCase()}`
}

export function OrdersPerHour({ data }: { data: DashboardSummary }) {
  const series = data.orders_per_hour
  const max = Math.max(1, ...series.map((s) => s.orders))
  const peak = Math.max(0, ...series.map((s) => s.orders))
  return (
    <Panel id="o2-hours" title={`Order per jam · ${PERIOD_WORD[data.period]}`} subtitle="Ramai ≥ 130% rata-rata per jam · sepi ≤ 60%">
      {series.length === 0 ? (
        <p className="py-8 text-center text-[13px] text-text-muted">Belum ada order di periode ini.</p>
      ) : (
        <>
          <div className="flex h-[180px] items-end gap-1 border-b border-border" role="list" aria-label="Order per jam">
            {series.map((s) => (
              <div key={s.hour} role="listitem" aria-label={`${pad(s.hour)}:00 ${s.orders} order${s.mark === 'busy' ? ', jam ramai' : s.mark === 'quiet' ? ', jam sepi' : ''}`}
                className="flex h-full min-w-0 flex-1 flex-col items-center justify-end">
                {s.orders === peak && peak > 0 && (
                  <span className={`text-[10px] font-semibold ${s.mark === 'busy' ? 'text-[#9A3412]' : 'text-text-muted'}`}>{s.orders}</span>
                )}
                <div className={`w-full max-w-[15px] rounded-t-sm ${s.mark === 'busy' ? 'bg-accent-orange' : s.mark === 'quiet' ? 'bg-[#B9CDF0]' : 'bg-primary'}`}
                  style={{ height: `${(s.orders / max) * 150}px` }} />
              </div>
            ))}
          </div>
          <div aria-hidden="true" className="mt-1 flex gap-1 text-[11px] text-text-muted">
            {series.map((s, i) => <span key={s.hour} className="min-w-0 flex-1 text-center">{i % 2 ? '' : pad(s.hour)}</span>)}
          </div>
          <p className="mt-3 flex items-center gap-2 text-[11px] text-text">
            <span aria-hidden="true" className="h-2 w-2 rounded-sm bg-accent-orange" />{summaryLine('Jam ramai', data.busy_summary)}
          </p>
          <p className="mt-1 flex items-center gap-2 text-[11px] text-text">
            <span aria-hidden="true" className="h-2 w-2 rounded-sm bg-[#B9CDF0]" />{summaryLine('Jam sepi', data.quiet_summary)}
          </p>
        </>
      )}
    </Panel>
  )
}

export function LowStock({ data, outletCount }: { data: DashboardSummary; outletCount: number }) {
  const rows = data.low_stock.slice(0, 5)
  return (
    <Panel id="o2-stock" title="Stok rendah & sold out" className="flex flex-col"
      actions={<Link to="/stock" className="shrink-0 text-[12px] font-semibold text-primary">Buka stok →</Link>}>
      {rows.length === 0 ? (
        <p className="py-8 text-center text-[13px] text-text-muted">Semua stok aman.</p>
      ) : (
        <ul className="divide-y divide-border">
          {rows.map((r) => (
            <li key={`${r.outlet_id}-${r.stock_item}`} className="flex items-start justify-between gap-2 py-2.5 first:pt-0">
              <div className="min-w-0">
                <p className="truncate text-[13px] font-semibold text-text">{r.stock_item}</p>
                <p className="text-[11px] text-text-muted">
                  {formatQty(r.on_hand, r.unit, r.display_unit)} tersisa
                  {r.status === 'low' ? ` · min ${formatQty(r.low_threshold, r.unit, r.display_unit)}` : ''}
                  {outletCount > 1 ? ` · ${r.outlet}` : ''}
                </p>
              </div>
              <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${r.status === 'out' ? 'bg-danger-soft text-danger' : 'bg-warning-soft text-warning'}`}>
                {r.status === 'out' ? 'Sold out' : 'Rendah'}
              </span>
            </li>
          ))}
        </ul>
      )}
      {data.low_stock.length > rows.length && (
        <p className="mt-1 text-[11px] text-text-muted">+{data.low_stock.length - rows.length} bahan lain</p>
      )}
      <p className="mt-auto pt-3 text-[11px] text-text-muted">Sold out otomatis disembunyikan dari katalog.</p>
    </Panel>
  )
}

function StackedBar({ parts, label }: { parts: number[]; label: string }) {
  const total = parts.reduce((a, b) => a + b, 0)
  return (
    <div aria-hidden="true" title={label} className="flex h-3.5 overflow-hidden rounded bg-[#EEF2F8]">
      {total > 0 && parts.map((p, i) => <div key={i} className={SERIES[i]} style={{ width: `${(p / total) * 100}%` }} />)}
    </div>
  )
}

export function ChannelsAndMethods({ data }: { data: DashboardSummary }) {
  const methods = data.payment_methods
  return (
    <Panel id="o2-channels" title="Komposisi per kanal" subtitle={`${formatNumber(data.kpis.orders)} order ${PERIOD_WORD[data.period]}`}
      className="flex flex-col">
      <StackedBar parts={data.channel_mix.map((c) => c.orders)} label="Komposisi per kanal" />
      <ul className="mt-3 space-y-2 text-[12px]">
        {data.channel_mix.map((c, i) => (
          <li key={c.channel} className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-2 text-text"><span aria-hidden="true" className={`h-2.5 w-2.5 rounded-sm ${SERIES[i]}`} />{CHANNELS[c.channel]}</span>
            <span className="text-text">{formatNumber(c.orders)} order · {c.share_pct}%</span>
          </li>
        ))}
      </ul>
      <div className="mt-4 border-t border-border pt-3">
        <p className="mb-2 text-[11px] font-semibold tracking-wide text-text-muted">METODE BAYAR</p>
        <StackedBar parts={methods.map((m) => Math.max(0, m.amount))} label="Metode bayar" />
        <ul className="mt-3 space-y-2 text-[12px]">
          {methods.map((m, i) => (
            <li key={m.method} className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-text"><span aria-hidden="true" className={`h-2.5 w-2.5 rounded-sm ${SERIES[i]}`} />{METHODS[m.method]}</span>
              <span className="text-text">{formatRupiah(m.amount)} · {formatNumber(m.transactions)} trx</span>
            </li>
          ))}
        </ul>
      </div>
      <Link to="/finance/cashflow" className="mt-auto pt-4 text-[12px] font-semibold text-primary">Lihat laporan cashflow →</Link>
    </Panel>
  )
}
