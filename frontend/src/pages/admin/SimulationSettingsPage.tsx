import { useEffect, useState } from 'react'
import type { SimulationSettingField } from '../../api/types'
import { ErrorNotice, Loading } from '../../components/common'
import { useResetSimulationSettings, useSaveSimulationSettings, useSimulationSettings } from '../../hooks/useAdmin'
import { formatSetting, groupFields, parseSetting, shown, toValues, type Drafts } from '../../lib/simSettings'

const NOT_EDITABLE_YET = [
  'Comfort modifiers by champion pool position',
  'Lane phase: roll range, score scale, matchup multipliers and assists',
  'Economy: gold per CS, kills, assists, towers and bounties',
  'Game phases and overtime: minutes, fights and objective limits',
  'Objectives: dragons, soul, elder and baron',
  'Structures and sieges',
  'Fights: damage, sturdiness and control weights',
  'Team style bonuses and coach effects',
]

function SettingRow({ field, value, onChange }: { field: SimulationSettingField; value: string | boolean; onChange: (value: string | boolean) => void }) {
  const id = `sim-${field.path.replace(/\./g, '-')}`
  const parsed = parseSetting(field, value)
  const changed = parsed !== undefined && parsed !== field.default
  return (
    <div className="sim-setting">
      <div className="sim-setting-text">
        <label htmlFor={id}>{field.label}{changed && <span className="sim-changed" title="Differs from the default"> • changed</span>}</label>
        <p className="muted small">{field.help} Default: {formatSetting(field.default)}.</p>
      </div>
      {field.kind === 'bool' ? (
        <input id={id} type="checkbox" checked={value === true} onChange={(e) => onChange(e.target.checked)} />
      ) : (
        <input
          id={id}
          className="sim-number"
          type="number"
          inputMode="decimal"
          min={field.min}
          max={field.max}
          step={field.step}
          value={value as string}
          aria-invalid={parsed === undefined}
          title={`${field.min} to ${field.max}`}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  )
}

export default function SimulationSettingsPage() {
  const settings = useSimulationSettings()
  const save = useSaveSimulationSettings()
  const reset = useResetSimulationSettings()
  const [drafts, setDrafts] = useState<Drafts>(new Map())

  const fields = settings.data?.fields ?? []
  const { values, invalid } = toValues(fields, drafts)
  const changes = Object.keys(values).length
  const dirty = changes > 0 || invalid.length > 0
  const busy = save.isPending || reset.isPending

  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const edit = (path: string, value: string | boolean) => setDrafts((d) => new Map(d).set(path, value))
  const clear = () => setDrafts(new Map())

  if (settings.isLoading) return <Loading />
  if (settings.error) return <ErrorNotice error={settings.error} />

  return (
    <div className="stack">
      <h1>Simulation Settings</h1>
      <p className="muted">How strongly champion win rates and damage type balance affect a match. Changes apply to matches simulated after saving.</p>
      <div className="row between wrap">
        <span className="muted small" aria-live="polite">
          {invalid.length ? `${invalid.length} ${invalid.length === 1 ? 'value is' : 'values are'} out of range` : dirty ? `${changes} unsaved ${changes === 1 ? 'change' : 'changes'}` : settings.data?.updated_at ? `Last saved ${new Date(settings.data.updated_at).toLocaleString()}` : 'All settings are at their defaults'}
        </span>
        <div className="row wrap">
          <button className="primary" disabled={!changes || invalid.length > 0 || busy} onClick={() => save.mutate(values, { onSuccess: clear })}>
            {save.isPending ? 'Saving…' : 'Save changes'}
          </button>
          <button className="ghost" disabled={!dirty || busy} onClick={clear}>Discard</button>
          <button
            className="ghost"
            disabled={busy}
            onClick={() => window.confirm('Put every setting on this page back to its default?') && reset.mutate(undefined, { onSuccess: clear })}
          >
            {reset.isPending ? 'Resetting…' : 'Reset to defaults'}
          </button>
        </div>
      </div>
      {(save.error || reset.error) && <ErrorNotice error={save.error ?? reset.error} />}
      {groupFields(fields).map(([group, list]) => (
        <section key={group} className="card stack">
          <h2>{group}</h2>
          {list.map((field) => (
            <SettingRow key={field.path} field={field} value={shown(field, drafts)} onChange={(v) => edit(field.path, v)} />
          ))}
        </section>
      ))}
      <div className="card stack">
        <div className="notice notice-warn">The rest of the simulation cannot be edited here yet. It is set in <code>backend/app/game/config.py</code>.</div>
        <ul className="admin-planned">
          {NOT_EDITABLE_YET.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </div>
    </div>
  )
}
