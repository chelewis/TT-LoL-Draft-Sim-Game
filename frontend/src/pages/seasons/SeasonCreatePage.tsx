import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import type { CpuStrength, RosterMode, Season, SeasonFormat, SeasonOptions, SeriesFormat } from '../../api/types'
import { ErrorNotice } from '../../components/common'
import DraftOptionsForm, { ANYTHING_GOES, draftSettingsPayload, type DraftOptions } from '../../components/DraftOptionsForm'
import { refreshSeason } from '../../hooks/useSeasons'
import {
  CPU_STRENGTH_LABELS, DEADLINE_CHOICES, deadlineLabel, formatLabel, matchesPerTeam, PICK_CLOCK_CHOICES, pickClockLabel,
  playoffChoices, roundRobinRounds, SWISS_TEAM_COUNTS, swissWins,
} from '../../lib/season'

const TEAM_COUNTS = Array.from({ length: 13 }, (_, i) => i + 4)     // 4 to 16

const DEFAULT_OPTIONS: SeasonOptions = {
  team_count: 8, human_slots: 1, rr_double: false, regular_series: 'BO1', cpu_strength: 'EVEN',
  playoff_size: 4, playoff_series: 'BO3', final_series: 'BO5', round_deadline_hours: 0,
  draft_pick_seconds: 0, max_signings: 3, free_agents_per_role: 2,
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
  const [rosterMode, setRosterMode] = useState<RosterMode>('BYO')
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
      const n = options.team_count > 8 ? 16 : 8
      set({ team_count: n, human_slots: Math.min(options.human_slots, n) })
    }
  }

  function setTeamCount(n: number) {
    // keep the playoffs no bigger than the league, and the managers no more than the teams
    set({ team_count: n, playoff_size: Math.min(options.playoff_size, Math.max(0, ...playoffChoices(n))),
      human_slots: Math.min(options.human_slots, n) })
  }

  const create = useMutation({
    mutationFn: () => api<Season>('/seasons', {
      body: {
        name: name.trim(),
        roster_mode: rosterMode,
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
        <label>
          Managers
          <select value={options.human_slots} onChange={(e) => set({ human_slots: Number(e.target.value) })}>
            {Array.from({ length: options.team_count }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>{n === 1 ? 'Just me (single player)' : `Up to ${n} managers`}</option>
            ))}
          </select>
        </label>
        <p className="muted small">
          {options.human_slots === 1
            ? `You manage one team; the CPU generates and runs the other ${options.team_count - 1}.`
            : `Friends join with the season's invite code and bring a team each. The CPU generates and runs every team nobody manages (at least ${options.team_count - options.human_slots}).`}
        </p>
        <label>
          Round deadline
          <select value={options.round_deadline_hours ?? 0} onChange={(e) => set({ round_deadline_hours: Number(e.target.value) })}>
            {DEADLINE_CHOICES.map((h) => <option key={h} value={h}>{deadlineLabel(h)}</option>)}
          </select>
        </label>
        <p className="muted small">
          {options.round_deadline_hours
            ? `Each round closes by itself ${deadlineLabel(options.round_deadline_hours)} after it opens, and the CPU plays any match managers haven't. You can still advance sooner.`
            : 'Rounds move on only when you advance them.'}
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
          <select value={rosterMode} onChange={(e) => setRosterMode(e.target.value as RosterMode)}>
            <option value="BYO">Bring Your Own: each manager enters one of their teams</option>
            <option value="DRAFT">Player Draft: managers draft their players from a pool</option>
          </select>
        </label>
        <p className="muted small">
          {rosterMode === 'DRAFT'
            ? "Managers enter a team name, playstyles and coach. You fill the pool (your own players or generated ones) before the start; then everyone snake-drafts five players."
            : "A frozen copy of each manager's team plays the season, so editing it later won't change the season."}
        </p>
        {rosterMode === 'DRAFT' && (
          <label>
            Pick clock
            <select value={options.draft_pick_seconds ?? 0} onChange={(e) => set({ draft_pick_seconds: Number(e.target.value) })}>
              {PICK_CLOCK_CHOICES.map((s) => <option key={s} value={s}>{pickClockLabel(s)}</option>)}
            </select>
          </label>
        )}
        <label>
          Free agency
          <select value={options.max_signings ?? 0} onChange={(e) => set({ max_signings: Number(e.target.value) })}>
            <option value={0}>Off</option>
            {[1, 2, 3, 5, 10].map((n) => <option key={n} value={n}>{n} signing{n === 1 ? '' : 's'} per team</option>)}
          </select>
        </label>
        {!!options.max_signings && (
          <label>
            Generated free agents
            <select value={options.free_agents_per_role ?? 0} onChange={(e) => set({ free_agents_per_role: Number(e.target.value) })}>
              {[0, 1, 2, 3, 5].map((n) => <option key={n} value={n}>{n ? `${n} per lane` : 'None'}{rosterMode === 'DRAFT' ? ' (plus the undrafted pool)' : ''}</option>)}
            </select>
          </label>
        )}
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
