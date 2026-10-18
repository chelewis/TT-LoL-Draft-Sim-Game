import { describe, expect, it } from 'vitest'
import { formatPoints, formatRate, physicalShare, rateTone } from './matchupPanel'

describe('rateTone', () => {
  it('reads a win rate against the baseline', () => {
    expect(rateTone(53)).toBe('good')
    expect(rateTone(47.5)).toBe('bad')
    expect(rateTone(50.6)).toBe('even')
    expect(rateTone(null)).toBe('none')
    expect(rateTone(51, 52)).toBe('bad')
  })
})

describe('formatting', () => {
  it('formats rates and points', () => {
    expect(formatRate(57.25)).toBe('57.3%')
    expect(formatRate(50)).toBe('50%')
    expect(formatRate(null)).toBe('–')
    expect(formatPoints(1.25)).toBe('+1.3 pts')
    expect(formatPoints(-0.5)).toBe('-0.5 pts')
  })
})

describe('physicalShare', () => {
  it('splits the damage mix', () => {
    expect(physicalShare({ physical: 9, magic: 3 })).toBe(0.75)
    expect(physicalShare({ physical: 0, magic: 0 })).toBe(0.5)
  })
})
