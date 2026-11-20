// Wireframe components `Sidebar/Owner` and `Sidebar/Staff` (01-admin-owner.png, 02-admin-staff.png):
// light 220px sidebar, logo, outlet switcher, grouped nav with uppercase headings.
import { NavLink } from "react-router";
import { NAV, rolePath, STAFF_SIDEBAR_NOTE, type Role } from "../app/nav";
import { useSession } from "../app/session";
import { Brand } from "../ui/Brand";

interface SidebarProps {
  role: Role;
  onNavigate?: () => void;
}

export function Sidebar({ role, onNavigate }: SidebarProps) {
  const { me, outlet, setOutletId, signOut } = useSession();
  return (
    <nav
      aria-label="Navigasi utama"
      className="flex h-full w-[220px] shrink-0 flex-col overflow-y-auto border-r border-border bg-surface px-3 py-4"
    >
      <div className="px-2">
        <Brand className="text-[15px]" />
        {/* Outlet switcher: outlets from GET /me (owner: all, staff: assigned only). */}
        <label className="mt-0.5 block text-[11px] text-text-muted">
          <span>Outlet: {me.tenant?.name} – </span>
          <select
            aria-label="Ganti outlet"
            className="max-w-full cursor-pointer appearance-none bg-transparent text-[11px] text-text-muted hover:text-text focus:outline-none"
            value={outlet?.id ?? ""}
            onChange={(event) => setOutletId(event.target.value)}
          >
            {me.outlets.length === 0 && (
              <option value="">belum ada outlet</option>
            )}
            {me.outlets.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
          <span aria-hidden="true"> ▾</span>
        </label>
      </div>

      {NAV[role].map((group) => (
        <div
          key={group.heading}
          className="mt-4"
          role="group"
          aria-label={group.heading}
        >
          <div className="px-2 pb-1 text-[10px] font-medium tracking-wider text-text-muted uppercase">
            {group.heading}
          </div>
          <ul>
            {group.items.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={rolePath(role, item.path)}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    [
                      "flex h-8 items-center gap-2.5 rounded-md px-2 text-[13px]",
                      isActive
                        ? "bg-primary-soft font-medium text-text"
                        : "text-text hover:bg-page",
                    ].join(" ")
                  }
                >
                  {({ isActive }) => (
                    <>
                      <item.icon
                        aria-hidden="true"
                        size={16}
                        strokeWidth={isActive ? 2.25 : 1.75}
                        className={[
                          "shrink-0",
                          isActive ? "text-primary" : "text-text-muted",
                        ].join(" ")}
                      />
                      {item.label}
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}

      {role === "staff" && (
        <p className="mt-6 px-2 text-[11px] leading-4 text-text-muted">
          Staf: {me.user.display_name ?? me.user.email}
          <br />
          {STAFF_SIDEBAR_NOTE}
        </p>
      )}

      <div className="mt-auto px-2 pt-6 text-[11px] text-text-muted">
        <div className="truncate">{me.user.email}</div>
        <button
          type="button"
          onClick={() => void signOut()}
          className="mt-1 text-primary hover:underline"
        >
          Keluar
        </button>
      </div>
    </nav>
  );
}
