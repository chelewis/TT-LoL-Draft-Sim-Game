import type { MatchEvent, Side } from '../api/types'
import { describeEvent } from './summary'

/** How fast the replay runs: real seconds per minute of game time. */
export const REPLAY_SECONDS_PER_GAME_MINUTE = 1.5
/** Lines never land closer together than this, so events at the same minute still arrive one by one. */
export const REPLAY_MIN_GAP_MS = 500
/** How long the finished feed stays up before the result screen takes over. */
export const REPLAY_END_PAUSE_MS = 2500

const MS_PER_GAME_MINUTE = REPLAY_SECONDS_PER_GAME_MINUTE * 1000

export interface ReplayLine {
  sequence: number
  type: string
  text: string
  atMs: number                    // real time into the replay at which the line appears
}

/** One event and the moment it takes effect; the scoreboard follows these so it moves with the feed. */
export interface ReplayStep {
  event: MatchEvent
  atMs: number
}

export interface Replay {
  lines: ReplayLine[]
  steps: ReplayStep[]             // every event, including the internal ones that have no line
  totalMs: number
}

/** Turn the event log into timed play-by-play lines. Events with no description (internal ones) get no line. */
export function buildReplay(events: MatchEvent[], sideNames: Record<Side, string>, durationSeconds: number): Replay {
  const lines: ReplayLine[] = []
  const steps: ReplayStep[] = []
  let previous = -REPLAY_MIN_GAP_MS
  let last = 0
  // the log is in simulation order, not clock order: the lane results come first but are stamped with the minute
  // the lane phase ends, after the early game's events
  const byClock = [...events].sort((a, b) => a.minute - b.minute || a.sequence - b.sequence)
  for (const e of byClock) {
    const text = describeEvent(e, sideNames)
    const atMs = Math.max(e.minute * MS_PER_GAME_MINUTE, text ? previous + REPLAY_MIN_GAP_MS : previous)
    steps.push({ event: e, atMs })
    last = atMs
    if (!text) continue
    lines.push({ sequence: e.sequence, type: e.type, text, atMs })
    previous = atMs
  }
  return { lines, steps, totalMs: Math.max((durationSeconds / 60) * MS_PER_GAME_MINUTE, last) }
}

/** The game clock, in whole seconds, after `elapsedMs` of replay; it stops at the match duration. */
export function gameClockSeconds(elapsedMs: number, durationSeconds: number): number {
  const seconds = Math.floor((elapsedMs / MS_PER_GAME_MINUTE) * 60)
  return Math.max(0, Math.min(durationSeconds, seconds))
}
