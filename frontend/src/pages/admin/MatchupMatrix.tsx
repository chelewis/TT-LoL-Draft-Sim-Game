import { memo, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react'
import type { MatchupChampion, MatchupKind } from '../../api/types'
import { ChampionIcon } from '../../components/ChampionArt'
import { ErrorNotice, Loading } from '../../components/common'
import { useMatchups, useResetMatchups, useSaveMatchups } from '../../hooks/useAdmin'
import { COLOR_SPAN, cellColor, formatRate, indexCells, parseRate, readCell, writeCell, type CellView, type Pending, type StoredCell } from '../../lib/matchups'

const TEXT: Record<MatchupKind, { intro: string; joiner: string; listHeading: (name: string) => string; other: string }> = {
  ally: {
    intro: 'Win rate (%) of two champions when they are on the same team. A pair has one value, so each one appears twice, mirrored across the diagonal.',
    joiner: 'with',
    listHeading: (name) => `${name} on the same team as…`,
    other: 'Teammate',
  },
  enemy: {
    intro: "Win rate (%) of the row champion when the column champion is on the other team. The opposite cell is always 100 minus it, and is kept in step as you edit.",
    joiner: 'against',
    listHeading: (name) => `${name} against…`,
    other: 'Opponent',
  },
}

type Move = 'left' | 'right' | 'up' | 'down'
type GetCell = (row: number, col: number) => CellView

function cellTitle(kind: MatchupKind, row: MatchupChampion, col: MatchupChampion, view: CellView): string {
  const value = view.winRate === null ? 'no data' : `${formatRate(view.winRate)}%`
  const notes = [view.games ? `${view.games} games` : '', view.pending ? 'not saved yet' : view.edited ? 'edited by an admin' : '']
  return `${row.name} ${TEXT[kind].joiner} ${col.name}: ${[value, ...notes].filter(Boolean).join(' · ')}`
}

/** The one text box that moves to whichever matrix cell is being edited. */
function CellInput({ initial, label, onDone }: { initial: number | null; label: string; onDone: (value: number | null | undefined, move?: Move) => void }) {
  const [text, setText] = useState(initial === null ? '' : String(initial))
  const done = useRef(false)
  const finish = (value: number | null | undefined, move?: Move) => {
    if (done.current) return // Enter and Tab are followed by a blur as the box is removed
    done.current = true
    onDone(value, move)
  }
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') finish(parseRate(text), e.shiftKey ? 'up' : 'down')
    else if (e.key === 'Tab') { e.preventDefault(); finish(parseRate(text), e.shiftKey ? 'left' : 'right') }
    else if (e.key === 'Escape') finish(undefined)
  }
  return (
    <input
      className="mx-input"
      autoFocus
      inputMode="decimal"
      aria-label={label}
      aria-invalid={parseRate(text) === undefined}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onFocus={(e) => e.target.select()}
      onBlur={() => finish(parseRate(text))}
      onKeyDown={onKeyDown}
    />
  )
}

interface RowProps {
  kind: MatchupKind
  champion: MatchupChampion
  columns: MatchupChampion[]
  activeCol: number | null
  getCell: GetCell
  onDone: (row: number, col: number, value: number | null | undefined, move?: Move) => void
  onFocus: (id: number) => void
  // not read: they change when this row's cells do, which is what makes the memoised row render again
  stored: Map<string, StoredCell>
  version: number
  epoch: number
}

/** One matrix row. Memoised so that an edit re-renders the two rows it touches, not all of them. */
const MatrixRow = memo(function MatrixRow({ kind, champion, columns, activeCol, getCell, onDone, onFocus }: RowProps) {
  return (
    <tr data-r={champion.id}>
      <th scope="row" className="mx-rowhead">
        <button type="button" className="mx-head" onClick={() => onFocus(champion.id)} title={`Show only ${champion.name}`}>
          <ChampionIcon champion={champion} size={20} />
          <span>{champion.name}</span>
        </button>
      </th>
      {columns.map((col) => {
        if (col.id === champion.id) return <td key={col.id} className="mx-diag" />
        const view = getCell(champion.id, col.id)
        if (col.id === activeCol) {
          return (
            <td key={col.id} className="mx-editing">
              <CellInput initial={view.winRate} label={`${champion.name} ${TEXT[kind].joiner} ${col.name}`} onDone={(value, move) => onDone(champion.id, col.id, value, move)} />
            </td>
          )
        }
        const classes = [view.winRate === null ? 'mx-none' : '', view.pending ? 'mx-pending' : view.edited ? 'mx-edited' : ''].join(' ').trim()
        return (
          <td key={col.id} data-c={col.id} className={classes || undefined} style={{ background: cellColor(view.winRate) }} title={cellTitle(kind, champion, col, view)}>
            {formatRate(view.winRate)}
          </td>
        )
      })}
    </tr>
  )
})

function Legend() {
  return (
    <div className="mx-legend small muted" aria-label="Colour key">
      <span>{50 - COLOR_SPAN} or less</span>
      <span className="mx-legend-bar" aria-hidden="true" />
      <span>{50 + COLOR_SPAN} or more</span>
      <span className="mx-legend-mark"><i className="mx-key mx-key-edited" aria-hidden="true" /> edited by an admin</span>
      <span className="mx-legend-mark"><i className="mx-key mx-key-pending" aria-hidden="true" /> not saved yet</span>
      <span className="mx-legend-mark">– no data</span>
    </div>
  )
}

type SortBy = 'name' | 'rate'

/** One champion's pairs as a list: the comfortable way to edit on a phone, or to work through one champion. */
function FocusList({ kind, champion, others, getCell, onCommit }: {
  kind: MatchupKind
  champion: MatchupChampion
  others: MatchupChampion[]
  getCell: GetCell
  onCommit: (row: number, col: number, value: number | null) => void
}) {
  const [sort, setSort] = useState<{ by: SortBy; desc: boolean }>({ by: 'name', desc: false })
  const rows = others.map((other) => ({ other, view: getCell(champion.id, other.id) }))
  rows.sort((x, y) => {
    const order = sort.by === 'name'
      ? x.other.name.localeCompare(y.other.name)
      : (x.view.winRate ?? -1) - (y.view.winRate ?? -1) || x.other.name.localeCompare(y.other.name)
    return sort.desc ? -order : order
  })
  const header = (by: SortBy, label: string) => (
    <th aria-sort={sort.by === by ? (sort.desc ? 'descending' : 'ascending') : undefined}>
      <button type="button" className="mx-sort" onClick={() => setSort({ by, desc: sort.by === by ? !sort.desc : by === 'rate' })}>
        {label}{sort.by === by ? (sort.desc ? ' ▼' : ' ▲') : ''}
      </button>
    </th>
  )
  return (
    <div className="card stack">
      <h2 className="row"><ChampionIcon champion={champion} size={28} /> {TEXT[kind].listHeading(champion.name)}</h2>
      <div className="table-scroll">
        <table className="compact mx-list">
          <thead>
            <tr>{header('name', TEXT[kind].other)}{header('rate', 'Win rate %')}<th>Games</th><th>Status</th></tr>
          </thead>
          <tbody>
            {rows.map(({ other, view }) => (
              <tr key={other.id}>
                <td><span className="row"><ChampionIcon champion={other} size={22} /> {other.name}</span></td>
                <td>
                  <span className="mx-list-rate">
                    <i className="mx-swatch" style={{ background: cellColor(view.winRate) }} aria-hidden="true" />
                    <input
                      key={String(view.winRate)}
                      className="mx-list-input"
                      inputMode="decimal"
                      placeholder="–"
                      aria-label={`${champion.name} ${TEXT[kind].joiner} ${other.name}`}
                      defaultValue={view.winRate === null ? '' : String(view.winRate)}
                      onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }}
                      onBlur={(e) => {
                        const value = parseRate(e.target.value)
                        if (value === undefined) e.target.value = view.winRate === null ? '' : String(view.winRate)
                        else if (value !== view.winRate) onCommit(champion.id, other.id, value)
                      }}
                    />
                  </span>
                </td>
                <td className="muted">{view.games || '–'}</td>
                <td>{view.pending ? <span className="badge gold">Not saved</span> : view.edited ? <span className="badge">Edited</span> : null}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function MatchupMatrix({ kind, onDirtyChange }: { kind: MatchupKind; onDirtyChange: (dirty: boolean) => void }) {
  const query = useMatchups(kind)
  const save = useSaveMatchups(kind)
  const reset = useResetMatchups(kind)
  const [pending, setPending] = useState<Pending>(() => new Map())
  const [versions, setVersions] = useState<Map<number, number>>(() => new Map()) // champion id -> edits touching its row
  const [epoch, setEpoch] = useState(0) // bumped when every row must be drawn again
  const [active, setActive] = useState<{ row: number; col: number } | null>(null)
  const [focusId, setFocusId] = useState<number | null>(null)

  const champions = useMemo(() => query.data?.champions ?? [], [query.data])
  const stored = useMemo(() => indexCells(query.data?.cells ?? []), [query.data])
  const filled = useMemo(() => (query.data?.cells ?? []).filter((c) => c[2] !== null).length, [query.data])

  // rows read cells through a stable function, so they only render again when their own props change
  const storedRef = useRef(stored)
  const pendingRef = useRef(pending)
  storedRef.current = stored
  pendingRef.current = pending
  const getCell = useCallback<GetCell>((row, col) => readCell(kind, storedRef.current, pendingRef.current, row, col), [kind])

  const dirty = pending.size > 0
  useEffect(() => {
    onDirtyChange(dirty)
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, onDirtyChange])
  useEffect(() => () => onDirtyChange(false), [onDirtyChange])

  const commit = useCallback((row: number, col: number, value: number | null) => {
    setPending((p) => writeCell(kind, storedRef.current, p, row, col, value))
    setVersions((v) => new Map(v).set(row, (v.get(row) ?? 0) + 1).set(col, (v.get(col) ?? 0) + 1))
  }, [kind])

  const order = useMemo(() => champions.map((c) => c.id), [champions])
  const finishEdit = useCallback((row: number, col: number, value: number | null | undefined, move?: Move) => {
    if (value !== undefined) commit(row, col, value)
    if (!move || value === undefined) return setActive(null)
    let r = order.indexOf(row)
    let c = order.indexOf(col)
    do {
      if (move === 'left') c -= 1
      else if (move === 'right') c += 1
      else if (move === 'up') r -= 1
      else r += 1
    } while (r === c) // step over the diagonal
    setActive(r >= 0 && c >= 0 && r < order.length && c < order.length ? { row: order[r], col: order[c] } : null)
  }, [commit, order])

  const onGridClick = (e: MouseEvent<HTMLTableSectionElement>) => {
    const cell = (e.target as HTMLElement).closest<HTMLElement>('td[data-c]')
    const row = cell?.closest<HTMLElement>('tr[data-r]')
    if (cell && row) setActive({ row: Number(row.dataset.r), col: Number(cell.dataset.c) })
  }

  const clearEdits = () => { setPending(new Map()); setVersions(new Map()); setActive(null); setEpoch((n) => n + 1) }
  const busy = save.isPending || reset.isPending

  if (query.isLoading) return <Loading label="Loading win rates…" />
  if (query.error) return <ErrorNotice error={query.error} />

  const focused = champions.find((c) => c.id === focusId)
  const pairs = (champions.length * (champions.length - 1)) / 2

  return (
    <div className="stack">
      <p className="muted small">{TEXT[kind].intro}</p>
      {filled === 0 && (
        <div className="notice notice-warn">
          This matrix has no data yet. Fill cells in by hand, or sample matches with <code>python -m scripts.champion_synergy</code>, copy the CSV it writes into <code>backend/app/data/seed/</code> and press “Reset to seed data”.
        </div>
      )}
      <div className="row between wrap">
        <label className="mx-focus">
          Champion
          <select value={focusId ?? ''} onChange={(e) => { setActive(null); setFocusId(e.target.value ? Number(e.target.value) : null) }}>
            <option value="">All champions (matrix)</option>
            {champions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <div className="row wrap">
          <span className="muted small" aria-live="polite">{dirty ? `${pending.size} unsaved ${pending.size === 1 ? 'change' : 'changes'}` : `${filled.toLocaleString()} of ${pairs.toLocaleString()} pairs have a value`}</span>
          <button className="primary" disabled={!dirty || busy} onClick={() => save.mutate(pending, { onSuccess: clearEdits })}>
            {save.isPending ? 'Saving…' : 'Save changes'}
          </button>
          <button className="ghost" disabled={!dirty || busy} onClick={clearEdits}>Discard</button>
          <button
            className="ghost danger"
            disabled={busy}
            onClick={() => window.confirm('Replace this whole matrix with the seed file on the server? Every edit made here, saved or not, is lost.') && reset.mutate(undefined, { onSuccess: clearEdits })}
          >
            {reset.isPending ? 'Resetting…' : 'Reset to seed data'}
          </button>
        </div>
      </div>
      <ErrorNotice error={save.error ?? reset.error} />
      <Legend />
      {focused ? (
        <FocusList kind={kind} champion={focused} others={champions.filter((c) => c.id !== focused.id)} getCell={getCell} onCommit={commit} />
      ) : (
        <>
          <div className="mx-scroll">
            <table className="mx">
              <thead>
                <tr>
                  <th className="mx-rowhead mx-corner">{kind === 'enemy' ? 'Row vs column' : 'Champion'}</th>
                  {champions.map((c) => (
                    <th key={c.id} scope="col">
                      <button type="button" className="mx-head" onClick={() => setFocusId(c.id)} title={c.name} aria-label={c.name}>
                        <ChampionIcon champion={c} size={24} />
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody onClick={onGridClick}>
                {champions.map((c) => (
                  <MatrixRow
                    key={c.id}
                    kind={kind}
                    champion={c}
                    columns={champions}
                    activeCol={active?.row === c.id ? active.col : null}
                    getCell={getCell}
                    onDone={finishEdit}
                    onFocus={setFocusId}
                    stored={stored}
                    version={versions.get(c.id) ?? 0}
                    epoch={epoch}
                  />
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small">Click a cell to edit it. Enter moves down, Tab moves right, Esc cancels; an empty box clears the cell. Click a champion to see only its pairs as a list.</p>
        </>
      )}
    </div>
  )
}
