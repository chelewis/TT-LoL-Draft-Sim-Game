import { Link, useParams } from 'react-router-dom'
import { LANES, type Player } from '../../api/types'
import { ErrorNotice, Loading } from '../../components/common'
import TeamCard from '../../components/TeamCard'
import { useSeasonTeam } from '../../hooks/useSeasons'
import { isHidden, LANE_LABEL } from '../../lib/format'
import { diffLabel, opponentOf, recordLabel, resultFor, roundLabel } from '../../lib/season'

export default function SeasonTeamPage() {
  const params = useParams()
  const seasonId = Number(params.seasonId)
  const teamId = Number(params.teamId)
  const detail = useSeasonTeam(seasonId, teamId)

  if (detail.isLoading) return <Loading label="Loading team…" />
  if (detail.error || !detail.data) {
    return (
      <div className="stack">
        <ErrorNotice error={detail.error ?? new Error('Team not found.')} />
        <Link to={`/seasons/${seasonId}`}>← Back to the season</Link>
      </div>
    )
  }
  const { team, view, record, matches, player_stats: stats } = detail.data
  const players = LANES.map((lane) => ({ lane, player: view.roster[lane] }))
    .filter((p): p is { lane: typeof p.lane; player: Player } => !!p.player && !isHidden(p.player))

  return (
    <div className="stack">
      <div className="card stack">
        <div className="row between wrap">
          <h2>
            {team.name}
            {team.is_you && <span className="badge you-badge">YOU</span>}
          </h2>
          {record && (
            <span className="badge">
              #{record.rank} · {recordLabel(record)} · GD {diffLabel(record.game_diff)}
            </span>
          )}
        </div>
        <p className="muted small">
          Seed {team.seed} · {team.is_cpu ? 'Run by the CPU' : `Managed by ${team.manager?.username}`}
        </p>
        <Link className="small" to={`/seasons/${seasonId}`}>← Back to the season</Link>
      </div>

      <div className="grid two">
        <TeamCard team={view} side="BLUE" you={team.is_you} />
        <div className="card stack">
          <h3>Season stats</h3>
          {players.length === 0 || Object.keys(stats).length === 0 ? (
            <p className="muted">{Object.keys(stats).length === 0 && view.hidden ? 'Player data is hidden in this season.' : 'No games played yet.'}</p>
          ) : (
            <div className="table-scroll">
              <table className="compact">
                <thead>
                  <tr>
                    <th>Player</th>
                    <th className="num" title="Games played">G</th>
                    <th className="num" title="Kills / deaths / assists">K/D/A</th>
                    <th className="num" title="(Kills + assists) / deaths">KDA</th>
                    <th className="num" title="Creep score per game">CS/g</th>
                    <th className="num" title="Times named MVP">MVP</th>
                  </tr>
                </thead>
                <tbody>
                  {players.map(({ lane, player }) => {
                    const s = stats[String(player.id)]
                    return (
                      <tr key={player.id}>
                        <td title={LANE_LABEL[lane]}>{player.name}</td>
                        <td className="num">{s?.games ?? 0}</td>
                        <td className="num">{s ? `${s.kills}/${s.deaths}/${s.assists}` : '-'}</td>
                        <td className="num">{s ? s.kda.toFixed(2) : '-'}</td>
                        <td className="num">{s && s.games ? Math.round(s.cs / s.games) : '-'}</td>
                        <td className="num">{s?.mvps ?? 0}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <div className="card stack">
        <h3>Matches</h3>
        {matches.map((m) => {
          const opponent = opponentOf(m, team.id)
          const result = resultFor(m, team.id)
          const link = m.series_id && m.games.length > 1 ? `/series/${m.series_id}` : m.latest_game_id ? `/game/${m.latest_game_id}` : null
          return (
            <div key={m.id} className="list-row">
              <span>
                <span className="muted small">{m.stage === 'PLAYOFF' ? `Playoffs round ${m.round}` : `${m.stage === 'SWISS' ? 'Swiss ' : ''}${roundLabel(m.round, 0)}`} · </span>
                {m.home?.id === team.id ? 'vs' : '@'}{' '}
                {opponent ? <Link to={`/seasons/${seasonId}/teams/${opponent.id}`}>{opponent.name}</Link> : 'TBD'}
              </span>
              <span className="row">
                {result ? <strong className={result.startsWith('W') ? 'win-text' : 'loss-text'}>{result}</strong>
                  : <span className="muted small">{m.status === 'LIVE' ? 'in progress' : 'to play'}</span>}
                {link && <Link className="small" to={link}>{m.status === 'COMPLETED' ? 'Result' : 'Watch'}</Link>}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
