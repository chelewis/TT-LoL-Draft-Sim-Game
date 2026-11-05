import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Coach, ImportCheck, Lane, Player, PlaystyleTag, RiotPreview, Team, TeamInsightsRequest } from '../api/types'
import { LANES, STYLES } from '../api/types'
import { ErrorNotice, Loading } from '../components/common'
import { ChampionIcon } from '../components/ChampionArt'
import RiotBadge from '../components/RiotBadge'
import { TagChip } from '../components/TagChips'
import { OverBudgetBadge } from '../components/TeamCard'
import { useChampionFit, useChampions, useCoaches, usePlayers, useTeams } from '../hooks/useData'
import RosterSummary from '../components/RosterSummary'
import TeamNotes from '../components/TeamNotes'
import { LANE_LABEL, TIER_LABEL, editedFieldsText, isHidden, rankLabel, riotSourceLabel, riotSourceTag, roleLabel, titleCase } from '../lib/format'
import { MAX_TAGS, sortTags } from '../lib/playstyle'
import { useRiotStatus } from './RiotImportPage'

interface GameConfig {
  player_stat_budget: number
  coach_stat_budget: number
  stat_range: [number, number]
  champion_pool_size: number
}

const useConfig = () => useQuery({ queryKey: ['config'], queryFn: () => api<GameConfig>('/config'), staleTime: Infinity })

/** Whose content a page manages: the signed-in user's own, or (admin area) the default content everyone sees.
 * Reads always use the normal routes, which list defaults too; writes go to `api`. Links stay under `home`. */
export interface Scope {
  defaults: boolean
  api: string
  home: string
}

export const USER_SCOPE: Scope = { defaults: false, api: '', home: '' }
export const DEFAULTS_SCOPE: Scope = { defaults: true, api: '/admin/defaults', home: '/admin/defaults' }

const confirmDelete = (scope: Scope, name: string) =>
  window.confirm(scope.defaults ? `Delete default ${name}? It is also removed from any player's team that uses it.` : `Delete ${name}?`)

function useInvalidate() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: ['teams'] })
    qc.invalidateQueries({ queryKey: ['players'] })
    qc.invalidateQueries({ queryKey: ['coaches'] })
  }
}

// ------------------------------------------------------------------ teams
export function TeamsPage({ scope = USER_SCOPE }: { scope?: Scope }) {
  const teams = useTeams()
  const invalidate = useInvalidate()
  const del = useMutation({ mutationFn: (id: number) => api(`${scope.api}/teams/${id}`, { method: 'DELETE' }), onSuccess: invalidate })
  const dup = useMutation({ mutationFn: (id: number) => api(`/teams/${id}/duplicate`, { method: 'POST' }), onSuccess: invalidate })

  const mine = (teams.data ?? []).filter((t) => !t.is_default)
  const defaults = (teams.data ?? []).filter((t) => t.is_default)

  if (scope.defaults) return (
    <div className="stack">
      <div className="row between wrap">
        <h1>Default teams</h1>
        <Link className="button primary" to={`${scope.home}/teams/new`}>New default team</Link>
      </div>
      <p className="muted">Every player can see and duplicate these teams. Changes apply to new games straight away.</p>
      <ErrorNotice error={del.error} />
      {teams.isLoading && <Loading />}
      <div className="grid two">
        {defaults.map((t) => (
          <TeamRow key={t.id} team={t} actions={
            <>
              <Link className="button ghost small" to={`${scope.home}/teams/${t.id}`}>Edit</Link>
              <button className="ghost small danger" onClick={() => confirmDelete(scope, t.name) && del.mutate(t.id)}>Delete</button>
            </>
          } />
        ))}
      </div>
      <p><Link to={`${scope.home}/players`}>Default players →</Link> · <Link to={`${scope.home}/coaches`}>Default coaches →</Link></p>
    </div>
  )

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

export function TeamEditorPage({ scope = USER_SCOPE }: { scope?: Scope }) {
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
      return isNew ? api<Team>(`${scope.api}/teams`, { body }) : api<Team>(`${scope.api}/teams/${teamId}`, { method: 'PUT', body })
    },
    onSuccess: () => { invalidate(); navigate(`${scope.home}/teams`) },
  })

  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate() }
  // a default team may only use default players and coaches
  const playerOptions = (players.data ?? []).filter((p) => !scope.defaults || p.is_default)
  const coachOptions = (coaches.data ?? []).filter((c) => !scope.defaults || c.is_default)
  const rosterPlayers: Partial<Record<Lane, Player>> = {}
  for (const l of LANES) {
    const p = playerOptions.find((x) => x.id === roster[l])
    if (p) rosterPlayers[l] = p
  }
  const overBudget = Object.values(rosterPlayers).filter((p) => p.over_budget_by > 0)
  const [notesOpen, setNotesOpen] = useState(false)
  const notesRequest: TeamInsightsRequest = {
    style1: style1 || null, style2: style2 || null, focus1: focus1 || null, focus2: focus2 || null,
    coach_id: coachId ? Number(coachId) : null, roster,
  }

  if (!isNew && existing.isLoading) return <Loading />
  if (existing.data && existing.data.is_default !== scope.defaults) return scope.defaults
    ? <div className="card"><p>This is not a default team.</p><Link to={`${scope.home}/teams`}>← Back</Link></div>
    : <div className="card"><p>Default teams are read-only. Duplicate it from My teams to edit a copy.</p><Link to="/teams">← Back</Link></div>

  return (
    <form className="stack" onSubmit={submit}>
      <div className="row between wrap">
        <h1>{isNew ? 'New' : 'Edit'}{scope.defaults ? ' default' : ''} team</h1>
        <button type="button" className="notes-button" onClick={() => setNotesOpen(true)}
                disabled={Object.keys(rosterPlayers).length === 0} title={Object.keys(rosterPlayers).length ? undefined : 'Add a player first'}>
          📋 Team notes
        </button>
      </div>
      <TeamNotes open={notesOpen} onClose={() => setNotesOpen(false)} request={notesRequest}
                 onUseStyles={(a, b) => { setStyle1(a); setStyle2(b) }}
                 onUseFocus={(a, b) => { setFocus1(a); setFocus2(b ?? '') }} />
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
              {coachOptions.map((c) => <option key={c.id} value={c.id}>{c.name} (Draft {c.draft} / Synergy {c.synergy}){c.is_default && !scope.defaults ? ' — default' : ''}</option>)}
            </select>
          </label>
        </div>
      </div>
      <div className="card stack">
        <h2>Roster</h2>
        <RosterSummary roster={rosterPlayers} />
        {LANES.map((lane) => (
          <label key={lane}>{LANE_LABEL[lane]}
            <select value={roster[lane] ?? ''} onChange={(e) => setRoster({ ...roster, [lane]: e.target.value ? Number(e.target.value) : undefined })}>
              <option value="">Empty</option>
              {playerOptions.filter((p) => p.role === lane || p.secondary_role === lane).map((p) => (
                <option key={p.id} value={p.id}>{p.name} ({p.stat_total}){p.role !== lane ? ' · secondary' : ''}{p.over_budget_by > 0 ? ' ⚠' : ''}{p.is_default && !scope.defaults ? ' — default' : ''}</option>
              ))}
            </select>
          </label>
        ))}
        {overBudget.length > 0 && (
          <div className="notice notice-warn">
            ⚠ {overBudget.map((p) => p.name).join(', ')} exceed the stat ceiling. You can still save; this team will show a "potentially illegal team" warning to your opponent.
          </div>
        )}
        <p className="small muted">Players are created in {scope.defaults
          ? <Link to={`${scope.home}/players/new`}>Default players</Link>
          : <Link to="/players/new">My players</Link>}.</p>
      </div>
      <ErrorNotice error={save.error} />
      <div className="row wrap">
        <button className="primary" disabled={save.isPending}>Save team</button>
        <Link className="button ghost" to={`${scope.home}/teams`}>Cancel</Link>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------- players
export function PlayersPage({ scope = USER_SCOPE }: { scope?: Scope }) {
  const riotStatus = useRiotStatus()
  const players = usePlayers()
  const invalidate = useInvalidate()
  const del = useMutation({ mutationFn: (id: number) => api(`${scope.api}/players/${id}`, { method: 'DELETE' }), onSuccess: invalidate })
  const champs = useChampions()
  const names = new Map((champs.data ?? []).map((c) => [c.id, c.name]))
  const mine = (players.data ?? []).filter((p) => !p.is_default)
  const defaults = (players.data ?? []).filter((p) => p.is_default)

  const row = (p: Player) => (
    <tr key={p.id}>
      <td>{p.name} <RiotBadge riot={p.riot} showAccount />
        {p.riot?.rank && <span className="badge" title={`${riotSourceLabel(p.riot.rank.queue)} rank when imported: ${rankLabel(p.riot.rank, true)}`}>{rankLabel(p.riot.rank)}</span>}
        {p.riot && riotSourceTag(p.riot.data_source) && <span className="badge badge-warn" title={`Stats come from ${riotSourceLabel(p.riot.data_source)} (${p.riot.games_used ?? '?'} games), not solo queue`}>⚠ {riotSourceTag(p.riot.data_source)}</span>} {p.over_budget_by > 0 && <span className="badge badge-warn" title="Above the soft stat ceiling">⚠ +{p.over_budget_by}</span>}</td>
      <td>{roleLabel(p)}</td>
      <td>{p.aggr}/{p.aware}/{p.pos}/{p.dmg}/{p.cs}</td>
      <td>{p.stat_total}</td>
      <td className="small muted">{p.pool.map((id) => names.get(id)).join(', ')}</td>
      <td>{p.is_default === scope.defaults && <>
        <Link className="button ghost small" to={`${scope.home}/players/${p.id}`}>Edit</Link>{' '}
        <button type="button" className="ghost small danger" onClick={() => confirmDelete(scope, p.name) && del.mutate(p.id)}>Delete</button></>}</td>
    </tr>
  )
  const table = (list: Player[]) => (
    <div className="table-scroll"><table><thead><tr><th>Name</th><th>Role</th><th title="aggr/aware/pos/dmg/cs">Stats</th><th>Total</th><th>Champion pool</th><th /></tr></thead><tbody>{list.map(row)}</tbody></table></div>
  )
  if (scope.defaults) return (
    <div className="stack">
      <div className="row between wrap"><h1>Default players</h1>
        <Link className="button primary" to={`${scope.home}/players/new`}>New default player</Link></div>
      <ErrorNotice error={del.error} />
      {players.isLoading && <Loading />}
      {table(defaults)}
      <p><Link to={`${scope.home}/teams`}>← Default teams</Link></p>
    </div>
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

export function PlayerEditorPage({ scope = USER_SCOPE }: { scope?: Scope }) {
  const { playerId } = useParams()
  const isNew = !playerId || playerId === 'new'
  const navigate = useNavigate()
  const invalidate = useInvalidate()
  const config = useConfig()
  const champs = useChampions()
  const existing = useQuery({ queryKey: ['player', playerId], queryFn: () => api<Player>(`/players/${playerId}`), enabled: !isNew })

  const [name, setName] = useState('')
  const [role, setRole] = useState<Lane>('TOP')
  const [secondary, setSecondary] = useState<Lane | ''>('')
  const [age, setAge] = useState(21)
  const [region, setRegion] = useState('')
  const [stats, setStats] = useState({ aggr: 5, aware: 5, pos: 5, dmg: 5, cs: 5 })
  const [pool, setPool] = useState<string[]>(['', '', '', '', ''])
  const [riotRef, setRiotRef] = useState<string | null>(null)
  const [riotNotes, setRiotNotes] = useState<string[]>([])
  const [riotSource, setRiotSource] = useState<{ queue: string; games: number } | null>(null)
  const [riotRank, setRiotRank] = useState<RiotPreview['analysis']['rank'] | null>(null)
  // playstyle tags: the keys kept, and the tags the Riot account earned to choose from
  const [tags, setTags] = useState<string[]>([])
  const [earned, setEarned] = useState<PlaystyleTag[]>([])
  // what the Riot import produced: changing role, stats, imported pool champions or weaknesses marks the player edited
  const [baseline, setBaseline] = useState<ImportCheck['original']>(null)
  const location = useLocation()
  const riotStatus = useRiotStatus()

  /** Fill the form from a Riot preview (import or refresh). Nothing is saved until the user presses Save. */
  const applyDraft = (draft: RiotPreview) => {
    const d = draft.player
    setName(d.name); setRole(d.role); setAge(d.age); setRegion(d.region)
    // a refresh keeps the secondary role the user already chose; an import takes the suggestion
    setSecondary((cur) => (cur && cur !== d.role ? cur : (d.secondary_role ?? '')))
    setStats({ aggr: d.aggr, aware: d.aware, pos: d.pos, dmg: d.dmg, cs: d.cs })
    setPool([...d.pool.map(String), '', '', '', '', ''].slice(0, 5))
    setRiotRef(draft.riot_ref)
    setRiotNotes(draft.analysis.notes)
    setRiotSource({ queue: draft.analysis.source.queue, games: draft.analysis.source.games })
    setRiotRank(draft.analysis.rank)
    setEarned(draft.analysis.tags?.earned ?? [])
    setTags(d.tags ?? [])
    const negative = new Set((draft.analysis.tags?.earned ?? []).filter((t) => t.polarity === 'negative').map((t) => t.key))
    setBaseline({ role: d.role, aggr: d.aggr, aware: d.aware, pos: d.pos, dmg: d.dmg, cs: d.cs, pool: d.pool,
      negative_tags: (d.tags ?? []).filter((k) => negative.has(k)) })
  }

  useEffect(() => {
    const p = existing.data
    if (!p) return
    setName(p.name); setRole(p.role); setSecondary(p.secondary_role ?? ''); setAge(p.age); setRegion(p.region)
    setStats({ aggr: p.aggr, aware: p.aware, pos: p.pos, dmg: p.dmg, cs: p.cs })
    setPool(p.pool.map(String))
    setTags((p.tags ?? []).map((t) => t.key))
    setEarned(p.earned_tags ?? [])
    setBaseline(p.riot?.import_check?.original ?? null)
  }, [existing.data])

  useEffect(() => {
    const draft = (location.state as { draft?: RiotPreview } | null)?.draft
    if (isNew && draft && !scope.defaults) applyDraft(draft)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const refresh = useMutation({
    mutationFn: () => api<RiotPreview>(`/players/${playerId}/riot-refresh`, { method: 'POST' }),
    onSuccess: applyDraft,
  })

  const total = stats.aggr + stats.aware + stats.pos + stats.dmg + stats.cs
  // the ceiling follows the rank of a Riot import: a draft being reviewed first, then the saved player
  const rank = riotRank ?? existing.data?.riot?.rank
  const budget = riotRank?.budget ?? existing.data?.stat_budget ?? config.data?.player_stat_budget ?? 32
  const over = total - budget
  const sorted = useMemo(() => [...(champs.data ?? [])].sort((a, b) => a.name.localeCompare(b.name)), [champs.data])
  const changed = baseline ? [
    ...(role !== baseline.role ? ['role'] : []),
    ...(['aggr', 'aware', 'pos', 'dmg', 'cs'] as const).filter((k) => stats[k] !== baseline[k]),
    ...(baseline.pool.some((id, i) => pool[i] !== String(id)) ? ['pool'] : []),
    ...(baseline.negative_tags.some((k) => !tags.includes(k)) ? ['tags'] : []),
  ] : []
  const champName = (id: number) => champs.data?.find((c) => c.id === id)?.name ?? String(id)

  const save = useMutation({
    mutationFn: () => {
      const linked = Boolean(riotRef || existing.data?.riot)
      const body = { name, role, secondary_role: secondary || null, age, region, ...stats, pool: pool.map(Number), riot_ref: riotRef,
        ...(linked && !scope.defaults ? { tags } : {}) }
      return isNew ? api<Player>(`${scope.api}/players`, { body }) : api<Player>(`${scope.api}/players/${playerId}`, { method: 'PUT', body })
    },
    onSuccess: () => { invalidate(); navigate(`${scope.home}/players`) },
  })
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate() }
  const setStat = (key: keyof typeof stats, value: number) => setStats({ ...stats, [key]: Math.max(1, Math.min(10, value || 1)) })
  const poolLabels = ['Best pick (+40%)', 'Comfort (+25%)', 'Comfort (+25%)', 'Familiar (+10%)', 'Familiar (+10%)']
  const poolValid = pool.every(Boolean) && new Set(pool).size === pool.length

  if (!isNew && existing.isLoading) return <Loading />
  if (existing.data && existing.data.is_default !== scope.defaults) return (
    <div className="card"><p>{scope.defaults ? 'This is not a default player.' : 'Default players are read-only.'}</p><Link to={`${scope.home}/players`}>← Back</Link></div>
  )

  return (
    <form className="stack" onSubmit={submit}>
      <h1>{isNew ? 'New' : 'Edit'}{scope.defaults ? ' default' : ''} player</h1>
      {!scope.defaults && (riotRef || existing.data?.riot) && (
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
          {!riotRef && existing.data?.riot?.import_check?.status === 'unverified' && (
            <div className="notice notice-warn">This import can't be verified (it was imported before checks existed, or its record changed). Refresh it from Riot to verify it.</div>
          )}
          {changed.length > 0 ? (
            <div className="notice notice-warn">Saving will mark this player as <strong>edited</strong> (changed from the Riot import: {editedFieldsText(changed)}). Name, age, region and secondary role are free to change.</div>
          ) : baseline && <p className="small muted">✓ Matches the Riot import. Name, age, region and secondary role can change without affecting this.</p>}
          {riotRef && !isNew && <p className="small muted">Refreshed values are loaded below. Press Save to keep them.</p>}
        </div>
      )}
      <div className="card stack">
        <div className="grid two">
          <label>Name<input value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required /></label>
          <label>Primary role{baseline && role !== baseline.role && <span className="small muted"> (imported {LANE_LABEL[baseline.role]})</span>}
            <select value={role} onChange={(e) => { const l = e.target.value as Lane; setRole(l); if (l === secondary) setSecondary('') }}>{LANES.map((l) => <option key={l} value={l}>{LANE_LABEL[l]}</option>)}</select>
          </label>
          <label>Secondary role
            <select value={secondary} onChange={(e) => setSecondary(e.target.value as Lane | '')}>
              <option value="">None</option>
              {LANES.map((l) => <option key={l} value={l} disabled={l === role}>{LANE_LABEL[l]}</option>)}
            </select>
          </label>
          <label>Age<input type="number" min={16} max={99} value={age} onChange={(e) => setAge(Number(e.target.value))} /></label>
          <label>Region<input value={region} onChange={(e) => setRegion(e.target.value)} maxLength={16} /></label>
        </div>
      </div>
      {!scope.defaults && (riotRef || existing.data?.riot) && (
        <PlaystyleTagsCard earned={earned} tags={tags} setTags={setTags} />
      )}
      <div className="card stack">
        <div className="row between wrap">
          <h2>Stats</h2>
          <span className={`badge ${over > 0 ? 'badge-warn' : 'ok'}`} title={rank?.tier ? `The stat ceiling for ${rankLabel(rank)} is ${budget}` : undefined}>Total {total} / {budget}{rank?.tier ? ` (${rankLabel(rank)})` : ''}</span>
        </div>
        <div className="grid stats-inputs">
          {([['aggr', 'Aggression'], ['aware', 'Awareness'], ['pos', 'Positioning'], ['dmg', 'Damage'], ['cs', 'Farming (CS)']] as const).map(([key, label]) => (
            <label key={key}>{label}: <strong>{stats[key]}</strong>{baseline && stats[key] !== baseline[key] && <span className="small muted"> (imported {baseline[key]})</span>}
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
          <label key={i}>{poolLabels[i]}{baseline && i < baseline.pool.length && pool[i] !== String(baseline.pool[i]) && <span className="small muted"> (imported {champName(baseline.pool[i])})</span>}
            <select value={value} onChange={(e) => setPool(pool.map((v, j) => (j === i ? e.target.value : v)))} required>
              <option value="">Choose a champion…</option>
              {sorted.map((c) => <option key={c.id} value={c.id} disabled={pool.includes(String(c.id)) && pool[i] !== String(c.id)}>{c.name} ({c.class})</option>)}
            </select>
          </label>
        ))}
      </div>
      <ChampionFitCard stats={stats} pool={pool} />
      <ErrorNotice error={save.error} />
      <div className="row wrap">
        <button className="primary" disabled={save.isPending || !poolValid}>Save player</button>
        <Link className="button ghost" to={`${scope.home}/players`}>Cancel</Link>
      </div>
    </form>
  )
}

/** Choose which earned playstyle tags the player keeps (up to MAX_TAGS). Tags can't be added unless earned. */
function PlaystyleTagsCard({ earned, tags, setTags }: { earned: PlaystyleTag[]; tags: string[]; setTags: (t: string[]) => void }) {
  const byKey = new Map(earned.map((t) => [t.key, t]))
  const kept = tags.map((k) => byKey.get(k)).filter((t): t is PlaystyleTag => Boolean(t))
  const spare = sortTags(earned.filter((t) => !tags.includes(t.key)))
  const full = kept.length >= MAX_TAGS
  return (
    <div className="card stack">
      <div className="row between wrap">
        <h2>Playstyle tags</h2>
        <span className="badge">{kept.length} / {MAX_TAGS}</span>
      </div>
      <p className="small muted">
        Earned from this Riot account: ▲ strengths from its challenge levels, ▼ weaknesses from its recent games. Each tag nudges the simulation a little (hover for details).
        You can remove any tag, including weaknesses, and only add tags the account earned.
      </p>
      {earned.length === 0 ? <p className="muted small">This account has not earned any playstyle tags.</p> : (
        <>
          <div className="tag-list">
            {kept.length === 0 && <span className="muted small">No tags kept.</span>}
            {sortTags(kept).map((t) => <TagChip key={t.key} tag={t} onRemove={() => setTags(tags.filter((k) => k !== t.key))} />)}
          </div>
          {spare.length > 0 && (
            <div className="stack">
              <span className="muted small">Also earned{full ? ` (remove one to add another; ${MAX_TAGS} at most)` : ''}:</span>
              <div className="tag-list">
                {spare.map((t) => <TagChip key={t.key} tag={t} onAdd={() => setTags([...tags, t.key])} addDisabled={full} />)}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

const FIT_STAT_LABEL = { aggr: 'Aggression', aware: 'Awareness', pos: 'Positioning', dmg: 'Damage' } as const
const STRENGTH_STATS = { Offence: 'Damage and Positioning', Defence: 'Aggression', Control: 'Awareness' } as const

type FitSort = 'rank' | 'name' | 'class' | 'strength' | 'top_stat'
const FIT_SORT_TEXT: FitSort[] = ['name', 'class', 'top_stat']   // these start ascending, the rest best first

/** Every champion's lane fit for these stats, recomputed as the sliders and pool change; searchable and sortable. */
function ChampionFitCard({ stats, pool }: { stats: { aggr: number; aware: number; pos: number; dmg: number }; pool: string[] }) {
  const fit = useChampionFit(stats, pool.filter(Boolean).map(Number))
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<{ by: FitSort; desc: boolean }>({ by: 'rank', desc: true })
  const all = useMemo(() => (fit.data ?? []).map((r, i) => ({ ...r, rank: i + 1 })), [fit.data])
  const top = all[0]?.score || 1
  const q = query.trim().toLowerCase()
  const rows = all.filter((r) => !q || r.name.toLowerCase().includes(q) || r.class.toLowerCase().includes(q))
  rows.sort((x, y) => {
    const order = sort.by === 'name' ? x.name.localeCompare(y.name)
      : sort.by === 'class' ? x.class.localeCompare(y.class)
      : sort.by === 'top_stat' ? FIT_STAT_LABEL[x.top_stat].localeCompare(FIT_STAT_LABEL[y.top_stat])
      : sort.by === 'strength' ? x.strength_fit - y.strength_fit
      : y.rank - x.rank
    return (sort.desc ? -order : order) || x.rank - y.rank
  })
  const header = (by: FitSort, label: string, className = '') => (
    <th className={className} aria-sort={sort.by === by ? (sort.desc ? 'descending' : 'ascending') : undefined}>
      <button type="button" className="mx-sort" onClick={() => setSort({ by, desc: sort.by === by ? !sort.desc : !FIT_SORT_TEXT.includes(by) })}>
        {label}{sort.by === by ? (sort.desc ? ' ▼' : ' ▲') : ''}
      </button>
    </th>
  )
  return (
    <div className="card stack">
      <div className="row between wrap">
        <h2>Champion fits</h2>
        <input
          type="search"
          className="fit-search"
          placeholder="Search name or class"
          aria-label="Search champion fits"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') e.preventDefault() }}
        />
      </div>
      <p className="small muted">Based on the lane formula: these stats × each champion's attributes, boosted by pool comfort, then raised or lowered by the stats behind the champion's strength (Offence: Damage + Positioning, Defence: Aggression, Control: Awareness).</p>
      <ErrorNotice error={fit.error} />
      {fit.isLoading ? <Loading label="Ranking champions…" /> : (
        <>
          <p className="small muted">{q ? `${rows.length} of ${all.length}` : all.length} champions</p>
          <div className="table-scroll fit-table-scroll">
            <table className="compact fit-table">
              <thead>
                <tr>
                  <th className="fit-rank">#</th>
                  {header('name', 'Champion')}
                  {header('class', 'Class', 'fit-optional')}
                  {header('strength', 'Strength')}
                  {header('top_stat', 'Best stat', 'fit-optional')}
                  {header('rank', 'Fit', 'fit-score')}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.champion_id}>
                    <td className="fit-rank muted">{r.rank}</td>
                    <td>
                      <span className="row fit-name">
                        <ChampionIcon champion={r} size={22} />
                        <span>
                          {r.name}
                          {r.comfort_tier !== 'VULNERABLE' && <span className={`badge tier-${r.comfort_tier.toLowerCase()}`}>{TIER_LABEL[r.comfort_tier]}</span>}
                        </span>
                      </span>
                    </td>
                    <td className="fit-optional muted">{r.class}</td>
                    <td
                      className={r.strength_fit < 0.97 ? 'fit-penalty' : r.strength_fit > 1.03 ? 'fit-bonus' : 'muted'}
                      title={`${r.strength} champion: ${STRENGTH_STATS[r.strength]} stats ${r.strength_fit < 1 ? 'cut' : 'raise'} the lane score`}
                    >
                      {r.strength} ×{r.strength_fit.toFixed(2)}
                    </td>
                    <td className="fit-optional muted">{FIT_STAT_LABEL[r.top_stat]}</td>
                    <td className="fit-score">
                      <span className="fit-cell" title={`Fit ${r.score}`}>
                        <span className="fit-bar"><span style={{ width: `${(r.score / top) * 100}%` }} /></span>
                        {Math.round(r.score)}
                      </span>
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && <tr><td colSpan={6} className="muted">No champion matches “{query}”.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- coaches
export function CoachesPage({ scope = USER_SCOPE }: { scope?: Scope }) {
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
      return editing ? api(`${scope.api}/coaches/${editing.id}`, { method: 'PUT', body }) : api(`${scope.api}/coaches`, { body })
    },
    onSuccess: () => { invalidate(); reset() },
  })
  const del = useMutation({ mutationFn: (id: number) => api(`${scope.api}/coaches/${id}`, { method: 'DELETE' }), onSuccess: invalidate })
  function reset() { setEditing(null); setName(''); setDraft(5); setSynergy(5) }
  function edit(c: Coach) { setEditing(c); setName(c.name); setDraft(c.draft); setSynergy(c.synergy) }

  return (
    <div className="stack">
      <h1>{scope.defaults ? 'Default coaches' : 'Coaches'}</h1>
      <p className="muted">Draft makes your favourable lane matchups stronger in the match simulation. Synergy strengthens team cohesion (lane assists and playstyle bonuses).</p>
      <form className="card stack" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
        <h2>{editing ? 'Edit' : 'New'}{scope.defaults ? ' default' : ''} coach</h2>
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
      {(coaches.data ?? []).filter((c) => !scope.defaults || c.is_default).map((c) => (
        <div key={c.id} className="list-row">
          <span>{c.name} — Draft {c.draft}, Synergy {c.synergy} {c.is_default && !scope.defaults && <span className="badge">default</span>}</span>
          {c.is_default === scope.defaults && <span className="row">
            <button className="ghost small" onClick={() => edit(c)}>Edit</button>
            <button className="ghost small danger" onClick={() => confirmDelete(scope, c.name) && del.mutate(c.id)}>Delete</button>
          </span>}
        </div>
      ))}
      <p><Link to={`${scope.home}/teams`}>← {scope.defaults ? 'Default teams' : 'Teams'}</Link></p>
    </div>
  )
}
