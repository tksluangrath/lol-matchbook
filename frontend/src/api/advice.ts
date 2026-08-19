/**
 * Real client for GET /advice, the champ-select path (backend/app/routers/advice.py).
 *
 * The endpoint returns one of five real response shapes (confirmed by reading
 * advice.py and its integration tests -- test_advice_endpoint.py and
 * test_lazy_tier_fallback.py -- not assumed):
 *   1. Exact precomputed hit   -> 200 { early, mid, late }
 *   2. Wider-rank-bracket hit  -> 200 { early, mid, late, source: "wider_rank_fallback" }
 *   3. Abstention              -> 200 { status: "abstention", reason }
 *      (can happen at the exact rank OR discovered via the wider-rank lookup --
 *      same shape either way, per advice.py's `if "status" in wider: return wider`)
 *   4. Archetype fallback      -> 200 { status: "archetype_fallback", source: "archetype_fallback",
 *                                       champ_a_blurb, champ_b_blurb }
 *   5. Not precomputed         -> 404 { status: "not_precomputed" }
 *
 * classifyAdviceResponse() is a pure function so the 5-way branching is
 * testable without a network call.
 */

export type AdviceRequest = {
  champA: string
  champB: string
  role: string
  rank: string
}

export type AdvicePhaseText = {
  early: string
  mid: string
  late: string
}

export type AdviceResult =
  | { kind: 'hit'; phases: AdvicePhaseText }
  | { kind: 'wider_rank_fallback'; phases: AdvicePhaseText }
  | { kind: 'abstention'; reason: string }
  | { kind: 'archetype_fallback'; champABlurb: string; champBBlurb: string }
  | { kind: 'not_precomputed' }

// VITE_API_URL is the one env var a hosted deployment (e.g. a Render Static
// Site pointed at a separately-deployed backend) needs to set -- Vite only
// exposes client-code env vars prefixed VITE_. Falls back to local dev's
// real backend address when unset, so nothing changes for `npm run dev`.
export const DEFAULT_ADVICE_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

export function classifyAdviceResponse(status: number, body: Record<string, unknown>): AdviceResult {
  if (status === 404 || body.status === 'not_precomputed') {
    return { kind: 'not_precomputed' }
  }
  if (body.status === 'abstention') {
    return { kind: 'abstention', reason: String(body.reason ?? '') }
  }
  if (body.status === 'archetype_fallback') {
    return {
      kind: 'archetype_fallback',
      champABlurb: String(body.champ_a_blurb ?? ''),
      champBBlurb: String(body.champ_b_blurb ?? ''),
    }
  }
  const phases: AdvicePhaseText = {
    early: String(body.early ?? ''),
    mid: String(body.mid ?? ''),
    late: String(body.late ?? ''),
  }
  if (body.source === 'wider_rank_fallback') {
    return { kind: 'wider_rank_fallback', phases }
  }
  return { kind: 'hit', phases }
}

export async function fetchAdvice(
  req: AdviceRequest,
  baseUrl: string = DEFAULT_ADVICE_BASE_URL,
): Promise<AdviceResult> {
  const params = new URLSearchParams({
    champ_a: req.champA,
    champ_b: req.champB,
    role: req.role,
    rank: req.rank,
  })
  const res = await fetch(`${baseUrl}/advice?${params.toString()}`)
  const body = await res.json()
  return classifyAdviceResponse(res.status, body)
}
