import type { PairChampion, PairRate } from '../api/types'

export const DAMAGE_LABEL: Record<string, string> = { P: 'Physical', M: 'Magic', PM: 'Mixed' }
export const RANGE_LABEL: Record<number, string> = { 1: 'Melee', 2: 'Short range', 3: 'Long range' }
export const SCALING_LABEL: Record<number, string> = { 1: 'Early game', 2: 'Even curve', 3: 'Late game' }
export const WAVECLEAR_LABEL: Record<number, string> = { 1: 'Weak waveclear', 2: 'Average waveclear', 3: 'Strong waveclear' }

/** The champions selected for a pair after clicking `id`: a selected one is removed, otherwise it's added, and
 * past two the oldest is dropped. Order is kept (first = the pair's first champion). */
export function togglePair(selected: number[], id: number): number[] {
  if (selected.includes(id)) return selected.filter((x) => x !== id)
  return [...selected, id].slice(-2)
}

/** Where a win rate came from, for the caption under it. */
export function rateSource(rate: Pick<PairRate, 'win_rate' | 'games' | 'edited'>): string {
  if (rate.win_rate === null) return 'No data yet, so no bonus or penalty'
  if (rate.edited) return 'Set by an admin'
  if (rate.games > 0) return `From ${rate.games.toLocaleString()} games`
  return 'Estimated'
}

/** The short facts shown under a champion's name. */
export function championFacts(c: PairChampion): string[] {
  return [
    DAMAGE_LABEL[c.damage_type] ? `${DAMAGE_LABEL[c.damage_type]} damage` : c.damage_type,
    RANGE_LABEL[c.range] ?? `Range ${c.range}`,
    SCALING_LABEL[c.scaling] ?? `Scaling ${c.scaling}`,
    WAVECLEAR_LABEL[c.waveclear] ?? `Waveclear ${c.waveclear}`,
  ]
}
