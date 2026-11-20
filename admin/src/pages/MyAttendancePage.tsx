// Wireframe S9 — Absensi Saya (mobile: M6) (T-116, T-117, T-122). Staff, own records only.
// Endpoints: GET /ops/me/attendance/today, GET /ops/me/attendance (this week by default),
// GET /ops/me/attendance/{id}/selfies/in|out (PoC: photo bytes).
// Canvas notes: no clock-in button on phones or in the admin app (only the outlet tablet); a record
// flagged "perlu dikoreksi" shows a banner; a history row opens the person's own selfies; selfies
// are kept 45 days, visible to the owner and the person only.
import { useState } from 'react'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { formatDay, formatMinutes, formatTime, shortOutlet, ZONE_LABEL } from '../lib/format'
import type { AttendanceRecord, MyAttendanceHistory, MyAttendanceToday } from '../lib/types'
import { useBlobUrl } from '../lib/useBlobUrl'
import { useLoad } from '../lib/useLoad'
import { usePolling } from '../lib/usePolling'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Card, Loading } from '../ui/kit'
import { durationCell, selfieIcons, timeIn, useNow } from './attendance/util'

function workedSince(iso: string, now: number): string {
  return formatMinutes(Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60000)), true)
}

export default function MyAttendancePage() {
  const { api } = useSession()
  const today = useLoad(() => api.get<MyAttendanceToday>('/ops/me/attendance/today'), 'today')
  const history = useLoad(() => api.get<MyAttendanceHistory>('/ops/me/attendance'), 'history')
  usePolling(today, 60_000)
  usePolling(history, 60_000) // the table and total follow a clock out on the tablet
  const [open, setOpen] = useState<string>()
  const now = useNow()
  const t = today.data
  const h = history.data
  const working = t?.status === 'working'
  const tz = t?.outlet?.timezone ?? 'Asia/Jakarta'

  return (
    <>
      <PageHeader title="Absensi Saya" />
      <div className="grid items-start gap-4 p-4 md:p-6 lg:grid-cols-[minmax(0,480px)_1fr]">
        <div className="space-y-4">
          {today.error ? <Alert>{errorMessage(today.error)}</Alert> : null}
          {!t ? (today.loading ? <Loading /> : null) : (
            <section className={`rounded-lg border bg-surface p-5 md:p-6 ${working ? 'border-2 border-[#22A06B]' : 'border-border'}`}>
              <div className="hidden text-[12px] text-primary md:block">Status hari ini</div>
              {working && t.clock_in_at ? (
                <div className="text-center md:text-left">
                  <div className="mt-2 text-[14px] font-semibold text-success md:mt-6">● Sedang bekerja</div>
                  <div className="mt-1 text-[36px] font-bold leading-tight md:text-[44px]">
                    {workedSince(t.clock_in_at, now)}
                  </div>
                  <div className="mt-1 text-[12px] text-text-muted">
                    Clock in {formatTime(t.clock_in_at, tz)} {ZONE_LABEL[tz]}
                    {t.device_name ? ` · tablet “${t.device_name}”` : ''}{t.outlet ? ` · ${t.outlet.name}` : ''}
                  </div>
                </div>
              ) : (
                <div className="mt-2 text-center text-[14px] font-semibold md:mt-6 md:text-left">
                  ○ Belum clock in. Absen di tablet outlet.
                </div>
              )}
              <div className="mt-6 rounded-lg border border-primary bg-primary-soft px-4 py-3 text-center text-[14px] font-semibold text-primary">
                <span className="hidden md:inline">ⓘ Clock in / out hanya di tablet absensi outlet</span>
                <span className="md:hidden">ⓘ {working ? 'Clock out' : 'Clock in'} di tablet outlet</span>
              </div>
              <p className="mt-4 hidden text-[11px] text-text-muted md:block">
                Tidak ada tombol absen di HP atau admin app. Staf memilih nama + selfie di tablet outlet.
              </p>
            </section>
          )}
          {(t?.flagged_records ?? []).map((f) => (
            <div key={f.id} role="status" className="rounded-lg border border-[#E8C66B] bg-warning-soft px-4 py-3 text-[12px] text-warning">
              ⚠ Kamu lupa clock out {formatDay(f.date)} ({shortOutlet(f.outlet.name)}). Catatan ditandai perlu dikoreksi
              oleh owner.
            </div>
          ))}
        </div>

        <Card title={<span className="text-[14px]">Riwayat saya · minggu ini</span>}>
          {history.error ? <Alert>{errorMessage(history.error)}</Alert> : null}
          {!h ? (history.loading ? <Loading /> : null) : (
            <>
              <p className="text-[12px] text-text-muted md:hidden">Riwayat (tap untuk lihat selfie)</p>
              <table className="hidden w-full text-left text-[12px] md:table">
                <thead className="text-[11px] tracking-wide text-text-muted">
                  <tr>
                    <th className="py-2 font-semibold">TANGGAL</th>
                    <th className="font-semibold">OUTLET</th>
                    <th className="font-semibold">MASUK</th>
                    <th className="font-semibold">PULANG</th>
                    <th className="font-semibold">DURASI</th>
                    <th className="font-semibold">SELFIE</th>
                  </tr>
                </thead>
                <tbody>
                  {h.records.map((r) => (
                    <tr key={r.id} className="cursor-pointer hover:bg-page" onClick={() => setOpen(open === r.id ? undefined : r.id)}>
                      <td className="py-2.5">
                        <button type="button" aria-expanded={open === r.id} aria-label={`Selfie ${formatDay(r.date)}`}
                          onClick={(e) => { e.stopPropagation(); setOpen(open === r.id ? undefined : r.id) }}>
                          {formatDay(r.date)}
                        </button>
                      </td>
                      <td>{shortOutlet(r.outlet.name)}</td>
                      <td>{timeIn(r, r.clock_in_at)}</td>
                      {r.status === 'needs_correction' ? (
                        <><td>—</td><td className="text-danger">⚠ koreksi</td></>
                      ) : (
                        <><td>{timeIn(r, r.clock_out_at, false)}</td><td>{durationCell(r)}</td></>
                      )}
                      <td>{selfieIcons(r)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <ul className="space-y-1.5 text-[13px] md:hidden">
                {h.records.map((r) => (
                  <li key={r.id}>
                    <button type="button" className="text-left" aria-expanded={open === r.id}
                      onClick={() => setOpen(open === r.id ? undefined : r.id)}>
                      {mobileLine(r)}
                    </button>
                  </li>
                ))}
              </ul>
              {h.records.length === 0 && <p className="py-2 text-[12px] text-text-muted">Belum ada absen minggu ini.</p>}
              {open && <MySelfies record={h.records.find((r) => r.id === open)} />}
              <p className="mt-3 text-[12px] text-text-muted">
                Total minggu ini: {formatMinutes(h.total_minutes, true)} (tanpa catatan yang perlu dikoreksi)
              </p>
              <p className="text-[12px] text-text-muted">Staf hanya melihat catatan sendiri.</p>
            </>
          )}
        </Card>
        <p className="text-[11px] text-text-muted md:hidden">
          Absen tidak bisa dari HP. Clock in / out hanya di tablet absensi outlet dengan selfie.
        </p>
      </div>
    </>
  )
}

function mobileLine(r: AttendanceRecord): string {
  const out = r.status === 'needs_correction' ? '— · ⚠' : `${timeIn(r, r.clock_out_at, false)} · ${durationCell(r)}`
  return `${formatDay(r.date)} · ${shortOutlet(r.outlet.name)} · ${timeIn(r, r.clock_in_at, false)}–${out} ${selfieIcons(r)}`
}

function MySelfies({ record }: { record: AttendanceRecord | undefined }) {
  if (!record) return null
  return (
    <div className="mt-3 flex flex-wrap gap-4 rounded-md bg-page p-3 text-[12px]">
      {record.has_selfie_in || record.has_selfie_out ? (
        <>
          {record.has_selfie_in && <SelfieImage id={record.id} which="in" label="Selfie masuk" />}
          {record.has_selfie_out && <SelfieImage id={record.id} which="out" label="Selfie pulang" />}
        </>
      ) : (
        <span className="text-text-muted">Selfie sudah dihapus otomatis setelah 45 hari.</span>
      )}
    </div>
  )
}

function SelfieImage({ id, which, label }: { id: string; which: 'in' | 'out'; label: string }) {
  const { url, failed } = useBlobUrl(`/ops/me/attendance/${id}/selfies/${which}`)
  return (
    <figure className="text-center">
      {url ? <img src={url} alt={label} className="h-28 w-24 rounded-md object-cover" />
        : <div className="flex h-28 w-24 items-center justify-center rounded-md bg-[#CDD6E6] text-text-muted">{failed ? 'terhapus' : ''}</div>}
      <figcaption className="mt-1">{label}</figcaption>
    </figure>
  )
}
