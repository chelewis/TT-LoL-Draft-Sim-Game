import { useMutation } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
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
  useRefetchOnPicks(game, teams.refetch)
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
                    disabled={choose.isPending || (chosen[side] !== t.id && teamIssues(t, side).length > 0)}
                    aria-pressed={chosen[side] === t.id}
                    title={teamIssues(t, side).join('; ') || undefined}
                  >
                    <strong>{t.name}</strong>
                    <span className="muted small">{t.is_default ? 'Default team' : 'Your team'}</span>
                    <RuleBadge issues={teamIssues(t, side)} />
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

/** Why a team can't be chosen for this side: the lobby's restrictions, plus players already on the other team. */
function teamIssues(team: Team, side: Side | null): string[] {
  return [...(team.rule_issues ?? []), ...(side ? team.mirror_issues?.[side] ?? [] : [])]
}

/** Shown on a team that breaks the lobby's restrictions (the reasons are in the card's tooltip). */
function RuleBadge({ issues }: { issues: string[] }) {
  if (!issues.length) return null
  return <span className="badge badge-warn">⚠ Not allowed: {issues[0]}{issues.length > 1 ? ` (+${issues.length - 1} more)` : ''}</span>
}

/** The mirror clause depends on the other side's team: refresh the team list whenever either side's pick changes. */
function useRefetchOnPicks(game: GameState, refetch: () => unknown) {
  const blue = game.players.blue?.team_id ?? null
  const red = game.players.red?.team_id ?? null
  useEffect(() => { refetch() }, [blue, red, refetch])
}

/** The link a friend clicks to join this lobby (signing in first if they need to). */
function inviteLink(code: string): string {
  return `${window.location.origin}${import.meta.env.BASE_URL}join/${code}`
}

/** Copy to the clipboard. navigator.clipboard only exists on HTTPS or localhost, so fall back to execCommand. */
async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* try the fallback */
  }
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  document.body.removeChild(area)
  return ok
}

/** A copy button that says "Copied!" for a moment. If copying fails, shows the text so it can be copied by hand. */
export function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')
  useEffect(() => {
    if (state !== 'copied') return
    const t = setTimeout(() => setState('idle'), 2000)
    return () => clearTimeout(t)
  }, [state])
  return (
    <>
      <button className="ghost small" onClick={async () => setState((await copyText(text)) ? 'copied' : 'failed')}>
        {state === 'copied' ? 'Copied!' : label}
      </button>
      {state === 'failed' && (
        <input readOnly value={text} aria-label={label} onFocus={(e) => e.currentTarget.select()} autoFocus />
      )}
    </>
  )
}

export default function LobbyView({ game, onChange }: { game: GameState; onChange: () => void }) {
  if (isSolo(game) || isCpu(game)) return <SoloLobby game={game} onChange={onChange} />
  if (game.season) return <SeasonMatchLobby game={game} onChange={onChange} />
  return <MultiLobby game={game} onChange={onChange} />
}

/** Two managers' season match: the teams are fixed by the fixture, so all that's left is readying up. */
function SeasonMatchLobby({ game, onChange }: { game: GameState; onChange: () => void }) {
  const me = game.you.team
  const mine = me === 'BLUE' ? game.players.blue : me === 'RED' ? game.players.red : null
  const other = me === 'BLUE' ? game.players.red : game.players.blue
  const ready = useMutation({
    mutationFn: (value: boolean) => api(`/games/${game.game_id}/ready`, { body: { ready: value } }),
    onSuccess: onChange,
  })
  const status = !me
    ? 'Waiting for both managers to ready up.'
    : !mine?.ready
      ? 'Ready up to start the draft.'
      : `Waiting for ${other?.username ?? 'the other manager'} to ready up. The draft starts as soon as they do.`
  return (
    <div className="stack">
      <div className="card stack">
        <h2>Season match</h2>
        <p className="muted">{status}</p>
        <p className="small muted">Draft: {draftRules(game.settings)}</p>
        {seriesLabel(game.settings) && <p className="small muted">Format: {seriesLabel(game.settings)}</p>}
        <p className="small muted">
          Ruleset: {rulesetLabel(game.settings)} · {lobbyLimits(game.settings)} ·{' '}
          {game.settings.hide_player_data ? 'Player data hidden' : 'Player data visible'}
        </p>
      </div>
      <div className="grid two">
        {(['BLUE', 'RED'] as const).map((side) => {
          const p = side === 'BLUE' ? game.players.blue : game.players.red
          return (
            <div key={side} className="stack">
              <p>
                <strong>{side === 'BLUE' ? 'Blue' : 'Red'}:</strong> {p?.username ?? '—'}{' '}
                {p?.ready ? <span className="badge ok">ready</span> : <span className="badge">not ready</span>}
              </p>
              <TeamCard team={game.teams[side]} side={side} you={me === side} />
            </div>
          )
        })}
      </div>
      {me && (
        <div className="card stack">
          <ErrorNotice error={ready.error} />
          <div className="row wrap">
            <button className="primary" onClick={() => ready.mutate(!mine?.ready)} disabled={ready.isPending}>
              {mine?.ready ? 'Not ready' : 'Ready'}
            </button>
            {game.season && <Link to={`/seasons/${game.season.season_id}`}>← Back to the season</Link>}
          </div>
          <p className="muted small">
            You can leave this page and come back: the match waits here until you're both ready, or until the round
            is closed (then the CPU plays it).
          </p>
        </div>
      )}
    </div>
  )
}

function MultiLobby({ game, onChange }: { game: GameState; onChange: () => void }) {
  const navigate = useNavigate()
  const teams = useTeams(true, game.game_id)
  useRefetchOnPicks(game, teams.refetch)
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
          <div className="row wrap">
            <CopyButton text={game.lobby_code} label="Copy code" />
            {game.you.is_owner && !bothJoined && <CopyButton text={inviteLink(game.lobby_code)} label="Copy invite link" />}
          </div>
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
              disabled={choose.isPending || (myTeamId !== t.id && teamIssues(t, me).length > 0)}
              title={teamIssues(t, me).join('; ') || undefined}
            >
              <strong>{t.name}</strong>
              <span className="muted small">{t.is_default ? 'Default team' : 'Your team'}</span>
              <RuleBadge issues={teamIssues(t, me)} />
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
