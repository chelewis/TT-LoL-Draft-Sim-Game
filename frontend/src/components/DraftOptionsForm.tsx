import type { Ruleset, RulesetSettings, SeriesFormat } from '../api/types'
import { useRulesets } from '../hooks/useData'
import { RANK_TIERS, titleCase } from '../lib/format'

export type DraftOptions = RulesetSettings & { ruleset: string }

/** Anything Goes, used until the ruleset list loads (the server has the same preset). */
export const ANYTHING_GOES: DraftOptions = {
  ruleset: 'ANYTHING_GOES', hide_player_data: false, bans_enabled: true, timers_enabled: true, pick_seconds: 30,
  ban_seconds: 30, series_format: 'BO1', fearless: false, max_rank: null, max_player_total: null, max_team_total: null,
  duplicate_clause: false, mirror_clause: false,
}

const clampTo = (lo: number, hi: number, fallback: number) => (n: number) => Math.max(lo, Math.min(hi, Math.round(n) || fallback))
const clamp = clampTo(5, 600, 30)
const clampPlayerTotal = clampTo(5, 50, 32)
const clampTeamTotal = clampTo(25, 250, 160)

/** The options as the server takes them (numbers clamped to their allowed ranges). `allowHidden`: false where
 * hidden player data makes no sense (single player). */
export function draftSettingsPayload(o: DraftOptions, allowHidden: boolean) {
  return {
    ruleset: o.ruleset,
    hide_player_data: allowHidden && o.hide_player_data,
    bans_enabled: o.bans_enabled,
    timers_enabled: o.timers_enabled,
    pick_seconds: clamp(o.pick_seconds),
    ban_seconds: clamp(o.ban_seconds),
    series_format: o.series_format,
    fearless: o.series_format !== 'BO1' && o.fearless,
    max_rank: o.max_rank,
    max_player_total: o.max_player_total === null ? null : clampPlayerTotal(o.max_player_total),
    max_team_total: o.max_team_total === null ? null : clampTeamTotal(o.max_team_total),
    duplicate_clause: o.duplicate_clause,
    mirror_clause: o.mirror_clause,
  }
}

/** Whether the options differ from their ruleset's preset. Single player ignores hidden data (it's always shown);
 * `ignore` lists other options the caller sets elsewhere. */
function isModified(value: DraftOptions, rulesets: Ruleset[], single: boolean, ignore: (keyof RulesetSettings)[]): boolean {
  const preset = rulesets.find((r) => r.key === value.ruleset)?.settings
  if (!preset) return false
  return (Object.keys(preset) as (keyof RulesetSettings)[]).some(
    (k) => !(single && k === 'hide_player_data') && !ignore.includes(k) && preset[k] !== value[k],
  )
}

/** A stat total cap: a "limit" checkbox and the number (null means no limit). */
function CapField({ label, value, fallback, min, max, onChange }: {
  label: string
  value: number | null
  fallback: number
  min: number
  max: number
  onChange: (v: number | null) => void
}) {
  return (
    <div className="stack">
      <label className="check">
        <input type="checkbox" checked={value !== null} onChange={(e) => onChange(e.target.checked ? fallback : null)} />
        {label}
      </label>
      {value !== null && (
        <input type="number" aria-label={label} min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      )}
    </div>
  )
}

/** Ruleset, series format, ban phases, pick/ban timers and team restrictions: the same options in every mode.
 * Choosing a ruleset fills in every option; the creator can still change any of them afterwards.
 * `seriesElsewhere`: the series length is chosen somewhere else (a season sets it per stage), so the Format
 * picker is hidden and Fearless applies to whichever matches are best of 3 or 5. */
export default function DraftOptionsForm({ value, onChange, single, seriesElsewhere = false }: {
  value: DraftOptions
  onChange: (v: DraftOptions) => void
  single: boolean
  seriesElsewhere?: boolean
}) {
  const rulesets = useRulesets()
  const list = rulesets.data?.rulesets ?? []
  const current = list.find((r) => r.key === value.ruleset)
  const modified = isModified(value, list, single, seriesElsewhere ? ['series_format'] : [])
  const set = (patch: Partial<DraftOptions>) => onChange({ ...value, ...patch })
  const apply = (key: string) => {
    const preset = list.find((r) => r.key === key)
    if (preset) onChange({ ruleset: key, ...preset.settings })
  }
  const choices = list.length ? list.map((r) => ({ key: r.key, name: r.name })) : [{ key: ANYTHING_GOES.ruleset, name: 'Anything Goes' }]
  const noSeries = !seriesElsewhere && value.series_format === 'BO1'
  return (
    <>
      <label>
        Ruleset
        <select value={value.ruleset} onChange={(e) => apply(e.target.value)} disabled={!list.length}>
          {choices.map((r) => (
            <option key={r.key} value={r.key}>{r.name}</option>
          ))}
        </select>
      </label>
      {current && (
        <p className="muted small">
          {current.description}
          {modified && (
            <>
              {' '}<span className="badge">Modified</span>{' '}
              <button type="button" className="ghost small" onClick={() => apply(value.ruleset)}>Reset to {current.name}</button>
            </>
          )}
        </p>
      )}
      {!single && (
        <label className="check">
          <input type="checkbox" checked={value.hide_player_data} onChange={(e) => set({ hide_player_data: e.target.checked })} />
          Hide player data (opponent stats and champion pools stay secret until the match ends)
        </label>
      )}
      {!seriesElsewhere && (
        <label>
          Format
          <select value={value.series_format} onChange={(e) => set({ series_format: e.target.value as SeriesFormat })}>
            <option value="BO1">Best of 1</option>
            <option value="BO3">Best of 3</option>
            <option value="BO5">Best of 5</option>
          </select>
        </label>
      )}
      <label className="check" title={noSeries ? 'Fearless Draft needs a Best of 3 or Best of 5' : undefined}>
        <input
          type="checkbox"
          checked={value.fearless && !noSeries}
          disabled={noSeries}
          onChange={(e) => set({ fearless: e.target.checked })}
        />
        Fearless Draft (champions picked in a game can't be picked or banned again in the series
        {seriesElsewhere ? '; only affects best of 3 and best of 5 matches)' : ')'}
      </label>
      <label className="check">
        <input type="checkbox" checked={!value.bans_enabled} onChange={(e) => set({ bans_enabled: !e.target.checked })} />
        Disable ban phases (pick only)
      </label>
      <label className="check">
        <input type="checkbox" checked={value.timers_enabled} onChange={(e) => set({ timers_enabled: e.target.checked })} />
        Enable pick/ban timers
      </label>
      {value.timers_enabled && (
        <div className="grid two">
          <label>
            Pick time limit (seconds)
            <input type="number" min={5} max={600} value={value.pick_seconds} onChange={(e) => set({ pick_seconds: Number(e.target.value) })} />
          </label>
          {value.bans_enabled && (
            <label>
              Ban time limit (seconds)
              <input type="number" min={5} max={600} value={value.ban_seconds} onChange={(e) => set({ ban_seconds: Number(e.target.value) })} />
            </label>
          )}
        </div>
      )}
      <h3>Team restrictions</h3>
      <label>
        Max rank
        <select value={value.max_rank ?? ''} onChange={(e) => set({ max_rank: e.target.value || null })}>
          <option value="">No limit</option>
          {(rulesets.data?.rank_tiers ?? RANK_TIERS).map((tier) => (
            <option key={tier} value={tier}>{titleCase(tier)} and below</option>
          ))}
        </select>
      </label>
      {value.max_rank && <p className="muted small">A rank limit only allows players imported from a ranked Riot account.</p>}
      <div className="grid two">
        <CapField label="Limit each player's stat total" value={value.max_player_total} fallback={32} min={5} max={50}
          onChange={(v) => set({ max_player_total: v })} />
        <CapField label="Limit the team's stat total" value={value.max_team_total} fallback={160} min={25} max={250}
          onChange={(v) => set({ max_team_total: v })} />
      </div>
      <label className="check">
        <input type="checkbox" checked={value.duplicate_clause} onChange={(e) => set({ duplicate_clause: e.target.checked })} />
        Duplicate clause (a team can't roster the same Riot account twice; hand-made players are matched by name)
      </label>
      <label className="check">
        <input type="checkbox" checked={value.mirror_clause} onChange={(e) => set({ mirror_clause: e.target.checked })} />
        No mirror players (the same player can't be on both teams)
      </label>
    </>
  )
}
