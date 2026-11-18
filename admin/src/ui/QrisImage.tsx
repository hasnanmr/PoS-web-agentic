// The outlet's static QRIS (O3 upload, PoC demo), shown to the customer at the counter (S1)
// and when a bill is closed (S5). Loaded with the session token, so it is fetched as a blob.
import { formatRupiah } from '../lib/format'
import { useQrisImage } from '../lib/useQrisImage'

export function QrisPayPanel({ outletId, amount }: { outletId: string; amount: number }) {
  const { url, missing } = useQrisImage(outletId)
  return (
    <div className="mt-3 rounded-md border border-border bg-page p-3 text-center text-[12px]">
      {url ? (
        <img src={url} alt="QRIS outlet" className="mx-auto h-48 w-48 rounded bg-surface object-contain" />
      ) : (
        <p className="py-6 text-text-muted">
          {missing ? 'Belum ada QRIS. Owner mengunggahnya di Bisnis & Outlet.' : 'Memuat QRIS…'}
        </p>
      )}
      <p className="mt-2 font-semibold">Scan QRIS · bayar tepat {formatRupiah(amount)}</p>
      <p className="text-[11px] text-text-muted">Staf mengecek mutasi di rekening penerima dari Order Board (Cek →).</p>
    </div>
  )
}
