/**
 * Real LcuClient, swapping in for lcu.mock.ts. Subscribes to the backend's
 * real /lcu WebSocket (backend/app/routers/lcu.py), which forwards
 * app.lcu.listener.LCUListener's real polling loop one push per tick.
 *
 * Real server messages, one JSON object per push:
 *   {"type": "idle"} -- client not running, no lockfile, or no active pick
 *     yet. Maps to `null` -- same "fall back to manual entry" state the
 *     mock already modeled for its own idle periods.
 *   {"type": "champ_select", champ_a, champ_b, role, rank} -- champ_b can
 *     itself be null (the real backend's index-matched opponent lookup,
 *     see listener.py's documented limitation, hasn't resolved yet) --
 *     only surfaced to the callback once both champions are known, since
 *     /advice needs both; a my-pick-only state is treated the same as
 *     `null` rather than firing a lookup that would 400.
 */
import { DEFAULT_ADVICE_BASE_URL } from './advice'

export type LcuChampSelectState = {
  champA: string
  champB: string
  role: string
  rank: string
} | null

export interface LcuClient {
  /** Subscribes to champ-select pushes; returns an unsubscribe function. */
  onChampSelect(callback: (state: LcuChampSelectState) => void): () => void
}

export const DEFAULT_LCU_WS_URL = `${DEFAULT_ADVICE_BASE_URL.replace(/^http/, 'ws')}/lcu`

type LcuServerMessage =
  | { type: 'idle' }
  | { type: 'champ_select'; champ_a: string; champ_b: string | null; role: string; rank: string }

export const lcuClient: LcuClient = {
  onChampSelect(callback) {
    const ws = new WebSocket(DEFAULT_LCU_WS_URL)

    ws.addEventListener('message', (event) => {
      const msg = JSON.parse(event.data as string) as LcuServerMessage
      if (msg.type === 'champ_select' && msg.champ_a && msg.champ_b) {
        callback({ champA: msg.champ_a, champB: msg.champ_b, role: msg.role, rank: msg.rank })
      } else {
        callback(null)
      }
    })
    // A closed/errored connection just means no more pushes -- same "fall
    // back to manual entry" state as an "idle" message, not a thrown error
    // (unlike ask.ts's connection failure, nothing here is user-initiated
    // or blocking, so there's no request to fail).
    ws.addEventListener('close', () => callback(null))
    ws.addEventListener('error', () => callback(null))

    return () => ws.close()
  },
}
