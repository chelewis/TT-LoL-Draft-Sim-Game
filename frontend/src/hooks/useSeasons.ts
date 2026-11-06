import { useQuery, type QueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Season, SeasonSchedule, SeasonSummary, SeasonTeamDetail } from '../api/types'

/** Every season query starts with this key, so one change can refresh the hub, schedule and team pages. */
export const seasonKey = (id: number) => ['season', id]

/** Season pages poll while a season is in play: other matches finish and rounds advance without this tab. */
const POLL_MS = 15000
const live = (status: string | undefined) => status === 'REGULAR' || status === 'PLAYOFFS' || status === 'SETUP'

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
