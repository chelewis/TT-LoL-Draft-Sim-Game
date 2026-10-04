import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Champion, Coach, Player, Team } from '../api/types'
import { fetchLatestVersion } from '../lib/ddragon'

export function useChampions() {
  return useQuery({
    queryKey: ['champions'],
    queryFn: () => api<Champion[]>('/champions'),
    staleTime: Infinity,
  })
}

/** Latest Data Dragon version for champion art; null until known (falls back to a pinned version on failure). */
export function useDDragonVersion(): string | null {
  const { data } = useQuery({ queryKey: ['ddragon-version'], queryFn: fetchLatestVersion, staleTime: Infinity, retry: false })
  return data ?? null
}

export function useChampionMap(): Map<number, Champion> {
  const { data } = useChampions()
  return new Map((data ?? []).map((c) => [c.id, c]))
}

export const useTeams = (selectable?: boolean) =>
  useQuery({
    queryKey: ['teams', selectable ?? 'all'],
    queryFn: () => api<Team[]>(`/teams${selectable === undefined ? '' : `?selectable=${selectable}`}`),
  })

export const usePlayers = () => useQuery({ queryKey: ['players'], queryFn: () => api<Player[]>('/players') })

export const useCoaches = () => useQuery({ queryKey: ['coaches'], queryFn: () => api<Coach[]>('/coaches') })

/** Remaining seconds to an ISO timestamp, re-rendering a few times a second. */
import { useEffect, useState } from 'react'
import { remainingSeconds } from '../lib/format'

export function useCountdown(expiresAt: string | null): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!expiresAt) return
    const id = window.setInterval(() => setNow(Date.now()), 250)
    return () => window.clearInterval(id)
  }, [expiresAt])
  return remainingSeconds(expiresAt, now)
}
