/**
 * Where the backend lives. Set VITE_API_URL (e.g. http://localhost:8003) in frontend/.env;
 * leave it empty to use the page's own origin (backend serving the built frontend).
 */
const ORIGIN = (import.meta.env.VITE_API_URL ?? '').trim().replace(/\/+$/, '')

export const API_BASE = `${ORIGIN}/api/v1`

/** WebSocket URL for a path such as `/ws/games/1`, on the same host as the API. */
export function wsUrl(path: string): string {
  const base = ORIGIN || window.location.origin
  return `${base.replace(/^http/, 'ws')}${path}`
}
