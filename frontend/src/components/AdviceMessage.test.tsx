import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AdviceMessage } from './AdviceMessage'
import { colors } from '../theme'
import type { AdviceResult } from '../api/advice'

const phases = { early: 'early text', mid: 'mid text', late: 'late text' }

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
