import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import type { CpuStrength, Season, SeasonFormat, SeasonOptions, SeriesFormat } from '../../api/types'
import { ErrorNotice } from '../../components/common'
import DraftOptionsForm, { ANYTHING_GOES, draftSettingsPayload, type DraftOptions } from '../../components/DraftOptionsForm'
import { refreshSeason } from '../../hooks/useSeasons'
import {
  CPU_STRENGTH_LABELS, formatLabel, matchesPerTeam, playoffChoices, roundRobinRounds, SWISS_TEAM_COUNTS, swissWins,
} from '../../lib/season'

const TEAM_COUNTS = Array.from({ length: 13 }, (_, i) => i + 4)     // 4 to 16

const DEFAULT_OPTIONS: SeasonOptions = {
  team_count: 8, human_slots: 1, rr_double: false, regular_series: 'BO1', cpu_strength: 'EVEN',
  playoff_size: 4, playoff_series: 'BO3', final_series: 'BO5',
}

function SeriesSelect({ label, value, onChange }: { label: string; value: SeriesFormat; onChange: (v: SeriesFormat) => void }) {
  return (
    <label>
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value as SeriesFormat)}>
        <option value="BO1">Best of 1</option>
        <option value="BO3">Best of 3</option>
        <option value="BO5">Best of 5</option>
      </select>
    </label>
  )
}

export default function SeasonCreatePage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [format, setFormatState] = useState<SeasonFormat>('ROUND_ROBIN')
  const [options, setOptions] = useState<SeasonOptions>(DEFAULT_OPTIONS)
  // a season of many matches defaults to no draft timers, like single player
  const [rules, setRules] = useState<DraftOptions>({ ...ANYTHING_GOES, timers_enabled: false })
  const set = (patch: Partial<SeasonOptions>) => setOptions({ ...options, ...patch })

  const swiss = format === 'SWISS'
  const rounds = roundRobinRounds(options.team_count, options.rr_double)
  const perTeam = matchesPerTeam(options.team_count, options.rr_double)
  const teamCounts = swiss ? [...SWISS_TEAM_COUNTS] : TEAM_COUNTS
  // a Swiss stage always ends in a bracket of the half that qualifies
  const playoffSize = swiss ? options.team_count / 2 : options.playoff_size

  function setFormat(next: SeasonFormat) {
    setFormatState(next)
    if (next === 'SWISS' && !(SWISS_TEAM_COUNTS as readonly number[]).includes(options.team_count)) {
      set({ team_count: options.team_count > 8 ? 16 : 8 })
    }
  }

  function setTeamCount(n: number) {
    // keep the playoffs no bigger than the league
    set({ team_count: n, playoff_size: Math.min(options.playoff_size, Math.max(0, ...playoffChoices(n))) })
  }

  const create = useMutation({
    mutationFn: () => api<Season>('/seasons', {
      body: {
        name: name.trim(),
        roster_mode: 'BYO',
        format,
        // fearless is kept even though the rules' own series format is unused: it applies to BO3 / BO5 fixtures
        rules: { ...draftSettingsPayload(rules, true), series_format: 'BO1', fearless: rules.fearless },
        options: { ...options, playoff_size: swiss ? 0 : options.playoff_size, rr_double: !swiss && options.rr_double },
      },
    }),
    onSuccess: (season) => {
      refreshSeason(qc, season)
      navigate(`/seasons/${season.id}`)
    },
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    create.mutate()
  }

  return (
    <form className="stack" onSubmit={submit}>
      <div className="row between wrap">
        <h2>Create a season</h2>
        <Link to="/seasons">← All seasons</Link>
      </div>

      <div className="card stack">
        <h3>1. The league</h3>
        <label>
          Season name
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} placeholder="Spring Split" required />
        </label>
        <label>
          Teams
          <select value={options.team_count} onChange={(e) => setTeamCount(Number(e.target.value))}>
            {teamCounts.map((n) => <option key={n} value={n}>{n} teams</option>)}
          </select>
        </label>
        <p className="muted small">
          You manage one team; the CPU generates and runs the other {options.team_count - 1}. Inviting friends to manage teams
          is coming with multiplayer seasons.
        </p>
      </div>

      <div className="card stack">
        <h3>2. Format</h3>
        <label>
          Competition
          <select value={format} onChange={(e) => setFormat(e.target.value as SeasonFormat)}>
            <option value="ROUND_ROBIN">Round robin league (LCS / LEC style)</option>
            <option value="SWISS">Swiss stage into a bracket (Worlds style)</option>
          </select>
        </label>
        {swiss ? (
          <p className="muted small">
            Every round, teams play someone with the same record. {swissWins(options.team_count)} wins qualifies and{' '}
            {swissWins(options.team_count)} losses knocks a team out, so the stage takes up to {swissWins(options.team_count) * 2 - 1}{' '}
            rounds. The {playoffSize} qualifiers are seeded into a single-elimination bracket by record.
          </p>
        ) : (
          <>
            <label className="check">
              <input type="checkbox" checked={options.rr_double} onChange={(e) => set({ rr_double: e.target.checked })} />
              Double round robin (every team plays every other team twice, home and away)
            </label>
            <label>
              Playoffs
              <select value={options.playoff_size} onChange={(e) => set({ playoff_size: Number(e.target.value) })}>
                <option value={0}>None: the top of the table is champion</option>
                {playoffChoices(options.team_count).map((n) => (
                  <option key={n} value={n}>{n === 2 ? 'Top 2 play a final' : `Top ${n} into a bracket`}</option>
                ))}
              </select>
            </label>
            <p className="muted small">
              {rounds} rounds · {perTeam} matches per team. Ties in the table go to head-to-head, then game difference.
            </p>
          </>
        )}
        <SeriesSelect label={swiss ? 'Swiss match length' : 'League match length'} value={options.regular_series}
          onChange={(v) => set({ regular_series: v })} />
        {playoffSize > 2 && (
          <SeriesSelect label="Playoff match length" value={options.playoff_series} onChange={(v) => set({ playoff_series: v })} />
        )}
        {playoffSize >= 2 && (
          <SeriesSelect label="Final length" value={options.final_series} onChange={(v) => set({ final_series: v })} />
        )}
        <p className="muted small">{formatLabel(format, { playoff_size: playoffSize, rr_double: !swiss && options.rr_double })}</p>
      </div>

      <div className="card stack">
        <h3>3. Match rules</h3>
        <p className="muted small">The same options as a lobby. Your team must meet the team restrictions to enter.</p>
        <DraftOptionsForm value={rules} onChange={setRules} single={false} seriesElsewhere />
      </div>

      <div className="card stack">
        <h3>4. Teams</h3>
        <label>
          Rosters
          <select value="BYO" disabled>
            <option value="BYO">Bring Your Own: enter one of your teams</option>
          </select>
        </label>
        <p className="muted small">
          A frozen copy of your team plays the season, so editing it later won't change the season. A Player Draft mode
          (draft your roster from a pool) is coming soon.
        </p>
        <label>
          CPU team strength
          <select value={options.cpu_strength} onChange={(e) => set({ cpu_strength: e.target.value as CpuStrength })}>
            {(Object.keys(CPU_STRENGTH_LABELS) as CpuStrength[]).map((k) => (
              <option key={k} value={k}>{CPU_STRENGTH_LABELS[k]}</option>
            ))}
          </select>
        </label>
      </div>

      <ErrorNotice error={create.error} />
      <button className="primary" disabled={create.isPending || !name.trim()}>Create season</button>
    </form>
  )
}
