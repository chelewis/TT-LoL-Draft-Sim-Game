import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { api } from '../api/client'
import type { NotificationInbox } from '../api/types'
import { useSocket, type SocketEvent } from './useGameSocket'

const KEY = ['notifications']

/** Your inbox. /ws/me says when something new arrives; the slow poll is only a safety net. */
export function useNotifications(enabled = true) {
  const qc = useQueryClient()
  const onEvent = useCallback((event: SocketEvent) => {
    if (event.type === 'PONG') return
    qc.invalidateQueries({ queryKey: KEY })        // NOTIFICATION, or CONNECTED after a reconnect
  }, [qc])
  useSocket(enabled ? '/ws/me' : null, onEvent)
  return useQuery({
    queryKey: KEY,
    queryFn: () => api<NotificationInbox>('/notifications'),
    enabled,
    refetchInterval: 120000,
  })
}

/** Mark some notifications read (no ids: all of them). */
export function useMarkRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids?: number[]) => api<NotificationInbox>('/notifications/read', { body: ids ? { ids } : {} }),
    onSuccess: (inbox) => qc.setQueryData(KEY, inbox),
  })
}
