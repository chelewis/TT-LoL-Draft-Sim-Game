import type { Lane, MetaChampion } from '../api/types'

export interface ChampionFilters {
  query: string
  /** champions that usually play any of these lanes; empty = every champion */
  lanes: Lane[]
  /** empty = every class */
  champClass: string
}

export type ChampionSortBy = 'name' | 'win_rate' | 'pick_rate'

export interface ChampionSort {
  by: ChampionSortBy
  desc: boolean
}

export const NO_FILTERS: ChampionFilters = { query: '', lanes: [], champClass: '' }

export const hasFilters = (f: ChampionFilters): boolean => Boolean(f.query.trim() || f.lanes.length || f.champClass)

/** The rows matching every filter: name search (any case), any of the lanes, and the class. */
export function filterChampions(rows: MetaChampion[], f: ChampionFilters): MetaChampion[] {
  const q = f.query.trim().toLowerCase()
  return rows.filter((r) =>
    (!q || r.name.toLowerCase().includes(q)) &&
    (!f.lanes.length || r.roles.some((lane) => f.lanes.includes(lane))) &&
    (!f.champClass || r.class === f.champClass))
}

/** A sorted copy; ties go by name. */
export function sortChampions(rows: MetaChampion[], sort: ChampionSort): MetaChampion[] {
  return [...rows].sort((x, y) => {
    const order = sort.by === 'name' ? x.name.localeCompare(y.name) : x[sort.by] - y[sort.by]
    return (sort.desc ? -order : order) || x.name.localeCompare(y.name)
  })
}

/** The direction a column starts in when first clicked: names A→Z, rates highest first. */
export const startsDescending = (by: ChampionSortBy): boolean => by !== 'name'

/** Every class among the rows, A→Z, for the class filter. */
export const championClasses = (rows: MetaChampion[]): string[] => [...new Set(rows.map((r) => r.class))].sort()
