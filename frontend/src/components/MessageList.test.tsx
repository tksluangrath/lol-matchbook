import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MessageList } from './MessageList'
import type { ChatMessage } from '../chatTypes'

describe('MessageList ARIA roles', () => {
  it('exposes the conversation as a live region and each message as an article with a sender label', () => {
    const messages: ChatMessage[] = [
      { id: '1', kind: 'user', text: 'hello' },
      { id: '2', kind: 'assistant-text', text: 'hi there', streaming: false },
      { id: '3', kind: 'error', text: 'something broke' },
    ]
    render(<MessageList messages={messages} />)

    const log = screen.getByRole('log', { name: /conversation/i })
    expect(log).toHaveAttribute('aria-live', 'polite')

    expect(screen.getByRole('article', { name: /you/i })).toHaveTextContent('hello')
    expect(screen.getByRole('article', { name: /assistant/i })).toHaveTextContent('hi there')
    expect(screen.getByRole('alert')).toHaveTextContent('something broke')
  })
})
