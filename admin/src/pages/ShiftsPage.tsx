// Wireframe S8 — Shift Kasir & Blind Count (T-039; T-040 blind count close comes next).
// Endpoints: GET /ops/outlets/{id}/drawers, POST /ops/drawers/{id}/shifts.
// One drawer = at most one open shift; cash is accepted only while a shift is open.
import { useState } from 'react'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { formatRupiah, formatTime } from '../lib/format'
import type { DrawerCard } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Card, Loading, TextInput } from '../ui/kit'

export default function ShiftsPage() {
  const { api, outlet } = useSession()
  const outletId = outlet?.id ?? ''
  const drawers = useLoad(() => api.get<DrawerCard[]>(`/ops/outlets/${outletId}/drawers`), outletId)
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string }>()
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
                    <p className="pt-2 text-text-muted">Tutup shift dengan blind count tersedia di rilis berikutnya.</p>
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
