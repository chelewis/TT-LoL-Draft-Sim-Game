import { useId } from 'react'
import type { MatchEvent, Side } from '../api/types'
import { formatGold, type GoldPoint } from '../lib/scoreboard'
import { describeEvent } from '../lib/summary'

const W = 640
const PLOT_H = 140
const PAD = { left: 44, right: 12, top: 8 }
const AXIS_H = 20
/** The x axis spans at least this much, so a live graph does not stretch its first minutes across the whole width. */
const MIN_SPAN_SECONDS = 15 * 60
const MIN_RANGE = 2000

// objective icons: Blue's sit in a strip above the plot and Red's in one below, matching the side each lead is drawn on
const ROW = 18                    // height of one row of icons
const ROWS = 2                    // icons taken close together stack into a second row, then shift right
const ICON_GAP = 17               // the closest two icons in a row may sit, centre to centre

type ObjectiveKind = 'DRAGON' | 'ELDER_DRAGON' | 'BARON' | 'TOWER' | 'INHIBITOR' | 'NEXUS_TOWER' | 'NEXUS'

/** Glyphs on a 24-unit grid, drawn white on a disc in the taking team's colour. */
const GLYPHS: Record<ObjectiveKind, string> = {
  DRAGON: 'M12 2c1 4 6 6 6 12a6 6 0 0 1-12 0c0-3 2-5 3-7 0 2 1 3 2 3 0-3-1-5 1-8z',
  ELDER_DRAGON: 'M12 2c1 4 6 6 6 12a6 6 0 0 1-12 0c0-3 2-5 3-7 0 2 1 3 2 3 0-3-1-5 1-8z',
  BARON: 'M4 3l4 6h8l4-6v9a8 8 0 0 1-16 0zM9 13a1.5 1.5 0 1 0 0 .1zM15 13a1.5 1.5 0 1 0 0 .1z',
  TOWER: 'M7 3h2v2h2V3h2v2h2V3h2v5l-2 2v8h2v3H7v-3h2v-8L7 8z',
  NEXUS_TOWER: 'M7 3h2v2h2V3h2v2h2V3h2v5l-2 2v8h2v3H7v-3h2v-8L7 8z',
  INHIBITOR: 'M12 2l8 10-8 10-8-10z',
  NEXUS: 'M12 1l7 8-7 14-7-14z',
}

const LEGEND: [ObjectiveKind, string][] = [
  ['DRAGON', 'Dragon'], ['ELDER_DRAGON', 'Elder Dragon'], ['BARON', 'Baron'], ['TOWER', 'Tower'], ['INHIBITOR', 'Inhibitor'], ['NEXUS', 'Nexus'],
]

const isObjective = (type: string): type is ObjectiveKind => type in GLYPHS

function ObjectiveIcon({ kind, x, y, side, title }: { kind: ObjectiveKind; x: number; y: number; side: Side | null; title?: string }) {
  return (
    <g className={`gold-graph-objective ${side ? side.toLowerCase() : 'neutral'} ${kind.toLowerCase().replace(/_/g, '-')}`}>
      {title && <title>{title}</title>}
      <circle cx={x} cy={y} r={8} />
      <path d={GLYPHS[kind]} transform={`translate(${x - 6} ${y - 6}) scale(0.5)`} />
    </g>
  )
}

interface PlacedObjective { event: MatchEvent; kind: ObjectiveKind; side: Side; x: number; row: number }

/** Each side's objectives along its strip: by time, stacking into a second row and then shifting right when crowded. */
function placeObjectives(events: MatchEvent[], x: (seconds: number) => number): PlacedObjective[] {
  const placed: PlacedObjective[] = []
  for (const side of ['BLUE', 'RED'] as Side[]) {
    const lastX: number[] = []
    const mine = events
      .filter((e) => isObjective(e.type) && e.payload.team === side)
      .sort((a, b) => a.minute - b.minute || a.sequence - b.sequence)
    for (const event of mine) {
      let at = x(event.minute * 60)
      let row = lastX.findIndex((last) => at - last >= ICON_GAP)
      if (row < 0 && lastX.length < ROWS) row = lastX.length
      if (row < 0) {
        row = lastX.indexOf(Math.min(...lastX))
        at = lastX[row] + ICON_GAP
      }
      lastX[row] = at
      placed.push({ event, kind: event.type as ObjectiveKind, side, x: at, row })
    }
  }
  return placed
}

/**
 * The gold lead over time: above the line Blue is ahead, below it Red. With `objectives` (any events; the
 * objective ones are picked out) each dragon, Baron and structure taken is marked at its minute.
 */
export default function GoldGraph({ points, names, objectives }: {
  points: GoldPoint[]; names: Record<Side, string>; objectives?: MatchEvent[]
}) {
  const id = `gold${useId().replace(/[^a-zA-Z0-9]/g, '')}`   // React ids contain colons, which break url(#…)
  if (points.length === 0) return null
  const strip = objectives ? ROWS * ROW : 0
  const top = PAD.top + strip
  const bottom = top + PLOT_H
  const H = bottom + strip + AXIS_H
  const span = Math.max(points[points.length - 1].seconds, MIN_SPAN_SECONDS)
  const range = Math.ceil(Math.max(MIN_RANGE, ...points.map((p) => Math.abs(p.diff))) / 1000) * 1000
  const innerW = W - PAD.left - PAD.right
  const x = (s: number) => PAD.left + (Math.min(s, span) / span) * innerW
  const y = (d: number) => top + ((range - d) / (2 * range)) * PLOT_H
  const zero = y(0)

  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(p.seconds).toFixed(1)},${y(p.diff).toFixed(1)}`).join('')
  const area = `${line}L${x(points[points.length - 1].seconds).toFixed(1)},${zero}L${x(points[0].seconds).toFixed(1)},${zero}Z`
  const ticks: number[] = []
  for (let m = 0; m * 60 <= span; m += 5) ticks.push(m)
  const placed = objectives ? placeObjectives(objectives, x) : []

  const last = points[points.length - 1].diff
  const leader = last > 0 ? names.BLUE : last < 0 ? names.RED : null
  const label = leader ? `Gold lead over time: ${leader} ahead by ${Math.abs(last).toLocaleString()}` : 'Gold lead over time: even'

  return (
    <figure className="gold-graph-figure">
      <svg className="gold-graph" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
        <defs>
          <clipPath id={`${id}-above`}><rect x={0} y={0} width={W} height={zero} /></clipPath>
          <clipPath id={`${id}-below`}><rect x={0} y={zero} width={W} height={H - zero} /></clipPath>
        </defs>
        {ticks.map((m) => (
          <g key={m}>
            <line className="gold-graph-grid" x1={x(m * 60)} x2={x(m * 60)} y1={top} y2={bottom} />
            <text className="gold-graph-axis" x={x(m * 60)} y={H - 6} textAnchor="middle">{m}:00</text>
          </g>
        ))}
        <line className="gold-graph-zero" x1={PAD.left} x2={W - PAD.right} y1={zero} y2={zero} />
        <text className="gold-graph-axis" x={PAD.left - 6} y={top + 4} textAnchor="end">+{formatGold(range)}</text>
        <text className="gold-graph-axis" x={PAD.left - 6} y={zero + 4} textAnchor="end">0</text>
        <text className="gold-graph-axis" x={PAD.left - 6} y={bottom} textAnchor="end">+{formatGold(range)}</text>
        <text className="gold-graph-team blue" x={PAD.left + 6} y={top + 14}>{names.BLUE}</text>
        <text className="gold-graph-team red" x={PAD.left + 6} y={bottom - 6}>{names.RED}</text>
        <path className="gold-graph-area blue" d={area} clipPath={`url(#${id}-above)`} />
        <path className="gold-graph-area red" d={area} clipPath={`url(#${id}-below)`} />
        <path className="gold-graph-line blue" d={line} clipPath={`url(#${id}-above)`} />
        <path className="gold-graph-line red" d={line} clipPath={`url(#${id}-below)`} />
        {placed.map((o) => (
          <ObjectiveIcon key={o.event.sequence} kind={o.kind} side={o.side} x={o.x}
            y={o.side === 'BLUE' ? top - ROW / 2 - o.row * ROW : bottom + ROW / 2 + o.row * ROW}
            title={describeEvent(o.event, names) ?? undefined} />
        ))}
      </svg>
      {objectives && (
        <figcaption>
          <ul className="gold-graph-legend small muted">
            {LEGEND.map(([kind, text]) => (
              <li key={kind}>
                <svg viewBox="0 0 18 18" width={16} height={16} aria-hidden="true"><ObjectiveIcon kind={kind} x={9} y={9} side={null} /></svg>
                {text}
              </li>
            ))}
            <li>{names.BLUE}'s above the graph, {names.RED}'s below</li>
          </ul>
        </figcaption>
      )}
    </figure>
  )
}
