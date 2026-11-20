import { render, screen } from '@testing-library/react'
import type { SupabaseClient } from '@supabase/supabase-js'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Role } from '../app/nav'
import { fakeSession } from '../test/fakes'
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

function renderGate(role: Role, area: Role) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(fakeSession(role).me), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  })))
  return render(
    <AuthGate supabase={signedInSupabase()} apiBaseUrl="http://api.test" area={area}>
      <p>shell</p>
    </AuthGate>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('AuthGate URL areas (owner at /, staff at /admin)', () => {
  it('lets each role into its own area', async () => {
    renderGate('staff', 'staff')
    expect(await screen.findByText('shell')).toBeInTheDocument()
  })

  it('points a staff account opened at the owner URL to /admin', async () => {
    renderGate('staff', 'owner')
    expect(await screen.findByRole('heading', { name: 'Ini akun staf' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Buka halaman staf/ })).toHaveAttribute('href', '/admin/orders')
    expect(screen.queryByText('shell')).not.toBeInTheDocument()
  })

  it('points an owner account opened at /admin back to the owner URL', async () => {
    renderGate('owner', 'staff')
    expect(await screen.findByRole('heading', { name: 'Ini akun owner' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Buka halaman owner/ })).toHaveAttribute('href', '/dashboard')
  })
})
