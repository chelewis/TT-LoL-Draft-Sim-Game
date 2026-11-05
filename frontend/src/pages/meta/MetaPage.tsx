import { Navigate, Route, Routes } from 'react-router-dom'
import ChampionsMetaPage from './ChampionsMetaPage'
import { META_HOME } from './nav'

/** Layout for the Meta area: read-only views of the state of the game's meta, for every player. Pages are listed in nav.ts. */
export default function MetaPage() {
  return (
    <Routes>
      <Route index element={<Navigate to={META_HOME} replace />} />
      <Route path="champions" element={<ChampionsMetaPage />} />
      <Route path="*" element={<p className="muted">Page not found.</p>} />
    </Routes>
  )
}
