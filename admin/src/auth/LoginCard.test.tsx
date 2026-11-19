import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { SupabaseClient } from '@supabase/supabase-js'
import { describe, expect, it } from 'vitest'
import { LoginCard } from './LoginCard'

describe('Masuk', () => {
  it('lets the user show and hide the password they typed', async () => {
    render(<LoginCard supabase={{} as SupabaseClient} />)
    const field = screen.getByLabelText('Password')
    await userEvent.type(field, 'rahasia123')
    expect(field).toHaveAttribute('type', 'password')

    await userEvent.click(screen.getByRole('button', { name: 'Lihat password' }))
    expect(field).toHaveAttribute('type', 'text')
    expect(field).toHaveValue('rahasia123')

    await userEvent.click(screen.getByRole('button', { name: 'Sembunyikan password' }))
    expect(field).toHaveAttribute('type', 'password')
  })
})
