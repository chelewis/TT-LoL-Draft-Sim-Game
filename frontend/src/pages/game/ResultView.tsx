import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import type { GameState, Lane, MatchEvent, MatchResult, ResultPlayer, Side } from '../../api/types'
import { LANES } from '../../api/types'
import { ChampionTag, ErrorNotice, Loading } from '../../components/common'
import MatchMap from '../../components/MatchMap'
import { OverBudgetBadge } from '../../components/TeamCard'
import { useChampionMap } from '../../hooks/useData'
import { LANE_LABEL, TIER_LABEL, formatDuration, isSolo, matchupText, seriesLabel, titleCase } from '../../lib/format'
import { describeEvent, summarize } from '../../lib/summary'

export default function ResultView({ game }: { game: GameState }) {
  const champions = useChampionMap()
  const result = useQuery({ queryKey: ['result', game.game_id], queryFn: () => api<MatchResult>(`/games/${game.game_id}/result`) })
  const events = useQuery({
    queryKey: ['result-events', game.game_id],
    queryFn: () => api<{ events: MatchEvent[] }>(`/games/${game.game_id}/result/events?limit=500`),
  })
  const [showLog, setShowLog] = useState(false)
  const [showMap, setShowMap] = useState(true)
  const qc = useQueryClient()
  // same teams, draft and lineups with a new seed; the current result is replaced
  const rerun = useMutation({
    mutationFn: () => api(`/games/${game.game_id}/rerun`, { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['game', game.game_id] })
      qc.resetQueries({ queryKey: ['result', game.game_id] })
      qc.resetQueries({ queryKey: ['result-events', game.game_id] })
    },
  })

  if (result.isLoading) return <Loading label="Loading results…" />
  if (result.error || !result.data) return <ErrorNotice error={result.error ?? new Error('No result.')} />
  const r = result.data
  const solo = isSolo(game)
  const me = solo ? null : game.you.team      // single player: you are neither side, so no "you" labels
  const names: Record<Side, string> = { BLUE: r.teams.BLUE.name, RED: r.teams.RED.name }
  const youWon = r.winner === me
  const bySide = (side: Side) => r.players.filter((p) => p.team === side)
  const playerName = (id: number) => r.players.find((p) => p.player_id === id)?.name ?? ''

  return (
    <div className="stack">
      <div className={`card result-banner side-${r.winner.toLowerCase()}`}>
        <p className="muted">{solo ? 'Match result' : youWon ? 'Victory' : 'Defeat'}</p>
        <h1>{names[r.winner]} wins</h1>
        {game.series && (
          <p className="muted">
            Game {game.series.game_number} of {seriesLabel(game.series)} · Series {names.BLUE} {game.series.score.BLUE}–{game.series.score.RED} {names.RED}
          </p>
        )}
        <p className="muted">
          {r.win_condition === 'NEXUS' ? 'Nexus destroyed' : 'Decided on time'} · {formatDuration(r.duration_seconds)}
        </p>
        <div className="row wrap center">
          <span className="badge gold">MVP: {r.mvp.name} ({r.mvp.champion})</span>
          <span className="badge gold">
            ACE: {r.ace.name} ({r.ace.champion}){r.ace.player_id === r.mvp.player_id ? ' — also MVP' : ''}
          </span>
        </div>
      </div>

      <div className="card stack">
        <h2>How it happened</h2>
        {summarize(r).map((line) => (
          <p key={line}>{line}</p>
        ))}
      </div>

      <div className="card stack">
        <div className="row between wrap">
          <h2>Final map</h2>
          <button className="ghost" aria-expanded={showMap} onClick={() => setShowMap(!showMap)}>{showMap ? 'Hide' : 'Show'}</button>
        </div>
        {!showMap ? null : events.isLoading ? <Loading label="Loading the map…" />
          : events.error || !events.data ? <ErrorNotice error={events.error ?? new Error('The map could not be loaded.')} />
            : <MatchMap result={r} events={events.data.events} champions={champions} names={names} />}
      </div>

      <div className="grid two">
        {(['BLUE', 'RED'] as Side[]).map((side) => (
          <div key={side} className={`card side-${side.toLowerCase()} ${side === me ? 'is-you' : ''}`}>
            <div className="row between wrap">
              <h3>
                {names[side]} {side === me && <span className="badge">you</span>}
              </h3>
              {game.teams[side] && <OverBudgetBadge team={game.teams[side]!} />}
            </div>
            <table className="compact">
              <tbody>
                <tr><td>Kills</td><td>{r.teams[side].kills}</td></tr>
                <tr><td>Gold</td><td>{r.teams[side].gold.toLocaleString()}</td></tr>
                <tr><td>Towers destroyed</td><td>{r.teams[side].towers}</td></tr>
                <tr><td>Inhibitors</td><td>{r.teams[side].inhibitors}</td></tr>
                <tr><td>Dragons</td><td>{r.teams[side].dragons}{r.teams[side].soul ? ' (soul)' : ''}</td></tr>
                <tr><td>Barons</td><td>{r.teams[side].barons}</td></tr>
                <tr><td>Damage mix</td><td>{r.teams[side].comp.damage_profile.physical} physical / {r.teams[side].comp.damage_profile.magic} magic</td></tr>
              </tbody>
            </table>
          </div>
        ))}
      </div>

      <div className="card stack">
        <h2>Lane results</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Lane</th><th>{names.BLUE}</th><th>{names.RED}</th><th>Winner</th><th>Matchup</th></tr>
            </thead>
            <tbody>
              {LANES.map((lane: Lane) => {
                const l = r.lanes[lane]
                return (
                  <tr key={lane}>
                    <td>{LANE_LABEL[lane]}</td>
                    <td><ChampionTag champion={champions.get(l.blue_champion)} /> <span className="muted small">{playerName(l.blue_player)}</span></td>
                    <td><ChampionTag champion={champions.get(l.red_champion)} /> <span className="muted small">{playerName(l.red_player)}</span></td>
                    <td>{l.winner ? `${titleCase(l.winner)} advantage` : 'Even'}</td>
                    <td className="muted">{matchupText(l.matchup)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {(['BLUE', 'RED'] as Side[]).map((side) => (
        <Scoreboard key={side} side={side} name={names[side]} players={bySide(side)} mvp={r.mvp.player_id} ace={r.ace.player_id} />
      ))}

      <div className="card stack">
        <h2>Draft summary</h2>
        <div className="grid two">
          {(['BLUE', 'RED'] as Side[]).map((side) => (
            <div key={side}>
              <h3>{names[side]}</h3>
              <p className="small muted">Picks</p>
              <div className="row wrap">
                {(side === 'BLUE' ? r.draft.blue_picks : r.draft.red_picks).map((id) => (
                  <span key={id} className="chip"><ChampionTag champion={champions.get(id)} /></span>
                ))}
              </div>
              <p className="small muted">Bans</p>
              <div className="row wrap">
                {r.draft.bans.filter((b) => b.team === side).map((b) => (
                  <span key={b.champion_id} className="chip banned"><ChampionTag champion={champions.get(b.champion_id)} /></span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card stack">
        <div className="row between wrap">
          <h2>Play by play</h2>
          <button className="ghost" onClick={() => setShowLog(!showLog)}>{showLog ? 'Hide' : 'Show'}</button>
        </div>
        {showLog && (
          <ol className="log">
            {(events.data?.events ?? []).map((e) => {
              const text = describeEvent(e, names)
              return text ? <li key={e.sequence}>{text}</li> : null
            })}
          </ol>
        )}
        <p className="small muted">Simulation v{r.simulation_version} · seed {r.seed}</p>
      </div>

      {game.series && <SeriesNext game={game} names={names} />}

      {rerun.error && <ErrorNotice error={rerun.error} />}
      <div className="row between wrap">
        <Link to="/">← Back home</Link>
        {game.you.is_owner && !game.series && (
          <button
            disabled={rerun.isPending}
            onClick={() => window.confirm('Re-run this match with the same teams and draft? The current result will be replaced.') && rerun.mutate()}
          >
            {rerun.isPending ? 'Re-running…' : 'Re-run'}
          </button>
        )}
      </div>
    </div>
  )
}

/** Between games of a series: both sides ready up, and the loser of this game picks their side for the next. */
function SeriesNext({ game, names }: { game: GameState; names: Record<Side, string> }) {
  const qc = useQueryClient()
  const s = game.series!
  const solo = isSolo(game)
  const me = game.you.team
  const loser = s.loser_side
  const choosing = !!loser && (solo || me === loser)
  const [side, setSide] = useState<Side | null>(s.next_loser_side ?? null)
  const ready = useMutation({
    mutationFn: (value: boolean) =>
      api(`/games/${game.game_id}/series/ready`, { body: { ready: value, side: value && choosing ? side : null } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['game', game.game_id] }),
  })
  const next = s.game_number + 1

  if (s.abandoned) {
    return <div className="card"><p className="muted">This series was abandoned: a game was cancelled.</p></div>
  }
  if (s.complete) {
    return (
      <div className="card row between wrap">
        <strong>{names[s.series_winner!]} wins the series {Math.max(s.score.BLUE, s.score.RED)}–{Math.min(s.score.BLUE, s.score.RED)}</strong>
        <Link to={`/series/${s.id}`}>View series result →</Link>
      </div>
    )
  }
  if (s.next_game_id) {
    return (
      <div className="card row between wrap">
        <span>Game {next} has started.</span>
        <Link to={`/game/${s.next_game_id}`}>Continue to Game {next} →</Link>
      </div>
    )
  }
  const mineReady = solo ? s.next_ready.blue && s.next_ready.red : me === 'BLUE' ? s.next_ready.blue : s.next_ready.red
  const sideName = (x: Side) => (x === 'BLUE' ? 'Blue' : 'Red')
  return (
    <div className="card stack">
      <h2>Next up: Game {next}</h2>
      <p className="muted">
        Series {names.BLUE} {s.score.BLUE}–{s.score.RED} {names.RED} · first to {s.wins_needed} wins
        {s.fearless && ' · Fearless: every champion picked so far stays locked for the rest of the series'}
      </p>
      {!solo && (
        <div className="row wrap">
          {(['BLUE', 'RED'] as Side[]).map((x) => (
            <span key={x}>
              <strong>{names[x]}</strong>{' '}
              {s.next_ready[x === 'BLUE' ? 'blue' : 'red'] ? <span className="badge ok">ready</span> : <span className="badge">not ready</span>}
            </span>
          ))}
        </div>
      )}
      {choosing && loser && (
        <div className="stack">
          <p>
            {solo ? `${names[loser]} lost this game` : 'You lost this game'}, so {solo ? 'they' : 'you'} choose the side for Game {next}:
          </p>
          <div className="row wrap side-choice" role="radiogroup" aria-label="Side for the next game">
            {(['BLUE', 'RED'] as Side[]).map((x) => (
              <button
                key={x}
                role="radio"
                aria-checked={side === x}
                className={`ghost side-${x.toLowerCase()} ${side === x ? 'active' : ''}`}
                disabled={mineReady}
                onClick={() => setSide(x)}
              >
                {sideName(x)} side{x === loser ? ' (stay)' : ' (swap)'}
              </button>
            ))}
          </div>
        </div>
      )}
      {!choosing && loser && !solo && (
        <p className="muted small">{names[loser]} lost this game, so they choose the sides for Game {next}.</p>
      )}
      <ErrorNotice error={ready.error} />
      <div className="row wrap">
        <button
          className="primary"
          disabled={ready.isPending || (!mineReady && choosing && !side)}
          onClick={() => ready.mutate(!mineReady)}
        >
          {mineReady ? 'Not ready' : solo ? `Start Game ${next}` : `Ready for Game ${next}`}
        </button>
        {mineReady && !solo && <span className="muted">Waiting for the other player…</span>}
      </div>
    </div>
  )
}

function Scoreboard({ side, name, players, mvp, ace }: { side: Side; name: string; players: ResultPlayer[]; mvp: number; ace: number }) {
  return (
    <div className={`card side-${side.toLowerCase()}`}>
      <h3>{name}</h3>
      <div className="table-scroll">
        <table className="compact">
          <thead>
            <tr><th>Player</th><th>Champion</th><th>Pool</th><th>K/D/A</th><th>CS</th><th>Gold</th><th>Rank</th></tr>
          </thead>
          <tbody>
            {players.map((p) => (
              <tr key={p.player_id}>
                <td>
                  {p.name} {p.player_id === mvp && <span className="badge gold">MVP</span>} {p.player_id === ace && <span className="badge gold">ACE</span>}
                </td>
                <td>{p.champion}</td>
                <td><span className={`badge tier-${p.comfort_tier.toLowerCase()}`}>{TIER_LABEL[p.comfort_tier]}</span></td>
                <td>{p.kills}/{p.deaths}/{p.assists}</td>
                <td>{p.cs}</td>
                <td>{p.gold.toLocaleString()}</td>
                <td>#{p.rank}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
