// Wireframe components `Sidebar/Owner` and `Sidebar/Staff` (01-admin-owner.png, 02-admin-staff.png):
// light 220px sidebar, logo, outlet switcher, grouped nav with uppercase headings.
import { NavLink } from 'react-router'
import { NAV, STAFF_SIDEBAR_NOTE, type Role } from '../app/nav'
import { DEV_IDENTITY } from '../app/dev-identity'
import { DevRoleSwitch } from './DevRoleSwitch'

interface SidebarProps {
  role: Role
  onNavigate?: () => void
}

export function Sidebar({ role, onNavigate }: SidebarProps) {
  return (
    <nav
      aria-label="Navigasi utama"
      className="flex h-full w-[220px] shrink-0 flex-col overflow-y-auto border-r border-border bg-surface px-3 py-4"
    >
      <div className="px-2">
        <div className="text-[15px] font-bold text-primary">
          <span aria-hidden="true">◼</span> SME POS
        </div>
        {/* Outlet switcher — wired to real outlets in T-011/T-013. */}
        <button
          type="button"
          className="mt-0.5 text-left text-[11px] text-text-muted hover:text-text"
          title="Ganti outlet"
        >
          Outlet: {DEV_IDENTITY.businessName} – {DEV_IDENTITY.outletName} ▾
        </button>
      </div>

      {NAV[role].map((group) => (
        <div key={group.heading} className="mt-4" role="group" aria-label={group.heading}>
          <div className="px-2 pb-1 text-[10px] font-medium tracking-wider text-text-muted uppercase">
            {group.heading}
          </div>
          <ul>
            {group.items.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    [
                      'flex h-8 items-center gap-2 rounded-md px-2 text-[13px]',
                      isActive
                        ? 'bg-primary-soft font-medium text-text'
                        : 'text-text hover:bg-page',
                    ].join(' ')
                  }
                >
                  <span aria-hidden="true" className="w-4 text-center text-[12px] text-text-muted">
                    {item.icon}
                  </span>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}

      {role === 'staff' && (
        <p className="mt-6 px-2 text-[11px] leading-4 text-text-muted">
          Staf: {DEV_IDENTITY.staffName} ({DEV_IDENTITY.staffTitle})
          <br />
          {STAFF_SIDEBAR_NOTE}
        </p>
      )}

      {import.meta.env.DEV && <DevRoleSwitch />}
    </nav>
  )
}
