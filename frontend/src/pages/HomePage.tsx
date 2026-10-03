import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { LobbySummary } from '../api/types'
import { ErrorNotice, Loading } from '../components/common'
import { titleCase } from '../lib/format'

type Mode = 'SOLO' | 'MULTI'
const MODE_KEY = 'ldm_create_mode'

function savedMode(): Mode {
  try {
    return localStorage.getItem(MODE_KEY) === 'SOLO' ? 'SOLO' : 'MULTI'
  } catch {
    return 'MULTI'
  }
}

interface DraftOptions {
  bans: boolean
  timers: boolean
  pickSeconds: number
  banSeconds: number
}

const clamp = (n: number) => Math.max(5, Math.min(600, Math.round(n) || 30))

/** Ban phases and pick/ban timers: the same options in both modes. */
function DraftOptionsForm({ value, onChange }: { value: DraftOptions; onChange: (v: DraftOptions) => void }) {
  const set = (patch: Partial<DraftOptions>) => onChange({ ...value, ...patch })
  return (
    <>
      <label className="check">
        <input type="checkbox" checked={!value.bans} onChange={(e) => set({ bans: !e.target.checked })} />
        Disable ban phases (pick only)
      </label>
      <label className="check">
        <input type="checkbox" checked={value.timers} onChange={(e) => set({ timers: e.target.checked })} />
        Enable pick/ban timers
      </label>
      {value.timers && (
        <div className="grid two">
          <label>
            Pick time limit (seconds)
            <input type="number" min={5} max={600} value={value.pickSeconds} onChange={(e) => set({ pickSeconds: Number(e.target.value) })} />
          </label>
          {value.bans && (
            <label>
              Ban time limit (seconds)
              <input type="number" min={5} max={600} value={value.banSeconds} onChange={(e) => set({ banSeconds: Number(e.target.value) })} />
            </label>
          )}
        </div>
      )}
    </>
  )
}

export default function HomePage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [code, setCode] = useState('')
  const [mode, setModeState] = useState<Mode>(savedMode)
  const [hide, setHide] = useState(false)
  // each tab keeps its own draft options: a single player sandbox defaults to no timers
  const [multi, setMulti] = useState<DraftOptions>({ bans: true, timers: true, pickSeconds: 30, banSeconds: 30 })
  const [solo, setSolo] = useState<DraftOptions>({ bans: true, timers: false, pickSeconds: 30, banSeconds: 30 })

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
          mode,
          settings: {
            hide_player_data: mode === 'MULTI' && hide,
            bans_enabled: o.bans,
            timers_enabled: o.timers,
            pick_seconds: clamp(o.pickSeconds),
            ban_seconds: clamp(o.banSeconds),
          },
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
  const gameLabel = (g: LobbySummary) =>
    g.settings.mode === 'SOLO' ? <strong>Single player</strong> : <>Lobby <strong>{g.code}</strong></>

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
              <p className="muted">
                Play both sides yourself: choose a team for Blue and for Red, make every pick and ban, then watch the
                simulated match. No second player needed.
              </p>
              <DraftOptionsForm value={solo} onChange={setSolo} />
            </>
          ) : (
            <>
              <p className="muted">You play Blue. Share the lobby code with a friend.</p>
              <label className="check">
                <input type="checkbox" checked={hide} onChange={(e) => setHide(e.target.checked)} />
                Hide player data (opponent stats and champion pools stay secret until the match ends)
              </label>
              <DraftOptionsForm value={multi} onChange={setMulti} />
            </>
          )}

          <ErrorNotice error={create.error} />
          <button className="primary" onClick={() => create.mutate()} disabled={create.isPending}>
            {mode === 'SOLO' ? 'Start single player game' : 'Create lobby'}
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
          <Link key={g.game_id} className="list-row" to={`/game/${g.game_id}`}>
            <span>{gameLabel(g)}</span>
            <span className="badge">{titleCase(g.status)}</span>
          </Link>
        ))}
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
