// Wireframe O9b — Pengeluaran (sidebar KEUANGAN › Pengeluaran). Owner only.
// Endpoints: GET /owner/expenses/summary, GET /owner/expenses?source=, POST /owner/expenses,
// POST /owner/ledger-entries/{id}/reversal (same as O9).
// Canvas notes: the list is every expense in the ledger — supplier payments on purchase orders
// (source "po", highlighted; staff open the PO in S12 and check the goods in S11, the owner's
// "Catat pembayaran" posts the expense) plus direct expenses. PO rows cannot be reversed here
// ("Lihat PO →" opens the PO); direct rows can ("Reversal"). "Hutang PO belum dibayar" is as of
// today, not the period.
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { formatDay, formatRange, formatRupiah, shortOutlet } from '../lib/format'
import type { Expense, ExpensePage, ExpenseSummary } from '../lib/types'
import { useKept, useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Card, LinkButton, Loading, Select } from '../ui/kit'
import { RangePicker } from '../ui/RangePicker'
import { ExpenseForm, ReversalForm } from './CashflowPage'

type Source = 'all' | 'po' | 'direct'

const METHOD_LABEL = { cash: 'Tunai', transfer: 'Transfer' } as const

/** "Dibuat Rina (staf) · Transfer · lunas": who opened the PO, how it was paid, payment state. */
function poSubline(e: Expense): string {
  const po = e.purchase_order
  if (!po) return `oleh ${e.recorded_by ?? 'Owner'}`
  const state = po.payment_term === 'pay_in_advance' ? 'di muka'
    : po.payment_status === 'paid' ? 'lunas' : po.payment_status === 'partially_paid' ? 'sebagian' : 'belum dibayar'
  const who = po.created_by ? `Dibuat ${po.created_by}${po.created_by_role === 'staff' ? ' (staf)' : ''}` : 'Dibuat —'
  return [who, e.payment_method ? METHOD_LABEL[e.payment_method] : null, state].filter(Boolean).join(' · ')
}

export default function ExpensesPage() {
  const { api, me } = useSession()
  const navigate = useNavigate()
  const [outletId, setOutletId] = useState('')
  const [range, setRange] = useState<{ from: string; to: string }>()
  const [source, setSource] = useState<Source>('all')
  const [version, setVersion] = useState(0)
  const base = new URLSearchParams()
  if (outletId) base.set('outlet_id', outletId)
  if (range) {
    base.set('from', range.from)
    base.set('to', range.to)
  }
  const baseQuery = base.toString()
  const summary = useLoad(() => api.get<ExpenseSummary>(`/owner/expenses/summary?${baseQuery}`), `${baseQuery}#${version}`)
  // While a save, reversal, outlet or period change reloads the summary, keep showing the last one
  // so the page (and the form's "tersimpan" message) stays put; a failed reload clears it.
  const s = useKept(summary.data, !summary.error)
  const refreshing = summary.loading && !summary.data
  // The summary resolves an unset period to month to date; the history must list the same period
  // the KPI cards, chip counts and RangePicker show, so it gets the summary's from/to (or the
  // picked range if the summary failed). It waits for the first summary to avoid a double fetch.
  const history = new URLSearchParams()
  if (outletId) history.set('outlet_id', outletId)
  const period = s ?? range
  if (period) {
    history.set('from', period.from)
    history.set('to', period.to)
  }
  const historyQuery = history.toString()
  const historyReady = Boolean(s) || Boolean(summary.error)

  return (
    <>
      <PageHeader title="Pengeluaran" />
      <div className="space-y-4 p-4 md:p-6">
        <div className="flex flex-wrap items-center gap-2 text-[12px]">
          <Select aria-label="Outlet" className="h-8 w-auto" value={outletId} onChange={(e) => setOutletId(e.target.value)}>
            <option value="">Semua outlet</option>
            {me.outlets.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </Select>
          <RangePicker value={s ? { from: s.from, to: s.to } : range} onChange={setRange} />
        </div>
        {summary.error ? <Alert>Ringkasan belum bisa dimuat: {errorMessage(summary.error)}</Alert> : null}
        {s ? (
          <div aria-busy={refreshing} className={`grid gap-3 transition-opacity sm:grid-cols-2 xl:grid-cols-4 ${refreshing ? 'opacity-60' : ''}`}>
            <Kpi label="Total pengeluaran" amount={s.total.amount} caption={`${s.total.count} entri · ${formatRange(s.from, s.to, false)}`} accent="border-l-action" />
            <Kpi label="Pembayaran PO (supplier)" amount={s.po.amount} highlight
              caption={`${pct(s.po.amount, s.total.amount)}% dari total · ${s.po.po_count} PO`} />
            <Kpi label="Pengeluaran langsung" amount={s.direct.amount} accent="border-l-text-muted"
              caption={`${pct(s.direct.amount, s.total.amount)}% dari total · ${s.direct.count} entri`} />
            <Kpi label="Hutang PO belum dibayar" amount={s.po_owed.amount} tone="warning" accent="border-l-warning"
              caption={`${s.po_owed.count} PO${s.po_owed.overdue_count ? ` · ${s.po_owed.overdue_count} lewat jatuh tempo` : ''}`} />
          </div>
        ) : summary.loading ? <Loading /> : null}
        <div className="grid gap-4 lg:grid-cols-3">
          {historyReady ? (
            <History className="lg:col-span-2" baseQuery={historyQuery} source={source} onSource={setSource} summary={s} version={version}
              onViewPo={(id) => navigate(`/dashboard?tab=po&po=${id}`)} onChanged={() => { setVersion((v) => v + 1) }} />
          ) : <div className="lg:col-span-2" />}
          <div className="space-y-4">
            {s && <BySupplier summary={s} onOpen={() => navigate('/dashboard?tab=po')} />}
            <ExpenseForm defaultOutletId={outletId || me.outlets[0]?.id || ''} onSaved={() => setVersion((v) => v + 1)} />
            <p className="rounded-md bg-primary-soft p-3 text-[11px] text-primary">
              Pembayaran PO tidak dicatat di sini — pakai “Catat pembayaran” di Dashboard › PO &amp; Supplier.
            </p>
          </div>
        </div>
      </div>
    </>
  )
}

function pct(part: number, whole: number): number {
  return whole ? Math.round((part / whole) * 100) : 0
}

function Kpi({ label, amount, caption, highlight, accent, tone }: {
  label: string
  amount: number
  caption: string
  highlight?: boolean
  accent?: string
  tone?: 'warning'
}) {
  return (
    <div className={`rounded-lg border p-4 ${highlight ? 'border-primary bg-primary text-white' : `border-border bg-surface border-l-4 ${accent ?? ''}`}`}>
      <p className={`text-[12px] ${highlight ? 'font-semibold' : 'text-text-muted'}`}>{label}</p>
      <p className={`mt-1 text-[20px] font-bold ${tone === 'warning' ? 'text-warning' : ''}`}>{formatRupiah(amount)}</p>
      <p className={`mt-1 text-[11px] ${highlight ? 'text-white/80' : tone === 'warning' ? 'text-warning' : 'text-text-muted'}`}>{caption}</p>
    </div>
  )
}

function BySupplier({ summary, onOpen }: { summary: ExpenseSummary; onOpen: () => void }) {
  const max = Math.max(...summary.by_supplier.map((x) => x.amount), 1)
  return (
    <Card title="Pengeluaran PO per supplier">
      <p className="-mt-2 mb-3 text-[11px] text-text-muted">
        Dibayar {formatRange(summary.from, summary.to, false)} · total {formatRupiah(summary.po.amount)}
      </p>
      <ul className="space-y-3 text-[12px]">
        {summary.by_supplier.map((x) => (
          <li key={x.supplier.id}>
            <div className="flex justify-between"><span>{x.supplier.name}</span><span className="font-semibold">{formatRupiah(x.amount)}</span></div>
            <div className="mt-1 h-2 rounded-full bg-primary-soft">
              <div className="h-2 rounded-full bg-primary" style={{ width: `${Math.round((x.amount / max) * 100)}%` }} />
            </div>
          </li>
        ))}
        {summary.by_supplier.length === 0 && <li className="text-text-muted">Belum ada pembayaran PO di periode ini.</li>}
      </ul>
      <LinkButton className="mt-3 text-[12px] font-semibold" onClick={onOpen}>Buka Dashboard › PO &amp; Supplier →</LinkButton>
    </Card>
  )
}

function History({ baseQuery, source, onSource, summary, version, onViewPo, onChanged, className = '' }: {
  baseQuery: string
  source: Source
  onSource: (s: Source) => void
  summary: ExpenseSummary | undefined
  version: number
  onViewPo: (poId: string) => void
  onChanged: () => void
  className?: string
}) {
  const { api } = useSession()
  // Pages fetched with "Muat lagi", tagged with the query they belong to, so a filter change
  // (chip, outlet, period, save/reversal) drops them and a late response for an old query is ignored.
  const [extra, setExtra] = useState<{ key: string; items: Expense[]; cursor: string | null }>()
  const [moreState, setMoreState] = useState<{ key: string; loading: boolean; error?: unknown }>()
  const [reversing, setReversing] = useState<number>()
  const query = new URLSearchParams(baseQuery)
  query.set('limit', '20')
  if (source !== 'all') query.set('source', source)
  const key = `${query.toString()}#${version}`
  const keyRef = useRef(key)
  useEffect(() => {
    keyRef.current = key
  })
  const first = useLoad(() => api.get<ExpensePage>(`/owner/expenses?${query.toString()}`), key)
  // Keep the last rows on screen while a reload runs; "Muat lagi" waits for the fresh page.
  const shown = useKept(first.data, !first.error)
  const own = extra?.key === key ? extra : undefined
  const more = moreState?.key === key ? moreState : undefined
  const cursor = first.data ? (own ? own.cursor : first.data.next_cursor) : null
  const items = [...(shown?.items ?? []), ...(own?.items ?? [])]
  const count = (n: number | undefined) => (n === undefined ? '' : ` (${n})`)
  const chips: [Source, string][] = [
    // Counts come from the summary, which leaves reversed expenses out; the list still shows them.
    // The PO chip counts payments (= rows), not POs.
    ['all', `Semua${count(summary?.total.count)}`],
    ['po', `PO supplier${count(summary?.po.count)}`],
    ['direct', `Langsung${count(summary?.direct.count)}`],
  ]

  async function loadMore() {
    if (!cursor || more?.loading) return
    const k = key
    setMoreState({ key: k, loading: true })
    try {
      const page = await api.get<ExpensePage>(`/owner/expenses?${query.toString()}&cursor=${encodeURIComponent(cursor)}`)
      if (keyRef.current !== k) return
      setExtra((prev) => ({
        key: k,
        items: [...(prev?.key === k ? prev.items : []), ...page.items],
        cursor: page.next_cursor,
      }))
      setMoreState({ key: k, loading: false })
    } catch (error) {
      if (keyRef.current === k) setMoreState({ key: k, loading: false, error })
    }
  }

  return (
    <Card className={className} title="Riwayat pengeluaran">
      <div role="group" aria-label="Sumber" className="mb-3 flex flex-wrap gap-2 text-[12px]">
        {chips.map(([k, label]) => (
          <button key={k} type="button" aria-pressed={source === k} onClick={() => onSource(k)}
            className={`h-7 rounded-full border px-3 ${source === k ? 'border-transparent bg-primary-soft font-semibold text-primary'
              : k === 'po' ? 'border-primary bg-surface font-semibold text-primary' : 'border-border bg-surface text-text-muted'}`}>
            {label}
          </button>
        ))}
      </div>
      {first.error ? <Alert>Riwayat belum bisa dimuat: {errorMessage(first.error)}</Alert> : null}
      {!shown ? (first.loading ? <Loading /> : null) : (
        <div aria-busy={first.loading} className={`overflow-x-auto transition-opacity ${first.loading ? 'opacity-60' : ''}`}>
          <table className="w-full text-left text-[12px]">
            <thead className="text-[11px] uppercase text-text-muted">
              <tr>
                <th className="py-2 pr-2 font-semibold">Tanggal</th>
                <th className="py-2 pr-2 font-semibold">Keterangan</th>
                <th className="py-2 pr-2 font-semibold">Sumber</th>
                <th className="py-2 pr-2 font-semibold">Outlet</th>
                <th className="py-2 pr-2 text-right font-semibold">Nominal</th>
                <th className="py-2 font-semibold">Aksi</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => {
                const po = e.purchase_order
                return (
                  <tr key={e.id} className={`border-t border-border align-top ${po ? 'bg-primary-soft/40' : ''}`}>
                    <td className="whitespace-nowrap py-2 pr-2">{formatDay(e.business_date)}</td>
                    <td className="py-2 pr-2">
                      <p className={`text-[13px] font-semibold ${e.reversed ? 'text-text-muted line-through' : ''}`}>
                        {po ? `${po.number} · ${po.supplier.name}` : e.description}
                      </p>
                      <p className="text-[11px] text-text-muted">{poSubline(e)}</p>
                      {e.reversed && <p className="text-[11px] text-text-muted">Di-reversal: {e.reversal_reason}</p>}
                      {reversing === e.id && (
                        <ReversalForm expense={e} onCancel={() => setReversing(undefined)}
                          onDone={() => { setReversing(undefined); onChanged() }} />
                      )}
                    </td>
                    <td className="py-2 pr-2">
                      <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] ${po ? 'bg-primary font-bold text-white' : 'bg-page text-text-muted'}`}>
                        {po ? 'PO' : 'Langsung'}
                      </span>
                    </td>
                    <td className="whitespace-nowrap py-2 pr-2">{shortOutlet(e.outlet.name)}</td>
                    <td className={`whitespace-nowrap py-2 pr-2 text-right text-[13px] font-semibold ${e.reversed ? 'text-text-muted line-through' : 'text-[#9A3412]'}`}>
                      {formatRupiah(-e.amount)}
                    </td>
                    <td className="whitespace-nowrap py-2">
                      {po ? <LinkButton className="text-[11px] font-semibold" onClick={() => onViewPo(po.id)}>Lihat PO →</LinkButton>
                        : !e.reversed && reversing !== e.id
                          ? <LinkButton className="text-[11px] text-text-muted" onClick={() => setReversing(e.id)}>Reversal</LinkButton> : null}
                    </td>
                  </tr>
                )
              })}
              {items.length === 0 && (
                <tr><td colSpan={6} className="py-3 text-text-muted">Belum ada pengeluaran.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {more?.error ? <Alert>Halaman berikutnya belum bisa dimuat: {errorMessage(more.error)}</Alert> : null}
      {cursor && (
        <LinkButton className="mt-2 text-[12px]" disabled={more?.loading} onClick={() => void loadMore()}>
          Muat lagi
        </LinkButton>
      )}
      <p className="mt-3 text-[11px] text-text-muted">
        Baris PO berasal dari “Catat pembayaran” di PO (tidak bisa diedit/dibalik di sini). Pengeluaran langsung: koreksi lewat reversal. Angka di filter tidak menghitung entri yang sudah di-reversal.
      </p>
    </Card>
  )
}
