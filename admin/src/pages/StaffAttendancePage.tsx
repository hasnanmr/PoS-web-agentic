// Wireframe O14 — Kehadiran Staf, Selfie & Koreksi (T-118, T-119, T-122). Owner only.
// Endpoints: GET /owner/attendance?outlet_id=&user_id=&from=&to= (+ format=csv for "⭳ Ekspor CSV"),
// GET /owner/attendance/{id}, POST /owner/attendance/{id}/corrections,
// GET /owner/attendance/{id}/selfies/in|out (PoC: photo bytes), GET /owner/staff for the Staf filter.
// Canvas notes: flagged records ("perlu dikoreksi") are not counted in the totals; day boundaries
// follow each outlet's zone; corrections need a reason and keep the original values (append-only).
import { useState } from 'react'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { formatDay, formatMinutes, formatTime, localDay, shortOutlet } from '../lib/format'
import type { AttendanceDetail, AttendanceRecord, AttendanceReport, AttendanceTimes, StaffMember } from '../lib/types'
import { useBlobUrl } from '../lib/useBlobUrl'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Card, Loading, Select, TextInput } from '../ui/kit'
import { RangePicker } from '../ui/RangePicker'
import { durationCell, nextDate, selfieIcons, timeIn, toInstant } from './attendance/util'

function StatusLabel({ status }: { status: AttendanceRecord['status'] }) {
  switch (status) {
    case 'open': return <span>● Bekerja</span>
    case 'needs_correction': return <span className="text-danger">⚠ Koreksi</span>
    case 'corrected': return <span className="text-text-muted">✎ dikoreksi</span>
    default: return <span className="text-success" aria-label="Selesai">✓</span>
  }
}

export default function StaffAttendancePage() {
  const { api, me } = useSession()
  const [outletId, setOutletId] = useState('')
  const [userId, setUserId] = useState('')
  const [range, setRange] = useState<{ from: string; to: string }>()
  const [selected, setSelected] = useState<string>()
  const [exportError, setExportError] = useState<string>()
  const params = new URLSearchParams()
  if (outletId) params.set('outlet_id', outletId)
  if (userId) params.set('user_id', userId)
  if (range) {
    params.set('from', range.from)
    params.set('to', range.to)
  }
  const query = params.toString()
  const report = useLoad(() => api.get<AttendanceReport>(`/owner/attendance${query ? `?${query}` : ''}`), query)
  const staff = useLoad(() => api.get<StaffMember[]>('/owner/staff'), 'staff')
  const r = report.data
  // A chosen row stays open while it is in the table (also after it was corrected); otherwise the
  // first flagged record opens.
  const selectedId = (selected && r?.records.some((x) => x.id === selected) ? selected : undefined)
    ?? r?.records.find((x) => x.status === 'needs_correction')?.id

  async function exportCsv() {
    setExportError(undefined)
    try {
      const blob = await api.blob(`/owner/attendance?${query ? `${query}&` : ''}format=csv`)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `kehadiran-${r?.from ?? ''}-${r?.to ?? ''}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setExportError(errorMessage(e))
    }
  }

  const filters = (
    <>
      <Select aria-label="Outlet" className="h-8 w-auto" value={outletId} onChange={(e) => setOutletId(e.target.value)}>
        <option value="">Outlet: Semua</option>
        {me.outlets.map((o) => <option key={o.id} value={o.id}>Outlet: {o.name}</option>)}
      </Select>
      <Select aria-label="Staf" className="h-8 w-auto" value={userId} onChange={(e) => setUserId(e.target.value)}>
        <option value="">Staf: Semua</option>
        {(staff.data ?? []).map((s) => <option key={s.id} value={s.id}>Staf: {s.display_name}</option>)}
      </Select>
      <RangePicker value={r ? { from: r.from, to: r.to } : range} onChange={setRange} />
      <Button variant="ghost" className="h-8" onClick={() => void exportCsv()}>⭳ Ekspor CSV</Button>
    </>
  )

  return (
    <>
      <PageHeader title="Kehadiran Staf" />
      <div className="space-y-4 p-4 md:p-6">
        <div className="flex flex-wrap items-center justify-end gap-2 text-[12px]">{filters}</div>
        {exportError && <Alert>{exportError}</Alert>}
        {report.error ? <Alert>Data kehadiran belum bisa dimuat: {errorMessage(report.error)}</Alert> : null}
        {!r ? (report.loading ? <Loading /> : null) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {r.summary.map((s) => (
                <Card key={s.user.id}>
                  <div className="text-[13px]">{s.user.name} · {s.outlets.map(shortOutlet).join(', ')}</div>
                  <div className="mt-2 text-[13px]">{formatMinutes(s.worked_minutes, true)} · {s.days} hari</div>
                </Card>
              ))}
              <section className="rounded-lg border border-danger/30 bg-danger-soft p-4 text-danger">
                <div className="text-[13px] font-semibold">⚠ Perlu dikoreksi</div>
                <div className="mt-2 text-[13px] font-semibold">{r.needs_correction_count} catatan</div>
              </section>
            </div>
            <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
              <Card className="min-w-0">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[600px] text-left text-[12px]">
                    <thead className="text-[11px] tracking-wide text-text-muted">
                      <tr className="border-b border-border">
                        <th className="py-2 font-semibold">TANGGAL</th>
                        <th className="font-semibold">STAF</th>
                        <th className="font-semibold">OUTLET</th>
                        <th className="font-semibold">MASUK</th>
                        <th className="font-semibold">PULANG</th>
                        <th className="font-semibold">DURASI</th>
                        <th className="font-semibold">SELFIE</th>
                        <th className="font-semibold">STATUS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {r.records.map((row) => (
                        <tr key={row.id} onClick={() => setSelected(row.id)}
                          className={`cursor-pointer border-b border-border last:border-0 ${
                            row.status === 'needs_correction' ? 'bg-danger-soft'
                              : row.id === selectedId ? 'bg-primary-soft' : 'hover:bg-page'}`}>
                          <td className="py-2.5">
                            <button type="button" className="text-left" aria-pressed={row.id === selectedId}
                              aria-label={`Buka catatan ${row.user.name} ${formatDay(row.date)}`}
                              onClick={() => setSelected(row.id)}>
                              {formatDay(row.date)}
                            </button>
                          </td>
                          <td>{row.user.name}</td>
                          <td>{shortOutlet(row.outlet.name)}</td>
                          <td>{timeIn(row, row.clock_in_at)}</td>
                          <td>{timeIn(row, row.clock_out_at, false)}</td>
                          <td>{durationCell(row)}</td>
                          <td>{selfieIcons(row)}</td>
                          <td><StatusLabel status={row.status} /></td>
                        </tr>
                      ))}
                      {r.records.length === 0 && (
                        <tr><td colSpan={8} className="py-4 text-text-muted">Belum ada catatan kehadiran di periode ini.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <p className="mt-6 text-[11px] text-text-muted">
                  Catatan “perlu dikoreksi” belum dihitung ke total jam. Batas hari mengikuti zona waktu tiap outlet. Gaji &amp;
                  lembur tidak termasuk MVP.
                </p>
              </Card>
              {selectedId ? (
                <CorrectionPanel key={selectedId} recordId={selectedId}
                  onSaved={() => { setSelected(selectedId); void report.reload() }} />
              ) : (
                <Card><p className="text-[12px] text-text-muted">Pilih catatan untuk melihat selfie dan mengoreksi.</p></Card>
              )}
            </div>
          </>
        )}
      </div>
    </>
  )
}

function Selfie({ recordId, which, label }: { recordId: string; which: 'in' | 'out'; label: string }) {
  const { url, failed } = useBlobUrl(`/owner/attendance/${recordId}/selfies/${which}`)
  return url ? (
    <img src={url} alt={label} className="h-16 w-16 shrink-0 rounded-full object-cover" />
  ) : (
    <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-[#CDD6E6] text-[10px] text-text-muted">
      {failed ? 'terhapus' : ''}
    </div>
  )
}

function formatGrace(minutes: number): string {
  return minutes % 60 === 0 ? `${minutes / 60} jam` : `${minutes} menit`
}

function describeChange(r: { timezone: string }, from: AttendanceTimes, to: AttendanceTimes): string {
  const parts: string[] = []
  if (from.clock_in_at !== to.clock_in_at) {
    parts.push(`masuk ${timeIn(r, from.clock_in_at, false)} → ${timeIn(r, to.clock_in_at, false)}`)
  }
  if (from.clock_out_at !== to.clock_out_at) {
    parts.push(`pulang ${timeIn(r, from.clock_out_at, false)} → ${timeIn(r, to.clock_out_at, false)}`)
  }
  return parts.join(' · ')
}

function CorrectionPanel({ recordId, onSaved }: { recordId: string; onSaved: () => void }) {
  const { api } = useSession()
  const detail = useLoad(() => api.get<AttendanceDetail>(`/owner/attendance/${recordId}`), recordId)
  const d = detail.data
  const [clockOut, setClockOut] = useState<string>()
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)

  if (!d) return <Card>{detail.error ? <Alert>{errorMessage(detail.error)}</Alert> : <Loading />}</Card>

  const tz = d.timezone
  const local = (iso: string | null) => (iso ? formatTime(iso, tz) : '')
  const inValue = local(d.clock_in_at)
  const outValue = clockOut ?? local(d.clock_out_at)
  const changed = outValue !== local(d.clock_out_at)
  // A clock-out at or before the clock-in time falls on the next day: say so before saving.
  const nextDay = outValue !== '' && outValue <= inValue

  async function save(record: AttendanceDetail) {
    setBusy(true)
    setError(undefined)
    try {
      const body: Record<string, string> = { reason: reason.trim() }
      // Only the changed time is sent, so the stored seconds of the other one stay untouched.
      if (changed) body.clock_out_at = toInstant(record.date, outValue, tz, inValue)
      await api.post(`/owner/attendance/${record.id}/corrections`, body)
      setReason('')
      setClockOut(undefined)
      await detail.reload()
      onSaved()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title={`Koreksi catatan · ${d.user.name}, ${formatDay(d.date)}`}>
      <div className="space-y-3 text-[13px]">
        {d.has_selfie_in || d.has_selfie_out ? (
          <div className="space-y-2">
            {d.has_selfie_in && (
              <div className="flex items-center gap-3">
                <Selfie recordId={d.id} which="in" label={`Selfie masuk ${d.user.name}`} />
                <div>
                  <div>Selfie masuk {timeIn(d, d.clock_in_at)}{d.devices.clock_in ? ` · tablet ${d.devices.clock_in}` : ''}</div>
                  <div className="text-[11px] text-text-muted">Cocokkan wajah dengan nama staf. Tanpa face recognition di MVP.</div>
                </div>
              </div>
            )}
            {d.has_selfie_out && (
              <div className="flex items-center gap-3">
                <Selfie recordId={d.id} which="out" label={`Selfie pulang ${d.user.name}`} />
                <div>Selfie pulang {timeIn(d, d.clock_out_at)}{d.devices.clock_out ? ` · tablet ${d.devices.clock_out}` : ''}</div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-[12px] text-text-muted">Selfie sudah dihapus otomatis (lebih dari 45 hari).</p>
        )}
        <div>
          <div>
            Nilai asli: masuk {timeIn(d, d.original.clock_in_at, false)} · pulang {timeIn(d, d.original.clock_out_at, false)}
          </div>
          {d.flag && (
            <div>
              Ditandai otomatis {formatTime(d.flag.at, tz)}
              {d.flag.closes_at ? ` (tutup ${d.flag.closes_at} + ${formatGrace(d.flag.grace_minutes ?? 0)})` : ''}
            </div>
          )}
        </div>
        {d.status !== 'open' ? (
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (reason.trim()) void save(d) }}>
            <label className="flex items-center gap-2">Jam pulang *
              <TextInput type="time" aria-label="Jam pulang" className="h-8 w-28" required value={outValue}
                onChange={(e) => setClockOut(e.target.value)} />
            </label>
            {nextDay && (
              <p className="text-[12px] text-warning" role="status">
                Jam pulang {outValue} jatuh di hari berikutnya ({formatDay(nextDate(d.date))}), bukan {formatDay(d.date)}.
              </p>
            )}
            <label className="block">Alasan koreksi *
              <TextInput aria-label="Alasan koreksi" maxLength={500} placeholder="Lupa clock out, dikonfirmasi via chat"
                value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
            {error && <Alert>{error}</Alert>}
            <Button type="submit" variant="action" className="mt-2 h-11 w-full"
              disabled={busy || !reason.trim() || !outValue || !changed}>Simpan koreksi</Button>
          </form>
        ) : (
          <p className="text-[12px] text-text-muted">Staf masih bekerja; catatan bisa dikoreksi setelah clock out.</p>
        )}
        <div className="pt-2 text-[12px]">
          <div className="text-text-muted">Riwayat koreksi (append-only)</div>
          {d.corrections.length === 0 && <div className="text-text-muted">Belum ada koreksi.</div>}
          {d.corrections.map((c, i) => (
            <div key={i} className="mt-1">
              <div>{formatDay(d.date)} · {d.user.name} · {describeChange(d, c.from, c.to)}</div>
              <div className="text-text-muted">
                oleh {c.by} · {formatDay(localDay(c.at, tz))} {formatTime(c.at, tz)} · “{c.reason}”
              </div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  )
}
