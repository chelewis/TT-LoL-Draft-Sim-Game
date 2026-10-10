import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import type { Champion } from '../api/types'
import { ChampionIcon } from './ChampionArt'

export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null
  const message = error instanceof Error ? error.message : String(error)
  return (
    <div className="notice notice-error" role="alert">
      {message}
    </div>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <p className="muted">{label}</p>
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <Loading />
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  return <>{children}</>
}

/** Admin-only pages. The server refuses the data anyway; this just explains why the page is empty. */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  if (!user?.is_admin) return <div className="notice notice-error" role="alert">This page is for admins only.</div>
  return <>{children}</>
}

export function ChampionTag({ champion }: { champion: Champion | undefined }) {
  if (!champion) return <span className="muted">?</span>
  return (
    <span className="champ-tag" title={`${champion.class} · ${champion.strength} · win rate ${champion.win_rate}%`}>
      <ChampionIcon champion={champion} size={22} />
      {champion.name}
    </span>
  )
}

/** Small set of attribute pips (1-3) for a champion card. */
export function Pips({ value, max = 3 }: { value: number; max?: number }) {
  return (
    <span className="pips" aria-label={`${value} of ${max}`}>
      {Array.from({ length: max }, (_, i) => (
        <i key={i} className={i < value ? 'on' : ''} />
      ))}
    </span>
  )
}
