import type { CpuStrength, SeasonBracketRound, SeasonFormat, SeasonMatch, SeasonOptions, SeasonStatus, SeasonTeamRef, StandingRow } from '../api/types'
import { seriesShort } from './format'

export const SEASON_STATUS_LABELS: Record<SeasonStatus, string> = {
  SETUP: 'Setting up',
  PLAYER_DRAFT: 'Player draft',
  REGULAR: 'In progress',
  PLAYOFFS: 'Playoffs',
  COMPLETED: 'Finished',
  CANCELLED: 'Cancelled',
}

export const CPU_STRENGTH_LABELS: Record<CpuStrength, string> = {
  WEAKER: 'Weaker: CPU teams sit well below the rules\' stat limits',
  EVEN: 'Even: CPU teams sit a little below the limits',
  STRONGER: 'Stronger: CPU teams are built right up to the limits',
}

/** Rounds in a round robin of `teams` teams (an odd count gives every team one bye). */
export function roundRobinRounds(teams: number, double: boolean): number {
  if (teams < 2) return 0
  const rounds = teams % 2 === 0 ? teams - 1 : teams
  return double ? rounds * 2 : rounds
}

/** Matches each team plays in a round robin of `teams` teams. */
export function matchesPerTeam(teams: number, double: boolean): number {
  return Math.max(0, teams - 1) * (double ? 2 : 1)
}

export function roundLabel(round: number, total: number): string {
  return total > 0 ? `Round ${round} of ${total}` : `Round ${round}`
}

export function recordLabel(row: { wins: number; losses: number }): string {
  return `${row.wins}-${row.losses}`
}

/** Game differential with its sign ("+3", "0", "-2"). */
export function diffLabel(diff: number): string {
  return diff > 0 ? `+${diff}` : String(diff)
}

/** The other team in a match, from `teamId`'s point of view. */
export function opponentOf(match: SeasonMatch, teamId: number): SeasonTeamRef | null {
  if (match.home?.id === teamId) return match.away
  if (match.away?.id === teamId) return match.home
  return null
}

/** "W 2-1" / "L 0-1" from `teamId`'s point of view; null until the match is decided or if the team isn't in it. */
export function resultFor(match: SeasonMatch, teamId: number): string | null {
  if (match.status !== 'COMPLETED') return null
  const home = match.home?.id === teamId
  if (!home && match.away?.id !== teamId) return null
  const mine = home ? match.home_score : match.away_score
  const theirs = home ? match.away_score : match.home_score
  return `${match.winner_team_id === teamId ? 'W' : 'L'} ${mine}-${theirs}`
}

/** The score line of a match ("2 - 1"), or "vs" before it's played. */
export function scoreLine(match: SeasonMatch): string {
  return match.status === 'SCHEDULED' ? 'vs' : `${match.home_score} - ${match.away_score}`
}

export type StandingsKey = 'rank' | 'name' | 'wins' | 'losses' | 'game_diff' | 'played'

/** The table re-sorted by a column; ties keep the official order (rank). */
export function sortStandings(rows: StandingRow[], key: StandingsKey, descending: boolean): StandingRow[] {
  const value = (r: StandingRow): number | string => (key === 'name' ? r.team.name.toLowerCase() : r[key])
  return [...rows].sort((a, b) => {
    const va = value(a)
    const vb = value(b)
    if (va !== vb) {
      const order = va < vb ? -1 : 1
      return descending ? -order : order
    }
    return a.rank - b.rank
  })
}

/** What to do next with your match, for the main button. */
export function myMatchAction(match: SeasonMatch | null): 'PLAY' | 'CONTINUE' | 'DONE' | null {
  if (!match) return null
  if (match.status === 'COMPLETED') return 'DONE'
  return match.games.length ? 'CONTINUE' : 'PLAY'
}

/** Swiss sizes the server accepts, with wins to qualify (= losses to go out). */
export const SWISS_TEAM_COUNTS = [8, 16] as const
export const swissWins = (teams: number): number => Math.max(1, Math.log2(teams) - 1)

/** Playoff sizes that fit a league of `teams`. */
export function playoffChoices(teams: number): number[] {
  return [2, 4, 8].filter((n) => n <= teams)
}

/** "Round robin + top 4 playoffs", "Swiss stage + 8-team bracket". */
export function formatLabel(format: SeasonFormat, options: Pick<SeasonOptions, 'playoff_size' | 'rr_double'>): string {
  if (format === 'SWISS') return `Swiss stage + ${options.playoff_size}-team bracket`
  const league = options.rr_double ? 'Double round robin' : 'Round robin'
  if (!options.playoff_size) return league
  return options.playoff_size === 2 ? `${league} + final` : `${league} + top ${options.playoff_size} playoffs`
}

/** "Bo1 league · Bo3 playoffs · Bo5 final" (playoffs left out when there are none). */
export function seriesSummary(format: SeasonFormat, o: Pick<SeasonOptions, 'regular_series' | 'playoff_size' | 'playoff_series' | 'final_series'>): string {
  const parts = [`${seriesShort(o.regular_series)} ${format === 'SWISS' ? 'Swiss' : 'league'}`]
  if (o.playoff_size > 2) parts.push(`${seriesShort(o.playoff_series)} playoffs`)
  if (o.playoff_size >= 2) parts.push(`${seriesShort(o.final_series)} final`)
  return parts.join(' · ')
}

/** A bracket round's boxes: the drawn matches, then empty (TBD) slots up to the round's size. */
export function bracketSlots(round: SeasonBracketRound): (SeasonMatch | null)[] {
  return Array.from({ length: round.slots }, (_, i) => round.matches[i] ?? null)
}
