// C6 payment (static QRIS, exact total, deadline, "Saya sudah bayar", cancel) and C7 live
// status + Pesanan Saya. Canvas rules: the status refreshes by itself (≤ 10 s, polled every 5 s)
// while the chat is open; nothing is sent outside the chat; a rejected payment shows the reason;
// the customer can cancel only until "Saya sudah bayar".
import { useState } from 'react'
import { formatRupiah, formatTime } from '../lib/format'
import { isActive, statusWord } from './status'
import type { OrderOverview, OrderStatus } from './types'
import { Action, Bubble, TextLink } from './ui'

const FULFILLMENT_WORD: Record<OrderStatus['fulfillment'], string> = {
  dine_in: 'dine-in', pickup: 'pickup', delivery: 'delivery',
}

// C6 ----------------------------------------------------------------------------------------------

export function PayCard({ order, qrisUrl, busy, error, onClaim, onCancel }: {
  order: OrderStatus; qrisUrl: string | null; busy: boolean; error: string | null
  onClaim: () => void; onCancel: () => void
}) {
  const count = order.items.reduce((s, i) => s + i.quantity, 0)
  const minutes = Math.max(1, Math.round((new Date(order.pay_by).getTime() - new Date(order.created_at).getTime()) / 60000))
  return (
    <div className="max-w-[92%] space-y-2">
      <Bubble tone="success">✓ Pesanan {order.order_no} dibuat · {count} item · {FULFILLMENT_WORD[order.fulfillment]}</Bubble>
      <Bubble>
        <div className="text-center">
          <p className="text-[12px] text-text-muted">Total bayar (tepat)</p>
          <p className="text-[22px] font-bold">{formatRupiah(order.total)}</p>
          {qrisUrl ? (
            <img src={qrisUrl} alt="QRIS outlet" className="mx-auto my-2 w-48 rounded border border-border" />
          ) : (
            <div className="mx-auto my-2 flex h-48 w-48 items-center justify-center rounded border border-border bg-page text-[11px] text-text-muted">
              Memuat QRIS…
            </div>
          )}
        </div>
        <p className="text-[12px]">1. Scan dengan e-wallet / m-banking  2. Bayar tepat {formatRupiah(order.total)}  3. Tekan &quot;Saya sudah bayar&quot;</p>
        <p className="mt-2 rounded-lg bg-warning-soft px-2 py-1.5 text-[12px] text-warning">
          ⏱ Bayar sebelum {formatTime(order.pay_by, order.timezone)} ({minutes} menit). Lewat dari itu pesanan batal otomatis.
        </p>
        <Action tone="action" className="mt-2" disabled={busy} onClick={onClaim}>Saya sudah bayar</Action>
        <p className="mt-2 text-center">
          {qrisUrl && <a href={qrisUrl} download="qris.png" className="text-[12px] font-semibold text-primary">↓ Simpan gambar QRIS</a>}
          {qrisUrl && <span className="text-text-muted">  ·  </span>}
          <TextLink disabled={busy} onClick={onCancel}>Batalkan pesanan</TextLink>
        </p>
      </Bubble>
      {error && <Bubble tone="danger">{error}</Bubble>}
    </div>
  )
}

// C7 ----------------------------------------------------------------------------------------------

function timeline(order: OrderStatus): { label: string; at: string | null; state: 'done' | 'now' | 'next' }[] {
  const at = (status: string) => order.events.find((e) => e.status === status)?.at ?? null
  const steps: { key: string; label: string; at: string | null }[] = [
    { key: 'pending_payment', label: 'Pesanan dibuat', at: order.created_at },
  ]
  if (order.claimed_at) steps.push({ key: 'claimed', label: 'Kamu bilang sudah bayar', at: order.claimed_at })
  steps.push({ key: 'confirmed', label: 'Pembayaran dikonfirmasi staf', at: at('confirmed') })
  steps.push({ key: 'preparing', label: 'Sedang disiapkan', at: at('preparing') })
  if (order.fulfillment === 'delivery') steps.push({ key: 'out_for_delivery', label: 'Dalam pengantaran', at: at('out_for_delivery') })
  else steps.push({ key: 'ready', label: order.fulfillment === 'pickup' ? 'Siap diambil' : 'Siap diantar ke meja', at: at('ready') })
  steps.push({ key: 'completed', label: 'Selesai', at: at('completed') })
  const reached = steps.map((s) => s.at !== null)
  const lastDone = reached.lastIndexOf(true)
  return steps.map((s, i) => ({
    label: s.label,
    at: s.at,
    state: i <= lastDone ? 'done' : i === lastDone + 1 ? 'now' : 'next',
  }))
}

export function StatusCard({ order, link }: { order: OrderStatus; link: string }) {
  const [copied, setCopied] = useState(false)
  const count = order.items.reduce((s, i) => s + i.quantity, 0)
  const fulfillment = { dine_in: 'Dine-in', pickup: 'Pickup', delivery: 'Delivery' }[order.fulfillment]
  async function copy() {
    try {
      await navigator.clipboard.writeText(link)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }
  if (order.status === 'cancelled') {
    return (
      <Bubble tone="danger">
        {order.reject_reason ? (
          <>
            <p>
              Maaf, pembayaranmu belum kami temukan, jadi pesanan {order.order_no} kami batalkan. Kalau kamu sudah transfer,
              hubungi outlet ya, nanti dibantu cek.
            </p>
            <p className="mt-1 text-[12px]">Catatan dari staf: {order.reject_reason}</p>
          </>
        ) : order.cancel_reason?.startsWith('Batal otomatis') ? (
          <p>Pesanan {order.order_no} batal otomatis karena belum dibayar sampai batas waktu. Kalau masih mau, pesan lagi ya.</p>
        ) : (
          <p>Pesanan {order.order_no} sudah dibatalkan.</p>
        )}
      </Bubble>
    )
  }
  return (
    <Bubble>
      <div className="flex items-center justify-between">
        <p className="font-semibold">Pesanan {order.order_no}</p>
        {isActive(order) && <span className="rounded-full bg-success-soft px-2 py-0.5 text-[11px] font-semibold text-success">● Live</span>}
      </div>
      <p className="text-[11px] text-text-muted">{fulfillment} · {count} item · {formatRupiah(order.total)} · QRIS</p>
      <ol className="mt-2 space-y-1 text-[12px]" aria-label="Status pesanan">
        {timeline(order).map((s) => (
          <li key={s.label} className={`flex gap-2 ${s.state === 'next' ? 'text-text-muted' : ''}`}>
            <span className="w-14 shrink-0">
              {s.state === 'done' ? `✓ ${s.at ? formatTime(s.at, order.timezone) : ''}` : s.state === 'now' ? '●' : '○'}
            </span>
            <span className={s.state === 'now' ? 'font-semibold' : ''}>{s.label}</span>
          </li>
        ))}
      </ol>
      <p className="mt-2 rounded-lg bg-page px-2 py-1.5 text-[11px] text-primary">
        🔗 Simpan link pesanan — untuk buka lagi kalau data browser terhapus.{' '}
        <TextLink className="text-[11px]" onClick={copy}>{copied ? 'Link tersalin ✓' : 'Salin link'}</TextLink>
      </p>
    </Bubble>
  )
}

export function MyOrders({ orders, timezone, onOpen }: {
  orders: OrderOverview[]; timezone: string; onOpen: (id: string) => void
}) {
  return (
    <Bubble>
      <p className="mb-1 font-semibold">🧾 Pesanan Saya (dari HP ini)</p>
      {orders.length === 0 ? (
        <p className="text-[12px] text-text-muted">Belum ada pesanan dari HP ini.</p>
      ) : (
        <ul className="space-y-1">
          {orders.map((o) => (
            <li key={o.order_id}>
              <TextLink className="text-left" onClick={() => onOpen(o.order_id)}>
                {o.order_no} · {FULFILLMENT_WORD[o.fulfillment]} · {statusWord(o.status, o.payment_status)}
                {o.status === 'completed' ? ` ${formatTime(o.created_at, timezone)}` : ''}  ›
              </TextLink>
            </li>
          ))}
        </ul>
      )}
    </Bubble>
  )
}
