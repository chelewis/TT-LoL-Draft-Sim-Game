import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import type { AppNotification } from '../api/types'
import { useMarkRead, useNotifications } from '../hooks/useNotifications'
import { timeAgo } from '../lib/season'

const ICONS: Record<AppNotification['kind'], string> = {
  MATCH_READY: '⚔️', OPPONENT_READY: '🟢', AUTO_SIM_ASKED: '🤖', ON_THE_CLOCK: '⏱️', DEADLINE: '⏳',
  SEASON_STARTED: '📋', SEASON_OVER: '🏆', SEASON_JOINED: '👋', SEASON_REMOVED: '🚪',
}

/** The top bar's bell: your unread count, and the inbox under it. Opening a notification marks it read. */
export function NotificationBell() {
  const inbox = useNotifications()
  const markRead = useMarkRead()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)
  const unread = inbox.data?.unread ?? 0

  useEffect(() => setOpen(false), [pathname])
  useEffect(() => {
    if (!open) return
    const outside = (e: PointerEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false) }
    const escape = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  // "(2) League Draft Manager" while something is waiting for you, even in a background tab
  useEffect(() => {
    const base = document.title.replace(/^\(\d+\) /, '')
    document.title = unread ? `(${unread}) ${base}` : base
  }, [unread])

  function openItem(n: AppNotification) {
    if (!n.read) markRead.mutate([n.id])
    setOpen(false)
    if (n.link) navigate(n.link)
  }

  const items = inbox.data?.items ?? []
  return (
    <div className="notif" ref={wrap}>
      <button type="button" className="notif-bell ghost small" aria-expanded={open} aria-haspopup="true"
        aria-label={unread ? `Notifications: ${unread} unread` : 'Notifications'} onClick={() => setOpen((o) => !o)}>
        <span aria-hidden="true">🔔</span>
        {unread > 0 && <span className="notif-count" aria-hidden="true">{unread > 99 ? '99+' : unread}</span>}
      </button>
      {open && (
        <div className="notif-panel" role="dialog" aria-label="Notifications">
          <div className="row between notif-head">
            <strong>Notifications</strong>
            {unread > 0 && (
              <button type="button" className="ghost small" onClick={() => markRead.mutate(undefined)} disabled={markRead.isPending}>
                Mark all read
              </button>
            )}
          </div>
          {items.length === 0 ? (
            <p className="muted small notif-empty">Nothing yet. Season matches, draft picks and deadlines show up here.</p>
          ) : (
            <ul className="notif-list">
              {items.map((n) => (
                <li key={n.id}>
                  <button type="button" className={`notif-item${n.read ? '' : ' unread'}`} onClick={() => openItem(n)}>
                    <span className="notif-icon" aria-hidden="true">{ICONS[n.kind] ?? '•'}</span>
                    <span className="notif-text">
                      <span className="notif-title">{n.title}</span>
                      {n.body && <span className="muted small">{n.body}</span>}
                      <span className="muted small">{timeAgo(n.created_at)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
