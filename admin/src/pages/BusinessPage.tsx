// Wireframe O3 — Bisnis & Outlet (T-011, T-039 drawers, T-066).
// Endpoints: GET/POST /owner/outlets, GET/PATCH /owner/outlets/{id},
// PUT /owner/outlets/{id}/opening-hours, drawers under /owner/outlets/{id}/drawers.
// Not yet here: QRIS statis card (T-014) and tablet pairing (T-121); they come with those tasks.
import { useState, type ReactNode } from 'react'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import { hhmm, summarizeHours, timeAgo, WEEKDAYS } from '../lib/format'
import { TIMEZONE_LABEL, type Drawer, type OpeningHours, type OutletDetail, type Timezone } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Card, FieldRow, LinkButton, Loading, Select, StatusDot, TextInput } from '../ui/kit'

type Draft = Omit<OutletDetail, 'id' | 'order_prefix' | 'whatsapp_status' | 'catalog_synced_at' | 'is_active'>

function toDraft(o: OutletDetail): Draft {
  return {
    name: o.name,
    address: o.address,
    timezone: o.timezone,
    whatsapp_phone: o.whatsapp_phone,
    payment_mode: o.payment_mode,
    pb1_enabled: o.pb1_enabled,
    pb1_rate_bps: o.pb1_rate_bps,
    delivery_fee: o.delivery_fee,
    unpaid_timeout_minutes: o.unpaid_timeout_minutes,
    attendance_grace_minutes: o.attendance_grace_minutes,
    opening_hours: o.opening_hours.map((h) => ({ ...h, opens_at: hhmm(h.opens_at), closes_at: hhmm(h.closes_at) })),
  }
}

function changedFields(before: Draft, after: Draft): Partial<Draft> {
  const out: Record<string, unknown> = {}
  for (const key of Object.keys(after) as (keyof Draft)[]) {
    if (key === 'opening_hours') continue
    if (before[key] !== after[key]) out[key] = after[key]
  }
  return out as Partial<Draft>
}

const WA_STATUS: Record<OutletDetail['whatsapp_status'], { label: string; tone: 'success' | 'warning' | 'muted' | 'danger' }> = {
  connected: { label: '● Terhubung', tone: 'success' },
  pending_verification: { label: '● Menunggu verifikasi', tone: 'warning' },
  not_started: { label: '○ Belum terhubung', tone: 'muted' },
  error: { label: '● Error', tone: 'danger' },
}

export default function BusinessPage() {
  const { api, me, outlet: current, setOutletId, reload: reloadMe } = useSession()
  const outletId = current?.id
  const detail = useLoad(
    () => (outletId ? api.get<OutletDetail>(`/owner/outlets/${outletId}`) : Promise.resolve(undefined)),
    outletId ?? '',
  )
  const [draft, setDraft] = useState<Draft>()
  const [editHours, setEditHours] = useState(false)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string }>()
  const [adding, setAdding] = useState(false)

  // Reset the form whenever fresh outlet data arrives (adjusting state during render).
  const [shown, setShown] = useState<OutletDetail>()
  if (detail.data !== shown) {
    setShown(detail.data)
    setDraft(detail.data ? toDraft(detail.data) : undefined)
    setEditHours(false)
  }

  const base = detail.data ? toDraft(detail.data) : undefined
  const hoursChanged = Boolean(base && draft && JSON.stringify(base.opening_hours) !== JSON.stringify(draft.opening_hours))
  const changes = base && draft ? changedFields(base, draft) : {}
  const dirty = Object.keys(changes).length > 0 || hoursChanged

  async function save() {
    if (!outletId || !draft) return
    setSaving(true)
    setNotice(undefined)
    try {
      if (Object.keys(changes).length > 0) await api.patch(`/owner/outlets/${outletId}`, changes)
      if (hoursChanged) await api.put(`/owner/outlets/${outletId}/opening-hours`, draft.opening_hours)
      await detail.reload()
      if ('name' in changes || 'timezone' in changes || 'payment_mode' in changes) await reloadMe()
      setNotice({ tone: 'success', text: 'Perubahan disimpan.' })
    } catch (e) {
      setNotice({ tone: 'danger', text: errorMessage(e) })
    } finally {
      setSaving(false)
    }
  }

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => draft && setDraft({ ...draft, [key]: value })

  return (
    <>
      <PageHeader
        title="Bisnis & Outlet"
        actions={
          <Button variant="action" onClick={save} disabled={!dirty || saving}>
            {saving ? 'Menyimpan…' : 'Simpan perubahan'}
          </Button>
        }
      />
      <div className="space-y-4 p-4 md:p-6">
        <div className="flex flex-wrap items-center gap-3 text-[13px]">
          <label className="flex items-center gap-2">
            <span className="text-primary">Outlet:</span>
            <Select aria-label="Pilih outlet" className="h-8 w-auto" value={outletId ?? ''}
              onChange={(e) => setOutletId(e.target.value)}>
              {me.outlets.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
          </label>
          <LinkButton onClick={() => setAdding(true)}>+ Tambah outlet</LinkButton>
        </div>
        {adding && (
          <AddOutletForm
            onCancel={() => setAdding(false)}
            onCreated={async (id) => {
              setAdding(false)
              await reloadMe()
              setOutletId(id)
            }}
          />
        )}
        {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}
        {detail.error ? <Alert>{errorMessage(detail.error)}</Alert> : null}
        {!draft || !detail.data ? (
          detail.loading ? <Loading /> : null
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Umum">
              <FieldRow label="Nama outlet" htmlFor="o-name">
                <TextInput id="o-name" value={draft.name} onChange={(e) => set('name', e.target.value)} />
              </FieldRow>
              <FieldRow label="Alamat" htmlFor="o-address">
                <TextInput id="o-address" value={draft.address ?? ''}
                  onChange={(e) => set('address', e.target.value || null)} />
              </FieldRow>
              <FieldRow label="Jam buka">
                <div className="flex flex-wrap items-center gap-2">
                  <span>{summarizeHours(draft.opening_hours)}</span>
                  <LinkButton onClick={() => setEditHours((v) => !v)}>✎ atur per hari</LinkButton>
                </div>
                {editHours && (
                  <HoursEditor value={draft.opening_hours} onChange={(h) => set('opening_hours', h)} />
                )}
              </FieldRow>
              <FieldRow label="Zona waktu" htmlFor="o-tz">
                <Select id="o-tz" value={draft.timezone} onChange={(e) => set('timezone', e.target.value as Timezone)}>
                  {Object.entries(TIMEZONE_LABEL).map(([v, label]) => <option key={v} value={v}>{label}</option>)}
                </Select>
              </FieldRow>
              <FieldRow label="Nomor WhatsApp" htmlFor="o-wa">
                <div className="flex flex-wrap items-center gap-2">
                  <TextInput id="o-wa" className="max-w-[200px]" inputMode="tel" placeholder="+62 8xx xxxx xxxx"
                    value={draft.whatsapp_phone ?? ''}
                    onChange={(e) => set('whatsapp_phone', e.target.value.replace(/[\s-]/g, '') || null)} />
                  <StatusDot tone={WA_STATUS[detail.data.whatsapp_status].tone}>
                    {WA_STATUS[detail.data.whatsapp_status].label}
                  </StatusDot>
                </div>
              </FieldRow>
              <FieldRow label="Katalog WA">
                {detail.data.catalog_synced_at ? (
                  <StatusDot tone="success">● Tersinkron {timeAgo(detail.data.catalog_synced_at)}</StatusDot>
                ) : (
                  <StatusDot tone="muted">○ Belum tersinkron</StatusDot>
                )}
              </FieldRow>
            </Card>

            <DrawerCard outletId={detail.data.id}
              grace={draft.attendance_grace_minutes}
              onGrace={(minutes) => set('attendance_grace_minutes', minutes)} />

            <Card title="Order, pajak & pembayaran" className="lg:col-span-2">
              <Section title="PB1">
                <div className="flex flex-wrap items-center gap-4">
                  <label className="flex items-center gap-2">
                    <input type="checkbox" role="switch" checked={draft.pb1_enabled}
                      onChange={(e) => set('pb1_enabled', e.target.checked)} />
                    Aktif
                  </label>
                  <label className="flex items-center gap-2">
                    Tarif
                    <TextInput aria-label="Tarif PB1 (%)" className="w-16" inputMode="decimal"
                      value={draft.pb1_rate_bps == null ? '' : String(draft.pb1_rate_bps / 100)}
                      onChange={(e) => {
                        const pct = Number(e.target.value.replace(',', '.'))
                        set('pb1_rate_bps', e.target.value === '' || Number.isNaN(pct) ? null : Math.round(pct * 100))
                      }} />
                    %
                  </label>
                </div>
                <Note>Dihitung dari subtotal + add-on, tanpa delivery fee, dibulatkan ke rupiah.</Note>
              </Section>
              <Section title="Mode pembayaran dine-in">
                <div className="flex flex-col gap-1 sm:flex-row sm:gap-6">
                  <label className="flex items-center gap-2">
                    <input type="radio" name="payment-mode" checked={draft.payment_mode === 'pay_first'}
                      onChange={() => set('payment_mode', 'pay_first')} />
                    Pay first (bayar dulu via QRIS/cash)
                  </label>
                  <label className="flex items-center gap-2">
                    <input type="radio" name="payment-mode" checked={draft.payment_mode === 'open_bill'}
                      onChange={() => set('payment_mode', 'open_bill')} />
                    Open bill (bayar di akhir)
                  </label>
                </div>
                <Note>Perubahan berlaku untuk order baru; order lama tetap di flow asalnya.</Note>
              </Section>
              <div className="grid gap-2 sm:grid-cols-2">
                <label className="flex items-center gap-2">
                  <span className="w-48 shrink-0">Biaya delivery flat</span>
                  <span className="text-text-muted">Rp</span>
                  <TextInput aria-label="Biaya delivery flat" className="w-28" inputMode="numeric"
                    value={String(draft.delivery_fee)}
                    onChange={(e) => set('delivery_fee', Number(e.target.value.replace(/\D/g, '')) || 0)} />
                </label>
                <label className="flex items-center gap-2">
                  <span className="w-48 shrink-0">Batas waktu order belum bayar</span>
                  <TextInput aria-label="Batas waktu order belum bayar (menit)" className="w-16" inputMode="numeric"
                    value={String(draft.unpaid_timeout_minutes)}
                    onChange={(e) => set('unpaid_timeout_minutes', Number(e.target.value.replace(/\D/g, '')) || 1)} />
                  <span>menit → auto-cancel</span>
                </label>
              </div>
            </Card>
          </div>
        )}
      </div>
    </>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-4">
      <div className="mb-1 text-[13px] font-semibold">{title}</div>
      {children}
    </div>
  )
}

function Note({ children }: { children: ReactNode }) {
  return <p className="mt-1 text-[11px] text-text-muted">{children}</p>
}

function HoursEditor({ value, onChange }: { value: OpeningHours[]; onChange: (h: OpeningHours[]) => void }) {
  const byDay = new Map(value.map((h) => [h.weekday, h]))
  function update(weekday: number, patch: Partial<OpeningHours> | null) {
    const next = new Map(byDay)
    if (patch === null) next.delete(weekday)
    else next.set(weekday, { weekday, opens_at: '08:00', closes_at: '22:00', ...byDay.get(weekday), ...patch })
    onChange([...next.values()].sort((a, b) => a.weekday - b.weekday))
  }
  return (
    <div className="mt-2 space-y-1 rounded-md border border-border p-2">
      {WEEKDAYS.map((label, i) => {
        const day = i + 1
        const h = byDay.get(day)
        return (
          <div key={day} className="flex flex-wrap items-center gap-2 text-[12px]">
            <label className="flex w-20 items-center gap-1.5">
              <input type="checkbox" checked={Boolean(h)} onChange={(e) => update(day, e.target.checked ? {} : null)} />
              {label}
            </label>
            {h ? (
              <>
                <TextInput type="time" aria-label={`${label} buka`} className="h-8 w-28" value={h.opens_at}
                  onChange={(e) => update(day, { opens_at: e.target.value })} />
                –
                <TextInput type="time" aria-label={`${label} tutup`} className="h-8 w-28" value={h.closes_at}
                  onChange={(e) => update(day, { closes_at: e.target.value })} />
              </>
            ) : (
              <span className="text-text-muted">Tutup</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

function DrawerCard({ outletId, grace, onGrace }: { outletId: string; grace: number; onGrace: (m: number) => void }) {
  const { api } = useSession()
  const drawers = useLoad(() => api.get<Drawer[]>(`/owner/outlets/${outletId}/drawers`), outletId)
  const [error, setError] = useState<string>()
  const [editing, setEditing] = useState<{ id: string | null; name: string }>()

  async function run(action: () => Promise<unknown>) {
    setError(undefined)
    try {
      await action()
      setEditing(undefined)
      await drawers.reload()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <Card title="Cash drawer & absensi">
      <ul className="space-y-1.5">
        {(drawers.data ?? []).map((d, i) => (
          <li key={d.id} className="flex items-center gap-2">
            {editing?.id === d.id ? (
              <DrawerNameForm initial={d.name} onCancel={() => setEditing(undefined)}
                onSave={(name) => run(() => api.patch(`/owner/drawers/${d.id}`, { name }))} />
            ) : (
              <>
                <span className="flex-1">
                  Drawer {i + 1} · {d.name}{i === 0 ? ' (default)' : ''}
                </span>
                <button type="button" aria-label={`Ubah ${d.name}`} className="text-text-muted hover:text-text"
                  onClick={() => setEditing({ id: d.id, name: d.name })}>✎</button>
                <button type="button" aria-label={`Hapus ${d.name}`} className="text-text-muted hover:text-danger"
                  onClick={() => void run(() => api.del(`/owner/drawers/${d.id}`))}>✕</button>
              </>
            )}
          </li>
        ))}
      </ul>
      {editing?.id === null ? (
        <div className="mt-2">
          <DrawerNameForm initial="" onCancel={() => setEditing(undefined)}
            onSave={(name) => run(() => api.post(`/owner/outlets/${outletId}/drawers`, { name }))} />
        </div>
      ) : (
        <LinkButton className="mt-2" onClick={() => setEditing({ id: null, name: '' })}>+ Tambah drawer</LinkButton>
      )}
      {error && <div className="mt-2"><Alert>{error}</Alert></div>}

      <div className="mt-5 border-t border-border pt-3">
        <div className="mb-1 text-[13px] font-semibold">Tablet absensi</div>
        <label className="flex flex-wrap items-center gap-2">
          Tenggang lupa clock out:
          <TextInput aria-label="Tenggang lupa clock out (jam)" className="h-8 w-14" inputMode="numeric"
            value={String(Math.round(grace / 60))}
            onChange={(e) => onGrace(Math.min(12, Number(e.target.value.replace(/\D/g, '')) || 0) * 60)} />
          jam setelah tutup
        </label>
      </div>
    </Card>
  )
}

function DrawerNameForm({ initial, onSave, onCancel }: {
  initial: string
  onSave: (name: string) => void
  onCancel: () => void
}) {
  const [name, setName] = useState(initial)
  return (
    <form className="flex flex-1 items-center gap-2"
      onSubmit={(e) => { e.preventDefault(); if (name.trim()) onSave(name.trim()) }}>
      <TextInput aria-label="Nama drawer" autoFocus maxLength={40} className="h-8" value={name}
        onChange={(e) => setName(e.target.value)} />
      <Button type="submit" className="h-8" disabled={!name.trim()}>Simpan</Button>
      <LinkButton onClick={onCancel}>Batal</LinkButton>
    </form>
  )
}

function AddOutletForm({ onCreated, onCancel }: { onCreated: (id: string) => Promise<void>; onCancel: () => void }) {
  const { api } = useSession()
  const [name, setName] = useState('')
  const [timezone, setTimezone] = useState<Timezone>('Asia/Jakarta')
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  return (
    <Card title="Tambah outlet">
      <form className="flex flex-wrap items-end gap-2"
        onSubmit={async (e) => {
          e.preventDefault()
          setBusy(true)
          setError(undefined)
          try {
            const created = await api.post<OutletDetail>('/owner/outlets', { name: name.trim(), timezone })
            await onCreated(created.id)
          } catch (err) {
            setError(errorMessage(err))
            setBusy(false)
          }
        }}>
        <TextInput aria-label="Nama outlet baru" placeholder="Bandung – Riau" className="max-w-[240px]"
          value={name} onChange={(e) => setName(e.target.value)} />
        <Select aria-label="Zona waktu outlet baru" className="w-auto" value={timezone}
          onChange={(e) => setTimezone(e.target.value as Timezone)}>
          {Object.entries(TIMEZONE_LABEL).map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </Select>
        <Button type="submit" disabled={busy || !name.trim()}>Tambah</Button>
        <LinkButton onClick={onCancel}>Batal</LinkButton>
      </form>
      <p className="mt-2 text-[11px] text-text-muted">Outlet baru otomatis mendapat drawer "Kasir depan".</p>
      {error && <div className="mt-2"><Alert>{error}</Alert></div>}
    </Card>
  )
}
