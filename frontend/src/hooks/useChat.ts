import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ChatMessage } from '../api/types'

const chatKey = (gameId: number) => ['chat', gameId]

/** Add a message to the cached chat (from the socket or our own send), ignoring duplicates. */
export function addChatMessage(qc: QueryClient, gameId: number, message: ChatMessage) {
  qc.setQueryData<ChatMessage[]>(chatKey(gameId), (old) =>
    old?.some((m) => m.id === message.id) ? old : [...(old ?? []), message],
  )
}

/** The game's all-chat: history from the server, new lines pushed over the WebSocket. */
export function useChat(gameId: number, enabled = true) {
  const qc = useQueryClient()
  const messages = useQuery({
    queryKey: chatKey(gameId),
    queryFn: () => api<ChatMessage[]>(`/games/${gameId}/chat`),
    enabled,
    // the socket delivers new messages; this only catches up after a dropped connection
    refetchInterval: 30000,
  })
  const send = useMutation({
    mutationFn: (text: string) => api<ChatMessage>(`/games/${gameId}/chat`, { body: { text } }),
    onSuccess: (message) => addChatMessage(qc, gameId, message),
  })
  return { messages: messages.data ?? [], send }
}
