import { useState, type FormEvent } from 'react'
import type { AdminPlaystyleTag, ChallengeRule, Lane, MatchRule, PlaystyleOptions } from '../../api/types'
import { ErrorNotice, Loading } from '../../components/common'
import { TagChip } from '../../components/TagChips'
import { useDeletePlaystyleTag, usePlaystyleOptions, usePlaystyleTags, useSavePlaystyleTag, type PlaystyleTagBody } from '../../hooks/useAdmin'
import { LANE_LABEL, titleCase } from '../../lib/format'
import { effectText } from '../../lib/playstyle'

const slug = (text: string) => text.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').replace(/^[^a-z]+/, '').slice(0, 32)

const blank = (): PlaystyleTagBody => ({
  key: '', label: '', description: '', polarity: 'positive', source: 'challenge',
  rule: { challenges: [], min_level: 'DIAMOND' }, effects: [{ hook: 'lane_score', value: 0.03 }], enabled: true, sort_order: 500,
})

const defaultRule = (source: 'challenge' | 'match', options?: PlaystyleOptions): ChallengeRule | MatchRule =>
  source === 'challenge'
    ? { challenges: [], min_level: 'DIAMOND' }
    : { metric: options?.metrics[0]?.metric ?? 'deaths_per_min', op: '>=', value: null, lanes: {} }

/** "Diamond+ in Solo Bolo / Flame Horizon" or "Deaths per minute ≥ 0.3 (Top 0.25, not Support)". */
function ruleText(tag: Pick<AdminPlaystyleTag, 'source' | 'rule'>, options?: PlaystyleOptions): string {
  if (tag.source === 'challenge') {
    const r = tag.rule as ChallengeRule
    return `${titleCase(r.min_level)}+ in ${r.challenges.map((c) => c.name).join(' / ') || 'no challenges'}`
  }
  const r = tag.rule as MatchRule
  const label = options?.metrics.find((m) => m.metric === r.metric)?.label ?? r.metric
  const op = r.op === '>=' ? '≥' : '≤'
  const lanes = Object.entries(r.lanes ?? {}).map(([lane, v]) => (v == null ? `not ${LANE_LABEL[lane as Lane]}` : `${LANE_LABEL[lane as Lane]} ${v}`))
  return `${label} ${op} ${r.value ?? '—'}${lanes.length ? ` (${lanes.join(', ')})` : ''}`
}

function ChallengePicker({ rule, options, onChange }: { rule: ChallengeRule; options?: PlaystyleOptions; onChange: (r: ChallengeRule) => void }) {
  const [query, setQuery] = useState('')
  const list = options?.challenges ?? []
  const add = () => {
    const q = query.trim()
    const id = Number(/#(\d+)$/.exec(q)?.[1] ?? (/^\d+$/.test(q) ? q : NaN))
    const found = list.find((c) => c.id === id) ?? list.find((c) => c.name.toLowerCase() === q.toLowerCase())
    const pick = found ? { id: found.id, name: found.name } : Number.isFinite(id) ? { id, name: `Challenge ${id}` } : null
    if (!pick || rule.challenges.some((c) => c.id === pick.id)) return
    onChange({ ...rule, challenges: [...rule.challenges, pick] })
    setQuery('')
  }
  return (
    <div className="stack">
      <label>Minimum level reached in any of these challenges
        <select value={rule.min_level} onChange={(e) => onChange({ ...rule, min_level: e.target.value })}>
          {(options?.levels ?? []).map((l) => <option key={l} value={l}>{titleCase(l)}</option>)}
        </select>
      </label>
      <div className="tag-list">
        {rule.challenges.length === 0 && <span className="muted small">No challenges yet.</span>}
        {rule.challenges.map((c) => (
          <span key={c.id} className="chip">{c.name} <span className="muted">#{c.id}</span>{' '}
            <button type="button" className="tag-chip-btn" aria-label={`Remove ${c.name}`}
              onClick={() => onChange({ ...rule, challenges: rule.challenges.filter((x) => x.id !== c.id) })}>✕</button>
          </span>
        ))}
      </div>
      <div className="row wrap">
        <input list="challenge-list" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={list.length ? 'Search challenges or type an id' : 'Challenge id'}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }} aria-label="Challenge to add" />
        <button type="button" className="ghost" onClick={add}>Add challenge</button>
      </div>
      <datalist id="challenge-list">
        {list.map((c) => <option key={c.id} value={`${c.name} #${c.id}`}>{c.description}</option>)}
      </datalist>
      {options?.challenges_error && <p className="small muted">{options.challenges_error}</p>}
    </div>
  )
}

type LaneMode = 'default' | 'custom' | 'off'

function MatchRuleEditor({ rule, options, onChange }: { rule: MatchRule; options?: PlaystyleOptions; onChange: (r: MatchRule) => void }) {
  const metric = options?.metrics.find((m) => m.metric === rule.metric)
  const lanes = options?.lanes ?? []
  const mode = (lane: Lane): LaneMode => (!(lane in rule.lanes) ? 'default' : rule.lanes[lane] == null ? 'off' : 'custom')
  const setLane = (lane: Lane, next: LaneMode, value?: number) => {
    const copy = { ...rule.lanes }
    if (next === 'default') delete copy[lane]
    else copy[lane] = next === 'off' ? null : (value ?? rule.value ?? 0)
    onChange({ ...rule, lanes: copy })
  }
  return (
    <div className="stack">
      <div className="grid two">
        <label>Recent-games stat
          <select value={rule.metric} onChange={(e) => onChange({ ...rule, metric: e.target.value })}>
            {(options?.metrics ?? []).map((m) => <option key={m.metric} value={m.metric}>{m.label}</option>)}
          </select>
        </label>
        <label>Earned when the player's average is
          <select value={rule.op} onChange={(e) => onChange({ ...rule, op: e.target.value as MatchRule['op'] })}>
            <option value=">=">at least</option>
            <option value="<=">at most</option>
          </select>
        </label>
        <label>Threshold (all lanes)
          <input type="number" step="any" value={rule.value ?? ''} placeholder="no default"
            onChange={(e) => onChange({ ...rule, value: e.target.value === '' ? null : Number(e.target.value) })} />
        </label>
      </div>
      {metric && <p className="small muted">{metric.how}{metric.unit === 'percent' ? ' · a share: 0.4 means 40%' : ''}</p>}
      <div className="stack">
        <span className="small muted">Per lane</span>
        {lanes.map((lane) => {
          const bench = metric?.benchmarks?.[lane]
          return (
            <div key={lane} className="tag-lane-row">
              <span>{LANE_LABEL[lane]}</span>
              <select value={mode(lane)} onChange={(e) => setLane(lane, e.target.value as LaneMode)} aria-label={`${LANE_LABEL[lane]} threshold`}>
                <option value="default">Use threshold</option>
                <option value="custom">Own threshold</option>
                <option value="off">Never earned</option>
              </select>
              {mode(lane) === 'custom' ? (
                <input type="number" step="any" value={rule.lanes[lane] ?? ''} onChange={(e) => setLane(lane, 'custom', Number(e.target.value))} aria-label={`${LANE_LABEL[lane]} value`} />
              ) : <span className="small muted">{bench ? `typical ${bench[0]}–${bench[1]}` : ''}</span>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function TagForm({ initial, id, options, onDone }: { initial: PlaystyleTagBody; id?: number; options?: PlaystyleOptions; onDone: () => void }) {
  const [tag, setTag] = useState<PlaystyleTagBody>(initial)
  const [keyTouched, setKeyTouched] = useState(Boolean(id))
  const save = useSavePlaystyleTag()
  const set = (patch: Partial<PlaystyleTagBody>) => setTag({ ...tag, ...patch })
  const hooks = options?.hooks ?? []
  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate({ id, body: tag }, { onSuccess: onDone })
  }
  return (
    <form className="card stack" onSubmit={submit}>
      <h2>{id ? `Edit ${initial.label}` : 'New playstyle tag'}</h2>
      <div className="grid two">
        <label>Label<input value={tag.label} maxLength={40} required
          onChange={(e) => set({ label: e.target.value, ...(keyTouched ? {} : { key: slug(e.target.value) }) })} /></label>
        <label>Key <span className="small muted">(stored on players; letters, digits, _)</span>
          <input value={tag.key} maxLength={32} required pattern="[a-z][a-z0-9_]{1,31}" onChange={(e) => { setKeyTouched(true); set({ key: e.target.value }) }} /></label>
        <label>Kind
          <select value={tag.polarity} onChange={(e) => set({ polarity: e.target.value as PlaystyleTagBody['polarity'] })}>
            <option value="positive">▲ Strength</option>
            <option value="negative">▼ Weakness</option>
          </select>
        </label>
        <label>Earned from
          <select value={tag.source} onChange={(e) => { const source = e.target.value as PlaystyleTagBody['source']; set({ source, rule: defaultRule(source, options) }) }}>
            <option value="challenge">Riot challenge levels</option>
            <option value="match">Recent games (imported matches)</option>
          </select>
        </label>
      </div>
      <label>Description<input value={tag.description} maxLength={400} onChange={(e) => set({ description: e.target.value })} /></label>

      <h3>How it is earned</h3>
      {tag.source === 'challenge'
        ? <ChallengePicker rule={tag.rule as ChallengeRule} options={options} onChange={(rule) => set({ rule })} />
        : <MatchRuleEditor rule={tag.rule as MatchRule} options={options} onChange={(rule) => set({ rule })} />}

      <h3>What it does in the simulation</h3>
      {tag.effects.map((effect, i) => {
        const hook = hooks.find((h) => h.hook === effect.hook)
        const [lo, hi] = hook?.range ?? [-0.1, 0.1]
        return (
          <div key={i} className="stack">
            <div className="tag-editor-row">
              <label>Effect
                <select value={effect.hook} onChange={(e) => set({ effects: tag.effects.map((x, j) => (j === i ? { ...x, hook: e.target.value } : x)) })}>
                  {hooks.map((h) => <option key={h.hook} value={h.hook} disabled={h.hook !== effect.hook && tag.effects.some((x) => x.hook === h.hook)}>{h.label}</option>)}
                </select>
              </label>
              <label>Value (%)
                <input type="number" step="0.5" min={lo * 100} max={hi * 100} value={Math.round(effect.value * 1000) / 10}
                  onChange={(e) => set({ effects: tag.effects.map((x, j) => (j === i ? { ...x, value: Number(e.target.value) / 100 } : x)) })} />
              </label>
              <button type="button" className="ghost small danger" disabled={tag.effects.length === 1}
                onClick={() => set({ effects: tag.effects.filter((_, j) => j !== i) })}>Remove</button>
            </div>
            <p className="small muted">{effectText(effect)}. {hook?.help} Allowed {lo * 100}% to {hi * 100}%; all of a player's tags together are capped at ±{(hook?.cap ?? 0) * 100}%.</p>
          </div>
        )
      })}
      {tag.effects.length < 4 && (
        <button type="button" className="ghost" onClick={() => {
          const free = hooks.find((h) => !tag.effects.some((x) => x.hook === h.hook))
          if (free) set({ effects: [...tag.effects, { hook: free.hook, value: tag.polarity === 'positive' ? 0.02 : -0.02 }] })
        }}>Add another effect</button>
      )}

      <div className="grid two">
        <label>Order <span className="small muted">(lower comes first)</span>
          <input type="number" min={0} max={100000} value={tag.sort_order} onChange={(e) => set({ sort_order: Number(e.target.value) })} /></label>
        <label className="row"><input type="checkbox" checked={tag.enabled} onChange={(e) => set({ enabled: e.target.checked })} /> Enabled (imports can earn it and games use it)</label>
      </div>
      <ErrorNotice error={save.error} />
      <div className="row wrap">
        <button className="primary" disabled={save.isPending}>{save.isPending ? 'Saving…' : 'Save tag'}</button>
        <button type="button" className="ghost" onClick={onDone}>Cancel</button>
      </div>
    </form>
  )
}

/** Admin: the playstyle tags Riot imports can earn, how they are earned, and what they do in the simulation. */
export default function PlaystyleTagsPage() {
  const tags = usePlaystyleTags()
  const options = usePlaystyleOptions()
  const del = useDeletePlaystyleTag()
  const [editing, setEditing] = useState<AdminPlaystyleTag | 'new' | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const remove = (t: AdminPlaystyleTag) => {
    const text = t.players
      ? `"${t.label}" is kept on ${t.players} player(s), so it will be disabled instead of deleted. Continue?`
      : `Delete "${t.label}"? This cannot be undone.`
    if (!window.confirm(text)) return
    del.mutate(t.id, { onSuccess: (r) => setNotice(r.deleted ? `Deleted "${t.label}".` : `Disabled "${t.label}" (kept on ${r.players} player(s)).`) })
  }

  if (tags.isLoading) return <Loading />
  return (
    <div className="stack">
      <div className="row between wrap">
        <h1>Playstyle tags</h1>
        <button className="primary" onClick={() => { setEditing('new'); setNotice(null) }} disabled={editing !== null}>New tag</button>
      </div>
      <p className="muted small">
        Players imported from Riot earn these tags: strengths from their challenge levels, weaknesses from the games the import reads.
        A player keeps up to {options.data?.max_tags ?? 5}. Games copy a tag's effects when they start, so edits only change new games.
      </p>
      <ErrorNotice error={tags.error ?? del.error} />
      {notice && <div className="notice">{notice}</div>}
      {editing && (
        <TagForm key={editing === 'new' ? 'new' : editing.id} id={editing === 'new' ? undefined : editing.id}
          initial={editing === 'new' ? blank() : (({ id: _id, players: _p, ...rest }) => rest)(editing)}
          options={options.data} onDone={() => setEditing(null)} />
      )}
      <div className="table-scroll">
        <table>
          <thead><tr><th>Tag</th><th>Earned by</th><th>Effects</th><th title="Players keeping this tag">Players</th><th /></tr></thead>
          <tbody>
            {(tags.data ?? []).map((t) => (
              <tr key={t.id} className={t.enabled ? '' : 'muted'}>
                <td><TagChip tag={t} />{!t.enabled && <span className="badge">disabled</span>}</td>
                <td className="small">{ruleText(t, options.data)}</td>
                <td className="small">{t.effects.map(effectText).join(', ')}</td>
                <td>{t.players}</td>
                <td>
                  <span className="row wrap">
                    <button type="button" className="ghost small" onClick={() => { setEditing(t); setNotice(null) }} disabled={editing !== null}>Edit</button>
                    <button type="button" className="ghost small danger" onClick={() => remove(t)} disabled={del.isPending}>Delete</button>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
