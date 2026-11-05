import { describe, expect, it } from 'vitest'
import type { AdminChampion, AdminChampionColumn, AdminChampionField } from '../api/types'
import { draftKey, filterAndSort, parseValue, shownValue, toChanges, type ChampionDrafts } from './championAdmin'

const int = (min: number, max: number): AdminChampionField => ({ kind: 'int', min, max, choices: [] })
const pct: AdminChampionField = { kind: 'float', min: 0, max: 100, choices: [] }
const type: AdminChampionField = { kind: 'choice', min: 0, max: 0, choices: ['P', 'M', 'PM'] }

const FIELDS = {
  win_rate: pct, pick_rate: pct, style: int(1, 10), difficulty: int(1, 3), damage_type: type,
  damage: int(0, 5), sturdiness: int(0, 5), crowd_control: int(0, 5), mobility: int(0, 5), utility: int(0, 5),
  scaling: int(1, 3), attack_range: int(1, 3), waveclear: int(1, 3),
} satisfies Record<AdminChampionColumn, AdminChampionField>

const champ = (id: number, name: string, extra: Partial<AdminChampion> = {}): AdminChampion => ({
  id, name, class: 'Mage', enabled: true, roles: ['MID'], edited: [], seed: {}, in_seed: true, updated_at: null,
  win_rate: 50, pick_rate: 5, style: 5, difficulty: 2, damage_type: 'M', damage: 2, sturdiness: 1,
  crowd_control: 2, mobility: 2, utility: 1, scaling: 2, attack_range: 2, waveclear: 2, ...extra,
})

describe('parseValue', () => {
  it('accepts values in range and rounds rates', () => {
    expect(parseValue(pct, ' 51.236 ')).toBe(51.24)
    expect(parseValue(int(1, 3), '3')).toBe(3)
    expect(parseValue(type, 'PM')).toBe('PM')
  })
  it('rejects blanks, out of range, fractions for whole numbers and unknown choices', () => {
    expect(parseValue(pct, '')).toBeUndefined()
    expect(parseValue(pct, '100.1')).toBeUndefined()
    expect(parseValue(int(1, 3), '2.5')).toBeUndefined()
    expect(parseValue(int(1, 3), 'abc')).toBeUndefined()
    expect(parseValue(type, 'X')).toBeUndefined()
  })
})

describe('toChanges', () => {
  const champions = [champ(1, 'Ahri'), champ(2, 'Zed')]

  it('sends only values that differ from the saved ones', () => {
    const drafts: ChampionDrafts = new Map([
      [draftKey(1, 'pick_rate'), '12.5'],
      [draftKey(1, 'win_rate'), '50'],          // same as saved
      [draftKey(2, 'damage_type'), 'P'],
    ])
    expect(toChanges(champions, FIELDS, drafts)).toEqual({
      changes: [{ id: 1, values: { pick_rate: 12.5 } }, { id: 2, values: { damage_type: 'P' } }],
      count: 2,
      invalid: [],
    })
  })

  it('lists cells that cannot be saved', () => {
    const drafts: ChampionDrafts = new Map([[draftKey(2, 'scaling'), '9']])
    expect(toChanges(champions, FIELDS, drafts).invalid).toEqual(['Zed Scaling'])
  })
})

describe('shownValue', () => {
  it('shows the draft over the saved value', () => {
    const c = champ(1, 'Ahri')
    expect(shownValue(c, 'pick_rate', new Map())).toBe('5')
    expect(shownValue(c, 'pick_rate', new Map([[draftKey(1, 'pick_rate'), '7']]))).toBe('7')
  })
})

describe('filterAndSort', () => {
  const champions = [champ(1, 'Ahri', { pick_rate: 12 }), champ(2, 'Zed', { pick_rate: 20, edited: ['pick_rate'] }), champ(3, 'Annie', { class: 'Support', pick_rate: 12 })]

  it('searches by name or class and can show edited champions only', () => {
    expect(filterAndSort(champions, 'an', false, { by: 'name', desc: false }).map((c) => c.name)).toEqual(['Annie'])
    expect(filterAndSort(champions, 'support', false, { by: 'name', desc: false }).map((c) => c.name)).toEqual(['Annie'])
    expect(filterAndSort(champions, '', true, { by: 'name', desc: false }).map((c) => c.name)).toEqual(['Zed'])
  })

  it('sorts by a column, ties by name', () => {
    expect(filterAndSort(champions, '', false, { by: 'pick_rate', desc: true }).map((c) => c.name)).toEqual(['Zed', 'Ahri', 'Annie'])
  })
})
