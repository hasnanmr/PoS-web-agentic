// Wireframe S5 / M3 — Open Bills (T-033, T-068).
// Endpoints: GET/POST /ops/outlets/{id}/bills, GET /ops/bills/{id}, POST /ops/bills/{id}/close
// (Idempotency-Key). One open bill per table or guest; one full payment; no split bill.
// Tutup bill opens the payment step (PaymentDialog): cash received + change, or the QRIS.
import { useState } from 'react'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { formatRupiah, formatTime } from '../lib/format'
import type { BillCard, BillDetail, ShiftRow, TableRow } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { usePolling } from '../lib/usePolling'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Card, LinkButton, Loading, Select, TextInput } from '../ui/kit'
import { PaymentDialog } from '../ui/PaymentDialog'

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
  const { api, me, outlet } = useSession()
  const bill = useLoad(() => api.get<BillDetail>(`/ops/bills/${billId}`), billId)
  const shifts = useLoad(() => api.get<ShiftRow[]>(`/ops/outlets/${outlet!.id}/shifts/current`), outlet!.id)
  usePolling(bill) // orders added from the counter show up, and the total to pay stays current
  const [method, setMethod] = useState<'cash' | 'qris'>('cash')
  const [paying, setPaying] = useState(false)
  const [drawerId, setDrawerId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const [key] = useState(() => (typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `bill-${Date.now()}`))
  const b = bill.data
  if (!b || !outlet) return <Loading />
  // The server needs a drawer when several shifts are open and none is the cashier's own.
  const openShifts = shifts.data ?? []
  const myShift = openShifts.find((s) => s.opened_by === me.user.id)
  const shift = openShifts.find((s) => s.drawer_id === drawerId) ?? myShift ??
    (openShifts.length === 1 ? openShifts[0] : undefined)
  const drawerAmbiguous = !shift && openShifts.length > 1
  // A failed shifts request is not the same as "no open shift": show the error, not the shift hint.
  const shiftsFailed = shifts.data === undefined && Boolean(shifts.error)
  const canPay = b.orders.length > 0 && (method === 'qris' || Boolean(shift))

  // Cash and QRIS both go through the payment step; the bill closes on "Pembayaran selesai".
  async function close(cash?: number) {
    setBusy(true)
    setError(undefined)
    try {
      const res = await api.post<{ total: number; change_due: number | null; orders_completed: number }>(
        `/ops/bills/${b!.id}/close`,
        method === 'cash' ? { method, cash_received: cash, drawer_id: shift?.drawer_id } : { method },
        { 'Idempotency-Key': key })
      await onClosed(`Bill ditutup · ${formatRupiah(res.total)} · ${res.orders_completed} order completed${res.change_due != null ? ` · kembalian ${formatRupiah(res.change_due)}` : ''}`)
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

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
        {b.orders.length === 0 && (
          <li className="text-text-muted">
            Belum ada order di bill ini.{' '}
            <LinkButton className="text-danger" onClick={async () => {
              try {
                await api.post(`/ops/bills/${b.id}/void`)
                await onClosed('Bill kosong dibatalkan.')
              } catch (e) {
                setError(errorMessage(e))
              }
            }}>Batalkan bill</LinkButton>
          </li>
        )}
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
            className={`h-9 rounded-md border ${method === m ? 'border-primary bg-primary-soft font-semibold text-primary' : 'border-border'}`}>
            {m === 'cash' ? 'Cash' : 'QRIS'}
          </button>
        ))}
      </div>
      {method === 'cash' && drawerAmbiguous && (
        <label className="mt-2 block text-[12px]">
          <span className="mb-1 block font-semibold">Drawer penerima cash</span>
          <Select aria-label="Drawer" value={drawerId} onChange={(e) => setDrawerId(e.target.value)}>
            <option value="">Pilih drawer</option>
            {openShifts.map((s) => (
              <option key={s.id} value={s.drawer_id}>
                Drawer {s.drawer_number} · {s.drawer_name}{s.opened_by_name ? ` (${s.opened_by_name})` : ''}
              </option>
            ))}
          </Select>
        </label>
      )}
      {method === 'cash' && shifts.data !== undefined && !shift && !drawerAmbiguous && (
        <p className="mt-1 text-[11px] text-text-muted">Cash butuh shift kasir terbuka.</p>
      )}
      {method === 'cash' && shiftsFailed && (
        <div className="mt-2">
          <Alert>
            Gagal memuat shift kasir: {errorMessage(shifts.error)}{' '}
            <LinkButton onClick={() => void shifts.reload()}>Coba lagi</LinkButton>
          </Alert>
        </div>
      )}
      <p className="mt-2 text-[11px] text-text-muted">Split bill tidak didukung di MVP.</p>
      {error && !paying && <div className="mt-2"><Alert>{error}</Alert></div>}
      <Button variant="action" className="mt-3 w-full" disabled={!canPay || busy}
        onClick={() => { setError(undefined); setPaying(true) }}>
        Tutup bill & bayar {formatRupiah(b.total)} → semua order completed
      </Button>
      {paying && (
        <PaymentDialog method={method} total={b.total} outletId={outlet.id} busy={busy} error={error}
          onConfirm={(cash) => void close(cash)} onCancel={() => { setPaying(false); setError(undefined) }} />
      )}
    </Card>
  )
}
