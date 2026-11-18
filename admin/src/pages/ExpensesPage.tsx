// Sidebar "Pengeluaran" — opens wireframe O9 (Laporan Cashflow & Pengeluaran) with the expense list opened
// in full ("Lihat semua") so entries can be reviewed and reversed. Same endpoints as O9. The Purchase Order
// tab of this menu (O15, T-125–T-131) is a later wave; until then only direct expenses are shown.
import CashflowPage from './CashflowPage'

export default function ExpensesPage() {
  return <CashflowPage expandExpenses />
}
