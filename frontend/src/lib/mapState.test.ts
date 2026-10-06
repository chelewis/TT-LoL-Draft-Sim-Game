import { describe, expect, it } from 'vitest'
import type { MatchEvent } from '../api/types'
import { MAP_LAYOUT, buildMapState } from './mapState'

let sequence = 0
const event = (type: string, payload: Record<string, unknown> = {}): MatchEvent =>
  ({ sequence: ++sequence, phase: 'mid', minute: 20, type, payload })

describe('buildMapState', () => {
  it('leaves the map intact when nothing happened', () => {
    const state = buildMapState([event('PHASE_START', { name: 'early' }), event('FIGHT', { winner: 'BLUE' })])
    for (const side of ['BLUE', 'RED'] as const) {
      expect(state[side].towersLost).toEqual({ TOP: 0, MID: 0, BOT: 0 })
      expect(state[side].inhibitorsLost).toEqual({ TOP: false, MID: false, BOT: false })
      expect(state[side].nexusTowersLost).toBe(0)
      expect(state[side].nexusDestroyed).toBe(false)
      expect(state[side].dragons + state[side].barons).toBe(0)
    }
  })

  it('counts towers and inhibitors per lane against the defending side', () => {
    const state = buildMapState([
      event('TOWER', { team: 'BLUE', lane: 'MID' }), event('TOWER', { team: 'BLUE', lane: 'MID' }),
      event('TOWER', { team: 'BLUE', lane: 'MID' }), event('INHIBITOR', { team: 'BLUE', lane: 'MID' }),
      event('TOWER', { team: 'RED', lane: 'TOP' }),
    ])
    expect(state.RED.towersLost).toEqual({ TOP: 0, MID: 3, BOT: 0 })
    expect(state.RED.inhibitorsLost).toEqual({ TOP: false, MID: true, BOT: false })
    expect(state.BLUE.towersLost).toEqual({ TOP: 1, MID: 0, BOT: 0 })
    expect(state.BLUE.inhibitorsLost.MID).toBe(false)
  })

  it('puts nexus towers and the nexus on the losing side', () => {
    const state = buildMapState([
      event('NEXUS_TOWER', { team: 'RED' }), event('NEXUS_TOWER', { team: 'RED' }), event('NEXUS', { team: 'RED' }),
      event('GAME_END', { winner: 'RED', win_condition: 'NEXUS' }),
    ])
    expect(state.BLUE.nexusTowersLost).toBe(2)
    expect(state.BLUE.nexusDestroyed).toBe(true)
    expect(state.RED.nexusTowersLost).toBe(0)
    expect(state.RED.nexusDestroyed).toBe(false)
  })

  it('destroys neither nexus in a game decided on time', () => {
    const state = buildMapState([event('TOWER', { team: 'BLUE', lane: 'BOT' }), event('TIMEOUT', { winner: 'BLUE' })])
    expect(state.BLUE.nexusDestroyed).toBe(false)
    expect(state.RED.nexusDestroyed).toBe(false)
    expect(state.RED.towersLost.BOT).toBe(1)
  })

  it('credits dragons, soul, elder and barons to the team that took them', () => {
    const state = buildMapState([
      ...Array.from({ length: 4 }, () => event('DRAGON', { team: 'BLUE' })), event('DRAGON_SOUL', { team: 'BLUE' }),
      event('DRAGON', { team: 'RED' }), event('ELDER_DRAGON', { team: 'RED' }),
      event('BARON', { team: 'RED' }), event('BARON', { team: 'RED' }),
    ])
    expect(state.BLUE).toMatchObject({ dragons: 4, soul: true, elder: false, barons: 0 })
    expect(state.RED).toMatchObject({ dragons: 2, soul: false, elder: true, barons: 2 })     // the elder counts as a dragon
  })

  it('ignores malformed events', () => {
    const state = buildMapState([event('TOWER', { team: 'BLUE' }), event('TOWER', { team: 'GREEN', lane: 'MID' }), event('TOWER', { team: 'BLUE', lane: 'JUNGLE' })])
    expect(state.RED.towersLost).toEqual({ TOP: 0, MID: 0, BOT: 0 })
  })
})

describe('MAP_LAYOUT', () => {
  it("mirrors red's structures through the centre, swapping top and bottom lanes", () => {
    const { BLUE, RED } = MAP_LAYOUT
    expect(RED.nexus).toEqual({ x: 100 - BLUE.nexus.x, y: 100 - BLUE.nexus.y })
    expect(RED.towers.TOP[0]).toEqual({ x: 100 - BLUE.towers.BOT[0].x, y: 100 - BLUE.towers.BOT[0].y })
    expect(RED.inhibitors.MID).toEqual({ x: 100 - BLUE.inhibitors.MID.x, y: 100 - BLUE.inhibitors.MID.y })
  })

  it('keeps everything on the map', () => {
    for (const side of [MAP_LAYOUT.BLUE, MAP_LAYOUT.RED]) {
      const points = [side.nexus, ...side.nexusTowers, ...Object.values(side.towers).flat(), ...Object.values(side.inhibitors), ...Object.values(side.champions)]
      for (const p of points) {
        expect(p.x).toBeGreaterThan(0); expect(p.x).toBeLessThan(100)
        expect(p.y).toBeGreaterThan(0); expect(p.y).toBeLessThan(100)
      }
    }
  })
})
