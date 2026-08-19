/**
 * Real client for POST /ask (backend/app/routers/ask.py), a WebSocket, not
 * a streamed HTTP response as ask.mock.ts's docstring guessed before the
 * real endpoint existed -- the wire shape below is read directly from the
 * real handler and docs/decisions/phase4-ask-endpoint.md, not assumed to
 * match the mock.
 *
 * Real request: {question, champ_a, champ_b, role, rank} -- role is
 * REQUIRED (app/routers/ask.py's REQUIRED_FIELDS), even though
 * docs/system-design.md's original contract omitted it; the real handler
 * rejects a request missing it. The mock's AskRequest never carried role
 * at all -- fixed here, not silently dropped.
 *
 * Real server messages, one JSON object per WebSocket message:
 *   {"type": "chunk", "text": "..."} -- zero or more, in order
 *   {"type": "warning", "message": "..."} -- zero or one, after the last
 *     chunk: the real fact-grounding check (same one precompute.py gates
 *     writes on) flagged an unverified claim in the response. Non-fatal --
 *     the already-streamed answer is still shown, flagged rather than
 *     silently dropped or treated as a stream-ending error.
 *   {"type": "done"}                 -- exactly one, ends the stream
 *   {"type": "error", "message": "..."} -- terminal, no further messages
 */
export type AskRequest = {
  question: string
  champA: string
  champB: string
  role: string
  rank: string
}

export interface AskClient {
  /** Yields response text incrementally, matching the real streamed shape. */
  ask(req: AskRequest): AsyncGenerator<string, void, unknown>
}

// Derived from the same VITE_API_URL as advice.ts's DEFAULT_ADVICE_BASE_URL
// -- one env var for a hosted deployment to set, not two, since it's the
// same backend origin either way. http(s) -> ws(s): the leading "http" in
// "https://" is also replaced, correctly producing "wss://" (the trailing
// "s" is untouched by the replace, so "https" -> "wss", not "wshttps").
import { DEFAULT_ADVICE_BASE_URL } from './advice'

export const DEFAULT_ASK_WS_URL = `${DEFAULT_ADVICE_BASE_URL.replace(/^http/, 'ws')}/ask`

type AskServerMessage =
  | { type: 'chunk'; text: string }
  | { type: 'warning'; message: string }
  | { type: 'done' }
  | { type: 'error'; message: string }

// Set on the hosted Render Static Site deploy (free-tier backend can't run
// real quantized inference) -- unset locally, so `npm run dev`'s /ask
// behavior is unchanged. Thrown before any WebSocket is attempted; App.tsx's
// existing runAsk() catch block already renders a thrown Error as a chat
// error message, so no separate UI-gating code is needed for this to work.
const HOSTED_DEMO = Boolean(import.meta.env.VITE_HOSTED_DEMO)

export const askClient: AskClient = {
  async *ask(req: AskRequest) {
    if (HOSTED_DEMO) {
      throw new Error('/ask is not available in this hosted demo -- try /advice for a precomputed matchup instead.')
    }

    const ws = new WebSocket(DEFAULT_ASK_WS_URL)

    // Bridges WebSocket's event callbacks into an async queue so the
    // generator can `await` the next message instead of nesting callbacks.
    const queue: AskServerMessage[] = []
    let resolveNext: (() => void) | null = null
    let closedUnexpectedly = false

    function wake() {
      resolveNext?.()
      resolveNext = null
    }

    ws.addEventListener('message', (event) => {
      queue.push(JSON.parse(event.data as string) as AskServerMessage)
      wake()
    })
    ws.addEventListener('close', (event) => {
      if (!event.wasClean) closedUnexpectedly = true
      wake()
    })
    ws.addEventListener('error', () => {
      closedUnexpectedly = true
      wake()
    })

    await new Promise<void>((resolve, reject) => {
      ws.addEventListener('open', () => resolve(), { once: true })
      ws.addEventListener('error', () => reject(new Error('Could not connect to the /ask service.')), { once: true })
    })

    ws.send(
      JSON.stringify({
        question: req.question,
        champ_a: req.champA,
        champ_b: req.champB,
        role: req.role,
        rank: req.rank,
      }),
    )

    try {
      while (true) {
        if (queue.length === 0) {
          if (closedUnexpectedly) {
            throw new Error('Lost connection to the /ask service before it finished responding.')
          }
          await new Promise<void>((resolve) => {
            resolveNext = resolve
          })
          continue
        }
        const msg = queue.shift() as AskServerMessage
        if (msg.type === 'chunk') {
          yield msg.text
        } else if (msg.type === 'warning') {
          yield `\n\n⚠️ ${msg.message}`
        } else if (msg.type === 'done') {
          return
        } else {
          throw new Error(msg.message)
        }
      }
    } finally {
      ws.close()
    }
  },
}
