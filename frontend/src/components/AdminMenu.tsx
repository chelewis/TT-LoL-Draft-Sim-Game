import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { ADMIN_NAV, type AdminLink } from '../pages/admin/nav'

/** The top bar's Admin entry: a button that opens the list of admin pages. */
export function AdminMenu() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const wrap = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)

  useEffect(() => setOpen(false), [pathname])
  useEffect(() => {
    if (!open) return
    const outside = (e: PointerEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open])

  const links = () => Array.from(wrap.current?.querySelectorAll<HTMLAnchorElement>('.admin-menu-panel a') ?? [])
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape' && open) {
      setOpen(false)
      button.current?.focus()
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (!open) return setOpen(true)
      const all = links()
      const at = all.indexOf(document.activeElement as HTMLAnchorElement)
      const next = e.key === 'ArrowDown' ? at + 1 : at - 1
      all[(next + all.length) % all.length]?.focus()
    }
  }

  const link = (item: AdminLink, nested = false) => (
    <li key={item.to}>
      <NavLink to={item.to} className={nested ? 'nested' : undefined} onClick={() => setOpen(false)}>{item.label}</NavLink>
    </li>
  )

  return (
    <div className="admin-menu" ref={wrap} onKeyDown={onKeyDown}>
      <button
        ref={button}
        type="button"
        className={pathname.startsWith('/admin') ? 'active' : ''}
        aria-expanded={open}
        aria-controls="admin-menu-panel"
        onClick={() => setOpen((o) => !o)}
      >
        Admin <span className="admin-menu-caret" aria-hidden="true">▾</span>
      </button>
      {open && (
        <ul id="admin-menu-panel" className="admin-menu-panel">
          {ADMIN_NAV.map((entry) =>
            'items' in entry ? (
              <li key={entry.label}>
                <span className="admin-menu-group" id={`admin-group-${entry.label}`}>{entry.label}</span>
                <ul aria-labelledby={`admin-group-${entry.label}`}>{entry.items.map((item) => link(item, true))}</ul>
              </li>
            ) : (
              link(entry)
            ),
          )}
        </ul>
      )}
    </div>
  )
}
