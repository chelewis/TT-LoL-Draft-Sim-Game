import type { Champion, GameState, Lane, MatchupLane, MatchupTeam, Side } from '../../api/types'
import { LANES } from '../../api/types'
import { ChampionIcon, LaneIcon } from '../../components/ChampionArt'
import { ErrorNotice, Loading } from '../../components/common'
import { LANE_LABEL, scalingLabel } from '../../lib/format'
import { formatPoints, formatRate, physicalShare, rateTone, wheelEdge } from '../../lib/matchupPanel'
import { useMatchupPreview } from '../../hooks/useMatchupPreview'
import { CounterChip, FactorList, GradeChip, RoleTag } from './LaneInsights'

const SIDES: Side[] = ['BLUE', 'RED']
const sideName = (s: Side) => (s === 'BLUE' ? 'Blue' : 'Red')

const TOTALS: { key: keyof MatchupTeam['totals']; label: string }[] = [
  { key: 'damage', label: 'Damage' },
  { key: 'sturdiness', label: 'Sturdiness' },
  { key: 'cc', label: 'Crowd control' },
  { key: 'mobility', label: 'Mobility' },
  { key: 'utility', label: 'Utility' },
  { key: 'range', label: 'Range' },
  { key: 'waveclear', label: 'Waveclear' },
]

/** Finalization's "Show Matchup Data" view, in place of the champion grid: lane matchups, damage mix and totals. */
export default function MatchupPanel({ game, byId }: { game: GameState; byId: Map<number, Champion> }) {
  const query = useMatchupPreview(game)
  if (query.isLoading) return <Loading label="Loading matchup data…" />
  if (query.error) return <ErrorNotice error={query.error} />
  const data = query.data!
  const baseline = data.settings.baseline

  return (
    <div className="mp" aria-live="polite">
      <section className="mp-section">
        <h3 className="mp-heading">Lane matchups</h3>
        <div className="mp-lanes">
          {LANES.map((lane) => {
            const l = data.lanes[lane]
            return <LaneRow key={lane} lane={lane} data={l} blue={byId.get(l.blue ?? -1)} red={byId.get(l.red ?? -1)} baseline={baseline} />
          })}
        </div>
        <p className="mp-note">
          Grades (S best … F worst) rank each player's expected lane score on their champion against every champion they could play there,
          counting comfort, stats, role, the matchup wheel, win rates, range and scaling. ▲/▼ is the matchup wheel (Offence beats Defence beats Control beats Offence).
        </p>
        {!data.counter_data && (
          <p className="mp-note">No lane win rates yet: the against-team win rate matrix is empty. An admin can fill it in under Admin → Champions → Winrates → Against team.</p>
        )}
        {!data.settings.win_rates_enabled && <p className="mp-note">Win rates are switched off in the simulation settings, so these do not affect this match.</p>}
      </section>

      <section className="mp-section">
        <h3 className="mp-heading">Damage composition</h3>
        <div className="mp-damage-pair">
          {SIDES.map((s) => <DamageMix key={s} side={s} team={data.teams[s]} />)}
        </div>
        <p className="mp-note">
          {data.settings.damage_balance_enabled
            ? `Over ${Math.round(data.settings.damage_threshold * 100)}% of one damage type lets the enemy itemize against it: up to −${Math.round(data.settings.max_damage_penalty * 100)}% fight damage for a single-type comp.`
            : 'The damage balance penalty is switched off in the simulation settings.'}
        </p>
      </section>

      <section className="mp-section">
        <h3 className="mp-heading">Team totals</h3>
        <table className="mp-totals">
          <thead>
            <tr><th className="blue">{sideName('BLUE')}</th><th /><th className="red">{sideName('RED')}</th></tr>
          </thead>
          <tbody>
            {TOTALS.map(({ key, label }) => (
              <TotalRow key={key} label={label} blue={data.teams.BLUE.totals[key]} red={data.teams.RED.totals[key]} strong={key === 'damage'} />
            ))}
            <tr>
              <td className={`mp-num tone-${toneOfPoints(data.teams.BLUE.ally_synergy)}`}>{formatPoints(data.teams.BLUE.ally_synergy)}</td>
              <th scope="row" title="Average same-team win rate of the whole comp, against the baseline">Synergy</th>
              <td className={`mp-num tone-${toneOfPoints(data.teams.RED.ally_synergy)}`}>{formatPoints(data.teams.RED.ally_synergy)}</td>
            </tr>
            <tr>
              <td className={`mp-num tone-${rateTone(data.teams.BLUE.duo_win_rate, baseline)}`}>{formatRate(data.teams.BLUE.duo_win_rate)}</td>
              <th scope="row" title="Same-team win rate of the bot laner and support">Bot lane duo</th>
              <td className={`mp-num tone-${rateTone(data.teams.RED.duo_win_rate, baseline)}`}>{formatRate(data.teams.RED.duo_win_rate)}</td>
            </tr>
          </tbody>
        </table>
        {data.notes.map((note) => <p key={note} className="mp-note">{note}</p>)}
      </section>
    </div>
  )
}

const toneOfPoints = (points: number | null) => rateTone(points === null ? null : 50 + points)

function LaneRow({ lane, data, blue, red, baseline }: { lane: Lane; data: MatchupLane; blue?: Champion; red?: Champion; baseline: number }) {
  const rate = data.blue_win_rate
  const blueShare = rate ?? 50
  const bot = lane === 'BOT' || lane === 'SUPPORT'
  const edge = wheelEdge(data.wheel, 'BLUE')
  return (
    <div className="mp-lane-wrap">
      <div className="mp-lane">
        <LaneSide side="BLUE" champion={blue} data={data} baseline={baseline} bot={bot} />
        <span className="mp-lane-mid">
          <span className="mp-lane-label"><LaneIcon lane={lane} size={14} /> {LANE_LABEL[lane]}</span>
          <span className={`mp-rate-bar ${rate === null ? 'none' : ''}`} role="img" aria-label={rate === null ? 'No win rate data' : `Blue ${formatRate(rate)}, Red ${formatRate(100 - rate)}`}>
            <span className="mp-rate-fill" style={{ width: `${blueShare}%` }} />
          </span>
          <span className="mp-rate-nums">
            <span className={`tone-${rateTone(rate, baseline)}`}>{formatRate(rate)}</span>
            <span className={`tone-${rateTone(rate === null ? null : 100 - rate, baseline)}`}>{formatRate(rate === null ? null : 100 - rate)}</span>
          </span>
          {data.wheel && (
            <span className={`mp-wheel ${edge}`} title="The matchup wheel: Offence beats Defence, Defence beats Control, Control beats Offence">
              <span className="blue">{data.wheel.blue.strength}</span>
              <span className="mp-wheel-arrow">{data.wheel.winner === 'BLUE' ? '▶' : data.wheel.winner === 'RED' ? '◀' : '='}</span>
              <span className="red">{data.wheel.red.strength}</span>
              {data.wheel.kind && <span className="mp-wheel-kind">{data.wheel.kind === 'STRONG' ? 'strong' : 'slight'}</span>}
            </span>
          )}
        </span>
        <LaneSide side="RED" champion={red} data={data} baseline={baseline} bot={bot} />
      </div>
      {(data.players.BLUE || data.players.RED) && (
        <details className="mp-lane-details">
          <summary>Why these grades</summary>
          <div className="mp-factor-pair">
            {data.players.BLUE ? <FactorList analysis={data.players.BLUE} /> : <span />}
            {data.players.RED ? <FactorList analysis={data.players.RED} /> : <span />}
          </div>
        </details>
      )}
    </div>
  )
}

function LaneSide({ side, champion, data, baseline, bot }: { side: Side; champion?: Champion; data: MatchupLane; baseline: number; bot: boolean }) {
  const analysis = data.players[side]
  const cls = side.toLowerCase()
  return (
    <span className={`mp-champ ${cls}`}>
      {side === 'BLUE' && <ChampionIcon champion={champion} size={34} />}
      <span className="mp-champ-text">
        <span className="mp-champ-name">{champion?.name ?? '—'}</span>
        {analysis && (
          <span className="mp-champ-insights">
            <GradeChip analysis={analysis} />
            <CounterChip wheel={data.wheel} side={side} rate={analysis.counter_rate} baseline={baseline} botLane={bot} />
            <RoleTag analysis={analysis} />
          </span>
        )}
      </span>
      {side === 'RED' && <ChampionIcon champion={champion} size={34} />}
    </span>
  )
}

function DamageMix({ side, team }: { side: Side; team: MatchupTeam }) {
  const phys = physicalShare(team.damage_profile)
  return (
    <div className={`mp-damage ${side.toLowerCase()}`}>
      <div className="mp-damage-head">
        <span className={side.toLowerCase()}>{sideName(side)}</span>
        <span className={team.damage_penalty > 0 ? 'tone-bad' : 'tone-good'}>
          {team.damage_penalty > 0 ? `Itemized against: −${Math.round(team.damage_penalty * 100)}% fight damage` : 'Balanced'}
        </span>
      </div>
      <div className="mp-damage-bar" role="img" aria-label={`${Math.round(phys * 100)}% physical, ${Math.round((1 - phys) * 100)}% magic`}>
        <span className="mp-phys" style={{ width: `${phys * 100}%` }} />
        <span className="mp-magic" style={{ width: `${(1 - phys) * 100}%` }} />
      </div>
      <div className="mp-damage-nums">
        <span>Physical {team.damage_profile.physical} ({Math.round(phys * 100)}%)</span>
        <span>Magic {team.damage_profile.magic} ({Math.round((1 - phys) * 100)}%)</span>
      </div>
      <div className="mp-damage-nums">
        <span>Scaling {team.scaling.toFixed(1)}: {scalingLabel(team.scaling)}</span>
      </div>
    </div>
  )
}

function TotalRow({ label, blue, red, strong }: { label: string; blue: number; red: number; strong?: boolean }) {
  const max = Math.max(blue, red, 1)
  return (
    <tr className={strong ? 'mp-strong' : undefined}>
      <td className={`mp-num ${blue > red ? 'lead' : ''}`}>
        <span className="mp-total-bar blue" style={{ width: `${(blue / max) * 100}%` }} />
        <span className="mp-total-val">{blue}</span>
      </td>
      <th scope="row">{label}</th>
      <td className={`mp-num ${red > blue ? 'lead' : ''}`}>
        <span className="mp-total-bar red" style={{ width: `${(red / max) * 100}%` }} />
        <span className="mp-total-val">{red}</span>
      </td>
    </tr>
  )
}
