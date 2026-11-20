// Wireframe O9 — Laporan Cashflow & Pengeluaran (T-041, T-042, T-043). Owner only.
// Endpoints: GET /owner/reports/cashflow?outlet_id=&granularity=&from=&to=, GET /owner/expenses,
// POST /owner/expenses (Idempotency-Key), POST /owner/ledger-entries/{id}/reversal.
// Canvas notes: figures come from the ledger and day boundaries follow each outlet's time zone;
// PB1 is "titipan pajak, bukan pendapatan"; expenses cannot be edited or deleted — a mistake is
// corrected with a reversal entry. The sidebar item "Pengeluaran" has its own screen, O9b
// (ExpensesPage); "Lihat semua" here opens this card's full list in place.
import { useState } from 'react'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { MONTHS, formatDay, formatRange, formatRupiah, formatSignedRupiah, shortOutlet, todayIn } from '../lib/format'
import type { Cashflow, Expense, ExpensePage, Granularity, Tile } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Card, Field, LinkButton, Loading, Select, TextInput } from '../ui/kit'
import { RangePicker } from '../ui/RangePicker'

/** Server cap per expense entry (ledger.EXPENSE_MAX). */
const EXPENSE_MAX = 1_000_000_000

const GRANULARITY: { key: Granularity; label: string }[] = [
  { key: 'daily', label: 'Harian' },
  { key: 'weekly', label: 'Mingguan' },
  { key: 'monthly', label: 'Bulanan' },
]

const SERIES_TITLE: Record<Granularity, string> = {
  daily: 'Kas masuk vs kas keluar per hari',
  weekly: 'Kas masuk vs kas keluar per minggu',
  monthly: 'Kas masuk vs kas keluar per bulan',
}

export default function CashflowPage() {
  const { api, me } = useSession()
  const [outletId, setOutletId] = useState('')
  const [granularity, setGranularity] = useState<Granularity>('daily')
  const [range, setRange] = useState<{ from: string; to: string }>()
  const params = new URLSearchParams({ granularity })
  if (outletId) params.set('outlet_id', outletId)
  if (range) {
    params.set('from', range.from)
    params.set('to', range.to)
  }
  const query = params.toString()
  const report = useLoad(() => api.get<Cashflow>(`/owner/reports/cashflow?${query}`), query)
  const [expensesVersion, setExpensesVersion] = useState(0)
  // "Lihat semua →" (Pengeluaran terbaru) and "Lihat semua pengeluaran →" (per outlet) open the
  // full list in the Pengeluaran terbaru card.
  const [allExpenses, setAllExpenses] = useState(false)
  const r = report.data

  return (
    <>
      <PageHeader title="Laporan Cashflow" />
      <div className="space-y-4 p-4 md:p-6">
        <div className="flex flex-wrap items-center gap-2 text-[12px]">
          <Select aria-label="Outlet" className="h-8 w-auto" value={outletId} onChange={(e) => setOutletId(e.target.value)}>
            <option value="">Semua outlet</option>
            {me.outlets.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </Select>
          <div role="group" aria-label="Periode" className="flex overflow-hidden rounded-md border border-border">
            {GRANULARITY.map((g) => (
              <button key={g.key} type="button" aria-pressed={granularity === g.key} onClick={() => setGranularity(g.key)}
                className={`h-8 px-3 ${granularity === g.key ? 'bg-primary-soft font-semibold text-primary' : 'bg-surface text-text'}`}>
                {g.label}
              </button>
            ))}
          </div>
          <RangePicker value={r ? { from: r.from, to: r.to } : range} onChange={setRange} />
        </div>
        {report.error ? <Alert>Laporan belum bisa dimuat: {errorMessage(report.error)}</Alert> : null}
        {!r ? (report.loading ? <Loading /> : null) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Kpi label="Kas masuk" tile={r.totals.cash_in} previous={r.previous} />
              <Kpi label="Kas keluar" tile={r.totals.cash_out} previous={r.previous} />
              <Kpi label="Kas bersih" tile={r.totals.net} previous={r.previous} />
              <div className="rounded-lg border border-border bg-surface p-4">
                <p className="text-[12px] text-text-muted">PB1 terkumpul</p>
                <p className="mt-1 text-[20px] font-bold">{formatRupiah(r.totals.pb1_collected.amount)}</p>
                <p className="mt-1 text-[11px] text-text-muted">Titipan pajak, bukan pendapatan</p>
              </div>
            </div>
            <div className="grid gap-4 lg:grid-cols-3">
              <Card className="lg:col-span-2" title={SERIES_TITLE[r.granularity]}>
                <p className="-mt-2 mb-2 text-[11px] text-text-muted">
                  {periodCaption(r.from, r.to)} · dari ledger · batas hari mengikuti zona waktu tiap outlet
                </p>
                <SeriesChart series={r.series} granularity={r.granularity} />
              </Card>
              <Card title="Pengeluaran per outlet">
                <p className="-mt-2 mb-3 text-[11px] text-text-muted">
                  Total {formatRupiah(r.expenses_total)} · {r.expenses_count} entri
                </p>
                <ul className="space-y-2 text-[12px]">
                  {r.expenses_by_outlet.map((e) => (
                    <li key={e.outlet_id}>
                      <div className="flex justify-between"><span>{e.outlet}</span><span>{formatRupiah(e.amount)}</span></div>
                      <div className="mt-1 h-1.5 rounded-full bg-page">
                        <div className="h-1.5 rounded-full bg-accent-orange"
                          style={{ width: `${r.expenses_total ? Math.max(2, (e.amount / r.expenses_total) * 100) : 0}%` }} />
                      </div>
                    </li>
                  ))}
                  {r.expenses_by_outlet.length === 0 && <li className="text-text-muted">Belum ada pengeluaran di periode ini.</li>}
                </ul>
                <LinkButton className="mt-3 text-[12px]" onClick={() => {
                  setAllExpenses(true)
                  document.getElementById('recent-expenses')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
                }}>Lihat semua pengeluaran →</LinkButton>
              </Card>
            </div>
          </>
        )}
        <div className="grid gap-4 lg:grid-cols-3">
          {r && <BreakdownCard r={r} />}
          <RecentExpenses outletId={outletId} version={expensesVersion} all={allExpenses} onShowAll={() => setAllExpenses(true)}
            onChanged={() => { setExpensesVersion((v) => v + 1); void report.reload() }} />
          <ExpenseForm defaultOutletId={outletId || me.outlets[0]?.id || ''} onSaved={() => {
            setExpensesVersion((v) => v + 1)
            void report.reload()
          }} />
        </div>
      </div>
    </>
  )
}

function Kpi({ label, tile, previous }: { label: string; tile: Tile; previous: { from: string; to: string } }) {
  const pct = tile.change_pct
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="text-[12px] text-text-muted">{label}</p>
      <p className="mt-1 text-[20px] font-bold">{formatRupiah(tile.amount)}</p>
      <p className={`mt-1 text-[11px] ${pct === null ? 'text-text-muted' : pct >= 0 ? 'text-success' : 'text-danger'}`}>
        {pct === null ? '—' : `${pct >= 0 ? '▲' : '▼'} ${Math.abs(pct)}%`} vs {formatRange(previous.from, previous.to, false)}
      </p>
    </div>
  )
}

function juta(value: number): string {
  if (value === 0) return '0'
  if (value >= 1_000_000) return `${(value / 1_000_000).toLocaleString('id-ID', { maximumFractionDigits: 1 })} jt`
  return `${(value / 1000).toLocaleString('id-ID', { maximumFractionDigits: 0 })} rb`
}

function niceStep(max: number): number {
  const raw = max / 4
  const power = 10 ** Math.floor(Math.log10(raw || 1))
  return [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? power * 10
}

/** "Nov 2026" when the range sits in one month (as drawn), else the range itself. */
function periodCaption(from: string, to: string): string {
  if (from.slice(0, 7) !== to.slice(0, 7)) return formatRange(from, to)
  return `${MONTHS[Number(to.slice(5, 7)) - 1]} ${to.slice(0, 4)}`
}

// Grouped bars per period, as drawn on O9: kas masuk (primary) next to kas keluar (orange),
// with the value written above the highest kas masuk bar.
function SeriesChart({ series, granularity }: { series: Cashflow['series']; granularity: Granularity }) {
  const W = 600
  const H = 200
  const pad = { l: 44, r: 8, t: 16, b: 22 }
  const peak = Math.max(0, ...series.flatMap((p) => [p.cash_in, p.cash_out]))
  const step = niceStep(peak)
  const top = peak === 0 ? step * 4 : Math.ceil(peak / step) * step
  const slot = (W - pad.l - pad.r) / Math.max(1, series.length)
  const bar = Math.max(2, Math.min(14, (slot - 4) / 2))
  const center = (i: number) => pad.l + slot * (i + 0.5)
  const y = (v: number) => pad.t + (1 - v / top) * (H - pad.t - pad.b)
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step)
  const every = Math.max(1, Math.ceil(series.length / 9))
  const label = (d: string) => granularity === 'daily' ? String(Number(d.slice(8))) : formatDay(d)
  const peakIn = series.reduce((best, p, i) => (p.cash_in > (series[best]?.cash_in ?? 0) ? i : best), 0)
  return (
    <div>
      <div className="mb-1 flex gap-4 text-[11px]">
        <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-primary" />Kas masuk</span>
        <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-accent-orange" />Kas keluar</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Grafik kas masuk dan kas keluar">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="var(--pos-border)" strokeWidth="1" />
            <text x={pad.l - 6} y={y(t) + 3} textAnchor="end" fontSize="10" fill="var(--pos-text-muted)">{juta(t)}</text>
          </g>
        ))}
        {series.map((p, i) => (
          <g key={p.date} data-testid="series-bar">
            <rect x={center(i) - bar} y={y(p.cash_in)} width={bar} height={y(0) - y(p.cash_in)} rx="2" fill="var(--pos-primary)">
              <title>{`${label(p.date)} · Kas masuk ${formatRupiah(p.cash_in)}`}</title>
            </rect>
            <rect x={center(i)} y={y(p.cash_out)} width={bar} height={y(0) - y(p.cash_out)} rx="2" fill="var(--pos-accent-orange)">
              <title>{`${label(p.date)} · Kas keluar ${formatRupiah(p.cash_out)}`}</title>
            </rect>
            {i % every === 0 && (
              <text x={center(i)} y={H - 6} textAnchor="middle" fontSize="10" fill="var(--pos-text-muted)">{label(p.date)}</text>
            )}
          </g>
        ))}
        {series[peakIn]?.cash_in > 0 && (
          <text x={center(peakIn) - bar / 2} y={y(series[peakIn].cash_in) - 4} textAnchor="middle" fontSize="10"
            fontWeight="600" fill="var(--pos-text)">{juta(series[peakIn].cash_in)}</text>
        )}
      </svg>
    </div>
  )
}

function BreakdownCard({ r }: { r: Cashflow }) {
  const b = r.breakdown
  const methods = b.cash + b.qris
  const share = (v: number) => (methods ? Math.round((v / methods) * 100) : 0)
  const row = (label: string, value: string, strong = false) => (
    <div className={`flex justify-between py-0.5 ${strong ? 'font-semibold' : ''}`}><span>{label}</span><span>{value}</span></div>
  )
  return (
    <Card title="Rincian kas periode">
      <div className="space-y-2 text-[12px]">
        <p className="text-[11px] font-semibold tracking-wide text-text-muted">KAS MASUK</p>
        {row('Revenue (excl. PB1)', formatRupiah(b.revenue_excl_pb1))}
        {row('PB1 (titipan pajak)', formatRupiah(b.pb1))}
        {row('Delivery fee', formatRupiah(b.delivery_fee))}
        <p className="text-[11px] text-text-muted">
          Cash {juta(b.cash)} ({share(b.cash)}%) · QRIS {juta(b.qris)} ({share(b.qris)}%)
        </p>
        <p className="pt-1 text-[11px] font-semibold tracking-wide text-text-muted">KAS KELUAR</p>
        {row('Refund / reversal', formatRupiah(-b.refunds))}
        {row('Pengeluaran', formatRupiah(-b.expenses))}
        {row('Selisih kas (surplus − shortage)', formatSignedRupiah(b.cash_difference))}
        <div className="border-t border-border pt-1">{row('Kas bersih', formatRupiah(r.totals.net.amount), true)}</div>
      </div>
    </Card>
  )
}

function RecentExpenses({ outletId, version, all, onShowAll, onChanged }: {
  outletId: string
  version: number
  all: boolean
  onShowAll: () => void
  onChanged: () => void
}) {
  const { api } = useSession()
  const [more, setMore] = useState<Expense[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [reversing, setReversing] = useState<number>()
  const limit = all ? 20 : 5
  const query = new URLSearchParams({ limit: String(limit) })
  if (outletId) query.set('outlet_id', outletId)
  const key = `${query.toString()}#${version}`
  const first = useLoad(async () => {
    const page = await api.get<ExpensePage>(`/owner/expenses?${query.toString()}`)
    setMore([])
    setCursor(page.next_cursor)
    return page
  }, key)
  const items = [...(first.data?.items ?? []), ...more]

  async function loadMore() {
    if (!cursor) return
    const page = await api.get<ExpensePage>(`/owner/expenses?${query.toString()}&cursor=${encodeURIComponent(cursor)}`)
    setMore((m) => [...m, ...page.items])
    setCursor(page.next_cursor)
  }

  return (
    <Card id="recent-expenses" title="Pengeluaran terbaru" actions={!all ? <LinkButton onClick={onShowAll}>Lihat semua →</LinkButton> : null}>
      {first.loading && !first.data ? <Loading /> : (
        <ul className="divide-y divide-border text-[12px]">
          {items.map((e) => (
            <li key={e.id} className="py-2">
              <div className="flex items-start justify-between gap-2">
                <div className={e.reversed ? 'text-text-muted line-through' : ''}>
                  <p className="font-medium">{e.description}</p>
                  <p className="text-[11px] text-text-muted">
                    {formatDay(e.business_date)} · {shortOutlet(e.outlet.name)} · oleh {e.recorded_by ?? 'Owner'}
                  </p>
                </div>
                <span className={`whitespace-nowrap ${e.reversed ? 'text-text-muted line-through' : ''}`}>{formatRupiah(-e.amount)}</span>
              </div>
              {e.reversed ? (
                <p className="text-[11px] text-text-muted">Di-reversal: {e.reversal_reason}</p>
              ) : all && (reversing === e.id ? (
                <ReversalForm expense={e} onCancel={() => setReversing(undefined)}
                  onDone={() => { setReversing(undefined); onChanged() }} />
              ) : (
                <LinkButton className="text-[11px]" onClick={() => setReversing(e.id)}>Buat entry reversal</LinkButton>
              ))}
            </li>
          ))}
          {items.length === 0 && <li className="py-2 text-text-muted">Belum ada pengeluaran.</li>}
        </ul>
      )}
      {all && cursor && <LinkButton className="mt-2 text-[12px]" onClick={() => void loadMore()}>Muat lagi</LinkButton>}
      <p className="mt-3 text-[11px] text-text-muted">Tidak bisa diedit/dihapus. Koreksi lewat reversal.</p>
    </Card>
  )
}

export function ReversalForm({ expense, onCancel, onDone }: { expense: Expense; onCancel: () => void; onDone: () => void }) {
  const { api } = useSession()
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  return (
    <div className="mt-2 space-y-2 rounded-md bg-page p-2">
      <TextInput aria-label={`Alasan reversal ${expense.description}`} placeholder="Alasan reversal (wajib)…" maxLength={300}
        value={reason} onChange={(e) => setReason(e.target.value)} className="h-8" />
      {error && <Alert>{error}</Alert>}
      <div className="flex gap-2">
        <Button variant="danger" className="h-8" disabled={!reason.trim() || busy} onClick={async () => {
          setBusy(true)
          setError(undefined)
          try {
            await api.post(`/owner/ledger-entries/${expense.id}/reversal`, { reason: reason.trim() })
            onDone()
          } catch (e) {
            setError(errorMessage(e))
          } finally {
            setBusy(false)
          }
        }}>Buat reversal {formatRupiah(expense.amount)}</Button>
        <LinkButton onClick={onCancel}>Batal</LinkButton>
      </div>
    </div>
  )
}

export function ExpenseForm({ defaultOutletId, onSaved }: { defaultOutletId: string; onSaved: () => void }) {
  const { api, me } = useSession()
  const [outletId, setOutletId] = useState('')
  const chosen = outletId || defaultOutletId
  const timezone = me.outlets.find((o) => o.id === chosen)?.timezone ?? 'Asia/Jakarta'
  const today = todayIn(timezone)
  const [amount, setAmount] = useState('')
  const [day, setDay] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string }>()
  const [key, setKey] = useState(() => crypto.randomUUID())
  const tooLarge = Number(amount) > EXPENSE_MAX

  async function save() {
    setBusy(true)
    setNotice(undefined)
    try {
      await api.post('/owner/expenses', {
        outlet_id: chosen,
        amount: Number(amount),
        business_date: day || today,
        description: description.trim(),
      }, { 'Idempotency-Key': `expense-${key}` })
      setAmount('')
      setDescription('')
      setKey(crypto.randomUUID())
      setNotice({ tone: 'success', text: 'Pengeluaran tersimpan di ledger.' })
      onSaved()
    } catch (e) {
      setNotice({ tone: 'danger', text: errorMessage(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Catat pengeluaran" actions={<span className="rounded-full bg-primary-soft px-2 py-0.5 text-[11px] text-primary">Owner</span>}>
      <Field label="Outlet" htmlFor="expense-outlet">
        <Select id="expense-outlet" value={chosen} onChange={(e) => setOutletId(e.target.value)}>
          {me.outlets.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </Select>
      </Field>
      <Field label="Nominal" htmlFor="expense-amount">
        <TextInput id="expense-amount" inputMode="numeric" placeholder="Rp 0"
          value={amount ? `Rp ${Number(amount).toLocaleString('id-ID')}` : ''}
          onChange={(e) => setAmount(e.target.value.replace(/\D/g, '').replace(/^0+/, '').slice(0, 10))} />
        {tooLarge && <p className="mt-1 text-[11px] text-danger">Maksimal {formatRupiah(EXPENSE_MAX)} per entri.</p>}
      </Field>
      <Field label="Tanggal" htmlFor="expense-date">
        <TextInput id="expense-date" type="date" max={today} value={day || today} onChange={(e) => setDay(e.target.value)} />
      </Field>
      <Field label="Deskripsi" htmlFor="expense-desc">
        <TextInput id="expense-desc" maxLength={120} placeholder="mis. Beli es batu & gas" value={description}
          onChange={(e) => setDescription(e.target.value)} />
      </Field>
      {notice && <div className="mb-2"><Alert tone={notice.tone}>{notice.text}</Alert></div>}
      <Button variant="action" className="w-full" disabled={busy || !chosen || !Number(amount) || tooLarge || !description.trim()}
        onClick={() => void save()}>
        Simpan pengeluaran
      </Button>
      <p className="mt-2 text-[11px] text-text-muted">Tersimpan permanen di ledger. Salah input? Buat entry reversal, bukan edit.</p>
    </Card>
  )
}
