// Dialogs of the Dashboard tab "PO & Supplier" (owner only):
// - O17 "Catat pembayaran" — POST /owner/purchase-orders/{id}/payments (Idempotency-Key).
// - O17/O15 "Tutup dengan catatan" — POST /owner/purchase-orders/{id}/close.
// - O15 "Batalkan PO" — POST /owner/purchase-orders/{id}/cancel.
// - O15 "Daftar supplier" — GET/POST /owner/suppliers, PATCH /owner/suppliers/{id}.
import { useState } from 'react'
import { useSession } from '../../app/session'
import { errorMessage } from '../../lib/api'
import { formatDay, formatRupiah, todayIn } from '../../lib/format'
import type { PaymentTerm, ShiftRow, Supplier } from '../../lib/types'
import { useLoad } from '../../lib/useLoad'
import { Alert, Button, Field, LinkButton, Loading, Select, TextInput } from '../../ui/kit'
import { Dialog } from './ui'
import { TERM_LABEL, newKey } from './util'

export interface PayTarget {
  id: string
  number: string
  supplier: string
  outletId: string
  term: PaymentTerm
  total: number
  paid: number
  owed: number
  dueDate: string | null
}

type Method = 'transfer' | 'cash_drawer' | 'cash_outside'

/** O17 "Catat pembayaran". Pay later: up to what is still owed (instalments). Pay in advance:
 * the full amount at once. Cash can come out of an open shift's drawer, which lowers that
 * shift's expected cash. */
export function PaymentDialog({ target, onClose, onDone }: {
  target: PayTarget
  onClose: () => void
  onDone: () => void
}) {
  const { api, me } = useSession()
  const tz = me.outlets.find((o) => o.id === target.outletId)?.timezone ?? 'Asia/Jakarta'
  const [paidOn, setPaidOn] = useState(() => todayIn(tz))
  const [amount, setAmount] = useState(String(target.owed))
  const [method, setMethod] = useState<Method>('transfer')
  const [drawerId, setDrawerId] = useState('')
  const [key] = useState(newKey)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const shifts = useLoad(() => api.get<ShiftRow[]>(`/ops/outlets/${target.outletId}/shifts/current`), target.outletId)
  const openShifts = shifts.data ?? []
  const fixed = target.term === 'pay_in_advance'
  const value = fixed ? target.owed : Number(amount)
  const valid = Number.isInteger(value) && value > 0 && value <= target.owed && paidOn !== ''
    && (method !== 'cash_drawer' || drawerId !== '')

  async function save() {
    setBusy(true)
    setError(undefined)
    try {
      await api.post(`/owner/purchase-orders/${target.id}/payments`, {
        paid_on: paidOn,
        amount: value,
        method: method === 'transfer' ? 'transfer' : 'cash',
        drawer_id: method === 'cash_drawer' ? drawerId : null,
      }, { 'Idempotency-Key': key })
      onDone()
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <Dialog label={`Catat pembayaran ${target.number}`} onClose={onClose}>
      <h2 className="text-[15px] font-bold text-text">Catat pembayaran · {target.number} · {target.supplier}</h2>
      <p className="mt-1 text-[11px] text-text-muted">
        {TERM_LABEL[target.term]} · total {formatRupiah(target.total)} · sudah dibayar {formatRupiah(target.paid)} ·
        sisa {formatRupiah(target.owed)}{target.dueDate ? ` (JT ${formatDay(target.dueDate)})` : ''}
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Field label="Tanggal bayar" htmlFor="pay-date">
          <TextInput id="pay-date" type="date" value={paidOn} max={todayIn(tz)} onChange={(e) => setPaidOn(e.target.value)} />
        </Field>
        <Field label={fixed ? 'Nominal (bayar penuh)' : 'Nominal (maks. sisa)'} htmlFor="pay-amount">
          <TextInput id="pay-amount" type="number" inputMode="numeric" min={1} max={target.owed} disabled={fixed}
            value={fixed ? String(target.owed) : amount} onChange={(e) => setAmount(e.target.value)} />
        </Field>
      </div>
      <fieldset className="mt-1 text-[12px] text-text">
        <legend className="mb-1 text-[13px] font-semibold">Metode</legend>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <label className="flex items-center gap-1.5">
            <input type="radio" name="pay-method" checked={method === 'transfer'} onChange={() => setMethod('transfer')} />
            Transfer bank
          </label>
          <label className="flex items-center gap-1.5">
            <input type="radio" name="pay-method" checked={method === 'cash_drawer'} onChange={() => setMethod('cash_drawer')}
              disabled={openShifts.length === 0} />
            Cash — dari laci
          </label>
          {method === 'cash_drawer' && (
            <Select aria-label="Drawer" className="h-8 w-auto text-[12px]" value={drawerId} onChange={(e) => setDrawerId(e.target.value)}>
              <option value="">Pilih drawer (shift aktif)</option>
              {openShifts.map((s) => <option key={s.drawer_id} value={s.drawer_id}>{s.drawer_name} · {s.opened_by_name ?? 'shift aktif'}</option>)}
            </Select>
          )}
          <label className="flex items-center gap-1.5">
            <input type="radio" name="pay-method" checked={method === 'cash_outside'} onChange={() => setMethod('cash_outside')} />
            Cash di luar laci
          </label>
        </div>
        {!shifts.loading && openShifts.length === 0 && (
          <p className="mt-1 text-[11px] text-text-muted">Tidak ada shift kasir aktif di outlet ini, jadi cash dari laci tidak tersedia.</p>
        )}
      </fieldset>
      {error && <div className="mt-3"><Alert>{error}</Alert></div>}
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Batal</Button>
        <Button variant="action" disabled={!valid || busy} onClick={save}>{busy ? 'Menyimpan…' : 'Simpan pembayaran'}</Button>
      </div>
      <p className="mt-3 text-[11px] text-text-muted">
        Diposting ke ledger sebagai expense −{formatRupiah(value > 0 ? value : 0)} pada tanggal bayar
        (dengan no. PO & supplier). Tidak bisa diubah/dihapus. Cash dari laci mengurangi ekspektasi kas shift.
      </p>
    </Dialog>
  )
}

/** "Tutup dengan catatan" (owner only, PO with a difference) and "Batalkan PO" (reason
 * required): both take one required text. */
export function NoteDialog({ kind, poId, number, onClose, onDone }: {
  kind: 'close' | 'cancel'
  poId: string
  number: string
  onClose: () => void
  onDone: () => void
}) {
  const { api } = useSession()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const close = kind === 'close'

  async function save() {
    setBusy(true)
    setError(undefined)
    try {
      await api.post(`/owner/purchase-orders/${poId}/${kind}`, close ? { note: text.trim() } : { reason: text.trim() })
      onDone()
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <Dialog label={`${close ? 'Tutup dengan catatan' : 'Batalkan PO'} ${number}`} onClose={onClose}>
      <h2 className="text-[15px] font-bold text-text">{close ? 'Tutup dengan catatan' : 'Batalkan PO'} · {number}</h2>
      <p className="mt-1 text-[11px] text-text-muted">
        {close
          ? 'Catatan wajib (mis. “supplier kehabisan stok”). Hutang PO tempo menjadi qty diterima × harga; PO yang sudah ditutup tidak bisa dibuka lagi.'
          : 'Hanya untuk PO yang belum dibayar dan belum ada barang diterima. Alasan wajib.'}
      </p>
      <div className="mt-3">
        <Field label={close ? 'Catatan *' : 'Alasan *'} htmlFor="po-note">
          <TextInput id="po-note" maxLength={300} value={text} onChange={(e) => setText(e.target.value)} />
        </Field>
      </div>
      {error && <Alert>{error}</Alert>}
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Batal</Button>
        <Button variant={close ? 'action' : 'danger'} disabled={!text.trim() || busy} onClick={save}>
          {busy ? 'Menyimpan…' : close ? 'Tutup PO' : 'Batalkan PO'}
        </Button>
      </div>
    </Dialog>
  )
}

const EMPTY = { name: '', phone: '', note: '', is_active: true }

/** O15 "Daftar supplier" dialog (owner only): list, add, edit, deactivate. No delete. */
export function SupplierDialog({ onClose }: { onClose: () => void }) {
  const { api } = useSession()
  const list = useLoad(() => api.get<Supplier[]>('/owner/suppliers'), 'suppliers')
  const [editing, setEditing] = useState<Supplier | null>(null)
  const [form, setForm] = useState(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()

  function edit(s: Supplier) {
    setEditing(s)
    setForm({ name: s.name, phone: s.phone ?? '', note: s.note ?? '', is_active: s.is_active })
    setError(undefined)
  }

  function reset() {
    setEditing(null)
    setForm(EMPTY)
  }

  async function save() {
    setBusy(true)
    setError(undefined)
    const body = { name: form.name.trim(), phone: form.phone.trim() || null, note: form.note.trim() || null }
    try {
      if (editing) await api.patch(`/owner/suppliers/${editing.id}`, { ...body, is_active: form.is_active })
      else await api.post('/owner/suppliers', body)
      reset()
      await list.reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog label="Daftar supplier" onClose={onClose} wide>
      <div className="flex items-center justify-between">
        <h2 className="text-[16px] font-bold text-text">Daftar supplier</h2>
        <LinkButton onClick={onClose}>✕ Tutup</LinkButton>
      </div>
      {list.error ? <div className="mt-3"><Alert>{errorMessage(list.error)}</Alert></div> : null}
      {!list.data ? (list.loading ? <Loading /> : null) : (
        <table className="mt-3 w-full text-[12px]">
          <thead>
            <tr className="bg-page text-left text-[10px] text-text-muted">
              <th className="px-2 py-1.5 font-semibold">NAMA</th>
              <th className="px-2 py-1.5 font-semibold">TELEPON</th>
              <th className="hidden px-2 py-1.5 font-semibold sm:table-cell">CATATAN</th>
              <th className="px-2 py-1.5 font-semibold">STATUS</th>
              <th className="px-2 py-1.5" />
            </tr>
          </thead>
          <tbody>
            {list.data.length === 0 && (
              <tr><td colSpan={5} className="px-2 py-4 text-center text-text-muted">Belum ada supplier.</td></tr>
            )}
            {list.data.map((s) => (
              <tr key={s.id} className={s.is_active ? 'text-text' : 'text-text-muted'}>
                <td className="px-2 py-1.5 font-semibold">{s.name}</td>
                <td className="px-2 py-1.5">{s.phone ?? '—'}</td>
                <td className="hidden px-2 py-1.5 text-text-muted sm:table-cell">{s.note ?? '—'}</td>
                <td className={`px-2 py-1.5 ${s.is_active ? 'text-success' : ''}`}>{s.is_active ? '● Aktif' : '○ Nonaktif'}</td>
                <td className="px-2 py-1.5"><LinkButton className="text-[12px]" onClick={() => edit(s)} aria-label={`Ubah ${s.name}`}>Ubah</LinkButton></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <section aria-label={editing ? 'Ubah supplier' : 'Tambah supplier'} className="mt-3 rounded-lg bg-page p-3.5">
        <h3 className="mb-2 text-[13px] font-semibold text-text">{editing ? 'Ubah supplier' : 'Tambah supplier'}</h3>
        <div className="grid gap-x-3 sm:grid-cols-2">
          <Field label="Nama *" htmlFor="sup-name">
            <TextInput id="sup-name" maxLength={120} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="Telepon" htmlFor="sup-phone">
            <TextInput id="sup-phone" maxLength={30} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </Field>
        </div>
        <Field label="Catatan" htmlFor="sup-note">
          <TextInput id="sup-note" maxLength={300} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
        </Field>
        {editing && (
          <div role="radiogroup" aria-label="Status supplier" className="mb-3 flex gap-4 text-[12px]">
            <label className="flex items-center gap-1.5">
              <input type="radio" checked={form.is_active} onChange={() => setForm({ ...form, is_active: true })} /> Aktif
            </label>
            <label className="flex items-center gap-1.5">
              <input type="radio" checked={!form.is_active} onChange={() => setForm({ ...form, is_active: false })} /> Nonaktif
            </label>
          </div>
        )}
        {error && <div className="mb-2"><Alert>{error}</Alert></div>}
        <div className="flex gap-2">
          <Button variant="action" disabled={!form.name.trim() || busy} onClick={save}>{busy ? 'Menyimpan…' : 'Simpan supplier'}</Button>
          {editing && <Button variant="ghost" onClick={reset}>Batal</Button>}
        </div>
      </section>
      <p className="mt-3 text-[11px] text-text-muted">
        Supplier berlaku untuk semua outlet dan tidak bisa dihapus. Supplier nonaktif tidak muncul di pilihan Buka PO; PO lamanya tetap tampil.
      </p>
    </Dialog>
  )
}
