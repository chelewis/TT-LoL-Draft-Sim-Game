import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import type { Champion, GameState, Lane, MatchupPreview, MatchupTeam, Side } from '../../api/types'
import { LANES } from '../../api/types'
import { ChampionIcon, LaneIcon } from '../../components/ChampionArt'
import { ErrorNotice, Loading } from '../../components/common'
import { LANE_LABEL, scalingLabel } from '../../lib/format'
import { formatPoints, formatRate, physicalShare, rateTone } from '../../lib/matchupPanel'

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
  const query = useQuery({
    // my own swaps change the key; the opponent's arrive as LINEUP_UPDATED, which GamePage turns into a refetch
    queryKey: ['matchups', game.game_id, game.lineup],
    queryFn: () => api<MatchupPreview>(`/games/${game.game_id}/matchups`),
    placeholderData: keepPreviousData,
  })
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
            return <LaneRow key={lane} lane={lane} blue={byId.get(l.blue ?? -1)} red={byId.get(l.red ?? -1)} rate={l.blue_win_rate} baseline={baseline} />
          })}
        </div>
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

function LaneRow({ lane, blue, red, rate, baseline }: { lane: Lane; blue?: Champion; red?: Champion; rate: number | null; baseline: number }) {
  const blueShare = rate ?? 50
  return (
    <div className="mp-lane">
      <span className="mp-champ blue">
        <ChampionIcon champion={blue} size={34} />
        <span>{blue?.name ?? '—'}</span>
      </span>
      <span className="mp-lane-mid">
        <span className="mp-lane-label"><LaneIcon lane={lane} size={14} /> {LANE_LABEL[lane]}</span>
        <span className={`mp-rate-bar ${rate === null ? 'none' : ''}`} role="img" aria-label={rate === null ? 'No win rate data' : `Blue ${formatRate(rate)}, Red ${formatRate(100 - rate)}`}>
          <span className="mp-rate-fill" style={{ width: `${blueShare}%` }} />
        </span>
        <span className="mp-rate-nums">
          <span className={`tone-${rateTone(rate, baseline)}`}>{formatRate(rate)}</span>
          <span className={`tone-${rateTone(rate === null ? null : 100 - rate, baseline)}`}>{formatRate(rate === null ? null : 100 - rate)}</span>
        </span>
      </span>
      <span className="mp-champ red">
        <span>{red?.name ?? '—'}</span>
        <ChampionIcon champion={red} size={34} />
      </span>
    </div>
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
