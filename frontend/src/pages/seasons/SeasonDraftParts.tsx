import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { api } from '../../api/client'
import { LANES, STYLES, type CpuStrength, type Lane, type Season, type SeasonPoolPlayer } from '../../api/types'
import { ErrorNotice, Loading } from '../../components/common'
import { useCoaches, useCountdown, usePlayers } from '../../hooks/useData'
import { refreshSeason, useSeasonPool, useSeasonTeam } from '../../hooks/useSeasons'
import { isHidden, LANE_LABEL, titleCase } from '../../lib/format'
import { CPU_STRENGTH_LABELS, draftRounds, filterPool, pickableLanes, timeUntil } from '../../lib/season'

// ---------------------------------------------------------- draft teams
export interface DraftTeamBody {
  name: string
  logo: string
  style1: string | null
  style2: string | null
  coach_id: number | null
}

/** Player Draft: the team you enter is a name, logo, playstyles and coach. Its players are drafted. */
export function DraftTeamForm({ onSubmit, pending, error, label }: {
  onSubmit: (body: DraftTeamBody) => void
  pending: boolean
  error: unknown
  label: string
}) {
  const coaches = useCoaches()
  const [name, setName] = useState('')
  const [logo, setLogo] = useState('')
  const [style1, setStyle1] = useState('')
  const [style2, setStyle2] = useState('')
  const [coachId, setCoachId] = useState<number | ''>('')
  return (
    <div className="stack">
      <p className="muted small">
        Name your team and pick its identity. Its five players are drafted from the season's pool when the season starts.
      </p>
      <label>
        Team name
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} placeholder="Academy" />
      </label>
      <label>
        Logo (short text, optional)
        <input value={logo} onChange={(e) => setLogo(e.target.value)} maxLength={8} placeholder="ACA" />
      </label>
      <div className="row wrap">
        <label>
          Primary playstyle
          <select value={style1} onChange={(e) => setStyle1(e.target.value)}>
            <option value="">Random</option>
            {STYLES.map((s) => <option key={s} value={s} disabled={s === style2}>{titleCase(s)}</option>)}
          </select>
        </label>
        <label>
          Secondary playstyle
          <select value={style2} onChange={(e) => setStyle2(e.target.value)}>
            <option value="">Random</option>
            {STYLES.map((s) => <option key={s} value={s} disabled={s === style1}>{titleCase(s)}</option>)}
          </select>
        </label>
      </div>
      <label>
        Coach
        <select value={coachId} onChange={(e) => setCoachId(e.target.value ? Number(e.target.value) : '')}>
          <option value="">A generated coach</option>
          {(coaches.data ?? []).map((c) => (
            <option key={c.id} value={c.id}>{c.name} (draft {c.draft}, synergy {c.synergy}){c.is_default ? ' · default' : ''}</option>
          ))}
        </select>
      </label>
      <ErrorNotice error={error} />
      <button className="primary" disabled={!name.trim() || pending}
        onClick={() => onSubmit({ name: name.trim(), logo: logo.trim(), style1: style1 || null, style2: style2 || null,
          coach_id: coachId === '' ? null : coachId })}>
        {label}
      </button>
    </div>
  )
}

// ----------------------------------------------------------- pool table
const STAT_COLUMNS = [
  { key: 'aggr', label: 'AGG' }, { key: 'aware', label: 'AWR' }, { key: 'pos', label: 'POS' },
  { key: 'dmg', label: 'DMG' }, { key: 'cs', label: 'CS' },
] as const

function LaneFilter({ lane, onLane, query, onQuery }: {
  lane: Lane | null; onLane: (l: Lane | null) => void; query: string; onQuery: (q: string) => void
}) {
  return (
    <div className="row wrap">
      <div className="tabs" role="tablist" aria-label="Lane">
        {([null, ...LANES] as (Lane | null)[]).map((l) => (
          <button key={l ?? 'all'} type="button" role="tab" aria-selected={lane === l} className={lane === l ? 'active' : ''}
            onClick={() => onLane(l)}>
            {l ? LANE_LABEL[l] : 'All'}
          </button>
        ))}
      </div>
      <input value={query} onChange={(e) => onQuery(e.target.value)} placeholder="Search players" aria-label="Search players" />
    </div>
  )
}

/** Pool players (or free agents), filterable by lane, with an actions cell per row. */
function PoolTable({ players, actions }: { players: SeasonPoolPlayer[]; actions?: (p: SeasonPoolPlayer) => ReactNode }) {
  const [lane, setLane] = useState<Lane | null>(null)
  const [query, setQuery] = useState('')
  const shown = filterPool(players, lane, query)
  return (
    <div className="stack">
      <LaneFilter lane={lane} onLane={setLane} query={query} onQuery={setQuery} />
      <div className="table-scroll">
        <table className="compact">
          <thead>
            <tr>
              <th>Player</th>
              <th>Lanes</th>
              <th className="num" title="Stat total">Total</th>
              {STAT_COLUMNS.map((c) => <th key={c.key} className="num">{c.label}</th>)}
              {actions && <th />}
            </tr>
          </thead>
          <tbody>
            {shown.map((p) => (
              <tr key={p.id}>
                <td>{p.name}{p.riot && <span className="muted small"> · {p.riot.game_name}</span>}</td>
                <td className="small">{p.lanes.map((l) => LANE_LABEL[l]).join(' / ')}</td>
                <td className="num"><strong>{p.stat_total}</strong></td>
                {STAT_COLUMNS.map((c) => <td key={c.key} className="num">{p[c.key]}</td>)}
                {actions && <td className="row wrap">{actions(p)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {shown.length === 0 && <p className="muted small">No players{lane ? ` for ${LANE_LABEL[lane]}` : ''}.</p>}
    </div>
  )
}

// ----------------------------------------------------------------- pool
/** Setup: the draft pool, and (for the creator) adding, generating and removing players. */
export function PoolCard({ season }: { season: Season }) {
  const qc = useQueryClient()
  const pool = useSeasonPool(season.id)
  const summary = season.pool
  const creator = season.is_creator
  const onDone = (s: Season) => refreshSeason(qc, s)
  const [perRole, setPerRole] = useState(2)
  const [strength, setStrength] = useState<CpuStrength>('EVEN')
  const [adding, setAdding] = useState(false)
  const generate = useMutation({
    mutationFn: () => api<Season>(`/seasons/${season.id}/pool/generate`, { body: { per_role: perRole, strength } }),
    onSuccess: onDone,
  })
  const remove = useMutation({
    mutationFn: (id: number) => api<Season>(`/seasons/${season.id}/pool/${id}`, { method: 'DELETE' }),
    onSuccess: onDone,
  })
  const clear = useMutation({
    mutationFn: () => api<Season>(`/seasons/${season.id}/pool`, { method: 'DELETE' }),
    onSuccess: onDone,
  })
  const short = summary ? Object.entries(summary.shortfall) : []
  return (
    <div className="card stack">
      <div className="row between wrap">
        <h3>Draft pool · {summary?.count ?? 0} players</h3>
        {summary && (
          <span className="muted small">
            {LANES.map((l) => `${LANE_LABEL[l]} ${summary.by_lane[l]}`).join(' · ')}
          </span>
        )}
      </div>
      {short.length > 0 ? (
        <p className="notice small">
          Every manager drafts one player per lane. For the {Math.max(1, season.managers)} manager{season.managers === 1 ? '' : 's'} entered so far the pool is short of{' '}
          {short.map(([lane, n]) => `${n} ${LANE_LABEL[lane as Lane]}`).join(', ')}.
          {creator ? ' Add or generate more players before starting.' : ''}
        </p>
      ) : (
        <p className="muted small">
          The pool can fill every manager's roster. Players nobody drafts become free agents{season.free_agency.enabled ? ' managers can sign during the season' : ''}.
        </p>
      )}
      {creator && (
        <div className="stack">
          <div className="row wrap">
            <label>
              Generate
              <select value={perRole} onChange={(e) => setPerRole(Number(e.target.value))}>
                {[1, 2, 3, 4, 5, 6, 8, 10].map((n) => <option key={n} value={n}>{n} per lane ({n * 5} players)</option>)}
              </select>
            </label>
            <label>
              Strength
              <select value={strength} onChange={(e) => setStrength(e.target.value as CpuStrength)}>
                {(Object.keys(CPU_STRENGTH_LABELS) as CpuStrength[]).map((k) => (
                  <option key={k} value={k}>{CPU_STRENGTH_LABELS[k].split(':')[0]}</option>
                ))}
              </select>
            </label>
            <button onClick={() => generate.mutate()} disabled={generate.isPending}>Generate players</button>
            <button className="ghost" onClick={() => setAdding(!adding)}>{adding ? 'Close' : 'Add my players…'}</button>
            {!!summary?.count && (
              <button className="ghost danger" disabled={clear.isPending}
                onClick={() => window.confirm('Remove every player from the pool?') && clear.mutate()}>
                Clear pool
              </button>
            )}
          </div>
          {adding && <AddMyPlayers season={season} onDone={() => setAdding(false)} />}
          <ErrorNotice error={generate.error ?? remove.error ?? clear.error} />
        </div>
      )}
      {pool.isLoading && <Loading />}
      {pool.data && pool.data.players.length > 0 && (
        <PoolTable players={pool.data.players} actions={creator ? (p) => (
          <button className="ghost small" onClick={() => remove.mutate(p.id)} disabled={remove.isPending} title="Remove from the pool">✕</button>
        ) : undefined} />
      )}
    </div>
  )
}

function AddMyPlayers({ season, onDone }: { season: Season; onDone: () => void }) {
  const qc = useQueryClient()
  const players = usePlayers()
  const [chosen, setChosen] = useState<Set<number>>(new Set())
  const add = useMutation({
    mutationFn: () => api<Season>(`/seasons/${season.id}/pool/players`, { body: { player_ids: [...chosen] } }),
    onSuccess: (s) => {
      refreshSeason(qc, s)
      onDone()
    },
  })
  const toggle = (id: number) => {
    const next = new Set(chosen)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setChosen(next)
  }
  if (players.isLoading) return <Loading />
  return (
    <div className="stack pool-picker">
      <p className="muted small">Copies of the players you tick join the pool (each must meet the season's player rules).</p>
      <div className="check-grid">
        {(players.data ?? []).map((p) => (
          <label key={p.id} className="check">
            <input type="checkbox" checked={chosen.has(p.id)} onChange={() => toggle(p.id)} />
            {p.name} <span className="muted small">{LANE_LABEL[p.role]} · {p.stat_total}{p.is_default ? ' · default' : ''}</span>
          </label>
        ))}
      </div>
      <ErrorNotice error={add.error} />
      <button className="primary" disabled={!chosen.size || add.isPending} onClick={() => add.mutate()}>
        Add {chosen.size || ''} to the pool
      </button>
    </div>
  )
}

// ---------------------------------------------------------------- draft
/** The live player draft: who's on the clock, the available players, and every pick so far. */
export function DraftBoard({ season }: { season: Season }) {
  const qc = useQueryClient()
  const draft = season.draft!
  const pool = useSeasonPool(season.id)
  const seconds = useCountdown(draft.pick_deadline_at)
  const onDone = (s: Season) => refreshSeason(qc, s)
  const pick = useMutation({
    mutationFn: (body: { player_id: number; lane: Lane }) => api<Season>(`/seasons/${season.id}/draft/pick`, { body }),
    onSuccess: onDone,
  })
  const auto = useMutation({
    mutationFn: () => api<Season>(`/seasons/${season.id}/draft/auto`, { method: 'POST' }),
    onSuccess: onDone,
  })
  const onClock = draft.on_the_clock
  const busy = pick.isPending || auto.isPending
  return (
    <div className="stack">
      <div className={`card stack ${draft.my_turn ? 'my-match' : ''}`}>
        <div className="row between wrap">
          <h3>
            Player draft · pick {draft.current_pick} of {draft.total_picks}
          </h3>
          {draft.pick_deadline_at && <span className="badge">{seconds > 0 ? `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}` : '0:00'}</span>}
        </div>
        <p>
          {draft.my_turn
            ? <strong>You're on the clock.</strong>
            : <>On the clock: <strong>{onClock?.name}</strong> <span className="muted small">({onClock?.manager?.username ?? 'CPU'})</span></>}
          {draft.pick_deadline_at && seconds > 3600 && <span className="muted small"> · {timeUntil(draft.pick_deadline_at)} left</span>}
        </p>
        {draft.my_open_lanes.length > 0 && (
          <p className="muted small">Your open lanes: {draft.my_open_lanes.map((l) => LANE_LABEL[l]).join(', ')}</p>
        )}
        <ErrorNotice error={pick.error ?? auto.error} />
        <div className="row wrap">
          {draft.my_turn && (
            <button onClick={() => auto.mutate()} disabled={busy} title="The best available player for one of your open lanes">
              Auto-pick for me
            </button>
          )}
          {!draft.my_turn && season.is_creator && (
            <button className="ghost" disabled={busy}
              onClick={() => window.confirm(`Pick the best available player for ${onClock?.name}?`) && auto.mutate()}>
              Auto-pick for {onClock?.name}
            </button>
          )}
        </div>
        <p className="muted small">
          Snake order: the order reverses every round. A pick that would leave another team unable to fill a lane isn't allowed.
          {draft.pick_deadline_at ? ' When the clock runs out the best available player is picked automatically.' : ''}
        </p>
      </div>

      <div className="grid two">
        <div className="card stack">
          <h3>Available players</h3>
          {pool.isLoading && <Loading />}
          {pool.data && (
            <PoolTable players={pool.data.players} actions={draft.my_turn ? (p) => pickableLanes(p, draft.my_open_lanes).map((lane) => (
              <button key={lane} className="small primary" disabled={busy} onClick={() => pick.mutate({ player_id: p.id, lane })}>
                Pick · {LANE_LABEL[lane]}
              </button>
            )) : undefined} />
          )}
        </div>
        <DraftResults season={season} />
      </div>
    </div>
  )
}

/** Every pick so far, by round. */
export function DraftResults({ season }: { season: Season }) {
  const draft = season.draft
  if (!draft) return null
  const rounds = draftRounds(draft.picks, draft.order.length)
  return (
    <div className="card stack">
      <h3>Draft order</h3>
      <p className="muted small">{draft.order.map((t, i) => `${i + 1}. ${t?.name ?? '?'}`).join(' · ')}</p>
      {rounds.length === 0 && <p className="muted small">No picks yet.</p>}
      {rounds.map((picks, r) => (
        <div key={r} className="stack">
          <h4>Round {r + 1}</h4>
          {picks.map((p) => (
            <div key={p.pick_number} className={`list-row ${p.team?.is_you ? 'is-yours' : ''}`}>
              <span><span className="muted small">#{p.pick_number}</span> <strong>{p.player_name}</strong> <span className="muted small">{LANE_LABEL[p.lane]}</span></span>
              <span className="muted small">{p.team?.name}{p.auto && <span className="badge" title="Picked automatically">auto</span>}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------- free agency
export function FreeAgents({ season }: { season: Season }) {
  const qc = useQueryClient()
  const pool = useSeasonPool(season.id)
  const mine = useSeasonTeam(season.id, season.my_team_id ?? NaN)
  const fa = season.free_agency
  const sign = useMutation({
    mutationFn: (body: { player_id: number; lane: Lane }) => api<Season>(`/seasons/${season.id}/free-agents/sign`, { body }),
    onSuccess: (s) => refreshSeason(qc, s),
  })
  const roster = mine.data?.view.roster
  const canSign = fa.open && season.my_team_id !== null && (fa.signings_left ?? 0) > 0
  return (
    <div className="stack">
      <div className="card stack">
        <h3>Free agents</h3>
        <p className="muted small">
          Sign a free agent into one of your lanes: the player there now is released into free agency. Each team can make{' '}
          {fa.max_signings} signing{fa.max_signings === 1 ? '' : 's'} over the season, and not while its match is in progress.
          {fa.signings_left !== null && <> You have <strong>{fa.signings_left}</strong> left.</>}
        </p>
        <ErrorNotice error={sign.error} />
        {pool.isLoading && <Loading />}
        {pool.data && (
          <PoolTable players={pool.data.players} actions={canSign ? (p) => p.lanes.map((lane) => {
            const slot = roster?.[lane]
            const current = slot && !isHidden(slot) ? slot : null
            return (
              <button key={lane} className="small" disabled={sign.isPending}
                onClick={() => window.confirm(`Sign ${p.name} at ${LANE_LABEL[lane]}${current ? `, releasing ${current.name} (total ${current.stat_total})` : ''}?`)
                  && sign.mutate({ player_id: p.id, lane })}
                title={current ? `Replaces ${current.name} (${current.stat_total})` : undefined}>
                Sign · {LANE_LABEL[lane]}{current ? ` (${p.stat_total - current.stat_total >= 0 ? '+' : ''}${p.stat_total - current.stat_total})` : ''}
              </button>
            )
          }) : undefined} />
        )}
      </div>
      <Transactions season={season} />
    </div>
  )
}

export function Transactions({ season }: { season: Season }) {
  if (!season.transactions.length) return null
  return (
    <div className="card stack">
      <h3>Transactions</h3>
      {season.transactions.map((t) => (
        <div key={t.id} className="list-row">
          <span>
            <span className={`badge ${t.type === 'SIGN' ? 'ok' : ''}`}>{t.type === 'SIGN' ? 'Signed' : 'Released'}</span>{' '}
            <strong>{t.player_name}</strong> <span className="muted small">{LANE_LABEL[t.lane]}</span>
          </span>
          <span className="muted small">{t.team?.name} · round {t.round}</span>
        </div>
      ))}
    </div>
  )
}
