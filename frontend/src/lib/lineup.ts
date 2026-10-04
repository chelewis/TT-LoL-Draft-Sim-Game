import type { Lane } from '../api/types'
import { LANES } from '../api/types'

/** A side's lineup: which champion and which player (by id) is in each lane. */
export interface Lineup {
  champions: Partial<Record<Lane, number>>
  players: Partial<Record<Lane, number>>
}

export type SwapKind = 'position' | 'champion'

/**
 * Swap two lanes of a lineup, like the client's "Swap for…" menu.
 * position: the two players trade lanes and take their champions with them.
 * champion: the players stay put and trade champions.
 */
export function swapLanes(lineup: Lineup, a: Lane, b: Lane, kind: SwapKind): Lineup {
  const champions = { ...lineup.champions }
  const players = { ...lineup.players }
  ;[champions[a], champions[b]] = [champions[b], champions[a]]
  if (kind === 'position') [players[a], players[b]] = [players[b], players[a]]
  return { champions, players }
}

/** The request body for PUT /games/{id}/lineup. */
export function lineupAssignments(lineup: Lineup): { lane: Lane; champion_id: number; player_id?: number }[] {
  return LANES.filter((lane) => lineup.champions[lane] !== undefined).map((lane) => ({
    lane,
    champion_id: lineup.champions[lane]!,
    ...(lineup.players[lane] !== undefined ? { player_id: lineup.players[lane] } : {}),
  }))
}
