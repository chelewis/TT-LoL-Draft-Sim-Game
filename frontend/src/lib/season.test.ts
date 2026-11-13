import { describe, expect, it } from 'vitest'
import type { SeasonMatch, SeasonTeamRef, StandingRow } from '../api/types'
import {
  autoSimState, bracketSlots, draftRounds, filterPool, pickableLanes, pickClockLabel, deadlineLabel, formatLabel, playoffChoices, seasonInviteLink, seriesSummary, swissWins,
  timeUntil, vsManager,
  diffLabel, matchesPerTeam, myMatchAction, opponentOf, recordLabel, resultFor, roundLabel, roundRobinRounds,
  scoreLine, sortStandings,
} from './season'

const team = (id: number, name: string): SeasonTeamRef => ({
  id, team_id: id + 100, name, logo: '', seed: id, is_cpu: id !== 1, is_you: id === 1, manager: null,
})

const match = (patch: Partial<SeasonMatch> = {}): SeasonMatch => ({
  id: 1, stage: 'REGULAR', round: 1, slot: 0, format: 'BO3', status: 'SCHEDULED', played_mode: null,
  home: team(1, 'Alpha'), away: team(2, 'Bravo'), home_score: 0, away_score: 0, winner_team_id: null,
  series_id: null, live_game_id: null, latest_game_id: null, games: [], has_manager: true, yours: true,
  auto_requested: { home: false, away: false }, completed_at: null, ...patch,
})

const row = (id: number, name: string, wins: number, losses: number, rank: number, gameDiff = 0): StandingRow => ({
  team: team(id, name), seed: id, rank, played: wins + losses, wins, losses, game_wins: 0, game_losses: 0,
  game_diff: gameDiff, streak: '', form: [], swiss_status: null, eliminated: false,
})

describe('round robin sizes', () => {
  it('counts rounds with byes for odd team counts', () => {
    expect(roundRobinRounds(4, false)).toBe(3)
    expect(roundRobinRounds(5, false)).toBe(5)
    expect(roundRobinRounds(10, true)).toBe(18)
    expect(roundRobinRounds(1, false)).toBe(0)
  })
  it('counts matches per team', () => {
    expect(matchesPerTeam(8, false)).toBe(7)
    expect(matchesPerTeam(8, true)).toBe(14)
  })
})

describe('labels', () => {
  it('formats rounds, records and differentials', () => {
    expect(roundLabel(2, 7)).toBe('Round 2 of 7')
    expect(roundLabel(2, 0)).toBe('Round 2')
    expect(recordLabel({ wins: 5, losses: 2 })).toBe('5-2')
    expect([diffLabel(3), diffLabel(0), diffLabel(-2)]).toEqual(['+3', '0', '-2'])
  })
})

describe('match helpers', () => {
  it('finds the opponent from either side', () => {
    const m = match()
    expect(opponentOf(m, 1)?.name).toBe('Bravo')
    expect(opponentOf(m, 2)?.name).toBe('Alpha')
    expect(opponentOf(m, 3)).toBeNull()
  })
  it('shows a result from a team\'s point of view', () => {
    const m = match({ status: 'COMPLETED', home_score: 1, away_score: 2, winner_team_id: 2 })
    expect(resultFor(m, 1)).toBe('L 1-2')
    expect(resultFor(m, 2)).toBe('W 2-1')
    expect(resultFor(match(), 1)).toBeNull()
    expect(scoreLine(m)).toBe('1 - 2')
    expect(scoreLine(match())).toBe('vs')
  })
  it('picks the next action for your match', () => {
    expect(myMatchAction(null)).toBeNull()
    expect(myMatchAction(match())).toBe('PLAY')
    expect(myMatchAction(match({ status: 'LIVE', games: [{ game_id: 1, game_number: 1, status: 'DRAFTING', winner_team_id: null }] })))
      .toBe('CONTINUE')
    expect(myMatchAction(match({ status: 'COMPLETED' }))).toBe('DONE')
  })
})

describe('sortStandings', () => {
  const rows = [row(1, 'Alpha', 3, 1, 1, 4), row(2, 'bravo', 3, 1, 2, 2), row(3, 'Charlie', 1, 3, 3, -6)]
  it('sorts by a column and keeps rank order for ties', () => {
    expect(sortStandings(rows, 'wins', true).map((r) => r.team.id)).toEqual([1, 2, 3])
    expect(sortStandings(rows, 'wins', false).map((r) => r.team.id)).toEqual([3, 1, 2])
    expect(sortStandings(rows, 'game_diff', false).map((r) => r.team.id)).toEqual([3, 2, 1])
  })
  it('sorts names case-insensitively', () => {
    expect(sortStandings(rows, 'name', false).map((r) => r.team.name)).toEqual(['Alpha', 'bravo', 'Charlie'])
  })
  it('does not change the original', () => {
    sortStandings(rows, 'name', true)
    expect(rows.map((r) => r.team.id)).toEqual([1, 2, 3])
  })
})

describe('formats', () => {
  const o = { regular_series: 'BO1', playoff_size: 4, playoff_series: 'BO3', final_series: 'BO5', rr_double: false } as const
  it('names the competition', () => {
    expect(formatLabel('ROUND_ROBIN', { playoff_size: 0, rr_double: true })).toBe('Double round robin')
    expect(formatLabel('ROUND_ROBIN', { playoff_size: 2, rr_double: false })).toBe('Round robin + final')
    expect(formatLabel('ROUND_ROBIN', o)).toBe('Round robin + top 4 playoffs')
    expect(formatLabel('SWISS', { playoff_size: 8, rr_double: false })).toBe('Swiss stage + 8-team bracket')
  })
  it('summarises series lengths', () => {
    expect(seriesSummary('ROUND_ROBIN', o)).toBe('Bo1 league · Bo3 playoffs · Bo5 final')
    expect(seriesSummary('ROUND_ROBIN', { ...o, playoff_size: 2 })).toBe('Bo1 league · Bo5 final')
    expect(seriesSummary('SWISS', { ...o, playoff_size: 0 })).toBe('Bo1 Swiss')
  })
  it('lists playoff sizes that fit and Swiss win targets', () => {
    expect(playoffChoices(6)).toEqual([2, 4])
    expect(playoffChoices(16)).toEqual([2, 4, 8])
    expect([swissWins(8), swissWins(16)]).toEqual([2, 3])
  })
  it('fills a bracket round with empty slots', () => {
    const m = match()
    expect(bracketSlots({ round: 1, name: 'Semifinals', slots: 2, format: 'BO3', matches: [m] })).toEqual([m, null])
    expect(bracketSlots({ round: 2, name: 'Final', slots: 1, format: 'BO5', matches: [] })).toEqual([null])
  })
})

describe('multiplayer', () => {
  const human = (id: number, name: string): SeasonTeamRef => ({ ...team(id, name), is_cpu: false, manager: { id, username: name } })
  const pvp = (auto = { home: false, away: false }) => match({ home: human(1, 'Alpha'), away: human(2, 'Bravo'), auto_requested: auto })
  it('tells manager matches from CPU ones', () => {
    expect(vsManager(match())).toBe(false)
    expect(vsManager(pvp())).toBe(true)
  })
  it('follows the auto-sim agreement from each side', () => {
    expect(autoSimState(match(), 1)).toBe('SOLO')
    expect(autoSimState(pvp(), 1)).toBe('NONE')
    expect(autoSimState(pvp({ home: true, away: false }), 1)).toBe('ASKED')
    expect(autoSimState(pvp({ home: true, away: false }), 2)).toBe('OFFERED')
  })
  it('labels deadlines', () => {
    expect([0, 12, 24, 48, 168].map(deadlineLabel)).toEqual(['No deadline', '12 hours', '1 day', '2 days', '1 week'])
    const now = Date.parse('2026-01-01T00:00:00Z')
    expect(timeUntil('2026-01-01T00:05:30Z', now)).toBe('5m')
    expect(timeUntil('2026-01-01T03:20:00Z', now)).toBe('3h 20m')
    expect(timeUntil('2026-01-03T04:00:00Z', now)).toBe('2d 4h')
    expect(timeUntil('2025-12-31T23:00:00Z', now)).toBe('now')
  })
  it('builds the invite link', () => {
    expect(seasonInviteLink('ABC123', 'https://x.test')).toBe('https://x.test/seasons/join/ABC123')
  })
})

describe('player draft', () => {
  it('labels pick clocks', () => {
    expect([0, 60, 300, 3600, 86400].map(pickClockLabel))
      .toEqual(['No pick clock', '1 minute per pick', '5 minutes per pick', '1 hour per pick', '24 hours per pick'])
  })
  it('groups picks by round', () => {
    const pick = (n: number) => ({ pick_number: n, team: null, player_id: n, player_name: `P${n}`, lane: 'TOP' as const, auto: false })
    expect(draftRounds([1, 2, 3, 4, 5].map(pick), 2).map((r) => r.map((p) => p.pick_number))).toEqual([[1, 2], [3, 4], [5]])
  })
  it('finds the lanes a player can fill and filters the pool', () => {
    expect(pickableLanes({ lanes: ['MID', 'TOP'] }, ['TOP', 'BOT'])).toEqual(['TOP'])
    const pool = [
      { name: 'b', stat_total: 30, lanes: ['MID' as const] },
      { name: 'a', stat_total: 30, lanes: ['TOP' as const, 'MID' as const] },
      { name: 'c', stat_total: 40, lanes: ['BOT' as const] },
    ]
    expect(filterPool(pool, null).map((p) => p.name)).toEqual(['c', 'a', 'b'])
    expect(filterPool(pool, 'MID').map((p) => p.name)).toEqual(['a', 'b'])
    expect(filterPool(pool, null, 'C').map((p) => p.name)).toEqual(['c'])
  })
})
