import { useState, type CSSProperties } from 'react'
import type { Lane, Player } from '../api/types'
import { LANES } from '../api/types'
import { LANE_LABEL, averageRank, rankLabel, teamRating } from '../lib/format'
import { MAX_STAT_TOTAL, rankCrestUrl, rankEmblemUrl, ratingBand, tierColour } from '../lib/ranked'

/** Ranked art that hides itself if the image can't load. */
function RankImage({ src, className }: { src: string; className: string }) {
  const [failed, setFailed] = useState<string | null>(null)
  if (failed === src) return null
  return <img className={className} src={src} alt="" loading="lazy" onError={() => setFailed(src)} />
}

/** Team rating and average rank for the roster being edited, with each lane's player underneath. */
export default function RosterSummary({ roster }: { roster: Partial<Record<Lane, Player>> }) {
  const players = LANES.flatMap((l) => roster[l] ?? [])
  const { rating, filled } = teamRating(players)
  const avg = averageRank(players)
  const band = filled ? ratingBand(rating / filled) : null
  const max = LANES.length * MAX_STAT_TOTAL
  const rankColour = tierColour(avg.rank?.tier)

  return (
    <div className="roster-summary" aria-live="polite">
      <div className="summary-tiles">
        <div className="summary-tile" style={{ '--accent': band?.colour ?? 'var(--line)' } as CSSProperties}
             title="Sum of the rostered players' stat totals; the band comes from the average per player">
          <div className="summary-label">Team rating</div>
          <div className="summary-value">
            <span className="summary-number">{rating}</span><span className="muted"> / {max}</span>
            {band && <span className="summary-band">{band.label}</span>}
          </div>
          <div className="summary-bar"><span style={{ width: `${(rating / max) * 100}%` }} /></div>
          <div className="small muted">{filled}/{LANES.length} players{filled ? ` · ${(rating / filled).toFixed(1)} per player` : ''}</div>
        </div>

        <div className="summary-tile rank-tile" style={{ '--accent': rankColour } as CSSProperties}
             title="Average Riot rank of the rostered players that have one">
          <div className="rank-emblem">
            {avg.rank?.tier
              ? <RankImage key={avg.rank.tier} className="rank-emblem-img" src={rankEmblemUrl(avg.rank.tier)} />
              : <RankImage className="rank-emblem-crest" src={rankCrestUrl(null)} />}
          </div>
          <div>
            <div className="summary-label">Average rank</div>
            <div className="summary-number rank-name">{rankLabel(avg.rank)}</div>
            <div className="small muted">{avg.ranked} of {avg.total} ranked</div>
          </div>
        </div>
      </div>

      <ul className="summary-lanes">
        {LANES.map((lane) => {
          const p = roster[lane]
          const tier = p?.riot?.rank?.tier
          return (
            <li key={lane} className={p ? '' : 'empty'}>
              <span className="summary-lane muted">{LANE_LABEL[lane]}</span>
              {p ? <>
                <span className="summary-player">
                  <RankImage className="rank-crest" src={rankCrestUrl(tier)} />
                  <span className="truncate">{p.name}</span>
                </span>
                <span className="summary-rank" style={{ color: tierColour(tier) }}>{rankLabel(p.riot?.rank)}</span>
                <span className="summary-stat" style={{ '--accent': ratingBand(p.stat_total).colour } as CSSProperties}
                      title={`${ratingBand(p.stat_total).label} · stat total`}>{p.stat_total}</span>
              </> : <span className="muted">Empty</span>}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
