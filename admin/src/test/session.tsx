import type { ReactNode } from 'react'
import { SessionContext, type Session } from '../app/session'

export function WithSession({ session, children }: { session: Session; children: ReactNode }) {
  return <SessionContext.Provider value={session}>{children}</SessionContext.Provider>
}
