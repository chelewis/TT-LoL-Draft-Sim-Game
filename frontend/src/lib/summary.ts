import type { Lane, MatchEvent, MatchResult, Side } from '../api/types'
import { LANE_LABEL, formatDuration, titleCase } from './format'

const other = (s: Side): Side => (s === 'BLUE' ? 'RED' : 'BLUE')
const sideName = (r: MatchResult, s: Side) => r.teams[s].name || titleCase(s)

/** Plain-language explanation of the outcome. Never exposes formulas or internal scores. */
export function summarize(result: MatchResult): string[] {
  const w = result.winner
  const l = other(w)
  const lines: string[] = []
  const when = formatDuration(result.duration_seconds)

  lines.push(
    result.win_condition === 'NEXUS'
      ? `${sideName(result, w)} destroyed the enemy nexus at ${when}.`
      : `Nobody broke the nexus, so ${sideName(result, w)} took the win on structures after ${when}.`,
  )

  const laneWins = (Object.entries(result.lanes) as [Lane, MatchResult['lanes'][Lane]][])
    .filter(([, lane]) => lane.winner === w)
    .map(([name]) => LANE_LABEL[name])
  if (laneWins.length >= 3) lines.push(`${sideName(result, w)} won the early lanes (${laneWins.join(', ')}).`)
  else if (laneWins.length === 0) lines.push(`${sideName(result, l)} controlled the lanes, but ${sideName(result, w)} won the map.`)

  const tw = result.teams[w]
  const tl = result.teams[l]
  if (tw.dragons > tl.dragons + 0) lines.push(`${sideName(result, w)} took ${tw.dragons} dragons to ${tl.dragons}${tw.soul ? ' and claimed the dragon soul' : ''}.`)
  if (tw.barons > 0) lines.push(`${sideName(result, w)} converted ${tw.barons === 1 ? 'a baron' : `${tw.barons} barons`} into pushes.`)
  if (tw.kills > tl.kills) lines.push(`Kills: ${tw.kills} to ${tl.kills}.`)

  const offPool = result.players.filter((p) => p.comfort_tier === 'VULNERABLE')
  const losingOffPool = offPool.filter((p) => p.team === l)
  if (losingOffPool.length > 0) {
    lines.push(`${sideName(result, l)} had ${losingOffPool.length === 1 ? 'a player' : `${losingOffPool.length} players`} on off-pool champions (${losingOffPool.map((p) => p.name).join(', ')}).`)
  }
  const strongMatchups = Object.entries(result.lanes).filter(([, lane]) => lane.matchup === `${w}_STRONG`)
  if (strongMatchups.length > 0) lines.push(`${sideName(result, w)} had strong lane matchups in ${strongMatchups.map(([n]) => LANE_LABEL[n as Lane]).join(', ')}.`)

  return lines
}

/** One-line description of a simulation event for the play-by-play list. */
export function describeEvent(e: MatchEvent, sideNames: Record<Side, string>): string | null {
  const p = e.payload as Record<string, never>
  const team = (p.team as unknown as Side) ?? undefined
  const who = team ? sideNames[team] : ''
  const clock = `${Math.floor(e.minute)}:${String(Math.floor((e.minute % 1) * 60)).padStart(2, '0')}`
  switch (e.type) {
    case 'LANE_RESULT': {
      const winner = p.winner as unknown as Side | null
      return `Lane phase — ${LANE_LABEL[p.lane as unknown as Lane]}: ${winner ? `${sideNames[winner]} wins the lane` : 'even lane'}.`
    }
    case 'FIGHT': {
      const kills = p.kills as unknown as Record<Side, number>
      const winner = p.winner as unknown as Side | null
      const kind = String(p.kind).toLowerCase()
      const total = kills.BLUE + kills.RED
      const result = winner ? `${sideNames[winner]} win it` : 'it ends even'
      return `${clock} — ${kind}: ${result}${total ? ` (${kills.BLUE}–${kills.RED} kills)` : ''}.`
    }
    case 'DRAGON':
      return `${clock} — ${who} slay a dragon.`
    case 'DRAGON_SOUL':
      return `${clock} — ${who} claim the dragon soul!`
    case 'ELDER_DRAGON':
      return `${clock} — ${who} take the Elder Dragon.`
    case 'BARON':
      return `${clock} — ${who} slay the Baron.`
    case 'TOWER':
      return `${clock} — ${who} destroy a tower (${String(p.lane).toLowerCase()}).`
    case 'INHIBITOR':
      return `${clock} — ${who} destroy an inhibitor (${String(p.lane).toLowerCase()}).`
    case 'NEXUS_TOWER':
      return `${clock} — ${who} destroy a nexus tower.`
    case 'NEXUS':
      return `${clock} — ${who} DESTROY THE NEXUS!`
    case 'PHASE_START':
      return `— ${titleCase(String(p.name))} game begins —`
    case 'TIMEOUT':
      return `Time runs out with both nexuses standing.`
    default:
      return null
  }
}
