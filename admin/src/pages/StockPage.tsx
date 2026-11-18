// Wireframe S7 / M5 — Stok & Pergerakan (T-020, T-022, T-069). Owner and staff.
// Endpoints: GET /ops/outlets/{id}/stock, POST/GET /ops/outlets/{id}/stock-movements.
// Stock is never edited directly: only through append-only movements.
import { useRef, useState, type FormEvent } from 'react'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { displayFactor, formatDelta, formatQty, formatTime } from '../lib/format'
import type { Movement, StockResponse, StockRow } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Card, Field, Loading, Select, TextInput } from '../ui/kit'

type Filter = 'all' | 'low' | 'out'
type MoveType = 'restock' | 'waste' | 'adjustment'

const STATUS = {
  ok: { label: '● Aman', className: 'text-success' },
  low: { label: '● Rendah', className: 'text-warning' },
  out: { label: '● Habis', className: 'text-danger' },
} as const

const MOVE_LABEL: Record<Movement['type'], string> = {
  sale: 'sale',
  sale_reversal: 'reversal',
  restock: 'restock',
  waste: 'waste',
  adjustment: 'adjust',
}

function affectedText(row: StockRow): string {
  if (row.affected_products.length === 0) return '—'
  return row.affected_products
    .map((a) => `${a.name}${a.kind === 'addon' ? ' add-on' : ''}${a.sold_out && a.kind === 'product' ? ' SOLD OUT' : ''}`)
    .join(', ')
}

export default function StockPage() {
  const { api, outlet } = useSession()
  const outletId = outlet?.id ?? ''
  const [filter, setFilter] = useState<Filter>('all')
  const [q, setQ] = useState('')
  const stock = useLoad(() => api.get<StockResponse>(`/ops/outlets/${outletId}/stock`), outletId)
  const history = useLoad(
    () => api.get<{ items: Movement[] }>(`/ops/outlets/${outletId}/stock-movements?limit=20`),
    outletId,
  )
  const formRef = useRef<HTMLDivElement>(null)
  const [preselect, setPreselect] = useState<string>()

  if (!outlet) return <PageHeader title="Stok Bahan" />
  const items = (stock.data?.items ?? []).filter(
    (i) => (filter === 'all' || i.status === filter) && i.name.toLowerCase().includes(q.trim().toLowerCase()),
  )
  const counts = stock.data?.counts ?? { low: 0, out: 0 }
  const chip = (value: Filter, label: string) => (
    <button type="button" onClick={() => setFilter(value)} aria-pressed={filter === value}
      className={`rounded-full px-2.5 py-1 text-[12px] ${filter === value ? 'bg-primary-soft font-semibold text-primary' : 'text-text-muted hover:text-text'}`}>
      {label}
    </button>
  )

  return (
    <>
      <PageHeader
        title="Stok Bahan"
        actions={
          <Button className="hidden md:inline-flex" onClick={() => formRef.current?.scrollIntoView({ behavior: 'smooth' })}>
            + Catat pergerakan
          </Button>
        }
      />
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface px-4 py-2 md:px-6">
        {chip('all', 'Semua')}
        {chip('low', `Stok rendah (${counts.low})`)}
        {chip('out', `Habis (${counts.out})`)}
        <TextInput aria-label="Cari bahan" placeholder="⌕ Cari bahan" className="ml-auto h-8 w-full sm:w-48"
          value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="grid gap-4 p-4 md:p-6 lg:grid-cols-[1fr_340px]">
        <Card className="min-w-0">
          {stock.error ? <Alert>{errorMessage(stock.error)}</Alert> : null}
          {stock.loading && !stock.data ? <Loading /> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-[12px]">
                <thead className="text-[11px] tracking-wide text-text-muted uppercase">
                  <tr>
                    <th className="pb-2 font-medium">Bahan</th>
                    <th className="pb-2 font-medium">Stok</th>
                    <th className="pb-2 font-medium">Min</th>
                    <th className="pb-2 font-medium">Status</th>
                    <th className="pb-2 font-medium">Menu terdampak</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((i) => (
                    <tr key={i.stock_item_id} className="cursor-pointer border-t border-border hover:bg-page"
                      onClick={() => setPreselect(i.stock_item_id)}>
                      <td className="py-2.5">{i.name}</td>
                      <td className="py-2.5">{formatQty(i.on_hand, i.unit, i.display_unit)}</td>
                      <td className="py-2.5 text-text-muted">{formatQty(i.low_threshold, i.unit, i.display_unit)}</td>
                      <td className={`py-2.5 ${STATUS[i.status].className}`}>{STATUS[i.status].label}</td>
                      <td className="py-2.5 text-text-muted">{affectedText(i)}</td>
                    </tr>
                  ))}
                  {items.length === 0 && (
                    <tr><td colSpan={5} className="py-4 text-text-muted">Tidak ada bahan.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <div className="space-y-4" ref={formRef}>
          <MovementForm key={preselect ?? 'none'} items={stock.data?.items ?? []} preselect={preselect}
            onSaved={async () => { await Promise.all([stock.reload(), history.reload()]) }} />
          <Card title="Riwayat movement (append-only)">
            <ul className="space-y-1.5 text-[12px]">
              {(history.data?.items ?? []).map((m) => (
                <li key={m.id} className="flex gap-2">
                  <span className="w-10 shrink-0 text-text-muted">{formatTime(m.at, outlet.timezone)}</span>
                  <span className="w-14 shrink-0">{MOVE_LABEL[m.type]}</span>
                  <span className="min-w-0">
                    {formatDelta(m.quantity, m.unit, m.display_unit)} {m.stock_item.toLowerCase()}
                    {m.order_no ? ` · ${m.order_no}` : ''}{m.note ? ` · ${m.note}` : ''} · {m.actor}
                  </span>
                </li>
              ))}
              {history.data?.items.length === 0 && <li className="text-text-muted">Belum ada movement.</li>}
            </ul>
            <p className="mt-3 text-[11px] text-text-muted">
              Stok tidak bisa diedit langsung — hanya lewat movement. Movement tidak bisa diubah/dihapus.
            </p>
          </Card>
        </div>
      </div>
    </>
  )
}

function MovementForm({ items, preselect, onSaved }: {
  items: StockRow[]
  preselect?: string
  onSaved: () => Promise<void>
}) {
  const { api, outlet } = useSession()
  const [type, setType] = useState<MoveType>('restock')
  const [itemId, setItemId] = useState(preselect ?? '')
  const [amount, setAmount] = useState('')
  const [sign, setSign] = useState<1 | -1>(1)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ tone: 'success' | 'danger'; text: string }>()
  const item = items.find((i) => i.stock_item_id === itemId)
  const displayUnit = item?.display_unit ?? item?.unit ?? ''

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!item || !outlet) return
    const typed = Number(amount.replace(',', '.'))
    if (!Number.isFinite(typed) || typed <= 0) return setMessage({ tone: 'danger', text: 'Isi jumlah lebih dari 0.' })
    const base = Math.round(typed * displayFactor(item.display_unit) * 1000) / 1000
    setBusy(true)
    setMessage(undefined)
    try {
      await api.post(`/ops/outlets/${outlet.id}/stock-movements`, {
        type,
        stock_item_id: item.stock_item_id,
        quantity: String(type === 'adjustment' ? sign * base : base),
        note: note.trim() || null,
      })
      setAmount('')
      setNote('')
      setMessage({ tone: 'success', text: 'Movement disimpan.' })
      await onSaved()
    } catch (e) {
      setMessage({ tone: 'danger', text: errorMessage(e) })
    } finally {
      setBusy(false)
    }
  }

  const typeButton = (value: MoveType, label: string) => (
    <button type="button" aria-pressed={type === value} onClick={() => setType(value)}
      className={`h-8 flex-1 rounded-md border text-[12px] ${type === value ? 'border-primary bg-primary-soft font-semibold text-primary' : 'border-border'}`}>
      {label}
    </button>
  )

  return (
    <Card title="Catat pergerakan stok">
      <form onSubmit={submit} noValidate>
        <div className="mb-3">
          <div className="mb-1 text-[13px] font-semibold">Tipe</div>
          <div className="flex gap-2">
            {typeButton('restock', 'Restock')}
            {typeButton('waste', 'Waste')}
            {typeButton('adjustment', 'Adjustment')}
          </div>
        </div>
        <Field label="Bahan" htmlFor="move-item">
          <Select id="move-item" value={itemId} onChange={(e) => setItemId(e.target.value)}>
            <option value="">Pilih bahan</option>
            {items.map((i) => <option key={i.stock_item_id} value={i.stock_item_id}>{i.name}</option>)}
          </Select>
        </Field>
        <Field label="Jumlah & satuan" htmlFor="move-qty">
          <div className="flex items-center gap-2">
            {type === 'adjustment' ? (
              <Button variant="ghost" className="w-10" aria-label="Ganti tanda" onClick={() => setSign(sign === 1 ? -1 : 1)}>
                {sign === 1 ? '+' : '−'}
              </Button>
            ) : (
              <span className="w-4 text-center">{type === 'waste' ? '−' : '+'}</span>
            )}
            <TextInput id="move-qty" inputMode="decimal" className="w-28" value={amount}
              onChange={(e) => setAmount(e.target.value)} />
            <span>{displayUnit}</span>
          </div>
        </Field>
        <Field label="Catatan" htmlFor="move-note">
          <TextInput id="move-note" placeholder="Kiriman supplier pagi" value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        {message && <div className="mb-3"><Alert tone={message.tone}>{message.text}</Alert></div>}
        <Button type="submit" variant="action" className="w-full" disabled={busy || !item || !amount}>
          {busy ? 'Menyimpan…' : 'Simpan movement'}
        </Button>
      </form>
    </Card>
  )
}
