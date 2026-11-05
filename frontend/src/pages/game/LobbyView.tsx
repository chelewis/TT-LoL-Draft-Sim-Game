import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import type { GameState, Side, Team } from '../../api/types'
import { ErrorNotice, Loading } from '../../components/common'
import TeamCard from '../../components/TeamCard'
import { draftRules, isCpu, isSolo, lobbyLimits, rulesetLabel, seriesLabel } from '../../lib/format'
import { useTeams } from '../../hooks/useData'

/** Single player: pick a team for each side from your own teams and the defaults, then start the draft.
 * Also used against the CPU: you choose your team and the CPU's, and which side you play. */
function SoloLobby({ game, onChange }: { game: GameState; onChange: () => void }) {
  const cpu = isCpu(game)
  const navigate = useNavigate()
  const teams = useTeams(true, game.game_id)
  const choose = useMutation({
    mutationFn: ({ side, teamId }: { side: Side; teamId: number }) =>
      api(`/lobbies/${game.lobby_id}/team`, { body: { team_id: teamId, side } }),
    onSuccess: onChange,
  })
  const start = useMutation({ mutationFn: () => api(`/games/${game.game_id}/ready`, { body: { ready: true } }), onSuccess: onChange })
  const switchSide = useMutation({
    mutationFn: (side: Side) => api(`/lobbies/${game.lobby_id}/side`, { body: { side } }),
    onSuccess: onChange,
  })
  const leave = useMutation({
    mutationFn: () => api(`/lobbies/${game.lobby_id}/leave`, { method: 'POST' }),
    onSuccess: () => navigate('/'),
  })
  const chosen = { BLUE: game.players.blue?.team_id ?? null, RED: game.players.red?.team_id ?? null }

  return (
    <div className="stack">
      <div className="card">
        <h2>{cpu ? 'Single player vs CPU' : 'Single player'}</h2>
        <p className="muted">
          {cpu
            ? "Choose your team and the CPU's team (the same team on both sides is fine), then draft against the CPU. It takes a moment to think before each pick and ban."
            : 'You control both sides. Choose a team for Blue and for Red (the same team on both sides is fine), then make every pick and ban yourself.'}{' '}
          Draft: {draftRules(game.settings)}.
          {seriesLabel(game.settings) && <> Format: {seriesLabel(game.settings)}.</>}
        </p>
        <p className="small muted">Ruleset: {rulesetLabel(game.settings)} · {lobbyLimits(game.settings)}</p>
        {cpu && (
          <div className="row wrap side-choice" role="radiogroup" aria-label="Your side">
            {(['BLUE', 'RED'] as Side[]).map((side) => (
              <button
                key={side}
                role="radio"
                aria-checked={game.you.team === side}
                className={`ghost side-${side.toLowerCase()} ${game.you.team === side ? 'active' : ''}`}
                disabled={switchSide.isPending || game.you.team === side}
                onClick={() => switchSide.mutate(side)}
              >
                Play {side === 'BLUE' ? 'Blue' : 'Red'}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="grid two">
        {(['BLUE', 'RED'] as Side[]).map((side) => (
          <div key={side} className="stack">
            <div className={`card side-${side.toLowerCase()} stack`}>
              <h3>
                {side === 'BLUE' ? 'Blue' : 'Red'} team
                {cpu && <span className="muted small"> · {game.you.team === side ? 'You' : 'CPU'}</span>}
              </h3>
              <div className="team-picker">
                {(teams.data ?? []).map((t) => (
                  <button
                    key={t.id}
                    className={`pick-card ${chosen[side] === t.id ? 'selected' : ''}`}
                    onClick={() => choose.mutate({ side, teamId: t.id })}
                    disabled={choose.isPending || !!t.rule_issues?.length}
                    aria-pressed={chosen[side] === t.id}
                    title={t.rule_issues?.join('; ') || undefined}
                  >
                    <strong>{t.name}</strong>
                    <span className="muted small">{t.is_default ? 'Default team' : 'Your team'}</span>
                    <RuleBadge team={t} />
                  </button>
                ))}
              </div>
              {teams.isLoading && <Loading />}
            </div>
            <TeamCard team={game.teams[side]} side={side} />
          </div>
        ))}
      </div>
      <ErrorNotice error={choose.error ?? start.error ?? switchSide.error ?? leave.error} />
      <div className="row wrap">
        <button className="primary" disabled={game.status !== 'READY_CHECK' || start.isPending} onClick={() => start.mutate()}>
          {game.status === 'READY_CHECK' ? 'Start draft' : 'Choose a team for both sides'}
        </button>
        <button className="ghost" onClick={() => leave.mutate()} disabled={leave.isPending}>
          Cancel game
        </button>
      </div>
    </div>
  )
}

/** Shown on a team that breaks the lobby's restrictions (the reasons are in the card's tooltip). */
function RuleBadge({ team }: { team: Team }) {
  if (!team.rule_issues?.length) return null
  return <span className="badge badge-warn">⚠ Not allowed: {team.rule_issues[0]}{team.rule_issues.length > 1 ? ` (+${team.rule_issues.length - 1} more)` : ''}</span>
}

export default function LobbyView({ game, onChange }: { game: GameState; onChange: () => void }) {
  if (isSolo(game) || isCpu(game)) return <SoloLobby game={game} onChange={onChange} />
  return <MultiLobby game={game} onChange={onChange} />
}

function MultiLobby({ game, onChange }: { game: GameState; onChange: () => void }) {
  const navigate = useNavigate()
  const teams = useTeams(true, game.game_id)
  const me = game.you.team
  const mine = me === 'BLUE' ? game.players.blue : game.players.red
  const myTeamId = mine?.team_id ?? null
  const bothJoined = !!game.players.blue && !!game.players.red

  const choose = useMutation({
    mutationFn: (teamId: number) => api(`/lobbies/${game.lobby_id}/team`, { body: { team_id: teamId } }),
    onSuccess: onChange,
  })
  const ready = useMutation({
    mutationFn: (value: boolean) => api(`/games/${game.game_id}/ready`, { body: { ready: value } }),
    onSuccess: onChange,
  })
  const swap = useMutation({
    mutationFn: (side: Side) => api(`/lobbies/${game.lobby_id}/side`, { body: { side } }),
    onSuccess: onChange,
  })
  const leave = useMutation({
    mutationFn: () => api(`/lobbies/${game.lobby_id}/leave`, { method: 'POST' }),
    onSuccess: () => navigate('/'),
  })

  const status = !bothJoined
    ? 'Waiting for a second player to join…'
    : game.status === 'READY_CHECK'
      ? 'Both teams chosen. Ready up to start the draft.'
      : 'Both players are here. Choose your teams.'

  return (
    <div className="stack">
      <div className="card row between wrap">
        <div>
          <h2>Lobby</h2>
          <p className="muted">{status}</p>
          <p className="small muted">
            Expires {game.expires_at ? new Date(game.expires_at).toLocaleTimeString() : ''} ·{' '}
            {game.settings.hide_player_data ? 'Player data hidden' : 'Player data visible'}
          </p>
          <p className="small muted">
            Draft: {draftRules(game.settings)}
          </p>
          {seriesLabel(game.settings) && <p className="small muted">Format: {seriesLabel(game.settings)}</p>}
          <p className="small muted">Ruleset: {rulesetLabel(game.settings)} · {lobbyLimits(game.settings)}</p>
        </div>
        <div className="code-box" aria-label="Lobby code">
          <span className="muted small">Lobby code</span>
          <strong>{game.lobby_code}</strong>
          <button className="ghost small" onClick={() => navigator.clipboard?.writeText(game.lobby_code)}>
            Copy
          </button>
        </div>
      </div>

      <div className="grid two">
        <div className="stack">
          <p>
            <strong>Blue:</strong> {game.players.blue?.username ?? '—'} {game.players.blue?.ready && <span className="badge ok">ready</span>}
          </p>
          <TeamCard team={game.teams.BLUE} side="BLUE" you={me === 'BLUE'} />
        </div>
        <div className="stack">
          <p>
            <strong>Red:</strong> {game.players.red?.username ?? 'waiting…'} {game.players.red?.ready && <span className="badge ok">ready</span>}
          </p>
          <TeamCard team={game.teams.RED} side="RED" you={me === 'RED'} />
        </div>
      </div>

      <div className="card stack">
        <h3>Your team</h3>
        <ErrorNotice error={choose.error ?? ready.error ?? leave.error ?? swap.error} />
        {teams.isLoading && <Loading />}
        <div className="team-picker">
          {(teams.data ?? []).map((t) => (
            <button
              key={t.id}
              className={`pick-card ${myTeamId === t.id ? 'selected' : ''}`}
              onClick={() => choose.mutate(t.id)}
              disabled={choose.isPending || !!t.rule_issues?.length}
              title={t.rule_issues?.join('; ') || undefined}
            >
              <strong>{t.name}</strong>
              <span className="muted small">{t.is_default ? 'Default team' : 'Your team'}</span>
              <RuleBadge team={t} />
              {t.over_budget && <span className="badge badge-warn">⚠ over stat ceiling</span>}
            </button>
          ))}
        </div>
        {teams.data && teams.data.length === 0 && <p className="muted">No selectable teams yet.</p>}
        <div className="row wrap">
          <button
            className="primary"
            onClick={() => ready.mutate(!mine?.ready)}
            disabled={game.status !== 'READY_CHECK' || ready.isPending}
          >
            {mine?.ready ? 'Not ready' : 'Ready'}
          </button>
          {game.you.is_owner && (
            <button
              className="ghost"
              onClick={() => swap.mutate(me === 'BLUE' ? 'RED' : 'BLUE')}
              disabled={swap.isPending}
              title={bothJoined ? 'Swap sides with the other player' : 'Move to the other side'}
            >
              ⇄ Switch to {me === 'BLUE' ? 'Red' : 'Blue'} team{bothJoined ? ' (swaps players)' : ''}
            </button>
          )}
          <button className="ghost" onClick={() => leave.mutate()} disabled={leave.isPending}>
            Leave lobby
          </button>
        </div>
      </div>
    </div>
  )
}
