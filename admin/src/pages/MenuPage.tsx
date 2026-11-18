// Wireframe O5 — Menu, Add-on & Harga Outlet (T-016, T-017, T-018, T-066).
// Endpoints: GET/POST /owner/products, GET/PATCH/DELETE /owner/products/{id},
// PUT /owner/products/{id}/prices, add-on groups under /owner/products/{id}/addon-groups.
// Not yet here: photo upload (Supabase Storage) and WhatsApp catalog sync (T-051).
import { useState } from 'react'
import { Link } from 'react-router'
import { useSession } from '../app/session'
import { ROUTES } from '../app/nav'
import { errorMessage } from '../lib/api'
import { formatDelta, formatRupiah } from '../lib/format'
import type { AddonGroup, ProductDetail, ProductRow } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Card, FieldRow, LinkButton, Loading, Select, TextInput } from '../ui/kit'

const STATUS_LABEL: Record<ProductRow['status'], string> = { active: 'Aktif', sold_out: 'Sold out', inactive: 'Nonaktif' }

export default function MenuPage() {
  const { api, me, outlet } = useSession()
  // Prices follow the sidebar outlet; the page selector overrides it until the sidebar outlet changes.
  const [override, setOverride] = useState<{ base: string; id: string }>()
  const priceOutlet = override && override.base === (outlet?.id ?? '') ? override.id : (outlet?.id ?? '')
  const [q, setQ] = useState('')
  const [category, setCategory] = useState('')
  const [status, setStatus] = useState('all')
  const [selected, setSelected] = useState<string | 'new'>()
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string }>()
  const products = useLoad(
    () => api.get<ProductRow[]>(priceOutlet ? `/owner/products?price_outlet_id=${priceOutlet}` : '/owner/products'),
    priceOutlet,
  )
  const all = products.data ?? []
  const categories = [...new Set(all.map((p) => p.category).filter(Boolean))] as string[]
  const rows = all.filter((p) =>
    p.name.toLowerCase().includes(q.trim().toLowerCase()) &&
    (!category || p.category === category) && (status === 'all' || p.status === status))
  const current = selected ?? rows[0]?.id

  return (
    <>
      <PageHeader
        title="Menu & Add-on"
        actions={<Button onClick={() => setSelected('new')}>+ Item menu</Button>}
      />
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface px-4 py-2 text-[13px] md:px-6">
        <span className="text-primary">Harga ditampilkan untuk:</span>
        <Select aria-label="Harga ditampilkan untuk outlet" className="h-8 w-auto" value={priceOutlet}
          onChange={(e) => setOverride({ base: outlet?.id ?? '', id: e.target.value })}>
          {me.outlets.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </Select>
      </div>
      <div className="grid gap-4 p-4 md:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <Card className="min-w-0">
          <div className="mb-3 flex flex-wrap gap-2">
            <TextInput aria-label="Cari menu" placeholder="⌕ Cari menu" className="h-8 flex-1" value={q}
              onChange={(e) => setQ(e.target.value)} />
            <Select aria-label="Kategori" className="h-8 w-auto" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">Kategori: Semua</option>
              {categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </Select>
            <Select aria-label="Status" className="h-8 w-auto" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="all">Status: Semua</option>
              <option value="active">Aktif</option>
              <option value="sold_out">Sold out</option>
              <option value="inactive">Nonaktif</option>
            </Select>
          </div>
          {products.loading && !products.data ? <Loading /> : (
            <ul>
              {rows.map((p) => (
                <li key={p.id}>
                  <button type="button" onClick={() => setSelected(p.id)}
                    className={`flex w-full items-center gap-3 rounded-md px-2 py-2 text-left ${current === p.id ? 'bg-primary-soft' : 'hover:bg-page'}`}>
                    <span aria-hidden="true" className="h-10 w-10 shrink-0 rounded bg-page" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-semibold">
                        {p.name}{p.is_owner_pick ? '  ★' : ''}{p.is_sample ? <span className="font-normal text-text-muted">  · sample</span> : null}
                      </span>
                      <span className="block text-[11px] text-text-muted">
                        {p.category ?? 'Tanpa kategori'} · {p.addon_group_count ? `${p.addon_group_count} grup add-on` : '—'}
                      </span>
                    </span>
                    <span className={`shrink-0 text-[12px] ${p.status === 'sold_out' ? 'text-danger' : p.status === 'inactive' ? 'text-text-muted' : ''}`}>
                      {p.price == null ? 'Belum ada harga' : formatRupiah(p.price)} · {STATUS_LABEL[p.status]}
                    </span>
                  </button>
                </li>
              ))}
              {rows.length === 0 && <li className="p-2 text-text-muted">Tidak ada menu.</li>}
            </ul>
          )}
        </Card>
        <div className="min-w-0 space-y-3">
          {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}
          {current === 'new' ? (
            <NewProduct onCreated={async (id) => {
              setNotice({ tone: 'success', text: 'Item menu dibuat. Lengkapi harga, add-on, dan resep.' })
              await products.reload()
              setSelected(id)
            }} onCancel={() => setSelected(undefined)} />
          ) : current ? (
            <ProductEditor key={current} productId={current} priceOutlet={priceOutlet}
              onChanged={async (text) => { setNotice({ tone: 'success', text }); await products.reload() }}
              onDeleted={async (text) => { setNotice({ tone: 'success', text }); setSelected(undefined); await products.reload() }}
              onError={(text) => setNotice({ tone: 'danger', text })} />
          ) : null}
        </div>
      </div>
    </>
  )
}

function NewProduct({ onCreated, onCancel }: { onCreated: (id: string) => Promise<void>; onCancel: () => void }) {
  const { api } = useSession()
  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [error, setError] = useState<string>()
  return (
    <Card title="Item menu baru">
      <FieldRow label="Nama *" htmlFor="new-name">
        <TextInput id="new-name" value={name} onChange={(e) => setName(e.target.value)} />
      </FieldRow>
      <FieldRow label="Kategori" htmlFor="new-category">
        <TextInput id="new-category" placeholder="Kopi" value={category} onChange={(e) => setCategory(e.target.value)} />
      </FieldRow>
      {error && <div className="my-2"><Alert>{error}</Alert></div>}
      <div className="mt-3 flex items-center gap-3">
        <Button variant="action" disabled={!name.trim()} onClick={async () => {
          try {
            const created = await api.post<ProductDetail>('/owner/products', { name: name.trim(), category: category.trim() || null })
            await onCreated(created.id)
          } catch (e) {
            setError(errorMessage(e))
          }
        }}>Buat item</Button>
        <LinkButton onClick={onCancel}>Batal</LinkButton>
      </div>
    </Card>
  )
}

interface Draft {
  name: string
  category: string
  description: string
  tags: string
  is_owner_pick: boolean
  is_active: boolean
  prices: Record<string, string>
}

function toDraft(p: ProductDetail): Draft {
  return {
    name: p.name,
    category: p.category ?? '',
    description: p.description ?? '',
    tags: p.tags.join(', '),
    is_owner_pick: p.is_owner_pick,
    is_active: p.is_active,
    prices: Object.fromEntries(p.prices.map((x) => [x.outlet_id, x.price == null ? '' : String(x.price)])),
  }
}

function ProductEditor({ productId, priceOutlet, onChanged, onDeleted, onError }: {
  productId: string
  priceOutlet: string
  onChanged: (text: string) => Promise<void>
  onDeleted: (text: string) => Promise<void>
  onError: (text: string) => void
}) {
  const { api } = useSession()
  const detail = useLoad(() => api.get<ProductDetail>(`/owner/products/${productId}`), productId)
  const [draft, setDraft] = useState<Draft>()
  const [shown, setShown] = useState<ProductDetail>()
  const [busy, setBusy] = useState(false)
  const [editingGroup, setEditingGroup] = useState<AddonGroup | 'new'>()
  const [confirmDelete, setConfirmDelete] = useState(false)
  if (detail.data !== shown) {
    setShown(detail.data)
    setDraft(detail.data ? toDraft(detail.data) : undefined)
  }
  if (!detail.data || !draft) return detail.error ? <Alert>{errorMessage(detail.error)}</Alert> : <Loading />
  const p = detail.data
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft({ ...draft, [key]: value })

  async function save() {
    if (!draft) return
    setBusy(true)
    try {
      await api.patch(`/owner/products/${productId}`, {
        name: draft.name.trim(),
        category: draft.category.trim() || null,
        description: draft.description.trim() || null,
        is_owner_pick: draft.is_owner_pick,
        is_active: draft.is_active,
        tags: draft.tags.split(',').map((t) => t.trim()).filter(Boolean),
      })
      await api.put(`/owner/products/${productId}/prices`, p.prices.map((x) => ({
        outlet_id: x.outlet_id,
        price: draft.prices[x.outlet_id] === '' ? null : Number(draft.prices[x.outlet_id].replace(/\D/g, '')),
      })))
      await detail.reload()
      await onChanged('Perubahan menu disimpan. Sync katalog WhatsApp belum aktif untuk demo.')
    } catch (e) {
      onError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const outletName = (id: string) => p.prices.find((x) => x.outlet_id === id)?.outlet_name.split(/\s[–-]\s/).pop() ?? ''

  return (
    <Card title={`Edit: ${p.name}`}>
      <div className="flex gap-4">
        <div className="hidden h-28 w-28 shrink-0 items-center justify-center rounded-md bg-page text-[11px] text-text-muted sm:flex"
          title="Upload foto menyusul (Supabase Storage)">
          Foto * ⇪
        </div>
        <div className="min-w-0 flex-1">
          <FieldRow label="Nama *" htmlFor="p-name">
            <TextInput id="p-name" value={draft.name} onChange={(e) => set('name', e.target.value)} />
          </FieldRow>
          <FieldRow label="Kategori" htmlFor="p-category">
            <div className="flex items-center gap-3">
              <TextInput id="p-category" className="max-w-[160px]" value={draft.category} onChange={(e) => set('category', e.target.value)} />
              <label className="flex items-center gap-1.5 text-[12px]">
                <input type="checkbox" checked={draft.is_owner_pick} onChange={(e) => set('is_owner_pick', e.target.checked)} />
                ★ Owner&apos;s pick
              </label>
            </div>
          </FieldRow>
          <FieldRow label="Tag" htmlFor="p-tags" hint="Pisahkan dengan koma, mis. coffee, sweet">
            <TextInput id="p-tags" value={draft.tags} onChange={(e) => set('tags', e.target.value)} />
          </FieldRow>
          <FieldRow label="Deskripsi" htmlFor="p-desc">
            <TextInput id="p-desc" value={draft.description} onChange={(e) => set('description', e.target.value)} />
          </FieldRow>
          <FieldRow label="Status">
            <label className="flex items-center gap-2">
              <input type="checkbox" role="switch" checked={draft.is_active} onChange={(e) => set('is_active', e.target.checked)} />
              {draft.is_active ? 'Aktif' : 'Nonaktif'}
            </label>
          </FieldRow>
        </div>
      </div>

      <h3 className="mt-4 mb-2 text-[13px] font-semibold">Harga per outlet</h3>
      <div className="grid gap-2 sm:grid-cols-2">
        {p.prices.map((x) => (
          <label key={x.outlet_id} className="flex items-center gap-2 text-[12px]">
            <span className="w-32 shrink-0 truncate">{x.outlet_name}</span>
            <span className="text-text-muted">Rp</span>
            <TextInput aria-label={`Harga ${x.outlet_name}`} inputMode="numeric" className="h-8 w-28"
              value={draft.prices[x.outlet_id] ?? ''}
              onChange={(e) => set('prices', { ...draft.prices, [x.outlet_id]: e.target.value.replace(/\D/g, '') })} />
          </label>
        ))}
      </div>

      <h3 className="mt-4 mb-2 text-[13px] font-semibold">Grup add-on</h3>
      <div className="space-y-2">
        {p.addon_groups.map((g) => editingGroup !== 'new' && editingGroup?.id === g.id ? (
          <GroupEditor key={g.id} group={g} productId={productId} priceOutlet={priceOutlet}
            onDone={async (text) => { setEditingGroup(undefined); await detail.reload(); if (text) await onChanged(text) }}
            onError={onError} />
        ) : (
          <div key={g.id} className="rounded-md border border-border p-2.5 text-[12px]">
            <div className="flex items-center justify-between">
              <span>
                <span className="font-semibold">{g.name}</span> · {g.is_required ? 'REQUIRED' : 'optional'} · {g.selection === 'single' ? 'pilih 1' : 'pilih banyak'}
              </span>
              <button type="button" aria-label={`Ubah grup ${g.name}`} className="text-text-muted hover:text-text"
                onClick={() => setEditingGroup(g)}>✎</button>
            </div>
            <ul className="mt-1 space-y-0.5">
              {g.options.map((o) => {
                const price = o.prices.find((x) => x.outlet_id === priceOutlet)?.price
                return (
                  <li key={o.id}>
                    • {o.name}  {price == null ? '(belum ada harga)' : `+${formatRupiah(price)} (${outletName(priceOutlet)})`}
                    {o.recipe.length > 0 && (
                      <span className="text-text-muted"> · resep: {o.recipe.map((r) => `${formatDelta(r.quantity, r.unit)} ${r.stock_item.toLowerCase()}`).join(', ')}</span>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
        {editingGroup === 'new' ? (
          <GroupEditor productId={productId} priceOutlet={priceOutlet}
            onDone={async (text) => { setEditingGroup(undefined); await detail.reload(); if (text) await onChanged(text) }}
            onError={onError} />
        ) : (
          <p className="text-[12px]">
            <LinkButton onClick={() => setEditingGroup('new')}>+ Tambah grup add-on</LinkButton>
            <span className="text-text-muted">   (maks. 10 opsi per grup; required/optional; single/multi)</span>
          </p>
        )}
        <p className="text-[12px]">
          <Link to={ROUTES.recipes.path} className="text-primary hover:underline">Resep item → buka Resep &amp; Bahan</Link>
        </p>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
        {confirmDelete ? (
          <span className="flex items-center gap-3 text-[12px]">
            <span>Hapus &quot;{p.name}&quot;?</span>
            <LinkButton className="text-danger" onClick={async () => {
              try {
                const res = await api.del<{ result: string }>(`/owner/products/${productId}`)
                await onDeleted(res.result === 'deleted' ? `${p.name} dihapus.` : `${p.name} sudah pernah dipesan, jadi dinonaktifkan.`)
              } catch (e) {
                setConfirmDelete(false)
                onError(errorMessage(e))
              }
            }}>Ya, hapus</LinkButton>
            <LinkButton onClick={() => setConfirmDelete(false)}>Batal</LinkButton>
          </span>
        ) : (
          <LinkButton className="text-danger" onClick={() => setConfirmDelete(true)}>✕ Hapus item</LinkButton>
        )}
        <Button variant="action" onClick={save} disabled={busy || !draft.name.trim()}>
          {busy ? 'Menyimpan…' : 'Simpan & sync katalog'}
        </Button>
      </div>
    </Card>
  )
}

interface OptionDraft { id: string | null; name: string; price: string }

function GroupEditor({ group, productId, priceOutlet, onDone, onError }: {
  group?: AddonGroup
  productId: string
  priceOutlet: string
  onDone: (text?: string) => Promise<void>
  onError: (text: string) => void
}) {
  const { api } = useSession()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [name, setName] = useState(group?.name ?? '')
  const [selection, setSelection] = useState<'single' | 'multiple'>(group?.selection ?? 'single')
  const [required, setRequired] = useState(group?.is_required ?? false)
  const [options, setOptions] = useState<OptionDraft[]>(
    group?.options.map((o) => ({ id: o.id, name: o.name, price: String(o.prices.find((x) => x.outlet_id === priceOutlet)?.price ?? '') }))
      ?? [{ id: null, name: '', price: '0' }],
  )
  const update = (i: number, patch: Partial<OptionDraft>) => setOptions(options.map((o, j) => (j === i ? { ...o, ...patch } : o)))

  async function save() {
    const body = {
      name: name.trim(),
      selection,
      is_required: required,
      options: options.filter((o) => o.name.trim()).map((o) => ({
        id: o.id,
        name: o.name.trim(),
        // An empty price stays unpriced at this outlet (null), it is not Rp 0.
        prices: priceOutlet ? [{ outlet_id: priceOutlet, price: o.price === '' ? null : Number(o.price) }] : [],
      })),
    }
    try {
      if (group) await api.patch(`/owner/addon-groups/${group.id}`, body)
      else await api.post(`/owner/products/${productId}/addon-groups`, body)
      await onDone(`Grup add-on "${body.name}" disimpan.`)
    } catch (e) {
      onError(errorMessage(e))
    }
  }

  return (
    <div className="space-y-2 rounded-md border border-primary p-2.5 text-[12px]">
      <div className="flex flex-wrap items-center gap-2">
        <TextInput aria-label="Nama grup" placeholder="Ukuran" className="h-8 max-w-[180px]" value={name} onChange={(e) => setName(e.target.value)} />
        <label className="flex items-center gap-1"><input type="checkbox" checked={required} onChange={(e) => setRequired(e.target.checked)} /> Required</label>
        <Select aria-label="Pilihan" className="h-8 w-auto" value={selection} onChange={(e) => setSelection(e.target.value as 'single' | 'multiple')}>
          <option value="single">pilih 1</option>
          <option value="multiple">pilih banyak</option>
        </Select>
      </div>
      {options.map((o, i) => (
        <div key={o.id ?? `new-${i}`} className="flex items-center gap-2">
          <TextInput aria-label={`Opsi ${i + 1}`} placeholder="Regular" className="h-8 flex-1" value={o.name}
            onChange={(e) => update(i, { name: e.target.value })} />
          <span className="text-text-muted">+Rp</span>
          <TextInput aria-label={`Harga opsi ${i + 1}`} inputMode="numeric" placeholder="—" className="h-8 w-20" value={o.price}
            onChange={(e) => update(i, { price: e.target.value.replace(/\D/g, '') })} />
          <button type="button" aria-label={`Hapus opsi ${i + 1}`} className="text-text-muted hover:text-danger"
            onClick={() => setOptions(options.filter((_, j) => j !== i))}>✕</button>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-3">
        <LinkButton disabled={options.length >= 10} onClick={() => setOptions([...options, { id: null, name: '', price: '0' }])}>+ Opsi</LinkButton>
        <span className="text-text-muted">Harga untuk outlet yang dipilih di atas.</span>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button className="h-8" disabled={!name.trim() || !options.some((o) => o.name.trim())} onClick={save}>Simpan grup</Button>
        <LinkButton onClick={() => void onDone()}>Batal</LinkButton>
        {group && (confirmDelete ? (
          <span className="ml-auto flex items-center gap-3">
            <span>Hapus grup ini?</span>
            <LinkButton className="text-danger" onClick={async () => {
              try {
                await api.del(`/owner/addon-groups/${group.id}`)
                await onDone(`Grup add-on "${group.name}" dihapus.`)
              } catch (e) {
                setConfirmDelete(false)
                onError(errorMessage(e))
              }
            }}>Ya, hapus</LinkButton>
            <LinkButton onClick={() => setConfirmDelete(false)}>Batal</LinkButton>
          </span>
        ) : (
          <LinkButton className="ml-auto text-danger" onClick={() => setConfirmDelete(true)}>Hapus grup</LinkButton>
        ))}
      </div>
    </div>
  )
}
