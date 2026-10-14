import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import type { SeriesResult, Side } from '../../api/types'
import { ChampionTag, ErrorNotice, Loading } from '../../components/common'
import { useChampionMap } from '../../hooks/useData'
import { formatDuration, seriesLabel, titleCase } from '../../lib/format'

/** Every game of a series: who played which side, the draft and the result. */
export default function SeriesResultView({ seriesId }: { seriesId: number }) {
  const champions = useChampionMap()
  const series = useQuery({ queryKey: ['series', seriesId], queryFn: () => api<SeriesResult>(`/series/${seriesId}`) })

  if (series.isLoading) return <Loading label="Loading the series…" />
  if (series.error || !series.data) return <ErrorNotice error={series.error ?? new Error('Series not found.')} />
  const s = series.data
  // team keys are the side each team played in game 1
  const name = (team: Side) => s.teams[team] ?? (team === 'BLUE' ? 'Blue team' : 'Red team')
  const banner = s.winner ? `side-${s.winner.toLowerCase()}` : ''

  return (
    <div className="stack series-card">
      <div className={`card result-banner ${banner}`}>
        <p className="muted">Series result · {seriesLabel(s)}</p>
        <h1>
          {s.winner ? `${name(s.winner)} wins the series` : s.abandoned ? 'Series abandoned' : 'Series in progress'}
        </h1>
        <p className="muted">
          {name('BLUE')} {s.score.BLUE}–{s.score.RED} {name('RED')} · first to {s.wins_needed} wins
        </p>
      </div>

      {s.games.map((g) => {
        const sides: [Side, Side, number[]][] = g.draft
          ? [['BLUE', g.blue_team, g.draft.blue_picks], ['RED', g.red_team, g.draft.red_picks]]
          : []
        return (
          <div key={g.game_id} className="card stack">
            <div className="row between wrap">
              <h2>Game {g.game_number}</h2>
              <Link to={`/game/${g.game_id}`}>Full result →</Link>
            </div>
            <p>
              <span className="badge side-blue">Blue</span> {name(g.blue_team)} vs <span className="badge side-red">Red</span> {name(g.red_team)}
            </p>
            {g.winner ? (
              <p>
                <strong>{name(g.winner)} wins</strong>
                <span className="muted">
                  {' '}· {g.win_condition === 'NEXUS' ? 'Nexus destroyed' : 'Decided on time'}
                  {g.duration_seconds != null && ` · ${formatDuration(g.duration_seconds)}`}
                </span>
                {g.mvp && <span className="badge gold">MVP: {g.mvp.name} ({g.mvp.champion})</span>}
              </p>
            ) : (
              <p className="muted">{titleCase(g.status.replaceAll('_', ' '))}</p>
            )}
            {g.draft && (
              <div className="grid two">
                {sides.map(([side, team, picks]) => (
                  <div key={side} className={`side-${side.toLowerCase()}`}>
                    <h3>{name(team)} <span className="muted small">({side === 'BLUE' ? 'Blue' : 'Red'})</span></h3>
                    <p className="small muted">Picks</p>
                    <div className="row wrap">
                      {picks.map((id) => (
                        <span key={id} className="chip"><ChampionTag champion={champions.get(id)} /></span>
                      ))}
                    </div>
                    <p className="small muted">Bans</p>
                    <div className="row wrap">
                      {g.draft!.bans.filter((b) => b.team === side).map((b) => (
                        <span key={b.champion_id} className="chip banned"><ChampionTag champion={champions.get(b.champion_id)} /></span>
                      ))}
                      {g.draft!.bans.every((b) => b.team !== side) && <span className="muted small">None</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
