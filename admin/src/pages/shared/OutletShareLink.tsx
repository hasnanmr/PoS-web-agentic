// The outlet link /o/<slug> to paste in an Instagram bio, a WhatsApp status or Google Maps
// (page 07 "Catatan perilaku · Bagikan link outlet"). Shown read-only in two places:
// - O2 Dashboard, tab Ringkasan: the "Link pesan online" strip above the KPI tiles (OutletLinkStrip);
// - O3 Bisnis & Outlet → Umum: the "Link pesan" row (OutletLinkValue).
// The slug is changed only in O8 (Meja & Reservasi, with a confirmation); "Atur link & QR →"
// switches to that outlet and opens it. Endpoint: GET /owner/outlets/{id}/public-link (owner).
// Canvas notes: Salin → "Link outlet disalin."; Bagikan opens the phone's share menu and is
// hidden when the browser can't share; no URL yet → "Link pesan belum aktif.", both disabled.
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useSession } from '../../app/session'
import { errorMessage } from '../../lib/api'
import type { OutletPublicLink } from '../../lib/types'
import { useLoad } from '../../lib/useLoad'
import { LinkButton, Select } from '../../ui/kit'

type Notice = { tone: 'success' | 'danger'; text: string }

const canShare = () => typeof navigator !== 'undefined' && typeof navigator.share === 'function'

function useOutletLink(outletId: string) {
  const { api } = useSession()
  return useLoad(() => api.get<OutletPublicLink>(`/owner/outlets/${outletId}/public-link`), outletId)
}

/** Salin · Bagikan for one URL, with the notice under it. */
function ShareActions({ url, outletName, onNotice }: {
  url: string | null; outletName: string; onNotice: (n: Notice | undefined) => void
}) {
  async function copy() {
    if (!url) return
    try {
      await navigator.clipboard.writeText(url)
      onNotice({ tone: 'success', text: 'Link outlet disalin.' })
    } catch {
      onNotice({ tone: 'danger', text: 'Link belum bisa disalin. Salin manual dari kolom link.' })
    }
  }

  async function share() {
    if (!url) return
    onNotice(undefined)
    try {
      await navigator.share({ title: `Pesan di ${outletName}`, url })
    } catch (e) {
      // Closing the share menu is not an error.
      if (e instanceof DOMException && e.name === 'AbortError') return
      onNotice({ tone: 'danger', text: 'Link belum bisa dibagikan. Pakai Salin, lalu tempel manual.' })
    }
  }

  return (
    <span className="flex shrink-0 items-center gap-2 text-[12px]">
      <LinkButton className="text-[12px] font-semibold" aria-label="Salin link pesan" disabled={!url} onClick={() => void copy()}>Salin</LinkButton>
      {canShare() && (
        <>
          <span aria-hidden="true" className="text-text-muted">·</span>
          <LinkButton className="text-[12px] font-semibold" aria-label="Bagikan link pesan" disabled={!url} onClick={() => void share()}>Bagikan</LinkButton>
        </>
      )}
    </span>
  )
}

function NoticeLine({ notice }: { notice?: Notice }) {
  if (!notice) return null
  return (
    <span role={notice.tone === 'danger' ? 'alert' : 'status'}
      className={`block text-[11px] ${notice.tone === 'success' ? 'text-success' : 'text-danger'}`}>
      {notice.text}
    </span>
  )
}

/** O3 → Umum, row "Link pesan": the link, Salin · Bagikan. */
export function OutletLinkValue({ outletId, outletName }: { outletId: string; outletName: string }) {
  const link = useOutletLink(outletId)
  const [notice, setNotice] = useState<Notice>()
  if (link.error && !link.data) return <span className="text-[12px] text-danger">{errorMessage(link.error)}</span>
  if (!link.data) return <span className="text-[12px] text-text-muted">Memuat…</span>
  const url = link.data.url
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="min-w-0 break-all text-[13px]" data-testid="outlet-link-url">
          {url ? url.replace(/^https?:\/\//, '') : 'Link pesan belum aktif.'}
        </span>
        <ShareActions url={url} outletName={outletName} onNotice={setNotice} />
      </div>
      <NoticeLine notice={notice} />
    </div>
  )
}

/** O2 Ringkasan: "Link pesan online" strip. Follows the header outlet filter; with
 * "Semua outlet" the strip has its own outlet choice (first outlet by default). */
export function OutletLinkStrip({ headerOutletId }: { headerOutletId: string }) {
  const { me, setOutletId } = useSession()
  const navigate = useNavigate()
  const [chosen, setChosen] = useState('')
  const outlets = me.outlets
  const outletId = headerOutletId || (outlets.some((o) => o.id === chosen) ? chosen : outlets[0]?.id ?? '')
  const outlet = outlets.find((o) => o.id === outletId)
  const link = useOutletLink(outletId)
  const [notice, setNotice] = useState<Notice>()
  if (!outlet) return null
  const url = link.data?.url ?? null

  return (
    <section aria-label="Link pesan online" className="rounded-lg border border-border bg-surface px-4 py-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1 basis-[240px]">
          <h2 className="text-[13px] font-semibold">Link pesan online</h2>
          <p className="text-[11px] text-text-muted">Tempel di bio Instagram, status WhatsApp, atau Google Maps.</p>
        </div>
        {!headerOutletId && outlets.length > 1 && (
          <Select aria-label="Outlet link pesan" className="h-8 w-full text-[12px] sm:w-[150px]" value={outletId}
            onChange={(e) => {
              setChosen(e.target.value)
              setNotice(undefined)
            }}>
            {outlets.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </Select>
        )}
        <div className="flex h-8 w-full min-w-0 items-center rounded-md border border-border bg-page px-2.5 text-[12px] sm:w-[240px]"
          data-testid="outlet-link-url">
          <span className="truncate">
            {link.data ? (url ? url.replace(/^https?:\/\//, '') : 'Link pesan belum aktif.')
              : link.error ? errorMessage(link.error) : 'Memuat…'}
          </span>
        </div>
        <ShareActions url={url} outletName={outlet.name} onNotice={setNotice} />
        <LinkButton className="text-[12px]" onClick={() => {
          setOutletId(outlet.id)
          navigate('/settings/tables')
        }}>Atur link & QR →</LinkButton>
      </div>
      <NoticeLine notice={notice} />
    </section>
  )
}
