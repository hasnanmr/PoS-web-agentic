// Wireframes O17 + O15 — Dashboard tab "PO & Supplier" (owner only). O17 cards on top, the O15 PO
// list and detail below.
// Endpoints: GET /owner/dashboard/purchase-orders?outlet_id=&month= (O17),
// GET /owner/purchase-orders?outlet_id=&status=|month=&state=&goods=&payment=&cursor= (O15 list),
// GET /owner/purchase-orders/{id} (detail); payment, close-with-note and cancel in ./dialogs.
// Canvas notes: the outlet filter applies to the whole tab; the month only to Ringkasan PO (by PO
// open date). Pembayaran supplier and PO ada selisih always show every PO that needs action. The
// list uses the status chips; a Ringkasan figure opens it with exactly those POs. Ledger expense is
// posted when a payment is recorded — not when a PO is opened, checked or closed.
import { useRef, useState } from 'react'
import { useSession } from '../../app/session'
import { errorMessage } from '../../lib/api'
import { formatDay, formatRupiah, formatTime, localDay, plainQuantity, shortOutlet, todayIn } from '../../lib/format'
import type {
  Bucket, PaymentItem, PoChip, PoDashboard, PoDetail, PoDifference, PoPage, PoRow,
} from '../../lib/types'
import { useLoad } from '../../lib/useLoad'
import { Alert, Button, LinkButton, Loading } from '../../ui/kit'
import { NoteDialog, PaymentDialog, type PayTarget } from './dialogs'
import { Badge } from './ui'
import { CHIPS, TERM_LABEL, monthLabel, rowBadge, termDetail } from './util'

/** Ringkasan PO drill-down (FR3.12): one figure's POs. */
export interface Drill {
  label: string
  param: 'state' | 'goods' | 'payment'
  value: string
}

type ListFilter = { chip: PoChip | null } | { drill: Drill }

export function PoTab({ outletId, month, focusId }: {
  outletId: string
  month: string
  /** A PO to select when the tab mounts (e.g. just opened from O16). */
  focusId?: string
}) {
  const { api, me } = useSession()
  const params = new URLSearchParams({ month })
  if (outletId) params.set('outlet_id', outletId)
  const dashQuery = params.toString()
  const dash = useLoad(() => api.get<PoDashboard>(`/owner/dashboard/purchase-orders?${dashQuery}`), dashQuery)
  const [filter, setFilter] = useState<ListFilter>({ chip: null })
  const [selected, setSelected] = useState<string | undefined>(focusId)
  const [listVersion, setListVersion] = useState(0)
  const [paying, setPaying] = useState<PayTarget>()
  const [noting, setNoting] = useState<{ kind: 'close' | 'cancel'; id: string; number: string }>()
  const listRef = useRef<HTMLElement>(null)
  const outletName = outletId ? me.outlets.find((o) => o.id === outletId)?.name ?? '' : 'Semua outlet'

  async function refreshAll() {
    setPaying(undefined)
    setNoting(undefined)
    setListVersion((v) => v + 1)
    await dash.reload()
  }

  function showList(next: ListFilter) {
    setFilter(next)
    listRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  }

  function select(id: string) {
    setSelected(id)
    listRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  }

  const d = dash.data
  return (
    <div className="space-y-4">
      {dash.error ? <Alert>Kartu PO belum bisa dimuat: {errorMessage(dash.error)}</Alert> : null}
      {!d ? (dash.loading ? <Loading /> : null) : (
        <div className="grid gap-4 lg:grid-cols-[1fr_376px]">
          <SummaryCard data={d} month={month} outletName={outletName}
            onDrill={(drill) => showList({ drill })} />
          <div className="space-y-4 lg:row-span-2">
            <PaymentsCard data={d} onPay={(item) => setPaying(payTarget(item))}
              onShowAll={() => showList({ chip: 'awaiting_payment' })} />
            <DifferencesCard items={d.po_differences} onOpen={select}
              onClose={(item) => setNoting({ kind: 'close', id: item.po_id, number: item.number })} />
          </div>
        </div>
      )}

      <section ref={listRef} aria-label="Daftar PO" className="scroll-mt-20">
        <div className="mb-2 flex flex-wrap items-baseline gap-x-3">
          <h2 className="text-[14px] font-semibold text-text">Daftar PO · {outletName}</h2>
          <p className="text-[11px] text-text-muted">Chip status untuk semua PO · angka di Ringkasan PO membuka daftar ini berisi PO yang sama</p>
        </div>
        <div className="grid gap-4 lg:grid-cols-[1fr_396px]">
          <PoList key={`${outletId}|${listVersion}`} outletId={outletId} month={month} filter={filter}
            selected={selected} onFilter={setFilter} onSelect={setSelected} />
          {selected ? (
            <DetailPanel key={`${selected}|${listVersion}`} id={selected}
              onPay={(po) => setPaying(payTarget(po))}
              onNote={(kind, po) => setNoting({ kind, id: po.id, number: po.number })} />
          ) : (
            <p className="hidden rounded-lg border border-dashed border-border p-6 text-center text-[12px] text-text-muted lg:block">
              Pilih PO untuk melihat detail, riwayat, dan sisa hutang.
            </p>
          )}
        </div>
      </section>

      {paying && <PaymentDialog target={paying} onClose={() => setPaying(undefined)} onDone={refreshAll} />}
      {noting && <NoteDialog kind={noting.kind} poId={noting.id} number={noting.number}
        onClose={() => setNoting(undefined)} onDone={refreshAll} />}
    </div>
  )
}

function payTarget(po: PaymentItem | PoDetail): PayTarget {
  const isItem = 'po_id' in po
  return {
    id: isItem ? po.po_id : po.id,
    number: po.number,
    supplier: po.supplier.name,
    outletId: po.outlet.id,
    term: po.payment_term,
    total: po.total,
    paid: po.amount_paid ?? 0,
    owed: po.amount_owed ?? 0,
    dueDate: po.due_date,
  }
}

// O17 · Ringkasan PO ------------------------------------------------------------------------

const TILE: Record<string, string> = {
  primary: 'bg-primary-soft text-primary',
  success: 'bg-success-soft text-success',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-danger-soft text-danger',
  plain: 'bg-page text-text',
}

function Tile({ label, bucket, tone, sisa = false, onClick }: {
  label: string
  bucket: Bucket
  tone: keyof typeof TILE
  sisa?: boolean
  onClick: () => void
}) {
  return (
    <button type="button" onClick={onClick} aria-label={`${label}: ${bucket.count} PO`}
      className={`w-full rounded-md px-2.5 py-2 text-left hover:ring-1 hover:ring-primary ${TILE[tone]}`}>
      <span className="block text-[11px]">{label} →</span>
      <span className="block text-[14px] font-bold text-text">
        {bucket.count} PO · {sisa ? 'sisa ' : ''}{formatRupiah(bucket.amount)}
      </span>
    </button>
  )
}

function SummaryCard({ data, month, outletName, onDrill }: {
  data: PoDashboard
  month: string
  outletName: string
  onDrill: (drill: Drill) => void
}) {
  const s = data.po_summary
  const drill = (label: string, param: Drill['param'], value: string) => () => onDrill({ label, param, value })
  return (
    <section aria-label="Ringkasan PO" className="rounded-lg border border-border bg-surface p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[13px] font-semibold text-text">Ringkasan PO · {monthLabel(month)} · {outletName}</h2>
        <p className="text-[12px] text-text-muted">{s.total.count} PO · {formatRupiah(s.total.amount)}</p>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <div className="space-y-2">
          <p className="text-[10px] font-semibold text-text-muted">STATUS PO</p>
          <Tile label="Dibuka" tone="primary" bucket={s.status.open} onClick={drill('Dibuka', 'state', 'open')} />
          <Tile label="Ditutup" tone="success" bucket={s.status.closed} onClick={drill('Ditutup', 'state', 'closed')} />
        </div>
        <div className="space-y-2">
          <p className="text-[10px] font-semibold text-text-muted">BARANG</p>
          <Tile label="Belum datang" tone="plain" bucket={s.goods.not_arrived} onClick={drill('Barang belum datang', 'goods', 'not_arrived')} />
          <Tile label="Sebagian (ada selisih)" tone="warning" bucket={s.goods.partly_arrived}
            onClick={drill('Barang sebagian', 'goods', 'partly_arrived')} />
          <Tile label="Sudah datang" tone="success" bucket={s.goods.arrived} onClick={drill('Barang sudah datang', 'goods', 'arrived')} />
        </div>
        <div className="space-y-2">
          <p className="text-[10px] font-semibold text-text-muted">PEMBAYARAN</p>
          <Tile label="Belum dibayar" tone="danger" bucket={s.payment.unpaid} onClick={drill('Belum dibayar', 'payment', 'unpaid')} />
          <Tile label="Sebagian" tone="warning" sisa bucket={s.payment.partially_paid}
            onClick={drill('Dibayar sebagian', 'payment', 'partially_paid')} />
          <Tile label="Lunas" tone="success" bucket={s.payment.paid} onClick={drill('Lunas', 'payment', 'paid')} />
        </div>
      </div>
      <p className="mt-3 text-[11px] text-text-muted">
        Bayar mundur {s.by_term.pay_later.count} PO · Bayar di muka {s.by_term.pay_in_advance.count} PO • Bulan = tanggal PO dibuka •
        Klik angka → Daftar PO (di bawah) dengan filter yang sama
      </p>
    </section>
  )
}

// O17 · Pembayaran supplier -----------------------------------------------------------------

function paymentHeadline(item: PaymentItem): string {
  if (item.reason === 'overdue') return `OVERDUE ${item.days_overdue} HARI · bayar mundur`
  if (item.reason === 'pay_in_advance') return `PERLU DIBAYAR · bayar di muka${item.created_by ? ` (dibuka ${item.created_by})` : ''}`
  return `JATUH TEMPO ${item.due_date ? formatDay(item.due_date).toUpperCase() : ''} · PO ditutup`
}

function PaymentsCard({ data, onPay, onShowAll }: {
  data: PoDashboard
  onPay: (item: PaymentItem) => void
  onShowAll: () => void
}) {
  const p = data.supplier_payments
  const tone = { overdue: 'bg-danger-soft', pay_in_advance: 'bg-warning-soft', due: 'bg-page' } as const
  return (
    <section aria-label="Pembayaran supplier" className="rounded-lg border border-border bg-surface p-4">
      <h2 className="text-[13px] font-semibold text-text">Pembayaran supplier</h2>
      <p className="mt-1 text-[11px] text-text-muted">
        Semua PO yang perlu dibayar (tidak ikut filter bulan) · Hutang supplier {formatRupiah(p.debt_total)} · {p.overdue_count} overdue ·
        {' '}{formatRupiah(p.due_7d_amount)} jatuh tempo 7 hari
      </p>
      <ul className="mt-3 space-y-2">
        {p.items.length === 0 && <li className="py-3 text-center text-[12px] text-text-muted">Tidak ada PO yang perlu dibayar.</li>}
        {p.items.map((item) => (
          <li key={item.po_id} className={`flex items-center justify-between gap-3 rounded-md px-2.5 py-2 text-[11px] text-text ${tone[item.reason]}`}>
            <div className="min-w-0">
              <p>{paymentHeadline(item)}</p>
              <p>{item.number} · {item.supplier.name} · {shortOutlet(item.outlet.name)}</p>
              <p>{item.amount_paid > 0 ? `Sisa ${formatRupiah(item.amount_owed)} dari ${formatRupiah(item.total)}` : formatRupiah(item.amount_owed)}</p>
            </div>
            <Button variant="action" className="h-8 shrink-0" aria-label={`Bayar ${item.number}`} onClick={() => onPay(item)}>Bayar</Button>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[11px] text-success">
        Sudah dibayar, barang belum diterima: {formatRupiah(p.prepaid_not_received)} ({p.prepaid_not_received_count} PO bayar di muka)
      </p>
      <LinkButton className="text-[11px] text-success" onClick={onShowAll}>Lihat semua di Daftar PO ↓</LinkButton>
    </section>
  )
}

// O17 · PO ada selisih ----------------------------------------------------------------------

function DifferencesCard({ items, onOpen, onClose }: {
  items: PoDifference[]
  onOpen: (id: string) => void
  onClose: (item: PoDifference) => void
}) {
  return (
    <section aria-label="PO ada selisih" className="rounded-lg border border-border bg-surface p-4">
      <h2 className="text-[13px] font-semibold text-text">PO ada selisih · perlu keputusan owner</h2>
      <p className="mt-1 text-[11px] text-text-muted">
        Staf tidak bisa menutup PO yang qty-nya tidak sesuai. Tunggu sisa barang datang, atau tutup dengan catatan (owner saja).
      </p>
      <ul className="mt-3 space-y-2">
        {items.length === 0 && <li className="py-3 text-center text-[12px] text-text-muted">Tidak ada PO dengan selisih.</li>}
        {items.map((item) => (
          <li key={item.po_id} className="rounded-md bg-warning-soft px-2.5 py-2 text-[11px] text-text">
            <p>{item.number} · {item.supplier.name} · {shortOutlet(item.outlet.name)} · {TERM_LABEL[item.payment_term].toLowerCase()}</p>
            {item.short_lines.map((l) => (
              <p key={l.item}>
                {l.item} {plainQuantity(l.received)} / {plainQuantity(l.ordered)} {l.unit} (kurang {plainQuantity(l.short)} {l.unit})
                {item.last_received_on ? ` · diterima ${formatDay(item.last_received_on)}` : ''}
              </p>
            ))}
            <div className="mt-2 flex gap-2">
              <Button variant="ghost" className="h-7 text-[11px]" onClick={() => onOpen(item.po_id)}>Lihat PO</Button>
              <Button variant="action" className="h-7 text-[11px]" aria-label={`Tutup dengan catatan ${item.number}`}
                onClick={() => onClose(item)}>Tutup dengan catatan</Button>
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[11px] text-text-muted">
        Tutup dengan catatan: catatan wajib (mis. “supplier kehabisan stok”); hutang PO tempo menjadi qty diterima × harga; pengingat
        bayar lalu muncul di Pembayaran supplier.
      </p>
    </section>
  )
}

// O15 · Daftar PO ---------------------------------------------------------------------------

function PoList({ outletId, month, filter, selected, onFilter, onSelect }: {
  outletId: string
  month: string
  filter: ListFilter
  selected?: string
  onFilter: (f: ListFilter) => void
  onSelect: (id: string) => void
}) {
  const { api, me } = useSession()
  const params = new URLSearchParams()
  if (outletId) params.set('outlet_id', outletId)
  if ('chip' in filter && filter.chip) params.set('status', filter.chip)
  if ('drill' in filter) {
    params.set('month', month)
    params.set(filter.drill.param, filter.drill.value)
  }
  const query = params.toString()
  const first = useLoad(() => api.get<PoPage>(`/owner/purchase-orders${query ? `?${query}` : ''}`), query)
  const [more, setMore] = useState<{ query: string; items: PoRow[]; cursor: string | null }>()
  const [loadingMore, setLoadingMore] = useState(false)
  const extra = more?.query === query ? more : undefined
  const rows = [...(first.data?.items ?? []), ...(extra?.items ?? [])]
  const cursor = extra ? extra.cursor : first.data?.next_cursor
  const tz = (id: string) => me.outlets.find((o) => o.id === id)?.timezone ?? 'Asia/Jakarta'

  async function loadMore() {
    if (!cursor) return
    setLoadingMore(true)
    try {
      const page = await api.get<PoPage>(`/owner/purchase-orders?${query ? `${query}&` : ''}cursor=${encodeURIComponent(cursor)}`)
      setMore({ query, items: [...(extra?.items ?? []), ...page.items], cursor: page.next_cursor })
    } finally {
      setLoadingMore(false)
    }
  }

  const activeChip = 'chip' in filter ? filter.chip : undefined
  return (
    <div className="min-w-0 rounded-lg border border-border bg-surface p-4">
      <div role="group" aria-label="Filter status PO" className="flex flex-wrap gap-1.5">
        {CHIPS.map((c) => (
          <button key={c.label} type="button" aria-pressed={activeChip === c.key} onClick={() => onFilter({ chip: c.key })}
            className={`h-6 rounded-full px-2.5 text-[11px] ${activeChip === c.key
              ? 'bg-primary font-semibold text-white'
              : c.danger ? 'bg-danger-soft text-danger' : 'bg-page text-text'}`}>
            {c.label}
          </button>
        ))}
      </div>
      {'drill' in filter && (
        <p className="mt-2 inline-flex items-center gap-2 rounded-full bg-primary-soft px-2.5 py-0.5 text-[11px] text-primary">
          Dari Ringkasan PO: {filter.drill.label} · {monthLabel(month)}
          <button type="button" aria-label="Hapus filter Ringkasan" onClick={() => onFilter({ chip: null })}>✕</button>
        </p>
      )}
      {first.error ? <div className="mt-3"><Alert>{errorMessage(first.error)}</Alert></div> : null}
      {!first.data ? (first.loading ? <Loading /> : null) : rows.length === 0 ? (
        <p className="py-8 text-center text-[12px] text-text-muted">Belum ada PO untuk filter ini.</p>
      ) : (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[520px] text-[12px]">
            <thead>
              <tr className="text-left text-[10px] text-text-muted">
                <th className="px-2 py-2 font-semibold">NO. PO</th>
                <th className="px-2 py-2 font-semibold">SUPPLIER · OUTLET</th>
                <th className="px-2 py-2 font-semibold">TERMIN</th>
                <th className="px-2 py-2 font-semibold">STATUS</th>
                <th className="px-2 py-2 text-right font-semibold">TOTAL</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const badge = rowBadge(r, todayIn(tz(r.outlet.id)))
                const muted = r.status === 'cancelled' || (r.status === 'closed' && r.payment_status === 'paid')
                return (
                  <tr key={r.id} onClick={() => onSelect(r.id)} aria-selected={selected === r.id}
                    className={`cursor-pointer border-t border-border ${selected === r.id ? 'bg-primary-soft' : 'hover:bg-page'} ${muted ? 'text-text-muted' : 'text-text'}`}>
                    <td className="px-2 py-2.5 font-semibold">
                      <button type="button" className="text-left" onClick={() => onSelect(r.id)}>{r.number}</button>
                    </td>
                    <td className="px-2 py-2.5">{r.supplier.name}<br /><span className="text-text-muted">{r.outlet.name}</span></td>
                    <td className="px-2 py-2.5 text-text-muted">
                      {TERM_LABEL[r.payment_term]}{r.payment_term === 'pay_in_advance' && r.payment_status === 'paid' && r.status !== 'closed' ? ' ✓' : ''}
                      <br />{termDetail(r)}
                    </td>
                    <td className="px-2 py-2.5"><Badge tone={badge.tone}>{badge.label}</Badge></td>
                    <td className="px-2 py-2.5 text-right">{formatRupiah(r.total)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {cursor && (
        <div className="mt-3 text-center">
          <LinkButton disabled={loadingMore} onClick={loadMore}>{loadingMore ? 'Memuat…' : 'Muat lagi'}</LinkButton>
        </div>
      )}
    </div>
  )
}

// O15 · Detail PO ---------------------------------------------------------------------------

const ROLE: Record<string, string> = { owner: 'Owner', staff: 'staf' }

function eventText(e: PoDetail['events'][number], po: PoDetail): string {
  const who = e.actor.name ? (e.actor.role === 'owner' ? 'Owner' : `${e.actor.name} (${ROLE[e.actor.role ?? ''] ?? e.actor.role})`) : 'Sistem'
  const data = e.data
  switch (e.kind) {
    case 'opened':
      return `PO dibuka · ${who}`
    case 'received': {
      const lines = (data.lines as { item: string; quantity: string; unit: string }[] | undefined) ?? []
      const text = lines.map((l) => `${l.item} ${plainQuantity(l.quantity)} ${l.unit}`).join(', ')
      return `Barang dicek: ${text} · ${who}`
    }
    case 'paid':
      return `Bayar ${formatRupiah(Number(data.amount))} · ${data.method === 'transfer' ? 'transfer' : data.from_drawer ? 'cash dari laci' : 'cash'} · ${who}`
    case 'closed':
      return data.note ? `PO ditutup dengan catatan “${String(data.note)}” · ${who}` : `PO ditutup · ${who}`
    case 'cancelled':
      return `PO dibatalkan: ${String(data.reason ?? po.cancel_reason ?? '')} · ${who}`
  }
}

function flow(po: PoDetail): { label: string; done: boolean }[] {
  const checked = po.goods_status !== 'not_arrived'
  const closed = po.status === 'closed'
  const paid = po.payment_status === 'paid'
  return po.payment_term === 'pay_later'
    ? [{ label: 'Dibuka', done: true }, { label: 'Barang dicek', done: checked }, { label: 'PO ditutup', done: closed }, { label: 'Dibayar', done: paid }]
    : [{ label: 'Dibuka', done: true }, { label: 'Dibayar', done: paid }, { label: 'Barang dicek', done: checked }, { label: 'PO ditutup', done: closed }]
}

function DetailPanel({ id, onPay, onNote }: {
  id: string
  onPay: (po: PoDetail) => void
  onNote: (kind: 'close' | 'cancel', po: PoDetail) => void
}) {
  const { api, me } = useSession()
  const detail = useLoad(() => api.get<PoDetail>(`/owner/purchase-orders/${id}`), id)
  const po = detail.data
  if (detail.error) return <Alert>{errorMessage(detail.error)}</Alert>
  if (!po) return <Loading />
  const tz = me.outlets.find((o) => o.id === po.outlet.id)?.timezone ?? 'Asia/Jakarta'
  const badge = rowBadge(po, todayIn(tz))
  const owed = po.amount_owed ?? 0
  const can = (a: PoDetail['allowed_actions'][number]) => po.allowed_actions.includes(a)
  const dateLine = po.payment_term === 'pay_later'
    ? po.due_date ? `jatuh tempo ${formatDay(po.due_date)}` : ''
    : po.expected_date ? `tiba ± ${formatDay(po.expected_date)}` : ''

  return (
    <section aria-label={`Detail ${po.number}`} className="h-fit space-y-2.5 rounded-lg border border-border bg-surface p-4">
      <h2 className="text-[15px] font-bold text-text">{po.number} · {po.supplier.name}</h2>
      <p className="text-[12px] text-text-muted">{po.outlet.name} · {TERM_LABEL[po.payment_term]} · {dateLine}</p>
      <div className="flex flex-wrap gap-1.5">
        <Badge tone={badge.tone}>{badge.label}</Badge>
        {po.status !== 'cancelled' && po.payment_status !== 'paid' && po.payment_status === 'partially_paid' && (
          <Badge tone="warning">Dibayar sebagian</Badge>
        )}
      </div>
      <div className="rounded-md bg-page px-2.5 py-2">
        <p className="text-[10px] font-semibold text-text-muted">Skema {TERM_LABEL[po.payment_term].toLowerCase()}</p>
        <p className="text-[11px] font-medium text-text">
          {flow(po).map((s) => `${s.done ? '✓' : '○'} ${s.label}`).join('  →  ')}
        </p>
      </div>
      <table className="w-full text-[12px]">
        <thead>
          <tr className="bg-page text-left text-[10px] text-text-muted">
            <th className="px-1.5 py-1 font-semibold">ITEM</th>
            <th className="px-1.5 py-1 font-semibold">QTY PO</th>
            <th className="px-1.5 py-1 font-semibold">DITERIMA</th>
            <th className="px-1.5 py-1 text-right font-semibold">SUBTOTAL</th>
          </tr>
        </thead>
        <tbody>
          {po.lines.map((l) => (
            <tr key={l.id} className="align-top text-text">
              <td className="px-1.5 py-1.5">{l.item}<br /><span className="text-text-muted">{formatRupiah(l.unit_price)} / {l.unit}</span></td>
              <td className="px-1.5 py-1.5">{plainQuantity(l.quantity)} {l.unit}</td>
              <td className={`px-1.5 py-1.5 font-semibold ${l.check === 'match' ? 'text-success' : 'text-warning'}`}>
                {plainQuantity(l.received_quantity)} {l.unit} {l.check === 'match' ? '✓' : ''}
              </td>
              <td className="px-1.5 py-1.5 text-right">{formatRupiah(l.subtotal)}</td>
            </tr>
          ))}
          <tr className="font-semibold text-text">
            <td className="px-1.5 pt-2" colSpan={3}>Total PO</td>
            <td className="px-1.5 pt-2 text-right">{formatRupiah(po.total)}</td>
          </tr>
        </tbody>
      </table>
      {po.note && <p className="text-[11px] text-text-muted">Catatan: {po.note}</p>}
      <div>
        <h3 className="text-[12px] font-semibold text-text">Riwayat (tidak bisa diubah)</h3>
        <ul className="mt-1 space-y-0.5 text-[11px] leading-[18px] text-text">
          {po.events.map((e, i) => (
            <li key={i} className="flex gap-1.5">
              <span aria-hidden="true">●</span>
              <span><span className="mr-1.5">{formatDay(localDay(e.at, tz))} {formatTime(e.at, tz)}</span>{eventText(e, po)}</span>
            </li>
          ))}
        </ul>
      </div>
      {po.status !== 'cancelled' && owed > 0 && (
        <div className="flex items-center justify-between rounded-md bg-warning-soft px-2.5 py-2 text-warning">
          <span className="text-[12px] font-semibold">
            {po.payment_term === 'pay_later' ? `Sisa hutang${po.due_date ? ` (JT ${formatDay(po.due_date)})` : ''}` : 'Perlu dibayar'}
          </span>
          <span className="text-[13px] font-bold">{formatRupiah(owed)}</span>
        </div>
      )}
      {can('record_payment') && (
        <Button variant="action" className="w-full" onClick={() => onPay(po)}>Catat pembayaran</Button>
      )}
      {(can('close_with_note') || can('cancel')) && (
        <div className="flex gap-2">
          {can('close_with_note') && <Button variant="ghost" className="flex-1" onClick={() => onNote('close', po)}>Tutup dengan catatan</Button>}
          {can('cancel') && <Button variant="danger" className="flex-1" onClick={() => onNote('cancel', po)}>Batalkan PO</Button>}
        </div>
      )}
      <p className="text-[11px] text-text-muted">Ledger expense diposting saat pembayaran dicatat — bukan saat PO dibuka, dicek, atau ditutup.</p>
    </section>
  )
}
