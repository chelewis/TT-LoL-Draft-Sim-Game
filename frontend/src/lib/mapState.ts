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

/** Blue's base is the bottom-left corner. Red's layout is this one turned half a circle around the centre. */
const BLUE_LAYOUT: SideLayout = {
  nexus: { x: 11, y: 89 },
  nexusTowers: [{ x: 14, y: 81 }, { x: 19, y: 86 }],
  towers: {
    TOP: [{ x: 9, y: 30 }, { x: 9, y: 50 }, { x: 9, y: 67 }],
    MID: [{ x: 38, y: 62 }, { x: 31, y: 69 }, { x: 25, y: 75 }],
    BOT: [{ x: 70, y: 91 }, { x: 50, y: 91 }, { x: 33, y: 91 }],
  },
  inhibitors: { TOP: { x: 9, y: 74 }, MID: { x: 20.5, y: 79.5 }, BOT: { x: 26, y: 91 } },
  champions: {
    TOP: { x: 9, y: 19 },
    JUNGLE: { x: 26, y: 46 },
    MID: { x: 45, y: 56 },
    BOT: { x: 81, y: 76 },
    SUPPORT: { x: 81, y: 88 },
  },
}

const mirror = (p: Point): Point => ({ x: 100 - p.x, y: 100 - p.y })
const mirrorLanes = <T,>(lanes: Record<StructureLane, T>, f: (v: T) => T): Record<StructureLane, T> => ({
  // the lanes swap too: red's top lane is the mirror image of blue's bottom lane
  TOP: f(lanes.BOT), MID: f(lanes.MID), BOT: f(lanes.TOP),
})

const RED_LAYOUT: SideLayout = {
  nexus: mirror(BLUE_LAYOUT.nexus),
  nexusTowers: BLUE_LAYOUT.nexusTowers.map(mirror),
  towers: mirrorLanes(BLUE_LAYOUT.towers, (ps) => ps.map(mirror)),
  inhibitors: mirrorLanes(BLUE_LAYOUT.inhibitors, mirror),
  // champions stand beside their lane opponent, not at the mirrored spot
  champions: {
    TOP: { x: 23, y: 8 },
    JUNGLE: { x: 74, y: 52 },
    MID: { x: 55, y: 42 },
    BOT: { x: 92, y: 76 },
    SUPPORT: { x: 92, y: 88 },
  },
}

export const MAP_LAYOUT: Record<Side, SideLayout> = { BLUE: BLUE_LAYOUT, RED: RED_LAYOUT }
export const BARON_PIT: Point = { x: 35, y: 31 }
export const DRAGON_PIT: Point = { x: 65, y: 69 }
