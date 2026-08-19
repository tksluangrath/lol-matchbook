import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AdviceMessage, renderInlineMarkdown, splitIntoSentences } from './AdviceMessage'
import { colors } from '../theme'
import type { AdviceResult } from '../api/advice'

const phases = { early: 'early text', mid: 'mid text', late: 'late text' }

// Real /advice text for the real, already-precomputed Aatrox/Kayle (top,
// emerald) matchup -- pulled directly from a live GET /advice response,
// not invented. Used to verify the sentence-split against real generated
// prose, not a synthetic string that happens to split cleanly.
const REAL_AATROX_KAYLE_EARLY =
  "Aatrox’s high health and fear-driven crowd control can deter early ganks, but Kayle’s ability to gain attack range and her presence of a divine ally makes her a persistent threat. Avoid engaging directly in the early game; let Kayle establish positioning. Aatrox should use his stance to close gaps and prepare for a counter-punch, while Kayle can use her spellblade to pressure and harass if the opportunity arises."

describe('splitIntoSentences on real generated /advice text', () => {
  it('splits the real Aatrox/Kayle early-phase paragraph into exactly 3 sentences, keeping the semicolon-joined clause together', () => {
    const sentences = splitIntoSentences(REAL_AATROX_KAYLE_EARLY)
    expect(sentences).toHaveLength(3)
    expect(sentences[1]).toBe('Avoid engaging directly in the early game; let Kayle establish positioning.')
  })
})

describe('renderInlineMarkdown on real generated text containing literal "**bold**" markers', () => {
  // Real /advice text observed live for Aphelios/Ezreal (bottom, emerald) --
  // the model sometimes emits literal markdown bold that the frontend
  // previously rendered as raw asterisks instead of emphasis.
  const REAL_TEXT_WITH_BOLD = '**Advice:** Ezreal should prioritize killing low-health enemies.'

  it('renders the bolded segment as <strong>, not literal asterisks', () => {
    render(<div>{renderInlineMarkdown(REAL_TEXT_WITH_BOLD)}</div>)
    const strong = screen.getByText('Advice:')
    expect(strong.tagName).toBe('STRONG')
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument()
  })

  it('passes plain text through unchanged when there is no bold marker', () => {
    expect(renderInlineMarkdown('no markdown here')).toBe('no markdown here')
  })
})

describe('AdviceMessage renders all 4 real /advice response states distinctly', () => {
  it('precomputed hit: teal accent, phase breakdown, no fallback/abstention copy', () => {
    const result: AdviceResult = { kind: 'hit', phases }
    render(<AdviceMessage champA="Ashe" champB="Draven" result={result} />)
    const article = screen.getByRole('article')
    expect(article).toHaveAttribute('data-advice-kind', 'hit')
    expect(article).toHaveStyle({ borderColor: colors.teal })
    expect(screen.getByText('early text')).toBeInTheDocument()
    expect(screen.queryByText(/not enough data/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/fallback/i)).not.toBeInTheDocument()
  })

  it('wider-rank fallback: gold accent, explicit fallback copy', () => {
    const result: AdviceResult = { kind: 'wider_rank_fallback', phases }
    render(<AdviceMessage champA="Ashe" champB="Draven" result={result} />)
    const article = screen.getByRole('article')
    expect(article).toHaveStyle({ borderColor: colors.gold })
    expect(screen.getByText(/wider rank bracket/i)).toBeInTheDocument()
    expect(screen.getByText('early text')).toBeInTheDocument()
  })

  it('abstention: grey accent, explicit "not enough data" copy', () => {
    const result: AdviceResult = { kind: 'abstention', reason: 'not enough data at this rank' }
    render(<AdviceMessage champA="Ashe" champB="Draven" result={result} />)
    const article = screen.getByRole('article')
    expect(article).toHaveStyle({ borderColor: colors.greyText })
    expect(screen.getAllByText(/not enough data/i).length).toBeGreaterThan(0)
  })

  it('not-precomputed (cold-start / 404): grey accent, explicit "not yet computed" copy, distinct from abstention', () => {
    const result: AdviceResult = { kind: 'not_precomputed' }
    render(<AdviceMessage champA="Ashe" champB="Draven" result={result} />)
    const article = screen.getByRole('article')
    expect(article).toHaveStyle({ borderColor: colors.greyText })
    expect(screen.getByText(/not yet computed/i)).toBeInTheDocument()
    expect(screen.queryByText(/not enough data/i)).not.toBeInTheDocument()
  })

  it('archetype fallback (5th real backend state, flagged gap): grey accent, distinct copy from abstention and cold-start', () => {
    const result: AdviceResult = { kind: 'archetype_fallback', champABlurb: 'Ashe blurb', champBBlurb: 'Draven blurb' }
    render(<AdviceMessage champA="Ashe" champB="Draven" result={result} />)
    const article = screen.getByRole('article')
    expect(article).toHaveStyle({ borderColor: colors.greyText })
    expect(screen.getByText(/general champion info only/i)).toBeInTheDocument()
    expect(screen.getByText('Ashe blurb')).toBeInTheDocument()
    expect(screen.queryByText(/not yet computed/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/not enough data/i)).not.toBeInTheDocument()
  })
})
