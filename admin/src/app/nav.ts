/**
 * Role-aware navigation, mirroring wireframe components `Sidebar/Owner` and `Sidebar/Staff`
 * (design/previews/01-admin-owner.png, 02-admin-staff.png) and the mobile bottom nav (M1–M6).
 * Labels are copied verbatim from the wireframe; do not rename without updating the design.
 */

export type Role = 'owner' | 'staff'

export interface NavItem {
  label: string
  path: string
  /** Wireframe screen code that this route will implement. */
  screen: string
  /** Glyph used in the wireframe sidebar. */
  icon: string
}

export interface NavGroup {
  heading: string
  items: NavItem[]
}

export const ROUTES = {
  dashboard: { label: 'Dashboard', path: '/dashboard', screen: 'O2', icon: '▦' },
  orderBoard: { label: 'Order Board', path: '/orders', screen: 'S2', icon: '≡' },
  counter: { label: 'Counter / POS', path: '/counter', screen: 'S1', icon: '⊞' },
  openBills: { label: 'Open Bills', path: '/open-bills', screen: 'S5', icon: '⊟' },
  paymentReview: { label: 'Review Pembayaran', path: '/payment-review', screen: 'S4', icon: '◎' },
  reservations: { label: 'Reservasi & Meja', path: '/reservations', screen: 'S6', icon: '▣' },
  stock: { label: 'Stok', path: '/stock', screen: 'S7', icon: '▥' },
  purchaseOrders: { label: 'Purchase Order', path: '/purchase-orders', screen: 'S10', icon: '▧' },
  shifts: { label: 'Shift Kasir', path: '/shifts', screen: 'S8', icon: '◷' },
  myAttendance: { label: 'Absensi Saya', path: '/my-attendance', screen: 'S9', icon: '⏱' },
  menu: { label: 'Menu & Add-on', path: '/catalog/menu', screen: 'O5', icon: '◫' },
  recipes: { label: 'Resep & Bahan', path: '/catalog/recipes', screen: 'O6', icon: '⚗' },
  recommendations: {
    label: 'Rekomendasi',
    path: '/catalog/recommendations',
    screen: 'O7',
    icon: '★',
  },
  cashflow: { label: 'Laporan Cashflow', path: '/finance/cashflow', screen: 'O9', icon: '↗' },
  expenses: { label: 'Pengeluaran', path: '/finance/expenses', screen: 'O9b', icon: '−' },
  cashCount: { label: 'Laporan Cash Count', path: '/finance/cash-count', screen: 'O10', icon: '≣' },
  auditLog: { label: 'Audit Log', path: '/finance/audit-log', screen: 'O11', icon: '⌕' },
  business: { label: 'Bisnis & Outlet', path: '/settings/business', screen: 'O3', icon: '○' },
  staff: { label: 'Staf & Akses', path: '/settings/staff', screen: 'O4', icon: '☺' },
  staffAttendance: {
    label: 'Kehadiran Staf',
    path: '/settings/attendance',
    screen: 'O14',
    icon: '⏱',
  },
  tables: { label: 'Meja & Reservasi', path: '/settings/tables', screen: 'O8', icon: '◻' },
  whatsapp: { label: 'WhatsApp Setup', path: '/settings/whatsapp', screen: 'O12', icon: '✆' },
} as const satisfies Record<string, NavItem>

const R = ROUTES

export const NAV: Record<Role, NavGroup[]> = {
  owner: [
    {
      heading: 'OPERASIONAL',
      items: [
        R.dashboard,
        R.orderBoard,
        R.counter,
        R.openBills,
        R.paymentReview,
        R.reservations,
        R.stock,
        R.shifts,
      ],
    },
    { heading: 'KATALOG', items: [R.menu, R.recipes, R.recommendations] },
    { heading: 'KEUANGAN (OWNER)', items: [R.cashflow, R.expenses, R.cashCount, R.auditLog] },
    {
      heading: 'PENGATURAN',
      items: [R.business, R.staff, R.staffAttendance, R.tables, R.whatsapp],
    },
  ],
  staff: [
    {
      heading: 'OPERASIONAL',
      items: [
        R.orderBoard,
        R.counter,
        R.openBills,
        R.paymentReview,
        R.reservations,
        R.stock,
        R.purchaseOrders,
        R.shifts,
        R.myAttendance,
      ],
    },
  ],
}

/** Footer note under the staff sidebar (wireframe S1–S9). */
export const STAFF_SIDEBAR_NOTE = 'Menu, harga, laporan & pengaturan hanya untuk owner.'

/** Mobile bottom nav (M1–M6). Same five tabs for both roles. */
export const MOBILE_NAV: { label: string; item: NavItem }[] = [
  { label: 'Order', item: R.orderBoard },
  { label: 'Counter', item: R.counter },
  { label: 'Bill', item: R.openBills },
  { label: 'Reservasi', item: R.reservations },
  { label: 'Stok', item: R.stock },
]

/**
 * Each role has its own URL area so owner and staff can be signed in on the same device at once
 * (one tab each): the owner app lives at the root, the staff app under `/admin`. `ROUTES` paths
 * are area-relative; always resolve them with `rolePath` before linking or routing.
 */
export const AREA_BASE: Record<Role, string> = {
  owner: '',
  staff: '/admin',
}

/** The role whose app owns this URL: `/admin` and below is staff, everything else owner. */
export function areaForPath(pathname: string): Role {
  return /^\/admin(\/|$)/.test(pathname) ? 'staff' : 'owner'
}

export function rolePath(role: Role, path: string): string {
  return AREA_BASE[role] + path
}

export const HOME_PATH: Record<Role, string> = {
  owner: rolePath('owner', R.dashboard.path),
  staff: rolePath('staff', R.orderBoard.path),
}

export function navItemsFor(role: Role): NavItem[] {
  return NAV[role].flatMap((group) => group.items)
}

/** `path` is a full URL path (area prefix included). */
export function canAccess(role: Role, path: string): boolean {
  return navItemsFor(role).some((item) => rolePath(role, item.path) === path)
}
