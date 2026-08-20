import { afterEach, describe, expect, it, vi } from 'vitest'

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  url: string
  listeners: Record<string, ((event: unknown) => void)[]> = {}
  closed = false
  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }
  addEventListener(type: string, cb: (event: unknown) => void) {
    ;(this.listeners[type] ??= []).push(cb)
  }
  close() {
    this.closed = true
  }
  emitMessage(data: unknown) {
    for (const cb of this.listeners.message ?? []) cb({ data: JSON.stringify(data) })
  }
}

describe('lcuClient', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.resetModules()
    FakeWebSocket.instances = []
  })

  it('does not attempt a WebSocket connection when VITE_HOSTED_DEMO is set', async () => {
    vi.stubEnv('VITE_HOSTED_DEMO', 'true')
    vi.stubGlobal('WebSocket', FakeWebSocket)
    const { lcuClient } = await import('./lcu')

    const unsubscribe = lcuClient.onChampSelect(vi.fn())

    expect(FakeWebSocket.instances).toHaveLength(0)
    expect(() => unsubscribe()).not.toThrow()
  })

  it('maps a real "idle" push to null', async () => {
    vi.stubGlobal('WebSocket', FakeWebSocket)
    const { lcuClient } = await import('./lcu')

    const callback = vi.fn()
    lcuClient.onChampSelect(callback)
    FakeWebSocket.instances[0].emitMessage({ type: 'idle' })

    expect(callback).toHaveBeenCalledWith(null)
  })

  it('maps a real "champ_select" push with both champions known to a real state', async () => {
    vi.stubGlobal('WebSocket', FakeWebSocket)
    const { lcuClient } = await import('./lcu')

    const callback = vi.fn()
    lcuClient.onChampSelect(callback)
    FakeWebSocket.instances[0].emitMessage({
      type: 'champ_select', champ_a: 'Aatrox', champ_b: 'Kayle', role: 'top', rank: 'emerald',
    })

    expect(callback).toHaveBeenCalledWith({ champA: 'Aatrox', champB: 'Kayle', role: 'top', rank: 'emerald' })
  })

  it('treats a real "champ_select" push with an unresolved opponent (champ_b null) the same as idle', async () => {
    vi.stubGlobal('WebSocket', FakeWebSocket)
    const { lcuClient } = await import('./lcu')

    const callback = vi.fn()
    lcuClient.onChampSelect(callback)
    FakeWebSocket.instances[0].emitMessage({
      type: 'champ_select', champ_a: 'Aatrox', champ_b: null, role: 'top', rank: 'emerald',
    })

    expect(callback).toHaveBeenCalledWith(null)
  })

  it('closes the real WebSocket when unsubscribed', async () => {
    vi.stubGlobal('WebSocket', FakeWebSocket)
    const { lcuClient } = await import('./lcu')

    const unsubscribe = lcuClient.onChampSelect(vi.fn())
    unsubscribe()

    expect(FakeWebSocket.instances[0].closed).toBe(true)
  })
})
