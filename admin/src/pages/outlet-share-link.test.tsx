// Page 07 note "Bagikan link outlet": the outlet link on O2 (strip) and O3 (row "Link pesan").
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeApi, fakeSession } from '../test/fakes'
import { WithSession } from '../test/session'
import { OutletLinkStrip, OutletLinkValue } from './shared/OutletShareLink'

const DAGO = { slug: 'kopisenja-dago', url: 'https://pesan.thinker.id/o/kopisenja-dago' }
const RIAU = { slug: 'kopisenja-riau', url: 'https://pesan.thinker.id/o/kopisenja-riau' }

function renderStrip(session: ReturnType<typeof fakeSession>, headerOutletId = '') {
  render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <WithSession session={session}>
        <Routes>
          <Route path="/dashboard" element={<OutletLinkStrip headerOutletId={headerOutletId} />} />
          <Route path="/settings/tables" element={<p>Halaman Meja & Reservasi</p>} />
        </Routes>
      </WithSession>
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  Reflect.deleteProperty(navigator, 'share')
})

describe('O2 · Link pesan online', () => {
  it('shows the first outlet with "Semua outlet", switches outlet, copies the link', async () => {
    const writeText = vi.fn(async () => {})
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const api = fakeApi({
      'GET /owner/outlets/o-dago/public-link': DAGO,
      'GET /owner/outlets/o-riau/public-link': RIAU,
    })
    renderStrip(fakeSession('owner', { api }))
    const strip = screen.getByRole('region', { name: 'Link pesan online' })
    expect(await within(strip).findByText('pesan.thinker.id/o/kopisenja-dago')).toBeInTheDocument()
    expect(within(strip).getByText('Tempel di bio Instagram, status WhatsApp, atau Google Maps.')).toBeInTheDocument()
    // No Web Share API in this browser → no Bagikan.
    expect(within(strip).queryByRole('button', { name: 'Bagikan link pesan' })).not.toBeInTheDocument()

    await userEvent.selectOptions(within(strip).getByLabelText('Outlet link pesan'), 'o-riau')
    expect(await within(strip).findByText('pesan.thinker.id/o/kopisenja-riau')).toBeInTheDocument()
    await userEvent.click(within(strip).getByRole('button', { name: 'Salin link pesan' }))
    expect(writeText).toHaveBeenCalledWith(RIAU.url)
    expect(await within(strip).findByText('Link outlet disalin.')).toBeInTheDocument()
  })

  it('follows the header outlet and opens Meja & Reservasi for it', async () => {
    const session = fakeSession('owner', { api: fakeApi({ 'GET /owner/outlets/o-riau/public-link': RIAU }) })
    renderStrip(session, 'o-riau')
    const strip = screen.getByRole('region', { name: 'Link pesan online' })
    expect(await within(strip).findByText('pesan.thinker.id/o/kopisenja-riau')).toBeInTheDocument()
    expect(within(strip).queryByLabelText('Outlet link pesan')).not.toBeInTheDocument()
    await userEvent.click(within(strip).getByRole('button', { name: 'Atur link & QR →' }))
    expect(session.setOutletId).toHaveBeenCalledWith('o-riau')
    expect(await screen.findByText('Halaman Meja & Reservasi')).toBeInTheDocument()
  })

  it('shares through the phone menu when the browser can share', async () => {
    const share = vi.fn(async () => {})
    Object.defineProperty(navigator, 'share', { value: share, configurable: true })
    renderStrip(fakeSession('owner', { api: fakeApi({ 'GET /owner/outlets/o-dago/public-link': DAGO }) }), 'o-dago')
    await screen.findByText('pesan.thinker.id/o/kopisenja-dago')
    await userEvent.click(screen.getByRole('button', { name: 'Bagikan link pesan' }))
    expect(share).toHaveBeenCalledWith({ title: 'Pesan di Bandung – Dago', url: DAGO.url })
  })

  it('disables Salin while the link is not active yet', async () => {
    renderStrip(fakeSession('owner', {
      api: fakeApi({ 'GET /owner/outlets/o-dago/public-link': { slug: 'kopisenja-dago', url: null } }),
    }), 'o-dago')
    expect(await screen.findByText('Link pesan belum aktif.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Salin link pesan' })).toBeDisabled()
  })
})

describe('O3 · Umum → Link pesan', () => {
  it('shows the outlet link with Salin', async () => {
    const api = fakeApi({ 'GET /owner/outlets/o-dago/public-link': DAGO })
    render(
      <MemoryRouter>
        <WithSession session={fakeSession('owner', { api })}>
          <OutletLinkValue outletId="o-dago" outletName="Bandung – Dago" />
        </WithSession>
      </MemoryRouter>,
    )
    expect(await screen.findByText('pesan.thinker.id/o/kopisenja-dago')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Salin link pesan' })).toBeEnabled())
  })
})
