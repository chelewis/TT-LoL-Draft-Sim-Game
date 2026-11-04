import type { LaneAnalysis, LaneWheel, Side } from '../../api/types'
import { TIER_LABEL } from '../../lib/format'
import { GRADE_TONE, WHEEL_ARROW, factorLines, formatRate, gradeSummary, rateTone, roleBadge, wheelEdge, wheelText } from '../../lib/matchupPanel'

/** The player's predicted lane performance on their champion as a letter (S best … F worst); "?" when hidden. */
export function GradeChip({ analysis }: { analysis: LaneAnalysis }) {
  const grade = analysis.grade
  const factors = factorLines(analysis.factors)
  const title = [
    gradeSummary(analysis),
    analysis.factors ? `Comfort: ${TIER_LABEL[analysis.factors.comfort_tier] ?? analysis.factors.comfort_tier}` : '',
    ...factors.map((f) => `${f.label} ×${f.value.toFixed(2)}`),
  ]
    .filter(Boolean)
    .join('\n')
  return (
    <span className={`grade-chip ${grade ? `grade-${grade.toLowerCase()} tone-${GRADE_TONE[grade]}` : 'grade-hidden'}`} title={title} aria-label={grade ? `Lane grade ${grade}` : 'Lane grade hidden'}>
      {grade ?? '?'}
    </span>
  )
}

/** Matchup wheel arrows and the counter win rate for one side of a lane. */
export function CounterChip({ wheel, side, rate, baseline, botLane }: { wheel: LaneWheel | null; side: Side; rate: number | null; baseline: number; botLane: boolean }) {
  const edge = wheelEdge(wheel, side)
  const title = `${wheelText(wheel, side)}\nWin rate ${botLane ? 'vs both enemy bot laners' : 'vs lane opponent'}: ${rate === null ? 'no data' : formatRate(rate)}`
  return (
    <span className="counter-chip" title={title}>
      <span className={`counter-wheel edge-${edge}`} aria-label={wheelText(wheel, side)}>{WHEEL_ARROW[edge]}</span>
      <span className={`counter-rate tone-${rateTone(rate, baseline)}`}>{formatRate(rate)}</span>
    </span>
  )
}

/** "Secondary role", "Off-role −15%", "Off-role (pool exempt)", or nothing in the champion's main role. */
export function RoleTag({ analysis }: { analysis: LaneAnalysis }) {
  const badge = roleBadge(analysis.role_status, analysis.off_role_penalty)
  if (!badge) return null
  return (
    <span className={`role-badge role-${badge.kind}`} title={badge.title}>
      {badge.label}
    </span>
  )
}

/** The non-neutral multipliers behind a grade, as a short list. */
export function FactorList({ analysis }: { analysis: LaneAnalysis }) {
  const lines = factorLines(analysis.factors)
  if (!analysis.factors) return <p className="mp-note">Hidden until the game ends.</p>
  return (
    <ul className="mp-factors">
      <li>
        <span>Comfort tier</span>
        <span>{TIER_LABEL[analysis.factors.comfort_tier] ?? analysis.factors.comfort_tier}</span>
      </li>
      {lines.map((f) => (
        <li key={f.label}>
          <span>{f.label}</span>
          <span className={`tone-${f.tone}`}>×{f.value.toFixed(2)}</span>
        </li>
      ))}
    </ul>
  )
}
