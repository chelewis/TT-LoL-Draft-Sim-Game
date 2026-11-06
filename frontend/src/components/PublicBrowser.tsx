import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { Coach, Player, PlaystyleTag, PublicKind, SearchFilters, Shared, SharedTeam } from '../api/types'
import { LANES, STYLES } from '../api/types'
import { useChampions, usePublicSearch } from '../hooks/useData'
import { LANE_LABEL, RANK_TIERS, rankLabel, roleLabel, titleCase } from '../lib/format'
import { ErrorNotice, Loading } from './common'
import RiotBadge from './RiotBadge'
import { TagChip } from './TagChips'

const PAGE = 20
const STAT_FIELDS = [['aggr', 'Aggression'], ['aware', 'Awareness'], ['pos', 'Positioning'], ['dmg', 'Damage'], ['cs', 'CS']] as const

type Fields = Record<string, string>

function useDebounced<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return debounced
}

function remembered(key: string): boolean {
  try {
    return localStorage.getItem(key) === 'open'
  } catch {
    return false
  }
}

/** An expandable card, closed by default, that remembers whether it was open. */
function BrowseSection({ title, storageKey, children }: { title: string; storageKey: string; children: (open: boolean) => ReactNode }) {
  const [open, setOpen] = useState(() => remembered(storageKey))
  return (
    <details
      className="card stack public-browser"
      open={open}
      onToggle={(e) => {
        const next = (e.currentTarget as HTMLDetailsElement).open
        setOpen(next)
        try {
          localStorage.setItem(storageKey, next ? 'open' : 'closed')
        } catch {
          /* just not remembered */
        }
      }}
    >
      <summary><h2>{title}</h2></summary>
      {open && children(open)}
    </details>
  )
}

/** Text fields -> query filters (blank fields are dropped by the query builder). */
const asFilters = (fields: Fields): SearchFilters => Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, v.trim()]))

function NumberField({ label, name, fields, set, min, max }: { label: string; name: string; fields: Fields; set: (k: string, v: string) => void; min?: number; max?: number }) {
  return (
    <label className="small">
      {label}
      <input type="number" min={min} max={max} value={fields[name] ?? ''} onChange={(e) => set(name, e.target.value)} />
    </label>
  )
}

function RankSelect({ label, name, fields, set }: { label: string; name: string; fields: Fields; set: (k: string, v: string) => void }) {
  return (
    <label className="small">
      {label}
      <select value={fields[name] ?? ''} onChange={(e) => set(name, e.target.value)}>
        <option value="">Any</option>
        {RANK_TIERS.map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}
      </select>
    </label>
  )
}

function SortSelect({ fields, set, options }: { fields: Fields; set: (k: string, v: string) => void; options: [string, string][] }) {
  return (
    <label className="small">
      Sort by
      <select value={fields.sort ?? 'newest'} onChange={(e) => set('sort', e.target.value)}>
        {options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
    </label>
  )
}

/** Shared search state: filter fields, debounced, with paging that resets when a filter changes. */
function useSearch<T>(kind: PublicKind, open: boolean, extra: SearchFilters = {}) {
  const [fields, setFields] = useState<Fields>({})
  const [offset, setOffset] = useState(0)
  const set = (k: string, v: string) => { setFields((f) => ({ ...f, [k]: v })); setOffset(0) }
  const reset = () => { setFields({}); setOffset(0) }
  // debounce the serialized filters: a fresh object every render would never settle
  const settled = useDebounced(JSON.stringify({ ...asFilters(fields), ...extra }))
  const filters = useMemo(() => JSON.parse(settled) as SearchFilters, [settled])
  const results = usePublicSearch<T>(kind, { ...filters, offset, limit: PAGE }, open)
  return { fields, set, reset, results, offset, setOffset }
}

/** "Add to my …": copies the public item into the user's account. Remembers which ones were added. */
function useCopy(kind: PublicKind) {
  const qc = useQueryClient()
  const [added, setAdded] = useState<Set<number>>(new Set())
  const copy = useMutation({
    mutationFn: (id: number) => api(`/public/${kind}/${id}/copy`, { method: 'POST' }),
    onSuccess: (_, id) => {
      setAdded((s) => new Set(s).add(id))
      qc.invalidateQueries({ queryKey: [kind] })
      if (kind === 'teams') {
        qc.invalidateQueries({ queryKey: ['players'] })
        qc.invalidateQueries({ queryKey: ['coaches'] })
      }
    },
  })
  const button = (id: number, label: string) => (
    <button type="button" className="ghost small" disabled={copy.isPending || added.has(id)} onClick={() => copy.mutate(id)}>
      {added.has(id) ? 'Added ✓' : label}
    </button>
  )
  return { copy, button }
}

function Pager({ total, offset, setOffset, fetching }: { total: number; offset: number; setOffset: (n: number) => void; fetching: boolean }) {
  if (total === 0) return null
  const end = Math.min(total, offset + PAGE)
  return (
    <div className="row between wrap small">
      <span className="muted">{offset + 1}–{end} of {total}{fetching ? ' · updating…' : ''}</span>
      <span className="row">
        <button type="button" className="ghost small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>← Previous</button>
        <button type="button" className="ghost small" disabled={end >= total} onClick={() => setOffset(offset + PAGE)}>Next →</button>
      </span>
    </div>
  )
}

/** A collapsible card section (closed by default, then remembers the viewer's choice). */
export function CollapsibleSection({ title, storageKey, children }: { title: string; storageKey: string; children: ReactNode }) {
  return <BrowseSection title={title} storageKey={storageKey}>{() => children}</BrowseSection>
}

// ---------------------------------------------------------------- players
const usePlaystyleTagList = () =>
  useQuery({ queryKey: ['playstyle-tags'], queryFn: () => api<PlaystyleTag[]>('/playstyle-tags'), staleTime: 300000 })
const useRiotRegions = () =>
  useQuery({ queryKey: ['riot-status'], queryFn: () => api<{ enabled: boolean; regions: string[] }>('/riot/status'), staleTime: 60000 })

export function PublicPlayersBrowser() {
  return (
    <BrowseSection title="Browse public players" storageKey="ldm_browse_players">
      {(open) => <PlayerSearch open={open} />}
    </BrowseSection>
  )
}

function PlayerSearch({ open }: { open: boolean }) {
  const [champions, setChampions] = useState<number[]>([])
  const [tags, setTags] = useState<string[]>([])
  const { fields, set, reset, results, offset, setOffset } = useSearch<Shared<Player>>('players', open, { champions, tags })
  const champs = useChampions()
  const tagList = usePlaystyleTagList()
  const regions = useRiotRegions()
  const { copy, button } = useCopy('players')
  const names = new Map((champs.data ?? []).map((c) => [c.id, c.name]))
  const tagByKey = new Map((tagList.data ?? []).map((t) => [t.key, t]))
  const page = results.data

  return (
    <div className="stack">
      <p className="muted small">Genuine Riot imports other users have shared. Adding one makes your own copy, which stays a verified import.</p>
      <div className="grid three">
        <label className="small">Name<input value={fields.q ?? ''} onChange={(e) => set('q', e.target.value)} placeholder="Riot name" /></label>
        <label className="small">Role (primary or secondary)
          <select value={fields.role ?? ''} onChange={(e) => set('role', e.target.value)}>
            <option value="">Any</option>
            {LANES.map((l) => <option key={l} value={l}>{LANE_LABEL[l]}</option>)}
          </select>
        </label>
        <label className="small">Region
          <select value={fields.region ?? ''} onChange={(e) => set('region', e.target.value)}>
            <option value="">Any</option>
            {(regions.data?.regions ?? []).map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        <RankSelect label="Rank from" name="rank_min" fields={fields} set={set} />
        <RankSelect label="Rank to" name="rank_max" fields={fields} set={set} />
        <SortSelect fields={fields} set={set} options={[['newest', 'Newest'], ['total', 'Stat total'], ['rank', 'Rank'], ['name', 'Name']]} />
      </div>
      <div className="grid three">
        {STAT_FIELDS.map(([key, label]) => (
          <div key={key} className="row">
            <NumberField label={`${label} min`} name={`${key}_min`} fields={fields} set={set} min={1} max={10} />
            <NumberField label="max" name={`${key}_max`} fields={fields} set={set} min={1} max={10} />
          </div>
        ))}
        <div className="row">
          <NumberField label="Stat total min" name="total_min" fields={fields} set={set} min={5} max={50} />
          <NumberField label="max" name="total_max" fields={fields} set={set} min={5} max={50} />
        </div>
      </div>
      <div className="grid two">
        <div className="stack">
          <label className="small">Champion pool includes (all of)
            <select value="" onChange={(e) => { const id = Number(e.target.value); if (id && !champions.includes(id)) { setChampions([...champions, id]); setOffset(0) } }}>
              <option value="">Add a champion…</option>
              {[...(champs.data ?? [])].sort((a, b) => a.name.localeCompare(b.name)).map((c) => (
                <option key={c.id} value={c.id} disabled={champions.includes(c.id)}>{c.name}</option>
              ))}
            </select>
          </label>
          <div>{champions.map((id) => (
            <span key={id} className="chip">{names.get(id) ?? id}{' '}
              <button type="button" className="tag-chip-btn" aria-label={`Remove ${names.get(id)}`} onClick={() => setChampions(champions.filter((c) => c !== id))}>✕</button>
            </span>
          ))}</div>
        </div>
        <div className="stack">
          <label className="small">Has playstyle tags (all of)
            <select value="" onChange={(e) => { const k = e.target.value; if (k && !tags.includes(k)) { setTags([...tags, k]); setOffset(0) } }}>
              <option value="">Add a tag…</option>
              {(tagList.data ?? []).map((t) => <option key={t.key} value={t.key} disabled={tags.includes(t.key)}>{t.label}</option>)}
            </select>
          </label>
          <div>{tags.map((k) => {
            const tag = tagByKey.get(k)
            return tag ? <TagChip key={k} tag={tag} onRemove={() => setTags(tags.filter((t) => t !== k))} /> : null
          })}</div>
        </div>
      </div>
      <div><button type="button" className="ghost small" onClick={() => { reset(); setChampions([]); setTags([]) }}>Clear filters</button></div>

      <ErrorNotice error={results.error ?? copy.error} />
      {results.isLoading && <Loading />}
      {page && page.total === 0 && <p className="muted">No public players match.</p>}
      {page && page.items.length > 0 && (
        <div className="table-scroll"><table>
          <thead><tr><th>Name</th><th>Role</th><th>Rank</th><th title="aggr/aware/pos/dmg/cs">Stats</th><th>Total</th><th>Champion pool</th><th>Shared by</th><th /></tr></thead>
          <tbody>{page.items.map((p) => (
            <tr key={p.id}>
              <td>{p.name} <RiotBadge riot={p.riot} showAccount />{p.riot?.region && <span className="badge">{p.riot.region}</span>}</td>
              <td>{roleLabel(p)}</td>
              <td>{rankLabel(p.riot?.rank)}</td>
              <td>{p.aggr}/{p.aware}/{p.pos}/{p.dmg}/{p.cs}</td>
              <td>{p.stat_total}</td>
              <td className="small muted">{p.pool.map((id) => names.get(id)).join(', ')}</td>
              <td className="small">{p.owner}</td>
              <td>{button(p.id, 'Add to my players')}</td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
      {page && <Pager total={page.total} offset={offset} setOffset={setOffset} fetching={results.isFetching} />}
    </div>
  )
}

// ---------------------------------------------------------------- coaches
export function PublicCoachesBrowser() {
  return (
    <BrowseSection title="Browse public coaches" storageKey="ldm_browse_coaches">
      {(open) => <CoachSearch open={open} />}
    </BrowseSection>
  )
}

function CoachSearch({ open }: { open: boolean }) {
  const { fields, set, reset, results, offset, setOffset } = useSearch<Shared<Coach>>('coaches', open)
  const { copy, button } = useCopy('coaches')
  const page = results.data
  return (
    <div className="stack">
      <div className="grid three">
        <label className="small">Name<input value={fields.q ?? ''} onChange={(e) => set('q', e.target.value)} /></label>
        <div className="row">
          <NumberField label="Draft min" name="draft_min" fields={fields} set={set} min={1} max={10} />
          <NumberField label="max" name="draft_max" fields={fields} set={set} min={1} max={10} />
        </div>
        <div className="row">
          <NumberField label="Synergy min" name="synergy_min" fields={fields} set={set} min={1} max={10} />
          <NumberField label="max" name="synergy_max" fields={fields} set={set} min={1} max={10} />
        </div>
        <SortSelect fields={fields} set={set} options={[['newest', 'Newest'], ['total', 'Draft + Synergy'], ['name', 'Name']]} />
      </div>
      <div><button type="button" className="ghost small" onClick={reset}>Clear filters</button></div>
      <ErrorNotice error={results.error ?? copy.error} />
      {results.isLoading && <Loading />}
      {page && page.total === 0 && <p className="muted">No public coaches match.</p>}
      {page?.items.map((c) => (
        <div key={c.id} className="list-row">
          <span>{c.name} — Draft {c.draft}, Synergy {c.synergy} <span className="muted small">· shared by {c.owner}</span></span>
          {button(c.id, 'Add to my coaches')}
        </div>
      ))}
      {page && <Pager total={page.total} offset={offset} setOffset={setOffset} fetching={results.isFetching} />}
    </div>
  )
}

// ------------------------------------------------------------------ teams
export function PublicTeamsBrowser() {
  return (
    <BrowseSection title="Browse public teams" storageKey="ldm_browse_teams">
      {(open) => <TeamSearch open={open} />}
    </BrowseSection>
  )
}

function TeamSearch({ open }: { open: boolean }) {
  const { fields, set, reset, results, offset, setOffset } = useSearch<SharedTeam>('teams', open)
  const champs = useChampions()
  const { copy, button } = useCopy('teams')
  const page = results.data
  const tierName = (avg: number | null) => (avg === null ? 'Unranked' : titleCase(RANK_TIERS[Math.round(avg)]))
  return (
    <div className="stack">
      <p className="muted small">Teams of genuine Riot imports. Adding one copies the team, its players and its coach into your account.</p>
      <div className="grid three">
        <label className="small">Team name<input value={fields.q ?? ''} onChange={(e) => set('q', e.target.value)} /></label>
        <label className="small">Has a player named<input value={fields.player ?? ''} onChange={(e) => set('player', e.target.value)} /></label>
        <label className="small">Playstyle
          <select value={fields.style ?? ''} onChange={(e) => set('style', e.target.value)}>
            <option value="">Any</option>
            {STYLES.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
          </select>
        </label>
        <label className="small">Focus lane
          <select value={fields.focus ?? ''} onChange={(e) => set('focus', e.target.value)}>
            <option value="">Any</option>
            {LANES.map((l) => <option key={l} value={l}>{LANE_LABEL[l]}</option>)}
          </select>
        </label>
        <RankSelect label="Average rank from" name="rank_min" fields={fields} set={set} />
        <RankSelect label="Average rank to" name="rank_max" fields={fields} set={set} />
        <div className="row">
          <NumberField label="Team stat total min" name="total_min" fields={fields} set={set} min={25} max={250} />
          <NumberField label="max" name="total_max" fields={fields} set={set} min={25} max={250} />
        </div>
        <label className="small">A player's pool has
          <select value={fields.champion ?? ''} onChange={(e) => set('champion', e.target.value)}>
            <option value="">Any champion</option>
            {[...(champs.data ?? [])].sort((a, b) => a.name.localeCompare(b.name)).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <div className="row">
          <NumberField label="Coach draft min" name="coach_draft_min" fields={fields} set={set} min={1} max={10} />
          <NumberField label="Coach synergy min" name="coach_synergy_min" fields={fields} set={set} min={1} max={10} />
        </div>
        <SortSelect fields={fields} set={set} options={[['newest', 'Newest'], ['total', 'Stat total'], ['rank', 'Average rank'], ['name', 'Name']]} />
      </div>
      <div><button type="button" className="ghost small" onClick={reset}>Clear filters</button></div>
      <ErrorNotice error={results.error ?? copy.error} />
      {results.isLoading && <Loading />}
      {page && page.total === 0 && <p className="muted">No public teams match.</p>}
      <div className="grid two">
        {page?.items.map((t) => (
          <div key={t.id} className="card stack">
            <div className="row between wrap">
              <h3>{t.name}</h3>
              <span className="small muted">shared by {t.owner}</span>
            </div>
            <p className="small muted">
              {[t.style1, t.style2].filter(Boolean).map(titleCase).join(' + ')}
              {t.coach ? ` · coach ${t.coach.name} (${t.coach.draft}/${t.coach.synergy})` : ''}
              {` · stats ${t.stat_total} · avg ${tierName(t.average_rank)}`}
            </p>
            <p className="small">
              {LANES.map((l) => {
                const p = t.roster[l]
                return <span key={l} className="chip">{LANE_LABEL[l]}: {p ? p.name : '—'}</span>
              })}
            </p>
            <div className="row wrap">{button(t.id, 'Add to my teams')}</div>
          </div>
        ))}
      </div>
      {page && <Pager total={page.total} offset={offset} setOffset={setOffset} fetching={results.isFetching} />}
    </div>
  )
}
