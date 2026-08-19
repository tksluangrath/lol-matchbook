import { afterEach, describe, expect, it, vi } from 'vitest'

// A real WebSocket connection depends on whatever's actually listening on
// this machine's port 8000 (a real dev backend may or may not be up) --
// stubbing the constructor makes "was a connection even attempted" a
// deterministic assertion instead of an environment-dependent network call.
class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  url: string
  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }
  addEventListener() {}
  close() {}
}

describe('askClient hosted-mode gating', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.resetModules()
    FakeWebSocket.instances = []
  })

  it('throws a real, user-facing error before attempting a WebSocket connection when VITE_HOSTED_DEMO is set', async () => {
    vi.stubEnv('VITE_HOSTED_DEMO', 'true')
    vi.stubGlobal('WebSocket', FakeWebSocket)
    const { askClient } = await import('./ask')

    const generator = askClient.ask({ question: 'q', champA: 'Ahri', champB: 'Sylas', role: 'middle', rank: 'emerald' })
    await expect(generator.next()).rejects.toThrow(/not available in this hosted demo/i)
    expect(FakeWebSocket.instances).toHaveLength(0)
  })

  it('does not gate /ask when VITE_HOSTED_DEMO is unset (local dev unchanged)', async () => {
    vi.stubEnv('VITE_HOSTED_DEMO', '')
    vi.stubGlobal('WebSocket', FakeWebSocket)
    const { askClient, DEFAULT_ASK_WS_URL } = await import('./ask')

    const generator = askClient.ask({ question: 'q', champA: 'Ahri', champB: 'Sylas', role: 'middle', rank: 'emerald' })
    // FakeWebSocket never dispatches 'open', so the real code hangs
    // awaiting it -- don't await generator.next() to completion, just
    // confirm the real connection attempt happened with the real URL.
    void generator.next()
    await Promise.resolve()
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(FakeWebSocket.instances[0].url).toBe(DEFAULT_ASK_WS_URL)
  })
})
