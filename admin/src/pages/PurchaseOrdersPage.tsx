// Staff "Purchase Order" (sidebar OPERASIONAL): wireframes S10 (Purchase Order outlet), S11 (Cek barang
// datang) and S12 (Buka PO, the O16 form). The view lives in the URL: ?po=<id> (S11), ?view=new (S12).
// Endpoints: GET /ops/outlets/{id}/purchase-orders?status=&cursor= (S10, no debt figures),
// GET /ops/purchase-orders/{id} (S11 form), POST /ops/purchase-orders/{id}/receipts (Idempotency-Key),
// POST /ops/purchase-orders/{id}/close; S12 → ./po/PoForm.
// Canvas notes: staff see their outlet's POs (with prices) and the payment status read-only; recording
// payments, cancelling, closing a PO with a difference and supplier debt are owner-only. Staff can only
// close a PO when every line's received qty equals the PO qty; while a line is short the Tutup PO button
// is locked (the API refuses it too) and the PO shows on the owner dashboard. Saving a receipt adds stock
// through restock movements (ingredient lines only); received qty can never exceed the PO qty.
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { formatDay, formatRupiah, formatTime, localDay, plainQuantity, todayIn } from '../lib/format'
import type { PoChip, PoDetail, PoPage, PoRow } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, LinkButton, Loading, TextInput } from '../ui/kit'
import { PoForm } from './po/PoForm'
import { TERM_LABEL, eventText, useIdempotencyKey } from './po/util'

/** S10 filters: the O15 status filters that concern staff (no payment chips; screen-endpoint-map S10). */
const STAFF_CHIPS: { key: PoChip | null; label: string }[] = [
  { key: null, label: 'Semua' },
  { key: 'open', label: 'Terbuka' },
  { key: 'difference_found', label: 'Ada selisih' },
  { key: 'closed', label: 'Ditutup' },
]

export default function PurchaseOrdersPage() {
  const { outlet } = useSession()
  const [search, setSearch] = useSearchParams()
  const poId = search.get('po')
  if (!outlet) return <PageHeader title="Purchase Order" />
  if (search.get('view') === 'new') {
    return (
      <>
        <PageHeader title="Buka Purchase Order" />
        <div className="p-4 md:p-6">
          <PoForm defaultOutletId={outlet.id} onCancel={() => setSearch({})} onOpened={(po) => setSearch({ po: po.id })} />
        </div>
      </>
    )
  }
  if (poId) return <GoodsCheck key={poId} id={poId} onBack={() => setSearch({})} />
  return <OutletList outletId={outlet.id} outletName={outlet.name} timezone={outlet.timezone}
    onOpen={(id) => setSearch({ po: id })} onNew={() => setSearch({ view: 'new' })} />
}

// S10 · Purchase Order outlet ----------------------------------------------------------------

function goods(row: PoRow, today: string): { text: string; className: string } {
  if (row.status === 'cancelled') return { text: 'Dibatalkan', className: 'text-text-muted' }
  if (row.status === 'difference_found') return { text: '⚠ Ada selisih', className: 'font-semibold text-warning' }
  if (row.status === 'closed') return { text: '✓ Lengkap · PO ditutup', className: 'font-semibold text-success' }
  if (row.goods_status === 'arrived') return { text: '✓ Lengkap · siap ditutup', className: 'font-semibold text-success' }
  const due = row.expected_date ?? row.due_date
  if (row.goods_status === 'partly_arrived') return { text: 'Sebagian datang', className: 'text-warning' }
  return due && due < today
    ? { text: 'Belum datang (terlambat)', className: 'text-danger' }
    : { text: 'Belum datang', className: 'text-primary' }
}

/** PEMBAYARAN (OWNER), read-only: staff never see amounts owed (US-061). */
function payment(row: PoRow): { text: string; className: string } {
  if (row.status === 'cancelled') return { text: '—', className: 'text-text-muted' }
  if (row.payment_status === 'paid') {
    return { text: row.status === 'closed' ? '✓ Lunas' : '✓ Sudah dibayar', className: 'font-semibold text-success' }
  }
  if (row.payment_term === 'pay_in_advance') {
    return { text: 'Menunggu dibayar owner (notif di dashboard owner)', className: 'font-semibold text-danger' }
  }
  if (row.status !== 'closed') return { text: '— (setelah PO ditutup)', className: 'text-text-muted' }
  return { text: row.payment_status === 'partially_paid' ? 'Dicicil owner' : 'Menunggu bayar owner', className: 'text-warning' }
}

function OutletList({ outletId, outletName, timezone, onOpen, onNew }: {
  outletId: string
  outletName: string
  timezone: string
  onOpen: (id: string) => void
  onNew: () => void
}) {
  const { api } = useSession()
  const [chip, setChip] = useState<PoChip | null>(null)
  const query = `${outletId}|${chip ?? ''}`
  const path = `/ops/outlets/${outletId}/purchase-orders${chip ? `?status=${chip}` : ''}`
  const first = useLoad(() => api.get<PoPage>(path), query)
  const [more, setMore] = useState<{ query: string; items: PoRow[]; cursor: string | null }>()
  const [moreError, setMoreError] = useState<{ query: string; message: string }>()
  const [loadingMore, setLoadingMore] = useState(false)
  const extra = more?.query === query ? more : undefined
  const rows = [...(first.data?.items ?? []), ...(extra?.items ?? [])]
  const cursor = extra ? extra.cursor : first.data?.next_cursor
  const today = todayIn(timezone)

  async function loadMore() {
    if (!cursor) return
    setLoadingMore(true)
    setMoreError(undefined)
    try {
      const page = await api.get<PoPage>(`${path}${chip ? '&' : '?'}cursor=${encodeURIComponent(cursor)}`)
      setMore({ query, items: [...(extra?.items ?? []), ...page.items], cursor: page.next_cursor })
    } catch (err) {
      setMoreError({ query, message: errorMessage(err) })
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <>
      <PageHeader title="Purchase Order"
        tabs={
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-text-muted">
            <span>{outletName} ·</span>
            <div role="group" aria-label="Filter status PO" className="flex flex-wrap gap-1">
              {STAFF_CHIPS.map((c) => (
                <button key={c.label} type="button" aria-pressed={chip === c.key} onClick={() => setChip(c.key)}
                  className={`rounded px-1.5 py-0.5 ${chip === c.key ? 'bg-primary-soft font-semibold text-primary' : 'hover:text-text'}`}>
                  {c.label}
                </button>
              ))}
            </div>
          </div>
        }
        actions={<Button variant="action" className="h-8" onClick={onNew}>+ Buka PO</Button>} />
      <div className="p-4 md:p-6">
        <section aria-label="Daftar PO outlet" className="rounded-lg border border-border bg-surface p-4">
          {first.error ? <Alert>{errorMessage(first.error)}</Alert> : null}
          {!first.data ? (first.loading ? <Loading /> : null) : rows.length === 0 ? (
            <p className="py-8 text-center text-[12px] text-text-muted">Belum ada PO untuk outlet ini.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-[12px]">
                <thead>
                  <tr className="bg-page text-left text-[10px] text-text-muted">
                    <th className="px-2 py-2 font-semibold">NO. PO</th>
                    <th className="px-2 py-2 font-semibold">SUPPLIER</th>
                    <th className="px-2 py-2 font-semibold">TERMIN</th>
                    <th className="px-2 py-2 font-semibold">BARANG</th>
                    <th className="px-2 py-2 font-semibold">PEMBAYARAN (OWNER)</th>
                    <th className="px-2 py-2 text-right font-semibold">TOTAL</th>
                    <th className="px-2 py-2 font-semibold">AKSI</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const g = goods(r, today)
                    const p = payment(r)
                    const done = r.status === 'closed' || r.status === 'cancelled'
                    return (
                      <tr key={r.id} className={`border-t border-border ${done ? 'text-text-muted' : 'text-text'}`}>
                        <td className="px-2 py-2.5 font-semibold">{r.number}</td>
                        <td className="px-2 py-2.5">
                          {r.supplier.name}<br />
                          <span className="text-text-muted">dibuka {r.created_by ?? '—'} · {formatDay(r.ordered_on)}</span>
                        </td>
                        <td className="px-2 py-2.5 text-text-muted">
                          {TERM_LABEL[r.payment_term]}<br />
                          {r.payment_term === 'pay_later'
                            ? r.due_date && `JT ${formatDay(r.due_date)}`
                            : r.expected_date && `tiba ± ${formatDay(r.expected_date)}`}
                        </td>
                        <td className={`px-2 py-2.5 ${g.className}`}>{g.text}</td>
                        <td className={`max-w-[200px] px-2 py-2.5 ${p.className}`}>{p.text}</td>
                        <td className="px-2 py-2.5 text-right">{formatRupiah(r.total)}</td>
                        <td className="px-2 py-2.5">
                          {done ? (
                            <LinkButton className="text-[12px]" onClick={() => onOpen(r.id)} aria-label={`Lihat detail ${r.number}`}>
                              Lihat detail →
                            </LinkButton>
                          ) : (
                            <Button className="h-7 text-[11px]" onClick={() => onOpen(r.id)} aria-label={`Cek barang datang ${r.number}`}>
                              Cek barang datang
                            </Button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
          {moreError?.query === query && <div className="mt-3"><Alert>PO berikutnya belum bisa dimuat: {moreError.message}</Alert></div>}
          {cursor && (
            <div className="mt-3 text-center">
              <LinkButton disabled={loadingMore} onClick={loadMore}>{loadingMore ? 'Memuat…' : 'Muat lagi'}</LinkButton>
            </div>
          )}
          <p className="mt-3 text-[11px] text-text-muted">
            Staf melihat PO outlet yang ditugaskan (termasuk harga) dan status pembayaran (hanya baca). Mencatat pembayaran,
            membatalkan PO, menutup PO dengan selisih, dan hutang supplier hanya untuk owner.
          </p>
        </section>
      </div>
    </>
  )
}

// S11 · Cek barang datang -------------------------------------------------------------------

/** Quantities are decimals from the API ("12.000"); compare in thousandths to avoid float drift. */
function milli(value: string): number {
  const n = Number(value.replace(',', '.'))
  return Number.isFinite(n) ? Math.round(n * 1000) : NaN
}

function fromMilli(value: number): string {
  return plainQuantity((value / 1000).toFixed(3))
}

function GoodsCheck({ id, onBack }: { id: string; onBack: () => void }) {
  const { api, me } = useSession()
  const loaded = useLoad(() => api.get<PoDetail>(`/ops/purchase-orders/${id}`), id)
  const [saved, setSaved] = useState<PoDetail>()
  const po = saved ?? loaded.data
  const tz = me.outlets.find((o) => o.id === po?.outlet.id)?.timezone ?? 'Asia/Jakarta'
  const today = todayIn(tz)
  const [arriving, setArriving] = useState<Record<string, string>>({})
  const [receivedOn, setReceivedOn] = useState(today)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState<'save' | 'close'>()
  const [error, setError] = useState<string>()
  const keyFor = useIdempotencyKey()

  if (loaded.error && !po) return <><PageHeader title="Cek barang datang" /><div className="p-4 md:p-6"><Alert>{errorMessage(loaded.error)}</Alert></div></>
  if (!po) return <><PageHeader title="Cek barang datang" /><Loading /></>

  const canReceive = po.allowed_actions.includes('receive')
  const canClose = po.allowed_actions.includes('close')
  const rows = po.lines.map((l) => {
    const now = arriving[l.id] ?? ''
    const nowMilli = now.trim() === '' ? 0 : milli(now)
    const remaining = milli(l.remaining_quantity)
    const invalid = Number.isNaN(nowMilli) || nowMilli < 0 || nowMilli > remaining
    const left = remaining - (invalid ? 0 : nowMilli)
    return { line: l, now, nowMilli, invalid, left }
  })
  const anyInvalid = rows.some((r) => r.invalid)
  const toSave = rows.filter((r) => !r.invalid && r.nowMilli > 0)
  const shortAfter = rows.filter((r) => r.left > 0)
  const restock = toSave.filter((r) => r.line.stock_item_id)
  const closed = po.status === 'closed' || po.status === 'cancelled'
  const lockReason = po.payment_term === 'pay_in_advance' && po.payment_status !== 'paid' && po.goods_status === 'arrived'
    ? 'PO bayar di muka belum dibayar owner'
    : 'qty belum sesuai PO'

  async function save() {
    if (!po) return
    setBusy('save')
    setError(undefined)
    try {
      const body = {
        received_on: receivedOn,
        note: note.trim() || null,
        lines: toSave.map((r) => ({ line_id: r.line.id, quantity: fromMilli(r.nowMilli).replace(',', '.') })),
      }
      const next = await api.post<PoDetail>(`/ops/purchase-orders/${po.id}/receipts`, body,
        { 'Idempotency-Key': keyFor({ po: po.id, ...body }) })
      setSaved(next)
      setArriving({})
      setNote('')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(undefined)
    }
  }

  async function close() {
    if (!po) return
    setBusy('close')
    setError(undefined)
    try {
      setSaved(await api.post<PoDetail>(`/ops/purchase-orders/${po.id}/close`))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(undefined)
    }
  }

  const dateLine = po.payment_term === 'pay_later'
    ? po.due_date ? `(JT ${formatDay(po.due_date)})` : ''
    : po.expected_date ? `(tiba ± ${formatDay(po.expected_date)})` : ''
  const received = po.events.filter((e) => e.kind === 'received' || e.kind === 'closed' || e.kind === 'cancelled')

  return (
    <>
      <PageHeader title={`Cek barang datang · ${po.number}`} actions={<LinkButton onClick={onBack}>‹ Daftar PO</LinkButton>} />
      <div className="grid gap-4 p-4 md:p-6 lg:grid-cols-[1fr_356px]">
        <section aria-label={`Cek barang ${po.number}`} className="rounded-lg border border-border bg-surface p-4">
          <h2 className="text-[15px] font-bold text-text">{po.number} · {po.supplier.name}</h2>
          <p className="mt-1 text-[12px] text-text-muted">
            {po.outlet.name} · {TERM_LABEL[po.payment_term]} {dateLine} · dibuka {po.created_by ?? '—'} {formatDay(po.ordered_on)}
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[560px] text-[12px]">
              <thead>
                <tr className="bg-page text-left text-[10px] text-text-muted">
                  <th className="px-2 py-1.5 font-semibold">ITEM</th>
                  <th className="px-2 py-1.5 font-semibold">QTY PO</th>
                  <th className="px-2 py-1.5 font-semibold">DITERIMA</th>
                  {canReceive && <th className="px-2 py-1.5 font-semibold">DATANG SEKARANG</th>}
                  <th className="px-2 py-1.5 font-semibold">SISA</th>
                  <th className="px-2 py-1.5 font-semibold">CEK</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ line, now, invalid, left }) => (
                  <tr key={line.id} className={left > 0 && (now !== '' || line.check === 'short') ? 'bg-warning-soft' : ''}>
                    <td className="px-2 py-2 text-text">{line.item}</td>
                    <td className="px-2 py-2 font-semibold text-text">{plainQuantity(line.quantity)} {line.unit}</td>
                    <td className="px-2 py-2 text-text-muted">{plainQuantity(line.received_quantity)} {line.unit}</td>
                    {canReceive && (
                      <td className="px-2 py-2">
                        <div className="flex items-center gap-1">
                          <TextInput aria-label={`Datang sekarang ${line.item}`} inputMode="decimal" className="h-8 w-20 text-[12px]"
                            disabled={milli(line.remaining_quantity) === 0} value={now}
                            onChange={(e) => setArriving({ ...arriving, [line.id]: e.target.value })} />
                          <span className="text-text-muted">{line.unit}</span>
                        </div>
                        {invalid && <p className="mt-0.5 text-[10px] text-danger">Maks. {plainQuantity(line.remaining_quantity)} {line.unit}</p>}
                      </td>
                    )}
                    <td className={`px-2 py-2 ${left > 0 ? 'font-semibold text-warning' : 'text-text'}`}>{fromMilli(left)}{left > 0 ? ` ${line.unit}` : ''}</td>
                    <td className={`px-2 py-2 font-semibold ${left > 0 ? 'text-warning' : 'text-success'}`}>
                      {left > 0 ? `⚠ Kurang ${fromMilli(left)} ${line.unit}` : '✓ Sesuai'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {canReceive && (
            <div className="mt-3 grid gap-3 sm:grid-cols-[180px_1fr]">
              <label className="text-[12px] text-text">
                Tanggal terima
                <TextInput type="date" className="mt-1" value={receivedOn} min={po.ordered_on} max={today}
                  onChange={(e) => setReceivedOn(e.target.value)} />
              </label>
              <label className="text-[12px] text-text">
                Catatan
                <TextInput className="mt-1" maxLength={300} placeholder="Susu kurang 4 L, menyusul besok" value={note}
                  onChange={(e) => setNote(e.target.value)} />
              </label>
            </div>
          )}

          {!closed && shortAfter.length > 0 && (
            <div className="mt-3 rounded-md bg-warning-soft px-3 py-2 text-[11px] text-warning">
              <p className="text-[12px] font-semibold">⚠ Qty tidak sesuai PO — {shortAfter.length} baris kurang → PO tidak bisa ditutup oleh staf</p>
              <p>Setelah disimpan, PO berstatus “Ada selisih” dan staf tidak bisa menutupnya. PO muncul di dashboard owner (PO ada
                selisih) sampai sisanya datang dan dicek; hanya owner yang dapat menutupnya dengan catatan.</p>
            </div>
          )}
          {error && <div className="mt-3"><Alert>{error}</Alert></div>}

          {!closed && (
            <div className="mt-3 flex flex-wrap justify-end gap-2">
              {!canClose && (
                <Button variant="ghost" disabled className="bg-page">🔒 Tutup PO terkunci — {lockReason}</Button>
              )}
              {canReceive && (
                <Button disabled={busy !== undefined || anyInvalid || toSave.length === 0 || receivedOn > today} onClick={save}>
                  {busy === 'save' ? 'Menyimpan…' : 'Simpan penerimaan'}
                </Button>
              )}
            </div>
          )}
          {canReceive && (
            <p className="mt-2 text-[11px] text-text-muted">
              Disimpan → stok bertambah lewat movement restock
              {restock.length > 0 && `: ${restock.map((r) => `+${fromMilli(r.nowMilli)} ${r.line.unit} ${r.line.item}`).join(', ')}`}
              {' '}(ref. {po.number}); item teks bebas tidak menambah stok. Qty diterima tidak boleh melebihi qty PO.
            </p>
          )}
          {closed && <p className="mt-3 text-[12px] text-text-muted">{po.status === 'closed' ? 'PO sudah ditutup.' : 'PO dibatalkan.'}</p>}
        </section>

        <aside aria-label="Status penerimaan" className="h-fit space-y-3 rounded-lg border border-border bg-surface p-4 text-[12px] text-text">
          {canClose && (
            <>
              <p className="rounded-md bg-success-soft px-3 py-2 font-semibold text-success">✓ Semua qty sesuai PO</p>
              <Button variant="action" className="w-full" disabled={busy !== undefined} onClick={close}>
                {busy === 'close' ? 'Menutup…' : 'Tutup PO'}
              </Button>
            </>
          )}
          <div className="text-[11px] leading-4">
            <p className="font-semibold">Setelah PO ditutup:</p>
            <p>• Bayar mundur → pengingat bayar muncul di dashboard owner (Pembayaran supplier).</p>
            <p>• Bayar di muka → PO hanya bisa ditutup jika sudah dibayar owner.</p>
          </div>
          <div>
            <h3 className="font-semibold">Riwayat penerimaan</h3>
            {received.length === 0 ? <p className="mt-1 text-[11px] text-text-muted">Belum ada barang diterima.</p> : (
              <ul className="mt-1 space-y-0.5 text-[11px] leading-[18px]">
                {received.map((e, i) => (
                  <li key={i} className="flex gap-1.5">
                    <span aria-hidden="true">●</span>
                    <span><span className="mr-1.5">{formatDay(localDay(e.at, tz))} {formatTime(e.at, tz)}</span>{eventText(e, po)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <p className="text-[11px] text-text-muted">
            Aturan: staf hanya bisa menutup PO jika semua baris qty diterima = qty PO. Selama ada selisih, tombol Tutup PO terkunci
            (juga ditolak oleh API) dan PO muncul di dashboard owner. Setiap penerimaan dan penutupan tercatat (siapa, kapan).
          </p>
        </aside>
      </div>
    </>
  )
}
