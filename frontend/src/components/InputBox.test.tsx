import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { InputBox } from './InputBox'

describe('InputBox keyboard navigation', () => {
  it('is reachable and submittable via keyboard alone (tab to input, type, Enter)', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(<InputBox onSubmit={onSubmit} />)

    await user.tab()
    expect(screen.getByLabelText(/ask a follow-up question/i)).toHaveFocus()

    await user.keyboard('How do I trade in lane?{Enter}')

    expect(onSubmit).toHaveBeenCalledWith('How do I trade in lane?')
  })

  it('the submit button is keyboard-focusable and disabled without text', () => {
    render(<InputBox onSubmit={vi.fn()} />)
    expect(screen.getByRole('button', { name: /send/i })).toBeDisabled()
  })
})

describe('InputBox rank/role dropdowns', () => {
  it('appends the selected rank and role to a /advice command that omits them', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(<InputBox onSubmit={onSubmit} />)

    await user.selectOptions(screen.getByLabelText(/rank/i), 'gold')
    await user.selectOptions(screen.getByLabelText(/role/i), 'jungle')
    await user.type(screen.getByLabelText(/ask a follow-up question/i), '/advice Aatrox vs Kayle')
    await user.click(screen.getByRole('button', { name: /send/i }))

    expect(onSubmit).toHaveBeenCalledWith('/advice Aatrox vs Kayle gold jungle')
  })

  it('does not double-append when the user already typed a rank and role', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(<InputBox onSubmit={onSubmit} />)

    await user.type(screen.getByLabelText(/ask a follow-up question/i), '/advice Aatrox vs Kayle emerald top')
    await user.click(screen.getByRole('button', { name: /send/i }))

    expect(onSubmit).toHaveBeenCalledWith('/advice Aatrox vs Kayle emerald top')
  })

  it('leaves plain (non-/advice) input untouched', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(<InputBox onSubmit={onSubmit} />)

    await user.type(screen.getByLabelText(/ask a follow-up question/i), 'How do I win the late game?')
    await user.click(screen.getByRole('button', { name: /send/i }))

    expect(onSubmit).toHaveBeenCalledWith('How do I win the late game?')
  })
})
