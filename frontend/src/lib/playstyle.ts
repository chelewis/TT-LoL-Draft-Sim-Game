import type { PlaystyleEffect, PlaystyleTag, TagEvidence } from '../api/types'
import { formatMetric, titleCase } from './format'

/** The server's limit on tags per player (game/config.py PLAYSTYLE_MAX_TAGS). */
export const MAX_TAGS = 5

/** Player-facing names for the simulation hooks (game/config.py PLAYSTYLE_HOOKS). */
export const HOOK_LABEL: Record<string, string> = {
  lane_score: 'Lane phase score',
  initiative: 'Fight initiative',
  objective: 'Objective control',
  tower: 'Tower trades',
  cs_rate: 'CS per minute',
  fight_perf: 'Fight performance',
  survival: 'Survival in fights',
  off_pool_penalty: 'Off-pool penalty',
  pool_best_bonus: 'Best champion bonus',
}

const pct = (v: number) => `${Math.round(Math.abs(v) * 1000) / 10}%`

/** One effect in words, e.g. "CS per minute +4%" or "Off-pool penalty halved". */
export function effectText(effect: PlaystyleEffect): string {
  const label = HOOK_LABEL[effect.hook] ?? effect.hook
  if (effect.hook === 'off_pool_penalty') {
    if (effect.value >= 1) return `${label} removed`
    if (effect.value === 0.5) return `${label} halved`
    return effect.value > 0 ? `${label} ${pct(effect.value)} smaller` : `${label} ${pct(effect.value)} bigger`
  }
  return `${label} ${effect.value > 0 ? '+' : '−'}${pct(effect.value)}`
}

/** Why the account earned the tag, in words. */
export function evidenceText(e: TagEvidence | null | undefined): string | null {
  if (!e) return null
  if (e.source === 'challenge') {
    const top = e.percentile != null ? ` (top ${Math.max(0.1, Math.round(e.percentile * 1000) / 10)}%)` : ''
    return `${titleCase(e.level ?? '')} in ${e.challenge_name ?? `challenge ${e.challenge_id}`}${top}`
  }
  if (e.value == null || e.threshold == null) return e.label ?? null
  const unit = e.unit ?? 'number'
  return `${e.label}: ${formatMetric(e.value, unit)} (${e.op === '>=' ? 'at least' : 'at most'} ${formatMetric(e.threshold, unit)})`
}

/** Positive tags first, then negative, each in the order given. */
export function sortTags<T extends Pick<PlaystyleTag, 'polarity'>>(tags: T[]): T[] {
  return [...tags.filter((t) => t.polarity === 'positive'), ...tags.filter((t) => t.polarity !== 'positive')]
}
