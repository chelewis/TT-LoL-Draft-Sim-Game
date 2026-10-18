export type Tone = 'good' | 'bad' | 'even' | 'none'

/** How a win rate reads for the side it belongs to: within a point of the baseline counts as even. */
export function rateTone(rate: number | null | undefined, baseline = 50): Tone {
  if (rate === null || rate === undefined) return 'none'
  if (rate >= baseline + 1) return 'good'
  if (rate <= baseline - 1) return 'bad'
  return 'even'
}

export function formatRate(rate: number | null | undefined): string {
  return rate === null || rate === undefined ? '–' : `${Number.isInteger(rate) ? rate : rate.toFixed(1)}%`
}

export function formatPoints(points: number | null | undefined): string {
  if (points === null || points === undefined) return '–'
  return `${points > 0 ? '+' : ''}${points.toFixed(1)} pts`
}

/** Physical share of a damage mix, 0..1 (an even split when there is no damage at all). */
export function physicalShare(profile: { physical: number; magic: number }): number {
  const total = profile.physical + profile.magic
  return total > 0 ? profile.physical / total : 0.5
}
