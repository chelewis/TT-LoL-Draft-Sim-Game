import { describe, expect, it } from 'vitest'
import type { MetaChampion } from '../api/types'
import { championClasses, filterChampions, hasFilters, NO_FILTERS, sortChampions, startsDescending } from './metaChampions'

const row = (name: string, extra: Partial<MetaChampion>): MetaChampion => ({
  id: name.length, name, class: 'Mage', roles: [], win_rate: 50, role: null, win_rate_source: 'matchups', opponents: 10, pick_rate: 5, ...extra,
})

const rows = [
  row('Ahri', { class: 'Mage', roles: ['MID'], win_rate: 51.2, pick_rate: 12.3 }),
  row('Aatrox', { class: 'Warrior', roles: ['TOP', 'MID'], win_rate: 49.8, pick_rate: 6.5 }),
  row('Lee Sin', { class: 'Warrior', roles: ['JUNGLE'], win_rate: 51.2, pick_rate: 14 }),
  row('Thresh', { class: 'Support', roles: ['SUPPORT'], win_rate: 50.5, pick_rate: 6.5 }),
]
const names = (list: MetaChampion[]) => list.map((r) => r.name)

describe('filterChampions', () => {
  it('keeps everything with no filters', () => {
    expect(filterChampions(rows, NO_FILTERS)).toHaveLength(4)
    expect(hasFilters(NO_FILTERS)).toBe(false)
  })
  it('searches names in any case', () => {
    expect(names(filterChampions(rows, { ...NO_FILTERS, query: '  LEE ' }))).toEqual(['Lee Sin'])
    expect(names(filterChampions(rows, { ...NO_FILTERS, query: 'a' }))).toEqual(['Ahri', 'Aatrox'])
  })
  it('keeps champions that play any chosen lane', () => {
    expect(names(filterChampions(rows, { ...NO_FILTERS, lanes: ['MID'] }))).toEqual(['Ahri', 'Aatrox'])
    expect(names(filterChampions(rows, { ...NO_FILTERS, lanes: ['TOP', 'SUPPORT'] }))).toEqual(['Aatrox', 'Thresh'])
  })
  it('filters by class and combines every filter', () => {
    expect(names(filterChampions(rows, { ...NO_FILTERS, champClass: 'Warrior' }))).toEqual(['Aatrox', 'Lee Sin'])
    const all = { query: 'a', lanes: ['MID' as const], champClass: 'Warrior' }
    expect(names(filterChampions(rows, all))).toEqual(['Aatrox'])
    expect(hasFilters(all)).toBe(true)
  })
})

describe('sortChampions', () => {
  it('sorts by name either way', () => {
    expect(names(sortChampions(rows, { by: 'name', desc: false }))).toEqual(['Aatrox', 'Ahri', 'Lee Sin', 'Thresh'])
    expect(names(sortChampions(rows, { by: 'name', desc: true }))).toEqual(['Thresh', 'Lee Sin', 'Ahri', 'Aatrox'])
  })
  it('sorts by win rate, ties by name', () => {
    expect(names(sortChampions(rows, { by: 'win_rate', desc: true }))).toEqual(['Ahri', 'Lee Sin', 'Thresh', 'Aatrox'])
    expect(names(sortChampions(rows, { by: 'win_rate', desc: false }))).toEqual(['Aatrox', 'Thresh', 'Ahri', 'Lee Sin'])
  })
  it('sorts by pick rate, ties by name', () => {
    expect(names(sortChampions(rows, { by: 'pick_rate', desc: true }))).toEqual(['Lee Sin', 'Ahri', 'Aatrox', 'Thresh'])
  })
  it('does not change the list it was given', () => {
    sortChampions(rows, { by: 'pick_rate', desc: true })
    expect(rows[0].name).toBe('Ahri')
  })
})

describe('column helpers', () => {
  it('starts names ascending and rates descending', () => {
    expect(startsDescending('name')).toBe(false)
    expect(startsDescending('win_rate')).toBe(true)
  })
  it('lists each class once, A to Z', () => {
    expect(championClasses(rows)).toEqual(['Mage', 'Support', 'Warrior'])
  })
})
