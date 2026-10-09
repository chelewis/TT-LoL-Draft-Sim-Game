import type { Lane, MatchEvent, Side } from '../api/types'

/** Lanes that have structures (the jungle and support roles have none). */
export type StructureLane = 'TOP' | 'MID' | 'BOT'
export const STRUCTURE_LANES: StructureLane[] = ['TOP', 'MID', 'BOT']
export const TOWERS_PER_LANE = 3
export const NEXUS_TOWERS = 2

/** One team's side of the map when the game ended: what it lost and which neutral objectives it took. */
export interface SideMapState {
  towersLost: Record<StructureLane, number>      // 0-3 per lane; the outer tower falls first
  inhibitorsLost: Record<StructureLane, boolean>
  nexusTowersLost: number                        // 0-2
  nexusDestroyed: boolean
  dragons: number
  soul: boolean
  elder: boolean
  barons: number
}

export type MapState = Record<Side, SideMapState>

const emptySide = (): SideMapState => ({
  towersLost: { TOP: 0, MID: 0, BOT: 0 },
  inhibitorsLost: { TOP: false, MID: false, BOT: false },
  nexusTowersLost: 0,
  nexusDestroyed: false,
  dragons: 0,
  soul: false,
  elder: false,
  barons: 0,
})

const other = (s: Side): Side => (s === 'BLUE' ? 'RED' : 'BLUE')
const isSide = (v: unknown): v is Side => v === 'BLUE' || v === 'RED'
const isStructureLane = (v: unknown): v is StructureLane => v === 'TOP' || v === 'MID' || v === 'BOT'

/**
 * Replay the event log into the final state of the map. An event's `team` is the team that did the thing, so
 * a destroyed structure is recorded against the other side.
 */
export function buildMapState(events: MatchEvent[]): MapState {
  const state: MapState = { BLUE: emptySide(), RED: emptySide() }
  for (const e of events) {
    const team = e.payload.team
    if (!isSide(team)) continue
    const mine = state[team]
    const theirs = state[other(team)]
    const lane = e.payload.lane
    switch (e.type) {
      case 'TOWER':
        if (isStructureLane(lane)) theirs.towersLost[lane] = Math.min(TOWERS_PER_LANE, theirs.towersLost[lane] + 1)
        break
      case 'INHIBITOR':
        if (isStructureLane(lane)) theirs.inhibitorsLost[lane] = true
        break
      case 'NEXUS_TOWER':
        theirs.nexusTowersLost = Math.min(NEXUS_TOWERS, theirs.nexusTowersLost + 1)
        break
      case 'NEXUS':
        theirs.nexusDestroyed = true
        break
      case 'DRAGON':
        mine.dragons += 1
        break
      case 'DRAGON_SOUL':
        mine.soul = true
        break
      case 'ELDER_DRAGON':
        mine.dragons += 1
        mine.elder = true
        break
      case 'BARON':
        mine.barons += 1
        break
    }
  }
  return state
}

// ------------------------------------------------------------------ layout
/** A point on the map in percent of its width and height; (0, 0) is the top-left corner. */
export interface Point { x: number; y: number }

export interface SideLayout {
  nexus: Point
  nexusTowers: Point[]
  towers: Record<StructureLane, Point[]>          // outer tower first, matching the order they fall
  inhibitors: Record<StructureLane, Point>
  champions: Record<Lane, Point>
}

/**
 * Riot's in-game map units to a point on the minimap image. The playable area runs from about -120 to 14870
 * across and -120 to 14980 up, with the origin in the bottom-left corner.
 */
const fromGame = (x: number, y: number): Point => ({
  x: Math.round(((x + 120) / 14990) * 1000) / 10,
  y: Math.round((100 - ((y + 120) / 15100) * 100) * 10) / 10,
})

/** Blue's base is the bottom-left corner. Structures sit where they stand on Summoner's Rift. */
const BLUE_LAYOUT: SideLayout = {
  // the nexuses sit a little nearer their corner than in game, so the nexus towers stay visible beside them
  nexus: { x: 9, y: 91 },
  nexusTowers: [fromGame(1748, 2270), fromGame(2177, 1807)],
  towers: {
    TOP: [fromGame(981, 10441), fromGame(1512, 6699), fromGame(1169, 4287)],
    MID: [fromGame(5846, 6396), fromGame(5048, 4812), fromGame(3651, 3696)],
    BOT: [fromGame(10504, 1029), fromGame(6919, 1483), fromGame(4281, 1253)],
  },
  inhibitors: { TOP: fromGame(1171, 3571), MID: fromGame(3203, 3208), BOT: fromGame(3452, 1236) },
  // champions stand in their lane beside their opponent, clear of the towers; the bot laners meet at the
  // lane's corner with each support behind their own, back towards their base
  champions: {
    TOP: { x: 8.5, y: 17 },
    JUNGLE: { x: 24, y: 48 },
    MID: { x: 46, y: 54 },
    BOT: { x: 84.5, y: 91.5 },
    SUPPORT: { x: 76.3, y: 91.5 },
  },
}

const RED_LAYOUT: SideLayout = {
  nexus: { x: 91.5, y: 9 },
  nexusTowers: [fromGame(12611, 13084), fromGame(13052, 12612)],
  towers: {
    TOP: [fromGame(4318, 13875), fromGame(7943, 13411), fromGame(10481, 13650)],
    MID: [fromGame(8955, 8510), fromGame(9767, 10113), fromGame(11134, 11207)],
    BOT: [fromGame(13866, 4505), fromGame(13327, 8226), fromGame(13624, 10572)],
  },
  inhibitors: { TOP: fromGame(11261, 13676), MID: fromGame(11598, 11667), BOT: fromGame(13604, 11316) },
  champions: {
    TOP: { x: 19.5, y: 8.5 },
    JUNGLE: { x: 76, y: 52 },
    MID: { x: 54, y: 46 },
    BOT: { x: 92.5, y: 86 },
    SUPPORT: { x: 92.5, y: 75 },
  },
}

export const MAP_LAYOUT: Record<Side, SideLayout> = { BLUE: BLUE_LAYOUT, RED: RED_LAYOUT }
export const BARON_PIT: Point = fromGame(5007, 10471)
export const DRAGON_PIT: Point = fromGame(9866, 4414)
