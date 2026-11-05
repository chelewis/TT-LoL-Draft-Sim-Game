import { useEffect, useRef } from 'react'
import type { ChampionPair, PairChampion, PairNote } from '../../api/types'
import { ChampionIcon, LaneIcon } from '../../components/ChampionArt'
import { ErrorNotice, Loading } from '../../components/common'
import { useChampionPair } from '../../hooks/useData'
import { championFacts, rateSource } from '../../lib/championPair'
import { LANE_LABEL } from '../../lib/format'

const percent = (value: number) => `${value.toFixed(1)}%`

/** Side drawer for two champions chosen in the Champions table: how they do on the same team and against each
 * other, with notes on what the simulation does with the pair. */
export default function ChampionPairDrawer({ a, b, open, onClose }: {
  a: number | null
  b: number | null
  open: boolean
  onClose: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const pair = useChampionPair(open ? a : null, open ? b : null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  const data = pair.data
  return (
    <dialog ref={ref} className="notes-drawer" aria-labelledby="pair-drawer-title" onClose={onClose}
            onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="notes-body">
        <header className="notes-head">
          <div>
            <h2 id="pair-drawer-title">Champion pair</h2>
            <p className="small muted">
              Win rates from the tables the simulation uses, with notes from its own formulas: synergy, counters, the
              lane matchup wheel, range, scaling and damage mix.
            </p>
          </div>
          <button type="button" className="ghost" onClick={onClose} aria-label="Close champion pair">✕</button>
        </header>
        <ErrorNotice error={pair.error} />
        {pair.isLoading && <Loading label="Reading the pair…" />}
        {data && (
          <div className={`stack ${pair.isPlaceholderData ? 'notes-stale' : ''}`} aria-busy={pair.isFetching}>
            <div className="pair-header">
              <ChampionCard champion={data.champions[0]} />
              <span className="pair-and muted" aria-hidden="true">&amp;</span>
              <ChampionCard champion={data.champions[1]} />
            </div>
            <SameTeamCard pair={data} />
            <AgainstCard pair={data} />
          </div>
        )}
      </div>
    </dialog>
  )
}

function ChampionCard({ champion: c }: { champion: PairChampion }) {
  return (
    <div className="card pair-champion">
      <ChampionIcon champion={c} size={48} />
      <div className="stack pair-champion-body">
        <div className="row wrap">
          <h3>{c.name}</h3>
          <span className="muted small">{c.class}</span>
          {c.roles.map((r) => <span key={r} className="meta-role muted" title={LANE_LABEL[r]}><LaneIcon lane={r} size={16} /></span>)}
        </div>
        <div className="row wrap pair-facts">
          {championFacts(c).map((f) => <span key={f} className="chip small">{f}</span>)}
          <span className="chip small" title={`Matchup wheel: ${c.strength} is beaten by ${c.weakness}`}>
            {c.strength} · weak to {c.weakness}
          </span>
        </div>
      </div>
    </div>
  )
}

function SameTeamCard({ pair }: { pair: ChampionPair }) {
  const rate = pair.same_team
  return (
    <section className="card stack pair-card">
      <h3>Same team</h3>
      <div>
        <p className="pair-rate">{rate.win_rate === null ? '—' : percent(rate.win_rate)}</p>
        <p className="small muted">{rateSource(rate)}</p>
      </div>
      <NoteList notes={rate.notes} pair={pair} />
    </section>
  )
}

function AgainstCard({ pair }: { pair: ChampionPair }) {
  const rate = pair.against
  const [a, b] = pair.champions
  const lane = rate.lane === null
    ? 'Never share a lane: they only meet in fights'
    : rate.head_to_head ? `Face each other in ${LANE_LABEL[rate.lane]}` : 'Face each other across the bot lane'
  return (
    <section className="card stack pair-card">
      <h3>Against each other</h3>
      {rate.win_rate === null ? (
        <p className="pair-rate">—</p>
      ) : (
        <div className="pair-split" role="img" aria-label={`${a.name} ${percent(rate.win_rate)}, ${b.name} ${percent(100 - rate.win_rate)}`}>
          <div className="row between small">
            <span className="row pair-split-side"><ChampionIcon champion={a} size={22} /><strong>{percent(rate.win_rate)}</strong></span>
            <span className="row pair-split-side"><strong>{percent(100 - rate.win_rate)}</strong><ChampionIcon champion={b} size={22} /></span>
          </div>
          <div className="pair-split-bar"><span style={{ width: `${rate.win_rate}%` }} /></div>
        </div>
      )}
      <p className="small muted">{rateSource(rate)} · {lane}</p>
      <NoteList notes={rate.notes} pair={pair} />
    </section>
  )
}

function NoteList({ notes, pair }: { notes: PairNote[]; pair: ChampionPair }) {
  const [a, b] = pair.champions
  return (
    <ul className="note-list pair-notes">
      {notes.map((n) => {
        const favours = n.kind === 'a' ? a : n.kind === 'b' ? b : null
        return (
          <li key={n.title} className={`pair-note-${n.kind}`}>
            <strong className="row pair-note-title">
              {favours && <ChampionIcon champion={favours} size={18} />}
              {n.title}
            </strong>
            <span className="small">{n.detail}</span>
          </li>
        )
      })}
    </ul>
  )
}
