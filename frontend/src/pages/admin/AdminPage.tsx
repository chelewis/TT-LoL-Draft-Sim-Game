import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import GlobalsPage from './GlobalsPage'
import SimulationSettingsPage from './SimulationSettingsPage'
import WinratesPage from './WinratesPage'
import { ADMIN_HOME, adminTrail } from './nav'

/** Layout for the admin area: global config that applies to every player. Pages are listed in nav.ts. */
export default function AdminPage() {
  const { pathname } = useLocation()
  return (
    <div className="stack">
      <p className="admin-crumbs muted small" aria-label="You are here">{['Admin', ...adminTrail(pathname)].join(' / ')}</p>
      <Routes>
        <Route index element={<Navigate to={ADMIN_HOME} replace />} />
        <Route path="champions/winrates/:matrix?" element={<WinratesPage />} />
        <Route path="simulation" element={<SimulationSettingsPage />} />
        <Route path="globals" element={<GlobalsPage />} />
        <Route path="*" element={<p className="muted">Page not found.</p>} />
      </Routes>
    </div>
  )
}
