import { describe, expect, it } from 'vitest'
import {
  areaForPath,
  canAccess,
  HOME_PATH,
  MOBILE_NAV,
  NAV,
  navItemsFor,
  ownAreaPath,
  rolePath,
  STAFF_SIDEBAR_NOTE,
} from './nav'

const labels = (role: 'owner' | 'staff') =>
  NAV[role].map((group) => [group.heading, group.items.map((item) => item.label)])

describe('navigation per role (wireframe Sidebar/Owner, Sidebar/Staff)', () => {
  it('owner sees exactly the four wireframe groups in order', () => {
    expect(labels('owner')).toEqual([
      [
        'OPERASIONAL',
        [
          'Dashboard',
          'Order Board',
          'Counter / POS',
          'Open Bills',
          'Review Pembayaran',
          'Reservasi & Meja',
          'Stok',
          'Shift Kasir',
        ],
      ],
      ['KATALOG', ['Menu & Add-on', 'Resep & Bahan', 'Rekomendasi']],
      ['KEUANGAN (OWNER)', ['Laporan Cashflow', 'Pengeluaran', 'Laporan Cash Count', 'Audit Log']],
      [
        'PENGATURAN',
        ['Bisnis & Outlet', 'Staf & Akses', 'Kehadiran Staf', 'Meja & Reservasi', 'WhatsApp Setup'],
      ],
    ])
  })

  it('staff sees only OPERASIONAL plus Absensi Saya', () => {
    expect(labels('staff')).toEqual([
      [
        'OPERASIONAL',
        [
          'Order Board',
          'Counter / POS',
          'Open Bills',
          'Review Pembayaran',
          'Reservasi & Meja',
          'Stok',
          'Purchase Order',
          'Shift Kasir',
          'Absensi Saya',
        ],
      ],
    ])
    expect(STAFF_SIDEBAR_NOTE).toBe('Menu, harga, laporan & pengaturan hanya untuk owner.')
  })

  it('staff cannot reach owner-only routes', () => {
    expect(canAccess('staff', '/admin/dashboard')).toBe(false)
    expect(canAccess('staff', '/admin/finance/cashflow')).toBe(false)
    expect(canAccess('staff', '/admin/settings/whatsapp')).toBe(false)
    expect(canAccess('owner', '/my-attendance')).toBe(false)
    expect(canAccess('staff', '/admin/orders')).toBe(true)
  })

  it('staff pages live under /admin, owner pages at the root', () => {
    expect(rolePath('staff', '/orders')).toBe('/admin/orders')
    expect(rolePath('owner', '/orders')).toBe('/orders')
    expect(HOME_PATH).toEqual({ owner: '/dashboard', staff: '/admin/orders' })
    // Same page, two URLs: each role only reaches its own area.
    expect(canAccess('staff', '/orders')).toBe(false)
    expect(canAccess('owner', '/admin/orders')).toBe(false)
    expect(areaForPath('/admin')).toBe('staff')
    expect(areaForPath('/admin/counter')).toBe('staff')
    expect(areaForPath('/administrator')).toBe('owner')
    expect(areaForPath('/orders')).toBe('owner')
  })

  it('sends an account in the wrong area to the same page in its own area, else its home', () => {
    expect(ownAreaPath('staff', '/orders')).toBe('/admin/orders')
    expect(ownAreaPath('staff', '/dashboard')).toBe('/admin/orders')
    expect(ownAreaPath('staff', '/')).toBe('/admin/orders')
    expect(ownAreaPath('owner', '/admin/stock')).toBe('/stock')
    expect(ownAreaPath('owner', '/admin/my-attendance')).toBe('/dashboard')
    expect(ownAreaPath('owner', '/admin')).toBe('/dashboard')
  })

  it('every route path is unique per role and every item names a wireframe screen', () => {
    for (const role of ['owner', 'staff'] as const) {
      const items = navItemsFor(role)
      expect(new Set(items.map((i) => i.path)).size).toBe(items.length)
      for (const item of items) expect(item.screen).toMatch(/^[OS]\d+[a-z]?$/)
    }
  })

  it('mobile bottom nav has the five M1–M6 tabs, reachable by both roles', () => {
    expect(MOBILE_NAV.map((t) => t.label)).toEqual(['Order', 'Counter', 'Bill', 'Reservasi', 'Stok'])
    for (const { item } of MOBILE_NAV) {
      expect(canAccess('owner', rolePath('owner', item.path))).toBe(true)
      expect(canAccess('staff', rolePath('staff', item.path))).toBe(true)
    }
  })
})

describe('nav icons', () => {
  it.each(['owner', 'staff'] as const)('every %s menu has its own icon', (role) => {
    const items = navItemsFor(role)
    expect(new Set(items.map((item) => item.icon)).size).toBe(items.length)
  })
})
