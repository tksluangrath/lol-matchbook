/**
 * The LCU (League client) auto-detection listener is unbuilt (per
 * docs/system-design.md: an internal backend listener that reads the
 * lockfile, polls the League client's local `GET /lol-champ-select/v1/session`,
 * and pushes champ_a/champ_b/rank to the UI). This file mocks that push
 * behind the LcuClient interface.
 *
 * To swap in the real implementation later: write a new module (e.g.
 * lcu.ts) exporting an LcuClient that subscribes to the backend's real push
 * channel (e.g. a WebSocket the backend opens once it detects a champ-select
 * session) and calls the same callback shape. Point the one import in
 * App.tsx at it instead of this file. No other app code changes.
 */

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

// ponytail: fires one canned champ-select state after a fixed delay to
// simulate the League client locking in picks -- real listener instead
// polls continuously and fires on every pick/ban change.
export const mockLcuClient: LcuClient = {
  onChampSelect(callback) {
    const timer = setTimeout(() => {
      callback({ champA: 'Aatrox', champB: 'Kayle', role: 'top', rank: 'emerald' })
    }, 1200)
    return () => clearTimeout(timer)
  },
}
