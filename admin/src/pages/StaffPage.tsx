// Wireframe O4 — Staf & Akses (T-012, T-013, T-066).
// Endpoints: GET /owner/staff, POST /owner/staff/invitations, PUT /owner/staff/{id}/outlets,
// POST /owner/staff/{id}/invitations/resend, POST /owner/staff/{id}/deactivate.
// The access matrix is static (FR1.5); the API enforces it.
import { useState, type FormEvent } from 'react'
import { useSession } from '../app/session'
import { errorMessage } from '../lib/api'
import type { StaffMember } from '../lib/types'
import { useLoad } from '../lib/useLoad'
import { PageHeader } from '../layout/PageHeader'
import { Alert, Button, Card, Field, LinkButton, Loading, StatusDot, TextInput } from '../ui/kit'

const STATUS: Record<StaffMember['status'], { label: string; tone: 'success' | 'muted' | 'warning' }> = {
  active: { label: '● Aktif', tone: 'success' },
  inactive: { label: '○ Nonaktif', tone: 'muted' },
  invited: { label: '✉ Diundang', tone: 'warning' },
}

const MATRIX: [string, string, string][] = [
  ['Order board, counter, open bill, pembayaran', '✓', '✓ (outlet ditugaskan)'],
  ['Reservasi & meja, stok, shift kasir', '✓', '✓ (outlet ditugaskan)'],
  ['Clock in / out (absensi sendiri)', '—', '✓ (hanya catatan sendiri)'],
  ['Menu, resep, harga, rekomendasi', '✓', '✕'],
  ['Pengeluaran, laporan, cash count, kehadiran staf', '✓', '✕'],
  ['Outlet, staf, WhatsApp setup, audit log', '✓', '✕'],
]

/** Wireframe shows the short outlet name ("Dago, Riau" for "Bandung – Dago", "Bandung – Riau"). */
function shortOutlet(name: string): string {
  const parts = name.split(/\s[–-]\s/)
  return parts[parts.length - 1]
}

export default function StaffPage() {
  const { api, me } = useSession()
  const staff = useLoad(() => api.get<StaffMember[]>('/owner/staff'), 'staff')
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string }>()
  const [menuFor, setMenuFor] = useState<string>()
  const [editOutlets, setEditOutlets] = useState<StaffMember>()

  async function act(action: () => Promise<unknown>, success: string) {
    setMenuFor(undefined)
    setNotice(undefined)
    try {
      await action()
      setNotice({ tone: 'success', text: success })
      await staff.reload()
    } catch (e) {
      setNotice({ tone: 'danger', text: errorMessage(e) })
    }
  }

  return (
    <>
      <PageHeader title="Staf & Akses" />
      <div className="grid gap-4 p-4 md:p-6 lg:grid-cols-[1fr_340px]">
        <div className="min-w-0 space-y-4">
          {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}
          <Card>
            {staff.loading && !staff.data ? (
              <Loading />
            ) : staff.error ? (
              <Alert>{errorMessage(staff.error)}</Alert>
            ) : (
              <table className="w-full table-fixed text-left text-[12px]">
                <thead className="text-[11px] tracking-wide text-text-muted uppercase">
                  <tr>
                    <th className="pb-2 font-medium">Nama / Email</th>
                    <th className="hidden pb-2 font-medium sm:table-cell">Outlet</th>
                    <th className="w-32 pb-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(staff.data ?? []).length === 0 && (
                    <tr><td colSpan={3} className="py-4 text-text-muted">Belum ada staf. Undang staf di panel kanan.</td></tr>
                  )}
                  {(staff.data ?? []).map((s) => (
                    <tr key={s.id} className="border-t border-border align-top">
                      <td className="truncate py-2.5">
                        {s.display_name} · <span className="text-text-muted">{s.email}</span>
                        <div className="text-text-muted sm:hidden">{s.outlets.map((o) => shortOutlet(o.name)).join(', ')}</div>
                      </td>
                      <td className="hidden py-2.5 sm:table-cell">{s.outlets.map((o) => shortOutlet(o.name)).join(', ')}</td>
                      <td className="relative py-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <StatusDot tone={STATUS[s.status].tone}>{STATUS[s.status].label}</StatusDot>
                          <button type="button" aria-label={`Menu ${s.display_name}`} aria-expanded={menuFor === s.id}
                            className="px-1 text-text-muted hover:text-text"
                            onClick={() => setMenuFor(menuFor === s.id ? undefined : s.id)}>⋯</button>
                        </div>
                        {menuFor === s.id && (
                          <ul role="menu" className="absolute right-0 z-10 mt-1 w-48 rounded-md border border-border bg-surface py-1 shadow-lg">
                            <MenuItem onClick={() => { setMenuFor(undefined); setEditOutlets(s) }}>Edit outlet</MenuItem>
                            {s.status === 'invited' && (
                              <MenuItem onClick={() => act(() => api.post(`/owner/staff/${s.id}/invitations/resend`),
                                `Undangan dikirim ulang ke ${s.email}.`)}>Kirim ulang undangan</MenuItem>
                            )}
                            {s.status !== 'inactive' && (
                              <MenuItem danger onClick={() => act(() => api.post(`/owner/staff/${s.id}/deactivate`),
                                `${s.display_name} dinonaktifkan; sesi aktif langsung dicabut.`)}>Nonaktifkan</MenuItem>
                            )}
                          </ul>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          {editOutlets && (
            <EditOutletsCard member={editOutlets} outlets={me.outlets}
              onCancel={() => setEditOutlets(undefined)}
              onSave={(ids) => act(async () => {
                await api.put(`/owner/staff/${editOutlets.id}/outlets`, { outlet_ids: ids })
                setEditOutlets(undefined)
              }, `Outlet ${editOutlets.display_name} diperbarui.`)} />
          )}

          <Card title="Matriks akses (MVP)">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[420px] text-left text-[12px]">
                <thead>
                  <tr className="text-text-muted">
                    <th className="pb-2 font-medium">Fitur</th>
                    <th className="w-16 pb-2 font-medium text-success">Owner</th>
                    <th className="w-44 pb-2 font-medium">Staf</th>
                  </tr>
                </thead>
                <tbody>
                  {MATRIX.map(([feature, owner, staffAccess]) => (
                    <tr key={feature} className="border-t border-border">
                      <td className="py-2">{feature}</td>
                      <td className="py-2 text-success">{owner}</td>
                      <td className={`py-2 ${staffAccess === '✕' ? 'text-danger' : 'text-success'}`}>{staffAccess}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        <InviteCard outlets={me.outlets} onInvited={async (email) => {
          setNotice({ tone: 'success', text: `Undangan dikirim ke ${email}.` })
          await staff.reload()
        }} />
      </div>
    </>
  )
}

function MenuItem({ children, onClick, danger }: { children: string; onClick: () => void; danger?: boolean }) {
  return (
    <li>
      <button type="button" role="menuitem" onClick={onClick}
        className={`block w-full px-3 py-1.5 text-left text-[12px] hover:bg-page ${danger ? 'text-danger' : ''}`}>
        {children}
      </button>
    </li>
  )
}

function OutletChecks({ outlets, selected, onChange }: {
  outlets: { id: string; name: string }[]
  selected: string[]
  onChange: (ids: string[]) => void
}) {
  return (
    <div className="space-y-1">
      {outlets.map((o) => (
        <label key={o.id} className="flex items-center gap-2 text-[13px]">
          <input type="checkbox" checked={selected.includes(o.id)}
            onChange={(e) => onChange(e.target.checked ? [...selected, o.id] : selected.filter((id) => id !== o.id))} />
          {o.name}
        </label>
      ))}
    </div>
  )
}

function InviteCard({ outlets, onInvited }: {
  outlets: { id: string; name: string }[]
  onInvited: (email: string) => Promise<void>
}) {
  const { api, outlet } = useSession()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [selected, setSelected] = useState<string[]>(outlet ? [outlet.id] : [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(undefined)
    try {
      const invited = await api.post<StaffMember>('/owner/staff/invitations', {
        display_name: name.trim(),
        email: email.trim(),
        outlet_ids: selected,
      })
      setName('')
      setEmail('')
      await onInvited(invited.email)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Undang staf" className="h-fit">
      <form onSubmit={submit} noValidate>
        <Field label="Nama" htmlFor="invite-name">
          <TextInput id="invite-name" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Email (ditentukan owner)" htmlFor="invite-email"
          hint="Staf menerima email undangan dan mengatur password sendiri.">
          <TextInput id="invite-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <fieldset className="mb-4">
          <legend className="mb-1 text-[13px] font-semibold">Tugaskan ke outlet</legend>
          <OutletChecks outlets={outlets} selected={selected} onChange={setSelected} />
        </fieldset>
        {error && <div className="mb-3"><Alert>{error}</Alert></div>}
        <Button type="submit" variant="action" className="w-full"
          disabled={busy || !name.trim() || !email.trim() || selected.length === 0}>
          {busy ? 'Mengirim…' : 'Kirim undangan'}
        </Button>
      </form>
      <p className="mt-3 text-[11px] text-text-muted">
        Menu ⋯ per staf: Edit outlet · Kirim ulang undangan · Nonaktifkan.
        <br />
        Nonaktifkan → sesi aktif langsung dicabut. Tidak ada pendaftaran publik.
      </p>
    </Card>
  )
}

function EditOutletsCard({ member, outlets, onSave, onCancel }: {
  member: StaffMember
  outlets: { id: string; name: string }[]
  onSave: (ids: string[]) => void
  onCancel: () => void
}) {
  const [selected, setSelected] = useState(member.outlets.map((o) => o.id))
  return (
    <Card title={`Edit outlet · ${member.display_name}`}>
      <OutletChecks outlets={outlets} selected={selected} onChange={setSelected} />
      <div className="mt-3 flex items-center gap-3">
        <Button onClick={() => onSave(selected)} disabled={selected.length === 0}>Simpan</Button>
        <LinkButton onClick={onCancel}>Batal</LinkButton>
      </div>
    </Card>
  )
}
