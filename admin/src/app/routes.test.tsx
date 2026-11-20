import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { fakeSession } from '../test/fakes'
import { WithSession } from '../test/session'
import type { Role } from './nav'
import { AppRoutes } from './routes'

function renderAt(path: string, role: Role) {
  return render(
    <WithSession session={fakeSession(role)}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </WithSession>,
  )
}

describe('app shell', () => {
  it('owner lands on the dashboard with all four groups', () => {
    renderAt('/', 'owner')
    expect(screen.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Ganti outlet' })).toHaveValue('o-dago')
    const nav = screen.getByRole('navigation', { name: 'Navigasi utama' })
    for (const heading of ['OPERASIONAL', 'KATALOG', 'KEUANGAN (OWNER)', 'PENGATURAN']) {
      expect(within(nav).getByRole('group', { name: heading })).toBeInTheDocument()
    }
    expect(within(nav).queryByText(/hanya untuk owner/)).not.toBeInTheDocument()
  })

  it('shows the Thinker brand (logo + name) at the top of the sidebar', () => {
    renderAt('/', 'staff')
    const nav = screen.getByRole('navigation', { name: 'Navigasi utama' })
    const brand = within(nav).getByText('Thinker')
    expect(brand.querySelector('img')).toHaveAttribute('src', '/favicon.svg')
    expect(within(nav).queryByText(/SME POS/)).not.toBeInTheDocument()
  })

  it('staff is redirected away from owner pages and sees the footer note', () => {
    renderAt('/admin/finance/cashflow', 'staff')
    expect(screen.getByRole('heading', { level: 1, name: 'Order Board' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Navigasi utama' })
    expect(within(nav).queryByRole('group', { name: 'KATALOG' })).not.toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: /Absensi Saya/ })).toBeInTheDocument()
    expect(
      within(nav).getByText(/Menu, harga, laporan & pengaturan hanya untuk owner\./),
    ).toBeInTheDocument()
  })

  it('staff pages are served under /admin and staff links stay there', () => {
    for (const path of ['/admin', '/orders', '/finance/cashflow']) {
      const { unmount } = renderAt(path, 'staff')
      expect(screen.getByRole('heading', { level: 1, name: 'Order Board' })).toBeInTheDocument()
      unmount()
    }
    renderAt('/admin/my-attendance', 'staff')
    const nav = screen.getByRole('navigation', { name: 'Navigasi utama' })
    expect(within(nav).getByRole('link', { name: /Absensi Saya/ })).toHaveAttribute('href', '/admin/my-attendance')
    expect(within(nav).getByRole('link', { name: /Counter \/ POS/ })).toHaveAttribute('href', '/admin/counter')
    const bottom = screen.getByRole('navigation', { name: 'Navigasi bawah' })
    expect(within(bottom).getByRole('link', { name: /Stok/ })).toHaveAttribute('href', '/admin/stock')
  })

  it('owner stays at the root and is sent home from the staff area', () => {
    renderAt('/admin/orders', 'owner')
    expect(screen.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Navigasi utama' })
    expect(within(nav).getByRole('link', { name: /Order Board/ })).toHaveAttribute('href', '/orders')
  })

  it('renders the mobile bottom nav', () => {
    renderAt('/admin/orders', 'staff')
    const bottom = screen.getByRole('navigation', { name: 'Navigasi bawah' })
    expect(within(bottom).getAllByRole('link').map((a) => a.textContent)).toEqual([
      '≡Order',
      '⊞Counter',
      '⊟Bill',
      '▣Reservasi',
      '▥Stok',
    ])
  })
})
