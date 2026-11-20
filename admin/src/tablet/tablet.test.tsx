import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { fakeApi } from '../test/fakes'
import { Tablet } from './TabletApp'
import { durationLabel, timeLabel, type Pairing } from './util'

const PAIRING: Pairing = {
  token: 'dev_x', device_name: 'Tablet 1', outlet: { name: 'Kopi Senja – Dago', timezone: 'Asia/Jakarta' },
}

const STAFF = {
  outlet: PAIRING.outlet,
  device_name: 'Tablet 1',
  staff: [
    { user_id: 'u-dodi', display_name: 'Dodi', status: 'working', since: '2026-11-17T00:30:00Z', first_time: false },
    { user_id: 'u-rina', display_name: 'Rina', status: 'not_clocked_in', since: null, first_time: true },
  ],
}

function fakeCamera() {
  const track = { stop: vi.fn() }
  const stream = { getTracks: () => [track] } as unknown as MediaStream
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: vi.fn(async () => stream) },
  })
  Object.defineProperty(HTMLVideoElement.prototype, 'videoWidth', { configurable: true, get: () => 640 })
  Object.defineProperty(HTMLVideoElement.prototype, 'videoHeight', { configurable: true, get: () => 480 })
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    { drawImage: vi.fn() } as unknown as CanvasRenderingContext2D)
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(function (cb: BlobCallback) {
    cb(new Blob(['jpeg'], { type: 'image/jpeg' }))
  })
  return track
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => 'blob:selfie')
  URL.revokeObjectURL = vi.fn()
})

afterEach(() => {
  vi.restoreAllMocks()
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: undefined })
})

describe('K0 Pairing tablet ke outlet', () => {
  it('pairs with the 6-digit code', async () => {
    const api = fakeApi({
      'POST /device/pair': { device_token: 'dev_new', device_name: 'Tablet 1', outlet: PAIRING.outlet },
    })
    const onPairing = vi.fn()
    render(<Tablet api={api} pairing={null} onPairing={onPairing} />)
    expect(screen.getByText('Masukkan kode pairing dari owner')).toBeInTheDocument()
    const connect = screen.getByRole('button', { name: 'Hubungkan tablet' })
    expect(connect).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Digit 1'), '482913')
    await userEvent.click(connect)
    await waitFor(() => expect(onPairing).toHaveBeenCalledWith({
      token: 'dev_new', device_name: 'Tablet 1', outlet: PAIRING.outlet }))
    expect(api.calls).toContainEqual(['POST', '/device/pair', { code: '482913' }])
  })

  it('explains a wrong or expired code', async () => {
    const api = fakeApi({ 'POST /device/pair': new ApiError(400, 'pairing_code_invalid', 'bad') })
    render(<Tablet api={api} pairing={null} onPairing={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('Digit 1'), '000000')
    await userEvent.click(screen.getByRole('button', { name: 'Hubungkan tablet' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Kode salah, sudah dipakai, atau kedaluwarsa')
  })
})

describe('K0 digit boxes', () => {
  it('replaces one wrong digit without wiping the code, and spreads a pasted code', async () => {
    render(<Tablet api={fakeApi()} pairing={null} onPairing={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('Digit 1'), '482813')
    await userEvent.click(screen.getByLabelText('Digit 4'))
    await userEvent.keyboard('9')
    expect(['1', '2', '3', '4', '5', '6'].map((n) => (screen.getByLabelText(`Digit ${n}`) as HTMLInputElement).value).join(''))
      .toBe('482913')
    await userEvent.click(screen.getByLabelText('Digit 1'))
    await userEvent.paste('123456')
    expect(['1', '2', '3', '4', '5', '6'].map((n) => (screen.getByLabelText(`Digit ${n}`) as HTMLInputElement).value).join(''))
      .toBe('123456')
  })
})

describe('K1–K4 attendance', () => {
  it('retries a save with the same selfie and never uploads twice', async () => {
    fakeCamera()
    let attempts = 0
    const api = fakeApi({ 'GET /device/staff': STAFF, 'POST /device/selfies': { selfie_id: 's1' } })
    const post = api.post
    api.post = vi.fn(async (path: string, body?: unknown, headers?: Record<string, string>) => {
      if (path === '/device/attendance' && attempts++ === 0) {
        throw new ApiError(0, 'network_error', 'lost')
      }
      if (path === '/device/attendance') {
        return { action: 'clock_out', display_name: 'Dodi', at: '2026-11-17T09:02:00Z', duration_minutes: 512, timezone: 'Asia/Jakarta' }
      }
      return post(path, body, headers)
    }) as typeof api.post
    render(<Tablet api={api} pairing={PAIRING} onPairing={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Dodi, clock out' }))
    const shoot = screen.getByRole('button', { name: '● Ambil foto' })
    await waitFor(() => expect(shoot).toBeEnabled())
    await userEvent.click(shoot)
    await userEvent.click(screen.getByRole('button', { name: '✓ Simpan clock out' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Absen belum tercatat')
    await userEvent.click(screen.getByRole('button', { name: '✓ Simpan clock out' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Dodi clock out 16:02 WIB')
    expect(api.calls.filter(([, p]) => p === '/device/selfies')).toHaveLength(1)
    expect(api.post).toHaveBeenCalledWith('/device/attendance', { user_id: 'u-dodi', selfie_id: 's1', action: 'clock_out' })
  })

  it('goes back to the staff list when another tablet changed the state', async () => {
    fakeCamera()
    const api = fakeApi({
      'GET /device/staff': STAFF,
      'POST /device/selfies': { selfie_id: 's1' },
      'POST /device/attendance': new ApiError(409, 'state_changed', 'changed'),
    })
    render(<Tablet api={api} pairing={PAIRING} onPairing={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Rina, clock in' }))
    const shoot = screen.getByRole('button', { name: '● Ambil foto' })
    await waitFor(() => expect(shoot).toBeEnabled())
    await userEvent.click(shoot)
    await userEvent.click(screen.getByRole('button', { name: '✓ Simpan clock in' }))
    expect(await screen.findByText('Tap nama kamu untuk clock in / clock out')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Status absen sudah berubah')
  })

  it('shows a neutral message when the staff list cannot load', async () => {
    const api = fakeApi({ 'GET /device/staff': new ApiError(0, 'network_error', 'offline') })
    render(<Tablet api={api} pairing={PAIRING} onPairing={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Tidak ada koneksi internet')
    expect(screen.queryByText(/Absen belum tercatat/)).not.toBeInTheDocument()
  })

  it('lists the outlet staff with their state', async () => {
    const api = fakeApi({ 'GET /device/staff': STAFF })
    render(<Tablet api={api} pairing={PAIRING} onPairing={vi.fn()} />)
    expect(await screen.findByText('Absensi · Kopi Senja – Dago')).toBeInTheDocument()
    expect(screen.getByText('Tap nama kamu untuk clock in / clock out')).toBeInTheDocument()
    expect(screen.getByText('● Bekerja sejak 07:30')).toBeInTheDocument()
    expect(screen.getByText('○ Belum masuk')).toBeInTheDocument()
    expect(screen.getByText(/Tanpa PIN: tap nama lalu selfie/)).toBeInTheDocument()
  })

  it('clocks in with a selfie and shows the first-use notice', async () => {
    fakeCamera()
    const api = fakeApi({
      'GET /device/staff': STAFF,
      'POST /device/selfies': { selfie_id: 's1' },
      'POST /device/attendance': {
        action: 'clock_in', display_name: 'Rina', at: '2026-11-17T01:01:00Z', duration_minutes: null,
        timezone: 'Asia/Jakarta',
      },
    })
    render(<Tablet api={api} pairing={PAIRING} onPairing={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Rina, clock in' }))
    expect(screen.getByText(/Rina · Clock in ·/)).toBeInTheDocument()
    const shoot = screen.getByRole('button', { name: '● Ambil foto' })
    await waitFor(() => expect(shoot).toBeEnabled())
    await userEvent.click(shoot)

    expect(screen.getByRole('heading', { name: 'Rina · Clock in' })).toBeInTheDocument()
    expect(screen.getByText('Pertama kali absen')).toBeInTheDocument()
    expect(screen.getByText(/Kopi Senja – Dago · tablet Tablet 1/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '✓ Simpan clock in' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Rina clock in 08:01 WIB')
    expect(screen.getByText(/Selamat bekerja!/)).toBeInTheDocument()
    expect(api.calls).toContainEqual(['POST', '/device/attendance', { user_id: 'u-rina', selfie_id: 's1', action: 'clock_in' }])
    const upload = api.calls.find(([m, p]) => m === 'POST' && p === '/device/selfies')
    expect(upload?.[2]).toBeInstanceOf(Blob)
  })

  it('requires the camera: no way to skip the selfie', async () => {
    const api = fakeApi({ 'GET /device/staff': STAFF })
    render(<Tablet api={api} pairing={PAIRING} onPairing={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Dodi, clock out' }))
    expect(screen.getByText(/Dodi · Clock out ·/)).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Selfie wajib untuk absen. Izinkan kamera lalu coba lagi.')
    expect(screen.queryByRole('button', { name: '● Ambil foto' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '✕ Batal' }))
    expect(screen.getByText('Tap nama kamu untuk clock in / clock out')).toBeInTheDocument()
  })

  it('does not queue a save while offline', async () => {
    fakeCamera()
    const api = fakeApi({
      'GET /device/staff': STAFF,
      'POST /device/selfies': new ApiError(0, 'network_error', 'offline'),
    })
    render(<Tablet api={api} pairing={PAIRING} onPairing={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Dodi, clock out' }))
    const shoot = screen.getByRole('button', { name: '● Ambil foto' })
    await waitFor(() => expect(shoot).toBeEnabled())
    await userEvent.click(shoot)
    expect(screen.queryByText('Pertama kali absen')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '✓ Simpan clock out' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Absen belum tercatat. Periksa internet lalu coba lagi.')
    expect(api.calls.some(([, p]) => p === '/device/attendance')).toBe(false)
  })

  it('goes back to K0 when the owner revoked the tablet', async () => {
    const api = fakeApi({ 'GET /device/staff': new ApiError(401, 'device_revoked', 'revoked') })
    function Stateful() {
      const [pairing, setPairing] = useState<Pairing | null>(PAIRING)
      return <Tablet api={api} pairing={pairing} onPairing={setPairing} />
    }
    render(<Stateful />)
    expect(await screen.findByText('Masukkan kode pairing dari owner')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Tablet ini tidak lagi terhubung ke outlet.')
  })
})

describe('tablet helpers', () => {
  it('formats outlet-local times and durations', () => {
    expect(timeLabel(new Date('2026-11-17T01:01:00Z'), 'Asia/Makassar')).toBe('09:01 WITA')
    expect(durationLabel(512)).toBe('8 j 32 mnt')
    expect(durationLabel(45)).toBe('45 mnt')
  })
})
