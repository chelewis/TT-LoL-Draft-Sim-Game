import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { AdminPlaystyleTag, AdminUser, MatchupKind, MatchupMatrix, PlaystyleOptions, SimulationSettings } from '../api/types'
import { toChanges, type Pending } from '../lib/matchups'

const matchupsKey = (kind: MatchupKind) => ['admin', 'matchups', kind]

export const useMatchups = (kind: MatchupKind) =>
  useQuery({
    queryKey: matchupsKey(kind),
    queryFn: () => api<MatchupMatrix>(`/admin/matchups/${kind}`),
    staleTime: Infinity, // only admins change it, and an edit in progress should not be refetched under them
  })

/** Save unsaved edits. Resolves once the matrix has been reloaded, so the caller can drop its edits without a flicker. */
export function useSaveMatchups(kind: MatchupKind) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (pending: Pending) => {
      await api(`/admin/matchups/${kind}`, { method: 'PUT', body: { changes: toChanges(pending) } })
      await qc.invalidateQueries({ queryKey: matchupsKey(kind) })
    },
  })
}

export function useResetMatchups(kind: MatchupKind) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      await api(`/admin/matchups/${kind}/reset`, { method: 'POST' })
      await qc.invalidateQueries({ queryKey: matchupsKey(kind) })
    },
  })
}

const simulationKey = ['admin', 'simulation']

export const useSimulationSettings = () =>
  useQuery({
    queryKey: simulationKey,
    queryFn: () => api<SimulationSettings>('/admin/simulation'),
    staleTime: Infinity,
  })

/** Both resolve with the settings as saved, which replace the cached ones. */
export function useSaveSimulationSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (values: Record<string, number | boolean>) =>
      api<SimulationSettings>('/admin/simulation', { method: 'PUT', body: { values } }),
    onSuccess: (data) => qc.setQueryData(simulationKey, data),
  })
}

export function useResetSimulationSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api<SimulationSettings>('/admin/simulation/reset', { method: 'POST' }),
    onSuccess: (data) => qc.setQueryData(simulationKey, data),
  })
}

const usersKey = ['admin', 'users']

export const useAdminUsers = () => useQuery({ queryKey: usersKey, queryFn: () => api<AdminUser[]>('/admin/users') })

/** Set a user's password; this also signs them out everywhere. */
export function useResetPassword() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, password }: { userId: number; password: string }) =>
      api(`/admin/users/${userId}/password`, { body: { password } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: usersKey }),
  })
}


// ------------------------------------------------------------ playstyle tags
const playstyleKey = ['admin', 'playstyle-tags']

export const usePlaystyleTags = () =>
  useQuery({ queryKey: playstyleKey, queryFn: () => api<AdminPlaystyleTag[]>('/admin/playstyle-tags') })

export const usePlaystyleOptions = () =>
  useQuery({ queryKey: [...playstyleKey, 'options'], queryFn: () => api<PlaystyleOptions>('/admin/playstyle-tags/options'), staleTime: Infinity })

export type PlaystyleTagBody = Omit<AdminPlaystyleTag, 'id' | 'players'>

/** Create (no id) or update a tag; resolves once the list has been reloaded. */
export function useSavePlaystyleTag() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, body }: { id?: number; body: PlaystyleTagBody }) => {
      const saved = id
        ? await api<AdminPlaystyleTag>(`/admin/playstyle-tags/${id}`, { method: 'PUT', body })
        : await api<AdminPlaystyleTag>('/admin/playstyle-tags', { body })
      await qc.invalidateQueries({ queryKey: playstyleKey })
      return saved
    },
  })
}

export function useDeletePlaystyleTag() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const res = await api<{ deleted: boolean; disabled: boolean; players: number }>(`/admin/playstyle-tags/${id}`, { method: 'DELETE' })
      await qc.invalidateQueries({ queryKey: playstyleKey })
      return res
    },
  })
}
