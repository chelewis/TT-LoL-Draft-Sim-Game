import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../api/client'
import type { Season, SeasonBracket, SeasonMatch, SeasonTeamRef, StandingRow } from '../../api/types'
import { ErrorNotice, Loading } from '../../components/common'
import { useTeams } from '../../hooks/useData'
import { refreshSeason, useSeason, useSeasonSchedule } from '../../hooks/useSeasons'
import { lobbyLimits, seriesShort } from '../../lib/format'
import {
  bracketSlots, CPU_STRENGTH_LABELS, diffLabel, formatLabel, myMatchAction, opponentOf, recordLabel, resultFor,
  roundLabel, scoreLine, SEASON_STATUS_LABELS, seriesSummary, sortStandings, type StandingsKey,
} from '../../lib/season'

/** "Swiss stage · Round 2 of 3", or the bracket round's name in the playoffs. */
function roundTitle(season: Season): string {
  if (season.stage === 'PLAYOFF') return season.bracket?.rounds[season.current_round - 1]?.name ?? 'Playoffs'
  return `${season.stage_label} · ${roundLabel(season.current_round, season.total_rounds)}`
}

type Tab = 'overview' | 'standings' | 'bracket' | 'schedule' | 'teams'
const TABS: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'standings', label: 'Standings' },
  { key: 'bracket', label: 'Bracket' },
  { key: 'schedule', label: 'Schedule' },
  { key: 'teams', label: 'Teams' },
]

export default function SeasonPage() {
  const seasonId = Number(useParams().seasonId)
  const season = useSeason(seasonId)
  const [tab, setTab] = useState<Tab>('overview')

  if (season.isLoading) return <Loading label="Loading season…" />
  if (season.error || !season.data) {
    return (
      <div className="stack">
        <ErrorNotice error={season.error ?? new Error('Season not found.')} />
        <Link to="/seasons">← All seasons</Link>
      </div>
    )
  }
  const s = season.data
  return (
    <div className="stack">
      <SeasonHeader season={s} />
      {s.status === 'SETUP' ? (
        <SetupPanel season={s} />
      ) : (
        <>
          <div className="tabs" role="tablist" aria-label="Season view">
            {TABS.filter((t) => t.key !== 'bracket' || s.bracket).map((t) => (
              <button key={t.key} type="button" role="tab" aria-selected={tab === t.key}
                className={tab === t.key ? 'active' : ''} onClick={() => setTab(t.key)}>
                {t.label}
              </button>
            ))}
          </div>
          {tab === 'overview' && <Overview season={s} onStandings={() => setTab('standings')} />}
          {tab === 'standings' && <StandingsTable season={s} rows={s.standings} />}
          {tab === 'bracket' && s.bracket && <Bracket season={s} bracket={s.bracket} />}
          {tab === 'schedule' && <Schedule season={s} />}
          {tab === 'teams' && <TeamsGrid season={s} />}
        </>
      )}
    </div>
  )
}

function SeasonHeader({ season }: { season: Season }) {
  const limits = lobbyLimits(season.rules)
  return (
    <div className="card stack">
      <div className="row between wrap">
        <h2>{season.name}</h2>
        <span className={`badge ${season.status === 'COMPLETED' ? 'gold' : season.status === 'REGULAR' ? 'ok' : ''}`}>
          {SEASON_STATUS_LABELS[season.status]}
        </span>
      </div>
      <p className="muted small">
        {season.options.team_count} teams · {formatLabel(season.format, season.options)} ·{' '}
        {seriesSummary(season.format, { ...season.options, playoff_size: season.options.playoff_size ?? 0 })} · {season.ruleset_name} rules
        {limits ? ` (${limits})` : ''}
        {season.rules.fearless ? ' · Fearless' : ''}
        {' · '}{season.created_by ? `run by ${season.created_by.username}` : ''}
      </p>
      <Link className="small" to="/seasons">← All seasons</Link>
    </div>
  )
}

// ------------------------------------------------------------------- setup
function SetupPanel({ season }: { season: Season }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const teams = useTeams(true)
  const [teamId, setTeamId] = useState<number | ''>('')
  const mine = season.teams.find((t) => t.is_you)
  const onDone = (s: Season) => refreshSeason(qc, s)
  const enter = useMutation({
    mutationFn: () => api<Season>(`/seasons/${season.id}/teams`, { body: { team_id: teamId } }),
    onSuccess: onDone,
  })
  const withdraw = useMutation({
    mutationFn: () => api<Season>(`/seasons/${season.id}/teams/mine`, { method: 'DELETE' }),
    onSuccess: onDone,
  })
  const start = useMutation({ mutationFn: () => api<Season>(`/seasons/${season.id}/start`, { method: 'POST' }), onSuccess: onDone })
  const cancel = useMutation({
    mutationFn: () => api<Season>(`/seasons/${season.id}/cancel`, { method: 'POST' }),
    onSuccess: (s) => {
      refreshSeason(qc, s)
      navigate('/seasons')
    },
  })
  const cpuCount = season.options.team_count - season.teams.length

  return (
    <div className="grid two">
      <div className="card stack">
        <h3>Your team</h3>
        {mine ? (
          <>
            <div className="list-row">
              <strong>{mine.name}</strong>
              <span className="muted small">rating {mine.rating}</span>
            </div>
            <p className="muted small">
              A frozen copy of your team is entered: changes you make to the original from now on won't affect the season.
            </p>
            <ErrorNotice error={withdraw.error} />
            <button className="ghost" onClick={() => withdraw.mutate()} disabled={withdraw.isPending}>Withdraw team</button>
          </>
        ) : (
          <>
            <p className="muted small">Choose one of your complete teams (or a default team). It must meet the season's team restrictions.</p>
            <label>
              Team
              <select value={teamId} onChange={(e) => setTeamId(e.target.value ? Number(e.target.value) : '')}>
                <option value="">Choose a team…</option>
                {(teams.data ?? []).map((t) => (
                  <option key={t.id} value={t.id}>{t.name}{t.is_default ? ' (default)' : ''}</option>
                ))}
              </select>
            </label>
            {teams.data && teams.data.length === 0 && (
              <p className="muted small">You have no complete teams yet. <Link to="/teams/new">Build one →</Link></p>
            )}
            <ErrorNotice error={enter.error} />
            <button className="primary" onClick={() => enter.mutate()} disabled={!teamId || enter.isPending}>Enter team</button>
          </>
        )}
      </div>
      <div className="card stack">
        <h3>Start the season</h3>
        <p className="muted small">
          {cpuCount > 0
            ? `Starting generates ${cpuCount} CPU team${cpuCount === 1 ? '' : 's'} to fill the league (${CPU_STRENGTH_LABELS[season.options.cpu_strength].split(':')[0].toLowerCase()} strength), seeds everyone at random and draws up the schedule.`
            : 'Every place is filled. Starting seeds everyone at random and draws up the schedule.'}
        </p>
        {season.is_creator ? (
          <>
            <ErrorNotice error={start.error ?? cancel.error} />
            <button className="primary" onClick={() => start.mutate()} disabled={!season.can_start || start.isPending}>
              {start.isPending ? 'Building the league…' : 'Start season'}
            </button>
            {!season.can_start && <p className="muted small">Enter your team first.</p>}
            <button className="ghost danger" disabled={cancel.isPending}
              onClick={() => window.confirm('Cancel this season? It cannot be restarted.') && cancel.mutate()}>
              Cancel season
            </button>
          </>
        ) : (
          <p className="muted small">Waiting for the creator to start the season.</p>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- overview
function TeamName({ team, seasonId }: { team: SeasonTeamRef | null; seasonId: number }) {
  if (!team) return <span className="muted">TBD</span>
  return (
    <Link to={`/seasons/${seasonId}/teams/${team.id}`} className={team.is_you ? 'you-team' : undefined}>
      {team.name}
      {team.is_you && <span className="badge you-badge">YOU</span>}
    </Link>
  )
}

function MatchRow({ match, seasonId }: { match: SeasonMatch; seasonId: number }) {
  const watch = match.series_id && match.games.length > 1 ? `/series/${match.series_id}` : match.latest_game_id ? `/game/${match.latest_game_id}` : null
  const homeWon = match.winner_team_id !== null && match.winner_team_id === match.home?.id
  const awayWon = match.winner_team_id !== null && match.winner_team_id === match.away?.id
  return (
    <div className={`match-row ${match.yours ? 'is-yours' : ''}`}>
      <span className={`match-team home ${homeWon ? 'won' : ''}`}><TeamName team={match.home} seasonId={seasonId} /></span>
      <span className="match-score">
        {scoreLine(match)}
        {match.status === 'LIVE' && <span className="badge ok">live</span>}
      </span>
      <span className={`match-team away ${awayWon ? 'won' : ''}`}><TeamName team={match.away} seasonId={seasonId} /></span>
      <span className="match-meta muted small">
        {match.format !== 'BO1' && seriesShort(match.format)}
        {match.played_mode === 'AUTO' && match.status === 'COMPLETED' && <span className="badge" title="Played by the CPU for both teams">sim</span>}
        {watch && <Link to={watch}>{match.status === 'COMPLETED' ? 'Result' : 'Watch'}</Link>}
      </span>
    </div>
  )
}

function MyMatchCard({ season }: { season: Season }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const match = season.my_match
  const action = myMatchAction(match)
  const play = useMutation({
    mutationFn: () => api<{ game_id: number }>(`/seasons/matches/${match!.id}/play`, { method: 'POST' }),
    onSuccess: (r) => navigate(`/game/${r.game_id}`),
  })
  const auto = useMutation({
    mutationFn: () => api<Season>(`/seasons/matches/${match!.id}/auto`, { method: 'POST' }),
    onSuccess: (s) => refreshSeason(qc, s),
  })
  if (!match || season.my_team_id === null) {
    return (
      <div className="card stack">
        <h3>Your match</h3>
        <p className="muted">
          {season.my_team_id === null ? "You don't manage a team in this season."
            : season.my_team_eliminated ? 'Your team is out. The rest of the season plays on without you.'
            : season.standings.find((r) => r.team.is_you)?.swiss_status === 'QUALIFIED' && season.stage === 'SWISS'
              ? 'Your team has qualified for the playoffs. Waiting for the Swiss stage to finish.'
            : 'Your team has a bye this round.'}
        </p>
      </div>
    )
  }
  const opponent = opponentOf(match, season.my_team_id)
  const result = resultFor(match, season.my_team_id)
  return (
    <div className="card stack my-match">
      <h3>Your match · {roundTitle(season)}</h3>
      <div className="row between wrap">
        <span>
          vs <TeamName team={opponent} seasonId={season.id} />
          {opponent?.is_cpu && <span className="badge">CPU</span>}
        </span>
        <span className="muted small">{seriesShort(match.format)} · you are {match.home?.id === season.my_team_id ? 'Blue' : 'Red'} in game 1</span>
      </div>
      {action === 'DONE' ? (
        <div className="row between wrap">
          <strong className={result?.startsWith('W') ? 'win-text' : 'loss-text'}>{result?.startsWith('W') ? 'Won' : 'Lost'} {result?.slice(2)}</strong>
          {match.latest_game_id && <Link to={match.series_id && match.games.length > 1 ? `/series/${match.series_id}` : `/game/${match.latest_game_id}`}>See the result →</Link>}
        </div>
      ) : (
        <>
          {match.status === 'LIVE' && <p className="muted small">Score {match.home_score} - {match.away_score}. Pick up where you left off, or let the CPU finish it.</p>}
          <ErrorNotice error={play.error ?? auto.error} />
          <div className="row wrap">
            <button className="primary" onClick={() => play.mutate()} disabled={play.isPending || auto.isPending}>
              {action === 'CONTINUE' ? 'Continue match' : 'Play live (draft)'}
            </button>
            <button onClick={() => auto.mutate()} disabled={play.isPending || auto.isPending}
              title="The CPU drafts and sets the lineup for your team too">
              {auto.isPending ? 'Simulating…' : 'Auto-sim'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}

function AdvancePanel({ season }: { season: Season }) {
  const qc = useQueryClient()
  const advance = useMutation({
    mutationFn: (force: boolean) => api<Season>(`/seasons/${season.id}/advance`, { body: { force } }),
    onSuccess: (s) => refreshSeason(qc, s),
  })
  const last = season.current_round >= season.total_rounds
  const waiting = season.waiting_on_managers
  const label = season.stage === 'PLAYOFF'
    ? (last ? 'Finish the season' : 'Advance to the next round')
    : season.stage === 'REGULAR' && last
      ? (season.options.playoff_size ? 'Start the playoffs' : 'Finish the season')
      : 'Advance to the next round'
  return (
    <div className="stack">
      <ErrorNotice error={advance.error} />
      <div className="row wrap">
        <button className="primary" onClick={() => advance.mutate(false)} disabled={advance.isPending || waiting > 0}>
          {advance.isPending ? 'Simulating the round…' : label}
        </button>
        {waiting > 0 && (
          <button className="ghost" disabled={advance.isPending}
            onClick={() => window.confirm(`Auto-sim the ${waiting} unplayed manager match${waiting === 1 ? '' : 'es'} and move on?`) && advance.mutate(true)}>
            Force it (auto-sim {waiting} unplayed)
          </button>
        )}
      </div>
      <p className="muted small">
        {waiting > 0
          ? 'Play or auto-sim your match first. The CPU plays the other matches when the round closes.'
          : 'The CPU plays the remaining matches of the round when you advance.'}
      </p>
    </div>
  )
}

function Overview({ season, onStandings }: { season: Season; onStandings: () => void }) {
  const top = season.standings.slice(0, 5)
  return (
    <div className="stack">
      {season.status === 'COMPLETED' && season.champion && (
        <div className="card result-banner champion-banner">
          <span className="muted">Champion</span>
          <h2>🏆 {season.champion.name}</h2>
          {season.champion.is_you && <p>Your team won the season!</p>}
        </div>
      )}
      {season.status === 'CANCELLED' && <div className="notice">This season was cancelled.</div>}
      {(season.status === 'REGULAR' || season.status === 'PLAYOFFS') && (
        <div className="grid two">
          <MyMatchCard season={season} />
          <div className="card stack">
            <h3>{roundTitle(season)}</h3>
            {season.round_matches.map((m) => <MatchRow key={m.id} match={m} seasonId={season.id} />)}
            {season.is_creator && <AdvancePanel season={season} />}
            {!season.is_creator && <p className="muted small">The season's creator moves the season on to the next round.</p>}
          </div>
        </div>
      )}
      <div className="card stack">
        <div className="row between wrap">
          <h3>{season.format === 'SWISS' ? 'Swiss standings' : 'Standings'}</h3>
          <button className="ghost small" onClick={onStandings}>Full table →</button>
        </div>
        <StandingsTable season={season} rows={top} compact />
      </div>
    </div>
  )
}

// --------------------------------------------------------------- standings
const COLUMNS: { key: StandingsKey; label: string; title?: string; numeric?: boolean }[] = [
  { key: 'rank', label: '#', numeric: true },
  { key: 'name', label: 'Team' },
  { key: 'played', label: 'P', title: 'Played', numeric: true },
  { key: 'wins', label: 'W', title: 'Wins', numeric: true },
  { key: 'losses', label: 'L', title: 'Losses', numeric: true },
  { key: 'game_diff', label: 'GD', title: 'Game differential (games won minus games lost)', numeric: true },
]

function FormPips({ form }: { form: StandingRow['form'] }) {
  return (
    <span className="form-pips" aria-label={`Last results: ${form.join(' ') || 'none'}`}>
      {form.map((f, i) => <i key={i} className={f === 'W' ? 'w' : 'l'}>{f}</i>)}
    </span>
  )
}

function StandingsTable({ season, rows, compact = false }: { season: Season; rows: StandingRow[]; compact?: boolean }) {
  const [sort, setSort] = useState<{ key: StandingsKey; desc: boolean }>({ key: 'rank', desc: false })
  const sorted = compact ? rows : sortStandings(rows, sort.key, sort.desc)
  const choose = (key: StandingsKey) =>
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: key !== 'rank' && key !== 'name' && key !== 'losses' }))
  return (
    <div className={compact ? 'table-scroll' : 'card table-scroll'}>
      <table className="compact standings">
        <thead>
          <tr>
            {COLUMNS.map((c) => (
              <th key={c.key} title={c.title} className={c.numeric ? 'num' : undefined}
                aria-sort={!compact && sort.key === c.key ? (sort.desc ? 'descending' : 'ascending') : undefined}>
                {compact ? c.label : (
                  <button type="button" className="mx-sort" onClick={() => choose(c.key)}>
                    {c.label}{sort.key === c.key ? (sort.desc ? ' ▼' : ' ▲') : ''}
                  </button>
                )}
              </th>
            ))}
            <th>Form</th>
            {season.format === 'SWISS' && <th>Status</th>}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.team.id} className={[r.team.is_you ? 'is-you' : '', r.eliminated ? 'is-out' : ''].join(' ').trim() || undefined}>
              <td className="num">{r.rank}</td>
              <td>
                <TeamName team={r.team} seasonId={season.id} />
                {r.team.is_cpu && <span className="muted small"> CPU</span>}
              </td>
              <td className="num">{r.played}</td>
              <td className="num">{r.wins}</td>
              <td className="num">{r.losses}</td>
              <td className="num">{diffLabel(r.game_diff)}</td>
              <td><FormPips form={r.form} /></td>
              {season.format === 'SWISS' && (
                <td>
                  {r.swiss_status === 'QUALIFIED' && <span className="badge ok">Qualified</span>}
                  {r.swiss_status === 'ELIMINATED' && <span className="badge">Out</span>}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {!compact && (
        <p className="muted small">
          {season.format === 'SWISS'
            ? `${season.options.swiss_wins} wins qualifies for the playoffs; ${season.options.swiss_losses} losses and a team is out.`
            : 'Ranked by wins, then head-to-head between tied teams, then game differential.'}
          {season.format !== 'SWISS' && season.options.playoff_size ? ` The top ${season.options.playoff_size} reach the playoffs.` : ''}
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- schedule
function Schedule({ season }: { season: Season }) {
  const schedule = useSeasonSchedule(season.id)
  const [mineOnly, setMineOnly] = useState(false)
  if (schedule.isLoading) return <Loading />
  if (schedule.error) return <ErrorNotice error={schedule.error} />
  return (
    <div className="stack">
      {season.my_team_id !== null && (
        <label className="check">
          <input type="checkbox" checked={mineOnly} onChange={(e) => setMineOnly(e.target.checked)} />
          Only my team's matches
        </label>
      )}
      {(schedule.data?.rounds ?? []).map((r) => {
        const matches = mineOnly ? r.matches.filter((m) => m.yours) : r.matches
        if (!matches.length) return null
        return (
          <div key={`${r.stage}-${r.round}`} className={`card stack ${r.current ? 'current-round' : ''}`}>
            <h3>
              {r.stage === 'PLAYOFF' ? r.name : `${r.stage_label} · ${r.name}`}
              {r.current && <span className="badge ok">current</span>}
            </h3>
            {matches.map((m) => <MatchRow key={m.id} match={m} seasonId={season.id} />)}
          </div>
        )
      })}
    </div>
  )
}

// ------------------------------------------------------------------- teams
function TeamsGrid({ season }: { season: Season }) {
  const records = new Map(season.standings.map((r) => [r.team.id, r]))
  const teams = [...season.teams].sort((a, b) => a.seed - b.seed)
  return (
    <div className="grid two">
      {teams.map((t) => {
        const record = records.get(t.id)
        return (
          <Link key={t.id} className="list-row" to={`/seasons/${season.id}/teams/${t.id}`}>
            <span className="stack season-row-text">
              <strong>{t.name}{t.is_you && <span className="badge you-badge">YOU</span>}</strong>
              <span className="muted small">
                Seed {t.seed} · {t.is_cpu ? 'CPU' : `managed by ${t.manager?.username}`} · rating {t.rating}
              </span>
            </span>
            {record && <span className="badge">{recordLabel(record)}</span>}
          </Link>
        )
      })}
    </div>
  )
}

// ----------------------------------------------------------------- bracket
function BracketBox({ match, seasonId }: { match: SeasonMatch | null; seasonId: number }) {
  if (!match) {
    return (
      <div className="bracket-match tbd">
        <span className="muted">TBD</span>
        <span className="muted">TBD</span>
      </div>
    )
  }
  const link = match.series_id && match.games.length > 1 ? `/series/${match.series_id}` : match.latest_game_id ? `/game/${match.latest_game_id}` : null
  const line = (team: SeasonTeamRef | null, score: number) => (
    <span className={`bracket-team ${match.winner_team_id !== null && match.winner_team_id === team?.id ? 'won' : ''}`}>
      <TeamName team={team} seasonId={seasonId} />
      <strong>{match.status === 'SCHEDULED' ? '' : score}</strong>
    </span>
  )
  return (
    <div className={`bracket-match ${match.yours ? 'is-yours' : ''}`}>
      {line(match.home, match.home_score)}
      {line(match.away, match.away_score)}
      {(link || match.status === 'LIVE') && (
        <span className="small bracket-link">
          {match.status === 'LIVE' && <span className="badge ok">live</span>}
          {link && <Link to={link}>{match.status === 'COMPLETED' ? 'Result' : 'Watch'}</Link>}
        </span>
      )}
    </div>
  )
}

function Bracket({ season, bracket }: { season: Season; bracket: SeasonBracket }) {
  return (
    <div className="card stack">
      <h3>Playoffs</h3>
      {season.status === 'REGULAR' && (
        <p className="muted small">
          {season.format === 'SWISS'
            ? `The ${bracket.size} teams that qualify from the Swiss stage are seeded by record.`
            : `The top ${bracket.size} of the table qualify: 1st plays ${bracket.size}th, and the top two seeds can only meet in the final.`}
        </p>
      )}
      <div className="bracket" style={{ gridTemplateColumns: `repeat(${bracket.rounds.length}, minmax(180px, 1fr))` }}>
        {bracket.rounds.map((r) => (
          <div key={r.round} className="bracket-round">
            <h4>{r.name} <span className="muted small">{seriesShort(r.format)}</span></h4>
            <div className="bracket-column">
              {bracketSlots(r).map((m, i) => <BracketBox key={m?.id ?? `tbd-${i}`} match={m} seasonId={season.id} />)}
            </div>
          </div>
        ))}
      </div>
      {season.champion && <p>🏆 <strong>{season.champion.name}</strong> won the playoffs.</p>}
    </div>
  )
}
