import { useEffect, useRef, useState } from 'react'
import { useChat } from '../hooks/useChat'
import { playSound } from '../lib/sound'

const MAX_LENGTH = 200

/** All-chat for champ select: both players, team-coloured names, Enter to send. */
export default function ChatPanel({ gameId, myUserId }: { gameId: number; myUserId: number }) {
  const { messages, loaded, send } = useChat(gameId)
  const [text, setText] = useState('')
  const log = useRef<HTMLOListElement>(null)

  // sound for lines from the opponent that arrive after the history has loaded
  const lastHeard = useRef<number | null>(null)
  useEffect(() => {
    if (!loaded) return
    const newest = messages.reduce((max, m) => Math.max(max, m.id), 0)
    const heard = lastHeard.current
    lastHeard.current = newest
    if (heard !== null && messages.some((m) => m.id > heard && m.user_id !== myUserId)) playSound('chatReceive')
  }, [messages, loaded, myUserId])

  // keep the newest line in view
  useEffect(() => {
    const el = log.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages.length])

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const body = text.trim()
    if (!body || send.isPending) return
    send.mutate(body, {
      onSuccess: () => {
        playSound('chatSend')
        setText('')
      },
    })
  }

  return (
    <section className="cs-chat" aria-label="All chat">
      <div className="cs-chat-title">All chat</div>
      <ol className="cs-chat-log" ref={log} aria-live="polite">
        {messages.length === 0 && <li className="cs-chat-empty">Say something to your opponent…</li>}
        {messages.map((m) => (
          <li key={m.id} title={new Date(m.created_at).toLocaleTimeString()}>
            <span className={`cs-chat-name ${m.team.toLowerCase()}`}>
              {m.username}
              {m.user_id === myUserId ? ' (you)' : ''}:
            </span>{' '}
            <span className="cs-chat-body">{m.body}</span>
          </li>
        ))}
      </ol>
      {send.error && <div className="cs-chat-error">{send.error instanceof Error ? send.error.message : 'Could not send.'}</div>}
      <form className="cs-chat-form" onSubmit={submit}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={MAX_LENGTH}
          placeholder="Talk some smack…"
          aria-label="Chat message"
        />
      </form>
    </section>
  )
}
