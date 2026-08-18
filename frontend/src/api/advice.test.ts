import { describe, expect, it, vi, afterEach } from 'vitest'
import { classifyAdviceResponse, fetchAdvice } from './advice'

describe('classifyAdviceResponse (pure, matches the real GET /advice contract)', () => {
  it('classifies a precomputed hit', () => {
    const result = classifyAdviceResponse(200, { early: 'e', mid: 'm', late: 'l' })
    expect(result).toEqual({ kind: 'hit', phases: { early: 'e', mid: 'm', late: 'l' } })
  })

  it('classifies a wider-rank-bracket fallback', () => {
    const result = classifyAdviceResponse(200, { early: 'e', mid: 'm', late: 'l', source: 'wider_rank_fallback' })
    expect(result).toEqual({ kind: 'wider_rank_fallback', phases: { early: 'e', mid: 'm', late: 'l' } })
  })

  it('classifies an abstention', () => {
    const result = classifyAdviceResponse(200, { status: 'abstention', reason: 'not enough data at this rank' })
    expect(result).toEqual({ kind: 'abstention', reason: 'not enough data at this rank' })
  })

  it('classifies an abstention reached via the wider-rank lookup (same shape, no source field)', () => {
    const result = classifyAdviceResponse(200, { status: 'abstention', reason: 'not enough data at this rank' })
    expect(result.kind).toBe('abstention')
  })

  it('classifies an archetype fallback', () => {
    const result = classifyAdviceResponse(200, {
      status: 'archetype_fallback',
      source: 'archetype_fallback',
      champ_a_blurb: 'blurb a',
      champ_b_blurb: 'blurb b',
    })
    expect(result).toEqual({ kind: 'archetype_fallback', champABlurb: 'blurb a', champBBlurb: 'blurb b' })
  })

  it('classifies a 404 not-precomputed response', () => {
    const result = classifyAdviceResponse(404, { status: 'not_precomputed' })
    expect(result).toEqual({ kind: 'not_precomputed' })
  })
})

describe('fetchAdvice', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('builds the real query params and classifies the response', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({ early: 'e', mid: 'm', late: 'l' }),
    })
    vi.stubGlobal('fetch', mockFetch)

    const result = await fetchAdvice({ champA: 'Ashe', champB: 'Draven', role: 'bottom', rank: 'emerald' })

    expect(mockFetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/advice?champ_a=Ashe&champ_b=Draven&role=bottom&rank=emerald',
    )
    expect(result.kind).toBe('hit')
  })
})
