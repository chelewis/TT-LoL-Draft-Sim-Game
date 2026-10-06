import type { Lane, Player, RiotRank, Team, HiddenPlayer } from '../api/types'

export const LANE_LABEL: Record<Lane, string> = {
  TOP: 'Top',
  JUNGLE: 'Jungle',
  MID: 'Mid',
  BOT: 'Bot',
  SUPPORT: 'Support',
}

export const TIER_LABEL: Record<string, string> = {
  BEST: 'Best pick',
  COMFORT: 'Comfort',
  FAMILIAR: 'Familiar',
  VULNERABLE: 'Off-pool',
}

export const TIER_MODIFIER: Record<string, number> = { BEST: 40, COMFORT: 25, FAMILIAR: 10, VULNERABLE: -10 }
const POOL_TIERS = ['BEST', 'COMFORT', 'COMFORT', 'FAMILIAR', 'FAMILIAR']

/** Comfort tier of a champion for a player pool (index 0 = best). Mirrors the server rule. */
export function comfortTier(pool: number[], championId: number): string {
  const position = pool.indexOf(championId)
  return position >= 0 && position < POOL_TIERS.length ? POOL_TIERS[position] : 'VULNERABLE'
}

/** One-line description of the lobby's draft rules, e.g. "Picks only · 45s per pick". */
export function draftRules(s: { bans_enabled: boolean; timers_enabled: boolean; pick_seconds: number; ban_seconds: number }): string {
  const parts = [s.bans_enabled ? 'Bans and picks' : 'Picks only (no bans)']
  if (!s.timers_enabled) parts.push('no timers')
  else parts.push(s.bans_enabled ? `${s.pick_seconds}s per pick, ${s.ban_seconds}s per ban` : `${s.pick_seconds}s per pick`)
  return parts.join(' · ')
}

const RIOT_SOURCE_LABEL: Record<string, string> = { SOLO: 'Ranked solo', FLEX: 'Ranked flex', NORMAL: 'Normal games' }
const RIOT_SOURCE_SHORT: Record<string, string> = { FLEX: 'Flex', NORMAL: 'Normals' }

/** Solo queue is the trusted source; a missing source (older imports) is treated as solo. */
export function isSoloSource(source: string | null | undefined): boolean {
  return !source || source === 'SOLO'
}

export function riotSourceLabel(source: string | null | undefined): string {
  return RIOT_SOURCE_LABEL[source ?? 'SOLO'] ?? 'Ranked solo'
}

/** Short tag for badges, only for non-solo sources (empty for solo). */
export function riotSourceTag(source: string | null | undefined): string {
  return isSoloSource(source) ? '' : (RIOT_SOURCE_SHORT[source as string] ?? 'Other')
}

/** "Emerald II", "Master" or "Unranked"; with `withLp`, "Emerald II · 45 LP". */
export function rankLabel(rank: Pick<RiotRank, 'tier' | 'division' | 'lp'> | null | undefined, withLp = false): string {
  if (!rank?.tier) return 'Unranked'
  const name = [titleCase(rank.tier), rank.division].filter(Boolean).join(' ')
  return withLp && rank.lp != null ? `${name} · ${rank.lp} LP` : name
}

/** Show a metric value the way people read it: percentages as 47%, everything else with 2 decimals. */
export function formatMetric(value: number, unit: 'percent' | 'number'): string {
  return unit === 'percent' ? `${Math.round(value * 1000) / 10}%` : String(Math.round(value * 100) / 100)
}

/** Single player: one person plays both sides. */
export function isSolo(game: { settings: { mode?: string } }): boolean {
  return game.settings.mode === 'SOLO'
}

export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export function titleCase(text: string | null | undefined): string {
  if (!text) return ''
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase()
}

export function isHidden(player: Player | HiddenPlayer | null): player is HiddenPlayer {
  return !!player && 'hidden' in player && player.hidden === true
}

/** Text for the "potentially illegal team" notice shown to both players. */
export function overBudgetNotice(team: Pick<Team, 'over_budget' | 'over_budget_players'>): string {
  if (!team.over_budget) return ''
  const names = team.over_budget_players.map((p) => `${p.name} (+${p.over_by})`).join(', ')
  return `Potentially illegal team: custom players above the stat ceiling: ${names}`
}

export function remainingSeconds(expiresAt: string | null, now: number = Date.now()): number {
  if (!expiresAt) return 0
  return Math.max(0, Math.ceil((Date.parse(expiresAt) - now) / 1000))
}

/** Plain-language lane matchup text for the results screen. */
export function matchupText(matchup: string | null): string {
  if (!matchup) return 'Even matchup'
  const [side, strength] = matchup.split('_')
  return `Favours ${titleCase(side)} ${strength === 'STRONG' ? 'strongly' : 'slightly'}`
}
