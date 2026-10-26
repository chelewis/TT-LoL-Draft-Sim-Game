/** The admin area's pages, as shown in the top bar dropdown. A new page is one entry here plus a route in AdminPage. */
export interface AdminLink {
  label: string
  to: string
}

export interface AdminGroup {
  label: string
  items: AdminLink[]
}

export const ADMIN_NAV: (AdminLink | AdminGroup)[] = [
  { label: 'Champions', items: [{ label: 'Winrates', to: '/admin/champions/winrates' }] },
  {
    label: 'Defaults',
    items: [
      { label: 'Teams', to: '/admin/defaults/teams' },
      { label: 'Players', to: '/admin/defaults/players' },
      { label: 'Coaches', to: '/admin/defaults/coaches' },
    ],
  },
  { label: 'Simulation Settings', to: '/admin/simulation' },
  { label: 'Globals', to: '/admin/globals' },
]

export const ADMIN_HOME = '/admin/champions/winrates'

const under = (pathname: string, to: string): boolean => pathname === to || pathname.startsWith(`${to}/`)

/** Labels leading to the page at `pathname`, e.g. ['Champions', 'Winrates']; empty when it is not an admin page. */
export function adminTrail(pathname: string): string[] {
  for (const entry of ADMIN_NAV) {
    if ('items' in entry) {
      const item = entry.items.find((i) => under(pathname, i.to))
      if (item) return [entry.label, item.label]
    } else if (under(pathname, entry.to)) {
      return [entry.label]
    }
  }
  return []
}
