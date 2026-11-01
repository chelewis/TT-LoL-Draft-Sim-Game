import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { CoachesPage, DEFAULTS_SCOPE, PlayerEditorPage, PlayersPage, TeamEditorPage, TeamsPage } from '../ManagementPages'
import GlobalsPage from './GlobalsPage'
import PlaystyleTagsPage from './PlaystyleTagsPage'
import SimulationSettingsPage from './SimulationSettingsPage'
import UsersPage from './UsersPage'
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
        <Route path="defaults/teams" element={<TeamsPage scope={DEFAULTS_SCOPE} />} />
        <Route path="defaults/teams/new" element={<TeamEditorPage scope={DEFAULTS_SCOPE} />} />
        <Route path="defaults/teams/:teamId" element={<TeamEditorPage scope={DEFAULTS_SCOPE} />} />
        <Route path="defaults/players" element={<PlayersPage scope={DEFAULTS_SCOPE} />} />
        <Route path="defaults/players/new" element={<PlayerEditorPage scope={DEFAULTS_SCOPE} />} />
        <Route path="defaults/players/:playerId" element={<PlayerEditorPage scope={DEFAULTS_SCOPE} />} />
        <Route path="defaults/coaches" element={<CoachesPage scope={DEFAULTS_SCOPE} />} />
        <Route path="playstyle-tags" element={<PlaystyleTagsPage />} />
        <Route path="simulation" element={<SimulationSettingsPage />} />
        <Route path="globals" element={<GlobalsPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="*" element={<p className="muted">Page not found.</p>} />
      </Routes>
    </div>
  )
}
