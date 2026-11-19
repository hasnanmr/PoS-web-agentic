// Wireframe O11 — Audit Log (T-101). Owner only, read-only.
// Endpoint: GET /owner/audit-log?outlet_id=&actor_id=&kind=reversal,status,payment&from=&to=&cursor=
// (order reversals, status and payment changes from order_events, newest first);
// GET /owner/staff for the "Staf" filter.
// Canvas note: "Log bersifat append-only dan tidak bisa diubah. Aktor "agent" akan muncul di Phase 2."
import { useState } from 'react'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { formatDay, formatTime, localDay, ZONE_LABEL } from '../lib/format'
import type { AuditKind, AuditPage, AuditRow, StaffMember } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Card, LinkButton, Loading, Select } from '../ui/kit'
import { RangePicker } from '../ui/RangePicker'

const KINDS: { key: AuditKind; label: string; tag: string }[] = [
  { key: 'reversal', label: 'Reversal', tag: 'REVERSAL' },
  { key: 'status', label: 'Status', tag: 'STATUS' },
  { key: 'payment', label: 'Pembayaran', tag: 'PAYMENT' },
]
const TAG = Object.fromEntries(KINDS.map((k) => [k.key, k.tag])) as Record<AuditKind, string>

function when(r: AuditRow): string {
  return `${formatDay(localDay(r.created_at, r.timezone))} ${formatTime(r.created_at, r.timezone)} ${ZONE_LABEL[r.timezone] ?? ''}`.trim()
}

/** "Rina (staf)", "Owner", "system" — as on the wireframe. */
function actorLabel(a: AuditRow['actor']): string {
  if (a.type !== 'user') return a.type
  if (a.role === 'owner') return 'Owner'
  return `${a.name ?? 'Staf'} (staf)`
}

export default function AuditLogPage() {
  const { api, me } = useSession()
  const [outletId, setOutletId] = useState('')
  const [actorId, setActorId] = useState('')
  const [kinds, setKinds] = useState<AuditKind[]>(KINDS.map((k) => k.key))
  const [range, setRange] = useState<{ from: string; to: string }>()
  const [more, setMore] = useState<{ key: string; items: AuditRow[]; cursor: string | null }>()
  const [loadingMore, setLoadingMore] = useState(false)
  const [moreError, setMoreError] = useState<string>()

  const params = new URLSearchParams()
  if (outletId) params.set('outlet_id', outletId)
  if (actorId) params.set('actor_id', actorId)
  if (kinds.length < KINDS.length) params.set('kind', kinds.join(','))
  if (range) {
    params.set('from', range.from)
    params.set('to', range.to)
  }
  const query = params.toString()
  const page = useLoad(() => api.get<AuditPage>(`/owner/audit-log${query ? `?${query}` : ''}`), query)
  const staff = useLoad(() => api.get<StaffMember[]>('/owner/staff'), 'staff')
  const extra = more?.key === query ? more : undefined
  const rows = [...(page.data?.items ?? []), ...(extra?.items ?? [])]
  const cursor = extra ? extra.cursor : page.data?.next_cursor

  async function loadMore() {
    if (!cursor) return
    setLoadingMore(true)
    setMoreError(undefined)
    try {
      const next = await api.get<AuditPage>(`/owner/audit-log?${query ? `${query}&` : ''}cursor=${encodeURIComponent(cursor)}`)
      setMore({ key: query, items: [...(extra?.items ?? []), ...next.items], cursor: next.next_cursor })
    } catch (e) {
      setMoreError(errorMessage(e))
    } finally {
      setLoadingMore(false)
    }
  }

  function toggleKind(k: AuditKind) {
    if (kinds.includes(k)) {
      if (kinds.length > 1) setKinds(kinds.filter((x) => x !== k))
    } else {
      setKinds(KINDS.map((x) => x.key).filter((x) => x === k || kinds.includes(x)))
    }
  }

  const people = (staff.data ?? []).filter((s) => s.status !== 'invited')

  return (
    <>
      <PageHeader title="Audit Log" actions={
        <div className="flex flex-wrap items-center gap-2 text-[12px]">
          <Select aria-label="Outlet" className="h-8 w-full text-[12px] sm:w-[190px]" value={outletId} onChange={(e) => setOutletId(e.target.value)}>
            <option value="">Outlet: Semua</option>
            {me.outlets.map((o) => <option key={o.id} value={o.id}>Outlet: {o.name}</option>)}
          </Select>
          <Select aria-label="Staf" className="h-8 w-full text-[12px] sm:w-[150px]" value={actorId} onChange={(e) => setActorId(e.target.value)}>
            <option value="">Staf: Semua</option>
            <option value={me.user.id}>Staf: Owner</option>
            {people.map((s) => <option key={s.id} value={s.id}>Staf: {s.display_name}</option>)}
          </Select>
          <div role="group" aria-label="Jenis" className="flex h-8 items-center rounded-md border border-border bg-surface px-1">
            <span className="px-1.5 text-text-muted">Jenis:</span>
            {KINDS.map((k, i) => (
              <span key={k.key} className="flex items-center">
                {i > 0 && <span aria-hidden="true" className="text-border">|</span>}
                <button type="button" aria-pressed={kinds.includes(k.key)} onClick={() => toggleKind(k.key)}
                  className={`rounded px-1.5 ${kinds.includes(k.key) ? 'font-semibold text-primary' : 'text-text-muted line-through'}`}>
                  {k.label}
                </button>
              </span>
            ))}
          </div>
          <RangePicker value={page.data ? { from: page.data.date_from, to: page.data.date_to } : range} onChange={setRange} />
        </div>
      } />
      <div className="p-4 md:p-6">
        {page.error ? <div className="mb-3"><Alert>Audit log belum bisa dimuat: {errorMessage(page.error)}</Alert></div> : null}
        <Card className="flex min-h-[60vh] flex-col">
          {!page.data ? (page.loading ? <Loading /> : null) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-[13px]">
                <thead className="text-[11px] tracking-wide text-text-muted">
                  <tr className="border-b border-border">
                    <th className="py-2.5 font-semibold">WAKTU (zona outlet)</th>
                    <th className="font-semibold">ORDER</th>
                    <th className="font-semibold">PERUBAHAN</th>
                    <th className="font-semibold">AKTOR</th>
                    <th className="font-semibold">ALASAN</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} className="border-b border-border last:border-0">
                      <td className="py-3.5 pr-3 whitespace-nowrap">{when(r)}</td>
                      <td className="pr-3 text-primary">{r.order_no}</td>
                      <td className="pr-3">{TAG[r.kind]} · {r.change}</td>
                      <td className="pr-3 whitespace-nowrap">{actorLabel(r.actor)}</td>
                      <td>{r.reason || '—'}</td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr><td colSpan={5} className="py-6 text-text-muted">Belum ada perubahan order di periode ini.</td></tr>
                  )}
                </tbody>
              </table>
              {cursor && (
                <LinkButton className="mt-3 text-[12px]" disabled={loadingMore} onClick={() => void loadMore()}>
                  {loadingMore ? 'Memuat…' : 'Muat lagi'}
                </LinkButton>
              )}
              {moreError && <div className="mt-2"><Alert>{moreError}</Alert></div>}
            </div>
          )}
          <p className="mt-auto pt-6 text-[11px] text-text-muted">
            Log bersifat append-only dan tidak bisa diubah. Aktor &ldquo;agent&rdquo; akan muncul di Phase 2.
          </p>
        </Card>
      </div>
    </>
  )
}
