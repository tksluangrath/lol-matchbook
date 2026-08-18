/**
 * Fixed, non-negotiable LoL-player dark palette (see task brief / this
 * project's frontend design brief). Load-bearing: the four /advice
 * confidence states must be distinguishable by color alone.
 *
 * WCAG AA text contrast requires >= 4.5:1 for normal text against its
 * background. --grey-strong (#5A6472) measures ~3.22:1 against the navy
 * background -- passes AA's 3:1 floor for large text/graphical UI
 * components, but NOT for normal body text. --grey-text (#8A95A3) measures
 * ~6.35:1 -- passes AA normal-text contrast. See contrast.ts /
 * contrast.test.ts for the real, calculated numbers (not assumed).
 */
export const colors = {
  bg: '#0A0E16',
  surface: '#10161F',
  border: '#1C2530',
  teal: '#0AC8B9', // primary accent: primary input action + precomputed-hit state
  gold: '#C8AA6E', // secondary accent: wider-rank-fallback state ONLY
  greyStrong: '#5A6472', // muted: borders/icons/chrome for low-confidence states, not body text
  greyText: '#8A95A3', // muted: body text for low-confidence states -- AA-passing
  text: '#E7ECF2',
} as const

export type AdviceStateKind =
  | 'hit'
  | 'wider_rank_fallback'
  | 'abstention'
  | 'archetype_fallback'
  | 'not_precomputed'

/**
 * Color-to-confidence mapping. Real backend has 5 distinct /advice shapes,
 * one more than the 4-state palette this task's brief names (precomputed
 * hit / wider-rank fallback / abstention / not-precomputed). The 5th real
 * shape, archetype_fallback (a 200 with real Data Dragon lore blurbs, no
 * matchup-specific advice), doesn't have an assigned color in the brief.
 * Flagged in the report; resolved here by grouping it into the same grey
 * (low-confidence) tier as abstention/cold-start -- it's a generic,
 * non-matchup-specific fallback, same confidence tier as those two -- with
 * its own distinct copy so it's never confused with either by text.
 */
export const ADVICE_STATE_COLOR: Record<AdviceStateKind, string> = {
  hit: colors.teal,
  wider_rank_fallback: colors.gold,
  abstention: colors.greyText,
  archetype_fallback: colors.greyText,
  not_precomputed: colors.greyText,
}

/**
 * Short, scannable label for the hex confidence badge on each advice card --
 * the same color mapping above, restated as text so the state is never
 * conveyed by color alone (color-blind-safe redundancy, not decoration).
 */
export const ADVICE_STATE_BADGE_LABEL: Record<AdviceStateKind, string> = {
  hit: 'Matchup Data',
  wider_rank_fallback: 'Nearby Rank',
  abstention: 'Low Data',
  archetype_fallback: 'General Info',
  not_precomputed: 'Not Computed',
}
