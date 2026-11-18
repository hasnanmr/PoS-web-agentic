/**
 * Signed-in session for the admin shell: who the user is (`GET /me`), the API client, and the
 * selected outlet (sidebar switcher "Outlet: … ▾"). Provided by <AuthGate> once the user is a
 * tenant owner or staff member; tests provide a fake value.
 */
import { createContext, useContext } from 'react'
import type { Api } from '../lib/api'
import type { Me, MeOutlet } from '../lib/types'

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

export const OUTLET_STORAGE_KEY = 'sme-pos.outlet'

export function pickOutlet(outlets: MeOutlet[], preferred: string | null): MeOutlet | null {
  return outlets.find((o) => o.id === preferred) ?? outlets[0] ?? null
}
