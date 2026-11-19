// Loads an authenticated image (attendance selfies, PoC: served by the API, not a Storage
// bucket) with the session token, as an object URL that is revoked when it changes.
import { useEffect, useState } from 'react'
import { useSession } from '../app/session'

export function useBlobUrl(path: string | null): { url?: string; failed: boolean } {
  const { api } = useSession()
  const [state, setState] = useState<{ path: string | null; url?: string; failed: boolean }>({ path: null, failed: false })
  useEffect(() => {
    if (!path) return
    let cancelled = false
    let url: string | undefined
    api.blob(path, 'image/*').then((blob) => {
      if (cancelled || !(blob instanceof Blob)) return
      url = URL.createObjectURL(blob)
      setState({ path, url, failed: false })
    }).catch(() => {
      if (!cancelled) setState({ path, failed: true })
    })
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [api, path])
  return state.path === path ? { url: state.url, failed: state.failed } : { failed: false }
}
