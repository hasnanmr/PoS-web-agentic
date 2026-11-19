// Attendance tablet, wireframes K0–K4 (page 05 · Tablet Absensi Outlet; T-117, T-121, T-122).
// A separate full-screen app on route /tablet: no sidebar and no Supabase sign-in. The tablet is
// paired once with a 6-digit code from O3 and then only lists the outlet's staff and records
// clock in / clock out with a required selfie. Endpoints: POST /device/pair, GET /device/staff,
// POST /device/selfies, POST /device/attendance (docs/architecture/screen-endpoint-map.md).
// Behaviour notes from the canvas: no PIN; a working staff member's tap becomes clock out; the
// camera is required (no skip); offline submissions are not queued; a revoked tablet goes to K0.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, createApi, type Api } from '../lib/api'
import { useLoad } from '../lib/useLoad'
import { usePolling } from '../lib/usePolling'
import { PRODUCT_NAME } from '../ui/Brand'
import { Camera } from './Camera'
import {
  clearPairing, durationLabel, loadPairing, savePairing, tabletErrorMessage, timeLabel, dateLabel,
  type Pairing,
} from './util'

export interface TabletStaff {
  user_id: string
  display_name: string
  status: 'not_clocked_in' | 'working'
  since: string | null
  first_time: boolean
}

interface StaffList {
  outlet: { name: string; timezone: string }
  device_name: string
  server_time: string
  staff: TabletStaff[]
}

interface AttendanceResult {
  action: 'clock_in' | 'clock_out'
  display_name: string
  at: string
  duration_minutes: number | null
  timezone: string
}

type Step =
  | { name: 'list' }
  | { name: 'camera'; person: TabletStaff }
  | { name: 'confirm'; person: TabletStaff; photo: Blob }
  | { name: 'done'; result: AttendanceResult }

const RETURN_AFTER_MS = 5000
const REFRESH_MS = 30000

export function TabletApp({ apiBaseUrl }: { apiBaseUrl: string }) {
  const [pairing, setPairing] = useState<Pairing | null>(() => loadPairing())
  const [api] = useState(() => createApi(apiBaseUrl, async () => loadPairing()?.token ?? null))
  return <Tablet api={api} pairing={pairing} onPairing={(p) => {
    if (p) savePairing(p)
    else clearPairing()
    setPairing(p)
  }} />
}

export function Tablet({ api, pairing, onPairing }: {
  api: Api
  pairing: Pairing | null
  onPairing: (p: Pairing | null) => void
}) {
  const [notice, setNotice] = useState<string>()
  if (!pairing) return <PairingScreen api={api} notice={notice} onPaired={(p) => { setNotice(undefined); onPairing(p) }} />
  return <AttendanceScreens api={api} pairing={pairing} onUnpaired={(message) => {
    setNotice(message)
    onPairing(null)
  }} />
}

// K0 · Pairing tablet ke outlet -------------------------------------------------------------

function PairingScreen({ api, notice, onPaired }: {
  api: Api
  notice?: string
  onPaired: (p: Pairing) => void
}) {
  const [digits, setDigits] = useState<string[]>(['', '', '', '', '', ''])
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  const inputs = useRef<(HTMLInputElement | null)[]>([])
  const code = digits.join('')

  function setDigit(i: number, value: string) {
    const clean = value.replace(/\D/g, '')
    if (clean.length > 1) {
      // Pasted code: spread it over the boxes.
      const next = clean.slice(0, 6).padEnd(6, ' ').split('').map((c) => c.trim())
      setDigits(next)
      inputs.current[Math.min(clean.length, 5)]?.focus()
      return
    }
    setDigits((d) => d.map((c, j) => (j === i ? clean : c)))
    if (clean && i < 5) inputs.current[i + 1]?.focus()
  }

  async function submit() {
    setBusy(true)
    setError(undefined)
    try {
      const res = await api.post<{ device_token: string; device_name: string; outlet: Pairing['outlet'] }>(
        '/device/pair', { code })
      onPaired({ token: res.device_token, device_name: res.device_name, outlet: res.outlet })
    } catch (e) {
      setError(tabletErrorMessage(e))
      setBusy(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-page p-4 text-text">
      <form className="w-full max-w-[460px] text-center"
        onSubmit={(e) => { e.preventDefault(); if (code.length === 6) void submit() }}>
        <div className="inline-flex items-center gap-2 text-[14px] font-bold text-primary">
          <img src="/favicon.svg" alt="" width={16} height={16} className="rounded-[22%]" />
          {PRODUCT_NAME} · Tablet Absensi
        </div>
        <h1 className="mt-3 text-[20px] font-bold">Masukkan kode pairing dari owner</h1>
        <p className="mx-auto mt-3 max-w-[360px] text-[11px] text-text-muted">
          Owner membuat kode di Admin → Bisnis &amp; Outlet → Tablet absensi. Kode berlaku sekali dan 10 menit.
        </p>
        {notice && <div role="alert" className="mt-3 rounded-md bg-danger-soft px-3 py-2 text-[12px] text-danger">{notice}</div>}
        <div className="mt-4 flex justify-center gap-2">
          {digits.map((d, i) => (
            <input key={i} ref={(el) => { inputs.current[i] = el }} value={d} inputMode="numeric"
              autoComplete="one-time-code" aria-label={`Digit ${i + 1}`} autoFocus={i === 0}
              onChange={(e) => setDigit(i, e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Backspace' && !d && i > 0) inputs.current[i - 1]?.focus() }}
              className="h-12 w-10 rounded-md border border-border bg-surface text-center text-[20px] font-semibold focus:border-primary focus:outline-none sm:h-14 sm:w-12" />
          ))}
        </div>
        {error && <div role="alert" className="mt-3 rounded-md bg-danger-soft px-3 py-2 text-[12px] text-danger">{error}</div>}
        <button type="submit" disabled={busy || code.length !== 6}
          className="mt-4 h-10 w-[190px] rounded-md bg-primary text-[13px] font-semibold text-white disabled:opacity-60">
          {busy ? 'Menghubungkan…' : 'Hubungkan tablet'}
        </button>
        <p className="mx-auto mt-6 max-w-[360px] text-[10px] text-text-muted">
          Setelah terhubung, tablet tetap login sebagai outlet dan hanya bisa dipakai untuk absensi. Owner bisa
          mencabutnya kapan saja.
        </p>
      </form>
    </main>
  )
}

// K1–K4 ----------------------------------------------------------------------------------------

function AttendanceScreens({ api, pairing, onUnpaired }: {
  api: Api
  pairing: Pairing
  onUnpaired: (message: string) => void
}) {
  const staff = useLoad(() => api.get<StaffList>('/device/staff'), pairing.token)
  usePolling(staff, REFRESH_MS)
  const [step, setStep] = useState<Step>({ name: 'list' })
  const now = useNow()
  const list = staff.data

  const handleError = useCallback((e: unknown): string | undefined => {
    if (e instanceof ApiError && (e.code === 'device_revoked' || e.code === 'device_unpaired')) {
      onUnpaired(tabletErrorMessage(e))
      return undefined
    }
    return tabletErrorMessage(e)
  }, [onUnpaired])

  const unpaired = staff.error instanceof ApiError
    && (staff.error.code === 'device_revoked' || staff.error.code === 'device_unpaired')
  useEffect(() => {
    if (unpaired) handleError(staff.error)
  }, [unpaired, staff.error, handleError])
  const listError = staff.error && !unpaired ? tabletErrorMessage(staff.error) : undefined

  useEffect(() => {
    if (step.name !== 'done') return
    const id = setTimeout(() => setStep({ name: 'list' }), RETURN_AFTER_MS)
    return () => clearTimeout(id)
  }, [step])

  const outlet = list?.outlet ?? pairing.outlet
  const deviceName = list?.device_name ?? pairing.device_name

  if (step.name === 'camera') {
    const action = step.person.status === 'working' ? 'Clock out' : 'Clock in'
    return (
      <Camera title={`${step.person.display_name} · ${action} · ${timeLabel(now, outlet.timezone)}`}
        onCancel={() => setStep({ name: 'list' })}
        onCapture={(photo) => setStep({ name: 'confirm', person: step.person, photo })} />
    )
  }

  if (step.name === 'confirm') {
    return (
      <ConfirmScreen api={api} person={step.person} photo={step.photo} outletName={outlet.name}
        deviceName={deviceName} timezone={outlet.timezone} now={now} onError={handleError}
        onRetake={() => setStep({ name: 'camera', person: step.person })}
        onDone={(result) => { setStep({ name: 'done', result }); void staff.reload() }} />
    )
  }

  if (step.name === 'done') {
    return <DoneScreen result={step.result} onBack={() => setStep({ name: 'list' })} />
  }

  // K1 · Pilih nama staf
  return (
    <main className="min-h-screen bg-page p-4 text-text sm:p-7">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[16px] font-semibold">Absensi · {outlet.name}</h1>
          <p className="text-[14px] font-semibold">Tap nama kamu untuk clock in / clock out</p>
        </div>
        <div className="text-right text-[16px] font-bold text-primary">
          <div>{timeLabel(now, outlet.timezone)}</div>
          <div>{dateLabel(now, outlet.timezone)}</div>
        </div>
      </header>
      {listError && (
        <div role="alert" className="mt-4 rounded-md bg-danger-soft px-3 py-2 text-[12px] text-danger">{listError}</div>
      )}
      {!list && !listError && <p className="mt-6 text-[13px] text-text-muted">Memuat daftar staf…</p>}
      {list && list.staff.length === 0 && (
        <p className="mt-6 text-[13px] text-text-muted">Belum ada staf yang ditugaskan ke outlet ini.</p>
      )}
      <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {(list?.staff ?? []).map((s) => {
          const working = s.status === 'working'
          return (
            <li key={s.user_id}>
              <button type="button" onClick={() => setStep({ name: 'camera', person: s })}
                aria-label={`${s.display_name}, ${working ? 'clock out' : 'clock in'}`}
                className={`flex h-[100px] w-full flex-col items-center justify-center gap-1 rounded-lg border text-[12px] ${
                  working ? 'border-[#22A06B] bg-success-soft text-success' : 'border-border bg-surface text-text'}`}>
                <span aria-hidden="true"
                  className={`flex h-11 w-11 items-center justify-center rounded-full text-[16px] font-semibold ${
                    working ? 'bg-[#C9EBD8] text-success' : 'bg-border text-text-muted'}`}>
                  {s.display_name.slice(0, 1).toUpperCase()}
                </span>
                <span className="font-medium">{s.display_name}</span>
                <span className="text-[11px]">
                  {working && s.since ? `● Bekerja sejak ${timeLabel(new Date(s.since), outlet.timezone, false)}` : '○ Belum masuk'}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
      <p className="mt-6 text-[10px] text-text-muted">
        Tanpa PIN: tap nama lalu selfie. Hanya staf yang ditugaskan ke outlet ini yang tampil. Tablet ini tidak bisa
        membuka order, laporan, atau pengaturan.
      </p>
    </main>
  )
}

// K3 · Cek foto & simpan (+ pemberitahuan pertama kali) ---------------------------------------

function ConfirmScreen({ api, person, photo, outletName, deviceName, timezone, now, onError, onRetake, onDone }: {
  api: Api
  person: TabletStaff
  photo: Blob
  outletName: string
  deviceName: string
  timezone: string
  now: Date
  onError: (e: unknown) => string | undefined
  onRetake: () => void
  onDone: (r: AttendanceResult) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const url = useMemo(() => URL.createObjectURL(photo), [photo])
  const clockOut = person.status === 'working'
  const action = clockOut ? 'Clock out' : 'Clock in'

  useEffect(() => () => URL.revokeObjectURL(url), [url])

  async function save() {
    setBusy(true)
    setError(undefined)
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      setError(tabletErrorMessage(new ApiError(0, 'network_error', 'offline')))
      setBusy(false)
      return
    }
    try {
      const { selfie_id } = await api.post<{ selfie_id: string }>('/device/selfies', photo,
        { 'Content-Type': photo.type || 'image/jpeg' })
      const result = await api.post<AttendanceResult>('/device/attendance', { user_id: person.user_id, selfie_id })
      onDone(result)
    } catch (e) {
      const message = onError(e)
      if (message) setError(message)
      setBusy(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center bg-page p-4 text-text sm:p-8">
      <div className="grid w-full items-center gap-6 sm:grid-cols-[minmax(0,240px)_1fr]">
        <div className="aspect-[3/4] w-full overflow-hidden rounded-lg bg-[#CDD6E6]">
          {url && <img src={url} alt={`Selfie ${person.display_name}`} className="h-full w-full -scale-x-100 object-cover" />}
        </div>
        <div className="max-w-[300px]">
          <h1 className="text-[20px] font-bold">{person.display_name} · {action}</h1>
          <p className="mt-2 text-[11px] text-text-muted">
            {timeLabel(now, timezone)} · {outletName} · tablet {deviceName}
          </p>
          {person.first_time && !clockOut && (
            <div className="mt-3 rounded-md border border-[#E8C66B] bg-warning-soft px-3 py-2 text-[10px] text-text">
              <div className="font-semibold text-warning">Pertama kali absen</div>
              Selfie disimpan sebagai bukti kehadiran selama 30 hari, hanya bisa dilihat owner dan kamu sendiri, lalu
              dihapus otomatis. Tidak ada pengenalan wajah otomatis.
            </div>
          )}
          {error && <div role="alert" className="mt-3 rounded-md bg-danger-soft px-3 py-2 text-[11px] text-danger">{error}</div>}
          <button type="button" disabled={busy} onClick={() => void save()}
            className="mt-3 h-10 w-full rounded-md bg-[#22A06B] text-[12px] font-semibold text-white disabled:opacity-60">
            {busy ? 'Menyimpan…' : `✓ Simpan ${action.toLowerCase()}`}
          </button>
          <button type="button" disabled={busy} onClick={onRetake}
            className="mt-2 h-9 w-full rounded-md border border-border bg-surface text-[11px] font-semibold">
            ↻ Ulangi foto
          </button>
        </div>
      </div>
    </main>
  )
}

// K4 · Berhasil -------------------------------------------------------------------------------

function DoneScreen({ result, onBack }: { result: AttendanceResult; onBack: () => void }) {
  const at = timeLabel(new Date(result.at), result.timezone)
  const clockOut = result.action === 'clock_out'
  return (
    <main className="flex min-h-screen items-center justify-center bg-page p-4 text-text">
      <button type="button" onClick={onBack}
        className="flex w-full max-w-[420px] flex-col items-center rounded-xl border border-[#22A06B] bg-success-soft px-6 py-16 text-center">
        <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="#22A06B" strokeWidth="3"
          strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 12.5l5 5L20 7" /></svg>
        <h1 className="mt-4 text-[16px] font-bold" role="status">
          {result.display_name} {clockOut ? 'clock out' : 'clock in'} {at}
        </h1>
        <p className="mt-2 text-[11px]">
          {clockOut && result.duration_minutes !== null
            ? `Durasi ${durationLabel(result.duration_minutes)}. Terima kasih!`
            : 'Selamat bekerja!'}{' '}
          Layar kembali ke daftar nama dalam 5 detik.
        </p>
      </button>
    </main>
  )
}

function useNow(): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 15000)
    return () => clearInterval(id)
  }, [])
  return now
}
