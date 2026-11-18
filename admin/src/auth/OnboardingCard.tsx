// Wireframe O1 · "Buat profil bisnis" (Langkah 1: bisnis, Langkah 2: outlet pertama).
// POST /api/v1/owner/onboarding (T-010, T-011).
import { useState, type FormEvent } from 'react'
import { errorMessage, type Api } from '../lib/api'
import { TIMEZONE_LABEL, type Timezone } from '../lib/types'
import { Alert, Button, Card, Field, LinkButton, Select, TextInput } from '../ui/kit'

export function OnboardingCard({ api, onCreated, onSignOut }: {
  api: Api
  onCreated: () => Promise<void>
  onSignOut: () => void
}) {
  const [business, setBusiness] = useState({ name: '', type: 'cafe' as 'cafe' | 'restaurant' })
  const [outlet, setOutlet] = useState({
    name: '',
    timezone: 'Asia/Jakarta' as Timezone,
    address: '',
    whatsapp_phone: '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(undefined)
    try {
      await api.post('/owner/onboarding', {
        business: { name: business.name.trim(), type: business.type },
        outlet: {
          name: outlet.name.trim(),
          timezone: outlet.timezone,
          address: outlet.address.trim() || null,
          whatsapp_phone: outlet.whatsapp_phone.replace(/[\s-]/g, '') || null,
        },
      })
      await onCreated()
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  const radio = 'flex items-center gap-2 text-[13px]'
  return (
    <Card>
      <p className="text-[11px] text-text-muted">Langkah 1 dari 2 · Buat bisnis</p>
      <h1 className="mb-4 text-[18px] font-bold">Buat profil bisnis</h1>
      <form onSubmit={submit} noValidate>
        <Field label="Nama bisnis" htmlFor="biz-name">
          <TextInput id="biz-name" placeholder="Kopi Senja" value={business.name}
            onChange={(e) => setBusiness({ ...business, name: e.target.value })} />
        </Field>
        <fieldset className="mb-4">
          <legend className="mb-1 text-[13px] font-semibold">Tipe bisnis</legend>
          <div className="space-y-1">
            <label className={`${radio} text-text-muted`}>
              <input type="radio" name="biz-type" disabled /> Dropshipper <span className="text-[11px]">Segera (Phase 3)</span>
            </label>
            {(['cafe', 'restaurant'] as const).map((t) => (
              <label key={t} className={radio}>
                <input type="radio" name="biz-type" checked={business.type === t}
                  onChange={() => setBusiness({ ...business, type: t })} />
                {t === 'cafe' ? 'Cafe' : 'Restaurant'}
              </label>
            ))}
          </div>
        </fieldset>

        <p className="mb-2 border-t border-border pt-3 text-[13px] font-semibold">Langkah 2 · Outlet pertama</p>
        <Field label="Nama outlet" htmlFor="outlet-name">
          <TextInput id="outlet-name" placeholder="Bandung – Dago" value={outlet.name}
            onChange={(e) => setOutlet({ ...outlet, name: e.target.value })} />
        </Field>
        <Field label="Zona waktu" htmlFor="outlet-tz">
          <Select id="outlet-tz" value={outlet.timezone}
            onChange={(e) => setOutlet({ ...outlet, timezone: e.target.value as Timezone })}>
            {Object.entries(TIMEZONE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </Select>
        </Field>
        <Field label="Alamat" htmlFor="outlet-address">
          <TextInput id="outlet-address" placeholder="Jl. Ir. H. Juanda No. …" value={outlet.address}
            onChange={(e) => setOutlet({ ...outlet, address: e.target.value })} />
        </Field>
        <Field label="Nomor WhatsApp outlet" htmlFor="outlet-wa">
          <TextInput id="outlet-wa" inputMode="tel" placeholder="+62 8xx xxxx xxxx" value={outlet.whatsapp_phone}
            onChange={(e) => setOutlet({ ...outlet, whatsapp_phone: e.target.value })} />
        </Field>
        <div className="mb-3">
          <Alert tone="info">ℹ  Sample menu, foto, harga & add-on otomatis ditambahkan dan bisa diedit.</Alert>
        </div>
        {error && <div className="mb-3"><Alert>{error}</Alert></div>}
        <Button type="submit" variant="action" className="w-full"
          disabled={busy || !business.name.trim() || !outlet.name.trim()}>
          {busy ? 'Membuat…' : 'Buat bisnis'}
        </Button>
      </form>
      <LinkButton className="mt-3" onClick={onSignOut}>Keluar</LinkButton>
    </Card>
  )
}
