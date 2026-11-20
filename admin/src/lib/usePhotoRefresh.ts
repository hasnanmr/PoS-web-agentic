import { useEffect } from 'react'

export const PHOTO_REFRESH_MS = 15 * 60 * 1000

/** Call `reload` every PHOTO_REFRESH_MS while the screen is open (fresh signed photo URLs). */
export function usePhotoRefresh(reload: () => Promise<void>) {
  useEffect(() => {
    const id = setInterval(() => { void reload().catch(() => {}) }, PHOTO_REFRESH_MS)
    return () => clearInterval(id)
  }, [reload])
}
