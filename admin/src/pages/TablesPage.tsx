// Wireframe O8 — Meja & Aturan Reservasi (T-057) with the table QR (T-136, issue #44).
// Endpoints: GET/POST /owner/outlets/{id}/tables, PATCH/DELETE /owner/tables/{id},
// GET/PUT /owner/outlets/{id}/reservation-settings, GET /owner/tables/{id}/qr.png,
// GET /owner/outlets/{id}/tables/qr.pdf, POST /owner/tables/{id}/qr-token,
// GET/PUT /owner/outlets/{id}/table-qr-settings. All times in the outlet's time zone.
// Behaviour notes (canvas): the QR opens the Thinker page /t/<token>; "↻ Ganti" makes a new token
// and the old printed QR stops working; without WhatsApp the QR always goes to the web page.
import { useState } from 'react'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { hhmm } from '../lib/format'
import type { OwnerTable, ReservationSettings, TableQrSettings, TableQrTarget } from '../lib/types'
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
          {qrError && <div className="mb-2"><Alert>{qrError}</Alert></div>}
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
            QR membuka halaman pesan Thinker untuk meja itu (thinker…/t/‹token›). Pelanggan memilih “Pesan di sini”
            (web, channel web_table, bayar dulu dengan QRIS statis outlet, dikonfirmasi staf) atau “Pesan via WhatsApp”
            (chat outlet dengan kode meja, channel whatsapp_table, mengikuti mode bayar outlet). “↻ Ganti” membuat
            token baru: QR lama berhenti berfungsi dan harus dicetak ulang.
          </p>
          <QrTargetSection key={outletId} outletId={outletId} />
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

const QR_TARGETS: { value: TableQrTarget; label: string; whatsapp: boolean }[] = [
  { value: 'web_whatsapp', label: 'Web + WhatsApp', whatsapp: true },
  { value: 'web', label: 'Web saja', whatsapp: false },
  { value: 'whatsapp', label: 'WhatsApp saja', whatsapp: true },
]

function QrTargetSection({ outletId }: { outletId: string }) {
  const { api } = useSession()
  const settings = useLoad(() => api.get<TableQrSettings>(`/owner/outlets/${outletId}/table-qr-settings`), outletId)
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string }>()
  const [busy, setBusy] = useState(false)
  const data = settings.data

  async function choose(target: TableQrTarget) {
    setBusy(true)
    setNotice(undefined)
    try {
      await api.put(`/owner/outlets/${outletId}/table-qr-settings`, { target })
      await settings.reload()
      setNotice({ tone: 'success', text: 'Tujuan QR disimpan. QR yang sudah dicetak tetap berlaku.' })
    } catch (e) {
      setNotice({ tone: 'danger', text: errorMessage(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <fieldset className="mt-4 border-t border-border pt-4">
      <legend className="text-[13px] font-semibold text-text">Tujuan QR meja</legend>
      {!data ? (settings.error ? <Alert>{errorMessage(settings.error)}</Alert> : <Loading />) : (
        <>
          <div className="mt-2 flex flex-wrap gap-x-6 gap-y-2 text-[12px]">
            {QR_TARGETS.map((t) => (
              <label key={t.value} className={`flex items-center gap-2 ${t.whatsapp && !data.whatsapp_connected ? 'text-text-muted' : ''}`}>
                <input type="radio" name="qr-target" value={t.value} checked={data.target === t.value}
                  disabled={busy || (t.whatsapp && !data.whatsapp_connected)} onChange={() => void choose(t.value)} />
                {t.label}
              </label>
            ))}
          </div>
          {notice && <div className="mt-2"><Alert tone={notice.tone}>{notice.text}</Alert></div>}
          <p className="mt-2 text-[11px] leading-[18px] text-text-muted">
            Web + WhatsApp: pelanggan memilih di layar pertama (Q1). Web saja: langsung ke menu web (Q2). WhatsApp saja:
            langsung membuka chat WhatsApp outlet. Selama WhatsApp outlet belum terhubung (O12), QR selalu ke web dan
            pilihan WhatsApp nonaktif. Pesan di web perlu QRIS statis outlet (O3); tanpa QRIS, QR hanya menampilkan menu.
            QR yang sudah dicetak tetap berlaku saat pilihan ini diubah.
          </p>
        </>
      )}
    </fieldset>
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
