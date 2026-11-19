// Sidebar "Pengeluaran" — opens wireframe O9 (Laporan Cashflow & Pengeluaran) with the expense list opened
// in full ("Lihat semua") so entries can be reviewed and reversed. Same endpoints as O9. Direct expenses only:
// purchase orders live in the Dashboard tab "PO & Supplier" (O15–O17, PRD v0.15).
import CashflowPage from './CashflowPage'

export default function ExpensesPage() {
  return <CashflowPage expandExpenses />
}
