import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { GameState, MatchEvent, MatchResult, Side } from '../../api/types'
import { Loading } from '../../components/common'
import MatchMap from '../../components/MatchMap'
import { useChampionMap } from '../../hooks/useData'
import { REPLAY_END_PAUSE_MS, buildReplay, gameClockSeconds } from '../../lib/replay'
import { scoreAt } from '../../lib/scoreboard'
import { ReplayHud, ReplayPlayers } from './ReplayScoreboard'

/**
 * The match played back before the result screen: a scrolling play-by-play and a live scoreboard and map that
 * follow it, under a running game clock.
 */
export default function ReplayView({ game, onDone }: { game: GameState; onDone: () => void }) {
  const champions = useChampionMap()
  // same query keys as the result screen, so it opens from cache once the replay is over
  const result = useQuery({ queryKey: ['result', game.game_id], queryFn: () => api<MatchResult>(`/games/${game.game_id}/result`) })
  const events = useQuery({
    queryKey: ['result-events', game.game_id],
    queryFn: () => api<{ events: MatchEvent[] }>(`/games/${game.game_id}/result/events?limit=500`),
  })
  const blueName = game.teams.BLUE?.name || 'Blue'
  const redName = game.teams.RED?.name || 'Red'
  const names = useMemo((): Record<Side, string> => ({ BLUE: blueName, RED: redName }), [blueName, redName])
  const replay = useMemo(
    () => (result.data && events.data ? buildReplay(events.data.events, names, result.data.duration_seconds) : null),
    [result.data, events.data, names],
  )
  const [elapsed, setElapsed] = useState(0)
  const feed = useRef<HTMLOListElement>(null)

  // a replay that cannot load must never stand between the player and the result
  const failed = !!(result.error || events.error)
  useEffect(() => {
    if (failed) onDone()
  }, [failed, onDone])

  useEffect(() => {
    if (!replay) return
    const start = performance.now()
    let frame = requestAnimationFrame(function tick(now) {
      const ms = now - start
      setElapsed(ms)
      if (ms < replay.totalMs) frame = requestAnimationFrame(tick)
    })
    return () => cancelAnimationFrame(frame)
  }, [replay])

  const finished = !!replay && elapsed >= replay.totalMs
  useEffect(() => {
    if (!finished) return
    const timer = setTimeout(onDone, REPLAY_END_PAUSE_MS)
    return () => clearTimeout(timer)
  }, [finished, onDone])

  const shown = replay ? replay.lines.filter((l) => l.atMs <= elapsed) : []
  useEffect(() => {
    if (feed.current) feed.current.scrollTop = feed.current.scrollHeight
  }, [shown.length])

  // the scoreboard and map only change when another event lands or the clock ticks over, not on every frame
  const clock = gameClockSeconds(elapsed, result.data?.duration_seconds ?? 0)
  const landed = replay ? replay.steps.filter((s) => s.atMs <= elapsed).length : 0
  const revealed = useMemo(() => (replay ? replay.steps.slice(0, landed).map((s) => s.event) : []), [replay, landed])
  const score = useMemo(
    () => (result.data && events.data ? scoreAt(result.data, events.data.events, revealed, clock) : null),
    [result.data, events.data, revealed, clock],
  )

  return (
    <div className="card stack replay">
      {!replay || !result.data || !score ? <Loading label="Simulating match…" /> : (
        <>
          <ReplayHud names={names} score={score} clockSeconds={clock} />
          <div className="replay-body">
            <ol className="replay-feed" ref={feed} aria-live="polite">
              {shown.length === 0 && <li className="replay-phase-start">— The match is under way —</li>}
              {shown.map((l) => (
                <li key={l.sequence} className={`replay-${l.type.toLowerCase().replace(/_/g, '-')}`}>{l.text}</li>
              ))}
            </ol>
            <MatchMap live result={result.data} events={revealed} champions={champions} names={names} />
          </div>
          <ReplayPlayers result={result.data} score={score} champions={champions} />
        </>
      )}
      <div className="row between wrap">
        <span className="small muted">{finished ? 'Match over. Loading results…' : 'Live play by play'}</span>
        <button onClick={onDone}>Skip to results</button>
      </div>
    </div>
  )
}
