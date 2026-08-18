import { describe, expect, it } from 'vitest'
import { matchChampion, parseSlashCommand } from './commands'

// Real Data Dragon KEYS (not display names), confirmed against the live
// champion.json for patch 16.15.1 -- not a small convenient fiction.
// "Kaisa" (no apostrophe/capital-S) and "MonkeyKing" (Wukong's real key,
// a total rename, not just punctuation) are both real quirks found by
// checking, not assumed.
const REAL_CHAMPIONS = [
  'Aatrox',
  'Kayle',
  'Kayn',
  'Warwick',
  'Kaisa',
  'Khazix',
  'Velkoz',
  'MonkeyKing',
  'MissFortune',
  'AurelionSol',
  'JarvanIV',
  'DrMundo',
  'Milio',
  'Nami',
]

describe('matchChampion', () => {
  it('matches case-insensitively for a plain single-word name', () => {
    expect(matchChampion('aatrox', REAL_CHAMPIONS)).toBe('Aatrox')
  })

  it('strips apostrophes/spacing for champions whose display name uses them (Kai\'Sa, Kha\'Zix, Vel\'Koz)', () => {
    expect(matchChampion("kai'sa", REAL_CHAMPIONS)).toBe('Kaisa')
    expect(matchChampion('KAI SA', REAL_CHAMPIONS)).toBe('Kaisa')
    expect(matchChampion("kha'zix", REAL_CHAMPIONS)).toBe('Khazix')
    expect(matchChampion("vel'koz", REAL_CHAMPIONS)).toBe('Velkoz')
  })

  it('matches multi-word display names against their real camelCase key (Miss Fortune, Aurelion Sol, Jarvan IV, Dr. Mundo)', () => {
    expect(matchChampion('miss fortune', REAL_CHAMPIONS)).toBe('MissFortune')
    expect(matchChampion('aurelion sol', REAL_CHAMPIONS)).toBe('AurelionSol')
    expect(matchChampion('jarvan iv', REAL_CHAMPIONS)).toBe('JarvanIV')
    expect(matchChampion('dr. mundo', REAL_CHAMPIONS)).toBe('DrMundo')
  })

  it('resolves "wukong" via the real, verified name alias to its actual Data Dragon key MonkeyKing', () => {
    expect(matchChampion('wukong', REAL_CHAMPIONS)).toBe('MonkeyKing')
    expect(matchChampion('Wukong', REAL_CHAMPIONS)).toBe('MonkeyKing')
  })

  it('returns null for a name Data Dragon does not recognize', () => {
    expect(matchChampion('notachampion', REAL_CHAMPIONS)).toBeNull()
  })
})

describe('parseSlashCommand', () => {
  it('/help returns the help command', () => {
    expect(parseSlashCommand('/help', REAL_CHAMPIONS)).toEqual({ kind: 'help' })
  })

  it('/ask <question> passes the question through unchanged (still the mock path)', () => {
    expect(parseSlashCommand('/ask how do I trade?', REAL_CHAMPIONS)).toEqual({
      kind: 'ask',
      question: 'how do I trade?',
    })
  })

  it('/advice with champ, rank, and role resolves to a real advice command', () => {
    const result = parseSlashCommand('/advice aatrox vs kayle emerald top', REAL_CHAMPIONS)
    expect(result).toEqual({ kind: 'advice', champA: 'Aatrox', champB: 'Kayle', rank: 'emerald', role: 'top' })
  })

  it('/advice with rank/role in swapped order still resolves (order-insensitive)', () => {
    const result = parseSlashCommand('/advice aatrox vs kayle top emerald', REAL_CHAMPIONS)
    expect(result).toEqual({ kind: 'advice', champA: 'Aatrox', champB: 'Kayle', rank: 'emerald', role: 'top' })
  })

  it('/advice kayn vs warwick emerald jungle resolves both real champions', () => {
    const result = parseSlashCommand('/advice kayn vs warwick emerald jungle', REAL_CHAMPIONS)
    expect(result).toEqual({ kind: 'advice', champA: 'Kayn', champB: 'Warwick', rank: 'emerald', role: 'jungle' })
  })

  it('/advice missing rank and role prompts inline instead of firing an incomplete request', () => {
    const result = parseSlashCommand('/advice aatrox vs kayle', REAL_CHAMPIONS)
    expect(result.kind).toBe('advice_incomplete')
    if (result.kind === 'advice_incomplete') {
      expect(result.message).toMatch(/rank and role/i)
      expect(result.message).toMatch(/Aatrox vs Kayle/)
    }
  })

  it('/advice with an unrecognized champion name reports it clearly, not silently', () => {
    const result = parseSlashCommand('/advice notachamp vs kayle emerald top', REAL_CHAMPIONS)
    expect(result.kind).toBe('advice_incomplete')
    if (result.kind === 'advice_incomplete') {
      expect(result.message).toMatch(/notachamp/)
    }
  })

  it('an unrecognized slash command is flagged, not silently routed anywhere', () => {
    expect(parseSlashCommand('/foobar', REAL_CHAMPIONS)).toEqual({ kind: 'unrecognized', raw: '/foobar' })
  })

  it('/advice resolves a different real pair (Milio vs Nami, utility, gold) end to end', () => {
    const result = parseSlashCommand('/advice milio vs nami gold utility', REAL_CHAMPIONS)
    expect(result).toEqual({ kind: 'advice', champA: 'Milio', champB: 'Nami', rank: 'gold', role: 'utility' })
  })

  it('/advice resolves champions typed with apostrophes and multi-word spacing in the same command', () => {
    const result = parseSlashCommand("/advice kai'sa vs miss fortune emerald bottom", REAL_CHAMPIONS)
    expect(result).toEqual({ kind: 'advice', champA: 'Kaisa', champB: 'MissFortune', rank: 'emerald', role: 'bottom' })
  })

  it('/advice resolves "wukong" to MonkeyKing end to end via parseSlashCommand', () => {
    const result = parseSlashCommand('/advice wukong vs aatrox emerald top', REAL_CHAMPIONS)
    expect(result).toEqual({ kind: 'advice', champA: 'MonkeyKing', champB: 'Aatrox', rank: 'emerald', role: 'top' })
  })

  it('/advice where rank/role stripping consumes every trailing token reports a missing champB name, not a false match', () => {
    const result = parseSlashCommand('/advice aatrox vs emerald top', REAL_CHAMPIONS)
    expect(result.kind).toBe('advice_incomplete')
    if (result.kind === 'advice_incomplete') {
      expect(result.message).toMatch(/missing champB/i)
    }
  })
})
