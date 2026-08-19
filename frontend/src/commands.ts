/**
 * Slash-command parsing for the chat input. Only input starting with `/`
 * reaches this module -- everything else keeps going to /ask unchanged
 * (App.tsx makes that routing decision, not this file).
 *
 * Fixes the earlier confusion where `/advice kayn vs warwick` silently
 * fell through to /ask and got echoed like plain text: any unrecognized
 * slash input now returns an explicit `unrecognized` result instead of
 * nothing / an /ask echo.
 */

// Real values confirmed against the live DB (Advice.role / Advice.rank_bracket
// distinct columns) -- not guessed. The backend's canonical role string is
// now 'support' (app/data_pipeline/aggregate.py maps Riot's raw "UTILITY"
// team_position to it) -- 'utility' is accepted here only as a typed alias,
// via ROLE_ALIASES below, so old habits/muscle memory still resolve.
export const REAL_ROLES = ['top', 'jungle', 'middle', 'bottom', 'support'] as const
export const REAL_RANKS = ['iron', 'gold', 'platinum', 'emerald'] as const

export type Role = (typeof REAL_ROLES)[number]
export type Rank = (typeof REAL_RANKS)[number]

const ROLE_ALIASES: Record<string, Role> = { utility: 'support' }

export type ParsedCommand =
  | { kind: 'help' }
  | { kind: 'ask'; question: string }
  | { kind: 'advice'; champA: string; champB: string; rank: Rank; role: Role }
  | { kind: 'advice_incomplete'; message: string }
  | { kind: 'unrecognized'; raw: string }

/** Structured, not a flat string -- rendered as a real list in the UI
 * (MessageList's 'help' case), not newline-joined text that a plain
 * <article> would collapse into one run-on line. */
export const HELP_COMMANDS: { command: string; description: string }[] = [
  { command: '/help', description: 'Show this list' },
  {
    command: '/advice <champA> vs <champB> [rank] [role]',
    description: 'Real precomputed matchup advice',
  },
  { command: '/ask <question>', description: 'Placeholder only, not real retrieval yet' },
]

/** Strips punctuation/spaces and lowercases, so "Kai'Sa" / "kaisa" / "Kai Sa" all match. */
function normalizeChampName(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]/g, '')
}

/**
 * A handful of real Data Dragon keys that don't just differ from the common
 * name by punctuation/spacing (which normalizeChampName already handles) --
 * they're a different word entirely, confirmed against the real live
 * champion.json for patch 16.15.1, not guessed:
 *   - "Wukong" (what every player types) -> real key "MonkeyKing"
 * Only real, verified mismatches belong here -- not a speculative list.
 */
const CHAMPION_NAME_ALIASES: Record<string, string> = {
  wukong: 'monkeyking',
}

/** Matches `raw` against the real Data Dragon champion list, returning the real
 * spelling on success. Case/punctuation-insensitive; not a second hardcoded list. */
export function matchChampion(raw: string, realChampionNames: string[]): string | null {
  const normalized = normalizeChampName(raw)
  if (!normalized) return null
  const target = CHAMPION_NAME_ALIASES[normalized] ?? normalized
  const hit = realChampionNames.find((name) => normalizeChampName(name) === target)
  return hit ?? null
}

function matchToken<T extends string>(token: string, values: readonly T[]): T | undefined {
  const lower = token.toLowerCase()
  return values.find((v) => v === lower)
}

function parseAdvice(argsText: string, realChampionNames: string[]): ParsedCommand {
  const parts = argsText.split(/\s+vs\s+/i)
  if (parts.length !== 2 || !parts[0].trim() || !parts[1].trim()) {
    return {
      kind: 'advice_incomplete',
      message: 'Usage: /advice <champA> vs <champB> [rank] [role]',
    }
  }

  const champARaw = parts[0].trim()

  // champB's raw name can be multiple words (e.g. "Miss Fortune", "Aurelion
  // Sol") -- pull rank/role tokens out from anywhere in the trailing text
  // first, and whatever's left over (in order) is champB's name, not just
  // the first token after "vs".
  const tokens = parts[1].trim().split(/\s+/)
  let rank: Rank | undefined
  let role: Role | undefined
  const champBTokens: string[] = []
  for (const token of tokens) {
    if (!rank) {
      const r = matchToken(token, REAL_RANKS)
      if (r) {
        rank = r
        continue
      }
    }
    if (!role) {
      const r = matchToken(token, REAL_ROLES) ?? ROLE_ALIASES[token.toLowerCase()]
      if (r) {
        role = r
        continue
      }
    }
    champBTokens.push(token)
  }
  const champBRaw = champBTokens.join(' ')
  if (!champBRaw) {
    return {
      kind: 'advice_incomplete',
      message: 'Missing champB name -- try: /advice <champA> vs <champB> [rank] [role]',
    }
  }

  const champA = matchChampion(champARaw, realChampionNames)
  const champB = matchChampion(champBRaw, realChampionNames)

  const unknownNames = [!champA ? champARaw : null, !champB ? champBRaw : null].filter(
    (v): v is string => v !== null,
  )
  if (unknownNames.length > 0) {
    return {
      kind: 'advice_incomplete',
      message: `Don't recognize ${unknownNames.map((n) => `"${n}"`).join(' or ')} as a champion name.`,
    }
  }

  if (!rank || !role) {
    const missing = [!rank ? 'rank' : null, !role ? 'role' : null].filter(Boolean).join(' and ')
    return {
      kind: 'advice_incomplete',
      message:
        `Missing ${missing} -- try: /advice ${champA} vs ${champB} ` +
        `${rank ?? '<rank>'} ${role ?? '<role>'}. ` +
        `Valid ranks: ${REAL_RANKS.join(', ')}. Valid roles: ${REAL_ROLES.join(', ')}.`,
    }
  }

  return { kind: 'advice', champA: champA as string, champB: champB as string, rank, role }
}

export function parseSlashCommand(input: string, realChampionNames: string[]): ParsedCommand {
  const trimmed = input.trim()
  const firstSpace = trimmed.indexOf(' ')
  const word = (firstSpace === -1 ? trimmed : trimmed.slice(0, firstSpace)).slice(1).toLowerCase()
  const rest = firstSpace === -1 ? '' : trimmed.slice(firstSpace + 1).trim()

  if (word === 'help') return { kind: 'help' }
  if (word === 'ask') return { kind: 'ask', question: rest }
  if (word === 'advice') return parseAdvice(rest, realChampionNames)
  return { kind: 'unrecognized', raw: trimmed }
}
