/**
 * TEMPORARY dev-only role switch. There is no authentication yet (T-006 adds Supabase Auth
 * and server-side roles). Role comes from `?role=owner|staff`, then localStorage, then owner.
 */
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import type { Role } from './nav'

const STORAGE_KEY = 'sme-pos.dev-role'

interface RoleContextValue {
  role: Role
  setRole: (role: Role) => void
}

const RoleContext = createContext<RoleContextValue | null>(null)

function isRole(value: unknown): value is Role {
  return value === 'owner' || value === 'staff'
}

function initialRole(): Role {
  if (typeof window === 'undefined') return 'owner'
  const fromQuery = new URLSearchParams(window.location.search).get('role')
  if (isRole(fromQuery)) return fromQuery
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (isRole(stored)) return stored
  } catch {
    // storage unavailable (private mode); fall through
  }
  return 'owner'
}

export function RoleProvider({ children, initial }: { children: ReactNode; initial?: Role }) {
  const [role, setRoleState] = useState<Role>(() => initial ?? initialRole())
  const setRole = useCallback((next: Role) => {
    setRoleState(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // ignore
    }
  }, [])
  const value = useMemo(() => ({ role, setRole }), [role, setRole])
  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useRole(): RoleContextValue {
  const ctx = useContext(RoleContext)
  if (!ctx) throw new Error('useRole must be used inside <RoleProvider>')
  return ctx
}
