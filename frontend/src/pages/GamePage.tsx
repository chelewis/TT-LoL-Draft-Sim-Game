import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { ChatMessage, GameState } from '../api/types'
import { ErrorNotice, Loading } from '../components/common'
import { useGameSocket, type SocketEvent } from '../hooks/useGameSocket'
import { addChatMessage } from '../hooks/useChat'
import SideBanner from '../components/SideBanner'
import DraftView from './game/DraftView'
import LobbyView from './game/LobbyView'
import ReplayView from './game/ReplayView'
import ResultView from './game/ResultView'

export default function GamePage() {
  const gameId = Number(useParams().gameId)
  const qc = useQueryClient()
  const key = ['game', gameId]

  const { data: game, error, isLoading } = useQuery({
    queryKey: key,
    queryFn: () => api<GameState>(`/games/${gameId}/state`),
    // The WebSocket normally triggers refetches; polling is only a safety net.
    refetchInterval: 10000,
    enabled: Number.isFinite(gameId),
  })

  const refresh = useCallback(() => {
    qc.invalidateQueries({ queryKey: ['game', gameId] })
  }, [qc, gameId])

  // chat messages arrive whole over the socket; everything else means "refetch the game state"
  const onEvent = useCallback(
    (event: SocketEvent) => {
      if (event.type === 'CHAT_MESSAGE') addChatMessage(qc, gameId, event.message as ChatMessage)
      else refresh()
      // a re-run replaces the stored result: drop the cached one so nothing shows the old match
      if (event.type === 'SIMULATION_COMPLETED') {
        qc.resetQueries({ queryKey: ['result', gameId] })
        qc.resetQueries({ queryKey: ['result-events', gameId] })
      }
    },
    [qc, gameId, refresh],
  )

  const connected = useGameSocket(gameId, onEvent)

  // the replay only plays for someone who was here when the match was simulated, not when reopening a finished game
  const sawLive = useRef(false)
  const [replayDone, setReplayDone] = useState(false)
  const endReplay = useCallback(() => setReplayDone(true), [])
  if (game && game.status !== 'COMPLETED' && game.status !== 'CANCELLED') sawLive.current = true
  // a new seed on a finished game means the match was re-run: play the replay again
  const lastSeed = useRef<number | null>(null)
  if (game?.status === 'COMPLETED' && game.seed != null && game.seed !== lastSeed.current) {
    if (lastSeed.current !== null) {
      sawLive.current = true
      if (replayDone) setReplayDone(false)
    }
    lastSeed.current = game.seed
  }

  if (isLoading) return <Loading label="Loading game…" />
  if (error || !game) {
    return (
      <div className="stack">
        <ErrorNotice error={error ?? new Error('Game not found.')} />
        <Link to="/">← Back home</Link>
      </div>
    )
  }

  return (
    <div className="stack">
      {!connected && game.status !== 'COMPLETED' && game.status !== 'CANCELLED' && (
        <div className="notice">Reconnecting to live updates…</div>
      )}
      {game.status !== 'CANCELLED' && <SideBanner game={game} />}
      {(game.status === 'WAITING_FOR_PLAYERS' || game.status === 'TEAM_SELECTION' || game.status === 'READY_CHECK') && (
        <LobbyView game={game} onChange={refresh} />
      )}
      {/* champ select covers the draft and the lineup finalization that follows it */}
      {(game.status === 'DRAFTING' || game.status === 'LANE_ASSIGNMENT' || game.status === 'READY_TO_SIMULATE' || game.status === 'SIMULATING') && (
        <DraftView game={game} onChange={refresh} />
      )}
      {game.status === 'COMPLETED' && (sawLive.current && !replayDone
        ? <ReplayView game={game} onDone={endReplay} />
        : <ResultView game={game} />)}
      {game.status === 'CANCELLED' && (
        <div className="card stack">
          <h2>Game cancelled</h2>
          <p className="muted">A player left or the lobby expired.</p>
          <Link to="/">← Back home</Link>
        </div>
      )}
    </div>
  )
}
