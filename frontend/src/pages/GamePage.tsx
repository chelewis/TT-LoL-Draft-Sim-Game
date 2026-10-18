import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { ChatMessage, GameState } from '../api/types'
import { ErrorNotice, Loading } from '../components/common'
import { useGameSocket, type SocketEvent } from '../hooks/useGameSocket'
import { addChatMessage } from '../hooks/useChat'
import MusicPlayer from '../components/MusicPlayer'
import SideBanner from '../components/SideBanner'
import DraftView from './game/DraftView'
import LobbyView from './game/LobbyView'
import ReplayView from './game/ReplayView'
import ResultView from './game/ResultView'
import SeriesResultView from './game/SeriesResultView'

export default function GamePage() {
  const gameId = Number(useParams().gameId)
  // keyed by game: moving on to the next game of a series starts with fresh replay state
  return <GameScreen key={gameId} gameId={gameId} />
}

function GameScreen({ gameId }: { gameId: number }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
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
      // either side swapped: the matchup panel shows both lineups, and the opponent's isn't in the game state
      if (event.type === 'LINEUP_UPDATED') qc.invalidateQueries({ queryKey: ['matchups', gameId] })
      // a re-run replaces the stored result: drop the cached one so nothing shows the old match
      if (event.type === 'SIMULATION_COMPLETED') {
        qc.resetQueries({ queryKey: ['result', gameId] })
        qc.resetQueries({ queryKey: ['result-events', gameId] })
      }
      // both players readied up: everyone moves on to the series' next game
      if (event.type === 'SERIES_NEXT_GAME') navigate(`/game/${event.next_game_id}`)
    },
    [qc, gameId, refresh, navigate],
  )

  const connected = useGameSocket(gameId, onEvent)

  // the replay only plays for someone who was here when the match was simulated, not when reopening a finished game
  const sawLive = useRef(false)
  const [replayDone, setReplayDone] = useState(false)
  const endReplay = useCallback(() => setReplayDone(true), [])
  // after watching the deciding game of a series, show the series result first
  const [gameDetails, setGameDetails] = useState(false)
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

  // while the replay plays the result is still a secret, including what it did to the series score
  const replaying = game?.status === 'COMPLETED' && sawLive.current && !replayDone

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
      {game.status !== 'CANCELLED' && <SideBanner game={game} hideResult={replaying} />}
      {game.status !== 'CANCELLED' && <MusicPlayer seriesGameNumber={game.series?.game_number} />}
      {(game.status === 'WAITING_FOR_PLAYERS' || game.status === 'TEAM_SELECTION' || game.status === 'READY_CHECK') && (
        <LobbyView game={game} onChange={refresh} />
      )}
      {/* champ select covers the draft and the lineup finalization that follows it */}
      {(game.status === 'DRAFTING' || game.status === 'LANE_ASSIGNMENT' || game.status === 'READY_TO_SIMULATE' || game.status === 'SIMULATING') && (
        <DraftView game={game} onChange={refresh} />
      )}
      {game.status === 'COMPLETED' && (replaying
        ? <ReplayView game={game} onDone={endReplay} />
        : sawLive.current && game.series?.complete && !gameDetails
          ? (
            <div className="stack">
              <SeriesResultView seriesId={game.series.id} />
              <div className="row between wrap">
                <Link to="/">← Back home</Link>
                <button className="ghost" onClick={() => setGameDetails(true)}>Game {game.series.game_number} details</button>
              </div>
            </div>
          )
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
