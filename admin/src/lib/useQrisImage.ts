// Loads the outlet's static QRIS (PoC demo) with the session token, as an object URL.
import { useEffect, useState } from 'react'
import { useSession } from '../app/session'
import { ApiError } from './api'

type Loaded = { outletId: string; url?: string; missing: boolean }

export function useQrisImage(outletId: string | undefined, version = 0): { url?: string; missing: boolean } {
  const { api } = useSession()
  const [state, setState] = useState<Loaded>()
  useEffect(() => {
    if (!outletId) return
    let cancelled = false
    api.blob(`/ops/outlets/${outletId}/qris/image`, 'image/*').then((blob) => {
      if (cancelled || !(blob instanceof Blob)) return
      setState({ outletId, url: URL.createObjectURL(blob), missing: false })
    }).catch((e: unknown) => {
      if (!cancelled) setState({ outletId, missing: e instanceof ApiError && e.status === 404 })
    })
    return () => { cancelled = true }
  }, [api, outletId, version])
  // A new version keeps showing the old image until the new one is in; the old URL is
  // revoked only once it is replaced (or on unmount), so <img> never points at a revoked URL.
  const url = state?.url
  useEffect(() => () => { if (url) URL.revokeObjectURL(url) }, [url])
  // Another outlet's QRIS is never shown while this outlet's image loads.
  return state && state.outletId === outletId ? { url: state.url, missing: state.missing } : { missing: false }
}
