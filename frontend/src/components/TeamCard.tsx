import { LANES, type HiddenPlayer, type Lane, type Player, type Side, type Team } from '../api/types'
import { LaneIcon } from './ChampionArt'
import { LANE_LABEL, isHidden, overBudgetNotice, riotSourceLabel, riotSourceTag, titleCase } from '../lib/format'

export function OverBudgetBadge({ team }: { team: Pick<Team, 'over_budget' | 'over_budget_players'> }) {
  if (!team.over_budget) return null
  const notice = overBudgetNotice(team)
  return (
    <span className="badge badge-warn" title={notice} role="img" aria-label={notice}>
      ⚠ Potentially illegal team
    </span>
  )
}

function PlayerRow({ lane, player }: { lane: Lane; player: Player | HiddenPlayer | null }) {
  if (!player) {
    return (
      <tr>
        <td className="muted" title={LANE_LABEL[lane]}><LaneIcon lane={lane} size={16} /></td>
        <td colSpan={6} className="muted">
          Empty
        </td>
      </tr>
    )
  }
  if (isHidden(player)) {
    return (
      <tr>
        <td className="muted" title={LANE_LABEL[lane]}><LaneIcon lane={lane} size={16} /></td>
        <td>
          {player.name}
          {!!player.over_budget_by && (
            <span className="badge badge-warn" title={`Over the stat ceiling by ${player.over_budget_by}`}>
              ⚠ +{player.over_budget_by}
            </span>
          )}
        </td>
        <td colSpan={5} className="muted">
          stats hidden
        </td>
      </tr>
    )
  }
  return (
    <tr>
      <td className="muted" title={LANE_LABEL[lane]}><LaneIcon lane={lane} size={16} /></td>
      <td>
        {player.name}
        {player.riot && (
          <span className="badge" title={`Imported from Riot: ${player.riot.game_name}#${player.riot.tag_line} (unverified)`}>Riot</span>
        )}
        {player.riot && riotSourceTag(player.riot.data_source) && (
          <span className="badge badge-warn" title={`Stats come from ${riotSourceLabel(player.riot.data_source)}, not solo queue`}>⚠ {riotSourceTag(player.riot.data_source)}</span>
        )}
        {player.over_budget_by > 0 && (
          <span className="badge badge-warn" title={`Over the stat ceiling by ${player.over_budget_by}`}>
            ⚠ +{player.over_budget_by}
          </span>
        )}
      </td>
      <td title="Aggression">{player.aggr}</td>
      <td title="Awareness">{player.aware}</td>
      <td title="Positioning">{player.pos}</td>
      <td title="Damage">{player.dmg}</td>
      <td title="CS">{player.cs}</td>
    </tr>
  )
}

export default function TeamCard({ team, side, you }: { team: Team | null; side: Side; you?: boolean }) {
  if (!team) {
    return (
      <div className={`card team-card side-${side.toLowerCase()} ${you ? 'is-you' : ''}`}>
        <h3>
          {side === 'BLUE' ? 'Blue' : 'Red'} team {you && <span className="badge you-badge">YOU</span>}
        </h3>
        <p className="muted">No team selected yet.</p>
      </div>
    )
  }
  return (
    <div className={`card team-card side-${side.toLowerCase()} ${you ? 'is-you' : ''}`}>
      <div className="row between wrap">
        <h3>
          {team.name} {you && <span className="badge">you</span>}
        </h3>
        <OverBudgetBadge team={team} />
      </div>
      <p className="muted small">
        {[team.style1, team.style2].filter(Boolean).map(titleCase).join(' + ') || 'No playstyle'} · focus{' '}
        {[team.focus1, team.focus2]
          .filter(Boolean)
          .map((f) => LANE_LABEL[f as keyof typeof LANE_LABEL] ?? f)
          .join(' / ') || 'none'}
        {team.coach ? ` · coach ${team.coach.name}` : ''}
      </p>
      <div className="table-scroll">
        <table className="compact">
          <thead>
            <tr>
              <th />
              <th>Player</th>
              <th title="Aggression">Agg</th>
              <th title="Awareness">Awr</th>
              <th title="Positioning">Pos</th>
              <th title="Damage">Dmg</th>
              <th title="CS">CS</th>
            </tr>
          </thead>
          <tbody>
            {LANES.map((lane) => (
              <PlayerRow key={lane} lane={lane} player={team.roster[lane]} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
