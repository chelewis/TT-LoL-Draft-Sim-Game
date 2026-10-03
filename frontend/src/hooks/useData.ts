import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Champion, Coach, Player, Team } from '../api/types'

export function useChampions() {
  return useQuery({
    queryKey: ['champions'],
    queryFn: () => api<Champion[]>('/champions'),
    staleTime: Infinity,
  })
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
