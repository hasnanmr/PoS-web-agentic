import type { ComponentType } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import { AppShell } from '../layout/AppShell'
import AuditLogPage from '../pages/AuditLogPage'
import BusinessPage from '../pages/BusinessPage'
import CashCountPage from '../pages/CashCountPage'
import CashflowPage from '../pages/CashflowPage'
import CounterPage from '../pages/CounterPage'
import DashboardPage from '../pages/DashboardPage'
import ExpensesPage from '../pages/ExpensesPage'
import MenuPage from '../pages/MenuPage'
import MyAttendancePage from '../pages/MyAttendancePage'
import OpenBillsPage from '../pages/OpenBillsPage'
import OrderBoardPage from '../pages/OrderBoardPage'
import PaymentReviewPage from '../pages/PaymentReviewPage'
import PurchaseOrdersPage from '../pages/PurchaseOrdersPage'
import RecipesPage from '../pages/RecipesPage'
import RecommendationsPage from '../pages/RecommendationsPage'
import ReservationsPage from '../pages/ReservationsPage'
import ShiftsPage from '../pages/ShiftsPage'
import StaffAttendancePage from '../pages/StaffAttendancePage'
import StaffPage from '../pages/StaffPage'
import StockPage from '../pages/StockPage'
import TablesPage from '../pages/TablesPage'
import WhatsAppSetupPage from '../pages/WhatsAppSetupPage'
import { HOME_PATH, navItemsFor, ROUTES } from './nav'
import { useSession } from './session'

const PAGES: Record<keyof typeof ROUTES, ComponentType> = {
  dashboard: DashboardPage,
  orderBoard: OrderBoardPage,
  counter: CounterPage,
  openBills: OpenBillsPage,
  paymentReview: PaymentReviewPage,
  reservations: ReservationsPage,
  stock: StockPage,
  purchaseOrders: PurchaseOrdersPage,
  shifts: ShiftsPage,
  myAttendance: MyAttendancePage,
  menu: MenuPage,
  recipes: RecipesPage,
  recommendations: RecommendationsPage,
  cashflow: CashflowPage,
  expenses: ExpensesPage,
  cashCount: CashCountPage,
  auditLog: AuditLogPage,
  business: BusinessPage,
  staff: StaffPage,
  staffAttendance: StaffAttendancePage,
  tables: TablesPage,
  whatsapp: WhatsAppSetupPage,
}

const PAGE_BY_PATH = new Map<string, ComponentType>(
  (Object.keys(ROUTES) as (keyof typeof ROUTES)[]).map((key) => [ROUTES[key].path, PAGES[key]]),
)

/**
 * Only routes in the current role's navigation are mounted; anything else redirects to the
 * role's home. This is UX only — real authorization is enforced by the API (T-006/T-013).
 */
export function AppRoutes() {
  const { role } = useSession()
  const home = HOME_PATH[role]
  return (
    <Routes>
      <Route element={<AppShell />}>
        {navItemsFor(role).map((item) => {
          const Page = PAGE_BY_PATH.get(item.path)
          return Page ? <Route key={item.path} path={item.path} element={<Page />} /> : null
        })}
        <Route path="*" element={<Navigate to={home} replace />} />
      </Route>
    </Routes>
  )
}
