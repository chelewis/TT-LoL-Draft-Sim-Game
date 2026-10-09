import { describe, expect, it } from 'vitest'
import type { MatchupCell } from '../api/types'
import { cellColor, formatRate, indexCells, pairKey, parseRate, readCell, toChanges, writeCell, type Pending } from './matchups'

const cells: MatchupCell[] = [
  [1, 2, 55, 40, false],
  [1, 3, null, 0, true],
]
const stored = indexCells(cells)
const none: Pending = new Map()

describe('pairKey', () => {
  it('is the same either way round', () => {
    expect(pairKey(7, 3)).toBe('3:7')
    expect(pairKey(3, 7)).toBe('3:7')
  })
})

describe('readCell', () => {
  it('reads a same-team pair identically from both sides', () => {
    expect(readCell('ally', stored, none, 1, 2)).toEqual({ winRate: 55, games: 40, edited: false, pending: false })
    expect(readCell('ally', stored, none, 2, 1).winRate).toBe(55)
  })
  it('mirrors an against-team pair', () => {
    expect(readCell('enemy', stored, none, 1, 2).winRate).toBe(55)
    expect(readCell('enemy', stored, none, 2, 1).winRate).toBe(45)
  })
  it('reports cleared and missing cells as no data', () => {
    expect(readCell('enemy', stored, none, 3, 1)).toEqual({ winRate: null, games: 0, edited: true, pending: false })
    expect(readCell('ally', stored, none, 8, 9)).toEqual({ winRate: null, games: 0, edited: false, pending: false })
  })
  it('prefers an unsaved edit, including an unsaved clear', () => {
    expect(readCell('ally', stored, new Map([['1:2', 60]]), 2, 1)).toMatchObject({ winRate: 60, pending: true })
    expect(readCell('ally', stored, new Map([['1:2', null]]), 1, 2)).toMatchObject({ winRate: null, pending: true })
  })
})

describe('writeCell', () => {
  it('stores an against-team edit from the lower id side', () => {
    const pending = writeCell('enemy', stored, none, 2, 1, 70)
    expect([...pending]).toEqual([['1:2', 30]])
    expect(readCell('enemy', stored, pending, 2, 1).winRate).toBe(70)
    expect(readCell('enemy', stored, pending, 1, 2).winRate).toBe(30)
  })
  it('stores a same-team edit unchanged and rounds it', () => {
    expect([...writeCell('ally', stored, none, 2, 1, 61.26)]).toEqual([['1:2', 61.3]])
  })
  it('drops the edit when the value goes back to the saved one', () => {
    const pending = writeCell('enemy', stored, none, 1, 2, 70)
    expect(writeCell('enemy', stored, pending, 2, 1, 45).size).toBe(0)
    expect(writeCell('ally', stored, none, 1, 3, null).size).toBe(0)
  })
  it('does not change the map it was given', () => {
    writeCell('ally', stored, none, 1, 2, 70)
    expect(none.size).toBe(0)
  })
})

describe('toChanges', () => {
  it('lists each edit as a pair of ids', () => {
    expect(toChanges(new Map([['1:2', 30], ['4:19', null]]))).toEqual([
      { a: 1, b: 2, win_rate: 30 },
      { a: 4, b: 19, win_rate: null },
    ])
  })
})

describe('parseRate', () => {
  it('accepts numbers from 0 to 100', () => {
    expect(parseRate(' 52.34 ')).toBe(52.3)
    expect(parseRate('52,5%')).toBe(52.5)
    expect(parseRate('0')).toBe(0)
    expect(parseRate('100')).toBe(100)
  })
  it('treats an empty box as clearing the cell', () => {
    expect(parseRate('  ')).toBeNull()
  })
  it('rejects everything else', () => {
    expect(parseRate('abc')).toBeUndefined()
    expect(parseRate('101')).toBeUndefined()
    expect(parseRate('-1')).toBeUndefined()
  })
})

describe('display', () => {
  it('formats to one decimal and marks no data', () => {
    expect(formatRate(52)).toBe('52.0')
    expect(formatRate(null)).toBe('–')
  })
  it('tints away from 50 only', () => {
    expect(cellColor(50)).toBeUndefined()
    expect(cellColor(null)).toBeUndefined()
    expect(cellColor(54)).toContain('79, 140, 255')
    expect(cellColor(46)).toContain('255, 91, 110')
    expect(cellColor(90)).toBe(cellColor(58))
  })
})
