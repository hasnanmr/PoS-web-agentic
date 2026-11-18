import { createContext, useContext } from 'react'

export interface ShellContextValue {
  openDrawer: () => void
}

export const ShellContext = createContext<ShellContextValue>({ openDrawer: () => {} })

export function useShell(): ShellContextValue {
  return useContext(ShellContext)
}
