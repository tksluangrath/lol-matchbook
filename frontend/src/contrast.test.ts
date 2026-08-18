import { describe, expect, it } from 'vitest'
import { colors } from './theme'
import { contrastRatio, WCAG_AA_LARGE_TEXT_OR_UI, WCAG_AA_NORMAL_TEXT } from './contrast'

describe('grey-state contrast against the navy background', () => {
  it('greyText (body copy for abstention/cold-start/archetype states) passes WCAG AA normal-text contrast', () => {
    const ratio = contrastRatio(colors.greyText, colors.bg)
    // eslint-disable-next-line no-console
    console.log(`greyText (${colors.greyText}) vs bg (${colors.bg}) contrast ratio: ${ratio.toFixed(2)}:1`)
    expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_NORMAL_TEXT)
  })

  it('greyStrong (chrome/borders only, never body text) meets at least the AA large-text/UI-component floor', () => {
    const ratio = contrastRatio(colors.greyStrong, colors.bg)
    console.log(`greyStrong (${colors.greyStrong}) vs bg (${colors.bg}) contrast ratio: ${ratio.toFixed(2)}:1`)
    expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_LARGE_TEXT_OR_UI)
  })

  it('greyStrong does NOT meet normal-text AA -- documents why it is never used for body copy', () => {
    const ratio = contrastRatio(colors.greyStrong, colors.bg)
    expect(ratio).toBeLessThan(WCAG_AA_NORMAL_TEXT)
  })
})
