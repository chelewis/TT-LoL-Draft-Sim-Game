import type { AdminChampion, AdminChampionColumn, AdminChampionField } from '../api/types'

/** The editable columns in table order: short header, full name and what the value means. */
export const CHAMPION_COLUMNS: { key: AdminChampionColumn; short: string; label: string; help: string }[] = [
  { key: 'win_rate', short: 'WR %', label: 'Win rate', help: 'Base win rate, in percent' },
  { key: 'pick_rate', short: 'PR %', label: 'Pick rate', help: 'How often it is picked, in percent. Weights the Meta view and CPU drafts' },
  { key: 'difficulty', short: 'Diff', label: 'Difficulty', help: '1 easy to 3 hard' },
  { key: 'style', short: 'Style', label: 'Style', help: '1 to 10' },
  { key: 'damage_type', short: 'Type', label: 'Damage type', help: 'P physical, M magic, PM mixed' },
  { key: 'damage', short: 'Dmg', label: 'Damage', help: '0 to 5, usually 1 to 3' },
  { key: 'sturdiness', short: 'Tank', label: 'Sturdiness', help: '0 to 5, usually 1 to 3' },
  { key: 'crowd_control', short: 'CC', label: 'Crowd control', help: '0 to 5, usually 1 to 3' },
  { key: 'mobility', short: 'Mob', label: 'Mobility', help: '0 to 5, usually 1 to 3' },
  { key: 'utility', short: 'Util', label: 'Utility', help: '0 to 5, usually 1 to 3' },
  { key: 'scaling', short: 'Scale', label: 'Scaling', help: '1 early game, 2 neutral, 3 late game' },
  { key: 'attack_range', short: 'Range', label: 'Range', help: '1 melee, 2 short, 3 long' },
  { key: 'waveclear', short: 'Wave', label: 'Waveclear', help: '1 weak, 2 average, 3 strong' },
]

/** Unsaved edits as typed, keyed by `${championId}:${column}`. */
export type ChampionDrafts = Map<string, string>
export interface ChampionChange { id: number; values: Partial<Record<AdminChampionColumn, number | string>> }

export const draftKey = (id: number, column: AdminChampionColumn) => `${id}:${column}`

export const formatValue = (value: number | string) => (typeof value === 'number' ? String(value) : value)

/** The typed text as a value the backend accepts, or undefined when it is not one. */
export function parseValue(field: AdminChampionField, text: string): number | string | undefined {
  const trimmed = text.trim()
  if (field.kind === 'choice') return field.choices.includes(trimmed) ? trimmed : undefined
  if (trimmed === '') return undefined
  const value = Number(trimmed)
  if (!Number.isFinite(value) || value < field.min || value > field.max) return undefined
  if (field.kind === 'int' && !Number.isInteger(value)) return undefined
  return field.kind === 'float' ? Math.round(value * 100) / 100 : value
}

export function shownValue(champion: AdminChampion, column: AdminChampionColumn, drafts: ChampionDrafts): string {
  return drafts.get(draftKey(champion.id, column)) ?? formatValue(champion[column])
}

/** Turn drafts into a save request: only values that differ from the saved ones. `invalid` lists the bad cells. */
export function toChanges(
  champions: AdminChampion[],
  fields: Record<AdminChampionColumn, AdminChampionField>,
  drafts: ChampionDrafts,
): { changes: ChampionChange[]; count: number; invalid: string[] } {
  const changes: ChampionChange[] = []
  const invalid: string[] = []
  let count = 0
  for (const champion of champions) {
    const values: ChampionChange['values'] = {}
    for (const { key, label } of CHAMPION_COLUMNS) {
      const text = drafts.get(draftKey(champion.id, key))
      if (text === undefined) continue
      const value = parseValue(fields[key], text)
      if (value === undefined) invalid.push(`${champion.name} ${label}`)
      else if (value !== champion[key]) values[key] = value
    }
    const n = Object.keys(values).length
    if (n) {
      changes.push({ id: champion.id, values })
      count += n
    }
  }
  return { changes, count, invalid }
}

export type ChampionSortBy = 'name' | 'class' | AdminChampionColumn
export interface ChampionSort { by: ChampionSortBy; desc: boolean }

export function filterAndSort(champions: AdminChampion[], query: string, editedOnly: boolean, sort: ChampionSort): AdminChampion[] {
  const q = query.trim().toLowerCase()
  const rows = champions.filter((c) =>
    (!q || c.name.toLowerCase().includes(q) || c.class.toLowerCase().includes(q)) && (!editedOnly || c.edited.length > 0))
  const dir = sort.desc ? -1 : 1
  return rows.sort((a, b) => {
    const x = a[sort.by]
    const y = b[sort.by]
    const order = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))
    return order * dir || a.name.localeCompare(b.name)
  })
}
