import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { LobbySummary, Ruleset, RulesetSettings, SeriesFormat } from '../api/types'
import { ErrorNotice, Loading } from '../components/common'
import { useRulesets } from '../hooks/useData'
import { RANK_TIERS, seriesShort, titleCase } from '../lib/format'

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

type DraftOptions = RulesetSettings & { ruleset: string }

/** Anything Goes, used until the ruleset list loads (the server has the same preset). */
const ANYTHING_GOES: DraftOptions = {
  ruleset: 'ANYTHING_GOES', hide_player_data: false, bans_enabled: true, timers_enabled: true, pick_seconds: 30,
  ban_seconds: 30, series_format: 'BO1', fearless: false, max_rank: null, max_player_total: null, max_team_total: null,
  duplicate_clause: false, mirror_clause: false,
}

const clampTo = (lo: number, hi: number, fallback: number) => (n: number) => Math.max(lo, Math.min(hi, Math.round(n) || fallback))
const clamp = clampTo(5, 600, 30)
const clampPlayerTotal = clampTo(5, 50, 32)
const clampTeamTotal = clampTo(25, 250, 160)

/** Whether the options differ from their ruleset's preset. Single player ignores hidden data (it's always shown). */
function isModified(value: DraftOptions, rulesets: Ruleset[], single: boolean): boolean {
  const preset = rulesets.find((r) => r.key === value.ruleset)?.settings
  if (!preset) return false
  return (Object.keys(preset) as (keyof RulesetSettings)[]).some(
    (k) => !(single && k === 'hide_player_data') && preset[k] !== value[k],
  )
}

/** A stat total cap: a "limit" checkbox and the number (null means no limit). */
function CapField({ label, value, fallback, min, max, onChange }: {
  label: string
  value: number | null
  fallback: number
  min: number
  max: number
  onChange: (v: number | null) => void
}) {
  return (
    <div className="stack">
      <label className="check">
        <input type="checkbox" checked={value !== null} onChange={(e) => onChange(e.target.checked ? fallback : null)} />
        {label}
      </label>
      {value !== null && (
        <input type="number" aria-label={label} min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      )}
    </div>
  )
}

/** Ruleset, series format, ban phases, pick/ban timers and team restrictions: the same options in both modes.
 * Choosing a ruleset fills in every option; the creator can still change any of them afterwards. */
function DraftOptionsForm({ value, onChange, single }: { value: DraftOptions; onChange: (v: DraftOptions) => void; single: boolean }) {
  const rulesets = useRulesets()
  const list = rulesets.data?.rulesets ?? []
  const current = list.find((r) => r.key === value.ruleset)
  const modified = isModified(value, list, single)
  const set = (patch: Partial<DraftOptions>) => onChange({ ...value, ...patch })
  const apply = (key: string) => {
    const preset = list.find((r) => r.key === key)
    if (preset) onChange({ ruleset: key, ...preset.settings })
  }
  const choices = list.length ? list.map((r) => ({ key: r.key, name: r.name })) : [{ key: ANYTHING_GOES.ruleset, name: 'Anything Goes' }]
  return (
    <>
      <label>
        Ruleset
        <select value={value.ruleset} onChange={(e) => apply(e.target.value)} disabled={!list.length}>
          {choices.map((r) => (
            <option key={r.key} value={r.key}>{r.name}</option>
          ))}
        </select>
      </label>
      {current && (
        <p className="muted small">
          {current.description}
          {modified && (
            <>
              {' '}<span className="badge">Modified</span>{' '}
              <button type="button" className="ghost small" onClick={() => apply(value.ruleset)}>Reset to {current.name}</button>
            </>
          )}
        </p>
      )}
      {!single && (
        <label className="check">
          <input type="checkbox" checked={value.hide_player_data} onChange={(e) => set({ hide_player_data: e.target.checked })} />
          Hide player data (opponent stats and champion pools stay secret until the match ends)
        </label>
      )}
      <label>
        Format
        <select value={value.series_format} onChange={(e) => set({ series_format: e.target.value as SeriesFormat })}>
          <option value="BO1">Best of 1</option>
          <option value="BO3">Best of 3</option>
          <option value="BO5">Best of 5</option>
        </select>
      </label>
      <label className="check" title={value.series_format === 'BO1' ? 'Fearless Draft needs a Best of 3 or Best of 5' : undefined}>
        <input
          type="checkbox"
          checked={value.fearless && value.series_format !== 'BO1'}
          disabled={value.series_format === 'BO1'}
          onChange={(e) => set({ fearless: e.target.checked })}
        />
        Fearless Draft (champions picked in a game can't be picked or banned again in the series)
      </label>
      <label className="check">
        <input type="checkbox" checked={!value.bans_enabled} onChange={(e) => set({ bans_enabled: !e.target.checked })} />
        Disable ban phases (pick only)
      </label>
      <label className="check">
        <input type="checkbox" checked={value.timers_enabled} onChange={(e) => set({ timers_enabled: e.target.checked })} />
        Enable pick/ban timers
      </label>
      {value.timers_enabled && (
        <div className="grid two">
          <label>
            Pick time limit (seconds)
            <input type="number" min={5} max={600} value={value.pick_seconds} onChange={(e) => set({ pick_seconds: Number(e.target.value) })} />
          </label>
          {value.bans_enabled && (
            <label>
              Ban time limit (seconds)
              <input type="number" min={5} max={600} value={value.ban_seconds} onChange={(e) => set({ ban_seconds: Number(e.target.value) })} />
            </label>
          )}
        </div>
      )}
      <h3>Team restrictions</h3>
      <label>
        Max rank
        <select value={value.max_rank ?? ''} onChange={(e) => set({ max_rank: e.target.value || null })}>
          <option value="">No limit</option>
          {(rulesets.data?.rank_tiers ?? RANK_TIERS).map((tier) => (
            <option key={tier} value={tier}>{titleCase(tier)} and below</option>
          ))}
        </select>
      </label>
      {value.max_rank && <p className="muted small">A rank limit only allows players imported from a ranked Riot account.</p>}
      <div className="grid two">
        <CapField label="Limit each player's stat total" value={value.max_player_total} fallback={32} min={5} max={50}
          onChange={(v) => set({ max_player_total: v })} />
        <CapField label="Limit the team's stat total" value={value.max_team_total} fallback={160} min={25} max={250}
          onChange={(v) => set({ max_team_total: v })} />
      </div>
      <label className="check">
        <input type="checkbox" checked={value.duplicate_clause} onChange={(e) => set({ duplicate_clause: e.target.checked })} />
        Duplicate clause (a team can't roster the same Riot account twice; hand-made players are matched by name)
      </label>
      <label className="check">
        <input type="checkbox" checked={value.mirror_clause} onChange={(e) => set({ mirror_clause: e.target.checked })} />
        No mirror players (the same player can't be on both teams)
      </label>
    </>
  )
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
          settings: {
            ruleset: o.ruleset,
            hide_player_data: mode === 'MULTI' && o.hide_player_data,
            bans_enabled: o.bans_enabled,
            timers_enabled: o.timers_enabled,
            pick_seconds: clamp(o.pick_seconds),
            ban_seconds: clamp(o.ban_seconds),
            series_format: o.series_format,
            fearless: o.series_format !== 'BO1' && o.fearless,
            max_rank: o.max_rank,
            max_player_total: o.max_player_total === null ? null : clampPlayerTotal(o.max_player_total),
            max_team_total: o.max_team_total === null ? null : clampTeamTotal(o.max_team_total),
            duplicate_clause: o.duplicate_clause,
            mirror_clause: o.mirror_clause,
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
              <p className="muted">You play Blue. Share the lobby code with a friend.</p>
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
