import { ADMIN_NAV } from '../pages/admin/nav'
import { NavMenu } from './NavMenu'

/** The top bar's Admin entry: a button that opens the list of admin pages. */
export function AdminMenu() {
  return <NavMenu label="Admin" base="/admin" items={ADMIN_NAV} />
}
