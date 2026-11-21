// Wireframe S4 — Review Pembayaran QRIS (T-037; screenshots arrive from WhatsApp in T-036).
// Endpoints: GET /ops/outlets/{id}/payment-proofs?status=pending (polled), GET /ops/payment-proofs/{id},
// POST /ops/payment-proofs/{id}/accept | reject.
// Behavior note (canvas): Tolak → order langsung cancelled, bahan dikembalikan, tidak ada ledger entry,
// pelanggan dapat pesan WA "hubungi outlet". Paid → ledger dibuat dengan aktor & waktu.
// "✓ Tandai paid" is enabled only after the merchant-account checkbox.
// A web chat order (web_table from a table QR, web_online from the outlet link; page 07, T-146)
// arrives as `kind: customer_claim`: the customer tapped "Saya sudah bayar" and there is no
// screenshot, so staff confirm only from the merchant account.
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { formatRupiah, formatTime, timeAgo, ZONE_LABEL } from '../lib/format'
import type { ProofDetail, ProofQueueItem } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { usePolling } from '../lib/usePolling'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Card, Loading } from '../ui/kit'

const TYPE_LABEL: Record<ProofQueueItem['order_type'], string> = {
  dine_in: 'Dine-in', takeaway: 'Takeaway', delivery: 'Delivery', pickup: 'Pickup',
}

function where(p: { table: string | null; order_type: ProofQueueItem['order_type'] }): string {
  return p.table ? p.table : TYPE_LABEL[p.order_type]
}

const WEB_CHANNELS: string[] = ['web_table', 'web_online']

function channelLabel(channel: string): string {
  return WEB_CHANNELS.includes(channel) ? 'web' : channel
}

export default function PaymentReviewPage() {
  const { api, outlet } = useSession()
  const outletId = outlet?.id ?? ''
  const [params] = useSearchParams()
  const [picked, setPicked] = useState<string>()
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string }>()
  const queue = useLoad(
    () => api.get<ProofQueueItem[]>(`/ops/outlets/${outletId}/payment-proofs?status=pending`),
    outletId,
  )
  usePolling(queue, 10_000)
  const items = queue.data ?? []
  const fromBoard = params.get('order')
  const selected = items.find((p) => p.proof_id === picked)
    ?? items.find((p) => p.order_id === fromBoard)
    ?? items[0]

  if (!outlet) return <PageHeader title="Review Pembayaran" />
  return (
    <>
      <PageHeader title="Review Pembayaran" />
      <div className="space-y-4 p-4 md:p-6">
        {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}
        {queue.error ? <Alert>Antrian belum bisa dimuat: {errorMessage(queue.error)}</Alert> : null}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[320px_1fr]">
          <Card title={`Antrian · proof_submitted (${items.length})`}>
            {queue.loading && !queue.data ? <Loading /> : (
              <ul className="space-y-2">
                {items.map((p) => (
                  <li key={p.proof_id}>
                    <button type="button" onClick={() => { setPicked(p.proof_id); setNotice(undefined) }}
                      aria-current={selected?.proof_id === p.proof_id}
                      className={`w-full rounded-md border px-3 py-2 text-left text-[12px] ${selected?.proof_id === p.proof_id
                        ? 'border-primary bg-primary-soft' : 'border-border bg-surface hover:bg-page'}`}>
                      <div className="font-semibold">{p.order_no} · {where(p)} · {formatRupiah(p.total)}</div>
                      <div className="text-text-muted">
                        {p.kind === 'customer_claim' ? 'Pelanggan bilang sudah bayar' : 'Screenshot masuk'}{' '}
                        {formatTime(p.received_at, p.timezone)} · {timeAgo(p.received_at)}
                      </div>
                    </button>
                  </li>
                ))}
                {items.length === 0 && <li className="text-[12px] text-text-muted">Tidak ada bukti bayar yang menunggu review.</li>}
              </ul>
            )}
          </Card>
          {selected ? (
            <ProofPanel key={selected.proof_id} proofId={selected.proof_id} onDone={async (text) => {
              setNotice({ tone: 'success', text })
              setPicked(undefined)
              await queue.reload()
            }} />
          ) : (
            <Card><p className="text-[12px] text-text-muted">Pilih bukti bayar di antrian.</p></Card>
          )}
        </div>
      </div>
    </>
  )
}

function ProofPanel({ proofId, onDone }: { proofId: string; onDone: (text: string) => Promise<void> }) {
  const { api } = useSession()
  const proof = useLoad(() => api.get<ProofDetail>(`/ops/payment-proofs/${proofId}`), proofId)
  const [checked, setChecked] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const [zoom, setZoom] = useState(false)
  const p = proof.data

  async function run(action: () => Promise<unknown>, done: string) {
    setBusy(true)
    setError(undefined)
    try {
      await action()
      await onDone(done)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  if (!p) return <Card>{proof.error ? <Alert>{errorMessage(proof.error)}</Alert> : <Loading />}</Card>
  return (
    <Card>
      <div className="grid gap-4 md:grid-cols-[220px_1fr]">
        <button type="button" onClick={() => p.image_url && setZoom(true)} disabled={!p.image_url}
          className="flex aspect-[3/4] items-center justify-center overflow-hidden rounded-md border border-border bg-page text-center text-[12px] text-text-muted">
          {p.image_url
            ? <img src={p.image_url} alt={`Bukti bayar ${p.order_no}`} className="h-full w-full object-cover" />
            : p.kind === 'customer_claim'
              ? <span className="px-3">Tanpa screenshot<br />Pelanggan menekan “Saya sudah bayar” di web chat</span>
              : <span>Screenshot bukti bayar<br />(klik untuk perbesar)</span>}
        </button>
        <div className="space-y-1 text-[12px]">
          <p className="text-[13px] font-semibold">{p.order_no} · {channelLabel(p.channel)}{p.table ? ` · ${p.table}` : p.channel === 'web_online' ? ` · ${TYPE_LABEL[p.order_type]}` : ''}</p>
          <p className="text-text-muted">Total yang harus diterima</p>
          <p className="text-[20px] font-bold">{formatRupiah(p.total)}</p>
          <p className="pt-2">Pelanggan: {p.customer_phone_masked ?? '—'}</p>
          <p>
            {p.kind === 'customer_claim' ? 'Bilang sudah bayar' : 'Screenshot'}: {formatTime(p.received_at, p.timezone)} {ZONE_LABEL[p.timezone] ?? ''}
            {p.timer_stopped ? ' (timer auto-cancel berhenti)' : ''}
          </p>
        </div>
      </div>

      <div className="mt-4 space-y-3">
        <div role="note" className="rounded-md bg-warning-soft px-3 py-2 text-[12px] text-warning">
          ⚠ Jangan konfirmasi hanya dari {p.kind === 'customer_claim' ? 'klaim pelanggan' : 'screenshot'}. Cek mutasi di akun merchant QRIS untuk nominal {formatRupiah(p.total)}.
        </div>
        <label className="flex items-center gap-2 text-[13px]">
          <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
          Saya sudah menemukan transaksi ini di akun merchant QRIS
        </label>
        {error && <Alert>{error}</Alert>}
        <Button className="w-full bg-success" disabled={!checked || busy}
          onClick={() => void run(
            () => api.post(`/ops/payment-proofs/${proofId}/accept`, { merchant_account_checked: true }),
            `${p.order_no} ditandai paid (QRIS).`,
          )}>
          ✓ Tandai paid
        </Button>
        <hr className="border-border" />
        <p id="tolak" className="text-[13px] font-semibold">Dana tidak ditemukan?</p>
        <textarea aria-label="Alasan penolakan" placeholder="Alasan penolakan (wajib)…" value={reason} maxLength={300}
          onChange={(e) => setReason(e.target.value)}
          className="h-16 w-full rounded-md border border-border px-2.5 py-2 text-[13px] focus:border-primary focus:outline-none" />
        <Button variant="danger" className="w-full" disabled={!reason.trim() || busy}
          onClick={() => void run(
            () => api.post(`/ops/payment-proofs/${proofId}/reject`, { reason: reason.trim() }),
            `Bukti bayar ${p.order_no} ditolak; order dibatalkan dan bahan dikembalikan.`,
          )}>
          ✕ Tolak bukti bayar & batalkan order
        </Button>
        <p className="rounded-md bg-page p-3 text-[11px] text-text-muted">
          Tolak → order langsung cancelled, bahan dikembalikan (reversal movement), tidak ada ledger entry, pelanggan
          {p.kind === 'customer_claim' ? ' melihat alasannya di web chat.' : ' dapat pesan WA “hubungi outlet”.'} Paid → ledger dibuat dengan aktor & waktu.
        </p>
      </div>
      {zoom && p.image_url && (
        <div role="dialog" aria-label="Screenshot bukti bayar" className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setZoom(false)}>
          <img src={p.image_url} alt={`Bukti bayar ${p.order_no}`} className="max-h-full max-w-full rounded-md" />
        </div>
      )}
    </Card>
  )
}
