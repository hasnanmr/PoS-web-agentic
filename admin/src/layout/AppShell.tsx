// App shell for the admin web app: Sidebar/Owner or Sidebar/Staff on desktop (O*, S* screens),
// hamburger drawer + bottom nav on mobile 360px (M1–M6). No horizontal scroll (AC7.2).
import { useEffect, useMemo, useState } from 'react'
import { Outlet, useLocation } from 'react-router'
import { useSession } from '../app/session'
import { MobileBottomNav } from './MobileBottomNav'
import { ShellContext } from './shell-context'
import { Sidebar } from './Sidebar'

export function AppShell() {
  const { role } = useSession()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location = useLocation()
  const shell = useMemo(() => ({ openDrawer: () => setDrawerOpen(true) }), [])

  // Close the drawer whenever the route changes.
  const [lastPath, setLastPath] = useState(location.pathname)
  if (lastPath !== location.pathname) {
    setLastPath(location.pathname)
    setDrawerOpen(false)
  }

  useEffect(() => {
    if (!drawerOpen) return
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setDrawerOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drawerOpen])

  return (
    <ShellContext.Provider value={shell}>
      <div className="flex min-h-dvh w-full overflow-x-hidden bg-page text-text">
        <aside className="sticky top-0 hidden h-dvh md:block">
          <Sidebar role={role} />
        </aside>

        {drawerOpen && (
          <div className="fixed inset-0 z-30 md:hidden" role="dialog" aria-modal="true">
            <button
              type="button"
              aria-label="Tutup menu"
              className="absolute inset-0 bg-text/40"
              onClick={() => setDrawerOpen(false)}
            />
            <div className="relative h-full w-[220px] max-w-[85vw] shadow-xl">
              <Sidebar role={role} onNavigate={() => setDrawerOpen(false)} />
            </div>
          </div>
        )}

        <main className="min-w-0 flex-1 pb-16 md:pb-0">
          <Outlet />
        </main>

        <MobileBottomNav />
      </div>
    </ShellContext.Provider>
  )
}
