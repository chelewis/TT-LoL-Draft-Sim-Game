import { useMemo, useState } from 'react'
import { LANES, type Lane, type MetaChampion } from '../../api/types'
import { ChampionIcon, LaneIcon } from '../../components/ChampionArt'
import { ErrorNotice, Loading } from '../../components/common'
import Tooltip from '../../components/Tooltip'
import { useMetaChampions } from '../../hooks/useData'
import { togglePair } from '../../lib/championPair'
import { LANE_LABEL } from '../../lib/format'
import {
  championClasses, filterChampions, hasFilters, NO_FILTERS, sortChampions, startsDescending,
  type ChampionFilters, type ChampionSort, type ChampionSortBy,
} from '../../lib/metaChampions'
import ChampionPairDrawer from './ChampionPairDrawer'

const percent = (value: number) => `${value.toFixed(1)}%`

/** Why a low winrate champion can still be a good pick. No numbers: comfort and scaling values are admin settings. */
const LOW_WINRATE_TIP = (
  <div className="tip-content">
    <strong>Winrate is an average over every matchup.</strong> The simulation cares more about:
    <ul>
      <li><strong>Comfort:</strong> a champion high in the player's pool gets a big bonus; one outside their pool gets a penalty.</li>
      <li><strong>Difficulty:</strong> hard champions swing more in each fight: stronger on a practised player, risky on anyone else.</li>
      <li><strong>Scaling:</strong> late-game champions are weaker in lane but stronger in late fights; early-game champions are the
        opposite. Match them to the team style.</li>
      <li><strong>Partners and matchups:</strong> some champions do much better with certain allies or against certain opponents.
        Select two champions to check.</li>
      <li><strong>Comp fit:</strong> range, waveclear and damage type (magic or physical) can fill a gap in the team.</li>
    </ul>
  </div>
)

function winRateTitle(r: MetaChampion): string {
  return r.win_rate_source === 'matchups'
    ? `Expected win rate against the ${r.opponents} other ${r.role ? LANE_LABEL[r.role] : ''} champions, weighted by how often each is picked`
    : 'No same-lane against-team win rates for this champion, so this is its base win rate'
}

/** Every champion's win rate and pick rate: searchable, filterable by lane and class, sortable by any column.
 * Selecting two rows opens a drawer on how that pair does together and against each other. */
export default function ChampionsMetaPage() {
  const champions = useMetaChampions()
  const [filters, setFilters] = useState<ChampionFilters>(NO_FILTERS)
  const [sort, setSort] = useState<ChampionSort>({ by: 'win_rate', desc: true })
  const [selected, setSelected] = useState<number[]>([])
  const [pairOpen, setPairOpen] = useState(false)

  const all = champions.data ?? []
  const classes = useMemo(() => championClasses(champions.data ?? []), [champions.data])
  const rows = useMemo(() => sortChampions(filterChampions(champions.data ?? [], filters), sort), [champions.data, filters, sort])
  const filtered = hasFilters(filters)
  const byId = useMemo(() => new Map(all.map((r) => [r.id, r])), [all])
  const picked = selected.map((id) => byId.get(id)).filter((r): r is MetaChampion => r !== undefined)

  const toggle = (id: number) => {
    const next = togglePair(selected, id)
    setSelected(next)
    if (next.length === 2) setPairOpen(true)
  }
  const remove = (id: number) => setSelected((s) => s.filter((x) => x !== id))

  const toggleLane = (lane: Lane) =>
    setFilters((f) => ({ ...f, lanes: f.lanes.includes(lane) ? f.lanes.filter((l) => l !== lane) : [...f.lanes, lane] }))

  const header = (by: ChampionSortBy, label: string, className = '') => (
    <th className={className} aria-sort={sort.by === by ? (sort.desc ? 'descending' : 'ascending') : undefined}>
      <button type="button" className="mx-sort" onClick={() => setSort({ by, desc: sort.by === by ? !sort.desc : startsDescending(by) })}>
        {label}{sort.by === by ? (sort.desc ? ' ▼' : ' ▲') : ''}
      </button>
    </th>
  )

  return (
    <div className="stack">
      <h1>Champions</h1>
      <p className="small muted">
        Select two champions to see how they do on the same team and against each other. Winrate is how a champion
        does in its main lane: its against-team win rates (the ones the simulation uses)
        against champions with the same main role, weighted by how often each opponent is picked. Extreme matchups are
        softened, so a few hard counters can't sink an otherwise strong champion. Pick Rate is how often the champion is
        picked.{' '}
        <Tooltip label="Why a low winrate champion can still be a good pick" content={LOW_WINRATE_TIP}>
          <span className="has-tip">Low winrate ≠ bad pick</span>
        </Tooltip>
      </p>
      <div className="card stack">
        <div className="meta-toolbar">
          <input
            type="search"
            className="fit-search"
            placeholder="Search champions"
            aria-label="Search champions"
            value={filters.query}
            onChange={(e) => setFilters((f) => ({ ...f, query: e.target.value }))}
          />
          <div className="meta-lanes" role="group" aria-label="Filter by lane">
            {LANES.map((lane) => (
              <button
                key={lane}
                type="button"
                className="meta-lane"
                aria-pressed={filters.lanes.includes(lane)}
                title={LANE_LABEL[lane]}
                onClick={() => toggleLane(lane)}
              >
                <LaneIcon lane={lane} size={18} />
              </button>
            ))}
          </div>
          <select
            aria-label="Filter by class"
            value={filters.champClass}
            onChange={(e) => setFilters((f) => ({ ...f, champClass: e.target.value }))}
          >
            <option value="">All classes</option>
            {classes.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          {filtered && <button type="button" className="ghost small" onClick={() => setFilters(NO_FILTERS)}>Clear filters</button>}
        </div>
        <ErrorNotice error={champions.error} />
        {champions.isLoading ? <Loading label="Loading champions…" /> : (
          <>
            <div className="meta-pair-bar" aria-live="polite">
              <span className="small muted">{filtered ? `${rows.length} of ${all.length}` : all.length} champions</span>
              <span className="row wrap meta-pair-picked">
                {picked.length === 0 && <span className="small muted">Select two champions to compare them.</span>}
                {picked.map((r) => (
                  <span key={r.id} className="chip meta-pair-chip">
                    <ChampionIcon champion={r} size={18} />
                    {r.name}
                    <button type="button" className="ghost meta-pair-remove" onClick={() => remove(r.id)} aria-label={`Remove ${r.name}`}>✕</button>
                  </span>
                ))}
                {picked.length === 1 && <span className="small muted">Select one more.</span>}
                {picked.length === 2 && <button type="button" className="small" onClick={() => setPairOpen(true)}>Compare</button>}
                {picked.length > 0 && <button type="button" className="ghost small" onClick={() => setSelected([])}>Clear</button>}
              </span>
            </div>
            <div className="table-scroll meta-table-scroll">
              <table className="compact meta-table">
                <thead>
                  <tr>
                    <th className="meta-select"><span className="visually-hidden">Compare</span></th>
                    {header('name', 'Champion')}
                    {header('win_rate', 'Winrate', 'meta-num')}
                    {header('pick_rate', 'Pick Rate', 'meta-num')}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const isSelected = selected.includes(r.id)
                    return (
                      <tr key={r.id} className={isSelected ? 'meta-row-selected' : undefined} onClick={() => toggle(r.id)}>
                        <td className="meta-select">
                          <input type="checkbox" checked={isSelected} aria-label={`Select ${r.name} to compare`}
                                 onClick={(e) => e.stopPropagation()} onChange={() => toggle(r.id)} />
                        </td>
                        <td>
                          <span className="row fit-name">
                            <ChampionIcon champion={r} size={22} />
                            {r.name}
                            {r.role && <span className="meta-role muted" title={`Main role: ${LANE_LABEL[r.role]}`}><LaneIcon lane={r.role} size={14} /></span>}
                          </span>
                        </td>
                        <td className="meta-num" title={winRateTitle(r)}>
                          {percent(r.win_rate)}
                          {r.win_rate_source === 'base' && <span className="muted" aria-hidden="true"> *</span>}
                        </td>
                        <td className="meta-num">{percent(r.pick_rate)}</td>
                      </tr>
                    )
                  })}
                  {rows.length === 0 && <tr><td colSpan={4} className="muted">No champion matches these filters.</td></tr>}
                </tbody>
              </table>
            </div>
            {rows.some((r) => r.win_rate_source === 'base') && (
              <p className="small muted">* No same-lane against-team win rates, so this is the champion's base win rate.</p>
            )}
          </>
        )}
      </div>
      <ChampionPairDrawer a={picked[0]?.id ?? null} b={picked[1]?.id ?? null} open={pairOpen && picked.length === 2}
                          onClose={() => setPairOpen(false)} />
    </div>
  )
}
