// Wireframe O2 — Dashboard + keramaian (T-071). Owner only.
// Built so far: header outlet filter + "Item terlaris" card. The other O2 cards (KPI, peta
// keramaian, keramaian outlet sekarang, order per jam, stok rendah, komposisi per kanal) and the
// header period/jam toggles come with T-071/T-123.
// Endpoint: GET /owner/dashboard/top-items?outlet_id=&period=day|month|year.
// Canvas notes (Item terlaris): the card has its own period toggle (Hari ini / Bulan ini /
// Tahun ini, default Hari ini) and follows only the header outlet filter; top 5 by quantity sold
// (ties: higher revenue); paid orders only; revenue excl. PB1 and delivery fee; empty →
// "Belum ada item terjual di periode ini."
import { useState } from 'react'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { formatNumber, formatRupiah } from '../lib/format'
import type { TopItems, TopItemsPeriod } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Loading, Select } from '../ui/kit'

const PERIODS: { key: TopItemsPeriod; label: string }[] = [
  { key: 'day', label: 'Hari ini' },
  { key: 'month', label: 'Bulan ini' },
  { key: 'year', label: 'Tahun ini' },
]

export default function DashboardPage() {
  const { me } = useSession()
  const [outletId, setOutletId] = useState('')

  return (
    <>
      <PageHeader
        title="Dashboard"
        actions={
          <Select aria-label="Outlet" className="h-8 w-auto text-[12px]" value={outletId}
            onChange={(e) => setOutletId(e.target.value)}>
            <option value="">Semua outlet</option>
            {me.outlets.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </Select>
        }
      />
      <div className="space-y-4 p-4 md:p-6">
        <TopItemsCard outletId={outletId} />
      </div>
    </>
  )
}

function TopItemsCard({ outletId }: { outletId: string }) {
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
          <p className="mt-0.5 text-[11px] text-text-muted">Top 5 menurut jumlah terjual · ikut filter outlet</p>
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
              <tr key={`${i}-${item.name}`} className="border-b border-border last:border-0">
                <td className="py-2 font-semibold text-text-muted">{i + 1}</td>
                <td className="py-2 font-semibold text-text">{item.name}</td>
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
