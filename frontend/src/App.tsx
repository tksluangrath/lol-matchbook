import { useEffect, useRef, useState } from 'react'
import './App.css'
import { MessageList } from './components/MessageList'
import { InputBox } from './components/InputBox'
import { fetchAdvice } from './api/advice'
import { mockAskClient } from './api/ask.mock'
import { mockLcuClient, type LcuChampSelectState } from './api/lcu.mock'
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

  async function runAdviceLookup(state: NonNullable<LcuChampSelectState>) {
    pushMessage({
      id: nextId(),
      kind: 'user',
      text: `Champ select detected: ${state.champA} vs ${state.champB} (${state.role}, ${state.rank})`,
    })
    try {
      const result = await fetchAdvice({ champA: state.champA, champB: state.champB, role: state.role, rank: state.rank })
      pushMessage({ id: nextId(), kind: 'advice', champA: state.champA, champB: state.champB, result })
    } catch {
      pushMessage({ id: nextId(), kind: 'error', text: 'Could not reach the advice service. Is the backend running?' })
    }
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

  async function handleAsk(question: string) {
    pushMessage({ id: nextId(), kind: 'user', text: question })
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
        <InputBox onSubmit={(text) => void handleAsk(text)} disabled={busy} />
      </main>
    </div>
  )
}
