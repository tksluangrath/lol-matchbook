import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MessageList } from './MessageList'
import { HELP_COMMANDS } from '../commands'
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

describe('MessageList assistant-text rendering', () => {
  it('renders the finished response as real sentence bullets, not a run-on paragraph', () => {
    const messages: ChatMessage[] = [
      {
        id: '1',
        kind: 'assistant-text',
        text: 'Play safe early. Look for picks around mid game. Group for objectives late.',
        streaming: false,
      },
    ]
    render(<MessageList messages={messages} />)

    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(3)
    expect(items[0]).toHaveTextContent('Play safe early.')
    expect(items[2]).toHaveTextContent('Group for objectives late.')
  })

  it('renders as plain growing text while still streaming (sentences are incomplete)', () => {
    const messages: ChatMessage[] = [
      { id: '1', kind: 'assistant-text', text: 'Play safe ea', streaming: true },
    ]
    render(<MessageList messages={messages} />)

    expect(screen.queryByRole('list')).not.toBeInTheDocument()
    expect(screen.getByRole('article', { name: /assistant/i })).toHaveTextContent('Play safe ea')
  })
})

describe('MessageList /help rendering', () => {
  it('renders /help as a real <ul>/<li> list, one item per real command -- not a newline-joined string a plain <article> would collapse', () => {
    const messages: ChatMessage[] = [{ id: '1', kind: 'help' }]
    render(<MessageList messages={messages} />)

    const list = screen.getByRole('list')
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(HELP_COMMANDS.length)
    for (const { command, description } of HELP_COMMANDS) {
      expect(list).toHaveTextContent(command)
      expect(list).toHaveTextContent(description)
    }
  })
})
