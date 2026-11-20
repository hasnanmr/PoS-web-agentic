// Wireframe O7 — Rekomendasi (owner's picks & tags, preview of the WhatsApp Rekomendasi menu)
// Endpoints: GET/PUT /owner/owner-picks, GET /owner/tags, GET /owner/products (picker),
// GET /owner/outlets/{id}/recommendation-preview (same function as the WhatsApp flow, W9).
// Behaviour notes (canvas): picks apply to every outlet; drag ≡ to reorder; the preview skips
// sold-out items, removes duplicates and shows at most 30 items. Tags are edited on the menu (O5).
import { useState, type DragEvent, type KeyboardEvent } from 'react'
import { Link } from 'react-router'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import type { OwnerPick, PreviewItem, ProductRow, RecommendationPreview } from '../lib/types'
import { useKept, useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Card, Loading, Select } from '../ui/kit'

const SKIPPED: Record<NonNullable<PreviewItem['skipped_reason']>, string> = {
  sold_out: 'dilewati: sold out',
  unavailable: 'dilewati: tidak tersedia di outlet ini',
  duplicate: 'duplikat, dihapus',
}

function move<T>(list: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return list
  const next = list.slice()
  next.splice(to, 0, ...next.splice(from, 1))
  return next
}

export default function RecommendationsPage() {
  const { api, outlet } = useSession()
  const outletId = outlet?.id ?? ''
  const picksLoad = useLoad(() => api.get<OwnerPick[]>('/owner/owner-picks'), 'picks')
  const tags = useLoad(() => api.get<string[]>('/owner/tags'), 'tags')
  const products = useLoad(() => api.get<ProductRow[]>('/owner/products'), 'products')
  const preview = useLoad(
    () => api.get<RecommendationPreview>(`/owner/outlets/${outletId}/recommendation-preview`),
    outletId,
  )
  const [picks, setPicks] = useState<OwnerPick[]>()
  const [dragFrom, setDragFrom] = useState<number>()
  const [adding, setAdding] = useState(false)
  const [candidate, setCandidate] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string>()
  const shown = picks ?? picksLoad.data

  // Every change saves the whole ordered list; the list on screen is the optimistic copy and
  // goes back to the server's when the save fails.
  async function save(next: OwnerPick[]) {
    setPicks(next)
    setError(undefined)
    setSaving(true)
    try {
      await api.put('/owner/owner-picks', { product_ids: next.map((p) => p.product_id) })
      await Promise.all([picksLoad.reload(), preview.reload(), products.reload()])
    } catch (e) {
      setError(errorMessage(e))
      await picksLoad.reload()
    } finally {
      setPicks(undefined)
      setSaving(false)
    }
  }

  function onDrop(e: DragEvent, to: number) {
    e.preventDefault()
    if (dragFrom !== undefined && shown) void save(move(shown, dragFrom, to))
    setDragFrom(undefined)
  }

  function onHandleKey(e: KeyboardEvent, index: number) {
    if (!shown || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) return
    e.preventDefault()
    void save(move(shown, index, index + (e.key === 'ArrowUp' ? -1 : 1)))
  }

  async function add() {
    const product = products.data?.find((p) => p.id === candidate)
    if (!product || !shown) return
    const pick: OwnerPick = {
      product_id: product.id, name: product.name, category: product.category, is_active: true, tags: [],
    }
    setAdding(false)
    setCandidate('')
    await save([...shown, pick])
  }

  const pickedIds = new Set((shown ?? []).map((p) => p.product_id))
  const options = (products.data ?? []).filter((p) => !pickedIds.has(p.id) && p.status !== 'inactive')
  const view = useKept(preview.data)

  return (
    <>
      <PageHeader title="Rekomendasi" />
      <div className="grid gap-4 p-4 md:p-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <Card title="★ Owner's picks (berlaku semua outlet)">
          {error && <div className="mb-3"><Alert>{error}</Alert></div>}
          {!shown ? <Loading /> : (
            <>
              {shown.length === 0 && (
                <p className="mb-3 text-[12px] text-text-muted">Belum ada owner's pick.</p>
              )}
              <ol className="divide-y divide-border">
                {shown.map((p, i) => (
                  <li
                    key={p.product_id}
                    draggable
                    onDragStart={() => setDragFrom(i)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => onDrop(e, i)}
                    onDragEnd={() => setDragFrom(undefined)}
                    className={`flex items-center gap-2 py-2 text-[13px] ${dragFrom === i ? 'opacity-50' : ''}`}
                  >
                    <button
                      type="button"
                      aria-label={`Atur urutan ${p.name}`}
                      title="Seret untuk mengatur urutan (atau tombol panah atas/bawah)"
                      onKeyDown={(e) => onHandleKey(e, i)}
                      disabled={saving}
                      className="cursor-grab px-1 text-text-muted hover:text-text"
                    >
                      ≡
                    </button>
                    <span className="w-5 text-text-muted">{i + 1}.</span>
                    <span className="min-w-0 flex-1 truncate font-medium text-text">
                      {p.name}
                      {!p.is_active && <span className="ml-2 text-[11px] font-normal text-warning">nonaktif</span>}
                    </span>
                    <span className="flex flex-wrap justify-end gap-1">
                      {p.tags.map((t) => (
                        <span key={t} className="rounded bg-primary-soft px-1.5 py-0.5 text-[11px] text-primary">
                          {t}
                        </span>
                      ))}
                    </span>
                    <button
                      type="button"
                      aria-label={`Hapus ${p.name} dari owner's picks`}
                      disabled={saving}
                      onClick={() => void save(shown.filter((x) => x.product_id !== p.product_id))}
                      className="px-1 text-text-muted hover:text-danger disabled:opacity-60"
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ol>

              <div className="mt-3">
                {adding ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <Select
                      aria-label="Produk"
                      value={candidate}
                      onChange={(e) => setCandidate(e.target.value)}
                      className="max-w-64"
                    >
                      <option value="">Pilih produk…</option>
                      {options.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </Select>
                    <Button disabled={!candidate || saving} onClick={() => void add()}>Tambah</Button>
                    <Button variant="ghost" onClick={() => { setAdding(false); setCandidate('') }}>Batal</Button>
                  </div>
                ) : (
                  <Button variant="ghost" disabled={saving} onClick={() => setAdding(true)}>
                    + Tambah owner's pick
                  </Button>
                )}
              </div>

              <p className="mt-4 text-[12px] text-text-muted">
                Tag tersedia: {(tags.data ?? []).length > 0 ? (tags.data ?? []).join(' · ') : '—'} ·{' '}
                <Link to="/catalog/menu" className="font-medium text-primary hover:underline">+ tag baru</Link>
              </p>
              <p className="mt-1 text-[12px] text-text-muted">Seret ≡ untuk mengatur urutan.</p>
            </>
          )}
        </Card>

        <Card title={`Preview menu Rekomendasi WhatsApp${outlet ? ` · ${outlet.name}` : ''}`}>
          {preview.error != null && <Alert>{errorMessage(preview.error)}</Alert>}
          {!view && preview.error == null ? <Loading /> : view && (
            <div className="text-[13px] text-text">
              <h3 className="mb-1 font-semibold">Owner's picks yang tersedia</h3>
              <PreviewList items={view.picks} empty="Belum ada owner's pick." />
              <h3 className="mb-1 mt-4 font-semibold">Best sellers 30 hari terakhir (outlet ini)</h3>
              <PreviewList
                items={view.best_sellers}
                empty="Belum ada penjualan 30 hari terakhir."
                units={Object.fromEntries(view.best_sellers.map((b) => [b.product_id, b.units_30d]))}
              />
              <p className="mt-4 text-[12px] text-text-muted">
                Maks. {view.max_items} item · sold out dikecualikan · tanpa duplikat
              </p>
            </div>
          )}
        </Card>
      </div>
    </>
  )
}

function PreviewList({ items, empty, units }: {
  items: PreviewItem[]
  empty: string
  units?: Record<string, number>
}) {
  if (items.length === 0) return <p className="text-[12px] text-text-muted">{empty}</p>
  return (
    <ul className="space-y-0.5">
      {items.map((it) => (
        <li key={it.product_id} className={it.skipped_reason ? 'text-text-muted' : ''}>
          {it.position !== null ? `${it.position}. ` : '— '}
          {it.name}
          {units && !it.skipped_reason && ` · ${units[it.product_id]} unit`}
          {it.skipped_reason && ` (${SKIPPED[it.skipped_reason]})`}
        </li>
      ))}
    </ul>
  )
}
