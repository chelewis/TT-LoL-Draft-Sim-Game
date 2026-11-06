import { Link } from 'react-router-dom'
import type { SeasonSummary } from '../../api/types'
import { ErrorNotice, Loading } from '../../components/common'
import { useSeasons } from '../../hooks/useSeasons'
import { roundLabel, SEASON_STATUS_LABELS } from '../../lib/season'

function progress(s: SeasonSummary): string {
  if (s.status === 'SETUP') return `${s.teams_entered} of ${s.team_count} teams entered`
  if (s.status === 'PLAYOFFS') return `Playoffs, round ${s.current_round} of ${s.total_rounds}`
  if (s.status === 'REGULAR') return `${s.stage === 'SWISS' ? 'Swiss stage' : 'League'}, ${roundLabel(s.current_round, s.total_rounds).toLowerCase()}`
  return `${s.team_count} teams`
}

function SeasonRow({ season }: { season: SeasonSummary }) {
  return (
    <Link className="list-row" to={`/seasons/${season.id}`}>
      <span className="stack season-row-text">
        <strong>{season.name}</strong>
        <span className="muted small">
          {season.format === 'SWISS' ? 'Swiss' : 'Round robin'} · Bring Your Own · {progress(season)}
          {!season.is_creator && season.created_by ? ` · run by ${season.created_by.username}` : ''}
        </span>
      </span>
      <span className={`badge ${season.status === 'COMPLETED' ? 'gold' : season.status === 'REGULAR' ? 'ok' : ''}`}>
        {SEASON_STATUS_LABELS[season.status]}
      </span>
    </Link>
  )
}

export default function SeasonsPage() {
  const seasons = useSeasons()
  const list = seasons.data ?? []
  const active = list.filter((s) => s.status !== 'COMPLETED' && s.status !== 'CANCELLED')
  const past = list.filter((s) => s.status === 'COMPLETED' || s.status === 'CANCELLED')
  return (
    <div className="stack">
      <div className="card row between wrap">
        <div className="stack">
          <h2>Seasons</h2>
          <p className="muted">
            Set up a league with the rules you like, enter one of your teams, and manage it through a full round robin.
            The CPU builds and runs every other team. Play your matches through the draft or let the CPU sim them.
          </p>
        </div>
        <Link className="button primary" to="/seasons/new">Create a season</Link>
      </div>

      <div className="card stack">
        <h2>Your seasons</h2>
        {seasons.isLoading && <Loading />}
        <ErrorNotice error={seasons.error} />
        {!seasons.isLoading && active.length === 0 && <p className="muted">No seasons in progress.</p>}
        {active.map((s) => <SeasonRow key={s.id} season={s} />)}
        {past.length > 0 && <h3>Finished</h3>}
        {past.map((s) => <SeasonRow key={s.id} season={s} />)}
      </div>
    </div>
  )
}
