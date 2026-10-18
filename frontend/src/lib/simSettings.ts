import type { SimulationSettingField } from '../api/types'

/** Unsaved edits on the Simulation Settings page, by setting path: the typed text for numbers, true/false for switches. */
export type Drafts = Map<string, string | boolean>

/** A draft as the value to save, or undefined when it is not valid for the field. */
export function parseSetting(field: SimulationSettingField, draft: string | boolean): number | boolean | undefined {
  if (field.kind === 'bool') return typeof draft === 'boolean' ? draft : undefined
  if (typeof draft !== 'string' || draft.trim() === '') return undefined
  const value = Number(draft.trim())
  if (!Number.isFinite(value) || value < field.min || value > field.max) return undefined
  return value
}

/** What the field shows: its draft if it has one, else the saved value. */
export function shown(field: SimulationSettingField, drafts: Drafts): string | boolean {
  const draft = drafts.get(field.path)
  if (draft !== undefined) return draft
  return field.kind === 'bool' ? Boolean(field.value) : String(field.value)
}

/** The drafts that differ from the saved values, ready to PUT, and the paths whose drafts are not valid. */
export function toValues(fields: SimulationSettingField[], drafts: Drafts): { values: Record<string, number | boolean>; invalid: string[] } {
  const values: Record<string, number | boolean> = {}
  const invalid: string[] = []
  for (const field of fields) {
    const draft = drafts.get(field.path)
    if (draft === undefined) continue
    const value = parseSetting(field, draft)
    if (value === undefined) invalid.push(field.path)
    else if (value !== field.value) values[field.path] = value
  }
  return { values, invalid }
}

/** Fields grouped under their headings, in the order the server lists them. */
export function groupFields(fields: SimulationSettingField[]): [string, SimulationSettingField[]][] {
  const groups = new Map<string, SimulationSettingField[]>()
  for (const field of fields) {
    const list = groups.get(field.group) ?? []
    list.push(field)
    groups.set(field.group, list)
  }
  return [...groups]
}

export function formatSetting(value: number | boolean): string {
  return typeof value === 'boolean' ? (value ? 'On' : 'Off') : String(value)
}
