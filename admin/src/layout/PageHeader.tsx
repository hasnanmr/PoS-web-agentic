// Page title bar. Desktop: white header band (O2/S1 layout). Mobile ≤ 767px: hamburger + title,
// outlet line underneath (M1–M6). Filter chips/actions are added per screen later.
import type { ReactNode } from 'react'
import { useSession } from '../app/session'
import { useShell } from './shell-context'

interface PageHeaderProps {
  title: string
  actions?: ReactNode
  /** Tabs right after the title (O2 Dashboard: Ringkasan · PO & Supplier). */
  tabs?: ReactNode
}

export function PageHeader({ title, actions, tabs }: PageHeaderProps) {
  const { openDrawer } = useShell()
  const { me, outlet } = useSession()
  const outletLine = (className: string) => (
    <p className={`pl-10 text-[11px] text-text-muted md:hidden ${className}`}>
      {me.tenant?.name} – {outlet?.name ?? 'belum ada outlet'}
    </p>
  )
  return (
    // Sticky on desktop only: on a phone the header with filters (O2) would cover a quarter of the
    // screen, so it scrolls away with the page and the bottom nav stays.
    <header className="z-10 border-b border-border bg-surface px-4 py-3 md:sticky md:top-0 md:px-6 md:py-4">
      <div className={`flex items-center gap-3 ${tabs ? 'flex-wrap' : ''}`}>
        <button
          type="button"
          onClick={openDrawer}
          aria-label="Buka menu"
          className="-ml-1 flex h-8 w-8 items-center justify-center rounded-md text-lg text-text hover:bg-page md:hidden"
        >
          ≡
        </button>
        <h1 className={`min-w-0 truncate text-[17px] font-bold text-text md:text-[18px] ${tabs ? '' : 'flex-1'}`}>
          {title}
        </h1>
        {tabs && <div className="min-w-0 flex-1">{tabs}</div>}
        {/* With tabs the filters wrap to their own line: keep the outlet line under the title (M1). */}
        {tabs && outletLine('basis-full')}
        {actions}
      </div>
      {!tabs && outletLine('mt-0.5')}
    </header>
  )
}
