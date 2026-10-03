import { describe, expect, it } from 'vitest'
import { comfortTier, draftRules, isSolo, formatDuration, formatMetric, isSoloSource, matchupText, overBudgetNotice, remainingSeconds, riotSourceLabel, riotSourceTag } from './format'

describe('comfortTier', () => {
  const pool = [10, 20, 30, 40, 50]
  it('maps pool positions to tiers', () => {
    expect(comfortTier(pool, 10)).toBe('BEST')
    expect(comfortTier(pool, 20)).toBe('COMFORT')
    expect(comfortTier(pool, 30)).toBe('COMFORT')
    expect(comfortTier(pool, 40)).toBe('FAMILIAR')
    expect(comfortTier(pool, 50)).toBe('FAMILIAR')
  })
  it('treats champions outside the pool as off-pool', () => {
    expect(comfortTier(pool, 99)).toBe('VULNERABLE')
  })
})

describe('draftRules', () => {
  it('describes the lobby draft options', () => {
    expect(draftRules({ bans_enabled: true, timers_enabled: true, pick_seconds: 30, ban_seconds: 20 })).toBe('Bans and picks · 30s per pick, 20s per ban')
    expect(draftRules({ bans_enabled: false, timers_enabled: true, pick_seconds: 45, ban_seconds: 20 })).toBe('Picks only (no bans) · 45s per pick')
    expect(draftRules({ bans_enabled: true, timers_enabled: false, pick_seconds: 30, ban_seconds: 30 })).toBe('Bans and picks · no timers')
  })
})

describe('riot data source', () => {
  it('treats solo and missing sources as trusted', () => {
    expect(isSoloSource('SOLO')).toBe(true)
    expect(isSoloSource(null)).toBe(true)
    expect(isSoloSource(undefined)).toBe(true)
    expect(isSoloSource('FLEX')).toBe(false)
    expect(isSoloSource('NORMAL')).toBe(false)
  })
  it('labels the queues and only tags non-solo ones', () => {
    expect(riotSourceLabel('FLEX')).toBe('Ranked flex')
    expect(riotSourceLabel('NORMAL')).toBe('Normal games')
    expect(riotSourceLabel(null)).toBe('Ranked solo')
    expect(riotSourceTag('SOLO')).toBe('')
    expect(riotSourceTag('FLEX')).toBe('Flex')
    expect(riotSourceTag('NORMAL')).toBe('Normals')
  })
})

describe('formatMetric', () => {
  it('formats percentages and plain numbers', () => {
    expect(formatMetric(0.4712, 'percent')).toBe('47.1%')
    expect(formatMetric(7.8333, 'number')).toBe('7.83')
    expect(formatMetric(2, 'number')).toBe('2')
  })
})

describe('isSolo', () => {
  it('recognises single player games', () => {
    expect(isSolo({ settings: { mode: 'SOLO' } })).toBe(true)
    expect(isSolo({ settings: { mode: 'MULTI' } })).toBe(false)
    expect(isSolo({ settings: {} })).toBe(false)
  })
})

describe('formatDuration', () => {
  it('formats m:ss', () => {
    expect(formatDuration(1980)).toBe('33:00')
    expect(formatDuration(65)).toBe('1:05')
  })
})

describe('remainingSeconds', () => {
  it('counts down and never goes negative', () => {
    const now = Date.parse('2026-09-30T15:00:10Z')
    expect(remainingSeconds('2026-09-30T15:00:30Z', now)).toBe(20)
    expect(remainingSeconds('2026-09-30T15:00:00Z', now)).toBe(0)
    expect(remainingSeconds(null, now)).toBe(0)
  })
})

describe('overBudgetNotice', () => {
  it('is empty for legal teams and lists players otherwise', () => {
    expect(overBudgetNotice({ over_budget: false, over_budget_players: [] })).toBe('')
    const text = overBudgetNotice({
      over_budget: true,
      over_budget_players: [{ player_id: 1, name: 'Zed', over_by: 4 }],
    })
    expect(text).toContain('Potentially illegal team')
    expect(text).toContain('Zed (+4)')
  })
})

describe('matchupText', () => {
  it('describes matchups', () => {
    expect(matchupText(null)).toBe('Even matchup')
    expect(matchupText('BLUE_STRONG')).toBe('Favours Blue strongly')
    expect(matchupText('RED_SLIGHT')).toBe('Favours Red slightly')
  })
})
