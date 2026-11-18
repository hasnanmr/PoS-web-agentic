// Wireframe S1 / M2 — Counter / POS (T-038, T-067).
// Endpoints: GET /ops/outlets/{id}/menu, /tables, /shifts/current; POST /quotes (server is the
// only source of prices and PB1); POST /orders with Idempotency-Key.
// Behavior notes from the canvas: required add-on groups must be chosen before "Tambah";
// options without enough stock show "unavailable"; Cash only with an open shift, otherwise
// disabled with a "Buka shift" link.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { ROUTES } from '../app/nav'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { formatRupiah, formatTime } from '../lib/format'
import type { MenuItem, OrderCreated, Quote, ShiftRow, TableRow } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Loading, Select, TextInput } from '../ui/kit'

interface CartLine {
  key: string
  item: MenuItem
  optionIds: string[]
  quantity: number
}

type Method = 'open_bill' | 'cash' | 'qris'

function newKey(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `k-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function addonText(line: CartLine): string {
  const names = line.item.addon_groups.flatMap((g) => g.options)
    .filter((o) => line.optionIds.includes(o.id))
    .map((o) => (o.price ? `${o.name} (+${o.price.toLocaleString('id-ID')})` : o.name))
  return names.length ? `+ ${names.join(', ')}` : ''
}

export default function CounterPage() {
  const { api, outlet } = useSession()
  const outletId = outlet?.id ?? ''
  const menu = useLoad(() => api.get<MenuItem[]>(`/ops/outlets/${outletId}/menu`), outletId)
  const tables = useLoad(() => api.get<TableRow[]>(`/ops/outlets/${outletId}/tables`), outletId)
  const shifts = useLoad(() => api.get<ShiftRow[]>(`/ops/outlets/${outletId}/shifts/current`), outletId)

  const [q, setQ] = useState('')
  const [tab, setTab] = useState<string>('all')
  const [type, setType] = useState<'dine_in' | 'takeaway'>('dine_in')
  const [tableId, setTableId] = useState('')
  const [cart, setCart] = useState<CartLine[]>([])
  const [picking, setPicking] = useState<MenuItem>()
  const [method, setMethod] = useState<Method>()
  const [received, setReceived] = useState('')
  const [quote, setQuote] = useState<Quote>()
  const [quoteError, setQuoteError] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string }>()
  const [idemKey, setIdemKey] = useState(newKey)
  const searchRef = useRef<HTMLInputElement>(null)

  const openBillOutlet = outlet?.payment_mode === 'open_bill'
  const toBill = type === 'dine_in' && openBillOutlet
  const shift = shifts.data?.[0]
  const effectiveMethod: Method | undefined = toBill ? 'open_bill' : method === 'open_bill' ? undefined : method

  const items = useMemo(() => cart.map((l) => ({
    product_id: l.item.product_id, quantity: l.quantity, addon_option_ids: l.optionIds,
  })), [cart])

  useEffect(() => {
    if (!outletId || items.length === 0) return
    let active = true
    api.post<Quote>(`/ops/outlets/${outletId}/quotes`, { type, items }).then(
      (result) => { if (active) { setQuote(result); setQuoteError(undefined) } },
      (e: unknown) => { if (active) { setQuote(undefined); setQuoteError(errorMessage(e)) } },
    )
    return () => { active = false }
  }, [api, outletId, type, items])

  const total = items.length ? quote?.total ?? 0 : 0
  const cashReceived = Number(received.replace(/\D/g, '') || 0)
  const change = effectiveMethod === 'cash' && cashReceived >= total ? cashReceived - total : null
  const canSubmit = !busy && cart.length > 0 && Boolean(quote) && Boolean(effectiveMethod) &&
    (!toBill || Boolean(tableId)) && (effectiveMethod !== 'cash' || (Boolean(shift) && cashReceived >= total))

  const submit = useCallback(async () => {
    if (!canSubmit || !outlet) return
    setBusy(true)
    setNotice(undefined)
    try {
      const payment = effectiveMethod === 'open_bill' ? { to_open_bill: true }
        : effectiveMethod === 'cash' ? { method: 'cash', cash_received: cashReceived } : { method: 'qris' }
      const created = await api.post<OrderCreated>(`/ops/outlets/${outlet.id}/orders`, {
        type, table_id: type === 'dine_in' && tableId ? tableId : null, items, payment,
      }, { 'Idempotency-Key': idemKey })
      const extra = created.change_due != null ? ` · Kembalian ${formatRupiah(created.change_due)}`
        : created.bill_id ? ' · masuk open bill' : ''
      setNotice({ tone: 'success', text: `Order ${created.order_no} dibuat · ${formatRupiah(created.total)}${extra}` })
      setCart([])
      setReceived('')
      setQuote(undefined)
      setIdemKey(newKey())
      await Promise.all([menu.reload(), tables.reload()])
    } catch (e) {
      setNotice({ tone: 'danger', text: errorMessage(e) })
    } finally {
      setBusy(false)
    }
  }, [canSubmit, outlet, effectiveMethod, cashReceived, api, type, tableId, items, idemKey, menu, tables])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'F2') { e.preventDefault(); searchRef.current?.focus() }
      if (e.key === 'F9') { e.preventDefault(); void submit() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [submit])

  function add(item: MenuItem, optionIds: string[]) {
    const key = `${item.product_id}:${[...optionIds].sort().join(',')}`
    setCart((c) => c.some((l) => l.key === key)
      ? c.map((l) => (l.key === key ? { ...l, quantity: l.quantity + 1 } : l))
      : [...c, { key, item, optionIds, quantity: 1 }])
  }

  function change_(key: string, delta: number) {
    setCart((c) => c.flatMap((l) => (l.key !== key ? [l] : l.quantity + delta <= 0 ? [] : [{ ...l, quantity: l.quantity + delta }])))
  }

  if (!outlet) return <PageHeader title="Kasir" />
  const all = menu.data ?? []
  const categories = [...new Set(all.map((m) => m.category).filter(Boolean))] as string[]
  const shown = all.filter((m) => m.name.toLowerCase().includes(q.trim().toLowerCase()) &&
    (tab === 'all' || (tab === 'picks' ? m.is_owner_pick : m.category === tab)))

  return (
    <>
      <PageHeader
        title="Kasir"
        actions={shift ? (
          <span className="text-[12px] text-success">● Shift aktif · Drawer {shift.drawer_number} · {formatTime(shift.opened_at, outlet.timezone)}</span>
        ) : (
          <Link to={ROUTES.shifts.path} className="text-[12px] text-warning hover:underline">○ Belum ada shift · Buka shift</Link>
        )}
      />
      <div className="grid gap-4 p-4 md:p-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <section className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <h2 className="mr-auto text-[15px] font-semibold">Order baru</h2>
            <TextInput ref={searchRef} aria-label="Cari produk" placeholder="⌕  Cari produk (F2)" className="h-9 w-full sm:w-64"
              value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div role="tablist" className="mb-3 flex flex-wrap gap-1 text-[12px]">
            {[['all', 'Semua produk'], ...categories.map((c) => [c, c]), ['picks', "Owner's picks ★"]].map(([value, label]) => (
              <button key={value} type="button" role="tab" aria-selected={tab === value} onClick={() => setTab(value)}
                className={`rounded-full px-3 py-1 ${tab === value ? 'bg-primary text-white' : 'bg-surface text-text hover:bg-primary-soft'}`}>
                {label}
              </button>
            ))}
          </div>
          {menu.loading && !menu.data ? <Loading /> : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {shown.map((m) => (
                <button key={m.product_id} type="button" disabled={m.sold_out}
                  aria-label={`Tambah ${m.name}`}
                  onClick={() => (m.addon_groups.length ? setPicking(m) : add(m, []))}
                  className="relative flex flex-col rounded-lg border border-border bg-surface p-3 text-left hover:border-primary disabled:cursor-not-allowed disabled:opacity-70">
                  <span aria-hidden="true" className="mb-2 h-16 rounded bg-page" />
                  <span className="text-[13px] font-semibold">{m.name}</span>
                  <span className="text-[12px] text-text-muted">{formatRupiah(m.price)}</span>
                  {m.sold_out ? (
                    <>
                      <span className="absolute top-2 left-2 rounded bg-danger px-1.5 py-0.5 text-[10px] font-bold text-white">SOLD OUT</span>
                      <span className="text-[11px] text-danger">{m.sold_out_reason}</span>
                    </>
                  ) : (
                    <span aria-hidden="true" className="absolute right-2 bottom-2 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-white">+</span>
                  )}
                </button>
              ))}
            </div>
          )}
        </section>

        <aside className="h-fit rounded-lg border border-border bg-surface p-4">
          <div className="mb-3 grid grid-cols-2 gap-1 rounded-md bg-page p-1 text-[13px]">
            {(['dine_in', 'takeaway'] as const).map((t) => (
              <button key={t} type="button" aria-pressed={type === t} onClick={() => setType(t)}
                className={`rounded py-1.5 ${type === t ? 'bg-surface font-semibold shadow-sm' : 'text-text-muted'}`}>
                {t === 'dine_in' ? 'Dine-in' : 'Takeaway'}
              </button>
            ))}
          </div>
          {type === 'dine_in' && (
            <label className="mb-3 block text-[12px]">
              <span className="mb-1 block font-semibold">Meja</span>
              <Select aria-label="Meja" value={tableId} onChange={(e) => setTableId(e.target.value)}>
                <option value="">{toBill ? 'Pilih meja' : 'Tanpa meja'}</option>
                {(tables.data ?? []).map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}{t.area ? ` · ${t.area}` : ''}{t.open_bill ? ` — open bill aktif (${formatRupiah(t.open_bill.total)})` : ''}
                  </option>
                ))}
              </Select>
            </label>
          )}

          <ul className="space-y-2">
            {cart.map((l, index) => (
              <li key={l.key} className="flex items-start gap-2 border-b border-border pb-2 text-[12px]">
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">{l.item.name}</div>
                  {addonText(l) && <div className="text-text-muted">{addonText(l)}</div>}
                  <div>{formatRupiah(quote?.lines[index]?.line_total ?? 0)}</div>
                </div>
                <div className="flex items-center gap-2">
                  <button type="button" aria-label={`Kurangi ${l.item.name}`} className="h-6 w-6 rounded border border-border" onClick={() => change_(l.key, -1)}>−</button>
                  <span className="w-5 text-center">{l.quantity}</span>
                  <button type="button" aria-label={`Tambah jumlah ${l.item.name}`} className="h-6 w-6 rounded border border-border" onClick={() => change_(l.key, 1)}>+</button>
                </div>
              </li>
            ))}
            {cart.length === 0 && <li className="py-6 text-center text-[12px] text-text-muted">Keranjang kosong. Pilih produk di kiri.</li>}
          </ul>
          {quoteError && cart.length > 0 && <div className="mt-2"><Alert>{quoteError}</Alert></div>}

          <dl className="mt-3 space-y-1 text-[12px]">
            <div className="flex justify-between"><dt>Subtotal (incl. add-on)</dt><dd>{formatRupiah(items.length ? quote?.subtotal ?? 0 : 0)}</dd></div>
            {(quote?.pb1_rate_bps ?? null) !== null && (
              <div className="flex justify-between"><dt>PB1 {(quote!.pb1_rate_bps! / 100).toLocaleString('id-ID')}%</dt><dd>{formatRupiah(items.length ? quote!.pb1_amount : 0)}</dd></div>
            )}
            <div className="flex justify-between text-[15px] font-bold"><dt>Total</dt><dd>{formatRupiah(total)}</dd></div>
          </dl>

          <div className="mt-3">
            <div className="mb-1 text-[12px] font-semibold">Metode pembayaran</div>
            <div className="grid grid-cols-3 gap-2 text-[12px]">
              <PayButton active={effectiveMethod === 'open_bill'} disabled={!toBill} onClick={() => setMethod('open_bill')}>
                Ke open bill<br /><span className="text-[10px] text-text-muted">(bayar nanti)</span>
              </PayButton>
              <PayButton active={effectiveMethod === 'cash'} disabled={toBill || !shift} onClick={() => setMethod('cash')}>▤ Cash</PayButton>
              <PayButton active={effectiveMethod === 'qris'} disabled={toBill} onClick={() => setMethod('qris')}>▦ QRIS</PayButton>
            </div>
            {!shift && !toBill && (
              <p className="mt-1 text-[11px] text-text-muted">Cash butuh shift kasir terbuka. <Link to={ROUTES.shifts.path} className="text-primary hover:underline">Buka shift</Link></p>
            )}
          </div>
          {effectiveMethod === 'cash' && (
            <div className="mt-3 space-y-2 text-[12px]">
              <label className="flex items-center justify-between gap-2">
                <span>Uang diterima</span>
                <TextInput aria-label="Uang diterima" inputMode="numeric" className="h-8 w-32 text-right"
                  value={received ? Number(received).toLocaleString('id-ID') : ''}
                  onChange={(e) => setReceived(e.target.value.replace(/\D/g, ''))} />
              </label>
              <div className="flex flex-wrap justify-end gap-1">
                {[total, 50000, 100000].filter((v, i, a) => v > 0 && a.indexOf(v) === i).map((v) => (
                  <button key={v} type="button" className="rounded border border-border px-2 py-0.5 hover:bg-page" onClick={() => setReceived(String(v))}>
                    {v === total ? 'Uang pas' : formatRupiah(v)}
                  </button>
                ))}
              </div>
              <div className="flex justify-between font-semibold">
                <span>Kembalian</span><span>{change == null ? '—' : formatRupiah(change)}</span>
              </div>
            </div>
          )}
          {notice && <div className="mt-3"><Alert tone={notice.tone}>{notice.text}</Alert></div>}
          <Button variant="action" className="mt-3 w-full" disabled={!canSubmit} onClick={() => void submit()}>
            {busy ? 'Memproses…' : toBill ? 'Buat order ke open bill (F9)' : 'Buat order & terima bayar (F9)'}
          </Button>
          <button type="button" className="mt-2 w-full text-[12px] text-text-muted hover:text-danger" onClick={() => setCart([])}>
            ✕ Kosongkan keranjang
          </button>
        </aside>
      </div>
      {picking && <AddonModal item={picking} onClose={() => setPicking(undefined)} onAdd={(ids) => { add(picking, ids); setPicking(undefined) }} />}
    </>
  )
}

function PayButton({ active, disabled, onClick, children }: {
  active: boolean
  disabled?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button type="button" aria-pressed={active} disabled={disabled} onClick={onClick}
      className={`min-h-10 rounded-md border px-2 py-1.5 ${active ? 'border-primary bg-primary-soft font-semibold text-primary' : 'border-border'} disabled:cursor-not-allowed disabled:opacity-50`}>
      {children}
    </button>
  )
}

function AddonModal({ item, onClose, onAdd }: { item: MenuItem; onClose: () => void; onAdd: (ids: string[]) => void }) {
  const [chosen, setChosen] = useState<Record<string, string[]>>({})
  const missing = item.addon_groups.some((g) => g.is_required && !(chosen[g.id]?.length))
  function toggle(groupId: string, optionId: string, single: boolean) {
    setChosen((c) => {
      const current = c[groupId] ?? []
      if (single) return { ...c, [groupId]: current[0] === optionId ? [] : [optionId] }
      return { ...c, [groupId]: current.includes(optionId) ? current.filter((x) => x !== optionId) : [...current, optionId] }
    })
  }
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-text/40 p-4 sm:items-center" role="dialog" aria-modal="true" aria-label={`Add-on ${item.name}`}>
      <div className="w-full max-w-md rounded-lg bg-surface p-4">
        <h2 className="text-[16px] font-bold">{item.name}</h2>
        <p className="mb-3 text-[12px] text-text-muted">{formatRupiah(item.price)}</p>
        {item.addon_groups.map((g) => (
          <fieldset key={g.id} className="mb-3">
            <legend className="mb-1 text-[13px] font-semibold">
              {g.name} <span className="text-[11px] font-normal text-text-muted">· {g.is_required ? 'wajib' : 'opsional'} · {g.selection === 'single' ? 'pilih 1' : 'pilih banyak'}</span>
            </legend>
            <div className="space-y-1">
              {g.options.map((o) => (
                <label key={o.id} className={`flex items-center gap-2 text-[13px] ${o.available ? '' : 'text-text-muted'}`}>
                  <input type={g.selection === 'single' ? 'radio' : 'checkbox'} name={g.id} disabled={!o.available}
                    checked={(chosen[g.id] ?? []).includes(o.id)} onChange={() => toggle(g.id, o.id, g.selection === 'single')} />
                  <span className="flex-1">{o.name}</span>
                  <span className="text-[12px]">{o.available ? `+${formatRupiah(o.price)}` : 'unavailable'}</span>
                </label>
              ))}
            </div>
          </fieldset>
        ))}
        <div className="flex gap-2">
          <Button variant="ghost" className="flex-1" onClick={onClose}>Batal</Button>
          <Button className="flex-1" disabled={missing} onClick={() => onAdd(Object.values(chosen).flat())}>Tambah</Button>
        </div>
      </div>
    </div>
  )
}
