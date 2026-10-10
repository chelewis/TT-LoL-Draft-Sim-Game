import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { MatchupKind, MatchupMatrix } from '../api/types'
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
