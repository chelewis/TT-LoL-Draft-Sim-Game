import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Champion, ChampionFit, ChampionPair, Coach, MetaChampion, Player, Team, TeamInsights, TeamInsightsRequest } from '../api/types'
import { fetchLatestVersion } from '../lib/ddragon'

/** Every Meta view's query starts with this key, so admin edits to what feeds them can refresh them all. */
export const metaKey = ['meta']

export const useMetaChampions = () =>
  useQuery({ queryKey: [...metaKey, 'champions'], queryFn: () => api<MetaChampion[]>('/meta/champions') })

/** How two champions interact; idle until two different champions are chosen. */
export const useChampionPair = (a: number | null, b: number | null) =>
  useQuery({
    queryKey: [...metaKey, 'pair', a, b],
    queryFn: () => api<ChampionPair>(`/meta/pair?a=${a}&b=${b}`),
    enabled: a !== null && b !== null && a !== b,
    placeholderData: keepPreviousData,
  })

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

/** Every champion ranked by lane fit for (possibly unsaved) stats and pool; keeps the last list while stats change. */
export const useChampionFit = (stats: { aggr: number; aware: number; pos: number; dmg: number }, pool: number[]) =>
  useQuery({
    queryKey: ['champion-fit', stats.aggr, stats.aware, stats.pos, stats.dmg, pool],
    queryFn: () => api<ChampionFit[]>('/champion-fit', {
      body: { aggr: stats.aggr, aware: stats.aware, pos: stats.pos, dmg: stats.dmg, pool, limit: null },
    }),
    placeholderData: keepPreviousData,
  })

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

/** Team notes for the team editor's current (unsaved) choices; keeps the last notes while the next load. */
export const useTeamInsights = (request: TeamInsightsRequest, enabled: boolean) =>
  useQuery({
    queryKey: ['team-insights', request],
    queryFn: () => api<TeamInsights>('/team-insights', { body: request }),
    placeholderData: keepPreviousData,
    enabled,
  })
