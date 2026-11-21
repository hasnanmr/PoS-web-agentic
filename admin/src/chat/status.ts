// Order status words for the chat (C1 Pesanan Saya, C7) and the QRIS object URL hook (C6).
import { useEffect, useState } from 'react'

const STATUS_WORD: Record<string, string> = {
  pending_payment: 'Menunggu pembayaran',
  confirmed: 'Pembayaran dikonfirmasi',
  preparing: 'Sedang disiapkan',
  ready: 'Siap',
  out_for_delivery: 'Dalam pengantaran',
  served: 'Sudah diantar',
  completed: 'Selesai',
  cancelled: 'Dibatalkan',
}

export function statusWord(status: string, payment: string): string {
  if (status === 'pending_payment' && payment === 'proof_submitted') return 'Menunggu konfirmasi staf'
  return STATUS_WORD[status] ?? status
}

export function isActive(o: { status: string }): boolean {
  return o.status !== 'completed' && o.status !== 'cancelled'
}

/** The outlet's QRIS image as an object URL (fetched with the order key). */
export function useObjectUrl(load: (() => Promise<Blob>) | null): string | null {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!load) return
    let made: string | null = null
    let cancelled = false
    load().then((blob) => {
      if (cancelled) return
      made = URL.createObjectURL(blob)
      setUrl(made)
    }).catch(() => setUrl(null))
    return () => {
      cancelled = true
      if (made) URL.revokeObjectURL(made)
    }
  }, [load])
  return url
}
