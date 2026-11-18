// Loads the outlet's static QRIS (PoC demo) with the session token, as an object URL.
import { useEffect, useState } from 'react'
import { useSession } from '../app/session'
import { ApiError } from './api'

export function useQrisImage(outletId: string | undefined, version = 0): { url?: string; missing: boolean } {
  const { api } = useSession()
  const [state, setState] = useState<{ url?: string; missing: boolean }>({ missing: false })
  useEffect(() => {
    if (!outletId) return
    let cancelled = false
    let url: string | undefined
    api.blob(`/ops/outlets/${outletId}/qris/image`, 'image/*').then((blob) => {
      if (cancelled || !(blob instanceof Blob)) return
      url = URL.createObjectURL(blob)
      setState({ url, missing: false })
    }).catch((e: unknown) => {
      if (!cancelled) setState({ missing: e instanceof ApiError && e.status === 404 })
    })
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [api, outletId, version])
  return state
}
