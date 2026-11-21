// Wireframe S2 / M1 — Order Board (T-030, T-031, T-068) with the S3 detail drawer
// (Detail Order & Reversal, T-032). Endpoints: GET /ops/outlets/{id}/orders/board (polled
// for "↻ live"), GET /ops/orders/{id}, POST /ops/orders/{id}/transitions | cancel | reversal.
// "Cek →" on a proof_submitted card opens S4 Review Pembayaran for that order.
// PoC demo: a paid QRIS order the server marks with `qris_check` shows "QRIS belum dicek" and a
// "Cek →" that opens the cross-check (POST /ops/orders/{id}/qris-check): staff confirm the
// transaction is in the receiving account, with the S4 merchant-account step.
// Behavior notes: order status and payment status are separate badges; buttons come only
// from the server's allowed_actions; unpaid pay-first orders have no "Mulai siapkan".
// Web orders from the table QR page (page 06 · "S2 kartu order web", #44): channel "web", table,
// name and kitchen note; once the customer taps "Saya sudah bayar" the card shows "Pelanggan
// bilang sudah bayar · 12:44" with "Cek & konfirmasi lunas →" and "Tolak", both opening S4.
import { useState } from 'react'
import { Link } from 'react-router'
import { ROUTES } from '../app/nav'
import { useRolePath, useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { formatRupiah, formatTime } from '../lib/format'
import type { Board, OrderCard } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { usePolling } from '../lib/usePolling'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Loading, Select, TextInput } from '../ui/kit'
import { paymentText, where } from './orders/labels'
import { OrderDrawer } from './orders/OrderDrawer'

const COLUMNS: { key: keyof Board; label: string }[] = [
  { key: 'awaiting_payment', label: 'MENUNGGU BAYAR' },
  { key: 'confirmed', label: 'CONFIRMED' },
  { key: 'preparing', label: 'PREPARING' },
  { key: 'ready', label: 'READY / DIANTAR' },
  { key: 'done_today', label: 'SELESAI / BATAL HARI INI' },
]

const ACTION_LABEL: Record<string, string> = {
  preparing: 'Mulai siapkan →',
  ready: 'Tandai ready →',
  out_for_delivery: 'Out for delivery →',
  served: 'Tandai disajikan →',
  completed: 'Selesai ✓',
}

const POLL_MS = 10_000

export default function OrderBoardPage() {
  const { api, outlet } = useSession()
  const pathFor = useRolePath()
  const outletId = outlet?.id ?? ''
  const [channel, setChannel] = useState('')
  const [type, setType] = useState('')
  const [q, setQ] = useState('')
  const [openId, setOpenId] = useState<string>()
  const [checking, setChecking] = useState<OrderCard>()
  const [error, setError] = useState<string>()
  const params = new URLSearchParams()
  if (channel) params.set('channel', channel)
  if (type) params.set('type', type)
  if (q.trim()) params.set('q', q.trim())
  const query = params.toString()
  const board = useLoad(
    () => api.get<Board>(`/ops/outlets/${outletId}/orders/board${query ? `?${query}` : ''}`),
    `${outletId}?${query}`,
  )
  const { reload } = board
  usePolling(board, POLL_MS)

  async function act(order: OrderCard, to: string) {
    setError(undefined)
    try {
      await api.post(`/ops/orders/${order.id}/transitions`, { to_status: to })
      await reload()
    } catch (e) {
      setError(errorMessage(e))
      await reload()
    }
  }

  if (!outlet) return <PageHeader title="Order Board" />
  return (
    <>
      <PageHeader title="Order Board" />
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface px-4 py-2 text-[12px] md:px-6">
        <Select aria-label="Kanal" className="h-8 w-auto" value={channel} onChange={(e) => setChannel(e.target.value)}>
          <option value="">Kanal: Semua</option>
          <option value="counter">counter</option>
          <option value="whatsapp_online">whatsapp_online</option>
          <option value="whatsapp_table">whatsapp_table</option>
          <option value="web_online">web (link outlet)</option>
          <option value="web_table">web (QR meja)</option>
        </Select>
        <Select aria-label="Tipe" className="h-8 w-auto" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">Tipe: Semua</option>
          <option value="dine_in">Dine-in</option>
          <option value="takeaway">Takeaway</option>
          <option value="delivery">Delivery</option>
          <option value="pickup">Pickup</option>
        </Select>
        <TextInput aria-label="Cari order" placeholder="⌕ Cari #order / nama" className="h-8 w-full sm:w-48" value={q} onChange={(e) => setQ(e.target.value)} />
        <button type="button" className={`ml-auto hover:text-text ${board.error ? 'text-danger' : 'text-text-muted'}`} onClick={() => void reload()}>
          {board.loading && board.data ? '↻ memuat…' : board.error ? '↻ gagal — coba lagi' : '↻ live'}
        </button>
      </div>
      {error && <div className="px-4 pt-3 md:px-6"><Alert>{error}</Alert></div>}
      {board.error ? (
        <div className="px-4 pt-3 md:px-6">
          <Alert>Board belum bisa diperbarui: {errorMessage(board.error)}{board.data ? ' Menampilkan data terakhir.' : ''}</Alert>
        </div>
      ) : null}
      {board.loading && !board.data ? <Loading /> : (
        <div className="grid gap-3 p-4 md:grid-cols-2 md:p-6 xl:grid-cols-5">
          {COLUMNS.map(({ key, label }) => {
            const cards = board.data?.[key] ?? []
            return (
              <section key={key} aria-label={label} className="min-w-0 rounded-lg bg-page/60 p-2">
                <h2 className="mb-2 text-[11px] font-semibold tracking-wide text-text-muted">{label}{key !== 'done_today' ? ` · ${cards.length}` : ''}</h2>
                {key === 'done_today' ? (
                  <ul className="space-y-1 rounded-md bg-surface p-2 text-[11px]">
                    {cards.map((o) => (
                      <li key={o.id}>
                        <button type="button" className="w-full text-left hover:underline" onClick={() => setOpenId(o.id)}>
                          {o.order_no}  {o.payment_status === 'refunded' ? 'reversed' : o.status}  {o.status === 'completed' ? formatRupiah(o.total) : ''}
                        </button>
                        {o.allowed_actions.includes('qris_check') && (
                          <button type="button" className="text-warning hover:underline" onClick={() => setChecking(o)}>
                            QRIS belum dicek · Cek →
                          </button>
                        )}
                      </li>
                    ))}
                    {cards.length === 0 && <li className="text-text-muted">Belum ada.</li>}
                  </ul>
                ) : (
                  <ul className="space-y-2">
                    {cards.map((o) => {
                      const forward = o.allowed_actions.find((a) => a in ACTION_LABEL)
                      return (
                        <li key={o.id} className="rounded-md border border-border bg-surface p-2.5 text-[12px]">
                          <button type="button" className="w-full text-left" onClick={() => setOpenId(o.id)}>
                            <div className="font-semibold">{o.order_no} · {o.channel === 'web_table' || o.channel === 'web_online' ? 'web' : o.channel}</div>
                            <div>{where(o)}</div>
                            {o.delivery_address && <div className="text-text-muted">{o.delivery_address}</div>}
                            <div className="truncate text-text-muted">{o.item_summary}</div>
                            {o.note && <div className="truncate text-text-muted">Catatan: {o.note}</div>}
                            <div>{formatRupiah(o.total)}{o.payment_status !== 'unpaid' || o.bill_id ? ` · ${paymentText(o)}` : ''}</div>
                            {o.auto_cancel_at && <div className="text-warning">⏱ Auto-cancel {formatTime(o.auto_cancel_at, outlet.timezone)}</div>}
                          </button>
                          {o.customer_phone && (
                            <a href={`tel:${o.customer_phone}`} className="mt-1 mr-1 inline-block text-[11px] font-semibold text-primary">📞 Hubungi</a>
                          )}
                          {o.payment_status !== 'paid' && !o.bill_id && (
                            <span className="mt-1 inline-block rounded-full bg-warning-soft px-2 py-0.5 text-[10px] text-warning">{o.payment_status}</span>
                          )}
                          {o.allowed_actions.includes('qris_check') && (
                            <>
                              <span className="mt-1 inline-block rounded-full bg-warning-soft px-2 py-0.5 text-[10px] text-warning">QRIS belum dicek</span>
                              <Button variant="ghost" className="mt-2 h-8 w-full" onClick={() => setChecking(o)}>Cek →</Button>
                            </>
                          )}
                          {o.payment_claimed_at && (
                            <span className="mt-1 ml-1 inline-block rounded-full bg-warning-soft px-2 py-0.5 text-[10px] font-semibold text-warning">
                              Pelanggan bilang sudah bayar · {formatTime(o.payment_claimed_at, outlet.timezone)}
                            </span>
                          )}
                          {o.payment_status === 'proof_submitted' && (
                            <Link to={`${pathFor(ROUTES.paymentReview.path)}?order=${o.id}`}
                              className="mt-2 inline-flex h-8 w-full items-center justify-center rounded-md bg-primary text-[13px] font-semibold text-white hover:opacity-90">
                              {o.payment_claimed_at ? 'Cek & konfirmasi lunas →' : 'Cek →'}
                            </Link>
                          )}
                          {o.payment_claimed_at && (
                            <Link to={`${pathFor(ROUTES.paymentReview.path)}?order=${o.id}#tolak`}
                              className="mt-1 block text-[11px] font-semibold text-danger hover:underline">
                              Tolak (pembayaran tidak ditemukan)
                            </Link>
                          )}
                          {forward && (
                            <Button className={`mt-2 h-8 w-full ${forward === 'completed' ? 'bg-success' : ''}`} onClick={() => void act(o, forward)}>
                              {ACTION_LABEL[forward]}
                            </Button>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                )}
              </section>
            )
          })}
        </div>
      )}
      <div className="mx-4 mb-6 rounded-md border border-dashed border-border p-3 text-[11px] text-text-muted md:mx-6">
        Status order & status pembayaran ditampilkan terpisah. Tombol aksi hanya menawarkan transisi yang valid.
        Klik kartu untuk detail, riwayat status, dan aksi Batalkan / Reversal.
      </div>
      {openId && <OrderDrawer orderId={openId} onClose={() => setOpenId(undefined)} onChanged={() => void reload()} />}
      {checking && <QrisCheckDialog order={checking} onClose={() => setChecking(undefined)}
        onChecked={async () => { setChecking(undefined); await reload() }} />}
    </>
  )
}

// PoC demo cross-check of a QRIS payment against the receiving account. Same step and copy as
// S4: "✓" stays disabled until the merchant-account checkbox is ticked.
function QrisCheckDialog({ order, onClose, onChecked }: {
  order: OrderCard
  onClose: () => void
  onChecked: () => Promise<void>
}) {
  const { api, outlet } = useSession()
  const [checked, setChecked] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-text/40 p-4 sm:items-center" role="dialog" aria-modal="true"
      aria-label={`Cek QRIS ${order.order_no}`}>
      <div className="w-full max-w-md rounded-lg bg-surface p-4 text-[13px]">
        <h2 className="text-[16px] font-bold">Cek pembayaran QRIS · {order.order_no}</h2>
        <p className="mb-3 text-[12px] text-text-muted">
          {where(order)} · {formatTime(order.created_at, outlet?.timezone ?? 'Asia/Jakarta')}{order.bill_id ? ' · dibayar lewat bill' : ''}
        </p>
        <p className="text-[20px] font-bold">{formatRupiah(order.total)}</p>
        <div className="my-3 rounded-md bg-warning-soft p-2 text-[12px] text-warning">
          ⚠ Jangan konfirmasi hanya dari screenshot. Cek mutasi di akun merchant QRIS untuk nominal {formatRupiah(order.total)}.
        </div>
        <label className="flex items-start gap-2">
          <input type="checkbox" className="mt-0.5" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
          <span>Saya sudah menemukan transaksi ini di akun merchant QRIS</span>
        </label>
        {error && <div className="mt-2"><Alert>{error}</Alert></div>}
        <div className="mt-4 flex gap-2">
          <Button variant="ghost" className="flex-1" onClick={onClose}>Batal</Button>
          <Button className="flex-1 bg-success" disabled={!checked || busy} onClick={async () => {
            setBusy(true)
            setError(undefined)
            try {
              await api.post(`/ops/orders/${order.id}/qris-check`, { merchant_account_checked: true })
              await onChecked()
            } catch (e) {
              setError(errorMessage(e))
              setBusy(false)
            }
          }}>✓ Sudah masuk rekening</Button>
        </div>
      </div>
    </div>
  )
}
