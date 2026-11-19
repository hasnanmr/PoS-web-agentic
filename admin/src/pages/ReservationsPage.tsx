// Wireframe S6 — Reservasi & Meja (hari ini); mobile M4 (T-062, T-063, T-064, T-070).
// Endpoints: GET /ops/outlets/{id}/reservations?date=, POST /ops/outlets/{id}/reservations,
// POST /ops/outlets/{id}/walk-ins, GET /ops/reservations/{id},
// POST /ops/reservations/{id}/seat|move|cancel|no-show|complete.
// Desktop: timeline per table. Mobile (M4): list by time. Buttons come from `allowed_actions`.
import { useEffect, useState } from 'react'
import { useSession } from '../app/session'
import { ApiError, errorMessage } from '../lib/api'
import { formatTime, hhmm, offsetAt } from '../lib/format'
import type { ReservationAction, ReservationBoard, ReservationDetail, ReservationRow } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { usePolling } from '../lib/usePolling'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Card, LinkButton, Loading, Select, TextInput } from '../ui/kit'

const ZONE_LABEL: Record<string, string> = { 'Asia/Jakarta': 'WIB', 'Asia/Makassar': 'WITA', 'Asia/Jayapura': 'WIT' }


const SOURCE: Record<ReservationRow['source'], string> = {
  whatsapp: 'WhatsApp',
  phone: 'Telepon',
  in_person: 'Langsung',
  walk_in: 'Tanpa reservasi',
}

const ACTION_LABEL: Record<ReservationAction, string> = {
  seat: 'Seated',
  move: 'Pindah meja',
  cancel: 'Batalkan',
  no_show: 'No-show',
  complete: 'Selesai',
}
const ACTION_PATH: Record<Exclude<ReservationAction, 'move'>, string> = {
  seat: 'seat',
  cancel: 'cancel',
  no_show: 'no-show',
  complete: 'complete',
}

type Look = 'booked' | 'seated' | 'walk_in' | 'hold' | 'no_show' | 'completed'
const LOOK: Record<Look, string> = {
  booked: 'border-primary bg-primary-soft text-primary',
  seated: 'border-[#6B4FA3] bg-[#F1ECFB] text-[#6B4FA3]',
  walk_in: 'border-[#22A06B] bg-success-soft text-success',
  hold: 'border-[#E0A800] bg-warning-soft text-warning',
  no_show: 'border-dashed border-[#9AA0A6] bg-[#F3F4F6] text-text-muted',
  completed: 'border-[#9AA0A6] bg-[#F3F4F6] text-text-muted',
}

/** Wall clock for hold / now-line rendering, refreshed every `ms`. */
function useNow(ms: number): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), ms)
    return () => window.clearInterval(timer)
  }, [ms])
  return now
}

function look(r: ReservationRow, now: number): Look {
  if (r.status === 'no_show') return 'no_show'
  if (r.status === 'completed') return 'completed'
  if (r.source === 'walk_in') return 'walk_in'
  if (r.status === 'seated') return 'seated'
  if (r.hold_until && now >= new Date(r.starts_at).getTime()) return 'hold'
  return 'booked'
}

function addDays(day: string, n: number): string {
  const d = new Date(`${day}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

function dayLabel(day: string, style: 'long' | 'short'): string {
  return new Intl.DateTimeFormat('id-ID', style === 'long'
    ? { weekday: 'long', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }
    : { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' }).format(new Date(`${day}T00:00:00Z`))
}

/** Minutes since local midnight of `day` in the outlet zone, clamped to the day. */
function minuteOfDay(iso: string, day: string, tz: string): number {
  const local = new Intl.DateTimeFormat('en-CA', {
    timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(new Date(iso))
  const get = (t: string) => local.find((p) => p.type === t)?.value ?? '00'
  const date = `${get('year')}-${get('month')}-${get('day')}`
  if (date < day) return 0
  if (date > day) return 24 * 60
  return (Number(get('hour')) % 24) * 60 + Number(get('minute'))
}

function blockText(r: ReservationRow, tz: string, now: number): [string, string] {
  const t = (iso: string) => formatTime(iso, tz)
  const range = `${t(r.starts_at)}–${t(r.ends_at)}`
  switch (look(r, now)) {
    case 'walk_in': return ['Tanpa reservasi · terisi', range]
    case 'hold': return [`${r.guest_name} · ${r.party_size} · hold 15 mnt ⏱`, `${t(r.starts_at)} — no-show ${t(r.hold_until!)}`]
    case 'no_show': return [`${r.guest_name} · ${r.party_size} · no-show`, `${t(r.starts_at)} (dilepas)`]
    case 'completed': return [`${r.guest_name ?? 'Tanpa reservasi'} · ${r.party_size} · selesai`, range]
    default: return [`${r.guest_name} · ${r.party_size} · ${r.status}`, range]
  }
}

function tableLabel(t: { name: string; capacity: number; area: string | null }): string {
  return `${t.name} · ${t.capacity} org${t.area && t.area !== 'Indoor' ? ` (${t.area})` : ''}`
}

function reservationError(e: unknown): string {
  if (e instanceof ApiError && e.code === 'conflict') return 'Meja sudah dibooking atau terisi di jam itu (bentrok).'
  return errorMessage(e)
}

export default function ReservationsPage() {
  const { api, outlet } = useSession()
  const outletId = outlet?.id ?? ''
  const [day, setDay] = useState<string>()
  const board = useLoad(
    () => api.get<ReservationBoard>(`/ops/outlets/${outletId}/reservations${day ? `?date=${day}` : ''}`),
    `${outletId}|${day ?? ''}`,
  )
  usePolling(board, 30_000) // holds turn into no-shows and other staff's changes show up
  const now = useNow(30_000)
  const [selected, setSelected] = useState<string>()
  const [form, setForm] = useState<'booking' | 'walk_in'>()
  const [notice, setNotice] = useState<string>()

  if (!outlet) return <PageHeader title="Reservasi & Meja" />
  const data = board.data
  const timezone = data?.timezone ?? outlet.timezone
  const zoneLabel = ZONE_LABEL[timezone] ?? timezone
  const shown = data?.date ?? day
  const refresh = async (text?: string) => {
    setNotice(text)
    await board.reload()
  }
  const actions = (
    <div className="flex flex-wrap gap-2">
      <Button variant="ghost" onClick={() => setForm('walk_in')}>
        Tandai meja terisi<span className="hidden md:inline">&nbsp;(tanpa reservasi)</span>
      </Button>
      <Button onClick={() => setForm('booking')}>
        + Booking<span className="hidden md:inline">&nbsp;telepon / langsung</span>
      </Button>
    </div>
  )

  return (
    <>
      <PageHeader title="Reservasi & Meja" actions={<div className="hidden md:block">{actions}</div>} />
      <div className="space-y-4 p-4 md:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-[13px]">
            <button type="button" aria-label="Hari sebelumnya" className="h-8 w-8 rounded-md hover:bg-surface"
              disabled={!shown} onClick={() => shown && setDay(addDays(shown, -1))}>‹</button>
            <span className="font-semibold">
              {shown ? <><span className="hidden md:inline">{dayLabel(shown, 'long')}</span><span className="md:hidden">{dayLabel(shown, 'short')}</span></> : '…'} ({zoneLabel})
            </span>
            <button type="button" aria-label="Hari berikutnya" className="h-8 w-8 rounded-md hover:bg-surface"
              disabled={!shown} onClick={() => shown && setDay(addDays(shown, 1))}>›</button>
          </div>
          <div className="md:hidden">{actions}</div>
        </div>
        {notice && <Alert tone="success">{notice}</Alert>}
        {form === 'booking' && data && (
          <BookingForm board={data} defaultDay={shown!} onCancel={() => setForm(undefined)}
            onDone={async (r, bookedDay) => {
              setForm(undefined)
              setDay(bookedDay)
              setSelected(r.id)
              await refresh(`Booking ${r.guest_name} · ${r.party_size} orang · ${r.table_name} disimpan.`)
            }} />
        )}
        {form === 'walk_in' && data && (
          <WalkInForm board={data} onCancel={() => setForm(undefined)} onDone={async (r) => {
            setForm(undefined)
            setSelected(r.id)
            await refresh(`${r.table_name} ditandai terisi (tanpa reservasi).`)
          }} />
        )}
        {board.error && !data ? <Alert>{errorMessage(board.error)}</Alert> : !data ? <Loading /> : (
          <>
            <Timeline board={data} now={now} selected={selected} onSelect={setSelected} />
            <MobileList board={data} now={now} selected={selected} onSelect={setSelected} onChanged={refresh} />
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="hidden md:block">
                {selected && data.reservations.some((r) => r.id === selected) ? (
                  <DetailCard key={selected} id={selected} board={data} now={now} onChanged={refresh} />
                ) : (
                  <Card title="Detail"><p className="text-[12px] text-text-muted">Pilih reservasi di timeline untuk melihat detail dan aksi.</p></Card>
                )}
              </div>
              <Card title="Legenda & aturan">
                <div className="flex flex-wrap gap-3 text-[12px]">
                  {([['booked', 'booked'], ['seated', 'seated'], ['walk_in', 'terisi tanpa reservasi'], ['hold', 'hold 15 mnt'], ['no_show', 'no-show']] as [Look, string][]).map(([k, label]) => (
                    <span key={k} className="flex items-center gap-1">
                      <span className={`inline-block h-3 w-3 rounded-sm border ${LOOK[k]}`} />{label}
                    </span>
                  ))}
                </div>
                <ul className="mt-2 space-y-1 text-[12px] text-text-muted">
                  <li>• Overlap ditolak di level database (pesan error jika bentrok).</li>
                  <li>• Meja terisi tanpa reservasi memblokir slot dari booking baru.</li>
                  <li>• Tanpa deposit. Semua jam dalam zona waktu outlet.</li>
                  <li>• Setiap perubahan menyimpan aktor &amp; waktu.</li>
                </ul>
              </Card>
            </div>
          </>
        )}
      </div>
    </>
  )
}

function Timeline({ board, now, selected, onSelect }: {
  board: ReservationBoard; now: number; selected?: string; onSelect: (id: string) => void
}) {
  const tz = board.timezone
  const toMin = (hms: string) => Number(hms.slice(0, 2)) * 60 + Number(hms.slice(3, 5))
  const spans = board.reservations.map((r) => [minuteOfDay(r.starts_at, board.date, tz), minuteOfDay(r.ends_at, board.date, tz)])
  const first = Math.min(toMin(board.settings.bookable_from), ...spans.map((s) => s[0]))
  const last = Math.max(toMin(board.settings.bookable_until), ...spans.map((s) => s[1]))
  const startHour = Math.floor(first / 60)
  const endHour = Math.min(24, Math.max(startHour + 1, Math.ceil(last / 60)))
  const total = (endHour - startHour) * 60
  const pct = (m: number) => `${((m - startHour * 60) / total) * 100}%`
  const nowMin = minuteOfDay(new Date(now).toISOString(), board.date, tz)
  const showNow = nowMin > startHour * 60 && nowMin < endHour * 60 && nowMin !== 0 && nowMin !== 24 * 60
  const hours = Array.from({ length: endHour - startHour + 1 }, (_, i) => startHour + i)

  return (
    <section aria-label="Timeline meja" className="hidden overflow-x-auto rounded-lg border border-border bg-surface p-4 md:block">
      <div className="min-w-[760px]">
        <div className="grid grid-cols-[140px_1fr] text-[11px] font-semibold text-text-muted">
          <span>MEJA</span>
          <div className="relative h-4">
            {hours.map((h) => (
              <span key={h} className="absolute -translate-x-1/2" style={{ left: pct(h * 60) }}>{String(h).padStart(2, '0')}:00</span>
            ))}
          </div>
        </div>
        {board.tables.map((t) => (
          <div key={t.id} className="grid grid-cols-[140px_1fr] items-center border-t border-border">
            <span className="py-3 text-[12px]">{tableLabel(t)}</span>
            <div className="relative h-12">
              {hours.map((h) => <span key={h} className="absolute inset-y-0 border-l border-border/60" style={{ left: pct(h * 60) }} />)}
              {board.reservations.filter((r) => r.table_id === t.id).map((r) => {
                const [line1, line2] = blockText(r, tz, now)
                const start = minuteOfDay(r.starts_at, board.date, tz)
                const end = Math.max(start + 15, minuteOfDay(r.ends_at, board.date, tz))
                return (
                  <button key={r.id} type="button" onClick={() => onSelect(r.id)} title={`${line1} · ${line2}`}
                    className={`absolute inset-y-1 overflow-hidden rounded-md border px-1.5 text-left text-[11px] leading-tight ${LOOK[look(r, now)]} ${selected === r.id ? 'ring-2 ring-primary' : ''}`}
                    style={{ left: pct(start), width: `calc(${pct(end)} - ${pct(start)})` }}>
                    <span className="block truncate font-semibold">{line1}</span>
                    <span className="block truncate">{line2}</span>
                  </button>
                )
              })}
              {showNow && <span aria-hidden className="absolute inset-y-0 w-0.5 bg-danger" style={{ left: pct(nowMin) }} />}
            </div>
          </div>
        ))}
        {board.tables.length === 0 && <p className="pt-3 text-[12px] text-text-muted">Belum ada meja. Owner menambah meja di Pengaturan → Meja &amp; Reservasi.</p>}
      </div>
    </section>
  )
}

function MobileList({ board, now, selected, onSelect, onChanged }: {
  board: ReservationBoard; now: number; selected?: string; onSelect: (id: string) => void
  onChanged: (text?: string) => Promise<void>
}) {
  const tz = board.timezone
  return (
    <section aria-label="Daftar reservasi" className="space-y-2 md:hidden">
      {board.reservations.map((r) => {
        const kind = look(r, now)
        const name = r.source === 'walk_in' ? 'Tanpa reservasi' : r.guest_name
        const status = kind === 'hold' ? null : kind === 'walk_in' ? 'terisi' : kind === 'no_show' ? 'no-show'
          : kind === 'completed' ? 'selesai' : r.status
        return (
          <div key={r.id} className={`rounded-lg border bg-surface p-3 text-[12px] ${selected === r.id ? 'border-primary' : 'border-border'}`}>
            <button type="button" className="w-full text-left" onClick={() => onSelect(r.id)}>
              <span className="block font-semibold">
                {formatTime(r.starts_at, tz)} · {name} · {r.party_size} org · {r.table_name}{status ? ` · ${status}` : ''}
              </span>
              {kind === 'hold' && <span className="block text-warning">Hold — auto no-show {formatTime(r.hold_until!, tz)}</span>}
            </button>
            {selected === r.id && r.allowed_actions.length > 0 && (
              <div className="mt-2"><ActionBar row={r} board={board} onChanged={onChanged} /></div>
            )}
          </div>
        )
      })}
      {board.reservations.length === 0 && <p className="text-[12px] text-text-muted">Belum ada reservasi hari ini.</p>}
      <p className="text-[11px] text-text-muted">Timeline per meja di desktop → daftar per jam di mobile.</p>
    </section>
  )
}

function ActionBar({ row, board, onChanged }: {
  row: ReservationRow; board: ReservationBoard; onChanged: (text?: string) => Promise<void>
}) {
  const { api } = useSession()
  const [moving, setMoving] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const targets = board.tables.filter((t) => t.id !== row.table_id && t.capacity >= row.party_size &&
    (row.status !== 'booked' || t.is_bookable))

  async function run(path: string, body: unknown, text: string) {
    setBusy(true)
    setError(undefined)
    try {
      await api.post(`/ops/reservations/${row.id}/${path}`, body)
      await onChanged(text)
    } catch (e) {
      setError(reservationError(e))
    } finally {
      setBusy(false)
    }
  }

  const name = row.guest_name ?? row.table_name
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        {row.allowed_actions.map((a) => a === 'move' ? (
          moving ? (
            <Select key={a} aria-label="Pindah ke meja" className="h-9 w-auto" disabled={busy} defaultValue=""
              onChange={(e) => e.target.value && void run('move', { table_id: e.target.value },
                `${name} dipindah ke ${board.tables.find((t) => t.id === e.target.value)?.name}.`)}>
              <option value="">Pilih meja…</option>
              {targets.map((t) => <option key={t.id} value={t.id}>{tableLabel(t)}</option>)}
            </Select>
          ) : (
            <Button key={a} variant="ghost" disabled={busy} onClick={() => setMoving(true)}>Pindah meja ▾</Button>
          )
        ) : (
          <Button key={a} variant={a === 'seat' || a === 'complete' ? 'primary' : a === 'cancel' ? 'danger' : 'ghost'}
            disabled={busy} onClick={() => void run(ACTION_PATH[a], undefined, `${name}: ${ACTION_LABEL[a].toLowerCase()}.`)}>
            {ACTION_LABEL[a]}
          </Button>
        ))}
      </div>
      {error && <div className="mt-2"><Alert>{error}</Alert></div>}
    </div>
  )
}

function eventText(e: ReservationDetail['events'][number], source: ReservationRow['source']): string {
  const who = e.actor_name ? ` (${e.actor_name})` : ''
  if (e.event === 'created') return `dibuat via ${source === 'whatsapp' ? 'WA' : SOURCE[source].toLowerCase()}${who}`
  if (e.event === 'table_changed') return `pindah ${e.from_table ?? '?'} → ${e.to_table ?? '?'}${who}`
  if (e.event === 'reminder_sent') return 'reminder terkirim'
  if (e.event === 'status_changed') {
    if (e.to_status === 'no_show' && e.actor_type === 'system') return 'auto no-show (meja dilepas)'
    const label: Record<string, string> = { seated: 'seated', cancelled: 'dibatalkan', no_show: 'ditandai no-show', completed: 'selesai' }
    return `${label[e.to_status ?? ''] ?? e.to_status}${who}`
  }
  return e.event
}

function DetailCard({ id, board, now, onChanged }: {
  id: string; board: ReservationBoard; now: number; onChanged: (text?: string) => Promise<void>
}) {
  const { api } = useSession()
  const row = board.reservations.find((r) => r.id === id)!
  const detail = useLoad(() => api.get<ReservationDetail>(`/ops/reservations/${id}`), `${id}|${row.status}|${row.table_id}`)
  const d = detail.data
  const tz = board.timezone
  const t = (iso: string) => formatTime(iso, tz)
  const kind = look(row, now)
  const name = row.source === 'walk_in' ? 'Tanpa reservasi' : row.guest_name
  const status = kind === 'hold' ? `booked → hold (auto no-show ${t(row.hold_until!)})`
    : row.status === 'booked' && row.hold_until ? `booked (hold sampai ${t(row.hold_until)})`
    : row.source === 'walk_in' && row.status === 'seated' ? 'terisi tanpa reservasi'
    : row.status === 'no_show' ? `no-show${row.no_show_at ? ` ${t(row.no_show_at)}` : ''} · meja dilepas`
    : row.status
  return (
    <Card title={`Detail: ${name} · ${row.party_size} orang · ${t(row.starts_at)}–${t(row.ends_at)} · ${row.table_name}`}>
      <div className="space-y-1 text-[12px]">
        <p>Sumber: {SOURCE[row.source]}{d?.phone_masked ? ` · ${d.phone_masked}` : ''}</p>
        <p>Status: {status}</p>
        {row.allowed_actions.length > 0 && (
          <div className="flex flex-wrap items-start gap-2 pt-1">
            <span className="pt-2">Aksi:</span>
            <ActionBar row={row} board={board} onChanged={onChanged} />
          </div>
        )}
        <p className="pt-1 text-text-muted">
          Riwayat: {d ? d.events.map((e) => `${t(e.created_at)} ${eventText(e, row.source)}`).join(' · ') : '…'}
        </p>
      </div>
    </Card>
  )
}

function BookingForm({ board, defaultDay, onDone, onCancel }: {
  board: ReservationBoard; defaultDay: string
  onDone: (r: ReservationDetail, day: string) => Promise<void>; onCancel: () => void
}) {
  const { api, outlet } = useSession()
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [party, setParty] = useState('2')
  const [date, setDate] = useState(defaultDay)
  const [time, setTime] = useState(hhmm(board.settings.bookable_from))
  const [tableId, setTableId] = useState('')
  const [source, setSource] = useState<'phone' | 'in_person'>('phone')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const size = Number(party)
  const valid = name.trim() !== '' && size >= 1 && date !== '' && time !== ''
  const fits = board.tables.filter((t) => t.is_bookable && t.capacity >= size)
  // A table that no longer fits the party drops out of the list: fall back to automatic.
  const chosen = fits.some((t) => t.id === tableId) ? tableId : ''

  return (
    <Card title="+ Booking telepon / langsung">
      <div className="grid gap-3 text-[12px] sm:grid-cols-2 lg:grid-cols-4">
        <label>Nama tamu<TextInput aria-label="Nama tamu" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} /></label>
        <label>No. HP (opsional)<TextInput aria-label="No. HP" inputMode="tel" value={phone} placeholder="+62 812…" onChange={(e) => setPhone(e.target.value)} /></label>
        <label>Jumlah orang (maks. {board.settings.max_party_size})
          <TextInput aria-label="Jumlah orang" inputMode="numeric" value={party} onChange={(e) => setParty(e.target.value.replace(/\D/g, ''))} />
        </label>
        <label>Meja
          <Select aria-label="Meja booking" value={chosen} onChange={(e) => setTableId(e.target.value)}>
            <option value="">Otomatis (meja terkecil yang cukup)</option>
            {fits.map((t) => <option key={t.id} value={t.id}>{tableLabel(t)}</option>)}
          </Select>
        </label>
        <label>Tanggal<TextInput aria-label="Tanggal booking" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        <label>Jam<TextInput aria-label="Jam booking" type="time" value={time} onChange={(e) => setTime(e.target.value)} /></label>
        <fieldset className="sm:col-span-2">
          <legend>Sumber</legend>
          <div className="mt-2 flex gap-4">
            <label className="flex items-center gap-1"><input type="radio" checked={source === 'phone'} onChange={() => setSource('phone')} /> Telepon</label>
            <label className="flex items-center gap-1"><input type="radio" checked={source === 'in_person'} onChange={() => setSource('in_person')} /> Langsung</label>
          </div>
        </fieldset>
      </div>
      <p className="mt-2 text-[11px] text-text-muted">
        Jam booking {hhmm(board.settings.bookable_from)}–{hhmm(board.settings.bookable_until)}, durasi {board.settings.default_duration_minutes} menit, hold {board.settings.hold_minutes} menit lalu otomatis no-show.
      </p>
      {error && <div className="mt-2"><Alert>{error}</Alert></div>}
      <div className="mt-3 flex gap-3">
        <Button variant="action" disabled={!valid || busy} onClick={async () => {
          setBusy(true)
          setError(undefined)
          try {
            const res = await api.post<ReservationDetail>(`/ops/outlets/${outlet!.id}/reservations`, {
              guest_name: name.trim(),
              guest_phone: phone.trim() || null,
              party_size: size,
              starts_at: `${date}T${time}:00${offsetAt(board.timezone, date, time)}`,
              table_id: chosen || null,
              source,
            })
            await onDone(res, date)
          } catch (e) {
            setError(reservationError(e))
            setBusy(false)
          }
        }}>Simpan booking</Button>
        <LinkButton onClick={onCancel}>Batal</LinkButton>
      </div>
    </Card>
  )
}

function WalkInForm({ board, onDone, onCancel }: {
  board: ReservationBoard; onDone: (r: ReservationDetail) => Promise<void>; onCancel: () => void
}) {
  const { api, outlet } = useSession()
  const [tableId, setTableId] = useState('')
  const [party, setParty] = useState('2')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const size = Number(party)
  const fits = board.tables.filter((t) => t.capacity >= size)
  const chosen = fits.some((t) => t.id === tableId) ? tableId : ''
  return (
    <Card title="Tandai meja terisi (tanpa reservasi)">
      <div className="grid gap-3 text-[12px] sm:grid-cols-2">
        <label>Meja
          <Select aria-label="Meja terisi" value={chosen} onChange={(e) => setTableId(e.target.value)}>
            <option value="">Pilih meja</option>
            {fits.map((t) => <option key={t.id} value={t.id}>{tableLabel(t)}</option>)}
          </Select>
        </label>
        <label>Jumlah orang
          <TextInput aria-label="Jumlah orang terisi" inputMode="numeric" value={party} onChange={(e) => setParty(e.target.value.replace(/\D/g, ''))} />
        </label>
      </div>
      <p className="mt-2 text-[11px] text-text-muted">
        Meja terisi mulai sekarang selama {board.settings.default_duration_minutes} menit dan tidak ditawarkan untuk booking yang bentrok. Tandai “Selesai” saat tamu pulang.
      </p>
      {error && <div className="mt-2"><Alert>{error}</Alert></div>}
      <div className="mt-3 flex gap-3">
        <Button variant="action" disabled={!chosen || size < 1 || busy} onClick={async () => {
          setBusy(true)
          setError(undefined)
          try {
            await onDone(await api.post<ReservationDetail>(`/ops/outlets/${outlet!.id}/walk-ins`, { table_id: chosen, party_size: size }))
          } catch (e) {
            setError(reservationError(e))
            setBusy(false)
          }
        }}>Tandai terisi</Button>
        <LinkButton onClick={onCancel}>Batal</LinkButton>
      </div>
    </Card>
  )
}
