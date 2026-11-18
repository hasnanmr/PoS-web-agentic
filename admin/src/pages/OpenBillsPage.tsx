// Wireframe S5 / M3 — Open Bills (T-033, T-068).
// Endpoints: GET/POST /ops/outlets/{id}/bills, GET /ops/bills/{id}, POST /ops/bills/{id}/close
// (Idempotency-Key). One open bill per table or guest; one full payment; no split bill.
import { useState } from 'react'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { formatRupiah, formatTime } from '../lib/format'
import type { BillCard, BillDetail, ShiftRow, TableRow } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Card, LinkButton, Loading, Select, TextInput } from '../ui/kit'

function duration(iso: string, now = Date.now()): string {
  const minutes = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000))
  if (minutes < 60) return `${minutes} mnt`
  return `${Math.floor(minutes / 60)} j ${minutes % 60} mnt`
}

function billName(b: { table_name: string | null; table_area: string | null; guest_name: string | null }): string {
  if (b.table_name) return `${b.table_name}${b.table_area && b.table_area !== 'Indoor' ? ` (${b.table_area})` : ''}`
  return `Tamu: ${b.guest_name ?? ''}`
}

export default function OpenBillsPage() {
  const { api, outlet } = useSession()
  const outletId = outlet?.id ?? ''
  const bills = useLoad(
    () => api.get<{ payment_mode: string; bills: BillCard[] }>(`/ops/outlets/${outletId}/bills`),
    outletId,
  )
  const [selected, setSelected] = useState<string>()
  const [opening, setOpening] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string }>()
  const list = bills.data?.bills ?? []
  const current = selected && list.some((b) => b.id === selected) ? selected : list[0]?.id

  if (!outlet) return <PageHeader title="Open Bills" />
  const openBillMode = bills.data?.payment_mode === 'open_bill'
  return (
    <>
      <PageHeader
        title="Open Bills"
        actions={
          <div className="flex items-center gap-2">
            <span className="hidden rounded-full bg-primary-soft px-3 py-1 text-[12px] sm:inline">
              Mode outlet: {openBillMode ? 'Open bill' : 'Pay first'}
            </span>
            <Button disabled={!openBillMode} onClick={() => setOpening(true)}>+ Buka bill (meja / nama tamu)</Button>
          </div>
        }
      />
      <div className="grid gap-4 p-4 md:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="min-w-0 space-y-3">
          {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}
          {opening && (
            <OpenBillForm onCancel={() => setOpening(false)} onOpened={async (id) => {
              setOpening(false)
              await bills.reload()
              setSelected(id)
            }} />
          )}
          {bills.loading && !bills.data ? <Loading /> : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {list.map((b) => (
                <button key={b.id} type="button" onClick={() => setSelected(b.id)}
                  className={`rounded-lg border bg-surface p-3 text-left text-[12px] ${current === b.id ? 'border-primary ring-1 ring-primary' : 'border-border'}`}>
                  <div className="text-[13px] font-semibold">{billName(b)}</div>
                  <div className="mt-1">{formatRupiah(b.running_total)}</div>
                  <div className="text-text-muted">{b.order_count} order · ⏱ {duration(b.opened_at)}</div>
                </button>
              ))}
              {list.length === 0 && (
                <p className="text-[12px] text-text-muted">
                  {openBillMode ? 'Belum ada open bill.' : 'Outlet ini memakai mode pay first; open bill tidak dipakai.'}
                </p>
              )}
            </div>
          )}
          <ul className="list-disc space-y-1 pl-5 text-[11px] text-text-muted">
            <li>Satu meja / tamu hanya boleh 1 open bill.</li>
            <li>Order baru dari QR meja atau counter otomatis masuk ke bill yang sama.</li>
            <li>Jika mode outlet diganti ke pay-first, order lama tetap di flow open bill.</li>
          </ul>
        </div>
        {current && (
          <BillPanel key={current} billId={current} onClosed={async (text) => {
            setNotice({ tone: 'success', text })
            setSelected(undefined)
            await bills.reload()
          }} />
        )}
      </div>
    </>
  )
}

function OpenBillForm({ onOpened, onCancel }: { onOpened: (id: string) => Promise<void>; onCancel: () => void }) {
  const { api, outlet } = useSession()
  const tables = useLoad(() => api.get<TableRow[]>(`/ops/outlets/${outlet!.id}/tables`), outlet!.id)
  const [mode, setMode] = useState<'table' | 'guest'>('table')
  const [tableId, setTableId] = useState('')
  const [guest, setGuest] = useState('')
  const [error, setError] = useState<string>()
  return (
    <Card title="Buka bill">
      <div className="mb-2 flex gap-4 text-[12px]">
        <label className="flex items-center gap-1"><input type="radio" checked={mode === 'table'} onChange={() => setMode('table')} /> Meja</label>
        <label className="flex items-center gap-1"><input type="radio" checked={mode === 'guest'} onChange={() => setMode('guest')} /> Nama tamu</label>
      </div>
      {mode === 'table' ? (
        <Select aria-label="Meja untuk bill" value={tableId} onChange={(e) => setTableId(e.target.value)}>
          <option value="">Pilih meja</option>
          {(tables.data ?? []).filter((t) => !t.open_bill).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </Select>
      ) : (
        <TextInput aria-label="Nama tamu" placeholder="Pak Joko" value={guest} onChange={(e) => setGuest(e.target.value)} />
      )}
      {error && <div className="mt-2"><Alert>{error}</Alert></div>}
      <div className="mt-3 flex gap-3">
        <Button disabled={mode === 'table' ? !tableId : !guest.trim()} onClick={async () => {
          try {
            const bill = await api.post<BillDetail>(`/ops/outlets/${outlet!.id}/bills`,
              mode === 'table' ? { table_id: tableId } : { guest_name: guest.trim() })
            await onOpened(bill.id)
          } catch (e) {
            setError(errorMessage(e))
          }
        }}>Buka bill</Button>
        <LinkButton onClick={onCancel}>Batal</LinkButton>
      </div>
    </Card>
  )
}

function BillPanel({ billId, onClosed }: { billId: string; onClosed: (text: string) => Promise<void> }) {
  const { api, outlet } = useSession()
  const bill = useLoad(() => api.get<BillDetail>(`/ops/bills/${billId}`), billId)
  const shifts = useLoad(() => api.get<ShiftRow[]>(`/ops/outlets/${outlet!.id}/shifts/current`), outlet!.id)
  const [method, setMethod] = useState<'cash' | 'qris'>('cash')
  const [received, setReceived] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const [key] = useState(() => (typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `bill-${Date.now()}`))
  const b = bill.data
  if (!b || !outlet) return <Loading />
  const cash = Number(received || 0)
  const shift = shifts.data?.[0]
  const canPay = b.orders.length > 0 && (method === 'qris' || (Boolean(shift) && cash >= b.total))

  return (
    <Card title={`Bill ${billName(b)} · dibuka ${formatTime(b.opened_at, outlet.timezone)} (${duration(b.opened_at)})`}>
      <ul className="space-y-2 text-[12px]">
        {b.orders.map((o) => (
          <li key={o.id}>
            <div className="text-text-muted">{o.order_no} · {o.channel} · {formatTime(o.created_at, outlet.timezone)}</div>
            <div className="flex justify-between gap-2 pl-3">
              <span>{o.items.map((i) => `${i.quantity}× ${i.name}${i.addons ? ` + ${i.addons}` : ''}`).join(', ')}</span>
              <span>{formatRupiah(o.line_total)}</span>
            </div>
          </li>
        ))}
        {b.orders.length === 0 && <li className="text-text-muted">Belum ada order di bill ini.</li>}
      </ul>
      <dl className="mt-3 space-y-0.5 border-t border-border pt-2 text-[12px]">
        <div className="flex justify-between"><dt>Subtotal</dt><dd>{formatRupiah(b.subtotal)}</dd></div>
        {b.pb1_rate_bps != null && <div className="flex justify-between"><dt>PB1 {b.pb1_rate_bps / 100}%</dt><dd>{formatRupiah(b.pb1_amount)}</dd></div>}
        <div className="flex justify-between font-bold"><dt>Total berjalan</dt><dd>{formatRupiah(b.total)}</dd></div>
      </dl>

      <h3 className="mt-4 mb-2 text-[13px] font-semibold">Tutup bill — satu pembayaran penuh</h3>
      <div className="grid grid-cols-2 gap-2 text-[12px]">
        {(['cash', 'qris'] as const).map((m) => (
          <button key={m} type="button" aria-pressed={method === m} onClick={() => setMethod(m)}
            disabled={m === 'cash' && !shift}
            className={`h-9 rounded-md border ${method === m ? 'border-primary bg-primary-soft font-semibold text-primary' : 'border-border'} disabled:opacity-50`}>
            {m === 'cash' ? 'Cash' : 'QRIS'}
          </button>
        ))}
      </div>
      {method === 'cash' && (
        <label className="mt-2 flex items-center gap-2 text-[12px]">
          Uang diterima:
          <TextInput aria-label="Uang diterima bill" inputMode="numeric" className="h-8 w-32"
            value={received ? Number(received).toLocaleString('id-ID') : ''}
            onChange={(e) => setReceived(e.target.value.replace(/\D/g, ''))} />
          {cash >= b.total && <span className="text-success">→ Kembalian {formatRupiah(cash - b.total)}</span>}
        </label>
      )}
      {method === 'cash' && !shift && <p className="mt-1 text-[11px] text-text-muted">Cash butuh shift kasir terbuka.</p>}
      <p className="mt-2 text-[11px] text-text-muted">Split bill tidak didukung di MVP.</p>
      {error && <div className="mt-2"><Alert>{error}</Alert></div>}
      <Button variant="action" className="mt-3 w-full" disabled={!canPay || busy} onClick={async () => {
        setBusy(true)
        setError(undefined)
        try {
          const res = await api.post<{ total: number; change_due: number | null; orders_completed: number }>(
            `/ops/bills/${b.id}/close`,
            method === 'cash' ? { method, cash_received: cash } : { method },
            { 'Idempotency-Key': key })
          await onClosed(`Bill ditutup · ${formatRupiah(res.total)} · ${res.orders_completed} order completed${res.change_due != null ? ` · kembalian ${formatRupiah(res.change_due)}` : ''}`)
        } catch (e) {
          setError(errorMessage(e))
          setBusy(false)
        }
      }}>
        Tutup bill & bayar {formatRupiah(b.total)} → semua order completed
      </Button>
    </Card>
  )
}
