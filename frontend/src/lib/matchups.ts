import type { MatchupCell, MatchupKind } from '../api/types'

/** A stored cell. The win rate is from the lower champion id's side (only matters for the against-team matrix). */
export interface StoredCell {
  winRate: number | null
  games: number
  edited: boolean
}

/** Unsaved edits, keyed like the stored cells and from the same side. */
export type Pending = Map<string, number | null>

export interface CellView {
  winRate: number | null
  games: number
  edited: boolean
  pending: boolean
}

export const pairKey = (a: number, b: number): string => (a < b ? `${a}:${b}` : `${b}:${a}`)

const round1 = (value: number): number => Math.round(value * 10) / 10

export function indexCells(cells: MatchupCell[]): Map<string, StoredCell> {
  return new Map(cells.map(([a, b, winRate, games, edited]) => [pairKey(a, b), { winRate, games, edited }]))
}

/** Same team: a pair has one win rate. Against team: the other champion's side is 100 minus it. */
function flip(kind: MatchupKind, row: number, col: number, value: number | null): number | null {
  return kind === 'enemy' && row > col && value !== null ? round1(100 - value) : value
}

/** What the matrix shows at (row champion, column champion), unsaved edits included. */
export function readCell(kind: MatchupKind, stored: Map<string, StoredCell>, pending: Pending, row: number, col: number): CellView {
  const key = pairKey(row, col)
  const cell = stored.get(key)
  const isPending = pending.has(key)
  const value = isPending ? pending.get(key) ?? null : cell?.winRate ?? null
  return { winRate: flip(kind, row, col, value), games: cell?.games ?? 0, edited: cell?.edited ?? false, pending: isPending }
}

/** Unsaved edits after setting (row, col). Setting a cell back to its saved value drops the edit. */
export function writeCell(kind: MatchupKind, stored: Map<string, StoredCell>, pending: Pending, row: number, col: number, value: number | null): Pending {
  const key = pairKey(row, col)
  const canonical = flip(kind, row, col, value === null ? null : round1(value))
  const next = new Map(pending)
  if (canonical === (stored.get(key)?.winRate ?? null)) next.delete(key)
  else next.set(key, canonical)
  return next
}

export function toChanges(pending: Pending): { a: number; b: number; win_rate: number | null }[] {
  return [...pending].map(([key, winRate]) => {
    const [a, b] = key.split(':').map(Number)
    return { a, b, win_rate: winRate }
  })
}

/** Typed text to a win rate: null for an empty box (clear the cell), undefined when it is not a valid 0-100 number. */
export function parseRate(text: string): number | null | undefined {
  const trimmed = text.trim().replace(',', '.').replace(/%$/, '')
  if (trimmed === '') return null
  const value = Number(trimmed)
  return Number.isFinite(value) && value >= 0 && value <= 100 ? round1(value) : undefined
}

export const formatRate = (winRate: number | null): string => (winRate === null ? '–' : winRate.toFixed(1))

/** How far from 50 a cell is at full colour, in percentage points. */
export const COLOR_SPAN = 8

/** Cell tint: nothing at 50, blue above and red below, stronger the further away. */
export function cellColor(winRate: number | null): string | undefined {
  if (winRate === null || winRate === 50) return undefined
  const strength = Math.min(Math.abs(winRate - 50) / COLOR_SPAN, 1)
  const alpha = (0.12 + 0.6 * strength).toFixed(2)
  return winRate > 50 ? `rgba(79, 140, 255, ${alpha})` : `rgba(255, 91, 110, ${alpha})`
}
