import { useEffect, useRef, type CSSProperties } from 'react'
import type { Lane, TeamInsights, TeamInsightsRequest, TeamNote } from '../api/types'
import { LANES } from '../api/types'
import { useTeamInsights } from '../hooks/useData'
import { LANE_LABEL, TIER_LABEL, titleCase } from '../lib/format'
import { ChampionIcon } from './ChampionArt'
import { ErrorNotice, Loading } from './common'

const STYLE_COLOUR: Record<string, string> = {
  early: '#ff8a5b', scaling: '#c77dff', teamfight: '#7aa2ff', skirmish: '#3ecf8e',
}

/** Notes on the team being edited, in a side panel. Reloads as the editor changes while it is open. */
export default function TeamNotes({ open, onClose, request, onUseStyles, onUseFocus }: {
  open: boolean
  onClose: () => void
  request: TeamInsightsRequest
  onUseStyles: (primary: string, secondary: string) => void
  onUseFocus: (first: Lane, second: Lane | null) => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const insights = useTeamInsights(request, open)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  const data = insights.data
  return (
    <dialog ref={ref} className="notes-drawer" aria-labelledby="team-notes-title" onClose={onClose}
            onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="notes-body">
        <header className="notes-head">
          <div>
            <h2 id="team-notes-title">Team notes</h2>
            <p className="small muted">From the simulation's own formulas, without the dice. Updates as you edit the team.</p>
          </div>
          <button type="button" className="ghost" onClick={onClose} aria-label="Close team notes">✕</button>
        </header>
        {insights.isLoading && <Loading label="Reading your roster…" />}
        <ErrorNotice error={insights.error} />
        {data && data.filled === 0 && <p className="muted">Add players to the roster to see notes on the team.</p>}
        {data && data.filled > 0 && (
          <div className={`stack ${insights.isFetching ? 'notes-stale' : ''}`} aria-busy={insights.isFetching}>
            <NotesSection data={data} />
            <StylesSection data={data} request={request} onUse={onUseStyles} />
            <FocusSection data={data} request={request} onUse={onUseFocus} />
            <CompsSection data={data} />
          </div>
        )}
      </div>
    </dialog>
  )
}

function NoteList({ notes, kind }: { notes: TeamNote[]; kind: 'strength' | 'weakness' }) {
  if (!notes.length) return <p className="small muted">{kind === 'strength' ? 'No standout strengths yet.' : 'No clear weaknesses.'}</p>
  return (
    <ul className={`note-list ${kind}`}>
      {notes.map((n) => (
        <li key={n.title}><strong>{n.title}</strong><span className="small">{n.detail}</span></li>
      ))}
    </ul>
  )
}

function NotesSection({ data }: { data: TeamInsights }) {
  return (
    <section className="notes-grid">
      <div className="notes-card strength-card">
        <h3>▲ Strengths</h3>
        <NoteList notes={data.strengths} kind="strength" />
      </div>
      <div className="notes-card weakness-card">
        <h3>▼ Weaknesses</h3>
        <NoteList notes={data.weaknesses} kind="weakness" />
      </div>
    </section>
  )
}

function StylesSection({ data, request, onUse }: {
  data: TeamInsights; request: TeamInsightsRequest; onUse: (primary: string, secondary: string) => void
}) {
  const [primary, secondary] = data.suggested_styles
  const already = request.style1 === primary && request.style2 === secondary
  return (
    <section className="notes-card">
      <div className="row between wrap">
        <h3>Suggested playstyle</h3>
        <button type="button" className="small" disabled={already} onClick={() => onUse(primary, secondary)}>
          {already ? 'In use' : `Use ${titleCase(primary)} + ${titleCase(secondary)}`}
        </button>
      </div>
      <ul className="style-list">
        {data.styles.map((s) => {
          const rank = s.style === primary ? 'Primary' : s.style === secondary ? 'Secondary' : null
          return (
            <li key={s.style} style={{ '--accent': STYLE_COLOUR[s.style] } as CSSProperties} className={rank ? 'suggested' : ''}>
              <div className="row between">
                <span><strong>{s.label}</strong>{rank && <span className="style-rank">{rank}</span>}</span>
                <span className="style-score">{s.score}</span>
              </div>
              <div className="style-bar"><span style={{ width: `${s.score}%` }} /></div>
              {(s.pros.length > 0 || s.cons.length > 0) && (
                <p className="small">
                  {s.pros.map((p) => <span key={p} className="pro">+ {p}</span>)}
                  {s.cons.map((c) => <span key={c} className="con">− {c}</span>)}
                </p>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function FocusSection({ data, request, onUse }: {
  data: TeamInsights; request: TeamInsightsRequest; onUse: (first: Lane, second: Lane | null) => void
}) {
  const [first, second = null] = data.suggested_focus
  const already = request.focus1 === first && (request.focus2 ?? null) === second
  const top = Math.max(...data.focus.map((f) => f.gain), 0.0001)
  return (
    <section className="notes-card">
      <div className="row between wrap">
        <h3>Lanes to focus</h3>
        <button type="button" className="small" disabled={already} onClick={() => onUse(first, second)}>
          {already ? 'In use' : `Use ${LANE_LABEL[first]}${second ? ` + ${LANE_LABEL[second]}` : ''}`}
        </button>
      </div>
      <p className="small muted">How much each lane's focus adds to the team's lane strength, weighted by fight damage.</p>
      <ul className="focus-list">
        {data.focus.map((f) => {
          const pick = f.lane === first ? 'Focus 1' : f.lane === second ? 'Focus 2' : null
          return (
            <li key={f.lane} className={pick ? 'suggested' : ''}>
              <span className="focus-lane">{LANE_LABEL[f.lane]}</span>
              <span className="focus-bar"><span style={{ width: `${(f.gain / top) * 100}%` }} /></span>
              <span className="focus-gain">+{(f.gain * 100).toFixed(1)}%</span>
              <span className="small muted focus-why">{pick && <strong className="focus-pick">{pick} · </strong>}{f.reason}</span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function CompsSection({ data }: { data: TeamInsights }) {
  if (!data.comps.length) return null
  return (
    <section className="stack">
      <h3>Ideal comps from your pools</h3>
      {data.comps.map((comp, i) => (
        <div key={comp.style} className="notes-card comp-card" style={{ '--accent': STYLE_COLOUR[comp.style] } as CSSProperties}>
          <div className="row between wrap">
            <strong className="comp-label">{comp.label}</strong>
            {i === 0 && <span className="style-rank">Best fit for this team</span>}
          </div>
          <ul className="comp-picks">
            {LANES.filter((l) => comp.picks[l]).map((lane) => {
              const p = comp.picks[lane]!
              return (
                <li key={lane} title={`${TIER_LABEL[p.comfort] ?? titleCase(p.comfort)} · ${Math.round(p.fit * 100)}% of this player's best lane value`}>
                  <ChampionIcon champion={{ name: p.name }} size={44} />
                  <span className="comp-name">{p.name}</span>
                  <span className="small muted">{LANE_LABEL[lane]}</span>
                </li>
              )
            })}
          </ul>
          <div className="damage-split" title={`${Math.round(comp.damage.physical * 100)}% physical / ${Math.round(comp.damage.magic * 100)}% magic`}>
            <span className="phys" style={{ width: `${comp.damage.physical * 100}%` }} />
            <span className="magic" style={{ width: `${comp.damage.magic * 100}%` }} />
          </div>
          <ul className="small comp-notes">{comp.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </div>
      ))}
    </section>
  )
}
