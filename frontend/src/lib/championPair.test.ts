import { describe, expect, it } from 'vitest'
import type { PairChampion } from '../api/types'
import { championFacts, rateSource, togglePair } from './championPair'

describe('togglePair', () => {
  it('adds up to two champions in order', () => {
    expect(togglePair([], 4)).toEqual([4])
    expect(togglePair([4], 9)).toEqual([4, 9])
  })
  it('removes a champion that is already selected', () => {
    expect(togglePair([4, 9], 4)).toEqual([9])
    expect(togglePair([4], 4)).toEqual([])
  })
  it('drops the oldest when a third is picked', () => {
    expect(togglePair([4, 9], 7)).toEqual([9, 7])
  })
})

describe('rateSource', () => {
  it('says where a win rate came from', () => {
    expect(rateSource({ win_rate: null, games: 0, edited: false })).toMatch(/No data/)
    expect(rateSource({ win_rate: 55, games: 900, edited: true })).toBe('Set by an admin')
    expect(rateSource({ win_rate: 55, games: 1200, edited: false })).toBe(`From ${(1200).toLocaleString()} games`)
    expect(rateSource({ win_rate: 55, games: 0, edited: false })).toBe('Estimated')
  })
})

describe('championFacts', () => {
  it('describes damage, range, scaling and waveclear', () => {
    const c: PairChampion = {
      id: 1, name: 'Jinx', class: 'Marksman', roles: ['BOT'], damage_type: 'P', range: 3, scaling: 3, waveclear: 3,
      strength: 'Offence', weakness: 'Control',
    }
    expect(championFacts(c)).toEqual(['Physical damage', 'Long range', 'Late game', 'Strong waveclear'])
  })
})
