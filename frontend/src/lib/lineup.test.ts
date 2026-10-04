import { describe, expect, it } from 'vitest'
import { lineupAssignments, swapLanes, type Lineup } from './lineup'

const lineup: Lineup = {
  champions: { TOP: 1, JUNGLE: 2, MID: 3, BOT: 4, SUPPORT: 5 },
  players: { TOP: 10, JUNGLE: 20, MID: 30, BOT: 40, SUPPORT: 50 },
}

describe('swapLanes', () => {
  it('champion swap: players stay, champions trade', () => {
    const next = swapLanes(lineup, 'BOT', 'SUPPORT', 'champion')
    expect(next.champions).toEqual({ TOP: 1, JUNGLE: 2, MID: 3, BOT: 5, SUPPORT: 4 })
    expect(next.players).toEqual(lineup.players)
  })
  it('position swap: players trade lanes and keep their champions', () => {
    const next = swapLanes(lineup, 'TOP', 'MID', 'position')
    expect(next.players).toEqual({ TOP: 30, JUNGLE: 20, MID: 10, BOT: 40, SUPPORT: 50 })
    expect(next.champions).toEqual({ TOP: 3, JUNGLE: 2, MID: 1, BOT: 4, SUPPORT: 5 })
  })
  it('does not change the original', () => {
    swapLanes(lineup, 'TOP', 'MID', 'position')
    expect(lineup.champions.TOP).toBe(1)
  })
})

describe('lineupAssignments', () => {
  it('lists lanes in order with their champion and player', () => {
    expect(lineupAssignments(lineup)[0]).toEqual({ lane: 'TOP', champion_id: 1, player_id: 10 })
    expect(lineupAssignments({ champions: { MID: 3 }, players: {} })).toEqual([{ lane: 'MID', champion_id: 3 }])
  })
})
