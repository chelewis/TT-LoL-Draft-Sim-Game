import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { LobbySummary } from '../api/types'
import { ErrorNotice, Loading } from '../components/common'
import DraftOptionsForm, { ANYTHING_GOES, draftSettingsPayload, type DraftOptions } from '../components/DraftOptionsForm'
import { seriesShort, titleCase } from '../lib/format'

type Mode = 'SOLO' | 'MULTI'
const MODE_KEY = 'ldm_create_mode'

function savedMode(): Mode {
  try {
    return localStorage.getItem(MODE_KEY) === 'SOLO' ? 'SOLO' : 'MULTI'
  } catch {
    return 'MULTI'
  }
}

/** Single player opponent: yourself (you play both sides) or the CPU. */
type Opponent = 'SELF' | 'CPU'
const OPPONENT_KEY = 'ldm_solo_opponent'

function savedOpponent(): Opponent {
  try {
    return localStorage.getItem(OPPONENT_KEY) === 'CPU' ? 'CPU' : 'SELF'
  } catch {
    return 'SELF'
  }
}

export default function HomePage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [code, setCode] = useState('')
  const [mode, setModeState] = useState<Mode>(savedMode)
  const [opponent, setOpponentState] = useState<Opponent>(savedOpponent)
  // each tab keeps its own draft options: a single player sandbox defaults to no timers
  const [multi, setMulti] = useState<DraftOptions>(ANYTHING_GOES)
  const [solo, setSolo] = useState<DraftOptions>({ ...ANYTHING_GOES, timers_enabled: false })

  function setOpponent(next: Opponent) {
    setOpponentState(next)
    try {
      localStorage.setItem(OPPONENT_KEY, next)
    } catch {
      /* the choice just will not be remembered */
    }
  }

  function setMode(next: Mode) {
    setModeState(next)
    try {
      localStorage.setItem(MODE_KEY, next)
    } catch {
      /* the tab just will not be remembered */
    }
  }

  const games = useQuery({ queryKey: ['my-games'], queryFn: () => api<LobbySummary[]>('/games') })
  const create = useMutation({
    mutationFn: () => {
      const o = mode === 'SOLO' ? solo : multi
      return api<LobbySummary>('/lobbies', {
        body: {
          mode: mode === 'SOLO' && opponent === 'CPU' ? 'CPU' : mode,
          settings: draftSettingsPayload(o, mode === 'MULTI'),
        },
      })
    },
    onSuccess: (lobby) => {
      qc.invalidateQueries({ queryKey: ['my-games'] })
      navigate(`/game/${lobby.game_id}`)
    },
  })
  const join = useMutation({
    mutationFn: () => api<LobbySummary>(`/lobbies/${code.trim().toUpperCase()}/join`, { method: 'POST' }),
    onSuccess: (lobby) => {
      qc.invalidateQueries({ queryKey: ['my-games'] })
      navigate(`/game/${lobby.game_id}`)
    },
  })

  function submitJoin(e: FormEvent) {
    e.preventDefault()
    join.mutate()
  }

  const active = (games.data ?? []).filter((g) => !['COMPLETED', 'CANCELLED'].includes(g.status))
  const past = (games.data ?? []).filter((g) => ['COMPLETED', 'CANCELLED'].includes(g.status)).slice(0, 8)
  const gameLabel = (g: LobbySummary) => (
    <>
      {g.settings.mode === 'SOLO' ? <strong>Single player</strong>
        : g.settings.mode === 'CPU' ? <strong>vs CPU</strong>
        : <>Lobby <strong>{g.code}</strong></>}
      {g.series && (
        <span className="badge series-badge">
          {seriesShort(g.series.format)} · Game {g.series.game_number}{g.series.fearless ? ' · Fearless' : ''}
        </span>
      )}
    </>
  )

  return (
    <div className="stack">
      <div className="grid two">
        <div className="card stack">
          <h2>Create a lobby</h2>
          <div className="tabs" role="tablist" aria-label="Game mode">
            <button type="button" role="tab" aria-selected={mode === 'SOLO'} className={mode === 'SOLO' ? 'active' : ''} onClick={() => setMode('SOLO')}>
              Single Player
            </button>
            <button type="button" role="tab" aria-selected={mode === 'MULTI'} className={mode === 'MULTI' ? 'active' : ''} onClick={() => setMode('MULTI')}>
              Multiplayer
            </button>
          </div>

          {mode === 'SOLO' ? (
            <>
              <label>
                Opponent
                <select value={opponent} onChange={(e) => setOpponent(e.target.value as Opponent)}>
                  <option value="SELF">Yourself (you control both sides)</option>
                  <option value="CPU">CPU</option>
                </select>
              </label>
              <p className="muted">
                {opponent === 'CPU'
                  ? "Draft against the CPU: choose your team and the CPU's team, then take turns picking and banning. The CPU drafts from the same stats, pools and matchups the simulation uses."
                  : 'Play both sides yourself: choose a team for Blue and for Red, make every pick and ban, then watch the simulated match. No second player needed.'}
              </p>
              <DraftOptionsForm value={solo} onChange={setSolo} single />
            </>
          ) : (
            <>
              <p className="muted">You play Blue. Share the lobby code or invite link with a friend.</p>
              <DraftOptionsForm value={multi} onChange={setMulti} single={false} />
            </>
          )}

          <ErrorNotice error={create.error} />
          <button className="primary" onClick={() => create.mutate()} disabled={create.isPending}>
            {mode === 'SOLO' ? (opponent === 'CPU' ? 'Start game vs CPU' : 'Start single player game') : 'Create lobby'}
          </button>
        </div>
        <form className="card stack" onSubmit={submitJoin}>
          <h2>Join a lobby</h2>
          <label>
            Lobby code
            <input
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              maxLength={8}
              placeholder="GP7K42"
              autoCapitalize="characters"
              required
            />
          </label>
          <ErrorNotice error={join.error} />
          <button className="primary" disabled={join.isPending || !code.trim()}>
            Join
          </button>
        </form>
      </div>

      <div className="card stack">
        <h2>Your games</h2>
        {games.isLoading && <Loading />}
        {!games.isLoading && active.length === 0 && <p className="muted">No active games.</p>}
        {active.map((g) => (
          <Link key={g.game_id} className="list-row" to={`/game/${g.game_id}`}>
            <span>{gameLabel(g)}</span>
            <span className="badge">{titleCase(g.status.replaceAll('_', ' '))}</span>
          </Link>
        ))}
        {past.length > 0 && <h3>Recent</h3>}
        {past.map((g) => (
          <div key={g.game_id} className="row history-row">
            <Link className="list-row" to={`/game/${g.game_id}`}>
              <span>{gameLabel(g)}</span>
              <span className="badge">{titleCase(g.status)}</span>
            </Link>
            {g.series && <Link className="small" to={`/series/${g.series.id}`}>Series →</Link>}
          </div>
        ))}
      </div>

      <div className="card row between wrap">
        <div className="stack">
          <h2>Seasons</h2>
          <p className="muted">
            Run a whole league: enter your team, play it through a round robin against CPU teams, and finish top of the table.
          </p>
        </div>
        <Link className="button primary" to="/seasons">Open Seasons →</Link>
      </div>

      <div className="card">
        <h2>Manage your teams</h2>
        <p className="muted">
          Create players, coaches and teams before you start a lobby, or use the default teams.{' '}
          <Link to="/teams">Open team management →</Link>
        </p>
      </div>
    </div>
  )
}
