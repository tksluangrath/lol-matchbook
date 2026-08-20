/**
 * Real client for POST /report (backend/app/routers/report.py) -- the
 * /report slash command's bug/matchup-mistake submission.
 */
import { DEFAULT_ADVICE_BASE_URL } from './advice'

export type ReportCategory = 'bug' | 'matchup_mistake'

export type ReportRequest = {
  category: ReportCategory
  message: string
  champA?: string
  champB?: string
  role?: string
  rank?: string
}

export async function submitReport(
  req: ReportRequest,
  baseUrl: string = DEFAULT_ADVICE_BASE_URL,
): Promise<void> {
  const res = await fetch(`${baseUrl}/report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      category: req.category,
      message: req.message,
      champ_a: req.champA ?? null,
      champ_b: req.champB ?? null,
      role: req.role ?? null,
      rank: req.rank ?? null,
    }),
  })
  if (!res.ok) {
    throw new Error('Could not submit the report. Is the backend running?')
  }
}
