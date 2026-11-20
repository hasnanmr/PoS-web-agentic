// Mobile bottom nav from M1–M6: Order, Counter, Bill, Reservasi, Stok.
import { NavLink } from "react-router";
import { MOBILE_NAV } from "../app/nav";
import { useRolePath } from "../app/session";

export function MobileBottomNav() {
  const pathFor = useRolePath();
  return (
    <nav
      aria-label="Navigasi bawah"
      className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      <ul className="grid grid-cols-5">
        {MOBILE_NAV.map(({ label, item }) => (
          <li key={item.path}>
            <NavLink
              to={pathFor(item.path)}
              className={({ isActive }) =>
                [
                  "flex h-14 flex-col items-center justify-center gap-0.5 text-[11px]",
                  isActive ? "font-semibold text-primary" : "text-text-muted",
                ].join(" ")
              }
            >
              {({ isActive }) => (
                <>
                  <item.icon
                    aria-hidden="true"
                    size={20}
                    strokeWidth={isActive ? 2.25 : 1.75}
                  />
                  {label}
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
