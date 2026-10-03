import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Coach, Lane, Player, RiotPreview, Team } from '../api/types'
import { LANES, STYLES } from '../api/types'
import { ErrorNotice, Loading } from '../components/common'
import { OverBudgetBadge } from '../components/TeamCard'
import { useChampions, useCoaches, usePlayers, useTeams } from '../hooks/useData'
import { LANE_LABEL, isHidden, riotSourceLabel, riotSourceTag, titleCase } from '../lib/format'
import { useRiotStatus } from './RiotImportPage'

interface GameConfig {
  player_stat_budget: number
  coach_stat_budget: number
  stat_range: [number, number]
  champion_pool_size: number
}

const useConfig = () => useQuery({ queryKey: ['config'], queryFn: () => api<GameConfig>('/config'), staleTime: Infinity })

function useInvalidate() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: ['teams'] })
    qc.invalidateQueries({ queryKey: ['players'] })
    qc.invalidateQueries({ queryKey: ['coaches'] })
  }
}

// ------------------------------------------------------------------ teams
export function TeamsPage() {
  const teams = useTeams()
  const invalidate = useInvalidate()
  const del = useMutation({ mutationFn: (id: number) => api(`/teams/${id}`, { method: 'DELETE' }), onSuccess: invalidate })
  const dup = useMutation({ mutationFn: (id: number) => api(`/teams/${id}/duplicate`, { method: 'POST' }), onSuccess: invalidate })

  const mine = (teams.data ?? []).filter((t) => !t.is_default)
  const defaults = (teams.data ?? []).filter((t) => t.is_default)

  return (
    <div className="stack">
      <div className="row between wrap">
        <h1>My teams</h1>
        <Link className="button primary" to="/teams/new">New team</Link>
      </div>
      <ErrorNotice error={del.error ?? dup.error} />
      {teams.isLoading && <Loading />}
      {mine.length === 0 && !teams.isLoading && <p className="muted">You have not created a team yet. Duplicate a default team or start from scratch.</p>}
      <div className="grid two">
        {mine.map((t) => (
          <TeamRow key={t.id} team={t} actions={
            <>
              <Link className="button ghost small" to={`/teams/${t.id}`}>Edit</Link>
              <button className="ghost small" onClick={() => dup.mutate(t.id)}>Duplicate</button>
              <button className="ghost small danger" onClick={() => window.confirm(`Delete ${t.name}?`) && del.mutate(t.id)}>Delete</button>
            </>
          } />
        ))}
      </div>
      <h2>Default teams</h2>
      <div className="grid two">
        {defaults.map((t) => (
          <TeamRow key={t.id} team={t} actions={<button className="ghost small" onClick={() => dup.mutate(t.id)} disabled={!t.selectable}>Duplicate to edit</button>} />
        ))}
      </div>
      <p><Link to="/players">Manage players →</Link> · <Link to="/coaches">Manage coaches →</Link></p>
    </div>
  )
}

function TeamRow({ team, actions }: { team: Team; actions: React.ReactNode }) {
  return (
    <div className="card stack">
      <div className="row between wrap">
        <h3>{team.name}</h3>
        <OverBudgetBadge team={team} />
      </div>
      <p className="small muted">
        {[team.style1, team.style2].filter(Boolean).map(titleCase).join(' + ') || 'No playstyle'}
        {team.coach ? ` · coach ${team.coach.name}` : ''}
      </p>
      <p className="small">
        {LANES.map((l) => {
          const p = team.roster[l]
          return <span key={l} className="chip">{LANE_LABEL[l]}: {p && !isHidden(p) ? p.name : '—'}</span>
        })}
      </p>
      {team.selectable ? <span className="badge ok">Ready to play</span> : <span className="badge" title={team.issues?.join('; ')}>Incomplete: {team.issues?.[0]}</span>}
      <div className="row wrap">{actions}</div>
    </div>
  )
}

export function TeamEditorPage() {
  const { teamId } = useParams()
  const isNew = !teamId || teamId === 'new'
  const navigate = useNavigate()
  const invalidate = useInvalidate()
  const players = usePlayers()
  const coaches = useCoaches()
  const existing = useQuery({ queryKey: ['team', teamId], queryFn: () => api<Team>(`/teams/${teamId}`), enabled: !isNew })

  const [name, setName] = useState('')
  const [logo, setLogo] = useState('')
  const [style1, setStyle1] = useState('')
  const [style2, setStyle2] = useState('')
  const [focus1, setFocus1] = useState('')
  const [focus2, setFocus2] = useState('')
  const [coachId, setCoachId] = useState('')
  const [roster, setRoster] = useState<Partial<Record<Lane, number>>>({})

  useEffect(() => {
    const t = existing.data
    if (!t) return
    setName(t.name); setLogo(t.logo); setStyle1(t.style1 ?? ''); setStyle2(t.style2 ?? '')
    setFocus1(t.focus1 ?? ''); setFocus2(t.focus2 ?? ''); setCoachId(t.coach ? String(t.coach.id) : '')
    const r: Partial<Record<Lane, number>> = {}
    for (const l of LANES) { const p = t.roster[l]; if (p) r[l] = p.id }
    setRoster(r)
  }, [existing.data])

  const save = useMutation({
    mutationFn: () => {
      const body = {
        name, logo, style1: style1 || null, style2: style2 || null, focus1: focus1 || null, focus2: focus2 || null,
        coach_id: coachId ? Number(coachId) : null, roster,
      }
      return isNew ? api<Team>('/teams', { body }) : api<Team>(`/teams/${teamId}`, { method: 'PUT', body })
    },
    onSuccess: () => { invalidate(); navigate('/teams') },
  })

  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate() }
  const overBudget = LANES.flatMap((l) => {
    const p = players.data?.find((x) => x.id === roster[l])
    return p && p.over_budget_by > 0 ? [p] : []
  })

  if (!isNew && existing.isLoading) return <Loading />
  if (existing.data?.is_default) return <div className="card"><p>Default teams are read-only. Duplicate it from My teams to edit a copy.</p><Link to="/teams">← Back</Link></div>

  return (
    <form className="stack" onSubmit={submit}>
      <h1>{isNew ? 'New team' : 'Edit team'}</h1>
      <div className="card stack">
        <div className="grid two">
          <label>Team name<input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required /></label>
          <label>Short logo text<input value={logo} onChange={(e) => setLogo(e.target.value)} maxLength={8} /></label>
          <label>Primary playstyle
            <select value={style1} onChange={(e) => setStyle1(e.target.value)}><option value="">Choose…</option>{STYLES.map((s) => <option key={s} value={s} disabled={s === style2}>{titleCase(s)}</option>)}</select>
          </label>
          <label>Secondary playstyle
            <select value={style2} onChange={(e) => setStyle2(e.target.value)}><option value="">Choose…</option>{STYLES.map((s) => <option key={s} value={s} disabled={s === style1}>{titleCase(s)}</option>)}</select>
          </label>
          <label>Focus lane 1
            <select value={focus1} onChange={(e) => setFocus1(e.target.value)}><option value="">None</option>{LANES.map((l) => <option key={l} value={l} disabled={l === focus2}>{LANE_LABEL[l]}</option>)}</select>
          </label>
          <label>Focus lane 2
            <select value={focus2} onChange={(e) => setFocus2(e.target.value)}><option value="">None</option>{LANES.map((l) => <option key={l} value={l} disabled={l === focus1}>{LANE_LABEL[l]}</option>)}</select>
          </label>
          <label>Coach
            <select value={coachId} onChange={(e) => setCoachId(e.target.value)}>
              <option value="">Choose…</option>
              {(coaches.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name} (Draft {c.draft} / Synergy {c.synergy}){c.is_default ? ' — default' : ''}</option>)}
            </select>
          </label>
        </div>
      </div>
      <div className="card stack">
        <h2>Roster</h2>
        {LANES.map((lane) => (
          <label key={lane}>{LANE_LABEL[lane]}
            <select value={roster[lane] ?? ''} onChange={(e) => setRoster({ ...roster, [lane]: e.target.value ? Number(e.target.value) : undefined })}>
              <option value="">Empty</option>
              {(players.data ?? []).filter((p) => p.role === lane).map((p) => (
                <option key={p.id} value={p.id}>{p.name} ({p.stat_total}){p.over_budget_by > 0 ? ' ⚠' : ''}{p.is_default ? ' — default' : ''}</option>
              ))}
            </select>
          </label>
        ))}
        {overBudget.length > 0 && (
          <div className="notice notice-warn">
            ⚠ {overBudget.map((p) => p.name).join(', ')} exceed the stat ceiling. You can still save; this team will show a "potentially illegal team" warning to your opponent.
          </div>
        )}
        <p className="small muted">Players are created in <Link to="/players/new">My players</Link>.</p>
      </div>
      <ErrorNotice error={save.error} />
      <div className="row wrap">
        <button className="primary" disabled={save.isPending}>Save team</button>
        <Link className="button ghost" to="/teams">Cancel</Link>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------- players
export function PlayersPage() {
  const riotStatus = useRiotStatus()
  const players = usePlayers()
  const invalidate = useInvalidate()
  const del = useMutation({ mutationFn: (id: number) => api(`/players/${id}`, { method: 'DELETE' }), onSuccess: invalidate })
  const champs = useChampions()
  const names = new Map((champs.data ?? []).map((c) => [c.id, c.name]))
  const mine = (players.data ?? []).filter((p) => !p.is_default)
  const defaults = (players.data ?? []).filter((p) => p.is_default)

  const row = (p: Player) => (
    <tr key={p.id}>
      <td>{p.name} {p.riot && <span className="badge" title="Imported from a Riot account (unverified)">Riot {p.riot.game_name}#{p.riot.tag_line}</span>}
        {p.riot && riotSourceTag(p.riot.data_source) && <span className="badge badge-warn" title={`Stats come from ${riotSourceLabel(p.riot.data_source)} (${p.riot.games_used ?? '?'} games), not solo queue`}>⚠ {riotSourceTag(p.riot.data_source)}</span>} {p.over_budget_by > 0 && <span className="badge badge-warn" title="Above the soft stat ceiling">⚠ +{p.over_budget_by}</span>}</td>
      <td>{LANE_LABEL[p.role]}</td>
      <td>{p.aggr}/{p.aware}/{p.pos}/{p.dmg}/{p.cs}</td>
      <td>{p.stat_total}</td>
      <td className="small muted">{p.pool.map((id) => names.get(id)).join(', ')}</td>
      <td>{!p.is_default && <>
        <Link className="button ghost small" to={`/players/${p.id}`}>Edit</Link>{' '}
        <button type="button" className="ghost small danger" onClick={() => window.confirm(`Delete ${p.name}?`) && del.mutate(p.id)}>Delete</button></>}</td>
    </tr>
  )
  const table = (list: Player[]) => (
    <div className="table-scroll"><table><thead><tr><th>Name</th><th>Role</th><th title="aggr/aware/pos/dmg/cs">Stats</th><th>Total</th><th>Champion pool</th><th /></tr></thead><tbody>{list.map(row)}</tbody></table></div>
  )
  return (
    <div className="stack">
      <div className="row between wrap"><h1>My players</h1>
        <span className="row wrap">
          {riotStatus.data?.enabled && <Link className="button" to="/players/import">Import from Riot</Link>}
          <Link className="button primary" to="/players/new">New player</Link>
        </span></div>
      <ErrorNotice error={del.error} />
      {players.isLoading && <Loading />}
      {mine.length === 0 ? <p className="muted">No custom players yet.</p> : table(mine)}
      <h2>Default players</h2>
      {table(defaults)}
      <p><Link to="/teams">← Teams</Link></p>
    </div>
  )
}

export function PlayerEditorPage() {
  const { playerId } = useParams()
  const isNew = !playerId || playerId === 'new'
  const navigate = useNavigate()
  const invalidate = useInvalidate()
  const config = useConfig()
  const champs = useChampions()
  const existing = useQuery({ queryKey: ['player', playerId], queryFn: () => api<Player>(`/players/${playerId}`), enabled: !isNew })

  const [name, setName] = useState('')
  const [role, setRole] = useState<Lane>('TOP')
  const [age, setAge] = useState(21)
  const [region, setRegion] = useState('')
  const [stats, setStats] = useState({ aggr: 5, aware: 5, pos: 5, dmg: 5, cs: 5 })
  const [pool, setPool] = useState<string[]>(['', '', '', '', ''])
  const [riotRef, setRiotRef] = useState<string | null>(null)
  const [riotNotes, setRiotNotes] = useState<string[]>([])
  const [riotSource, setRiotSource] = useState<{ queue: string; games: number } | null>(null)
  const location = useLocation()
  const riotStatus = useRiotStatus()

  /** Fill the form from a Riot preview (import or refresh). Nothing is saved until the user presses Save. */
  const applyDraft = (draft: RiotPreview) => {
    const d = draft.player
    setName(d.name); setRole(d.role); setAge(d.age); setRegion(d.region)
    setStats({ aggr: d.aggr, aware: d.aware, pos: d.pos, dmg: d.dmg, cs: d.cs })
    setPool([...d.pool.map(String), '', '', '', '', ''].slice(0, 5))
    setRiotRef(draft.riot_ref)
    setRiotNotes(draft.analysis.notes)
    setRiotSource({ queue: draft.analysis.source.queue, games: draft.analysis.source.games })
  }

  useEffect(() => {
    const p = existing.data
    if (!p) return
    setName(p.name); setRole(p.role); setAge(p.age); setRegion(p.region)
    setStats({ aggr: p.aggr, aware: p.aware, pos: p.pos, dmg: p.dmg, cs: p.cs })
    setPool(p.pool.map(String))
  }, [existing.data])

  useEffect(() => {
    const draft = (location.state as { draft?: RiotPreview } | null)?.draft
    if (isNew && draft) applyDraft(draft)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const refresh = useMutation({
    mutationFn: () => api<RiotPreview>(`/players/${playerId}/riot-refresh`, { method: 'POST' }),
    onSuccess: applyDraft,
  })

  const total = stats.aggr + stats.aware + stats.pos + stats.dmg + stats.cs
  const budget = config.data?.player_stat_budget ?? 32
  const over = total - budget
  const sorted = useMemo(() => [...(champs.data ?? [])].sort((a, b) => a.name.localeCompare(b.name)), [champs.data])

  const save = useMutation({
    mutationFn: () => {
      const body = { name, role, age, region, ...stats, pool: pool.map(Number), riot_ref: riotRef }
      return isNew ? api<Player>('/players', { body }) : api<Player>(`/players/${playerId}`, { method: 'PUT', body })
    },
    onSuccess: () => { invalidate(); navigate('/players') },
  })
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate() }
  const setStat = (key: keyof typeof stats, value: number) => setStats({ ...stats, [key]: Math.max(1, Math.min(10, value || 1)) })
  const poolLabels = ['Best pick (+40%)', 'Comfort (+25%)', 'Comfort (+25%)', 'Familiar (+10%)', 'Familiar (+10%)']
  const poolValid = pool.every(Boolean) && new Set(pool).size === pool.length

  if (!isNew && existing.isLoading) return <Loading />

  return (
    <form className="stack" onSubmit={submit}>
      <h1>{isNew ? 'New player' : 'Edit player'}</h1>
      {(riotRef || existing.data?.riot) && (
        <div className="card stack">
          <div className="row between wrap">
            <span>🔗 Imported from Riot: <strong>{existing.data?.riot ? `${existing.data.riot.game_name}#${existing.data.riot.tag_line}` : 'new import'}</strong> <span className="badge">unverified</span></span>
            {!isNew && existing.data?.riot && riotStatus.data?.enabled && (
              <button type="button" className="ghost small" disabled={refresh.isPending} onClick={() => refresh.mutate()}>{refresh.isPending ? 'Refreshing…' : 'Refresh stats from Riot'}</button>
            )}
          </div>
          <ErrorNotice error={refresh.error} />
          {(() => {
            const queue = riotSource?.queue ?? existing.data?.riot?.data_source
            const games = riotSource?.games ?? existing.data?.riot?.games_used
            return riotSourceTag(queue)
              ? <div className="notice notice-warn source-banner" role="alert"><strong>⚠ Stats from {riotSourceLabel(queue)}, not solo queue</strong>{games ? ` · ${games} games` : ''}</div>
              : <p className="muted small">Source: {riotSourceLabel(queue)}{games ? ` · ${games} games` : ''}</p>
          })()}
          {riotNotes.map((n) => <div key={n} className="notice notice-warn">{n}</div>)}
          {riotRef && !isNew && <p className="small muted">Refreshed values are loaded below. Press Save to keep them.</p>}
        </div>
      )}
      <div className="card stack">
        <div className="grid two">
          <label>Name<input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required /></label>
          <label>Role
            <select value={role} onChange={(e) => setRole(e.target.value as Lane)}>{LANES.map((l) => <option key={l} value={l}>{LANE_LABEL[l]}</option>)}</select>
          </label>
          <label>Age<input type="number" min={16} max={99} value={age} onChange={(e) => setAge(Number(e.target.value))} /></label>
          <label>Region<input value={region} onChange={(e) => setRegion(e.target.value)} maxLength={16} /></label>
        </div>
      </div>
      <div className="card stack">
        <div className="row between wrap">
          <h2>Stats</h2>
          <span className={`badge ${over > 0 ? 'badge-warn' : 'ok'}`}>Total {total} / {budget}</span>
        </div>
        <div className="grid stats-inputs">
          {([['aggr', 'Aggression'], ['aware', 'Awareness'], ['pos', 'Positioning'], ['dmg', 'Damage'], ['cs', 'Farming (CS)']] as const).map(([key, label]) => (
            <label key={key}>{label}: <strong>{stats[key]}</strong>
              <input type="range" min={1} max={10} value={stats[key]} onChange={(e) => setStat(key, Number(e.target.value))} />
            </label>
          ))}
        </div>
        {over > 0 && (
          <div className="notice notice-warn">
            ⚠ {over} point{over === 1 ? '' : 's'} over the {budget}-point ceiling. You can still save this player, but any team using them will be flagged as a potentially illegal team in lobbies.
          </div>
        )}
      </div>
      <div className="card stack">
        <h2>Champion pool</h2>
        <p className="small muted">Exactly five champions. Order matters: the first is this player's best pick. Champions outside the pool play at −10%.</p>
        {pool.map((value, i) => (
          <label key={i}>{poolLabels[i]}
            <select value={value} onChange={(e) => setPool(pool.map((v, j) => (j === i ? e.target.value : v)))} required>
              <option value="">Choose a champion…</option>
              {sorted.map((c) => <option key={c.id} value={c.id} disabled={pool.includes(String(c.id)) && pool[i] !== String(c.id)}>{c.name} ({c.class})</option>)}
            </select>
          </label>
        ))}
      </div>
      <ErrorNotice error={save.error} />
      <div className="row wrap">
        <button className="primary" disabled={save.isPending || !poolValid}>Save player</button>
        <Link className="button ghost" to="/players">Cancel</Link>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------- coaches
export function CoachesPage() {
  const coaches = useCoaches()
  const config = useConfig()
  const invalidate = useInvalidate()
  const [editing, setEditing] = useState<Coach | null>(null)
  const [name, setName] = useState('')
  const [draft, setDraft] = useState(5)
  const [synergy, setSynergy] = useState(5)
  const budget = config.data?.coach_stat_budget ?? 12

  const save = useMutation({
    mutationFn: () => {
      const body = { name, draft, synergy }
      return editing ? api(`/coaches/${editing.id}`, { method: 'PUT', body }) : api('/coaches', { body })
    },
    onSuccess: () => { invalidate(); reset() },
  })
  const del = useMutation({ mutationFn: (id: number) => api(`/coaches/${id}`, { method: 'DELETE' }), onSuccess: invalidate })
  function reset() { setEditing(null); setName(''); setDraft(5); setSynergy(5) }
  function edit(c: Coach) { setEditing(c); setName(c.name); setDraft(c.draft); setSynergy(c.synergy) }

  return (
    <div className="stack">
      <h1>Coaches</h1>
      <p className="muted">Draft makes your favourable lane matchups stronger in the match simulation. Synergy strengthens team cohesion (lane assists and playstyle bonuses).</p>
      <form className="card stack" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
        <h2>{editing ? 'Edit coach' : 'New coach'}</h2>
        <label>Name<input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required /></label>
        <label>Draft: <strong>{draft}</strong><input type="range" min={1} max={10} value={draft} onChange={(e) => setDraft(Number(e.target.value))} /></label>
        <label>Synergy: <strong>{synergy}</strong><input type="range" min={1} max={10} value={synergy} onChange={(e) => setSynergy(Number(e.target.value))} /></label>
        <span className={`badge ${draft + synergy > budget ? 'badge-warn' : 'ok'}`}>Total {draft + synergy} / {budget} (hard limit)</span>
        <ErrorNotice error={save.error ?? del.error} />
        <div className="row wrap">
          <button className="primary" disabled={save.isPending || draft + synergy > budget}>Save coach</button>
          {editing && <button type="button" className="ghost" onClick={reset}>Cancel</button>}
        </div>
      </form>
      {(coaches.data ?? []).map((c) => (
        <div key={c.id} className="list-row">
          <span>{c.name} — Draft {c.draft}, Synergy {c.synergy} {c.is_default && <span className="badge">default</span>}</span>
          {!c.is_default && <span className="row">
            <button className="ghost small" onClick={() => edit(c)}>Edit</button>
            <button className="ghost small danger" onClick={() => window.confirm(`Delete ${c.name}?`) && del.mutate(c.id)}>Delete</button>
          </span>}
        </div>
      ))}
      <p><Link to="/teams">← Teams</Link></p>
    </div>
  )
}
