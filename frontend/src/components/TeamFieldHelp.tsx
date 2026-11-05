import type { ReactNode } from 'react'
import Tooltip from './Tooltip'

/** The live simulation numbers behind the team editor's fields (GET /config → team_rules). */
export interface TeamRules {
  styles_enabled: boolean
  primary_bonus: number
  secondary_bonus: number
  scaling_lane_penalty: number
  focus_lane_bonus: number
  focus_cs_bonus: number
  focus_assist_boost: number
  jungle_assist: number
  support_assist: number
  coach_synergy_scale: number
  coach_draft_scale: number
  off_role_penalty: number
}

/** Used until /config loads; the simulation's defaults. */
export const DEFAULT_TEAM_RULES: TeamRules = {
  styles_enabled: true, primary_bonus: 0.10, secondary_bonus: 0.05, scaling_lane_penalty: 0.05,
  focus_lane_bonus: 0.08, focus_cs_bonus: 0.08, focus_assist_boost: 0.25, jungle_assist: 0.45, support_assist: 0.5,
  coach_synergy_scale: 0.02, coach_draft_scale: 0.05, off_role_penalty: 0.15,
}

export type TeamField = 'name' | 'logo' | 'style1' | 'style2' | 'focus1' | 'focus2' | 'coach' | 'roster'

const pct = (x: number, digits = 0) => `${+(x * 100).toFixed(digits)}%`

function StyleEffects({ bonus, r }: { bonus: number; r: TeamRules }) {
  const b = pct(bonus)
  return (
    <ul>
      <li><strong>Early game:</strong> +{b} lane score, and +{b} fight power in early-game fights.</li>
      <li><strong>Scaling:</strong> up to +{b} fight power and objective control as the game goes on (half in the mid game, all of it late), but −{pct(r.scaling_lane_penalty)} lane score.</li>
      <li><strong>Teamfight:</strong> +{b} fight power when 4 or more of your players fight.</li>
      <li><strong>Skirmish:</strong> +{b} fight power when 3 or fewer of your players fight.</li>
    </ul>
  )
}

function FocusEffects({ share, r }: { share: number; r: TeamRules }) {
  const boosted = (base: number) => pct(base * (1 + r.focus_assist_boost * share), 1)
  return (
    <ul>
      <li><strong>Top / Mid:</strong> +{pct(r.focus_lane_bonus * share, 1)} lane score and +{pct(r.focus_cs_bonus * share, 1)} CS for that player.</li>
      <li><strong>Bot:</strong> +{pct(r.focus_lane_bonus * share, 1)} lane score.</li>
      <li><strong>Jungle:</strong> +{pct(r.focus_lane_bonus * share, 1)} lane score, and the jungler shares more of their lane score with every lane ({pct(r.jungle_assist)} → {boosted(r.jungle_assist)}).</li>
      <li><strong>Support:</strong> +{pct(r.focus_lane_bonus * share, 1)} lane score, and the support shares more with Bot ({pct(r.support_assist)} → {boosted(r.support_assist)}).</li>
    </ul>
  )
}

function content(field: TeamField, r: TeamRules): { label: string; body: ReactNode } {
  const synergy = `Scaled by your coach's Synergy (±${pct(r.coach_synergy_scale)} per point from 5).`
  switch (field) {
    case 'name':
      return { label: 'Team name', body: <p>How your team appears in lobbies, drafts and match results. It has no effect on the simulation.</p> }
    case 'logo':
      return { label: 'Short logo text', body: <p>Up to 8 characters shown as the team's badge. Cosmetic only.</p> }
    case 'style1':
      return {
        label: 'Primary playstyle',
        body: <>
          <p>Your team's main game plan. Its bonus is <strong>+{pct(r.primary_bonus)}</strong>. {synergy}</p>
          <StyleEffects bonus={r.primary_bonus} r={r} />
          <p className="muted">Lane score turns into lane gold, and lane score plus gold make up each player's strength in fights. Team notes suggests the style that fits your roster.</p>
          {!r.styles_enabled && <p className="muted">Playstyles are currently switched off in the simulation settings.</p>}
        </>,
      }
    case 'style2':
      return {
        label: 'Secondary playstyle',
        body: <>
          <p>A second game plan at half strength: <strong>+{pct(r.secondary_bonus)}</strong>. It must differ from the primary. {synergy}</p>
          <StyleEffects bonus={r.secondary_bonus} r={r} />
          <p className="muted">A team needs two playstyles to be ready to play. Early game and Scaling pull against each other, because Scaling costs lane score.</p>
        </>,
      }
    case 'focus1':
      return {
        label: 'Focus lane 1',
        body: <>
          <p>The lane your team plays around in the lane phase. {synergy}</p>
          <FocusEffects share={1} r={r} />
          <p className="muted">A stronger lane wins more lane gold, which carries into every fight.</p>
        </>,
      }
    case 'focus2':
      return {
        label: 'Focus lane 2',
        body: <>
          <p>A second focus lane with <strong>half</strong> the effect of focus lane 1. {synergy}</p>
          <FocusEffects share={0.5} r={r} />
        </>,
      }
    case 'coach':
      return {
        label: 'Coach',
        body: <>
          <p>A team needs a coach to play. Both ratings count from 5 (neutral):</p>
          <ul>
            <li><strong>Draft:</strong> each point above 5 makes the bonus from a favourable lane matchup {pct(r.coach_draft_scale)} bigger, so a ×1.25 matchup becomes ×{(1 + 0.25 * (1 + 5 * r.coach_draft_scale)).toFixed(3)} at Draft 10. Points below 5 shrink it. Unfavourable matchups are unaffected.</li>
            <li><strong>Synergy:</strong> each point from 5 makes every playstyle bonus, focus bonus and lane assist {pct(r.coach_synergy_scale)} bigger or smaller ({pct(5 * r.coach_synergy_scale)} at 10, −{pct(5 * r.coach_synergy_scale)} at 0).</li>
          </ul>
        </>,
      }
    case 'roster':
      return {
        label: 'Roster',
        body: <>
          <p>One player per lane. Each lane lists players whose main or secondary role is that lane.</p>
          <ul>
            <li>Aggression, Awareness, Positioning and Damage set lane score with each champion. Aggression also decides who starts fights, Awareness + Positioning win objectives, Damage adds fight power and CS adds gold.</li>
            <li>The champion pool sets comfort: the first pick is best, and champions outside the pool are a penalty. Champions not normally played in a lane cost {pct(r.off_role_penalty)} lane score, unless they are in the player's top three.</li>
            <li>Players above the stat ceiling (⚠) can still play, but your opponent sees a warning.</li>
          </ul>
        </>,
      }
  }
}

/** An ⓘ icon that explains a team editor field on hover, focus or tap. */
export default function TeamFieldHelp({ field, rules }: { field: TeamField; rules?: TeamRules }) {
  const { label, body } = content(field, rules ?? DEFAULT_TEAM_RULES)
  return (
    // inside a <label>, a click would also open the field's select: keep the click on the icon
    <span className="field-help" onClick={(e) => e.preventDefault()}>
      <Tooltip label={`About ${label}: what it means and how it affects the game`}
               content={<div className="tip-content"><strong>{label}</strong>{body}</div>}>
        <span className="info-icon" aria-hidden="true">i</span>
      </Tooltip>
    </span>
  )
}
