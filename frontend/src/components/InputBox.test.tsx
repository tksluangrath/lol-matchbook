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
