import type { LaneAnalysis, LaneFactors, LaneGrade, LaneWheel, RoleStatus, Side } from '../api/types'

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

// ------------------------------------------------------- lineup-stage lane insights

/** How a lane grade reads: S/A strong picks, B/C fine, D/F poor. */
export const GRADE_TONE: Record<LaneGrade, Tone> = { S: 'good', A: 'good', B: 'even', C: 'even', D: 'bad', F: 'bad' }

/** "Top 8% of the champions they could play here" style summary of a grade's percentile. */
export function gradeSummary(a: Pick<LaneAnalysis, 'grade' | 'percentile'>): string {
  if (a.grade === null || a.percentile === null) return 'Grade hidden: this team’s player data is hidden until the game ends'
  const better = Math.round((1 - a.percentile) * 100)
  return better <= 0
    ? `Grade ${a.grade}: no champion would do better for this player here`
    : `Grade ${a.grade}: about ${better}% of champions would do better for this player here`
}

export type RoleBadge = { label: string; kind: 'off' | 'exempt' | 'secondary' | 'unknown'; title: string }

/** The badge for a champion's role in this lane, or null when it is in its main role (or has no role data). */
export function roleBadge(status: RoleStatus, penalty: number | null): RoleBadge | null {
  switch (status) {
    case 'SECONDARY':
      return { label: 'Secondary role', kind: 'secondary', title: 'One of this champion’s usual roles, but not its most played one. No penalty.' }
    case 'OFF_ROLE_EXEMPT':
      return { label: 'Off-role (pool exempt)', kind: 'exempt', title: 'Not one of this champion’s usual roles, but it is a top pool pick for this player, so there is no penalty.' }
    case 'OFF_ROLE':
      if (penalty === null) return { label: 'Off-role', kind: 'unknown', title: 'Not one of this champion’s usual roles. Their pool is hidden, so it isn’t known whether they are exempt.' }
      if (penalty <= 0) return { label: 'Off-role', kind: 'exempt', title: 'Not one of this champion’s usual roles. The off-role penalty is switched off.' }
      return { label: `Off-role −${Math.round(penalty * 100)}%`, kind: 'off', title: `Not one of this champion’s usual roles: −${Math.round(penalty * 100)}% lane score.` }
    default:
      return null
  }
}

export type WheelEdge = 'win-strong' | 'win' | 'even' | 'lose' | 'lose-strong'

/** This side's result on the matchup wheel. */
export function wheelEdge(wheel: LaneWheel | null, side: Side): WheelEdge {
  if (!wheel || !wheel.winner) return 'even'
  const strong = wheel.kind === 'STRONG'
  if (wheel.winner === side) return strong ? 'win-strong' : 'win'
  return strong ? 'lose-strong' : 'lose'
}

export const WHEEL_ARROW: Record<WheelEdge, string> = { 'win-strong': '▲▲', win: '▲', even: '–', lose: '▼', 'lose-strong': '▼▼' }

/** The wheel from one side's point of view, e.g. "Offence beats Defence · strong (×1.50)". */
export function wheelText(wheel: LaneWheel | null, side: Side): string {
  if (!wheel) return 'No lane opponent yet'
  const mine = side === 'BLUE' ? wheel.blue : wheel.red
  const theirs = side === 'BLUE' ? wheel.red : wheel.blue
  if (!wheel.winner) return `${mine.strength} vs ${theirs.strength}: even on the matchup wheel`
  const winnerMult = wheel.winner === 'BLUE' ? wheel.blue_multiplier : wheel.red_multiplier
  const how = `${wheel.kind === 'STRONG' ? 'strong' : 'slight'} (×${winnerMult.toFixed(2)})`
  return wheel.winner === side
    ? `${mine.strength} beats ${theirs.strength} · ${how}`
    : `${theirs.strength} beats ${mine.strength} · ${how} to the enemy`
}

const FACTOR_LABEL: { key: Exclude<keyof LaneFactors, 'comfort_tier'>; label: string }[] = [
  { key: 'comfort', label: 'Comfort' },
  { key: 'playstyle', label: 'Playstyle' },
  { key: 'strength_fit', label: 'Stats behind the champion’s strength' },
  { key: 'off_role', label: 'Off-role' },
  { key: 'wheel', label: 'Matchup wheel' },
  { key: 'counter', label: 'Counter win rate' },
  { key: 'duo', label: 'Bot lane duo' },
  { key: 'range', label: 'Range' },
  { key: 'scaling', label: 'Champion scaling' },
]

/** The multipliers behind a grade that aren't neutral, e.g. ["Comfort ×1.40", "Matchup wheel ×0.80"]. */
export function factorLines(f: LaneFactors | null): { label: string; value: number; tone: Tone }[] {
  if (!f) return []
  return FACTOR_LABEL.filter(({ key }) => Math.abs(f[key] - 1) >= 0.005).map(({ key, label }) => ({
    label,
    value: f[key],
    tone: f[key] > 1 ? 'good' : 'bad',
  }))
}
