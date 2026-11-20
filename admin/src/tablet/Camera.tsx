// K2 · Ambil selfie (wajib): front camera with the face oval. There is no way to skip the photo;
// when the camera cannot be used the canvas copy is shown ("Selfie wajib untuk absen…").
import { useEffect, useRef, useState } from 'react'

const MAX_WIDTH = 720
const JPEG_QUALITY = 0.8

interface Props {
  title: string
  onCancel: () => void
  onCapture: (photo: Blob) => void
}

export function Camera(props: Props) {
  // "Coba lagi" remounts the view, which asks for the camera again.
  const [attempt, setAttempt] = useState(0)
  return <CameraView key={attempt} {...props} onRetry={() => setAttempt((a) => a + 1)} />
}

function cameraApi(): MediaDevices | undefined {
  const media = typeof navigator !== 'undefined' ? navigator.mediaDevices : undefined
  return media?.getUserMedia ? media : undefined
}

function CameraView({ title, onCancel, onCapture, onRetry }: Props & { onRetry: () => void }) {
  const video = useRef<HTMLVideoElement>(null)
  const [denied, setDenied] = useState(() => !cameraApi())
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let stream: MediaStream | undefined
    let cancelled = false
    const media = cameraApi()
    if (!media) return
    media.getUserMedia({ video: { facingMode: 'user', width: { ideal: 1280 } }, audio: false }).then((s) => {
      if (cancelled) {
        s.getTracks().forEach((t) => t.stop())
        return
      }
      stream = s
      if (video.current) {
        video.current.srcObject = s
        void video.current.play?.()
      }
      setReady(true)
    }).catch(() => {
      if (!cancelled) setDenied(true)
    })
    return () => {
      cancelled = true
      stream?.getTracks().forEach((t) => t.stop())
    }
  }, [])

  function capture() {
    const v = video.current
    if (!v || !v.videoWidth) return
    const scale = Math.min(1, MAX_WIDTH / v.videoWidth)
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(v.videoWidth * scale)
    canvas.height = Math.round(v.videoHeight * scale)
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      setDenied(true)
      return
    }
    ctx.drawImage(v, 0, 0, canvas.width, canvas.height)
    canvas.toBlob((blob) => {
      if (blob) onCapture(blob)
      else setDenied(true)
    }, 'image/jpeg', JPEG_QUALITY)
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[#1B2430] p-4 text-white">
      <h1 className="text-[16px] font-semibold">{title}</h1>
      <div className="relative aspect-[4/3] w-full max-w-[640px] overflow-hidden rounded-lg bg-[#3A4452]">
        <video ref={video} playsInline muted aria-label="Kamera depan"
          className={`h-full w-full -scale-x-100 object-cover ${ready ? '' : 'invisible'}`} />
        <svg viewBox="0 0 640 480" className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true">
          <ellipse cx="320" cy="240" rx="120" ry="150" fill="none" stroke="white" strokeWidth="3" strokeDasharray="8 8" />
        </svg>
        {denied && (
          <div role="alert" className="absolute inset-x-4 bottom-4 rounded-md bg-danger-soft px-3 py-2 text-center text-[12px] text-danger">
            Selfie wajib untuk absen. Izinkan kamera lalu coba lagi.
          </div>
        )}
      </div>
      <p className="text-[12px] text-[#CBD5E6]">Posisikan wajah di dalam oval, lalu ambil foto</p>
      <div className="flex gap-3">
        <button type="button" onClick={onCancel}
          className="h-12 w-[133px] rounded-md bg-[#3A4452] text-[13px] font-semibold">✕ Batal</button>
        {denied ? (
          <button type="button" onClick={onRetry}
            className="h-12 w-[195px] rounded-md bg-[#22A06B] text-[13px] font-semibold">↻ Coba lagi</button>
        ) : (
          <button type="button" onClick={capture} disabled={!ready}
            className="h-12 w-[195px] rounded-md bg-[#22A06B] text-[13px] font-semibold disabled:opacity-60">● Ambil foto</button>
        )}
      </div>
    </main>
  )
}
