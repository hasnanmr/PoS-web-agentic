// Wireframes O16 / S12 — Buka PO: owner from Dashboard › PO & Supplier (O16), staff from S10 (S12,
// assigned outlets only — the session lists only those).
// Endpoints: GET /ops/suppliers (active suppliers), GET /ops/outlets/{id}/stock (bahan stok, as S7),
// POST /ops/outlets/{id}/purchase-orders (Idempotency-Key).
// Canvas notes: the PO is open straight away without approval and is recorded under its creator;
// opening a PO posts no ledger entry and changes no stock. Lines are a stock ingredient (g/kg,
// ml/L or pcs, matching its base unit) or free text (any unit, adds no stock).
import { useMemo, useState } from 'react'
import { useSession } from '../../app/session'
import { errorMessage } from '../../lib/api'
import { formatRupiah, todayIn } from '../../lib/format'
import type { PaymentTerm, PoDetail, StockResponse } from '../../lib/types'
import { useLoad } from '../../lib/useLoad'
import { Alert, Button, Field, LinkButton, Select, TextInput } from '../../ui/kit'
import { lineSubtotal, newKey, useIdempotencyKey } from './util'

const UNITS: Record<string, string[]> = { g: ['g', 'kg'], ml: ['ml', 'L'], pcs: ['pcs'] }
const FREE = '__free__'
const MAX_LINES = 50

interface Line {
  key: string
  stockItemId: string
  itemName: string
  quantity: string
  unit: string
  unitPrice: string
}

function emptyLine(): Line {
  return { key: newKey(), stockItemId: '', itemName: '', quantity: '', unit: '', unitPrice: '' }
}

export function PoForm({ defaultOutletId, onCancel, onOpened }: {
  defaultOutletId?: string
  onCancel: () => void
  onOpened: (po: PoDetail) => void
}) {
  const { api, me, role, outlet } = useSession()
  const [outletId, setOutletId] = useState(defaultOutletId || outlet?.id || me.outlets[0]?.id || '')
  const tz = me.outlets.find((o) => o.id === outletId)?.timezone ?? 'Asia/Jakarta'
  const today = todayIn(tz)
  const [supplierId, setSupplierId] = useState('')
  const [orderedOn, setOrderedOn] = useState(today)
  const [term, setTerm] = useState<PaymentTerm>('pay_later')
  const [dueDate, setDueDate] = useState('')
  const [expectedDate, setExpectedDate] = useState('')
  const [lines, setLines] = useState<Line[]>([emptyLine()])
  const [note, setNote] = useState('')
  const { keyFor, settled } = useIdempotencyKey()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()

  const suppliers = useLoad(() => api.get<{ id: string; name: string }[]>('/ops/suppliers'), 'suppliers')
  const stock = useLoad(() => api.get<StockResponse>(`/ops/outlets/${outletId}/stock`), outletId)
  const items = useMemo(() => stock.data?.items ?? [], [stock.data])
  const byId = useMemo(() => new Map(items.map((i) => [i.stock_item_id, i])), [items])

  const total = lines.reduce((sum, l) => sum + lineSubtotal(l.quantity, Number(l.unitPrice)), 0)
  // Money is whole rupiah (glossary): a unit price with a fraction is refused here, as by the API.
  const fractionalPrice = lines.some((l) => l.unitPrice !== '' && !Number.isInteger(Number(l.unitPrice)))
  const linesValid = !fractionalPrice && lines.every((l) => (l.stockItemId && l.stockItemId !== FREE ? true : l.itemName.trim() !== '')
    && Number(l.quantity.replace(',', '.')) > 0 && l.unit.trim() !== '' && l.unitPrice !== '' && Number(l.unitPrice) >= 0)
  const dateValid = term === 'pay_later' ? dueDate >= orderedOn && dueDate !== '' : expectedDate >= orderedOn && expectedDate !== ''
  const valid = outletId && supplierId && orderedOn && orderedOn <= today && dateValid && linesValid

  function update(index: number, change: Partial<Line>) {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, ...change } : l)))
  }

  function pickItem(index: number, value: string) {
    const item = byId.get(value)
    update(index, {
      stockItemId: value,
      itemName: '',
      unit: item ? (item.display_unit ?? item.unit) : '',
    })
  }

  async function submit() {
    setBusy(true)
    setError(undefined)
    try {
      const body = {
        supplier_id: supplierId,
        ordered_on: orderedOn,
        payment_term: term,
        due_date: term === 'pay_later' ? dueDate : null,
        expected_date: term === 'pay_in_advance' ? expectedDate : null,
        lines: lines.map((l) => ({
          ...(l.stockItemId && l.stockItemId !== FREE ? { stock_item_id: l.stockItemId } : { item_name: l.itemName.trim() }),
          quantity: l.quantity.replace(',', '.'),
          unit: l.unit.trim(),
          unit_price: Number(l.unitPrice),
        })),
        note: note.trim() || null,
      }
      const po = await api.post<PoDetail>(`/ops/outlets/${outletId}/purchase-orders`, body,
        { 'Idempotency-Key': keyFor({ outletId, ...body }) })
      settled()
      onOpened(po)
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  const termCard = (value: PaymentTerm) =>
    `rounded-lg border p-3 text-left ${term === value ? 'border-2 border-primary bg-primary-soft' : 'border-border bg-surface'}`

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_336px]">
      <section aria-label="Form Buka PO" className="rounded-lg border border-border bg-surface p-4">
        <div className="grid gap-x-3 sm:grid-cols-3">
          <Field label={role === 'owner' ? 'Outlet *' : 'Outlet * (yang ditugaskan)'} htmlFor="po-outlet">
            <Select id="po-outlet" value={outletId} onChange={(e) => {
              setOutletId(e.target.value)
              setLines([emptyLine()])
            }}>
              {me.outlets.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
          </Field>
          <Field label="Supplier *" htmlFor="po-supplier">
            <Select id="po-supplier" value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
              <option value="">Pilih supplier</option>
              {(suppliers.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          </Field>
          <Field label="Tanggal order *" htmlFor="po-date">
            <TextInput id="po-date" type="date" value={orderedOn} max={today} onChange={(e) => setOrderedOn(e.target.value)} />
          </Field>
        </div>
        {suppliers.error ? <div className="mb-3"><Alert>Daftar supplier belum bisa dimuat: {errorMessage(suppliers.error)}</Alert></div> : null}
        {stock.error ? <div className="mb-3"><Alert>Daftar bahan stok belum bisa dimuat: {errorMessage(stock.error)}</Alert></div> : null}
        {suppliers.data?.length === 0 && (
          <p className="-mt-2 mb-2 text-[11px] text-warning">
            Belum ada supplier aktif. {role === 'owner' ? 'Tambahkan lewat Daftar supplier.' : 'Minta owner menambahkan supplier.'}
          </p>
        )}

        <p className="mb-2 text-[13px] font-semibold text-text">Skema pembayaran *</p>
        <div role="radiogroup" aria-label="Skema pembayaran" className="mb-4 grid gap-3 sm:grid-cols-2">
          <div className={termCard('pay_later')}>
            <label className="flex items-center gap-2 text-[13px] font-semibold text-primary">
              <input type="radio" name="po-term" checked={term === 'pay_later'} onChange={() => setTerm('pay_later')} />
              Bayar mundur (tempo)
            </label>
            <p className="mt-1 text-[11px] text-text">Barang datang & dicek → PO ditutup → pengingat bayar di dashboard owner.</p>
            <label className="mt-2 flex items-center gap-2 text-[12px] text-text">
              Jatuh tempo:
              <TextInput aria-label="Jatuh tempo" type="date" className="h-8" value={dueDate} min={orderedOn}
                disabled={term !== 'pay_later'} onChange={(e) => setDueDate(e.target.value)} />
            </label>
          </div>
          <div className={termCard('pay_in_advance')}>
            <label className="flex items-center gap-2 text-[13px] font-semibold text-text">
              <input type="radio" name="po-term" checked={term === 'pay_in_advance'} onChange={() => setTerm('pay_in_advance')} />
              Bayar di muka
            </label>
            <p className="mt-1 text-[11px] text-text">Permintaan bayar langsung muncul di dashboard owner → barang tiba & dicek → PO ditutup.</p>
            <label className="mt-2 flex items-center gap-2 text-[12px] text-text">
              Perkiraan barang tiba:
              <TextInput aria-label="Perkiraan barang tiba" type="date" className="h-8" value={expectedDate} min={orderedOn}
                disabled={term !== 'pay_in_advance'} onChange={(e) => setExpectedDate(e.target.value)} />
            </label>
          </div>
        </div>

        <p className="mb-2 text-[13px] font-semibold text-text">Item PO *</p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-[12px]">
            <thead>
              <tr className="bg-page text-left text-[10px] text-text-muted">
                <th className="px-2 py-1.5 font-semibold">BAHAN STOK / ITEM TEKS</th>
                <th className="w-20 px-2 py-1.5 font-semibold">QTY</th>
                <th className="w-24 px-2 py-1.5 font-semibold">SATUAN</th>
                <th className="w-32 px-2 py-1.5 font-semibold">HARGA SATUAN</th>
                <th className="w-28 px-2 py-1.5 text-right font-semibold">SUBTOTAL</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {lines.map((l, i) => {
                const stockItem = byId.get(l.stockItemId)
                const free = !l.stockItemId || l.stockItemId === FREE
                return (
                  <tr key={l.key}>
                    <td className="px-1 py-1">
                      <div className="flex gap-1">
                        <Select aria-label={`Item ${i + 1}`} className="h-8 text-[12px]" value={l.stockItemId || FREE}
                          onChange={(e) => pickItem(i, e.target.value)}>
                          <option value={FREE}>Teks bebas (tidak menambah stok)</option>
                          {items.map((it) => <option key={it.stock_item_id} value={it.stock_item_id}>{it.name}</option>)}
                        </Select>
                        {free && (
                          <TextInput aria-label={`Nama item ${i + 1}`} placeholder="mis. Gas LPG 12 kg" className="h-8 text-[12px]"
                            maxLength={120} value={l.itemName} onChange={(e) => update(i, { itemName: e.target.value })} />
                        )}
                      </div>
                    </td>
                    <td className="px-1 py-1">
                      <TextInput aria-label={`Qty ${i + 1}`} inputMode="decimal" className="h-8 text-[12px]" value={l.quantity}
                        onChange={(e) => update(i, { quantity: e.target.value })} />
                    </td>
                    <td className="px-1 py-1">
                      {stockItem ? (
                        <Select aria-label={`Satuan ${i + 1}`} className="h-8 text-[12px]" value={l.unit}
                          onChange={(e) => update(i, { unit: e.target.value })}>
                          {UNITS[stockItem.unit].map((u) => <option key={u} value={u}>{u}</option>)}
                        </Select>
                      ) : (
                        <TextInput aria-label={`Satuan ${i + 1}`} placeholder="tabung" className="h-8 text-[12px]" maxLength={20}
                          value={l.unit} onChange={(e) => update(i, { unit: e.target.value })} />
                      )}
                    </td>
                    <td className="px-1 py-1">
                      <TextInput aria-label={`Harga satuan ${i + 1}`} type="number" inputMode="numeric" min={0} step={1} className="h-8 text-[12px]"
                        value={l.unitPrice} onChange={(e) => update(i, { unitPrice: e.target.value })} />
                    </td>
                    <td className="px-2 py-1 text-right text-text">{formatRupiah(lineSubtotal(l.quantity, Number(l.unitPrice)))}</td>
                    <td className="px-1 py-1 text-center">
                      <button type="button" aria-label={`Hapus item ${i + 1}`} disabled={lines.length === 1}
                        className="text-text-muted hover:text-danger disabled:opacity-30"
                        onClick={() => setLines((prev) => prev.filter((_, j) => j !== i))}>✕</button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {fractionalPrice && <p className="mt-1 text-[11px] text-danger">Harga satuan harus rupiah bulat (tanpa desimal).</p>}
        <LinkButton className="mt-2 text-[12px]" disabled={lines.length >= MAX_LINES}
          onClick={() => setLines((prev) => [...prev, emptyLine()])}>
          + Tambah item (bahan dari daftar stok, atau teks bebas — tidak menambah stok)
        </LinkButton>

        <div className="mt-4">
          <Field label="Catatan" htmlFor="po-note">
            <TextInput id="po-note" maxLength={300} placeholder="Antar pagi sebelum jam 09:00" value={note}
              onChange={(e) => setNote(e.target.value)} />
          </Field>
        </div>
        {error && <div className="mb-3"><Alert>{error}</Alert></div>}
        <div className="flex flex-wrap items-center justify-between gap-3 border-y border-border py-2">
          <p className="text-[16px] font-bold text-text">Total PO <span className="ml-2">{formatRupiah(total)}</span></p>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onCancel}>Batal</Button>
            <Button variant="action" disabled={!valid || busy} onClick={submit}>{busy ? 'Membuka…' : 'Buka PO'}</Button>
          </div>
        </div>
        <p className="mt-2 text-[11px] text-text-muted">
          Dibuka oleh: {me.user.display_name} ({role === 'owner' ? 'owner' : 'staf'}) · PO langsung terbuka tanpa persetujuan dan
          tercatat atas nama pembuat. Membuka PO tidak membuat ledger entry dan tidak mengubah stok.
        </p>
      </section>

      <aside aria-label="Setelah PO dibuka" className="h-fit rounded-lg border border-border bg-surface p-4 text-[12px] text-text">
        <h2 className="text-[13px] font-semibold">Setelah PO dibuka</h2>
        <p className="mt-2 font-semibold text-primary">Skema 1 · Bayar mundur</p>
        <ol className="mt-1 list-decimal pl-4 leading-5">
          <li>PO terbuka — menunggu barang</li>
          <li>Barang datang → staf cross-check qty vs PO</li>
          <li>Qty sesuai → PO ditutup</li>
          <li>Pengingat bayar muncul di dashboard owner sampai lunas (boleh dicicil)</li>
        </ol>
        <p className="mt-3 font-semibold text-teal">Skema 2 · Bayar di muka</p>
        <ol className="mt-1 list-decimal pl-4 leading-5">
          <li>PO terbuka → permintaan bayar langsung di dashboard owner</li>
          <li>Owner membayar (ledger expense hari itu)</li>
          <li>Barang tiba → staf cross-check qty vs PO</li>
          <li>Qty sesuai → PO ditutup (tidak bisa ditutup sebelum dibayar)</li>
        </ol>
        <div className="mt-3 rounded-md bg-page p-2.5 text-[11px] leading-4">
          <p className="mb-1 font-semibold text-text-muted">Hak akses</p>
          <p>Staf (outlet ditugaskan): buka PO, lihat PO outletnya, cross-check barang, tutup PO jika qty sesuai.</p>
          <p>Owner saja: supplier baru, catat pembayaran, batalkan PO, tutup PO yang ada selisih (catatan wajib), hutang & dashboard.</p>
        </div>
      </aside>
    </div>
  )
}
