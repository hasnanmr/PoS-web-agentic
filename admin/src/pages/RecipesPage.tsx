// Wireframe O6 — Resep & Bahan (T-019, T-021, T-022, T-066).
// Tabs: Resep menu (GET/PUT /owner/products/{id}/recipe, add-on deltas via
// /owner/addon-options/{id}/recipe, GET /owner/products/{id}/availability),
// Daftar bahan (GET/POST/PATCH/DELETE /owner/stock-items; Edit nama + satuan dasar, Hapus = arsip), Threshold per outlet
// (PUT /owner/stock-items/{id}/thresholds).
import { useState } from 'react'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { displayFactor, formatDelta, plainQuantity } from '../lib/format'
import type { AddonOption, Availability, DisplayUnit, ProductDetail, ProductRow, RecipeLine, StockItem, Unit } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Dialog } from './po/ui'
import { Alert, Button, Card, Field, LinkButton, Loading, Select, TextInput } from '../ui/kit'

type Tab = 'recipe' | 'items' | 'thresholds'

export default function RecipesPage() {
  const [tab, setTab] = useState<Tab>('recipe')
  const { api } = useSession()
  const stockItems = useLoad(() => api.get<StockItem[]>('/owner/stock-items'), 'stock-items')
  const tabButton = (value: Tab, label: string) => (
    <button type="button" role="tab" aria-selected={tab === value} onClick={() => setTab(value)}
      className={`px-2 py-1 text-[13px] ${tab === value ? 'font-semibold text-primary' : 'text-primary/80 hover:text-primary'}`}>
      {tab === value ? `[ ${label} ]` : label}
    </button>
  )
  return (
    <>
      <PageHeader title="Resep & Bahan" />
      <div role="tablist" className="flex flex-wrap gap-2 border-b border-border bg-surface px-4 py-2 md:px-6">
        {tabButton('recipe', 'Resep menu')}
        {tabButton('items', 'Daftar bahan')}
        {tabButton('thresholds', 'Threshold per outlet')}
      </div>
      <div className="p-4 md:p-6">
        {stockItems.error ? <Alert>{errorMessage(stockItems.error)}</Alert> : null}
        {tab === 'recipe' && <RecipeTab stockItems={stockItems.data ?? []} />}
        {tab === 'items' && <ItemsTab items={stockItems.data} reload={stockItems.reload} />}
        {tab === 'thresholds' && <ThresholdTab items={stockItems.data} reload={stockItems.reload} />}
      </div>
    </>
  )
}

interface LineDraft { stock_item_id: string; amount: string }

function toDrafts(lines: RecipeLine[]): LineDraft[] {
  return lines.map((l) => ({ stock_item_id: l.stock_item_id, amount: plainQuantity(l.quantity) }))
}

function toBody(lines: LineDraft[]) {
  return lines.filter((l) => l.stock_item_id && l.amount !== '')
    .map((l) => ({ stock_item_id: l.stock_item_id, quantity: l.amount.replace(',', '.') }))
}

function RecipeTab({ stockItems }: { stockItems: StockItem[] }) {
  const { api } = useSession()
  const products = useLoad(() => api.get<ProductRow[]>('/owner/products'), 'recipe-products')
  const [selected, setSelected] = useState<string>()
  const current = selected ?? products.data?.[0]?.id
  return (
    <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
      <Card title="Pilih menu">
        {products.loading && !products.data ? <Loading /> : (
          <ul>
            {(products.data ?? []).map((p) => (
              <li key={p.id}>
                <button type="button" onClick={() => setSelected(p.id)}
                  className={`w-full rounded-md px-2 py-2 text-left text-[12px] ${current === p.id ? 'bg-primary-soft' : 'hover:bg-page'}`}>
                  {p.name} · {p.ingredient_count ? `${p.ingredient_count} bahan` : <span className="text-danger">belum ada resep</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      {current && (
        <RecipeEditor key={current} productId={current} stockItems={stockItems}
          onSaved={() => void products.reload()} />
      )}
    </div>
  )
}

function LinesEditor({ lines, onChange, stockItems, allowNegative }: {
  lines: LineDraft[]
  onChange: (lines: LineDraft[]) => void
  stockItems: StockItem[]
  allowNegative?: boolean
}) {
  const unitOf = (id: string) => stockItems.find((s) => s.id === id)?.unit ?? ''
  const update = (i: number, patch: Partial<LineDraft>) => onChange(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  return (
    <div>
      <div className="grid grid-cols-[1fr_90px_40px_24px] gap-2 pb-1 text-[11px] tracking-wide text-text-muted uppercase">
        <span>Bahan</span><span>Jumlah</span><span>Satuan</span><span />
      </div>
      {lines.map((l, i) => (
        <div key={i} className="grid grid-cols-[1fr_90px_40px_24px] items-center gap-2 py-1">
          <Select aria-label={`Bahan ${i + 1}`} className="h-8" value={l.stock_item_id} onChange={(e) => update(i, { stock_item_id: e.target.value })}>
            <option value="">Pilih bahan</option>
            {stockItems.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
          <TextInput aria-label={`Jumlah ${i + 1}`} inputMode="decimal" className="h-8" value={l.amount}
            placeholder={allowNegative ? '±' : ''}
            onChange={(e) => update(i, { amount: e.target.value.replace(allowNegative ? /[^\d.,-]/g : /[^\d.,]/g, '') })} />
          <span className="text-[12px]">{unitOf(l.stock_item_id)}</span>
          <button type="button" aria-label={`Hapus bahan ${i + 1}`} className="text-text-muted hover:text-danger"
            onClick={() => onChange(lines.filter((_, j) => j !== i))}>✕</button>
        </div>
      ))}
      <LinkButton className="mt-1" onClick={() => onChange([...lines, { stock_item_id: '', amount: '' }])}>+ Tambah bahan</LinkButton>
    </div>
  )
}

function RecipeEditor({ productId, stockItems, onSaved }: { productId: string; stockItems: StockItem[]; onSaved: () => void }) {
  const { api } = useSession()
  const product = useLoad(() => api.get<ProductDetail>(`/owner/products/${productId}`), productId)
  const recipe = useLoad(() => api.get<RecipeLine[]>(`/owner/products/${productId}/recipe`), productId)
  const availability = useLoad(() => api.get<Availability[]>(`/owner/products/${productId}/availability`), productId)
  const [lines, setLines] = useState<LineDraft[]>()
  const [shown, setShown] = useState<RecipeLine[]>()
  const [message, setMessage] = useState<{ tone: 'success' | 'danger'; text: string }>()
  const [editingOption, setEditingOption] = useState<string>()
  if (recipe.data !== shown) {
    setShown(recipe.data)
    setLines(recipe.data ? toDrafts(recipe.data) : undefined)
  }
  const loadError = product.error ?? recipe.error
  if (loadError) return <Alert>{errorMessage(loadError)}</Alert>
  if (!product.data || !lines) return <Loading />

  async function save() {
    try {
      await api.put(`/owner/products/${productId}/recipe`, toBody(lines ?? []))
      await Promise.all([recipe.reload(), availability.reload()])
      setMessage({ tone: 'success', text: 'Resep disimpan.' })
      onSaved()
    } catch (e) {
      setMessage({ tone: 'danger', text: errorMessage(e) })
    }
  }

  const options: { group: string; option: AddonOption }[] = product.data.addon_groups.flatMap((g) =>
    g.options.map((option) => ({ group: g.name, option })))

  return (
    <Card title={`Resep: ${product.data.name} (1 porsi)`}>
      <LinesEditor lines={lines} onChange={setLines} stockItems={stockItems} />

      <h3 className="mt-5 mb-2 text-[13px] font-semibold">Delta resep dari add-on</h3>
      {options.length === 0 && <p className="text-[12px] text-text-muted">Item ini tidak punya add-on.</p>}
      <ul className="space-y-1.5 text-[12px]">
        {options.map(({ group, option }) => (
          <li key={option.id}>
            {editingOption === option.id ? (
              <OptionDeltaEditor option={option} stockItems={stockItems}
                onDone={async () => { setEditingOption(undefined); await Promise.all([product.reload(), availability.reload()]) }} />
            ) : (
              <div className="flex gap-2">
                <span className="w-44 shrink-0">{group} › {option.name}</span>
                <span className="flex-1 text-text-muted">
                  {option.recipe.length ? option.recipe.map((r) => `${formatDelta(r.quantity, r.unit)} ${r.stock_item.toLowerCase()}`).join('   ·   ') : '—'}
                </span>
                <button type="button" aria-label={`Ubah delta ${option.name}`} className="text-text-muted hover:text-text"
                  onClick={() => setEditingOption(option.id)}>✎</button>
              </div>
            )}
          </li>
        ))}
      </ul>

      <div className="mt-5 rounded-md bg-page p-3 text-[12px]">
        <p className="font-semibold">Simulasi ketersediaan per outlet (1 porsi Regular)</p>
        {availability.error ? <div className="mt-1"><Alert>{errorMessage(availability.error)}</Alert></div> : null}
        <p className="mt-1">
          {(availability.data ?? []).map((a) => (
            <span key={a.outlet_id} className={a.sold_out ? 'text-danger' : ''}>
              {a.outlet_name}: {a.sold_out ? `SOLD OUT${a.limiting_stock_item ? ` (${a.limiting_stock_item.toLowerCase()} habis)` : ''}` : `tersedia ${a.portions_available} porsi`}
              {' · '}
            </span>
          ))}
        </p>
        <p className="mt-1 text-text-muted">Item sold out jika salah satu bahan tidak cukup untuk 1 porsi; add-on unavailable jika bahannya kurang.</p>
      </div>
      <p className="mt-3 text-[11px] text-text-muted">Setiap menu wajib punya min. 1 bahan (produk as-is pun dicatat sebagai bahan).</p>
      {message && <div className="mt-3"><Alert tone={message.tone}>{message.text}</Alert></div>}
      <div className="mt-3 flex justify-end">
        <Button variant="action" onClick={save} disabled={toBody(lines).length === 0}>Simpan resep</Button>
      </div>
    </Card>
  )
}

function OptionDeltaEditor({ option, stockItems, onDone }: { option: AddonOption; stockItems: StockItem[]; onDone: () => Promise<void> }) {
  const { api } = useSession()
  const [lines, setLines] = useState<LineDraft[]>(toDrafts(option.recipe))
  const [error, setError] = useState<string>()
  return (
    <div className="rounded-md border border-primary p-2">
      <p className="mb-1 font-semibold">{option.name}: delta per porsi (negatif = mengurangi)</p>
      <LinesEditor lines={lines} onChange={setLines} stockItems={stockItems} allowNegative />
      {error && <div className="mt-2"><Alert>{error}</Alert></div>}
      <div className="mt-2 flex gap-3">
        <Button className="h-8" onClick={async () => {
          try {
            await api.put(`/owner/addon-options/${option.id}/recipe`, toBody(lines))
            await onDone()
          } catch (e) {
            setError(errorMessage(e))
          }
        }}>Simpan delta</Button>
        <LinkButton onClick={() => void onDone()}>Batal</LinkButton>
      </div>
    </div>
  )
}

const DISPLAY_OPTIONS: Record<Unit, DisplayUnit[]> = { g: ['g', 'kg'], ml: ['ml', 'L'], pcs: ['pcs'] }

function ItemsTab({ items, reload }: { items?: StockItem[]; reload: () => Promise<void> }) {
  const { api } = useSession()
  const [name, setName] = useState('')
  const [unit, setUnit] = useState<Unit>('g')
  const [editing, setEditing] = useState<StockItem>()
  const [deleting, setDeleting] = useState<StockItem>()
  const [message, setMessage] = useState<{ tone: 'success' | 'danger'; text: string }>()
  async function run(action: () => Promise<unknown>, text: string) {
    try {
      await action()
      setMessage({ tone: 'success', text })
      await reload()
    } catch (e) {
      setMessage({ tone: 'danger', text: errorMessage(e) })
    }
  }
  if (!items) return <Loading />
  return (
    <Card title="Daftar bahan">
      <table className="w-full text-left text-[12px]">
        <thead className="text-[11px] tracking-wide text-text-muted uppercase">
          <tr><th className="pb-2 font-medium">Bahan</th><th className="pb-2 font-medium">Satuan dasar</th><th className="pb-2 font-medium">Tampilan</th><th className="pb-2" /></tr>
        </thead>
        <tbody>
          {items.map((i) => (
            <tr key={i.id} className="border-t border-border">
              <td className="py-2">{i.name}</td>
              <td className="py-2">{i.unit}</td>
              <td className="py-2">
                <Select aria-label={`Tampilan ${i.name}`} className="h-8 w-auto" value={i.display_unit ?? i.unit}
                  onChange={(e) => void run(() => api.patch(`/owner/stock-items/${i.id}`, { display_unit: e.target.value }), 'Satuan tampilan disimpan.')}>
                  {DISPLAY_OPTIONS[i.unit].map((u) => <option key={u} value={u}>{u}</option>)}
                </Select>
              </td>
              <td className="py-2 text-right whitespace-nowrap">
                <LinkButton aria-label={`Edit ${i.name}`} onClick={() => setEditing(i)}>Edit</LinkButton>
                <LinkButton aria-label={`Hapus ${i.name}`} className="ml-3 text-danger" onClick={() => setDeleting(i)}>Hapus</LinkButton>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3"
        onSubmit={(e) => {
          e.preventDefault()
          void run(async () => {
            await api.post('/owner/stock-items', { name: name.trim(), unit })
            setName('')
          }, 'Bahan ditambahkan.')
        }}>
        <TextInput aria-label="Nama bahan baru" placeholder="Nama bahan" className="h-8 max-w-[220px]" value={name} onChange={(e) => setName(e.target.value)} />
        <Select aria-label="Satuan dasar" className="h-8 w-auto" value={unit} onChange={(e) => setUnit(e.target.value as Unit)}>
          <option value="g">g</option><option value="ml">ml</option><option value="pcs">pcs</option>
        </Select>
        <Button type="submit" className="h-8" disabled={!name.trim()}>+ Tambah bahan</Button>
      </form>
      {message && <div className="mt-3"><Alert tone={message.tone}>{message.text}</Alert></div>}
      {editing && (
        <EditItemDialog item={editing} onClose={() => setEditing(undefined)}
          onSave={async (patch) => {
            await api.patch(`/owner/stock-items/${editing.id}`, patch)
            setEditing(undefined)
            setMessage({ tone: 'success', text: 'Bahan diperbarui.' })
            await reload()
          }} />
      )}
      {deleting && (
        <Dialog label="Hapus bahan" onClose={() => setDeleting(undefined)}>
          <h3 className="text-[16px] font-semibold">Hapus &quot;{deleting.name}&quot;?</h3>
          <p className="mt-2 text-[12px] text-text-muted">
            Bahan hilang dari daftar, stok, dan pilihan resep/PO. Riwayat stok dan PO lama tetap tersimpan. Bahan yang masih dipakai di resep tidak bisa dihapus.
          </p>
          <div className="mt-4 flex gap-3">
            <Button variant="danger" className="h-8" onClick={() => {
              const target = deleting
              setDeleting(undefined)
              void run(() => api.del(`/owner/stock-items/${target.id}`), `${target.name} dihapus.`)
            }}>Ya, hapus</Button>
            <LinkButton onClick={() => setDeleting(undefined)}>Batal</LinkButton>
          </div>
        </Dialog>
      )}
    </Card>
  )
}

function EditItemDialog({ item, onClose, onSave }: {
  item: StockItem
  onClose: () => void
  onSave: (patch: { name?: string; unit?: Unit }) => Promise<void>
}) {
  const [name, setName] = useState(item.name)
  const [unit, setUnit] = useState<Unit>(item.unit)
  const [error, setError] = useState<string>()
  const changed = name.trim() !== item.name || unit !== item.unit
  async function submit() {
    const patch: { name?: string; unit?: Unit } = {}
    if (name.trim() !== item.name) patch.name = name.trim()
    if (unit !== item.unit) patch.unit = unit
    try {
      await onSave(patch)
    } catch (e) {
      setError(errorMessage(e))
    }
  }
  return (
    <Dialog label="Edit bahan" onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); void submit() }}>
        <h3 className="text-[16px] font-semibold">Edit bahan</h3>
        <div className="mt-3 flex flex-col gap-3">
          <Field label="Nama bahan" htmlFor="edit-item-name">
            <TextInput id="edit-item-name" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Satuan dasar" htmlFor="edit-item-unit"
            hint="Satuan dasar hanya bisa diubah jika bahan belum punya stok, resep, atau PO.">
            <Select id="edit-item-unit" value={unit} onChange={(e) => setUnit(e.target.value as Unit)}>
              <option value="g">g</option><option value="ml">ml</option><option value="pcs">pcs</option>
            </Select>
          </Field>
        </div>
        {error && <div className="mt-3"><Alert>{error}</Alert></div>}
        <div className="mt-4 flex gap-3">
          <Button type="submit" className="h-8" disabled={!name.trim() || !changed}>Simpan</Button>
          <LinkButton type="button" onClick={onClose}>Batal</LinkButton>
        </div>
      </form>
    </Dialog>
  )
}

function ThresholdTab({ items, reload }: { items?: StockItem[]; reload: () => Promise<void> }) {
  const { api, me, outlet } = useSession()
  const [outletId, setOutletId] = useState(outlet?.id ?? '')
  const [values, setValues] = useState<Record<string, string>>({})
  const [message, setMessage] = useState<{ tone: 'success' | 'danger'; text: string }>()
  if (!items) return <Loading />
  const current = (i: StockItem) => {
    const t = i.thresholds.find((x) => x.outlet_id === outletId)?.low_threshold ?? '0'
    return plainQuantity(String(Number(t) / displayFactor(i.display_unit)))
  }
  async function save() {
    try {
      for (const [id, value] of Object.entries(values)) {
        const item = items!.find((i) => i.id === id)!
        const base = Number(value.replace(',', '.')) * displayFactor(item.display_unit)
        await api.put(`/owner/stock-items/${id}/thresholds`, [{ outlet_id: outletId, low_threshold: String(Math.round(base * 1000) / 1000) }])
      }
      setValues({})
      setMessage({ tone: 'success', text: 'Threshold disimpan.' })
      await reload()
    } catch (e) {
      setMessage({ tone: 'danger', text: errorMessage(e) })
    }
  }
  return (
    <Card title="Threshold per outlet" actions={
      <Select aria-label="Outlet threshold" className="h-8 w-auto" value={outletId} onChange={(e) => { setOutletId(e.target.value); setValues({}) }}>
        {me.outlets.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
      </Select>
    }>
      <table className="w-full text-left text-[12px]">
        <thead className="text-[11px] tracking-wide text-text-muted uppercase">
          <tr><th className="pb-2 font-medium">Bahan</th><th className="pb-2 font-medium">Stok rendah jika ≤</th></tr>
        </thead>
        <tbody>
          {items.map((i) => (
            <tr key={i.id} className="border-t border-border">
              <td className="py-2">{i.name}</td>
              <td className="py-2">
                <span className="flex items-center gap-2">
                  <TextInput aria-label={`Threshold ${i.name}`} inputMode="decimal" className="h-8 w-24"
                    value={values[i.id] ?? current(i)}
                    onChange={(e) => setValues({ ...values, [i.id]: e.target.value.replace(/[^\d.,]/g, '') })} />
                  {i.display_unit ?? i.unit}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {message && <div className="mt-3"><Alert tone={message.tone}>{message.text}</Alert></div>}
      <div className="mt-3 flex justify-end">
        <Button variant="action" onClick={save} disabled={Object.keys(values).length === 0}>Simpan threshold</Button>
      </div>
    </Card>
  )
}
