import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { api } from '../api/client'
import type { Season, SeasonJoinPreview, SeasonPoolPlayer, SeasonSchedule, SeasonSummary, SeasonTeamDetail } from '../api/types'
import { useSocket, type SocketEvent } from './useGameSocket'

/** Every season query starts with this key, so one change can refresh the hub, schedule and team pages. */
export const seasonKey = (id: number) => ['season', id]

/** The season socket says when anything changes; polling is only a safety net while a season is in play. */
const POLL_MS = 60000
const live = (status: string | undefined) =>
  status === 'REGULAR' || status === 'PLAYOFFS' || status === 'SETUP' || status === 'PLAYER_DRAFT'

export const useSeasons = () => useQuery({ queryKey: ['seasons'], queryFn: () => api<SeasonSummary[]>('/seasons') })

export const useSeason = (id: number) =>
  useQuery({
    queryKey: seasonKey(id),
    queryFn: () => api<Season>(`/seasons/${id}`),
    enabled: Number.isFinite(id),
    refetchInterval: (q) => (live(q.state.data?.status) ? POLL_MS : false),
  })

export const useSeasonSchedule = (id: number, enabled = true) =>
  useQuery({
    queryKey: [...seasonKey(id), 'schedule'],
    queryFn: () => api<SeasonSchedule>(`/seasons/${id}/schedule`),
    enabled: enabled && Number.isFinite(id),
  })

export const useSeasonTeam = (id: number, teamId: number) =>
  useQuery({
    queryKey: [...seasonKey(id), 'team', teamId],
    queryFn: () => api<SeasonTeamDetail>(`/seasons/${id}/teams/${teamId}`),
    enabled: Number.isFinite(id) && Number.isFinite(teamId),
  })

/** After a change to a season: store the new hub view and refetch everything else about it. */
export function refreshSeason(qc: QueryClient, season: Season) {
  qc.setQueryData(seasonKey(season.id), season)
  qc.invalidateQueries({ queryKey: seasonKey(season.id) })
  qc.invalidateQueries({ queryKey: ['seasons'] })
}

/** The draft pool, or the free agents once the season is under way (both: season players on no roster). */
export const useSeasonPool = (id: number, enabled = true) =>
  useQuery({
    queryKey: [...seasonKey(id), 'pool'],
    queryFn: () => api<{ players: SeasonPoolPlayer[] }>(`/seasons/${id}/pool`),
    enabled: enabled && Number.isFinite(id),
  })

export const useSeasonInvite = (code: string) =>
  useQuery({ queryKey: ['season-invite', code], queryFn: () => api<SeasonJoinPreview>(`/seasons/join/${code}`), retry: false })

/** Live updates for a season hub: other managers' results, joins and round changes refetch the season. */
export function useSeasonSocket(id: number): boolean {
  const qc = useQueryClient()
  // SEASON_UPDATED, or CONNECTED after a reconnect (something may have changed meanwhile)
  const onEvent = useCallback((event: SocketEvent) => {
    if (event.type === 'PONG') return
    qc.invalidateQueries({ queryKey: seasonKey(id) })
    qc.invalidateQueries({ queryKey: ['seasons'] })
  }, [qc, id])
  return useSocket(Number.isFinite(id) ? `/ws/seasons/${id}` : null, onEvent)
}
