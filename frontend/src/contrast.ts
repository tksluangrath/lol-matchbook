/**
 * Real WCAG 2.x relative-luminance / contrast-ratio calculation (the
 * standard formula, https://www.w3.org/TR/WCAG21/#dfn-relative-luminance),
 * used to verify the muted-grey states actually meet AA against the navy
 * background rather than assuming they do.
 */
function srgbChannelToLinear(c: number): number {
  const cs = c / 255
  return cs <= 0.03928 ? cs / 12.92 : ((cs + 0.055) / 1.055) ** 2.4
}

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace('#', '')
  const r = Number.parseInt(clean.slice(0, 2), 16)
  const g = Number.parseInt(clean.slice(2, 4), 16)
  const b = Number.parseInt(clean.slice(4, 6), 16)
  return [r, g, b]
}

export function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex)
  const [rl, gl, bl] = [r, g, b].map(srgbChannelToLinear)
  return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl
}

export function contrastRatio(hexA: string, hexB: string): number {
  const lA = relativeLuminance(hexA)
  const lB = relativeLuminance(hexB)
  const lighter = Math.max(lA, lB)
  const darker = Math.min(lA, lB)
  return (lighter + 0.05) / (darker + 0.05)
}

export const WCAG_AA_NORMAL_TEXT = 4.5
export const WCAG_AA_LARGE_TEXT_OR_UI = 3
