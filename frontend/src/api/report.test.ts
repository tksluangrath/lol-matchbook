import { afterEach, describe, expect, it, vi } from 'vitest'
import { submitReport } from './report'

describe('submitReport', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('POSTs a real matchup-mistake report with champ-select context included', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', mockFetch)

    await submitReport({
      category: 'matchup_mistake',
      message: 'this feels wrong',
      champA: 'Aatrox',
      champB: 'Kayle',
      role: 'top',
      rank: 'emerald',
    })

    expect(mockFetch).toHaveBeenCalledWith('http://127.0.0.1:8000/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        category: 'matchup_mistake',
        message: 'this feels wrong',
        champ_a: 'Aatrox',
        champ_b: 'Kayle',
        role: 'top',
        rank: 'emerald',
      }),
    })
  })

  it('POSTs a real bug report with null champ-select fields when none is active', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', mockFetch)

    await submitReport({ category: 'bug', message: 'the dropdown reset' })

    const body = JSON.parse((mockFetch.mock.calls[0][1] as RequestInit).body as string)
    expect(body).toEqual({
      category: 'bug',
      message: 'the dropdown reset',
      champ_a: null,
      champ_b: null,
      role: null,
      rank: null,
    })
  })

  it('throws a real, user-facing error when the backend rejects the request', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: false })
    vi.stubGlobal('fetch', mockFetch)

    await expect(submitReport({ category: 'bug', message: 'x' })).rejects.toThrow(
      'Could not submit the report. Is the backend running?',
    )
  })
})
