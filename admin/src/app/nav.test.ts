import { describe, expect, it } from 'vitest'
import { canAccess, MOBILE_NAV, NAV, navItemsFor, STAFF_SIDEBAR_NOTE } from './nav'

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
          'Shift Kasir',
          'Absensi Saya',
        ],
      ],
    ])
    expect(STAFF_SIDEBAR_NOTE).toBe('Menu, harga, laporan & pengaturan hanya untuk owner.')
  })

  it('staff cannot reach owner-only routes', () => {
    expect(canAccess('staff', '/dashboard')).toBe(false)
    expect(canAccess('staff', '/finance/cashflow')).toBe(false)
    expect(canAccess('staff', '/settings/whatsapp')).toBe(false)
    expect(canAccess('owner', '/my-attendance')).toBe(false)
    expect(canAccess('staff', '/orders')).toBe(true)
  })

  it('every route path is unique per role and every item names a wireframe screen', () => {
    for (const role of ['owner', 'staff'] as const) {
      const items = navItemsFor(role)
      expect(new Set(items.map((i) => i.path)).size).toBe(items.length)
      for (const item of items) expect(item.screen).toMatch(/^[OS]\d+$/)
    }
  })

  it('mobile bottom nav has the five M1–M6 tabs, reachable by both roles', () => {
    expect(MOBILE_NAV.map((t) => t.label)).toEqual(['Order', 'Counter', 'Bill', 'Reservasi', 'Stok'])
    for (const { item } of MOBILE_NAV) {
      expect(canAccess('owner', item.path)).toBe(true)
      expect(canAccess('staff', item.path)).toBe(true)
    }
  })
})
