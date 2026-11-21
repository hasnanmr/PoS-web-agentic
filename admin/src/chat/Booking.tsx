// C10 reservation flow (party → date → available time → name + phone → "Cek lagi"), C11 the
// confirmed booking (code, calendar file, saveable link), C12 Reservasi Saya (bookings from
// this phone, or booking code + phone from another phone; reschedule reuses the date and time
// steps of C10 for the same party; changes only until the outlet's cutoff).
import { useEffect, useRef, useState } from 'react'
import { formatTime, todayIn } from '../lib/format'
import type { ChatApi } from './api'
import { friendly } from './copy'
import { addDays, dayLabel, longDate, shortDate, zone } from './dates'
import { randomKey } from './storage'
import type { Availability, Booking, BookingCreated } from './types'
import { Action, Bubble, Chip, Field, FromPhone, TextLink, inputClass } from './ui'

export interface Person {
  name: string
  phone: string
}

/** A time the agent already checked (C15): the flow opens at name + phone with it chosen. */
export interface BookingPreset {
  party_size: number
  start_at: string
  label: string
}

function localDate(iso: string, timezone: string): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' })
    .format(new Date(iso))
}

export function BookingFlow({ api, outletName, timezone, privacyUrl, privacyVersion, reschedule, preset = null, person,
  prefilled, remember, onRemember, onBooked, onRescheduled }: {
  api: ChatApi
  outletName: string
  timezone: string
  privacyUrl: string
  privacyVersion: string
  reschedule: { booking: Booking; key: string } | null
  preset?: BookingPreset | null
  person: Person
  prefilled: boolean
  remember: boolean
  onRemember: (on: boolean) => void
  onBooked: (created: BookingCreated, person: Person) => void
  onRescheduled: (booking: Booking) => void
}) {
  const today = todayIn(timezone)
  const [limits, setLimits] = useState<{ max: number; last: string } | null>(null)
  const [party, setParty] = useState<number | null>(reschedule?.booking.party_size ?? preset?.party_size ?? null)
  const [day, setDay] = useState<string | null>(preset ? localDate(preset.start_at, timezone) : null)
  const [otherDay, setOtherDay] = useState(false)
  const [slotsFor, setSlotsFor] = useState<{ key: string; times: Availability['times'] } | null>(null)
  const [slot, setSlot] = useState<Availability['times'][number] | null>(
    preset ? { start_at: preset.start_at, label: preset.label } : null)
  const [who, setWho] = useState<Person>(person)
  const [whoDone, setWhoDone] = useState(Boolean(reschedule))
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const keys = useRef<{ idempotencyKey: string; accessKey: string } | null>(null)

  useEffect(() => {
    let cancelled = false
    api.availability(1, today).then((a) => {
      if (!cancelled) setLimits({ max: a.max_party_size, last: a.last_date })
    }).catch((e: unknown) => { if (!cancelled) setError(friendly(e)) })
    return () => { cancelled = true }
  }, [api, today])

  const slotsKey = party !== null && day !== null ? `${party}|${day}` : null
  const slots = slotsFor && slotsFor.key === slotsKey ? slotsFor.times : null
  useEffect(() => {
    if (party === null || day === null) return
    let cancelled = false
    const k = `${party}|${day}`
    api.availability(party, day).then((a) => { if (!cancelled) setSlotsFor({ key: k, times: a.times }) })
      .catch((e: unknown) => { if (!cancelled) setError(friendly(e)) })
    return () => { cancelled = true }
  }, [api, party, day])

  // A new choice is a new request: the next confirm gets fresh keys.
  useEffect(() => { keys.current = null }, [party, slot, who.name, who.phone])

  async function confirm() {
    if (!slot || party === null) return
    setBusy(true)
    setError(null)
    keys.current ??= { idempotencyKey: randomKey(), accessKey: randomKey() }
    try {
      if (reschedule) {
        onRescheduled(await api.reschedule(reschedule.booking.reservation_id, reschedule.key, slot.start_at, keys.current.idempotencyKey))
      } else {
        const created = await api.book({
          party_size: party, start_at: slot.start_at, customer: { name: who.name.trim(), phone: who.phone.trim() },
          privacy_notice_version: privacyVersion,
        }, keys.current, preset && slot && Date.parse(slot.start_at) === Date.parse(preset.start_at) ? 'agent' : 'buttons')
        onBooked(created, who)
      }
    } catch (e) {
      setError(friendly(e))
      const code = (e as { code?: string }).code
      if (code === 'slot_unavailable' && day) {
        setSlot(null)
        api.availability(party, day).then((a) => setSlotsFor({ key: `${party}|${day}`, times: a.times })).catch(() => undefined)
      }
    } finally {
      setBusy(false)
    }
  }

  const max = limits?.max ?? 0
  const step = (n: number) => `${n}/${reschedule ? 2 : 4}`
  return (
    <div className="max-w-[92%] space-y-2">
      {!reschedule && (
        <Bubble>
          <p className="mb-2 font-semibold">{step(1)} · Untuk berapa orang?{max ? ` (maks. ${max})` : ''}</p>
          {limits && (max <= 10 ? (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Jumlah orang">
              {Array.from({ length: max }, (_, i) => i + 1).map((n) => (
                <Chip key={n} selected={party === n} onClick={() => { setParty(n); setSlot(null) }}>{n}</Chip>
              ))}
            </div>
          ) : (
            <input aria-label="Jumlah orang" type="number" min={1} max={max} className={inputClass} value={party ?? ''}
              onChange={(e) => setParty(Math.min(max, Math.max(1, Number(e.target.value) || 1)))} />
          ))}
        </Bubble>
      )}
      {party !== null && limits && (
        <Bubble>
          <p className="mb-2 font-semibold">{reschedule ? step(1) : step(2)} · Tanggal</p>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Tanggal">
            {[0, 1, 2].map((n) => addDays(today, n)).filter((d) => d <= limits.last).map((d, i) => (
              <Chip key={d} selected={day === d && !otherDay} onClick={() => { setOtherDay(false); setDay(d); setSlot(null) }}>
                {i === 0 ? `Hari ini · ${dayLabel(d, false)}` : dayLabel(d, true)}
              </Chip>
            ))}
            {addDays(today, 3) <= limits.last && (
              <Chip selected={otherDay} onClick={() => setOtherDay(true)}>Tanggal lain ›</Chip>
            )}
          </div>
          {otherDay && (
            <input aria-label="Tanggal lain" type="date" className={`${inputClass} mt-2`} min={today} max={limits.last}
              value={day ?? ''} onChange={(e) => { setDay(e.target.value || null); setSlot(null) }} />
          )}
        </Bubble>
      )}
      {party !== null && day !== null && (
        <Bubble>
          <p className="mb-2 font-semibold">
            {reschedule ? step(2) : step(3)} · Jam tersedia ({zone(timezone)}) untuk {party} orang
          </p>
          {slots === null ? (
            <p className="text-[12px] text-text-muted">Sebentar ya, cek meja yang kosong…</p>
          ) : slots.length === 0 ? (
            <p className="text-[12px]">Yah, di tanggal itu sudah tidak ada meja yang muat. Coba tanggal lain ya.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Jam">
              {slots.map((s) => <Chip key={s.start_at} selected={slot !== null && Date.parse(slot.start_at) === Date.parse(s.start_at)} onClick={() => setSlot(s)}>{s.label}</Chip>)}
            </div>
          )}
        </Bubble>
      )}
      {!reschedule && slot && (
        <Bubble>
          <p className="mb-2 font-semibold">{step(4)} · Atas nama</p>
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (who.name.trim() && who.phone.trim()) setWhoDone(true) }}>
            <Field label="Nama" hint={prefilled && who.name === person.name && who.name ? <FromPhone /> : undefined}>
              <input className={inputClass} value={who.name} maxLength={60} autoComplete="name"
                onChange={(e) => { setWho({ ...who, name: e.target.value }); setWhoDone(false) }} />
            </Field>
            <Field label="No HP" hint={prefilled && who.phone === person.phone && who.phone ? <FromPhone /> : undefined}>
              <input className={inputClass} value={who.phone} inputMode="tel" maxLength={20} autoComplete="tel"
                onChange={(e) => { setWho({ ...who, phone: e.target.value }); setWhoDone(false) }} />
            </Field>
            <p className="text-[11px] text-text-muted">
              🔒 Nama &amp; no HP hanya untuk booking ini, dihapus setelah booking selesai.{' '}
              <a href={privacyUrl} target="_blank" rel="noreferrer" className="font-semibold text-primary">Kebijakan privasi ›</a>
            </p>
            <label className="flex items-center gap-2 text-[12px]">
              <input type="checkbox" checked={remember} onChange={(e) => onRemember(e.target.checked)} />
              Ingat data di HP ini (tidak disimpan di server)
            </label>
            {!whoDone && <Action type="submit" disabled={!who.name.trim() || !who.phone.trim()}>Lanjut</Action>}
          </form>
        </Bubble>
      )}
      {slot && whoDone && (
        <div className="rounded-xl border border-primary bg-surface p-3 text-[13px]">
          <p>
            {reschedule ? 'Jadwal baru: ' : 'Cek lagi: '}{outletName} · {shortDate(slot.start_at, timezone)} · {slot.label}{' '}
            {zone(timezone)} · {party} orang{reschedule ? '' : ` · a.n. ${who.name.trim()}`}. Meja ditahan 15 menit setelah jam
            booking. Tanpa deposit.
          </p>
          <Action tone="action" className="mt-2" disabled={busy} onClick={confirm}>
            {reschedule ? 'Simpan jadwal baru' : 'Konfirmasi booking'}
          </Action>
        </div>
      )}
      {error && <Bubble tone="danger">{error}</Bubble>}
    </div>
  )
}

export function BookedCard({ booking, calendarUrl, link, onMyBookings, onMenu }: {
  booking: Booking; calendarUrl: string; link: string; onMyBookings: () => void; onMenu: () => void
}) {
  const [copied, setCopied] = useState(false)
  const tz = booking.timezone
  const reminderHours = booking.reminder_at
    ? Math.round((new Date(booking.start_at).getTime() - new Date(booking.reminder_at).getTime()) / 3600000)
    : 0
  return (
    <div className="max-w-[92%] space-y-2">
      <Bubble>
        <p className="mb-1 inline-block rounded-full bg-success-soft px-2 py-0.5 text-[11px] font-semibold text-success">✓ Booking terkonfirmasi</p>
        <p className="text-[11px] text-text-muted">Kode booking</p>
        <p className="text-[24px] font-bold tracking-wider">{booking.booking_code}</p>
        <p>{booking.outlet_name}</p>
        <p>{longDate(booking.start_at, tz)} · {booking.label} {zone(tz)}</p>
        <p>{booking.party_size} orang{booking.guest_name ? ` · a.n. ${booking.guest_name}` : ''} · meja disiapkan outlet</p>
        <p className="mt-1 text-[12px]">
          {booking.hold_until && `Meja ditahan sampai ${formatTime(booking.hold_until, tz)}. `}
          Ubah/batal paling lambat {formatTime(booking.change_until, tz)}.
        </p>
        <a href={calendarUrl}
          className="mt-2 block w-full rounded-lg bg-primary px-3 py-2.5 text-center text-[13px] font-semibold text-white">
          📅 Tambah ke kalender (.ics)
        </a>
        {booking.reminder_at && (
          <p className="mt-1 text-[11px] text-text-muted">
            Pengingat di kalender HP: {formatTime(booking.reminder_at, tz)}
            {reminderHours > 0 ? ` (${reminderHours} jam sebelum, setelan outlet)` : ' (setelan outlet)'}.
          </p>
        )}
        <p className="mt-2 rounded-lg bg-page px-2 py-1.5 text-[11px] text-primary">
          🔗 Simpan link booking ·{' '}
          <TextLink className="text-[11px]" onClick={async () => {
            try { await navigator.clipboard.writeText(link); setCopied(true) } catch { setCopied(false) }
          }}>{copied ? 'Tersalin ✓' : 'Salin'}</TextLink>
          . Di HP lain: Reservasi Saya → kode booking + no HP.
        </p>
      </Bubble>
      <div className="grid grid-cols-2 gap-2">
        <Action tone="ghost" onClick={onMyBookings}>Reservasi Saya</Action>
        <Action tone="ghost" onClick={onMenu}>Lihat menu</Action>
      </div>
    </div>
  )
}

export function MyBookings({ bookings, calendarUrl, error, busy, onReschedule, onCancel, onLookup }: {
  bookings: Booking[] | null
  calendarUrl: (b: Booking) => string
  error: string | null
  busy: boolean
  onReschedule: (b: Booking) => void
  onCancel: (b: Booking) => void
  onLookup: (code: string, phone: string) => void
}) {
  const [code, setCode] = useState('')
  const [phone, setPhone] = useState('')
  return (
    <div className="max-w-[92%] space-y-2">
      <Bubble>
        <p className="mb-2 font-semibold">Booking mendatang dari HP ini</p>
        {bookings === null ? (
          <p className="text-[12px] text-text-muted">Memuat…</p>
        ) : bookings.length === 0 ? (
          <p className="text-[12px] text-text-muted">Belum ada booking dari HP ini.</p>
        ) : (
          <ul className="space-y-2">
            {bookings.map((b) => (
              <li key={b.reservation_id} className="rounded-lg bg-page p-2">
                <p>{b.booking_code} · {shortDate(b.start_at, b.timezone)} · {b.label} {zone(b.timezone)} · {b.party_size} orang</p>
                <p className="text-[11px] text-text-muted">
                  {b.can_change ? `Bisa diubah/batal s/d ${formatTime(b.change_until, b.timezone)}` : 'Sudah tidak bisa diubah lewat chat'}
                </p>
                <p className="mt-1 flex flex-wrap gap-3">
                  <TextLink disabled={busy} onClick={() => onReschedule(b)}>↻ Jadwal ulang</TextLink>
                  <TextLink disabled={busy} onClick={() => onCancel(b)}>✕ Batalkan</TextLink>
                  <a href={calendarUrl(b)} className="text-[12px] font-semibold text-primary">📅 Kalender</a>
                </p>
              </li>
            ))}
          </ul>
        )}
      </Bubble>
      {error && <Bubble tone="danger">{error}</Bubble>}
      <Bubble>
        <p className="mb-2 font-semibold">Booking dari HP lain?</p>
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); onLookup(code.trim(), phone.trim()) }}>
          <input aria-label="Kode booking" className={inputClass} placeholder="Kode booking, mis. 7Q2KXM" value={code}
            maxLength={6} autoCapitalize="characters" onChange={(e) => setCode(e.target.value.toUpperCase())} />
          <input aria-label="No HP yang dipakai saat booking" className={inputClass} placeholder="No HP yang dipakai saat booking"
            value={phone} inputMode="tel" maxLength={20} onChange={(e) => setPhone(e.target.value)} />
          <Action type="submit" disabled={busy || code.length !== 6 || phone.length < 8}>Cari booking</Action>
        </form>
      </Bubble>
    </div>
  )
}
