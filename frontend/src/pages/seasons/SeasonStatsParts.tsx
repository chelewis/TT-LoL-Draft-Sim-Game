import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Lane, Season, SeasonPlayerStats, SeasonTeamRef } from '../../api/types'
import { ErrorNotice, Loading } from '../../components/common'
import { useSeasonStats } from '../../hooks/useSeasons'
import { LANE_LABEL } from '../../lib/format'
import { sortPlayerStats, statValue, type PlayerStatsKey } from '../../lib/season'

const LANES: Lane[] = ['TOP', 'JUNGLE', 'MID', 'BOT', 'SUPPORT']

function TeamLink({ team, seasonId }: { team: SeasonTeamRef | null; seasonId: number }) {
  if (!team) return <span className="muted">?</span>
  return (
    <Link to={`/seasons/${seasonId}/teams/${team.id}`} className={team.is_you ? 'is-yours' : undefined}>
      {team.logo ? `${team.logo} ` : ''}{team.name}
    </Link>
  )
}

function AwardLine({ label, player, seasonId }: { label: string; player: SeasonPlayerStats | null; seasonId: number }) {
  return (
    <div className="award">
      <span className="muted small">{label}</span>
      {player ? (
        <>
          <strong>{player.name}</strong>
          <span className="small"><TeamLink team={player.team} seasonId={seasonId} /> · {player.lane ? LANE_LABEL[player.lane] : ''}</span>
          <span className="muted small">
            {statValue(player.rating, 1)} rating · {statValue(player.kda, 2)} KDA · {player.mvps} MVP{player.mvps === 1 ? '' : 's'} in {player.games} games
          </span>
        </>
      ) : <span className="muted small">Not decided yet</span>}
    </div>
  )
}

/** Season MVP, finals MVP and the all-pro team. Before the season ends: who's leading the race for them. */
export function AwardsCard({ season }: { season: Season }) {
  const stats = useSeasonStats(season.id)
  if (stats.isLoading) return <Loading label="Loading awards…" />
  if (stats.error) return <ErrorNotice error={stats.error} />
  if (!stats.data || stats.data.games === 0) return null
  const { awards, final } = stats.data
  return (
    <div className="card stack">
      <div className="row between wrap">
        <h3>{final ? 'Season awards' : 'Award race'}</h3>
        {!final && <span className="muted small">Leaders so far · decided when the season ends</span>}
      </div>
      <div className="awards">
        <AwardLine label={final ? 'Season MVP' : 'MVP race leader'} player={awards.season_mvp} seasonId={season.id} />
        {(final && awards.finals_mvp) && <AwardLine label="Finals MVP" player={awards.finals_mvp} seasonId={season.id} />}
      </div>
      <h4>{final ? 'All-pro team' : 'All-pro team so far'}</h4>
      <div className="table-scroll">
        <table className="compact">
          <tbody>
            {awards.all_pro.map((a) => (
              <tr key={a.lane}>
                <td className="muted">{LANE_LABEL[a.lane]}</td>
                <td>{a.player ? <strong>{a.player.name}</strong> : <span className="muted">—</span>}</td>
                <td>{a.player && <TeamLink team={a.player.team} seasonId={season.id} />}</td>
                <td className="num">{a.player ? `${statValue(a.player.rating, 1)} rating` : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const COLUMNS: { key: Exclude<PlayerStatsKey, 'name'>; label: string; title?: string; decimals: number }[] = [
  { key: 'games', label: 'G', title: 'Games played', decimals: 0 },
  { key: 'rating', label: 'Rating', title: 'Average rank score: the score that picks each game\'s MVP', decimals: 1 },
  { key: 'kda', label: 'KDA', title: '(Kills + assists) / deaths', decimals: 2 },
  { key: 'kills_pg', label: 'K', title: 'Kills per game', decimals: 1 },
  { key: 'deaths_pg', label: 'D', title: 'Deaths per game', decimals: 1 },
  { key: 'assists_pg', label: 'A', title: 'Assists per game', decimals: 1 },
  { key: 'cs_pg', label: 'CS', title: 'CS per game', decimals: 0 },
  { key: 'damage_pg', label: 'Dmg', title: 'Damage per game', decimals: 0 },
  { key: 'mvps', label: 'MVP', title: 'Game MVPs', decimals: 0 },
]

/** The Stats tab: the leaders in each stat, the awards and every player's season line. */
export function SeasonStatsTab({ season }: { season: Season }) {
  const stats = useSeasonStats(season.id)
  const [sort, setSort] = useState<{ key: PlayerStatsKey; desc: boolean }>({ key: 'rating', desc: true })
  const [lane, setLane] = useState<Lane | ''>('')
  if (stats.isLoading) return <Loading label="Loading stats…" />
  if (stats.error || !stats.data) return <ErrorNotice error={stats.error ?? new Error('No stats.')} />
  const data = stats.data
  if (data.games === 0) return <div className="card muted">No games played yet. Stats appear after the first match.</div>

  const rows = sortPlayerStats(lane ? data.players.filter((p) => p.lane === lane) : data.players, sort.key, sort.desc)
  // fewer deaths is better: sort that one ascending first
  const choose = (key: PlayerStatsKey) =>
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: key !== 'deaths_pg' && key !== 'name' }))

  return (
    <div className="stack">
      <AwardsCard season={season} />
      <div className="leader-grid">
        {data.leaders.map((cat) => (
          <div key={cat.key} className="card stack leader-card">
            <h4>{cat.label}</h4>
            {cat.rows.length === 0 ? <p className="muted small">No one yet.</p> : (
              <ol className="leader-list">
                {cat.rows.map((r) => (
                  <li key={r.player_id} className={r.team?.is_you ? 'is-yours' : undefined}>
                    <span className="leader-name">
                      {r.name}
                      <span className="muted small"> {r.team?.name ?? ''}</span>
                    </span>
                    <strong className="num">{statValue(r.value, cat.decimals)}</strong>
                  </li>
                ))}
              </ol>
            )}
          </div>
        ))}
      </div>
      <p className="muted small">
        Per-game leaders need at least {data.min_games} game{data.min_games === 1 ? '' : 's'} (half the most anyone has played). {data.games} games so far.
      </p>

      <div className="card stack">
        <div className="row between wrap">
          <h3>Players</h3>
          <label className="row small">
            Lane
            <select value={lane} onChange={(e) => setLane(e.target.value as Lane | '')}>
              <option value="">All lanes</option>
              {LANES.map((l) => <option key={l} value={l}>{LANE_LABEL[l]}</option>)}
            </select>
          </label>
        </div>
        <div className="table-scroll">
          <table className="compact">
            <thead>
              <tr>
                <th aria-sort={sort.key === 'name' ? (sort.desc ? 'descending' : 'ascending') : undefined}>
                  <button type="button" className="mx-sort" onClick={() => choose('name')}>
                    Player{sort.key === 'name' ? (sort.desc ? ' ▼' : ' ▲') : ''}
                  </button>
                </th>
                <th>Team</th>
                <th>Lane</th>
                {COLUMNS.map((c) => (
                  <th key={c.key} className="num" title={c.title}
                    aria-sort={sort.key === c.key ? (sort.desc ? 'descending' : 'ascending') : undefined}>
                    <button type="button" className="mx-sort" onClick={() => choose(c.key)}>
                      {c.label}{sort.key === c.key ? (sort.desc ? ' ▼' : ' ▲') : ''}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.player_id} className={p.team?.is_you ? 'is-you' : undefined}>
                  <td title={p.champions.length ? `Most played: ${p.champions.join(', ')}` : undefined}>{p.name}</td>
                  <td><TeamLink team={p.team} seasonId={season.id} /></td>
                  <td className="muted">{p.lane ? LANE_LABEL[p.lane] : ''}</td>
                  {COLUMNS.map((c) => <td key={c.key} className="num">{statValue(p[c.key], c.decimals)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
