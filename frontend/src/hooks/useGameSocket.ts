import { useEffect, useRef, useState } from 'react'
import { tokenStore } from '../api/client'

export interface SocketEvent {
  type: string
  game_id?: number
  [key: string]: unknown
}

/**
 * Keeps a WebSocket open for one game and calls `onEvent` for every notification.
 * The socket only notifies; callers refetch state from the REST API. Reconnects with backoff,
 * so a browser refresh or a dropped connection never loses the game.
 */
export function useGameSocket(gameId: number | undefined, onEvent: (event: SocketEvent) => void): boolean {
  const [connected, setConnected] = useState(false)
  const handler = useRef(onEvent)
  handler.current = onEvent

  useEffect(() => {
    if (!gameId) return
    let closed = false
    let socket: WebSocket | null = null
    let retry = 0
    let timer: number | undefined
    let ping: number | undefined

    const connect = () => {
      const token = tokenStore.get()
      if (!token || closed) return
      const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
      socket = new WebSocket(`${scheme}://${window.location.host}/ws/games/${gameId}?token=${encodeURIComponent(token)}`)
      socket.onopen = () => {
        retry = 0
        setConnected(true)
        ping = window.setInterval(() => socket?.readyState === WebSocket.OPEN && socket.send('ping'), 25000)
      }
      socket.onmessage = (message) => {
        try {
          handler.current(JSON.parse(message.data) as SocketEvent)
        } catch {
          /* ignore malformed frames */
        }
      }
      socket.onclose = () => {
        setConnected(false)
        window.clearInterval(ping)
        if (!closed) {
          retry += 1
          timer = window.setTimeout(connect, Math.min(1000 * 2 ** retry, 15000))
        }
      }
    }
    connect()
    return () => {
      closed = true
      window.clearTimeout(timer)
      window.clearInterval(ping)
      socket?.close()
    }
  }, [gameId])

  return connected
}
