import type { SearchFilters } from '../api/types'

/** Filters -> "a=1&b=x&champions=3&champions=7". Empty strings, null, undefined and empty arrays are left out. */
export function searchQuery(filters: SearchFilters): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value === null || value === undefined || value === '') continue
    if (Array.isArray(value)) value.forEach((v) => params.append(key, String(v)))
    else params.set(key, String(value))
  }
  return params.toString()
}
