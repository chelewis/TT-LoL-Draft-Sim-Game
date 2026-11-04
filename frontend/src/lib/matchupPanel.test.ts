import { describe, expect, it } from 'vitest'
import { GRADE_TONE, factorLines, formatPoints, formatRate, gradeSummary, physicalShare, rateTone, roleBadge, wheelEdge, wheelText } from './matchupPanel'
import type { LaneWheel } from '../api/types'

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

describe('lane insights', () => {
  const wheel: LaneWheel = {
    blue: { strength: 'Offence', weakness: 'Control' },
    red: { strength: 'Defence', weakness: 'Offence' },
    winner: 'BLUE',
    kind: 'STRONG',
    blue_multiplier: 1.5,
    red_multiplier: 1,
  }

  it('reads the wheel from each side', () => {
    expect(wheelEdge(wheel, 'BLUE')).toBe('win-strong')
    expect(wheelEdge(wheel, 'RED')).toBe('lose-strong')
    expect(wheelEdge({ ...wheel, kind: 'SLIGHT' }, 'RED')).toBe('lose')
    expect(wheelEdge({ ...wheel, winner: null, kind: null }, 'BLUE')).toBe('even')
    expect(wheelEdge(null, 'BLUE')).toBe('even')
    expect(wheelText(wheel, 'BLUE')).toBe('Offence beats Defence · strong (×1.50)')
    expect(wheelText(wheel, 'RED')).toBe('Offence beats Defence · strong (×1.50) to the enemy')
    expect(wheelText({ ...wheel, winner: null, kind: null }, 'RED')).toBe('Defence vs Offence: even on the matchup wheel')
  })

  it('labels roles', () => {
    expect(roleBadge('MAIN', 0)).toBeNull()
    expect(roleBadge(null, 0)).toBeNull()
    expect(roleBadge('SECONDARY', 0)?.label).toBe('Secondary role')
    expect(roleBadge('OFF_ROLE', 0.15)).toMatchObject({ label: 'Off-role −15%', kind: 'off' })
    expect(roleBadge('OFF_ROLE', 0)?.kind).toBe('exempt')
    expect(roleBadge('OFF_ROLE', null)?.kind).toBe('unknown')
    expect(roleBadge('OFF_ROLE_EXEMPT', 0)?.label).toBe('Off-role (pool exempt)')
  })

  it('tones grades and lists the factors that matter', () => {
    expect([GRADE_TONE.S, GRADE_TONE.C, GRADE_TONE.F]).toEqual(['good', 'even', 'bad'])
    expect(gradeSummary({ grade: null, percentile: null })).toMatch(/hidden/)
    expect(gradeSummary({ grade: 'A', percentile: 0.9 })).toMatch(/10%/)
    const lines = factorLines({ comfort_tier: 'BEST', comfort: 1.4, playstyle: 1, strength_fit: 1.001, off_role: 0.85, wheel: 1, counter: 1, duo: 1, range: 1, scaling: 1 })
    expect(lines).toEqual([
      { label: 'Comfort', value: 1.4, tone: 'good' },
      { label: 'Off-role', value: 0.85, tone: 'bad' },
    ])
    expect(factorLines(null)).toEqual([])
  })
})
