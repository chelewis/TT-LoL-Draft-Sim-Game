import { describe, expect, it } from 'vitest'
import type { MatchEvent } from '../api/types'
import { REPLAY_MIN_GAP_MS, REPLAY_SECONDS_PER_GAME_MINUTE, buildReplay, gameClockSeconds } from './replay'

const names = { BLUE: 'Alpha', RED: 'Beta' }
const perMinute = REPLAY_SECONDS_PER_GAME_MINUTE * 1000
const event = (sequence: number, minute: number, type: string, payload: Record<string, unknown> = { team: 'BLUE' }): MatchEvent =>
  ({ sequence, phase: 'early', minute, type, payload })

describe('buildReplay', () => {
  it('times each line from its game minute', () => {
    const { lines, totalMs } = buildReplay([event(1, 4, 'DRAGON'), event(2, 20, 'BARON')], names, 1800)
    expect(lines.map((l) => l.atMs)).toEqual([4 * perMinute, 20 * perMinute])
    expect(lines[0].text).toContain('Alpha slay a dragon')
    expect(totalMs).toBe(30 * perMinute)
  })

  it('plays events in clock order even when the log is not', () => {
    // the lane results are logged first but stamped at the end of the lane phase
    const log = [event(1, 15, 'LANE_RESULT', { lane: 'TOP', winner: 'RED' }), event(2, 3, 'PHASE_START', { name: 'early' }), event(3, 6, 'DRAGON')]
    const { lines } = buildReplay(log, names, 1800)
    expect(lines.map((l) => l.type)).toEqual(['PHASE_START', 'DRAGON', 'LANE_RESULT'])
    expect(lines.map((l) => l.atMs)).toEqual([3 * perMinute, 6 * perMinute, 15 * perMinute])
  })

  it('staggers lines that share a minute', () => {
    const lanes = ['TOP', 'JUNGLE', 'MID'].map((lane, i) => event(i + 1, 0, 'LANE_RESULT', { lane, winner: 'RED' }))
    const { lines } = buildReplay(lanes, names, 1800)
    expect(lines.map((l) => l.atMs)).toEqual([0, REPLAY_MIN_GAP_MS, 2 * REPLAY_MIN_GAP_MS])
  })

  it('drops internal events and never ends before its last line', () => {
    const log = [event(1, 30, 'NEXUS_TOWER'), event(2, 30, 'SIEGE'), event(3, 30, 'NEXUS'), event(4, 30, 'GAME_END')]
    const { lines, steps, totalMs } = buildReplay(log, names, 1800)
    expect(lines.map((l) => l.type)).toEqual(['NEXUS_TOWER', 'NEXUS'])
    // every event keeps a step; one without a line takes effect with the line before it
    expect(steps.map((s) => s.atMs)).toEqual([30 * perMinute, 30 * perMinute, 30 * perMinute + REPLAY_MIN_GAP_MS, 30 * perMinute + REPLAY_MIN_GAP_MS])
    expect(totalMs).toBe(30 * perMinute + REPLAY_MIN_GAP_MS)
  })
})

describe('gameClockSeconds', () => {
  it('runs with the replay and stops at the match duration', () => {
    expect(gameClockSeconds(0, 1800)).toBe(0)
    expect(gameClockSeconds(10 * perMinute, 1800)).toBe(600)
    expect(gameClockSeconds(99 * perMinute, 1800)).toBe(1800)
  })
})
