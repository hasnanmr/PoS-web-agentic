// Menu photo (T-132) from a signed, expiring URL. If the image cannot load (the URL expired
// while the screen stayed open, or Storage is down) it falls back to the grey placeholder
// instead of a broken-image icon. Screens reload their data with usePhotoRefresh, and the API
// only hands out URLs with at least 20 minutes left, so a fresh URL arrives in time.
import { useState } from 'react'

export function Photo({ src, alt = '', className }: { src: string | null; alt?: string; className: string }) {
  const [failed, setFailed] = useState<string | null>(null)
  if (!src || failed === src) return <span aria-hidden="true" className={`${className} bg-page`} />
  return <img src={src} alt={alt} className={`${className} object-cover`} onError={() => setFailed(src)} />
}
