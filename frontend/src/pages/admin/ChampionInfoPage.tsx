import { useEffect, useMemo, useState } from 'react'
import type { AdminChampion, AdminChampionColumn, AdminChampionField } from '../../api/types'
import { ChampionIcon, LaneIcon } from '../../components/ChampionArt'
import { ErrorNotice, Loading } from '../../components/common'
import { useAdminChampions, useResetChampions, useSaveChampions } from '../../hooks/useAdmin'
import {
  CHAMPION_COLUMNS, draftKey, filterAndSort, formatValue, parseValue, shownValue, toChanges,
  type ChampionDrafts, type ChampionSort, type ChampionSortBy,
} from '../../lib/championAdmin'
import { LANE_LABEL } from '../../lib/format'

function Cell({ champion, column, field, drafts, onChange }: {
  champion: AdminChampion
  column: AdminChampionColumn
  field: AdminChampionField
  drafts: ChampionDrafts
  onChange: (value: string) => void
}) {
  const text = shownValue(champion, column, drafts)
  const pending = drafts.has(draftKey(champion.id, column))
  const parsed = parseValue(field, text)
  const unsaved = pending && parsed !== champion[column]
  const edited = champion.edited.includes(column)
  const seed = champion.seed[column]
  const title = [
    edited && (seed !== undefined ? `Edited by an admin. CSV value: ${formatValue(seed)}` : 'Edited by an admin'),
    field.kind !== 'choice' && `${field.min} to ${field.max}`,
  ].filter(Boolean).join(' · ')
  const className = ['champ-admin-input', unsaved && 'unsaved', edited && 'edited'].filter(Boolean).join(' ')
  const label = `${champion.name} ${CHAMPION_COLUMNS.find((c) => c.key === column)?.label}`

  return (
    <td className="champ-admin-cell">
      {field.kind === 'choice' ? (
        <select className={className} aria-label={label} title={title} value={text} onChange={(e) => onChange(e.target.value)}>
          {field.choices.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      ) : (
        <input
          className={className}
          type="number"
          inputMode="decimal"
          aria-label={label}
          title={title}
          min={field.min}
          max={field.max}
          step={field.kind === 'int' ? 1 : 0.1}
          value={text}
          aria-invalid={parsed === undefined}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </td>
  )
}

/** Every champion's win rate, pick rate and attributes, editable in place. Edits beat the seed CSV until reset. */
export default function ChampionInfoPage() {
  const data = useAdminChampions()
  const save = useSaveChampions()
  const reset = useResetChampions()
  const [drafts, setDrafts] = useState<ChampionDrafts>(new Map())
  const [query, setQuery] = useState('')
  const [editedOnly, setEditedOnly] = useState(false)
  const [sort, setSort] = useState<ChampionSort>({ by: 'name', desc: false })

  const champions = data.data?.champions ?? []
  const fields = data.data?.fields
  const rows = useMemo(() => filterAndSort(data.data?.champions ?? [], query, editedOnly, sort), [data.data, query, editedOnly, sort])
  const { changes, count, invalid } = fields ? toChanges(champions, fields, drafts) : { changes: [], count: 0, invalid: [] }
  const dirty = count > 0 || invalid.length > 0
  const busy = save.isPending || reset.isPending
  const editedCount = champions.filter((c) => c.edited.length).length

  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const edit = (id: number, column: AdminChampionColumn, value: string) =>
    setDrafts((d) => new Map(d).set(draftKey(id, column), value))
  const clear = () => setDrafts(new Map())
  const dropDrafts = (id: number) =>
    setDrafts((d) => new Map([...d].filter(([key]) => !key.startsWith(`${id}:`))))

  const resetOne = (c: AdminChampion) => {
    const list = c.edited.map((k) => CHAMPION_COLUMNS.find((col) => col.key === k)?.label ?? k).join(', ')
    if (window.confirm(`Put ${c.name}'s ${list} back to the CSV values?`)) reset.mutate([c.id], { onSuccess: () => dropDrafts(c.id) })
  }
  const resetAll = () =>
    window.confirm(`Put every edited champion (${editedCount}) back to the CSV values? Unsaved changes are discarded too.`)
    && reset.mutate(null, { onSuccess: clear })

  const header = (by: ChampionSortBy, label: string, title?: string) => (
    <th key={by} className={by === 'name' || by === 'class' ? '' : 'meta-num'} title={title} aria-sort={sort.by === by ? (sort.desc ? 'descending' : 'ascending') : undefined}>
      <button type="button" className="mx-sort" onClick={() => setSort({ by, desc: sort.by === by ? !sort.desc : by !== 'name' && by !== 'class' })}>
        {label}{sort.by === by ? (sort.desc ? ' ▼' : ' ▲') : ''}
      </button>
    </th>
  )

  if (data.isLoading) return <Loading label="Loading champions…" />
  if (data.error || !fields) return <ErrorNotice error={data.error} />

  return (
    <div className="stack">
      <h1>Champion info</h1>
      <p className="muted small">
        Base win rate, pick rate and the attributes the simulation reads. Saved changes apply to drafts and matches started
        afterwards. Edited values are outlined; they are kept when the backend restarts, instead of being replaced by the seed
        CSV, until you reset them. Hover a value to see its range and CSV value.
      </p>
      <div className="row between wrap">
        <span className="muted small" aria-live="polite">
          {invalid.length
            ? `${invalid.length} ${invalid.length === 1 ? 'value is' : 'values are'} not valid: ${invalid.slice(0, 3).join(', ')}${invalid.length > 3 ? '…' : ''}`
            : count ? `${count} unsaved ${count === 1 ? 'change' : 'changes'}`
              : editedCount ? `${editedCount} ${editedCount === 1 ? 'champion differs' : 'champions differ'} from the CSV` : 'Every champion matches the CSV'}
        </span>
        <div className="row wrap">
          <button className="primary" disabled={!count || invalid.length > 0 || busy} onClick={() => save.mutate(changes, { onSuccess: clear })}>
            {save.isPending ? 'Saving…' : 'Save changes'}
          </button>
          <button className="ghost" disabled={!dirty || busy} onClick={clear}>Discard</button>
          <button className="ghost" disabled={!editedCount || busy} onClick={resetAll}>
            {reset.isPending ? 'Resetting…' : 'Reset all to CSV'}
          </button>
        </div>
      </div>
      {(save.error || reset.error) && <ErrorNotice error={save.error ?? reset.error} />}
      <div className="card stack">
        <div className="meta-toolbar">
          <input
            type="search"
            className="fit-search"
            placeholder="Search name or class"
            aria-label="Search champions"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <label className="row small">
            <input type="checkbox" checked={editedOnly} onChange={(e) => setEditedOnly(e.target.checked)} />
            Edited only
          </label>
          <span className="small muted">{rows.length === champions.length ? champions.length : `${rows.length} of ${champions.length}`} champions</span>
        </div>
        <div className="table-scroll meta-table-scroll">
          <table className="compact meta-table champ-admin-table">
            <thead>
              <tr>
                {header('name', 'Champion')}
                {header('class', 'Class')}
                {CHAMPION_COLUMNS.map((c) => header(c.key, c.short, `${c.label}: ${c.help}`))}
                <th><span className="sr-only">Reset</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className={c.enabled ? '' : 'muted'}>
                  <td>
                    <span className="row fit-name">
                      <ChampionIcon champion={c} size={22} />
                      {c.name}
                      {c.roles.map((r) => <span key={r} className="meta-role muted" title={LANE_LABEL[r]}><LaneIcon lane={r} size={14} /></span>)}
                      {!c.enabled && <span className="small muted">(disabled)</span>}
                      {!c.in_seed && <span className="small muted" title="Not in the seed CSV, so it cannot be reset">(not in CSV)</span>}
                    </span>
                  </td>
                  <td className="small muted">{c.class}</td>
                  {CHAMPION_COLUMNS.map((col) => (
                    <Cell key={col.key} champion={c} column={col.key} field={fields[col.key]} drafts={drafts} onChange={(v) => edit(c.id, col.key, v)} />
                  ))}
                  <td>
                    {c.edited.length > 0 && (
                      <button type="button" className="ghost small" disabled={busy} title="Put the CSV values back" onClick={() => resetOne(c)}>Reset</button>
                    )}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={CHAMPION_COLUMNS.length + 3} className="muted">No champion matches.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
