import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { NavLink, useLocation } from 'react-router-dom'

export interface MenuLink {
  label: string
  to: string
}

export interface MenuGroup {
  label: string
  items: MenuLink[]
}

export type MenuEntry = MenuLink | MenuGroup

/** A top bar entry that opens a list of pages, e.g. Admin or Meta. `base` is the path all its pages live under. */
export function NavMenu({ label, base, items }: { label: string; base: string; items: MenuEntry[] }) {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const wrap = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const id = `nav-menu-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`

  useEffect(() => setOpen(false), [pathname])
  useEffect(() => {
    if (!open) return
    const outside = (e: PointerEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open])

  const links = () => Array.from(wrap.current?.querySelectorAll<HTMLAnchorElement>('.nav-menu-panel a') ?? [])
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

  const link = (item: MenuLink, nested = false) => (
    <li key={item.to}>
      <NavLink to={item.to} className={nested ? 'nested' : undefined} onClick={() => setOpen(false)}>{item.label}</NavLink>
    </li>
  )

  const active = pathname === base || pathname.startsWith(`${base}/`)
  return (
    <div className="nav-menu" ref={wrap} onKeyDown={onKeyDown}>
      <button
        ref={button}
        type="button"
        className={active ? 'active' : ''}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      >
        {label} <span className="nav-menu-caret" aria-hidden="true">▾</span>
      </button>
      {open && (
        <ul id={id} className="nav-menu-panel">
          {items.map((entry) =>
            'items' in entry ? (
              <li key={entry.label}>
                <span className="nav-menu-group" id={`${id}-group-${entry.label}`}>{entry.label}</span>
                <ul aria-labelledby={`${id}-group-${entry.label}`}>{entry.items.map((item) => link(item, true))}</ul>
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
