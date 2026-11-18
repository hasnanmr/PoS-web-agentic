import { useEffect, useRef } from 'react'

/** Reload `loaded` every `ms`, skipping a tick while the previous request is still running. */
export function usePolling(loaded: { loading: boolean; reload: () => Promise<void> }, ms = 10_000) {
  const loadingRef = useRef(loaded.loading)
  useEffect(() => {
    loadingRef.current = loaded.loading
  })
  const { reload } = loaded
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!loadingRef.current) void reload()
    }, ms)
    return () => window.clearInterval(timer)
  }, [reload, ms])
}
