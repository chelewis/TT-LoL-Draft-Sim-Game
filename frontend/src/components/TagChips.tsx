import type { PlaystyleTag } from '../api/types'
import { effectText, evidenceText, sortTags } from '../lib/playstyle'
import Tooltip from './Tooltip'

function TagTip({ tag }: { tag: PlaystyleTag }) {
  const why = evidenceText(tag.evidence)
  return (
    <div className="tip-content">
      <strong>{tag.label}</strong> <span className="muted">({tag.polarity === 'positive' ? 'strength' : 'weakness'})</span>
      {tag.description && <p>{tag.description}</p>}
      <ul>{tag.effects.map((e) => <li key={e.hook}>{effectText(e)}</li>)}</ul>
      {why && <p className="muted">Earned by: {why}</p>}
    </div>
  )
}

/** One playstyle tag: green for strengths, red for weaknesses, with its effects on hover. */
export function TagChip({ tag, onRemove, onAdd, addDisabled }: {
  tag: PlaystyleTag; onRemove?: () => void; onAdd?: () => void; addDisabled?: boolean
}) {
  return (
    <span className={`tag-chip ${tag.polarity}`}>
      <Tooltip label={`${tag.label}: ${tag.effects.map(effectText).join(', ')}`} content={<TagTip tag={tag} />}>
        <span>{tag.polarity === 'positive' ? '▲' : '▼'} {tag.label}</span>
      </Tooltip>
      {onRemove && <button type="button" className="tag-chip-btn" onClick={onRemove} aria-label={`Remove ${tag.label}`}>✕</button>}
      {onAdd && <button type="button" className="tag-chip-btn" onClick={onAdd} disabled={addDisabled} aria-label={`Add ${tag.label}`}>＋</button>}
    </span>
  )
}

/** A player's playstyle tags, strengths first. Renders nothing when there are none. */
export default function TagChips({ tags }: { tags?: PlaystyleTag[] | null }) {
  if (!tags?.length) return null
  return <span className="tag-chips">{sortTags(tags).map((t) => <TagChip key={t.key} tag={t} />)}</span>
}
