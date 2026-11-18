import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { SupabaseClient } from '@supabase/supabase-js'
import { describe, expect, it } from 'vitest'
import { SetPasswordCard } from './SetPasswordCard'

describe('Atur password', () => {
  it('lets the user show and hide the password they typed', async () => {
    render(<SetPasswordCard supabase={{} as SupabaseClient} onDone={() => {}} />)
    const field = screen.getByLabelText('Password')
    await userEvent.type(field, 'rahasia123')
    expect(field).toHaveAttribute('type', 'password')

    const [toggle] = screen.getAllByRole('button', { name: 'Lihat' })
    await userEvent.click(toggle)
    expect(field).toHaveAttribute('type', 'text')
    expect(field).toHaveValue('rahasia123')
    expect(screen.getByLabelText('Ulangi password')).toHaveAttribute('type', 'password')

    await userEvent.click(screen.getByRole('button', { name: 'Sembunyikan' }))
    expect(field).toHaveAttribute('type', 'password')
  })
})
