// Page title bar. Desktop: white header band (O2/S1 layout). Mobile ≤ 767px: hamburger + title,
// outlet line underneath (M1–M6). Filter chips/actions are added per screen later.
import type { ReactNode } from 'react'
import { DEV_IDENTITY } from '../app/dev-identity'
import { useShell } from './shell-context'

interface PageHeaderProps {
  title: string
  actions?: ReactNode
}

export function PageHeader({ title, actions }: PageHeaderProps) {
  const { openDrawer } = useShell()
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-surface px-4 py-3 md:px-6 md:py-4">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={openDrawer}
          aria-label="Buka menu"
          className="-ml-1 flex h-8 w-8 items-center justify-center rounded-md text-lg text-text hover:bg-page md:hidden"
        >
          ≡
        </button>
        <h1 className="min-w-0 flex-1 truncate text-[17px] font-bold text-text md:text-[18px]">
          {title}
        </h1>
        {actions}
      </div>
      <p className="mt-0.5 pl-10 text-[11px] text-text-muted md:hidden">
        {DEV_IDENTITY.businessName} – {DEV_IDENTITY.outletName} ▾
      </p>
    </header>
  )
}
