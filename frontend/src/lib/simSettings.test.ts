import { describe, expect, it } from 'vitest'
import type { SimulationSettingField } from '../api/types'
import { formatSetting, groupFields, parseSetting, shown, toValues, type Drafts } from './simSettings'

const scale: SimulationSettingField = {
  path: 'win_rates.lane_counter_scale', group: 'Champion win rates', label: 'Lane counter strength', help: '',
  kind: 'number', min: 0, max: 0.2, step: 0.005, default: 0.03, value: 0.03,
}
const enabled: SimulationSettingField = {
  path: 'damage_balance.enabled', group: 'Damage balance', label: 'Penalize one-sided damage', help: '',
  kind: 'bool', default: true, value: true,
}
const fields = [scale, enabled]

describe('parseSetting', () => {
  it('accepts numbers inside the range', () => {
    expect(parseSetting(scale, '0.05')).toBe(0.05)
    expect(parseSetting(scale, ' 0 ')).toBe(0)
  })
  it('rejects blank, non-numeric and out-of-range text', () => {
    expect(parseSetting(scale, '')).toBeUndefined()
    expect(parseSetting(scale, 'abc')).toBeUndefined()
    expect(parseSetting(scale, '0.5')).toBeUndefined()
    expect(parseSetting(scale, '-1')).toBeUndefined()
  })
  it('takes switches as booleans only', () => {
    expect(parseSetting(enabled, false)).toBe(false)
    expect(parseSetting(enabled, 'false')).toBeUndefined()
  })
})

describe('shown', () => {
  it('prefers the draft, else the saved value', () => {
    expect(shown(scale, new Map())).toBe('0.03')
    expect(shown(scale, new Map([[scale.path, '0.0']]))).toBe('0.0')
    expect(shown(enabled, new Map())).toBe(true)
  })
})

describe('toValues', () => {
  it('sends only real changes', () => {
    const drafts: Drafts = new Map<string, string | boolean>([[scale.path, '0.030'], [enabled.path, false]])
    expect(toValues(fields, drafts)).toEqual({ values: { 'damage_balance.enabled': false }, invalid: [] })
  })
  it('lists invalid drafts', () => {
    expect(toValues(fields, new Map([[scale.path, '9']]))).toEqual({ values: {}, invalid: [scale.path] })
  })
})

describe('groupFields', () => {
  it('keeps server order within and across groups', () => {
    expect(groupFields(fields).map(([group, list]) => [group, list.map((f) => f.path)])).toEqual([
      ['Champion win rates', [scale.path]],
      ['Damage balance', [enabled.path]],
    ])
  })
})

describe('formatSetting', () => {
  it('formats switches and numbers', () => {
    expect(formatSetting(true)).toBe('On')
    expect(formatSetting(0.25)).toBe('0.25')
  })
})
