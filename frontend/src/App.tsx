import { useQueryClient } from '@tanstack/react-query'
import { Link, NavLink, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { AdminMenu } from './components/AdminMenu'
import { NavMenu } from './components/NavMenu'
import { NotificationBell } from './components/NotificationBell'
import { RequireAdmin, RequireAuth } from './components/common'
import AdminPage from './pages/admin/AdminPage'
import GamePage from './pages/GamePage'
import HomePage from './pages/HomePage'
import JoinPage from './pages/JoinPage'
import LoginPage from './pages/LoginPage'
import MetaPage from './pages/meta/MetaPage'
import { META_NAV } from './pages/meta/nav'
import RiotImportPage from './pages/RiotImportPage'
import SeriesPage from './pages/SeriesPage'
import SeasonCreatePage from './pages/seasons/SeasonCreatePage'
import SeasonJoinPage from './pages/seasons/SeasonJoinPage'
import SeasonPage from './pages/seasons/SeasonPage'
import SeasonsPage from './pages/seasons/SeasonsPage'
import SeasonTeamPage from './pages/seasons/SeasonTeamPage'
import { CoachesPage, PlayerEditorPage, PlayersPage, TeamEditorPage, TeamsPage } from './pages/ManagementPages'

function Shell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()
  const qc = useQueryClient()
  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">League Draft Manager</Link>
        <nav>
          <NavLink to="/" end>Play</NavLink>
          <NavLink to="/seasons">Seasons</NavLink>
          <NavLink to="/teams">Teams</NavLink>
          <NavLink to="/players">Players</NavLink>
          <NavLink to="/coaches">Coaches</NavLink>
          <NavMenu label="Meta" base="/meta" items={META_NAV} />
          {user?.is_admin && <AdminMenu />}
        </nav>
        <div className="row">
          <NotificationBell />
          <span className="muted small">{user?.username}</span>
          <button className="ghost small" onClick={() => { logout(); qc.clear() }}>Log out</button>
        </div>
      </header>
      <main className="page">{children}</main>
      <footer className="legal">
        League Draft Manager isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone
        officially involved in producing or managing Riot Games properties. Riot Games and all associated properties are
        trademarks or registered trademarks of Riot Games, Inc.
      </footer>
    </>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="*"
        element={
          <RequireAuth>
            <Shell>
              <Routes>
                <Route path="/" element={<HomePage />} />
                <Route path="/join/:code" element={<JoinPage />} />
                <Route path="/game/:gameId" element={<GamePage />} />
                <Route path="/series/:seriesId" element={<SeriesPage />} />
                <Route path="/seasons" element={<SeasonsPage />} />
                <Route path="/seasons/new" element={<SeasonCreatePage />} />
                <Route path="/seasons/join/:code" element={<SeasonJoinPage />} />
                <Route path="/seasons/:seasonId" element={<SeasonPage />} />
                <Route path="/seasons/:seasonId/teams/:teamId" element={<SeasonTeamPage />} />
                <Route path="/teams" element={<TeamsPage />} />
                <Route path="/teams/new" element={<TeamEditorPage />} />
                <Route path="/teams/:teamId" element={<TeamEditorPage />} />
                <Route path="/players" element={<PlayersPage />} />
                <Route path="/players/import" element={<RiotImportPage />} />
                <Route path="/players/new" element={<PlayerEditorPage />} />
                <Route path="/players/:playerId" element={<PlayerEditorPage />} />
                <Route path="/coaches" element={<CoachesPage />} />
                <Route path="/meta/*" element={<MetaPage />} />
                <Route path="/admin/*" element={<RequireAdmin><AdminPage /></RequireAdmin>} />
                <Route path="*" element={<p className="muted">Page not found.</p>} />
              </Routes>
            </Shell>
          </RequireAuth>
        }
      />
    </Routes>
  )
}
