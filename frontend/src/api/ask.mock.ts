/**
 * POST /ask is unbuilt on the backend (per docs/system-design.md's contract:
 * `POST /ask -> { question, champ_a, champ_b, rank } -> streamed text`, and
 * the stubbed status called out in this task). This file mocks it behind the
 * AskClient interface so the UI can be built and tested against the real
 * eventual shape now.
 *
 * To swap in the real implementation later: write a new module (e.g.
 * ask.ts) exporting an AskClient whose ask() reads a real streamed HTTP
 * response (fetch + ReadableStream, or SSE) chunk by chunk and yields each
 * chunk's text, then point the one import in App.tsx at it instead of this
 * file. No other app code changes.
 */

export type AskRequest = {
  question: string
  champA: string
  champB: string
  rank: string
}

export interface AskClient {
  /** Yields response text incrementally, matching the real streamed shape. */
  ask(req: AskRequest): AsyncGenerator<string, void, unknown>
}

// ponytail: fixed 40ms per-token delay and a canned reply -- good enough to
// exercise incremental rendering; replace with the real streaming client
// once POST /ask exists, no timing tuning needed here.
export const mockAskClient: AskClient = {
  async *ask(req) {
    const reply =
      `(mock /ask reply) For ${req.champA} vs ${req.champB} at ${req.rank}: ` +
      `${req.question} -- this is a placeholder streamed answer standing in ` +
      `for the real retrieval + quantized-model follow-up path.`
    for (const word of reply.split(' ')) {
      await new Promise((resolve) => setTimeout(resolve, 40))
      yield word + ' '
    }
  },
}
