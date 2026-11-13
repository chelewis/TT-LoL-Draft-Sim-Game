import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../api/client'
import type { Season } from '../../api/types'
import { ErrorNotice, Loading } from '../../components/common'
import { useTeams } from '../../hooks/useData'
import { refreshSeason, useSeasonInvite } from '../../hooks/useSeasons'
import { lobbyLimits } from '../../lib/format'
import { CPU_STRENGTH_LABELS, deadlineLabel, formatLabel, SEASON_STATUS_LABELS, seriesSummary } from '../../lib/season'
import { DraftTeamForm, type DraftTeamBody } from './SeasonDraftParts'

/** /seasons/join/:code: what the season is, then enter one of your teams to join it. */
export default function SeasonJoinPage() {
  const code = (useParams().code ?? '').toUpperCase()
  const invite = useSeasonInvite(code)
  const teams = useTeams(true)
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [teamId, setTeamId] = useState<number | ''>('')
  const join = useMutation({
    mutationFn: (body: { team_id: number } | DraftTeamBody) => api<Season>(`/seasons/join/${code}`, { body }),
    onSuccess: (season) => {
      refreshSeason(qc, season)
      navigate(`/seasons/${season.id}`)
    },
  })

  if (invite.isLoading) return <Loading label="Looking up the season…" />
  if (invite.error || !invite.data) {
    return (
      <div className="stack">
        <ErrorNotice error={invite.error ?? new Error('No season with that code.')} />
        <Link to="/seasons">← All seasons</Link>
      </div>
    )
  }
  const s = invite.data
  // already in it: straight to the hub
  if (s.has_team || (s.is_member && !s.can_join)) return <Navigate to={`/seasons/${s.id}`} replace />
  const limits = lobbyLimits(s.rules)

  return (
    <div className="stack">
      <div className="card stack">
        <div className="row between wrap">
          <h2>{s.name}</h2>
          <span className="badge">{SEASON_STATUS_LABELS[s.status]}</span>
        </div>
        <p className="muted small">
          Run by {s.created_by?.username ?? '?'} · {s.roster_mode === 'DRAFT' ? 'Player Draft' : 'Bring Your Own'} · {s.options.team_count} teams · {formatLabel(s.format, s.options)} ·{' '}
          {seriesSummary(s.format, { ...s.options, playoff_size: s.options.playoff_size ?? 0 })}
        </p>
        <p className="muted small">
          {s.ruleset_name} rules{limits ? ` (${limits})` : ''}{s.rules.fearless ? ' · Fearless' : ''} ·{' '}
          {s.rules.hide_player_data ? 'player data hidden between managers' : 'player data visible'} ·{' '}
          CPU teams {CPU_STRENGTH_LABELS[s.options.cpu_strength].split(':')[0].toLowerCase()} ·{' '}
          {deadlineLabel(s.options.round_deadline_hours ?? 0).toLowerCase()} per round
        </p>
        <p className="small">{s.managers} manager{s.managers === 1 ? '' : 's'} in, {s.open_slots} slot{s.open_slots === 1 ? '' : 's'} open.</p>
      </div>

      <div className="card stack">
        <h3>{s.roster_mode === 'DRAFT' ? 'Your team' : 'Bring your team'}</h3>
        {!s.can_join ? (
          <p className="muted">
            {s.status !== 'SETUP' ? 'This season has already started, so it can no longer be joined.' : 'Every manager slot in this season is taken.'}
          </p>
        ) : s.roster_mode === 'DRAFT' ? (
          <DraftTeamForm onSubmit={(body) => join.mutate(body)} pending={join.isPending} error={join.error} label="Join the season" />
        ) : (
          <>
            <p className="muted small">
              Choose one of your complete teams (or a default team). It must meet the season's team restrictions. A frozen
              copy plays the season, so editing your team later won't change it.
            </p>
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
            <ErrorNotice error={join.error} />
            <button className="primary" onClick={() => teamId && join.mutate({ team_id: teamId })} disabled={!teamId || join.isPending}>Join the season</button>
          </>
        )}
      </div>
      <Link to="/seasons">← All seasons</Link>
    </div>
  )
}
