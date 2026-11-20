import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { SupabaseClient } from '@supabase/supabase-js'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Role } from '../app/nav'
import { fakeSession } from '../test/fakes'
import { useSession } from '../app/session'
import { AuthGate } from './AuthGate'

function signedInSupabase() {
  return {
    auth: {
      getSession: async () => ({ data: { session: { access_token: 't' } } }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
      signOut: vi.fn(async () => ({ error: null })),
    },
  } as unknown as SupabaseClient
}

function renderGate(role: Role, area: Role, supabase = signedInSupabase()) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(fakeSession(role).me), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  })))
  return render(
    <AuthGate supabase={supabase} apiBaseUrl="http://api.test" area={area}>
      <p>shell</p>
    </AuthGate>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  window.history.replaceState(null, '', '/')
  window.localStorage.clear()
})

describe('AuthGate URL areas (owner at /, staff at /admin)', () => {
  it('lets each role into its own area', async () => {
    renderGate('staff', 'staff')
    expect(await screen.findByText('shell')).toBeInTheDocument()
  })

  it('points a staff account opened at the owner URL to /admin', async () => {
    renderGate('staff', 'owner')
    expect(await screen.findByRole('heading', { name: 'Ini akun staf' })).toBeInTheDocument()
    expect(screen.getByText(/terdaftar sebagai staf\. Silakan buka halaman staf/)).toBeInTheDocument()
    expect(screen.queryByText('shell')).not.toBeInTheDocument()
  })

  it('signs out of this area locally before opening the own area, on the same page', async () => {
    window.history.replaceState(null, '', '/stock')
    const assign = vi.fn()
    vi.spyOn(window, 'location', 'get').mockReturnValue({ ...window.location, pathname: '/stock', assign })
    const supabase = signedInSupabase()
    renderGate('staff', 'owner', supabase)
    fireEvent.click(await screen.findByRole('button', { name: /Buka halaman staf/ }))
    await waitFor(() => expect(assign).toHaveBeenCalledWith('/admin/stock'))
    expect(supabase.auth.signOut).toHaveBeenCalledWith({ scope: 'local' })
  })

  it('sends an owner account opened at /admin to the owner home when the page is staff-only', async () => {
    const assign = vi.fn()
    vi.spyOn(window, 'location', 'get').mockReturnValue({ ...window.location, pathname: '/admin/my-attendance', assign })
    renderGate('owner', 'staff')
    expect(await screen.findByRole('heading', { name: 'Ini akun owner' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Buka halaman owner/ }))
    await waitFor(() => expect(assign).toHaveBeenCalledWith('/dashboard'))
  })

  it('"Keluar" signs out locally and shows the login card of this area', async () => {
    const supabase = signedInSupabase()
    renderGate('staff', 'owner', supabase)
    fireEvent.click(await screen.findByRole('button', { name: 'Keluar' }))
    expect(await screen.findByRole('button', { name: /Masuk/ })).toBeInTheDocument()
    expect(supabase.auth.signOut).toHaveBeenCalledWith({ scope: 'local' })
  })

  it('remembers the selected outlet per area', async () => {
    window.localStorage.setItem('sme-pos.outlet', 'owner-outlet')
    window.localStorage.setItem('sme-pos.outlet.staff', 'staff-outlet')
    let seen: string | null | undefined
    function Probe() {
      seen = useSession().outlet?.id
      return null
    }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      ...fakeSession('staff').me,
      outlets: [
        { ...fakeSession('staff').me.outlets[0], id: 'owner-outlet' },
        { ...fakeSession('staff').me.outlets[0], id: 'staff-outlet' },
      ],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
    render(
      <AuthGate supabase={signedInSupabase()} apiBaseUrl="http://api.test" area="staff">
        <Probe />
      </AuthGate>,
    )
    await waitFor(() => expect(seen).toBe('staff-outlet'))
  })
})
