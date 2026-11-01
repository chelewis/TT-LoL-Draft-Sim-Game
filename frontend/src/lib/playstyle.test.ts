import { describe, expect, it } from 'vitest'
import { effectText, evidenceText, sortTags } from './playstyle'

describe('effectText', () => {
  it('words multipliers with a sign', () => {
    expect(effectText({ hook: 'cs_rate', value: 0.04 })).toBe('CS per minute +4%')
    expect(effectText({ hook: 'survival', value: -0.05 })).toBe('Survival in fights −5%')
  })
  it('words the off-pool penalty as a change to the penalty', () => {
    expect(effectText({ hook: 'off_pool_penalty', value: 1 })).toBe('Off-pool penalty removed')
    expect(effectText({ hook: 'off_pool_penalty', value: 0.5 })).toBe('Off-pool penalty halved')
    expect(effectText({ hook: 'off_pool_penalty', value: -0.5 })).toBe('Off-pool penalty 50% bigger')
  })
  it('falls back to the hook name', () => {
    expect(effectText({ hook: 'new_hook', value: 0.1 })).toBe('new_hook +10%')
  })
})

describe('evidenceText', () => {
  it('explains challenge levels', () => {
    expect(evidenceText({ source: 'challenge', challenge_id: 1, challenge_name: 'Solo Bolo', level: 'MASTER', percentile: 0.012 }))
      .toBe('Master in Solo Bolo (top 1.2%)')
  })
  it('explains match stats', () => {
    expect(evidenceText({ source: 'match', label: 'CS per minute', unit: 'number', op: '<=', value: 4.21, threshold: 5.5 }))
      .toBe('CS per minute: 4.21 (at most 5.5)')
    expect(evidenceText({ source: 'match', label: 'Share of games on the most played champion', unit: 'percent', op: '>=', value: 0.7, threshold: 0.6 }))
      .toBe('Share of games on the most played champion: 70% (at least 60%)')
  })
  it('handles missing evidence', () => {
    expect(evidenceText(null)).toBeNull()
  })
})

describe('sortTags', () => {
  it('puts positive tags first', () => {
    const tags = [{ k: 'a', polarity: 'negative' as const }, { k: 'b', polarity: 'positive' as const }, { k: 'c', polarity: 'positive' as const }]
    expect(sortTags(tags).map((t) => t.k)).toEqual(['b', 'c', 'a'])
  })
})
