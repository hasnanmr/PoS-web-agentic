// Wireframe S3 — Detail Order & Reversal (T-031, T-032): the order detail drawer opened from the
// S2 Order Board and, inside the O2b drawer, from the owner Dashboard (with "← Kembali").
// Endpoints: GET /ops/orders/{id}, POST /ops/orders/{id}/transitions | cancel | reversal.
// Buttons come only from the server's allowed_actions.
import { useState } from 'react'
import { useSession } from '../../app/session'
import { errorMessage } from '../../lib/api'
import { formatRupiah, formatTime } from '../../lib/format'
import type { OrderDetail } from '../../lib/types'
import { useLoad } from '../../lib/useLoad'
import { Alert, Button, LinkButton, Loading } from '../../ui/kit'
import { paymentText, where } from './labels'

/** S3 as a drawer from the right (S2 Order Board). */
export function OrderDrawer({ orderId, onClose, onChanged }: { orderId: string; onClose: () => void; onChanged: () => void }) {
  return (
    <div className="fixed inset-0 z-40 flex animate-fade-in justify-end bg-text/30" role="dialog" aria-modal="true" aria-label="Detail order">
      <button type="button" aria-label="Tutup detail" className="flex-1 cursor-default" onClick={onClose} />
      <div className="h-full w-full max-w-[440px] animate-drawer-in overflow-y-auto overscroll-contain bg-surface p-4 shadow-xl">
        <OrderDetailPanel orderId={orderId} onClose={onClose} onChanged={onChanged} />
      </div>
    </div>
  )
}

/** S3 content; `onBack` adds "← Kembali" when it is shown inside another drawer (O2b). */
export function OrderDetailPanel({ orderId, onClose, onChanged, onBack }: {
  orderId: string
  onClose: () => void
  onChanged: () => void
  onBack?: () => void
}) {
  const { api } = useSession()
  const detail = useLoad(() => api.get<OrderDetail>(`/ops/orders/${orderId}`), orderId)
  const [reversing, setReversing] = useState(false)
  const [error, setError] = useState<string>()
  const [notice, setNotice] = useState<string>()
  const o = detail.data

  async function run(action: () => Promise<OrderDetail>, success?: (d: OrderDetail) => string) {
    setError(undefined)
    try {
      const result = await action()
      setReversing(false)
      if (success) setNotice(success(result))
      await detail.reload()
      onChanged()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <>
      {onBack && <LinkButton className="mb-2 text-[12px]" onClick={onBack}>← Kembali</LinkButton>}
      {!o ? <Loading /> : (
          <>
            <div className="flex items-start justify-between gap-2">
              <h2 className="text-[16px] font-bold">{o.order_no}  ·  {where(o)}</h2>
              <button type="button" aria-label="Tutup" className="text-[16px]" onClick={onClose}>✕</button>
            </div>
            <p className="mt-1 text-[12px] text-text-muted">
              Kanal: {o.channel}  ·  Order: {o.status}  ·  Payment: {paymentText(o)}
            </p>
            <ul className="mt-3 space-y-1 text-[12px]">
              {o.items.map((i) => (
                <li key={i.id} className="flex justify-between gap-2">
                  <span>
                    {i.quantity}× {i.name}
                    {i.addons.length > 0 && <span className="block pl-4 text-text-muted">+ {i.addons.map((a) => a.name).join(', ')}</span>}
                  </span>
                  <span>{formatRupiah(i.line_total)}</span>
                </li>
              ))}
            </ul>
            <dl className="mt-2 space-y-0.5 border-t border-border pt-2 text-[12px]">
              <div className="flex justify-between"><dt>Subtotal</dt><dd>{formatRupiah(o.subtotal)}</dd></div>
              {o.pb1_rate_bps != null && <div className="flex justify-between"><dt>PB1 {o.pb1_rate_bps / 100}%</dt><dd>{formatRupiah(o.pb1_amount)}</dd></div>}
              <div className="flex justify-between font-bold"><dt>Total</dt><dd>{formatRupiah(o.total)}</dd></div>
            </dl>

            <h3 className="mt-4 mb-1 text-[13px] font-semibold">Riwayat status (immutable)</h3>
            <ul className="space-y-1 text-[12px]">
              {o.events.map((e, idx) => (
                <li key={idx}>
                  ● {formatTime(e.at, o.timezone)}{'  '}
                  {e.kind === 'payment_changed' ? `payment → ${e.to_payment}${e.data.method ? ` (${String(e.data.method)}${e.data.amount ? ` ${Number(e.data.amount).toLocaleString('id-ID')}` : ''})` : ''}`
                    : e.kind === 'created' ? `created → ${e.to}`
                    : e.kind === 'reversed' ? `reversal → refund ${formatRupiah(Number(e.data.refund ?? 0))}`
                    : `${e.from} → ${e.to}`}
                  {'  · '}{e.actor.name ?? e.actor.type}{e.actor.role ? ` (${e.actor.role === 'owner' ? 'owner' : 'staf'})` : ''}
                  {e.reason ? <span className="block pl-4 text-text-muted">alasan: {e.reason}</span> : null}
                </li>
              ))}
            </ul>

            {notice && <div className="mt-3"><Alert tone="success">{notice}</Alert></div>}
            {error && <div className="mt-3"><Alert>{error}</Alert></div>}
            {reversing ? (
              <ReversalForm order={o} onCancel={() => setReversing(false)}
                onConfirm={(reason, ingredients) => run(
                  () => api.post<OrderDetail>(`/ops/orders/${o.id}/reversal`, { reason, ingredients }),
                  (d) => `Reversal tercatat · refund ${formatRupiah(d.refund?.amount ?? o.total)} (${d.refund?.method ?? ''}).`)} />
            ) : (
              <div className="mt-4 flex flex-wrap gap-2">
                {o.allowed_actions.includes('completed') && (
                  <Button onClick={() => void run(() => api.post<OrderDetail>(`/ops/orders/${o.id}/transitions`, { to_status: 'completed' }))}>Tandai selesai</Button>
                )}
                {o.allowed_actions.includes('cancel') && (
                  <Button variant="danger" onClick={() => void run(() => api.post<OrderDetail>(`/ops/orders/${o.id}/cancel`, {}), () => 'Order dibatalkan; stok dikembalikan.')}>Batalkan</Button>
                )}
                {o.allowed_actions.includes('reversal') && (
                  <Button variant="danger" onClick={() => setReversing(true)}>Reversal order…</Button>
                )}
              </div>
            )}
          </>
        )}
    </>
  )
}

function ReversalForm({ order, onCancel, onConfirm }: {
  order: OrderDetail
  onCancel: () => void
  onConfirm: (reason: string, ingredients: 'waste' | 'return') => void
}) {
  const prepared = ['preparing', 'ready', 'served', 'out_for_delivery', 'completed'].includes(order.status)
  const [ingredients, setIngredients] = useState<'waste' | 'return'>(prepared ? 'waste' : 'return')
  const [reason, setReason] = useState('')
  const [touched, setTouched] = useState(false)
  const { me } = useSession()
  return (
    <div className="mt-4 rounded-md border border-danger p-3 text-[12px]">
      <h3 className="text-[13px] font-semibold">Reversal order {order.order_no}</h3>
      <p className="mt-1 text-text-muted">Order sudah dibayar. Reversal membuat refund ledger entry. Uang dikembalikan manual di luar sistem.</p>
      <fieldset className="mt-3">
        <legend className="mb-1 font-semibold">Perlakuan bahan</legend>
        <label className="flex items-center gap-2"><input type="radio" checked={ingredients === 'waste'} onChange={() => setIngredients('waste')} /> Sudah diprepare → bahan dicatat sebagai WASTE</label>
        <label className="flex items-center gap-2"><input type="radio" checked={ingredients === 'return'} onChange={() => setIngredients('return')} /> Belum diprepare → bahan dikembalikan (reversal movement)</label>
      </fieldset>
      <label className="mt-3 block">
        <span className="mb-1 block font-semibold">Alasan reversal *</span>
        <textarea aria-label="Alasan reversal" className="w-full rounded-md border border-border p-2" rows={3}
          placeholder="Tulis alasan (wajib)…" value={reason} onChange={(e) => setReason(e.target.value)} onBlur={() => setTouched(true)} />
      </label>
      {touched && !reason.trim() && <p className="text-danger">Alasan wajib diisi — reversal tanpa alasan ditolak.</p>}
      <p className="mt-1 text-text-muted">Tercatat: aktor = {me.user.display_name ?? me.user.email}, waktu = sekarang, refund {formatRupiah(order.total)} ({order.payment_method ?? 'cash'}).</p>
      <div className="mt-3 flex gap-3">
        <LinkButton onClick={onCancel}>Batal</LinkButton>
        <Button variant="action" disabled={!reason.trim()} onClick={() => onConfirm(reason.trim(), ingredients)}>Konfirmasi reversal</Button>
      </div>
    </div>
  )
}
