/**
 * Signed-in session for the admin shell: who the user is (`GET /me`), the API client, and the
 * selected outlet (sidebar switcher "Outlet: … ▾"). Provided by <AuthGate> once the user is a
 * tenant owner or staff member; tests provide a fake value.
 */
import { createContext, useCallback, useContext } from 'react'
import type { Api } from '../lib/api'
import type { Me, MeOutlet } from '../lib/types'
import { rolePath, type Role } from './nav'

export interface Session {
  me: Me
  role: 'owner' | 'staff'
  api: Api
  outlet: MeOutlet | null
  setOutletId: (id: string) => void
  /** Re-read /me (after adding an outlet, renaming, …). */
  reload: () => Promise<void>
  signOut: () => Promise<void>
}

export const SessionContext = createContext<Session | null>(null)

export function useSession(): Session {
  const session = useContext(SessionContext)
  if (!session) throw new Error('useSession must be used inside <SessionContext.Provider>')
  return session
}

/** Resolve an area-relative `ROUTES` path to a URL for the signed-in role (staff → `/admin…`). */
export function useRolePath(): (path: string) => string {
  const { role } = useSession()
  return useCallback((path: string) => rolePath(role, path), [role])
}

/** Selected outlet, remembered per area so an owner tab and a staff tab don't overwrite it. */
export const OUTLET_STORAGE_KEY: Record<Role, string> = {
  owner: 'sme-pos.outlet',
  staff: 'sme-pos.outlet.staff',
}

export function pickOutlet(outlets: MeOutlet[], preferred: string | null): MeOutlet | null {
  return outlets.find((o) => o.id === preferred) ?? outlets[0] ?? null
}
