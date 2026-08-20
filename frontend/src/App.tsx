import { useEffect, useRef, useState } from 'react'
import './App.css'
import { MessageList } from './components/MessageList'
import { InputBox } from './components/InputBox'
import { fetchAdvice } from './api/advice'
import { fetchChampionNames } from './api/championList'
import { askClient } from './api/ask'
import { lcuClient, HOSTED_DEMO, type LcuChampSelectState } from './api/lcu'
import { parseSlashCommand } from './commands'
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
    // On the hosted demo, the backend can never see the visitor's local
    // League client (see lcu.ts's HOSTED_DEMO comment) -- say so once
    // instead of leaving auto-detect silently doing nothing forever.
    if (HOSTED_DEMO) {
      pushMessage({
        id: nextId(),
        kind: 'error',
        text: 'Champ-select auto-detect is not available in this hosted demo -- it requires running the backend locally alongside League. Use /advice to enter a matchup manually.',
      })
      return
    }

    // The real listener polls every ~1.5s and re-pushes the same state on
    // every tick while champ-select is ongoing (unlike the mock, which
    // fired once) -- only fire a real advice lookup when the state
    // actually changed, so this doesn't spam /advice or repeat the "Champ
    // select detected" message once per poll.
    const unsubscribe = lcuClient.onChampSelect((state) => {
      const changed =
        state?.champA !== champSelectRef.current?.champA ||
        state?.champB !== champSelectRef.current?.champB ||
        state?.role !== champSelectRef.current?.role ||
        state?.rank !== champSelectRef.current?.rank
      champSelectRef.current = state
      if (state && changed) void runAdviceLookup(state)
    })
    return unsubscribe
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function runAsk(question: string) {
    const state = champSelectRef.current
    const assistantId = nextId()
    pushMessage({ id: assistantId, kind: 'assistant-text', text: '', streaming: true })
    setBusy(true)
    try {
      for await (const chunk of askClient.ask({
        question,
        champA: state?.champA ?? 'unknown',
        champB: state?.champB ?? 'unknown',
        role: state?.role ?? 'unknown',
        rank: state?.rank ?? 'unknown',
      })) {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId && m.kind === 'assistant-text' ? { ...m, text: m.text + chunk } : m)),
        )
      }
    } catch (err) {
      pushMessage({
        id: nextId(),
        kind: 'error',
        text: err instanceof Error ? err.message : 'The /ask request failed unexpectedly.',
      })
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
      await runAsk(text)
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
          pushMessage({ id: nextId(), kind: 'help' })
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
          await runAsk(command.question)
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
