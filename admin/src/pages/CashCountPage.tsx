// Wireframe O10 — Laporan Cash Count (T-040, T-102). Owner only.
// Endpoints: GET /owner/reports/cash-count?outlet_id=&drawer_id=&from=&to= (+ format=csv for "⭳ Ekspor CSV"),
// GET /owner/outlets/{id}/drawers for the drawer filter.
// Canvas note: "Selisih otomatis diposting ke ledger sebagai shortage / surplus."
import { useState } from 'react'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { formatDay, formatNumber, formatSignedRupiah, formatTime, localDay, shortOutlet, ZONE_LABEL } from '../lib/format'
import type { CashCount, CashCountRow, Drawer } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Card, Loading, Select } from '../ui/kit'
import { RangePicker } from '../ui/RangePicker'

function shiftWhen(r: CashCountRow): string {
  return `${formatDay(localDay(r.opened_at, r.timezone))} · ${formatTime(r.opened_at, r.timezone)}–${formatTime(r.closed_at, r.timezone)}`
}

function differenceText(d: number): string {
  if (d === 0) return '0'
  return `${d < 0 ? '−' : '+'} ${formatNumber(Math.abs(d))} ${d < 0 ? 'shortage' : 'surplus'}`
}

export default function CashCountPage() {
  const { api, me } = useSession()
  const [outletId, setOutletId] = useState('')
  const [drawerId, setDrawerId] = useState('')
  const [range, setRange] = useState<{ from: string; to: string }>()
  const [exportError, setExportError] = useState<string>()
  const params = new URLSearchParams()
  if (outletId) params.set('outlet_id', outletId)
  if (outletId && drawerId) params.set('drawer_id', drawerId)
  if (range) {
    params.set('from', range.from)
    params.set('to', range.to)
  }
  const query = params.toString()
  const report = useLoad(() => api.get<CashCount>(`/owner/reports/cash-count${query ? `?${query}` : ''}`), query)
  const drawers = useLoad(
    () => (outletId ? api.get<Drawer[]>(`/owner/outlets/${outletId}/drawers`) : Promise.resolve([])),
    outletId,
  )
  const r = report.data

  async function exportCsv() {
    setExportError(undefined)
    try {
      const sep = query ? '&' : '?'
      const blob = await api.blob(`/owner/reports/cash-count${query ? `?${query}` : ''}${sep}format=csv`)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `cash-count-${r?.from ?? ''}-${r?.to ?? ''}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setExportError(errorMessage(e))
    }
  }

  return (
    <>
      <PageHeader title="Laporan Cash Count" />
      <div className="space-y-4 p-4 md:p-6">
        <div className="flex flex-wrap items-center gap-2 text-[12px]">
          <Select aria-label="Outlet" className="h-8 w-auto" value={outletId}
            onChange={(e) => { setOutletId(e.target.value); setDrawerId('') }}>
            <option value="">Outlet: Semua</option>
            {me.outlets.map((o) => <option key={o.id} value={o.id}>Outlet: {o.name}</option>)}
          </Select>
          <Select aria-label="Drawer" className="h-8 w-auto" value={drawerId} disabled={!outletId}
            onChange={(e) => setDrawerId(e.target.value)}>
            <option value="">Drawer: Semua</option>
            {(drawers.data ?? []).map((d) => <option key={d.id} value={d.id}>Drawer: {d.number} · {d.name}</option>)}
          </Select>
          <RangePicker value={r ? { from: r.from, to: r.to } : range} onChange={setRange} />
          <Button variant="ghost" className="h-8 sm:ml-auto" onClick={() => void exportCsv()}>⭳ Ekspor CSV</Button>
        </div>
        {exportError && <Alert>{exportError}</Alert>}
        {report.error ? <Alert>Laporan belum bisa dimuat: {errorMessage(report.error)}</Alert> : null}
        {!r ? (report.loading ? <Loading /> : null) : (
          <Card>
            <div className="flex flex-wrap gap-x-8 gap-y-1 text-[13px]">
              <span>Total shift: <b>{r.summary.shifts}</b></span>
              <span>Shift dengan selisih: <b>{r.summary.shifts_with_difference}</b></span>
              <span>Total shortage: <b className="text-danger">{formatSignedRupiah(r.summary.total_shortage)}</b></span>
              <span>Total surplus: <b className="text-success">{formatSignedRupiah(r.summary.total_surplus)}</b></span>
            </div>
            <p className="mt-1 text-[11px] text-text-muted">Selisih otomatis diposting ke ledger sebagai shortage / surplus.</p>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-[12px]">
                <thead className="text-[11px] tracking-wide text-text-muted">
                  <tr className="border-b border-border">
                    <th className="py-2 font-semibold">TANGGAL / SHIFT</th>
                    <th className="font-semibold">OUTLET · DRAWER</th>
                    <th className="text-right font-semibold">KAS AWAL</th>
                    <th className="text-right font-semibold">EKSPEKTASI</th>
                    <th className="text-right font-semibold">DIHITUNG</th>
                    <th className="text-right font-semibold">SELISIH</th>
                    <th className="pl-4 font-semibold">DIHITUNG OLEH</th>
                  </tr>
                </thead>
                <tbody>
                  {r.rows.map((row) => (
                    <tr key={row.shift_id} className="border-b border-border last:border-0">
                      <td className="py-2">{shiftWhen(row)}</td>
                      <td>
                        {shortOutlet(row.outlet.name)} · Drawer {row.drawer.number}
                        {row.timezone !== 'Asia/Jakarta' ? ` (${ZONE_LABEL[row.timezone]})` : ''}
                      </td>
                      <td className="text-right">{formatNumber(row.starting_cash)}</td>
                      <td className="text-right">{formatNumber(row.expected_cash)}</td>
                      <td className="text-right">{formatNumber(row.counted_cash)}</td>
                      <td className={`text-right ${row.difference < 0 ? 'text-danger' : row.difference > 0 ? 'text-success' : ''}`}>
                        {differenceText(row.difference)}
                      </td>
                      <td className="pl-4">{row.counted_by ?? '—'}</td>
                    </tr>
                  ))}
                  {r.rows.length === 0 && (
                    <tr><td colSpan={7} className="py-4 text-text-muted">Belum ada shift yang ditutup di periode ini.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </div>
    </>
  )
}
