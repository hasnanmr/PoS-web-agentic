// Wireframe O8 — Meja & Aturan Reservasi (T-057) with the table QR (T-136, issue #44) and
// "O8 Link outlet & QR" on page 07 (T-147).
// Endpoints: GET/POST /owner/outlets/{id}/tables, PATCH/DELETE /owner/tables/{id},
// GET/PUT /owner/outlets/{id}/reservation-settings, GET /owner/tables/{id}/qr.png,
// GET /owner/outlets/{id}/tables/qr.pdf, POST /owner/tables/{id}/qr-token,
// GET/PUT /owner/outlets/{id}/public-link, GET /owner/outlets/{id}/outlet-qr.png | outlet-poster.pdf.
// All times in the outlet's time zone.
// Behaviour notes (canvas): the QR always opens the web chat (/o/<slug>, /t/<token>); the
// "Tujuan QR" choice is gone. Changing the slug or "↻ Ganti" a table token makes the old link
// or printed QR stop working at once (C13), so both ask for confirmation first. Owner only.
import { useState } from 'react'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { hhmm } from '../lib/format'
import type { OutletPublicLink, OwnerTable, ReservationSettings } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Card, FieldRow, LinkButton, Loading, TextInput } from '../ui/kit'

const ZONE: Record<string, string> = { 'Asia/Jakarta': 'WIB', 'Asia/Makassar': 'WITA', 'Asia/Jayapura': 'WIT' }

export default function TablesPage() {
  const { api, outlet } = useSession()
  const outletId = outlet?.id ?? ''
  const tables = useLoad(() => api.get<OwnerTable[]>(`/owner/outlets/${outletId}/tables`), outletId)
  const settings = useLoad(
    () => api.get<ReservationSettings>(`/owner/outlets/${outletId}/reservation-settings`),
    outletId,
  )
  const [editing, setEditing] = useState<OwnerTable | 'new'>()
  const [qrError, setQrError] = useState<string>()

  async function download(path: string, accept: string, filename: string) {
    setQrError(undefined)
    try {
      const blob = await api.blob(path, accept)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setQrError(errorMessage(e))
    }
  }

  if (!outlet) return <PageHeader title="Meja & Reservasi" />
  return (
    <>
      <PageHeader title={`Meja & Reservasi · ${outlet.name}`} />
      <div className="grid gap-4 p-4 md:p-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <OutletLinkCard key={outletId} outletId={outletId} outletName={outlet.name} tableCount={tables.data?.length ?? null}
          onDownload={(path, accept, filename) => void download(path, accept, filename)} error={qrError} />
        <Card title="Daftar meja" actions={(
          <div className="flex items-center gap-3">
            {(tables.data?.length ?? 0) > 0 && (
              <LinkButton className="text-[12px]" onClick={() => void download(
                `/owner/outlets/${outletId}/tables/qr.pdf`, 'application/pdf', 'qr-meja.pdf')}>
                ⭳ Unduh semua QR (PDF)
              </LinkButton>
            )}
            <Button onClick={() => setEditing('new')}>+ Meja</Button>
          </div>
        )}>
          {editing && (
            <TableForm key={editing === 'new' ? 'new' : editing.id} table={editing === 'new' ? undefined : editing}
              onDone={async () => {
                setEditing(undefined)
                await tables.reload()
              }}
              onCancel={() => setEditing(undefined)} />
          )}
          {tables.loading && !tables.data ? <Loading /> : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[12px]">
                <thead className="text-[11px] uppercase text-text-muted">
                  <tr>
                    <th className="py-2 pr-2 font-semibold">Meja</th>
                    <th className="py-2 pr-2 font-semibold">Kapasitas</th>
                    <th className="py-2 pr-2 font-semibold">Area</th>
                    <th className="py-2 pr-2 font-semibold">Bisa di-book</th>
                    <th className="py-2 font-semibold">QR meja</th>
                  </tr>
                </thead>
                <tbody>
                  {(tables.data ?? []).map((t) => (
                    <tr key={t.id} className="border-t border-border">
                      <td className="py-2 pr-2">
                        <LinkButton className="text-[12px] font-semibold" aria-label={`Ubah meja ${t.name}`}
                          onClick={() => setEditing(t)}>{t.name}</LinkButton>
                      </td>
                      <td className="py-2 pr-2">{t.capacity}</td>
                      <td className="py-2 pr-2">{t.area ?? '—'}</td>
                      <td className="py-2 pr-2">
                        {t.is_bookable ? <span className="text-success">✓</span>
                          : <span className="text-text-muted">✕ (tidak via reservasi)</span>}
                      </td>
                      <td className="py-2">
                        <QrCell table={t} onDownload={() => void download(
                          `/owner/tables/${t.id}/qr.png`, 'image/png', `qr-meja-${t.name}.png`)} />
                      </td>
                    </tr>
                  ))}
                  {tables.data?.length === 0 && (
                    <tr><td colSpan={5} className="py-3 text-text-muted">Belum ada meja. Tambah dengan “+ Meja”.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-3 text-[11px] leading-[18px] text-text-muted">
            QR meja membuka web chat untuk meja itu (/t/‹token›): pelanggan pesan dine-in dan bayar dulu dengan QRIS
            statis outlet, lalu staf mengonfirmasi. “↻ Ganti” membuat token baru: QR lama langsung tidak berlaku dan
            harus dicetak ulang.
          </p>
        </Card>
        <Card title="Aturan reservasi">
          {settings.data ? (
            <RulesForm key={outletId} initial={settings.data} zone={ZONE[outlet.timezone] ?? outlet.timezone}
              onSaved={() => void settings.reload()} />
          ) : settings.error ? <Alert>{errorMessage(settings.error)}</Alert> : <Loading />}
        </Card>
      </div>
    </>
  )
}

function QrCell({ table, onDownload }: { table: OwnerTable; onDownload: () => void }) {
  const { api } = useSession()
  const [confirming, setConfirming] = useState(false)
  const [state, setState] = useState<{ tone: 'success' | 'danger'; text: string }>()
  const [busy, setBusy] = useState(false)
  if (confirming) {
    return (
      <span className="flex flex-wrap items-center gap-2">
        <span>Ganti QR {table.name}? QR lama tidak berlaku.</span>
        <Button variant="danger" className="h-7 px-2 text-[12px]" disabled={busy} onClick={async () => {
          setBusy(true)
          try {
            await api.post(`/owner/tables/${table.id}/qr-token`, {})
            setState({ tone: 'success', text: 'QR baru dibuat. Unduh & cetak ulang.' })
            setConfirming(false)
          } catch (e) {
            setState({ tone: 'danger', text: errorMessage(e) })
          } finally {
            setBusy(false)
          }
        }}>Ya, ganti</Button>
        <LinkButton className="text-[12px]" onClick={() => setConfirming(false)}>Batal</LinkButton>
      </span>
    )
  }
  return (
    <span className="flex flex-wrap items-center gap-1 text-primary">
      <LinkButton className="text-[12px]" aria-label={`Unduh QR meja ${table.name}`} onClick={onDownload}>⭳ Unduh</LinkButton>
      <span aria-hidden="true" className="text-text-muted">·</span>
      <LinkButton className="text-[12px]" aria-label={`Ganti QR meja ${table.name}`}
        onClick={() => { setState(undefined); setConfirming(true) }}>↻ Ganti</LinkButton>
      {state && <span className={`w-full text-[11px] ${state.tone === 'success' ? 'text-success' : 'text-danger'}`}>{state.text}</span>}
    </span>
  )
}

// O8 "Link outlet & QR" (page 07): the outlet link /o/<slug> for Instagram, Google Maps, posters,
// and the counter, its QR, and the table QR downloads.
function OutletLinkCard({ outletId, outletName, tableCount, onDownload, error }: {
  outletId: string; outletName: string; tableCount: number | null; error?: string
  onDownload: (path: string, accept: string, filename: string) => void
}) {
  const { api } = useSession()
  const link = useLoad(() => api.get<OutletPublicLink>(`/owner/outlets/${outletId}/public-link`), outletId)
  const [draft, setDraft] = useState<string>()
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string }>()
  const data = link.data
  const slug = draft ?? data?.slug ?? ''
  const cleaned = slug.trim().toLowerCase()
  const changed = data !== undefined && cleaned !== data.slug
  const prefix = data?.url ? data.url.slice(0, data.url.length - data.slug.length).replace(/^https?:\/\//, '') : '/o/'

  async function copy() {
    if (!data?.url) return
    try {
      await navigator.clipboard.writeText(data.url)
      setNotice({ tone: 'success', text: 'Link outlet disalin.' })
    } catch {
      setNotice({ tone: 'danger', text: 'Link belum bisa disalin. Salin manual dari kolom di atas.' })
    }
  }

  async function save() {
    setBusy(true)
    setNotice(undefined)
    try {
      await api.put(`/owner/outlets/${outletId}/public-link`, { slug: cleaned })
      await link.reload()
      setDraft(undefined)
      setConfirming(false)
      setNotice({ tone: 'success', text: 'Link outlet disimpan. Link & QR outlet lama sudah tidak berlaku — unduh & pasang QR baru.' })
    } catch (e) {
      setConfirming(false)
      setNotice({ tone: 'danger', text: errorMessage(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="lg:col-span-2" title={`Link outlet & QR · ${outletName}`}>
      <p className="text-[12px] text-text-muted">
        Pelanggan membuka chat pemesanan dari link ini (pesan online, rekomendasi, reservasi). Pasang di Instagram,
        Google Maps, poster, dan kasir.
      </p>
      {!data ? (link.error ? <div className="mt-2"><Alert>{errorMessage(link.error)}</Alert></div> : <Loading />) : (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
            <label htmlFor="outlet-slug" className="text-[13px] font-semibold">Link outlet</label>
            <div className="flex h-9 min-w-0 flex-1 items-center rounded-md border border-border bg-surface px-2.5 text-[13px] focus-within:border-primary">
              <span className="shrink-0 text-text-muted">{prefix}</span>
              <input id="outlet-slug" aria-label="Slug outlet" className="min-w-0 flex-1 bg-transparent outline-none" value={slug}
                maxLength={40} onChange={(e) => { setDraft(e.target.value); setConfirming(false); setNotice(undefined) }} />
            </div>
            <span className="flex items-center gap-2 text-[12px]">
              <LinkButton className="text-[12px]" aria-label="Salin link outlet" disabled={!data.url || changed} onClick={() => void copy()}>Salin</LinkButton>
              <span aria-hidden="true" className="text-text-muted">·</span>
              <LinkButton className="text-[12px]" aria-label="Simpan link outlet" disabled={!changed || busy || cleaned === ''}
                onClick={() => { setNotice(undefined); setConfirming(true) }}>Simpan</LinkButton>
            </span>
          </div>
          {confirming && (
            <div role="alertdialog" aria-label="Konfirmasi ganti link" className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-danger bg-danger-soft px-3 py-2 text-[12px] text-danger">
              <span>Ganti link ke <b>{cleaned}</b>? Link & QR outlet lama langsung tidak berlaku.</span>
              <Button variant="danger" className="h-7 px-2 text-[12px]" disabled={busy} onClick={() => void save()}>Ya, ganti</Button>
              <LinkButton className="text-[12px]" onClick={() => setConfirming(false)}>Batal</LinkButton>
            </div>
          )}
          <p role="note" className="mt-2 rounded-md bg-warning-soft px-3 py-2 text-[12px] text-warning">
            Slug unik di seluruh Thinker (huruf kecil, angka, tanda hubung). Mengganti slug membuat link & QR outlet lama
            langsung tidak berlaku — konfirmasi dulu.
          </p>
          {notice && <div className="mt-2"><Alert tone={notice.tone}>{notice.text}</Alert></div>}
        </>
      )}
      {error && <div className="mt-2"><Alert>{error}</Alert></div>}
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <div className="rounded-md border border-border p-3">
          <p className="text-[13px] font-semibold">QR outlet (link di atas)</p>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-[12px]">
            <LinkButton className="text-[12px]" disabled={!data || changed} onClick={() => onDownload(
              `/owner/outlets/${outletId}/outlet-qr.png`, 'image/png', `qr-${data?.slug ?? 'outlet'}.png`)}>↓ Unduh PNG</LinkButton>
            <span aria-hidden="true" className="text-text-muted">·</span>
            <LinkButton className="text-[12px]" disabled={!data || changed} onClick={() => onDownload(
              `/owner/outlets/${outletId}/outlet-poster.pdf`, 'application/pdf', `poster-${data?.slug ?? 'outlet'}.pdf`)}>↓ Poster PDF</LinkButton>
          </p>
        </div>
        <div className="rounded-md border border-border p-3">
          <p className="text-[13px] font-semibold">QR meja{tableCount !== null ? ` (${tableCount} meja)` : ''} — dine-in</p>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-text-muted">
            <span>↓ PNG · ↻ Ganti per meja di Daftar meja</span>
            {(tableCount ?? 0) > 0 && (
              <>
                <span aria-hidden="true">|</span>
                <LinkButton className="text-[12px]" onClick={() => onDownload(
                  `/owner/outlets/${outletId}/tables/qr.pdf`, 'application/pdf', 'qr-meja.pdf')}>↓ Semua QR meja (PDF)</LinkButton>
              </>
            )}
          </p>
        </div>
      </div>
      <p className="mt-3 text-[11px] leading-[18px] text-text-muted">
        QR selalu ke web chat. “Ganti” membuat token meja baru; QR lama langsung tidak berlaku. Hanya owner yang bisa
        mengubah link dan QR.
      </p>
    </Card>
  )
}

function TableForm({ table, onDone, onCancel }: { table?: OwnerTable; onDone: () => Promise<void>; onCancel: () => void }) {
  const { api, outlet } = useSession()
  const [name, setName] = useState(table?.name ?? '')
  const [capacity, setCapacity] = useState(String(table?.capacity ?? 2))
  const [area, setArea] = useState(table?.area ?? '')
  const [bookable, setBookable] = useState(table?.is_bookable ?? true)
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  const cap = Number(capacity)
  const valid = name.trim() !== '' && Number.isInteger(cap) && cap >= 1 && cap <= 100

  async function run(fn: () => Promise<unknown>) {
    setBusy(true)
    setError(undefined)
    try {
      await fn()
      await onDone()
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  const body = { name: name.trim(), capacity: cap, area: area.trim() || null, is_bookable: bookable }
  return (
    <div className="mb-3 rounded-md border border-border bg-page p-3">
      <h3 className="mb-2 text-[13px] font-semibold">{table ? `Ubah meja ${table.name}` : 'Meja baru'}</h3>
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="text-[12px]">Nama / nomor meja
          <TextInput aria-label="Nama meja" value={name} maxLength={30} placeholder="M05" onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="text-[12px]">Kapasitas (orang)
          <TextInput aria-label="Kapasitas" inputMode="numeric" value={capacity}
            onChange={(e) => setCapacity(e.target.value.replace(/\D/g, ''))} />
        </label>
        <label className="text-[12px]">Area
          <TextInput aria-label="Area" value={area} maxLength={60} placeholder="Indoor" onChange={(e) => setArea(e.target.value)} />
        </label>
      </div>
      <label className="mt-2 flex items-center gap-2 text-[12px]">
        <input type="checkbox" checked={bookable} onChange={(e) => setBookable(e.target.checked)} />
        Bisa di-book lewat reservasi
      </label>
      {error && <div className="mt-2"><Alert>{error}</Alert></div>}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button variant="action" disabled={!valid || busy} onClick={() => run(() => table
          ? api.patch(`/owner/tables/${table.id}`, body)
          : api.post(`/owner/outlets/${outlet!.id}/tables`, body))}>
          Simpan
        </Button>
        <LinkButton onClick={onCancel}>Batal</LinkButton>
        {table && (
          <Button variant="danger" className="ml-auto" disabled={busy}
            onClick={() => run(() => api.del(`/owner/tables/${table.id}`))}>Hapus meja</Button>
        )}
      </div>
    </div>
  )
}

/** Minutes shown as hours ("2", "0,75"); display only, see `minutesFrom`. */
function hours(minutes: number): string {
  return String(Math.round((minutes / 60) * 100) / 100).replace('.', ',')
}

function RulesForm({ initial, zone, onSaved }: { initial: ReservationSettings; zone: string; onSaved: () => void }) {
  const { api, outlet } = useSession()
  const [enabled, setEnabled] = useState(initial.is_enabled)
  const [from, setFrom] = useState(hhmm(initial.bookable_from))
  const [until, setUntil] = useState(hhmm(initial.bookable_until))
  const [duration, setDuration] = useState(String(initial.default_duration_minutes))
  const [windowDays, setWindowDays] = useState(String(initial.booking_window_days))
  const [maxParty, setMaxParty] = useState(String(initial.max_party_size))
  const [reminder, setReminder] = useState(hours(initial.reminder_offset_minutes))
  const [cutoff, setCutoff] = useState(hours(initial.cancellation_cutoff_minutes))
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string }>()
  const [busy, setBusy] = useState(false)
  const num = (v: string) => Number(v.replace(',', '.'))
  // An untouched field sends the stored minutes, so a value that is not a whole fraction of an
  // hour (e.g. 45 or 20 minutes) is not changed by rounding when another field is saved.
  const minutesFrom = (value: string, stored: number) =>
    value === hours(stored) ? stored : Math.round(num(value) * 60)
  const valid = [duration, windowDays, maxParty].every((v) => v !== '' && Number.isInteger(Number(v))) &&
    [reminder, cutoff].every((v) => v !== '' && !Number.isNaN(num(v))) && from !== '' && until !== ''

  return (
    <div>
      <FieldRow label="Reservasi WhatsApp" htmlFor="res-enabled">
        <label className="flex items-center gap-2 text-[12px]">
          <input id="res-enabled" type="checkbox" role="switch" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          {enabled ? 'Aktif' : 'Nonaktif'}
        </label>
      </FieldRow>
      <FieldRow label="Jam bisa booking">
        <div className="flex items-center gap-2">
          <TextInput aria-label="Jam booking mulai" type="time" className="w-28" value={from} onChange={(e) => setFrom(e.target.value)} />
          –
          <TextInput aria-label="Jam booking sampai" type="time" className="w-28" value={until} onChange={(e) => setUntil(e.target.value)} />
        </div>
      </FieldRow>
      <NumberRow label="Durasi default" unit="menit" value={duration} onChange={setDuration} />
      <NumberRow label="Booking window" unit="hari ke depan" value={windowDays} onChange={setWindowDays} />
      <NumberRow label="Maks. jumlah orang" unit="orang" value={maxParty} onChange={setMaxParty} />
      <NumberRow label="Reminder dikirim" unit="jam sebelum" value={reminder} onChange={setReminder} decimal />
      <NumberRow label="Batas batal / reschedule" unit="jam sebelum" value={cutoff} onChange={setCutoff} decimal />
      <FieldRow label="Hold no-show">
        <span className="text-[12px]">{initial.hold_minutes} menit (tetap)</span>
      </FieldRow>
      <p className="mt-2 text-[11px] text-text-muted">Semua jam dalam zona waktu outlet ({zone}).</p>
      {notice && <div className="mt-2"><Alert tone={notice.tone}>{notice.text}</Alert></div>}
      <Button variant="action" className="mt-3" disabled={!valid || busy} onClick={async () => {
        setBusy(true)
        setNotice(undefined)
        try {
          await api.put(`/owner/outlets/${outlet!.id}/reservation-settings`, {
            is_enabled: enabled,
            bookable_from: from,
            bookable_until: until,
            default_duration_minutes: Number(duration),
            booking_window_days: Number(windowDays),
            max_party_size: Number(maxParty),
            reminder_offset_minutes: minutesFrom(reminder, initial.reminder_offset_minutes),
            cancellation_cutoff_minutes: minutesFrom(cutoff, initial.cancellation_cutoff_minutes),
          })
          setNotice({ tone: 'success', text: 'Aturan reservasi disimpan.' })
          onSaved()
        } catch (e) {
          setNotice({ tone: 'danger', text: errorMessage(e) })
        } finally {
          setBusy(false)
        }
      }}>Simpan</Button>
    </div>
  )
}

function NumberRow({ label, unit, value, onChange, decimal = false }: {
  label: string; unit: string; value: string; onChange: (v: string) => void; decimal?: boolean
}) {
  return (
    <FieldRow label={label}>
      <div className="flex items-center gap-2 text-[12px]">
        <TextInput aria-label={label} inputMode={decimal ? 'decimal' : 'numeric'} className="w-20" value={value}
          onChange={(e) => onChange(e.target.value.replace(decimal ? /[^\d.,]/g : /\D/g, ''))} />
        {unit}
      </div>
    </FieldRow>
  )
}
