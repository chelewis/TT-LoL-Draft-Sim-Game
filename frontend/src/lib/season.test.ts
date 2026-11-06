import { describe, expect, it } from 'vitest'
import type { SeasonMatch, SeasonTeamRef, StandingRow } from '../api/types'
import {
  bracketSlots, formatLabel, playoffChoices, seriesSummary, swissWins,
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
  completed_at: null, ...patch,
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
