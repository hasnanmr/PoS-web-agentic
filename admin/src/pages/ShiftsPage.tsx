// Wireframe S8 — Shift Kasir & Blind Count (T-039, T-040).
// Endpoints: GET /ops/outlets/{id}/drawers, POST /ops/drawers/{id}/shifts,
// POST /ops/shifts/{id}/close (Idempotency-Key).
// One drawer = at most one open shift; cash is accepted only while a shift is open.
// Blind count: Langkah 1 counts notes and coins with the expected cash hidden; Langkah 2 (expected,
// difference, surplus/shortage posted to the ledger) is shown only after the count is submitted.
import { useState } from 'react'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { formatNumber, formatRupiah, formatSignedRupiah, formatTime, ZONE_LABEL } from '../lib/format'
import type { DrawerCard, ShiftClosed } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Card, Loading, TextInput } from '../ui/kit'

const NOTES = [100000, 50000, 20000, 10000, 5000, 2000] as const

interface Closing {
  shiftId: string
  label: string
}

export default function ShiftsPage() {
  const { api, outlet } = useSession()
  const outletId = outlet?.id ?? ''
  const drawers = useLoad(() => api.get<DrawerCard[]>(`/ops/outlets/${outletId}/drawers`), outletId)
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string }>()
  const [closing, setClosing] = useState<Closing>()
  if (!outlet) return <PageHeader title="Shift Kasir" />
  return (
    <>
      <PageHeader title="Shift Kasir" />
      <div className="space-y-4 p-4 md:p-6">
        {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}
        {drawers.loading && !drawers.data ? <Loading /> : (
          <div className="grid gap-4 md:grid-cols-2">
            {(drawers.data ?? []).map((d, i) => (
              <Card key={d.drawer.id} title={`Drawer ${i + 1} · ${d.drawer.name}`}>
                {d.shift ? (
                  <div className="space-y-1 text-[12px]">
                    <p className="text-success">● Shift aktif — {d.shift.opened_by ?? '—'}</p>
                    <p>Dibuka {formatTime(d.shift.opened_at, outlet.timezone)} · kas awal {formatRupiah(d.shift.starting_cash)}</p>
                    <p>Cash masuk: {formatRupiah(d.shift.cash_in)} ({d.shift.cash_in_count} trx)</p>
                    <p>Refund cash: {formatRupiah(d.shift.cash_refunds)}</p>
                    <Button variant="action" className="mt-2" disabled={closing?.shiftId === d.shift.id}
                      onClick={() => { setNotice(undefined); setClosing({ shiftId: d.shift!.id, label: `Drawer ${i + 1}` }) }}>
                      Tutup shift & hitung kas
                    </Button>
                  </div>
                ) : (
                  <OpenShiftForm drawerId={d.drawer.id} onOpened={async () => {
                    setNotice({ tone: 'success', text: `Shift ${d.drawer.name} dibuka.` })
                    await drawers.reload()
                  }} onError={(text) => setNotice({ tone: 'danger', text })} />
                )}
              </Card>
            ))}
          </div>
        )}
        <ul className="list-disc space-y-1 pl-5 text-[11px] text-text-muted">
          <li>1 drawer = maks. 1 shift aktif.</li>
          <li>Cash hanya bisa diterima jika shift terbuka.</li>
          <li>Drawer diatur owner di Pengaturan Outlet.</li>
        </ul>
        {closing && (
          <CloseShiftPanel key={closing.shiftId} closing={closing}
            onClosed={() => void drawers.reload()} onDismiss={() => setClosing(undefined)} />
        )}
      </div>
    </>
  )
}

function OpenShiftForm({ drawerId, onOpened, onError }: {
  drawerId: string
  onOpened: () => Promise<void>
  onError: (text: string) => void
}) {
  const { api } = useSession()
  const [cash, setCash] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <div className="space-y-2 text-[12px]">
      <p className="text-text-muted">○ Tidak ada shift aktif</p>
      <label className="flex items-center gap-2">
        Kas awal
        <TextInput aria-label="Kas awal" inputMode="numeric" className="h-8 w-36"
          value={cash ? Number(cash).toLocaleString('id-ID') : ''} onChange={(e) => setCash(e.target.value.replace(/\D/g, ''))} />
      </label>
      <Button disabled={busy || cash === ''} onClick={async () => {
        setBusy(true)
        try {
          await api.post(`/ops/drawers/${drawerId}/shifts`, { starting_cash: Number(cash) })
          await onOpened()
        } catch (e) {
          onError(errorMessage(e))
        } finally {
          setBusy(false)
        }
      }}>Buka shift</Button>
    </div>
  )
}

const digits = (value: string) => value.replace(/\D/g, '').slice(0, 9)

function CloseShiftPanel({ closing, onClosed, onDismiss }: {
  closing: Closing
  onClosed: () => void
  onDismiss: () => void
}) {
  const { api } = useSession()
  const [counts, setCounts] = useState<Record<string, string>>({})
  const [coins, setCoins] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const [result, setResult] = useState<ShiftClosed>()
  // One key per count panel: a retry after a lost response replays instead of failing.
  const [idempotencyKey] = useState(() => `shift-close-${closing.shiftId}-${crypto.randomUUID()}`)
  const total = NOTES.reduce((sum, n) => sum + n * Number(counts[n] || 0), 0) + Number(coins || 0)

  async function submit() {
    setBusy(true)
    setError(undefined)
    const breakdown: Record<string, number> = { coins: Number(coins || 0) }
    NOTES.forEach((n) => { breakdown[String(n)] = Number(counts[n] || 0) })
    try {
      const closed = await api.post<ShiftClosed>(`/ops/shifts/${closing.shiftId}/close`,
        { count_breakdown: breakdown }, { 'Idempotency-Key': idempotencyKey })
      setResult(closed)
      onClosed()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title={`Tutup shift · ${closing.label}`}
      actions={result ? <button type="button" className="text-[12px] text-primary hover:underline" onClick={onDismiss}>Tutup</button> : null}>
      <p className="mb-3 text-[12px] text-text-muted">
        Langkah 1 — Blind count: hitung uang fisik di laci. Angka ekspektasi disembunyikan.
      </p>
      <div className="max-w-md space-y-1.5 text-[12px]">
        {NOTES.map((n) => (
          <div key={n} className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
            <span>{formatRupiah(n)}</span>
            <span className="flex items-center gap-1">×
              <TextInput aria-label={`Jumlah lembar ${formatRupiah(n)}`} inputMode="numeric" className="h-8 w-16 text-right"
                disabled={!!result} value={counts[n] ?? ''} onChange={(e) => setCounts({ ...counts, [n]: digits(e.target.value) })} />
            </span>
            <span className="text-right">{formatRupiah(n * Number(counts[n] || 0))}</span>
          </div>
        ))}
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
          <span>Rp 1.000 & koin</span>
          <TextInput aria-label="Nominal Rp 1.000 & koin" inputMode="numeric" className="h-8 w-28 text-right" disabled={!!result}
            value={coins ? `Rp ${Number(coins).toLocaleString('id-ID')}` : ''} onChange={(e) => setCoins(digits(e.target.value))} />
          <span className="text-right">{formatRupiah(Number(coins || 0))}</span>
        </div>
        <div className="flex items-center justify-between border-t border-border pt-2 text-[13px] font-semibold">
          <span>Total dihitung</span>
          <span>{formatRupiah(result?.counted_cash ?? total)}</span>
        </div>
      </div>

      <div className="mt-4 rounded-md bg-page p-3 text-[12px]">
        {result ? (
          <div className="space-y-1" role="status">
            <p className="font-semibold">Langkah 2 — hasil hitungan</p>
            <p>
              Ekspektasi = kas awal {formatNumber(result.starting_cash)} + cash masuk {formatNumber(result.cash_in)} − refund{' '}
              {formatNumber(result.cash_refunds)} = {formatRupiah(result.expected_cash)}
            </p>
            <p className={result.kind === 'shortage' ? 'text-danger' : result.kind === 'surplus' ? 'text-success' : ''}>
              Selisih: {formatSignedRupiah(result.difference)}
              {result.kind !== 'none' ? ` (${result.kind.toUpperCase()}) → diposting ke ledger` : ' (pas)'}
              {' · '}dihitung oleh {result.counted_by ?? '—'} {formatTime(result.closed_at, result.timezone)}{' '}
              {ZONE_LABEL[result.timezone] ?? ''}
            </p>
            <p className="text-text-muted">Hasil masuk Laporan Cash Count owner.</p>
          </div>
        ) : (
          <p className="text-text-muted">
            Langkah 2 — setelah submit hitungan: ekspektasi (kas awal + cash masuk − refund) dan selisih baru ditampilkan.
            Jika minus → SHORTAGE ke ledger, jika plus → SURPLUS. Hasil masuk Laporan Cash Count owner.
          </p>
        )}
      </div>
      {error && <div className="mt-3"><Alert>{error}</Alert></div>}
      {!result && (
        <Button variant="action" className="mt-3" disabled={busy} onClick={() => void submit()}>
          Submit hitungan & tutup shift
        </Button>
      )}
    </Card>
  )
}
