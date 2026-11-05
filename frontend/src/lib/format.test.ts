import { describe, expect, it } from 'vitest'
import { championRoles, comfortTier, isOffRole, editedFieldsText, importCheckBadge, draftRules, isSolo, formatDuration, formatMetric, isSoloSource, matchupText, overBudgetNotice, rankLabel, averageRank, rankValue, teamRating, remainingSeconds, riotSourceLabel, riotSourceTag, roleLabel, scalingLabel } from './format'
import type { Lane } from '../api/types'

describe('scalingLabel', () => {
  it('names champion scaling scores', () => {
    expect(scalingLabel(1)).toBe('Early game')
    expect(scalingLabel(2)).toBe('Neutral scaling')
    expect(scalingLabel(3)).toBe('Late game')
  })
  it('names comp averages by their lean', () => {
    expect(scalingLabel(1.4)).toBe('Early game')
    expect(scalingLabel(2.2)).toBe('Neutral scaling')
    expect(scalingLabel(2.6)).toBe('Late game')
  })
})

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

describe('rankLabel', () => {
  it('names the tier and division, with LP on request', () => {
    expect(rankLabel({ tier: 'EMERALD', division: 'II', lp: 45 })).toBe('Emerald II')
    expect(rankLabel({ tier: 'EMERALD', division: 'II', lp: 45 }, true)).toBe('Emerald II · 45 LP')
    expect(rankLabel({ tier: 'GRANDMASTER', division: null, lp: 210 }, true)).toBe('Grandmaster · 210 LP')
  })
  it('says unranked when there is no tier', () => {
    expect(rankLabel(null)).toBe('Unranked')
    expect(rankLabel(undefined, true)).toBe('Unranked')
    expect(rankLabel({ tier: null, division: null, lp: null })).toBe('Unranked')
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

describe('roleLabel', () => {
  it('shows the secondary role when there is one', () => {
    expect(roleLabel({ role: 'TOP', secondary_role: null })).toBe('Top')
    expect(roleLabel({ role: 'TOP' })).toBe('Top')
    expect(roleLabel({ role: 'TOP', secondary_role: 'MID' })).toBe('Top / Mid')
  })
})

describe('importCheckBadge', () => {
  const base = { edited_fields: [] as string[], original: null }
  it('marks genuine unedited imports', () => {
    expect(importCheckBadge({ ...base, status: 'unedited' })).toMatchObject({ text: 'Riot ✓', tone: 'ok' })
  })
  it('lists what was edited', () => {
    const b = importCheckBadge({ ...base, status: 'edited', edited_fields: ['aggr', 'pool', 'tags'] })
    expect(b.tone).toBe('warn')
    expect(b.title).toContain('aggression, champion pool, weakness tags')
  })
  it('flags imports that cannot be verified, and old snapshots without a check', () => {
    expect(importCheckBadge({ ...base, status: 'unverified' }).text).toBe('Riot · unverified')
    expect(importCheckBadge(undefined)).toMatchObject({ text: 'Riot', tone: 'plain' })
  })
  it('words edited fields', () => {
    expect(editedFieldsText(['role', 'cs'])).toBe('role, farming')
  })
})

describe('isOffRole', () => {
  const jungler = { id: 50, roles: ['JUNGLE', 'TOP'] as Lane[] }
  it('is false in either usual role', () => {
    expect(isOffRole(jungler, 'JUNGLE', [])).toBe(false)
    expect(isOffRole(jungler, 'TOP', [])).toBe(false)
  })
  it('is true elsewhere, unless it is a top 3 pool pick', () => {
    expect(isOffRole(jungler, 'BOT', [1, 2, 3, 50, 5])).toBe(true)
    expect(isOffRole(jungler, 'BOT', [1, 2, 50, 4, 5])).toBe(false)
  })
  it('is false without role data', () => {
    expect(isOffRole({ id: 50, roles: [] }, 'BOT', [])).toBe(false)
    expect(championRoles({ roles: [] })).toBeNull()
    expect(championRoles(jungler)).toBe('Jungle / Top')
  })
})

describe('averageRank', () => {
  const p = (tier: string | null, division: string | null = null) => ({ riot: tier === undefined ? null : { rank: { tier, division } } }) as never
  it('averages across tiers and divisions', () => {
    expect(rankValue({ tier: 'IRON', division: 'IV' })).toBe(0)
    expect(averageRank([p('GOLD', 'I'), p('PLATINUM', 'III')]).rank).toEqual({ tier: 'PLATINUM', division: 'IV' })
  })
  it('snaps apex tiers to the nearest apex tier', () => {
    expect(averageRank([p('MASTER'), p('CHALLENGER')]).rank).toEqual({ tier: 'GRANDMASTER', division: null })
  })
  it('skips unranked and custom players', () => {
    const result = averageRank([p('DIAMOND', 'II'), p(null), { riot: null } as never])
    expect(result).toEqual({ rank: { tier: 'DIAMOND', division: 'II' }, ranked: 1, total: 3 })
  })
  it('returns no rank when nobody is ranked', () => {
    expect(averageRank([{ riot: null } as never]).rank).toBeNull()
    expect(rankLabel(averageRank([]).rank)).toBe('Unranked')
  })
})

describe('teamRating', () => {
  it('sums stat totals', () => {
    expect(teamRating([{ stat_total: 30 }, { stat_total: 34 }])).toEqual({ rating: 64, filled: 2 })
    expect(teamRating([])).toEqual({ rating: 0, filled: 0 })
  })
})
