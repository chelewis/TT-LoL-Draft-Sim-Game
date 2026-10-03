import { describe, expect, it } from 'vitest'
import type { MatchEvent, MatchResult } from '../api/types'
import { describeEvent, summarize } from './summary'

const team = (name: string, extra = {}) => ({
  name, gold: 1, kills: 10, towers: 5, inhibitors: 1, dragons: 3, barons: 1, soul: false,
  comp: { win_rate: 50, damage_profile: { physical: 1, magic: 1 } }, ...extra,
})

const result = {
  winner: 'BLUE', win_condition: 'NEXUS', duration_seconds: 1980,
  teams: { BLUE: team('Alpha', { kills: 20 }), RED: team('Beta', { dragons: 1, barons: 0, kills: 8 }) },
  lanes: {
    TOP: { winner: 'BLUE', matchup: 'BLUE_STRONG' }, JUNGLE: { winner: 'BLUE', matchup: null },
    MID: { winner: 'BLUE', matchup: null }, BOT: { winner: 'RED', matchup: null }, SUPPORT: { winner: null, matchup: null },
  },
  players: [{ name: 'Zed', team: 'RED', comfort_tier: 'VULNERABLE' }],
} as unknown as MatchResult

describe('summarize', () => {
  it('explains a nexus win in plain language', () => {
    const lines = summarize(result)
    expect(lines[0]).toBe('Alpha destroyed the enemy nexus at 33:00.')
    expect(lines.join(' ')).toContain('won the early lanes (Top, Jungle, Mid)')
    expect(lines.join(' ')).toContain('Beta had a player on off-pool champions (Zed)')
    expect(lines.join(' ')).not.toMatch(/seed|formula|multiplier/i)
  })
})

describe('describeEvent', () => {
  const names = { BLUE: 'Alpha', RED: 'Beta' }
  it('describes objectives and ignores internal events', () => {
    const nexus: MatchEvent = { sequence: 1, phase: 'late', minute: 33, type: 'NEXUS', payload: { team: 'BLUE' } }
    expect(describeEvent(nexus, names)).toContain('Alpha DESTROY THE NEXUS')
    const siege: MatchEvent = { sequence: 2, phase: 'late', minute: 33, type: 'SIEGE', payload: {} }
    expect(describeEvent(siege, names)).toBeNull()
  })
})
