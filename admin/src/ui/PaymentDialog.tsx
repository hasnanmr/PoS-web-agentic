// Wireframe S1 · Popup Pembayaran (Cash / QRIS), also used by S5 Tutup bill.
// Payment confirmation step (owner request, 2026-11-20):
// after choosing Cash or QRIS the cashier confirms the payment in a popup before the order
// or bill is completed.
// - Cash: type the money received; as soon as it covers the total the change ("Kembalian")
//   shows and only then "Pembayaran selesai" can be clicked.
// - QRIS: the outlet QRIS is shown large for the customer to scan; after the customer shows
//   the payment proof the cashier closes it with "Pembayaran selesai".
import { useEffect, useRef, useState } from 'react'
import { formatRupiah } from '../lib/format'
import { QrisPayPanel } from './QrisImage'
import { Alert, Button, TextInput } from './kit'

export function PaymentDialog({ method, total, outletId, busy, error, onConfirm, onCancel }: {
  method: 'cash' | 'qris'
  total: number
  outletId: string
  busy: boolean
  error?: string
  /** Cash passes the money received; QRIS passes nothing. */
  onConfirm: (cashReceived?: number) => void
  onCancel: () => void
}) {
  const [received, setReceived] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const cash = Number(received || 0)
  const enough = method === 'qris' || (received !== '' && cash >= total)
  const canConfirm = enough && !busy

  useEffect(() => { inputRef.current?.focus() }, [])

  function confirm() {
    if (canConfirm) onConfirm(method === 'cash' ? cash : undefined)
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) { e.preventDefault(); onCancel() }
      if (e.key === 'F9') { e.preventDefault(); confirm() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const title = method === 'cash' ? 'Pembayaran cash' : 'Pembayaran QRIS'
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-text/40 p-4 sm:items-center"
      role="dialog" aria-modal="true" aria-label={title}>
      <div className="w-full max-w-sm rounded-lg bg-surface p-4">
        <h2 className="text-[16px] font-bold">{title}</h2>
        <div className="mt-2 flex justify-between text-[15px] font-bold">
          <span>Total</span><span>{formatRupiah(total)}</span>
        </div>

        {method === 'cash' ? (
          <form className="mt-3 space-y-2 text-[12px]" onSubmit={(e) => { e.preventDefault(); confirm() }}>
            <label className="flex items-center justify-between gap-2">
              <span className="font-semibold">Uang diterima</span>
              <TextInput ref={inputRef} aria-label="Uang diterima" inputMode="numeric" className="h-9 w-40 text-right"
                value={received ? Number(received).toLocaleString('id-ID') : ''}
                onChange={(e) => setReceived(e.target.value.replace(/\D/g, ''))} />
            </label>
            <div className="flex flex-wrap justify-end gap-1">
              {[total, 50000, 100000].filter((v, i, a) => v >= total && v > 0 && a.indexOf(v) === i).map((v) => (
                <button key={v} type="button" className="rounded border border-border px-2 py-0.5 hover:bg-page"
                  onClick={() => setReceived(String(v))}>
                  {v === total ? 'Uang pas' : formatRupiah(v)}
                </button>
              ))}
            </div>
            {enough ? (
              <div className="flex justify-between rounded-md bg-success-soft px-3 py-2 text-[15px] font-bold text-success">
                <span>Kembalian</span><span>{formatRupiah(cash - total)}</span>
              </div>
            ) : (
              <p className="text-[11px] text-text-muted">
                {received ? `Kurang ${formatRupiah(total - cash)}` : 'Masukkan uang yang diterima dari pelanggan.'}
              </p>
            )}
          </form>
        ) : (
          <>
            <QrisPayPanel outletId={outletId} amount={total} />
            <p className="mt-2 text-[11px] text-text-muted">
              Klik “Pembayaran selesai” setelah pelanggan menunjukkan bukti bayar.
            </p>
          </>
        )}

        {error && <div className="mt-3"><Alert>{error}</Alert></div>}
        <div className="mt-4 flex gap-2">
          <Button variant="ghost" className="flex-1" disabled={busy} onClick={onCancel}>Batal</Button>
          <Button variant="action" className="flex-1" disabled={!canConfirm} onClick={confirm}>
            {busy ? 'Memproses…' : 'Pembayaran selesai'}
          </Button>
        </div>
      </div>
    </div>
  )
}
