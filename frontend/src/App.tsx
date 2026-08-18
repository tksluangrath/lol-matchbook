import { useEffect, useRef, useState } from 'react'
import './App.css'
import { MessageList } from './components/MessageList'
import { InputBox } from './components/InputBox'
import { fetchAdvice } from './api/advice'
import { fetchChampionNames } from './api/championList'
import { mockAskClient } from './api/ask.mock'
import { mockLcuClient, type LcuChampSelectState } from './api/lcu.mock'
import { HELP_TEXT, parseSlashCommand } from './commands'
import type { ChatMessage } from './chatTypes'

let idCounter = 0
function nextId(): string {
  idCounter += 1
  return `msg-${idCounter}`
}

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [busy, setBusy] = useState(false)
  const champSelectRef = useRef<LcuChampSelectState>(null)

  function pushMessage(message: ChatMessage) {
    setMessages((prev) => [...prev, message])
  }

  // Shared by the LCU auto-detect path and the /advice command -- both real
  // /advice callers render through this one fetch+classify+render path
  // rather than each having their own.
  async function fetchAndRenderAdvice(champA: string, champB: string, role: string, rank: string) {
    try {
      const result = await fetchAdvice({ champA, champB, role, rank })
      pushMessage({ id: nextId(), kind: 'advice', champA, champB, result })
    } catch {
      pushMessage({ id: nextId(), kind: 'error', text: 'Could not reach the advice service. Is the backend running?' })
    }
  }

  async function runAdviceLookup(state: NonNullable<LcuChampSelectState>) {
    pushMessage({
      id: nextId(),
      kind: 'user',
      text: `Champ select detected: ${state.champA} vs ${state.champB} (${state.role}, ${state.rank})`,
    })
    await fetchAndRenderAdvice(state.champA, state.champB, state.role, state.rank)
  }

  useEffect(() => {
    // LCU auto-detect: swap mockLcuClient for a real implementation in
    // src/api/lcu.ts once the backend push exists (see lcu.mock.ts).
    const unsubscribe = mockLcuClient.onChampSelect((state) => {
      champSelectRef.current = state
      if (state) void runAdviceLookup(state)
    })
    return unsubscribe
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function runAskMock(question: string) {
    const state = champSelectRef.current
    const assistantId = nextId()
    pushMessage({ id: assistantId, kind: 'assistant-text', text: '', streaming: true })
    setBusy(true)
    try {
      // /ask is unbuilt server-side: mockAskClient stands in behind the
      // AskClient interface (src/api/ask.mock.ts) until it's real.
      for await (const chunk of mockAskClient.ask({
        question,
        champA: state?.champA ?? 'unknown',
        champB: state?.champB ?? 'unknown',
        rank: state?.rank ?? 'unknown',
      })) {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId && m.kind === 'assistant-text' ? { ...m, text: m.text + chunk } : m)),
        )
      }
    } finally {
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId && m.kind === 'assistant-text' ? { ...m, streaming: false } : m)),
      )
      setBusy(false)
    }
  }

  async function handleSubmit(text: string) {
    pushMessage({ id: nextId(), kind: 'user', text })

    if (!text.startsWith('/')) {
      await runAskMock(text)
      return
    }

    setBusy(true)
    try {
      // Only /advice needs the real champion list -- skip the network call
      // for /help, /ask, and anything else (the fetch is cached after the
      // first real /advice command anyway, via championList.ts).
      const commandWord = text.trim().slice(1).split(/\s+/)[0]?.toLowerCase()
      const championNames = commandWord === 'advice' ? await fetchChampionNames() : []
      const command = parseSlashCommand(text, championNames)
      switch (command.kind) {
        case 'help':
          pushMessage({ id: nextId(), kind: 'assistant-text', text: HELP_TEXT, streaming: false })
          return
        case 'advice_incomplete':
          pushMessage({ id: nextId(), kind: 'error', text: command.message })
          return
        case 'unrecognized':
          pushMessage({
            id: nextId(),
            kind: 'error',
            text: `"${command.raw}" isn't a recognized command. Try /help.`,
          })
          return
        case 'advice':
          await fetchAndRenderAdvice(command.champA, command.champB, command.role, command.rank)
          return
        case 'ask':
          await runAskMock(command.question)
          return
      }
    } catch {
      pushMessage({
        id: nextId(),
        kind: 'error',
        text: 'Could not load the champion list, so /advice can\'t validate names right now. Is the network reachable?',
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__inner">
          <span className="hex-mark" aria-hidden="true" />
          <div className="app-header__titles">
            <p className="app-header__eyebrow">Lane Intelligence</p>
            <h1>Matchup Copilot</h1>
          </div>
        </div>
      </header>
      <main className="app-main">
        <MessageList messages={messages} />
        <InputBox onSubmit={(text) => void handleSubmit(text)} disabled={busy} />
      </main>
    </div>
  )
}
