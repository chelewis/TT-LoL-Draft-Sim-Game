import { describe, expect, it } from 'vitest'
import type { Lane, MatchEvent, MatchResult, Side } from '../api/types'
import { LANES } from '../api/types'
import { formatGold, playerKey, scoreAt } from './scoreboard'

// every player ends on 600 CS and 10,000 gold; champions are named after their side and lane
const players = (['BLUE', 'RED'] as Side[]).flatMap((team) =>
  LANES.map((lane: Lane) => ({ team, lane, champion: `${team}-${lane}`, cs: 600, gold: 10000 })))
const result = { duration_seconds: 1800, players } as unknown as MatchResult

const gold = (blue: number[], red: number[]) => ({ BLUE: blue, RED: red })
const none = [0, 0, 0, 0, 0]
const event = (sequence: number, minute: number, type: string, payload: Record<string, unknown>): MatchEvent =>
  ({ sequence, phase: 'mid', minute, type, payload })

const laneResult = event(1, 15, 'LANE_RESULT', { lane: 'TOP', winner: 'BLUE', gold_diff: 400, event_gold: gold([400, 0, 0, 0, 0], none) })
const dragon = event(2, 6, 'DRAGON', { team: 'RED', event_gold: gold([400, 0, 0, 0, 0], none) })
const fight = event(3, 18, 'FIGHT', {
  kind: 'SKIRMISH', attacker: 'BLUE', defender: 'RED', attackers: ['TOP', 'MID'], defenders: ['TOP'], winner: 'BLUE',
  kills: { BLUE: 1, RED: 0 }, log: [{ killer: 'BLUE-TOP', victim: 'RED-TOP', team: 'BLUE' }],
  event_gold: gold([700, 0, 150, 0, 0], none),
})
const tower = event(4, 20, 'TOWER', { team: 'BLUE', lane: 'TOP', event_gold: gold([1000, 0, 150, 0, 0], none) })
const end = event(5, 30, 'GAME_END', { event_gold: gold([1000, 0, 150, 0, 0], none) })
const log = [laneResult, dragon, fight, tower, end]

describe('scoreAt', () => {
  it('starts from nothing', () => {
    const score = scoreAt(result, log, [], 0)
    expect(score.teams.BLUE).toMatchObject({ kills: 0, gold: 0, towers: 0, dragons: 0 })
    expect(score.players[playerKey('BLUE', 'TOP')]).toEqual({ kills: 0, deaths: 0, assists: 0, cs: 0, gold: 0, damageDealt: null, damageTaken: null })
  })

  it('credits kills, deaths and assists from a fight', () => {
    const score = scoreAt(result, log, [dragon, laneResult, fight], 1080)
    expect(score.teams.BLUE.kills).toBe(1)
    expect(score.teams.RED.dragons).toBe(1)
    expect(score.players[playerKey('BLUE', 'TOP')]).toMatchObject({ kills: 1, assists: 0 })
    expect(score.players[playerKey('BLUE', 'MID')]).toMatchObject({ kills: 0, assists: 1 })
    expect(score.players[playerKey('RED', 'TOP')]).toMatchObject({ deaths: 1, assists: 0 })
  })

  it('holds the lane winner\'s gold back until the lane result is shown', () => {
    // a third of the way in: 3,000 of the 9,000 CS gold, and the 400 lane gold is still hidden
    expect(scoreAt(result, log, [dragon], 600).players[playerKey('BLUE', 'TOP')]).toMatchObject({ cs: 200, gold: 3000 })
    expect(scoreAt(result, log, [dragon, laneResult], 900).players[playerKey('BLUE', 'TOP')].gold).toBe(4900)
  })

  it('ends on the final result', () => {
    const score = scoreAt(result, log, log, 1800)
    expect(score.players[playerKey('BLUE', 'TOP')]).toEqual({ kills: 1, deaths: 0, assists: 0, cs: 600, gold: 10000, damageDealt: null, damageTaken: null })
    expect(score.teams.BLUE).toMatchObject({ kills: 1, gold: 50000, towers: 1 })
  })

  it('adds up damage from the fights shown so far', () => {
    const damage = { BLUE: { TOP: [1200, 300], MID: [800, 500] }, RED: { TOP: [600, 2000] } }
    const second = event(6, 25, 'FIGHT', { ...fight.payload, damage })
    const withDamage = [laneResult, dragon, { ...fight, payload: { ...fight.payload, damage } }, tower, second, end]
    const before = scoreAt(result, withDamage, [laneResult], 900)
    expect(before.players[playerKey('BLUE', 'TOP')]).toMatchObject({ damageDealt: 0, damageTaken: 0 })
    const after = scoreAt(result, withDamage, withDamage, 1800)
    expect(after.players[playerKey('BLUE', 'TOP')]).toMatchObject({ damageDealt: 2400, damageTaken: 600 })
    expect(after.players[playerKey('RED', 'TOP')]).toMatchObject({ damageDealt: 1200, damageTaken: 4000 })
    expect(after.players[playerKey('RED', 'MID')]).toMatchObject({ damageDealt: 0, damageTaken: 0 })   // never fought
  })

  it('leaves gold out for a game whose events carry none', () => {
    const old = log.map((e) => ({ ...e, payload: { ...e.payload, event_gold: undefined } }))
    const score = scoreAt(result, old, old, 1800)
    expect(score.teams.BLUE.gold).toBeNull()
    expect(score.players[playerKey('BLUE', 'TOP')]).toMatchObject({ kills: 1, cs: 600, gold: null })
  })
})

describe('formatGold', () => {
  it('shows thousands with one decimal', () => {
    expect(formatGold(56649)).toBe('56.6k')
  })
})
