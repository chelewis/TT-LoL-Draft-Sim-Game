import type { Lane, MatchEvent, MatchResult, Side } from '../api/types'
import { LANES } from '../api/types'
import { STRUCTURE_LANES, buildMapState } from './mapState'

export interface TeamScore {
  kills: number
  gold: number | null             // null when the game's events carry no gold (simulated before they did)
  towers: number                  // enemy towers destroyed, nexus towers included
  inhibitors: number
  dragons: number
  barons: number
  soul: boolean
  elder: boolean
}

export interface PlayerScore {
  kills: number
  deaths: number
  assists: number
  cs: number
  gold: number | null
  damageDealt: number | null      // null when the game's fights carry no damage (simulated before they did)
  damageTaken: number | null
}

export interface Score {
  teams: Record<Side, TeamScore>
  players: Record<string, PlayerScore>   // by `playerKey`
}

const SIDES: Side[] = ['BLUE', 'RED']
const other = (s: Side): Side => (s === 'BLUE' ? 'RED' : 'BLUE')

/** Players are keyed by side and lane: both sides can field the same roster, so player ids are not unique. */
export const playerKey = (team: Side, lane: Lane) => `${team}:${lane}`

type EventGold = Record<Side, number[]>
const eventGold = (e: MatchEvent | undefined) => e?.payload.event_gold as EventGold | undefined
const latest = (events: MatchEvent[]) => events.reduce<MatchEvent | undefined>((a, b) => (a && a.sequence > b.sequence ? a : b), undefined)

/**
 * The score with only `revealed` events having happened and the clock at `clockSeconds`. `events` is the whole
 * log: the final event's gold is what separates CS gold from the rest. At the end it equals the final result.
 */
export function scoreAt(result: MatchResult, events: MatchEvent[], revealed: MatchEvent[], clockSeconds: number): Score {
  const players: Record<string, PlayerScore> = {}
  const byChampion: Record<string, PlayerScore> = {}
  const hasDamage = events.some((e) => e.type === 'FIGHT' && e.payload.damage)
  const damage = hasDamage ? 0 : null
  for (const p of result.players) {
    const score: PlayerScore = { kills: 0, deaths: 0, assists: 0, cs: 0, gold: null, damageDealt: damage, damageTaken: damage }
    players[playerKey(p.team, p.lane)] = score
    byChampion[`${p.team}:${p.champion}`] = score
  }
  const kills: Record<Side, number> = { BLUE: 0, RED: 0 }

  for (const e of revealed) {
    if (e.type !== 'FIGHT') continue
    const p = e.payload as unknown as {
      attacker: Side; defender: Side; attackers: Lane[]; defenders: Lane[]
      kills: Record<Side, number>; log: { killer: string; victim: string; team: Side }[]
      damage?: Partial<Record<Side, Partial<Record<Lane, [number, number]>>>>
    }
    for (const side of SIDES) kills[side] += p.kills[side] ?? 0
    for (const side of SIDES) {
      for (const [lane, [dealt, taken]] of Object.entries(p.damage?.[side] ?? {}) as [Lane, [number, number]][]) {
        const score = players[playerKey(side, lane)]
        if (!score) continue
        score.damageDealt = (score.damageDealt ?? 0) + dealt
        score.damageTaken = (score.damageTaken ?? 0) + taken
      }
    }
    const own: Record<string, number> = {}
    for (const k of p.log) {
      const killer = byChampion[`${k.team}:${k.killer}`]
      const victim = byChampion[`${other(k.team)}:${k.victim}`]
      if (killer) killer.kills += 1
      if (victim) victim.deaths += 1
      own[`${k.team}:${k.killer}`] = (own[`${k.team}:${k.killer}`] ?? 0) + 1
    }
    // everyone in the fight assists each of their side's kills that they did not land themselves
    for (const [side, lanes] of [[p.attacker, p.attackers], [p.defender, p.defenders]] as [Side, Lane[]][]) {
      const sideKills = p.log.filter((k) => k.team === side).length
      for (const lane of lanes) {
        const member = result.players.find((x) => x.team === side && x.lane === lane)
        if (member) players[playerKey(side, lane)].assists += sideKills - (own[`${side}:${member.champion}`] ?? 0)
      }
    }
  }

  const progress = result.duration_seconds > 0 ? Math.min(1, Math.max(0, clockSeconds / result.duration_seconds)) : 1
  const finalGold = eventGold(latest(events))
  const nowGold = eventGold(latest(revealed))
  // a lane's winner is paid when the lane phase ends, but the log simulates the lanes first: hold that gold back
  // until the lane result has been shown
  const shown = new Set(revealed.map((e) => e.sequence))
  const held: Record<string, number> = {}
  for (const e of events) {
    const winner = e.payload.winner as Side | null
    if (e.type === 'LANE_RESULT' && winner && !shown.has(e.sequence)) held[playerKey(winner, e.payload.lane as Lane)] = Number(e.payload.gold_diff) || 0
  }
  const teamGold: Record<Side, number> = { BLUE: 0, RED: 0 }
  for (const p of result.players) {
    const key = playerKey(p.team, p.lane)
    const score = players[key]
    score.cs = Math.round(p.cs * progress)
    if (!finalGold) continue
    const index = LANES.indexOf(p.lane)
    const fromCs = (p.gold - finalGold[p.team][index]) * progress
    const fromEvents = Math.max(0, (nowGold?.[p.team][index] ?? 0) - (held[key] ?? 0))
    score.gold = Math.round(fromCs + fromEvents)
    teamGold[p.team] += score.gold
  }

  const map = buildMapState(revealed)
  const team = (side: Side): TeamScore => {
    const enemy = map[other(side)]
    return {
      kills: kills[side],
      gold: finalGold ? teamGold[side] : null,
      towers: STRUCTURE_LANES.reduce((n, lane) => n + enemy.towersLost[lane], enemy.nexusTowersLost),
      inhibitors: STRUCTURE_LANES.filter((lane) => enemy.inhibitorsLost[lane]).length,
      dragons: map[side].dragons,
      barons: map[side].barons,
      soul: map[side].soul,
      elder: map[side].elder,
    }
  }
  return { teams: { BLUE: team('BLUE'), RED: team('RED') }, players }
}

/** Blue's gold minus Red's: positive when Blue leads. Null when the game's events carry no gold. */
export function goldDiff(score: Score): number | null {
  const { BLUE, RED } = score.teams
  return BLUE.gold == null || RED.gold == null ? null : BLUE.gold - RED.gold
}

export interface GoldPoint {
  seconds: number
  diff: number                    // Blue's gold minus Red's
}

/** The gold difference at every game minute and at the end. Null when the game's events carry no gold. */
export function goldTimeline(result: MatchResult, events: MatchEvent[]): GoldPoint[] | null {
  const byClock = [...events].sort((a, b) => a.minute - b.minute || a.sequence - b.sequence)
  const at = (seconds: number) => goldDiff(scoreAt(result, events, byClock.filter((e) => e.minute * 60 <= seconds), seconds))
  if (at(result.duration_seconds) == null) return null
  const points: GoldPoint[] = []
  for (let s = 0; s < result.duration_seconds; s += 60) points.push({ seconds: s, diff: at(s)! })
  points.push({ seconds: result.duration_seconds, diff: at(result.duration_seconds)! })
  return points
}

/** A large number the way a broadcast shows it: 56.6k. */
export function formatThousands(value: number): string {
  return `${(value / 1000).toFixed(1)}k`
}

/** Team gold the way a broadcast shows it: 56.6k. */
export const formatGold = formatThousands
