import { useMutation, useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Lane, RiotMetric, RiotPreview } from '../api/types'
import { ErrorNotice, Loading } from '../components/common'
import { TagChip } from '../components/TagChips'
import Tooltip from '../components/Tooltip'
import { useChampionMap } from '../hooks/useData'
import { LANE_LABEL, formatMetric, rankLabel, riotSourceLabel } from '../lib/format'
import { MAX_TAGS, sortTags } from '../lib/playstyle'

export const useRiotStatus = () =>
  useQuery({ queryKey: ['riot-status'], queryFn: () => api<{ enabled: boolean; regions: string[] }>('/riot/status'), staleTime: 60000 })

const STAT_LABELS: [keyof RiotPreview['player'], string][] = [
  ['aggr', 'Aggression'], ['aware', 'Awareness'], ['pos', 'Positioning'], ['dmg', 'Damage'], ['cs', 'Farming (CS)'],
]

function RawExplanation({ label, lane, rows, raw }: { label: string; lane: Lane; rows: RiotMetric[]; raw: number }) {
  return (
    <div className="tip-content">
      <strong>{label}: raw {raw}</strong>
      <p>The average of {rows.length === 1 ? 'one score' : `${rows.length} scores`}, each from a real measurement across their games, scaled 1&ndash;10 against typical {LANE_LABEL[lane]} players.</p>
      <ul>
        {rows.map((r) => (
          <li key={r.metric}>
            <strong>{r.label}</strong> <span className="muted">({r.how})</span>
            <br />
            Their average <b>{formatMetric(r.value, r.unit)}</b> &rarr; {formatMetric(r.low, r.unit)} {r.lower_is_better ? 'scores 10, ' : 'scores 1, '}
            {formatMetric(r.high, r.unit)} {r.lower_is_better ? 'scores 1' : 'scores 10'} &rarr; <b>{r.score}</b>
          </li>
        ))}
      </ul>
      <p className="formula">
        score = 1 + 9 &times; (value &minus; low) &divide; (high &minus; low), kept between 1 and 10{rows.some((r) => r.lower_is_better) ? ' (flipped when lower is better)' : ''}
      </p>
      <p className="formula">raw = ({rows.map((r) => r.score).join(' + ')}) &divide; {rows.length} = {raw}</p>
    </div>
  )
}

function FinalExplanation({ label, raw, final, rank, fit }: {
  label: string; raw: number; final: number; rank: RiotPreview['analysis']['rank']; fit: RiotPreview['analysis']['fit']
}) {
  const fitted = fit.total_before > fit.budget
  const whose = rank.tier ? `for ${rankLabel(rank)}` : 'for unranked players'
  return (
    <div className="tip-content">
      <strong>{label}: {final}</strong>
      <p>Rounded raw value: {Math.max(1, Math.min(10, Math.round(raw)))}.</p>
      <p>The stat ceiling{fit.floor > 0 ? ' and floor depend' : ' depends'} on rank: {fit.floor > 0 ? `${fit.budget} and ${fit.floor}` : fit.budget} {whose}.</p>
      {fit.total_before < fit.floor ? (
        <>
          <p>All five rounded stats total <b>{fit.total_before}</b>, below the floor of <b>{fit.floor}</b>, so every stat is scaled up together until they total {fit.floor}:</p>
          <p className="formula">final &asymp; rounded &times; {fit.floor} &divide; {fit.total_before} &asymp; {final} (at most 10)</p>
        </>
      ) : fitted ? (
        <>
          <p>All five rounded stats total <b>{fit.total_before}</b>, above the soft ceiling of <b>{fit.budget}</b>, so every stat is scaled down together:</p>
          <p className="formula">final = round(rounded &times; {fit.budget} &divide; {fit.total_before}) &asymp; {final}</p>
          <p>Teams with players above the ceiling are flagged as potentially illegal. You can raise a stat in the editor.</p>
        </>
      ) : (
        <p>The five stats total {fit.total_before}, within the ceiling of {fit.budget}{fit.floor > 0 ? ` and at or above the floor of ${fit.floor}` : ''}, so nothing was scaled.</p>
      )}
    </div>
  )
}

export default function RiotImportPage() {
  const navigate = useNavigate()
  const status = useRiotStatus()
  const champions = useChampionMap()
  const [riotId, setRiotId] = useState('')
  const [region, setRegion] = useState('NA1')
  const [role, setRole] = useState('')
  const [preview, setPreview] = useState<RiotPreview | null>(null)

  const fetchPreview = useMutation({
    mutationFn: () => api<RiotPreview>('/riot/preview', { body: { riot_id: riotId.trim(), region, role: role || null } }),
    onSuccess: setPreview,
  })
  const submit = (e: FormEvent) => { e.preventDefault(); setPreview(null); fetchPreview.mutate() }

  if (status.isLoading) return <Loading />
  if (!status.data?.enabled) {
    return (
      <div className="card stack">
        <h1>Import from Riot</h1>
        <p className="muted">Riot import is not set up on this server. The host needs to set a Riot API key (<code>LDM_RIOT_API_KEY</code>).</p>
        <Link to="/players">← Back to players</Link>
      </div>
    )
  }

  const p = preview?.player
  return (
    <div className="stack">
      <h1>Import a player from Riot</h1>
      <form className="card stack" onSubmit={submit}>
        <p className="muted">
          Enter a Riot ID. We read that account's public ranked solo games and rank, and turn their performance into a player.
          A higher rank allows a higher stat total and guarantees a higher minimum.
          You can edit everything before saving. Imports are unverified: anyone can import any public Riot ID.
        </p>
        <div className="grid two">
          <label>Riot ID<input value={riotId} onChange={(e) => setRiotId(e.target.value)} placeholder="GameName#TAG" required /></label>
          <label>Region
            <select value={region} onChange={(e) => setRegion(e.target.value)}>
              {(status.data.regions).map((r) => <option key={r}>{r}</option>)}
            </select>
          </label>
          <label>Role (optional)
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="">Detect from their games</option>
              {(Object.keys(LANE_LABEL) as (keyof typeof LANE_LABEL)[]).map((l) => <option key={l} value={l}>{LANE_LABEL[l]}</option>)}
            </select>
          </label>
        </div>
        <ErrorNotice error={fetchPreview.error} />
        <button className="primary" disabled={fetchPreview.isPending}>{fetchPreview.isPending ? 'Reading their games… (this can take a few seconds)' : 'Look up'}</button>
      </form>

      {preview && p && (
        <div className="card stack">
          <div className="row between wrap">
            <h2>{preview.riot.game_name}<span className="muted">#{preview.riot.tag_line}</span></h2>
            <span className="badge">{LANE_LABEL[p.role]} · {preview.analysis.games} ranked games</span>
          </div>
          <p className="small">
            <span className="badge" title={preview.analysis.rank.tier ? `${riotSourceLabel(preview.analysis.rank.queue)} rank` : 'No rank found for this account'}>{rankLabel(preview.analysis.rank, true)}</span>
            {preview.analysis.rank.tier && <span className="muted"> {preview.analysis.rank.wins}W {preview.analysis.rank.losses}L</span>}
            <span className="muted"> · stat ceiling {preview.analysis.rank.budget}{preview.analysis.rank.floor > 0 ? `, floor ${preview.analysis.rank.floor}` : ''}</span>
          </p>
          {preview.analysis.source.is_solo ? (
            <p className="muted small">Source: {preview.analysis.source.label} · {preview.analysis.source.games} games</p>
          ) : (
            <div className="notice notice-warn source-banner" role="alert">
              <strong>⚠ Stats from {riotSourceLabel(preview.analysis.source.queue)}, not solo queue</strong>
              <span> · {preview.analysis.source.games} games</span>
            </div>
          )}
          <p className="muted small">Hover (or tap) a number to see how it was calculated.</p>
          <div className="grid stats-inputs">
            {STAT_LABELS.map(([key, label]) => (
              <div key={key}>
                <span className="muted small">{label}</span>
                <div className="row">
                  <Tooltip label={`How the final ${label} stat is calculated`}
                    content={<FinalExplanation label={label} raw={preview.analysis.raw_stats[key as string]} final={p[key] as number} rank={preview.analysis.rank} fit={preview.analysis.fit} />}>
                    <strong className="has-tip">{p[key] as number}</strong>
                  </Tooltip>
                  <Tooltip label={`How the raw ${label} number is calculated`}
                    content={<RawExplanation label={label} lane={p.role} rows={preview.analysis.breakdown[key as string] ?? []} raw={preview.analysis.raw_stats[key as string]} />}>
                    <span className="muted small has-tip">(raw {preview.analysis.raw_stats[key as string]})</span>
                  </Tooltip>
                </div>
              </div>
            ))}
          </div>
          <div>
            <p className="muted small">Champion pool (best first)</p>
            <div className="row wrap">
              {p.pool.map((id, i) => <span key={id} className="chip">{i + 1}. {champions.get(id)?.name ?? id}</span>)}
              {Array.from({ length: preview.analysis.missing_pool_slots }, (_, i) => <span key={`m${i}`} className="chip muted">choose in editor</span>)}
            </div>
          </div>
          {preview.analysis.tags && (
            <div>
              <p className="muted small">Playstyle tags (up to {MAX_TAGS}; ▲ strengths from Riot challenges, ▼ weaknesses from these games)</p>
              {preview.analysis.tags.earned.length === 0 ? (
                <p className="muted small">No playstyle tags earned.</p>
              ) : (
                <div className="tag-list">
                  {sortTags(preview.analysis.tags.earned).map((t) => <TagChip key={t.key} tag={t} />)}
                </div>
              )}
              {preview.analysis.tags.earned.length > 0 && (
                <p className="muted small">
                  Starting with: {(p.tags ?? []).map((k) => preview.analysis.tags!.earned.find((t) => t.key === k)?.label ?? k).join(', ') || 'none'}.
                  Choose which to keep in the editor.
                </p>
              )}
            </div>
          )}
          {preview.analysis.notes.map((n) => <div key={n} className="notice notice-warn">{n}</div>)}
          <div className="row wrap">
            <button className="primary" onClick={() => navigate('/players/new', { state: { draft: preview } })}>Open in editor</button>
            <Link className="button ghost" to="/players">Cancel</Link>
          </div>
        </div>
      )}
    </div>
  )
}
